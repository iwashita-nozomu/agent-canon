#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Resolve AgentCanon runtime source root for command execution and route entry.
# upstream implementation ../../tools/agent_tools/route.py consumes deterministic source root for route-root selection
# upstream implementation ../../tools/agent_tools/skill_tool_commands.py consumes deterministic command execution roots
# @dependency-end

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

LAYOUT_STANDALONE = "standalone"
LAYOUT_VENDORED = "vendored"


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
            return candidate
    return start


def _has_catalog(root: Path) -> bool:
    return (root / "agents" / "skills" / "catalog.yaml").is_file()


def resolve_agent_canon_source_root(raw_root: Path) -> RootResolution:
    """Resolve a deterministic AgentCanon source root from an entry directory."""

    current_repository_root = _find_current_repository_root(raw_root)
    vendor_root = current_repository_root / "vendor" / "agent-canon"
    candidates: list[tuple[str, Path]] = []

    if _has_catalog(current_repository_root):
        candidates.append((LAYOUT_STANDALONE, current_repository_root))

    if _has_catalog(vendor_root):
        candidates.append((LAYOUT_VENDORED, vendor_root))

    if not candidates:
        raise SourceRootFailure(
            "agent_canon_source_root_missing",
            (
                f"No AgentCanon catalog found from current_repository_root={current_repository_root}"
                f" (standalone: {current_repository_root}, vendored: {vendor_root})"
            ),
        )

    if len(candidates) > 1:
        candidate_labels = tuple(f"{label}:{path}" for label, path in candidates)
        raise SourceRootFailure(
            "agent_canon_source_root_ambiguous",
            " | ".join(candidate_labels),
        )

    layout, source_root = candidates[0]
    return RootResolution(
        current_repository_root=current_repository_root,
        source_root=source_root,
        layout=layout,
    )
