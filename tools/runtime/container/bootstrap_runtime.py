#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Owns container-side TOML/JSON/state/tool/check/eval logic for the shared AgentCanon tool container without implicit source writes.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared runtime design
# downstream implementation ../../bootstrap.sh fixed host entrypoint
# downstream implementation ../../tests/bootstrap/test_bootstrap_runtime.py lifecycle validation
# @dependency-end
"""Container control plane for the AgentCanon tool runtime.

The host-side DockerAdapter is the only owner of Docker and accepts argv arrays only.
BootstrapRuntime owns durable state and performs state/path readback under an
external lifecycle lock. The resident container never instantiates the host
Docker lifecycle path; its control mode owns only state/tool/check/eval work.
Build results are Docker results; immutable container ownership and security
invariants are checked once after create/adopt, while health polling reads
only the mutable Running/Health fields.
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

import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

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
TOOL_SOURCE_DESTINATION = "/usr/local/share/agent-canon/runtime"
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
# This is the only historical source of runtime state that the bootstrap may
# migrate.  It is intentionally a fixed path; arbitrary source/workspace
# directories are never scanned or adopted.
LEGACY_RUNTIME_RELATIVE = Path("workspace") / "agent-canon-runtime" / "host"
REQUIRED_LABELS = frozenset(
    {
        "io.agent-canon.runtime=shared-v1",
        "io.agent-canon.control-root-digest",
    }
)
ADMISSION_STATES = frozenset({"ready", "running"})
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
MAX_RECEIPT_IO_BYTES = 512
MAX_EMBEDDING_RESPONSE_BYTES = 16 * 1024 * 1024


def _container_control() -> bool:
    """Return whether this process runs behind the host container adapter."""
    return os.environ.get("AGENT_CANON_CONTAINER_CONTROL") == "1"


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
    secret_names = ("token", "password", "secret", "api-key", "api_key", "authorization")
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
    image_tool_root = "/usr/local/share/agent-canon/runtime/tools/"
    if executable in {"python3", "bash"} and len(argv) > 1:
        script = argv[1]
        if script.startswith(image_tool_root):
            return
    if root.resolve() == repository_root.resolve():
        if executable == "python3" and len(argv) > 2 and argv[1:3] == ["-m", "pytest"]:
            return
        if executable == "cargo" and len(argv) > 1 and argv[1] in {
            "build",
            "clippy",
            "fmt",
            "test",
        }:
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
        Path(os.fsdecode(value))
        for value in inventory.stdout.split(b"\0")
        if value
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
        metrics.setdefault("failed_count", sum(item["status"] != "pass" for item in matrix))
    return matrix, metrics


def _copy_external_files(source_root: Path, destination_root: Path) -> int:
    """Copy an exchange subtree into host spool with symlink and conflict checks."""
    if not source_root.exists():
        return 0
    if source_root.is_symlink() or not source_root.is_dir():
        raise BootstrapError("eval_exchange_invalid", f"invalid exchange path: {source_root}")
    files: list[tuple[Path, Path, bytes]] = []
    for source in sorted(source_root.rglob("*")):
        if source.is_symlink():
            raise BootstrapError("eval_exchange_symlink", f"exchange contains a symlink: {source}")
        if not source.is_file():
            continue
        relative = source.relative_to(source_root)
        payload = source.read_bytes()
        target = destination_root / relative
        files.append((source, target, payload))
    for _source, target, payload in files:
        if target.exists():
            if target.is_symlink() or not target.is_file() or target.read_bytes() != payload:
                raise BootstrapError("eval_spool_conflict", f"spool file differs: {target}")
    for _source, target, payload in files:
        if not target.exists():
            _atomic_bytes(target, payload)
    return len(files)


def _validate_exported_tree(root: Path) -> int:
    """Validate a Docker-exported task tree after daemon ownership normalization."""
    if root.is_symlink() or not root.is_dir():
        raise BootstrapError("eval_export_invalid", f"invalid exported tree: {root}")
    count = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise BootstrapError("eval_exchange_symlink", f"export contains a symlink: {path}")
        if path.is_file():
            path.read_bytes()
            count += 1
    return count


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reject redirects for the embedding Host adapter."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _embedding_response(
    request: Mapping[str, Any], *, allowed_endpoints: set[str]
) -> dict[str, Any]:
    """Execute one allowlisted HTTPS embedding request on the Host."""
    required = {
        "schema", "operation", "mode", "uid", "nonce", "deadline_ms",
        "redirect_policy", "endpoint", "body", "request_digest",
    }
    if set(request) != required:
        raise BootstrapError("embedding_request_invalid", "request fields are invalid")
    if (
        request.get("schema") != "agent_canon.embedding.https.request.v1"
        or request.get("operation") != "embedding.https.request"
        or request.get("mode") != "request"
        or request.get("redirect_policy") != "deny"
    ):
        raise BootstrapError("embedding_request_invalid", "request identity is invalid")
    endpoint = request.get("endpoint")
    if not isinstance(endpoint, str) or endpoint not in allowed_endpoints:
        raise BootstrapError("embedding_endpoint_rejected", str(endpoint))
    without_digest = dict(request)
    request_digest = without_digest.pop("request_digest")
    if request_digest != sha256_bytes(_json(without_digest).encode("utf-8")):
        raise BootstrapError("embedding_request_invalid", "request digest mismatch")
    deadline = request.get("deadline_ms")
    if not isinstance(deadline, int) or int(time.time() * 1000) > deadline:
        raise BootstrapError("embedding_request_stale", "request deadline expired")
    body = json.dumps(request["body"], separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("OPENAI_API_KEY")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    http_request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(http_request, timeout=30) as response:
            declared_length = response.headers.get("Content-Length")
            if declared_length is not None:
                try:
                    if int(declared_length) > MAX_EMBEDDING_RESPONSE_BYTES:
                        raise BootstrapError(
                            "embedding_response_quota_exceeded",
                            "embedding response exceeds the Host byte quota",
                        )
                except ValueError as exc:
                    raise BootstrapError(
                        "embedding_request_failed", "invalid Content-Length"
                    ) from exc
            response_bytes = response.read(MAX_EMBEDDING_RESPONSE_BYTES + 1)
            if len(response_bytes) > MAX_EMBEDDING_RESPONSE_BYTES:
                raise BootstrapError(
                    "embedding_response_quota_exceeded",
                    "embedding response exceeds the Host byte quota",
                )
            response_body = json.loads(response_bytes.decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise BootstrapError("embedding_request_failed", type(exc).__name__) from exc
    envelope: dict[str, Any] = {
        "schema": request["schema"],
        "operation": request["operation"],
        "mode": "response",
        "uid": request["uid"],
        "nonce": request["nonce"],
        "deadline_ms": deadline,
        "request_digest": request_digest,
        "status": "ok",
        "body": response_body,
    }
    envelope["response_digest"] = sha256_bytes(_json(envelope).encode("utf-8"))
    return envelope


def _io_evidence(
    task_path: Path, stdout: str, stderr: str, *, quota_bytes: int
) -> dict[str, Any]:
    """Persist redacted command streams and return bounded receipt evidence."""
    streams: dict[str, tuple[str, str]] = {
        "stdout": (stdout, "stdout.log"),
        "stderr": (stderr, "stderr.log"),
    }
    evidence: dict[str, Any] = {}
    total_bytes = sum(len(_redact_output(value).encode("utf-8")) for value in (stdout, stderr))
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
            raise BootstrapError("path_missing", f"{field} does not exist: {path}") from exc
        if stat.S_ISLNK(observed.st_mode):
            raise BootstrapError("symlink_path_rejected", f"{field} contains a symlink: {current}")
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
    *,
    source_root: Path | None = None,
) -> tuple[Path, Path]:
    """Validate roots for the host or the mounted container control plane.

    Host callers use the source-owned ``.runtime`` default.  Container control
    receives its state directory through the host adapter and must use that
    mounted path; otherwise controller writes would land in the image source
    tree and be invisible to the host lifecycle.
    """
    control = _existing_no_symlink(
        Path(control_parent_root), field="control-parent-root"
    )
    if _container_control():
        runtime = _validate_new_path(
            _normalize_absolute_path(Path(runtime_root)),
            field="runtime-root",
            beneath=control,
        )
    else:
        source = _normalize_absolute_path(Path(source_root or runtime_root))
        runtime = _validate_new_path(
            source / ".runtime", field="runtime-root", beneath=source
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


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BootstrapError(
            "docker_readback_invalid",
            f"inspect field is not a non-empty string: {field}",
        )
    return value


def _inspect_object(stdout: str, *, field: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise BootstrapError(
            "docker_readback_invalid", f"Docker {field} inspect was not JSON"
        ) from exc
    if isinstance(payload, list):
        if len(payload) != 1 or not isinstance(payload[0], dict):
            raise BootstrapError(
                "docker_readback_invalid",
                f"Docker {field} inspect returned an unexpected object count",
            )
        payload = payload[0]
    if not isinstance(payload, dict):
        raise BootstrapError(
            "docker_readback_invalid",
            f"Docker {field} inspect did not return an object",
        )
    return payload


class DockerAdapter:
    """Typed Docker argv adapter. No method accepts a shell string."""

    def __init__(
        self, executable: str | Path = "docker", *, timeout: int = 120
    ) -> None:
        """Select a Docker executable without invoking it during construction."""
        self.executable = str(executable)
        self.timeout = timeout
        self.commands: list[list[str]] = []
        self.last_image_created = False

    def run(
        self,
        argv: Sequence[str],
        *,
        check: bool = True,
        timeout: int | None = None,
        environment: Mapping[str, str] | None = None,
        stdin: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one allowlisted Docker argv and return its captured result."""
        if (
            not isinstance(argv, (list, tuple))
            or not argv
            or any(not isinstance(item, str) for item in argv)
        ):
            raise BootstrapError(
                "argv_required", "Docker operations require an argv list of strings"
            )
        if argv[0] != self.executable or any("\x00" in item for item in argv):
            raise BootstrapError(
                "argv_rejected", "Docker argv contains an invalid executable or NUL"
            )
        command = list(argv)
        self.commands.append(command)
        try:
            result = subprocess.run(
                command,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                input=stdin,
                env={**os.environ, **dict(environment or {})},
                timeout=timeout or self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise BootstrapError(
                "docker_command_timeout",
                f"Docker operation exceeded {timeout or self.timeout} seconds",
                evidence={"argv": command[1:]},
            ) from exc
        except (FileNotFoundError, OSError) as exc:
            raise BootstrapError(
                "runtime_unavailable", "Docker executable is unavailable"
            ) from exc
        if check and result.returncode != 0:
            stderr = _redact_output(result.stderr or "")
            stdout = _redact_output(result.stdout or "")
            raise BootstrapError(
                "docker_command_failed",
                f"Docker operation failed with exit {result.returncode}",
                evidence={
                    "argv": _redact_argv(command[1:]),
                    "exit": result.returncode,
                    "stderr_digest": sha256_text(stderr),
                    "stderr_preview": _bounded_output_preview(stderr, 1000),
                    "stderr_truncated": len(stderr) > 1000,
                    "stdout_digest": sha256_text(stdout),
                    "stdout_preview": _bounded_output_preview(stdout, 1000),
                    "stdout_truncated": len(stdout) > 1000,
                },
            )
        return result

    def inspect_image(self, ref: str) -> dict[str, Any] | None:
        """Inspect an image reference, returning ``None`` when absent."""
        result = self.run([self.executable, "image", "inspect", ref], check=False)
        return (
            None if result.returncode else _inspect_object(result.stdout, field="image")
        )

    def pull_image(
        self,
        ref: str,
        *,
        docker_config: Path | None = None,
    ) -> dict[str, Any]:
        """Pull one immutable registry reference and return native-platform inspect."""
        environment = {"DOCKER_CONFIG": str(docker_config)} if docker_config else None
        self.run([self.executable, "pull", ref], environment=environment)
        record = self.inspect_image(ref)
        if record is None:
            raise BootstrapError("docker_readback_invalid", "pulled image disappeared before inspect")
        return record

    @staticmethod
    def validate_registry_image(
        record: Mapping[str, Any], *, source_head: str, image_ref: str
    ) -> dict[str, Any]:
        """Validate OCI revision and native platform for one pulled image."""
        _required_string(record.get("Id"), "image.Id")
        config = record.get("Config")
        labels = config.get("Labels", {}) if isinstance(config, dict) else {}
        if not isinstance(labels, dict) or labels.get("org.opencontainers.image.revision") != source_head:
            raise BootstrapError(
                "image_source_mismatch",
                "registry image revision does not match staged source HEAD",
                evidence={"image_ref": image_ref, "source_head": source_head},
            )
        observed_os = record.get("Os")
        observed_arch = record.get("Architecture")
        if observed_os != "linux" or observed_arch not in {"amd64", "arm64"}:
            raise BootstrapError(
                "unsupported_image_platform",
                "registry image is not a supported native Linux variant",
                evidence={"os": observed_os, "architecture": observed_arch},
            )
        repo_digests = record.get("RepoDigests", [])
        digest = next(
            (value for value in repo_digests if isinstance(value, str) and "@sha256:" in value),
            None,
        )
        if digest is None:
            raise BootstrapError("image_digest_missing", "registry image has no RepoDigest")
        return {
            "image_id": record["Id"],
            "image_repo_digest": digest,
            "image_os": observed_os,
            "image_architecture": observed_arch,
            "image_revision": labels["org.opencontainers.image.revision"],
        }

    def ensure_image(
        self,
        *,
        repository_root: Path,
        dockerfile: Path,
        tag: str,
        labels: Mapping[str, str],
        force_build: bool = False,
    ) -> dict[str, Any]:
        """Build or adopt one manifest-tagged image without install labels."""
        record = self.inspect_image(tag)
        self.last_image_created = record is None
        if record is not None and not force_build:
            self.validate_image(record, {})
            # A matching pre-existing tag is a protected resource. Adopt its
            # exact ID and leave it untouched; rebuilding to the same tag would
            # make ownership of the replacement ambiguous.
            return record
        argv = [
            self.executable,
            "build",
            "--file",
            str(dockerfile),
            "--tag",
            tag,
        ]
        argv.append(str(repository_root))
        self.run(argv)
        record = self.inspect_image(tag)
        if record is None:
            raise BootstrapError(
                "docker_readback_invalid", "built image disappeared before inspect"
            )
        self.validate_image(record, {})
        return record

    @staticmethod
    def validate_image(record: Mapping[str, Any], labels: Mapping[str, str]) -> None:
        """Validate the image ID and ownership labels from Docker inspect."""
        _required_string(record.get("Id"), "image.Id")
        config = record.get("Config")
        observed = config.get("Labels", {}) if isinstance(config, dict) else {}
        if not isinstance(observed, dict) or any(
            observed.get(key) != value for key, value in labels.items()
        ):
            raise BootstrapError(
                "docker_readback_invalid",
                "image labels do not match the manifest owner",
            )

    def inspect_container(self, name_or_id: str) -> dict[str, Any] | None:
        """Inspect a container, returning ``None`` when absent."""
        result = self.run(
            [self.executable, "container", "inspect", name_or_id], check=False
        )
        return (
            None
            if result.returncode
            else _inspect_object(result.stdout, field="container")
        )

    def owned_container_ids(self, control_digest: str) -> list[str]:
        """List container IDs selected by the runtime ownership labels."""
        result = self.run(
            [
                self.executable,
                "container",
                "ls",
                "--all",
                "--filter",
                "label=io.agent-canon.runtime=shared-v1",
                "--filter",
                f"label=io.agent-canon.control-root-digest={control_digest}",
                "--no-trunc",
                "--quiet",
            ],
            check=False,
        )
        return (
            [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if result.returncode == 0
            else []
        )

    def owned_image_ids(self, control_digest: str) -> list[str]:
        """List exact image IDs owned by the shared runtime labels."""
        result = self.run(
            [
                self.executable,
                "image",
                "ls",
                "--filter",
                "label=io.agent-canon.runtime=shared-v1",
                "--filter",
                f"label=io.agent-canon.control-root-digest={control_digest}",
                "--no-trunc",
                "--quiet",
            ],
            check=True,
        )
        return (
            list(dict.fromkeys(line.strip() for line in result.stdout.splitlines() if line.strip()))
            if result.returncode == 0
            else []
        )

    def create_container(
        self,
        *,
        name: str,
        image: str,
        labels: Mapping[str, str],
        cpus: int,
        memory_bytes: int,
        pids: int,
        mounts: Sequence[Mapping[str, str]],
    ) -> str:
        """Create one constrained container and return its ID."""
        argv = [
            self.executable,
            "create",
            "--name",
            name,
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--network",
            "none",
            "--cpus",
            str(cpus),
            "--memory",
            str(memory_bytes),
            "--pids-limit",
            str(pids),
            "--tmpfs",
            "/tmp",
        ]
        for key, value in sorted(labels.items()):
            argv.extend(("--label", f"{key}={value}"))
        for mount in sorted(mounts, key=lambda item: item["destination"]):
            spec = f"type=bind,src={mount['source']},dst={mount['destination']}"
            if mount["mode"] == "read-only":
                spec += ",readonly"
            argv.extend(("--mount", spec))
        argv.append(image)
        result = self.run(argv)
        cid = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        return _required_string(cid, "create stdout container ID")

    def start_container(self, identifier: str) -> None:
        """Start one exact container ID."""
        self.run([self.executable, "start", identifier])

    def stop_container(self, identifier: str, *, timeout: int) -> None:
        """Stop one exact container ID with a bounded grace period."""
        self.run([self.executable, "stop", "--time", str(timeout), identifier])

    def remove_container(self, identifier: str) -> None:
        """Remove one exact owned container ID."""
        self.run([self.executable, "rm", identifier])

    def remove_image(self, identifier: str) -> None:
        """Remove one exact owned image ID."""
        self.run([self.executable, "image", "rm", identifier])

    def exec_container(
        self,
        identifier: str,
        *,
        cwd: str,
        argv: Sequence[str],
        environment: Mapping[str, str] | None = None,
        embedding_exchange: Path | None = None,
        embedding_allowed_endpoints: set[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Execute an argv list in the resident container."""
        if not argv or any(not isinstance(item, str) for item in argv):
            raise BootstrapError(
                "argv_required", "container exec requires a non-empty argv list"
            )
        if _container_control():
            # Container-side tool execution is local to the resident image.
            # Lifecycle Docker operations are not available on this path.
            try:
                return subprocess.run(
                    list(argv),
                    cwd=cwd,
                    env={**os.environ, **dict(environment or {})},
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise BootstrapError(
                    "docker_command_timeout", "container tool execution timed out"
                ) from exc
            except OSError as exc:
                raise BootstrapError(
                    "tool_execution_failed", "container tool execution is unavailable"
                ) from exc
        command = [self.executable, "exec", "--workdir", cwd]
        for key, value in sorted((environment or {}).items()):
            if key not in TOOL_ENVIRONMENT_KEYS:
                raise BootstrapError("environment_rejected", key)
            command.extend(("--env", f"{key}={value}"))
        command.extend((identifier, *argv))
        if embedding_exchange is None:
            return self.run(command, check=False)
        self.commands.append(command)
        try:
            process = subprocess.Popen(
                command,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as exc:
            raise BootstrapError("runtime_unavailable", "Docker executable is unavailable") from exc
        served: set[Path] = set()
        deadline = time.monotonic() + self.timeout
        while process.poll() is None:
            for request_path in embedding_exchange.glob(
                "ipc/embedding.https.request/*/*.request.json"
            ):
                if request_path in served:
                    continue
                served.add(request_path)
                try:
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    if not isinstance(request, dict):
                        raise BootstrapError("embedding_request_invalid", "request is not an object")
                    response = _embedding_response(
                        request,
                        allowed_endpoints=embedding_allowed_endpoints or set(),
                    )
                    nonce = request.get("nonce")
                    if not isinstance(nonce, str) or not SAFE_ID.fullmatch(nonce):
                        raise BootstrapError("embedding_request_invalid", "nonce")
                    host_dir = embedding_exchange / "host-responses"
                    _ensure_directory(host_dir)
                    host_response = host_dir / f"{nonce}.response.json"
                    _atomic_json(host_response, response)
                    relative = request_path.parent.relative_to(embedding_exchange)
                    container_response = (
                        Path(CONTAINER_RUNTIME_DESTINATION)
                        / relative
                        / f"{nonce}.response.json"
                    )
                    copied = subprocess.run(
                        [
                            self.executable,
                            "cp",
                            str(host_response),
                            f"{identifier}:{container_response}",
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if copied.returncode != 0:
                        raise BootstrapError("embedding_response_copy_failed", "docker cp failed")
                    host_response.unlink(missing_ok=True)
                except (OSError, json.JSONDecodeError, BootstrapError):
                    # The Rust caller times out with its typed request identity;
                    # secret-bearing error details are never written to exchange.
                    continue
            if time.monotonic() >= deadline:
                process.kill()
                process.communicate()
                raise BootstrapError("docker_command_timeout", "container exec timed out")
            time.sleep(0.02)
        stdout, stderr = process.communicate()
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

    def copy_from_container(
        self,
        identifier: str,
        *,
        source: str,
        destination: Path,
        allowed_root: Path,
    ) -> None:
        """Export one exact task subtree through Docker's UID normalization."""
        source_path = Path(source)
        if (
            not source.startswith("/var/lib/agent-canon/exchange/tasks/")
            or ".." in source_path.parts
        ):
            raise BootstrapError(
                "docker_copy_rejected", f"unsafe container export: {source}"
            )
        if _container_control():
            source_local = Path(source)
            if source_local.is_symlink() or not source_local.exists():
                raise BootstrapError("docker_copy_rejected", f"container export is missing: {source}")
            destination_resolved = destination.resolve(strict=False)
            allowed_resolved = allowed_root.resolve()
            if destination_resolved != allowed_resolved and allowed_resolved not in destination_resolved.parents:
                raise BootstrapError(
                    "docker_copy_rejected", f"export destination escapes runtime: {destination}"
                )
            if source_local.is_dir():
                shutil.copytree(source_local, destination, dirs_exist_ok=False)
            else:
                _ensure_directory(destination.parent)
                shutil.copy2(source_local, destination)
            return
        destination_resolved = destination.resolve(strict=False)
        allowed_resolved = allowed_root.resolve()
        if destination_resolved != allowed_resolved and allowed_resolved not in destination_resolved.parents:
            raise BootstrapError(
                "docker_copy_rejected", f"export destination escapes runtime: {destination}"
            )
        _ensure_directory(destination)
        self.run(
            [
                self.executable,
                "cp",
                f"{identifier}:{source.rstrip('/')}/.",
                str(destination),
            ]
        )


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
    def mounts(self) -> Path:
        """Return the mount registry path."""
        if _container_control():
            return Path(REGISTRY_DESTINATION)
        return self.runtime_root / "mounts.toml"

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
        """Resolve an explicitly mounted host surface in container control."""
        if not _container_control():
            return None
        value = os.environ.get(f"AGENT_CANON_HOST_{name}_ROOT", "").strip()
        return Path(value) if value else None

    @property
    def container_runtime(self) -> Path:
        """Return the writable, credential-free container exchange directory."""
        if _container_control():
            exchange = os.environ.get("AGENT_CANON_EXCHANGE_ROOT", "").strip()
            if exchange:
                return Path(exchange)
        return self.runtime_root / CONTAINER_RUNTIME_DIR

    @property
    def source_sync(self) -> Path:
        """Return source/image correspondence state."""
        if _container_control():
            return Path(SOURCE_SYNC_DESTINATION) / "source-sync.json"
        return self.runtime_root / "source-sync" / "source-sync.json"

    @property
    def docker_config(self) -> Path:
        """Return the temporary registry authentication directory."""
        return self.runtime_root / "docker-config"

class BootstrapRuntime:
    """Persistent, lock-serialized lifecycle with one Docker container."""

    def __init__(
        self,
        control_parent_root: Path,
        runtime_root: Path,
        *,
        repository_root: Path | None = None,
        manifest_path: Path | None = None,
        docker: DockerAdapter | None = None,
    ) -> None:
        """Create a lifecycle manager bound to explicit control and runtime roots."""
        self.repository_root = (
            repository_root or Path(__file__).resolve().parents[3]
        ).resolve()
        control, runtime = validate_roots(
            Path(control_parent_root),
            Path(runtime_root),
            source_root=self.repository_root,
        )
        self.paths = RuntimePaths(control, runtime)
        self.manifest_path = _manifest_path(self.repository_root, manifest_path)
        self.manifest, policy_digest = load_manifest(self.manifest_path)
        self.manifest_digest = policy_digest
        self.control_digest = os.environ.get(
            "AGENT_CANON_CONTROL_ROOT_DIGEST", sha256_text(str(control))
        )
        self.docker = docker or DockerAdapter(
            os.environ.get("AGENT_CANON_DOCKER", "docker"),
            timeout=int(self.manifest["container"]["task_timeout_seconds"]),
        )
        self._legacy_runtime_pending_cleanup: Path | None = None
        self._legacy_runtime_expected_running = False

    @property
    def private_log_root(self) -> Path:
        """Return the log checkout sibling of the source install.

        The container controller sees the host checkout through its fixed
        private-log mount.  The host-side runtime derives the real checkout
        from the install root, so a caller's control root cannot create a log
        checkout under an unrelated workspace.
        """
        if self._container_control():
            return Path(PRIVATE_LOG_DESTINATION)
        return self.repository_root.parent / "agent-canon-log"

    @property
    def source_sync_read_path(self) -> Path:
        """Return the host-owned source-sync path visible to this controller."""
        if self._container_control():
            return Path(SOURCE_SYNC_DESTINATION) / "source-sync.json"
        return self.paths.source_sync

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

    @staticmethod
    def _container_control() -> bool:
        """Return whether this controller is running behind the host adapter."""
        return _container_control()

    @property
    def default_runtime_root(self) -> bool:
        """Return whether this manager uses the source-owned default runtime."""
        return self.paths.runtime_root == self.repository_root / ".runtime"

    @property
    def legacy_runtime_root(self) -> Path:
        """Return the one fixed pre-source-owned runtime migration path."""
        return self.paths.control_parent_root / LEGACY_RUNTIME_RELATIVE

    def _read_legacy_runtime_state(self, legacy: Path) -> dict[str, Any]:
        """Read the fixed legacy state without applying current-root mapping."""
        if legacy.is_symlink() or not legacy.is_dir():
            raise BootstrapError(
                "legacy_runtime_invalid", f"legacy runtime is not a directory: {legacy}"
            )
        try:
            state = json.loads(
                _safe_read(legacy / STATE_FILE, field="legacy runtime state").decode("utf-8")
            )
            owner = json.loads(
                _safe_read(legacy / OWNER_FILE, field="legacy runtime owner").decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BootstrapError(
                "legacy_runtime_invalid", "legacy runtime state or owner is not valid JSON"
            ) from exc
        if not isinstance(state, dict) or state.get("schema") not in {
            SCHEMA_STATE,
            "agent-canon.bootstrap-state.v1",
        }:
            raise BootstrapError("legacy_runtime_invalid", "legacy runtime state schema is unsupported")
        if not isinstance(owner, dict) or owner.get("schema") != "agent-canon.bootstrap-owner.v1":
            raise BootstrapError("legacy_runtime_invalid", "legacy runtime owner schema is unsupported")
        expected_root = legacy.resolve()
        for record, name in ((state, "state"), (owner, "owner")):
            if record.get("control_root_digest") != self.control_digest:
                raise BootstrapError(
                    "legacy_runtime_invalid", f"legacy runtime {name} belongs to another control root"
                )
            recorded_source = record.get("repository_root")
            if not recorded_source or Path(str(recorded_source)).resolve() != self.repository_root:
                raise BootstrapError(
                    "legacy_runtime_invalid", f"legacy runtime {name} belongs to another source root"
                )
            recorded_runtime = record.get("runtime_root")
            if not recorded_runtime or Path(str(recorded_runtime)).resolve() != expected_root:
                raise BootstrapError(
                    "legacy_runtime_invalid", f"legacy runtime {name} points at a different root"
                )
        return state

    def _ensure_layout(self) -> None:
        _ensure_directory(self.paths.runtime_root)
        self._enforce_private_directory(self.paths.runtime_root)
        controller_dirs = (RECEIPT_DIR, GENERATION_DIR, TASK_DIR)
        for name in controller_dirs:
            path = self.paths.runtime_root / name
            _ensure_directory(path)
            self._enforce_private_directory(path)
        for path in (self.paths.spool, self.paths.archive, self.paths.cache, self.paths.codex_home):
            _ensure_directory(path)
            self._enforce_private_directory(path)
        exchange_mode = 0o700 if self._container_control() else 0o1777
        _ensure_directory(self.paths.container_runtime, mode=exchange_mode)
        if self._container_control():
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
        else:
            try:
                os.chmod(self.paths.container_runtime, exchange_mode, follow_symlinks=False)
            except OSError as exc:
                raise BootstrapError(
                    "exchange_directory_invalid",
                    "cannot set container runtime exchange mode 01777",
                ) from exc
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
            raise BootstrapError("symlink_path_rejected", "private log checkout is a symlink")
        if not private_log.exists():
            if self._container_control():
                raise BootstrapError(
                    "private_log_mount_invalid",
                    "resident container is missing the host-owned private log mount",
                )
            try:
                private_log.mkdir(mode=0o700)
            except OSError as exc:
                raise BootstrapError("private_log_mount_invalid", "cannot create private log mount") from exc
        if not self._container_control():
            self._enforce_private_directory(private_log)

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

    def _read_state(self, *, allow_manifest_drift: bool = False) -> dict[str, Any]:
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
        recorded_source = value.get("repository_root")
        if recorded_source and Path(str(recorded_source)).resolve() != self.repository_root:
            raise BootstrapError(
                "source_runtime_owned_elsewhere",
                "runtime is owned by another AgentCanon source root",
                evidence={
                    "owner_source_root": recorded_source,
                    "requested_source_root": str(self.repository_root),
                },
            )
        if (
            value.get("manifest_digest") != self.manifest_digest
            and not allow_manifest_drift
        ):
            raise BootstrapError(
                "manifest_mismatch",
                "runtime manifest digest differs from selected manifest",
            )
        return value

    def _preflight_runtime_reset(
        self, root: Path, state: Mapping[str, Any] | None
    ) -> None:
        """Reject only active or pending work before reconstructive cleanup."""
        if state is not None and int(state.get("active_task_count", 0)):
            raise BootstrapError(
                "runtime_reset_blocked",
                "active tasks prevent reconstructive runtime cleanup",
            )
        tasks = state.get("tasks", {}) if isinstance(state, Mapping) else {}
        if isinstance(tasks, Mapping) and any(
            isinstance(item, Mapping) and item.get("state") == "active"
            for item in tasks.values()
        ):
            raise BootstrapError(
                "runtime_reset_blocked",
                "active task records prevent reconstructive runtime cleanup",
            )
        spool = root / "spool"
        if spool.is_dir() and any(spool.iterdir()):
            raise BootstrapError(
                "runtime_reset_blocked",
                "pending runtime spool prevents reconstructive cleanup",
            )

    def _clear_source_runtime(self) -> None:
        """Clear only bootstrap-owned source runtime children, retaining its lock."""
        for child in self.paths.runtime_root.iterdir():
            if child.name == "lifecycle.lock":
                continue
            if child.is_symlink():
                raise BootstrapError(
                    "symlink_path_rejected", f"runtime child is a symlink: {child}"
                )
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    def _prepare_legacy_runtime_reset(self) -> None:
        """Stop the old owned runtime and prepare a fresh source runtime."""
        if not self.default_runtime_root or self._legacy_runtime_pending_cleanup:
            return
        legacy = self.legacy_runtime_root
        if legacy == self.paths.runtime_root or not legacy.exists():
            return
        if legacy.is_symlink() or not legacy.is_dir():
            raise BootstrapError(
                "legacy_runtime_invalid", f"legacy runtime is not a directory: {legacy}"
            )
        if not (legacy / STATE_FILE).is_file() or not (legacy / OWNER_FILE).is_file():
            return
        old_state = self._read_legacy_runtime_state(legacy)
        self._preflight_runtime_reset(legacy, old_state)
        current_state: dict[str, Any] | None = None
        if self.paths.state.exists():
            current_state = self._read_state(allow_manifest_drift=True)
            self._preflight_runtime_reset(self.paths.runtime_root, current_state)
        self._stop_owned_container(old_state)
        if current_state is not None:
            self._stop_owned_container(current_state)
        self._legacy_runtime_expected_running = bool(
            old_state.get("state") in {"ready", "running"}
            or old_state.get("resources", {}).get("container", {}).get("id")
        )
        self._clear_source_runtime()
        self._legacy_runtime_pending_cleanup = legacy

    def _finalize_legacy_runtime_reset(self) -> None:
        """Validate fresh state, then remove only the exact old owned root."""
        legacy = self._legacy_runtime_pending_cleanup
        if legacy is None:
            return
        state = self._read_state(allow_manifest_drift=True)
        if self._legacy_runtime_expected_running:
            if state.get("state") == "uninstalled":
                raise BootstrapError(
                    "runtime_reset_unhealthy", "fresh runtime was not installed"
                )
            self._write_mounts(state)
            self._ensure_container(state, start=True)
            state["state"] = "ready"
            self._write_state(state)
            container = self._container_inspect(state, require_running=True)
            if container is None:
                raise BootstrapError(
                    "runtime_reset_unhealthy", "fresh runtime has no healthy container"
                )
            self._verify_registry_mount(state, str(container["Id"]))
        if legacy.is_symlink() or not legacy.is_dir():
            raise BootstrapError("legacy_runtime_invalid", f"legacy runtime changed: {legacy}")
        self._read_legacy_runtime_state(legacy)
        shutil.rmtree(legacy)
        legacy_parent = legacy.parent
        if (
            legacy_parent == self.paths.control_parent_root / "workspace" / "agent-canon-runtime"
            and legacy_parent.is_dir()
            and not legacy_parent.is_symlink()
            and not any(legacy_parent.iterdir())
        ):
            legacy_parent.rmdir()
        self._legacy_runtime_pending_cleanup = None

    def _write_state(self, state: dict[str, Any]) -> None:
        state["schema"], state["updated_at"] = SCHEMA_STATE, _now()
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
        if self._container_control() and container_image:
            return container_image
        return (
            f"agent-canon-tools:{self.control_digest[:16]}-"
            f"{self.manifest_digest[:16]}"
        )

    def _labels(self) -> dict[str, str]:
        return {
            "io.agent-canon.runtime": "shared-v1",
            "io.agent-canon.control-root-digest": self.control_digest,
        }

    def _resource_records(self) -> dict[str, Any]:
        name = os.environ.get("AGENT_CANON_CONTAINER_NAME") if self._container_control() else None
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

    def _image(self, state: dict[str, Any], *, force_build: bool = False) -> dict[str, Any]:
        image = self.docker.ensure_image(
            repository_root=self.repository_root,
            dockerfile=self.repository_root / "bootstrap" / "container" / "image" / "Dockerfile",
            tag=self._image_tag(),
            labels=self._labels(),
            force_build=force_build,
        )
        image_id = _required_string(image.get("Id"), "image.Id")
        resources = state.setdefault("resources", self._resource_records())
        previous = resources.get("image", {})
        owned = (
            bool(previous.get("owned"))
            if previous.get("id")
            else bool(self.docker.last_image_created)
            or os.environ.get("AGENT_CANON_IMAGE_OWNED") == "1"
        )
        resources["image"] = {
            "id": image_id,
            "tag": self._image_tag(),
            "owned": owned,
            "labels": {},
            "state": "present",
        }
        return image

    def _adopt_registry_image_locked(
        self,
        state: dict[str, Any],
        image_ref: str,
        image_record: Mapping[str, Any],
        source_head: str,
    ) -> dict[str, Any]:
        """Adopt one already-pulled immutable image without invoking Docker build."""
        if state.get("state") == "uninstalled":
            raise BootstrapError("not_installed", "install must complete before registry image adoption")
        if state.get("active_task_count", 0):
            raise BootstrapError(
                "mount_update_blocked",
                "active tasks prevent registry image adoption",
                evidence={"active_task_count": state.get("active_task_count", 0)},
            )
        stale = self._prune_stale_targets(state)
        if stale:
            self._write_mounts(state)
            self._write_mount_manifest(state)
        image_id = _required_string(image_record.get("Id"), "registry image.Id")
        old_state = json.loads(_json(state))
        before = str(state.get("state"))
        old_container_running = bool(
            old_state.get("resources", {}).get("container", {}).get("id")
            or before in {"ready", "running"}
        )
        old_image = old_state.get("resources", {}).get("image", {})
        try:
            state.setdefault("resources", self._resource_records())["image"] = {
                "id": image_id,
                "tag": image_ref,
                "owned": True,
                "labels": {},
                "state": "present",
                "repo_digest": next(
                    (
                        value
                        for value in image_record.get("RepoDigests", [])
                        if isinstance(value, str) and "@sha256:" in value
                    ),
                    None,
                ),
                "os": image_record.get("Os"),
                "architecture": image_record.get("Architecture"),
                "source_head": source_head,
            }
            state["state"] = "maintenance_pending"
            self._write_state(state)
            self._stop_owned_container(state)
            if old_container_running:
                self._ensure_container(state, start=True)
                state["state"] = "ready"
            else:
                state["state"] = "installed"
            self._write_state(state)
            return self._result(
                self._receipt(
                    "update_registry_image",
                    "ok",
                    "updated",
                    before=before,
                    after=state["state"],
                    details={
                        "image_ref": image_ref,
                        "image_id": image_id,
                        "source_head": source_head,
                        "image_repo_digest": state["resources"]["image"].get("repo_digest"),
                        "image_os": state["resources"]["image"].get("os"),
                        "image_architecture": state["resources"]["image"].get("architecture"),
                    },
                    state=state,
                )
            )
        except BootstrapError as exc:
            candidate = state.get("resources", {}).get("image", {})
            candidate_id = candidate.get("id") if isinstance(candidate, dict) else None
            old_id = old_image.get("id") if isinstance(old_image, dict) else None
            if candidate_id and candidate_id != old_id:
                if self.docker.inspect_image(str(candidate_id)) is not None:
                    self.docker.remove_image(str(candidate_id))
            state.clear()
            state.update(old_state)
            recovery_error: BootstrapError | None = None
            try:
                self._write_mounts(state)
                if old_container_running:
                    self._ensure_container(state, start=True)
                state["state"] = before
                self._write_state(state)
            except BootstrapError as restore_error:
                recovery_error = restore_error
                state["state"] = "runtime_unavailable"
                self._write_state(state)
            receipt = self._result(
                self._receipt(
                    "update_registry_image",
                    "error",
                    "runtime_unavailable" if recovery_error else exc.code,
                    before=before,
                    after=state["state"],
                    details={"recovery_error": recovery_error.code if recovery_error else None},
                    state=state,
                )
            )
            raise BootstrapError(
                "runtime_unavailable" if recovery_error else exc.code,
                "registry image adoption failed" if recovery_error else exc.detail,
                evidence={**exc.evidence, "receipt_path": receipt["receipt_path"], "recovered": recovery_error is None},
            ) from exc

    def update_registry_image(
        self,
        image_ref: str,
        image_record: Mapping[str, Any],
        source_head: str,
    ) -> dict[str, Any]:
        """Adopt an already-pulled registry image; this route never builds locally."""
        self._materialize_skill_view()
        with self.locked():
            state = self._read_state(allow_manifest_drift=True)
            result = self._adopt_registry_image_locked(state, image_ref, image_record, source_head)
        self.codex_prepare()
        return result

    def _mounts(self, targets: Mapping[str, Mapping[str, Any]]) -> list[dict[str, str]]:
        mounts = [
            {
                "source": str(
                    self.paths.runtime_root
                    if self._container_control()
                    else self.paths.container_runtime
                ),
                "destination": CONTAINER_RUNTIME_DESTINATION,
                "mode": "explicit-target-write",
            },
            {
                "source": str(
                    self.private_log_root
                ),
                "destination": PRIVATE_LOG_DESTINATION,
                "mode": "read-only",
            },
        ]
        if not self._container_control():
            mounts.insert(
                1,
                {
                    "source": str(self.paths.mounts),
                    "destination": REGISTRY_DESTINATION,
                    "mode": "read-only",
                },
            )
        for digest, record in sorted(targets.items()):
            mounts.append(
                {
                    "source": str(record["root"]),
                    "destination": f"/targets/{digest}",
                    "mode": "read-only",
                }
            )
            for relative in record.get("allowed_paths", []):
                mounts.append(
                    {
                        "source": str(Path(record["root"]) / relative),
                        "destination": f"/targets/{digest}/{relative}",
                        "mode": "explicit-target-write",
                    }
                )
        return mounts

    def _validate_cleanup_resource(
        self,
        record: Mapping[str, Any],
        state: Mapping[str, Any],
        kind: str,
    ) -> None:
        """Authorize cleanup from pinned state, independent of changed source inputs."""
        resource = state.get("resources", {}).get(kind, {})
        if not isinstance(resource, dict) or resource.get("owned") is not True:
            raise BootstrapError(
                "docker_readback_invalid", f"{kind} is not recorded as an owned resource"
            )
        expected_id = resource.get("id")
        if not expected_id or record.get("Id") != expected_id:
            raise BootstrapError(
                "docker_readback_invalid", f"{kind} ID differs from pinned state"
            )
        if kind == "image" and not resource.get("labels"):
            # Registry images intentionally carry only OCI publication labels;
            # the exact pulled ID in state is the install ownership receipt.
            return
        expected_labels = resource.get("labels")
        observed_config = record.get("Config")
        observed_labels = (
            observed_config.get("Labels", {})
            if isinstance(observed_config, dict)
            else {}
        )
        required_label_keys = {
            "io.agent-canon.runtime",
            "io.agent-canon.control-root-digest",
        }
        if (
            not isinstance(expected_labels, dict)
            or not required_label_keys.issubset(expected_labels)
            or any(
                observed_labels.get(key) != expected_labels.get(key)
                for key in required_label_keys
            )
            or expected_labels.get("io.agent-canon.control-root-digest")
            != self.control_digest
        ):
            raise BootstrapError(
                "docker_readback_invalid",
                f"{kind} labels differ from pinned ownership state",
            )
        if kind == "container":
            expected_name = resource.get("name")
            observed_name = record.get("Name")
            if expected_name and observed_name not in {
                expected_name,
                f"/{expected_name}",
            }:
                raise BootstrapError(
                    "docker_readback_invalid",
                    "container name differs from pinned ownership state",
                )

    def _validate_container(
        self, record: Mapping[str, Any], state: Mapping[str, Any]
    ) -> None:
        """Validate immutable post-create/adopt ownership and run invariants."""
        labels = (
            record.get("Config", {}).get("Labels", {})
            if isinstance(record.get("Config"), dict)
            else {}
        )
        if not isinstance(labels, dict) or any(
            labels.get(key) != value for key, value in self._labels().items()
        ):
            raise BootstrapError(
                "docker_readback_invalid", "container labels do not match the owner"
            )
        observed_id = _required_string(record.get("Id"), "container.Id")
        expected_id = state.get("resources", {}).get("container", {}).get("id")
        if expected_id and observed_id != expected_id and not self._container_control():
            raise BootstrapError(
                "docker_readback_invalid", "container ID differs from state"
            )
        expected_name = state.get("resources", {}).get("container", {}).get("name")
        observed_name = record.get("Name")
        if expected_name and observed_name not in {expected_name, f"/{expected_name}"}:
            raise BootstrapError(
                "docker_readback_invalid", "container name differs from state"
            )
        state_info = record.get("State", {})
        if not isinstance(state_info, dict):
            raise BootstrapError(
                "docker_readback_invalid", "container.State is missing"
            )
        host = record.get("HostConfig")
        if not isinstance(host, dict):
            raise BootstrapError(
                "docker_readback_invalid", "container HostConfig is missing"
            )

        c = self.manifest["container"]
        for key, expected in (
            ("ReadonlyRootfs", True),
            ("NetworkMode", "none"),
            ("Memory", int(c["memory_bytes"])),
            ("PidsLimit", int(c["pids_limit"])),
            ("NanoCpus", int(c["cpus"]) * 1_000_000_000),
        ):
            if key not in host or host.get(key) != expected:
                raise BootstrapError(
                    "docker_readback_invalid", f"resource mismatch: {key}"
                )
        cap_drop = host.get("CapDrop")
        if not isinstance(cap_drop, list) or "ALL" not in cap_drop:
            raise BootstrapError(
                "docker_readback_invalid", "container capability drop readback mismatch"
            )
        security = host.get("SecurityOpt")
        if not isinstance(security, list) or "no-new-privileges" not in security:
            raise BootstrapError(
                "docker_readback_invalid", "container security option readback mismatch"
            )
        tmpfs = host.get("Tmpfs")
        if isinstance(tmpfs, dict):
            has_tmpfs = "/tmp" in tmpfs
        elif isinstance(tmpfs, list):
            has_tmpfs = "/tmp" in tmpfs
        else:
            has_tmpfs = False
        if not has_tmpfs:
            raise BootstrapError(
                "docker_readback_invalid", "container /tmp tmpfs readback mismatch"
            )
        mounts = record.get("Mounts", [])
        if not isinstance(mounts, list):
            raise BootstrapError(
                "docker_readback_invalid", "mount readback is not a list"
            )
        expected_mounts = {
            (
                str(_normalize_absolute_path(Path(m["source"]))),
                m["destination"],
                m["mode"],
            )
            for m in self._mounts(state.get("targets", {}))
        }
        observed_mounts: set[tuple[str, str, str]] = set()
        for mount in mounts:
            if not isinstance(mount, dict):
                raise BootstrapError(
                    "docker_readback_invalid", "mount is not an object"
                )
            mode = (
                "read-only"
                if mount.get("RW") is False
                or mount.get("ReadOnly") is True
                or mount.get("Mode") in {"ro", "ro,z"}
                else "explicit-target-write"
            )
            source = str(mount.get("Source"))
            normalized_source = (
                str(_normalize_absolute_path(Path(source)))
                if Path(source).is_absolute()
                else source
            )
            if self._container_control():
                host_runtime = os.environ.get("AGENT_CANON_HOST_STATE_ROOT")
                host_private_log = os.environ.get("AGENT_CANON_HOST_PRIVATE_LOG")
                if host_runtime and normalized_source == str(Path(host_runtime).resolve()):
                    normalized_source = str(Path("/var/lib/agent-canon/runtime"))
                elif host_runtime and normalized_source.startswith(
                    str(Path(host_runtime).resolve()) + "/"
                ):
                    relative = normalized_source.removeprefix(
                        str(Path(host_runtime).resolve()) + "/"
                    )
                    normalized_source = f"/var/lib/agent-canon/runtime/{relative}"
                elif host_private_log and normalized_source == str(Path(host_private_log).resolve()):
                    normalized_source = str(Path("/var/lib/agent-canon/private-log"))
            observed_mounts.add(
                (normalized_source, str(mount.get("Destination")), mode)
            )
        if observed_mounts != expected_mounts:
            fields = ("source", "destination", "mode")
            raise BootstrapError(
                "docker_readback_invalid",
                "mount readback mismatch",
                evidence={
                    "missing_mounts": [
                        dict(zip(fields, item, strict=True))
                        for item in sorted(expected_mounts - observed_mounts)
                    ],
                    "unexpected_mounts": [
                        dict(zip(fields, item, strict=True))
                        for item in sorted(observed_mounts - expected_mounts)
                    ],
                },
            )

    @staticmethod
    def _validate_container_health(record: Mapping[str, Any]) -> None:
        """Validate only the mutable health fields during a health poll."""
        state_info = record.get("State")
        if not isinstance(state_info, dict) or state_info.get("Running") is not True:
            raise BootstrapError("container_unhealthy", "container is not running")
        health = state_info.get("Health")
        if not isinstance(health, dict) or health.get("Status") != "healthy":
            raise BootstrapError(
                "container_unhealthy", "container health probe is not healthy"
            )

    def _container_inspect(
        self, state: dict[str, Any], *, require_running: bool
    ) -> dict[str, Any] | None:
        c = state.get("resources", {}).get("container", {})
        identifier = c.get("id") or c.get("name")
        if not identifier:
            return None
        record = self.docker.inspect_container(str(identifier))
        if record is not None:
            self._validate_container(record, state)
            if require_running:
                self._validate_container_health(record)
        return record

    def _verify_registry_mount(
        self, state: Mapping[str, Any], container_id: str
    ) -> None:
        """Verify registry content visible through the container bind mount."""
        if self._container_control():
            return
        expected = _safe_read(self.paths.mounts, field="mount registry")
        result = self.docker.exec_container(
            container_id, cwd="/", argv=["cat", REGISTRY_DESTINATION]
        )
        if result.returncode != 0:
            raise BootstrapError(
                "registry_mount_readback_failed",
                "container could not read the sanitized mount registry",
                evidence={"container_id": container_id, "exit": result.returncode},
            )
        observed = result.stdout.encode("utf-8")
        if sha256_bytes(observed) != sha256_bytes(expected):
            raise BootstrapError(
                "registry_mount_readback_failed",
                "container registry content differs from the candidate snapshot",
                evidence={
                    "container_id": container_id,
                    "expected_digest": sha256_bytes(expected),
                    "observed_digest": sha256_bytes(observed),
                },
            )

    def _wait_for_healthy(
        self, state: dict[str, Any], container_id: str
    ) -> dict[str, Any]:
        """Poll Docker health until healthy or the manifest deadline expires."""
        container = self.manifest["container"]
        deadline = (
            time.monotonic()
            + float(container["health_start_period_seconds"])
            + float(container["health_timeout_seconds"])
        )
        interval = float(container["health_poll_interval_seconds"])
        last: dict[str, Any] | None = None
        while True:
            inspected = self.docker.inspect_container(container_id)
            if inspected is None:
                raise BootstrapError(
                    "docker_readback_invalid",
                    "container disappeared during health polling",
                    evidence={"container_id": container_id},
                )
            last = inspected
            state_info = inspected.get("State", {})
            health = (
                state_info.get("Health", {}) if isinstance(state_info, dict) else {}
            )
            if (
                isinstance(state_info, dict)
                and state_info.get("Running") is True
                and isinstance(health, dict)
                and health.get("Status") == "healthy"
            ):
                return inspected
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                cleanup: dict[str, Any] = {"stopped": False, "removed": False}
                try:
                    if (
                        isinstance(state_info, dict)
                        and state_info.get("Running") is True
                    ):
                        self.docker.stop_container(
                            container_id,
                            timeout=int(container["termination_grace_seconds"]),
                        )
                        cleanup["stopped"] = True
                    if self.docker.inspect_container(container_id) is not None:
                        self.docker.remove_container(container_id)
                        cleanup["removed"] = True
                    cleanup["absent"] = (
                        self.docker.inspect_container(container_id) is None
                    )
                except BootstrapError as exc:
                    cleanup["error"] = exc.code
                state["resources"]["container"]["state"] = "quarantined"
                raise BootstrapError(
                    "container_health_timeout",
                    "container did not become healthy before the manifest deadline",
                    evidence={
                        "container_id": container_id,
                        "health_deadline_seconds": float(
                            container["health_start_period_seconds"]
                        )
                        + float(container["health_timeout_seconds"]),
                        "last": self._container_summary(last),
                        "cleanup": cleanup,
                    },
                )
            time.sleep(min(interval, remaining))

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

    def _container_summary(
        self, record: Mapping[str, Any] | None
    ) -> dict[str, Any] | None:
        """Return safe Docker readback fields and omit Env/raw inspect data."""
        if record is None:
            return None
        state: Mapping[str, Any] = (
            cast(Mapping[str, Any], record.get("State"))
            if isinstance(record.get("State"), dict)
            else {}
        )
        health: Mapping[str, Any] = (
            cast(Mapping[str, Any], state.get("Health"))
            if isinstance(state.get("Health"), dict)
            else {}
        )
        host: Mapping[str, Any] = (
            cast(Mapping[str, Any], record.get("HostConfig"))
            if isinstance(record.get("HostConfig"), dict)
            else {}
        )
        mounts = (
            cast(list[Any], record.get("Mounts"))
            if isinstance(record.get("Mounts"), list)
            else []
        )
        summarized_mounts: list[dict[str, Any]] = []
        for mount in mounts:
            if not isinstance(mount, dict):
                continue
            source = mount.get("Source")
            mode = (
                "read-only"
                if mount.get("RW") is False
                or mount.get("ReadOnly") is True
                or mount.get("Mode") in {"ro", "ro,z"}
                else "explicit-target-write"
            )
            summarized_mounts.append(
                {
                    "source_digest": sha256_text(str(source)),
                    "destination": mount.get("Destination"),
                    "mode": mode,
                }
            )
        return {
            "id": record.get("Id"),
            "name": record.get("Name"),
            "running": state.get("Running"),
            "health": health.get("Status"),
            "resource_limits": {
                "readonly_rootfs": host.get("ReadonlyRootfs"),
                "network": host.get("NetworkMode"),
                "memory_bytes": host.get("Memory"),
                "pids_limit": host.get("PidsLimit"),
                "nano_cpus": host.get("NanoCpus"),
                "cap_drop": host.get("CapDrop"),
                "security_options": host.get("SecurityOpt"),
                "tmpfs": sorted(host.get("Tmpfs", {}).keys())
                if isinstance(host.get("Tmpfs"), dict)
                else host.get("Tmpfs"),
            },
            "mounts": summarized_mounts,
        }

    def _install_locked(self, image_ref: str | None = None) -> dict[str, Any]:
        """Install while the caller owns the lifecycle lock."""
        result: dict[str, Any] | None = None
        with contextlib.nullcontext():
            state = self._read_state(allow_manifest_drift=True)
            if state.get("state") == "uninstalled":
                stale = self._prune_stale_targets(state)
                if stale:
                    self._write_mounts(state)
                    self._write_mount_manifest(state)
                    self._write_state(state)
            if state.get("state") != "uninstalled":
                if image_ref:
                    raise BootstrapError(
                        "install_image_ref_requires_uninstalled",
                        "immutable install image adoption requires a fresh runtime",
                    )
                result = self._update_locked(state, "install")
                # codex_prepare runs after the lifecycle lock is released.
                pass
            else:
                if state.get("manifest_digest") != self.manifest_digest:
                    state = self._new_state()
                before = state["state"]
                if image_ref:
                    image_record = self.docker.inspect_image(image_ref)
                    if image_record is None:
                        raise BootstrapError(
                            "image_missing", f"registry image is not pulled: {image_ref}"
                        )
                    source_head = _source_snapshot(self.repository_root)["head"]
                    self.docker.validate_registry_image(
                        image_record, source_head=source_head, image_ref=image_ref
                    )
                    state["state"] = "installed"
                    state["resources"] = self._resource_records()
                    state["managed_paths"] = [
                        STATE_FILE,
                        OWNER_FILE,
                        "mounts.toml",
                        *KNOWN_SUBDIRS,
                        CONTAINER_RUNTIME_DIR,
                    ]
                    self._write_mounts(state)
                    self._write_state(state)
                    result = self._adopt_registry_image_locked(
                        state,
                        image_ref,
                        image_record,
                        source_head,
                    )
                else:
                    self._materialize_skill_view()
                    self._image(state)
                    state["state"] = "installed"
                    state.setdefault("resources", self._resource_records()).setdefault(
                        "container", self._resource_records()["container"]
                    )
                    state["managed_paths"] = [
                        STATE_FILE,
                        OWNER_FILE,
                        "mounts.toml",
                        *KNOWN_SUBDIRS,
                        CONTAINER_RUNTIME_DIR,
                    ]
                    self._write_mounts(state)
                    self._write_state(state)
                    result = self._result(
                        self._receipt(
                            "install",
                            "ok",
                            "installed",
                            before=before,
                            after=state["state"],
                            details={"image_id": state["resources"]["image"]["id"]},
                            state=state,
                        )
                    )
        assert result is not None
        return result

    def install(self, image_ref: str | None = None) -> dict[str, Any]:
        """Install the initial image or reconcile an existing runtime."""
        with self.locked():
            self._prepare_legacy_runtime_reset()
            result = self._install_locked(image_ref)
        self.codex_prepare()
        self._finalize_legacy_runtime_reset()
        return result

    def _update_locked(self, state: dict[str, Any], operation: str) -> dict[str, Any]:
        """Reconcile current checkout/image inputs with existing v2 lifecycle state."""
        if state.get("active_task_count", 0):
            raise BootstrapError(
                "mount_update_blocked",
                "active tasks prevent update; candidate build was not started",
                evidence={"active_task_count": state.get("active_task_count", 0)},
            )
        stale = self._prune_stale_targets(state)
        if stale:
            self._write_mounts(state)
            self._write_mount_manifest(state)
            self._write_state(state)
        resources = state.get("resources", {})
        image = resources.get("image", {}) if isinstance(resources, dict) else {}
        if image.get("owned") is not True:
            self._materialize_skill_view()
            self._write_state(state)
            return self._result(
                self._receipt(
                    operation,
                    "ok",
                    "up_to_date",
                    before=state["state"],
                    after=state["state"],
                    details={"changed": False, "reason": "pre_existing_image"},
                    state=state,
                )
            )
        old_state = json.loads(_json(state))
        before = state["state"]
        old_container_running = bool(
            old_state.get("resources", {}).get("container", {}).get("id")
            or before in {"ready", "running"}
        )
        try:
            self._materialize_skill_view()
            self._image(state, force_build=True)
            state["manifest_digest"] = self.manifest_digest
            state["state"] = "maintenance_pending"
            self._write_state(state)
            self._stop_owned_container(state)
            if old_container_running:
                self._ensure_container(state, start=True)
                state["state"] = "ready"
            else:
                state["state"] = "installed"
            self._write_state(state)
            return self._result(
                self._receipt(
                    operation,
                    "ok",
                    "updated",
                    before=before,
                    after=state["state"],
                    details={
                        "image_id": state["resources"]["image"]["id"],
                    },
                    state=state,
                )
            )
        except BootstrapError as exc:
            candidate_image = state.get("resources", {}).get("image", {})
            old_image = old_state.get("resources", {}).get("image", {})
            candidate_image_id = candidate_image.get("id") if isinstance(candidate_image, dict) else None
            old_image_id = old_image.get("id") if isinstance(old_image, dict) else None
            if candidate_image_id and candidate_image_id != old_image_id:
                inspected_image = self.docker.inspect_image(str(candidate_image_id))
                if inspected_image is not None:
                    self.docker.validate_image(inspected_image, {})
                    self.docker.remove_image(str(candidate_image_id))
            state.clear()
            state.update(old_state)
            recovery_error: BootstrapError | None = None
            try:
                self._write_mounts(state)
                if old_container_running:
                    self._ensure_container(state, start=True)
                state["state"] = before
                self._write_state(state)
            except BootstrapError as restore_error:
                recovery_error = restore_error
                state["state"] = "runtime_unavailable"
                self._write_state(state)
            receipt = self._result(
                self._receipt(
                    operation,
                    "error",
                    "runtime_unavailable" if recovery_error else exc.code,
                    before=before,
                    after=state["state"],
                    details={
                        "recovery_error": recovery_error.code if recovery_error else None,
                    },
                    state=state,
                )
            )
            if recovery_error:
                raise BootstrapError(
                    "runtime_unavailable",
                    "update failed and old runtime recovery failed",
                    evidence={"cause": exc.code, "recovery": recovery_error.code, "receipt_path": receipt["receipt_path"]},
                ) from exc
            raise BootstrapError(
                exc.code,
                exc.detail,
                evidence={**exc.evidence, "receipt_path": receipt["receipt_path"], "recovered": True},
            ) from exc

    def update(self, image_ref: str | None = None) -> dict[str, Any]:
        """Reconcile only the current checkout; never acquires a Git revision."""
        with self.locked():
            self._prepare_legacy_runtime_reset()
            state = self._read_state(allow_manifest_drift=True)
            fresh_reset = self._legacy_runtime_pending_cleanup is not None
            if state.get("state") == "uninstalled" and not fresh_reset:
                raise BootstrapError("not_installed", "install must complete before update")
            if state.get("state") == "uninstalled":
                stale = self._prune_stale_targets(state)
                if stale:
                    self._write_mounts(state)
                    self._write_mount_manifest(state)
                    self._write_state(state)
            fresh_result: dict[str, Any] | None = None
            if state.get("state") == "uninstalled":
                before = state["state"]
                state["state"] = "installed"
                state["resources"] = self._resource_records()
                state["managed_paths"] = [
                    STATE_FILE,
                    OWNER_FILE,
                    "mounts.toml",
                    "mounts.tsv",
                    *KNOWN_SUBDIRS,
                    CONTAINER_RUNTIME_DIR,
                ]
                if not image_ref:
                    self._image(state, force_build=True)
                    self._write_mounts(state)
                    self._write_state(state)
                    fresh_result = self._result(
                        self._receipt(
                            "update",
                            "ok",
                            "updated",
                            before=before,
                            after=state["state"],
                            details={"image_id": state["resources"]["image"]["id"]},
                            state=state,
                        )
                    )
                else:
                    self._write_mounts(state)
                    self._write_state(state)
            if image_ref:
                image_record = self.docker.inspect_image(image_ref)
                if image_record is None:
                    raise BootstrapError("image_missing", f"registry image is not pulled: {image_ref}")
                source_head = _source_snapshot(self.repository_root)["head"]
                self.docker.validate_registry_image(
                    image_record, source_head=source_head, image_ref=image_ref
                )
                result = self._adopt_registry_image_locked(
                    state,
                    image_ref,
                    image_record,
                    source_head,
                )
            elif fresh_result is not None:
                result = fresh_result
            else:
                result = self._update_locked(state, "update")
        self.codex_prepare()
        self._finalize_legacy_runtime_reset()
        return result

    def _ensure_container(
        self, state: dict[str, Any], *, start: bool
    ) -> dict[str, Any]:
        resources = state.setdefault("resources", self._resource_records())
        c = resources.setdefault("container", self._resource_records()["container"])
        name = str(c["name"])
        existing = self.docker.inspect_container(c.get("id") or name)
        if existing is None and self._container_control():
            # The host adapter may have replaced the resident before invoking
            # this controller. Re-adopt the exact name when the old ID is
            # naturally stale; never enumerate or claim another container.
            existing = self.docker.inspect_container(name)
        if existing is not None:
            labels = (
                existing.get("Config", {}).get("Labels", {})
                if isinstance(existing.get("Config"), dict)
                else {}
            )
            if labels.get("io.agent-canon.control-root-digest") != self.control_digest:
                raise BootstrapError(
                    "shared_runtime_owned_elsewhere",
                    "the shared AgentCanon container name belongs to another control root",
                )
            self._validate_container(existing, state)
            c["id"] = _required_string(existing.get("Id"), "container.Id")
        else:
            owners = self.docker.owned_container_ids(self.control_digest)
            if len(owners) > 1:
                raise BootstrapError(
                    "multiple_owned_containers",
                    "more than one AgentCanon container is present",
                )
            if owners:
                owner_record = self.docker.inspect_container(owners[0])
                if owner_record is None:
                    raise BootstrapError(
                        "docker_readback_invalid",
                        "label-selected container disappeared before inspect",
                    )
                owner_labels = owner_record.get("Config", {}).get("Labels", {})
                if (
                    owner_labels.get("io.agent-canon.control-root-digest")
                    != self.control_digest
                ):
                    raise BootstrapError(
                        "shared_runtime_owned_elsewhere",
                        "a container with this host UID belongs to another control root",
                    )
                raise BootstrapError(
                    "multiple_owned_containers",
                    "a label-selected container has an unexpected name or state record",
                )
            image = resources.get("image", {})
            image_ref = _required_string(
                image.get("id") or image.get("tag"), "state image reference"
            )
            c["id"] = self.docker.create_container(
                name=name,
                image=image_ref,
                labels=self._labels(),
                cpus=int(self.manifest["container"]["cpus"]),
                memory_bytes=int(self.manifest["container"]["memory_bytes"]),
                pids=int(self.manifest["container"]["pids_limit"]),
                mounts=self._mounts(state.get("targets", {})),
            )
            c["state"] = "created"
            existing = self.docker.inspect_container(str(c["id"]))
            if existing is None:
                raise BootstrapError(
                    "docker_readback_invalid",
                    "created container disappeared before inspect",
                )
            self._validate_container(existing, state)
        if start:
            existing_state = (
                existing.get("State", {}) if isinstance(existing, dict) else {}
            )
            if (
                not isinstance(existing_state, dict)
                or existing_state.get("Running") is not True
            ):
                self.docker.start_container(str(c["id"]))
            self._wait_for_healthy(state, str(c["id"]))
            container_id = str(c["id"])
            try:
                final = self.docker.inspect_container(container_id)
                if final is None:
                    raise BootstrapError(
                        "docker_readback_invalid",
                        "container disappeared during final readback",
                    )
                self._validate_container(final, state)
                self._verify_registry_mount(state, container_id)
            except BootstrapError:
                try:
                    self._stop_owned_container(state)
                finally:
                    c["id"] = container_id
                    c["state"] = "quarantined"
                raise
            c["state"] = "running"
        return c

    def _start_locked(self) -> dict[str, Any]:
        """Start while the caller owns the lifecycle lock."""
        with contextlib.nullcontext():
            state = self._read_state()
            if state["state"] == "uninstalled":
                raise BootstrapError(
                    "not_installed", "install must complete before start"
                )
            before = state["state"]
            try:
                self._ensure_container(state, start=True)
            except BootstrapError:
                self._write_state(state)
                raise
            state["state"] = "ready"
            self._write_state(state)
            return self._result(
                self._receipt(
                    "start",
                    "ok",
                    "ready",
                    before=before,
                    after="ready",
                    details={"container_id": state["resources"]["container"]["id"]},
                    state=state,
                )
            )

    def start(self) -> dict[str, Any]:
        """Create or adopt exactly one constrained healthy container."""
        with self.locked():
            return self._start_locked()

    def status(self) -> dict[str, Any]:
        """Return state plus Docker inspect readback."""
        with self.locked():
            state = self._read_state(allow_manifest_drift=True)
            manifest_drift = state.get("manifest_digest") != self.manifest_digest
            if manifest_drift:
                container = state.get("resources", {}).get("container", {})
                identifier = container.get("id") or container.get("name")
                inspected = (
                    self.docker.inspect_container(str(identifier))
                    if identifier
                    else None
                )
                if inspected is not None:
                    self._validate_cleanup_resource(inspected, state, "container")
            else:
                inspected = (
                    self._container_inspect(state, require_running=False)
                    if state.get("resources")
                    else None
                )
            return self._result(
                self._receipt(
                    "status",
                    "ok",
                    "status",
                    before=state["state"],
                    after=state["state"],
                    details={
                        "state": self._state_summary(state),
                        "docker_container": self._container_summary(inspected),
                        "runtime_bytes": _dir_bytes(self.paths.runtime_root),
                        "manifest_drift": manifest_drift,
                        "source_sync": self._read_source_sync_state(),
                    },
                    state=state,
                )
            )

    def _stop_owned_container(self, state: dict[str, Any]) -> None:
        c = state.get("resources", {}).get("container", {})
        cid = c.get("id")
        if not cid or not c.get("owned", True):
            return
        inspected = self.docker.inspect_container(str(cid))
        if inspected is not None:
            self._validate_cleanup_resource(inspected, state, "container")
        if inspected is not None and inspected.get("State", {}).get("Running") is True:
            self.docker.stop_container(
                str(cid),
                timeout=int(self.manifest["container"]["termination_grace_seconds"]),
            )
        if self.docker.inspect_container(str(cid)) is not None:
            self.docker.remove_container(str(cid))
        if self.docker.inspect_container(str(cid)) is not None:
            raise BootstrapError(
                "old_generation_stop_failed", "owned container remains after removal"
            )
        c["state"], c["id"] = "absent", None

    def _clear_exchange_in_container(self, state: dict[str, Any]) -> None:
        """Remove user-namespace-owned exchange children before container stop."""
        container = state.get("resources", {}).get("container", {})
        # A missing state ID means there is no owned container to clean. Do not
        # inspect the manifest name: another control root may own that name.
        identifier = container.get("id")
        if not identifier:
            return
        inspected = self.docker.inspect_container(str(identifier))
        if inspected is None:
            return
        self._validate_cleanup_resource(inspected, state, "container")
        if inspected.get("State", {}).get("Running") is not True:
            self.docker.start_container(str(identifier))
            self._wait_for_healthy(state, str(identifier))
        result = self.docker.exec_container(
            str(identifier),
            cwd=CONTAINER_RUNTIME_DESTINATION,
            argv=[
                "python3",
                "/usr/local/share/agent-canon/runtime/tools/runtime/archive/"
                "runtime_exchange_cleanup.py",
            ],
        )
        if result.returncode != 0:
            stderr = _redact_output(result.stderr or "")
            stdout = _redact_output(result.stdout or "")
            raise BootstrapError(
                "exchange_cleanup_failed",
                f"container exchange cleanup exited with {result.returncode}",
                evidence={
                    "exit": result.returncode,
                    "stderr_digest": sha256_text(stderr),
                    "stderr_preview": _bounded_output_preview(stderr, 1000),
                    "stdout_digest": sha256_text(stdout),
                    "stdout_preview": _bounded_output_preview(stdout, 1000),
                },
            )

    def _remove_exchange(self) -> None:
        """Remove the dedicated container exchange after the container is absent."""
        exchange = self.paths.container_runtime
        if exchange.is_symlink():
            raise BootstrapError(
                "symlink_path_rejected", "container runtime exchange is a symlink"
            )
        if exchange.exists():
            if not exchange.is_dir():
                raise BootstrapError(
                    "exchange_directory_invalid",
                    "container runtime exchange is not a directory",
                )
            shutil.rmtree(exchange)

    def stop(self) -> dict[str, Any]:
        """Stop and remove only the owned container after admission drains."""
        with self.locked():
            state = self._read_state(allow_manifest_drift=True)
            before = state["state"]
            if state.get("active_task_count", 0):
                raise BootstrapError(
                    "active_tasks", "cannot stop while tasks are active"
                )
            self._stop_owned_container(state)
            state["state"] = "stopped" if before != "uninstalled" else before
            self._write_state(state)
            return self._result(
                self._receipt(
                    "stop",
                    "ok",
                    "stopped",
                    before=before,
                    after=state["state"],
                    state=state,
                )
            )

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
            if not self._container_control():
                raise BootstrapError(
                    "target_host_root_unexpected",
                    "host target metadata is only valid in container control",
                )
            if not isinstance(host_root, str) or not host_root.startswith("/"):
                raise BootstrapError(
                    "target_host_root_invalid",
                    "host target root must be an absolute path",
                )
            if any(character in host_root for character in "\x00\n\r\t\\\""):
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
                raise BootstrapError("mutation_capability_invalid", "capability fields are invalid")
            allowed = mutation_capability.get("allowed_paths")
            if not isinstance(allowed, list) or not allowed:
                raise BootstrapError("mutation_capability_invalid", "allowed_paths is required")
            normalized: list[str] = []
            for value in allowed:
                if not isinstance(value, str):
                    raise BootstrapError("mutation_capability_invalid", "allowed path is not text")
                relative = Path(value)
                if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                    raise BootstrapError("mutation_capability_invalid", f"unsafe allowed path: {value}")
                _existing_path_no_symlink(canonical / relative, field="mutation allowed path")
                normalized.append(relative.as_posix())
            for field in ("purpose", "authority"):
                if not isinstance(mutation_capability.get(field), str) or not mutation_capability[field].strip():
                    raise BootstrapError("mutation_capability_invalid", field)
            record.update(
                {
                    "allowed_paths": sorted(set(normalized)),
                    "purpose": mutation_capability["purpose"],
                    "authority": mutation_capability["authority"],
                }
            )
        elif mutation_capability is not None:
            raise BootstrapError("mutation_capability_unexpected", "read-only target cannot accept mutation capability")
        return record

    def _prune_stale_targets(self, state: dict[str, Any]) -> list[str]:
        """Remove only target records whose derived source is unavailable.

        Host records use ``host_root`` when present; the resident controller
        must instead inspect the mounted ``root`` path because host paths are
        intentionally outside its namespace.  Malformed records are left for
        the normal manifest/readback validators to reject.
        """
        raw_targets = state.get("targets")
        if not isinstance(raw_targets, Mapping):
            return []
        targets = dict(raw_targets)
        stale: list[str] = []
        for digest, record in targets.items():
            if not isinstance(digest, str) or not isinstance(record, Mapping):
                continue
            source_value = record.get("root") if self._container_control() else record.get("host_root", record.get("root"))
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
        destination = (
            self.paths.container_runtime / "mounts.toml"
            if self._container_control()
            else self.paths.mounts
        )
        _atomic_bytes(destination, "\n".join(lines).encode("utf-8"), mode=0o444)

    def _write_mount_manifest(self, state: Mapping[str, Any]) -> None:
        """Write the strict host-readable target mount manifest."""
        path = (
            self.paths.container_runtime / "mounts.tsv"
            if self._container_control()
            else self.paths.runtime_root / "mounts.tsv"
        )
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
                if any(char in source or char in str(digest) for char in ("\t", "\n", "\r")):
                    raise BootstrapError("mount_manifest_invalid", "target mount contains a control character")
                if mode != "read-only":
                    raise BootstrapError(
                        "mount_manifest_invalid",
                        "only read-only targets may be projected into the resident mount manifest",
                    )
                lines.append(f"target\t{digest}\t{source}\t/targets/{digest}\tread-only")
        _atomic_bytes(
            path,
            ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8"),
            mode=0o444 if self._container_control() else 0o600,
        )

    def target_add(
        self,
        root: Path,
        mode: str = "read-only",
        *,
        health_ok: bool = True,
        readback_ok: bool = True,
        stop_ok: bool = True,
        mutation_capability: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Commit a multi-target mount generation or quarantine it on failure."""
        candidate_target = self._target_record(root, mode, mutation_capability)
        with self.locked():
            state = self._read_state()
            if state.get("active_task_count", 0):
                raise BootstrapError(
                    "mount_update_blocked", "active tasks prevent generation update"
                )
            if state.get("state") not in {"ready", "stopped", "installed"}:
                raise BootstrapError(
                    "runtime_unavailable",
                    f"target updates require idle runtime, got {state.get('state')}",
                )
            stale = self._prune_stale_targets(state)
            if stale:
                self._write_mounts(state)
                self._write_mount_manifest(state)
                self._write_state(state)
            before, old_generation = state["state"], state.get("current_generation")
            old_targets = dict(state.get("targets", {}))
            existing_target = old_targets.get(candidate_target["digest"])
            if (
                not stale
                and health_ok
                and readback_ok
                and stop_ok
                and isinstance(existing_target, Mapping)
                and self._same_target_record(existing_target, candidate_target)
            ):
                try:
                    if self._container_inspect(state, require_running=True) is not None:
                        return self._result(
                            self._receipt(
                                "target_add",
                                "ok",
                                "target_unchanged",
                                before=before,
                                after=before,
                                details={"target": dict(existing_target), "changed": False},
                                state=state,
                            )
                        )
                except BootstrapError:
                    # A valid registry entry with a missing/drifted resident
                    # still needs the normal replacement path below.
                    pass
            old_container = dict(state.get("resources", {}).get("container", {}))
            old_registry = _safe_read(self.paths.mounts, field="mount registry")
            candidate_targets = dict(old_targets)
            candidate_targets[candidate_target["digest"]] = candidate_target
            counter = int(state.get("generation_counter", 0)) + 1
            generation = f"generation-{counter:04d}"
            path = self.paths.generations / generation
            _ensure_directory(path)
            candidate = {
                "id": generation,
                "state": "candidate",
                "targets": candidate_targets,
                "health": health_ok,
                "mount_readback": readback_ok,
                "created_at": _now(),
            }
            _atomic_json(path / "manifest.json", candidate)
            state["state"] = "maintenance_pending"
            try:
                if not stop_ok:
                    raise BootstrapError(
                        "old_generation_stop_failed",
                        "old generation did not reach absence",
                    )
                self._stop_owned_container(state)
                state["targets"] = candidate_targets
                state["generation_counter"] = counter
                state["generations"][generation] = candidate
                # The registry is a bind-mounted file. Write the candidate
                # inode before create; replacing it after create would leave
                # the container attached to the old inode.
                self._write_mounts(state)
                if not health_ok or not readback_ok:
                    raise BootstrapError(
                        "candidate_generation_unhealthy"
                        if not health_ok
                        else "mount_readback_failed",
                        "candidate generation failed health or mount readback",
                    )
                self._ensure_container(state, start=True)
                candidate["state"] = "current"
                _atomic_json(path / "manifest.json", candidate)
                if old_generation and old_generation in state["generations"]:
                    state["generations"][old_generation]["state"] = "rollback"
                (
                    state["rollback_generation"],
                    state["current_generation"],
                    state["state"],
                ) = old_generation, generation, "ready"
                self._verify_registry_mount(
                    state, str(state["resources"]["container"]["id"])
                )
                self._write_state(state)
                return self._result(
                    self._receipt(
                        "target_add",
                        "ok",
                        "generation_active",
                        before=before,
                        after="ready",
                        details={
                            "candidate_generation": generation,
                            "old_generation": old_generation,
                            "targets": candidate_targets,
                        },
                        state=state,
                    )
                )
            except BootstrapError as exc:
                candidate.update({"state": "quarantined", "failure": exc.code})
                _atomic_json(path / "manifest.json", candidate)
                state["generations"][generation] = candidate
                candidate_id = state.get("resources", {}).get("container", {}).get("id")
                candidate_cleanup: dict[str, Any] = {"stopped": False, "removed": False}
                if candidate_id and candidate_id != old_container.get("id"):
                    try:
                        self._stop_owned_container(state)
                        candidate_cleanup["removed"] = True
                    except BootstrapError as cleanup_error:
                        candidate_cleanup["error"] = cleanup_error.code
                registry_restored = False
                try:
                    _atomic_bytes(self.paths.mounts, old_registry, mode=0o444)
                    registry_restored = True
                except BootstrapError as restore_error:
                    candidate_cleanup["registry_restore_error"] = restore_error.code
                state["targets"] = old_targets
                state["current_generation"] = old_generation
                state["resources"]["container"] = old_container
                restored = False
                if registry_restored and old_generation and old_targets:
                    try:
                        state["state"] = "maintenance_pending"
                        self._ensure_container(state, start=True)
                        restored = True
                    except BootstrapError:
                        restored = False
                state["state"] = (
                    before
                    if registry_restored and (restored or not old_generation)
                    else "runtime_unavailable"
                )
                self._write_state(state)
                if exc.code in {
                    "candidate_generation_unhealthy",
                    "mount_readback_failed",
                }:
                    raise BootstrapError(
                        exc.code,
                        "candidate quarantined; previous generation restored",
                        evidence={
                            "candidate_generation": generation,
                            "current_generation": old_generation,
                            "restored": restored,
                            "registry_restored": registry_restored,
                            "candidate_cleanup": candidate_cleanup,
                        },
                    ) from exc
                raise

    def _admit_task_locked(
        self, state: dict[str, Any], task_id: str, *, target_root: Path | None = None
    ) -> dict[str, Any]:
        task_id = _slug(task_id)
        if state.get("state") not in ADMISSION_STATES:
            raise BootstrapError(
                "task_admission_closed", f"runtime state is {state.get('state')}"
            )
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
        if target and self._container_control():
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
        record = {
            "id": task_id,
            "state": "active",
            "generation": state.get("current_generation"),
            "target": target,
            "started_at": _now(),
            "pinned": True,
        }
        state.setdefault("tasks", {})[task_id] = record
        state["active_task_count"] = int(state.get("active_task_count", 0)) + 1
        state["state"] = "running"
        self._write_state(state)
        return record

    def admit_task(
        self, task_id: str, *, target_root: Path | None = None
    ) -> dict[str, Any]:
        """Atomically reserve one task slot and its target generation."""
        with self.locked():
            state = self._read_state()
            before = state["state"]
            record = self._admit_task_locked(state, task_id, target_root=target_root)
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
            task = self._release_task_locked(state, task_id, outcome=outcome)
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

    def _materialize_skill_view(self) -> dict[str, Any]:
        """Generate the ignored project-local skill view before image/link use."""
        if self._container_control():
            self._validate_source_adapters()
            # The resident owns the materializer write.  Generate into the
            # writable container-runtime exchange, then let the host adapter
            # export that exact generated tree to the live checkout.  The
            # source image remains read-only and the host never imports the
            # materializer's Python dependencies.
            staging = self.paths.container_runtime / "skill-projection"
            if staging.is_symlink():
                raise BootstrapError(
                    "skill_projection_path_invalid",
                    "skill projection staging path is a symlink",
                )
            if staging.exists():
                if not staging.is_dir():
                    raise BootstrapError(
                        "skill_projection_path_invalid",
                        "skill projection staging path is not a directory",
                    )
                shutil.rmtree(staging)
            staging.mkdir(parents=True, exist_ok=True)
            try:
                from tools.agent.skills.skill_shim_materializer import materialize

                previous_image_build = os.environ.get("AGENT_CANON_IMAGE_BUILD")
                os.environ["AGENT_CANON_IMAGE_BUILD"] = "1"
                try:
                    materializer = materialize(
                        self.repository_root,
                        all_skills=True,
                        image_build=True,
                        output_root=staging,
                    )
                finally:
                    if previous_image_build is None:
                        os.environ.pop("AGENT_CANON_IMAGE_BUILD", None)
                    else:
                        os.environ["AGENT_CANON_IMAGE_BUILD"] = previous_image_build
            except Exception as exc:  # noqa: BLE001 - translate owner failure once
                raise BootstrapError(
                    "skill_view_materialization_failed", str(exc)
                ) from exc
            return {
                "mode": "resident-exchange",
                "materialized": True,
                "readback_digest": materializer.get("readback_digest"),
            }
        tools_root = self.repository_root / "tools" / "agent_tools"
        if str(tools_root) not in sys.path:
            sys.path.insert(0, str(tools_root))
        from tools.agent.skills.skill_shim_materializer import materialize

        previous = os.environ.get("AGENT_CANON_PARENT_ROOT")
        os.environ["AGENT_CANON_PARENT_ROOT"] = str(self.repository_root)
        try:
            return materialize(self.repository_root, all_skills=True)
        except Exception as exc:  # noqa: BLE001 - translate owner failure once
            raise BootstrapError("skill_view_materialization_failed", str(exc)) from exc
        finally:
            if previous is None:
                os.environ.pop("AGENT_CANON_PARENT_ROOT", None)
            else:
                os.environ["AGENT_CANON_PARENT_ROOT"] = previous

    def _validate_source_adapters(self) -> None:
        """Read back the ignored personal skill view before runtime convergence."""
        source = self.repository_root / ".codex" / "personal"
        skills = source / "skills"
        if source.is_symlink() or not source.is_dir() or skills.is_symlink() or not skills.is_dir():
            raise BootstrapError(
                "source_adapters_invalid",
                "ignored .codex/personal/skills is missing or not regular",
            )
        skill_files = sorted(skills.glob("*/SKILL.md"))
        if not skill_files or any(path.is_symlink() or not path.is_file() for path in skill_files):
            raise BootstrapError("source_adapters_invalid", "personal skill adapters failed readback")

    def _managed_links(self) -> list[dict[str, str]]:
        projection_root: Path | None = None
        if self._container_control():
            raw_projection_root = os.environ.get("AGENT_CANON_HOST_INSTALL_ROOT", "").strip()
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

        entries: list[dict[str, str]] = []
        for surface, source in (
            ("skills", self.repository_root / ".codex" / "personal" / "skills"),
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
                return self.paths.codex_home / str(entry["surface"]) / str(entry["relative"])

            desired_targets = {
                str(link_target(entry))
                for entry in desired
            }
            previous_entries: list[Mapping[str, Any]] = []
            previous_manifest = self.paths.codex_home / "manifest.json"
            if previous_manifest.is_file() and not previous_manifest.is_symlink():
                try:
                    previous_payload = json.loads(previous_manifest.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise BootstrapError("codex_manifest_invalid", "runtime-local Codex manifest is invalid") from exc
                raw_previous = previous_payload.get("links", []) if isinstance(previous_payload, dict) else []
                if isinstance(raw_previous, list):
                    previous_entries = [entry for entry in raw_previous if isinstance(entry, dict)]
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
                        os.environ.get("AGENT_CANON_HOST_INSTALL_ROOT", self.repository_root)
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
        """Install only manifest-managed links into isolated ``CODEX_HOME``."""
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
        env["AGENT_CANON_CONTROL_PARENT_ROOT"] = str(
            self.paths.control_parent_root
        )
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
            target_digest = (
                os.environ.get("AGENT_CANON_TARGET_DIGEST")
                if self._container_control()
                else target["digest"]
            )
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
            self._admit_task_locked(state, task_id, target_root=root)
            try:
                c = (
                    {"id": os.environ.get("AGENT_CANON_CONTAINER_ID")}
                    if self._container_control()
                    else self._ensure_container(state, start=True)
                )
                if not c.get("id"):
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
                }
                environment.update(extra_environment or {})
                result = self.docker.exec_container(
                    str(c["id"]),
                    cwd=f"/targets/{target['digest']}",
                    argv=list(argv),
                    environment=environment,
                    embedding_exchange=self.paths.container_runtime,
                    embedding_allowed_endpoints={
                        value.strip()
                        for value in os.environ.get(
                            "AGENT_CANON_EMBEDDING_ALLOWED_ENDPOINTS", ""
                        ).split(",")
                        if value.strip()
                    },
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
                        if not any(path == item or path.startswith(item + "/") for item in allowed)
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
                self._release_task_locked(state, task_id)

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
                requested = self._target_record(root, "read-only")
                requested_digest = (
                    os.environ.get("AGENT_CANON_TARGET_DIGEST")
                    if self._container_control()
                    else requested["digest"]
                )
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
                raise BootstrapError("tool_catalog_invalid", "cannot resolve tool output capability") from exc
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

    def template_export(
        self, root: Path, profile: str, output: str
    ) -> dict[str, Any]:
        """Export a template profile through the resident tool-container catalog."""
        _slug(profile)
        relative = Path(output)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise BootstrapError("template_output_invalid", "output must be runtime-relative")
        target = self._target_record(root, "read-only")
        host_output = self.paths.runtime_root / "template-exports" / relative
        if host_output.exists() or host_output.is_symlink():
            raise BootstrapError("template_output_exists", str(host_output))
        container_output = f"{CONTAINER_RUNTIME_DESTINATION}/template-exports/{relative.as_posix()}"
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
        _slug(run_id)
        source = _existing_no_symlink(root, field="eval source root")
        spool = self.paths.spool / run_id
        if spool.exists():
            if spool.is_symlink():
                raise BootstrapError("symlink_path_rejected", f"eval spool is a symlink: {spool}")
            raise BootstrapError("eval_spool_exists", f"eval spool already exists: {run_id}")
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
            "agent_canon_commit": (
                os.environ.get("AGENT_CANON_SOURCE_HEAD")
                if self._container_control()
                else _source_snapshot(self.repository_root)["head"]
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
                raise BootstrapError("target_not_registered", "eval root is not registered")
            if registered.get("mode") != "read-only":
                raise BootstrapError("eval_target_not_read_only", "eval root is not mounted read-only")
            self._admit_task_locked(state, task_id, target_root=source)
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
                container = (
                    {"id": os.environ.get("AGENT_CANON_CONTAINER_ID")}
                    if self._container_control()
                    else self._ensure_container(state, start=True)
                )
                if not container.get("id"):
                    raise BootstrapError(
                        "container_control_missing_identity",
                        "resident container identity was not provided",
                    )
                image = state.get("resources", {}).get("image", {})
                collection["tool_image_digest"] = image.get("id")
                target_path = f"/targets/{target['digest']}"
                canon_root = "/usr/local/share/agent-canon/runtime"
                container_runtime = "/var/lib/agent-canon/exchange"
                exchange_runtime = (
                    f"{container_runtime}/tasks/{task_id}/{exchange_nonce}"
                )
                command = [
                    "python3",
                    "/usr/local/share/agent-canon/runtime/eval/producers/run_accumulated_agent_evals.py",
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
                    "--prompt-eval-manifest",
                    f"{canon_root}/eval/definitions/skill_workflow_prompt_eval.toml",
                ]
                result = self.docker.exec_container(
                    str(container["id"]),
                    cwd=canon_root,
                    argv=command,
                    environment={
                        "AGENT_CANON_TARGET_ROOT": target_path,
                        "AGENT_CANON_TASK_ROOT": target_path,
                        "GIT_CONFIG_COUNT": "1",
                        "GIT_CONFIG_KEY_0": "safe.directory",
                        "GIT_CONFIG_VALUE_0": target_path,
                    },
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
                elif result.returncode != 0 or any(item["status"] != "pass" for item in matrix):
                    collection["status"] = "failed"
                    collection["failure"] = "eval_producer_failed"
                else:
                    collection["status"] = "collected"
                # The container writes only into the mounted exchange. Move
                # that bundle to host spool before releasing task admission.
                eval_export = spool / "eval-results"
                log_export = spool / "producer-logs"
                self.docker.copy_from_container(
                    str(container["id"]),
                    source=f"{exchange_runtime}/eval-results",
                    destination=eval_export,
                    allowed_root=self.paths.spool,
                )
                self.docker.copy_from_container(
                    str(container["id"]),
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
                state_quota = int(
                    self.manifest["container"]["task_state_quota_bytes"]
                )
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
                task_outcome = "completed" if collection["status"] == "collected" else "failed"
                if task_outcome != "completed":
                    raise BootstrapError(
                        str(collection.get("failure", "eval_failed")),
                        "eval producer collection failed; spool retained",
                        evidence={
                            "spool": str(spool),
                            "collection": str(spool / "collection.json"),
                            "producer_matrix": matrix,
                            "source_tree_unchanged": collection["source_tree_unchanged"],
                            "exit": result.returncode,
                        },
                    )
                if exchange.exists() and not exchange.is_symlink():
                    shutil.rmtree(exchange)
                released = self._release_task_locked(state, task_id, outcome=task_outcome)
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
                    collection["failure"] = collection.get("failure", "eval_runtime_failed")
                    collection["source_tree_unchanged"] = False
                    _atomic_json(spool / "collection.json", collection)
                raise
            finally:
                if state.get("tasks", {}).get(task_id, {}).get("state") == "active":
                    self._release_task_locked(state, task_id, outcome=task_outcome)

    def eval_sync(self, run_id: str) -> dict[str, Any]:
        """Prepare one retained eval spool for the Host archive adapter.

        The resident validates the collection and writes only the body-free
        request consumed by the host shell.  Credentialed Git operations and
        the operational archive checkout are never reachable from this
        container-side method.
        """
        return self.eval_sync_prepare(run_id)

    def eval_sync_prepare(self, run_id: str) -> dict[str, Any]:
        """Prepare a body-free eval publication request for the Host adapter.

        The resident validates the collection and records only fixed metadata.
        The credentialed archive clone, Git network, and publication transaction
        remain exclusively on the host side of the bootstrap boundary.
        """
        _slug(run_id)
        spool = self.paths.spool / run_id
        if not spool.is_dir() or spool.is_symlink():
            raise BootstrapError("eval_spool_missing", f"eval spool does not exist: {run_id}")
        collection_path = spool / "collection.json"
        try:
            collection = json.loads(
                _safe_read(collection_path, field="eval collection").decode("utf-8")
            )
        except (BootstrapError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BootstrapError("eval_collection_invalid", f"invalid eval collection: {run_id}") from exc
        if not isinstance(collection, dict) or collection.get("run_id") != run_id:
            raise BootstrapError("eval_collection_invalid", "eval collection run id mismatch")
        if (
            collection.get("status") != "collected"
            or collection.get("source_tree_unchanged") is not True
        ):
            raise BootstrapError(
                "eval_collection_failed",
                "only a successful source-unchanged collection may be published",
            )
        with self.locked():
            state = self._read_state(allow_manifest_drift=True)
        if collection.get("manifest_digest") != state.get("manifest_digest"):
            raise BootstrapError(
                "eval_collection_generation_mismatch",
                "eval collection is not bound to the installed runtime generation",
            )
        source_root = collection.get("source_repository")
        target_digest = os.environ.get("AGENT_CANON_TARGET_DIGEST", "")
        if not isinstance(source_root, str) or not source_root.startswith("/"):
            raise BootstrapError("eval_collection_invalid", "eval source root is not absolute")
        if any(character in source_root for character in "\x00\t\n\r"):
            raise BootstrapError("eval_collection_invalid", "eval source root contains a control character")
        if not target_digest and source_root.startswith("/targets/"):
            target_digest = source_root.removeprefix("/targets/")
        if target_digest and not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", target_digest):
            raise BootstrapError("eval_collection_invalid", "eval target digest is invalid")
        request_path = spool / "sync-request.tsv"
        if request_path.is_symlink():
            raise BootstrapError("eval_sync_request_invalid", "eval sync request is a symlink")
        lines = [
            "schema\tagent-canon.eval-sync-request.v1",
            "operation\tsync",
            "execution-plane\tagentcanon_tool_container",
            f"run-id\t{run_id}",
            f"target-digest\t{target_digest}",
            f"source-root\t{source_root}",
        ]
        _atomic_bytes(request_path, ("\n".join(lines) + "\n").encode("utf-8"), mode=0o600)
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

    def rollback(self) -> dict[str, Any]:
        """Activate the last verified generation after stopping the current one."""
        with self.locked():
            state = self._read_state()
            current, rollback = (
                state.get("current_generation"),
                state.get("rollback_generation"),
            )
            if state.get("active_task_count", 0):
                raise BootstrapError(
                    "mount_update_blocked", "cannot rollback while tasks are active"
                )
            if not rollback or rollback not in state.get("generations", {}):
                raise BootstrapError(
                    "rollback_unavailable", "no verified rollback generation exists"
                )
            self._stop_owned_container(state)
            state["targets"] = state["generations"][rollback].get("targets", {})
            state["current_generation"], state["rollback_generation"] = (
                rollback,
                current,
            )
            self._ensure_container(state, start=True)
            state["generations"][rollback]["state"] = "current"
            if current and current in state["generations"]:
                state["generations"][current]["state"] = "rollback"
            state["state"] = "ready"
            self._write_mounts(state)
            self._write_state(state)
            return self._result(
                self._receipt(
                    "rollback",
                    "ok",
                    "rollback_active",
                    before="ready",
                    after="ready",
                    details={
                        "current_generation": rollback,
                        "previous_generation": current,
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
            idle_seconds = int(self.manifest["container"].get("idle_stop_seconds", 0))
            idle_age = max(0.0, time.time() - self.paths.state.stat().st_mtime)
            idle_stop = False
            if not self._container_control():
                idle_stop = bool(
                    idle_seconds
                    and idle_age >= idle_seconds
                    and not state.get("active_task_count", 0)
                    and state.get("resources", {}).get("container", {}).get("state") == "running"
                )
            current_image = state.get("resources", {}).get("image", {}).get("id")
            owned_images = (
                []
                if self._container_control()
                else self.docker.owned_image_ids(self.control_digest)
            )
            max_images = int(self.manifest["container"].get("max_image_generations", 2))
            stale_images = [image for image in owned_images if image != current_image][
                : max(0, len(owned_images) - max_images)
            ]
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
                "idle_stop": idle_stop,
                "stale_images": stale_images,
                "candidates": candidates,
                "preserved": {
                    "current_generation": current,
                    "rollback_generation": rollback,
                    "active_task_count": state.get("active_task_count", 0),
                    "unpublished_spool": True,
                },
                "deleted": [],
            }
            if not dry_run and (
                high_water
                or cache_high_water
                or archive_high_water
                or idle_stop
                or stale_images
            ):
                if idle_stop:
                    self._stop_owned_container(state)
                    state["state"] = "stopped"
                    details["deleted"].append("idle-container")
                if cache_high_water and not state.get("active_task_count", 0):
                    cache_root = self.paths.cache
                    for child in sorted(cache_root.iterdir()) if cache_root.is_dir() else ():
                        if child.is_symlink():
                            raise BootstrapError("symlink_path_rejected", f"cache path is a symlink: {child}")
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
                for image_id in stale_images:
                    inspected = self.docker.inspect_image(image_id)
                    if inspected is None:
                        continue
                    self.docker.validate_image(
                        inspected,
                        {
                            "io.agent-canon.runtime": "shared-v1",
                            "io.agent-canon.control-root-digest": self.control_digest,
                        },
                    )
                    self.docker.remove_image(image_id)
                    details["deleted"].append(f"image:{image_id}")
            if not dry_run and high_water:
                for key, _ in tasks:
                    path = self.paths.tasks / key
                    if path.is_symlink():
                        raise BootstrapError(
                            "symlink_path_rejected", f"task path is a symlink: {path}"
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
            if not dry_run and (
                high_water
                or cache_high_water
                or archive_high_water
                or idle_stop
                or stale_images
            ):
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

    def uninstall(self) -> dict[str, Any]:
        """Remove exact owned Docker resources and managed Codex links."""
        with self.locked():
            state = self._read_state(allow_manifest_drift=True)
            before = state["state"]
            if state.get("active_task_count", 0):
                raise BootstrapError(
                    "active_tasks", "cannot uninstall while tasks are active"
                )
            self._clear_exchange_in_container(state)
            self._stop_owned_container(state)
            self._remove_exchange()
            for entry in state.get("managed_links", []):
                target = Path(entry["target"])
                if (
                    target.is_symlink()
                    and target.resolve() == Path(entry["source"]).resolve()
                ):
                    target.unlink()
            manifest = self.paths.codex_home / "manifest.json"
            if manifest.exists() and not manifest.is_symlink():
                manifest.unlink()
            image = state.get("resources", {}).get("image", {})
            image_id = image.get("id")
            if image_id and image.get("owned"):
                inspected = self.docker.inspect_image(str(image_id))
                if inspected is not None:
                    self._validate_cleanup_resource(inspected, state, "image")
                    self.docker.remove_image(str(image_id))
                    if self.docker.inspect_image(str(image_id)) is not None:
                        raise BootstrapError(
                            "image_absence_failed", "owned image remains after removal"
                        )
            for resource in state.get("resources", {}).values():
                if resource.get("owned"):
                    resource["state"] = "absent"
            state["state"] = "uninstalled"
            self._write_state(state)
            return self._result(
                self._receipt(
                    "uninstall",
                    "ok",
                    "owned_resources_released",
                    before=before,
                    after="uninstalled",
                    details={
                        "preserved_paths": [
                            str(self.paths.state),
                            str(self.paths.owner),
                        ]
                    },
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
    plan = (
        runtime.paths.container_runtime / "rollback-plan.tsv"
        if runtime._container_control()
        else runtime.paths.runtime_root / "rollback-plan.tsv"
    )
    rollback_id = state.get("rollback_generation")
    generations = state.get("generations", {})
    if not isinstance(rollback_id, str) or not isinstance(generations, Mapping):
        if plan.exists() or plan.is_symlink():
            if plan.is_symlink():
                raise BootstrapError("rollback_plan_invalid", "rollback plan is a symlink")
            plan.unlink()
        return
    previous = generations.get(rollback_id)
    resources = state.get("resources", {})
    image = resources.get("image", {}) if isinstance(resources, Mapping) else {}
    if not isinstance(previous, Mapping):
        raise BootstrapError("rollback_plan_invalid", "rollback generation is unavailable")
    image_id = previous.get("image_id") or image.get("id")
    image_ref = previous.get("image_ref") or image.get("tag") or image_id
    if (
        not isinstance(image_id, str)
        or not image_id.startswith("sha256:")
        or not isinstance(image_ref, str)
        or not image_ref
        or any(character in image_ref for character in "\x00\t\n\r")
    ):
        raise BootstrapError("rollback_plan_invalid", "rollback image identity is incomplete")
    targets = previous.get("targets", {})
    if not isinstance(targets, Mapping):
        raise BootstrapError("rollback_plan_invalid", "rollback target snapshot is invalid")
    lines = [
        "schema\tagent-canon.rollback-plan.v1",
        f"image-id\t{image_id}",
        f"image-ref\t{image_ref}",
    ]
    for digest, record in sorted(targets.items()):
        if not isinstance(digest, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", digest):
            raise BootstrapError("rollback_plan_invalid", "rollback target digest is invalid")
        if not isinstance(record, Mapping):
            raise BootstrapError("rollback_plan_invalid", "rollback target record is invalid")
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
            raise BootstrapError("rollback_plan_invalid", "rollback target mount is invalid")
        lines.append(f"mount\tmount\t{source}\t{destination}\ttrue")
    _atomic_bytes(
        plan,
        ("\n".join(lines) + "\n").encode("utf-8"),
        mode=0o444 if runtime._container_control() else 0o600,
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
    try:
        from tools.runtime.archive.log_repository_identity import (  # type: ignore[import-not-found]
            normalize_remote,
            stable_source_repository_id,
        )
    except ImportError:  # pragma: no cover - direct container script execution
        from tools.runtime.archive.log_repository_identity import normalize_remote, stable_source_repository_id

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
    if not isinstance(value, str) or not value or any(char in value for char in "\x00\n\r"):
        raise BootstrapError("invalid_exec_request", f"request field is invalid: {key}")
    return value


def _container_target_for_request(
    runtime: BootstrapRuntime, request: Mapping[str, Any]
) -> tuple[Path, Path, Path, Path]:
    """Resolve a host request to its registered container target and roots."""
    requested_target = Path(_request_string(request, "target_root")).resolve(strict=False)
    source_root = Path(_request_string(request, "source_root")).resolve(strict=False)
    environment = request.get("environment")
    if not isinstance(environment, Mapping):
        raise BootstrapError("invalid_exec_request", "request environment must be a mapping")
    host_runtime = Path(_request_string(environment, "AGENT_CANON_RUNTIME_ROOT")).resolve(strict=False)
    host_control = Path(_request_string(environment, "AGENT_CANON_CONTROL_PARENT_ROOT")).resolve(strict=False)
    digest = os.environ.get("AGENT_CANON_TARGET_DIGEST", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", digest):
        raise BootstrapError("invalid_exec_request", "registered target digest is missing")
    state = runtime._read_state()
    targets = state.get("targets", {})
    target = targets.get(digest) if isinstance(targets, Mapping) else None
    if not isinstance(target, dict):
        raise BootstrapError("target_not_registered", "request target is not registered")
    host_root_value = target.get("host_root")
    container_root = target.get("root")
    if (
        not isinstance(host_root_value, str)
        or not host_root_value
        or not isinstance(container_root, str)
        or container_root != f"/targets/{digest}"
        or requested_target != Path(host_root_value).resolve(strict=False)
    ):
        raise BootstrapError("invalid_exec_request", "request target does not match its registered mount")
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
        raise BootstrapError("invalid_exec_request", "path-valued environment must be absolute")
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
        raise BootstrapError("invalid_exec_request", "request environment must be a string-keyed mapping")
    host_target_value = _request_string(request, "target_root")
    host_target = Path(host_target_value).resolve(strict=False)
    result: dict[str, str] = {}
    for key, value in raw.items():
        if key not in TOOL_ENVIRONMENT_KEYS or not isinstance(value, str) or any(
            char in value for char in "\x00\n\r"
        ):
            raise BootstrapError("invalid_exec_request", f"request environment key is not allowlisted: {key}")
        if key in TOOL_PATH_ENVIRONMENT_KEYS:
            if key in {"AGENT_CANON_SOURCE_ROOT", "AGENT_CANON_ROOT"} and Path(value).resolve(strict=False) != source_root:
                raise BootstrapError("invalid_exec_request", f"source path does not match request: {key}")
            if key == "AGENT_CANON_RUNTIME_ROOT" and Path(value).resolve(strict=False) != host_runtime:
                raise BootstrapError("invalid_exec_request", "runtime path does not match request")
            if key == "AGENT_CANON_CONTROL_PARENT_ROOT" and Path(value).resolve(strict=False) != host_control:
                raise BootstrapError("invalid_exec_request", "control path does not match request")
            if key in {"AGENT_CANON_TARGET_ROOT", "AGENT_CANON_TASK_ROOT"} and Path(value).resolve(strict=False) != host_target:
                raise BootstrapError("invalid_exec_request", f"target path does not match request: {key}")
            if key == "AGENT_CANON_MOUNT_REGISTRY":
                result[key] = REGISTRY_DESTINATION
                continue
            if key in {"AGENT_CANON_HOOK_ARCHIVE_DIR", "AGENT_CANON_LOG_ROOT"}:
                if host_private_log is None or Path(value).resolve(strict=False) != host_private_log:
                    raise BootstrapError("invalid_exec_request", f"archive path does not match private log mount: {key}")
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
            raise BootstrapError("invalid_exec_request", "output environment is present without output_root")
    elif not isinstance(output, str) or not output:
        raise BootstrapError("invalid_exec_request", "request output_root is invalid")
    elif output_env != output:
        raise BootstrapError("invalid_exec_request", "output_root and output environment differ")
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
            state = runtime._read_state(allow_manifest_drift=True)
            if operation in {"install", "update"}:
                runtime._prune_stale_targets(state)
            before = str(state.get("state"))
            resources = state.setdefault("resources", _container_resource_state(runtime))
            resources.update(_container_resource_state(runtime))
            if operation in {"install", "update"}:
                runtime._materialize_skill_view()
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
                        state.get("current_generation") or f"generation-{previous_image_id[7:19]}"
                    )
                    current_generation = f"generation-{resources['image']['id'][7:19]}"
                    state.setdefault("generations", {})[previous_generation] = {
                        "image_id": previous_image_id,
                        "image_ref": os.environ.get("AGENT_CANON_PREVIOUS_IMAGE_REF"),
                        "state": "rollback",
                    }
                    state.setdefault("generations", {})[current_generation] = {
                        "image_id": resources["image"]["id"],
                        "image_ref": resources["image"].get("tag"),
                        "state": "current",
                    }
                    state["rollback_generation"] = previous_generation
                    state["current_generation"] = current_generation
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
            state = runtime._read_state(allow_manifest_drift=True)
            before = str(state.get("state"))
            resources = state.setdefault("resources", _container_resource_state(runtime))
            image = resources.setdefault("image", {})
            restored_image_id = os.environ.get("AGENT_CANON_RESTORE_IMAGE_ID")
            current_image_id = os.environ.get("AGENT_CANON_CURRENT_IMAGE_ID") or image.get("id")
            if not restored_image_id:
                raise BootstrapError("rollback_image_missing", "host did not provide a rollback image ID")
            previous_targets = _container_previous_target_manifest(runtime)
            current_targets = json.loads(_json(state.get("targets", {})))
            candidate_image_id = str(image.get("id") or restored_image_id)
            image.update(
                {
                    "id": restored_image_id,
                    "tag": os.environ.get("AGENT_CANON_RESTORE_IMAGE_REF", restored_image_id),
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
                "image_ref": os.environ.get("AGENT_CANON_RESTORE_IMAGE_REF", restored_image_id),
                "targets": previous_targets,
                "state": "current",
            }
            generations[rollback_generation] = {
                "image_id": current_image_id,
                "image_ref": os.environ.get("AGENT_CANON_CURRENT_IMAGE_REF", current_image_id),
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
            state = runtime._read_state(allow_manifest_drift=True)
            before = str(state.get("state"))
            resources = state.setdefault("resources", _container_resource_state(runtime))
            image = resources.setdefault("image", {})
            restored_image_id = os.environ.get("AGENT_CANON_RESTORE_IMAGE_ID")
            if not restored_image_id:
                raise BootstrapError("restore_image_missing", "host did not provide the previous image ID")
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
            state = runtime._read_state(allow_manifest_drift=True)
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
            target = runtime._target_record(
                Path(container_root or args.root),
                args.mode,
                host_root=host_root,
                host_digest=host_digest,
            )
            target_digest = host_digest or target["digest"]
            if target_digest not in state.get("targets", {}):
                raise BootstrapError("target_not_registered", "target root is not registered")
            targets = dict(state.get("targets", {}))
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
                raise BootstrapError("invalid_exec_request", "request is not JSON") from exc
            allowed = {
                "schema", "tool_id", "argv", "child_args", "source_root", "cwd",
                "cwd_policy", "target_root", "environment", "stdin", "stdout",
                "stderr", "exit", "signal", "side_effect", "output_root",
                "written_paths",
            }
            if not isinstance(request, dict) or set(request) - allowed:
                raise BootstrapError("invalid_exec_request", "request fields are invalid")
            if request.get("schema") != "agent-canon.tool-exec-request.v1":
                raise BootstrapError("invalid_exec_request", "request schema is invalid")
            tool_id = request.get("tool_id")
            child_args = request.get("child_args")
            descriptor_argv = request.get("argv")
            if (
                not isinstance(tool_id, str)
                or not SAFE_ID.fullmatch(tool_id)
                or not isinstance(child_args, list)
                or any(not isinstance(item, str) or "\x00" in item for item in child_args)
                or not isinstance(descriptor_argv, list)
                or any(not isinstance(item, str) or "\x00" in item for item in descriptor_argv)
            ):
                raise BootstrapError("invalid_exec_request", "tool or argv is invalid")
            if (
                not isinstance(args.target_digest, str)
                or args.target_digest != os.environ.get("AGENT_CANON_TARGET_DIGEST")
            ):
                raise BootstrapError("invalid_exec_request", "target digest handoff is invalid")
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
                    Path(os.environ["AGENT_CANON_PRIVATE_LOG_ROOT"]).resolve(strict=False)
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
    parser.add_argument(
        "--container-control",
        action="store_true",
        help=argparse.SUPPRESS,
    )
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
    add.add_argument(
        "--mode", choices=("read-only", "explicit-target-write"), default="read-only"
    )
    add.add_argument("--mutation-capability-json")
    remove = target_sub.add_parser("remove")
    remove.add_argument("--root", required=True)
    remove.add_argument(
        "--mode", choices=("read-only", "explicit-target-write"), default="read-only"
    )
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
    """Route parsed arguments to one lifecycle operation."""
    if getattr(args, "container_control", False):
        return _container_control_run(args)
    runtime = _runtime_from_args(args)
    operation = args.operation
    if operation == "install":
        return runtime.install(image_ref=args.image_ref)
    if operation == "update":
        return runtime.update(image_ref=args.image_ref)
    if operation == "start":
        return runtime.start()
    if operation == "status":
        return runtime.status()
    if operation == "stop":
        return runtime.stop()
    if operation == "rollback":
        return runtime.rollback()
    if operation == "uninstall":
        return runtime.uninstall()
    if operation == "gc":
        return runtime.gc(dry_run=args.dry_run)
    if operation == "target" and args.target_operation == "add":
        capability = None
        if args.mutation_capability_json:
            try:
                capability = json.loads(args.mutation_capability_json)
            except json.JSONDecodeError as exc:
                raise BootstrapError("mutation_capability_invalid", "capability is not JSON") from exc
        return runtime.target_add(
            Path(args.root), args.mode, mutation_capability=capability
        )
    if operation == "exec":
        if args.request_json:
            try:
                request = json.loads(args.request_json)
            except json.JSONDecodeError as exc:
                raise BootstrapError("invalid_exec_request", "request is not JSON") from exc
            allowed = {
                "schema", "tool_id", "runtime", "argv", "child_args",
                "source_root", "cwd", "cwd_policy", "target_root", "environment",
                "stdin", "stdout", "stderr", "exit", "signal", "side_effect",
                "output_root", "written_paths",
            }
            if not isinstance(request, dict) or set(request) - allowed:
                raise BootstrapError("invalid_exec_request", "request fields are invalid")
            if request.get("schema") != "agent-canon.tool-exec-request.v1":
                raise BootstrapError("invalid_exec_request", "request schema is invalid")
            tool_id = request.get("tool_id")
            target_root = request.get("target_root")
            child_args = request.get("child_args")
            if (
                not isinstance(tool_id, str)
                or not isinstance(target_root, str)
                or not isinstance(child_args, list)
                or any(not isinstance(item, str) or "\x00" in item for item in child_args)
            ):
                raise BootstrapError("invalid_exec_request", "tool, target, or argv is invalid")
            return runtime.tool_run(tool_id, child_args, root=Path(target_root))
        command = list(args.command)
        command = command[1:] if command and command[0] == "--" else command
        if not command:
            raise BootstrapError("argv_required", "exec requires argv after --")
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
        return runtime.template_export(
            Path(args.root), args.profile, args.output
        )
    if operation == "codex":
        if args.codex_operation == "prepare":
            return runtime.codex_prepare()
        if args.codex_operation == "launch":
            return runtime.codex_launch(Path(args.project_root))
        if args.project_root_shorthand:
            return runtime.codex_launch(Path(args.project_root_shorthand))
    if operation == "eval" and args.eval_operation == "collect":
        return runtime.eval_collect(Path(args.root), args.run_id)
    if operation == "eval" and args.eval_operation == "sync":
        return runtime.eval_sync(args.run_id)
    if operation == "task" and args.task_operation == "admit":
        return runtime.admit_task(
            args.task_id, target_root=Path(args.root) if args.root else None
        )
    if operation == "task" and args.task_operation == "release":
        return runtime.release_task(args.task_id, outcome=args.outcome)
    raise BootstrapError(
        "unsupported_operation", f"unsupported bootstrap operation: {operation}"
    )


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
