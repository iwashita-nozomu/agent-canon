#!/usr/bin/env bash
# @dependency-start
# contract test
# responsibility Runs the source-owned typed AgentCanon test contract in Docker or Dev Container mode.
# upstream design ../CONTAINER_OPERATIONS.md public standalone test boundary
# upstream design ../documents/runtime/shared-runtime-surfaces.toml retired parent test projections
# upstream design ../responsibility-scope.toml source responsibility scopes
# upstream implementation ./testlist.toml typed command records
# upstream implementation ../tools/agent_tools/parent_root_side_effects.py canonical child environment
# downstream implementation ../tests/tools/test_testrunner_schema.py schema and failure-semantics tests
# downstream implementation ../tests/tools/test_testrunner.py route and receipt tests
# @dependency-end
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SOURCE_ROOT="${AGENT_CANON_SOURCE_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd -P)}"
TEST_LIST="${AGENT_CANON_TESTLIST:-${SCRIPT_DIR}/testlist.toml}"
ACTIVE_ROUTE="${AGENT_CANON_ACTIVE_ROUTE:-docker}"

exec python3 - "${SOURCE_ROOT}" "${TEST_LIST}" "${ACTIVE_ROUTE}" <<'PY'
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Docker installs tomli for Python < 3.11.
    import tomli as tomllib  # type: ignore[no-redef]


SCHEMA_FIELDS = {
    "id",
    "environment",
    "require",
    "code_owner",
    "responsibility_scope",
    "command",
}
ENVIRONMENTS = {"tooling", "product"}
ROUTES = {"docker", "devcontainer"}
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
RECORD_IDENTITY_KEYS = (
    "AGENT_CANON_PARENT_ROOT",
    "AGENT_CANON_PARENT_ROOT_DEV",
    "AGENT_CANON_PARENT_ROOT_INO",
    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_SOURCE_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_CHILD_HANDOFF",
    "AGENT_CANON_CHILD_PURPOSE",
    "AGENT_CANON_HANDOFF_AUDIENCE",
)


class SchemaError(ValueError):
    """Raised when the source test contract is malformed."""


def fail(message: str) -> "NoReturn":
    print(f"testrunner: schema failure: {message}", file=sys.stderr)
    raise SystemExit(2)


def child_environment(
    source_root: Path,
    active_route: str,
) -> tuple[dict[str, str], Any, Any, Path]:
    """Authenticate the actual parent/source topology and derive child state."""
    try:
        sys.path.insert(0, str(source_root / "tools" / "agent_tools"))
        from parent_root_side_effects import (  # type: ignore[import-not-found]
            ParentRootAttestationRequest,
            ParentRootSideEffectBoundary,
        )

        base_env = os.environ.copy()
        transient_keys = (
            "TMPDIR",
            "TEMP",
            "TMP",
            "XDG_CACHE_HOME",
            "PYTHONPYCACHEPREFIX",
            "AGENT_CANON_TOOLS_HOME",
            "CARGO_HOME",
            "CARGO_TARGET_DIR",
            "AGENT_CANON_CLI_TARGET_DIR",
            "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
            "AGENT_CANON_PARENT_ROOT",
            "AGENT_CANON_PARENT_ROOT_DEV",
            "AGENT_CANON_PARENT_ROOT_INO",
            "AGENT_CANON_SOURCE_ROOT",
            "AGENT_CANON_ROOT",
            "AGENT_CANON_CHILD_HANDOFF",
            "AGENT_CANON_HANDOFF_AUDIENCE",
            "AGENT_CANON_CHILD_PURPOSE",
        )
        for key in transient_keys:
            base_env.pop(key, None)
        configured_parent = os.environ.get("AGENT_CANON_PARENT_ROOT", "").strip()
        if configured_parent:
            parent_root = Path(configured_parent).resolve()
        else:
            # The public image has /opt/agent-canon-parent/vendor/agent-canon.
            # Resolve through Git so host/devcontainer callers may use the
            # same runner from a nested checkout without synthetic roots.
            candidate = (source_root / "../..").resolve()
            parent_root = Path(
                subprocess.check_output(
                    ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
                    text=True,
                ).strip()
            ).resolve()
        if not source_root.is_relative_to(parent_root):
            fail(
                "source root must be contained by the authenticated parent root: "
                f"source={source_root} parent={parent_root}"
            )
        boundary = ParentRootSideEffectBoundary()
        previous_active_root = os.environ.get("AGENT_CANON_ACTIVE_REPOSITORY_ROOT")
        os.environ["AGENT_CANON_ACTIVE_REPOSITORY_ROOT"] = str(parent_root)
        try:
            attestation = boundary.attest(
                ParentRootAttestationRequest(
                    cwd=parent_root,
                    explicit_root=parent_root,
                    source_root=source_root,
                    purpose="public-test-runner",
                )
            )
        finally:
            if previous_active_root is None:
                os.environ.pop("AGENT_CANON_ACTIVE_REPOSITORY_ROOT", None)
            else:
                os.environ["AGENT_CANON_ACTIVE_REPOSITORY_ROOT"] = previous_active_root
        runtime_base = parent_root / ".agent-canon" / "runtime"
        runtime_base_receipt = boundary.ensure_parent_owned_directory(
            attestation,
            runtime_base,
            "public-test-runner-runtime-base",
        )
        runtime_receipt = boundary.create_parent_owned_temp_directory(
            attestation,
            runtime_base_receipt.physical_path,
            "public-test-runner-runtime",
            "testrunner",
        )
        runtime_root = runtime_receipt.physical_path
        image_runtime_root = parent_root / ".agent-canon" / "image-runtime"
        for relative, purpose in (
            ("home", "child-HOME"),
            ("config", "child-XDG-CONFIG-HOME"),
            ("data", "child-XDG-DATA-HOME"),
        ):
            boundary.ensure_parent_owned_directory(
                attestation,
                runtime_root / relative,
                purpose,
            )
        base_env.update(
            {
                "HOME": str(runtime_root / "home"),
                "TMPDIR": str(runtime_root / "tmp"),
                "TEMP": str(runtime_root / "tmp"),
                "TMP": str(runtime_root / "tmp"),
                "XDG_CACHE_HOME": str(runtime_root / "cache"),
                "XDG_CONFIG_HOME": str(runtime_root / "config"),
                "XDG_DATA_HOME": str(runtime_root / "data"),
                "PYTHONPYCACHEPREFIX": str(runtime_root / "cache" / "pycache"),
                "AGENT_CANON_TOOLS_HOME": str(image_runtime_root / "tools"),
                "CARGO_HOME": str(runtime_root / "cargo-home"),
                "CARGO_TARGET_DIR": str(image_runtime_root / "cargo-target"),
                "AGENT_CANON_CLI_TARGET_DIR": str(
                    image_runtime_root / "cargo-target"
                ),
            }
        )
        record_env = boundary.child_environment(
            attestation,
            base_env=base_env,
            issue_handoff=False,
        )
        # The parent capability owns only runner side effects.  A test record
        # must resolve its own repository from its cwd, especially when the
        # record launches a temporary fixture subprocess.  Keep the
        # parent-owned tools selector above; remove all identity and handoff
        # claims added by the generic boundary from the record environment.
        for key in RECORD_IDENTITY_KEYS:
            record_env.pop(key, None)
        return (
            record_env,
            boundary,
            attestation,
            runtime_receipt,
            runtime_base_receipt,
        )
    except (ImportError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        fail(f"source root child environment unavailable: {error}")
    raise AssertionError("unreachable")


def load_scopes(source_root: Path) -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    """Read declared responsibility scope identifiers and path patterns."""
    manifest_path = source_root / "responsibility-scope.toml"
    if not manifest_path.is_file():
        raise SchemaError("responsibility-scope.toml is missing")
    with manifest_path.open("rb") as handle:
        data = tomllib.load(handle)
    raw_scopes = data.get("scope")
    if not isinstance(raw_scopes, list) or not raw_scopes:
        raise SchemaError("responsibility-scope.toml has no [[scope]] records")
    scopes: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for index, raw_scope in enumerate(raw_scopes):
        if not isinstance(raw_scope, dict) or not isinstance(raw_scope.get("id"), str):
            raise SchemaError(f"scope record {index} has no string id")
        scope_id = raw_scope["id"]
        raw_paths = raw_scope.get("paths", [])
        raw_excludes = raw_scope.get("exclude_paths", [])
        if not isinstance(raw_paths, list) or not all(
            isinstance(path, str) and path for path in raw_paths
        ):
            raise SchemaError(f"scope record {index} paths must be non-empty strings")
        if not isinstance(raw_excludes, list) or not all(
            isinstance(path, str) and path for path in raw_excludes
        ):
            raise SchemaError(f"scope record {index} exclude_paths must be strings")
        if scope_id in scopes:
            raise SchemaError(f"duplicate responsibility scope: {scope_id}")
        scopes[scope_id] = (tuple(raw_paths), tuple(raw_excludes))
    return scopes


def validate_relative_owner(source_root: Path, value: object, index: int) -> str:
    """Validate a source-Git-root-relative owner path."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SchemaError(f"record {index} code_owner must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
        raise SchemaError(f"record {index} code_owner must be source-relative: {value!r}")
    owner = source_root.joinpath(*path.parts)
    if not owner.exists():
        raise SchemaError(f"record {index} code_owner does not exist: {value!r}")
    return path.as_posix()


def scope_matches(path: str, pattern: str) -> bool:
    """Match both a scoped path and its declared directory root."""
    if fnmatch.fnmatch(path, pattern):
        return True
    if pattern.endswith("/**"):
        root = pattern[:-3].rstrip("/")
        return path == root or path.startswith(f"{root}/")
    return False


def validate_record(
    source_root: Path,
    raw: object,
    index: int,
    scopes: dict[str, tuple[tuple[str, ...], tuple[str, ...]]],
) -> dict[str, Any]:
    """Validate one typed TOML test record without executing its command."""
    if not isinstance(raw, dict):
        raise SchemaError(f"record {index} must be a table")
    unknown = sorted(set(raw) - SCHEMA_FIELDS)
    missing = sorted(SCHEMA_FIELDS - set(raw))
    if unknown:
        raise SchemaError(f"record {index} has unsupported fields: {','.join(unknown)}")
    if missing:
        raise SchemaError(f"record {index} is missing fields: {','.join(missing)}")

    test_id = raw["id"]
    if not isinstance(test_id, str) or not ID_PATTERN.fullmatch(test_id):
        raise SchemaError(f"record {index} id is invalid")
    environment = raw["environment"]
    if not isinstance(environment, str) or environment not in ENVIRONMENTS:
        raise SchemaError(f"record {index} environment must be tooling or product")
    require = raw["require"]
    if not isinstance(require, str) or require not in ROUTES:
        raise SchemaError(f"record {index} require must be docker or devcontainer")
    code_owner = validate_relative_owner(source_root, raw["code_owner"], index)
    scope = raw["responsibility_scope"]
    if not isinstance(scope, str) or not scope or "\x00" in scope:
        raise SchemaError(f"record {index} responsibility_scope must be non-empty")
    if scope not in scopes:
        raise SchemaError(f"record {index} responsibility_scope is undeclared: {scope!r}")
    scope_paths, scope_excludes = scopes[scope]
    if scope_paths and not any(scope_matches(code_owner, pattern) for pattern in scope_paths):
        raise SchemaError(
            f"record {index} code_owner is outside responsibility_scope {scope!r}"
        )
    if any(scope_matches(code_owner, pattern) for pattern in scope_excludes):
        raise SchemaError(
            f"record {index} code_owner is excluded by responsibility_scope {scope!r}"
        )

    command = raw["command"]
    if not isinstance(command, list) or not command:
        raise SchemaError(f"record {index} command must be a non-empty token array")
    if any(not isinstance(token, str) or not token or "\x00" in token for token in command):
        raise SchemaError(f"record {index} command tokens must be non-empty NUL-free strings")
    return {
        "id": test_id,
        "environment": environment,
        "require": require,
        "code_owner": code_owner,
        "responsibility_scope": scope,
        "command": command,
    }


def load_records(source_root: Path, list_path: Path) -> list[dict[str, Any]]:
    """Load and validate every record before any command starts."""
    try:
        with list_path.open("rb") as handle:
            data = tomllib.load(handle)
        if not isinstance(data, dict) or set(data) != {"tests"}:
            raise SchemaError("top-level schema must contain only [[tests]]")
        raw_tests = data["tests"]
        if not isinstance(raw_tests, list) or not raw_tests:
            raise SchemaError("test list must contain at least one [[tests]] record")
        scopes = load_scopes(source_root)
        records = [
            validate_record(source_root, raw, index, scopes)
            for index, raw in enumerate(raw_tests)
        ]
        ids = [record["id"] for record in records]
        duplicates = sorted({test_id for test_id in ids if ids.count(test_id) > 1})
        if duplicates:
            raise SchemaError(f"duplicate test ids: {','.join(duplicates)}")
        return records
    except (OSError, tomllib.TOMLDecodeError, SchemaError) as error:
        fail(str(error))
    raise AssertionError("unreachable")


def emit(record: dict[str, Any]) -> None:
    """Emit one deterministic JSONL evidence record."""
    print(
        json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        flush=True,
    )


def run(source_root: Path, list_path: Path, active_route: str) -> int:
    """Validate, select, execute, and report the typed route."""
    if active_route not in ROUTES:
        fail(f"active route must be docker or devcontainer, got {active_route!r}")
    records = load_records(source_root, list_path)
    environment, boundary, attestation, runtime_receipt, runtime_base_receipt = child_environment(
        source_root, active_route
    )
    selected_count = 0
    failed_count = 0
    try:
        for record in records:
            argv = list(record["command"])
            common = {
                "id": record["id"],
                "argv": argv,
                "environment": record["environment"],
                "require": record["require"],
                "active_route": active_route,
                "code_owner": record["code_owner"],
                "responsibility_scope": record["responsibility_scope"],
            }
            if record["require"] != active_route:
                emit({**common, "status": "not_selected", "exit_code": None})
                continue
            selected_count += 1
            emit({**common, "status": "start", "exit_code": None})
            try:
                process = subprocess.Popen(
                    argv,
                    cwd=source_root,
                    env=environment,
                    stdout=sys.stderr,
                    stderr=sys.stderr,
                )
                exit_code = process.wait()
            except OSError as error:
                print(f"testrunner: command start failed: {error}", file=sys.stderr)
                exit_code = 127
            status = "pass" if exit_code == 0 else "fail"
            if status == "fail":
                failed_count += 1
            emit({**common, "status": status, "exit_code": exit_code})
        if selected_count == 0:
            print(
                f"testrunner: active route {active_route!r} selected no test records",
                file=sys.stderr,
            )
            return 1
        return 0 if failed_count == 0 else 1
    finally:
        if runtime_receipt.physical_path.exists():
            boundary.remove_parent_owned_tree(
                attestation,
                runtime_receipt,
                "public-test-runner-cleanup",
            )
        boundary.remove_empty_parent_owned_directory(
            attestation,
            runtime_base_receipt,
            "public-test-runner-runtime-base-cleanup",
        )


if __name__ == "__main__":
    if len(sys.argv) != 4:
        fail("internal invocation requires source root, test list, and active route")
    sys.exit(run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3]))
PY
