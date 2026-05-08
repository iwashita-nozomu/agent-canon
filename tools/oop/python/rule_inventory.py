#!/usr/bin/env python3
# @dependency-start
# responsibility Inventories Python OOP policy, tool, document, and test surfaces.
# upstream design ../../../documents/tools/README.md tool documentation placement policy
# upstream design ../../../documents/object-oriented-design.md OOP policy source
# downstream implementation ../../../tests/agent_tools/test_oop_rule_inventory.py tests inventory entrypoint
# @dependency-end
"""Inventory Python OOP rule surfaces."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class InventoryEntry:
    """One required Python OOP surface."""

    kind: str
    path: str
    purpose: str

    def exists(self, root: Path) -> bool:
        """Return whether this surface exists below root."""
        return (root / self.path).exists()


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


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    return parser


def missing_entries(root: Path) -> list[InventoryEntry]:
    """Return missing Python OOP surfaces."""
    return [entry for entry in ENTRIES if not entry.exists(root)]


def print_text(root: Path, missing: Sequence[InventoryEntry]) -> None:
    """Print stable text output."""
    status = "fail" if missing else "pass"
    print(f"OOP_PYTHON_RULE_INVENTORY={status}")
    print(f"OOP_PYTHON_RULE_INVENTORY_ENTRIES={len(ENTRIES)}")
    print(f"OOP_PYTHON_RULE_INVENTORY_MISSING={len(missing)}")
    for entry in ENTRIES:
        exists = "yes" if entry.exists(root) else "no"
        print(
            f"OOP_PYTHON_RULE_SOURCE={entry.kind}\t{entry.path}\t"
            f"exists={exists}\t{entry.purpose}"
        )


def print_markdown(root: Path, missing: Sequence[InventoryEntry]) -> None:
    """Print a Markdown inventory report."""
    status = "fail" if missing else "pass"
    print("# Python OOP Rule Inventory")
    print()
    print(f"- Status: `{status}`")
    print(f"- Entries: `{len(ENTRIES)}`")
    print(f"- Missing entries: `{len(missing)}`")
    print()
    print("| Kind | Path | Exists | Purpose |")
    print("| --- | --- | --- | --- |")
    for entry in ENTRIES:
        exists = "yes" if entry.exists(root) else "no"
        print(f"| {entry.kind} | `{entry.path}` | {exists} | {entry.purpose} |")


def print_json(root: Path, missing: Sequence[InventoryEntry]) -> None:
    """Print a JSON inventory report."""
    print(
        json.dumps(
            {
                "status": "fail" if missing else "pass",
                "entries": [
                    {**asdict(entry), "exists": entry.exists(root)}
                    for entry in ENTRIES
                ],
                "missing": [entry.path for entry in missing],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main(argv: Sequence[str]) -> int:
    """Run the Python OOP inventory CLI."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    missing = missing_entries(root)
    if args.format == "json":
        print_json(root, missing)
    elif args.format == "markdown":
        print_markdown(root, missing)
    else:
        print_text(root, missing)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
