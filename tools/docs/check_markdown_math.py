#!/usr/bin/env python3
# @dependency-start
# responsibility Checks markdown math documentation quality.
# upstream design ../README.md shared automation index
# @dependency-end

"""Check Markdown math notation policy."""

from __future__ import annotations

import argparse
import glob
import re
from pathlib import Path


Issue = tuple[int, str]

LEGACY_INLINE_PATTERN = re.compile(r"(?<!\\)\\\(|(?<!\\)\\\)")
LEGACY_DISPLAY_PATTERN = re.compile(r"(?<!\\)\\\[|(?<!\\)\\\]")
DISPLAY_SINGLE_LINE_PATTERN = re.compile(r"^\$\$.+\$\$$")
STANDALONE_INLINE_PATTERN = re.compile(r"^\$(?!\$).+(?<!\$)\$$")
INLINE_DOUBLE_DOLLAR_PATTERN = re.compile(r"\$\$.+?\$\$")


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


def scan_markdown_math(filepath: str) -> list[Issue]:
    """Return math-style issues for one markdown file."""
    issues: list[Issue] = []
    in_fence = False
    in_display_block = False
    with open(filepath, "r", encoding="utf-8", errors="ignore") as handle:
        for line_no, line in enumerate(handle, 1):
            stripped = line.lstrip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if LEGACY_INLINE_PATTERN.search(line):
                issues.append((line_no, "Inline math must use `$...$`, not `\\(...\\)`"))
            if LEGACY_DISPLAY_PATTERN.search(line):
                issues.append((line_no, "Display math must use `$$...$$`, not `\\[...\\]`"))
            compact = line.strip()
            if compact == "$$":
                in_display_block = not in_display_block
                continue
            if compact == "$":
                issues.append((line_no, "Display math must use `$$...$$`, not `$` block delimiters"))
                continue
            if in_display_block:
                continue
            if STANDALONE_INLINE_PATTERN.fullmatch(compact):
                issues.append((line_no, "Display math must use `$$...$$`, not `$...$` on its own line"))
                continue
            if DISPLAY_SINGLE_LINE_PATTERN.fullmatch(compact):
                continue
            if INLINE_DOUBLE_DOLLAR_PATTERN.search(line):
                issues.append((line_no, "Inline math must use `$...$`, not `$$...$$`"))
    return issues


def report(issues_by_file: dict[str, list[Issue]]) -> int:
    """Print findings and return an exit code."""
    if not issues_by_file:
        print("✅ No markdown math notation issues found!")
        return 0

    total = sum(len(issues) for issues in issues_by_file.values())
    print(f"Found {total} markdown math notation issue(s) in {len(issues_by_file)} file(s):\n")
    for filepath, issues in issues_by_file.items():
        print(f"📄 {filepath}:")
        for line_no, message in issues:
            print(f"  Line {line_no}: {message}")
        print()
    return 1


def main() -> int:
    """Run the CLI."""
    parser = argparse.ArgumentParser(description="Check markdown math notation")
    parser.add_argument("files", nargs="*", default=["."], help="Files or directories to check")
    args = parser.parse_args()

    issues_by_file: dict[str, list[Issue]] = {}
    for filepath in collect_markdown_files(args.files):
        issues = scan_markdown_math(filepath)
        if issues:
            issues_by_file[filepath] = issues
    return report(issues_by_file)


if __name__ == "__main__":
    raise SystemExit(main())
