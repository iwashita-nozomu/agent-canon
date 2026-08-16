#!/usr/bin/env python3
"""Apply the one-time Issue #706 runtime import-root ordering correction."""

from __future__ import annotations

from pathlib import Path

PATH = Path("tools/agent_tools/check_agent_runtime_alignment.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    """Replace one exact source fragment or fail without partial output."""
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    """Move source-root projection before the central fixture imports."""
    text = PATH.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from pathlib import Path\n\ntry:\n    from .fixture_spawn import (\n",
        "from pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))\n\n"
        "try:\n    from .fixture_spawn import (\n",
        "runtime import prelude",
    )
    text = replace_once(
        text,
        "\nsys.path.insert(0, str(Path(__file__).resolve().parents[2]))\n"
        "from typing import cast\n",
        "\nfrom typing import cast\n",
        "late source-root projection",
    )
    PATH.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
