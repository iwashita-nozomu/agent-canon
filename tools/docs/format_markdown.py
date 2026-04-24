#!/usr/bin/env python3
"""
Simple Markdown formatter:
- normalize line endings to LF
- remove trailing spaces
- collapse more than 2 consecutive blank lines to 2
- ensure file ends with a single newline

Usage: format_markdown.py [paths...]
If no paths given, formats common doc directories: README.md, documents/, notes/, reviews/.
"""
import sys
from pathlib import Path


def process_text(text: str) -> str:
    # Normalize CRLF to LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove trailing spaces on each line
    lines = [ln.rstrip() for ln in text.split("\n")]
    # Collapse more than 2 blank lines
    out_lines = []
    blank_count = 0
    for ln in lines:
        if ln == "":
            blank_count += 1
        else:
            blank_count = 0
        if blank_count > 2:
            continue
        out_lines.append(ln)
    # Ensure single newline at EOF
    return "\n".join(out_lines).rstrip("\n") + "\n"


def format_file(p: Path) -> bool:
    try:
        original = p.read_text(encoding="utf-8")
    except Exception:
        return False
    new = process_text(original)
    if new != original:
        p.write_text(new, encoding="utf-8")
        return True
    return False


def gather_targets(args):
    if args:
        paths = [Path(a) for a in args]
    else:
        paths = [Path("README.md"), Path("documents"), Path("notes"), Path("reviews")]
    files = []
    for p in paths:
        if p.is_dir():
            for f in p.rglob("*.md"):
                files.append(f)
        elif p.is_file():
            files.append(p)
    # filter common unwanted dirs
    files = [f for f in files if ".git" not in f.parts and ".worktrees" not in f.parts]
    return sorted(set(files))


def main():
    targets = gather_targets(sys.argv[1:])
    changed = []
    for f in targets:
        ok = format_file(f)
        if ok:
            changed.append(str(f))
    print(f"Formatted {len(changed)} files")
    for c in changed:
        print(c)


if __name__ == "__main__":
    main()
