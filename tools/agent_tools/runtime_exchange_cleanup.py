#!/usr/bin/env python3
"""Clear the fixed writable runtime exchange from inside the tool container."""

from __future__ import annotations

import os
import stat
from pathlib import Path

EXCHANGE_ROOT = Path("/var/lib/agent-canon/runtime")


def _clear_entry(candidate: Path) -> tuple[int, int]:
    """Remove container-owned content and leave Host-owned entries for Host cleanup."""
    try:
        observed = candidate.lstat()
    except PermissionError:
        return 0, 1
    if stat.S_ISDIR(observed.st_mode):
        removed = 0
        preserved = 0
        try:
            with os.scandir(candidate) as entries:
                children = [candidate / entry.name for entry in entries]
        except PermissionError:
            return 0, 1
        for child in children:
            child_removed, child_preserved = _clear_entry(child)
            removed += child_removed
            preserved += child_preserved
        if preserved:
            return removed, preserved
        try:
            candidate.rmdir()
        except PermissionError:
            return removed, 1
        return removed + 1, 0
    try:
        candidate.unlink()
    except PermissionError:
        return 0, 1
    return 1, 0


def clear_exchange(root: Path = EXCHANGE_ROOT) -> tuple[int, int]:
    """Clear container-owned children and classify Host-owned leftovers."""
    observed = root.lstat()
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise RuntimeError(f"runtime exchange is not a directory: {root}")
    removed = 0
    preserved = 0
    with os.scandir(root) as entries:
        children = [root / entry.name for entry in entries]
    for candidate in children:
        child_removed, child_preserved = _clear_entry(candidate)
        removed += child_removed
        preserved += child_preserved
    return removed, preserved


def main() -> int:
    """Clear the fixed container mount and emit a bounded readback."""
    removed, preserved = clear_exchange()
    print(f"AGENT_CANON_RUNTIME_EXCHANGE_REMOVED={removed}")
    print(f"AGENT_CANON_RUNTIME_EXCHANGE_HOST_PRESERVED={preserved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
