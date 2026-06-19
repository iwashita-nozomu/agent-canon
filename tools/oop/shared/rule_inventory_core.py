#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides shared OOP rule inventory CLI behavior.
# upstream design ../../../documents/tools/README.md tool documentation placement policy
# upstream design ../../../documents/SHARED_RUNTIME_SURFACES.md shared AgentCanon surface policy
# downstream implementation ../python/rule_inventory.py Python OOP inventory entrypoint
# downstream implementation ../cpp/rule_inventory.py C++ OOP inventory entrypoint
# downstream implementation ../../../tests/agent_tools/test_oop_rule_inventory.py tests inventory behavior
# @dependency-end
"""Shared implementation for language-specific OOP rule inventories."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class InventoryEntry:
    """One required OOP rule surface."""

    kind: str
    path: str
    purpose: str

    def exists(self, root: Path) -> bool:
        """Return whether this surface exists below root or the AgentCanon vendor."""
        resolved = resolve_surface_path(root, self.path)
        return resolved.exists()


def resolve_surface_path(root: Path, relative_path: str) -> Path:
    """Resolve a rule surface through the root view or vendored AgentCanon source."""
    root_path = root / relative_path
    if root_path.exists():
        return root_path
    vendor_path = root / "vendor" / "agent-canon" / relative_path
    if vendor_path.exists():
        return vendor_path
    return root_path


def missing_entries(root: Path, entries: Sequence[InventoryEntry]) -> list[InventoryEntry]:
    """Return inventory entries missing from both root and vendor surfaces."""
    return [entry for entry in entries if not entry.exists(root)]


def inventory_payload(
    root: Path,
    entries: Sequence[InventoryEntry],
) -> dict[str, object]:
    """Return machine-readable inventory status."""
    missing = missing_entries(root, entries)
    rendered_entries: list[dict[str, object]] = []
    for entry in entries:
        resolved = resolve_surface_path(root, entry.path)
        rendered_entries.append(
            {
                **asdict(entry),
                "exists": resolved.exists(),
                "resolved_path": str(resolved.relative_to(root))
                if resolved.exists()
                else "",
            }
        )
    return {
        "status": "fail" if missing else "pass",
        "entries": rendered_entries,
        "missing": [entry.path for entry in missing],
    }


def build_parser(description: str) -> argparse.ArgumentParser:
    """Create a language-specific inventory parser."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    return parser


def print_text(prefix: str, root: Path, entries: Sequence[InventoryEntry]) -> None:
    """Print stable line-oriented inventory output."""
    payload = inventory_payload(root, entries)
    print(f"{prefix}_RULE_INVENTORY={payload['status']}")
    print(f"{prefix}_RULE_INVENTORY_ENTRIES={len(entries)}")
    print(f"{prefix}_RULE_INVENTORY_MISSING={len(payload['missing'])}")
    for raw_entry in payload["entries"]:
        if not isinstance(raw_entry, dict):
            continue
        print(
            f"{prefix}_RULE_SOURCE={raw_entry['kind']}\t{raw_entry['path']}\t"
            f"exists={'yes' if raw_entry['exists'] else 'no'}\t"
            f"resolved={raw_entry['resolved_path']}\t{raw_entry['purpose']}"
        )


def print_markdown(title: str, root: Path, entries: Sequence[InventoryEntry]) -> None:
    """Print a Markdown inventory report."""
    payload = inventory_payload(root, entries)
    print(f"# {title}")
    print()
    print(f"- Status: `{payload['status']}`")
    print(f"- Entries: `{len(entries)}`")
    print(f"- Missing entries: `{len(payload['missing'])}`")
    print()
    print("| Kind | Path | Exists | Resolved Path | Purpose |")
    print("| --- | --- | --- | --- | --- |")
    for raw_entry in payload["entries"]:
        if not isinstance(raw_entry, dict):
            continue
        exists = "yes" if raw_entry["exists"] else "no"
        print(
            f"| {raw_entry['kind']} | `{raw_entry['path']}` | {exists} | "
            f"`{raw_entry['resolved_path']}` | {raw_entry['purpose']} |"
        )


def print_json(root: Path, entries: Sequence[InventoryEntry]) -> None:
    """Print inventory status as JSON."""
    print(json.dumps(inventory_payload(root, entries), ensure_ascii=False, indent=2))


def run_inventory_cli(
    argv: Sequence[str],
    *,
    description: str,
    prefix: str,
    title: str,
    entries: Sequence[InventoryEntry],
) -> int:
    """Run a language-specific OOP inventory CLI."""
    args = build_parser(description).parse_args(argv)
    root = Path(args.root).resolve()
    missing = missing_entries(root, entries)
    if args.format == "json":
        print_json(root, entries)
    elif args.format == "markdown":
        print_markdown(title, root, entries)
    else:
        print_text(prefix, root, entries)
    return 1 if missing else 0
