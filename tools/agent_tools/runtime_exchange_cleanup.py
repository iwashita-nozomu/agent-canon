#!/usr/bin/env python3
"""Clear the fixed writable runtime exchange from inside the tool container."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

EXCHANGE_ROOT = Path("/var/lib/agent-canon/runtime")


def clear_exchange(root: Path = EXCHANGE_ROOT) -> int:
    """Delete only children of the admitted exchange without following links."""
    observed = root.lstat()
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise RuntimeError(f"runtime exchange is not a directory: {root}")
    removed = 0
    with os.scandir(root) as entries:
        for entry in entries:
            candidate = root / entry.name
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(candidate)
            else:
                candidate.unlink()
            removed += 1
    return removed


def main() -> int:
    """Clear the fixed container mount and emit a bounded readback."""
    removed = clear_exchange()
    print(f"AGENT_CANON_RUNTIME_EXCHANGE_REMOVED={removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
