#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Defines shared tool-path hygiene rules for retired legacy surfaces.
# upstream design ../../documents/repo-local-tool-imports.md legacy tool disposition policy
# upstream design ../../tools/catalog.yaml structured AgentCanon tool catalog
# downstream implementation ./tool_catalog.py rejects retired legacy catalog paths
# downstream implementation ./tool_drift.py detects orphaned retired legacy tool files
# downstream implementation ./vector_search.py excludes retired legacy files from search indexes
# downstream implementation ../../tests/agent_tools/test_tool_catalog.py validates catalog findings
# downstream implementation ../../tests/agent_tools/test_tool_drift.py validates orphan detection
# downstream implementation ../../tests/agent_tools/test_vector_search.py validates search exclusion
# downstream implementation ../../tests/agent_tools/test_search_index.py validates search-card pruning
# @dependency-end
"""Shared path policy for retired AgentCanon tool surfaces."""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

LEGACY_TOKEN_RE = re.compile(r"[^0-9A-Za-z]+|_")


def has_retired_legacy_path_token(path: str) -> bool:
    """Return true when a path names a retired legacy implementation surface."""
    normalized = path.replace("\\", "/").removeprefix("./")
    for part in PurePosixPath(normalized).parts:
        stem = PurePosixPath(part).stem.lower()
        tokens = {token for token in LEGACY_TOKEN_RE.split(stem) if token}
        if "legacy" in stem or "legacy" in tokens:
            return True
    return False


def is_tool_surface_path(path: str) -> bool:
    """Return true when a path belongs to the AgentCanon tool tree."""
    normalized = path.replace("\\", "/").removeprefix("./")
    return normalized == "tools" or normalized.startswith("tools/")


def is_retired_legacy_tool_path(path: str) -> bool:
    """Return true when a path is a retired legacy path under tools/."""
    return is_tool_surface_path(path) and has_retired_legacy_path_token(path)


def iter_retired_legacy_tool_paths(root: Path) -> Sequence[str]:
    """Return existing tool paths whose names still carry retired legacy tokens."""
    tools_root = root / "tools"
    if not tools_root.exists():
        return ()
    retired: list[str] = []
    for current_root, dirnames, filenames in os.walk(tools_root):
        current = Path(current_root)
        relative_dir = current.relative_to(root).as_posix()
        if relative_dir != "tools" and is_retired_legacy_tool_path(relative_dir):
            retired.append(relative_dir)
            dirnames[:] = []
            continue
        for filename in sorted(filenames):
            relative_file = (current / filename).relative_to(root).as_posix()
            if is_retired_legacy_tool_path(relative_file):
                retired.append(relative_file)
    return tuple(sorted(set(retired)))


def retired_legacy_tool_detail(path: str) -> str:
    """Return the stable finding detail for one retired legacy tool path."""
    if path == "tools/legacy":
        return "legacy-directory-present"
    return "legacy-tools-are-retired"
