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
import errno
import fcntl
import hashlib
import hmac
import json
import math
import os
import secrets
import stat
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from types import TracebackType
from typing import TextIO, cast

SCHEMA_REQUEST = "agent-canon.parent-root-attestation-request.v1"
SCHEMA_RECEIPT = "agent-canon.parent-root-attestation-receipt.v1"
SCHEMA_HANDOFF = "agent-canon.child-handoff.v1"
SCHEMA_PATH = "agent-canon.parent-owned-path-receipt.v1"
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


@dataclass
class ParentOwnedTargetHandle:
    """An exclusively reserved, parent-owned directory kept open for a child."""

    parent_fd: int
    target_fd: int
    physical_path: Path
    purpose: str
    target_dev: int
    target_ino: int

    @property
    def proc_path(self) -> str:
        """Return the inherited fd path used by the child process."""
        return f"/proc/self/fd/{self.target_fd}"

    def close(self) -> None:
        """Close the target and its parent capability exactly once."""
        target_fd, parent_fd = self.target_fd, self.parent_fd
        self.target_fd = -1
        self.parent_fd = -1
        if target_fd >= 0:
            os.close(target_fd)
        if parent_fd >= 0:
            os.close(parent_fd)


@dataclass
class ParentOwnedFileHandle:
    """A locked text file opened beneath an authenticated parent receipt."""

    stream: TextIO
    physical_path: Path
    purpose: str
    target_dev: int
    target_ino: int
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
        ambient_root = os.environ.get("AGENT_CANON_ACTIVE_REPOSITORY_ROOT", "").strip()
        if ambient_root and _physical(Path(ambient_root), strict=True) != root:
            raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH,
                                            "ambient active repository root is inconsistent")
        parent_dev, parent_ino = _identity(root)
        source = _physical(request.source_root, strict=True) if request.source_root else None
        clone = _physical(request.clone_root, strict=True) if request.clone_root else None
        for label, path in (("source", source), ("clone", clone)):
            if path is None:
                continue
            if not _contains(root, path):
                raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH, f"{label} root is outside parent root")
            if _git_toplevel(path) != path:
                raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH, f"{label} is not an authenticated Git checkout")
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

    def resolve_parent_owned_path(self, attestation: ParentRootAttestationReceipt,
                                  candidate: Path | str, purpose: str, *, create: bool = False) -> ParentOwnedPathReceipt:
        if attestation.status != "attested":
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "attestation is not active")
        root = attestation.parent_root
        physical, _ = _physical_in_root(root, candidate, allow_missing=True)
        if create:
            parent_fd, name, _ = _parent_directory(root, physical, create=True)
            try:
                try:
                    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent_fd)
                    os.close(fd)
                except FileExistsError:
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
                    os.close(fd)
            except OSError as exc:
                raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED, f"cannot create target: {exc}") from exc
            finally:
                os.close(parent_fd)
            physical, _ = _physical_in_root(root, candidate, allow_missing=False)
        # Open every existing physical component once.  A missing parent is
        # permitted for a later atomic create; publication will create it by
        # dirfd before opening the final component.
        try:
            parent_fd, _, _ = _parent_directory(root, physical, create=False)
        except ParentRootSideEffectError as exc:
            if exc.reject is not ParentRootReject.ROOT_MISSING:
                raise
            parent_components: tuple[tuple[str, int, int], ...] = ()
        else:
            os.close(parent_fd)
            parent_components = _component_identities(
                root, tuple(physical.relative_to(root).parts)[:-1], create=False
            )
        if _identity(root) != (attestation.parent_dev, attestation.parent_ino):
            raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED, "parent identity changed")
        lexical = _lexical_candidate(root, candidate)
        target = None
        try:
            info = physical.stat()
            target = (info.st_dev, info.st_ino)
        except FileNotFoundError:
            pass
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
        )
        try:
            return replace(receipt, **_lexical_snapshot(root, lexical))
        except ParentRootSideEffectError as exc:
            if exc.reject is not ParentRootReject.ROOT_MISSING:
                raise
            return receipt

    def ensure_parent_owned_directory(self, attestation: ParentRootAttestationReceipt,
                                      candidate: Path | str, purpose: str) -> ParentOwnedPathReceipt:
        """Create and re-open a parent-local directory through component dirfds."""
        if attestation.status != "attested":
            raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "attestation is not active")
        physical, parts = _physical_in_root(attestation.parent_root, candidate, allow_missing=True)
        directory_fd, _ = _open_components(attestation.parent_root, parts, create=True)
        os.fsync(directory_fd)
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
        )
        return replace(receipt, **_lexical_snapshot(attestation.parent_root, lexical))

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
        if sys.platform != "linux":
            raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform)
        if mode not in {"a+", "r+"}:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                f"unsupported parent-owned file mode: {mode}",
            )
        if mode == "r+" and create:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                "r+ parent-owned files cannot create a missing target",
            )
        if mode == "a+" and not create:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                "a+ parent-owned files require create=True",
            )
        root = attestation.parent_root
        physical, _ = _physical_in_root(root, candidate, allow_missing=create)
        parent_fd, name, _ = _parent_directory(root, physical, create=create)
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
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH, "temporary-directory prefix is invalid"
            )
        base = self.ensure_parent_owned_directory(attestation, candidate, purpose)
        parent_fd, _ = _open_components(
            attestation.parent_root,
            tuple(base.physical_path.relative_to(attestation.parent_root).parts),
            create=False,
        )
        try:
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
            os.close(parent_fd)

    def open_parent_owned_target(self, attestation: ParentRootAttestationReceipt,
                                 candidate: Path | str, purpose: str) -> ParentOwnedTargetHandle:
        """Reserve and open an empty directory without a parent-fd/name gap.

        The final directory is created with mkdirat semantics and then kept open
        while Git runs.  The child receives the inherited target fd itself;
        resolving a parent fd plus a pathname in the child would reintroduce a
        replacement race between attestation and clone.
        """
        if sys.platform != "linux":
            raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform)
        physical, _ = _physical_in_root(attestation.parent_root, candidate, allow_missing=True)
        parent_fd, name, _ = _parent_directory(attestation.parent_root, physical, create=True)
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
            return ParentOwnedTargetHandle(
                parent_fd=parent_fd,
                target_fd=target_fd,
                physical_path=physical,
                purpose=purpose,
                target_dev=info.st_dev,
                target_ino=info.st_ino,
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

    def atomic_publish(self, receipt: ParentOwnedPathReceipt, data: bytes) -> ParentOwnedPathReceipt:
        """Publish with same-directory O_EXCL temp, fsync, renameat, and identity checks."""
        if sys.platform != "linux":
            raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform)
        root = receipt.parent_root
        before = _identity(root)
        if before != (receipt.parent_dev, receipt.parent_ino):
            raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED, "parent identity changed before publish")
        if receipt.parent_components:
            _verify_parent_components(receipt)
        physical, _ = _physical_in_root(root, receipt.physical_path, allow_missing=True)
        parent_fd, name, _ = _parent_directory(root, physical, create=True)
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
        if mode & ~0o777:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                f"unsupported file mode: {mode:o}",
            )
        _verify_parent_components(receipt)
        parent_fd, name, _ = _parent_directory(
            receipt.parent_root, receipt.physical_path, create=False
        )
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
        return self.resolve_parent_owned_path(
            attestation, receipt.physical_path, receipt.purpose, create=False
        )

    def publish_parent_owned_file_noreplace(
        self,
        attestation: ParentRootAttestationReceipt,
        candidate: Path | str,
        data: bytes,
        purpose: str,
    ) -> tuple[str, str]:
        """Publish one file without replacing an existing parent-owned target."""
        if sys.platform != "linux":
            raise ParentRootSideEffectError(
                ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform
            )
        receipt = self.resolve_parent_owned_path(attestation, candidate, purpose)
        root = receipt.parent_root
        before = _identity(root)
        if before != (receipt.parent_dev, receipt.parent_ino):
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                "parent identity changed before no-replace publication",
            )
        physical, _ = _physical_in_root(root, receipt.physical_path, allow_missing=True)
        parent_fd, name, _ = _parent_directory(root, physical, create=True)
        if not receipt.parent_components:
            receipt = replace(
                receipt,
                parent_components=_component_identities(
                    root,
                    tuple(physical.relative_to(root).parts)[:-1],
                    create=False,
                ),
            )
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
        if not argv or any("\x00" in argument for argument in argv):
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                "subprocess command is empty or contains NUL",
            )
        receipt = self.resolve_parent_owned_path(attestation, candidate, purpose)
        result = subprocess.run(
            list(argv),
            stdout=subprocess.PIPE,
            check=False,
            env=self.child_environment(attestation, issue_handoff=False),
        )
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
            raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH, "Git config key is invalid")
        if "\x00" in value or "\r" in value:
            raise ParentRootSideEffectError(ParentRootReject.ROOT_MISMATCH, "Git config value is invalid")
        receipt = self.resolve_parent_owned_path(attestation, candidate, purpose)
        if receipt.target_dev is None or receipt.target_ino is None:
            receipt = self.atomic_publish(receipt, b"")
        _verify_parent_components(receipt)
        physical, _ = _physical_in_root(attestation.parent_root, receipt.physical_path, allow_missing=False)
        parent_fd, name, _ = _parent_directory(attestation.parent_root, physical, create=False)
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
        readback = self.resolve_parent_owned_path(attestation, physical, purpose)
        if readback.target_dev is None or readback.target_ino is None:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                "Git config target disappeared after write",
            )
        return readback

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
            raise
        except OSError as exc:
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
        source_physical, _ = _physical_in_root(attestation.parent_root, source, allow_missing=False)
        target = self.ensure_parent_owned_directory(attestation, candidate, purpose)
        source_fd, _ = _open_components(
            attestation.parent_root,
            tuple(source_physical.relative_to(attestation.parent_root).parts),
            create=False,
        )
        target_fd, _ = _open_components(
            attestation.parent_root,
            tuple(target.physical_path.relative_to(attestation.parent_root).parts),
            create=False,
        )
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
        if (
            not index_path
            or "\x00" in index_path
            or Path(index_path).is_absolute()
            or any(part in {"", ".", ".."} for part in Path(index_path).parts)
        ):
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                f"checkout-index path is invalid: {index_path!r}",
            )
        repository_path, _ = _physical_in_root(
            attestation.parent_root, repository, allow_missing=False
        )
        stage_base = self.ensure_parent_owned_directory(
            attestation,
            attestation.parent_root / ".agent-canon" / "tmp" / "checkout-index",
            purpose,
        )
        stage = self.create_parent_owned_temp_directory(
            attestation, stage_base.physical_path, purpose, "entry"
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
        target_fd, target_name, _ = _parent_directory(attestation.parent_root, target_physical, create=True)
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

    def symlink_parent_owned(
        self,
        attestation: ParentRootAttestationReceipt,
        target: str,
        candidate: Path | str,
        purpose: str,
    ) -> ParentOwnedPathReceipt:
        """Create a non-replacing symlink in an authenticated parent."""
        physical, _ = _physical_in_root(attestation.parent_root, candidate, allow_missing=True)
        parent_fd, name, _ = _parent_directory(attestation.parent_root, physical, create=True)
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
        return self.resolve_parent_owned_path(attestation, physical, purpose)

    def replace_parent_owned_symlink(
        self,
        attestation: ParentRootAttestationReceipt,
        target: str,
        candidate: Path | str,
        purpose: str,
    ) -> Path:
        """Atomically replace one symlink below an authenticated parent root."""
        if "\x00" in target:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH, "symlink target contains NUL"
            )
        root = attestation.parent_root
        before = _identity(root)
        lexical = _lexical_candidate(root, candidate)
        if not _contains(root, lexical):
            raise ParentRootSideEffectError(
                ParentRootReject.SYMLINK_ESCAPE,
                f"symlink candidate is outside parent root: {lexical}",
            )
        self.ensure_parent_owned_directory(
            attestation, lexical.parent, f"{purpose}-parent"
        )
        parent_fd, name, _ = _parent_directory(root, lexical, create=True)
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
        return lexical

    def remove_parent_owned_tree(self, attestation: ParentRootAttestationReceipt,
                                 candidate: Path | str | ParentOwnedPathReceipt, purpose: str) -> None:
        """Remove one parent-local directory tree through no-follow dirfds."""
        if sys.platform != "linux":
            raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform)
        before = _identity(attestation.parent_root)
        expected_dev = expected_ino = None
        if isinstance(candidate, ParentOwnedPathReceipt):
            physical = candidate.physical_path
            expected_dev, expected_ino = candidate.target_dev, candidate.target_ino
            _verify_parent_components(candidate)
            if expected_dev is None or expected_ino is None:
                raise ParentRootSideEffectError(
                    ParentRootReject.ROOT_RACE_DETECTED,
                    "tree removal requires a published target identity",
                )
        else:
            physical, _ = _physical_in_root(attestation.parent_root, candidate, allow_missing=False)
        parent_fd, name, _ = _parent_directory(attestation.parent_root, physical, create=False)
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
        if _identity(attestation.parent_root) != before:
            raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED,
                                            "parent identity changed during removal")

    def read_parent_owned_file(self, receipt: ParentOwnedPathReceipt) -> bytes:
        """Read a capability target through its parent directory fd."""
        root = receipt.parent_root
        _verify_parent_components(receipt)
        physical, _ = _physical_in_root(root, receipt.physical_path, allow_missing=False)
        parent_fd, name, _ = _parent_directory(root, physical, create=False)
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
            return os.read(fd, 1 << 24)
        except OSError as exc:
            raise ParentRootSideEffectError(ParentRootReject.ROOT_RACE_DETECTED,
                                            f"cannot read parent-owned file: {exc}") from exc
        finally:
            if fd >= 0:
                os.close(fd)
            os.close(parent_fd)

    def remove_empty_parent_owned_directory(
        self,
        attestation: ParentRootAttestationReceipt,
        candidate: Path | str | ParentOwnedPathReceipt,
        purpose: str,
    ) -> bool:
        """Remove an owned directory after an fd-bound empty check."""
        if sys.platform != "linux":
            raise ParentRootSideEffectError(ParentRootReject.UNSUPPORTED_PLATFORM, sys.platform)
        before = _identity(attestation.parent_root)
        if isinstance(candidate, ParentOwnedPathReceipt):
            physical = candidate.physical_path
            expected = (candidate.target_dev, candidate.target_ino)
            _verify_parent_components(candidate)
        else:
            physical, _ = _physical_in_root(attestation.parent_root, candidate, allow_missing=False)
            expected = (None, None)
        parent_fd, name, _ = _parent_directory(attestation.parent_root, physical, create=False)
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
        if _identity(attestation.parent_root) != before:
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_RACE_DETECTED,
                "parent identity changed during empty removal",
            )
        return empty

    def remove_parent_owned_file(self, receipt: ParentOwnedPathReceipt) -> None:
        """Unlink a lexical receipt entry through its no-follow parent fd."""
        root = receipt.parent_root
        is_symlink = receipt.lexical_entry_type == stat.S_IFLNK
        if not is_symlink:
            _verify_parent_components(receipt)
        parent_fd, name = _open_lexical_entry(receipt)
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
    ) -> dict[str, str]:
        """Create fixed parent-local paths and transport a single-use handoff."""
        env = dict(os.environ if base_env is None else base_env)
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
        env["AGENT_CANON_ACTIVE_REPOSITORY_ROOT"] = str(root)
        env["AGENT_CANON_PARENT_ROOT"] = str(root)
        env["AGENT_CANON_SOURCE_ROOT"] = str(attestation.source_root or root)
        env["AGENT_CANON_PARENT_ROOT_DEV"] = str(attestation.parent_dev)
        env["AGENT_CANON_PARENT_ROOT_INO"] = str(attestation.parent_ino)
        if issue_handoff:
            handoff = self.issue_child_handoff(
                root,
                audience=attestation.purpose,
                source_root=attestation.source_root,
                clone_root=attestation.clone_root,
            )
            env["AGENT_CANON_CHILD_HANDOFF"] = handoff
            env["AGENT_CANON_HANDOFF_AUDIENCE"] = attestation.purpose
        else:
            env.pop("AGENT_CANON_CHILD_HANDOFF", None)
            env.pop("AGENT_CANON_HANDOFF_AUDIENCE", None)
            env.pop("AGENT_CANON_CHILD_PURPOSE", None)
        return env

    def exec_parent_bound(
        self,
        attestation: ParentRootAttestationReceipt,
        argv: Sequence[str],
        purpose: str,
        *,
        issue_handoff: bool = False,
    ) -> int:
        """Create parent-owned child env and execute argv without a shell."""
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
        env = self.child_environment(attestation, issue_handoff=issue_handoff)
        if issue_handoff:
            env["AGENT_CANON_CHILD_PURPOSE"] = purpose
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

    def self_check(self, root: Path, *, sentinel_outside: Path | None = None) -> dict[str, object]:
        before_home = os.environ.get("HOME")
        att = self.attest(ParentRootAttestationRequest(cwd=root, explicit_root=root, purpose="self-check"))
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


_DEFAULT_BOUNDARY = ParentRootSideEffectBoundary()


def attest_parent_root(request: ParentRootAttestationRequest) -> ParentRootAttestationReceipt:
    return _DEFAULT_BOUNDARY.attest(request)


def resolve_parent_owned_path(attestation: ParentRootAttestationReceipt, candidate: Path | str,
                              purpose: str, *, create: bool = False) -> ParentOwnedPathReceipt:
    return _DEFAULT_BOUNDARY.resolve_parent_owned_path(attestation, candidate, purpose, create=create)


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
) -> dict[str, str]:
    return _DEFAULT_BOUNDARY.child_environment(
        attestation,
        base_env,
        issue_handoff=issue_handoff,
    )


def _main(argv: Sequence[str] | None = None) -> int:
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
    exec_bound.add_argument("--purpose", default="shell-side-effect")
    exec_bound.add_argument("argv", nargs=argparse.REMAINDER)
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
            print(json.dumps(_DEFAULT_BOUNDARY.self_check(args.root, sentinel_outside=args.sentinel_outside), sort_keys=True))
        elif args.command == "attest":
            receipt = _DEFAULT_BOUNDARY.attest(ParentRootAttestationRequest(cwd=args.root, explicit_root=args.root, purpose=args.purpose))
            print(json.dumps({"status": receipt.status, "parent_root": str(receipt.parent_root), "parent_dev": receipt.parent_dev, "parent_ino": receipt.parent_ino}, sort_keys=True))
        elif args.command == "resolve":
            receipt = _DEFAULT_BOUNDARY.attest(ParentRootAttestationRequest(cwd=args.root, explicit_root=args.root, purpose=args.purpose))
            physical, _ = _physical_in_root(receipt.parent_root, args.candidate, allow_missing=True)
            print(str(physical))
        elif args.command == "ensure-dir":
            receipt = _DEFAULT_BOUNDARY.attest(ParentRootAttestationRequest(cwd=args.root, explicit_root=args.root, purpose=args.purpose))
            directory = _DEFAULT_BOUNDARY.ensure_parent_owned_directory(receipt, args.candidate, args.purpose)
            print(str(directory.physical_path))
        elif args.command == "verify-child":
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
            receipt = _DEFAULT_BOUNDARY.attest(
                ParentRootAttestationRequest(
                    cwd=args.root,
                    explicit_root=args.root,
                    source_root=source_root,
                    child_handoff_token=child_handoff_token,
                    purpose=args.purpose,
                )
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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
