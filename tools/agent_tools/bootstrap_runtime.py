#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Owns typed Host bootstrap and the shared AgentCanon tool container without implicit source writes.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared runtime design
# downstream implementation ../../bootstrap.sh fixed host entrypoint
# downstream implementation ../../tests/bootstrap/test_bootstrap_runtime.py lifecycle validation
# @dependency-end
"""Host control plane for the AgentCanon tool runtime.

DockerAdapter is the only owner of Docker and accepts argv arrays only.
BootstrapRuntime owns durable state and performs state/path readback under an
external lifecycle lock. A successful Docker command is not accepted until
inspect returns the expected ID, labels, health, mounts, and resource limits.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import fcntl
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
REGISTRY_DESTINATION = "/var/lib/agent-canon/mount-registry.toml"
REQUIRED_LABELS = frozenset(
    {
        "io.agent-canon.runtime=shared-v1",
        "io.agent-canon.owner-uid",
        "io.agent-canon.control-root-digest",
    }
)
ADMISSION_STATES = frozenset({"ready", "running"})
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
MAX_RECEIPT_IO_BYTES = 512
MAX_EMBEDDING_RESPONSE_BYTES = 16 * 1024 * 1024
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


def _image_input_digest(repository_root: Path) -> str:
    """Bind the image identity to every admitted repository build input."""
    roots = (
        repository_root / ".dockerignore",
        repository_root / "bootstrap" / "container",
        repository_root / "tools",
        repository_root / "agents",
        repository_root / "documents" / "runtime",
        repository_root / "rust" / "agent-canon",
    )
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
            continue
        for path in root.rglob("*"):
            relative_parts = path.relative_to(repository_root).parts
            if "target" in relative_parts or "__pycache__" in relative_parts:
                continue
            if (path.is_file() or path.is_symlink()) and path.suffix != ".pyc":
                files.append(path)
    digest = hashlib.sha256()
    for path in sorted(files):
        relative = path.relative_to(repository_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        status = path.lstat()
        digest.update(f"{stat.S_IMODE(status.st_mode):04o}".encode("ascii"))
        digest.update(b"\0")
        payload = (
            os.readlink(path).encode("utf-8") if path.is_symlink() else path.read_bytes()
        )
        digest.update(hashlib.sha256(payload).digest())
        digest.update(b"\0")
    return digest.hexdigest()


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
        bounded = redacted[:MAX_RECEIPT_IO_BYTES]
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


def validate_roots(control_parent_root: Path, runtime_root: Path) -> tuple[Path, Path]:
    """Validate explicit roots; effective host UID 0 is intentionally allowed."""
    control = _existing_no_symlink(
        Path(control_parent_root), field="control-parent-root"
    )
    runtime = _validate_new_path(
        Path(runtime_root), field="runtime-root", beneath=control
    )
    if runtime == control:
        raise BootstrapError(
            "runtime_root_escape", "runtime root must be a child of control root"
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
    path = explicit or (repository_root / "bootstrap" / "manifest.toml")
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
    uid, gid = (
        int(container.get("runtime_uid", 1000)),
        int(container.get("runtime_gid", 1000)),
    )
    if uid <= 0 or gid <= 0:
        raise BootstrapError(
            "manifest_invalid", "container runtime UID/GID must be nonzero"
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
        self, argv: Sequence[str], *, check: bool = True, timeout: int | None = None
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
                    "stderr_preview": stderr[:1000],
                    "stderr_truncated": len(stderr) > 1000,
                    "stdout_digest": sha256_text(stdout),
                    "stdout_preview": stdout[:1000],
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

    def ensure_image(
        self,
        *,
        repository_root: Path,
        dockerfile: Path,
        tag: str,
        labels: Mapping[str, str],
        runtime_uid: int,
        runtime_gid: int,
    ) -> dict[str, Any]:
        """Build at most one manifest-tagged image and verify its labels."""
        record = self.inspect_image(tag)
        self.last_image_created = record is None
        if record is None:
            argv = [
                self.executable,
                "build",
                "--file",
                str(dockerfile),
                "--tag",
                tag,
                "--build-arg",
                f"AGENT_CANON_RUNTIME_UID={runtime_uid}",
                "--build-arg",
                f"AGENT_CANON_RUNTIME_GID={runtime_gid}",
            ]
            for key, value in sorted(labels.items()):
                argv.extend(("--label", f"{key}={value}"))
            argv.append(str(repository_root))
            self.run(argv)
            record = self.inspect_image(tag)
        if record is None:
            raise BootstrapError(
                "docker_readback_invalid", "built image disappeared before inspect"
            )
        self.validate_image(record, labels)
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

    def owned_container_ids(self, uid: int) -> list[str]:
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
                f"label=io.agent-canon.owner-uid={uid}",
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

    def owned_image_ids(self, uid: int, control_digest: str) -> list[str]:
        """List exact image IDs owned by the shared runtime labels."""
        result = self.run(
            [
                self.executable,
                "image",
                "ls",
                "--filter",
                "label=io.agent-canon.runtime=shared-v1",
                "--filter",
                f"label=io.agent-canon.owner-uid={uid}",
                "--filter",
                f"label=io.agent-canon.control-root-digest={control_digest}",
                "--no-trunc",
                "--quiet",
            ],
            check=False,
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
        uid: int,
        gid: int,
        labels: Mapping[str, str],
        cpus: int,
        memory_bytes: int,
        pids: int,
        mounts: Sequence[Mapping[str, str]],
    ) -> str:
        """Create one constrained non-root container and return its ID."""
        argv = [
            self.executable,
            "create",
            "--name",
            name,
            "--user",
            f"{uid}:{gid}",
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
        command = [self.executable, "exec", "--workdir", cwd]
        for key, value in sorted((environment or {}).items()):
            if key not in {
                "AGENT_CANON_TARGET_ROOT",
                "AGENT_CANON_TASK_ROOT",
                "GIT_CONFIG_COUNT",
                "GIT_CONFIG_KEY_0",
                "GIT_CONFIG_VALUE_0",
            }:
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
            not source.startswith("/var/lib/agent-canon/runtime/tasks/")
            or ".." in source_path.parts
        ):
            raise BootstrapError(
                "docker_copy_rejected", f"unsafe container export: {source}"
            )
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
        return self.runtime_root / "codex-home"

    @property
    def container_runtime(self) -> Path:
        """Return the writable, credential-free container exchange directory."""
        return self.runtime_root / CONTAINER_RUNTIME_DIR


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
        control, runtime = validate_roots(Path(control_parent_root), Path(runtime_root))
        self.paths = RuntimePaths(control, runtime)
        self.repository_root = (
            repository_root or Path(__file__).resolve().parents[2]
        ).resolve()
        self.manifest_path = _manifest_path(self.repository_root, manifest_path)
        self.manifest, policy_digest = load_manifest(self.manifest_path)
        expected_platform = self.manifest["container"].get("platform")
        observed_platform = (
            "linux/amd64"
            if sys.platform.startswith("linux")
            and platform.machine().lower() in {"x86_64", "amd64"}
            else f"{sys.platform}/{platform.machine().lower()}"
        )
        if expected_platform != observed_platform:
            raise BootstrapError(
                "unsupported_platform",
                f"shared image requires {expected_platform}, observed {observed_platform}",
            )
        self.image_input_digest = _image_input_digest(self.repository_root)
        self.manifest_digest = sha256_text(f"{policy_digest}:{self.image_input_digest}")
        self.control_digest = sha256_text(str(control))
        self.uid = os.geteuid() if hasattr(os, "geteuid") else os.getuid()
        self.docker = docker or DockerAdapter(
            os.environ.get("AGENT_CANON_DOCKER", "docker"),
            timeout=int(self.manifest["container"]["task_timeout_seconds"]),
        )
        host_gid = os.getegid() if hasattr(os, "getegid") else os.getgid()
        self.container_uid = (
            self.uid
            if self.uid != 0
            else int(self.manifest["container"].get("runtime_uid", 1000))
        )
        self.container_gid = (
            host_gid
            if host_gid != 0
            else int(self.manifest["container"].get("runtime_gid", 1000))
        )

    def _ensure_layout(self) -> None:
        _ensure_directory(self.paths.runtime_root)
        self._enforce_private_directory(self.paths.runtime_root)
        for name in KNOWN_SUBDIRS:
            path = self.paths.runtime_root / name
            _ensure_directory(path)
            self._enforce_private_directory(path)
        _ensure_directory(self.paths.container_runtime, mode=0o1777)
        try:
            os.chmod(self.paths.container_runtime, 0o1777, follow_symlinks=False)
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

    def _enforce_private_directory(self, path: Path) -> None:
        """Make an owned Host control directory private and verify readback."""
        try:
            status = os.stat(path, follow_symlinks=False)
        except OSError as exc:
            raise BootstrapError(
                "runtime_directory_invalid", f"cannot inspect runtime directory: {path}"
            ) from exc
        if status.st_uid != self.uid:
            raise BootstrapError(
                "runtime_directory_owner_mismatch",
                f"runtime directory is owned by uid {status.st_uid}, expected {self.uid}",
            )
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
            "control_root_digest": self.control_digest,
            "manifest_digest": self.manifest_digest,
            "image_input_digest": self.image_input_digest,
            "owner_uid": self.uid,
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
        if (
            value.get("manifest_digest") != self.manifest_digest
            and not allow_manifest_drift
        ):
            raise BootstrapError(
                "manifest_mismatch",
                "runtime manifest digest differs from selected manifest",
            )
        return value

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
                "owner_uid": self.uid,
                "manifest_digest": state.get("manifest_digest", self.manifest_digest),
                "image_input_digest": state.get(
                    "image_input_digest", self.image_input_digest
                ),
            },
        )

    def _image_tag(self) -> str:
        return f"agent-canon-tools:{self.uid}-{self.manifest_digest[:16]}"

    def _labels(self) -> dict[str, str]:
        return {
            "io.agent-canon.runtime": "shared-v1",
            "io.agent-canon.owner-uid": str(self.uid),
            "io.agent-canon.control-root-digest": self.control_digest,
            "io.agent-canon.image-input-digest": self.image_input_digest,
        }

    def _resource_records(self) -> dict[str, Any]:
        name = str(self.manifest["container"]["name_template"]).replace(
            "<effective-uid>", str(self.uid)
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
            "owner_uid": self.uid,
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

    def _image(self, state: dict[str, Any]) -> dict[str, Any]:
        image = self.docker.ensure_image(
            repository_root=self.repository_root,
            dockerfile=self.repository_root / "bootstrap" / "container" / "Dockerfile",
            tag=self._image_tag(),
            labels=self._labels(),
            runtime_uid=self.container_uid,
            runtime_gid=self.container_gid,
        )
        image_id = _required_string(image.get("Id"), "image.Id")
        observed_input = _image_input_digest(self.repository_root)
        if observed_input != self.image_input_digest:
            if self.docker.last_image_created:
                self.docker.remove_image(image_id)
            raise BootstrapError(
                "image_input_changed",
                "repository build inputs changed during image construction",
            )
        resources = state.setdefault("resources", self._resource_records())
        previous = resources.get("image", {})
        owned = (
            bool(previous.get("owned"))
            if previous.get("id")
            else bool(self.docker.last_image_created)
        )
        resources["image"] = {
            "id": image_id,
            "tag": self._image_tag(),
            "owned": owned,
            "labels": self._labels(),
            "state": "present",
        }
        return image

    def _mounts(self, targets: Mapping[str, Mapping[str, Any]]) -> list[dict[str, str]]:
        mounts = [
            {
                "source": str(self.paths.container_runtime),
                "destination": CONTAINER_RUNTIME_DESTINATION,
                "mode": "explicit-target-write",
            },
            {
                "source": str(self.paths.mounts),
                "destination": REGISTRY_DESTINATION,
                "mode": "read-only",
            },
        ]
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
        expected_labels = resource.get("labels")
        observed_config = record.get("Config")
        observed_labels = (
            observed_config.get("Labels", {})
            if isinstance(observed_config, dict)
            else {}
        )
        required_label_keys = {
            "io.agent-canon.runtime",
            "io.agent-canon.owner-uid",
            "io.agent-canon.control-root-digest",
            "io.agent-canon.image-input-digest",
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
            or expected_labels.get("io.agent-canon.owner-uid") != str(self.uid)
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
        self,
        record: Mapping[str, Any],
        state: Mapping[str, Any],
        *,
        require_running: bool,
    ) -> None:
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
        config = record.get("Config")
        if (
            not isinstance(config, dict)
            or config.get("User") != f"{self.container_uid}:{self.container_gid}"
        ):
            raise BootstrapError(
                "docker_readback_invalid", "container UID/GID readback mismatch"
            )
        observed_id = _required_string(record.get("Id"), "container.Id")
        expected_id = state.get("resources", {}).get("container", {}).get("id")
        if expected_id and observed_id != expected_id:
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
        if require_running and state_info.get("Running") is not True:
            raise BootstrapError("container_unhealthy", "container is not running")
        health = state_info.get("Health")
        if require_running and (
            not isinstance(health, dict) or health.get("Status") != "healthy"
        ):
            raise BootstrapError(
                "container_unhealthy", "container health probe is not healthy"
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

    def _container_inspect(
        self, state: dict[str, Any], *, require_running: bool
    ) -> dict[str, Any] | None:
        c = state.get("resources", {}).get("container", {})
        identifier = c.get("id") or c.get("name")
        if not identifier:
            return None
        record = self.docker.inspect_container(str(identifier))
        if record is not None:
            self._validate_container(record, state, require_running=require_running)
        return record

    def _verify_registry_mount(
        self, state: Mapping[str, Any], container_id: str
    ) -> None:
        """Verify registry content visible through the container bind mount."""
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
            self._validate_container(inspected, state, require_running=False)
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
                self._validate_container(inspected, state, require_running=True)
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
        config = record.get("Config") if isinstance(record.get("Config"), dict) else {}
        state = record.get("State") if isinstance(record.get("State"), dict) else {}
        health = state.get("Health") if isinstance(state.get("Health"), dict) else {}
        host = (
            record.get("HostConfig")
            if isinstance(record.get("HostConfig"), dict)
            else {}
        )
        mounts = record.get("Mounts") if isinstance(record.get("Mounts"), list) else []
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
            "user": config.get("User"),
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

    def install(self) -> dict[str, Any]:
        """Build or adopt the verified image and initialize runtime state."""
        with self.locked():
            state = self._read_state(allow_manifest_drift=True)
            if state.get("manifest_digest") != self.manifest_digest:
                if state.get("state") != "uninstalled":
                    raise BootstrapError(
                        "manifest_mismatch",
                        "uninstall the previous runtime generation before installing changed inputs",
                    )
                state = self._new_state()
            before = state["state"]
            for container_id in self.docker.owned_container_ids(self.uid):
                record = self.docker.inspect_container(container_id)
                labels = (
                    record.get("Config", {}).get("Labels", {})
                    if isinstance(record, dict)
                    and isinstance(record.get("Config"), dict)
                    else {}
                )
                if labels.get("io.agent-canon.control-root-digest") != self.control_digest:
                    raise BootstrapError(
                        "shared_runtime_owned_elsewhere",
                        "the effective UID already has a shared AgentCanon runtime; use its control root",
                    )
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
            return self._result(
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

    def _ensure_container(
        self, state: dict[str, Any], *, start: bool
    ) -> dict[str, Any]:
        resources = state.setdefault("resources", self._resource_records())
        c = resources.setdefault("container", self._resource_records()["container"])
        name = str(c["name"])
        existing = self.docker.inspect_container(c.get("id") or name)
        if existing is not None:
            self._validate_container(existing, state, require_running=False)
            c["id"] = _required_string(existing.get("Id"), "container.Id")
        else:
            owners = self.docker.owned_container_ids(self.uid)
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
                uid=self.container_uid,
                gid=self.container_gid,
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
            self._validate_container(existing, state, require_running=False)
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

    def start(self) -> dict[str, Any]:
        """Create or adopt exactly one constrained healthy container."""
        with self.locked():
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
    ) -> dict[str, Any]:
        canonical = _existing_no_symlink(root, field="target root")
        if mode not in {"read-only", "explicit-target-write"}:
            raise BootstrapError(
                "invalid_target_mode", f"unsupported target mode: {mode}"
            )
        record: dict[str, Any] = {
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
        _atomic_bytes(self.paths.mounts, "\n".join(lines).encode("utf-8"), mode=0o444)

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
            before, old_generation = state["state"], state.get("current_generation")
            old_targets = dict(state.get("targets", {}))
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

    def _managed_links(self) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for surface, source in (
            ("skills", self.repository_root / "agents" / "skills"),
            ("agents", self.repository_root / ".codex" / "agents"),
            ("hooks", self.repository_root / ".codex" / "hooks"),
            ("config", self.repository_root / ".codex" / "config.toml"),
        ):
            if source.is_file():
                entries.append(
                    {
                        "surface": surface,
                        "source": str(source),
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
                                "source": str(path),
                                "relative": str(path.relative_to(source)),
                                "digest": sha256_bytes(
                                    _safe_read(path, field="Codex source")
                                ),
                            }
                        )
        return entries

    def codex_prepare(self) -> dict[str, Any]:
        """Install only manifest-managed links into isolated ``CODEX_HOME``."""
        with self.locked():
            state = self._read_state()
            _ensure_directory(self.paths.codex_home)
            links: list[dict[str, Any]] = []
            for entry in self._managed_links():
                target = self.paths.codex_home / entry["surface"] / entry["relative"]
                _ensure_directory(target.parent)
                if target.exists() or target.is_symlink():
                    if (
                        not target.is_symlink()
                        or target.resolve() != Path(entry["source"]).resolve()
                    ):
                        raise BootstrapError(
                            "skill_collision",
                            f"managed Codex target already exists: {target}",
                        )
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
                    "source_root": str(self.repository_root),
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

    def codex_launch(self, project_root: Path) -> dict[str, Any]:
        """Launch Codex with a process-local isolated home."""
        project = _existing_no_symlink(project_root, field="Codex project root")
        prepared = self.codex_prepare()
        executable = os.environ.get("AGENT_CANON_CODEX", "codex")
        env = os.environ.copy()
        env["CODEX_HOME"] = str(self.paths.codex_home)
        env["AGENT_CANON_CONTROL_PARENT_ROOT"] = str(
            self.paths.control_parent_root
        )
        env["AGENT_CANON_RUNTIME_ROOT"] = str(self.paths.runtime_root)
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

    def exec(self, root: Path, argv: Sequence[str]) -> dict[str, Any]:
        """Execute a typed argv in a registered target and collect a receipt."""
        _validate_tool_plane_argv(root, self.repository_root, argv)
        target = self._target_record(root, "read-only")
        with self.locked():
            state = self._read_state()
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
                c = self._ensure_container(state, start=True)
                result = self.docker.exec_container(
                    str(c["id"]),
                    cwd=f"/targets/{target['digest']}",
                    argv=list(argv),
                    environment={
                        "AGENT_CANON_TARGET_ROOT": f"/targets/{target['digest']}",
                        "AGENT_CANON_TASK_ROOT": f"/targets/{target['digest']}",
                        "GIT_CONFIG_COUNT": "1",
                        "GIT_CONFIG_KEY_0": "safe.directory",
                        "GIT_CONFIG_VALUE_0": f"/targets/{target['digest']}",
                    },
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
        self, catalog_id: str, argv: Sequence[str], *, root: Path | None = None
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
                target = targets.get(requested["digest"])
                if not isinstance(target, dict):
                    raise BootstrapError(
                        "target_not_registered", "tool run root is not registered"
                    )
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
        )

    def eval_collect(self, root: Path, run_id: str) -> dict[str, Any]:
        """Run every registered eval producer inside the resident tool image."""
        _slug(run_id)
        source = _existing_no_symlink(root, field="eval source root")
        spool = self.paths.runtime_root / "spool" / run_id
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
            "agent_canon_commit": _source_snapshot(self.repository_root)["head"],
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
                container = self._ensure_container(state, start=True)
                image = state.get("resources", {}).get("image", {})
                collection["tool_image_digest"] = image.get("id")
                target_path = f"/targets/{target['digest']}"
                container_runtime = "/var/lib/agent-canon/runtime"
                exchange_runtime = (
                    f"{container_runtime}/tasks/{task_id}/{exchange_nonce}"
                )
                command = [
                    "python3",
                    "/usr/local/share/agent-canon/runtime/tools/agent_tools/run_accumulated_agent_evals.py",
                    "--root",
                    target_path,
                    "--runtime-root",
                    exchange_runtime,
                    "--run-id",
                    run_id,
                    "--log-dir",
                    f"{exchange_runtime}/tasks/{run_id}/logs",
                    "--prompt-eval-manifest",
                    f"{target_path}/evidence/agent-evals/skill_workflow_prompt_eval.toml",
                ]
                result = self.docker.exec_container(
                    str(container["id"]),
                    cwd=target_path,
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
                    allowed_root=self.paths.runtime_root,
                )
                self.docker.copy_from_container(
                    str(container["id"]),
                    source=f"{exchange_runtime}/tasks/{run_id}/logs",
                    destination=log_export,
                    allowed_root=self.paths.runtime_root,
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
        """Publish one retained eval spool through the canonical Host archive adapter."""
        _slug(run_id)
        spool = self.paths.runtime_root / "spool" / run_id
        if not spool.is_dir() or spool.is_symlink():
            raise BootstrapError("eval_spool_missing", f"eval spool does not exist: {run_id}")
        collection_path = spool / "collection.json"
        try:
            collection = json.loads(_safe_read(collection_path, field="eval collection").decode("utf-8"))
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
        source = _existing_no_symlink(Path(str(collection.get("source_repository", ""))), field="eval source root")
        remote = str(self.manifest.get("archive", {}).get("remote", ""))
        if not remote:
            raise BootstrapError("archive_remote_missing", "archive remote is not configured")
        marker: dict[str, Any] = {
            "schema": "agent_canon.eval_sync.v1",
            "run_id": run_id,
            "state": "publishing",
            "spool": str(spool),
            "updated_at": _now(),
        }
        _atomic_json(spool / "sync.json", marker)
        command = [
            sys.executable,
            str(self.repository_root / "tools" / "agent_tools" / "runtime_log_archive_git.py"),
            "--source-root",
            str(source),
            "--canon-root",
            str(self.repository_root),
            "--runtime-root",
            str(self.paths.runtime_root),
            "--remote",
            remote,
            "archive-eval",
            "--spool-root",
            str(spool),
            "--run-id",
            run_id,
        ]
        try:
            result = subprocess.run(
                command,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=int(self.manifest["container"]["task_timeout_seconds"]),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            marker.update({"state": "failed", "failure": "archive_adapter_unavailable"})
            _atomic_json(spool / "sync.json", marker)
            raise BootstrapError("archive_sync_failed", "archive adapter unavailable") from exc
        stdout = _redact_output(result.stdout or "")
        stderr = _redact_output(result.stderr or "")
        sync_bytes = len(stdout.encode("utf-8")) + len(stderr.encode("utf-8"))
        log_quota = int(self.manifest["container"]["task_log_quota_bytes"])
        if log_quota > 0 and sync_bytes > log_quota:
            marker.update(
                {
                    "state": "failed",
                    "failure": "task_log_quota_exceeded",
                    "stdout_digest": sha256_text(stdout),
                    "stderr_digest": sha256_text(stderr),
                }
            )
            _atomic_json(spool / "sync.json", marker)
            raise BootstrapError(
                "task_log_quota_exceeded",
                f"archive adapter logs require {sync_bytes} bytes; quota is {log_quota}",
            )
        try:
            _atomic_bytes(spool / "sync.stdout.log", stdout.encode("utf-8"))
            _atomic_bytes(spool / "sync.stderr.log", stderr.encode("utf-8"))
        except BootstrapError:
            marker.update({"state": "failed", "failure": "archive_log_write_failed"})
            _atomic_json(spool / "sync.json", marker)
            raise
        status_match = re.search(r"RUNTIME_LOG_ARCHIVE_EVAL_STATUS=([^\n]+)", stdout)
        archive_status = status_match.group(1).strip() if status_match else "unknown"
        archive_fields: dict[str, str] = {}
        for field in ("COMMIT", "TREE", "REMOTE_REF", "BLOBS"):
            match = re.search(
                rf"RUNTIME_LOG_ARCHIVE_EVAL_{field}=([^\n]+)", stdout
            )
            archive_fields[field.lower()] = match.group(1).strip() if match else ""
        try:
            blob_identities = json.loads(archive_fields["blobs"])
        except json.JSONDecodeError:
            blob_identities = None
        archive_identity_ok = (
            bool(re.fullmatch(r"[0-9a-f]{40,64}", archive_fields["commit"]))
            and bool(re.fullmatch(r"[0-9a-f]{40,64}", archive_fields["tree"]))
            and archive_fields["remote_ref"].startswith("refs/heads/")
            and isinstance(blob_identities, dict)
            and bool(blob_identities)
            and all(
                isinstance(path, str)
                and isinstance(digest, str)
                and bool(re.fullmatch(r"[0-9a-f]{64}", digest))
                for path, digest in blob_identities.items()
            )
        )
        if (
            result.returncode != 0
            or archive_status not in {"committed", "duplicate_noop"}
            or not archive_identity_ok
        ):
            marker.update(
                {
                    "state": "failed",
                    "failure": "archive_publish_failed",
                    "adapter_exit": result.returncode,
                    "adapter_status": archive_status,
                    "archive_identity_valid": archive_identity_ok,
                    "stdout_digest": sha256_text(stdout),
                    "stderr_digest": sha256_text(stderr),
                }
            )
            _atomic_json(spool / "sync.json", marker)
            raise BootstrapError(
                "archive_sync_failed",
                "archive publication failed; spool retained",
                evidence={
                    "spool": str(spool),
                    "adapter_exit": result.returncode,
                    "adapter_status": archive_status,
                    "stdout_digest": sha256_text(stdout),
                    "stderr_digest": sha256_text(stderr),
                },
            )
        marker.update(
            {
                "state": "published",
                "adapter_exit": result.returncode,
                "adapter_status": archive_status,
                "archive_commit": archive_fields["commit"],
                "archive_tree": archive_fields["tree"],
                "remote_ref": archive_fields["remote_ref"],
                "blob_identities": blob_identities,
                "stdout_digest": sha256_text(stdout),
                "stderr_digest": sha256_text(stderr),
            }
        )
        _atomic_json(spool / "sync.json", marker)
        details = {
            "run_id": run_id,
            "status": archive_status,
            "source": str(source),
            "stdout_digest": sha256_text(stdout),
            "stderr_digest": sha256_text(stderr),
            "remote_readback": "verified",
            "archive_commit": archive_fields["commit"],
            "archive_tree": archive_fields["tree"],
            "remote_ref": archive_fields["remote_ref"],
            "blob_identities": blob_identities,
        }
        shutil.rmtree(spool)
        return self._result(
            self._receipt(
                "eval_sync",
                "ok",
                "archive_published" if archive_status == "committed" else "archive_duplicate_noop",
                before=None,
                after=None,
                details=details,
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
            cache_bytes = _dir_bytes(self.paths.runtime_root / "cache")
            cache_high_water = bool(cache_quota and cache_bytes >= cache_quota * 0.8)
            archive_quota = int(
                self.manifest["container"].get("archive_lease_quota_bytes", 0)
            )
            archive_bytes = _dir_bytes(self.paths.runtime_root / "archive")
            archive_high_water = bool(
                archive_quota and archive_bytes >= archive_quota * 0.8
            )
            idle_seconds = int(self.manifest["container"].get("idle_stop_seconds", 0))
            idle_age = max(0.0, time.time() - self.paths.state.stat().st_mtime)
            idle_stop = bool(
                idle_seconds
                and idle_age >= idle_seconds
                and not state.get("active_task_count", 0)
                and state.get("resources", {}).get("container", {}).get("state") == "running"
            )
            current_image = state.get("resources", {}).get("image", {}).get("id")
            owned_images = self.docker.owned_image_ids(
                self.uid, self.control_digest
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
                    cache_root = self.paths.runtime_root / "cache"
                    for child in sorted(cache_root.iterdir()) if cache_root.is_dir() else ():
                        if child.is_symlink():
                            raise BootstrapError("symlink_path_rejected", f"cache path is a symlink: {child}")
                        if child.is_dir():
                            shutil.rmtree(child)
                        elif child.is_file():
                            child.unlink()
                        details["deleted"].append(f"cache:{child.name}")
                if archive_high_water and not state.get("active_task_count", 0):
                    spool_root = self.paths.runtime_root / "spool"
                    spool_has_entries = bool(
                        spool_root.is_dir() and next(spool_root.iterdir(), None)
                    )
                    if spool_has_entries:
                        details["archive_cleanup_blocked_by_spool"] = True
                    else:
                        archive_root = self.paths.runtime_root / "archive"
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
                            "io.agent-canon.owner-uid": str(self.uid),
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
    return BootstrapRuntime(
        Path(args.control_parent_root),
        Path(args.runtime_root),
        repository_root=Path(args.repository_root),
        manifest_path=Path(args.manifest) if args.manifest else None,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the typed bootstrap command parser."""
    parser = argparse.ArgumentParser(description="AgentCanon shared runtime bootstrap")
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--control-parent-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--manifest")
    sub = parser.add_subparsers(dest="operation", required=True)
    for operation in ("install", "start", "status", "stop", "rollback", "uninstall"):
        sub.add_parser(operation)
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
    execute = sub.add_parser("exec")
    execute_group = execute.add_mutually_exclusive_group(required=True)
    execute_group.add_argument("--root")
    execute_group.add_argument("--request-json")
    execute.add_argument("command", nargs=argparse.REMAINDER)
    tool = sub.add_parser("tool")
    tool_sub = tool.add_subparsers(dest="tool_operation", required=True)
    tool_run = tool_sub.add_parser("run")
    tool_run.add_argument("--root")
    tool_run.add_argument("catalog_id")
    tool_run.add_argument("command", nargs=argparse.REMAINDER)
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
    runtime = _runtime_from_args(args)
    operation = args.operation
    if operation == "install":
        return runtime.install()
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
