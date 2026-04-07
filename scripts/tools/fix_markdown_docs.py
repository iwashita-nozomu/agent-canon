#!/usr/bin/env python3
"""
Simple Markdown fixer for repository documents.

Features:
- Ensure a top-level H1 exists (insert from filename if missing)
- Remove trailing whitespace on lines
- Ensure a single blank line after header lines

Usage:
  python3 scripts/tools/fix_markdown_docs.py [--apply]

This script is conservative and only performs small formatting fixes.
"""
import argparse
from pathlib import Path
import re


def fix_markdown_text(text: str, title: str) -> str:
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = text.split("\n")
    # Remove trailing whitespace
    lines = [re.sub(r"[ \t]+$", "", ln) for ln in lines]

    # Ensure top-level H1 exists
    first_nonempty = None
    for i, ln in enumerate(lines):
        if ln.strip() != "":
            first_nonempty = i
            break
    if first_nonempty is None:
        # empty file -> insert title
        lines = [f"# {title}", ""]
    else:
        if not re.match(r"^#\s+", lines[first_nonempty]):
            lines.insert(first_nonempty, f"# {title}")

    # Ensure single blank line after any header (lines starting with #)
    out = []
    i = 0
    while i < len(lines):
        out.append(lines[i])
        if re.match(r"^#{1,6}\s+", lines[i]):
            # ensure next line is blank
            if i + 1 < len(lines) and lines[i+1].strip() != "":
                out.append("")
                i += 1
        i += 1

    # Remove trailing blank lines (max 1)
    while len(out) > 1 and out[-1] == "":
        out.pop()
    out.append("")

    return "\n".join(out)


def process_file(path: Path, apply: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    title = path.stem.replace("_", " ").title()
    new_text = fix_markdown_text(text, title)
    if new_text != text:
        if apply:
            path.write_text(new_text, encoding="utf-8")
            print(f"Fixed: {path}")
        else:
            print(f"Would fix: {path}")
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Apply changes in-place")
    ap.add_argument("--root", default="documents", help="Root folder to scan")
    args = ap.parse_args()

    root = Path(args.root)
    md_files = list(root.rglob("*.md"))
    changed = 0
    for p in md_files:
        try:
            if process_file(p, args.apply):
                changed += 1
        except Exception as e:
            print(f"Error processing {p}: {e}")

    print(f"Processed {len(md_files)} files, changed: {changed}")


if __name__ == "__main__":
    main()
