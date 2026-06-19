#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Proposes conservative design-document organization by submodule.
# upstream design ../README.md shared tool index
# downstream design ../../documents/design/README.md documents design placement
# @dependency-end
"""
organize_designs.py

Scan `documents/design/` for design markdown files and copy/move them
into `documents/design/<submodule>/` according to heuristics.

This script is conservative: it will copy files and produce a report
(`reports/design_organize_report.txt`). It will NOT delete originals.

Usage: python3 scripts/tools/organize_designs.py
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "documents" / "design"
REPORT = ROOT / "reports" / "design_organize_report.txt"


def detect_submodule(text: str) -> str | None:
    # Heuristics: look for explicit code paths like `python/jax_util/...`
    m = re.search(r"`([^`/]+/[^`]+(?:/[^`]*)?)`", text)
    if m:
        candidate = m.group(1)
        # prefer top-level submodule name
        parts = candidate.split("/")
        if parts:
            return parts[0] if parts[0] != "python" else (parts[1] if len(parts) > 1 else "python")
    return None


def main():
    if not DESIGN_DIR.exists():
        print("design directory not found", file=sys.stderr)
        raise SystemExit(1)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report_lines = []

    md_files = list(DESIGN_DIR.rglob("*.md"))
    md_files = [p for p in md_files if "templates" not in p.parts]

    found_submodules = set()

    for p in md_files:
        # skip files already under submodule dir (documents/design/<name>/*)
        rel = p.relative_to(DESIGN_DIR)
        if len(rel.parts) >= 2:
            # already in a subfolder
            report_lines.append(f"SKIP (in-subdir): {p}")
            continue

        text = p.read_text(encoding="utf-8")
        sub = detect_submodule(text)
        if sub is None:
            report_lines.append(f"UNRESOLVED (no explicit code path): {p}")
            continue
        found_submodules.add(sub)
        target_dir = DESIGN_DIR / sub
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / p.name
        shutil.copy2(p, target)
        report_lines.append(f"COPIED {p} -> {target}")

    report_lines.append("")
    report_lines.append("Detected submodules:")
    for s in sorted(found_submodules):
        report_lines.append(f" - {s}")

    REPORT.write_text("\n".join(report_lines), encoding="utf-8")
    print("Organize complete. Report:", REPORT)


if __name__ == "__main__":
    main()
