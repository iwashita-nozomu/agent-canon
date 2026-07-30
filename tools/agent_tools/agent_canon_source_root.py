#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Resolve AgentCanon runtime source root for command execution and route entry.
# upstream implementation ../../tools/agent_tools/route.py consumes deterministic source root for route-root selection
# upstream implementation ../../tools/agent_tools/skill_tool_commands.py consumes deterministic command execution roots
# @dependency-end
"""Resolve the AgentCanon source root used by runtime entrypoints."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

LAYOUT_STANDALONE = "standalone"
LAYOUT_VENDORED = "vendored"
LAYOUT_OVERRIDE = "override"
SOURCE_ROOT_OVERRIDE_ENV = "AGENT_CANON_SOURCE_ROOT"
CANON_ROOT_OVERRIDE_ENV = "AGENT_CANON_ROOT"

VENDOR_OUTSIDE_REPOSITORY = "agent_canon_source_root_vendor_outside_repository"
ROOT_VIEW_OUTSIDE_REPOSITORY = "agent_canon_source_root_root_view_outside_repository"


@dataclass(frozen=True)
class SourceRootFailure(ValueError):
    """Typed failure raised when source-root resolution is not deterministic."""

    code: str
    detail: str


@dataclass(frozen=True)
class RootResolution:
    """Canonical root resolution used by all AgentCanon entrypoints."""

    current_repository_root: Path
    source_root: Path
    layout: str
    canon_root: Path


def _find_current_repository_root(raw_root: Path) -> Path:
    """Find repository root by walking up for `.git`, else keep the absolute path."""
    start = raw_root if raw_root.is_absolute() else raw_root.resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate.resolve()
    return start.resolve()


def _has_catalog(root: Path) -> bool:
    return (root / "agents" / "skills" / "catalog.yaml").is_file()


def _is_within(path: Path, root: Path) -> bool:
    """Return whether a canonical path remains within a repository root."""
    return path == root or root in path.parents


def _resolve_path(path: Path, *, failure_code: str, root: Path) -> Path:
    """Resolve one path and reject symlink targets outside the repository."""
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise SourceRootFailure(failure_code, f"Unable to resolve {path}: {exc}") from exc
    if not _is_within(resolved, root):
        raise SourceRootFailure(
            failure_code,
            f"{path} resolves outside current_repository_root={root}: {resolved}",
        )
    return resolved


def _same_canonical_entity(left: Path, right: Path) -> bool:
    """Return whether two existing paths identify the same filesystem entity."""
    try:
        return left.samefile(right)
    except OSError:
        return left.resolve() == right.resolve()


def _explicit_resolution(raw_root: Path, source: Path, canon: Path) -> RootResolution:
    """Resolve explicit source and canon roots without collapsing their identities."""
    if not _has_catalog(source):
        raise SourceRootFailure(
            "agent_canon_source_root_override_missing",
            f"Override source root has no AgentCanon catalog: {source}",
        )
    if not _has_catalog(canon):
        raise SourceRootFailure(
            "agent_canon_canon_root_override_missing",
            f"Override canon root has no AgentCanon catalog: {canon}",
        )
    return RootResolution(
        current_repository_root=_find_current_repository_root(raw_root),
        source_root=source,
        layout=LAYOUT_OVERRIDE,
        canon_root=canon,
    )


def _explicit_override(raw_root: Path) -> RootResolution | None:
    source_override = os.environ.get(SOURCE_ROOT_OVERRIDE_ENV, "").strip()
    canon_override = os.environ.get(CANON_ROOT_OVERRIDE_ENV, "").strip()
    if not source_override and not canon_override:
        return None
    if not source_override or not canon_override:
        raise SourceRootFailure(
            "agent_canon_source_root_override_incomplete",
            "AGENT_CANON_SOURCE_ROOT and AGENT_CANON_ROOT must be supplied together",
        )
    source_root = Path(source_override).expanduser().resolve()
    canon_root = Path(canon_override).expanduser().resolve()
    return _explicit_resolution(raw_root, source_root, canon_root)


def resolve_agent_canon_source_root(
    raw_root: Path,
    *,
    source_root: Path | None = None,
    canon_root: Path | None = None,
) -> RootResolution:
    """Resolve a deterministic AgentCanon source root from an entry directory."""
    if source_root is not None or canon_root is not None:
        if source_root is None or canon_root is None:
            raise SourceRootFailure(
                "agent_canon_source_root_override_incomplete",
                "source_root and canon_root must be supplied together",
            )
        source = source_root.expanduser().resolve()
        canon = canon_root.expanduser().resolve()
        return _explicit_resolution(raw_root, source, canon)

    explicit = _explicit_override(raw_root)
    if explicit is not None:
        return explicit

    current_repository_root = _find_current_repository_root(raw_root)
    vendor_root = current_repository_root / "vendor" / "agent-canon"
    vendor_source_root = _resolve_path(
        vendor_root,
        failure_code=VENDOR_OUTSIDE_REPOSITORY,
        root=current_repository_root,
    )
    root_view = current_repository_root / "agents"
    _resolve_path(
        root_view,
        failure_code=ROOT_VIEW_OUTSIDE_REPOSITORY,
        root=current_repository_root,
    )

    standalone_catalog = current_repository_root / "agents" / "skills" / "catalog.yaml"
    vendor_catalog = vendor_source_root / "agents" / "skills" / "catalog.yaml"
    has_standalone = _has_catalog(current_repository_root)
    has_vendor = _has_catalog(vendor_source_root)

    if not has_standalone and not has_vendor:
        raise SourceRootFailure(
            "agent_canon_source_root_missing",
            (
                f"No AgentCanon catalog found from current_repository_root={current_repository_root}"
                f" (standalone: {current_repository_root}, vendored: {vendor_source_root})"
            ),
        )

    if has_standalone and has_vendor:
        if _same_canonical_entity(standalone_catalog, vendor_catalog):
            return RootResolution(
                current_repository_root=current_repository_root,
                source_root=vendor_source_root,
                layout=LAYOUT_VENDORED,
                canon_root=vendor_source_root,
            )
        candidate_labels = (
            f"{LAYOUT_STANDALONE}:{current_repository_root}",
            f"{LAYOUT_VENDORED}:{vendor_source_root}",
        )
        raise SourceRootFailure(
            "agent_canon_source_root_ambiguous",
            " | ".join(candidate_labels),
        )

    layout = LAYOUT_STANDALONE if has_standalone else LAYOUT_VENDORED
    source_root = current_repository_root if has_standalone else vendor_source_root
    return RootResolution(
        current_repository_root=current_repository_root,
        source_root=source_root,
        layout=layout,
        canon_root=source_root,
    )
