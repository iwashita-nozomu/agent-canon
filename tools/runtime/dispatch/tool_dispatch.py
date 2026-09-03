#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Dispatches versioned AgentCanon catalog entries through typed tool run without shell evaluation.
# upstream design ../../../documents/design/agent-canon-bootstrap-tool-runtime.md catalog v2 and parity cutover
# upstream design ../../catalog.yaml typed runtime catalog
# downstream implementation ../../bin/agent-canon stable CLI namespace
# downstream implementation ../../../tests/agent_tools/test_tool_dispatch.py dispatcher contract tests
# @dependency-end
"""Run a parity-verified AgentCanon tool from the versioned catalog.

The existing catalog checker owns the legacy catalog shape.  This module owns
the additive runtime descriptor and deliberately uses ``subprocess`` with an
argument vector; catalog ``command`` strings are documentation and are never
interpreted as shell input.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

SCHEMA_VERSION = 2
PARITY_SCHEMA = "agent-canon-tool-parity/v2"
CONTAINER_MARKER = b"agent-canon-tool-container/v1\n"
RUNTIME_MARKER = b"agent-canon-runtime/v1\n"
CONTAINER_MARKER_NAME = ".agent-canon-tool-container"
RUNTIME_MARKER_NAME = ".agent-canon-runtime"
CATALOG_RELATIVE = Path("tools/catalog.yaml")
ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")
ALLOWED_RUNTIMES = frozenset({"python", "rust"})
ALLOWED_PLANES = frozenset({"tool-container"})
ALLOWED_CWDS = frozenset({"source-root", "target-root", "task-root", "explicit"})
ALLOWED_ENVS = frozenset({"allowlisted", "clean"})
ALLOWED_IO = frozenset({"inherited", "captured"})
ALLOWED_EXITS = frozenset({"propagate", "normalize-signal"})
ALLOWED_SIGNALS = frozenset({"propagate", "normalize-signal"})
ALLOWED_EFFECTS = frozenset({"read-only", "external-artifact", "explicit-target-write"})
ALLOWED_OUTPUT_ROOTS = frozenset({"none", "external-runtime", "explicit-target"})
ALLOWED_PARITY = frozenset({"verified", "pending", "legacy"})
ISSUE_SYNC_RECEIPT_OPTIONS = frozenset(
    {
        "--help",
        "--receipt-preflight",
        "--stage-publication-receipt",
        "--record-publication-receipt",
        "--repo",
        "--receipt-number",
        "--receipt-url",
        "--receipt-state",
        "--receipt-action",
        "--receipt-responsibility",
        "--receipt-occurrence-location",
        "--receipt-source-finding-kind",
        "--receipt-timestamp",
        "--checkout-head",
        "--checkout-repository",
    }
)
ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "TZ",
        "TMPDIR",
        "RUST_BACKTRACE",
        "CARGO_TERM_COLOR",
        # These are the only AgentCanon control variables accepted from the
        # parent process.  Never turn an ``AGENT_CANON_*`` prefix into an
        # implicit credential or policy channel.
        "AGENT_CANON_SOURCE_ROOT",
        "AGENT_CANON_ROOT",
        "AGENT_CANON_DISPATCH_ENTRY_ID",
        "AGENT_CANON_DISPATCH_RUNTIME",
        "AGENT_CANON_OUTPUT_ROOT",
        "AGENT_CANON_CONTROL_PARENT_ROOT",
        "AGENT_CANON_RUNTIME_ROOT",
        "AGENT_CANON_TASK_ROOT",
        "AGENT_CANON_TARGET_ROOT",
        "AGENT_CANON_EXPLICIT_CWD",
        "AGENT_CANON_MOUNT_REGISTRY",
        "AGENT_CANON_HOOK_ARCHIVE_DIR",
        "AGENT_CANON_LOG_ROOT",
    }
)
BOOTSTRAP_EXEC_ENV = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "TZ",
        "TMPDIR",
    }
)


class DispatchError(ValueError):
    """A fail-closed catalog or dispatcher error."""

    def __init__(self, code: str, detail: str) -> None:
        """Create an error with a stable machine-readable code."""
        super().__init__(f"TOOL_DISPATCH_ERROR={code}:{detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ToolSpec:
    """The normalized, typed execution contract for one public tool."""

    tool_id: str
    path: str
    runtime: str
    argv: tuple[str, ...]
    execution_plane: str
    cwd_policy: str
    env_policy: str
    stdin_policy: str
    stdout_policy: str
    stderr_policy: str
    exit_policy: str
    signal_policy: str
    side_effect_policy: str
    output_root: str
    written_paths: tuple[str, ...]
    parity: str
    parity_fixture: str

    def inventory_row(self) -> dict[str, object]:
        """Return a stable JSON-compatible inventory row."""
        return {
            "id": self.tool_id,
            "path": self.path,
            "runtime": self.runtime,
            "argv": list(self.argv),
            "execution_plane": self.execution_plane,
            "cwd": self.cwd_policy,
            "env": self.env_policy,
            "stdin": self.stdin_policy,
            "stdout": self.stdout_policy,
            "stderr": self.stderr_policy,
            "exit": self.exit_policy,
            "signal": self.signal_policy,
            "side_effect": self.side_effect_policy,
            "output_root": self.output_root,
            "written_paths": list(self.written_paths),
            "parity": self.parity,
            "parity_fixture": self.parity_fixture,
        }


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    """Require a YAML mapping with string keys."""
    if not isinstance(value, Mapping) or not all(isinstance(k, str) for k in value):
        raise DispatchError("invalid-type", field)
    return value  # type: ignore[return-value]


def _string(value: object, *, field: str) -> str:
    """Require a non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise DispatchError("invalid-type", field)
    return value


def _enum(value: object, allowed: frozenset[str], *, field: str) -> str:
    """Require an allowed string enum value."""
    result = _string(value, field=field)
    if result not in allowed:
        raise DispatchError("invalid-value", f"{field}={result}")
    return result


def _string_list(value: object, *, field: str) -> tuple[str, ...]:
    """Require an argument vector, never a shell command string."""
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise DispatchError("shell-string-rejected", field)
    result = tuple(value)
    if not result or any(not isinstance(item, str) or not item for item in result):
        raise DispatchError("invalid-argv", field)
    if any("\x00" in item for item in result):
        raise DispatchError("invalid-argv", field)
    return result


def _safe_relative(value: str, *, field: str) -> str:
    """Reject path traversal and absolute paths in catalog data."""
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise DispatchError("unsafe-path", f"{field}={value}")
    return value


def _relative_list(value: object, *, field: str) -> tuple[str, ...]:
    """Normalize the declared written-path set without accepting globs."""
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise DispatchError("invalid-written-paths", field)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or "*" in item:
            raise DispatchError("invalid-written-paths", field)
        result.append(_safe_relative(item, field=field))
    return tuple(result)


def _is_public_path(path: str) -> bool:
    """Return whether a catalog path is a public Python or Rust surface."""
    return path.endswith(".py") or path.endswith(".rs") or path == "tools/bin/agent-canon"


def _runtime_for(path: str) -> str:
    """Classify a public path without turning shell helpers into public tools."""
    return "rust" if path.endswith(".rs") or path == "tools/bin/agent-canon" else "python"


def _spec_from_entry(
    entry: Mapping[str, object],
    runtime_schema: Mapping[str, object],
) -> ToolSpec | None:
    """Normalize one catalog entry, or skip non-Python/Rust support entries."""
    raw_id = entry.get("id")
    raw_path = entry.get("path")
    if not isinstance(raw_id, str) or not raw_id or any(ch not in ID_CHARS for ch in raw_id):
        raise DispatchError("invalid-id", str(raw_id))
    if not isinstance(raw_path, str):
        raise DispatchError("invalid-path", raw_id)
    path = _safe_relative(raw_path, field=f"entry:{raw_id}:path")
    if not _is_public_path(path):
        return None
    explicit = entry.get("dispatch")
    if explicit is None:
        raise DispatchError("missing-dispatch", raw_id)
    dispatch = _mapping(explicit, field=f"entry:{raw_id}:dispatch")
    runtime = _enum(dispatch.get("runtime", _runtime_for(path)), ALLOWED_RUNTIMES, field=f"entry:{raw_id}:runtime")
    argv = _string_list(dispatch.get("argv"), field=f"entry:{raw_id}:argv")
    plane = _enum(dispatch.get("execution_plane", "tool-container"), ALLOWED_PLANES, field=f"entry:{raw_id}:execution_plane")
    cwd = _enum(dispatch.get("cwd", "source-root"), ALLOWED_CWDS, field=f"entry:{raw_id}:cwd")
    env = _enum(dispatch.get("env", "allowlisted"), ALLOWED_ENVS, field=f"entry:{raw_id}:env")
    stdin = _enum(dispatch.get("stdin", "inherited"), ALLOWED_IO, field=f"entry:{raw_id}:stdin")
    stdout = _enum(dispatch.get("stdout", "inherited"), ALLOWED_IO, field=f"entry:{raw_id}:stdout")
    stderr = _enum(dispatch.get("stderr", "inherited"), ALLOWED_IO, field=f"entry:{raw_id}:stderr")
    exit_policy = _enum(dispatch.get("exit", "propagate"), ALLOWED_EXITS, field=f"entry:{raw_id}:exit")
    signal_policy = _enum(dispatch.get("signal", "propagate"), ALLOWED_SIGNALS, field=f"entry:{raw_id}:signal")
    writes = entry.get("writes") is True
    effect = _enum(
        dispatch.get("side_effect", "external-artifact" if writes else "read-only"),
        ALLOWED_EFFECTS,
        field=f"entry:{raw_id}:side_effect",
    )
    output = _enum(
        dispatch.get("output_root", "external-runtime" if writes else "none"),
        ALLOWED_OUTPUT_ROOTS,
        field=f"entry:{raw_id}:output_root",
    )
    written_paths = _relative_list(
        dispatch.get("written_paths", entry.get("written_paths", ())),
        field=f"entry:{raw_id}:written_paths",
    )
    if effect == "read-only" and written_paths:
        raise DispatchError("read-only-written-paths", raw_id)
    if effect == "external-artifact" and output != "external-runtime":
        raise DispatchError("output-root-mismatch", raw_id)
    if effect == "explicit-target-write" and output != "explicit-target":
        raise DispatchError("output-root-mismatch", raw_id)
    if effect == "read-only" and output != "none":
        raise DispatchError("output-root-mismatch", raw_id)
    default_parity = runtime_schema.get("default_parity", "legacy")
    parity = _enum(dispatch.get("parity", default_parity), ALLOWED_PARITY, field=f"entry:{raw_id}:parity")
    fixture = dispatch.get("parity_fixture", runtime_schema.get("parity_fixture", ""))
    fixture_value = _safe_relative(_string(fixture, field=f"entry:{raw_id}:parity_fixture"), field=f"entry:{raw_id}:parity_fixture")
    return ToolSpec(
        tool_id=raw_id,
        path=path,
        runtime=runtime,
        argv=argv,
        execution_plane=plane,
        cwd_policy=cwd,
        env_policy=env,
        stdin_policy=stdin,
        stdout_policy=stdout,
        stderr_policy=stderr,
        exit_policy=exit_policy,
        signal_policy=signal_policy,
        side_effect_policy=effect,
        output_root=output,
        written_paths=written_paths,
        parity=parity,
        parity_fixture=fixture_value,
    )


def load_specs(root: Path) -> tuple[dict[str, ToolSpec], Mapping[str, object]]:
    """Load and validate all public catalog descriptors."""
    root = root.resolve()
    catalog_path = root / CATALOG_RELATIVE
    if not catalog_path.is_file():
        raise DispatchError("missing-catalog", str(catalog_path))
    try:
        raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DispatchError("invalid-catalog", str(error)) from error
    catalog = _mapping(raw, field="catalog")
    schema = _mapping(catalog.get("runtime_schema"), field="runtime_schema")
    version = schema.get("version")
    if version != SCHEMA_VERSION:
        raise DispatchError("unsupported-schema", str(version))
    raw_entries = catalog.get("entries")
    if isinstance(raw_entries, (str, bytes)) or not isinstance(raw_entries, Sequence):
        raise DispatchError("invalid-entries", "entries")
    specs: dict[str, ToolSpec] = {}
    for index, raw_entry in enumerate(raw_entries, start=1):
        entry = _mapping(raw_entry, field=f"entries[{index}]")
        spec = _spec_from_entry(entry, schema)
        if spec is None:
            continue
        if spec.tool_id in specs:
            raise DispatchError("duplicate-id", spec.tool_id)
        specs[spec.tool_id] = spec
    raw_rust_commands = schema.get("rust_public_commands", ())
    if isinstance(raw_rust_commands, (str, bytes)) or not isinstance(raw_rust_commands, Sequence):
        raise DispatchError("invalid-rust-inventory", "runtime_schema.rust_public_commands")
    for index, raw_command in enumerate(raw_rust_commands, start=1):
        command = dict(_mapping(raw_command, field=f"rust_public_commands[{index}]"))
        identifier = _string(command.get("id"), field=f"rust_public_commands[{index}].id")
        selector = _string(command.get("selector"), field=f"rust_public_commands[{index}].selector")
        if any(char.isspace() for char in selector):
            raise DispatchError("invalid-rust-selector", identifier)
        command["dispatch"] = {"argv": ["tools/bin/agent-canon", selector]}
        command["runtime"] = "rust"
        spec = _spec_from_entry(command, schema)
        if spec is None:
            raise DispatchError("invalid-rust-inventory", identifier)
        if spec.tool_id in specs:
            raise DispatchError("duplicate-id", spec.tool_id)
        specs[spec.tool_id] = spec
    if not specs:
        raise DispatchError("empty-inventory", "public Python/Rust commands")
    return specs, schema


def _check_parity_fixture(root: Path, spec: ToolSpec) -> None:
    """Require an exact measured route record before a descriptor cuts over."""
    if spec.parity != "verified":
        raise DispatchError("legacy-route", f"{spec.tool_id}:{spec.parity}")
    fixture_path = root / spec.parity_fixture
    if not fixture_path.is_file():
        raise DispatchError("missing-parity-fixture", f"{spec.tool_id}:{spec.parity_fixture}")
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DispatchError("invalid-parity-fixture", f"{spec.tool_id}:{error}") from error
    if not isinstance(payload, Mapping) or payload.get("schema") != PARITY_SCHEMA:
        raise DispatchError("invalid-parity-fixture", f"{spec.tool_id}:schema")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise DispatchError("invalid-parity-fixture", f"{spec.tool_id}:entries")
    row = next((row for row in entries if isinstance(row, Mapping) and row.get("id") == spec.tool_id), None)
    if row is None:
        raise DispatchError("parity-not-recorded", spec.tool_id)
    expected: dict[str, object] = {
        "argv": list(spec.argv),
        "cwd": spec.cwd_policy,
        "stdin": spec.stdin_policy,
        "stdout": spec.stdout_policy,
        "stderr": spec.stderr_policy,
        "exit": spec.exit_policy,
        "signal": spec.signal_policy,
        "written_paths": list(spec.written_paths),
    }
    observed = row.get("observed", row)
    if not isinstance(observed, Mapping):
        raise DispatchError("invalid-parity-fixture", f"{spec.tool_id}:observed")
    missing = sorted(key for key in expected if key not in observed)
    if missing:
        raise DispatchError("parity-incomplete", f"{spec.tool_id}:{','.join(missing)}")
    for key, value in expected.items():
        if observed.get(key) != value:
            raise DispatchError(
                "parity-mismatch",
                f"{spec.tool_id}:{key}:expected={value!r}:observed={observed.get(key)!r}",
            )
    probe_args = row.get("probe_args")
    if (
        isinstance(probe_args, (str, bytes))
        or not isinstance(probe_args, list)
        or any(not isinstance(item, str) or "\x00" in item for item in probe_args)
    ):
        raise DispatchError("parity-incomplete", f"{spec.tool_id}:probe_args")
    result_fields = {
        "exit_code",
        "stdout_sha256",
        "stderr_sha256",
        "written_paths",
    }
    measured: dict[str, Mapping[str, object]] = {}
    for route_name in ("legacy_result", "container_result"):
        result = row.get(route_name)
        if not isinstance(result, Mapping) or set(result) != result_fields:
            raise DispatchError("parity-incomplete", f"{spec.tool_id}:{route_name}")
        if not isinstance(result.get("exit_code"), int):
            raise DispatchError("parity-incomplete", f"{spec.tool_id}:{route_name}:exit_code")
        for digest_name in ("stdout_sha256", "stderr_sha256"):
            digest = result.get(digest_name)
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise DispatchError("parity-incomplete", f"{spec.tool_id}:{route_name}:{digest_name}")
        paths = result.get("written_paths")
        if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
            raise DispatchError("parity-incomplete", f"{spec.tool_id}:{route_name}:written_paths")
        measured[route_name] = result
    if measured["legacy_result"] != measured["container_result"]:
        raise DispatchError("parity-result-mismatch", spec.tool_id)


def _validate_child_route(spec: ToolSpec, args: Sequence[str]) -> None:
    """Keep the verified IssueSync route on body-free receipt operations."""
    if spec.tool_id != "issue-sync":
        return
    options = {token for token in args if token.startswith("--")}
    unsupported = sorted(options - ISSUE_SYNC_RECEIPT_OPTIONS)
    if unsupported:
        raise DispatchError(
            "container-route-restricted",
            f"issue-sync accepts receipt-only inputs; rejected={','.join(unsupported)}",
        )
    operations = options & {
        "--receipt-preflight",
        "--stage-publication-receipt",
        "--record-publication-receipt",
    }
    if "--help" in options:
        operations.add("--help")
    if len(operations) != 1:
        raise DispatchError(
            "container-route-restricted",
            "issue-sync requires exactly one receipt preflight, stage, or help operation",
        )


def _under(path: Path, root: Path) -> bool:
    """Return whether a resolved path is equal to or below a root."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _registered_roots(runtime: Path) -> tuple[Path, ...]:
    """Read bootstrap's target registry without owning or mutating it."""
    registry_value = os.environ.get("AGENT_CANON_MOUNT_REGISTRY")
    if registry_value:
        registry = Path(registry_value)
        if registry.is_symlink() or not registry.is_file() or os.access(registry, os.W_OK):
            raise DispatchError("invalid-mount-registry", str(registry))
        try:
            state = tomllib.loads(registry.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            raise DispatchError("invalid-mount-registry", str(registry))
        if state.get("schema") != "agent-canon.mount-registry.v2":
            raise DispatchError("invalid-mount-registry", "schema")
    else:
        state_path = runtime / "state.json"
        if not state_path.is_file():
            return ()
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise DispatchError("invalid-runtime-state", str(state_path))
    targets = state.get("targets", {}) if isinstance(state, Mapping) else {}
    if not isinstance(targets, Mapping):
        raise DispatchError("invalid-runtime-state", "targets")
    roots: list[Path] = []
    for digest, record in targets.items():
        if not isinstance(record, Mapping) or not isinstance(record.get("root"), str):
            continue
        if registry_value:
            if not isinstance(digest, str) or any(ch not in "0123456789abcdef" for ch in digest):
                raise DispatchError("invalid-mount-registry", "target digest")
            roots.append(Path("/targets") / digest)
        else:
            roots.append(Path(record["root"]).resolve())
    return tuple(roots)


def _cwd_for(root: Path, spec: ToolSpec, runtime: Path) -> Path:
    """Resolve a cwd only when bootstrap has a registered containment root."""
    if spec.cwd_policy == "source-root":
        cwd = root.resolve()
        if not cwd.is_dir():
            raise DispatchError("invalid-cwd", str(cwd))
        return cwd
    if spec.cwd_policy == "target-root":
        value = os.environ.get("AGENT_CANON_TARGET_ROOT")
        if not value:
            raise DispatchError("missing-target-root", spec.tool_id)
    elif spec.cwd_policy == "task-root":
        value = os.environ.get("AGENT_CANON_TASK_ROOT")
        if not value:
            raise DispatchError("missing-task-root", spec.tool_id)
    else:
        value = os.environ.get("AGENT_CANON_EXPLICIT_CWD")
        if not value:
            raise DispatchError("missing-explicit-cwd", spec.tool_id)
    cwd = Path(value).resolve()
    registered = _registered_roots(runtime)
    if not any(_under(cwd, target) for target in registered) and not _under(cwd, runtime / "tasks"):
        raise DispatchError("unregistered-cwd", str(cwd))
    if not cwd.is_dir():
        raise DispatchError("invalid-cwd", str(cwd))
    return cwd


def _output_root(spec: ToolSpec, runtime: Path, registered: Sequence[Path]) -> Path | None:
    """Resolve and enforce an output root against the declared effect."""
    if spec.output_root == "none":
        if os.environ.get("AGENT_CANON_OUTPUT_ROOT"):
            raise DispatchError("unexpected-output-root", spec.tool_id)
        return None
    value = os.environ.get("AGENT_CANON_OUTPUT_ROOT")
    if not value:
        raise DispatchError("missing-output-root", spec.tool_id)
    output = Path(value).resolve()
    if spec.output_root == "external-runtime":
        if not _under(output, runtime) or output == runtime:
            raise DispatchError("output-root-escape", str(output))
    elif not any(_under(output, target) for target in registered):
        raise DispatchError("output-root-unregistered", str(output))
    return output


def _immutable_file(path: Path, expected: bytes, *, field: str) -> str:
    """Read a fixed marker and return its digest only when it is immutable."""
    try:
        stat_result = path.stat()
        content = path.read_bytes()
    except OSError as error:
        raise DispatchError("container-marker-missing", f"{field}:{path}") from error
    if stat_result.st_mode & 0o222:
        raise DispatchError("container-marker-writable", f"{field}:{path}")
    if content != expected:
        raise DispatchError("container-marker-invalid", field)
    return hashlib.sha256(content).hexdigest()


def _validate_container_context(root: Path) -> None:
    """Authenticate the stable image and read-only source mount."""
    if os.environ.get("AGENT_CANON_EXECUTION_PLANE") != "tool-container":
        raise DispatchError("container-exec-not-authorized", "AGENT_CANON_EXECUTION_PLANE")
    image_root_value = os.environ.get("AGENT_CANON_IMAGE_ROOT")
    image_deps_value = os.environ.get("AGENT_CANON_IMAGE_DEPENDENCIES_ROOT")
    tools_root_value = os.environ.get("AGENT_CANON_RUNTIME_TOOLS_ROOT")
    marker_digest = os.environ.get("AGENT_CANON_IMAGE_MARKER_DIGEST")
    runtime_digest = os.environ.get("AGENT_CANON_RUNTIME_MARKER_DIGEST")
    if not image_root_value or not image_deps_value or not tools_root_value:
        raise DispatchError(
            "container-marker-missing",
            "AGENT_CANON_IMAGE_ROOT, AGENT_CANON_IMAGE_DEPENDENCIES_ROOT, AGENT_CANON_RUNTIME_TOOLS_ROOT",
        )
    image_root = Path(image_root_value).resolve()
    image_deps = Path(image_deps_value).resolve()
    tools_root = Path(tools_root_value).resolve()
    source = root.resolve()
    if source != tools_root or source == image_root:
        raise DispatchError("container-runtime-root-invalid", str(source))
    if image_deps != image_root / "image-dependencies":
        raise DispatchError("container-dependency-root-invalid", str(image_deps))
    observed_image_digest = _immutable_file(image_root / CONTAINER_MARKER_NAME, CONTAINER_MARKER, field="image")
    observed_runtime_digest = _immutable_file(
        image_root / "runtime" / RUNTIME_MARKER_NAME, RUNTIME_MARKER, field="runtime"
    )
    if marker_digest != f"sha256:{observed_image_digest}":
        raise DispatchError("container-marker-digest-mismatch", "image")
    if runtime_digest != f"sha256:{observed_runtime_digest}":
        raise DispatchError("container-marker-digest-mismatch", "runtime")
    dependencies = image_deps / "plan.json"
    try:
        if dependencies.stat().st_mode & 0o222:
            raise DispatchError("container-dependency-plan-writable", str(dependencies))
        plan = json.loads(dependencies.read_text(encoding="utf-8"))
    except DispatchError:
        raise
    except (OSError, json.JSONDecodeError) as error:
        raise DispatchError("container-dependency-plan-invalid", str(dependencies)) from error
    if not isinstance(plan, Mapping) or not plan.get("schema"):
        raise DispatchError("container-dependency-plan-invalid", str(dependencies))


def _resolve_argv(root: Path, spec: ToolSpec, args: Sequence[str]) -> list[str]:
    """Resolve a typed launcher vector to an argv accepted by subprocess."""
    if any("\x00" in item for item in args):
        raise DispatchError("invalid-argv", spec.tool_id)
    command = list(spec.argv) + list(args)
    if command[0] in {"python", "python3"}:
        command[0] = sys.executable
    for index, value in enumerate(command):
        if value in {"tools/bin/agent-canon"} or value.startswith("tools/"):
            candidate = root / value
            if candidate.exists():
                command[index] = str(candidate)
    target_index = 1 if command and command[0] == sys.executable else 0
    if spec.runtime == "python" and len(command) > target_index and command[target_index] not in {"-m"}:
        target = command[target_index]
        if target.startswith("tools/"):
            command[target_index] = str(root / target)
    return command


def _resolve_container_argv(root: Path, spec: ToolSpec, args: Sequence[str]) -> list[str]:
    """Resolve logical catalog paths against the immutable image mount."""
    command = list(spec.argv) + list(args)
    if any("\x00" in item for item in command):
        raise DispatchError("invalid-argv", spec.tool_id)
    if command and command[0] in {"python", "python3"}:
        command[0] = sys.executable
    for index, value in enumerate(command):
        if value == "tools/bin/agent-canon":
            command[index] = str(
                Path(os.environ.get("AGENT_CANON_COMPILED_BIN_DIR", "/var/lib/agent-canon/cache/bin"))
                / "agent-canon"
            )
        elif value.startswith("tools/") and (root / value).is_file():
            command[index] = str(root / value)
    return command


def _environment(root: Path, spec: ToolSpec, runtime: Path, output: Path | None) -> dict[str, str]:
    """Build the exact bootstrap environment without wildcard inheritance."""
    if spec.env_policy == "clean":
        result: dict[str, str] = {}
    else:
        result = {key: value for key, value in os.environ.items() if key in ENV_ALLOWLIST}
    result.update(
        {
            "AGENT_CANON_SOURCE_ROOT": str(root),
            "AGENT_CANON_ROOT": str(root),
            "AGENT_CANON_DISPATCH_ENTRY_ID": spec.tool_id,
            "AGENT_CANON_DISPATCH_RUNTIME": spec.runtime,
            "AGENT_CANON_RUNTIME_ROOT": str(runtime),
        }
    )
    source_path = str(root.resolve())
    inherited_pythonpath = result.get("PYTHONPATH", "")
    pythonpath_entries = [source_path]
    pythonpath_entries.extend(
        entry
        for entry in inherited_pythonpath.split(os.pathsep)
        if entry and entry != source_path
    )
    result["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    if output is not None:
        result["AGENT_CANON_OUTPUT_ROOT"] = str(output)
    for key in ("AGENT_CANON_CONTROL_PARENT_ROOT", "AGENT_CANON_TASK_ROOT", "AGENT_CANON_TARGET_ROOT", "AGENT_CANON_EXPLICIT_CWD"):
        value = os.environ.get(key)
        if value:
            result[key] = value
    return result


def _require_external_runtime(root: Path) -> None:
    """Require an explicit control/runtime pair for the public CLI route."""
    control_value = os.environ.get("AGENT_CANON_CONTROL_PARENT_ROOT")
    runtime_value = os.environ.get("AGENT_CANON_RUNTIME_ROOT")
    if not control_value or not runtime_value:
        raise DispatchError(
            "runtime-root-required",
            "AGENT_CANON_CONTROL_PARENT_ROOT and AGENT_CANON_RUNTIME_ROOT",
        )
    control = Path(control_value).resolve()
    runtime = Path(runtime_value).resolve()
    source = root.resolve()
    if not control.is_dir() or not runtime.is_dir():
        raise DispatchError("runtime-root-missing", f"{control}:{runtime}")
    if runtime == source or source in runtime.parents:
        raise DispatchError("runtime-root-inside-source", str(runtime))
    if runtime != control and control not in runtime.parents:
        raise DispatchError("runtime-root-outside-control", str(runtime))


def _bootstrap_command(root: Path, runtime: Path, spec: ToolSpec, args: Sequence[str], cwd: Path, output: Path | None) -> tuple[list[str], dict[str, str]]:
    """Build a typed request for bootstrap; never execute a tool on the host."""
    bootstrap = root / "bootstrap.sh"
    if not bootstrap.is_file() or not os.access(bootstrap, os.X_OK):
        raise DispatchError("bootstrap-unavailable", str(bootstrap))
    control = Path(os.environ["AGENT_CANON_CONTROL_PARENT_ROOT"]).resolve()
    registered = _registered_roots(runtime)
    target_value = os.environ.get("AGENT_CANON_TARGET_ROOT")
    if target_value:
        target_root = Path(target_value).resolve()
        if target_root not in registered:
            raise DispatchError("target-root-unregistered", str(target_root))
    elif len(registered) == 1:
        target_root = registered[0]
    else:
        raise DispatchError(
            "target-root-required",
            "set AGENT_CANON_TARGET_ROOT when zero or multiple targets are registered",
        )
    target_digest = hashlib.sha256(str(target_root).encode("utf-8")).hexdigest()
    request = {
        "schema": "agent-canon.tool-exec-request.v1",
        "tool_id": spec.tool_id,
        "runtime": spec.runtime,
        # Keep catalog paths logical. Bootstrap maps the source mount and the
        # image-owned Rust binary; host absolute paths must never leak into a
        # container request.
        "argv": [*spec.argv, *args],
        "source_root": str(root.resolve()),
        "cwd": str(cwd),
        "cwd_policy": spec.cwd_policy,
        "target_root": str(target_root),
        "child_args": list(args),
        "environment": _environment(root, spec, runtime, output),
        "stdin": spec.stdin_policy,
        "stdout": spec.stdout_policy,
        "stderr": spec.stderr_policy,
        "exit": spec.exit_policy,
        "signal": spec.signal_policy,
        "side_effect": spec.side_effect_policy,
        "output_root": str(output) if output is not None else None,
        "written_paths": list(spec.written_paths),
    }
    # JSON is one typed argv value. It is not a shell fragment and is decoded
    # only by bootstrap's request parser.
    command = [
        str(bootstrap),
        "--repository-root", str(root.resolve()),
        "--control-parent-root", str(control),
        "--runtime-root", str(runtime),
        "exec",
        "--target-digest",
        target_digest,
        "--request-json",
        json.dumps(request, sort_keys=True, separators=(",", ":")),
    ]
    environment = {key: value for key, value in os.environ.items() if key in BOOTSTRAP_EXEC_ENV}
    environment.update({"AGENT_CANON_CONTROL_PARENT_ROOT": str(control), "AGENT_CANON_RUNTIME_ROOT": str(runtime)})
    return command, environment


def _run_container_spec(root: Path, spec: ToolSpec, args: Sequence[str]) -> int:
    """Execute an already verified tool inside the authenticated image only."""
    _validate_container_context(root)
    runtime_value = os.environ.get("AGENT_CANON_RUNTIME_ROOT")
    if not runtime_value:
        raise DispatchError("runtime-root-required", "AGENT_CANON_RUNTIME_ROOT")
    runtime = Path(runtime_value).resolve()
    registered = _registered_roots(runtime)
    cwd = _cwd_for(root, spec, runtime)
    output = _output_root(spec, runtime, registered)
    command = _resolve_container_argv(root, spec, args)
    environment = _environment(root, spec, runtime, output)
    stdin = subprocess.PIPE if spec.stdin_policy == "captured" else None
    stdout = subprocess.PIPE if spec.stdout_policy == "captured" else None
    stderr = subprocess.PIPE if spec.stderr_policy == "captured" else None
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            input=b"" if stdin is subprocess.PIPE else None,
            check=False,
        )
    except OSError as error:
        raise DispatchError("container-exec-failed", f"{spec.tool_id}:{error}") from error
    if completed.stdout is not None:
        sys.stdout.buffer.write(completed.stdout)
        sys.stdout.flush()
    if completed.stderr is not None:
        sys.stderr.buffer.write(completed.stderr)
        sys.stderr.flush()
    if completed.returncode < 0:
        return 128 + (-completed.returncode)
    return completed.returncode


def _run_spec(
    root: Path,
    spec: ToolSpec,
    args: Sequence[str],
    *,
    require_parity: bool,
    container_exec: bool = False,
) -> int:
    """Build a typed request or execute only inside an authenticated image."""
    if require_parity:
        _check_parity_fixture(root, spec)
    _validate_child_route(spec, args)
    if container_exec:
        return _run_container_spec(root, spec, args)
    runtime_value = os.environ.get("AGENT_CANON_RUNTIME_ROOT")
    if not runtime_value:
        raise DispatchError("runtime-root-required", "AGENT_CANON_RUNTIME_ROOT")
    runtime = Path(runtime_value).resolve()
    registered = _registered_roots(runtime)
    cwd = _cwd_for(root, spec, runtime)
    output = _output_root(spec, runtime, registered)
    command, environment = _bootstrap_command(root, runtime, spec, args, cwd, output)
    try:
        completed = subprocess.run(command, cwd=root, env=environment, check=False)
    except OSError as error:
        raise DispatchError("bootstrap-exec-failed", f"{spec.tool_id}:{error}") from error
    if completed.returncode < 0:
        signum = -completed.returncode
        if spec.signal_policy == "normalize-signal":
            return 128 + signum
        return 128 + signum
    return completed.returncode


def run_tool(root: Path, spec: ToolSpec, args: Sequence[str]) -> int:
    """Ask bootstrap to execute one parity-verified catalog entry."""
    return _run_spec(root, spec, args, require_parity=True)


def run_container_tool(root: Path, spec: ToolSpec, args: Sequence[str]) -> int:
    """Run one parity-verified catalog entry inside the tool container."""
    return _run_spec(root, spec, args, require_parity=True, container_exec=True)


def run_rust_cli(root: Path, args: Sequence[str]) -> int:
    """Preserve the exact legacy Rust CLI behind bootstrap target mounts."""
    runtime = Path(os.environ["AGENT_CANON_RUNTIME_ROOT"]).resolve()
    control = Path(os.environ["AGENT_CANON_CONTROL_PARENT_ROOT"]).resolve()
    registered = _registered_roots(runtime)
    target_value = os.environ.get("AGENT_CANON_TARGET_ROOT")
    if target_value:
        target = Path(target_value).resolve()
        if target not in registered:
            raise DispatchError("target-root-unregistered", str(target))
    elif len(registered) == 1:
        target = registered[0]
    else:
        raise DispatchError("target-root-required", "select one registered target")
    bootstrap = root / "bootstrap.sh"
    command = [
        str(bootstrap),
        "--control-parent-root",
        str(control),
        "--runtime-root",
        str(runtime),
        "exec",
        "--root",
        str(target),
        "--",
        "agent-canon",
        *args,
    ]
    environment = {key: value for key, value in os.environ.items() if key in BOOTSTRAP_EXEC_ENV}
    completed = subprocess.run(command, cwd=root, env=environment, check=False)
    return 128 + (-completed.returncode) if completed.returncode < 0 else completed.returncode


def inventory(root: Path) -> dict[str, object]:
    """Return the versioned public-command inventory."""
    specs, _schema = load_specs(root)
    rows = [specs[key].inventory_row() for key in sorted(specs)]
    return {"schema": "agent-canon-tool-inventory/v1", "catalog_runtime_schema": SCHEMA_VERSION, "entries": rows}


def _error(error: DispatchError) -> int:
    """Render one stable error and return the CLI failure status."""
    print(str(error), file=sys.stderr)
    return 2


def _parse_run(argv: Sequence[str]) -> tuple[Path, str, tuple[str, ...]]:
    """Parse only dispatcher options; child options begin after ``--``."""
    root = Path.cwd()
    index = 0
    while index < len(argv) and argv[index] != "--":
        token = argv[index]
        if token == "--root":
            if index + 1 >= len(argv):
                raise DispatchError("missing-option-value", "--root")
            root = Path(argv[index + 1])
            index += 2
            continue
        if token.startswith("-"):
            raise DispatchError("unknown-option", token)
        break
    if index >= len(argv) or argv[index] == "--":
        raise DispatchError("missing-catalog-id", "run <catalog-id> -- <args...>")
    tool_id = argv[index]
    if any(ch not in ID_CHARS for ch in tool_id) or not tool_id:
        raise DispatchError("invalid-id", tool_id)
    index += 1
    if index >= len(argv) or argv[index] != "--":
        raise DispatchError("missing-argument-delimiter", tool_id)
    return root, tool_id, tuple(argv[index + 1 :])


def main(argv: Sequence[str] | None = None) -> int:
    """Run the namespaced dispatcher command."""
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print("usage: tool_dispatch.py [--root ROOT] run <catalog-id> -- <args...>", file=sys.stderr)
        return 2
    container_exec = False
    prefix_end = arguments.index("--") if "--" in arguments else len(arguments)
    if "--container-exec" in arguments[:prefix_end]:
        container_exec = True
        arguments = tuple(token for index, token in enumerate(arguments) if not (index < prefix_end and token == "--container-exec"))
    if arguments and arguments[0] == "--root":
        if len(arguments) < 3:
            return _error(DispatchError("missing-option-value", "--root"))
        # Accept the container wrapper's conventional global-option order and
        # normalize it to the dispatcher parser's command-first form.
        arguments = (arguments[2], "--root", arguments[1], *arguments[3:])
    if container_exec and arguments and arguments[0] != "--root" and arguments[0] != "run":
        return _error(DispatchError("container-exec-command-invalid", arguments[0]))
    if arguments[0] == "inventory":
        root = Path.cwd()
        index = 1
        as_json = False
        while index < len(arguments):
            token = arguments[index]
            if token == "--root":
                if index + 1 >= len(arguments):
                    return _error(DispatchError("missing-option-value", "--root"))
                root = Path(arguments[index + 1])
                index += 2
            elif token == "--json":
                as_json = True
                index += 1
            else:
                return _error(DispatchError("unknown-option", token))
        try:
            payload = inventory(root)
        except DispatchError as error:
            return _error(error)
        if as_json:
            print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        else:
            rows = cast(list[Mapping[str, object]], payload["entries"])
            for row in rows:
                print(row["id"])
        return 0
    if arguments[0] == "rust-cli":
        try:
            root = Path.cwd()
            index = 1
            if index < len(arguments) and arguments[index] == "--root":
                if index + 1 >= len(arguments):
                    return _error(DispatchError("missing-option-value", "--root"))
                root = Path(arguments[index + 1])
                index += 2
            if index >= len(arguments) or arguments[index] != "--":
                return _error(DispatchError("missing-argument-delimiter", "rust-cli"))
            _require_external_runtime(root)
            if container_exec:
                return _error(DispatchError("container-exec-command-invalid", "rust-cli"))
            return run_rust_cli(root, arguments[index + 1 :])
        except DispatchError as error:
            return _error(error)
    if arguments[0] != "run":
        return _error(DispatchError("unknown-command", arguments[0]))
    try:
        root, tool_id, child_args = _parse_run(arguments[1:])
        _require_external_runtime(root)
        specs, _schema = load_specs(root)
        if tool_id not in specs:
            raise DispatchError("unknown-id", tool_id)
        if container_exec:
            return run_container_tool(root.resolve(), specs[tool_id], child_args)
        return run_tool(root.resolve(), specs[tool_id], child_args)
    except DispatchError as error:
        return _error(error)


if __name__ == "__main__":
    raise SystemExit(main())
