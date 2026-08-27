#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns the external AgentCanon runtime artifact boundary and typed root capabilities.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md runtime-root ownership and side-effect boundary
# downstream implementation ./runtime_log_paths.py resolves external runtime paths
# downstream implementation ./run_accumulated_agent_evals.py propagates runtime capabilities to producers
# downstream implementation ../../tests/agent_tools/test_runtime_artifacts.py validates source exclusion and atomic writes
# @dependency-end
"""Resolve and publish AgentCanon runtime artifacts outside source trees.

Runtime output is deliberately a separate capability from an intentional
target mutation.  Callers must provide an explicit runtime root (or the
``AGENT_CANON_RUNTIME_ROOT`` environment variable); there is no source-tree,
HOME, or XDG fallback.  Every path is resolved beneath that root and writes
are published with a same-directory temporary file and atomic rename.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows does not expose flock.
    fcntl = None  # type: ignore[assignment]


RUNTIME_ROOT_ENV = "AGENT_CANON_RUNTIME_ROOT"
PARENT_ROOT_ENV = "AGENT_CANON_PARENT_ROOT"
TARGET_ROOT_ENV = "AGENT_CANON_TARGET_ROOT"
PARENT_ROOT_CAPABILITY_ENV = "AGENT_CANON_PARENT_ROOT_CAPABILITY"
TARGET_ROOT_CAPABILITY_ENV = "AGENT_CANON_TARGET_ROOT_CAPABILITY"
PARENT_ROOT_DEV_ENV = "AGENT_CANON_PARENT_ROOT_DEV"
PARENT_ROOT_INO_ENV = "AGENT_CANON_PARENT_ROOT_INO"
TARGET_ROOT_DEV_ENV = "AGENT_CANON_TARGET_ROOT_DEV"
TARGET_ROOT_INO_ENV = "AGENT_CANON_TARGET_ROOT_INO"
SAFE_CHILD_ENV_NAMES = frozenset(
    {
        "PATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED",
        "SYSTEMROOT",
        "PATHEXT",
    }
)


class RuntimeArtifactError(RuntimeError):
    """Base class for typed runtime artifact boundary errors."""


class RuntimeRootRequired(RuntimeArtifactError):
    """Raised when no explicit runtime root was supplied."""


class RuntimeRootInvalid(RuntimeArtifactError):
    """Raised when the runtime root is unsafe or unavailable."""


class SourceLocalArtifact(RuntimeArtifactError):
    """Raised when runtime output would be placed in the source checkout."""


class RuntimePathEscape(RuntimeArtifactError):
    """Raised when a path escapes the declared runtime root."""


class RuntimeSymlinkEscape(RuntimeArtifactError):
    """Raised when a symlink can redirect runtime output."""


SOURCE_RUNTIME_DIRECTORY = ".runtime"
SOURCE_RUNTIME_ALLOWED_TOP_LEVELS = frozenset({"locks", "spool"})


def root_capability_environment(
    *,
    source_root: Path,
    runtime_root: Path,
    base_env: dict[str, str] | None = None,
    target_root: Path | None = None,
) -> dict[str, str]:
    """Return a typed, non-secret environment for a producer child.

    The runtime root is the only write authority.  Parent and target roots are
    carried separately so a child cannot mistake the runtime control plane for
    the project it is analysing.  Identity fields make the handoff auditable
    and let consumers reject a replaced directory before using it.
    """
    parent = source_root.expanduser().resolve()
    target = (target_root or source_root).expanduser().resolve()
    runtime = runtime_root.expanduser().resolve()
    supplied = os.environ if base_env is None else base_env
    env = {
        name: value
        for name, value in supplied.items()
        if name in SAFE_CHILD_ENV_NAMES or name.startswith("LC_")
    }

    def identity(path: Path) -> tuple[str, str]:
        try:
            stat_result = path.stat()
        except OSError as exc:
            raise RuntimeRootInvalid(f"root capability is unavailable: {path}") from exc
        return str(stat_result.st_dev), str(stat_result.st_ino)

    parent_dev, parent_ino = identity(parent)
    target_dev, target_ino = identity(target)
    runtime_dev, runtime_ino = identity(runtime)
    env.update(
        {
            RUNTIME_ROOT_ENV: str(runtime),
            PARENT_ROOT_ENV: str(parent),
            TARGET_ROOT_ENV: str(target),
            PARENT_ROOT_DEV_ENV: parent_dev,
            PARENT_ROOT_INO_ENV: parent_ino,
            TARGET_ROOT_DEV_ENV: target_dev,
            TARGET_ROOT_INO_ENV: target_ino,
            PARENT_ROOT_CAPABILITY_ENV: json.dumps(
                {"kind": "parent-root", "root": str(parent), "dev": parent_dev, "ino": parent_ino},
                sort_keys=True,
                separators=(",", ":"),
            ),
            TARGET_ROOT_CAPABILITY_ENV: json.dumps(
                {"kind": "target-root", "root": str(target), "dev": target_dev, "ino": target_ino},
                sort_keys=True,
                separators=(",", ":"),
            ),
            "AGENT_CANON_RUNTIME_ROOT_DEV": runtime_dev,
            "AGENT_CANON_RUNTIME_ROOT_INO": runtime_ino,
        }
    )
    return env


def _absolute(path: Path, *, field: str) -> Path:
    if not path.is_absolute():
        raise RuntimeRootInvalid(f"{field} must be absolute: {path}")
    return path


def _resolved_source(source_root: Path) -> Path:
    try:
        # Path resolution is also used to render a cleanup/readback location
        # after a short-lived source fixture has already been removed.  The
        # artifact publisher still validates its destination beneath the
        # existing runtime root; source absence is not a reason to invent a
        # source-local fallback.
        return source_root.expanduser().resolve(strict=False)
    except OSError as exc:
        raise RuntimeRootInvalid(f"source root is unavailable: {source_root}") from exc


def _reject_symlink_components(path: Path, stop: Path) -> None:
    """Reject existing symlink components between ``stop`` and ``path``."""
    current = stop
    try:
        relative = path.relative_to(stop)
    except ValueError as exc:  # pragma: no cover - callers validate first.
        raise RuntimePathEscape(f"path is outside runtime root: {path}") from exc
    for part in relative.parts:
        current /= part
        try:
            if current.is_symlink():
                raise RuntimeSymlinkEscape(f"symlink component is not allowed: {current}")
        except OSError as exc:
            raise RuntimeArtifactError(f"cannot inspect runtime path: {current}") from exc


def _contains(parent: Path, child: Path) -> bool:
    return child == parent or parent in child.parents


def resolve_runtime_root(
    source_root: Path,
    runtime_root: Path | str | None = None,
    *,
    create: bool = False,
) -> Path:
    """Return a validated explicit runtime root.

    The root may live beside or above a source checkout (as in the shared
    control-plane layout), but it may never be the checkout itself or a child
    of it.  Existing root symlinks are rejected so a later write cannot be
    redirected outside the owner-selected root.
    """
    configured = runtime_root
    if configured is None:
        configured = os.environ.get(RUNTIME_ROOT_ENV, "").strip() or None
    if configured is None:
        raise RuntimeRootRequired(
            f"explicit runtime root required; pass --runtime-root or set {RUNTIME_ROOT_ENV}"
        )
    candidate = _absolute(Path(configured).expanduser(), field="runtime root")
    source = _resolved_source(source_root)
    try:
        _reject_symlink_components(candidate, Path(candidate.anchor))
        if candidate.exists() and candidate.is_symlink():
            raise RuntimeSymlinkEscape(f"runtime root is a symlink: {candidate}")
        planned = candidate.resolve(strict=False)
        if _contains(source, planned):
            raise SourceLocalArtifact(
                f"runtime root must not be inside source root: source={source} runtime={planned}"
            )
        if create:
            candidate.mkdir(parents=True, exist_ok=True)
        root = candidate.resolve(strict=create)
    except RuntimeArtifactError:
        raise
    except OSError as exc:
        raise RuntimeRootInvalid(f"runtime root is unavailable: {candidate}") from exc
    if create and not root.is_dir():
        raise RuntimeRootInvalid(f"runtime root is not a directory: {root}")
    if _contains(source, root):
        raise SourceLocalArtifact(
            f"runtime root must not be inside source root: source={source} runtime={root}"
        )
    return root


def _resolve_runtime_spool_root(
    source_root: Path,
    runtime_root: Path | str | None = None,
    *,
    create: bool = False,
) -> tuple[Path, bool]:
    """Resolve a spool boundary, allowing only the bootstrap source runtime.

    The ordinary runtime boundary remains source-external.  The resident
    bootstrap has one narrowly different capability: its source checkout may
    own the exact ``<source>/.runtime`` control directory.  That capability
    is limited by :meth:`RuntimeArtifactBoundary.resolve` to the ``locks``
    and ``spool`` subtrees; archive/report paths are never admitted here.
    """
    configured = runtime_root
    if configured is None:
        configured = os.environ.get(RUNTIME_ROOT_ENV, "").strip() or None
    if configured is None:
        raise RuntimeRootRequired(
            f"explicit runtime root required; pass --runtime-root or set {RUNTIME_ROOT_ENV}"
        )
    source = _resolved_source(source_root)
    candidate = _absolute(Path(configured).expanduser(), field="runtime root")
    source_runtime = source / SOURCE_RUNTIME_DIRECTORY
    try:
        planned = candidate.resolve(strict=False)
        if planned == source_runtime:
            # A source-local runtime is valid only as the exact bootstrap path;
            # every existing component is checked before it can be followed.
            _reject_symlink_components(candidate, Path(candidate.anchor))
            if candidate != source_runtime:
                raise RuntimeSymlinkEscape(
                    f"source runtime path is not canonical: {candidate}"
                )
            if create:
                candidate.mkdir(parents=True, exist_ok=True)
            elif candidate.exists() and not candidate.is_dir():
                raise RuntimeRootInvalid(
                    f"source runtime root is not a directory: {candidate}"
                )
            root = candidate.resolve(strict=create)
            if root != source_runtime or (create and not root.is_dir()):
                raise RuntimeRootInvalid(
                    f"source runtime root is not a directory: {candidate}"
                )
            return root, True
    except RuntimeArtifactError:
        raise
    except OSError as exc:
        raise RuntimeRootInvalid(f"runtime root is unavailable: {candidate}") from exc

    # Shared/external runtime roots retain the complete ordinary boundary.
    return resolve_runtime_root(source, candidate, create=create), False


@dataclass(frozen=True)
class RuntimeArtifactBoundary:
    """Typed external-artifact resolver and atomic publisher."""

    source_root: Path
    root: Path
    source_runtime_spool: bool = False

    @classmethod
    def for_source(
        cls,
        source_root: Path,
        runtime_root: Path | str | None = None,
        *,
        create: bool = False,
    ) -> "RuntimeArtifactBoundary":
        source = _resolved_source(source_root)
        root = resolve_runtime_root(source, runtime_root, create=create)
        return cls(source_root=source, root=root)

    @classmethod
    def for_source_runtime_spool(
        cls,
        source_root: Path,
        runtime_root: Path | str | None = None,
        *,
        create: bool = False,
    ) -> "RuntimeArtifactBoundary":
        """Create the narrowly scoped bootstrap spool/control boundary.

        External runtime roots use the ordinary boundary.  Only the exact
        source-local ``<source>/.runtime`` root receives the restricted source
        runtime capability.
        """
        source = _resolved_source(source_root)
        root, source_runtime = _resolve_runtime_spool_root(
            source, runtime_root, create=create
        )
        return cls(
            source_root=source,
            root=root,
            source_runtime_spool=source_runtime,
        )

    def resolve(self, path: Path | str, *, allow_absolute: bool = True) -> Path:
        """Resolve a path under the root and reject traversal/symlink escapes."""
        candidate = Path(path)
        if candidate.is_absolute():
            if not allow_absolute:
                raise RuntimePathEscape(f"absolute runtime path is not allowed: {candidate}")
            joined = candidate
        else:
            # Use POSIX parsing for deterministic rejection on all hosts.
            pure = PurePosixPath(candidate.as_posix())
            if any(part in ("", ".", "..") for part in pure.parts):
                # Empty parts are harmless in a Path, but rejecting them keeps
                # the serialized artifact path unambiguous.
                raise RuntimePathEscape(f"unsafe runtime-relative path: {candidate}")
            joined = self.root.joinpath(*pure.parts)
        try:
            relative = joined.relative_to(self.root)
        except ValueError as exc:
            raise RuntimePathEscape(f"path escapes runtime root: {joined}") from exc
        if relative == Path("."):
            raise RuntimePathEscape("runtime root itself is not an artifact")
        _reject_symlink_components(joined, self.root)
        try:
            resolved = joined.resolve(strict=False)
        except OSError as exc:
            raise RuntimeArtifactError(f"cannot resolve runtime path: {joined}") from exc
        if not _contains(self.root, resolved):
            raise RuntimeSymlinkEscape(f"runtime path escapes root: {joined}")
        if _contains(self.source_root, resolved):
            if not self.source_runtime_spool:
                raise SourceLocalArtifact(f"runtime artifact resolves into source: {resolved}")
            try:
                runtime_relative = resolved.relative_to(self.root)
            except ValueError as exc:  # pragma: no cover - root is validated above.
                raise SourceLocalArtifact(
                    f"runtime artifact resolves into source: {resolved}"
                ) from exc
            if (
                not runtime_relative.parts
                or runtime_relative.parts[0] not in SOURCE_RUNTIME_ALLOWED_TOP_LEVELS
            ):
                raise SourceLocalArtifact(
                    "source runtime artifact is outside bootstrap spool/control paths: "
                    f"{resolved}"
                )
        return resolved

    def ensure_directory(self, path: Path | str = Path(".")) -> Path:
        """Create one external directory after validating every component."""
        target = self.root if path == Path(".") else self.resolve(path)
        if target != self.root:
            _reject_symlink_components(target, self.root)
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeArtifactError(f"cannot create runtime directory: {target}") from exc
        return target

    def _prepare_parent(self, path: Path | str) -> Path:
        target = self.resolve(path)
        parent = target.parent
        self.ensure_directory(parent.relative_to(self.root))
        _reject_symlink_components(parent, self.root)
        return target

    def atomic_write_bytes(
        self,
        path: Path | str,
        data: bytes,
        *,
        mode: int = 0o600,
    ) -> Path:
        """Atomically replace one external artifact and fsync its directory."""
        target = self._prepare_parent(path)
        if target.is_symlink():
            raise RuntimeSymlinkEscape(f"runtime target is a symlink: {target}")
        temporary: Path | None = None
        try:
            descriptor, name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
            )
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), mode)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            temporary = None
            directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise RuntimeArtifactError(f"atomic runtime write failed: {target}") from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        return target

    def atomic_write_text(self, path: Path | str, text: str, *, mode: int = 0o600) -> Path:
        return self.atomic_write_bytes(path, text.encode("utf-8"), mode=mode)

    def atomic_write_json(
        self,
        path: Path | str,
        value: Any,
        *,
        mode: int = 0o600,
    ) -> Path:
        payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        return self.atomic_write_bytes(path, payload, mode=mode)

    def append_bytes(self, path: Path | str, data: bytes, *, mode: int = 0o600) -> Path:
        """Append through an external lock and atomic replacement.

        This is intentionally for small JSONL receipts.  Large producer output
        should use unique files and ``atomic_write_bytes`` instead.
        """
        target = self._prepare_parent(path)
        lock = self._prepare_parent(target.parent / f".{target.name}.lock")
        try:
            with lock.open("a+b") as stream:
                if fcntl is not None:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                existing = target.read_bytes() if target.exists() else b""
                result = self.atomic_write_bytes(target, existing + data, mode=mode)
                if fcntl is not None:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                return result
        except OSError as exc:
            raise RuntimeArtifactError(f"external append failed: {target}") from exc

    def digest(self, path: Path | str) -> str:
        """Return SHA-256 for one resolved external artifact."""
        target = self.resolve(path)
        try:
            return hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError as exc:
            raise RuntimeArtifactError(f"cannot read runtime artifact: {target}") from exc


def runtime_artifact_boundary(
    source_root: Path,
    runtime_root: Path | str | None = None,
    *,
    create: bool = False,
) -> RuntimeArtifactBoundary:
    """Short public factory used by path and eval helpers."""
    return RuntimeArtifactBoundary.for_source(source_root, runtime_root, create=create)


def runtime_spool_boundary(
    source_root: Path,
    runtime_root: Path | str | None = None,
    *,
    create: bool = False,
) -> RuntimeArtifactBoundary:
    """Return the bootstrap-owned spool/control boundary.

    This is intentionally separate from :func:`runtime_artifact_boundary` so
    source-local runtime state cannot become a general artifact exception.
    """
    return RuntimeArtifactBoundary.for_source_runtime_spool(
        source_root, runtime_root, create=create
    )
