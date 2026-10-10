#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Owns container-side TOML/JSON/state/tool/check/eval logic for the shared AgentCanon tool container without implicit source writes.
# upstream design ../../../documents/design/agent-canon-bootstrap-tool-runtime.md shared runtime design
# upstream implementation ../source/agent_canon_source_root.py standalone source identity
# upstream implementation ../../../bootstrap/container/image/Dockerfile builds the resident runtime image
# downstream implementation ../../../bootstrap.sh fixed host entrypoint
# downstream implementation ../../../tests/bootstrap/test_bootstrap_runtime.py lifecycle validation
# @dependency-end
"""Container control plane for the AgentCanon tool runtime.

The host shell completes Docker lifecycle operations before invoking this
controller. BootstrapRuntime owns durable state and performs state/path
readback under an external lifecycle lock; it never invokes Docker itself.
The resident controller handles state, target, tool, check, and eval work.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 in the pinned Ubuntu tool image.
    import tomli as tomllib  # type: ignore[no-redef]

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

SCHEMA_STATE = "agent-canon.bootstrap-state.v2"
SCHEMA_RECEIPT = "agent-canon.bootstrap-receipt.v2"
SCHEMA_MOUNTS = "agent-canon.mount-registry.v2"
SCHEMA_SKILLS = "agent-canon.managed-codex-home.v1"
STATE_FILE = "state.json"
OWNER_FILE = "owner.json"
RECEIPT_DIR = "receipts"
GENERATION_DIR = "generations"
TASK_DIR = "tasks"
KNOWN_SUBDIRS = (
    RECEIPT_DIR,
    GENERATION_DIR,
    TASK_DIR,
    "spool",
    "archive",
    "cache",
    "codex-home",
)
CONTAINER_RUNTIME_DIR = "container-runtime"
CONTAINER_RUNTIME_DESTINATION = "/var/lib/agent-canon/runtime"
RUFF_CACHE_DESTINATION = "/var/lib/agent-canon/cache/ruff"
PRIVATE_LOG_DESTINATION = "/var/lib/agent-canon/private-log"
REGISTRY_DESTINATION = "/var/lib/agent-canon/mount-registry.toml"
SOURCE_SYNC_SCHEMA = "agent-canon.source-sync.v1"
SOURCE_SYNC_DESTINATION = "/var/lib/agent-canon/source-sync"
SOURCE_SYNC_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SOURCE_SYNC_IDENTITY_RE = re.compile(r"^(?:unknown|[0-9a-f]{40})$")
SOURCE_SYNC_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
CODEX_SESSION_ROOT_ENV = "AGENT_CANON_CODEX_SESSION_ROOT"
TOOL_SOURCE_DESTINATION = "/opt/agent-canon/source"
TOOL_ENVIRONMENT_KEYS = frozenset(
    {
        "PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "TMPDIR",
        "RUST_BACKTRACE",
        "CARGO_TERM_COLOR",
        "RUFF_CACHE_DIR",
        "AGENT_CANON_SOURCE_ROOT",
        "AGENT_CANON_ROOT",
        "AGENT_CANON_DISPATCH_ENTRY_ID",
        "AGENT_CANON_DISPATCH_RUNTIME",
        "AGENT_CANON_RUNTIME_ROOT",
        "AGENT_CANON_CONTROL_PARENT_ROOT",
        "AGENT_CANON_TASK_ROOT",
        "AGENT_CANON_TARGET_ROOT",
        "AGENT_CANON_EXPLICIT_CWD",
        "AGENT_CANON_OUTPUT_ROOT",
        "AGENT_CANON_MOUNT_REGISTRY",
        "AGENT_CANON_HOOK_ARCHIVE_DIR",
        "AGENT_CANON_LOG_ROOT",
        CODEX_SESSION_ROOT_ENV,
        "AGENT_CANON_PRIVATE_LOG_ROOT",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_KEY_0",
        "GIT_CONFIG_VALUE_0",
    }
)
TOOL_PATH_ENVIRONMENT_KEYS = frozenset(
    {
        "AGENT_CANON_SOURCE_ROOT",
        "AGENT_CANON_ROOT",
        "AGENT_CANON_RUNTIME_ROOT",
        "AGENT_CANON_CONTROL_PARENT_ROOT",
        "AGENT_CANON_TASK_ROOT",
        "AGENT_CANON_TARGET_ROOT",
        "AGENT_CANON_EXPLICIT_CWD",
        "AGENT_CANON_OUTPUT_ROOT",
        "AGENT_CANON_MOUNT_REGISTRY",
        "AGENT_CANON_HOOK_ARCHIVE_DIR",
        "AGENT_CANON_LOG_ROOT",
        CODEX_SESSION_ROOT_ENV,
    }
)
REQUIRED_LABELS = frozenset(
    {
        "io.agent-canon.runtime=shared-v1",
        "io.agent-canon.control-root-digest",
    }
)
ADMISSION_STATES = frozenset({"ready", "running"})
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
MAX_RECEIPT_IO_BYTES = 512


_SECRET_OUTPUT = re.compile(
    r"(?i)(\b(?:password|passwd|secret|token|api[_-]?key|authorization)\b\s*[=:]\s*)([^\s,;]+)"
)
_BEARER_OUTPUT = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_EVAL_PRODUCER_LINE = re.compile(
    r"^ACCUMULATED_AGENT_EVAL_PRODUCER=(?P<name>[^:]+):"
    r"(?P<status>pass|fail):stdout=(?P<stdout>[^:]*):stderr=(?P<stderr>.*)$"
)


class BootstrapError(RuntimeError):
    """A typed, user-actionable lifecycle refusal."""

    def __init__(
        self, code: str, detail: str, *, evidence: Mapping[str, Any] | None = None
    ) -> None:
        """Create an error with a stable machine-readable code."""
        self.code = code
        self.detail = detail
        self.evidence = dict(evidence or {})
        super().__init__(f"{code}: {detail}")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    """Return the SHA-256 digest of bytes."""
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    """Return the SHA-256 digest of UTF-8 text."""
    return sha256_bytes(value.encode("utf-8"))


def _redact_output(value: str) -> str:
    """Redact common credential-shaped values before logging command output."""
    value = _SECRET_OUTPUT.sub(r"\1<redacted>", value)
    return _BEARER_OUTPUT.sub("Bearer <redacted>", value)


def _redact_argv(argv: Sequence[str]) -> list[str]:
    """Redact credential-shaped argv values before receipt serialization."""
    redacted: list[str] = []
    hide_next = False
    secret_names = (
        "token",
        "password",
        "secret",
        "api-key",
        "api_key",
        "authorization",
    )
    for value in argv:
        lowered = value.lower()
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
            continue
        if value.startswith("-") and any(name in lowered for name in secret_names):
            if "=" in value:
                redacted.append(value.split("=", 1)[0] + "=<redacted>")
            else:
                redacted.append(value)
                hide_next = True
            continue
        redacted.append(_redact_output(value))
    return redacted


def _bounded_output_preview(value: str, limit: int = MAX_RECEIPT_IO_BYTES) -> str:
    """Keep both failure context and the terminal diagnostic within a limit."""
    if len(value) <= limit:
        return value
    separator = "\n...<truncated>...\n"
    available = max(0, limit - len(separator))
    prefix = available // 2
    suffix = available - prefix
    return value[:prefix] + separator + value[-suffix:]


def _validate_tool_plane_argv(
    root: Path, repository_root: Path, argv: Sequence[str]
) -> None:
    """Reject project executables while retaining AgentCanon tool compatibility."""
    if not argv or any(not isinstance(item, str) or "\x00" in item for item in argv):
        raise BootstrapError("argv_required", "exec requires a non-empty argv list")
    executable = argv[0]
    if executable in {"agent-canon", "agent-canon-tool"}:
        return
    image_tool_root = f"{TOOL_SOURCE_DESTINATION}/tools/"
    if executable in {"python3", "bash"} and len(argv) > 1:
        script = argv[1]
        if script.startswith(image_tool_root):
            return
    if root.resolve() == repository_root.resolve():
        return
    from tools.runtime.source.agent_canon_source_root import (
        SourceRootFailure,
        resolve_agent_canon_source_root,
    )

    try:
        resolve_agent_canon_source_root(root, source_root=root, canon_root=root)
    except SourceRootFailure:
        pass
    else:
        return
    raise BootstrapError(
        "tool_plane_command_rejected",
        "exec accepts AgentCanon tools only; project commands use the project execution environment",
        evidence={"argv": _redact_argv(argv)},
    )


def _source_snapshot(root: Path) -> dict[str, Any]:
    """Capture tracked and non-ignored source state without scanning runtime artifacts."""
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"],
        check=False,
        capture_output=True,
        text=True,
    )
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    inventory = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        check=False,
        capture_output=True,
    )
    if status.returncode != 0 or head.returncode != 0 or inventory.returncode != 0:
        raise BootstrapError(
            "source_snapshot_failed", "eval source must be a readable Git checkout"
        )
    digest = hashlib.sha256()
    file_count = 0
    relative_paths = sorted(
        Path(os.fsdecode(value)) for value in inventory.stdout.split(b"\0") if value
    )
    for relative_path in relative_paths:
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise BootstrapError(
                "source_snapshot_failed", f"unsafe Git inventory path: {relative_path}"
            )
        path = root / relative_path
        relative = path.relative_to(root).as_posix().encode("utf-8")
        try:
            if path.is_symlink():
                payload = os.readlink(path).encode("utf-8")
                kind = b"symlink"
            elif path.is_file():
                payload = path.read_bytes()
                kind = b"file"
            else:
                continue
        except (FileNotFoundError, OSError) as exc:
            raise BootstrapError(
                "source_snapshot_failed", f"source changed while being read: {path}"
            ) from exc
        digest.update(kind)
        digest.update(b"\0")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload).digest())
        digest.update(b"\0")
        file_count += 1
    status_text = status.stdout
    return {
        "head": head.stdout.strip(),
        "git_status": status_text,
        "git_status_digest": sha256_text(status_text),
        "tree_digest": digest.hexdigest(),
        "file_count": file_count,
    }


def _changed_source_paths(root: Path) -> set[str]:
    """Return tracked and non-ignored untracked paths changed from HEAD."""
    tracked = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    untracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
        check=False,
        capture_output=True,
        text=True,
    )
    if tracked.returncode != 0 or untracked.returncode != 0:
        raise BootstrapError("source_snapshot_failed", "cannot enumerate changed paths")
    return {
        value
        for value in (*tracked.stdout.splitlines(), *untracked.stdout.splitlines())
        if value
    }


def _eval_producer_matrix(stdout: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse the registered runner's machine-readable producer matrix."""
    matrix: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    for line in stdout.splitlines():
        match = _EVAL_PRODUCER_LINE.fullmatch(line.strip())
        if match:
            matrix.append(
                {
                    "name": match.group("name"),
                    "status": match.group("status"),
                    "stdout": match.group("stdout"),
                    "stderr": match.group("stderr"),
                    "exit": 0 if match.group("status") == "pass" else 1,
                }
            )
            continue
        if line.startswith("ACCUMULATED_AGENT_EVAL_PRODUCERS="):
            metrics["producer_count"] = int(line.split("=", 1)[1])
        elif line.startswith("ACCUMULATED_AGENT_EVAL_FAILED="):
            metrics["failed"] = line.split("=", 1)[1]
        elif line.startswith("ACCUMULATED_AGENT_EVAL="):
            metrics["overall"] = line.split("=", 1)[1]
    if matrix:
        metrics.setdefault("producer_count", len(matrix))
        metrics.setdefault(
            "failed_count", sum(item["status"] != "pass" for item in matrix)
        )
    return matrix, metrics


def _copy_external_files(source_root: Path, destination_root: Path) -> int:
    """Copy an exchange subtree into host spool with symlink and conflict checks."""
    if not source_root.exists():
        return 0
    if source_root.is_symlink() or not source_root.is_dir():
        raise BootstrapError(
            "eval_exchange_invalid", f"invalid exchange path: {source_root}"
        )
    files: list[tuple[Path, Path, bytes]] = []
    for source in sorted(source_root.rglob("*")):
        if source.is_symlink():
            raise BootstrapError(
                "eval_exchange_symlink", f"exchange contains a symlink: {source}"
            )
        if not source.is_file():
            continue
        relative = source.relative_to(source_root)
        payload = source.read_bytes()
        target = destination_root / relative
        files.append((source, target, payload))
    for _source, target, payload in files:
        if target.exists():
            if (
                target.is_symlink()
                or not target.is_file()
                or target.read_bytes() != payload
            ):
                raise BootstrapError(
                    "eval_spool_conflict", f"spool file differs: {target}"
                )
    for _source, target, payload in files:
        if not target.exists():
            _atomic_bytes(target, payload)
    return len(files)


def _validate_exported_tree(root: Path) -> int:
    """Validate one resident task export before it enters the eval spool."""
    if root.is_symlink() or not root.is_dir():
        raise BootstrapError("eval_export_invalid", f"invalid exported tree: {root}")
    count = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise BootstrapError(
                "eval_exchange_symlink", f"export contains a symlink: {path}"
            )
        if path.is_file():
            path.read_bytes()
            count += 1
    return count


def _io_evidence(
    task_path: Path, stdout: str, stderr: str, *, quota_bytes: int
) -> dict[str, Any]:
    """Persist redacted command streams and return bounded receipt evidence."""
    streams: dict[str, tuple[str, str]] = {
        "stdout": (stdout, "stdout.log"),
        "stderr": (stderr, "stderr.log"),
    }
    evidence: dict[str, Any] = {}
    total_bytes = sum(
        len(_redact_output(value).encode("utf-8")) for value in (stdout, stderr)
    )
    if quota_bytes > 0 and total_bytes > quota_bytes:
        raise BootstrapError(
            "task_log_quota_exceeded",
            f"command streams require {total_bytes} bytes; quota is {quota_bytes}",
        )
    for name, (raw, filename) in streams.items():
        redacted = _redact_output(raw)
        payload = redacted.encode("utf-8")
        destination = task_path / "logs" / filename
        _atomic_bytes(destination, payload)
        bounded = _bounded_output_preview(redacted)
        evidence[f"{name}_log"] = str(destination)
        evidence[f"{name}_digest"] = sha256_bytes(payload)
        evidence[f"{name}_bytes"] = len(payload)
        evidence[f"{name}_preview"] = bounded
        evidence[f"{name}_truncated"] = len(redacted) > len(bounded)
    return evidence


def _assert_absolute(path: Path, field: str) -> None:
    if not path.is_absolute():
        raise BootstrapError(
            "explicit_path_required", f"{field} must be an absolute path"
        )


def _normalize_absolute_path(path: Path) -> Path:
    """Collapse lexical dot segments after the caller validates the raw path."""
    return Path(os.path.normpath(os.fspath(path)))


def _open_dir(path: Path) -> int:
    try:
        return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise BootstrapError(
                "symlink_path_rejected", f"symlink or non-directory path: {path}"
            ) from exc
        raise BootstrapError(
            "path_unresolvable", f"cannot open directory: {path}"
        ) from exc


def _existing_no_symlink(path: Path, *, field: str) -> Path:
    """Return an existing directory only if every component is non-symlink."""
    _assert_absolute(path, field)
    current = Path(path.anchor or "/")
    for part in path.parts[1:]:
        current = current / part
        try:
            os.lstat(current)
        except FileNotFoundError as exc:
            raise BootstrapError(
                "path_missing", f"{field} does not exist: {path}"
            ) from exc
        except OSError as exc:
            raise BootstrapError(
                "path_unresolvable", f"cannot inspect {field}: {path}"
            ) from exc
        if os.path.islink(current):
            raise BootstrapError(
                "symlink_path_rejected", f"{field} contains a symlink: {current}"
            )
        if not os.path.isdir(current):
            raise BootstrapError(
                "path_not_directory", f"{field} is not a directory: {current}"
            )
    return _normalize_absolute_path(path)


def _existing_path_no_symlink(path: Path, *, field: str) -> Path:
    """Return an existing file or directory with no symlink component."""
    _assert_absolute(path, field)
    current = Path(path.anchor or "/")
    for part in path.parts[1:]:
        current /= part
        try:
            observed = os.lstat(current)
        except OSError as exc:
            raise BootstrapError(
                "path_missing", f"{field} does not exist: {path}"
            ) from exc
        if stat.S_ISLNK(observed.st_mode):
            raise BootstrapError(
                "symlink_path_rejected", f"{field} contains a symlink: {current}"
            )
    return _normalize_absolute_path(path)


def _validate_new_path(path: Path, *, field: str, beneath: Path) -> Path:
    _assert_absolute(path, field)
    current = Path(path.anchor or "/")
    for part in path.parts[1:]:
        current = current / part
        try:
            os.lstat(current)
        except FileNotFoundError:
            break
        except OSError as exc:
            raise BootstrapError(
                "path_unresolvable", f"cannot inspect {field}: {path}"
            ) from exc
        if os.path.islink(current):
            raise BootstrapError(
                "symlink_path_rejected", f"{field} contains a symlink: {current}"
            )
        if not os.path.isdir(current):
            raise BootstrapError(
                "path_not_directory", f"{field} is not a directory: {current}"
            )
    normalized = _normalize_absolute_path(path)
    try:
        normalized.relative_to(beneath)
    except ValueError as exc:
        raise BootstrapError(
            "runtime_root_escape", f"{field} must be beneath {beneath}"
        ) from exc
    return normalized


def validate_roots(
    control_parent_root: Path,
    runtime_root: Path,
) -> tuple[Path, Path]:
    """Validate the explicit mounted runtime below its control parent."""
    control = _existing_no_symlink(
        Path(control_parent_root), field="control-parent-root"
    )
    runtime = _validate_new_path(
        _normalize_absolute_path(Path(runtime_root)),
        field="runtime-root",
        beneath=control,
    )
    return control, runtime


def _ensure_directory(path: Path, *, mode: int = 0o700) -> None:
    """Mkdir -p with no symlink traversal."""
    _assert_absolute(path, "directory")
    current = Path(path.anchor or "/")
    for part in path.parts[1:]:
        current = current / part
        try:
            os.lstat(current)
        except FileNotFoundError:
            try:
                current.mkdir(mode=mode)
            except FileExistsError:
                pass
        except OSError as exc:
            raise BootstrapError(
                "path_unresolvable", f"cannot inspect directory: {current}"
            ) from exc
        if os.path.islink(current) or not os.path.isdir(current):
            raise BootstrapError(
                "symlink_path_rejected", f"directory path is unsafe: {current}"
            )
        os.close(_open_dir(current))


def _safe_read(path: Path, *, field: str) -> bytes:
    fd = _open_dir(path.parent)
    try:
        try:
            os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise BootstrapError(
                "path_missing", f"{field} does not exist: {path}"
            ) from exc
        if path.is_symlink() or not path.is_file():
            raise BootstrapError("symlink_path_rejected", f"unsafe {field}: {path}")
        try:
            child = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        except OSError as exc:
            raise BootstrapError(
                "symlink_path_rejected", f"cannot safely open {field}: {path}"
            ) from exc
        with os.fdopen(child, "rb") as stream:
            return stream.read()
    finally:
        os.close(fd)


def _atomic_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    _ensure_directory(path.parent)
    fd = _open_dir(path.parent)
    temporary = f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    try:
        try:
            child = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                mode,
                dir_fd=fd,
            )
        except OSError as exc:
            raise BootstrapError(
                "state_write_failed", f"cannot create temporary state file: {path}"
            ) from exc
        try:
            with os.fdopen(child, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                if os.path.islink(path):
                    raise BootstrapError(
                        "symlink_path_rejected", f"refusing to replace symlink: {path}"
                    )
            except OSError as exc:
                raise BootstrapError(
                    "state_write_failed", f"cannot inspect destination: {path}"
                ) from exc
            os.replace(temporary, path.name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        except BootstrapError:
            try:
                os.unlink(temporary, dir_fd=fd)
            except OSError:
                pass
            raise
        except OSError as exc:
            try:
                os.unlink(temporary, dir_fd=fd)
            except OSError:
                pass
            raise BootstrapError(
                "state_write_failed", f"cannot replace state file: {path}"
            ) from exc
    finally:
        os.close(fd)


def _atomic_json(path: Path, payload: Mapping[str, Any], *, mode: int = 0o600) -> None:
    _atomic_bytes(path, (_json(payload) + "\n").encode("utf-8"), mode=mode)


def _slug(value: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise BootstrapError("invalid_identifier", f"identifier is not safe: {value!r}")
    return value


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _dir_bytes(path: Path) -> int:
    if not path.exists() or path.is_symlink():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat(follow_symlinks=False).st_size
        except OSError:
            continue
    return total


def _manifest_path(repository_root: Path, explicit: Path | None) -> Path:
    path = explicit or (repository_root / "bootstrap" / "host" / "manifest.toml")
    _assert_absolute(path, "manifest")
    if path.is_symlink() or not path.is_file():
        raise BootstrapError(
            "manifest_missing", f"manifest is not a regular file: {path}"
        )
    return path


def load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    """Load and validate the typed runtime manifest."""
    try:
        raw = _safe_read(path, field="manifest")
        payload = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise BootstrapError(
            "manifest_invalid", f"cannot parse manifest: {path}"
        ) from exc
    container = payload.get("container")
    if not isinstance(container, dict):
        raise BootstrapError("manifest_invalid", "manifest.container must be a table")
    labels = container.get("labels")
    if not isinstance(labels, list) or not REQUIRED_LABELS.issubset(set(labels)):
        raise BootstrapError(
            "manifest_invalid", "manifest is missing required ownership labels"
        )
    if container.get("max_instances") != 1 or container.get("network") != "none":
        raise BootstrapError(
            "manifest_invalid", "shared runtime requires one network=none container"
        )
    for key in (
        "cpus",
        "memory_bytes",
        "pids_limit",
        "max_parallel_tasks",
        "task_state_quota_bytes",
        "task_log_quota_bytes",
    ):
        if not isinstance(container.get(key), int) or int(container[key]) <= 0:
            raise BootstrapError(
                "manifest_invalid", f"container.{key} must be a positive integer"
            )
    for key in (
        "health_start_period_seconds",
        "health_timeout_seconds",
        "health_poll_interval_seconds",
    ):
        value = container.get(key)
        if not isinstance(value, (int, float)) or float(value) <= 0:
            raise BootstrapError(
                "manifest_invalid", f"container.{key} must be positive"
            )
    return payload, sha256_bytes(raw)


def _run_resident_command(
    argv: Sequence[str],
    *,
    cwd: str,
    environment: Mapping[str, str] | None = None,
    timeout: int,
    pass_fds: Sequence[int] = (),
) -> subprocess.CompletedProcess[str]:
    """Run one command inside the already-selected resident process."""
    try:
        return subprocess.run(
            list(argv),
            cwd=cwd,
            env={**os.environ, **dict(environment or {})},
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            pass_fds=tuple(pass_fds),
        )
    except subprocess.TimeoutExpired as exc:
        raise BootstrapError(
            "docker_command_timeout", "container tool execution timed out"
        ) from exc
    except OSError as exc:
        raise BootstrapError(
            "tool_execution_failed", "container tool execution is unavailable"
        ) from exc


def _copy_resident_export(
    source: str, *, destination: Path, allowed_root: Path
) -> None:
    """Copy one task export within the controller's mounted runtime tree."""
    source_path = Path(source)
    exchange_tasks_prefix = f"{CONTAINER_RUNTIME_DESTINATION}/exchange/tasks/"
    if not source.startswith(exchange_tasks_prefix) or ".." in source_path.parts:
        raise BootstrapError(
            "docker_copy_rejected", f"unsafe container export: {source}"
        )
    source_local = Path(source)
    if source_local.is_symlink() or not source_local.exists():
        raise BootstrapError(
            "docker_copy_rejected", f"container export is missing: {source}"
        )
    destination_resolved = destination.resolve(strict=False)
    allowed_resolved = allowed_root.resolve()
    if (
        destination_resolved != allowed_resolved
        and allowed_resolved not in destination_resolved.parents
    ):
        raise BootstrapError(
            "docker_copy_rejected",
            f"export destination escapes runtime: {destination}",
        )
    if source_local.is_dir():
        shutil.copytree(source_local, destination, dirs_exist_ok=False)
    else:
        _ensure_directory(destination.parent)
        shutil.copy2(source_local, destination)


@dataclass(frozen=True)
class RuntimePaths:
    """Names of all state surfaces below one validated runtime root."""

    control_parent_root: Path
    runtime_root: Path

    @property
    def state(self) -> Path:
        """Return the lifecycle state path."""
        return self.runtime_root / STATE_FILE

    @property
    def owner(self) -> Path:
        """Return the immutable ownership record path."""
        return self.runtime_root / OWNER_FILE

    @property
    def lock(self) -> Path:
        """Return the lifecycle lock path."""
        return self.runtime_root / "lifecycle.lock"

    @property
    def receipts(self) -> Path:
        """Return the receipt directory."""
        return self.runtime_root / RECEIPT_DIR

    @property
    def generations(self) -> Path:
        """Return the generation directory."""
        return self.runtime_root / GENERATION_DIR

    @property
    def tasks(self) -> Path:
        """Return the task directory."""
        return self.runtime_root / TASK_DIR

    @property
    def codex_home(self) -> Path:
        """Return the isolated managed Codex home."""
        surface = self._host_surface("CODEX_HOME")
        if surface is not None:
            return surface
        return self.runtime_root / "codex-home"

    @property
    def spool(self) -> Path:
        """Return the host-consumed eval spool surface."""
        return self._host_surface("SPOOL") or self.runtime_root / "spool"

    @property
    def archive(self) -> Path:
        """Return the host-consumed archive cache surface."""
        return self._host_surface("ARCHIVE") or self.runtime_root / "archive"

    @property
    def cache(self) -> Path:
        """Return the host-consumed runtime cache surface."""
        return self._host_surface("CACHE") or self.runtime_root / "cache"

    @staticmethod
    def _host_surface(name: str) -> Path | None:
        """Resolve an explicitly mounted host surface in the resident."""
        value = os.environ.get(f"AGENT_CANON_HOST_{name}_ROOT", "").strip()
        return Path(value) if value else None

    @property
    def container_runtime(self) -> Path:
        """Return the writable, credential-free container exchange directory."""
        exchange = os.environ.get("AGENT_CANON_EXCHANGE_ROOT", "").strip()
        if exchange:
            return Path(exchange)
        return self.runtime_root / CONTAINER_RUNTIME_DIR


class BootstrapRuntime:
    """Persistent resident controller state and tool execution."""

    def __init__(
        self,
        control_parent_root: Path,
        runtime_root: Path,
        *,
        repository_root: Path | None = None,
        manifest_path: Path | None = None,
    ) -> None:
        """Create a resident controller bound to explicit control and runtime roots."""
        self.repository_root = (
            repository_root or Path(__file__).resolve().parents[3]
        ).resolve()
        control, runtime = validate_roots(
            Path(control_parent_root),
            Path(runtime_root),
        )
        self.paths = RuntimePaths(control, runtime)
        self.manifest_path = _manifest_path(self.repository_root, manifest_path)
        self.manifest, policy_digest = load_manifest(self.manifest_path)
        self.manifest_digest = policy_digest
        self.control_digest = os.environ.get(
            "AGENT_CANON_CONTROL_ROOT_DIGEST", sha256_text(str(control))
        )

    @property
    def private_log_root(self) -> Path:
        """Return the host-owned log checkout through its fixed resident mount."""
        return Path(PRIVATE_LOG_DESTINATION)

    @property
    def source_sync_read_path(self) -> Path:
        """Return the host-owned source-sync path visible to this controller."""
        return Path(SOURCE_SYNC_DESTINATION) / "source-sync.json"

    def _read_source_sync_state(self) -> dict[str, Any] | None:
        """Read the canonical host source-sync record without writing it."""
        path = self.source_sync_read_path
        if path.is_symlink() or not path.exists():
            return None
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict) or value.get("schema") != SOURCE_SYNC_SCHEMA:
            return None
        required = {
            "schema",
            "status",
            "code",
            "source_root",
            "source_head",
            "source_tree",
            "remote",
            "remote_url",
            "branch",
            "updated_at",
        }
        status = value.get("status")
        expected = required | ({"failure"} if status == "failed" else set())
        if set(value) != expected:
            return None
        if (
            status not in {"success", "failed"}
            or not isinstance(value.get("code"), str)
            or not SOURCE_SYNC_CODE_RE.fullmatch(value["code"])
            or not isinstance(value.get("source_root"), str)
            or not value["source_root"].startswith("/")
            or '"' in value["source_root"]
            or "\\" in value["source_root"]
            or any(ord(character) < 0x20 for character in value["source_root"])
            or not isinstance(value.get("source_head"), str)
            or not SOURCE_SYNC_IDENTITY_RE.fullmatch(value["source_head"])
            or not isinstance(value.get("source_tree"), str)
            or not SOURCE_SYNC_IDENTITY_RE.fullmatch(value["source_tree"])
            or not isinstance(value.get("remote"), str)
            or re.fullmatch(r"[A-Za-z0-9_.-]+", value["remote"]) is None
            or not isinstance(value.get("remote_url"), str)
            or not value["remote_url"]
            or '"' in value["remote_url"]
            or "\\" in value["remote_url"]
            or any(ord(character) < 0x20 for character in value["remote_url"])
            or not isinstance(value.get("branch"), str)
            or re.fullmatch(r"[A-Za-z0-9._/-]+", value["branch"]) is None
            or not isinstance(value.get("updated_at"), str)
            or SOURCE_SYNC_TIMESTAMP_RE.fullmatch(value["updated_at"]) is None
        ):
            return None
        failure = value.get("failure")
        if status == "failed" and (
            not isinstance(failure, str) or not SOURCE_SYNC_CODE_RE.fullmatch(failure)
        ):
            return None
        return value

    def _ensure_layout(self) -> None:
        _ensure_directory(self.paths.runtime_root)
        self._enforce_private_directory(self.paths.runtime_root)
        controller_dirs = (RECEIPT_DIR, GENERATION_DIR, TASK_DIR)
        for name in controller_dirs:
            path = self.paths.runtime_root / name
            _ensure_directory(path)
            self._enforce_private_directory(path)
        for path in (
            self.paths.spool,
            self.paths.archive,
            self.paths.cache,
            self.paths.codex_home,
        ):
            _ensure_directory(path)
            self._enforce_private_directory(path)
        _ensure_directory(self.paths.container_runtime, mode=0o700)
        try:
            exchange_mode = stat.S_IMODE(
                os.stat(self.paths.container_runtime, follow_symlinks=False).st_mode
            )
        except OSError as exc:
            raise BootstrapError(
                "exchange_directory_invalid",
                "cannot inspect container runtime exchange mode",
            ) from exc
        if exchange_mode != 0o700:
            raise BootstrapError(
                "exchange_directory_invalid",
                "container runtime exchange mode is not 0700",
            )
        if not self.paths.lock.exists():
            try:
                fd = os.open(
                    self.paths.lock,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
            except OSError as exc:
                raise BootstrapError(
                    "symlink_path_rejected",
                    "lifecycle lock was replaced during creation",
                ) from exc
            os.close(fd)
        elif self.paths.lock.is_symlink():
            raise BootstrapError("symlink_path_rejected", "lifecycle lock is a symlink")
        private_log = self.private_log_root
        if private_log.exists() and private_log.is_symlink():
            raise BootstrapError(
                "symlink_path_rejected", "private log checkout is a symlink"
            )
        if not private_log.exists():
            raise BootstrapError(
                "private_log_mount_invalid",
                "resident container is missing the host-owned private log mount",
            )

    def _enforce_private_directory(self, path: Path) -> None:
        """Make an owned Host control directory private and verify readback."""
        try:
            os.chmod(path, 0o700, follow_symlinks=False)
        except OSError as exc:
            raise BootstrapError(
                "runtime_directory_invalid", f"cannot protect runtime directory: {path}"
            ) from exc
        if stat.S_IMODE(os.stat(path, follow_symlinks=False).st_mode) != 0o700:
            raise BootstrapError(
                "runtime_directory_mode_mismatch",
                f"runtime directory mode is not 0700: {path}",
            )

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        """Serialize lifecycle transitions using the external lock file."""
        self._ensure_layout()
        handle = os.fdopen(os.open(self.paths.lock, os.O_RDWR | os.O_NOFOLLOW), "r+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def _new_state(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_STATE,
            "control_parent_root": str(self.paths.control_parent_root),
            "runtime_root": str(self.paths.runtime_root),
            "repository_root": str(self.repository_root),
            "control_root_digest": self.control_digest,
            "manifest_digest": self.manifest_digest,
            "state": "uninstalled",
            "active_task_count": 0,
            "current_generation": None,
            "rollback_generation": None,
            "generation_counter": 0,
            "targets": {},
            "generations": {},
            "tasks": {},
            "resources": {},
            "managed_paths": [],
            "managed_links": [],
            "updated_at": _now(),
        }

    def _read_state(self) -> dict[str, Any]:
        try:
            raw = _safe_read(self.paths.state, field="state")
        except BootstrapError as exc:
            if exc.code == "path_missing" and not self.paths.owner.exists():
                return self._new_state()
            if exc.code == "path_missing" and self.paths.owner.exists():
                raise BootstrapError(
                    "state_missing",
                    "runtime owner exists but lifecycle state is missing",
                ) from exc
            raise

        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BootstrapError(
                "state_invalid", "runtime state is not valid JSON"
            ) from exc
        if not isinstance(value, dict) or value.get("schema") not in {
            SCHEMA_STATE,
            "agent-canon.bootstrap-state.v1",
        }:
            raise BootstrapError("state_invalid", "runtime state schema is unsupported")
        if value.get("control_root_digest") != self.control_digest:
            raise BootstrapError(
                "shared_runtime_owned_elsewhere",
                "runtime is owned by another control root",
                evidence={
                    "owner_control_root_digest": value.get("control_root_digest"),
                    "requested_control_root_digest": self.control_digest,
                },
            )
        return value

    def _write_state(self, state: dict[str, Any]) -> None:
        state["schema"], state["updated_at"] = SCHEMA_STATE, _now()
        state["repository_root"] = str(self.repository_root)
        _atomic_json(self.paths.state, state)
        _atomic_json(
            self.paths.owner,
            {
                "schema": "agent-canon.bootstrap-owner.v1",
                "control_root_digest": self.control_digest,
                "control_parent_root": str(self.paths.control_parent_root),
                "runtime_root": str(self.paths.runtime_root),
                "repository_root": str(self.repository_root),
                "manifest_digest": state.get("manifest_digest", self.manifest_digest),
            },
        )

    def _image_tag(self) -> str:
        container_image = os.environ.get("AGENT_CANON_IMAGE_REF")
        if container_image:
            return container_image
        return (
            f"agent-canon-tools:{self.control_digest[:16]}-{self.manifest_digest[:16]}"
        )

    def _labels(self) -> dict[str, str]:
        return {
            "io.agent-canon.runtime": "shared-v1",
            "io.agent-canon.control-root-digest": self.control_digest,
        }

    def _resource_records(self) -> dict[str, Any]:
        name = os.environ.get("AGENT_CANON_CONTAINER_NAME")
        if not name:
            name = str(self.manifest["container"]["name_template"]).replace(
                "<effective-uid>", self.control_digest[:16]
            )
        return {
            "image": {
                "id": None,
                "tag": self._image_tag(),
                "owned": True,
                "state": "absent",
            },
            "container": {
                "id": None,
                "name": name,
                "owned": True,
                "labels": self._labels(),
                "state": "absent",
            },
        }

    def _receipt(
        self,
        operation: str,
        status: str,
        code: str,
        *,
        before: str | None,
        after: str | None,
        details: Mapping[str, Any] | None = None,
        state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        resources = (
            state.get("resources", {})
            if state is not None
            else self._resource_records()
        )
        return {
            "schema": SCHEMA_RECEIPT,
            "operation": operation,
            "status": status,
            "code": code,
            "control_root_digest": self.control_digest,
            "manifest_digest": (
                state.get("manifest_digest", self.manifest_digest)
                if state is not None
                else self.manifest_digest
            ),
            "before_state": before,
            "after_state": after,
            "resource_ids": json.loads(_json(resources)),
            "created_at": _now(),
            "nonce": secrets.token_hex(16),
            "details": dict(details or {}),
        }

    def _write_receipt(self, payload: Mapping[str, Any]) -> Path:
        name = (
            f"{payload['created_at'].replace(':', '').replace('-', '')}-"
            f"{payload['operation']}-{payload['nonce']}.json"
        )
        destination = self.paths.receipts / _slug(name)
        _atomic_json(destination, payload)
        return destination

    def _result(
        self, payload: Mapping[str, Any], *, write: bool = True
    ) -> dict[str, Any]:
        result = dict(payload)
        if write:
            result["receipt_path"] = str(self._write_receipt(result))
        return result

    def _state_summary(self, state: Mapping[str, Any]) -> dict[str, Any]:
        """Return bounded lifecycle state without target paths or raw records."""
        resources = state.get("resources", {})
        image = resources.get("image", {}) if isinstance(resources, dict) else {}
        container = (
            resources.get("container", {}) if isinstance(resources, dict) else {}
        )
        return {
            "state": state.get("state"),
            "active_task_count": state.get("active_task_count", 0),
            "current_generation": state.get("current_generation"),
            "rollback_generation": state.get("rollback_generation"),
            "target_digests": sorted(state.get("targets", {}).keys()),
            "generations": {
                generation_id: {
                    "state": generation.get("state"),
                    "target_digests": sorted(generation.get("targets", {}).keys()),
                    "failure": generation.get("failure"),
                }
                for generation_id, generation in state.get("generations", {}).items()
            },
            "resources": {
                "image": {
                    "id": image.get("id"),
                    "tag": image.get("tag"),
                    "owned": image.get("owned"),
                    "state": image.get("state"),
                },
                "container": {
                    "id": container.get("id"),
                    "name": container.get("name"),
                    "owned": container.get("owned"),
                    "state": container.get("state"),
                },
            },
        }

    def _target_record(
        self,
        root: Path,
        mode: str,
        mutation_capability: Mapping[str, Any] | None = None,
        *,
        host_root: str | None = None,
        host_digest: str | None = None,
    ) -> dict[str, Any]:
        if mode not in {"read-only", "explicit-target-write"}:
            raise BootstrapError(
                "invalid_target_mode", f"unsupported target mode: {mode}"
            )

        # The host adapter validates the real source checkout and derives its
        # digest before it creates the target bind mount.  The resident cannot
        # see that host path; it must validate only the mounted container path
        # and carry the already validated host metadata into the state record.
        # Keeping these two namespaces separate prevents a container-side
        # Path.exists()/is_dir() check from producing a false failure for a
        # perfectly valid host source such as /home/user/agent-canon.
        if host_root is not None:
            if not isinstance(host_root, str) or not host_root.startswith("/"):
                raise BootstrapError(
                    "target_host_root_invalid",
                    "host target root must be an absolute path",
                )
            if any(character in host_root for character in '\x00\n\r\t\\"'):
                raise BootstrapError(
                    "target_host_root_invalid",
                    "host target root contains a forbidden character",
                )
            if not isinstance(host_digest, str) or not re.fullmatch(
                r"[A-Za-z0-9_.-]{1,128}", host_digest
            ):
                raise BootstrapError(
                    "target_digest_invalid",
                    "host target digest is invalid",
                )
            container_root = _normalize_absolute_path(root)
            expected_root = Path("/targets") / host_digest
            if container_root != expected_root:
                raise BootstrapError(
                    "target_mount_invalid",
                    "target request does not name its declared container mount",
                )
            # This is the resident-side verification point.  It checks the
            # bind-mounted namespace, never the host_root value above.
            canonical = _existing_no_symlink(
                container_root, field="mounted target root"
            )
            record: dict[str, Any] = {
                "root": str(canonical),
                "host_root": host_root,
                "mode": mode,
                "digest": host_digest,
            }
        else:
            canonical = _existing_no_symlink(root, field="target root")
            record = {
                "root": str(canonical),
                "mode": mode,
                "digest": sha256_text(str(canonical)),
            }
        if mode == "explicit-target-write":
            if not isinstance(mutation_capability, Mapping):
                raise BootstrapError(
                    "mutation_capability_required",
                    "explicit-target-write requires a typed capability",
                )
            if set(mutation_capability) != {"allowed_paths", "purpose", "authority"}:
                raise BootstrapError(
                    "mutation_capability_invalid", "capability fields are invalid"
                )
            allowed = mutation_capability.get("allowed_paths")
            if not isinstance(allowed, list) or not allowed:
                raise BootstrapError(
                    "mutation_capability_invalid", "allowed_paths is required"
                )
            normalized: list[str] = []
            for value in allowed:
                if not isinstance(value, str):
                    raise BootstrapError(
                        "mutation_capability_invalid", "allowed path is not text"
                    )
                relative = Path(value)
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or not relative.parts
                ):
                    raise BootstrapError(
                        "mutation_capability_invalid", f"unsafe allowed path: {value}"
                    )
                _existing_path_no_symlink(
                    canonical / relative, field="mutation allowed path"
                )
                normalized.append(relative.as_posix())
            for field in ("purpose", "authority"):
                if (
                    not isinstance(mutation_capability.get(field), str)
                    or not mutation_capability[field].strip()
                ):
                    raise BootstrapError("mutation_capability_invalid", field)
            record.update(
                {
                    "allowed_paths": sorted(set(normalized)),
                    "purpose": mutation_capability["purpose"],
                    "authority": mutation_capability["authority"],
                }
            )
        elif mutation_capability is not None:
            raise BootstrapError(
                "mutation_capability_unexpected",
                "read-only target cannot accept mutation capability",
            )
        return record

    def _prune_stale_targets(self, state: dict[str, Any]) -> list[str]:
        """Remove only target records whose derived source is unavailable.

        The resident controller inspects the mounted ``root`` path because
        host paths are intentionally outside its namespace. Malformed records
        are left for the normal manifest/readback validators to reject.
        """
        raw_targets = state.get("targets")
        if not isinstance(raw_targets, Mapping):
            return []
        targets = dict(raw_targets)
        stale: list[str] = []
        for digest, record in targets.items():
            if not isinstance(digest, str) or not isinstance(record, Mapping):
                continue
            source_value = record.get("root")
            if not isinstance(source_value, str) or not source_value:
                continue
            source = Path(source_value)
            if source.is_symlink() or not source.is_dir():
                stale.append(digest)
        if not stale:
            return []
        for digest in stale:
            targets.pop(digest, None)
        state["targets"] = targets
        generations = state.get("generations")
        if isinstance(generations, Mapping):
            for generation in generations.values():
                if not isinstance(generation, dict):
                    continue
                generation_targets = generation.get("targets")
                if not isinstance(generation_targets, Mapping):
                    continue
                generation["targets"] = {
                    digest: record
                    for digest, record in generation_targets.items()
                    if digest not in stale
                }
        return stale

    @staticmethod
    def _same_target_record(
        existing: Mapping[str, Any], candidate: Mapping[str, Any]
    ) -> bool:
        """Compare target identity/capability while ignoring host-only metadata."""
        keys = ("root", "mode", "digest", "allowed_paths", "purpose", "authority")
        return all(existing.get(key) == candidate.get(key) for key in keys)

    def _write_mounts(self, state: Mapping[str, Any]) -> None:
        lines = [f"schema = {json.dumps(SCHEMA_MOUNTS)}", ""]
        for key, record in sorted(state.get("targets", {}).items()):
            lines += [
                f"[targets.{key}]",
                f"root = {json.dumps(record['root'])}",
                f"mode = {json.dumps(record['mode'])}",
                f"digest = {json.dumps(record['digest'])}",
                "",
            ]
        # The controller writes the directory-mounted registry. The separate
        # file bind at REGISTRY_DESTINATION is read-only and is only a host
        # readback surface; replacing that inode from inside the container
        # would fail and leave a stale registry visible to the tool process.
        destination = self.paths.container_runtime / "mounts.toml"
        _atomic_bytes(destination, "\n".join(lines).encode("utf-8"), mode=0o444)

    def _write_mount_manifest(self, state: Mapping[str, Any]) -> None:
        """Write the strict host-readable target mount manifest."""
        path = self.paths.container_runtime / "mounts.tsv"
        lines: list[str] = []
        targets = state.get("targets", {})
        if isinstance(targets, Mapping):
            for digest, record in sorted(targets.items()):
                if not isinstance(record, Mapping):
                    continue
                source = record.get("host_root")
                mode = record.get("mode")
                if not isinstance(source, str) or not isinstance(mode, str):
                    continue
                if any(
                    char in source or char in str(digest) for char in ("\t", "\n", "\r")
                ):
                    raise BootstrapError(
                        "mount_manifest_invalid",
                        "target mount contains a control character",
                    )
                if mode != "read-only":
                    raise BootstrapError(
                        "mount_manifest_invalid",
                        "only read-only targets may be projected into the resident mount manifest",
                    )
                lines.append(
                    f"target\t{digest}\t{source}\t/targets/{digest}\tread-only"
                )
        _atomic_bytes(
            path,
            ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8"),
            mode=0o444,
        )

    def _task_process_lease_path(self, task_id: str) -> Path:
        return self.paths.tasks / _slug(task_id) / "locks" / "process-lease.lock"

    def _open_task_process_lease(
        self, task_id: str, *, create: bool = False
    ) -> int | None:
        """Open and exclusively lock one task's process-owned lease file."""
        path = self._task_process_lease_path(task_id)
        if not create:
            try:
                _existing_no_symlink(path.parent, field="task process lease directory")
            except BootstrapError as exc:
                if exc.code == "path_missing":
                    raise BootstrapError(
                        "task_lease_missing", "process-owned task lease file is missing"
                    ) from exc
                raise
        flags = os.O_RDWR | os.O_NOFOLLOW
        if create:
            flags |= os.O_CREAT | os.O_EXCL
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileNotFoundError as exc:
            raise BootstrapError(
                "task_lease_missing", "process-owned task lease file is missing"
            ) from exc
        except OSError as exc:
            code = (
                "task_lease_exists"
                if exc.errno == errno.EEXIST
                else "task_lease_invalid"
            )
            raise BootstrapError(
                code, "cannot open process-owned task lease file"
            ) from exc
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise BootstrapError(
                    "task_lease_invalid",
                    "process-owned task lease is not a regular file",
                )
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            return None
        except OSError as exc:
            os.close(descriptor)
            raise BootstrapError(
                "task_lease_lock_failed", "cannot lock process-owned task lease"
            ) from exc
        except BootstrapError:
            os.close(descriptor)
            raise
        return descriptor

    def _reconcile_process_task_leases_locked(self, state: dict[str, Any]) -> None:
        """Release only process-owned leases whose inherited lock has drained."""
        tasks = state.get("tasks", {})
        if not isinstance(tasks, dict):
            raise BootstrapError("state_invalid", "task state is not an object")
        for task_id, task in list(tasks.items()):
            if (
                not isinstance(task, dict)
                or task.get("state") != "active"
                or task.get("lease_kind") != "process"
            ):
                continue
            lease_fd = self._open_task_process_lease(task_id)
            if lease_fd is None:
                continue
            try:
                self._release_task_locked(state, task_id, outcome="terminated")
            finally:
                os.close(lease_fd)

    def _admit_task_locked(
        self,
        state: dict[str, Any],
        task_id: str,
        *,
        target_root: Path | None = None,
        process_owned: bool = False,
    ) -> tuple[dict[str, Any], int | None]:
        task_id = _slug(task_id)
        if state.get("state") not in ADMISSION_STATES:
            raise BootstrapError(
                "task_admission_closed", f"runtime state is {state.get('state')}"
            )
        self._reconcile_process_task_leases_locked(state)
        if task_id in state.get("tasks", {}):
            raise BootstrapError(
                "task_already_exists", f"task already exists: {task_id}"
            )
        if int(state.get("active_task_count", 0)) >= int(
            self.manifest["container"]["max_parallel_tasks"]
        ):
            raise BootstrapError(
                "task_capacity_exhausted", "max parallel task slots are reserved"
            )
        target = self._target_record(target_root, "read-only") if target_root else None
        if target:
            target_digest = os.environ.get("AGENT_CANON_TARGET_DIGEST")
            if target_digest and target_digest in state.get("targets", {}):
                target = state["targets"][target_digest]
        if target and target["digest"] not in state.get("targets", {}):
            raise BootstrapError(
                "target_not_registered",
                "task target is not in the active mount generation",
            )
        if target and any(
            record.get("state") == "active"
            and record.get("target", {}).get("digest") == target["digest"]
            for record in state.get("tasks", {}).values()
        ):
            raise BootstrapError(
                "target_busy", "target is already reserved by an active task"
            )
        task_path = self.paths.tasks / task_id
        _ensure_directory(task_path)
        for child in ("tmp", "locks", "reports", "logs", "receipts"):
            _ensure_directory(task_path / child)
        lease_fd = (
            self._open_task_process_lease(task_id, create=True)
            if process_owned
            else None
        )
        if process_owned and lease_fd is None:
            raise BootstrapError(
                "task_lease_lock_failed", "cannot hold process-owned task lease"
            )
        record = {
            "id": task_id,
            "state": "active",
            "generation": state.get("current_generation"),
            "target": target,
            "started_at": _now(),
            "pinned": True,
        }
        if process_owned:
            record["lease_kind"] = "process"
        state.setdefault("tasks", {})[task_id] = record
        state["active_task_count"] = int(state.get("active_task_count", 0)) + 1
        state["state"] = "running"
        try:
            self._write_state(state)
        except BaseException:
            if lease_fd is not None:
                os.close(lease_fd)
            raise
        return record, lease_fd

    def admit_task(
        self, task_id: str, *, target_root: Path | None = None
    ) -> dict[str, Any]:
        """Atomically reserve one task slot and its target generation."""
        with self.locked():
            state = self._read_state()
            before = state["state"]
            record, lease_fd = self._admit_task_locked(
                state, task_id, target_root=target_root
            )
            if lease_fd is not None:
                os.close(lease_fd)
                raise BootstrapError(
                    "task_lease_scope_invalid",
                    "manual task admission cannot own a process lease",
                )
            return self._result(
                self._receipt(
                    "task_admit",
                    "ok",
                    "task_reserved",
                    before=before,
                    after="running",
                    details={"task": record},
                    state=state,
                )
            )

    def _release_task_locked(
        self, state: dict[str, Any], task_id: str, *, outcome: str = "completed"
    ) -> dict[str, Any]:
        task = state.get("tasks", {}).get(_slug(task_id))
        if not isinstance(task, dict) or task.get("state") != "active":
            raise BootstrapError("task_not_active", f"task is not active: {task_id}")
        task.update(
            {
                "state": "completed" if outcome == "completed" else "cancelled",
                "outcome": outcome,
                "finished_at": _now(),
                "pinned": False,
            }
        )
        state["active_task_count"] = max(0, int(state.get("active_task_count", 0)) - 1)
        state["state"] = "ready" if state["active_task_count"] == 0 else "running"
        self._write_state(state)
        return task

    def release_task(
        self, task_id: str, *, outcome: str = "completed"
    ) -> dict[str, Any]:
        """Release one task slot and mark its state unpinned."""
        with self.locked():
            state = self._read_state()
            before = state["state"]
            task_record = state.get("tasks", {}).get(_slug(task_id))
            lease_fd = None
            if (
                isinstance(task_record, dict)
                and task_record.get("state") == "active"
                and task_record.get("lease_kind") == "process"
            ):
                lease_fd = self._open_task_process_lease(task_id)
                if lease_fd is None:
                    raise BootstrapError(
                        "task_process_active",
                        "cannot release a process-owned task while its worker is live",
                    )
            try:
                task = self._release_task_locked(state, task_id, outcome=outcome)
            finally:
                if lease_fd is not None:
                    os.close(lease_fd)
            return self._result(
                self._receipt(
                    "task_release",
                    "ok",
                    "task_released",
                    before=before,
                    after=state["state"],
                    details={"task": task},
                    state=state,
                )
            )

    def _managed_links(self) -> list[dict[str, str]]:
        projection_root: Path | None = None
        raw_projection_root = os.environ.get(
            "AGENT_CANON_HOST_INSTALL_ROOT", ""
        ).strip()
        if raw_projection_root:
            if not raw_projection_root.startswith("/") or any(
                character in raw_projection_root for character in "\x00\t\n\r"
            ):
                raise BootstrapError(
                    "codex_projection_root_invalid",
                    "host install root must be an absolute path without controls",
                )
            projection_root = Path(raw_projection_root)

        def projection_source(source: Path) -> Path:
            """Map an image-owned source to its corresponding host checkout."""
            if projection_root is None:
                return source
            try:
                relative = source.relative_to(self.repository_root)
            except ValueError:
                return source
            return projection_root / relative

        # One directory reference follows Git additions/removals without a
        # per-file registry or a generated copy in the runtime exchange.
        skills = self.repository_root / ".codex" / "personal" / "skills"
        if not skills.is_dir() or skills.is_symlink():
            raise BootstrapError("skill_source_missing", str(skills))
        entries: list[dict[str, str]] = [
            {
                "surface": "skills",
                "source": str(projection_source(skills)),
                "validation_source": str(skills),
                "relative": "agent-canon",
            }
        ]
        for surface, source in (
            ("agents", self.repository_root / ".codex" / "agents"),
            ("hooks", self.repository_root / ".codex" / "hooks"),
            ("config", self.repository_root / ".codex" / "config.toml"),
        ):
            if source.is_file():
                entries.append(
                    {
                        "surface": surface,
                        "source": str(projection_source(source)),
                        "validation_source": str(source),
                        "relative": source.name,
                        "digest": sha256_bytes(
                            _safe_read(source, field="Codex source")
                        ),
                    }
                )
            elif source.is_dir() and not source.is_symlink():
                for path in sorted(source.rglob("*")):
                    if path.is_file() and not path.is_symlink():
                        entries.append(
                            {
                                "surface": surface,
                                "source": str(projection_source(path)),
                                "validation_source": str(path),
                                "relative": str(path.relative_to(source)),
                                "digest": sha256_bytes(
                                    _safe_read(path, field="Codex source")
                                ),
                            }
                        )
        # Private runtime Skill candidates are an external, runtime-local
        # surface.  They are linked into the isolated CODEX_HOME only; this
        # never changes the public catalog or the source-tree personal view.
        private_skills = self.paths.runtime_root / "private-skills"
        if private_skills.is_dir() and not private_skills.is_symlink():
            for path in sorted(private_skills.rglob("*")):
                if path.is_file() and not path.is_symlink():
                    entries.append(
                        {
                            "surface": "skills",
                            "source": str(path),
                            "relative": str(path.relative_to(private_skills)),
                            "digest": sha256_bytes(
                                _safe_read(path, field="private Skill source")
                            ),
                        }
                    )
        return entries

    def _codex_prepare_locked(self) -> dict[str, Any]:
        """Prepare links while the caller owns the lifecycle lock."""
        with contextlib.nullcontext():
            state = self._read_state()
            _ensure_directory(self.paths.codex_home)
            desired = self._managed_links()

            def link_target(entry: Mapping[str, Any]) -> Path:
                """Return the path Codex actually reads for one surface."""
                if entry.get("surface") == "config":
                    return self.paths.codex_home / str(entry["relative"])
                return (
                    self.paths.codex_home
                    / str(entry["surface"])
                    / str(entry["relative"])
                )

            desired_targets = {str(link_target(entry)) for entry in desired}
            previous_entries: list[Mapping[str, Any]] = []
            previous_manifest = self.paths.codex_home / "manifest.json"
            if previous_manifest.is_file() and not previous_manifest.is_symlink():
                try:
                    previous_payload = json.loads(
                        previous_manifest.read_text(encoding="utf-8")
                    )
                except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise BootstrapError(
                        "codex_manifest_invalid",
                        "runtime-local Codex manifest is invalid",
                    ) from exc
                raw_previous = (
                    previous_payload.get("links", [])
                    if isinstance(previous_payload, dict)
                    else []
                )
                if isinstance(raw_previous, list):
                    previous_entries = [
                        entry for entry in raw_previous if isinstance(entry, dict)
                    ]
            previous_sources = {
                str(
                    Path(str(entry["target"]))
                    if entry.get("target")
                    else link_target(entry)
                ): entry
                for entry in previous_entries
                if entry.get("managed") is True
            }
            stale_links: list[str] = []
            for entry in previous_entries:
                target = Path(str(entry.get("target", "")))
                source = Path(str(entry.get("source", "")))
                if str(target) in desired_targets or entry.get("managed") is not True:
                    continue
                if target.is_symlink() and target.resolve() == source.resolve():
                    target.unlink()
                    stale_links.append(str(target))
            links: list[dict[str, Any]] = []
            for entry in desired:
                target = link_target(entry)
                _ensure_directory(target.parent)
                if target.exists() or target.is_symlink():
                    if (
                        not target.is_symlink()
                        or target.resolve() != Path(entry["source"]).resolve()
                    ):
                        previous = previous_sources.get(str(target))
                        previous_source = (
                            Path(str(previous.get("source", "")))
                            if previous is not None
                            else None
                        )
                        if (
                            previous_source is None
                            or not target.is_symlink()
                            or target.resolve() != previous_source.resolve()
                        ):
                            raise BootstrapError(
                                "skill_collision",
                                f"managed Codex target already exists: {target}",
                            )
                        target.unlink()
                        target.symlink_to(entry["source"])
                        created = True
                    else:
                        created = False
                else:
                    target.symlink_to(entry["source"])
                    created = True
                links.append(
                    {
                        **entry,
                        "target": str(target),
                        "created": created,
                        "managed": True,
                    }
                )
            _atomic_json(
                self.paths.codex_home / "manifest.json",
                {
                    "schema": SCHEMA_SKILLS,
                    "source_root": str(
                        os.environ.get(
                            "AGENT_CANON_HOST_INSTALL_ROOT", self.repository_root
                        )
                    ),
                    "manifest_digest": self.manifest_digest,
                    "stale_links_removed": stale_links,
                    "links": links,
                },
            )
            state["managed_links"] = links
            self._write_state(state)
            return self._result(
                self._receipt(
                    "codex_prepare",
                    "ok",
                    "codex_home_ready",
                    before=state["state"],
                    after=state["state"],
                    details={
                        "codex_home": str(self.paths.codex_home),
                        "links": links,
                        "requires_new_session": True,
                    },
                    state=state,
                )
            )

    def codex_prepare(self) -> dict[str, Any]:
        """Install fixed links to Git-distributed skills into isolated ``CODEX_HOME``."""
        with self.locked():
            return self._codex_prepare_locked()

    def codex_launch(self, project_root: Path) -> dict[str, Any]:
        """Launch Codex with a process-local isolated home."""
        project = _existing_no_symlink(project_root, field="Codex project root")
        prepared = self.codex_prepare()
        session_root = self.paths.codex_home / "sessions"
        _ensure_directory(session_root)
        self._enforce_private_directory(session_root)
        executable = os.environ.get("AGENT_CANON_CODEX", "codex")
        env = os.environ.copy()
        env["CODEX_HOME"] = str(self.paths.codex_home)
        env["AGENT_CANON_CONTROL_PARENT_ROOT"] = str(self.paths.control_parent_root)
        env["AGENT_CANON_RUNTIME_ROOT"] = str(self.paths.runtime_root)
        env[CODEX_SESSION_ROOT_ENV] = str(session_root)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            result = subprocess.run(
                [executable, "--project-root", str(project)],
                cwd=str(project),
                env=env,
                shell=False,
                check=False,
            )
        except OSError as exc:
            raise BootstrapError(
                "codex_unavailable", "Codex executable is unavailable"
            ) from exc
        if result.returncode != 0:
            raise BootstrapError(
                "codex_failed", f"Codex exited with {result.returncode}"
            )
        return prepared

    def exec(
        self,
        root: Path,
        argv: Sequence[str],
        *,
        extra_environment: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a typed argv in a registered target and collect a receipt."""
        _validate_tool_plane_argv(root, self.repository_root, argv)
        target = self._target_record(root, "read-only")
        with self.locked():
            state = self._read_state()
            target_digest = os.environ.get("AGENT_CANON_TARGET_DIGEST")
            if target_digest and target_digest in state.get("targets", {}):
                target = state["targets"][target_digest]
            if target["digest"] not in state.get("targets", {}):
                raise BootstrapError(
                    "target_not_registered", "exec root is not registered"
                )
            active_target = state["targets"][target["digest"]]
            mutation_before = (
                _source_snapshot(root)
                if active_target.get("mode") == "explicit-target-write"
                else None
            )
            mutation_changed_before = (
                _changed_source_paths(root) if mutation_before is not None else set()
            )
            task_id = f"exec-{secrets.token_hex(6)}"
            _, lease_fd = self._admit_task_locked(
                state, task_id, target_root=root, process_owned=True
            )
            if lease_fd is None:
                raise BootstrapError(
                    "task_lease_scope_invalid",
                    "exec admission did not return its process lease",
                )
            try:
                if not os.environ.get("AGENT_CANON_CONTAINER_ID"):
                    raise BootstrapError(
                        "container_control_missing_identity",
                        "resident container identity was not provided",
                    )
                environment = {
                    "AGENT_CANON_TARGET_ROOT": f"/targets/{target['digest']}",
                    "AGENT_CANON_TASK_ROOT": f"/targets/{target['digest']}",
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "safe.directory",
                    "GIT_CONFIG_VALUE_0": f"/targets/{target['digest']}",
                    "AGENT_CANON_MOUNT_REGISTRY": REGISTRY_DESTINATION,
                    # Runtime log readers use the existing explicit archive
                    # override. The host-owned private-log bind is the sole
                    # accumulated archive; runtime/ is only task exchange.
                    "AGENT_CANON_HOOK_ARCHIVE_DIR": PRIVATE_LOG_DESTINATION,
                    "AGENT_CANON_LOG_ROOT": PRIVATE_LOG_DESTINATION,
                    "AGENT_CANON_RUNTIME_ROOT": CONTAINER_RUNTIME_DESTINATION,
                    "TMPDIR": f"{CONTAINER_RUNTIME_DESTINATION}/tasks/{task_id}/tmp",
                    "RUFF_CACHE_DIR": RUFF_CACHE_DESTINATION,
                }
                environment.update(extra_environment or {})
                result = _run_resident_command(
                    list(argv),
                    cwd=f"/targets/{target['digest']}",
                    environment=environment,
                    timeout=int(self.manifest["container"]["task_timeout_seconds"]),
                    # The worker keeps the reservation locked if this controller dies.
                    pass_fds=(lease_fd,),
                )
                task_path = self.paths.tasks / task_id
                io = _io_evidence(
                    task_path,
                    result.stdout or "",
                    result.stderr or "",
                    quota_bytes=int(self.manifest["container"]["task_log_quota_bytes"]),
                )
                state["tasks"][task_id]["io"] = io
                details = {
                    "argv": _redact_argv(argv),
                    "cwd": str(root),
                    "exit": result.returncode,
                    "execution_plane": "agentcanon_tool_container",
                    **io,
                }
                if mutation_before is not None:
                    changed = _changed_source_paths(root)
                    newly_changed = changed - mutation_changed_before
                    allowed = set(active_target.get("allowed_paths", []))
                    outside = sorted(
                        path
                        for path in newly_changed
                        if not any(
                            path == item or path.startswith(item + "/")
                            for item in allowed
                        )
                    )
                    mutation_after = _source_snapshot(root)
                    details["mutation"] = {
                        "purpose": active_target.get("purpose"),
                        "authority": active_target.get("authority"),
                        "allowed_paths": sorted(allowed),
                        "changed_paths": sorted(newly_changed),
                        "before_digest": mutation_before["tree_digest"],
                        "after_digest": mutation_after["tree_digest"],
                    }
                    if outside:
                        raise BootstrapError(
                            "mutation_scope_violation",
                            f"write escaped allowed paths: {outside}",
                        )
                if result.returncode != 0:
                    failure_receipt = self._result(
                        self._receipt(
                            "exec",
                            "error",
                            "tool_failed",
                            before="running",
                            after="running",
                            details=details,
                            state=state,
                        )
                    )
                    raise BootstrapError(
                        "tool_failed",
                        f"command exited with {result.returncode}",
                        evidence={
                            "exit": result.returncode,
                            "receipt_path": failure_receipt["receipt_path"],
                            "stdout_digest": io["stdout_digest"],
                            "stdout_preview": io["stdout_preview"],
                            "stdout_truncated": io["stdout_truncated"],
                            "stderr_digest": io["stderr_digest"],
                            "stderr_preview": io["stderr_preview"],
                            "stderr_truncated": io["stderr_truncated"],
                        },
                    )
                return self._result(
                    self._receipt(
                        "exec",
                        "ok",
                        "completed",
                        before="running",
                        after="running",
                        details=details,
                        state=state,
                    )
                )
            finally:
                try:
                    self._release_task_locked(state, task_id)
                finally:
                    os.close(lease_fd)

    def tool_run(
        self,
        catalog_id: str,
        argv: Sequence[str],
        *,
        root: Path | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Dispatch a catalog command through the resident AgentCanon CLI."""
        _slug(catalog_id)
        with self.locked():
            state = self._read_state()
            if not state.get("targets"):
                raise BootstrapError(
                    "target_not_registered", "tool run requires a registered target"
                )
            targets = state["targets"]
            if root is None:
                if len(targets) != 1:
                    raise BootstrapError(
                        "target_root_required",
                        "tool run requires --root when multiple targets are registered",
                    )
                target = next(iter(targets.values()))
            else:
                self._target_record(root, "read-only")
                requested_digest = os.environ.get("AGENT_CANON_TARGET_DIGEST")
                target = targets.get(requested_digest)
                if not isinstance(target, dict):
                    raise BootstrapError(
                        "target_not_registered", "tool run root is not registered"
                    )
        if environment is None:
            # Direct ``bootstrap.sh tool run`` calls do not carry the host
            # dispatcher request envelope. Resolve only the catalog's declared
            # output capability so external-artifact tools still receive a
            # non-root container runtime output capability; read-only tools
            # continue to receive no output capability at all.
            environment = {}
            try:
                from ..dispatch.tool_dispatch import load_specs  # type: ignore[import-not-found]
            except ImportError:
                from tools.runtime.dispatch.tool_dispatch import load_specs  # type: ignore[no-redef]
            try:
                specs, _schema = load_specs(self.repository_root)
                spec = specs.get(catalog_id)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise BootstrapError(
                    "tool_catalog_invalid", "cannot resolve tool output capability"
                ) from exc
            if spec is not None and spec.output_root == "external-runtime":
                environment = {
                    "AGENT_CANON_OUTPUT_ROOT": f"{CONTAINER_RUNTIME_DESTINATION}/tool-output"
                }
            elif spec is not None and spec.output_root == "explicit-target":
                environment = {"AGENT_CANON_OUTPUT_ROOT": str(target["root"])}
        return self.exec(
            Path(target["root"]),
            [
                "agent-canon-tool",
                "tool",
                "run",
                catalog_id,
                "--",
                *list(argv),
            ],
            extra_environment=environment,
        )

    def template_export(self, root: Path, profile: str, output: str) -> dict[str, Any]:
        """Export a template profile through the resident tool-container catalog."""
        _slug(profile)
        relative = Path(output)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise BootstrapError(
                "template_output_invalid", "output must be runtime-relative"
            )
        target = self._target_record(root, "read-only")
        host_output = self.paths.runtime_root / "template-exports" / relative
        if host_output.exists() or host_output.is_symlink():
            raise BootstrapError("template_output_exists", str(host_output))
        container_output = (
            f"{CONTAINER_RUNTIME_DESTINATION}/template-exports/{relative.as_posix()}"
        )
        return self.tool_run(
            "template-bundle",
            [
                "export",
                "--source-root",
                f"/targets/{target['digest']}",
                "--source-ref",
                "HEAD",
                "--profile",
                profile,
                "--output",
                container_output,
            ],
            root=root,
            environment={"AGENT_CANON_OUTPUT_ROOT": container_output},
        )

    def eval_collect(self, root: Path, run_id: str) -> dict[str, Any]:
        """Run every registered eval producer inside the resident tool image."""
        from tools.runtime.archive.runtime_log_paths import mounted_log_archive_root

        _slug(run_id)
        source = _existing_no_symlink(root, field="eval source root")
        spool = self.paths.spool / run_id
        if spool.exists():
            if spool.is_symlink():
                raise BootstrapError(
                    "symlink_path_rejected", f"eval spool is a symlink: {spool}"
                )
            raise BootstrapError(
                "eval_spool_exists", f"eval spool already exists: {run_id}"
            )
        task_id = f"eval-{run_id}"
        exchange_nonce = secrets.token_hex(16)
        exchange_tasks = self.paths.container_runtime / "tasks"
        exchange_task = exchange_tasks / task_id
        exchange = exchange_task / exchange_nonce
        before_source = _source_snapshot(source)
        capabilities = [
            "target-read-only",
            "producer-definitions-image-owned",
            "tool-container-execution",
            "external-runtime-write",
            "no-network",
        ]
        collection: dict[str, Any] = {
            "schema": "agent_canon.eval_collection.v1",
            "run_id": run_id,
            "task_id": run_id,
            "source_repository": str(source),
            "source_head_before": before_source["head"],
            "source_git_status_before": before_source["git_status"],
            "source_tree_digest_before": before_source["tree_digest"],
            "agent_canon_commit": os.environ.get(
                "AGENT_CANON_SOURCE_HEAD",
                _source_snapshot(self.repository_root)["head"],
            ),
            "manifest_digest": self.manifest_digest,
            "tool_image_digest": None,
            "exchange_nonce": exchange_nonce,
            "request_digest": sha256_text(
                f"{run_id}:{source}:{exchange_nonce}:{self.manifest_digest}"
            ),
            "capabilities": capabilities,
            "family_status": {},
            "producer_matrix": [],
            "metrics": {},
            "timestamp": _now(),
            "source_tree_unchanged": False,
            "status": "running",
        }
        task_outcome = "failed"
        with self.locked():
            state = self._read_state()
            before_state = state.get("state")
            target = self._target_record(source, "read-only")
            registered = state.get("targets", {}).get(target["digest"])
            if not isinstance(registered, dict):
                raise BootstrapError(
                    "target_not_registered", "eval root is not registered"
                )
            if registered.get("mode") != "read-only":
                raise BootstrapError(
                    "eval_target_not_read_only", "eval root is not mounted read-only"
                )
            _, lease_fd = self._admit_task_locked(state, task_id, target_root=source)
            if lease_fd is not None:
                os.close(lease_fd)
                raise BootstrapError(
                    "task_lease_scope_invalid",
                    "eval admission cannot own an exec process lease",
                )
            task_path = self.paths.tasks / task_id
            try:
                _ensure_directory(spool)
                for directory in (exchange_tasks, exchange_task, exchange):
                    _ensure_directory(directory, mode=0o1733)
                    os.chmod(directory, 0o1733, follow_symlinks=False)
                if stat.S_IMODE(exchange.stat().st_mode) != 0o1733:
                    raise BootstrapError(
                        "eval_exchange_invalid", "eval exchange mode mismatch"
                    )
                if not os.environ.get("AGENT_CANON_CONTAINER_ID"):
                    raise BootstrapError(
                        "container_control_missing_identity",
                        "resident container identity was not provided",
                    )
                image = state.get("resources", {}).get("image", {})
                collection["tool_image_digest"] = image.get("id")
                target_path = f"/targets/{target['digest']}"
                canon_root = TOOL_SOURCE_DESTINATION
                container_runtime = f"{CONTAINER_RUNTIME_DESTINATION}/exchange"
                exchange_runtime = (
                    f"{container_runtime}/tasks/{task_id}/{exchange_nonce}"
                )
                command = [
                    "python3",
                    f"{TOOL_SOURCE_DESTINATION}/eval/producers/run_accumulated_agent_evals.py",
                    "--root",
                    canon_root,
                    "--target-root",
                    target_path,
                    "--runtime-root",
                    exchange_runtime,
                    "--run-id",
                    run_id,
                    "--log-dir",
                    f"{exchange_runtime}/tasks/{run_id}/logs",
                ]
                result = _run_resident_command(
                    command,
                    cwd=canon_root,
                    environment={
                        "AGENT_CANON_TARGET_ROOT": target_path,
                        "AGENT_CANON_TASK_ROOT": target_path,
                        "GIT_CONFIG_COUNT": "1",
                        "GIT_CONFIG_KEY_0": "safe.directory",
                        "GIT_CONFIG_VALUE_0": target_path,
                    },
                    timeout=int(self.manifest["container"]["task_timeout_seconds"]),
                )
                io = _io_evidence(
                    task_path,
                    result.stdout or "",
                    result.stderr or "",
                    quota_bytes=int(self.manifest["container"]["task_log_quota_bytes"]),
                )
                matrix, metrics = _eval_producer_matrix(result.stdout or "")
                collection["producer_matrix"] = matrix
                collection["metrics"] = {
                    **metrics,
                    "runner_exit": result.returncode,
                    "stdout_bytes": io["stdout_bytes"],
                    "stderr_bytes": io["stderr_bytes"],
                }
                collection["family_status"] = {
                    item["name"]: item["status"] for item in matrix
                }
                if not matrix:
                    collection["status"] = "failed"
                    collection["failure"] = "eval_producer_protocol"
                elif result.returncode != 0 or any(
                    item["status"] != "pass" for item in matrix
                ):
                    collection["status"] = "failed"
                    collection["failure"] = "eval_producer_failed"
                else:
                    collection["status"] = "collected"
                # The container writes only into the mounted exchange. Move
                # that bundle to host spool before releasing task admission.
                eval_export = spool / "eval-results"
                log_export = spool / "producer-logs"
                eval_source = (
                    mounted_log_archive_root(self.repository_root, exchange_runtime)
                    / "eval-results"
                )
                _copy_resident_export(
                    source=str(eval_source),
                    destination=eval_export,
                    allowed_root=self.paths.spool,
                )
                _copy_resident_export(
                    source=f"{exchange_runtime}/tasks/{run_id}/logs",
                    destination=log_export,
                    allowed_root=self.paths.spool,
                )
                for producer in matrix:
                    for stream in ("stdout", "stderr"):
                        original = Path(str(producer[stream])).name
                        producer[stream] = (
                            f"eval-results/runs/{run_id}/producer-logs/{original}"
                        )
                collection["exported_files"] = {
                    "eval_results": _validate_exported_tree(eval_export),
                    "producer_logs": _validate_exported_tree(log_export),
                }
                exported_bytes = _dir_bytes(eval_export) + _dir_bytes(log_export)
                state_quota = int(self.manifest["container"]["task_state_quota_bytes"])
                if state_quota > 0 and exported_bytes > state_quota:
                    shutil.rmtree(eval_export, ignore_errors=True)
                    shutil.rmtree(log_export, ignore_errors=True)
                    collection["status"] = "failed"
                    collection["failure"] = "task_state_quota_exceeded"
                    raise BootstrapError(
                        "task_state_quota_exceeded",
                        f"eval export requires {exported_bytes} bytes; quota is {state_quota}",
                    )
                collection["metrics"]["exported_bytes"] = exported_bytes
                after_source = _source_snapshot(source)
                collection.update(
                    {
                        "source_head_after": after_source["head"],
                        "source_git_status_after": after_source["git_status"],
                        "source_tree_digest_after": after_source["tree_digest"],
                        "source_tree_unchanged": before_source == after_source,
                    }
                )
                if not collection["source_tree_unchanged"]:
                    collection["status"] = "failed"
                    collection["failure"] = "source_tree_changed"
                _atomic_json(spool / "collection.json", collection)
                state["tasks"][task_id]["eval"] = {
                    "run_id": run_id,
                    "collection": str(spool / "collection.json"),
                    "producer_matrix": matrix,
                    "io": io,
                }
                task_outcome = (
                    "completed" if collection["status"] == "collected" else "failed"
                )
                if task_outcome != "completed":
                    raise BootstrapError(
                        str(collection.get("failure", "eval_failed")),
                        "eval producer collection failed; spool retained",
                        evidence={
                            "spool": str(spool),
                            "collection": str(spool / "collection.json"),
                            "producer_matrix": matrix,
                            "source_tree_unchanged": collection[
                                "source_tree_unchanged"
                            ],
                            "exit": result.returncode,
                        },
                    )
                if exchange.exists() and not exchange.is_symlink():
                    shutil.rmtree(exchange)
                released = self._release_task_locked(
                    state, task_id, outcome=task_outcome
                )
                return self._result(
                    self._receipt(
                        "eval_collect",
                        "ok",
                        "eval_spooled",
                        before=before_state,
                        after=state.get("state"),
                        details={
                            "spool": str(spool),
                            "collection": collection,
                            "task": released,
                            "io": io,
                        },
                        state=state,
                    )
                )
            except BootstrapError:
                # Preserve partial exchange and host spool for diagnosis. A
                # source snapshot is still written when the runner returned.
                if not (spool / "collection.json").exists():
                    collection["status"] = "failed"
                    collection["failure"] = collection.get(
                        "failure", "eval_runtime_failed"
                    )
                    collection["source_tree_unchanged"] = False
                    _atomic_json(spool / "collection.json", collection)
                raise
            finally:
                if state.get("tasks", {}).get(task_id, {}).get("state") == "active":
                    self._release_task_locked(state, task_id, outcome=task_outcome)

    def eval_sync_prepare(self, run_id: str) -> dict[str, Any]:
        """Prepare a body-free eval publication request for the Host adapter.

        The resident validates the collection and records only fixed metadata.
        The credentialed archive clone, Git network, and publication transaction
        remain exclusively on the host side of the bootstrap boundary.
        """
        _slug(run_id)
        with self.locked():
            spool = self.paths.spool / run_id
            if not spool.is_dir() or spool.is_symlink():
                raise BootstrapError(
                    "eval_spool_missing", f"eval spool does not exist: {run_id}"
                )
            collection_path = spool / "collection.json"
            try:
                collection = json.loads(
                    _safe_read(collection_path, field="eval collection").decode("utf-8")
                )
            except (BootstrapError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BootstrapError(
                    "eval_collection_invalid", f"invalid eval collection: {run_id}"
                ) from exc
            if not isinstance(collection, dict) or collection.get("run_id") != run_id:
                raise BootstrapError(
                    "eval_collection_invalid", "eval collection run id mismatch"
                )
            if (
                collection.get("status") != "collected"
                or collection.get("source_tree_unchanged") is not True
            ):
                raise BootstrapError(
                    "eval_collection_failed",
                    "only a successful source-unchanged collection may be published",
                )
            state = self._read_state()
            if collection.get("manifest_digest") != state.get("manifest_digest"):
                raise BootstrapError(
                    "eval_collection_generation_mismatch",
                    "eval collection is not bound to the installed runtime generation",
                )
            source_root = collection.get("source_repository")
            target_digest = os.environ.get("AGENT_CANON_TARGET_DIGEST", "")
            if not isinstance(source_root, str) or not source_root.startswith("/"):
                raise BootstrapError(
                    "eval_collection_invalid", "eval source root is not absolute"
                )
            if any(character in source_root for character in "\x00\t\n\r"):
                raise BootstrapError(
                    "eval_collection_invalid",
                    "eval source root contains a control character",
                )
            if not target_digest and source_root.startswith("/targets/"):
                target_digest = source_root.removeprefix("/targets/")
            if target_digest and not re.fullmatch(
                r"[A-Za-z0-9_.-]{1,128}", target_digest
            ):
                raise BootstrapError(
                    "eval_collection_invalid", "eval target digest is invalid"
                )
            request_path = spool / "sync-request.tsv"
            if request_path.is_symlink():
                raise BootstrapError(
                    "eval_sync_request_invalid", "eval sync request is a symlink"
                )
            lines = [
                "schema\tagent-canon.eval-sync-request.v1",
                "operation\tsync",
                "execution-plane\tagentcanon_tool_container",
                f"run-id\t{run_id}",
                f"target-digest\t{target_digest}",
                f"source-root\t{source_root}",
            ]
            _atomic_bytes(
                request_path, ("\n".join(lines) + "\n").encode("utf-8"), mode=0o600
            )
            return self._result(
                self._receipt(
                    "eval_sync",
                    "ok",
                    "host_archive_requested",
                    before=None,
                    after=None,
                    details={
                        "execution_plane": "host_archive_adapter",
                        "status": "requested",
                        "run_id": run_id,
                    },
                    state=state,
                )
            )

    def gc(self, *, dry_run: bool = False) -> dict[str, Any]:
        """Plan or perform bounded LRU cleanup while preserving protected state."""
        with self.locked():
            state = self._read_state()
            current, rollback = (
                state.get("current_generation"),
                state.get("rollback_generation"),
            )
            quota = int(self.manifest["container"].get("runtime_quota_bytes", 0))
            high_water = bool(
                quota and _dir_bytes(self.paths.runtime_root) >= quota * 0.8
            )
            cache_quota = int(self.manifest["container"].get("cache_quota_bytes", 0))
            cache_bytes = _dir_bytes(self.paths.cache)
            cache_high_water = bool(cache_quota and cache_bytes >= cache_quota * 0.8)
            archive_quota = int(
                self.manifest["container"].get("archive_lease_quota_bytes", 0)
            )
            archive_bytes = _dir_bytes(self.paths.archive)
            archive_high_water = bool(
                archive_quota and archive_bytes >= archive_quota * 0.8
            )
            tasks = [
                (key, val)
                for key, val in state.get("tasks", {}).items()
                if val.get("state") in {"completed", "cancelled"}
                and not val.get("pinned")
            ]
            tasks.sort(key=lambda item: item[1].get("finished_at", ""))
            generations = [
                (key, val)
                for key, val in state.get("generations", {}).items()
                if key not in {current, rollback}
                and val.get("state") not in {"in-use", "pinned"}
            ]
            candidates = [f"task:{key}" for key, _ in tasks] + [
                f"generation:{key}" for key, _ in generations
            ]
            details = {
                "dry_run": dry_run,
                "high_water": high_water,
                "cache_high_water": cache_high_water,
                "archive_high_water": archive_high_water,
                "archive_cleanup_blocked_by_spool": False,
                "candidates": candidates,
                "preserved": {
                    "current_generation": current,
                    "rollback_generation": rollback,
                    "active_task_count": state.get("active_task_count", 0),
                    "unpublished_spool": True,
                },
                "deleted": [],
            }
            if not dry_run and (high_water or cache_high_water or archive_high_water):
                if cache_high_water and not state.get("active_task_count", 0):
                    cache_root = self.paths.cache
                    for child in (
                        sorted(cache_root.iterdir()) if cache_root.is_dir() else ()
                    ):
                        if child.is_symlink():
                            raise BootstrapError(
                                "symlink_path_rejected",
                                f"cache path is a symlink: {child}",
                            )
                        if child.is_dir():
                            shutil.rmtree(child)
                        elif child.is_file():
                            child.unlink()
                        details["deleted"].append(f"cache:{child.name}")
                if archive_high_water and not state.get("active_task_count", 0):
                    spool_root = self.paths.spool
                    spool_has_entries = bool(
                        spool_root.is_dir() and next(spool_root.iterdir(), None)
                    )
                    if spool_has_entries:
                        details["archive_cleanup_blocked_by_spool"] = True
                    else:
                        archive_root = self.paths.archive
                        for child in (
                            sorted(archive_root.iterdir())
                            if archive_root.is_dir()
                            else ()
                        ):
                            if child.is_symlink():
                                raise BootstrapError(
                                    "symlink_path_rejected",
                                    f"archive path is a symlink: {child}",
                                )
                            if child.is_dir():
                                shutil.rmtree(child)
                            elif child.is_file():
                                child.unlink()
                            details["deleted"].append(f"archive:{child.name}")
                if high_water:
                    for key, _ in tasks:
                        path = self.paths.tasks / key
                        if path.is_symlink():
                            raise BootstrapError(
                                "symlink_path_rejected",
                                f"task path is a symlink: {path}",
                            )
                        if path.is_dir():
                            shutil.rmtree(path)
                        state["tasks"].pop(key, None)
                        details["deleted"].append(f"task:{key}")
                    for key, _ in generations:
                        path = self.paths.generations / key
                        if path.is_symlink():
                            raise BootstrapError(
                                "symlink_path_rejected",
                                f"generation path is a symlink: {path}",
                            )
                        if path.is_dir():
                            shutil.rmtree(path)
                        state["generations"].pop(key, None)
                        details["deleted"].append(f"generation:{key}")
                self._write_state(state)
            return self._result(
                self._receipt(
                    "gc",
                    "ok",
                    "gc_plan" if dry_run else "gc_complete",
                    before=state["state"],
                    after=state["state"],
                    details=details,
                    state=state,
                )
            )

def _runtime_from_args(args: argparse.Namespace) -> BootstrapRuntime:
    repository_root = Path(args.repository_root).resolve()
    requested_runtime = getattr(args, "runtime_root", None)
    runtime_root = (
        Path(requested_runtime).resolve()
        if requested_runtime
        else repository_root / ".runtime"
    )
    return BootstrapRuntime(
        Path(args.control_parent_root),
        runtime_root,
        repository_root=repository_root,
        manifest_path=Path(args.manifest) if args.manifest else None,
    )


def _container_resource_state(runtime: BootstrapRuntime) -> dict[str, Any]:
    """Build lifecycle resources from host readback passed at exec time."""
    resources = runtime._resource_records()
    image = resources["image"]
    container = resources["container"]
    image_id = os.environ.get("AGENT_CANON_IMAGE_ID")
    container_id = os.environ.get("AGENT_CANON_CONTAINER_ID")
    if image_id:
        image.update({"id": image_id, "state": "present", "owned": True})
    if container_id:
        container.update({"id": container_id, "state": "running", "owned": True})
    return resources


def _container_target_generation(
    state: dict[str, Any], targets: Mapping[str, Any]
) -> None:
    """Record a target change through the normal current/rollback snapshot owner."""
    image = state.get("resources", {}).get("image", {})
    image_snapshot = {
        "image_id": image.get("id"),
        "image_ref": image.get("tag"),
    }
    old_generation = state.get("current_generation")
    state["generation_counter"] = int(state.get("generation_counter", 0)) + 1
    generation = f"generation-{state['generation_counter']}"
    if old_generation:
        previous_targets = json.loads(_json(state.get("targets", {})))
        state.setdefault("generations", {})[str(old_generation)] = {
            **image_snapshot,
            "targets": previous_targets,
            "state": "rollback",
        }
    new_targets = json.loads(_json(dict(targets)))
    state.setdefault("generations", {})[generation] = {
        **image_snapshot,
        "targets": new_targets,
        "state": "current",
    }
    state["targets"] = new_targets
    state["current_generation"] = generation
    state["rollback_generation"] = old_generation


def _container_materialize_rollback_plan(
    runtime: BootstrapRuntime, state: Mapping[str, Any]
) -> None:
    """Materialize the one strict rollback plan from the active snapshots.

    This is state-only: Docker tags and host mount creation remain owned by
    the shell adapter.  The target source paths are carried as opaque host
    metadata and are revalidated by the host when the plan is consumed.
    """
    plan = runtime.paths.container_runtime / "rollback-plan.tsv"
    rollback_id = state.get("rollback_generation")
    generations = state.get("generations", {})
    if not isinstance(rollback_id, str) or not isinstance(generations, Mapping):
        if plan.exists() or plan.is_symlink():
            if plan.is_symlink():
                raise BootstrapError(
                    "rollback_plan_invalid", "rollback plan is a symlink"
                )
            plan.unlink()
        return
    previous = generations.get(rollback_id)
    resources = state.get("resources", {})
    image = resources.get("image", {}) if isinstance(resources, Mapping) else {}
    if not isinstance(previous, Mapping):
        raise BootstrapError(
            "rollback_plan_invalid", "rollback generation is unavailable"
        )
    image_id = previous.get("image_id") or image.get("id")
    image_ref = previous.get("image_ref") or image.get("tag") or image_id
    if (
        not isinstance(image_id, str)
        or not image_id.startswith("sha256:")
        or not isinstance(image_ref, str)
        or not image_ref
        or any(character in image_ref for character in "\x00\t\n\r")
    ):
        raise BootstrapError(
            "rollback_plan_invalid", "rollback image identity is incomplete"
        )
    targets = previous.get("targets", state.get("targets", {}))
    if not isinstance(targets, Mapping):
        raise BootstrapError(
            "rollback_plan_invalid", "rollback target snapshot is invalid"
        )
    lines = [
        "schema\tagent-canon.rollback-plan.v1",
        f"image-id\t{image_id}",
        f"image-ref\t{image_ref}",
    ]
    for digest, record in sorted(targets.items()):
        if not isinstance(digest, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,128}", digest
        ):
            raise BootstrapError(
                "rollback_plan_invalid", "rollback target digest is invalid"
            )
        if not isinstance(record, Mapping):
            raise BootstrapError(
                "rollback_plan_invalid", "rollback target record is invalid"
            )
        source = record.get("host_root")
        destination = record.get("root", f"/targets/{digest}")
        mode = record.get("mode")
        if (
            not isinstance(source, str)
            or not source.startswith("/")
            or any(character in source for character in "\x00\t\n\r")
            or destination != f"/targets/{digest}"
            or mode != "read-only"
        ):
            raise BootstrapError(
                "rollback_plan_invalid", "rollback target mount is invalid"
            )
        lines.append(f"mount\tmount\t{source}\t{destination}\ttrue")
    _atomic_bytes(
        plan,
        ("\n".join(lines) + "\n").encode("utf-8"),
        mode=0o444,
    )


def _container_target_manifest(
    runtime: BootstrapRuntime,
    path: Path,
    *,
    missing_code: str,
    invalid_code: str,
) -> dict[str, Any]:
    """Read one host-provided target set without touching Docker.

    The rollback manifest is a deliberately small TSV exchange.  The resident
    cannot see host source paths, so it validates only the fixed schema and
    carries those paths forward as opaque mount-source metadata; the host
    adapter performs source existence/scope checks before creating a container.
    """
    if path.is_symlink() or not path.is_file():
        raise BootstrapError(
            missing_code,
            "host did not provide the requested target mount manifest",
        )
    targets: dict[str, Any] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise BootstrapError(
            invalid_code,
            "target mount manifest is unreadable",
        ) from exc
    for line_number, line in enumerate(lines, start=1):
        fields = line.split("\t")
        if len(fields) != 5:
            raise BootstrapError(
                invalid_code,
                f"previous target mount row {line_number} is not TSV",
            )
        kind, digest, source, destination, mode = fields
        if (
            kind != "target"
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", digest)
            or not source.startswith("/")
            or any(character in source for character in "\x00\n\r")
            or destination != f"/targets/{digest}"
            or mode != "read-only"
            or digest in targets
        ):
            raise BootstrapError(
                invalid_code,
                f"previous target mount row {line_number} is invalid",
            )
        targets[digest] = {
            "digest": digest,
            "host_root": source,
            "root": destination,
            "mode": mode,
        }
    return targets


def _container_previous_target_manifest(runtime: BootstrapRuntime) -> dict[str, Any]:
    """Read the host-provided previous target set without touching Docker."""
    supplied = os.environ.get("AGENT_CANON_ROLLBACK_MOUNTS_FILE", "").strip()
    if supplied:
        if not Path(supplied).exists() and not Path(supplied).is_symlink():
            return {}
        return _container_target_manifest(
            runtime,
            Path(supplied),
            missing_code="rollback_target_manifest_missing",
            invalid_code="rollback_target_manifest_invalid",
        )
    return _container_target_manifest(
        runtime,
        runtime.paths.runtime_root / "rollback-mounts.tsv",
        missing_code="rollback_target_manifest_missing",
        invalid_code="rollback_target_manifest_invalid",
    )


def _container_restore_target_manifest(
    runtime: BootstrapRuntime,
) -> dict[str, Any] | None:
    """Read an optional target set used only when a rollback must recover."""
    raw_path = os.environ.get("AGENT_CANON_RESTORE_TARGETS_FILE", "")
    if not raw_path:
        return None
    return _container_target_manifest(
        runtime,
        Path(raw_path),
        missing_code="restore_target_manifest_missing",
        invalid_code="restore_target_manifest_invalid",
    )


def _container_source_identity(
    remote: str, repository_id: str = "", *, mode: str = "source"
) -> dict[str, str]:
    """Return a canonical source or generic remote identity without I/O."""
    from tools.runtime.archive.log_repository_identity import (
        normalize_remote,
        stable_source_repository_id,
    )

    try:
        normalized = normalize_remote(remote)
    except ValueError as exc:
        raise BootstrapError(
            "source_repository_identity_unavailable",
            str(exc),
        ) from exc
    if mode == "remote":
        if repository_id:
            raise BootstrapError(
                "source_repository_id_invalid",
                "generic remote identity does not accept a source override",
            )
        return {
            "schema": "agent-canon.remote-identity.v1",
            "normalized_remote": normalized,
        }
    if mode != "source":
        raise BootstrapError(
            "source_repository_identity_unavailable",
            "identity mode is invalid",
        )
    try:
        derived = stable_source_repository_id(remote)
    except ValueError as exc:
        raise BootstrapError(
            "source_repository_identity_unavailable",
            str(exc),
        ) from exc
    if repository_id:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,95}", repository_id):
            raise BootstrapError(
                "source_repository_id_invalid",
                "source repository identity override is invalid",
            )
        if repository_id != derived:
            raise BootstrapError(
                "source_repository_id_mismatch",
                "source repository identity override does not match its remote",
            )
        derived = repository_id
    return {
        "schema": "agent-canon.source-identity.v1",
        "normalized_remote": normalized,
        "repository_id": derived,
        "stable_branch": f"logs/{derived}",
    }


def _request_string(request: Mapping[str, Any], key: str) -> str:
    """Read one non-empty request string without accepting control bytes."""
    value = request.get(key)
    if (
        not isinstance(value, str)
        or not value
        or any(char in value for char in "\x00\n\r")
    ):
        raise BootstrapError("invalid_exec_request", f"request field is invalid: {key}")
    return value


def _container_target_for_request(
    runtime: BootstrapRuntime, request: Mapping[str, Any]
) -> tuple[Path, Path, Path, Path]:
    """Resolve a host request to its registered container target and roots."""
    requested_target = Path(_request_string(request, "target_root")).resolve(
        strict=False
    )
    source_root = Path(_request_string(request, "source_root")).resolve(strict=False)
    environment = request.get("environment")
    if not isinstance(environment, Mapping):
        raise BootstrapError(
            "invalid_exec_request", "request environment must be a mapping"
        )
    host_runtime = Path(
        _request_string(environment, "AGENT_CANON_RUNTIME_ROOT")
    ).resolve(strict=False)
    host_control = Path(
        _request_string(environment, "AGENT_CANON_CONTROL_PARENT_ROOT")
    ).resolve(strict=False)
    digest = os.environ.get("AGENT_CANON_TARGET_DIGEST", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", digest):
        raise BootstrapError(
            "invalid_exec_request", "registered target digest is missing"
        )
    state = runtime._read_state()
    targets = state.get("targets", {})
    target = targets.get(digest) if isinstance(targets, Mapping) else None
    if not isinstance(target, dict):
        raise BootstrapError(
            "target_not_registered", "request target is not registered"
        )
    host_root_value = target.get("host_root")
    container_root = target.get("root")
    if (
        not isinstance(host_root_value, str)
        or not host_root_value
        or not isinstance(container_root, str)
        or container_root != f"/targets/{digest}"
        or requested_target != Path(host_root_value).resolve(strict=False)
    ):
        raise BootstrapError(
            "invalid_exec_request", "request target does not match its registered mount"
        )
    return source_root, host_runtime, host_control, Path(container_root)


def _map_request_path(
    value: str,
    *,
    source_root: Path,
    host_runtime: Path,
    host_control: Path,
    host_target: Path,
    container_target: Path,
) -> str:
    """Map a validated host path into one of the fixed container mounts."""
    candidate = Path(value)
    if not candidate.is_absolute():
        raise BootstrapError(
            "invalid_exec_request", "path-valued environment must be absolute"
        )
    resolved = candidate.resolve(strict=False)
    if resolved == source_root:
        return TOOL_SOURCE_DESTINATION
    if resolved == host_target or host_target in resolved.parents:
        relative = resolved.relative_to(host_target)
        return (container_target / relative).as_posix()
    if resolved == host_runtime or host_runtime in resolved.parents:
        relative = resolved.relative_to(host_runtime)
        return (Path(CONTAINER_RUNTIME_DESTINATION) / relative).as_posix()
    if resolved == host_control:
        return "/var/lib/agent-canon"
    raise BootstrapError(
        "invalid_exec_request",
        f"path-valued environment escapes registered mounts: {value}",
    )


def _container_request_environment(
    request: Mapping[str, Any],
    *,
    container_target: Path,
    source_root: Path,
    host_runtime: Path,
    host_control: Path,
    host_private_log: Path | None,
) -> dict[str, str]:
    """Validate and map the structured tool environment for Docker exec."""
    raw = request.get("environment")
    if not isinstance(raw, Mapping) or not all(isinstance(key, str) for key in raw):
        raise BootstrapError(
            "invalid_exec_request", "request environment must be a string-keyed mapping"
        )
    host_target_value = _request_string(request, "target_root")
    host_target = Path(host_target_value).resolve(strict=False)
    result: dict[str, str] = {}
    for key, value in raw.items():
        if (
            key not in TOOL_ENVIRONMENT_KEYS
            or not isinstance(value, str)
            or any(char in value for char in "\x00\n\r")
        ):
            raise BootstrapError(
                "invalid_exec_request",
                f"request environment key is not allowlisted: {key}",
            )
        if key in TOOL_PATH_ENVIRONMENT_KEYS:
            if (
                key in {"AGENT_CANON_SOURCE_ROOT", "AGENT_CANON_ROOT"}
                and Path(value).resolve(strict=False) != source_root
            ):
                raise BootstrapError(
                    "invalid_exec_request", f"source path does not match request: {key}"
                )
            if (
                key == "AGENT_CANON_RUNTIME_ROOT"
                and Path(value).resolve(strict=False) != host_runtime
            ):
                raise BootstrapError(
                    "invalid_exec_request", "runtime path does not match request"
                )
            if (
                key == "AGENT_CANON_CONTROL_PARENT_ROOT"
                and Path(value).resolve(strict=False) != host_control
            ):
                raise BootstrapError(
                    "invalid_exec_request", "control path does not match request"
                )
            if (
                key in {"AGENT_CANON_TARGET_ROOT", "AGENT_CANON_TASK_ROOT"}
                and Path(value).resolve(strict=False) != host_target
            ):
                raise BootstrapError(
                    "invalid_exec_request", f"target path does not match request: {key}"
                )
            if key == "AGENT_CANON_MOUNT_REGISTRY":
                result[key] = REGISTRY_DESTINATION
                continue
            if key in {"AGENT_CANON_HOOK_ARCHIVE_DIR", "AGENT_CANON_LOG_ROOT"}:
                if (
                    host_private_log is None
                    or Path(value).resolve(strict=False) != host_private_log
                ):
                    raise BootstrapError(
                        "invalid_exec_request",
                        f"archive path does not match private log mount: {key}",
                    )
                result[key] = PRIVATE_LOG_DESTINATION
                continue
            result[key] = _map_request_path(
                value,
                source_root=source_root,
                host_runtime=host_runtime,
                host_control=host_control,
                host_target=host_target,
                container_target=container_target,
            )
        else:
            result[key] = value
    output = request.get("output_root")
    output_env = raw.get("AGENT_CANON_OUTPUT_ROOT")
    if output is None:
        if output_env is not None:
            raise BootstrapError(
                "invalid_exec_request",
                "output environment is present without output_root",
            )
    elif not isinstance(output, str) or not output:
        raise BootstrapError("invalid_exec_request", "request output_root is invalid")
    elif output_env != output:
        raise BootstrapError(
            "invalid_exec_request", "output_root and output environment differ"
        )
    return result


def _container_control_run(args: argparse.Namespace) -> dict[str, Any]:
    """Apply only state/tool-plane operations after host Docker activation."""
    operation = args.operation
    if operation == "source-identity":
        return _container_source_identity(
            args.remote,
            args.repository_id,
            mode=args.mode,
        )
    runtime = _runtime_from_args(args)
    if operation in {"install", "update", "start", "stop", "uninstall"}:
        with runtime.locked():
            state = runtime._read_state()
            if operation in {"install", "update"}:
                runtime._prune_stale_targets(state)
            before = str(state.get("state"))
            resources = state.setdefault("resources", {})
            resources.update(_container_resource_state(runtime))
            if operation == "install":
                # A clean install reconstructs controller-owned lifecycle
                # state, while host-consumed spool/archive/cache/Codex
                # surfaces remain on their explicitly mounted host roots.
                for directory in (runtime.paths.generations, runtime.paths.tasks):
                    if directory.is_symlink():
                        raise BootstrapError(
                            "symlink_path_rejected",
                            f"controller state directory is a symlink: {directory}",
                        )
                    if directory.is_dir():
                        for child in directory.iterdir():
                            if child.is_symlink() or child.is_file():
                                child.unlink()
                            elif child.is_dir():
                                shutil.rmtree(child)
                state.update(
                    {
                        "targets": {},
                        "generations": {},
                        "current_generation": None,
                        "rollback_generation": None,
                        "generation_counter": 0,
                        "active_task_count": 0,
                        "tasks": {},
                    }
                )
                state["state"] = "ready"
                state["managed_paths"] = [
                    STATE_FILE,
                    OWNER_FILE,
                    "mounts.toml",
                    "mounts.tsv",
                    *KNOWN_SUBDIRS,
                    CONTAINER_RUNTIME_DIR,
                ]
            elif operation == "update":
                state["state"] = "ready"
                previous_image_id = os.environ.get("AGENT_CANON_PREVIOUS_IMAGE_ID")
                if previous_image_id:
                    state["previous_image_id"] = previous_image_id
                    previous_generation = str(
                        state.get("current_generation")
                        or f"generation-{previous_image_id[7:19]}"
                    )
                    current_generation = f"generation-{resources['image']['id'][7:19]}"
                    state.setdefault("generations", {})[previous_generation] = {
                        "image_id": previous_image_id,
                        "image_ref": os.environ.get("AGENT_CANON_PREVIOUS_IMAGE_REF"),
                        "targets": json.loads(_json(state.get("targets", {}))),
                        "state": "rollback",
                    }
                    state.setdefault("generations", {})[current_generation] = {
                        "image_id": resources["image"]["id"],
                        "image_ref": resources["image"].get("tag"),
                        "state": "current",
                    }
                    state["rollback_generation"] = previous_generation
                    state["current_generation"] = current_generation
                if previous_image_id:
                    state.update(active_task_count=0, tasks={})
                state["manifest_digest"] = runtime.manifest_digest
            elif operation == "start":
                state["state"] = "ready"
            elif operation == "stop":
                state["state"] = "stopped"
                resources["container"].update({"id": None, "state": "absent"})
            else:
                state["state"] = "uninstalled"
                for resource in resources.values():
                    resource["id"] = None
                    resource["state"] = "absent"
            runtime._write_mounts(state)
            runtime._write_mount_manifest(state)
            runtime._write_state(state)
            if operation in {"install", "update"}:
                _container_materialize_rollback_plan(runtime, state)
            result = runtime._result(
                runtime._receipt(
                    operation,
                    "ok",
                    {
                        "install": "installed",
                        "update": "updated",
                        "start": "ready",
                        "stop": "stopped",
                        "uninstall": "owned_resources_released",
                    }[operation],
                    before=before,
                    after=state["state"],
                    state=state,
                )
            )
        if operation == "install":
            runtime.codex_prepare()
        return result
    if operation == "rollback":
        with runtime.locked():
            state = runtime._read_state()
            before = str(state.get("state"))
            resources = state.setdefault(
                "resources", _container_resource_state(runtime)
            )
            image = resources.setdefault("image", {})
            restored_image_id = os.environ.get("AGENT_CANON_RESTORE_IMAGE_ID")
            current_image_id = os.environ.get(
                "AGENT_CANON_CURRENT_IMAGE_ID"
            ) or image.get("id")
            if not restored_image_id:
                raise BootstrapError(
                    "rollback_image_missing", "host did not provide a rollback image ID"
                )
            previous_targets = _container_previous_target_manifest(runtime)
            current_targets = json.loads(_json(state.get("targets", {})))
            candidate_image_id = str(image.get("id") or restored_image_id)
            image.update(
                {
                    "id": restored_image_id,
                    "tag": os.environ.get(
                        "AGENT_CANON_RESTORE_IMAGE_REF", restored_image_id
                    ),
                    "owned": True,
                    "state": "present",
                }
            )
            previous_generation = str(
                state.get("rollback_generation")
                or f"generation-{restored_image_id[7:19]}"
            )
            rollback_generation = str(
                state.get("current_generation")
                or f"generation-{str(current_image_id)[7:19]}"
            )
            if previous_generation == rollback_generation:
                raise BootstrapError(
                    "rollback_generation_invalid",
                    "current and rollback generations are not distinct",
                )
            generations = state.setdefault("generations", {})
            generations[previous_generation] = {
                "image_id": restored_image_id,
                "image_ref": os.environ.get(
                    "AGENT_CANON_RESTORE_IMAGE_REF", restored_image_id
                ),
                "targets": previous_targets,
                "state": "current",
            }
            generations[rollback_generation] = {
                "image_id": current_image_id,
                "image_ref": os.environ.get(
                    "AGENT_CANON_CURRENT_IMAGE_REF", current_image_id
                ),
                "targets": current_targets,
                "state": "rollback",
            }
            state["targets"] = previous_targets
            state["rollback_generation"] = rollback_generation
            state["current_generation"] = previous_generation
            state["previous_image_id"] = None
            state["state"] = "ready"
            runtime._write_mounts(state)
            runtime._write_mount_manifest(state)
            runtime._write_state(state)
            _container_materialize_rollback_plan(runtime, state)
            return runtime._result(
                runtime._receipt(
                    "rollback",
                    "ok",
                    "previous_generation_restored",
                    before=before,
                    after=state["state"],
                    state=state,
                )
            )
    if operation == "restore":
        with runtime.locked():
            state = runtime._read_state()
            before = str(state.get("state"))
            resources = state.setdefault(
                "resources", _container_resource_state(runtime)
            )
            image = resources.setdefault("image", {})
            restored_image_id = os.environ.get("AGENT_CANON_RESTORE_IMAGE_ID")
            if not restored_image_id:
                raise BootstrapError(
                    "restore_image_missing",
                    "host did not provide the previous image ID",
                )
            candidate_image_id = str(image.get("id") or restored_image_id)
            candidate_targets = json.loads(_json(state.get("targets", {})))
            restored_targets = _container_restore_target_manifest(runtime)
            if restored_targets is not None:
                state["targets"] = restored_targets
            image.update(
                {
                    "id": restored_image_id,
                    "tag": restored_image_id,
                    "owned": True,
                    "state": "present",
                }
            )
            restored_generation = f"generation-{restored_image_id[7:19]}"
            candidate_generation = f"generation-{candidate_image_id[7:19]}"
            generations = state.setdefault("generations", {})
            generations[restored_generation] = {
                "image_id": restored_image_id,
                "targets": json.loads(_json(state.get("targets", {}))),
                "state": "current",
            }
            if candidate_generation != restored_generation:
                generations[candidate_generation] = {
                    "image_id": candidate_image_id,
                    "targets": candidate_targets,
                    "state": "rollback",
                }
                state["rollback_generation"] = candidate_generation
            state["current_generation"] = restored_generation
            state["previous_image_id"] = None
            state["state"] = "ready"
            runtime._write_mounts(state)
            runtime._write_mount_manifest(state)
            runtime._write_state(state)
            _container_materialize_rollback_plan(runtime, state)
            return runtime._result(
                runtime._receipt(
                    "restore",
                    "ok",
                    "previous_generation_restored",
                    before=before,
                    after=state["state"],
                    state=state,
                )
            )
    if operation == "status":
        with runtime.locked():
            state = runtime._read_state()
            return runtime._result(
                runtime._receipt(
                    "status",
                    "ok",
                    "status",
                    before=state["state"],
                    after=state["state"],
                    details={"state": runtime._state_summary(state)},
                    state=state,
                )
            )
    if operation == "codex":
        if args.codex_operation == "prepare":
            return runtime.codex_prepare()
        if args.codex_operation == "launch":
            return runtime.codex_launch(Path(args.project_root))
        raise BootstrapError(
            "container_control_unsupported",
            "unsupported Codex operation in resident controller",
        )
    if operation == "target" and args.target_operation == "add":
        with runtime.locked():
            state = runtime._read_state()
            stale = runtime._prune_stale_targets(state)
            host_root = os.environ.get("AGENT_CANON_TARGET_HOST_ROOT")
            container_root = os.environ.get("AGENT_CANON_TARGET_CONTAINER_ROOT")
            host_digest = os.environ.get("AGENT_CANON_TARGET_DIGEST")
            target = runtime._target_record(
                Path(container_root or args.root),
                args.mode,
                host_root=host_root,
                host_digest=host_digest,
            )
            targets = dict(state.get("targets", {}))
            existing_target = targets.get(target["digest"])
            if (
                not stale
                and isinstance(existing_target, Mapping)
                and runtime._same_target_record(existing_target, target)
            ):
                runtime._write_mounts(state)
                runtime._write_mount_manifest(state)
                runtime._write_state(state)
                return runtime._result(
                    runtime._receipt(
                        "target_add",
                        "ok",
                        "target_unchanged",
                        before=str(state.get("state")),
                        after=str(state.get("state")),
                        details={"target": dict(existing_target), "changed": False},
                        state=state,
                    )
                )
            targets[target["digest"]] = target
            _container_target_generation(state, targets)
            state["state"] = "ready"
            runtime._write_mounts(state)
            runtime._write_mount_manifest(state)
            runtime._write_state(state)
            _container_materialize_rollback_plan(runtime, state)
            return runtime._result(
                runtime._receipt(
                    "target_add",
                    "ok",
                    "target_registered",
                    before="ready",
                    after="ready",
                    details={"target": target},
                    state=state,
                )
            )
    if operation == "target" and args.target_operation == "remove":
        with runtime.locked():
            state = runtime._read_state()
            host_root = os.environ.get("AGENT_CANON_TARGET_HOST_ROOT")
            container_root = os.environ.get("AGENT_CANON_TARGET_CONTAINER_ROOT")
            host_digest = os.environ.get("AGENT_CANON_TARGET_DIGEST")
            targets = dict(state.get("targets", {}))
            # An unregistered host digest has no required mount to validate.
            if host_digest and host_digest not in targets:
                raise BootstrapError(
                    "target_not_registered", "target root is not registered"
                )
            target = runtime._target_record(
                Path(container_root or args.root),
                args.mode,
                host_root=host_root,
                host_digest=host_digest,
            )
            target_digest = host_digest or target["digest"]
            if target_digest not in targets:
                raise BootstrapError(
                    "target_not_registered", "target root is not registered"
                )
            del targets[target_digest]
            _container_target_generation(state, targets)
            runtime._write_mounts(state)
            runtime._write_mount_manifest(state)
            runtime._write_state(state)
            _container_materialize_rollback_plan(runtime, state)
            return runtime._result(
                runtime._receipt(
                    "target_remove",
                    "ok",
                    "target_removed",
                    before="ready",
                    after="ready",
                    details={"target_digest": target_digest},
                    state=state,
                )
            )
    if operation == "exec":
        command = list(args.command)
        command = command[1:] if command and command[0] == "--" else command
        if args.request_json:
            try:
                request = json.loads(args.request_json)
            except json.JSONDecodeError as exc:
                raise BootstrapError(
                    "invalid_exec_request", "request is not JSON"
                ) from exc
            allowed = {
                "schema",
                "tool_id",
                "argv",
                "child_args",
                "source_root",
                "cwd",
                "cwd_policy",
                "target_root",
                "environment",
                "stdin",
                "stdout",
                "stderr",
                "exit",
                "signal",
                "side_effect",
                "output_root",
                "written_paths",
            }
            if not isinstance(request, dict) or set(request) - allowed:
                raise BootstrapError(
                    "invalid_exec_request", "request fields are invalid"
                )
            if request.get("schema") != "agent-canon.tool-exec-request.v1":
                raise BootstrapError(
                    "invalid_exec_request", "request schema is invalid"
                )
            tool_id = request.get("tool_id")
            child_args = request.get("child_args")
            descriptor_argv = request.get("argv")
            if (
                not isinstance(tool_id, str)
                or not SAFE_ID.fullmatch(tool_id)
                or not isinstance(child_args, list)
                or any(
                    not isinstance(item, str) or "\x00" in item for item in child_args
                )
                or not isinstance(descriptor_argv, list)
                or any(
                    not isinstance(item, str) or "\x00" in item
                    for item in descriptor_argv
                )
            ):
                raise BootstrapError("invalid_exec_request", "tool or argv is invalid")
            if not isinstance(
                args.target_digest, str
            ) or args.target_digest != os.environ.get("AGENT_CANON_TARGET_DIGEST"):
                raise BootstrapError(
                    "invalid_exec_request", "target digest handoff is invalid"
                )
            source_root, host_runtime, host_control, container_target = (
                _container_target_for_request(runtime, request)
            )
            environment = _container_request_environment(
                request,
                container_target=container_target,
                source_root=source_root,
                host_runtime=host_runtime,
                host_control=host_control,
                host_private_log=(
                    Path(os.environ["AGENT_CANON_PRIVATE_LOG_ROOT"]).resolve(
                        strict=False
                    )
                    if os.environ.get("AGENT_CANON_PRIVATE_LOG_ROOT", "").strip()
                    else None
                ),
            )
            return runtime.tool_run(
                tool_id,
                child_args,
                root=container_target,
                environment=environment,
            )
        return runtime.exec(Path(args.root), command)
    if operation == "tool" and args.tool_operation == "run":
        command = list(args.command)
        command = command[1:] if command and command[0] == "--" else command
        return runtime.tool_run(
            args.catalog_id,
            command,
            root=Path(args.root) if args.root else None,
        )
    if operation == "template" and args.template_operation == "export":
        return runtime.template_export(Path(args.root), args.profile, args.output)
    if operation == "eval" and args.eval_operation == "collect":
        return runtime.eval_collect(Path(args.root), args.run_id)
    if operation == "eval" and args.eval_operation == "sync":
        return runtime.eval_sync_prepare(args.run_id)
    if operation == "task" and args.task_operation == "admit":
        return runtime.admit_task(
            args.task_id, target_root=Path(args.root) if args.root else None
        )
    if operation == "task" and args.task_operation == "release":
        return runtime.release_task(args.task_id, outcome=args.outcome)
    if operation == "gc":
        return runtime.gc(dry_run=args.dry_run)
    raise BootstrapError(
        "container_control_unsupported",
        f"{operation} requires host-owned Docker or a project execution plane",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the typed bootstrap command parser."""
    parser = argparse.ArgumentParser(description="AgentCanon shared runtime bootstrap")
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--control-parent-root", required=True)
    parser.add_argument(
        "--runtime-root",
        help="persistent runtime directory (default: <repository-root>/.runtime)",
    )
    parser.add_argument("--manifest")
    sub = parser.add_subparsers(dest="operation", required=True)
    for operation in ("start", "status", "stop", "rollback", "uninstall", "restore"):
        sub.add_parser(operation)
    install_parser = sub.add_parser("install")
    install_parser.add_argument("--image-ref")
    update_parser = sub.add_parser("update")
    update_parser.add_argument("--image-ref")
    source_identity = sub.add_parser(
        "source-identity",
        help=argparse.SUPPRESS,
    )
    source_identity.add_argument("--remote", required=True)
    source_identity.add_argument("--repository-id", default="")
    source_identity.add_argument(
        "--mode",
        choices=("source", "remote"),
        default="source",
        help=argparse.SUPPRESS,
    )
    gc_parser = sub.add_parser("gc")
    gc_parser.add_argument("--dry-run", action="store_true")
    target = sub.add_parser("target")
    target_sub = target.add_subparsers(dest="target_operation", required=True)
    add = target_sub.add_parser("add")
    add.add_argument("--root", required=True)
    add.add_argument("--mode", choices=("read-only",), default="read-only")
    remove = target_sub.add_parser("remove")
    remove.add_argument("--root", required=True)
    remove.add_argument("--mode", choices=("read-only",), default="read-only")
    execute = sub.add_parser("exec")
    execute_group = execute.add_mutually_exclusive_group(required=True)
    execute_group.add_argument("--root")
    execute_group.add_argument("--request-json")
    execute.add_argument("--target-digest")
    execute.add_argument("command", nargs=argparse.REMAINDER)
    tool = sub.add_parser("tool")
    tool_sub = tool.add_subparsers(dest="tool_operation", required=True)
    tool_run = tool_sub.add_parser("run")
    tool_run.add_argument("--root")
    tool_run.add_argument("catalog_id")
    tool_run.add_argument("command", nargs=argparse.REMAINDER)
    template = sub.add_parser("template")
    template_sub = template.add_subparsers(dest="template_operation", required=True)
    template_export = template_sub.add_parser("export")
    template_export.add_argument("--root", required=True)
    template_export.add_argument("--profile", required=True)
    template_export.add_argument("--output", required=True)
    codex = sub.add_parser("codex")
    codex_sub = codex.add_subparsers(dest="codex_operation")
    codex_sub.add_parser("prepare")
    launch = codex_sub.add_parser("launch")
    launch.add_argument("--project-root", required=True)
    codex.add_argument("--project-root", dest="project_root_shorthand")
    evaluation = sub.add_parser("eval")
    eval_sub = evaluation.add_subparsers(dest="eval_operation", required=True)
    collect = eval_sub.add_parser("collect")
    collect.add_argument("--root", required=True)
    collect.add_argument("--run-id", required=True)
    sync = eval_sub.add_parser("sync")
    sync.add_argument("--run-id", required=True)
    task = sub.add_parser("task")
    task_sub = task.add_subparsers(dest="task_operation", required=True)
    admit = task_sub.add_parser("admit")
    admit.add_argument("--task-id", required=True)
    admit.add_argument("--root")
    release = task_sub.add_parser("release")
    release.add_argument("--task-id", required=True)
    release.add_argument("--outcome", default="completed")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Apply controller operations after the host-owned Docker transaction."""
    return _container_control_run(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the bootstrap CLI and emit a typed JSON receipt or error."""
    try:
        result = run(build_parser().parse_args(argv))
    except BootstrapError as exc:
        print(
            _json(
                {
                    "schema": SCHEMA_RECEIPT,
                    "status": "error",
                    "code": exc.code,
                    "detail": exc.detail,
                    "evidence": exc.evidence,
                }
            ),
            file=sys.stderr,
        )
        if exc.code == "tool_failed":
            exit_code = exc.evidence.get("exit")
            if isinstance(exit_code, int) and 1 <= exit_code <= 125:
                return exit_code
        return 2
    print(_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
