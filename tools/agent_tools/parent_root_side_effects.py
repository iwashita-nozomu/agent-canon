#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Authenticates the selected parent repository and owns parent-local filesystem capabilities.
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md repository mutation and managed-clone authority
# downstream implementation ../bin/agent-canon bounds CLI child state
# downstream implementation ../ci/run_all_checks.sh bounds integrated CI child state and scratch
# downstream implementation ../ci/check_agent_canon_pr.sh bounds PR gate child state and scratch
# downstream implementation ../ci/agent_canon_pr_graph_selector.py bounds selector publication and graph children
# downstream implementation ../../tests/agent_tools/test_parent_root_side_effects.py verifies capabilities and authenticated child environments
# @dependency-end

"""Authenticate the parent repository and perform parent-owned effects.

The boundary is intentionally the only place where these adapters may turn a
path into a write capability.  Git identity is checked before a capability is
issued, and Linux writes use directory file descriptors rather than pathname
lookups after the check.
"""

from __future__ import annotations

import argparse
import base64
import contextvars
import errno
import fcntl
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from types import TracebackType
from typing import Iterator, Literal, TextIO, TypeGuard, cast

SCHEMA_REQUEST = "agent-canon.parent-root-attestation-request.v1"
SCHEMA_RECEIPT = "agent-canon.parent-root-attestation-receipt.v1"
SCHEMA_HANDOFF = "agent-canon.child-handoff.v1"
SCHEMA_PATH = "agent-canon.parent-owned-path-receipt.v1"
_RETIRED_SCHEMA_SIDE_EFFECT_SESSION = "agent-canon.parent-side-effect-session.v1"
_RETIRED_SCHEMA_SIDE_EFFECT_SESSION_STATE = "agent-canon.parent-side-effect-session-state.v1"
SIDE_EFFECT_PARENT_ROOT_ENV = "AGENT_CANON_SIDE_EFFECT_PARENT_ROOT"
SIDE_EFFECT_HANDOFF_ENV = "AGENT_CANON_SIDE_EFFECT_HANDOFF"
SIDE_EFFECT_REQUIRED_ENV = "AGENT_CANON_SIDE_EFFECT_SESSION_REQUIRED"
DATA_REPOSITORY_ROOT_ENV = "AGENT_CANON_DATA_REPOSITORY_ROOT"
DATA_REPOSITORY_DEV_ENV = "AGENT_CANON_DATA_REPOSITORY_DEV"
DATA_REPOSITORY_INO_ENV = "AGENT_CANON_DATA_REPOSITORY_INO"
DATA_SOURCE_ROOT_ENV = "AGENT_CANON_DATA_SOURCE_ROOT"
DATA_ROOT_ENV = "AGENT_CANON_DATA_ROOT"
_DEFAULT_TOKEN_TTL = 900
_ALLOWED_TRANSPORTS = frozenset({"parent-local-file", "stdin", "descriptor"})
_ALLOWED_STORAGE = frozenset({"parent-local-file", "pipe"})
_ALLOWED_MODES = frozenset({"0600", "pipe"})
_MARKER_FIELDS = frozenset(
    {"schema", "parent_repo_id", "topic_slug", "repo_name", "clone_path",
     "remote_url", "branch", "owner_evidence_sha256", "source_commit",
     "source_tree", "created_at", "nonce"}
)
_OWNER_FIELDS = frozenset(
    {"schema", "parent_repo_id", "physical_parent", "module_path",
     "remote_url", "observed_commit", "observed_tree", "evidence_sha256"}
)


class ParentRootReject(str, Enum):
    """Stable typed rejection reasons."""

    NONE = "none"
    ROOT_MISSING = "root_missing"
    ROOT_AMBIGUOUS = "root_ambiguous"
    ROOT_MISMATCH = "root_mismatch"
    ROOT_SPOOFED = "root_spoofed"
    MARKER_INVALID = "marker_invalid"
    MODULE_INVALID = "module_invalid"
    OWNER_EVIDENCE_INVALID = "owner_evidence_invalid"
    SYMLINK_ESCAPE = "symlink_escape"
    ROOT_RACE_DETECTED = "root_race_detected"
    HANDOFF_INVALID = "handoff_invalid"
    INPUT_INVALID = "input_invalid"
    UNSUPPORTED_PLATFORM = "unsupported_platform"


class ParentRootSideEffectError(RuntimeError):
    """Raised before an unauthenticated or unsafe side effect."""

    def __init__(self, reject: ParentRootReject, detail: str) -> None:
        self.reject = reject
        self.detail = detail
        super().__init__(f"{reject.value}: {detail}")


@dataclass(frozen=True)
class ParentRootAttestationRequest:
    """Untrusted root and identity inputs."""

    cwd: Path
    explicit_root: Path | None = None
    source_root: Path | None = None
    clone_root: Path | None = None
    topic_marker: Path | None = None
    gitmodules: Path | None = None
    owner_evidence: Path | None = None
    expected_remote: str | None = None
    expected_module_digest: str | None = None
    child_handoff_token: str | None = None
    purpose: str = "repository-side-effect"
    nonce: str = field(default_factory=lambda: secrets.token_hex(16))

    def __post_init__(self) -> None:
        if not str(self.cwd) or not self.purpose or self.purpose != self.purpose.strip():
            raise ValueError("cwd and purpose must be non-empty")
        for name in ("cwd", "explicit_root", "source_root", "clone_root",
                     "topic_marker", "gitmodules", "owner_evidence"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Path):
                object.__setattr__(self, name, Path(value))


@dataclass(frozen=True)
class ChildHandoffReceipt:
    """Validated single-use child capability metadata."""

    token_version: str
    audience: str
    parent_root: Path
    source_root: Path | None
    clone_root: Path | None
    issued_at: float
    expires_at: float
    nonce: str
    payload_sha256: str
    storage: str
    mode: str
    validation: str
    transport: str
    token: str = field(repr=False, compare=False, default="")


@dataclass(frozen=True)
class _RetiredParentSideEffectSessionReceipt:
    """Retired v1 state retained only while old on-disk data is rejected."""

    schema: str
    record_id: str
    session_id: str
    audience: str
    parent_root: Path
    issued_at: float
    expires_at: float
    nonce: str
    status: str
    state_path: Path
    attestation: "ParentRootAttestationReceipt"
    handle: str = field(repr=False, compare=False, default="")
    lease: "ParentSideEffectLease | None" = field(repr=False, compare=False, default=None)
    # v2 callers use the canonical result directly; this optional back-reference
    # keeps the legacy effect adapters source-compatible while the transport is
    # migrated to the one v2 parser/result.
    record: object | None = field(repr=False, compare=False, default=None)
    resolution: object | None = field(repr=False, compare=False, default=None)

    def close(self) -> None:
        """Release the operation lease carried by this session, if any."""
        if self.lease is not None:
            self.lease.close()


@dataclass
class ParentSideEffectLease:
    """A durable lease held while one side effect is being resolved."""

    lease_id: str
    path: Path
    lock_fd: int = field(repr=False, compare=False)
    state_path: Path = field(default=Path("."), repr=False, compare=False)
    session_lock_path: Path = field(default=Path("."), repr=False, compare=False)
    session_handle: str = field(default="", repr=False, compare=False)
    owner_thread_id: int = field(default=0, repr=False, compare=False)
    _closed: bool = field(default=False, repr=False, compare=False)

    @property
    def closed(self) -> bool:
        """Return whether this operation lease has already been released."""
        return self._closed

    def close(self) -> None:
        """Release the lock and durably remove this lease record exactly once."""
        if self._closed:
            return
        self._closed = True
        leases = _LOCAL_LEASES.get(self.session_handle)
        if leases is not None:
            _LOCAL_LEASES[self.session_handle] = [item for item in leases if item is not self]
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(self.lock_fd)
        if _physical(self.path.parent, strict=True) != self.path.parent:
            raise ParentRootSideEffectError(ParentRootReject.SYMLINK_ESCAPE, "lease parent changed")
        lease_dir_fd = os.open(
            self.path.parent,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        try:
            os.unlink(self.path.name, dir_fd=lease_dir_fd)
            os.unlink(self.path.with_suffix(".lock").name, dir_fd=lease_dir_fd)
        except FileNotFoundError:
            pass
        finally:
            os.close(lease_dir_fd)
        if self.state_path != Path(".") and self.session_lock_path != Path("."):
            update_fd = os.open(
                self.session_lock_path,
                os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
            try:
                fcntl.flock(update_fd, fcntl.LOCK_EX)
                state = _read_session_state(self.state_path)
                state["active_leases"] = len(tuple(self.path.parent.glob("*.json")))
                _atomic_private_json(self.state_path, state)
            finally:
                fcntl.flock(update_fd, fcntl.LOCK_UN)
                os.close(update_fd)


@dataclass(frozen=True)
class ParentOwnedPathReceipt:
    """A physical path and the parent identity it was opened beneath."""

    lexical_path: Path
    physical_path: Path
    purpose: str
    parent_dev: int
    parent_ino: int
    token_digest: str
    parent_root: Path = field(default=Path("."))
    target_dev: int | None = None
    target_ino: int | None = None
    parent_components: tuple[tuple[str, int, int], ...] = ()
    lexical_parent_path: Path | None = None
    lexical_parent_dev: int | None = None
    lexical_parent_ino: int | None = None
    lexical_name: str = ""
    lexical_entry_dev: int | None = None
    lexical_entry_ino: int | None = None
    lexical_entry_type: int | None = None
    lexical_entry_exists: bool = False
    lexical_link_target: str | None = None
    lexical_parent_components: tuple[tuple[str, int, int], ...] = ()
    session_lease: ParentSideEffectLease | _V2Lease | None = field(default=None, repr=False, compare=False)
    session_handle: str = field(default="", repr=False, compare=False)


@dataclass
class ParentOwnedTargetHandle:
    """An exclusively reserved, parent-owned directory kept open for a child."""

    parent_fd: int
    target_fd: int
    physical_path: Path
    purpose: str
    target_dev: int
    target_ino: int
    parent_name: str
    parent_dev: int
    parent_ino: int
    session_lease: ParentSideEffectLease | _V2Lease | None = field(default=None, repr=False)

    @property
    def proc_path(self) -> str:
        """Return the inherited fd path used by the child process."""
        return f"/proc/self/fd/{self.target_fd}"

    def close(self) -> None:
        """Close the target and its parent capability exactly once."""
        target_fd, parent_fd = self.target_fd, self.parent_fd
        self.target_fd = -1
        self.parent_fd = -1
        errors: list[OSError] = []
        for fd in (target_fd, parent_fd):
            if fd < 0:
                continue
            try:
                os.close(fd)
            except OSError as exc:
                errors.append(exc)
        if self.session_lease is not None:
            try:
                self.session_lease.close()
            except (OSError, ParentRootSideEffectError) as exc:
                errors.append(OSError(str(exc)))
        if errors:
            raise errors[0]


@dataclass
class ParentOwnedFileHandle:
    """A locked text file opened beneath an authenticated parent receipt."""

    stream: TextIO
    physical_path: Path
    purpose: str
    target_dev: int
    target_ino: int
    session_lease: ParentSideEffectLease | _V2Lease | None = field(default=None, repr=False)
    _closed: bool = False

    @property
    def fd(self) -> int:
        """Return the owned file descriptor while the handle is open."""
        return self.stream.fileno()

    def fileno(self) -> int:
        """Return the owned file descriptor for fd-based consumers."""
        return self.fd

    @property
    def closed(self) -> bool:
        """Return whether the receipt-bound stream is closed."""
        return self.stream.closed

    def read(self, size: int = -1) -> str:
        """Read text from the locked receipt-bound stream."""
        return self.stream.read(size)

    def readline(self, size: int = -1) -> str:
        """Read one line from the locked receipt-bound stream."""
        return self.stream.readline(size)

    def readlines(self, hint: int = -1) -> list[str]:
        """Read lines from the locked receipt-bound stream."""
        return self.stream.readlines(hint)

    def write(self, text: str) -> int:
        """Write text to the locked receipt-bound stream."""
        return self.stream.write(text)

    def writelines(self, lines: Sequence[str]) -> None:
        """Write lines to the locked receipt-bound stream."""
        self.stream.writelines(lines)

    def seek(self, offset: int, whence: int = 0) -> int:
        """Seek within the locked receipt-bound stream."""
        return self.stream.seek(offset, whence)

    def tell(self) -> int:
        """Return the locked receipt-bound stream position."""
        return self.stream.tell()

    def truncate(self, size: int | None = None) -> int:
        """Truncate the locked receipt-bound stream when explicitly requested."""
        return self.stream.truncate(size)

    def flush(self) -> None:
        """Flush the locked receipt-bound stream."""
        self.stream.flush()

    def readable(self) -> bool:
        """Return whether the locked receipt-bound stream is readable."""
        return self.stream.readable()

    def writable(self) -> bool:
        """Return whether the locked receipt-bound stream is writable."""
        return self.stream.writable()

    def seekable(self) -> bool:
        """Return whether the locked receipt-bound stream is seekable."""
        return self.stream.seekable()

    def __enter__(self) -> "ParentOwnedFileHandle":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        try:
            self.close()
        except ParentRootSideEffectError as cleanup_error:
            if exc_value is not None:
                raise cleanup_error from exc_value
            raise
        return False

    def close(self) -> None:
        """Flush, unlock, and close the owned descriptor exactly once."""
        if self._closed:
            return
        self._closed = True
        cleanup_error: ParentRootSideEffectError | None = None
        try:
            descriptor = self.stream.fileno()
            self.stream.flush()
            os.fsync(descriptor)
        except (OSError, ValueError) as exc:
            cleanup_error = ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"parent-owned file flush failed ({self.purpose}): {exc}",
            )
        finally:
            try:
                descriptor = self.stream.fileno()
            except ValueError:
                descriptor = -1
            if descriptor >= 0:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                except OSError as exc:
                    if cleanup_error is None:
                        cleanup_error = ParentRootSideEffectError(
                            ParentRootReject.ROOT_RACE_DETECTED,
                            f"parent-owned file unlock failed ({self.purpose}): {exc}",
                        )
            try:
                self.stream.close()
            except OSError as exc:
                    if cleanup_error is None:
                        cleanup_error = ParentRootSideEffectError(
                        ParentRootReject.ROOT_RACE_DETECTED,
                            f"parent-owned file close failed ({self.purpose}): {exc}",
                        )
            if self.session_lease is not None:
                try:
                    self.session_lease.close()
                except (OSError, ParentRootSideEffectError) as exc:
                    if cleanup_error is None:
                        cleanup_error = ParentRootSideEffectError(
                            ParentRootReject.ROOT_RACE_DETECTED,
                            f"parent-owned session lease close failed ({self.purpose}): {exc}",
                        )
        if cleanup_error is not None:
            raise cleanup_error


@dataclass
class _TreeRemovalFrame:
    """One opened directory in the iterative post-order removal stack."""

    directory_fd: int
    parent_fd: int | None = None
    entry_name: str | None = None
    expected_dev: int | None = None
    expected_ino: int | None = None
    entries: list[str] | None = None


@dataclass(frozen=True)
class ParentRootAttestationReceipt:
    """Immutable authenticated parent/source/clone identity."""

    parent_root: Path
    parent_dev: int
    parent_ino: int
    source_root: Path | None
    clone_root: Path | None
    root_kind: str
    precedence: str
    marker: Mapping[str, object] | None
    module: Mapping[str, object] | None
    owner: Mapping[str, object] | None
    handoff: ChildHandoffReceipt | None
    status: str
    reject: ParentRootReject = ParentRootReject.NONE
    detail: str = ""
    token_digest: str = ""
    purpose: str = "repository-side-effect"
    session_handle: str = field(default="", repr=False, compare=False)
    session_lease: ParentSideEffectLease | _V2Lease | None = field(default=None, repr=False, compare=False)
    session_role: str = field(default="legacy", repr=False, compare=False)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value.lower()
    )


def _absolute(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def _physical(path: Path, *, strict: bool = False) -> Path:
    try:
        return path.resolve(strict=strict)
    except (OSError, RuntimeError) as exc:
        raise ParentRootSideEffectError(ParentRootReject.ROOT_MISSING,
                                        f"cannot resolve {path}: {exc}") from exc


def _contains(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _identity(path: Path) -> tuple[int, int]:
    try:
        info = path.stat()
    except OSError as exc:
        raise ParentRootSideEffectError(ParentRootReject.ROOT_MISSING,
                                        f"cannot stat {path}: {exc}") from exc
    return info.st_dev, info.st_ino


def _write_all(fd: int, data: bytes) -> None:
    """Write all bytes, preserving short-write and interrupted-write semantics."""
    offset = 0
    while offset < len(data):
        try:
            written = os.write(fd, data[offset:])
        except InterruptedError:
            continue
        if written <= 0:
            raise OSError(errno.EIO, "write returned no progress")
        offset += written


def _read_all(fd: int) -> bytes:
    """Read a regular state file to EOF from its validated descriptor."""
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _git_toplevel(path: Path) -> Path:
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                            check=False, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise ParentRootSideEffectError(ParentRootReject.ROOT_MISSING,
                                        f"not an authenticated Git checkout: {path}")
    return _physical(Path(result.stdout.strip()), strict=True)


def _git_origin(path: Path) -> str:
    result = subprocess.run(["git", "-C", str(path), "remote", "get-url", "origin"],
                            check=False, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH,
                                        f"origin remote is unavailable: {path}")
    return result.stdout.strip()


def _parent_repo_id(path: Path) -> str:
    """Derive the stable parent identity from its physical root and origin."""
    return _sha256(
        f"{path.resolve(strict=True)}\0{_git_origin(path).rstrip('/')}".encode("utf-8")
    )


def _boot_id() -> str:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except OSError as exc:
        raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM,
                                        f"Linux boot identity is unavailable: {exc}") from exc
    if not value:
        raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM,
                                        "Linux boot identity is empty")
    return value


def _git_value(path: Path, *args: str, reject: ParentRootReject = ParentRootReject.ROOT_MISMATCH) -> str:
    result = subprocess.run(["git", "-C", str(path), *args], check=False,
                            capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise ParentRootSideEffectError(reject, f"Git identity is unavailable at {path}: {' '.join(args)}")
    return result.stdout.strip()


def _git_identity(path: Path, reject: ParentRootReject) -> tuple[str, str]:
    commit = _git_value(path, "rev-parse", "HEAD", reject=reject)
    tree = _git_value(path, "rev-parse", "HEAD^{tree}", reject=reject)
    return commit, tree


def _raw_digest(path: Path) -> str:
    try:
        return _sha256(path.read_bytes())
    except OSError as exc:
        raise ParentRootSideEffectError(ParentRootReject.OWNER_EVIDENCE_INVALID,
                                        f"cannot hash bound file {path}: {exc}") from exc


def _module_binding(root: Path, manifest: Path, source: Path,
                    reject: ParentRootReject) -> dict[str, object]:
    """Read one exact .gitmodules entry and bind it to the source checkout."""
    result = subprocess.run(
        ["git", "-C", str(root), "config", "--file", str(manifest), "--null", "--list"],
        check=False, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ParentRootSideEffectError(reject, f"cannot parse module manifest: {manifest}")
    values: dict[str, dict[str, str]] = {}
    for record in result.stdout.split("\0"):
        key, separator, value = record.partition("\n")
        if not separator:
            continue
        parts = key.split(".")
        if len(parts) == 3 and parts[0] == "submodule" and parts[2] in {"path", "url"}:
            values.setdefault(parts[1], {})[parts[2]] = value.strip()
    relative = source.relative_to(root).as_posix()
    matches = [item for item in values.values() if item.get("path") == relative]
    if len(matches) != 1 or not matches[0].get("url"):
        raise ParentRootSideEffectError(reject, f"module path is not uniquely bound: {relative}")
    commit, tree = _git_identity(source, reject)
    gitlink = _git_value(root, "ls-tree", "HEAD", "--", relative, reject=reject)
    fields = gitlink.split(None, 3)
    if len(fields) != 4 or fields[0] != "160000" or fields[1] != "commit" or fields[2] != commit:
        raise ParentRootSideEffectError(reject,
                                        f"module path is not an exact gitlink to source HEAD: {relative}")
    return {"schema": "gitmodules", "sha256": _raw_digest(manifest),
            "module_path": relative, "url": matches[0]["url"],
            "observed_commit": commit, "observed_tree": tree}


def _normalize_remote(value: str) -> str:
    return value.rstrip("/").removesuffix(".git")


def _lexical_candidate(root: Path, value: Path | str) -> Path:
    candidate = Path(value)
    lexical = candidate if candidate.is_absolute() else root / candidate
    if any(part == ".." for part in lexical.parts):
        raise ParentRootSideEffectError(ParentRootReject.SYMLINK_ESCAPE,
                                        f"lexical parent escape: {value}")
    return _absolute(lexical)


def _physical_in_root(root: Path, value: Path | str, *, allow_missing: bool) -> tuple[Path, tuple[str, ...]]:
    lexical = _lexical_candidate(root, value)
    try:
        physical = lexical.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ParentRootSideEffectError(ParentRootReject.SYMLINK_ESCAPE,
                                        f"cannot resolve {lexical}: {exc}") from exc
    if not _contains(root, physical):
        raise ParentRootSideEffectError(ParentRootReject.SYMLINK_ESCAPE,
                                        f"path resolves outside parent root: {lexical} -> {physical}")
    if not allow_missing and not physical.exists():
        raise ParentRootSideEffectError(ParentRootReject.ROOT_MISSING,
                                        f"path does not exist: {physical}")
    return physical, tuple(physical.relative_to(root).parts)


def _open_root(root: Path) -> int:
    if sys.platform != "linux":
        raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform)
    try:
        return os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        raise ParentRootSideEffectError(ParentRootReject.ROOT_MISSING,
                                        f"cannot open parent root: {exc}") from exc


def _open_components(root: Path, parts: Sequence[str], *, create: bool) -> tuple[int, Path]:
    """Open physical components with openat/O_NOFOLLOW and return leaf parent fd."""
    fd = _open_root(root)
    current = root
    try:
        for component in parts:
            if component in {"", ".", ".."}:
                raise ParentRootSideEffectError(ParentRootReject.SYMLINK_ESCAPE,
                                                f"invalid path component: {component!r}")
            try:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY |
                                os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise ParentRootSideEffectError(ParentRootReject.ROOT_MISSING,
                                                    f"missing directory component: {component}")
                try:
                    try:
                        os.mkdir(component, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                    child = os.open(component, os.O_RDONLY | os.O_DIRECTORY |
                                    os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                except OSError as exc:
                    raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED,
                                                    f"directory component changed: {component}: {exc}") from exc
            except OSError as exc:
                reason = ParentRootReject.SYMLINK_ESCAPE if exc.errno in {errno.ELOOP, errno.ENOTDIR} else ParentRootReject.ROOT_RACE_DETECTED
                raise ParentRootSideEffectError(reason, f"cannot open component {component}: {exc}") from exc
            os.close(fd)
            fd = child
            current = current / component
        return fd, current
    except Exception:
        os.close(fd)
        raise


def _component_identities(
    root: Path, parts: Sequence[str], *, create: bool
) -> tuple[tuple[str, int, int], ...]:
    """Capture every directory identity from the root through the parent."""
    fd = _open_root(root)
    identities: list[tuple[str, int, int]] = []
    try:
        root_info = os.fstat(fd)
        identities.append((".", root_info.st_dev, root_info.st_ino))
        for component in parts:
            if component in {"", ".", ".."}:
                raise ParentRootSideEffectError(
                    ParentRootReject.SYMLINK_ESCAPE,
                    f"invalid path component: {component!r}",
                )
            try:
                child = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=fd,
                )
            except FileNotFoundError:
                if not create:
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_MISSING,
                        f"missing directory component: {component}",
                    )
                try:
                    try:
                        os.mkdir(component, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                    child = os.open(
                        component,
                        os.O_RDONLY
                        | os.O_DIRECTORY
                        | os.O_NOFOLLOW
                        | os.O_CLOEXEC,
                        dir_fd=fd,
                    )
                except OSError as exc:
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_RACE_DETECTED,
                        f"directory component changed: {component}: {exc}",
                    ) from exc
            except OSError as exc:
                reason = (
                    ParentRootReject.SYMLINK_ESCAPE
                    if exc.errno in {errno.ELOOP, errno.ENOTDIR}
                    else ParentRootReject.ROOT_RACE_DETECTED
                )
                raise ParentRootSideEffectError(
                    reason, f"cannot open component {component}: {exc}"
                ) from exc
            info = os.fstat(child)
            identities.append((component, info.st_dev, info.st_ino))
            os.close(fd)
            fd = child
        return tuple(identities)
    finally:
        os.close(fd)


def _verify_parent_components(receipt: ParentOwnedPathReceipt) -> None:
    """Reject replacement of any root-to-parent directory component."""
    if not receipt.parent_components:
        raise ParentRootSideEffectError(
            ParentRootReject.ROOT_RACE_DETECTED,
            "path receipt has no complete parent component identities",
        )
    relative = tuple(receipt.physical_path.relative_to(receipt.parent_root).parts)
    expected_parts = relative[:-1]
    if len(receipt.parent_components) != len(expected_parts) + 1:
        raise ParentRootSideEffectError(
            ParentRootReject.ROOT_RACE_DETECTED,
            "path receipt parent component shape changed",
        )
    actual = _component_identities(receipt.parent_root, expected_parts, create=False)
    for expected_entry, actual_entry in zip(receipt.parent_components, actual):
        if expected_entry[0] != actual_entry[0] or expected_entry[1:] != actual_entry[1:]:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"parent directory identity changed: {expected_entry[0]}",
            )


def _lexical_snapshot(root: Path, lexical: Path) -> dict[str, object]:
    """Capture the no-follow lexical parent and entry identity for a receipt."""
    # The authenticated root itself is a valid directory capability used by
    # ensure-dir callers for top-level paths (whose lexical parent is ``.``).
    # It has no removable lexical entry; retain the attested receipt fields
    # rather than attempting to inspect the parent outside the boundary.
    if lexical == root:
        return {}
    try:
        parent_parts = tuple(lexical.parent.relative_to(root).parts)
    except ValueError as exc:
        raise ParentRootSideEffectError(
            ParentRootReject.SYMLINK_ESCAPE,
            f"lexical parent escapes parent root: {lexical}",
        ) from exc
    parent_fd, _ = _open_components(root, parent_parts, create=False)
    try:
        parent_info = os.fstat(parent_fd)
        entry_name = lexical.name
        entry_dev: int | None = None
        entry_ino: int | None = None
        entry_type: int | None = None
        entry_exists = False
        link_target: str | None = None
        try:
            entry_info = os.stat(
                entry_name, dir_fd=parent_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            pass
        else:
            entry_exists = True
            entry_dev = entry_info.st_dev
            entry_ino = entry_info.st_ino
            entry_type = stat.S_IFMT(entry_info.st_mode)
            if stat.S_ISLNK(entry_info.st_mode):
                link_target = os.readlink(entry_name, dir_fd=parent_fd)
        return {
            "lexical_parent_path": lexical.parent,
            "lexical_parent_dev": parent_info.st_dev,
            "lexical_parent_ino": parent_info.st_ino,
            "lexical_name": entry_name,
            "lexical_entry_dev": entry_dev,
            "lexical_entry_ino": entry_ino,
            "lexical_entry_type": entry_type,
            "lexical_entry_exists": entry_exists,
            "lexical_link_target": link_target,
            "lexical_parent_components": _component_identities(
                root, parent_parts, create=False
            ),
        }
    finally:
        os.close(parent_fd)


def _open_lexical_entry(receipt: ParentOwnedPathReceipt) -> tuple[int, str]:
    """Open and re-attest a receipt's lexical entry without following it."""
    root = receipt.parent_root
    lexical_parent = receipt.lexical_parent_path
    if (
        lexical_parent is None
        or not receipt.lexical_name
        or not receipt.lexical_entry_exists
        or receipt.lexical_entry_dev is None
        or receipt.lexical_entry_ino is None
        or receipt.lexical_entry_type is None
        or receipt.lexical_parent_dev is None
        or receipt.lexical_parent_ino is None
    ):
        raise ParentRootSideEffectError(
            ParentRootReject.ROOT_RACE_DETECTED,
            "path receipt has no complete lexical-entry identity",
        )
    try:
        parent_parts = tuple(lexical_parent.relative_to(root).parts)
    except ValueError as exc:
        raise ParentRootSideEffectError(
            ParentRootReject.SYMLINK_ESCAPE,
            f"lexical parent escapes parent root: {lexical_parent}",
        ) from exc
    parent_fd, _ = _open_components(root, parent_parts, create=False)
    try:
        parent_info = os.fstat(parent_fd)
        if (parent_info.st_dev, parent_info.st_ino) != (
            receipt.lexical_parent_dev,
            receipt.lexical_parent_ino,
        ):
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                "lexical parent identity changed before removal",
            )
        actual_components = _component_identities(
            root, parent_parts, create=False
        )
        if actual_components != receipt.lexical_parent_components:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                "lexical parent component identity changed before removal",
            )
        observed = os.stat(
            receipt.lexical_name, dir_fd=parent_fd, follow_symlinks=False
        )
        if (
            (observed.st_dev, observed.st_ino)
            != (receipt.lexical_entry_dev, receipt.lexical_entry_ino)
            or stat.S_IFMT(observed.st_mode) != receipt.lexical_entry_type
        ):
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                "lexical entry identity changed before removal",
            )
        if stat.S_ISLNK(observed.st_mode):
            link_target = os.readlink(
                receipt.lexical_name, dir_fd=parent_fd
            )
            if link_target != receipt.lexical_link_target:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "lexical symlink target changed before removal",
                )
            current_physical, _ = _physical_in_root(
                root, receipt.lexical_path, allow_missing=True
            )
            if current_physical != receipt.physical_path:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "resolved symlink target changed before removal",
                )
            try:
                target_info = current_physical.stat()
            except FileNotFoundError:
                if receipt.target_dev is not None or receipt.target_ino is not None:
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_RACE_DETECTED,
                        "symlink target disappeared before removal",
                    )
            else:
                if receipt.target_dev is None or receipt.target_ino is None:
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_RACE_DETECTED,
                        "broken symlink target appeared before removal",
                    )
                if (target_info.st_dev, target_info.st_ino) != (
                    receipt.target_dev,
                    receipt.target_ino,
                ):
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_RACE_DETECTED,
                        "symlink target identity changed before removal",
                    )
        else:
            current_physical, _ = _physical_in_root(
                root, receipt.lexical_path, allow_missing=False
            )
            if current_physical != receipt.physical_path:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "resolved lexical entry changed before removal",
                )
        return parent_fd, receipt.lexical_name
    except Exception:
        os.close(parent_fd)
        raise


def _parent_directory(root: Path, physical: Path, *, create: bool) -> tuple[int, str, Path]:
    relative = tuple(physical.relative_to(root).parts)
    if not relative:
        raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH,
                                        "parent root is not a file target")
    parent_fd, parent_path = _open_components(root, relative[:-1], create=create)
    return parent_fd, relative[-1], parent_path


def _read_json_exact(path: Path, reject: ParentRootReject, required: frozenset[str], schema: str) -> Mapping[str, object]:
    def reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicate_pairs)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ParentRootSideEffectError(reject, f"invalid bound file {path}: {exc}") from exc
    mapping = cast(Mapping[str, object], value) if isinstance(value, Mapping) else None
    if (mapping is None or set(mapping) != set(required) or mapping.get("schema") != schema
            or any(not isinstance(item, str) or not item for item in mapping.values())):
        raise ParentRootSideEffectError(reject, f"bound file schema mismatch: {path}")
    return mapping


def _read_bound_file(root: Path, path: Path | None, reject: ParentRootReject) -> Mapping[str, object] | None:
    if path is None:
        return None
    physical, _ = _physical_in_root(root, path, allow_missing=False)
    if not physical.is_file():
        raise ParentRootSideEffectError(reject, f"not a regular file: {physical}")
    if physical.name == ".gitmodules":
        try:
            raw = physical.read_bytes()
        except FileExistsError as exc:
            raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED, "publication target collision") from exc
        except OSError as exc:
            raise ParentRootSideEffectError(reject, f"cannot read {physical}: {exc}") from exc
        if not raw:
            raise ParentRootSideEffectError(reject, f"empty module file: {physical}")
        return {"schema": "gitmodules", "sha256": _sha256(raw), "path": str(physical)}
    if reject is ParentRootReject.MARKER_INVALID:
        return _read_json_exact(physical, reject, _MARKER_FIELDS, "agent-canon.repository-topic.v2")
    if reject is ParentRootReject.OWNER_EVIDENCE_INVALID:
        return _read_json_exact(physical, reject, _OWNER_FIELDS, "agent-canon.owner-evidence.v1")
    try:
        raw = physical.read_bytes()
    except OSError as exc:
        raise ParentRootSideEffectError(reject, f"cannot read {physical}: {exc}") from exc
    return {"schema": "gitmodules", "sha256": _sha256(raw), "path": str(physical)}


def _ensure_handoff_dir(root: Path) -> None:
    fd, _ = _open_components(root, (".agent-canon", "handoff"), create=True)
    os.close(fd)


def _secure_file(root: Path, name: str, data: bytes) -> None:
    _ensure_handoff_dir(root)
    directory_fd, _ = _open_components(root, (".agent-canon", "handoff"), create=False)
    flags = os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC | os.O_EXCL | os.O_NOFOLLOW
    try:
        fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
    except FileExistsError:
        os.close(directory_fd)
        return
    try:
        os.fchmod(fd, 0o600)
        _write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
        os.close(directory_fd)


def _load_secret(root: Path, *, create: bool) -> bytes:
    if create:
        _ensure_handoff_dir(root)
    directory_fd = -1
    fd = -1
    try:
        directory_fd, _ = _open_components(root, (".agent-canon", "handoff"), create=False)
        fd = os.open("secret", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd)
        info = os.fstat(fd)
        raw = os.read(fd, 4096)
        os.close(fd)
        fd = -1
        os.close(directory_fd)
        directory_fd = -1
        if info.st_mode & 0o077:
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "handoff secret is not private")
        if len(raw) < 32:
            raise ValueError("short secret")
        return raw
    except (FileNotFoundError, NotADirectoryError):
        if not create:
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "parent-local handoff secret is missing")
        value = secrets.token_bytes(32)
        _secure_file(root, "secret", value)
        # Another process may have won the O_EXCL race; always authenticate
        # with the durable parent-local secret actually stored on disk.
        return _load_secret(root, create=False)
    except OSError as exc:
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, f"cannot read handoff secret: {exc}") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        if directory_fd >= 0:
            os.close(directory_fd)


def _locked_state(root: Path, *, create: bool) -> tuple[int, dict[str, float]]:
    if create:
        _ensure_handoff_dir(root)
    directory_fd, _ = _open_components(root, (".agent-canon", "handoff"), create=False)
    if create:
        _secure_file(root, "nonces.json", b"{}")
    try:
        fd = os.open("nonces.json", os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd)
        os.close(directory_fd)
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        raw = os.read(fd, 1 << 20)
        value = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(value, Mapping):
            raise ValueError("invalid nonce state")
        state = cast(Mapping[str, object], value)
        return fd, {str(k): float(cast(float | int | str, v)) for k, v in state.items()}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        try:
            os.close(directory_fd)
        except OSError:
            pass
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID,
                                        f"cannot open nonce receipt: {exc}") from exc


def _write_locked_state(fd: int, state: Mapping[str, float]) -> None:
    raw = _canonical_bytes(state)
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    _write_all(fd, raw)
    os.fsync(fd)


def _close_state(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _decode_envelope(token: str) -> tuple[Mapping[str, object], str]:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        envelope = json.loads(raw.decode("utf-8"))
        payload = envelope["payload"]
        signature = envelope["signature"]
    except (ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID,
                                        f"malformed handoff token: {exc}") from exc
    if not isinstance(payload, Mapping) or not isinstance(signature, str):
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "invalid handoff envelope")
    return cast(Mapping[str, object], payload), token


def _signed_token(payload: Mapping[str, object], secret: bytes) -> str:
    signature = hmac.new(secret, _canonical_bytes(payload), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(_canonical_bytes({"payload": payload, "signature": signature})).decode("ascii")


_SESSION_FIELDS = (
    "schema", "record_id", "session_id", "audience", "parent_root",
    "issued_at", "expires_at", "nonce", "status",
)
_SESSION_STATE_FIELDS = (
    "schema", "record_id", "session_id", "audience", "parent_root",
    "issued_at", "expires_at", "nonce", "status", "active_leases", "revoked_at",
)
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_LOCAL_LEASES: dict[str, list[ParentSideEffectLease]] = {}


def _session_payload_bytes(payload: Mapping[str, object]) -> bytes:
    """Serialize the session payload in its documented field order."""
    ordered = {key: payload[key] for key in _SESSION_FIELDS}
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _session_handle(payload: Mapping[str, object], secret: bytes) -> str:
    signature = hmac.new(secret, _session_payload_bytes(payload), hashlib.sha256).hexdigest()
    envelope = {"payload": {key: payload[key] for key in _SESSION_FIELDS}, "signature": signature}
    return base64.urlsafe_b64encode(
        json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def _session_paths(root: Path, record_id: str, session_id: str) -> tuple[Path, Path, Path]:
    if not _SESSION_ID_RE.fullmatch(record_id) or not _SESSION_ID_RE.fullmatch(session_id):
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID, "session record/session identifier is invalid"
        )
    base = root / ".agent-canon" / "runtime" / "side-effect-sessions" / record_id / session_id
    return base, base / "state.json", base / "session.lock"


def _atomic_private_json(path: Path, payload: Mapping[str, object]) -> None:
    """Publish one state record with private mode, fsync, and atomic rename."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    temporary_name = f".{path.name}.{secrets.token_hex(8)}.tmp"
    temporary_fd = -1
    try:
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=directory_fd,
        )
        _write_all(
            temporary_fd,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = -1
        os.rename(temporary_name, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


def _read_session_state(path: Path) -> dict[str, object]:
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        value = json.loads(os.read(fd, 1 << 20).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, f"session state is unreadable: {exc}") from exc
    finally:
        if fd >= 0:
            os.close(fd)
    if not isinstance(value, dict):
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session state schema is invalid")
    state = cast(dict[str, object], value)
    if tuple(state) != _SESSION_STATE_FIELDS:
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session state schema is invalid")
    return state


def _parse_session_state(value: object) -> dict[str, object]:
    """Validate one decoded session-state object."""
    if not isinstance(value, dict):
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session state schema is invalid")
    state = cast(dict[str, object], value)
    if tuple(state) != _SESSION_STATE_FIELDS:
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session state schema is invalid")
    return state


def _read_session_state_fd(directory_fd: int) -> dict[str, object]:
    """Read session state relative to an already no-follow-opened directory."""
    fd = -1
    try:
        fd = os.open("state.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory_fd)
        value = json.loads(os.read(fd, 1 << 20).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, f"session state is unreadable: {exc}") from exc
    finally:
        if fd >= 0:
            os.close(fd)
    return _parse_session_state(value)


def _atomic_private_json_at(directory_fd: int, name: str, payload: Mapping[str, object]) -> None:
    """Atomically publish private JSON relative to a no-follow directory fd."""
    temporary_name = f".{name}.{secrets.token_hex(8)}.tmp"
    temporary_fd = -1
    try:
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=directory_fd,
        )
        _write_all(
            temporary_fd,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = -1
        os.rename(temporary_name, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _session_state_valid(state: Mapping[str, object], *, root: Path, record_id: str, session_id: str) -> None:
    if state.get("schema") != _RETIRED_SCHEMA_SIDE_EFFECT_SESSION_STATE:
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session state schema mismatch")
    if state.get("record_id") != record_id or state.get("session_id") != session_id:
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session state binding mismatch")
    if state.get("parent_root") != str(root):
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session state root mismatch")
    if state.get("status") not in {"active", "revoked"}:
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session state status is invalid")
    leases = state.get("active_leases")
    if isinstance(leases, bool) or not isinstance(leases, int) or leases < 0:
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session lease count is invalid")


def _session_status_reject(state: Mapping[str, object], now: float) -> None:
    status = state.get("status")
    expires = state.get("expires_at")
    if status == "revoked":
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_revoked")
    if isinstance(expires, bool) or not isinstance(expires, (int, float)) or not math.isfinite(float(expires)):
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session expiry is invalid")
    if now > float(expires):
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_expired")


def _make_session_state(payload: Mapping[str, object], *, status: str = "active", active_leases: int = 0,
                        revoked_at: float | None = None) -> dict[str, object]:
    return {
        "schema": _RETIRED_SCHEMA_SIDE_EFFECT_SESSION_STATE,
        "record_id": payload["record_id"],
        "session_id": payload["session_id"],
        "audience": payload["audience"],
        "parent_root": payload["parent_root"],
        "issued_at": payload["issued_at"],
        "expires_at": payload["expires_at"],
        "nonce": payload["nonce"],
        "status": status,
        "active_leases": active_leases,
        "revoked_at": revoked_at,
    }


def _session_secret(root: Path, *, create: bool) -> bytes:
    return hmac.new(_load_secret(root, create=create), _boot_id().encode("ascii"), hashlib.sha256).digest()


class ParentRootSideEffectBoundary:
    """Authenticate Git identity and expose race-safe parent-local effects."""

    def issue_child_handoff(self, parent_root: Path, *, audience: str,
                            source_root: Path | None = None, clone_root: Path | None = None,
                            ttl_seconds: int = _DEFAULT_TOKEN_TTL,
                            transport: str = "parent-local-file") -> str:
        root = _physical(Path(parent_root), strict=True)
        if _git_toplevel(root) != root:
            raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH, "handoff root is not Git toplevel")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if transport not in _ALLOWED_TRANSPORTS:
            raise ValueError(f"unsupported handoff transport: {transport}")
        resolved_source = _physical(source_root, strict=True) if source_root else None
        resolved_clone = _physical(clone_root, strict=True) if clone_root else None
        for label, path in (("source", resolved_source), ("clone", resolved_clone)):
            if path is not None and not _contains(root, path):
                raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH,
                                                f"handoff {label} is outside parent root")
            if label == "clone" and path is not None and _git_toplevel(path) != path:
                raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH,
                                                "handoff clone is not an authenticated Git checkout")
        secret = _session_secret(root, create=True)
        now = time.monotonic()
        storage = "parent-local-file" if transport == "parent-local-file" else "pipe"
        mode = "0600" if transport == "parent-local-file" else "pipe"
        payload: dict[str, object] = {
            "token_version": SCHEMA_HANDOFF, "audience": audience,
            "parent_root": str(root),
            "source_root": str(resolved_source) if resolved_source else None,
            "clone_root": str(resolved_clone) if resolved_clone else None,
            "issued_at": now, "expires_at": now + ttl_seconds,
            "nonce": secrets.token_hex(16), "storage": storage,
            "mode": mode, "validation": "hmac-single-use", "transport": transport,
        }
        payload["payload_sha256"] = _sha256(_canonical_bytes({k: v for k, v in payload.items() if k != "payload_sha256"}))
        fd, state = _locked_state(root, create=True)
        try:
            state[str(payload["nonce"])] = float(cast(float | int | str, payload["expires_at"]))
            _write_locked_state(fd, state)
        finally:
            _close_state(fd)
        return _signed_token(payload, secret)

    def issue_record_session(
        self,
        parent_root: Path,
        *,
        record_id: str,
        audience: str,
        ttl_seconds: int = _DEFAULT_TOKEN_TTL,
    ) -> SessionResolutionResult:
        """Reject the retired v1 record-session constructor."""
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID,
            "v1_session_api_rejected: use public_session",
        )
        """Unreachable historical implementation retained only in source history."""
        root = _physical(Path(parent_root), strict=True)
        if _git_toplevel(root) != root:
            raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH, "session root is not Git toplevel")
        if not _SESSION_ID_RE.fullmatch(record_id) or not audience or audience != audience.strip():
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "invalid record or audience")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        secret = _session_secret(root, create=True)
        session_id = secrets.token_urlsafe(18).replace("-", "_")
        nonce = secrets.token_urlsafe(18).replace("-", "_")
        base, state_path, lock_path = _session_paths(root, record_id, session_id)
        # The component opener refuses symlink traversal and binds all state
        # beneath the already-attested physical parent.
        directory_fd, _ = _open_components(
            root,
            (".agent-canon", "runtime", "side-effect-sessions", record_id, session_id),
            create=True,
        )
        os.fchmod(directory_fd, 0o700)
        os.close(directory_fd)
        base_fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            lock_fd = os.open(
                lock_path.name,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=base_fd,
            )
        except FileExistsError as exc:
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session id collision") from exc
        finally:
            os.close(base_fd)
        os.fchmod(lock_fd, 0o600)
        os.close(lock_fd)
        now = time.monotonic()
        payload: dict[str, object] = {
            "schema": _RETIRED_SCHEMA_SIDE_EFFECT_SESSION,
            "record_id": record_id,
            "session_id": session_id,
            "audience": audience,
            "parent_root": str(root),
            "issued_at": now,
            "expires_at": now + float(ttl_seconds),
            "nonce": nonce,
            "status": "active",
        }
        _atomic_private_json(state_path, _make_session_state(payload))
        attestation = self.attest(
            ParentRootAttestationRequest(cwd=root, explicit_root=root, purpose=audience)
        )
        handle = _session_handle(payload, secret)
        attestation = replace(attestation, session_handle=handle)
        return _RetiredParentSideEffectSessionReceipt(
            _RETIRED_SCHEMA_SIDE_EFFECT_SESSION,
            record_id,
            session_id,
            audience,
            root,
            now,
            now + float(ttl_seconds),
            nonce,
            "active",
            state_path,
            attestation,
            handle,
        )

    def session_environment(
        self,
        session: SessionResolutionResult,
        base_env: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """Return a record environment carrying only the side-effect channel."""
        return _v2_session_environment(session, base_env)

    def _validate_record_session(
        self,
        *,
        cwd: Path | str,
        env: Mapping[str, str],
        operation_purpose: str,
        hold_lease: bool = True,
    ) -> _RetiredParentSideEffectSessionReceipt:
        if not operation_purpose or operation_purpose != operation_purpose.strip():
            raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "operation_purpose is invalid")
        handoff = env.get(SIDE_EFFECT_HANDOFF_ENV, "")
        root_value = env.get(SIDE_EFFECT_PARENT_ROOT_ENV, "")
        if not handoff or not root_value:
            detail = "session_missing"
            if env.get("AGENT_CANON_PARENT_ROOT") or env.get("AGENT_CANON_ACTIVE_REPOSITORY_ROOT"):
                detail = "legacy_authority_forbidden"
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, detail)
        try:
            root = _physical(Path(root_value), strict=True)
            try:
                payload, _ = _decode_envelope(handoff)
            except ParentRootSideEffectError as exc:
                raise ParentRootSideEffectError(
                    ParentRootReject.HANDOFF_INVALID, "session_schema"
                ) from exc
            if tuple(payload) != _SESSION_FIELDS or payload.get("schema") != _RETIRED_SCHEMA_SIDE_EFFECT_SESSION:
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_schema")
            if any(not isinstance(payload.get(key), str) or not payload.get(key) for key in ("record_id", "session_id", "audience", "parent_root", "nonce")):
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_schema")
            if payload.get("status") != "active":
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_schema")
            if _physical(Path(str(payload["parent_root"])), strict=True) != root:
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_binding")
            expected = hmac.new(_session_secret(root, create=False), _session_payload_bytes(payload), hashlib.sha256).hexdigest()
            envelope_value = json.loads(base64.urlsafe_b64decode(handoff.encode("ascii")).decode("utf-8"))
            if not isinstance(envelope_value, dict):
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_schema")
            envelope = cast(dict[str, object], envelope_value)
            if set(envelope) != {"payload", "signature"}:
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_schema")
            signature = envelope.get("signature")
            if not isinstance(signature, str) or not hmac.compare_digest(expected, signature):
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_signature")
            now = time.monotonic()
            issued = payload.get("issued_at")
            expires = payload.get("expires_at")
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in (issued, expires)):
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_schema")
            issued_value = cast(int | float, issued)
            expires_value = cast(int | float, expires)
            if now < float(issued_value):
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_not_yet_valid")
            base, state_path, lock_path = _session_paths(root, str(payload["record_id"]), str(payload["session_id"]))
            if not _contains(root, base) or not _contains(root, state_path):
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_binding")
            if _physical(base, strict=True) != base or _physical(state_path, strict=True) != state_path or _physical(lock_path, strict=True) != lock_path:
                raise ParentRootSideEffectError(ParentRootReject.SYMLINK_ESCAPE, "session state symlink escape")
            cwd_path = _physical(Path(cwd), strict=True)
            if not _contains(root, cwd_path):
                raise ParentRootSideEffectError(ParentRootReject.ROOT_SPOOFED, "session cwd is outside parent")
            lock_fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            lease: ParentSideEffectLease | None = None
            lease_fd = -1
            lease_lock_path: Path | None = None
            lease_record_path: Path | None = None
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                state = _read_session_state(state_path)
                _session_state_valid(state, root=root, record_id=str(payload["record_id"]), session_id=str(payload["session_id"]))
                if state.get("audience") != payload["audience"] or state.get("nonce") != payload["nonce"]:
                    raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_binding")
                _session_status_reject(state, now)
                if now > float(expires_value):
                    state = _make_session_state(payload, status="revoked", revoked_at=now)
                    _atomic_private_json(state_path, state)
                    raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "session_expired")
                if hold_lease:
                    lease_dir = base / "leases"
                    if lease_dir.exists() and _physical(lease_dir, strict=True) != lease_dir:
                        raise ParentRootSideEffectError(ParentRootReject.SYMLINK_ESCAPE, "session lease symlink escape")
                    lease_dir.mkdir(mode=0o700, exist_ok=True)
                    os.chmod(lease_dir, 0o700)
                    lease_id = secrets.token_urlsafe(12).replace("-", "_")
                    lease_lock_path = lease_dir / f"{lease_id}.lock"
                    lease_record_path = lease_dir / f"{lease_id}.json"
                    lease_fd = os.open(lease_lock_path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
                    os.fchmod(lease_fd, 0o600)
                    fcntl.flock(lease_fd, fcntl.LOCK_SH)
                    _atomic_private_json(lease_record_path, {
                        "schema": "agent-canon.parent-side-effect-lease.v1",
                        "lease_id": lease_id, "record_id": payload["record_id"],
                        "session_id": payload["session_id"], "operation_purpose": operation_purpose,
                    })
                    lease = ParentSideEffectLease(
                        lease_id=lease_id,
                        path=lease_record_path,
                        lock_fd=lease_fd,
                        state_path=state_path,
                        session_lock_path=lock_path,
                        session_handle=handoff,
                        owner_thread_id=threading.get_ident(),
                    )
                    _LOCAL_LEASES.setdefault(handoff, []).append(lease)
                    active = len(tuple(lease_dir.glob("*.json")))
                    _atomic_private_json(state_path, _make_session_state(payload, active_leases=active))
            finally:
                if lease is None and lease_fd >= 0:
                    try:
                        fcntl.flock(lease_fd, fcntl.LOCK_UN)
                    finally:
                        os.close(lease_fd)
                    if lease_lock_path is not None:
                        lease_lock_path.unlink(missing_ok=True)
                    if lease_record_path is not None:
                        lease_record_path.unlink(missing_ok=True)
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            try:
                attestation = replace(
                    self.attest(ParentRootAttestationRequest(cwd=root, explicit_root=root, purpose=str(payload["audience"]))),
                    session_handle=handoff,
                    session_lease=lease,
                )
                return _RetiredParentSideEffectSessionReceipt(
                    _RETIRED_SCHEMA_SIDE_EFFECT_SESSION, str(payload["record_id"]), str(payload["session_id"]),
                    str(payload["audience"]), root, float(issued_value), float(expires_value), str(payload["nonce"]),
                    "active", state_path, attestation, handoff, lease,
                )
            except Exception:
                if lease is not None:
                    lease.close()
                raise
        except ParentRootSideEffectError:
            raise
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, f"session_schema: {exc}") from exc

    def revoke_record_session(self, session: _RetiredParentSideEffectSessionReceipt) -> None:
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID,
            "v1_session_api_rejected: use _SupervisorIssuer.revoke_drain_child",
        )

        """Atomically revoke a session and wait for durable leases to drain."""
        session.close()
        # A direct public adapter may be unwinding on the same thread after a
        # failed composite effect.  Release only leases owned by this thread;
        # leases admitted by another thread remain in the drain protocol and
        # preserve the concurrent-writer linearization guarantee.
        for lease in tuple(_LOCAL_LEASES.get(session.handle, ())):
            if lease.owner_thread_id == threading.get_ident():
                lease.close()
        try:
            validated = self._validate_record_session(
                cwd=session.parent_root,
                env={
                    SIDE_EFFECT_PARENT_ROOT_ENV: str(session.parent_root),
                    SIDE_EFFECT_HANDOFF_ENV: session.handle,
                    SIDE_EFFECT_REQUIRED_ENV: "1",
                },
                operation_purpose="revoke",
                hold_lease=False,
            )
        except ParentRootSideEffectError as exc:
            if "session_revoked" in exc.detail or "session_expired" in exc.detail:
                return
            raise
        _, state_path, lock_path = _session_paths(validated.parent_root, validated.record_id, validated.session_id)
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            state = _read_session_state(state_path)
            if state.get("status") != "revoked":
                _atomic_private_json(state_path, _make_session_state({key: state[key] for key in _SESSION_FIELDS}, status="revoked", revoked_at=time.monotonic()))
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        # Drain leases that linearized before revoke.  A writer that has not
        # acquired its shared lease is rejected by the state lock above.
        lease_dir = validated.state_path.parent / "leases"
        try:
            lease_info = lease_dir.stat(follow_symlinks=False)
            if not stat.S_ISDIR(lease_info.st_mode) or _physical(lease_dir, strict=True) != lease_dir:
                raise ParentRootSideEffectError(
                    ParentRootReject.SYMLINK_ESCAPE,
                    "session lease directory is not a private directory",
                )
        except FileNotFoundError:
            lease_dir.mkdir(mode=0o700)
            os.chmod(lease_dir, 0o700)
        cleanup_errors: list[str] = []
        for lease_lock_path in tuple(lease_dir.glob("*.lock")):
            try:
                lease_fd = os.open(lease_lock_path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            except OSError as exc:
                cleanup_errors.append(str(exc))
                continue
            try:
                fcntl.flock(lease_fd, fcntl.LOCK_EX)
                lease_lock_path.with_suffix(".json").unlink(missing_ok=True)
                lease_lock_path.unlink(missing_ok=True)
            except OSError as exc:
                cleanup_errors.append(str(exc))
            finally:
                os.close(lease_fd)
        if cleanup_errors:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"session lease drain failed: {'; '.join(cleanup_errors)}",
            )
        if state_path.exists():
            update_fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                fcntl.flock(update_fd, fcntl.LOCK_EX)
                state = _read_session_state(state_path)
                state["active_leases"] = len(tuple(lease_dir.glob("*.json")))
                _atomic_private_json(state_path, state)
            finally:
                fcntl.flock(update_fd, fcntl.LOCK_UN)
                os.close(update_fd)

    def recover_stale_record_sessions(self, parent_root: Path) -> int:
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID,
            "v1_session_api_rejected: use recover_v2_stale_sessions",
        )

        """Recover stale sessions/leases without following untrusted links."""
        root = _physical(parent_root, strict=True)
        recovered_v2 = recover_v2_stale_sessions(root)
        sessions_root = root / ".agent-canon" / "runtime" / "side-effect-sessions"
        try:
            sessions_info = sessions_root.stat(follow_symlinks=False)
        except OSError:
            return recovered_v2
        if not stat.S_ISDIR(sessions_info.st_mode) or _physical(sessions_root, strict=True) != sessions_root:
            return recovered_v2
        recovered = recovered_v2
        sessions_fd = -1
        try:
            sessions_fd, _ = _open_components(
                root,
                (".agent-canon", "runtime", "side-effect-sessions"),
                create=False,
            )
            records = tuple(os.listdir(sessions_fd))
        except (OSError, ParentRootSideEffectError):
            return 0
        finally:
            if sessions_fd >= 0:
                os.close(sessions_fd)
        for record_id in records:
            if not _SESSION_ID_RE.fullmatch(record_id):
                continue
            record_dir = sessions_root / record_id
            try:
                record_info = record_dir.stat(follow_symlinks=False)
            except OSError:
                continue
            if not stat.S_ISDIR(record_info.st_mode):
                continue
            record_fd = -1
            try:
                record_fd, _ = _open_components(
                    root,
                    (".agent-canon", "runtime", "side-effect-sessions", record_id),
                    create=False,
                )
                session_ids = tuple(os.listdir(record_fd))
            except (OSError, ParentRootSideEffectError):
                continue
            finally:
                if record_fd >= 0:
                    try:
                        os.close(record_fd)
                    except OSError:
                        pass
                    record_fd = -1
            for session_id in session_ids:
                if not _SESSION_ID_RE.fullmatch(session_id):
                    continue
                base, state_path, _ = _session_paths(root, record_id, session_id)
                session_fd = -1
                lease_dir_fd = -1
                try:
                    session_info = base.stat(follow_symlinks=False)
                    if not stat.S_ISDIR(session_info.st_mode):
                        continue
                    session_fd, _ = _open_components(
                        root,
                        (".agent-canon", "runtime", "side-effect-sessions", record_id, session_id),
                        create=False,
                    )
                    state_info = os.stat("state.json", dir_fd=session_fd, follow_symlinks=False)
                    if not stat.S_ISREG(state_info.st_mode):
                        continue
                    if _physical(base, strict=True) != base or _physical(state_path, strict=True) != state_path:
                        continue
                    state = _read_session_state_fd(session_fd)
                    if state.get("record_id") != record_id or state.get("session_id") != session_id:
                        continue
                    lock_fd = os.open(
                        "session.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                        dir_fd=session_fd,
                    )
                    try:
                        try:
                            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            continue
                        lease_dir_fd = -1
                        try:
                            lease_dir_fd = os.open(
                                "leases",
                                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=session_fd,
                            )
                        except FileNotFoundError:
                            lease_names: tuple[str, ...] = ()
                        else:
                            lease_names = tuple(os.listdir(lease_dir_fd))
                        lease_busy = False
                        for lease_name in lease_names:
                            if not lease_name.endswith(".json"):
                                continue
                            lock_name = f"{lease_name[:-5]}.lock"
                            if lease_dir_fd < 0:
                                continue
                            lease_fd = os.open(
                                lock_name,
                                os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=lease_dir_fd,
                            )
                            try:
                                try:
                                    fcntl.flock(lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                                except BlockingIOError:
                                    lease_busy = True
                                    continue
                                os.unlink(lease_name, dir_fd=lease_dir_fd)
                                os.unlink(lock_name, dir_fd=lease_dir_fd)
                                recovered += 1
                            finally:
                                os.close(lease_fd)
                        if lease_busy:
                            continue
                        state_map = dict(state)
                        expires_at = cast(str | int | float, state_map.get("expires_at", 0))
                        if float(expires_at) < time.monotonic():
                            state_map["status"] = "revoked"
                            state_map["revoked_at"] = time.monotonic()
                        state_map["active_leases"] = sum(
                            1 for name in lease_names if name.endswith(".json")
                        )
                        _atomic_private_json_at(session_fd, "state.json", state_map)
                    finally:
                        fcntl.flock(lock_fd, fcntl.LOCK_UN)
                        os.close(lock_fd)
                        if lease_dir_fd >= 0:
                            os.close(lease_dir_fd)
                except (OSError, ValueError, TypeError, KeyError, ParentRootSideEffectError):
                    continue
                finally:
                    if session_fd >= 0:
                        os.close(session_fd)
        return recovered

    def _handoff(self, token: str | None, *, request: ParentRootAttestationRequest,
                 parent_root: Path, source_root: Path | None,
                 clone_root: Path | None,
                 consume_nonce: bool = True) -> ChildHandoffReceipt | None:
        if token is None:
            return None
        payload, raw_token = _decode_envelope(token)
        required = {"token_version", "audience", "parent_root", "source_root", "clone_root",
                    "issued_at", "expires_at", "nonce", "payload_sha256", "storage", "mode",
                    "validation", "transport"}
        if set(payload) != required or payload.get("token_version") != SCHEMA_HANDOFF:
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "handoff fields are incomplete")
        if (payload.get("storage") not in _ALLOWED_STORAGE or payload.get("mode") not in _ALLOWED_MODES
                or payload.get("transport") not in _ALLOWED_TRANSPORTS
                or payload.get("validation") != "hmac-single-use"):
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID,
                                            "handoff transport/storage/mode validation is invalid")
        transport = payload["transport"]
        expected_storage = "parent-local-file" if transport == "parent-local-file" else "pipe"
        expected_mode = "0600" if transport == "parent-local-file" else "pipe"
        if payload["storage"] != expected_storage or payload["mode"] != expected_mode:
            raise ParentRootSideEffectError(
                ParentRootReject.HANDOFF_INVALID,
                "handoff transport storage and mode do not agree",
            )
        if (
            not isinstance(payload["audience"], str)
            or not payload["audience"]
            or not isinstance(payload["parent_root"], str)
            or not payload["parent_root"]
            or any(
                value is not None and (not isinstance(value, str) or not value)
                for value in (payload["source_root"], payload["clone_root"])
            )
            or not isinstance(payload["nonce"], str)
            or not payload["nonce"]
            or not isinstance(payload["payload_sha256"], str)
            or not _is_digest(payload["payload_sha256"])
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in (payload["issued_at"], payload["expires_at"])
            )
        ):
            raise ParentRootSideEffectError(
                ParentRootReject.HANDOFF_INVALID,
                "handoff value types are invalid",
            )
        root = parent_root
        try:
            expected = hmac.new(_session_secret(root, create=False), _canonical_bytes(payload), hashlib.sha256).hexdigest()
            envelope = base64.urlsafe_b64decode(token.encode("ascii"))
            observed = json.loads(envelope.decode("utf-8"))["signature"]
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, f"handoff authentication failed: {exc}") from exc
        if not isinstance(observed, str) or not hmac.compare_digest(expected, observed):
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "handoff signature mismatch")
        now = time.monotonic()
        issued_value, expires_value = payload["issued_at"], payload["expires_at"]
        nonce_value = payload["nonce"]
        if (
            isinstance(issued_value, bool)
            or not isinstance(issued_value, (int, float))
            or isinstance(expires_value, bool)
            or not isinstance(expires_value, (int, float))
        ):
            raise ParentRootSideEffectError(
                ParentRootReject.HANDOFF_INVALID, "handoff timestamp or nonce type changed"
            )
        issued, expires, nonce = float(issued_value), float(expires_value), nonce_value
        if not issued <= now <= expires:
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "handoff expired or not yet valid")
        if payload["audience"] != request.purpose or _physical(Path(str(payload["parent_root"])), strict=True) != root:
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "handoff audience or root mismatch")
        for key, expected_path in (("source_root", source_root), ("clone_root", clone_root)):
            token_path = payload[key]
            if expected_path is None:
                if token_path is not None:
                    raise ParentRootSideEffectError(
                        ParentRootReject.HANDOFF_INVALID,
                        f"handoff {key} unexpectedly binds a path",
                    )
            elif token_path is None or _physical(Path(str(token_path)), strict=True) != _physical(expected_path, strict=True):
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, f"handoff {key} mismatch")
        body = {k: v for k, v in payload.items() if k != "payload_sha256"}
        if payload["payload_sha256"] != _sha256(_canonical_bytes(body)):
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "handoff payload digest mismatch")
        fd, state = _locked_state(root, create=False)
        try:
            if nonce not in state:
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "unknown or replayed handoff nonce")
            if state[nonce] < now:
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "handoff nonce expired")
            if consume_nonce:
                del state[nonce]
                _write_locked_state(fd, state)
        finally:
            _close_state(fd)
        return ChildHandoffReceipt(str(payload["token_version"]), str(payload["audience"]), root,
                                   source_root, clone_root, issued, expires, nonce,
                                   str(payload["payload_sha256"]), str(payload["storage"]),
                                   str(payload["mode"]), str(payload["validation"]),
                                   str(payload["transport"]), raw_token)

    def attest(self, request: ParentRootAttestationRequest) -> ParentRootAttestationReceipt:
        """Authenticate the selected Git toplevel and all optional identities."""
        if sys.platform != "linux":
            raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform)
        cwd = _physical(Path(request.cwd), strict=True)
        explicit = _physical(request.explicit_root, strict=True) if request.explicit_root else None
        if explicit is not None:
            if not explicit.is_dir() or not _contains(explicit, cwd):
                raise ParentRootSideEffectError(ParentRootReject.ROOT_SPOOFED, f"cwd is outside explicit root: {cwd}")
            root = explicit
            precedence = "explicit-git"
            try:
                explicit_git = _git_toplevel(root)
            except ParentRootSideEffectError as exc:
                if exc.reject is ParentRootReject.ROOT_MISSING:
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_MISMATCH,
                        "explicit root is not an authenticated Git checkout",
                    ) from exc
                raise
            if explicit_git != root:
                raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH, "explicit root is not Git toplevel")
            git_cwd = _git_toplevel(cwd)
            if git_cwd != root:
                raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH, "cwd Git identity differs from explicit root")
        else:
            git_cwd = _git_toplevel(cwd)
            root = git_cwd
            precedence = "resolver"
        parent_dev, parent_ino = _identity(root)
        source = _physical(request.source_root, strict=True) if request.source_root else None
        clone = _physical(request.clone_root, strict=True) if request.clone_root else None
        for label, path in (("source", source), ("clone", clone)):
            if path is None:
                continue
            if not _contains(root, path):
                raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH, f"{label} root is outside parent root")
            if _git_toplevel(path) != path:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_MISMATCH,
                    f"{label} is not an authenticated Git checkout: {path}",
                )
        if source is not None and clone is not None and source == clone:
            raise ParentRootSideEffectError(ParentRootReject.ROOT_AMBIGUOUS, "source and clone roots are identical")
        # An outer parent is admitted only with all three authenticated binding files.
        if clone is not None and any(x is None for x in (request.topic_marker, request.gitmodules, request.owner_evidence)):
            raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH, "topic clone relation lacks marker/module/owner evidence")
        marker = _read_bound_file(root, request.topic_marker, ParentRootReject.MARKER_INVALID)
        module = _read_bound_file(root, request.gitmodules, ParentRootReject.MODULE_INVALID)
        owner = _read_bound_file(root, request.owner_evidence, ParentRootReject.OWNER_EVIDENCE_INVALID)
        if source is not None and module is not None and request.gitmodules is not None:
            module = _module_binding(root, _physical(request.gitmodules, strict=True), source,
                                     ParentRootReject.MODULE_INVALID)
        if clone is not None and marker is not None and module is not None and owner is not None:
            if source is None:
                raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH,
                                                "topic relation lacks an authenticated source root")
            _git_identity(clone, ParentRootReject.MARKER_INVALID)
            source_commit, source_tree = _git_identity(source, ParentRootReject.MODULE_INVALID)
            actual_branch = _git_value(clone, "symbolic-ref", "--short", "HEAD",
                                       reject=ParentRootReject.MARKER_INVALID)
            actual_clone_remote = _git_origin(clone)
            gitmodules = request.gitmodules
            owner_evidence = request.owner_evidence
            if gitmodules is None or owner_evidence is None:
                raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH,
                                                "topic relation binding files disappeared")
            actual_module = _module_binding(root, _physical(gitmodules, strict=True), source,
                                            ParentRootReject.MODULE_INVALID)
            if _normalize_remote(str(actual_module["url"])) != _normalize_remote(_git_origin(source)):
                raise ParentRootSideEffectError(ParentRootReject.MODULE_INVALID,
                                                "module URL does not match source Git origin")
            if (actual_module["observed_commit"] != source_commit
                    or actual_module["observed_tree"] != source_tree):
                raise ParentRootSideEffectError(ParentRootReject.MODULE_INVALID,
                                                "module observed commit/tree changed during attestation")
            owner_map = owner
            marker_map = marker
            marker_checks = {
                "parent_repo_id": _parent_repo_id(root),
                "clone_path": str(clone), "repo_name": clone.name,
                "topic_slug": clone.parent.name, "branch": actual_branch,
                "remote_url": actual_clone_remote, "source_commit": source_commit,
                "source_tree": source_tree,
            }
            for key, expected in marker_checks.items():
                if str(marker_map.get(key, "")).rstrip("/") != str(expected).rstrip("/"):
                    raise ParentRootSideEffectError(ParentRootReject.MARKER_INVALID,
                                                    f"marker {key} does not match observed identity")
            owner_raw_sha = _raw_digest(_physical(owner_evidence, strict=True))
            if not _is_digest(marker_map.get("owner_evidence_sha256")) or str(marker_map.get("owner_evidence_sha256")) != owner_raw_sha:
                raise ParentRootSideEffectError(ParentRootReject.OWNER_EVIDENCE_INVALID,
                                                "marker owner evidence digest does not match raw evidence")
            owner_checks = {
                "parent_repo_id": _parent_repo_id(root),
                "physical_parent": str(root), "module_path": actual_module["module_path"],
                "remote_url": _git_origin(root), "observed_commit": source_commit,
                "observed_tree": source_tree,
            }
            for key, expected in owner_checks.items():
                if str(owner_map.get(key, "")) != str(expected):
                    raise ParentRootSideEffectError(ParentRootReject.OWNER_EVIDENCE_INVALID,
                                                    f"owner evidence {key} does not match observed identity")
            evidence_without_digest = {key: value for key, value in owner_map.items() if key != "evidence_sha256"}
            expected_evidence_digest = _sha256(_canonical_bytes(evidence_without_digest))
            if not _is_digest(owner_map.get("evidence_sha256")) or str(owner_map.get("evidence_sha256")) != expected_evidence_digest:
                raise ParentRootSideEffectError(ParentRootReject.OWNER_EVIDENCE_INVALID,
                                                "owner evidence digest does not match canonical body")
            module = actual_module
        if request.expected_module_digest:
            if (not _is_digest(request.expected_module_digest) or module is None
                    or str(module.get("sha256", "")) != request.expected_module_digest):
                raise ParentRootSideEffectError(ParentRootReject.MODULE_INVALID, "module digest missing or mismatched")
        if request.expected_remote:
            if _normalize_remote(_git_origin(root)) != _normalize_remote(request.expected_remote):
                raise ParentRootSideEffectError(ParentRootReject.MARKER_INVALID, "expected remote does not match Git origin")
        handoff = self._handoff(request.child_handoff_token, request=request,
                                parent_root=root, source_root=source, clone_root=clone)
        if _identity(root) != (parent_dev, parent_ino):
            raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED, "parent identity changed during attestation")
        kind = ("topic" if clone is not None else
                ("vendored" if source and source.name == "agent-canon" else
                 ("direct" if request.explicit_root is not None else "standalone")))
        return ParentRootAttestationReceipt(root, parent_dev, parent_ino, source, clone, kind,
                                            precedence, marker, module, owner, handoff, "attested",
                                            token_digest=_sha256(request.child_handoff_token.encode()) if request.child_handoff_token else "",
                                            purpose=request.purpose)

    def resolve_parent_owned_path(
        self,
        attestation: SessionResolutionResult | ParentRootAttestationReceipt,
                                  candidate: Path | str, purpose: str, *, create: bool = False) -> ParentOwnedPathReceipt:
        """Resolve a capability path after revalidating its parent session."""
        if isinstance(attestation, SessionResolutionResult):
            if attestation.status != "active":
                attestation.close()
                raise _v2_error("session_revoked")
            attestation = attestation.attestation
        if isinstance(attestation, _RetiredParentSideEffectSessionReceipt):
            raise ParentRootSideEffectError(
                ParentRootReject.HANDOFF_INVALID,
                "v1_session_api_rejected: resolve a SessionResolutionResult",
            )
        if attestation.session_handle:
            channel_parent = _v2_handoff_parent_root(attestation.session_handle)
            refreshed = resolve_parent_side_effect_session_v2(
                observed_cwd=_physical(attestation.parent_root, strict=True),
                env={
                    SIDE_EFFECT_PARENT_ROOT_ENV: str(channel_parent),
                    SIDE_EFFECT_HANDOFF_ENV: attestation.session_handle,
                    SIDE_EFFECT_REQUIRED_ENV: "1",
                },
            )
            self._release_operation_lease(attestation.session_lease)
            attestation = refreshed.attestation
        if attestation.status != "attested":
            self._release_operation_lease(attestation.session_lease)
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "attestation is not active")
        root = attestation.parent_root
        try:
            physical, _ = _physical_in_root(root, candidate, allow_missing=True)
        except Exception:
            self._release_operation_lease(attestation.session_lease)
            raise
        if create:
            try:
                parent_fd, name, _ = _parent_directory(root, physical, create=True)
            except Exception:
                self._release_operation_lease(attestation.session_lease)
                raise
            try:
                try:
                    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent_fd)
                    os.close(fd)
                except FileExistsError:
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
                    os.close(fd)
            except OSError as exc:
                self._release_operation_lease(attestation.session_lease)
                raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED, f"cannot create target: {exc}") from exc
            finally:
                os.close(parent_fd)
            try:
                physical, _ = _physical_in_root(root, candidate, allow_missing=False)
            except Exception:
                self._release_operation_lease(attestation.session_lease)
                raise
        # Open every existing physical component once.  A missing parent is
        # permitted for a later atomic create; publication will create it by
        # dirfd before opening the final component.
        try:
            parent_fd, _, _ = _parent_directory(root, physical, create=False)
        except ParentRootSideEffectError as exc:
            if exc.reject is not ParentRootReject.ROOT_MISSING:
                self._release_operation_lease(attestation.session_lease)
                raise
            parent_components: tuple[tuple[str, int, int], ...] = ()
        else:
            try:
                os.close(parent_fd)
                parent_components = _component_identities(
                    root, tuple(physical.relative_to(root).parts)[:-1], create=False
                )
            except Exception:
                self._release_operation_lease(attestation.session_lease)
                raise
        try:
            if _identity(root) != (attestation.parent_dev, attestation.parent_ino):
                raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED, "parent identity changed")
            lexical = _lexical_candidate(root, candidate)
        except Exception:
            self._release_operation_lease(attestation.session_lease)
            raise
        target = None
        try:
            info = physical.stat()
            target = (info.st_dev, info.st_ino)
        except FileNotFoundError:
            pass
        except OSError:
            self._release_operation_lease(attestation.session_lease)
            raise
        receipt = ParentOwnedPathReceipt(
            lexical,
            physical,
            purpose,
            attestation.parent_dev,
            attestation.parent_ino,
            attestation.token_digest,
            root,
            *(target or (None, None)),
            parent_components,
            session_lease=attestation.session_lease,
            session_handle=attestation.session_handle,
        )
        try:
            return replace(receipt, **_lexical_snapshot(root, lexical))
        except ParentRootSideEffectError as exc:
            if exc.reject is not ParentRootReject.ROOT_MISSING:
                self._release_operation_lease(attestation.session_lease)
                raise
        return receipt

    def _refresh_attestation(
        self, attestation: ParentRootAttestationReceipt, purpose: str
    ) -> ParentRootAttestationReceipt:
        """Revalidate a session-backed attestation before a direct operation."""
        if attestation.session_handle:
            # A v2 resolution lease owns the session lock used by the next
            # resolution.  Release the consumed lease before opening its
            # replacement; resolving first would self-deadlock every effect
            # that receives the SessionResolutionResult attestation directly.
            self._release_operation_lease(attestation.session_lease)
            channel_parent = _v2_handoff_parent_root(attestation.session_handle)
            refreshed = resolve_parent_side_effect_session_v2(
                observed_cwd=_physical(attestation.parent_root, strict=True),
                env={
                    SIDE_EFFECT_PARENT_ROOT_ENV: str(channel_parent),
                    SIDE_EFFECT_HANDOFF_ENV: attestation.session_handle,
                    SIDE_EFFECT_REQUIRED_ENV: "1",
                },
            ).attestation
            return refreshed
        return attestation

    @staticmethod
    def _release_operation_lease(lease: ParentSideEffectLease | _V2Lease | None) -> None:
        """Release a session lease after the effect-level operation completes."""
        if lease is not None:
            lease.close()

    def release_parent_owned_path(self, receipt: ParentOwnedPathReceipt) -> None:
        """Release a path-resolution lease when no effect consumes the receipt."""
        self._release_operation_lease(receipt.session_lease)

    def _revalidate_path_session(
        self, receipt: ParentOwnedPathReceipt, purpose: str
    ) -> ParentOwnedPathReceipt:
        """Revalidate a path handle immediately before its effect-level operation."""
        if not receipt.session_handle:
            return receipt
        env = {
            SIDE_EFFECT_PARENT_ROOT_ENV: str(_v2_handoff_parent_root(receipt.session_handle)),
            SIDE_EFFECT_HANDOFF_ENV: receipt.session_handle,
            SIDE_EFFECT_REQUIRED_ENV: "1",
        }
        if receipt.session_lease is not None and not receipt.session_lease.closed:
            # The shared lease is the operation's linearization proof.  A
            # revoke may mark the state revoked before waiting for this lease;
            # re-reading that status here would reject the already-admitted
            # operation and leave revoke waiting forever.
            return receipt
        try:
            decoded_value: object = json.loads(
                base64.urlsafe_b64decode(receipt.session_handle.encode("ascii")).decode("utf-8")
            )
            decoded: Mapping[str, object] = (
                cast(Mapping[str, object], decoded_value) if type(decoded_value) is dict else {}
            )
            record_value: object = decoded.get("record")
            record_mapping: Mapping[str, object] = (
                cast(Mapping[str, object], record_value) if type(record_value) is dict else {}
            )
            if record_mapping.get("schema") == SCHEMA_SESSION_RECORD_V2:
                resolved = resolve_parent_side_effect_session_v2(
                    env=env, observed_cwd=_physical(receipt.parent_root, strict=True)
                )
                return replace(receipt, session_lease=resolved.lease)
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            pass
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID,
            "v1_session_api_rejected: path receipt is not a v2 handoff",
        )

    def ensure_parent_owned_directory(self, attestation: ParentRootAttestationReceipt,
                                      candidate: Path | str, purpose: str) -> ParentOwnedPathReceipt:
        """Create and re-open a parent-local directory through component dirfds."""
        attestation = self._refresh_attestation(attestation, purpose)
        try:
            if attestation.status != "attested":
                raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "attestation is not active")
            physical, parts = _physical_in_root(attestation.parent_root, candidate, allow_missing=True)
            directory_fd, _ = _open_components(attestation.parent_root, parts, create=True)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            physical, _ = _physical_in_root(attestation.parent_root, candidate, allow_missing=False)
            if _identity(attestation.parent_root) != (attestation.parent_dev, attestation.parent_ino):
                raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED, "parent identity changed")
            info = physical.stat()
            parent_components = _component_identities(
                attestation.parent_root, parts[:-1], create=False
            )
            lexical = _lexical_candidate(attestation.parent_root, candidate)
            receipt = ParentOwnedPathReceipt(
                lexical,
                physical,
                purpose,
                attestation.parent_dev,
                attestation.parent_ino,
                attestation.token_digest,
                attestation.parent_root,
                info.st_dev,
                info.st_ino,
                parent_components,
                session_lease=attestation.session_lease,
            )
            result = replace(receipt, **_lexical_snapshot(attestation.parent_root, lexical), session_lease=None)
        except Exception:
            self._release_operation_lease(attestation.session_lease)
            raise
        self._release_operation_lease(attestation.session_lease)
        return result

    def open_parent_owned_file(
        self,
        attestation: ParentRootAttestationReceipt,
        candidate: Path | str,
        purpose: str,
        *,
        create: bool,
        mode: str,
    ) -> ParentOwnedFileHandle:
        """Open and lock a receipt-bound ``a+`` or ``r+`` file without a path race."""
        attestation = self._refresh_attestation(attestation, purpose)
        if sys.platform != "linux":
            self._release_operation_lease(attestation.session_lease)
            raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform)
        if mode not in {"a+", "r+"}:
            self._release_operation_lease(attestation.session_lease)
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                f"unsupported parent-owned file mode: {mode}",
            )
        if mode == "r+" and create:
            self._release_operation_lease(attestation.session_lease)
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                "r+ parent-owned files cannot create a missing target",
            )
        if mode == "a+" and not create:
            self._release_operation_lease(attestation.session_lease)
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                "a+ parent-owned files require create=True",
            )
        root = attestation.parent_root
        try:
            physical, _ = _physical_in_root(root, candidate, allow_missing=create)
            parent_fd, name, _ = _parent_directory(root, physical, create=create)
        except Exception:
            self._release_operation_lease(attestation.session_lease)
            raise
        target_fd = -1
        handle: ParentOwnedFileHandle | None = None
        created = False
        created_info: os.stat_result | None = None
        before = (attestation.parent_dev, attestation.parent_ino)
        try:
            if _identity(root) != before:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "parent identity changed before file open",
                )
            try:
                existing = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
            if mode == "a+":
                flags |= os.O_APPEND | os.O_CREAT
            try:
                target_fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
            except FileNotFoundError as exc:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_MISSING,
                    f"parent-owned file does not exist: {physical}",
                ) from exc
            except OSError as exc:
                reject = (
                    ParentRootReject.SYMLINK_ESCAPE
                    if exc.errno in {errno.ELOOP, errno.ENOTDIR}
                    else ParentRootReject.ROOT_RACE_DETECTED
                )
                raise ParentRootSideEffectError(
                    reject, f"cannot open parent-owned file: {exc}"
                ) from exc
            created = existing is None and mode == "a+"
            info = os.fstat(target_fd)
            created_info = info if created else None
            if not stat.S_ISREG(info.st_mode):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_MISMATCH,
                    f"parent-owned target is not a regular file: {physical}",
                )
            if existing is not None and (info.st_dev, info.st_ino) != (
                existing.st_dev,
                existing.st_ino,
            ):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "parent-owned file identity changed during open",
                )
            if _identity(root) != before:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "parent identity changed after file open",
                )
            while True:
                try:
                    fcntl.flock(target_fd, fcntl.LOCK_EX)
                    break
                except InterruptedError:
                    continue
                except OSError as exc:
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_RACE_DETECTED,
                        f"cannot lock parent-owned file: {exc}",
                    ) from exc
            stream = cast(
                TextIO,
                os.fdopen(target_fd, mode, encoding="utf-8", newline=""),
            )
            target_fd = -1
            handle = ParentOwnedFileHandle(
                stream=stream,
                physical_path=physical,
                purpose=purpose,
                target_dev=info.st_dev,
                target_ino=info.st_ino,
                session_lease=attestation.session_lease,
            )
            os.close(parent_fd)
            parent_fd = -1
            return handle
        except Exception as exc:
            cleanup_errors: list[OSError] = []
            if handle is not None:
                try:
                    handle.close()
                except ParentRootSideEffectError as cleanup_error:
                    cleanup_errors.append(OSError(str(cleanup_error)))
            if target_fd >= 0:
                try:
                    fcntl.flock(target_fd, fcntl.LOCK_UN)
                except OSError as cleanup_error:
                    cleanup_errors.append(cleanup_error)
                try:
                    os.close(target_fd)
                except OSError as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            if created and created_info is not None:
                try:
                    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    if current.st_dev == created_info.st_dev and current.st_ino == created_info.st_ino:
                        os.unlink(name, dir_fd=parent_fd)
                        os.fsync(parent_fd)
                except OSError as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            try:
                if parent_fd >= 0:
                    os.close(parent_fd)
            except OSError as cleanup_error:
                cleanup_errors.append(cleanup_error)
            if handle is None:
                self._release_operation_lease(attestation.session_lease)
            if cleanup_errors:
                detail = "; ".join(str(error) for error in cleanup_errors)
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"{exc}; parent-owned file rollback failed: {detail}",
                ) from exc
            if isinstance(exc, ParentRootSideEffectError):
                raise
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"cannot open parent-owned file: {exc}",
            ) from exc

    def create_parent_owned_temp_directory(
        self,
        attestation: ParentRootAttestationReceipt,
        candidate: Path | str,
        purpose: str,
        prefix: str,
    ) -> ParentOwnedPathReceipt:
        """Create one unpredictable child directory beneath an owned directory."""
        if not prefix or "/" in prefix or "\\" in prefix or prefix in {".", ".."}:
            self._release_operation_lease(attestation.session_lease)
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH, "temporary-directory prefix is invalid"
            )
        base = self.ensure_parent_owned_directory(attestation, candidate, purpose)
        base_lease = base.session_lease
        parent_fd = -1
        try:
            parent_fd, _ = _open_components(
                attestation.parent_root,
                tuple(base.physical_path.relative_to(attestation.parent_root).parts),
                create=False,
            )
            for _ in range(32):
                name = f"{prefix}.{secrets.token_hex(12)}"
                try:
                    os.mkdir(name, 0o700, dir_fd=parent_fd)
                except FileExistsError:
                    continue
                os.fsync(parent_fd)
                info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode):
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_RACE_DETECTED,
                        "temporary target is not a directory",
                    )
                physical = base.physical_path / name
                if _identity(attestation.parent_root) != (
                    attestation.parent_dev,
                    attestation.parent_ino,
                ):
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_RACE_DETECTED,
                        "parent identity changed during temporary-directory creation",
                    )
                parent_components = _component_identities(
                    attestation.parent_root,
                    tuple(physical.relative_to(attestation.parent_root).parts)[:-1],
                    create=False,
                )
                receipt = replace(
                    base,
                    lexical_path=base.lexical_path / name,
                    physical_path=physical,
                    target_dev=info.st_dev,
                    target_ino=info.st_ino,
                    parent_components=parent_components,
                    session_lease=None,
                )
                return replace(
                    receipt,
                    **_lexical_snapshot(
                        attestation.parent_root, receipt.lexical_path
                    ),
                )
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                "could not allocate an exclusive temporary directory",
            )
        finally:
            if parent_fd >= 0:
                os.close(parent_fd)
            self._release_operation_lease(base_lease)

    def open_parent_owned_target(self, attestation: ParentRootAttestationReceipt,
                                 candidate: Path | str, purpose: str) -> ParentOwnedTargetHandle:
        """Reserve and open an empty directory without a parent-fd/name gap.

        The final directory is created with mkdirat semantics and then kept open
        while Git runs.  The child receives the inherited target fd itself;
        resolving a parent fd plus a pathname in the child would reintroduce a
        replacement race between attestation and clone.
        """
        attestation = self._refresh_attestation(attestation, purpose)
        if sys.platform != "linux":
            self._release_operation_lease(attestation.session_lease)
            raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform)
        try:
            physical, _ = _physical_in_root(attestation.parent_root, candidate, allow_missing=True)
            parent_fd, name, _ = _parent_directory(attestation.parent_root, physical, create=True)
        except Exception:
            self._release_operation_lease(attestation.session_lease)
            raise
        target_fd = -1
        reserved = False
        before = (attestation.parent_dev, attestation.parent_ino)
        try:
            if _identity(attestation.parent_root) != before:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "parent identity changed before target reservation",
                )
            try:
                os.mkdir(name, 0o700, dir_fd=parent_fd)
            except FileExistsError as exc:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"clone target already exists: {physical}",
                ) from exc
            reserved = True
            target_fd = os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
            info = os.fstat(target_fd)
            if not stat.S_ISDIR(info.st_mode) or os.listdir(target_fd):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "reserved clone target is not an empty directory",
                )
            if _identity(attestation.parent_root) != before:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "parent identity changed after target reservation",
                )
            os.fsync(parent_fd)
            parent_info = os.fstat(parent_fd)
            return ParentOwnedTargetHandle(
                parent_fd=parent_fd,
                target_fd=target_fd,
                physical_path=physical,
                purpose=purpose,
                target_dev=info.st_dev,
                target_ino=info.st_ino,
                parent_name=name,
                parent_dev=parent_info.st_dev,
                parent_ino=parent_info.st_ino,
                session_lease=attestation.session_lease,
            )
        except Exception as exc:
            cleanup_errors: list[OSError] = []
            if target_fd >= 0:
                try:
                    os.close(target_fd)
                except OSError as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            if reserved:
                try:
                    os.rmdir(name, dir_fd=parent_fd)
                    os.fsync(parent_fd)
                except OSError as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            try:
                os.close(parent_fd)
            except OSError as cleanup_error:
                cleanup_errors.append(cleanup_error)
            self._release_operation_lease(attestation.session_lease)
            if cleanup_errors:
                detail = "; ".join(str(error) for error in cleanup_errors)
                message = f"{exc}; clone-target rollback cleanup failed: {detail}"
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED, message
                ) from exc
            if isinstance(exc, ParentRootSideEffectError):
                raise
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"cannot reserve clone target: {exc}",
            ) from exc

    def _abort_reserved_target(
        self,
        attestation: ParentRootAttestationReceipt,
        handle: ParentOwnedTargetHandle,
        purpose: str,
    ) -> None:
        """Remove only the exact target reserved by an open target handle."""
        if sys.platform != "linux":
            raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform)
        try:
            if handle.parent_fd < 0 or handle.target_fd < 0:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"reserved-target handle is closed ({purpose})",
                )
            parent_info = os.fstat(handle.parent_fd)
            if (parent_info.st_dev, parent_info.st_ino) != (
                handle.parent_dev,
                handle.parent_ino,
            ):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"reserved-target parent identity changed ({purpose})",
                )
            observed = os.fstat(handle.target_fd)
            if (observed.st_dev, observed.st_ino) != (
                handle.target_dev,
                handle.target_ino,
            ):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"reserved-target identity changed ({purpose})",
                )
            parent_fd = handle.parent_fd
            name = handle.parent_name
            target_fd = handle.target_fd
            if _identity(attestation.parent_root) != (
                attestation.parent_dev,
                attestation.parent_ino,
            ):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"parent identity changed before reserved-target abort ({purpose})",
                )
            observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            expected = (handle.target_dev, handle.target_ino)
            if (observed.st_dev, observed.st_ino) != expected:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"reserved-target identity changed before removal ({purpose})",
                )
            opened = os.fstat(target_fd)
            if (opened.st_dev, opened.st_ino) != expected:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"reserved-target open identity changed ({purpose})",
                )
            self._remove_open_tree(target_fd)
            os.rmdir(name, dir_fd=parent_fd)
            os.fsync(parent_fd)
            if _identity(attestation.parent_root) != (
                attestation.parent_dev,
                attestation.parent_ino,
            ):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"parent identity changed during reserved-target abort ({purpose})",
                )
        except OSError as exc:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"cannot abort reserved target ({purpose}): {exc}",
            ) from exc
        finally:
            handle.close()

    def atomic_publish(self, receipt: ParentOwnedPathReceipt, data: bytes) -> ParentOwnedPathReceipt:
        """Publish with same-directory O_EXCL temp, fsync, renameat, and identity checks."""
        if sys.platform != "linux":
            raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform)
        receipt = self._revalidate_path_session(receipt, "atomic-publish")
        root = receipt.parent_root
        try:
            before = _identity(root)
            if before != (receipt.parent_dev, receipt.parent_ino):
                raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED, "parent identity changed before publish")
            if receipt.parent_components:
                _verify_parent_components(receipt)
            physical, _ = _physical_in_root(root, receipt.physical_path, allow_missing=True)
            parent_fd, name, _ = _parent_directory(root, physical, create=True)
        except Exception:
            self._release_operation_lease(receipt.session_lease)
            raise
        if receipt.parent_components:
            _verify_parent_components(receipt)
        else:
            receipt = replace(
                receipt,
                parent_components=_component_identities(
                    root, tuple(physical.relative_to(root).parts)[:-1], create=False
                ),
            )
        temporary = f".{name}.{secrets.token_hex(12)}.tmp"
        temp_fd = -1
        primary_error: Exception | None = None
        try:
            temp_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent_fd)
            _write_all(temp_fd, data)
            os.fsync(temp_fd)
            os.close(temp_fd)
            temp_fd = -1
            if _identity(root) != before:
                raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED, "parent identity changed before rename")
            try:
                existing = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            if receipt.target_dev is not None and (
                existing is None
                or (existing.st_dev, existing.st_ino)
                != (receipt.target_dev, receipt.target_ino)
            ):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "publication target identity changed before rename",
                )
            os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.fsync(parent_fd)
            if _identity(root) != before:
                raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED, "parent identity changed after rename")
            observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (observed.st_dev, observed.st_ino) == (0, 0):
                raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED, "published identity is invalid")
            published = replace(
                receipt,
                physical_path=physical,
                target_dev=observed.st_dev,
                target_ino=observed.st_ino,
            )
            return replace(published, **_lexical_snapshot(root, published.lexical_path))
        except ParentRootSideEffectError as exc:
            primary_error = exc
            raise
        except OSError as exc:
            primary_error = ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED, f"atomic publish failed: {exc}"
            )
            raise primary_error from exc
        finally:
            cleanup_errors: list[OSError] = []
            if temp_fd >= 0:
                try:
                    os.close(temp_fd)
                except OSError as exc:
                    cleanup_errors.append(exc)
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            except OSError as exc:
                cleanup_errors.append(exc)
            try:
                os.close(parent_fd)
            except OSError as exc:
                cleanup_errors.append(exc)
            try:
                self._release_operation_lease(receipt.session_lease)
            except (OSError, ParentRootSideEffectError) as exc:
                cleanup_errors.append(OSError(str(exc)))
            if cleanup_errors:
                detail = "; ".join(str(error) for error in cleanup_errors)
                message = f"atomic publish cleanup failed: {detail}"
                if primary_error is not None:
                    message = f"{primary_error}; {message}"
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_RACE_DETECTED, message
                    ) from primary_error
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED, message
                )

    def write_parent_owned_file(
        self,
        attestation: ParentRootAttestationReceipt,
        candidate: Path | str,
        data: bytes,
        purpose: str,
    ) -> ParentOwnedPathReceipt:
        """Atomically publish bytes beneath an already authenticated root."""
        receipt = self.resolve_parent_owned_path(attestation, candidate, purpose)
        return self.atomic_publish(receipt, data)

    def set_parent_owned_mode(
        self,
        attestation: ParentRootAttestationReceipt,
        receipt: ParentOwnedPathReceipt,
        mode: int,
    ) -> ParentOwnedPathReceipt:
        """Apply permission bits through the already authenticated file identity."""
        receipt = self._revalidate_path_session(receipt, "set-parent-owned-mode")
        operation_lease = receipt.session_lease
        if mode & ~0o777:
            self._release_operation_lease(operation_lease)
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                f"unsupported file mode: {mode:o}",
            )
        try:
            _verify_parent_components(receipt)
            parent_fd, name, _ = _parent_directory(
                receipt.parent_root, receipt.physical_path, create=False
            )
        except Exception:
            self._release_operation_lease(operation_lease)
            raise
        target_fd = -1
        try:
            target_fd = os.open(
                name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
            observed = os.fstat(target_fd)
            if (observed.st_dev, observed.st_ino) != (
                receipt.target_dev,
                receipt.target_ino,
            ):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "file identity changed before mode update",
                )
            os.fchmod(target_fd, mode)
            os.fsync(target_fd)
            readback = os.fstat(target_fd)
            if stat.S_IMODE(readback.st_mode) != mode:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "file mode readback differs",
                )
        except ParentRootSideEffectError:
            raise
        except OSError as exc:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"cannot update parent-owned file mode: {exc}",
            ) from exc
        finally:
            if target_fd >= 0:
                os.close(target_fd)
            os.close(parent_fd)
            self._release_operation_lease(operation_lease)
        result = self.resolve_parent_owned_path(
            attestation, receipt.physical_path, receipt.purpose, create=False
        )
        self._release_operation_lease(result.session_lease)
        return replace(result, session_lease=None)

    def publish_parent_owned_file_noreplace(
        self,
        attestation: ParentRootAttestationReceipt,
        candidate: Path | str,
        data: bytes,
        purpose: str,
    ) -> tuple[str, str]:
        """Publish one file without replacing an existing parent-owned target."""
        if sys.platform != "linux":
            self._release_operation_lease(attestation.session_lease)
            raise ParentRootSideEffectError(
                ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform
            )
        receipt = self.resolve_parent_owned_path(attestation, candidate, purpose)
        root = receipt.parent_root
        try:
            before = _identity(root)
            if before != (receipt.parent_dev, receipt.parent_ino):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "parent identity changed before no-replace publication",
                )
            physical, _ = _physical_in_root(root, receipt.physical_path, allow_missing=True)
            parent_fd, name, _ = _parent_directory(root, physical, create=True)
        except Exception:
            self._release_operation_lease(receipt.session_lease)
            raise
        if not receipt.parent_components:
            try:
                receipt = replace(
                    receipt,
                    parent_components=_component_identities(
                        root,
                        tuple(physical.relative_to(root).parts)[:-1],
                        create=False,
                    ),
                )
            except Exception:
                self._release_operation_lease(receipt.session_lease)
                raise
        temporary = f".{name}.{secrets.token_hex(12)}.tmp"
        temp_fd = -1
        primary_error: BaseException | None = None
        try:
            temp_fd = os.open(
                temporary,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | os.O_NOFOLLOW
                | os.O_CLOEXEC,
                0o600,
                dir_fd=parent_fd,
            )
            _write_all(temp_fd, data)
            os.fsync(temp_fd)
            os.close(temp_fd)
            temp_fd = -1
            _verify_parent_components(receipt)
            if _identity(root) != before:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "parent identity changed before no-replace link",
                )
            try:
                os.link(
                    temporary,
                    name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                existing = self.resolve_parent_owned_path(attestation, physical, purpose)
                if existing.target_dev is None:
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_RACE_DETECTED,
                        "no-replace target disappeared during collision readback",
                    )
                if self.read_parent_owned_file(existing) == data:
                    return "duplicate", ""
                return "failed", "spool_conflict"
            os.fsync(parent_fd)
            committed = self.resolve_parent_owned_path(attestation, physical, purpose)
            if committed.target_dev is None or self.read_parent_owned_file(committed) != data:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "no-replace publication readback differs",
                )
            return "spooled", ""
        except ParentRootSideEffectError as exc:
            primary_error = exc
            raise
        except OSError as exc:
            primary_error = ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"no-replace publication failed: {exc}",
            )
            raise primary_error from exc
        finally:
            cleanup_errors: list[OSError] = []
            if temp_fd >= 0:
                try:
                    os.close(temp_fd)
                except OSError as exc:
                    cleanup_errors.append(exc)
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            except OSError as exc:
                cleanup_errors.append(exc)
            try:
                os.close(parent_fd)
            except OSError as exc:
                cleanup_errors.append(exc)
            self._release_operation_lease(receipt.session_lease)
            if cleanup_errors:
                detail = "; ".join(str(error) for error in cleanup_errors)
                cleanup_error = ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"no-replace publication cleanup failed: {detail}",
                )
                if primary_error is not None:
                    raise cleanup_error from primary_error
                raise cleanup_error

    def capture_subprocess(
        self,
        attestation: ParentRootAttestationReceipt,
        candidate: Path | str,
        argv: Sequence[str],
        purpose: str,
    ) -> int:
        """Capture child stdout through an atomic parent-owned receipt and replay it."""
        argv_items = tuple(cast(Sequence[object], argv))
        if not argv_items or any(
            not isinstance(argument, str) or not argument or "\x00" in argument
            for argument in argv_items
        ):
            self._release_operation_lease(attestation.session_lease)
            raise ParentRootSideEffectError(
                ParentRootReject.INPUT_INVALID,
                "subprocess command is empty or contains NUL",
            )
        receipt = self.resolve_parent_owned_path(attestation, candidate, purpose)
        try:
            result = subprocess.run(
                list(cast(Sequence[str], argv_items)),
                stdout=subprocess.PIPE,
                check=False,
                env=self.child_environment(attestation, issue_handoff=False),
            )
        except Exception:
            self._release_operation_lease(receipt.session_lease)
            raise
        published = self.atomic_publish(receipt, result.stdout)
        if self.read_parent_owned_file(published) != result.stdout:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                "captured subprocess output changed during readback",
            )
        sys.stdout.buffer.write(result.stdout)
        sys.stdout.buffer.flush()
        return result.returncode

    def git_config_add(
        self,
        attestation: ParentRootAttestationReceipt,
        candidate: Path | str,
        key: str,
        value: str,
        purpose: str,
    ) -> ParentOwnedPathReceipt:
        """Run Git config against an inherited, boundary-owned file fd."""
        if not key or any(character in key for character in "\r\n\x00"):
            self._release_operation_lease(attestation.session_lease)
            raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH, "Git config key is invalid")
        if "\x00" in value or "\r" in value:
            self._release_operation_lease(attestation.session_lease)
            raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH, "Git config value is invalid")
        receipt = self.resolve_parent_owned_path(attestation, candidate, purpose)
        if receipt.target_dev is None or receipt.target_ino is None:
            receipt = self.atomic_publish(receipt, b"")
        try:
            _verify_parent_components(receipt)
            physical, _ = _physical_in_root(attestation.parent_root, receipt.physical_path, allow_missing=False)
            parent_fd, name, _ = _parent_directory(attestation.parent_root, physical, create=False)
        except Exception:
            self._release_operation_lease(receipt.session_lease)
            raise
        config_fd = -1
        before_root = _identity(attestation.parent_root)
        try:
            config_fd = os.open(
                name,
                os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
            observed = os.fstat(config_fd)
            if (observed.st_dev, observed.st_ino) != (receipt.target_dev, receipt.target_ino):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "Git config target identity changed before write",
                )
            result = subprocess.run(
                ["git", "config", "--file", f"/proc/self/fd/{config_fd}", "--add", key, value],
                check=False,
                capture_output=True,
                text=True,
                pass_fds=(config_fd,),
            )
            if result.returncode != 0:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"Git config write failed: {result.stderr.strip() or 'command failed'}",
                )
            os.fsync(config_fd)
            if _identity(attestation.parent_root) != before_root:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "parent identity changed during Git config write",
                )
        except ParentRootSideEffectError:
            raise
        except OSError as exc:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"cannot open parent-owned Git config ({purpose}): {exc}",
            ) from exc
        finally:
            if config_fd >= 0:
                os.close(config_fd)
            os.close(parent_fd)
            self._release_operation_lease(receipt.session_lease)
        readback = self.resolve_parent_owned_path(attestation, physical, purpose)
        if readback.target_dev is None or readback.target_ino is None:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                "Git config target disappeared after write",
            )
        self._release_operation_lease(readback.session_lease)
        return replace(readback, session_lease=None)

    def copy_parent_owned_file(
        self,
        attestation: ParentRootAttestationReceipt,
        source: Path | str,
        candidate: Path | str,
        purpose: str,
        *,
        preserve_mode: bool = False,
    ) -> ParentOwnedPathReceipt:
        """Read a parent-owned source and atomically publish its bytes."""
        source_receipt = self.resolve_parent_owned_path(attestation, source, purpose)
        data = self.read_parent_owned_file(source_receipt)
        published = self.write_parent_owned_file(attestation, candidate, data, purpose)
        if preserve_mode:
            source_mode = stat.S_IMODE(source_receipt.physical_path.stat().st_mode)
            published = self.set_parent_owned_mode(
                attestation, published, source_mode
            )
        return published

    def copy_read_only_file(
        self,
        attestation: ParentRootAttestationReceipt,
        source: Path | str,
        candidate: Path | str,
        purpose: str,
    ) -> ParentOwnedPathReceipt:
        """Copy one external read-only regular file into the authenticated parent."""
        source_path = _absolute(Path(source))
        source_fd = -1
        try:
            before = os.stat(source_path, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_MISMATCH,
                    f"read-only source is not a regular file: {source_path}",
                )
            source_fd = os.open(
                source_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
            )
            opened = os.fstat(source_fd)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "read-only source identity changed before copy",
                )
            data = bytearray()
            while True:
                chunk = os.read(source_fd, 1 << 20)
                if not chunk:
                    break
                data.extend(chunk)
            after = os.fstat(source_fd)
            if (after.st_dev, after.st_ino, after.st_size) != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
            ):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "read-only source identity changed during copy",
                )
        except ParentRootSideEffectError:
            self._release_operation_lease(attestation.session_lease)
            raise
        except OSError as exc:
            self._release_operation_lease(attestation.session_lease)
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"cannot copy read-only source ({purpose}): {exc}",
            ) from exc
        finally:
            if source_fd >= 0:
                os.close(source_fd)
        return self.write_parent_owned_file(
            attestation, candidate, bytes(data), purpose
        )

    def copy_parent_owned_tree(
        self,
        attestation: ParentRootAttestationReceipt,
        source: Path | str,
        candidate: Path | str,
        purpose: str,
        exclude: Sequence[str] = (),
    ) -> None:
        """Synchronize a directory tree through open directory descriptors."""
        attestation = self._refresh_attestation(attestation, purpose)
        try:
            source_physical, _ = _physical_in_root(attestation.parent_root, source, allow_missing=False)
        except Exception:
            self._release_operation_lease(attestation.session_lease)
            raise
        target = self.ensure_parent_owned_directory(attestation, candidate, purpose)
        source_fd = target_fd = -1
        try:
            source_fd, _ = _open_components(
                attestation.parent_root,
                tuple(source_physical.relative_to(attestation.parent_root).parts),
                create=False,
            )
            try:
                target_fd, _ = _open_components(
                    attestation.parent_root,
                    tuple(target.physical_path.relative_to(attestation.parent_root).parts),
                    create=False,
                )
            except Exception:
                os.close(source_fd)
                source_fd = -1
                raise
        except Exception:
            if source_fd >= 0:
                os.close(source_fd)
            if target_fd >= 0:
                os.close(target_fd)
            self._release_operation_lease(target.session_lease)
            raise
        excluded = frozenset(exclude)
        try:
            self._copy_open_tree(source_fd, target_fd, excluded, top_level=True)
            os.fsync(target_fd)
        finally:
            os.close(source_fd)
            os.close(target_fd)

    def checkout_index_parent_owned(
        self,
        attestation: ParentRootAttestationReceipt,
        repository: Path | str,
        index_path: str,
        candidate: Path | str,
        purpose: str,
    ) -> ParentOwnedPathReceipt:
        """Materialize one index entry in a boundary-owned staging directory.

        Git receives only the inherited staging directory fd.  The staged entry
        is read back through no-follow dirfds and then published to the final
        candidate by this boundary.
        """
        attestation = self._refresh_attestation(attestation, purpose)
        operation_lease = attestation.session_lease
        if (
            not index_path
            or "\x00" in index_path
            or Path(index_path).is_absolute()
            or any(part in {"", ".", ".."} for part in Path(index_path).parts)
        ):
            self._release_operation_lease(operation_lease)
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                f"checkout-index path is invalid: {index_path!r}",
            )
        try:
            repository_path, _ = _physical_in_root(
                attestation.parent_root, repository, allow_missing=False
            )
            stage_base = self.ensure_parent_owned_directory(
                attestation,
                attestation.parent_root / ".agent-canon" / "tmp" / "checkout-index",
                purpose,
            )
        except Exception:
            self._release_operation_lease(operation_lease)
            raise
        stage_base_path = stage_base.physical_path
        self._release_operation_lease(stage_base.session_lease)
        stage = self.create_parent_owned_temp_directory(
            attestation, stage_base_path, purpose, "entry"
        )
        stage_fd, _ = _open_components(
            attestation.parent_root,
            tuple(stage.physical_path.relative_to(attestation.parent_root).parts),
            create=False,
        )
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository_path),
                    "checkout-index",
                    "-f",
                    f"--prefix=/proc/self/fd/{stage_fd}/",
                    "--",
                    index_path,
                ],
                check=False,
                capture_output=True,
                text=True,
                pass_fds=(stage_fd,),
            )
            if result.returncode != 0:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"Git checkout-index failed: {result.stderr.strip() or 'command failed'}",
                )
            staged_path = _lexical_candidate(
                attestation.parent_root, stage.physical_path / index_path
            )
            staged_parent_fd, staged_name, _ = _parent_directory(
                attestation.parent_root, staged_path, create=False
            )
            try:
                staged_info = os.stat(
                    staged_name, dir_fd=staged_parent_fd, follow_symlinks=False
                )
                if stat.S_ISREG(staged_info.st_mode):
                    staged_fd = os.open(
                        staged_name,
                        os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                        dir_fd=staged_parent_fd,
                    )
                    try:
                        data = bytearray()
                        while True:
                            chunk = os.read(staged_fd, 1 << 20)
                            if not chunk:
                                break
                            data.extend(chunk)
                    finally:
                        os.close(staged_fd)
                    observed = os.stat(
                        staged_name, dir_fd=staged_parent_fd, follow_symlinks=False
                    )
                    if (observed.st_dev, observed.st_ino) != (
                        staged_info.st_dev,
                        staged_info.st_ino,
                    ):
                        raise ParentRootSideEffectError(
                            ParentRootReject.ROOT_RACE_DETECTED,
                            "checkout-index staged file identity changed",
                        )
                    target_receipt = self.resolve_parent_owned_path(
                        attestation, candidate, purpose, create=False
                    )
                    if target_receipt.target_dev is not None:
                        target_info = os.stat(
                            target_receipt.physical_path, follow_symlinks=False
                        )
                        if stat.S_ISDIR(target_info.st_mode):
                            self.remove_parent_owned_tree(
                                attestation, target_receipt, purpose
                            )
                    return self.atomic_publish(target_receipt, bytes(data))
                if stat.S_ISLNK(staged_info.st_mode):
                    link_target = os.readlink(staged_name, dir_fd=staged_parent_fd)
                    target_receipt = self.resolve_parent_owned_path(
                        attestation, candidate, purpose, create=False
                    )
                    if target_receipt.target_dev is not None:
                        target_info = os.stat(
                            target_receipt.physical_path, follow_symlinks=False
                        )
                        if stat.S_ISDIR(target_info.st_mode):
                            self.remove_parent_owned_tree(
                                attestation, target_receipt, purpose
                            )
                        else:
                            self.remove_parent_owned_file(target_receipt)
                    return self.symlink_parent_owned(
                        attestation, link_target, candidate, purpose
                    )
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"unsupported checkout-index entry type: {index_path}",
                )
            finally:
                os.close(staged_parent_fd)
        finally:
            os.close(stage_fd)
            self.remove_parent_owned_tree(attestation, stage, purpose)

    @classmethod
    def _copy_open_tree(cls, source_fd: int, target_fd: int,
                        excluded: frozenset[str], *, top_level: bool = False) -> None:
        source_names = set(os.listdir(source_fd))
        target_names = set(os.listdir(target_fd))
        for name in sorted(source_names):
            if top_level and name in excluded:
                continue
            source_info = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
            if stat.S_ISDIR(source_info.st_mode):
                try:
                    target_info = os.stat(name, dir_fd=target_fd, follow_symlinks=False)
                except FileNotFoundError:
                    os.mkdir(name, 0o700, dir_fd=target_fd)
                    target_info = os.stat(name, dir_fd=target_fd, follow_symlinks=False)
                if not stat.S_ISDIR(target_info.st_mode):
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_RACE_DETECTED,
                        f"tree target type changed: {name}",
                    )
                child_source = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=source_fd)
                child_target = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=target_fd)
                try:
                    cls._copy_open_tree(child_source, child_target, excluded)
                finally:
                    os.close(child_source)
                    os.close(child_target)
                continue
            try:
                os.stat(name, dir_fd=target_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                os.unlink(name, dir_fd=target_fd)
            if stat.S_ISLNK(source_info.st_mode):
                os.symlink(os.readlink(name, dir_fd=source_fd), name, dir_fd=target_fd)
                continue
            if not stat.S_ISREG(source_info.st_mode):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"unsupported tree source entry: {name}",
                )
            source_file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=source_fd)
            temporary = f".{name}.{secrets.token_hex(12)}.tmp"
            temp_file = -1
            primary_error: Exception | None = None
            try:
                temp_file = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=target_fd)
                while True:
                    chunk = os.read(source_file, 1 << 20)
                    if not chunk:
                        break
                    _write_all(temp_file, chunk)
                os.fsync(temp_file)
                os.close(temp_file)
                temp_file = -1
                os.replace(temporary, name, src_dir_fd=target_fd, dst_dir_fd=target_fd)
            except Exception as exc:
                primary_error = exc
                raise
            finally:
                cleanup_errors: list[OSError] = []
                try:
                    os.close(source_file)
                except OSError as exc:
                    cleanup_errors.append(exc)
                if temp_file >= 0:
                    try:
                        os.close(temp_file)
                    except OSError as exc:
                        cleanup_errors.append(exc)
                try:
                    os.unlink(temporary, dir_fd=target_fd)
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    cleanup_errors.append(exc)
                if cleanup_errors:
                    detail = "; ".join(str(error) for error in cleanup_errors)
                    message = f"tree copy cleanup failed: {detail}"
                    if primary_error is not None:
                        message = f"{primary_error}; {message}"
                        raise ParentRootSideEffectError(
                            ParentRootReject.ROOT_RACE_DETECTED, message
                        ) from primary_error
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_RACE_DETECTED, message
                    )
        for name in sorted(target_names - source_names - (excluded if top_level else frozenset())):
            info = os.stat(name, dir_fd=target_fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=target_fd)
                try:
                    cls._remove_open_tree(child)
                finally:
                    os.close(child)
                os.rmdir(name, dir_fd=target_fd)
            else:
                os.unlink(name, dir_fd=target_fd)
        os.fsync(target_fd)

    def move_parent_owned(
        self,
        attestation: ParentRootAttestationReceipt,
        source: Path | str,
        candidate: Path | str,
        purpose: str,
    ) -> None:
        """Rename a parent-owned path using source and destination dirfds."""
        attestation = self._refresh_attestation(attestation, purpose)
        operation_lease = attestation.session_lease
        source_fd = target_fd = -1
        try:
            before = _identity(attestation.parent_root)
            source_physical, _ = _physical_in_root(attestation.parent_root, source, allow_missing=False)
            target_physical, _ = _physical_in_root(attestation.parent_root, candidate, allow_missing=True)
            source_components = _component_identities(
                attestation.parent_root,
                tuple(source_physical.relative_to(attestation.parent_root).parts)[:-1],
                create=False,
            )
            target_components = _component_identities(
                attestation.parent_root,
                tuple(target_physical.relative_to(attestation.parent_root).parts)[:-1],
                create=True,
            )
            source_fd, source_name, _ = _parent_directory(attestation.parent_root, source_physical, create=False)
            try:
                target_fd, target_name, _ = _parent_directory(attestation.parent_root, target_physical, create=True)
            except Exception:
                os.close(source_fd)
                source_fd = -1
                raise
        except Exception:
            if source_fd >= 0:
                os.close(source_fd)
            if target_fd >= 0:
                os.close(target_fd)
            self._release_operation_lease(operation_lease)
            raise
        try:
            if _component_identities(
                attestation.parent_root,
                tuple(source_physical.relative_to(attestation.parent_root).parts)[:-1],
                create=False,
            ) != source_components or _component_identities(
                attestation.parent_root,
                tuple(target_physical.relative_to(attestation.parent_root).parts)[:-1],
                create=False,
            ) != target_components:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"parent directory identity changed before move ({purpose})",
                )
            source_info = os.stat(source_name, dir_fd=source_fd, follow_symlinks=False)
            try:
                os.stat(target_name, dir_fd=target_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"move destination already exists: {target_physical}",
                )
            os.rename(source_name, target_name, src_dir_fd=source_fd, dst_dir_fd=target_fd)
            os.fsync(source_fd)
            if target_fd != source_fd:
                os.fsync(target_fd)
            if _identity(attestation.parent_root) != before:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"parent identity changed during move ({purpose})",
                )
            observed = os.stat(target_name, dir_fd=target_fd, follow_symlinks=False)
            if (observed.st_dev, observed.st_ino) != (source_info.st_dev, source_info.st_ino):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "move target identity changed",
                )
        except ParentRootSideEffectError:
            raise
        except OSError as exc:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"cannot move parent-owned path ({purpose}): {exc}",
            ) from exc
        finally:
            os.close(source_fd)
            if target_fd != source_fd:
                os.close(target_fd)
            self._release_operation_lease(operation_lease)

    def symlink_parent_owned(
        self,
        attestation: ParentRootAttestationReceipt,
        target: str,
        candidate: Path | str,
        purpose: str,
    ) -> ParentOwnedPathReceipt:
        """Create a non-replacing symlink in an authenticated parent."""
        attestation = self._refresh_attestation(attestation, purpose)
        operation_lease = attestation.session_lease
        try:
            physical, _ = _physical_in_root(attestation.parent_root, candidate, allow_missing=True)
            parent_fd, name, _ = _parent_directory(attestation.parent_root, physical, create=True)
        except Exception:
            self._release_operation_lease(operation_lease)
            raise
        try:
            os.symlink(target, name, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError as exc:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"symlink destination already exists: {physical}",
            ) from exc
        except OSError as exc:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"cannot create parent-owned symlink ({purpose}): {exc}",
            ) from exc
        finally:
            os.close(parent_fd)
            self._release_operation_lease(operation_lease)
        result = self.resolve_parent_owned_path(attestation, physical, purpose)
        self._release_operation_lease(result.session_lease)
        return replace(result, session_lease=None)

    def replace_parent_owned_symlink(
        self,
        attestation: ParentRootAttestationReceipt,
        target: str,
        candidate: Path | str,
        purpose: str,
    ) -> Path:
        """Atomically replace one symlink below an authenticated parent root."""
        attestation = self._refresh_attestation(attestation, purpose)
        operation_lease = attestation.session_lease
        if "\x00" in target:
            self._release_operation_lease(operation_lease)
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH, "symlink target contains NUL"
            )
        root = attestation.parent_root
        try:
            before = _identity(root)
            lexical = _lexical_candidate(root, candidate)
        except Exception:
            self._release_operation_lease(operation_lease)
            raise
        if not _contains(root, lexical):
            self._release_operation_lease(operation_lease)
            raise ParentRootSideEffectError(
                ParentRootReject.SYMLINK_ESCAPE,
                f"symlink candidate is outside parent root: {lexical}",
            )
        self.ensure_parent_owned_directory(
            attestation, lexical.parent, f"{purpose}-parent"
        )
        try:
            parent_fd, name, _ = _parent_directory(root, lexical, create=True)
        except Exception:
            self._release_operation_lease(operation_lease)
            raise
        temporary = f".{name}.{secrets.token_hex(12)}.link"
        try:
            os.symlink(target, temporary, dir_fd=parent_fd)
            if _identity(root) != before:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "parent identity changed before symlink replacement",
                )
            os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.fsync(parent_fd)
            observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISLNK(observed.st_mode):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "symlink replacement readback is not a symlink",
                )
            if os.readlink(name, dir_fd=parent_fd) != target:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "symlink replacement target changed",
                )
            if _identity(root) != before:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "parent identity changed after symlink replacement",
                )
        except ParentRootSideEffectError:
            raise
        except OSError as exc:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"cannot replace parent-owned symlink ({purpose}): {exc}",
            ) from exc
        finally:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            os.close(parent_fd)
            self._release_operation_lease(operation_lease)
        return lexical

    def remove_parent_owned_tree(self, attestation: ParentRootAttestationReceipt,
                                 candidate: Path | str | ParentOwnedPathReceipt, purpose: str) -> None:
        """Remove one parent-local directory tree through no-follow dirfds."""
        attestation = self._refresh_attestation(attestation, purpose)
        candidate_lease = candidate.session_lease if isinstance(candidate, ParentOwnedPathReceipt) else None
        operation_lease = (
            candidate_lease
            if candidate_lease is not None and not candidate_lease.closed
            else attestation.session_lease
        )
        if sys.platform != "linux":
            self._release_operation_lease(operation_lease)
            raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform)
        try:
            before = _identity(attestation.parent_root)
        except Exception:
            self._release_operation_lease(operation_lease)
            raise
        expected_dev = expected_ino = None
        if isinstance(candidate, ParentOwnedPathReceipt):
            physical = candidate.physical_path
            expected_dev, expected_ino = candidate.target_dev, candidate.target_ino
            try:
                _verify_parent_components(candidate)
            except Exception:
                self._release_operation_lease(operation_lease)
                raise
            if expected_dev is None or expected_ino is None:
                self._release_operation_lease(operation_lease)
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "tree removal requires a published target identity",
                )
        else:
            try:
                physical, _ = _physical_in_root(attestation.parent_root, candidate, allow_missing=False)
            except Exception:
                self._release_operation_lease(operation_lease)
                raise
        try:
            parent_fd, name, _ = _parent_directory(attestation.parent_root, physical, create=False)
        except Exception:
            self._release_operation_lease(operation_lease)
            raise
        try:
            target_before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if expected_dev is not None and (target_before.st_dev, target_before.st_ino) != (expected_dev, expected_ino):
                raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED,
                                                "target identity changed before removal")
            target_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=parent_fd)
            try:
                target_open = os.fstat(target_fd)
                if (target_before.st_dev, target_before.st_ino) != (target_open.st_dev, target_open.st_ino):
                    raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED,
                                                    "target identity changed before removal")
                self._remove_open_tree(target_fd)
            finally:
                os.close(target_fd)
            os.rmdir(name, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except OSError as exc:
            raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED,
                                            f"cannot remove parent-owned tree ({purpose}): {exc}") from exc
        finally:
            os.close(parent_fd)
            self._release_operation_lease(operation_lease)
        if _identity(attestation.parent_root) != before:
            raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED,
                                            "parent identity changed during removal")

    def read_parent_owned_file(self, receipt: ParentOwnedPathReceipt) -> bytes:
        """Read a capability target through its parent directory fd."""
        receipt = self._revalidate_path_session(receipt, "read-parent-owned-file")
        root = receipt.parent_root
        try:
            _verify_parent_components(receipt)
            physical, _ = _physical_in_root(root, receipt.physical_path, allow_missing=False)
            parent_fd, name, _ = _parent_directory(root, physical, create=False)
        except Exception:
            self._release_operation_lease(receipt.session_lease)
            raise
        fd = -1
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
            observed = os.fstat(fd)
            if (observed.st_dev, observed.st_ino) == (0, 0):
                raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED,
                                                "file identity is invalid")
            if receipt.target_dev is not None and (
                observed.st_dev,
                observed.st_ino,
            ) != (receipt.target_dev, receipt.target_ino):
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "file identity changed before read",
                )
            chunks: list[bytes] = []
            while True:
                try:
                    chunk = os.read(fd, 1 << 20)
                except InterruptedError:
                    continue
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        except OSError as exc:
            raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED,
                                            f"cannot read parent-owned file: {exc}") from exc
        finally:
            if fd >= 0:
                os.close(fd)
            os.close(parent_fd)
            self._release_operation_lease(receipt.session_lease)

    def remove_empty_parent_owned_directory(
        self,
        attestation: ParentRootAttestationReceipt,
        candidate: Path | str | ParentOwnedPathReceipt,
        purpose: str,
    ) -> bool:
        """Remove an owned directory after an fd-bound empty check."""
        attestation = self._refresh_attestation(attestation, purpose)
        candidate_lease = candidate.session_lease if isinstance(candidate, ParentOwnedPathReceipt) else None
        operation_lease = (
            candidate_lease
            if candidate_lease is not None and not candidate_lease.closed
            else attestation.session_lease
        )
        if sys.platform != "linux":
            self._release_operation_lease(operation_lease)
            raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform)
        try:
            before = _identity(attestation.parent_root)
        except Exception:
            self._release_operation_lease(operation_lease)
            raise
        if isinstance(candidate, ParentOwnedPathReceipt):
            physical = candidate.physical_path
            expected = (candidate.target_dev, candidate.target_ino)
            try:
                _verify_parent_components(candidate)
            except Exception:
                self._release_operation_lease(operation_lease)
                raise
        else:
            try:
                physical, _ = _physical_in_root(attestation.parent_root, candidate, allow_missing=False)
            except Exception:
                self._release_operation_lease(operation_lease)
                raise
            expected = (None, None)
        try:
            parent_fd, name, _ = _parent_directory(attestation.parent_root, physical, create=False)
        except Exception:
            self._release_operation_lease(operation_lease)
            raise
        empty = True
        try:
            observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if expected[0] is not None and (observed.st_dev, observed.st_ino) != expected:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    f"target identity changed before empty removal ({purpose})",
                )
            target_fd = os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
            try:
                opened = os.fstat(target_fd)
                if (opened.st_dev, opened.st_ino) != (observed.st_dev, observed.st_ino):
                    raise ParentRootSideEffectError(
                        ParentRootReject.ROOT_RACE_DETECTED,
                        f"target identity changed during empty removal ({purpose})",
                    )
                empty = not bool(os.listdir(target_fd))
            finally:
                os.close(target_fd)
            if empty:
                os.rmdir(name, dir_fd=parent_fd)
                os.fsync(parent_fd)
        except ParentRootSideEffectError:
            raise
        except OSError as exc:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"cannot remove empty parent-owned directory ({purpose}): {exc}",
            ) from exc
        finally:
            os.close(parent_fd)
            self._release_operation_lease(operation_lease)
        if _identity(attestation.parent_root) != before:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                "parent identity changed during empty removal",
            )
        return empty

    def remove_parent_owned_file(self, receipt: ParentOwnedPathReceipt) -> None:
        """Unlink a lexical receipt entry through its no-follow parent fd."""
        receipt = self._revalidate_path_session(receipt, "remove-parent-owned-file")
        root = receipt.parent_root
        is_symlink = receipt.lexical_entry_type == stat.S_IFLNK
        try:
            if not is_symlink:
                _verify_parent_components(receipt)
            parent_fd, name = _open_lexical_entry(receipt)
        except Exception:
            self._release_operation_lease(receipt.session_lease)
            raise
        before = _identity(root)
        try:
            os.unlink(name, dir_fd=parent_fd)
            os.fsync(parent_fd)
            try:
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "lexical entry remained after removal",
                )
            if _identity(root) != before:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "parent identity changed during file removal",
                )
        except ParentRootSideEffectError:
            raise
        except OSError as exc:
            raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED,
                                            f"cannot remove parent-owned file: {exc}") from exc
        finally:
            os.close(parent_fd)
            self._release_operation_lease(receipt.session_lease)

    @staticmethod
    def _remove_open_tree(directory_fd: int) -> None:
        """Remove a directory tree with descriptor-bound iterative post-order."""
        stack = [_TreeRemovalFrame(directory_fd=directory_fd)]
        errors: list[Exception] = []
        while stack:
            frame = stack[-1]
            if frame.entries is None:
                try:
                    frame.entries = list(os.listdir(frame.directory_fd))
                except OSError as exc:
                    errors.append(exc)
                    frame.entries = []
            if frame.entries:
                name = frame.entries.pop()
                try:
                    observed = os.stat(
                        name, dir_fd=frame.directory_fd, follow_symlinks=False
                    )
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    errors.append(exc)
                    continue
                if stat.S_ISDIR(observed.st_mode):
                    child_fd = -1
                    try:
                        child_fd = os.open(
                            name,
                            os.O_RDONLY
                            | os.O_DIRECTORY
                            | os.O_NOFOLLOW
                            | os.O_CLOEXEC,
                            dir_fd=frame.directory_fd,
                        )
                        child_observed = os.fstat(child_fd)
                        if (child_observed.st_dev, child_observed.st_ino) != (
                            observed.st_dev,
                            observed.st_ino,
                        ):
                            raise ParentRootSideEffectError(
                                ParentRootReject.ROOT_RACE_DETECTED,
                                f"directory identity changed before cleanup: {name}",
                            )
                    except (OSError, ParentRootSideEffectError) as exc:
                        errors.append(exc)
                        if child_fd >= 0:
                            os.close(child_fd)
                        continue
                    stack.append(
                        _TreeRemovalFrame(
                            directory_fd=child_fd,
                            parent_fd=frame.directory_fd,
                            entry_name=name,
                            expected_dev=observed.st_dev,
                            expected_ino=observed.st_ino,
                        )
                    )
                    continue
                try:
                    current = os.stat(
                        name, dir_fd=frame.directory_fd, follow_symlinks=False
                    )
                    if (current.st_dev, current.st_ino) != (
                        observed.st_dev,
                        observed.st_ino,
                    ):
                        raise ParentRootSideEffectError(
                            ParentRootReject.ROOT_RACE_DETECTED,
                            f"file identity changed before cleanup: {name}",
                        )
                    os.unlink(name, dir_fd=frame.directory_fd)
                except FileNotFoundError:
                    continue
                except (OSError, ParentRootSideEffectError) as exc:
                    errors.append(exc)
                continue
            try:
                os.fsync(frame.directory_fd)
            except OSError as exc:
                errors.append(exc)
            if frame.parent_fd is not None and frame.entry_name is not None:
                try:
                    current = os.stat(
                        frame.entry_name,
                        dir_fd=frame.parent_fd,
                        follow_symlinks=False,
                    )
                    if (current.st_dev, current.st_ino) != (
                        frame.expected_dev,
                        frame.expected_ino,
                    ):
                        raise ParentRootSideEffectError(
                            ParentRootReject.ROOT_RACE_DETECTED,
                            f"directory identity changed before removal: {frame.entry_name}",
                        )
                    os.rmdir(frame.entry_name, dir_fd=frame.parent_fd)
                    os.fsync(frame.parent_fd)
                except (OSError, ParentRootSideEffectError) as exc:
                    errors.append(exc)
            if frame.parent_fd is not None:
                try:
                    os.close(frame.directory_fd)
                except OSError as exc:
                    errors.append(exc)
            stack.pop()
        if errors:
            detail = "; ".join(str(error) for error in errors)
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                f"parent-owned tree cleanup failed: {detail}",
            ) from errors[0]

    def child_environment(
        self,
        attestation: ParentRootAttestationReceipt,
        base_env: Mapping[str, str] | None = None,
        *,
        issue_handoff: bool = True,
        rebase_inherited_temp: bool = False,
    ) -> dict[str, str]:
        """Bind persistent child state and temporary state to the parent."""
        env = dict(os.environ if base_env is None else base_env)
        if rebase_inherited_temp:
            for name in ("TMPDIR", "TEMP", "TMP"):
                env.pop(name, None)
        root = attestation.parent_root
        default_tmp = root / ".agent-canon" / "tmp"
        default_cache = root / ".agent-canon" / "cache"
        default_target = default_cache / "cargo-target"

        def parent_local_value(name: str, default: Path) -> Path:
            """Validate one environment path without creating anything."""
            value = env.get(name)
            candidate = Path(value) if value else default
            physical, _ = _physical_in_root(root, candidate, allow_missing=True)
            return physical

        # Validate every override before creating any of the parent-local
        # directories.  In particular, a late invalid value must not leave
        # earlier defaults behind as an observable partial side effect.
        paths = {
            "TMPDIR": parent_local_value("TMPDIR", default_tmp),
            "TEMP": parent_local_value("TEMP", default_tmp),
            "TMP": parent_local_value("TMP", default_tmp),
            "XDG_CACHE_HOME": parent_local_value("XDG_CACHE_HOME", default_cache),
            "PYTHONPYCACHEPREFIX": parent_local_value(
                "PYTHONPYCACHEPREFIX", default_cache / "pycache"
            ),
            "AGENT_CANON_TOOLS_HOME": parent_local_value(
                "AGENT_CANON_TOOLS_HOME", root / ".agent-canon" / "tools"
            ),
            "CARGO_HOME": parent_local_value("CARGO_HOME", default_cache / "cargo-home"),
        }
        target_a = parent_local_value("CARGO_TARGET_DIR", default_target)
        target_b = parent_local_value("AGENT_CANON_CLI_TARGET_DIR", default_target)
        if env.get("CARGO_TARGET_DIR") and env.get("AGENT_CANON_CLI_TARGET_DIR") and target_a != target_b:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH, "target_alias_mismatch"
            )
        target = target_a if env.get("CARGO_TARGET_DIR") else target_b
        paths["CARGO_TARGET_DIR"] = target
        paths["AGENT_CANON_CLI_TARGET_DIR"] = target
        for key, path in paths.items():
            capability = self.ensure_parent_owned_directory(attestation, path, f"child-{key}")
            env[key] = str(capability.physical_path)
        # Every child receives the signed multi-use session.  Repository and
        # source identity are derived by the child from its physical cwd;
        # legacy parent/active/source variables and one-shot child handoffs
        # are never re-injected into a process environment.
        if not attestation.session_handle:
            raise ParentRootSideEffectError(
                ParentRootReject.HANDOFF_INVALID,
                "session_missing",
            )
        for key in (
            "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
            "AGENT_CANON_PARENT_ROOT",
            "AGENT_CANON_PARENT_ROOT_DEV",
            "AGENT_CANON_PARENT_ROOT_INO",
            "AGENT_CANON_SOURCE_ROOT",
            "AGENT_CANON_ROOT",
            "AGENT_CANON_CHILD_HANDOFF",
            "AGENT_CANON_CHILD_PURPOSE",
            "AGENT_CANON_HANDOFF_AUDIENCE",
        ):
            env.pop(key, None)
        env[SIDE_EFFECT_PARENT_ROOT_ENV] = str(root)
        env[SIDE_EFFECT_HANDOFF_ENV] = attestation.session_handle
        env[SIDE_EFFECT_REQUIRED_ENV] = "1"
        return env

    def data_identity_environment(
        self,
        *,
        cwd: Path | str,
        source_root: Path | str | None = None,
        base_env: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """Return explicit cwd-derived data identity, never side-effect authority.

        This is intentionally separate from :meth:`session_environment` so a
        parent-side-effect session cannot accidentally become a repository
        identity injector for nested fixtures.
        """
        cwd_path = _physical(Path(cwd), strict=True)
        root = _git_toplevel(cwd_path)
        source = _physical(Path(source_root), strict=True) if source_root is not None else None
        if source is not None and not _contains(root, source):
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                "data identity source is outside cwd-derived repository",
            )
        attestation = self.attest(
            ParentRootAttestationRequest(
                cwd=cwd_path,
                explicit_root=root,
                source_root=source,
                purpose="data-identity",
            )
        )
        env = dict(os.environ if base_env is None else base_env)
        for key in (SIDE_EFFECT_PARENT_ROOT_ENV, SIDE_EFFECT_HANDOFF_ENV, SIDE_EFFECT_REQUIRED_ENV):
            env.pop(key, None)
        env[DATA_REPOSITORY_ROOT_ENV] = str(attestation.parent_root)
        env[DATA_REPOSITORY_DEV_ENV] = str(attestation.parent_dev)
        env[DATA_REPOSITORY_INO_ENV] = str(attestation.parent_ino)
        env[DATA_SOURCE_ROOT_ENV] = str(
            attestation.source_root or attestation.parent_root
        )
        env[DATA_ROOT_ENV] = env[DATA_SOURCE_ROOT_ENV]
        return env

    def exec_parent_bound(
        self,
        attestation: ParentRootAttestationReceipt,
        argv: Sequence[str],
        purpose: str,
        *,
        issue_handoff: bool = False,
        rebase_inherited_temp: bool = False,
    ) -> int:
        """Create parent-owned child env and execute argv without a shell.

        Update/sync entrypoints are often launched by a runner that exports
        ``TMPDIR`` (and its portable aliases) for its own temporary state.
        Those values are inherited input, not an update/sync temp selection;
        rebasing them here lets the child environment bind them to the
        authenticated parent before the normal path checks run.  Callers that
        need an explicit temporary location use ``AGENT_CANON_PARENT_TMPDIR``
        and resolve it after the handoff.
        """
        if not argv:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                "exec command is empty",
            )
        if any("\x00" in argument for argument in argv):
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                "exec command contains NUL",
            )
        if os.environ.get(SIDE_EFFECT_PARENT_ROOT_ENV) or os.environ.get(SIDE_EFFECT_HANDOFF_ENV):
            session = resolve_parent_side_effect_session_v2(
                observed_cwd=_physical(Path.cwd(), strict=True),
                env=os.environ,
            )
            # Session authentication does not make inherited path overrides
            # safe.  Rebind and validate all writable tool paths under the
            # authenticated parent before handing the environment to the
            # child, while retaining only the signed side-effect channel as
            # its repository capability.
            env = self.child_environment(
                session.attestation,
                _v2_session_environment(session, os.environ),
                issue_handoff=False,
                rebase_inherited_temp=rebase_inherited_temp,
            )
            for key in (
                "AGENT_CANON_PARENT_ROOT", "AGENT_CANON_PARENT_ROOT_DEV",
                "AGENT_CANON_PARENT_ROOT_INO", "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
                "AGENT_CANON_SOURCE_ROOT", "AGENT_CANON_ROOT",
            ):
                env.pop(key, None)
            inherited_lease = session.lease
        else:
            env = self.child_environment(
                attestation,
                issue_handoff=issue_handoff,
                rebase_inherited_temp=rebase_inherited_temp,
            )
            inherited_lease = attestation.session_lease
        # The child receives the signed channel, not the parent's operation
        # lease.  Release the local lease before replacing this process so the
        # durable session cannot retain a stale lease record after exec.
        self._release_operation_lease(inherited_lease)
        os.execvpe(argv[0], list(argv), env)
        raise RuntimeError("exec failed")

    def reattest_child(self, request: ParentRootAttestationRequest,
                       environment: Mapping[str, str]) -> ParentRootAttestationReceipt:
        token = environment.get("AGENT_CANON_CHILD_HANDOFF", "")
        if not token:
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "child handoff token was dropped")
        return self.attest(replace(request, child_handoff_token=token))

    def verify_child_environment(
        self,
        request: ParentRootAttestationRequest,
        environment: Mapping[str, str],
    ) -> ChildHandoffReceipt:
        """Authenticate an inherited child environment without consuming its token."""
        token = environment.get("AGENT_CANON_CHILD_HANDOFF", "")
        if not token:
            raise ParentRootSideEffectError(
                ParentRootReject.HANDOFF_INVALID, "child handoff token was dropped"
            )
        root = _physical(request.explicit_root or request.cwd, strict=True)
        source = _physical(request.source_root, strict=True) if request.source_root else None
        clone = _physical(request.clone_root, strict=True) if request.clone_root else None
        handoff = self._handoff(
            token,
            request=request,
            parent_root=root,
            source_root=source,
            clone_root=clone,
            consume_nonce=False,
        )
        if handoff is None:
            raise ParentRootSideEffectError(
                ParentRootReject.HANDOFF_INVALID, "child handoff verification failed"
            )
        return handoff

    def self_check(
        self,
        root: Path,
        *,
        sentinel_outside: Path | None = None,
        attestation: ParentRootAttestationReceipt | None = None,
    ) -> dict[str, object]:
        before_home = os.environ.get("HOME")
        att = attestation or self.attest(
            ParentRootAttestationRequest(cwd=root, explicit_root=root, purpose="self-check")
        )
        receipt = self.resolve_parent_owned_path(att, Path(".agent-canon") / "self-check.txt", "self-check")
        published = self.atomic_publish(receipt, b"parent-owned\n")
        observed = self.read_parent_owned_file(published).decode("utf-8")
        self.remove_parent_owned_file(published)
        if sentinel_outside is not None and Path(sentinel_outside).exists():
            raise ParentRootSideEffectError(ParentRootReject.SYMLINK_ESCAPE, "outside sentinel exists")
        if os.environ.get("HOME") != before_home:
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "HOME changed")
        return {"status": "pass", "root": str(att.parent_root), "observed": observed,
                "home_unchanged": True,
                "outside_sentinel_absent": not (sentinel_outside and Path(sentinel_outside).exists())}


# ---------------------------------------------------------------------------
# v2 session boundary
# ---------------------------------------------------------------------------
#
# The original record-session implementation above remains available to old
# effect receipts while callers migrate.  Public entrypoints and the runner
# use the v2 unit below.  Keeping the storage/parser here (rather than in each
# writer) is intentional: one canonical record, one signature, one resolver,
# and one lease lifecycle are the security boundary.

SCHEMA_SESSION_RECORD_V2 = "agent-canon.parent-side-effect-session/v2"
SCHEMA_SESSION_RECORD = SCHEMA_SESSION_RECORD_V2
V2_SESSION_ROOT_NAME = "side-effect-sessions-v2"
SESSION_TTL_NS = 900_000_000_000
# Direct public sessions keep the short default TTL.  The private runner
# factory owns the only longer horizon; callers cannot select or extend it.
_RUNNER_HORIZON_NS = 14_400_000_000_000
_PUBLIC_EXEC_TERM_GRACE_NS = 5_000_000_000
_PUBLIC_EXEC_POLL_NS = 250_000_000

SESSION_RECORD_FIELDS = (
    "schema", "session_id", "parent_root_realpath", "parent_dev", "parent_ino",
    "root_realpath", "root_dev", "root_ino", "role", "issuer_id", "issuer_pid",
    "issuer_starttime_ticks", "record_id", "recovery_epoch", "nonce",
    "issued_mono_ns", "expires_mono_ns",
    "status", "expired_at_mono_ns", "revoked_at_mono_ns", "transition_reason",
    "signature",
)
SESSION_ROLES = frozenset({"supervisor", "record"})
SESSION_STATUSES = frozenset({"active", "revoked"})
REVOKE_REASONS = frozenset(
    {"normal_exit", "timeout", "expired", "signal", "shutdown", "parent_changed", "stale_recovery"}
)
_V2_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_V2_NONCE = re.compile(r"^[0-9a-f]{64}$")


class SessionResolutionError(ParentRootSideEffectError):
    """Typed v2 session resolution failure."""


def _v2_error(detail: str, reject: ParentRootReject = ParentRootReject.HANDOFF_INVALID) -> SessionResolutionError:
    return SessionResolutionError(reject, detail)


def _v2_json_bytes(value: Mapping[str, object]) -> bytes:
    """Serialize v2 fields without relying on mapping insertion by callers."""
    ordered = {field_name: value[field_name] for field_name in SESSION_RECORD_FIELDS[:-1]}
    return json.dumps(
        ordered, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


@dataclass(frozen=True)
class SessionRecord:
    """Canonical signed v2 supervisor or record session record."""

    schema: str
    session_id: str
    parent_root_realpath: str
    parent_dev: int
    parent_ino: int
    root_realpath: str | None
    root_dev: int | None
    root_ino: int | None
    role: Literal["supervisor", "record"]
    issuer_id: str
    issuer_pid: int
    issuer_starttime_ticks: int
    record_id: str | None
    recovery_epoch: int
    nonce: str
    issued_mono_ns: int
    expires_mono_ns: int
    status: Literal["active", "revoked"]
    expired_at_mono_ns: int | None
    revoked_at_mono_ns: int | None
    transition_reason: str | None
    signature: str

    def as_mapping(self, *, include_signature: bool = True) -> dict[str, object]:
        """Return fields in the normative canonical order."""
        mapping: dict[str, object] = {
            "schema": self.schema,
            "session_id": self.session_id,
            "parent_root_realpath": self.parent_root_realpath,
            "parent_dev": self.parent_dev,
            "parent_ino": self.parent_ino,
            "root_realpath": self.root_realpath,
            "root_dev": self.root_dev,
            "root_ino": self.root_ino,
            "role": self.role,
            "issuer_id": self.issuer_id,
            "issuer_pid": self.issuer_pid,
            "issuer_starttime_ticks": self.issuer_starttime_ticks,
            "record_id": self.record_id,
            "recovery_epoch": self.recovery_epoch,
            "nonce": self.nonce,
            "issued_mono_ns": self.issued_mono_ns,
            "expires_mono_ns": self.expires_mono_ns,
            "status": self.status,
            "expired_at_mono_ns": self.expired_at_mono_ns,
            "revoked_at_mono_ns": self.revoked_at_mono_ns,
            "transition_reason": self.transition_reason,
        }
        if include_signature:
            mapping["signature"] = self.signature
        return mapping

    def canonical_bytes(self) -> bytes:
        """Return the exact bytes authenticated by the v2 MAC."""
        return _v2_json_bytes(self.as_mapping(include_signature=False))


def _is_nonnegative_int(value: object) -> TypeGuard[int]:
    """Narrow one decoded JSON value to a non-bool non-negative integer."""
    return type(value) is int and value >= 0


def _is_path_value(value: object) -> TypeGuard[Path]:
    """Retain runtime validation for dynamically supplied path arguments."""
    return isinstance(value, Path)


def _v2_record_from_mapping(value: Mapping[str, object]) -> SessionRecord:
    if tuple(value) != SESSION_RECORD_FIELDS:
        raise _v2_error("session_record_fields")
    if value.get("schema") != SCHEMA_SESSION_RECORD_V2:
        raise _v2_error("v1_session_record_rejected")
    role = value.get("role")
    status = value.get("status")
    if role not in SESSION_ROLES or status not in SESSION_STATUSES:
        raise _v2_error("session_record_role_or_status")
    strings = ("session_id", "parent_root_realpath", "issuer_id", "nonce", "signature")
    if any(not isinstance(value.get(name), str) or not value[name] for name in strings):
        raise _v2_error("session_record_string_field")
    if not _SESSION_ID_RE.fullmatch(cast(str, value["session_id"])):
        raise _v2_error("session_record_session_id")
    nonce = cast(str, value["nonce"])
    signature = cast(str, value["signature"])
    if not _V2_NONCE.fullmatch(nonce) or not _V2_HEX64.fullmatch(signature):
        raise _v2_error("session_record_mac_field")
    nullable_strings = ("root_realpath", "transition_reason")
    if any(item is not None and not isinstance(item, str) for item in (value.get(name) for name in nullable_strings)):
        raise _v2_error("session_record_nullable_field")
    if value.get("record_id") is not None and not isinstance(value.get("record_id"), str):
        raise _v2_error("session_record_record_id")
    if value.get("record_id") is not None and not _SESSION_ID_RE.fullmatch(cast(str, value["record_id"])):
        raise _v2_error("session_record_record_id")
    for name in ("root_dev", "root_ino", "expired_at_mono_ns", "revoked_at_mono_ns"):
        item = value.get(name)
        if item is not None and not _is_nonnegative_int(item):
            raise _v2_error("session_record_nullable_integer")
    integer_fields = (
        "parent_dev", "parent_ino", "issuer_pid", "issuer_starttime_ticks", "recovery_epoch",
        "issued_mono_ns", "expires_mono_ns",
    )
    for name in integer_fields:
        if not _is_nonnegative_int(value.get(name)):
            raise _v2_error("session_record_integer")
    parent_dev = cast(int, value["parent_dev"])
    parent_ino = cast(int, value["parent_ino"])
    issuer_pid = cast(int, value["issuer_pid"])
    issuer_starttime_ticks = cast(int, value["issuer_starttime_ticks"])
    issued_mono_ns = cast(int, value["issued_mono_ns"])
    expires_mono_ns = cast(int, value["expires_mono_ns"])
    if parent_dev <= 0 or parent_ino <= 0:
        raise _v2_error("session_parent_identity")
    if issuer_pid <= 0 or issuer_starttime_ticks <= 0:
        raise _v2_error("session_issuer_identity")
    if role == "supervisor":
        if value.get("record_id") is not None or value.get("root_realpath") is not None:
            raise _v2_error("supervisor_nullable_fields")
    else:
        if not isinstance(value.get("record_id"), str) or not value.get("record_id"):
            raise _v2_error("child_record_id_required")
        if not isinstance(value.get("root_realpath"), str) or value.get("root_dev") is None or value.get("root_ino") is None:
            raise _v2_error("child_root_required")
        if role == "record" and (
            value.get("root_realpath") != value.get("parent_root_realpath")
            or value.get("root_dev") != value.get("parent_dev")
            or value.get("root_ino") != value.get("parent_ino")
        ):
            raise _v2_error("record_root_binding")
    if expires_mono_ns <= issued_mono_ns:
        raise _v2_error("session_record_horizon")
    expired_at = value.get("expired_at_mono_ns")
    revoked_at = value.get("revoked_at_mono_ns")
    reason = value.get("transition_reason")
    if status == "active":
        if expired_at is not None or revoked_at is not None or reason is not None:
            raise _v2_error("active_status_fields")
    else:
        if revoked_at is None or reason not in REVOKE_REASONS:
            raise _v2_error("revoked_status_fields")
        if reason == "expired" and expired_at is None:
            raise _v2_error("expired_status_fields")
        if reason != "expired" and expired_at is not None:
            raise _v2_error("explicit_revoke_expired_field")
    return SessionRecord(
        schema=cast(str, value["schema"]), session_id=cast(str, value["session_id"]),
        parent_root_realpath=cast(str, value["parent_root_realpath"]),
        parent_dev=cast(int, value["parent_dev"]), parent_ino=cast(int, value["parent_ino"]),
        root_realpath=cast(str | None, value.get("root_realpath")),
        root_dev=cast(int | None, value.get("root_dev")), root_ino=cast(int | None, value.get("root_ino")),
        role=cast(Literal["supervisor", "record"], role), issuer_id=cast(str, value["issuer_id"]),
        issuer_pid=cast(int, value["issuer_pid"]), issuer_starttime_ticks=cast(int, value["issuer_starttime_ticks"]),
        record_id=cast(str | None, value.get("record_id")),
        recovery_epoch=cast(int, value["recovery_epoch"]), nonce=nonce,
        issued_mono_ns=cast(int, value["issued_mono_ns"]), expires_mono_ns=cast(int, value["expires_mono_ns"]),
        status=cast(Literal["active", "revoked"], status),
        expired_at_mono_ns=cast(int | None, value.get("expired_at_mono_ns")),
        revoked_at_mono_ns=cast(int | None, value.get("revoked_at_mono_ns")),
        transition_reason=cast(str | None, value.get("transition_reason")), signature=signature,
    )


def _v2_signed_record(record: SessionRecord, key: bytes) -> SessionRecord:
    signature = hmac.new(
        key, b"agent-canon/parent-side-effect-session/v2\0" + record.canonical_bytes(), hashlib.sha256
    ).hexdigest()
    return replace(record, signature=signature)


def parse_session_record_v2(raw: bytes | str | Mapping[str, object], key: bytes) -> SessionRecord:
    """Parse and authenticate the sole canonical v2 record representation."""
    if type(key) is not bytes or len(key) != 32:
        raise _v2_error("session_key_invalid", ParentRootReject.INPUT_INVALID)
    try:
        if isinstance(raw, bytes):
            value = json.loads(raw.decode("utf-8"))
        elif isinstance(raw, str):
            value = json.loads(raw)
        else:
            value = dict(raw)
    except (TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise _v2_error("session_record_malformed") from exc
    if not isinstance(value, dict):
        raise _v2_error("session_record_malformed")
    record = _v2_record_from_mapping(cast(Mapping[str, object], value))
    expected = hmac.new(
        key, b"agent-canon/parent-side-effect-session/v2\0" + record.canonical_bytes(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, record.signature):
        raise _v2_error("session_record_signature")
    return record


def _v2_session_root(parent_root: Path) -> Path:
    return parent_root / ".agent-canon" / "runtime" / V2_SESSION_ROOT_NAME


def _v2_session_dir(parent_root: Path, session_id: str) -> Path:
    if not _SESSION_ID_RE.fullmatch(session_id):
        raise _v2_error("session_id_invalid", ParentRootReject.INPUT_INVALID)
    return _v2_session_root(parent_root) / session_id


def _v2_record_path(record: SessionRecord) -> Path:
    return _v2_session_dir(Path(record.parent_root_realpath), record.session_id) / "record.json"


def _v2_key_path(record: SessionRecord) -> Path:
    return _v2_session_root(Path(record.parent_root_realpath)) / f"issuer-{record.issuer_id}.key"


def _v2_key_probe(parent: Path, issuer_id: str) -> SessionRecord:
    """Build an untrusted path-only record used solely to locate an issuer key."""
    return SessionRecord(
        schema=SCHEMA_SESSION_RECORD_V2,
        session_id="placeholder",
        parent_root_realpath=str(parent),
        parent_dev=0,
        parent_ino=0,
        root_realpath=None,
        root_dev=None,
        root_ino=None,
        role="supervisor",
        issuer_id=issuer_id,
        issuer_pid=1,
        issuer_starttime_ticks=1,
        record_id=None,
        recovery_epoch=0,
        nonce="0" * 64,
        issued_mono_ns=1,
        expires_mono_ns=2,
        status="active",
        expired_at_mono_ns=None,
        revoked_at_mono_ns=None,
        transition_reason=None,
        signature="0" * 64,
    )


def _v2_lock_path(record: SessionRecord) -> Path:
    return _v2_session_dir(Path(record.parent_root_realpath), record.session_id) / "session.lock"


def _v2_lease_dir(record: SessionRecord) -> Path:
    return _v2_session_dir(Path(record.parent_root_realpath), record.session_id) / "leases"


def _v2_write_bytes(path: Path, data: bytes, mode: int = 0o600) -> None:
    parent = _physical(path.parent, strict=True)
    if parent != path.parent:
        raise _v2_error("state_parent_symlink", ParentRootReject.SYMLINK_ESCAPE)
    parent_fd = os.open(
        parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    temporary_name = f".{path.name}.{secrets.token_hex(8)}.tmp"
    fd = os.open(
        temporary_name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        mode,
        dir_fd=parent_fd,
    )
    try:
        _write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        target_fd = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
        try:
            os.fchmod(target_fd, mode)
        finally:
            os.close(target_fd)
        os.fsync(parent_fd)
    finally:
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)


def _v2_ensure_session_tree(parent: Path, session_id: str) -> Path:
    """Create one v2 session directory through no-follow component handles."""
    directory_fd, _ = _open_components(
        parent,
        (".agent-canon", "runtime", "side-effect-sessions-v2", session_id),
        create=True,
    )
    try:
        os.fchmod(directory_fd, 0o700)
    finally:
        os.close(directory_fd)
    session_dir = _v2_session_dir(parent, session_id)
    if _physical(session_dir, strict=True) != session_dir:
        raise _v2_error("state_session_symlink", ParentRootReject.SYMLINK_ESCAPE)
    return session_dir


def _v2_read_bytes(path: Path) -> bytes:
    """Read one v2 state file through a no-follow descriptor."""
    parent = _physical(path.parent, strict=True)
    if parent != path.parent:
        raise _v2_error("state_parent_symlink", ParentRootReject.SYMLINK_ESCAPE)
    parent_fd = os.open(
        parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
        try:
            return _read_all(fd)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _v2_write_record(record: SessionRecord, key: bytes) -> SessionRecord:
    _v2_parent_identity(record)
    signed = _v2_signed_record(record, key)
    _v2_write_bytes(_v2_record_path(signed), json.dumps(signed.as_mapping(), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return signed


def _v2_read_record(record_path: Path, key: bytes) -> SessionRecord:
    try:
        return parse_session_record_v2(_v2_read_bytes(record_path), key)
    except OSError as exc:
        raise _v2_error("session_record_unreadable") from exc


def _process_starttime_ticks(pid: int) -> int | None:
    """Read Linux process incarnation without treating PID alone as identity."""
    if pid <= 0:
        return None
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").split()
        return int(fields[21])
    except (OSError, ValueError, IndexError):
        return None


@dataclass
class _V2Lease:
    """One durable v2 operation lease."""

    lease_path: Path
    lock_path: Path
    lock_fd: int
    _closed: bool = False

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(self.lock_fd)
        for path in (self.lease_path, self.lock_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


@dataclass(frozen=True)
class SessionResolutionResult:
    """Single typed result consumed by every v2 writer."""

    record: SessionRecord
    lease: _V2Lease | None
    state_path: Path
    status: Literal["active", "revoked"]
    attestation: ParentRootAttestationReceipt
    handoff: str = field(repr=False, compare=False, default="")

    @property
    def parent_root(self) -> Path:
        return Path(self.record.parent_root_realpath)

    @property
    def session_id(self) -> str:
        return self.record.session_id

    @property
    def audience(self) -> str:
        """Return the role bound to this signed channel."""
        return self.record.role

    @property
    def session_role(self) -> str:
        """Return the capability role bound to this result."""
        return self.record.role

    @property
    def handle(self) -> str:
        return self.handoff

    @property
    def expires_mono_ns(self) -> int:
        return self.record.expires_mono_ns

    def close(self) -> None:
        if self.lease is not None:
            self.lease.close()


def _v2_session_environment(
    result: SessionResolutionResult,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Serialize one v2 result as the only supported child capability."""
    if result.status != "active":
        raise _v2_error("session_revoked")
    env = dict(os.environ if base_env is None else base_env)
    for key in (
        "AGENT_CANON_PARENT_ROOT", "AGENT_CANON_PARENT_ROOT_DEV",
        "AGENT_CANON_PARENT_ROOT_INO", "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
        "AGENT_CANON_SOURCE_ROOT", "AGENT_CANON_ROOT", "AGENT_CANON_CHILD_HANDOFF",
        "AGENT_CANON_CHILD_PURPOSE", "AGENT_CANON_HANDOFF_AUDIENCE",
        "AGENT_CANON_FIXTURE_ROLE", "AGENT_CANON_REPORT_ROOT",
        "AGENT_CANON_RUN_BUNDLE_ROOT", "AGENT_CANON_CLOSEOUT_ROOT",
    ):
        env.pop(key, None)
    env[SIDE_EFFECT_PARENT_ROOT_ENV] = str(result.parent_root)
    env[SIDE_EFFECT_HANDOFF_ENV] = result.handoff
    env[SIDE_EFFECT_REQUIRED_ENV] = "1"
    return env


@dataclass(frozen=True)
class SessionIssuerHandle:
    """Opaque in-process supervisor key handle."""

    session_id: str = field(repr=True)
    issuer_id: str = field(repr=True)
    _key: bytes = field(repr=False, compare=False, default=b"")

    @property
    def key(self) -> bytes:
        """Return the issuer key to private lifecycle owners."""
        return self._key


@dataclass(frozen=True)
class _PhysicalIdentity:
    """Verified physical Git root used by private fixture/issuer APIs."""

    realpath: Path
    dev: int
    ino: int


def _v2_physical_identity(root: Path) -> _PhysicalIdentity:
    checked = _physical(root, strict=True)
    dev, ino = _identity(checked)
    return _PhysicalIdentity(checked, dev, ino)


@dataclass(frozen=True)
class _ChildSessionRef:
    session_id: str
    record_id: str
    nonce: str


@dataclass(frozen=True)
class _RunnerHorizon:
    """Opaque, immutable deadline owned by the runner issuer."""

    run_started_mono_ns: int
    run_deadline_mono_ns: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.run_started_mono_ns, bool)
            or isinstance(self.run_deadline_mono_ns, bool)
            or self.run_started_mono_ns < 0
            or self.run_deadline_mono_ns <= self.run_started_mono_ns
        ):
            raise _v2_error("runner_horizon_invalid", ParentRootReject.INPUT_INVALID)


class _RunnerCallerMarker:
    """Opaque marker required by the private runner session factory."""


_RUNNER_CALLER_MARKER = _RunnerCallerMarker()


@dataclass(frozen=True)
class ChildSessionReceipt:
    record: SessionRecord
    handoff: str
    child: _ChildSessionRef


@dataclass(frozen=True)
class DrainReceipt:
    child_id: str
    observed_nonce: str
    status: str
    reason: str
    leases_before: int
    leases_after: int
    cleanup_disposition: str


@dataclass(frozen=True)
class RecoveryIssuerResult:
    issuer: "_RecoveryIssuer | None"
    status: str
    reason: str


def _v2_handoff(record: SessionRecord, key: bytes) -> str:
    envelope = {"record": record.as_mapping(), "signature": record.signature}
    # The signature is repeated as the envelope binding so malformed transport
    # cannot silently substitute a different record mapping.
    return base64.urlsafe_b64encode(
        json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def _v2_decode_handoff(raw: str, key: bytes) -> SessionRecord:
    try:
        value: object = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise _v2_error("session_handoff_malformed") from exc
    if type(value) is not dict:
        raise _v2_error("session_handoff_fields")
    envelope: Mapping[str, object] = cast(Mapping[str, object], value)
    if tuple(envelope) != ("record", "signature"):
        raise _v2_error("session_handoff_fields")
    record_value: object = envelope.get("record")
    envelope_signature = envelope.get("signature")
    if type(record_value) is not dict or envelope_signature != cast(Mapping[str, object], record_value).get("signature"):
        raise _v2_error("session_handoff_binding")
    return parse_session_record_v2(
        json.dumps(record_value, ensure_ascii=False, separators=(",", ":")), key
    )


def _v2_handoff_parent_root(raw: str) -> Path:
    """Read only the signed-channel parent hint for a subsequent resolver call."""
    try:
        value: object = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))
        envelope: Mapping[str, object] = (
            cast(Mapping[str, object], value) if type(value) is dict else {}
        )
        record_value: object = envelope.get("record")
        record: Mapping[str, object] = (
            cast(Mapping[str, object], record_value) if type(record_value) is dict else {}
        )
        parent = record.get("parent_root_realpath")
        if not isinstance(parent, str) or not parent:
            raise ValueError("parent_root_realpath")
        return _physical(Path(parent), strict=True)
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise _v2_error("session_handoff_malformed") from exc


def _v2_lease_for(record: SessionRecord, key: bytes | None = None) -> _V2Lease:
    session_lock_fd = os.open(_v2_lock_path(record), os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    fcntl.flock(session_lock_fd, fcntl.LOCK_EX)
    lock_fd: int | None = None
    lock_path: Path | None = None
    lease_path: Path | None = None
    try:
        _v2_parent_identity(record)
        if key is not None:
            current = _v2_read_record(_v2_record_path(record), key)
            if current.status != "active":
                raise _v2_error("session_revoked")
            record = current
        lease_dir = _v2_lease_dir(record)
        session_dir = _v2_session_dir(Path(record.parent_root_realpath), record.session_id)
        if _physical(session_dir, strict=True) != session_dir:
            raise _v2_error("state_session_symlink", ParentRootReject.SYMLINK_ESCAPE)
        lease_dir_fd, _ = _open_components(session_dir, ("leases",), create=True)
        try:
            os.fchmod(lease_dir_fd, 0o700)
        finally:
            os.close(lease_dir_fd)
        if _physical(lease_dir, strict=True) != lease_dir:
            raise _v2_error("state_lease_symlink", ParentRootReject.SYMLINK_ESCAPE)
        lease_id = secrets.token_hex(16)
        lock_path = lease_dir / f"{lease_id}.lock"
        lease_path = lease_dir / f"{lease_id}.json"
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_SH)
        _v2_write_bytes(
            lease_path,
            json.dumps(
                {"schema": "agent-canon.parent-side-effect-lease/v2", "lease_id": lease_id,
                 "session_id": record.session_id, "nonce": record.nonce},
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        lease = _V2Lease(lease_path, lock_path, lock_fd)
    except BaseException:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        if lease_path is not None:
            lease_path.unlink(missing_ok=True)
        if lock_path is not None:
            lock_path.unlink(missing_ok=True)
        raise
    finally:
        fcntl.flock(session_lock_fd, fcntl.LOCK_UN)
        os.close(session_lock_fd)
    return lease


def _v2_read_key(record: SessionRecord) -> bytes:
    try:
        key = _v2_read_bytes(_v2_key_path(record))
    except OSError as exc:
        raise _v2_error("session_key_missing") from exc
    if len(key) != 32:
        raise _v2_error("session_key_invalid")
    return key


def _v2_parent_identity(record: SessionRecord) -> None:
    try:
        root = _physical(Path(record.parent_root_realpath), strict=True)
        if root != Path(record.parent_root_realpath) or _identity(root) != (record.parent_dev, record.parent_ino):
            raise _v2_error("parent_identity_changed", ParentRootReject.ROOT_RACE_DETECTED)
    except ParentRootSideEffectError:
        raise
    except OSError as exc:
        raise _v2_error("parent_identity_unavailable", ParentRootReject.ROOT_MISSING) from exc


@contextmanager
def _v2_session_lock(record: SessionRecord) -> Iterator[None]:
    """Serialize lease creation, revoke/drain, and recovery for one session."""
    session_dir = _v2_session_dir(Path(record.parent_root_realpath), record.session_id)
    if _physical(session_dir, strict=True) != session_dir:
        raise _v2_error("state_session_symlink", ParentRootReject.SYMLINK_ESCAPE)
    fd = os.open(_v2_lock_path(record), os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        _v2_parent_identity(record)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _v2_abort_session(record: SessionRecord) -> None:
    """Remove a just-issued session tree after bootstrap cannot complete."""
    session_dir = _v2_session_dir(Path(record.parent_root_realpath), record.session_id)
    key_path = _v2_key_path(record)
    if not session_dir.exists():
        key_path.unlink(missing_ok=True)
        return
    _v2_parent_identity(record)
    with _v2_session_lock(record):
        leases = _v2_lease_dir(record)
        if leases.exists():
            if leases.is_symlink() or not leases.is_dir():
                raise _v2_error("state_lease_symlink", ParentRootReject.SYMLINK_ESCAPE)
            for entry in leases.iterdir():
                if entry.is_symlink() or not entry.is_file():
                    raise _v2_error("state_lease_not_regular", ParentRootReject.SYMLINK_ESCAPE)
                entry.unlink()
            leases.rmdir()
        record_path = _v2_record_path(record)
        if record_path.exists():
            if record_path.is_symlink() or not record_path.is_file():
                raise _v2_error("state_record_not_regular", ParentRootReject.SYMLINK_ESCAPE)
            record_path.unlink()
    lock_path = _v2_lock_path(record)
    lock_path.unlink(missing_ok=True)
    session_dir.rmdir()
    key_path.unlink(missing_ok=True)


def _v2_resolve(
    *, env: Mapping[str, str], observed_cwd: Path, now_mono_ns: int,
) -> SessionResolutionResult:
    if any(type(k) is not str or type(v) is not str for k, v in env.items()):
        raise _v2_error("environment_invalid", ParentRootReject.INPUT_INVALID)
    channel = env.get(SIDE_EFFECT_HANDOFF_ENV, "")
    root_value = env.get(SIDE_EFFECT_PARENT_ROOT_ENV, "")
    has_channel = bool(channel)
    has_root = bool(root_value)
    if not has_channel and not has_root:
        if _public_legacy_variables(env):
            raise _v2_error("legacy_authority_forbidden")
        raise _v2_error("session_missing")
    if has_channel != has_root:
        # A partial canonical channel is an authentication failure.  Never
        # reinterpret an unsigned legacy selector as the missing half.
        raise _v2_error("session_channel_incomplete")
    try:
        parent = _physical(Path(root_value), strict=True)
        decoded_value: object = json.loads(
            base64.urlsafe_b64decode(channel.encode("ascii")).decode("utf-8")
        )
        if type(decoded_value) is not dict:
            raise TypeError("handoff")
        decoded = cast(Mapping[str, object], decoded_value)
        record_hint_value = decoded.get("record")
        if type(record_hint_value) is not dict:
            raise TypeError("record")
        record_hint = cast(Mapping[str, object], record_hint_value)
        issuer_id = record_hint.get("issuer_id")
        if not isinstance(issuer_id, str) or not issuer_id:
            raise TypeError("issuer")
        key = _v2_read_key(
            _v2_key_probe(parent, issuer_id)
        )
        record = _v2_decode_handoff(channel, key)
    except ParentRootSideEffectError:
        raise
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise _v2_error("session_handoff_malformed") from exc
    if Path(record.parent_root_realpath) != parent:
        raise _v2_error("session_parent_binding")
    _v2_parent_identity(record)
    record_path = _v2_record_path(record)
    current = _v2_read_record(record_path, key)
    if current.session_id != record.session_id or current.nonce != record.nonce:
        raise _v2_error("session_stale", ParentRootReject.HANDOFF_INVALID)
    cwd = _physical(observed_cwd, strict=True)
    if not _contains(parent, cwd):
        raise _v2_error("session_cwd_outside_parent", ParentRootReject.ROOT_SPOOFED)
    if current.status != "active":
        raise _v2_error("session_revoked")
    if now_mono_ns >= current.expires_mono_ns:
        lock_fd = os.open(_v2_lock_path(current), os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            latest = _v2_read_record(record_path, key)
            if latest.status == "active" and now_mono_ns >= latest.expires_mono_ns:
                expired = replace(latest, status="revoked", expired_at_mono_ns=now_mono_ns,
                                  revoked_at_mono_ns=now_mono_ns, transition_reason="expired")
                _v2_write_record(expired, key)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        raise _v2_error("session_expired")
    lease = _v2_lease_for(current, key)
    effect_root = parent
    try:
        attestation = _DEFAULT_BOUNDARY.attest(
            ParentRootAttestationRequest(cwd=effect_root, explicit_root=effect_root, purpose=current.role)
        )
    except BaseException:
        lease.close()
        raise
    attestation = replace(
        attestation, session_handle=channel, session_lease=lease, session_role=current.role
    )
    return SessionResolutionResult(current, lease, record_path, current.status, attestation, channel)


def resolve_parent_side_effect_session_v2(
    *, env: Mapping[str, str], observed_cwd: Path, now_mono_ns: int | None = None,
) -> SessionResolutionResult:
    """Resolve one signed v2 channel using the observed physical CWD."""
    observed_value: object = observed_cwd
    if not _is_path_value(observed_value):
        raise _v2_error("observed_cwd_invalid", ParentRootReject.INPUT_INVALID)
    return _v2_resolve(env=env, observed_cwd=observed_cwd, now_mono_ns=time.monotonic_ns() if now_mono_ns is None else now_mono_ns)


def _v2_issue_session(
    parent_root: Path, *, role: Literal["supervisor", "record"], record_id: str | None,
    root: Path | None, now_mono_ns: int, expires_mono_ns: int | None = None,
    expected_expires_mono_ns: int | None = None,
    issuer_id: str | None = None, issuer_key: bytes | None = None,
) -> tuple[SessionRecord, bytes, str]:
    parent = _physical(parent_root, strict=True)
    if role not in ("supervisor", "record"):
        raise _v2_error("role_invalid", ParentRootReject.INPUT_INVALID)
    if _git_toplevel(parent) != parent:
        raise _v2_error("parent_not_git_toplevel", ParentRootReject.ROOT_MISMATCH)
    parent_dev, parent_ino = _identity(parent)
    issuer_id = issuer_id or secrets.token_hex(16)
    session_id = secrets.token_urlsafe(18).replace("-", "_")
    key = issuer_key or secrets.token_bytes(32)
    root_realpath: str | None = None
    root_dev: int | None = None
    root_ino: int | None = None
    if root is not None:
        checked = _physical(root, strict=True)
        if not _contains(parent, checked):
            raise _v2_error("child_root_outside_parent", ParentRootReject.ROOT_MISMATCH)
        if role == "record" and checked != parent:
            raise _v2_error("record_root_binding", ParentRootReject.ROOT_MISMATCH)
        root_realpath = str(checked)
        root_dev, root_ino = _identity(checked)
    if role == "supervisor":
        record_id = None
    elif not isinstance(record_id, str) or not _SESSION_ID_RE.fullmatch(record_id):
        raise _v2_error("record_id_invalid", ParentRootReject.INPUT_INVALID)
    expires = now_mono_ns + SESSION_TTL_NS if expires_mono_ns is None else expires_mono_ns
    if isinstance(expires, bool) or expires <= now_mono_ns:
        raise _v2_error("session_horizon_mismatch")
    if expected_expires_mono_ns is not None and expires != expected_expires_mono_ns:
        raise _v2_error("SESSION_HORIZON_MISMATCH")
    record = SessionRecord(
        SCHEMA_SESSION_RECORD_V2, session_id, str(parent), parent_dev, parent_ino,
        root_realpath, root_dev, root_ino, role, issuer_id,
        os.getpid(), _process_starttime_ticks(os.getpid()) or 0, record_id, 0,
        secrets.token_hex(32), now_mono_ns, expires, "active", None, None, None, "",
    )
    _v2_ensure_session_tree(parent, session_id)
    _v2_write_bytes(_v2_lock_path(record), b"", 0o600)
    _v2_write_bytes(_v2_key_path(record), key)
    signed = _v2_write_record(record, key)
    return signed, key, _v2_handoff(signed, key)


class _SupervisorIssuer:
    """Private parent-bound issuer for renewal and child lifecycle."""

    def __init__(
        self, session: SessionRecord, key: bytes, handle: SessionIssuerHandle,
        runner_horizon: _RunnerHorizon | None = None,
    ) -> None:
        self._session = session
        self._key = key
        self._handle = handle
        self._runner_horizon = runner_horizon or _RunnerHorizon(
            session.issued_mono_ns, session.expires_mono_ns
        )
        self._children: dict[str, _ChildSessionRef] = {}
        self._closed = False

    @property
    def session(self) -> SessionRecord:
        return self._session

    @property
    def handle(self) -> SessionIssuerHandle:
        return self._handle

    def _load(self) -> SessionRecord:
        current = _v2_read_record(_v2_record_path(self._session), self._key)
        if current.issuer_id != self._session.issuer_id or current.role != "supervisor":
            raise _v2_error("issuer_binding")
        _v2_parent_identity(current)
        return current

    def issue_child(
        self, *, role: Literal["record"], record_id: str | None,
        physical_root: Path | _PhysicalIdentity, now_mono_ns: int,
    ) -> ChildSessionReceipt:
        if self._closed or self._load().status != "active":
            raise _v2_error("issuer_closed")
        parent = Path(self._session.parent_root_realpath)
        root_identity = physical_root if isinstance(physical_root, _PhysicalIdentity) else _v2_physical_identity(physical_root)
        root = root_identity.realpath
        with _v2_session_lock(self._session):
            current = self._load()
            if current.status != "active":
                raise _v2_error("issuer_closed")
            _v2_parent_identity(current)
            if now_mono_ns >= current.expires_mono_ns:
                _v2_write_record(
                    replace(
                        current,
                        status="revoked",
                        expired_at_mono_ns=now_mono_ns,
                        revoked_at_mono_ns=now_mono_ns,
                        transition_reason="expired",
                    ),
                    self._key,
                )
                raise _v2_error("session_expired")
            if current.expires_mono_ns != self._runner_horizon.run_deadline_mono_ns:
                raise _v2_error("SESSION_HORIZON_MISMATCH")
            record, _key_unused, handoff = _v2_issue_session(
                parent, role=role, record_id=record_id, root=root,
                now_mono_ns=now_mono_ns, expires_mono_ns=self._runner_horizon.run_deadline_mono_ns,
                expected_expires_mono_ns=self._runner_horizon.run_deadline_mono_ns,
                issuer_id=self._session.issuer_id, issuer_key=self._key,
            )
        ref = _ChildSessionRef(record.session_id, cast(str, record.record_id), record.nonce)
        self._children[record.session_id] = ref
        return ChildSessionReceipt(record, handoff, ref)

    def revoke_drain_child(self, *, child: _ChildSessionRef, reason: str, now_mono_ns: int) -> DrainReceipt:
        if reason not in REVOKE_REASONS:
            raise _v2_error("revoke_reason_invalid", ParentRootReject.INPUT_INVALID)
        ref = self._children.get(child.session_id, child)
        record_path = _v2_session_dir(Path(self._session.parent_root_realpath), ref.session_id) / "record.json"
        record = _v2_read_record(record_path, self._key)
        with _v2_session_lock(record):
            record = _v2_read_record(record_path, self._key)
            if record.nonce != ref.nonce or record.record_id != ref.record_id:
                raise _v2_error("child_handle_stale")
            before = len(tuple(_v2_lease_dir(record).glob("*.json"))) if _v2_lease_dir(record).exists() else 0
            if record.status == "active":
                record = _v2_write_record(replace(record, status="revoked", revoked_at_mono_ns=now_mono_ns,
                                                    transition_reason=reason), self._key)
            _v2_drain_leases(record)
            after = len(tuple(_v2_lease_dir(record).glob("*.json"))) if _v2_lease_dir(record).exists() else 0
            return DrainReceipt(ref.session_id, record.nonce, record.status, reason, before, after,
                                "drained" if after == 0 else "live_leases_remaining")

    def close(self, *, reason: str = "shutdown", now_mono_ns: int | None = None) -> None:
        if self._closed:
            return
        if reason not in REVOKE_REASONS:
            raise _v2_error("close_reason_invalid", ParentRootReject.INPUT_INVALID)
        now = time.monotonic_ns() if now_mono_ns is None else now_mono_ns
        for child in tuple(self._children.values()):
            self.revoke_drain_child(child=child, reason="normal_exit" if reason == "shutdown" else reason, now_mono_ns=now)
        current = self._load()
        if current.status == "active":
            _v2_write_record(replace(current, status="revoked", revoked_at_mono_ns=now, transition_reason=reason), self._key)
        self._closed = True


def _open_supervisor_issuer(
    *, session: SessionRecord, resolution: SessionResolutionResult,
    issuer_handle: SessionIssuerHandle, now_mono_ns: int,
    runner_horizon: _RunnerHorizon | None = None,
) -> _SupervisorIssuer:
    """Open the only in-process authority that may renew or issue children."""
    if session.role != "supervisor" or resolution.record.session_id != session.session_id:
        raise _v2_error("issuer_session_binding")
    if issuer_handle.session_id != session.session_id or issuer_handle.issuer_id != session.issuer_id:
        raise _v2_error("issuer_handle_binding")
    with _v2_session_lock(session):
        current = _v2_read_record(_v2_record_path(session), issuer_handle.key)
        if current.session_id != session.session_id or current.issuer_id != session.issuer_id:
            raise _v2_error("issuer_session_binding")
        if current.status != "active" or now_mono_ns >= current.expires_mono_ns:
            raise _v2_error("issuer_session_expired")
        horizon = runner_horizon or _RunnerHorizon(
            current.issued_mono_ns, current.expires_mono_ns
        )
        if current.expires_mono_ns != horizon.run_deadline_mono_ns:
            raise _v2_error("SESSION_HORIZON_MISMATCH")
    return _SupervisorIssuer(current, issuer_handle.key, issuer_handle, horizon)


def _v2_drain_leases(record: SessionRecord) -> None:
    lease_dir = _v2_lease_dir(record)
    if not lease_dir.exists():
        return
    if _physical(lease_dir, strict=True) != lease_dir:
        raise _v2_error("state_lease_symlink", ParentRootReject.SYMLINK_ESCAPE)
    for lease_path in sorted(lease_dir.glob("*.json")):
        lock_path = lease_path.with_suffix(".lock")
        try:
            if not stat.S_ISREG(lease_path.lstat().st_mode) or not stat.S_ISREG(lock_path.lstat().st_mode):
                raise _v2_error("state_lease_not_regular", ParentRootReject.SYMLINK_ESCAPE)
            fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                lease_path.unlink(missing_ok=True)
                lock_path.unlink(missing_ok=True)
            finally:
                os.close(fd)
        except (FileNotFoundError, OSError):
            continue


def _v2_recover_dead_leases(record: SessionRecord) -> tuple[int, int]:
    """Remove only leases whose no-follow lock is not held by a live owner."""
    lease_dir = _v2_lease_dir(record)
    if not lease_dir.exists():
        return 0, 0
    if _physical(lease_dir, strict=True) != lease_dir:
        raise _v2_error("state_lease_symlink", ParentRootReject.SYMLINK_ESCAPE)
    before = len(tuple(lease_dir.glob("*.json")))
    for lease_path in sorted(lease_dir.glob("*.json")):
        lock_path = lease_path.with_suffix(".lock")
        try:
            fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        except OSError:
            continue
        try:
            if not stat.S_ISREG(lease_path.lstat().st_mode) or not stat.S_ISREG(lock_path.lstat().st_mode):
                raise _v2_error("state_lease_not_regular", ParentRootReject.SYMLINK_ESCAPE)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            lease_path.unlink(missing_ok=True)
            lock_path.unlink(missing_ok=True)
        finally:
            os.close(fd)
    after = len(tuple(lease_dir.glob("*.json")))
    return before, after


def _read_process_starttime(pid: int) -> int | None:
    return _process_starttime_ticks(pid)


class _RecoveryIssuer:
    """Parent-bound stale recovery issuer with no renewal/child authority."""

    def __init__(self, record: SessionRecord, key: bytes, recovery_nonce: str) -> None:
        self._record = record
        self._key = key
        self._recovery_nonce = recovery_nonce

    @property
    def recovery_nonce(self) -> str:
        """Return the one-use in-process recovery capability nonce."""
        return self._recovery_nonce

    def revoke_drain_child(self, *, child: _ChildSessionRef, reason: Literal["stale_recovery"], now_mono_ns: int) -> DrainReceipt:
        if reason != "stale_recovery":
            raise _v2_error("recovery_reason_invalid", ParentRootReject.INPUT_INVALID)
        path = _v2_session_dir(Path(self._record.parent_root_realpath), child.session_id) / "record.json"
        record = _v2_read_record(path, self._key)
        if record.role == "supervisor" or record.issuer_id != self._record.issuer_id or record.nonce != child.nonce:
            raise _v2_error("recovery_child_binding")
        with _v2_session_lock(record):
            record = _v2_read_record(path, self._key)
            if record.role == "supervisor" or record.issuer_id != self._record.issuer_id or record.nonce != child.nonce:
                raise _v2_error("recovery_child_binding")
            before = len(tuple(_v2_lease_dir(record).glob("*.json"))) if _v2_lease_dir(record).exists() else 0
            if record.status == "active":
                record = _v2_write_record(replace(record, status="revoked", revoked_at_mono_ns=now_mono_ns,
                                                    transition_reason="stale_recovery"), self._key)
            _v2_recover_dead_leases(record)
            after = len(tuple(_v2_lease_dir(record).glob("*.json"))) if _v2_lease_dir(record).exists() else 0
        return DrainReceipt(child.session_id, record.nonce, record.status, reason, before, after,
                            "drained" if after == 0 else "live_leases_remaining")


def _open_recovery_issuer(
    *, parent: Path | _PhysicalIdentity, session_dir: Path, expected_issuer_pid: int,
    expected_issuer_starttime_ticks: int, expected_recovery_epoch: int,
    now_mono_ns: int,
) -> RecoveryIssuerResult:
    """Classify issuer liveness before allowing stale-only recovery."""
    checked_parent = parent.realpath if isinstance(parent, _PhysicalIdentity) else _physical(parent, strict=True)
    if isinstance(parent, _PhysicalIdentity) and _identity(checked_parent) != (parent.dev, parent.ino):
        raise _v2_error("recovery_parent_identity", ParentRootReject.ROOT_RACE_DETECTED)
    checked_session_dir = _physical(session_dir, strict=True)
    if checked_session_dir != session_dir:
        raise _v2_error("recovery_session_symlink", ParentRootReject.SYMLINK_ESCAPE)
    if not _contains(checked_parent, checked_session_dir):
        raise _v2_error("recovery_session_outside_parent", ParentRootReject.ROOT_SPOOFED)
    record_path = checked_session_dir / "record.json"
    try:
        record_value = json.loads(_v2_read_bytes(record_path).decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise _v2_error("recovery_record_malformed") from exc
    if not isinstance(record_value, dict):
        raise _v2_error("recovery_record_malformed")
    record_mapping = cast(Mapping[str, object], record_value)
    issuer_id = record_mapping.get("issuer_id")
    if not isinstance(issuer_id, str):
        raise _v2_error("recovery_issuer_metadata_missing")
    key = _v2_read_key(_v2_key_probe(checked_parent, issuer_id))
    record = parse_session_record_v2(json.dumps(record_value, separators=(",", ":")), key)
    if Path(record.parent_root_realpath) != checked_parent or record.session_id != checked_session_dir.name:
        raise _v2_error("recovery_parent_binding", ParentRootReject.ROOT_SPOOFED)
    if record.issuer_pid != expected_issuer_pid or record.issuer_starttime_ticks != expected_issuer_starttime_ticks:
        raise _v2_error("recovery_issuer_metadata_mismatch")
    with _v2_session_lock(record):
        current = _v2_read_record(record_path, key)
        if current.status != "active":
            return RecoveryIssuerResult(None, "RECOVERY_DEFERRED", "session_revoked")
        if current.recovery_epoch != expected_recovery_epoch:
            raise _v2_error("recovery_stale", ParentRootReject.HANDOFF_INVALID)
        live_start = _read_process_starttime(expected_issuer_pid)
        if live_start == expected_issuer_starttime_ticks:
            return RecoveryIssuerResult(None, "RECOVERY_DEFERRED", "issuer_live")
        if live_start is not None:
            return RecoveryIssuerResult(None, "PID_REUSED", "issuer_incarnation_changed")
        recovery_nonce = secrets.token_hex(32)
        bumped = _v2_write_record(replace(current, recovery_epoch=current.recovery_epoch + 1), key)
    return RecoveryIssuerResult(_RecoveryIssuer(bumped, key, recovery_nonce), "ISSUER_PROCESS_ABSENT", "recovery_authorized")


def recover_v2_stale_sessions(parent_root: Path, *, now_mono_ns: int | None = None) -> int:
    """Recover v2 child leases only after the supervisor PID is absent."""
    root = _physical(parent_root, strict=True)
    sessions_root = _v2_session_root(root)
    if not sessions_root.is_dir() or _physical(sessions_root, strict=True) != sessions_root:
        return 0
    now = time.monotonic_ns() if now_mono_ns is None else now_mono_ns
    recovered = 0
    for session_dir in sorted(sessions_root.iterdir()):
        if not session_dir.is_dir() or session_dir.name.startswith("issuer-"):
            continue
        record_path = session_dir / "record.json"
        if not record_path.is_file():
            continue
        try:
            raw_value: object = json.loads(_v2_read_bytes(record_path).decode("utf-8"))
            raw: Mapping[str, object] = (
                cast(Mapping[str, object], raw_value) if type(raw_value) is dict else {}
            )
            if raw.get("role") != "supervisor":
                continue
            issuer_id = raw.get("issuer_id")
            if not isinstance(issuer_id, str):
                continue
            key = _v2_read_key(_v2_key_probe(root, issuer_id))
            record = parse_session_record_v2(json.dumps(raw, separators=(",", ":")), key)
            opened = _open_recovery_issuer(
                parent=root,
                session_dir=session_dir,
                expected_issuer_pid=record.issuer_pid,
                expected_issuer_starttime_ticks=record.issuer_starttime_ticks,
                expected_recovery_epoch=record.recovery_epoch,
                now_mono_ns=now,
            )
            issuer = opened.issuer
            if issuer is None:
                continue
            for child_dir in sorted(sessions_root.iterdir()):
                if not child_dir.is_dir() or child_dir == session_dir or child_dir.name.startswith("issuer-"):
                    continue
                child_path = child_dir / "record.json"
                try:
                    child_raw = json.loads(_v2_read_bytes(child_path).decode("utf-8"))
                    child = parse_session_record_v2(json.dumps(child_raw, separators=(",", ":")), key)
                except (OSError, ValueError, TypeError, ParentRootSideEffectError):
                    continue
                if child.issuer_id != record.issuer_id or child.status != "active":
                    continue
                receipt = issuer.revoke_drain_child(
                    child=_ChildSessionRef(child.session_id, cast(str, child.record_id), child.nonce),
                    reason="stale_recovery", now_mono_ns=now,
                )
                recovered += receipt.leases_before - receipt.leases_after + 1
        except (OSError, ValueError, TypeError, ParentRootSideEffectError):
            continue
    return recovered


class _RecordFixtureDirectCallerMarker:
    """Opaque route marker for the record-owned fixture-direct adapter."""


_RECORD_FIXTURE_DIRECT_CALLER_MARKER = _RecordFixtureDirectCallerMarker()
_V2_SESSION_CONTEXT: contextvars.ContextVar[SessionResolutionResult | None] = contextvars.ContextVar(
    "agent_canon_v2_session", default=None
)
_V2_ISSUER_CONTEXT: contextvars.ContextVar[_SupervisorIssuer | None] = contextvars.ContextVar(
    "agent_canon_v2_issuer", default=None
)


def current_supervisor_issuer() -> _SupervisorIssuer | None:
    """Return the private issuer for the active public supervisor context."""
    return _V2_ISSUER_CONTEXT.get()


@dataclass(frozen=True)
class CleanupEvidence:
    """Immutable evidence for paths owned and cleaned by one fixture spawn."""

    status: Literal["clean", "failed"]
    created_paths: tuple[str, ...] = ()
    removed_paths: tuple[str, ...] = ()
    detail: str | None = None


@dataclass(frozen=True)
class FixtureExecutionReceipt:
    """Frozen result of a record-owned fixture-direct command."""

    argv_sha256: str
    fixture_root_realpath: str
    fixture_root_dev: int
    fixture_root_ino: int
    returncode: int
    cleanup: CleanupEvidence


def _fixture_direct_error(
    detail: str, reject: ParentRootReject = ParentRootReject.HANDOFF_INVALID
) -> SessionResolutionError:
    return _v2_error(f"FIXTURE_DIRECT_{detail}", reject)


def _fixture_direct_argv(argv: Sequence[str]) -> tuple[str, ...]:
    value: object = cast(object, argv)
    if type(value) in (str, bytes) or not isinstance(value, Sequence):
        raise _fixture_direct_error("INPUT_INVALID", ParentRootReject.INPUT_INVALID)
    command = tuple(cast(Sequence[str], value))
    if not command or any(
        type(item) is not str or not item or "\x00" in item for item in command
    ):
        raise _fixture_direct_error("INPUT_INVALID", ParentRootReject.INPUT_INVALID)
    return command


def _fixture_direct_identity(
    record: SessionResolutionResult, fixture_cwd: Path, *, require_lease: bool = True,
    now_mono_ns: int | None = None,
) -> _PhysicalIdentity:
    if type(record) is not SessionResolutionResult:
        raise _fixture_direct_error("SESSION_REQUIRED", ParentRootReject.HANDOFF_INVALID)
    if record.status != "active" or record.record.status != "active" or record.record.role != "record":
        raise _fixture_direct_error("SESSION_REQUIRED", ParentRootReject.HANDOFF_INVALID)
    if (require_lease and (record.lease is None or record.lease.closed)) or not record.handoff:
        raise _fixture_direct_error("SESSION_REQUIRED", ParentRootReject.HANDOFF_INVALID)
    now = time.monotonic_ns() if now_mono_ns is None else now_mono_ns
    if now >= record.record.expires_mono_ns:
        raise _fixture_direct_error("SESSION_EXPIRED", ParentRootReject.HANDOFF_INVALID)
    try:
        _v2_parent_identity(record.record)
        parent = Path(record.record.parent_root_realpath)
        try:
            if fixture_cwd.is_symlink():
                raise _fixture_direct_error("SYMLINK_ROOT", ParentRootReject.SYMLINK_ESCAPE)
        except OSError as exc:
            raise _fixture_direct_error("INPUT_INVALID", ParentRootReject.INPUT_INVALID) from exc
        fixture = _v2_physical_identity(fixture_cwd)
        observed = _v2_physical_identity(Path.cwd())
    except ParentRootSideEffectError:
        raise
    if fixture != observed:
        raise _fixture_direct_error("CWD_MISMATCH", ParentRootReject.ROOT_SPOOFED)
    if _git_toplevel(fixture.realpath) != fixture.realpath:
        raise _fixture_direct_error("NOT_GIT_ROOT", ParentRootReject.ROOT_MISMATCH)
    if not _contains(parent, fixture.realpath):
        raise _fixture_direct_error("OUTSIDE_PARENT", ParentRootReject.ROOT_MISMATCH)
    return fixture


def _fixture_direct_child_environment(
    record: SessionResolutionResult, local_root: Path
) -> dict[str, str]:
    """Prepare only fixture-local process paths and no inherited authority."""
    env = _v2_session_environment(record, os.environ)
    for key in tuple(env):
        if key.startswith("AGENT_CANON_SIDE_EFFECT_"):
            env.pop(key, None)
    for key in (
        "AGENT_CANON_PARENT_ROOT", "AGENT_CANON_PARENT_ROOT_DEV", "AGENT_CANON_PARENT_ROOT_INO",
        "AGENT_CANON_ACTIVE_REPOSITORY_ROOT", "AGENT_CANON_SOURCE_ROOT", "AGENT_CANON_ROOT",
        "AGENT_CANON_CHILD_HANDOFF", "AGENT_CANON_CHILD_PURPOSE", "AGENT_CANON_HANDOFF_AUDIENCE",
        "AGENT_CANON_FIXTURE_ROLE", "AGENT_CANON_REPORT_ROOT", "AGENT_CANON_RUN_BUNDLE_ROOT",
        "AGENT_CANON_CLOSEOUT_ROOT", "AGENT_CANON_RECORD_ROOT", "AGENT_CANON_RECORD_ID",
        "AGENT_CANON_TOOLS_HOME", "AGENT_CANON_CLI_TARGET_DIR", DATA_REPOSITORY_ROOT_ENV, DATA_REPOSITORY_DEV_ENV,
        DATA_REPOSITORY_INO_ENV, DATA_SOURCE_ROOT_ENV, DATA_ROOT_ENV, "PYTHONPATH",
    ):
        env.pop(key, None)
    local_paths = {
        "HOME": local_root / "home",
        "TMPDIR": local_root / "tmp",
        "TEMP": local_root / "tmp",
        "TMP": local_root / "tmp",
        "XDG_CACHE_HOME": local_root / "xdg-cache",
        "XDG_CONFIG_HOME": local_root / "xdg-config",
        "XDG_DATA_HOME": local_root / "xdg-data",
        "PYTHONPYCACHEPREFIX": local_root / "pycache",
        "CARGO_HOME": local_root / "cargo-home",
        "CARGO_TARGET_DIR": local_root / "cargo-target",
        "AGENT_CANON_TOOLS_HOME": local_root / "tools",
        "AGENT_CANON_CLI_TARGET_DIR": local_root / "cargo-target",
    }
    for name, path in local_paths.items():
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        env[name] = str(path)
    return env


def _run_fixture_direct_command(
    *, caller: _RecordFixtureDirectCallerMarker, record: SessionResolutionResult,
    fixture_cwd: Path, argv: Sequence[str], now_mono_ns: int,
    clock: Callable[[], int] = time.monotonic_ns,
) -> FixtureExecutionReceipt:
    """Validate, spawn, read back, and clean one record-owned fixture command."""
    if caller is not _RECORD_FIXTURE_DIRECT_CALLER_MARKER:
        raise _fixture_direct_error("CALLER_MARKER", ParentRootReject.INPUT_INVALID)
    if type(now_mono_ns) is not int or now_mono_ns < 0:
        raise _fixture_direct_error("INPUT_INVALID", ParentRootReject.INPUT_INVALID)
    fixture_cwd_value: object = fixture_cwd
    if not _is_path_value(fixture_cwd_value):
        raise _fixture_direct_error("INPUT_INVALID", ParentRootReject.INPUT_INVALID)
    command = _fixture_direct_argv(argv)
    fixture = _fixture_direct_identity(record, fixture_cwd, now_mono_ns=now_mono_ns)
    parent_attestation = record.attestation
    local_receipt: ParentOwnedPathReceipt | None = None
    created: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    cleanup_detail: str | None = None
    returncode = -1
    digest = hashlib.sha256("\0".join(command).encode("utf-8")).hexdigest()
    try:
        local_receipt = _DEFAULT_BOUNDARY.create_parent_owned_temp_directory(
            parent_attestation, fixture.realpath / ".agent-canon" / "fixture-direct",
            "fixture-direct-local", "record",
        )
        local_root = local_receipt.physical_path
        created = (str(local_root),)
        env = _fixture_direct_child_environment(record, local_root)
        before = _fixture_direct_identity(
            record, fixture.realpath, require_lease=False, now_mono_ns=clock()
        )
        if before != fixture:
            raise _fixture_direct_error("ROOT_CHANGED", ParentRootReject.ROOT_RACE_DETECTED)
        result = subprocess.run(command, cwd=fixture.realpath, env=env, check=False)
        returncode = result.returncode
        after = _fixture_direct_identity(
            record, fixture.realpath, require_lease=False, now_mono_ns=clock()
        )
        if after != fixture:
            raise _fixture_direct_error("ROOT_CHANGED", ParentRootReject.ROOT_RACE_DETECTED)
    finally:
        if local_receipt is not None:
            try:
                _DEFAULT_BOUNDARY.remove_parent_owned_tree(
                    parent_attestation, local_receipt, "fixture-direct-local-cleanup"
                )
                removed = created
            except BaseException as exc:
                cleanup_detail = str(exc)
    cleanup = CleanupEvidence(
        "clean" if cleanup_detail is None else "failed", created, removed, cleanup_detail
    )
    return FixtureExecutionReceipt(
        digest, str(fixture.realpath), fixture.dev, fixture.ino, returncode, cleanup
    )


def fixture_direct_command(
    *,
    record: SessionResolutionResult,
    fixture_cwd: Path,
    argv: Sequence[str],
    now_mono_ns: int,
    clock: Callable[[], int] = time.monotonic_ns,
) -> FixtureExecutionReceipt:
    """Run one marker-bound fixture command through the private adapter."""
    return _run_fixture_direct_command(
        caller=_RECORD_FIXTURE_DIRECT_CALLER_MARKER,
        record=record,
        fixture_cwd=fixture_cwd,
        argv=argv,
        now_mono_ns=now_mono_ns,
        clock=clock,
    )


_DEFAULT_BOUNDARY = ParentRootSideEffectBoundary()
def _public_input_path(value: Path | str, name: str) -> Path:
    """Normalize public path arguments without exposing arbitrary values."""
    value_object: object = cast(object, value)
    if type(value_object) is bool or not isinstance(value_object, (Path, str)):
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, f"{name} must be a path")
    try:
        path = Path(value)
    except (TypeError, ValueError, OSError) as exc:
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, f"{name} is invalid") from exc
    if not str(path):
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, f"{name} is empty")
    if "\x00" in str(path):
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, f"{name} is invalid")
    return path


def _public_invocation_owner(invocation_script: Path | str) -> tuple[Path, Path, Path]:
    """Derive parent and source owners solely from physical cwd and script path."""
    script = _public_input_path(invocation_script, "invocation_script")
    cwd = _physical(Path.cwd(), strict=True)
    script_path = _physical(
        script if script.is_absolute() else cwd / script,
        strict=True,
    )
    if not script_path.is_file():
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "invocation_script is not a file")
    cwd_root = _git_toplevel(cwd)
    source_root = _git_toplevel(script_path.parent)
    parent_root = cwd_root
    if cwd_root == source_root:
        # A vendored checkout has its own Git root while the side-effect owner
        # is the superproject.  Admit that outer root only when the physical
        # gitlink and .gitmodules entry bind this exact source checkout; an
        # arbitrary filesystem ancestor is never inferred as authority.
        # A newly-created standalone checkout has no HEAD yet.  That is still
        # a complete physical owner; it simply cannot satisfy the stricter
        # committed-superproject binding below.  Do not weaken _git_value or
        # any other Git identity helper globally for this one optional probe.
        try:
            source_commit = _git_value(source_root, "rev-parse", "HEAD")
        except ParentRootSideEffectError:
            source_commit = None
        if source_commit is not None:
            for candidate in source_root.parents:
                manifest = candidate / ".gitmodules"
                if not manifest.is_file():
                    continue
                try:
                    if _git_toplevel(candidate) != candidate:
                        continue
                    # _module_binding is the single strict relation check:
                    # it requires a real parent HEAD, an exact .gitmodules
                    # path/url entry, and a matching 160000 gitlink OID.
                    _module_binding(candidate, manifest, source_root,
                                    ParentRootReject.MODULE_INVALID)
                except (OSError, ParentRootSideEffectError, ValueError):
                    continue
                parent_root = _physical(candidate, strict=True)
                break
    return cwd, parent_root, source_root


def _public_invocation_path(invocation_script: Path | str, cwd: Path) -> Path:
    """Resolve a nested invocation source for an already signed session."""
    script = _public_input_path(invocation_script, "invocation_script")
    script_path = _physical(
        script if script.is_absolute() else cwd / script,
        strict=True,
    )
    if not script_path.is_file():
        raise ParentRootSideEffectError(
            ParentRootReject.INPUT_INVALID, "invocation_script is not a file"
        )
    return script_path


def _public_legacy_variables(env: Mapping[str, str]) -> bool:
    return any(
        env.get(name, "")
        for name in (
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
    )


def _v2_public_bootstrap(
    *, parent_root: Path, purpose: str, source_root: Path | None,
    runner_horizon: _RunnerHorizon | None = None,
) -> tuple[SessionResolutionResult, _SupervisorIssuer]:
    now = time.monotonic_ns()
    record, key, handoff = _v2_issue_session(
        parent_root, role="supervisor", record_id=None, root=None, now_mono_ns=now,
        expires_mono_ns=runner_horizon.run_deadline_mono_ns if runner_horizon is not None else None,
        expected_expires_mono_ns=runner_horizon.run_deadline_mono_ns if runner_horizon is not None else None,
    )
    result: SessionResolutionResult | None = None
    try:
        environment = {
            SIDE_EFFECT_PARENT_ROOT_ENV: str(parent_root),
            SIDE_EFFECT_HANDOFF_ENV: handoff,
            SIDE_EFFECT_REQUIRED_ENV: "1",
        }
        result = _v2_resolve(
            env=environment,
            observed_cwd=_physical(Path.cwd(), strict=True),
            now_mono_ns=now,
        )
        # The invocation source identifies the code owner, but it is not itself
        # side-effect authority when the caller executes a checked-out tool from
        # outside the selected parent fixture.  Attestation only carries a source
        # root when the physical source tree is contained by that parent.
        owner_source = (
            source_root
            if source_root is not None
            and source_root != parent_root
            and _contains(parent_root, source_root)
            else None
        )
        attestation = _DEFAULT_BOUNDARY.attest(
            ParentRootAttestationRequest(
                cwd=parent_root, explicit_root=parent_root,
                source_root=owner_source, purpose=purpose,
            )
        )
        result = replace(
            result,
            attestation=replace(
                attestation, session_handle=handoff,
                session_lease=result.lease, session_role="supervisor",
            ),
        )
        handle = SessionIssuerHandle(record.session_id, record.issuer_id, key)
        issuer = _open_supervisor_issuer(
            session=result.record,
            resolution=result,
            issuer_handle=handle,
            now_mono_ns=now,
            runner_horizon=runner_horizon,
        )
        return result, issuer
    except BaseException as primary:
        cleanup_errors: list[BaseException] = []
        try:
            if result is not None:
                result.close()
        except BaseException as exc:
            cleanup_errors.append(exc)
        try:
            _v2_abort_session(record)
        except BaseException as exc:
            cleanup_errors.append(exc)
        if cleanup_errors:
            details = "; ".join(
                f"{type(error).__name__}: {error}" for error in cleanup_errors
            )
            cleanup_error = _v2_error(
                f"bootstrap_cleanup_failed: {details}",
                ParentRootReject.ROOT_RACE_DETECTED,
            )
            raise cleanup_error from primary
        raise


@contextmanager
def _open_runner_session(
    caller: object, invocation_script: Path | str
) -> Iterator[tuple[SessionResolutionResult, _RunnerHorizon]]:
    """Open the fixed-horizon supervisor used only by the source test runner."""
    if caller is not _RUNNER_CALLER_MARKER:
        raise _v2_error("runner_caller_marker_required", ParentRootReject.INPUT_INVALID)
    _cwd, parent_root, source_root = _public_invocation_owner(invocation_script)
    started_mono_ns = time.monotonic_ns()
    horizon = _RunnerHorizon(started_mono_ns, started_mono_ns + _RUNNER_HORIZON_NS)
    result, issuer = _v2_public_bootstrap(
        parent_root=parent_root,
        purpose="public-test-runner",
        source_root=source_root,
        runner_horizon=horizon,
    )
    try:
        # Re-read the signed record while holding the session lock.  The
        # factory must not yield a supervisor whose exact expiry differs from
        # the immutable runner horizon.
        with _v2_session_lock(result.record):
            current = _v2_read_record(_v2_record_path(result.record), issuer.handle.key)
            if current.expires_mono_ns != horizon.run_deadline_mono_ns:
                raise _v2_error("SESSION_HORIZON_MISMATCH")
    except BaseException:
        try:
            issuer.close(reason="shutdown")
        finally:
            result.close()
        raise

    session_token = _V2_SESSION_CONTEXT.set(result)
    issuer_token = _V2_ISSUER_CONTEXT.set(issuer)
    body_failed = False
    try:
        yield result, horizon
    except BaseException:
        body_failed = True
        raise
    finally:
        _V2_SESSION_CONTEXT.reset(session_token)
        _V2_ISSUER_CONTEXT.reset(issuer_token)
        cleanup_error: BaseException | None = None
        try:
            issuer.close(reason="shutdown")
        except BaseException as exc:
            cleanup_error = exc
        try:
            result.close()
        except BaseException as exc:
            if cleanup_error is None:
                cleanup_error = exc
        if cleanup_error is not None and not body_failed:
            raise cleanup_error


# The shell runner resolves this private factory dynamically, so retain an
# explicit module reference for static reachability/type checking as well.
_RUNNER_SESSION_FACTORY = _open_runner_session


@contextmanager
def public_session(
    *,
    invocation_script: Path | str,
    purpose: str,
) -> Iterator[SessionResolutionResult]:
    """Enter one direct or inherited authenticated side-effect session.

    Direct authority is derived from the physical process cwd and the physical
    owner of ``invocation_script``.  The public API intentionally has no cwd or
    parent-root selector; nested calls must reuse the signed inherited channel.
    """
    purpose_object: object = cast(object, purpose)
    if not isinstance(purpose_object, str) or not purpose_object or purpose_object != purpose_object.strip():
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "purpose is invalid")
    env = os.environ
    has_side_effect_channel = bool(env.get(SIDE_EFFECT_PARENT_ROOT_ENV) or env.get(SIDE_EFFECT_HANDOFF_ENV))
    if env.get(SIDE_EFFECT_REQUIRED_ENV) == "1" and not (
        env.get(SIDE_EFFECT_PARENT_ROOT_ENV) and env.get(SIDE_EFFECT_HANDOFF_ENV)
    ):
        raise _v2_error("session_missing")
    active = _V2_SESSION_CONTEXT.get()
    issuer = _V2_ISSUER_CONTEXT.get()
    owns_session = False
    result: SessionResolutionResult
    if has_side_effect_channel:
        cwd = _physical(Path.cwd(), strict=True)
        result = resolve_parent_side_effect_session_v2(env=env, observed_cwd=cwd)
        _public_invocation_path(invocation_script, cwd)
    elif active is not None:
        if _public_legacy_variables(env):
            raise _v2_error("legacy_authority_forbidden")
        cwd = _physical(Path.cwd(), strict=True)
        _public_invocation_path(invocation_script, cwd)
        result = active
    else:
        if _public_legacy_variables(env):
            raise _v2_error("legacy_authority_forbidden")
        _cwd, parent_root, source_root = _public_invocation_owner(invocation_script)
        result, issuer = _v2_public_bootstrap(parent_root=parent_root, purpose=purpose, source_root=source_root)
        owns_session = True
    if issuer is None and owns_session:
        raise _v2_error("supervisor_issuer_missing")
    session_token = _V2_SESSION_CONTEXT.set(result)
    issuer_token = _V2_ISSUER_CONTEXT.set(issuer) if issuer is not None else None
    body_failed = False
    try:
        yield result
    except BaseException:
        body_failed = True
        raise
    finally:
        _V2_SESSION_CONTEXT.reset(session_token)
        if issuer_token is not None:
            _V2_ISSUER_CONTEXT.reset(issuer_token)
        cleanup_error: BaseException | None = None
        if owns_session:
            assert issuer is not None
            try:
                issuer.close(reason="shutdown")
            except BaseException as exc:
                cleanup_error = exc
        try:
            result.close()
        except BaseException as exc:
            if cleanup_error is None:
                cleanup_error = exc
        if cleanup_error is not None and not body_failed:
            raise cleanup_error


def _terminate_public_process(
    process: subprocess.Popen[bytes],
    *,
    clock: Callable[[], int] = time.monotonic_ns,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Drain one process group with bounded TERM/KILL cleanup."""
    if process.poll() is not None:
        return False
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    deadline = clock() + _PUBLIC_EXEC_TERM_GRACE_NS
    while process.poll() is None and clock() < deadline:
        sleep(_PUBLIC_EXEC_POLL_NS / 1_000_000_000)
    killed = process.poll() is None
    if killed:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()
    return killed


def public_exec(
    *,
    invocation_script: Path | str,
    purpose: str,
    argv: Sequence[str],
) -> int:
    """Run a command under a direct or inherited public side-effect session."""
    argv_object: object = cast(object, argv)
    if isinstance(argv_object, (str, bytes)):
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "argv must be a sequence")
    try:
        command = tuple(cast(Sequence[object], argv_object))
    except TypeError as exc:
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "argv is invalid") from exc
    if not command or any(not isinstance(item, str) or not item or "\x00" in item for item in command):
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "argv is invalid")
    cwd = _physical(Path.cwd(), strict=True)
    with public_session(invocation_script=invocation_script, purpose=purpose) as session:
        child_base = _v2_session_environment(session, os.environ)
        for path_name in (
            "XDG_CACHE_HOME",
            "PYTHONPYCACHEPREFIX",
            "AGENT_CANON_TOOLS_HOME",
            "CARGO_HOME",
            "CARGO_TARGET_DIR",
            "AGENT_CANON_CLI_TARGET_DIR",
        ):
            child_base.pop(path_name, None)
        environment = _DEFAULT_BOUNDARY.child_environment(
            session.attestation,
            child_base,
            issue_handoff=False,
            rebase_inherited_temp=True,
        )
        process: subprocess.Popen[bytes] | None = None
        stop_requested = False
        interrupted_signum: int | None = None

        def forward_signal(signum: int, _frame: object) -> None:
            nonlocal interrupted_signum, stop_requested
            stop_requested = True
            if interrupted_signum is None:
                interrupted_signum = signum

        previous_handlers = {
            signum: signal.getsignal(signum)
            for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
        }
        for signum in previous_handlers:
            signal.signal(signum, forward_signal)
        try:
            process = subprocess.Popen(
                cast(Sequence[str], command),
                cwd=cwd,
                env=environment,
                start_new_session=True,
            )
            while process.poll() is None:
                if stop_requested:
                    _terminate_public_process(process)
                    break
                time.sleep(_PUBLIC_EXEC_POLL_NS / 1_000_000_000)
            return (
                128 + interrupted_signum
                if interrupted_signum is not None
                else process.wait()
            )
        finally:
            if process is not None and process.poll() is None:
                _terminate_public_process(process)
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)


def _cli_attestation(
    root: Path,
    *,
    purpose: str,
    source_root: Path | None = None,
    child_handoff_token: str | None = None,
) -> ParentRootAttestationReceipt:
    """Resolve the inherited record session before any CLI side effect."""
    if os.environ.get(SIDE_EFFECT_PARENT_ROOT_ENV) or os.environ.get(SIDE_EFFECT_HANDOFF_ENV):
        # ``root`` is a data target supplied to the subcommand.  Authority is
        # always revalidated against the process's physical CWD.
        resolved = resolve_parent_side_effect_session_v2(
            observed_cwd=_physical(Path.cwd(), strict=True), env=os.environ
        )
        return resolved.attestation
    active = _V2_SESSION_CONTEXT.get()
    if active is not None:
        return active.attestation
    if _public_legacy_variables(os.environ):
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID,
            "legacy_authority_forbidden",
        )
    raise ParentRootSideEffectError(
        ParentRootReject.HANDOFF_INVALID,
        "session_missing",
    )


def _close_cli_attestation(receipt: ParentRootAttestationReceipt) -> None:
    """Release a CLI session lease when the command has no write operation."""
    if receipt.session_lease is not None:
        receipt.session_lease.close()


def attest_parent_root(request: ParentRootAttestationRequest) -> ParentRootAttestationReceipt:
    """Reject the retired v1 attestation entrypoint.

    Writer modules must enter through the signed public-session resolver.  The
    request-shaped API remains only as a typed rejection boundary for old
    callers and historical test fixtures.
    """
    del request
    raise ParentRootSideEffectError(
        ParentRootReject.HANDOFF_INVALID,
        "v1_attest_parent_root_rejected: use public_session",
    )


def resolve_parent_writer_attestation(
    *,
    purpose: str,
    env: Mapping[str, str] | None = None,
) -> ParentRootAttestationReceipt:
    """Central writer adapter backed only by the signed public session."""
    observed_cwd = _physical(Path.cwd(), strict=True)
    environment = os.environ if env is None else env
    if type(purpose) is not str or not purpose or purpose != purpose.strip():
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "purpose is required")

    configured = environment.get(SIDE_EFFECT_PARENT_ROOT_ENV, "").strip()
    if configured or environment.get(SIDE_EFFECT_HANDOFF_ENV):
        session = resolve_parent_side_effect_session_v2(
            observed_cwd=observed_cwd,
            env=environment,
        )
        return session.attestation
    active = _V2_SESSION_CONTEXT.get()
    if active is not None and env is None:
        if not _contains(active.parent_root, observed_cwd):
            active.close()
            raise _v2_error("cwd_outside_parent", ParentRootReject.ROOT_MISMATCH)
        return active.attestation
    if _public_legacy_variables(environment):
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID,
            "legacy_authority_forbidden",
        )
    raise ParentRootSideEffectError(
        ParentRootReject.HANDOFF_INVALID,
        f"{purpose}: session_missing",
    )


def resolve_parent_owned_path(
    session_or_attestation: SessionResolutionResult | ParentRootAttestationReceipt,
    candidate: Path | str,
    operation_purpose: str,
    *,
    create: bool = False,
) -> ParentOwnedPathReceipt:
    """Resolve a path through a revalidated session or legacy attestation."""
    return _DEFAULT_BOUNDARY.resolve_parent_owned_path(
        session_or_attestation, candidate, operation_purpose, create=create
    )


def release_parent_owned_path(receipt: ParentOwnedPathReceipt) -> None:
    """Release a path-resolution lease that no effect operation consumed."""
    _DEFAULT_BOUNDARY.release_parent_owned_path(receipt)


def ensure_parent_owned_directory(attestation: ParentRootAttestationReceipt, candidate: Path | str,
                                  purpose: str) -> ParentOwnedPathReceipt:
    return _DEFAULT_BOUNDARY.ensure_parent_owned_directory(attestation, candidate, purpose)


def create_parent_owned_temp_directory(
    attestation: ParentRootAttestationReceipt,
    candidate: Path | str,
    purpose: str,
    prefix: str,
) -> ParentOwnedPathReceipt:
    return _DEFAULT_BOUNDARY.create_parent_owned_temp_directory(
        attestation, candidate, purpose, prefix
    )


def remove_parent_owned_tree(attestation: ParentRootAttestationReceipt, candidate: Path | str,
                             purpose: str) -> None:
    _DEFAULT_BOUNDARY.remove_parent_owned_tree(attestation, candidate, purpose)


def write_parent_owned_file(attestation: ParentRootAttestationReceipt, candidate: Path | str,
                            data: bytes, purpose: str) -> ParentOwnedPathReceipt:
    return _DEFAULT_BOUNDARY.write_parent_owned_file(attestation, candidate, data, purpose)


def capture_subprocess(
    attestation: ParentRootAttestationReceipt,
    candidate: Path | str,
    argv: Sequence[str],
    purpose: str,
) -> int:
    """Capture and replay subprocess stdout through the boundary."""
    return _DEFAULT_BOUNDARY.capture_subprocess(attestation, candidate, argv, purpose)


def git_config_add(attestation: ParentRootAttestationReceipt, candidate: Path | str,
                   key: str, value: str, purpose: str) -> ParentOwnedPathReceipt:
    """Append one Git config value through an inherited boundary file fd."""
    return _DEFAULT_BOUNDARY.git_config_add(attestation, candidate, key, value, purpose)


def copy_parent_owned_file(attestation: ParentRootAttestationReceipt, source: Path | str,
                           candidate: Path | str, purpose: str, *,
                           preserve_mode: bool = False) -> ParentOwnedPathReceipt:
    return _DEFAULT_BOUNDARY.copy_parent_owned_file(
        attestation,
        source,
        candidate,
        purpose,
        preserve_mode=preserve_mode,
    )


def copy_parent_owned_tree(attestation: ParentRootAttestationReceipt, source: Path | str,
                           candidate: Path | str, purpose: str,
                           exclude: Sequence[str] = ()) -> None:
    _DEFAULT_BOUNDARY.copy_parent_owned_tree(attestation, source, candidate, purpose, exclude)


def checkout_index_parent_owned(
    attestation: ParentRootAttestationReceipt,
    repository: Path | str,
    index_path: str,
    candidate: Path | str,
    purpose: str,
) -> ParentOwnedPathReceipt:
    """Materialize one Git index entry through boundary-owned staging."""
    return _DEFAULT_BOUNDARY.checkout_index_parent_owned(
        attestation, repository, index_path, candidate, purpose
    )


def move_parent_owned(attestation: ParentRootAttestationReceipt, source: Path | str,
                      candidate: Path | str, purpose: str) -> None:
    _DEFAULT_BOUNDARY.move_parent_owned(attestation, source, candidate, purpose)


def symlink_parent_owned(attestation: ParentRootAttestationReceipt, target: str,
                        candidate: Path | str, purpose: str) -> ParentOwnedPathReceipt:
    return _DEFAULT_BOUNDARY.symlink_parent_owned(attestation, target, candidate, purpose)


def remove_empty_parent_owned_directory(
    attestation: ParentRootAttestationReceipt,
    candidate: Path | str | ParentOwnedPathReceipt,
    purpose: str,
) -> bool:
    return _DEFAULT_BOUNDARY.remove_empty_parent_owned_directory(attestation, candidate, purpose)


def remove_empty_parent_owned_directory_cli(
    attestation: ParentRootAttestationReceipt,
    candidate: Path | str,
    purpose: str,
) -> bool:
    """Remove an empty directory through the boundary and return its state."""
    receipt = _DEFAULT_BOUNDARY.resolve_parent_owned_path(
        attestation, candidate, purpose, create=False
    )
    return _DEFAULT_BOUNDARY.remove_empty_parent_owned_directory(
        attestation, receipt, purpose
    )


def child_environment(
    attestation: ParentRootAttestationReceipt,
    base_env: Mapping[str, str] | None = None,
    *,
    issue_handoff: bool = True,
    rebase_inherited_temp: bool = False,
) -> dict[str, str]:
    return _DEFAULT_BOUNDARY.child_environment(
        attestation,
        base_env,
        issue_handoff=issue_handoff,
        rebase_inherited_temp=rebase_inherited_temp,
    )


def session_environment(
    session: SessionResolutionResult,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a child environment carrying only a signed session channel."""
    return _v2_session_environment(session, base_env)


def _run_cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("self-check")
    check.add_argument("--root", required=True, type=Path)
    check.add_argument("--sentinel-outside", type=Path)
    attest = sub.add_parser("attest")
    attest.add_argument("--root", required=True, type=Path)
    attest.add_argument("--purpose", default="shell-side-effect")
    resolve = sub.add_parser("resolve")
    resolve.add_argument("--root", required=True, type=Path)
    resolve.add_argument("--candidate", required=True, type=Path)
    resolve.add_argument("--purpose", default="shell-side-effect")
    ensure_dir = sub.add_parser("ensure-dir")
    ensure_dir.add_argument("--root", required=True, type=Path)
    ensure_dir.add_argument("--candidate", required=True, type=Path)
    ensure_dir.add_argument("--purpose", default="shell-side-effect")
    temp_dir = sub.add_parser("temp-dir")
    temp_dir.add_argument("--root", required=True, type=Path)
    temp_dir.add_argument("--candidate", required=True, type=Path)
    temp_dir.add_argument("--prefix", required=True)
    temp_dir.add_argument("--purpose", default="shell-side-effect")
    write = sub.add_parser("write")
    write.add_argument("--root", required=True, type=Path)
    write.add_argument("--candidate", required=True, type=Path)
    write.add_argument("--purpose", default="shell-side-effect")
    capture = sub.add_parser("capture-subprocess")
    capture.add_argument("--root", required=True, type=Path)
    capture.add_argument("--candidate", required=True, type=Path)
    capture.add_argument("--purpose", default="shell-side-effect")
    capture.add_argument("argv", nargs=argparse.REMAINDER)
    exec_bound = sub.add_parser("exec-parent-bound")
    exec_bound.add_argument("--root", required=True, type=Path)
    exec_bound.add_argument("--source-root", type=Path)
    exec_bound.add_argument("--consume-inherited-handoff", action="store_true")
    exec_bound.add_argument("--issue-handoff", action="store_true")
    exec_bound.add_argument("--rebase-inherited-temp", action="store_true")
    exec_bound.add_argument("--purpose", default="shell-side-effect")
    exec_bound.add_argument("argv", nargs=argparse.REMAINDER)
    public_bound = sub.add_parser("public-exec")
    public_bound.add_argument(
        "--invocation-script", required=True, type=Path
    )
    public_bound.add_argument("--purpose", required=True)
    public_bound.add_argument("argv", nargs=argparse.REMAINDER)
    verify_child = sub.add_parser("verify-child")
    verify_child.add_argument("--root", required=True, type=Path)
    verify_child.add_argument("--source-root", type=Path)
    verify_child.add_argument("--purpose", required=True)
    verify_child.add_argument("--consume", action="store_true")
    git_config = sub.add_parser("git-config-add")
    git_config.add_argument("--root", required=True, type=Path)
    git_config.add_argument("--candidate", required=True, type=Path)
    git_config.add_argument("--key", required=True)
    git_config.add_argument("--value", required=True)
    git_config.add_argument("--purpose", default="shell-side-effect")
    copy = sub.add_parser("copy")
    copy.add_argument("--root", required=True, type=Path)
    copy.add_argument("--source", required=True, type=Path)
    copy.add_argument("--candidate", required=True, type=Path)
    copy.add_argument("--preserve-mode", action="store_true")
    copy.add_argument("--purpose", default="shell-side-effect")
    copy_read_only = sub.add_parser("copy-read-only")
    copy_read_only.add_argument("--root", required=True, type=Path)
    copy_read_only.add_argument("--source", required=True, type=Path)
    copy_read_only.add_argument("--candidate", required=True, type=Path)
    copy_read_only.add_argument("--purpose", default="shell-side-effect")
    copy_tree = sub.add_parser("copy-tree")
    copy_tree.add_argument("--root", required=True, type=Path)
    copy_tree.add_argument("--source", required=True, type=Path)
    copy_tree.add_argument("--candidate", required=True, type=Path)
    copy_tree.add_argument("--exclude", action="append", default=[])
    copy_tree.add_argument("--purpose", default="shell-side-effect")
    checkout_index = sub.add_parser("checkout-index")
    checkout_index.add_argument("--root", required=True, type=Path)
    checkout_index.add_argument("--repository", required=True, type=Path)
    checkout_index.add_argument("--index-path", required=True)
    checkout_index.add_argument("--candidate", required=True, type=Path)
    checkout_index.add_argument("--purpose", default="shell-side-effect")
    move = sub.add_parser("move")
    move.add_argument("--root", required=True, type=Path)
    move.add_argument("--source", required=True, type=Path)
    move.add_argument("--candidate", required=True, type=Path)
    move.add_argument("--purpose", default="shell-side-effect")
    symlink = sub.add_parser("symlink")
    symlink.add_argument("--root", required=True, type=Path)
    symlink.add_argument("--target", required=True)
    symlink.add_argument("--candidate", required=True, type=Path)
    symlink.add_argument("--purpose", default="shell-side-effect")
    replace_symlink = sub.add_parser("replace-symlink")
    replace_symlink.add_argument("--root", required=True, type=Path)
    replace_symlink.add_argument("--target", required=True)
    replace_symlink.add_argument("--candidate", required=True, type=Path)
    replace_symlink.add_argument("--purpose", default="shell-side-effect")
    remove_file = sub.add_parser("remove-file")
    remove_file.add_argument("--root", required=True, type=Path)
    remove_file.add_argument("--candidate", required=True, type=Path)
    remove_file.add_argument("--purpose", default="shell-side-effect")
    remove_tree = sub.add_parser("remove-tree")
    remove_tree.add_argument("--root", required=True, type=Path)
    remove_tree.add_argument("--candidate", required=True, type=Path)
    remove_tree.add_argument("--purpose", default="shell-side-effect")
    remove_empty_dir = sub.add_parser("remove-empty-dir")
    remove_empty_dir.add_argument("--root", required=True, type=Path)
    remove_empty_dir.add_argument("--candidate", required=True, type=Path)
    remove_empty_dir.add_argument("--purpose", default="shell-side-effect")
    args = parser.parse_args(argv)
    try:
        if args.command == "self-check":
            receipt = _cli_attestation(args.root, purpose="self-check")
            print(json.dumps(_DEFAULT_BOUNDARY.self_check(
                args.root,
                sentinel_outside=args.sentinel_outside,
                attestation=receipt,
            ), sort_keys=True))
        elif args.command == "attest":
            receipt = _cli_attestation(args.root, purpose=args.purpose)
            try:
                print(json.dumps({"status": receipt.status, "parent_root": str(receipt.parent_root), "parent_dev": receipt.parent_dev, "parent_ino": receipt.parent_ino}, sort_keys=True))
            finally:
                _close_cli_attestation(receipt)
        elif args.command == "resolve":
            receipt = _cli_attestation(args.root, purpose=args.purpose)
            try:
                physical, _ = _physical_in_root(receipt.parent_root, args.candidate, allow_missing=True)
                print(str(physical))
            finally:
                _close_cli_attestation(receipt)
        elif args.command == "ensure-dir":
            receipt = _cli_attestation(args.root, purpose=args.purpose)
            directory = _DEFAULT_BOUNDARY.ensure_parent_owned_directory(receipt, args.candidate, args.purpose)
            print(str(directory.physical_path))
        elif args.command == "verify-child":
            if os.environ.get(SIDE_EFFECT_PARENT_ROOT_ENV) or os.environ.get(SIDE_EFFECT_HANDOFF_ENV):
                session = resolve_parent_side_effect_session_v2(
                    observed_cwd=_physical(Path.cwd(), strict=True),
                    env=os.environ,
                )
                try:
                    print(json.dumps({
                        "status": "consumed" if args.consume else "verified",
                        "audience": session.audience,
                    }))
                finally:
                    session.close()
                return 0
            request = ParentRootAttestationRequest(
                cwd=args.root,
                explicit_root=args.root,
                source_root=args.source_root,
                purpose=args.purpose,
            )
            if args.consume:
                child = _DEFAULT_BOUNDARY.reattest_child(request, os.environ)
                audience = child.handoff.audience if child.handoff else args.purpose
                status = "consumed"
            else:
                handoff = _DEFAULT_BOUNDARY.verify_child_environment(
                    request, os.environ
                )
                audience = handoff.audience
                status = "verified"
            print(json.dumps({"status": status, "audience": audience}))
        elif args.command == "public-exec":
            command = list(args.argv)
            if command and command[0] == "--":
                command = command[1:]
            return public_exec(
                invocation_script=args.invocation_script,
                purpose=args.purpose,
                argv=command,
            )
        else:
            child_handoff_token = None
            source_root = None
            if args.command == "exec-parent-bound":
                source_root = args.source_root
                if args.consume_inherited_handoff:
                    child_handoff_token = os.environ.get("AGENT_CANON_CHILD_HANDOFF")
                    if not child_handoff_token:
                        raise ParentRootSideEffectError(
                            ParentRootReject.HANDOFF_INVALID,
                            "inherited child handoff is missing",
                        )
            receipt = _cli_attestation(
                args.root,
                source_root=source_root,
                child_handoff_token=child_handoff_token,
                purpose=args.purpose,
            )
            if args.command == "temp-dir":
                directory = _DEFAULT_BOUNDARY.create_parent_owned_temp_directory(
                    receipt, args.candidate, args.purpose, args.prefix
                )
                print(str(directory.physical_path))
            elif args.command == "write":
                published = _DEFAULT_BOUNDARY.write_parent_owned_file(
                    receipt, args.candidate, sys.stdin.buffer.read(), args.purpose
                )
                print(str(published.physical_path))
            elif args.command == "capture-subprocess":
                command = list(args.argv)
                if command and command[0] == "--":
                    command = command[1:]
                return _DEFAULT_BOUNDARY.capture_subprocess(
                    receipt, args.candidate, command, args.purpose
                )
            elif args.command == "exec-parent-bound":
                command = list(args.argv)
                if command and command[0] == "--":
                    command = command[1:]
                return _DEFAULT_BOUNDARY.exec_parent_bound(
                    receipt,
                    command,
                    args.purpose,
                    issue_handoff=args.issue_handoff,
                    rebase_inherited_temp=args.rebase_inherited_temp,
                )
            elif args.command == "git-config-add":
                published = _DEFAULT_BOUNDARY.git_config_add(
                    receipt, args.candidate, args.key, args.value, args.purpose
                )
                print(str(published.physical_path))
            elif args.command == "copy":
                published = _DEFAULT_BOUNDARY.copy_parent_owned_file(
                    receipt,
                    args.source,
                    args.candidate,
                    args.purpose,
                    preserve_mode=args.preserve_mode,
                )
                print(str(published.physical_path))
            elif args.command == "copy-read-only":
                published = _DEFAULT_BOUNDARY.copy_read_only_file(
                    receipt, args.source, args.candidate, args.purpose
                )
                print(str(published.physical_path))
            elif args.command == "copy-tree":
                _DEFAULT_BOUNDARY.copy_parent_owned_tree(
                    receipt, args.source, args.candidate, args.purpose, args.exclude
                )
                print(str(args.candidate))
            elif args.command == "checkout-index":
                published = _DEFAULT_BOUNDARY.checkout_index_parent_owned(
                    receipt,
                    args.repository,
                    args.index_path,
                    args.candidate,
                    args.purpose,
                )
                print(str(published.physical_path))
            elif args.command == "move":
                _DEFAULT_BOUNDARY.move_parent_owned(receipt, args.source, args.candidate, args.purpose)
                print(str(args.candidate))
            elif args.command == "symlink":
                link = _DEFAULT_BOUNDARY.symlink_parent_owned(
                    receipt, args.target, args.candidate, args.purpose
                )
                print(str(link.physical_path))
            elif args.command == "replace-symlink":
                link = _DEFAULT_BOUNDARY.replace_parent_owned_symlink(
                    receipt, args.target, args.candidate, args.purpose
                )
                print(str(link))
            elif args.command == "remove-file":
                target = _DEFAULT_BOUNDARY.resolve_parent_owned_path(
                    receipt, args.candidate, args.purpose, create=False
                )
                _DEFAULT_BOUNDARY.remove_parent_owned_file(target)
                print(str(target.physical_path))
            elif args.command == "remove-tree":
                target = _DEFAULT_BOUNDARY.resolve_parent_owned_path(
                    receipt, args.candidate, args.purpose, create=False
                )
                _DEFAULT_BOUNDARY.remove_parent_owned_tree(receipt, target, args.purpose)
                print(str(target.physical_path))
            elif args.command == "remove-empty-dir":
                removed = remove_empty_parent_owned_directory_cli(
                    receipt, args.candidate, args.purpose
                )
                print(str(removed).lower())
        return 0
    except ParentRootSideEffectError as exc:
        print(f"PARENT_ROOT_SIDE_EFFECT_ERROR={exc}", file=sys.stderr)
        return 2


def _main(argv: Sequence[str] | None = None) -> int:
    """Bootstrap the public effect CLI before parsing data targets."""
    raw_argv = tuple(sys.argv[1:] if argv is None else argv)
    raw_items = tuple(cast(Sequence[object], raw_argv))
    if any(not isinstance(item, str) for item in raw_items):
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "argv is invalid")
    try:
        if not raw_argv:
            return _run_cli(raw_argv)
        command = next((item for item in raw_argv if not item.startswith("-")), "effect-cli")
        if os.environ.get(SIDE_EFFECT_PARENT_ROOT_ENV) or os.environ.get(SIDE_EFFECT_HANDOFF_ENV):
            return _run_cli(raw_argv)
        with public_session(
            invocation_script=Path(__file__),
            purpose=f"public-effect-cli:{command}",
        ):
            return _run_cli(raw_argv)
    except ParentRootSideEffectError as exc:
        print(f"PARENT_ROOT_SIDE_EFFECT_ERROR={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
