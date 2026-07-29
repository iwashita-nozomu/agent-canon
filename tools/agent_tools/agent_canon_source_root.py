#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Resolve AgentCanon runtime source root for command execution and route entry.
# upstream implementation ../../tools/agent_tools/route.py consumes deterministic source root for route-root selection
# upstream implementation ../../tools/agent_tools/skill_tool_commands.py consumes deterministic command execution roots
# @dependency-end
"""Resolve the AgentCanon source root used by runtime entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

LAYOUT_STANDALONE = "standalone"
LAYOUT_VENDORED = "vendored"

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


def resolve_agent_canon_source_root(raw_root: Path) -> RootResolution:
    """Resolve a deterministic AgentCanon source root from an entry directory."""
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
    )
