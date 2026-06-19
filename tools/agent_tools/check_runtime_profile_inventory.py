#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Detects drift between runtime profile inventory JSON and its rendered markdown doc.
# upstream design ../../documents/runtime-profiles-and-check-matrix.json runtime profile inventory source of truth
# upstream design ../../documents/runtime-profiles-and-check-matrix.md human-readable runtime profile doc
# upstream implementation ../docs/render_runtime_profile_inventory.py renderer used for drift comparison
# downstream implementation ../../tests/agent_tools/test_check_runtime_profile_inventory.py tests it
# @dependency-end
"""Fail when runtime profile inventory docs drift from the machine-readable source."""

from __future__ import annotations

import argparse
import difflib
import subprocess
import sys
from pathlib import Path

AGENT_CANON_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INVENTORY = AGENT_CANON_ROOT / "documents/runtime-profiles-and-check-matrix.json"
DEFAULT_DOC = AGENT_CANON_ROOT / "documents/runtime-profiles-and-check-matrix.md"
RENDER_SCRIPT = AGENT_CANON_ROOT / "tools/docs/render_runtime_profile_inventory.py"


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Detect drift between runtime profile inventory JSON and rendered markdown."
        )
    )
    parser.add_argument(
        "--inventory",
        default=str(DEFAULT_INVENTORY),
        help="Path to runtime profile inventory JSON.",
    )
    parser.add_argument(
        "--doc",
        default=str(DEFAULT_DOC),
        help="Path to rendered markdown doc.",
    )
    return parser


def main() -> int:
    """Run the runtime profile inventory drift check."""
    args = build_parser().parse_args()
    inventory_path = Path(args.inventory)
    doc_path = Path(args.doc)

    proc = subprocess.run(
        [
            sys.executable,
            str(RENDER_SCRIPT),
            "--inventory",
            str(inventory_path),
            "--doc",
            str(doc_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        details = proc.stderr.strip() or proc.stdout.strip() or "no output"
        print("RUNTIME_PROFILE_INVENTORY_DRIFT=error")
        print(f"renderer failed: {details}")
        return 1
    rendered = proc.stdout
    current = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""

    if current == rendered:
        print("RUNTIME_PROFILE_INVENTORY_DRIFT=pass")
        return 0

    diff = difflib.unified_diff(
        current.splitlines(True),
        rendered.splitlines(True),
        fromfile=str(doc_path),
        tofile="rendered",
    )
    print("RUNTIME_PROFILE_INVENTORY_DRIFT=fail")
    print("".join(diff).rstrip())
    print(
        f"Fix by running: python3 tools/docs/render_runtime_profile_inventory.py --write --doc {doc_path}"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
