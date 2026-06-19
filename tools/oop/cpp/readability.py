#!/usr/bin/env python3
# ruff: noqa: E402,I001
# @dependency-start
# contract tool
# responsibility Runs C++-specific OOP readability checks.
# upstream implementation ../shared/readability_core.py shared OOP readability heuristics
# upstream design ../../../documents/object-oriented-design.md OOP policy source
# upstream design ../../../documents/tools/README.md tool documentation placement policy
# downstream implementation ../../../tests/agent_tools/test_analyze_oop_readability.py tests C++ entrypoint
# @dependency-end
"""C++-specific OOP readability entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.oop.shared.readability_core import main


if __name__ == "__main__":
    raise SystemExit(main(default_language="cpp"))
