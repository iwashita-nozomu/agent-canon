#!/usr/bin/env python3
# @dependency-start
# responsibility Inventories OOP readability rule sources and legacy check-support disposition.
# upstream design ../../documents/object-oriented-design.md OOP policy source
# upstream design ../../documents/repo-local-tool-imports.md legacy tool disposition ledger
# downstream implementation ../../tests/agent_tools/test_oop_rule_inventory.py regression tests
# @dependency-end
"""Inventory OOP readability rule sources and legacy support-tool placement."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InventoryEntry:
    """One OOP rule or tool placement entry."""

    kind: str
    path: str
    purpose: str
    required: bool = True

    def exists(self, root: Path) -> bool:
        """Return true when the entry exists under root."""
        return (root / self.path).exists()

    def as_json(self, root: Path) -> Mapping[str, object]:
        """Return a machine-readable mapping."""
        return {
            "kind": self.kind,
            "path": self.path,
            "purpose": self.purpose,
            "required": self.required,
            "exists": self.exists(root),
        }


RULE_SOURCES = (
    InventoryEntry(
        "policy",
        "documents/object-oriented-design.md",
        "human-readable OOP boundary policy and machine-evaluation contract",
    ),
    InventoryEntry(
        "policy",
        "documents/coding-conventions-house-style.md",
        "shared readability and house-style constraints",
    ),
    InventoryEntry(
        "policy",
        "documents/coding-conventions-python.md",
        "Python type-boundary and readability entrypoint",
    ),
    InventoryEntry(
        "policy",
        "documents/coding-conventions-cpp.md",
        "C/C++ ownership, header, and public-surface entrypoint",
    ),
    InventoryEntry(
        "analyzer",
        "tools/agent_tools/analyze_oop_readability.py",
        "mechanical Python/C++ OOP readability score gate",
    ),
    InventoryEntry(
        "analyzer",
        "tools/agent_tools/analyze_refactor_surface.py",
        "large-refactor surface-size and public-surface score gate",
    ),
    InventoryEntry(
        "reviewer",
        ".codex/agents/oop_readability_reviewer.toml",
        "read-only reviewer role for mechanical OOP reports",
    ),
    InventoryEntry(
        "test",
        "tests/agent_tools/test_analyze_oop_readability.py",
        "regression tests for OOP readability analyzer",
    ),
)

LEGACY_PLACEMENT = (
    InventoryEntry(
        "legacy-oop-support",
        "tools/legacy/jax_solver_util/oop_check_support/restructure_code_review_skill.py",
        "legacy code-review skill restructuring script retained for provenance only",
        required=False,
    ),
    InventoryEntry(
        "legacy-oop-support",
        "tools/legacy/jax_solver_util/oop_check_support/read_conventions.sh",
        "legacy convention listing script retained as provenance for rule inventory",
        required=False,
    ),
    InventoryEntry(
        "legacy-oop-support",
        "tools/legacy/jax_solver_util/oop_check_support/view_conventions.sh",
        "legacy convention viewer retained as provenance for rule inventory",
        required=False,
    ),
)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Inventory OOP readability rule sources and legacy tool placement."
    )
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    parser.add_argument(
        "--include-legacy",
        action="store_true",
        help="Include legacy provenance placement entries in the output.",
    )
    return parser


def collect_entries(include_legacy: bool) -> tuple[InventoryEntry, ...]:
    """Return entries for the requested inventory scope."""
    if include_legacy:
        return RULE_SOURCES + LEGACY_PLACEMENT
    return RULE_SOURCES


def missing_required(root: Path, entries: Sequence[InventoryEntry]) -> list[InventoryEntry]:
    """Return missing required entries."""
    return [entry for entry in entries if entry.required and not entry.exists(root)]


def print_text(
    root: Path,
    entries: Sequence[InventoryEntry],
    missing: Sequence[InventoryEntry],
) -> None:
    """Print stable text output."""
    status = "fail" if missing else "pass"
    print(f"OOP_RULE_INVENTORY={status}")
    print(f"OOP_RULE_INVENTORY_ENTRIES={len(entries)}")
    print(f"OOP_RULE_INVENTORY_MISSING={len(missing)}")
    for entry in entries:
        exists = "yes" if entry.exists(root) else "no"
        required = "yes" if entry.required else "no"
        print(
            f"OOP_RULE_SOURCE={entry.kind}\t{entry.path}\t"
            f"exists={exists}\trequired={required}\t{entry.purpose}"
        )


def print_markdown(
    root: Path,
    entries: Sequence[InventoryEntry],
    missing: Sequence[InventoryEntry],
) -> None:
    """Print a Markdown inventory report."""
    status = "fail" if missing else "pass"
    print("# OOP Rule Inventory")
    print()
    print(f"- Status: `{status}`")
    print(f"- Entries: `{len(entries)}`")
    print(f"- Missing required entries: `{len(missing)}`")
    print()
    print("| Kind | Path | Exists | Required | Purpose |")
    print("| ---- | ---- | ------ | -------- | ------- |")
    for entry in entries:
        exists = "yes" if entry.exists(root) else "no"
        required = "yes" if entry.required else "no"
        print(f"| {entry.kind} | `{entry.path}` | {exists} | {required} | {entry.purpose} |")


def print_json(
    root: Path,
    entries: Sequence[InventoryEntry],
    missing: Sequence[InventoryEntry],
) -> None:
    """Print a JSON inventory report."""
    payload: Mapping[str, object] = {
        "status": "fail" if missing else "pass",
        "entries": [entry.as_json(root) for entry in entries],
        "missing_required": [entry.path for entry in missing],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: Sequence[str]) -> int:
    """Run the OOP rule inventory CLI."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    entries = collect_entries(args.include_legacy)
    missing = missing_required(root, entries)
    if args.format == "json":
        print_json(root, entries, missing)
    elif args.format == "markdown":
        print_markdown(root, entries, missing)
    else:
        print_text(root, entries, missing)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
