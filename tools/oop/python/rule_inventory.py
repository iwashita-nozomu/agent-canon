#!/usr/bin/env python3
# ruff: noqa: E402,I001
# @dependency-start
# contract tool
# responsibility Inventories Python OOP policy, tool, document, and test surfaces.
# upstream design ../../../documents/tools/README.md tool documentation placement policy
# upstream design ../../../documents/object-oriented-design.md OOP policy source
# upstream implementation ../shared/rule_inventory_core.py shared OOP inventory behavior
# downstream implementation ../../../tests/agent_tools/test_oop_rule_inventory.py tests inventory entrypoint
# @dependency-end
"""Inventory Python OOP rule surfaces."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.oop.shared.rule_inventory_core import InventoryEntry, run_inventory_cli


ENTRIES = (
    InventoryEntry(
        "policy",
        "documents/object-oriented-design.md",
        "OOP boundary, responsibility, and mechanical-evaluation policy.",
    ),
    InventoryEntry(
        "policy",
        "documents/coding-conventions-python.md",
        "Python type-boundary and readability policy entrypoint.",
    ),
    InventoryEntry(
        "tool",
        "tools/oop/python/readability.py",
        "Python-specific OOP readability analyzer entrypoint.",
    ),
    InventoryEntry(
        "tool",
        "tools/oop/python/rule_inventory.py",
        "Python OOP policy/tool/doc/test inventory.",
    ),
    InventoryEntry(
        "document",
        "documents/tools/oop/python/readability.md",
        "Japanese explanation of Python readability checks.",
    ),
    InventoryEntry(
        "document",
        "documents/tools/oop/python/rule_inventory.md",
        "Japanese explanation of this inventory check.",
    ),
    InventoryEntry(
        "reviewer",
        ".codex/agents/oop_readability_reviewer.toml",
        "Read-only reviewer role for mechanical OOP reports.",
    ),
    InventoryEntry(
        "test",
        "tests/agent_tools/test_analyze_oop_readability.py",
        "Regression tests for Python readability findings.",
    ),
    InventoryEntry(
        "test",
        "tests/agent_tools/test_oop_rule_inventory.py",
        "Regression tests for OOP inventory behavior.",
    ),
)


def main(argv: Sequence[str]) -> int:
    """Run the Python OOP inventory CLI."""
    entries = ENTRIES
    return run_inventory_cli(
        argv,
        description=__doc__ or "",
        prefix="OOP_PYTHON",
        title="Python OOP Rule Inventory",
        entries=entries,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
