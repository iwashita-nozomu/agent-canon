#!/usr/bin/env python3
# @dependency-start
# responsibility Fixes markdown math notation to repository-standard dollar delimiters.
# upstream design ../README.md shared automation index
# upstream implementation ./check_markdown_math.py defines math notation policy.
# downstream implementation ../../tests/tools/test_fix_markdown_math.py verifies rewrites.
# @dependency-end

"""Fix markdown math notation to `$...$` and `$$...$$`."""

from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path

INLINE_LEGACY_PATTERN = re.compile(r"\\\((.+?)\\\)")
DISPLAY_SINGLE_LINE_LEGACY_PATTERN = re.compile(r"^\s*\\\[(.+?)\\\]\s*$")
DISPLAY_BLOCK_START_PATTERN = re.compile(r"^\s*\\\[\s*$")
DISPLAY_BLOCK_END_PATTERN = re.compile(r"^\s*\\\]\s*$")
STANDALONE_INLINE_PATTERN = re.compile(r"^\$(?!\$)(.+?)(?<!\$)\$$")


def collect_markdown_files(patterns: list[str]) -> list[str]:
    """Collect markdown files from file, directory, or glob inputs."""
    files: list[str] = []
    for pattern in patterns:
        if "*" in pattern:
            files.extend(glob.glob(pattern, recursive=True))
            continue
        path = Path(pattern)
        if path.is_dir():
            files.extend(str(child) for child in path.rglob("*.md"))
        else:
            files.append(str(path))
    filtered = [
        path
        for path in files
        if path.endswith(".md")
        and not any(part in path for part in (".git/", ".worktrees/", "__pycache__/"))
    ]
    return sorted(set(filtered))


def fix_markdown_math(content: str) -> tuple[str, list[str]]:
    """Rewrite markdown math notation to the repo-standard delimiters."""
    lines = content.splitlines()
    fixed_lines: list[str] = []
    changes: list[str] = []
    in_fence = False
    in_legacy_display = False

    for line_no, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            fixed_lines.append(line)
            continue
        if in_fence:
            fixed_lines.append(line)
            continue

        if in_legacy_display:
            if DISPLAY_BLOCK_END_PATTERN.fullmatch(line):
                fixed_lines.append("$$")
                changes.append(f"Line {line_no}: replace `\\]` with `$$`")
                in_legacy_display = False
            else:
                fixed_lines.append(line)
            continue

        if DISPLAY_BLOCK_START_PATTERN.fullmatch(line):
            fixed_lines.append("$$")
            changes.append(f"Line {line_no}: replace `\\[` with `$$`")
            in_legacy_display = True
            continue

        single_line_display = DISPLAY_SINGLE_LINE_LEGACY_PATTERN.fullmatch(line)
        if single_line_display is not None:
            fixed_lines.append(f"$${single_line_display.group(1).strip()}$$")
            changes.append(f"Line {line_no}: replace `\\[...\\]` with `$$...$$`")
            continue

        if line.strip() == "$":
            fixed_lines.append("$$")
            changes.append(f"Line {line_no}: replace `$` block delimiter with `$$`")
            continue

        standalone_inline = STANDALONE_INLINE_PATTERN.fullmatch(line.strip())
        if standalone_inline is not None:
            fixed_lines.append(f"$${standalone_inline.group(1).strip()}$$")
            changes.append(f"Line {line_no}: replace standalone `$...$` with `$$...$$`")
            continue

        updated_line = INLINE_LEGACY_PATTERN.sub(r"$\1$", line)
        if updated_line != line:
            fixed_lines.append(updated_line)
            changes.append(f"Line {line_no}: replace `\\(...\\)` with `$...$`")
            continue

        fixed_lines.append(line)

    output = "\n".join(fixed_lines)
    if content.endswith("\n"):
        output += "\n"
    return output, changes


def process_file(filepath: str) -> tuple[bool, list[str]]:
    """Rewrite one markdown file in place when changes are needed."""
    try:
        original = Path(filepath).read_text(encoding="utf-8")
        fixed, changes = fix_markdown_math(original)
        if fixed == original:
            return False, []
        Path(filepath).write_text(fixed, encoding="utf-8")
        return True, changes
    except Exception as exc:
        print(f"❌ Error processing {filepath}: {exc}", file=sys.stderr)
        return False, []


def main() -> int:
    """Run the CLI."""
    parser = argparse.ArgumentParser(description="Fix markdown math notation")
    parser.add_argument("files", nargs="*", default=["."], help="Files or directories to process")
    args = parser.parse_args()

    md_files = collect_markdown_files(args.files)
    if not md_files:
        print("No markdown files found.")
        return 0

    total_changes = 0
    modified_files = 0
    for filepath in md_files:
        changed, changes = process_file(filepath)
        if not changed:
            continue
        rel_path = filepath.replace("./", "").replace("/workspace/", "")
        print(f"\n📄 {rel_path}:")
        for change in changes:
            print(f"  {change}")
        total_changes += len(changes)
        modified_files += 1

    print(f"\n✅ Fixed: {total_changes} math notation issue(s) in {modified_files} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
