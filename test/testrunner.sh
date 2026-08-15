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
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
TEST_LIST="${AGENT_CANON_TESTLIST:-${SCRIPT_DIR}/testlist.toml}"
ACTIVE_ROUTE="${AGENT_CANON_ACTIVE_ROUTE:-docker}"

exec python3 - "${SOURCE_ROOT}" "${TEST_LIST}" "${ACTIVE_ROUTE}" <<'PY'
from __future__ import annotations

import fnmatch
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
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
TERM_GRACE_NS = 5_000_000_000
TERMINATION_POLL_NS = 250_000_000
CLEANUP_GRACE_NS = 30_000_000_000
RECORD_SCRUB_KEYS = (
    "AGENT_CANON_PARENT_ROOT",
    "AGENT_CANON_PARENT_ROOT_DEV",
    "AGENT_CANON_PARENT_ROOT_INO",
    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_SOURCE_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_CHILD_HANDOFF",
    "AGENT_CANON_CHILD_PURPOSE",
    "AGENT_CANON_HANDOFF_AUDIENCE",
    "AGENT_CANON_FIXTURE_ROLE",
    "AGENT_CANON_DATA_REPOSITORY_ROOT",
    "AGENT_CANON_DATA_REPOSITORY_DEV",
    "AGENT_CANON_DATA_REPOSITORY_INO",
    "AGENT_CANON_DATA_SOURCE_ROOT",
    "AGENT_CANON_DATA_ROOT",
    "PYTHONPATH",
)


class SchemaError(ValueError):
    """Raised when the source test contract is malformed."""


def fail(message: str) -> "NoReturn":
    print(f"testrunner: schema failure: {message}", file=sys.stderr)
    raise SystemExit(2)


def validate_test_command_entrypoint(
    source_root: Path, command: list[str], record_id: object
) -> None:
    """Require every pytest record to use the exact source-owned prefix."""
    if not command:
        return
    pytest_token = any("pytest" in token.casefold() for token in command)
    if pytest_token:
        expected = ("python3", "test/pytest_entrypoint.py")
        if tuple(command[:2]) != expected:
            raise SchemaError(
                f"TEST_COMMAND_ENTRYPOINT_FORBIDDEN: record {record_id!r} must use exact prefix {list(expected)!r}"
            )


def child_environment(
    source_root: Path,
    active_route: str,
    session: Any,
) -> tuple[dict[str, str], Any, Any, Any, Any, Any]:
    """Authenticate the actual parent/source topology and derive child state."""
    try:
        sys.path.insert(0, str(source_root / "tools" / "agent_tools"))
        from parent_root_side_effects import (  # type: ignore[import-not-found]
            ParentRootSideEffectBoundary,
            current_supervisor_issuer,
            recover_v2_stale_sessions,
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
            "AGENT_CANON_FIXTURE_ROLE",
        )
        for key in transient_keys:
            base_env.pop(key, None)
        boundary = ParentRootSideEffectBoundary()
        issuer = current_supervisor_issuer()
        if issuer is None:
            fail("public supervisor issuer unavailable")
        attestation = session.attestation
        parent_root = session.parent_root
        base_env = boundary.session_environment(session, base_env)
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
        recover_v2_stale_sessions(parent_root)
        return (
            base_env,
            boundary,
            attestation,
            runtime_receipt,
            runtime_base_receipt,
            issuer,
        )
    except (ImportError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        fail(f"source root child environment unavailable: {error}")
    raise AssertionError("unreachable")


def record_environment(
    source_root: Path,
    base_environment: dict[str, str],
    boundary: Any,
    attestation: Any,
    runtime_receipt: Any,
    issuer: Any,
    record_id: str,
    horizon: Any,
) -> tuple[dict[str, str], Any, Any]:
    """Issue one authenticated handoff and parent-owned state root per record."""
    record_receipt = boundary.create_parent_owned_temp_directory(
        attestation,
        runtime_receipt.physical_path,
        "public-test-runner-record-base",
        f"record-{record_id}",
    )
    record_root = record_receipt.physical_path
    record_environment_base = dict(base_environment)
    record_environment_base.update(
        {
            "HOME": str(record_root / "home"),
            "TMPDIR": str(record_root / "tmp"),
            "TEMP": str(record_root / "tmp"),
            "TMP": str(record_root / "tmp"),
            "XDG_CACHE_HOME": str(record_root / "cache"),
            "XDG_CONFIG_HOME": str(record_root / "config"),
            "XDG_DATA_HOME": str(record_root / "data"),
            "PYTHONPYCACHEPREFIX": str(record_root / "cache" / "pycache"),
            "AGENT_CANON_RECORD_ROOT": str(record_root),
            "AGENT_CANON_RECORD_ID": record_id,
        }
    )
    for name in ("home", "tmp", "cache", "config"):
        boundary.ensure_parent_owned_directory(
            attestation,
            record_root / name,
            f"public-test-runner-record-{name}",
        )
    child = issuer.issue_child(
        role="record",
        record_id=record_id,
        physical_root=attestation.parent_root,
        now_mono_ns=time.monotonic_ns(),
    )
    validate_child_horizon(child, horizon.run_deadline_mono_ns)
    child_environment = dict(record_environment_base)
    # A broad test record may own nested Git fixtures. Keep the complete
    # parent-confined signed side-effect channel for record-local lifecycle,
    # HOME/TMP/XDG/CARGO, and writer infrastructure effects. Repository/data
    # identity and the host import path are derived only from each physical
    # command CWD or removed by the record-only fixture-direct adapter.
    for key in RECORD_SCRUB_KEYS:
        child_environment.pop(key, None)
    # Replace the supervisor channel with the exact record handoff issued
    # above.  The record process must resolve the capability it was issued;
    # retaining the supervisor handoff would make fixture-direct commands
    # fail closed (or, worse, accidentally retain supervisor authority).
    child_environment["AGENT_CANON_SIDE_EFFECT_PARENT_ROOT"] = (
        child.record.parent_root_realpath
    )
    child_environment["AGENT_CANON_SIDE_EFFECT_HANDOFF"] = child.handoff
    child_environment["AGENT_CANON_SIDE_EFFECT_SESSION_REQUIRED"] = "1"
    # The record retains its private lifecycle receipt and signed channel;
    # explicitly spawned fixture commands use tools/agent_tools/fixture_spawn.py, which
    # removes that channel immediately before the production child starts.
    return child_environment, record_receipt, child


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
    validate_test_command_entrypoint(source_root, command, index)
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


class SupervisorWatchdog:
    """Observe issuer, parent, and active-process health without token mutation."""

    def __init__(
        self,
        issuer: Any,
        active_process: Any = None,
        *,
        clock: Any = time.monotonic_ns,
        wake_event: Any = None,
    ) -> None:
        self.issuer = issuer
        self.active_process = active_process
        self.clock = clock
        self.wake_event = wake_event
        self.stop_event = threading.Event()
        self.failure_event = threading.Event()
        self.failure: BaseException | None = None
        self.thread = threading.Thread(
            target=self._run, name="agent-canon-session-watchdog", daemon=True
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2.0)

    def check_once(self) -> None:
        """Observe one state snapshot and publish the first failure."""
        try:
            session = self.issuer.session
            if session.status != "active":
                raise RuntimeError("supervisor session is not active")
            if self.clock() >= session.expires_mono_ns:
                raise RuntimeError("supervisor session expired")
            if not Path(session.parent_root_realpath).is_dir():
                raise RuntimeError("supervisor parent root is unavailable")
            if self.active_process is not None:
                process = self.active_process()
                if process is not None and process.poll() is None and not process.pid:
                    raise RuntimeError("active process identity is unavailable")
        except BaseException as error:
            self.failure = error
            self.failure_event.set()
            self.stop_event.set()
            if self.wake_event is not None:
                self.wake_event.set()

    def _run(self) -> None:
        while not self.stop_event.wait(TERMINATION_POLL_NS / 1_000_000_000):
            self.check_once()


class HorizonMismatch(RuntimeError):
    """Raised when a parent API returns a child outside the runner horizon."""


def command_deadline(run_deadline_ns: int) -> int:
    """Reserve the fixed cleanup grace from the invocation deadline."""
    return run_deadline_ns - CLEANUP_GRACE_NS


def admit_record(
    run_deadline_ns: int, now_ns: int, *, cleanup_failed: bool = False
) -> bool:
    """Admit a record only while more than cleanup grace remains."""
    return not cleanup_failed and run_deadline_ns - now_ns > CLEANUP_GRACE_NS


def validate_child_horizon(child: Any, run_deadline_ns: int) -> None:
    """Reject a parent-issued child token with a differing immutable expiry."""
    if child.record.expires_mono_ns != run_deadline_ns:
        raise HorizonMismatch("SESSION_HORIZON_MISMATCH")


def terminate_process(
    process: Any,
    *,
    clock: Any = time.monotonic_ns,
    sleep: Any = time.sleep,
) -> bool:
    """Send TERM, wait exactly the five-second grace, then KILL if needed."""
    if process.poll() is not None:
        return False
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    term_deadline_ns = clock() + TERM_GRACE_NS
    while process.poll() is None:
        now_ns = clock()
        if now_ns >= term_deadline_ns:
            break
        sleep(min(TERMINATION_POLL_NS, term_deadline_ns - now_ns) / 1_000_000_000)
    killed = process.poll() is None
    if killed:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()
    return killed


def _run(
    source_root: Path,
    list_path: Path,
    active_route: str,
    session: Any,
    horizon: Any,
) -> int:
    """Validate, select, execute, and report the typed route."""
    if active_route not in ROUTES:
        fail(f"active route must be docker or devcontainer, got {active_route!r}")
    run_deadline_ns = horizon.run_deadline_mono_ns
    selected_count = 0
    failed_count = 0
    active_process: subprocess.Popen[bytes] | None = None
    stop_requested = False
    interrupted_signum: int | None = None
    cleanup_failed = False
    result = 1
    environment: dict[str, str] | None = None
    boundary: Any | None = None
    attestation: Any | None = None
    runtime_receipt: Any | None = None
    runtime_base_receipt: Any | None = None
    issuer: Any | None = None
    watchdog: SupervisorWatchdog | None = None
    control_event = threading.Event()

    def forward_signal(signum: int, _frame: Any) -> None:
        """Stop admission and wake the active lifecycle loop."""
        nonlocal interrupted_signum, stop_requested
        stop_requested = True
        if interrupted_signum is None:
            interrupted_signum = signum
        control_event.set()

    previous_handlers = {
        signum: signal.getsignal(signum)
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
    }
    for signum in previous_handlers:
        signal.signal(signum, forward_signal)
    try:
        records = load_records(source_root, list_path)
        environment, boundary, attestation, runtime_receipt, runtime_base_receipt, issuer = child_environment(
            source_root, active_route, session
        )
        watchdog = SupervisorWatchdog(issuer, lambda: active_process, wake_event=control_event)
        watchdog.start()
        for record in records:
            if stop_requested or watchdog.failure is not None or cleanup_failed:
                break
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
            if not admit_record(run_deadline_ns, time.monotonic_ns(), cleanup_failed=cleanup_failed):
                print(
                    f"testrunner: record {record['id']!r} not admitted; "
                    "invocation cleanup grace is exhausted",
                    file=sys.stderr,
                )
                result = 1
                break
            selected_count += 1
            emit({**common, "status": "start", "exit_code": None})
            record_environment_value: dict[str, str] | None = None
            record_receipt: Any | None = None
            record_child: Any | None = None
            termination_reason = "normal_exit"
            exit_code = 1
            try:
                record_environment_value, record_receipt, record_child = record_environment(
                    source_root,
                    environment,
                    boundary,
                    attestation,
                    runtime_receipt,
                    issuer,
                    record["id"],
                    horizon,
                )
                if stop_requested or watchdog.failure is not None:
                    termination_reason = "signal" if stop_requested else "parent_changed"
                    exit_code = 128 + (interrupted_signum or signal.SIGTERM) if stop_requested else 1
                elif time.monotonic_ns() >= command_deadline(run_deadline_ns):
                    termination_reason = "timeout"
                    exit_code = 124
                else:
                    process = subprocess.Popen(
                        argv,
                        cwd=source_root,
                        env=record_environment_value,
                        start_new_session=True,
                        stdout=sys.stderr,
                        stderr=sys.stderr,
                    )
                    active_process = process
                    while process.poll() is None:
                        if stop_requested:
                            termination_reason = "signal"
                            terminate_process(process)
                            break
                        if watchdog.failure is not None:
                            termination_reason = "parent_changed"
                            terminate_process(process)
                            break
                        if time.monotonic_ns() >= command_deadline(run_deadline_ns):
                            termination_reason = "timeout"
                            terminate_process(process)
                            break
                        control_event.wait(TERMINATION_POLL_NS / 1_000_000_000)
                        control_event.clear()
                    exit_code = process.wait()
                    if termination_reason == "signal" and exit_code == 0:
                        exit_code = 128 + (interrupted_signum or signal.SIGTERM)
                    elif termination_reason == "parent_changed" and exit_code == 0:
                        exit_code = 1
            except HorizonMismatch as error:
                print(f"testrunner: parent session horizon rejected: {error}", file=sys.stderr)
                exit_code = 1
            except OSError as error:
                print(f"testrunner: command start failed: {error}", file=sys.stderr)
                exit_code = 127
            except Exception as error:
                detail = str(error)
                if "horizon_mismatch" in detail.lower() or "session_horizon_mismatch" in detail.lower():
                    print(f"testrunner: parent session horizon rejected: {error}", file=sys.stderr)
                else:
                    print(f"testrunner: record execution failed: {error}", file=sys.stderr)
                exit_code = 1
            finally:
                active_process = None
                if record_child is not None and issuer is not None:
                    try:
                        drain = issuer.revoke_drain_child(
                            child=record_child.child,
                            reason=termination_reason,
                            now_mono_ns=time.monotonic_ns(),
                        )
                        if drain.leases_after != 0:
                            raise RuntimeError("record session leases remain after drain")
                    except Exception as error:
                        cleanup_failed = True
                        print(f"testrunner: record session cleanup failed: {error}", file=sys.stderr)
                if record_receipt is not None and record_receipt.physical_path.exists():
                    try:
                        boundary.remove_parent_owned_tree(
                            attestation,
                            record_receipt,
                            "public-test-runner-record-cleanup",
                        )
                    except Exception as error:
                        cleanup_failed = True
                        print(f"testrunner: record cleanup failed: {error}", file=sys.stderr)
            status = "pass" if exit_code == 0 and not cleanup_failed else "fail"
            if status == "fail":
                failed_count += 1
            emit({**common, "status": status, "exit_code": exit_code})
            if cleanup_failed:
                print("testrunner: cleanup_failed; later records are not admitted", file=sys.stderr)
                break
        if watchdog is not None and watchdog.failure is not None:
            print(f"testrunner: supervisor watchdog failed: {watchdog.failure}", file=sys.stderr)
            result = 1
        elif interrupted_signum is not None:
            result = 128 + interrupted_signum
        elif selected_count == 0:
            print(
                f"testrunner: active route {active_route!r} selected no test records",
                file=sys.stderr,
            )
            result = 1
        else:
            result = 0 if failed_count == 0 and not cleanup_failed else 1
    finally:
        if watchdog is not None:
            watchdog.stop()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        if active_process is not None and active_process.poll() is None:
            try:
                terminate_process(active_process)
            except (OSError, ProcessLookupError):
                cleanup_failed = True
        if boundary is not None and attestation is not None:
            if runtime_receipt is not None and runtime_receipt.physical_path.exists():
                try:
                    boundary.remove_parent_owned_tree(
                        attestation,
                        runtime_receipt,
                        "public-test-runner-cleanup",
                    )
                except Exception as error:
                    cleanup_failed = True
                    print(f"testrunner: runtime cleanup failed: {error}", file=sys.stderr)
            if runtime_base_receipt is not None:
                try:
                    boundary.remove_empty_parent_owned_directory(
                        attestation,
                        runtime_base_receipt,
                        "public-test-runner-runtime-base-cleanup",
                    )
                except Exception as error:
                    cleanup_failed = True
                    print(f"testrunner: runtime-base cleanup failed: {error}", file=sys.stderr)
    return 1 if cleanup_failed else result


def run(source_root: Path, list_path: Path, active_route: str) -> int:
    """Bootstrap the fixed runner session, then execute typed test records."""
    sys.path.insert(0, str(source_root / "tools" / "agent_tools"))
    import parent_root_side_effects as parent_side_effects  # type: ignore[import-not-found]

    with parent_side_effects._open_runner_session(
        parent_side_effects._RUNNER_CALLER_MARKER,
        source_root / "test" / "testrunner.sh",
    ) as (session, horizon):
        return _run(source_root, list_path, active_route, session, horizon)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        fail("internal invocation requires source root, test list, and active route")
    sys.exit(run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3]))
PY
