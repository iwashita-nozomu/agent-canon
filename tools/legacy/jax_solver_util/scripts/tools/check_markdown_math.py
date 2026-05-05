#!/usr/bin/env python3
# @dependency-start
# upstream implementation ../README.md directory index and local context contract
# @dependency-end
r"""Markdown math notation checker.

Markdown 内の数式記法を点検し、インライン数式は `$...$`、
独立数式は `$$...$$` を使う方針から外れる記法を検出する。

現在は次を違反として扱う。
- `\\(...\\)` のインライン数式
- `\\[...\\]` の独立数式
- TeX 風の内容を backtick で囲った擬似 inline math
- display math がある文書で、単純な数式記号を backtick で囲った擬似 inline math

コードブロック内は検査対象から外す。
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path

Issue = tuple[int, str]


def collect_markdown_files(patterns: list[str]) -> list[str]:
    """Collect markdown files from file, directory, or glob inputs."""
    files: list[str] = []
    for pattern in patterns:
        if "*" in pattern:
            files.extend(glob.glob(pattern, recursive=True))
            continue
        path = Path(pattern)
        if path.is_dir():
            files.extend(str(p) for p in path.rglob("*.md"))
        else:
            files.append(str(path))
    filtered = [
        path
        for path in files
        if path.endswith(".md")
        and not any(part in path for part in [".git/", ".worktrees/", "__pycache__/"])
    ]
    return sorted(set(filtered))


def iter_text_lines(filepath: str):
    """Yield non-fenced lines with display-math state."""
    in_fence = False
    in_display_math = False
    with open(filepath, encoding="utf-8", errors="ignore") as handle:
        for line_no, line in enumerate(handle, 1):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if not in_fence and stripped == "$$":
                in_display_math = not in_display_math
                continue
            yield line_no, line, in_fence, in_display_math


def file_has_math_context(filepath: str) -> bool:
    """Return true when the file already uses Markdown math notation."""
    inline_math_pattern = re.compile(r"(?<!\\)\$[^$\n]+(?<!\\)\$")
    with open(filepath, encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            stripped = raw_line.strip()
            if stripped == "$$":
                return True
            if inline_math_pattern.search(raw_line):
                return True
    return False


def looks_like_math_code_span(content: str, *, file_has_context: bool) -> bool:
    """Return true when a code span is more likely math than code."""
    stripped = content.strip()
    code_identifier_pattern = re.compile(
        r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?:\([^`\n]*\))?"
    )
    if not stripped:
        return False
    if any(
        token in stripped
        for token in ("/", ".md", ".py", ".toml", ".json", ".yaml", ".yml", "::", "--")
    ):
        return False
    if file_has_context and re.fullmatch(r"[A-Za-z]", stripped):
        return True
    if re.search(r"\\[A-Za-z]+", stripped):
        return True
    if any(ch in stripped for ch in ("^", "{", "}")):
        return True
    if re.fullmatch(r"[A-Za-z]_[A-Za-z0-9{}]+", stripped):
        return True
    if re.search(r"(^|\s)(=|>=|<=|>|<)(\s|$)", stripped):
        return True
    if code_identifier_pattern.fullmatch(stripped):
        return False
    return False


def scan_markdown_math(filepath: str) -> list[Issue]:
    """Scan one markdown file and return math-notation issues."""
    issues: list[Issue] = []
    inline_pattern = re.compile(r"(?<!\\)\\\(|(?<!\\)\\\)")
    display_pattern = re.compile(r"(?<!\\)\\\[|(?<!\\)\\\]")
    code_span_pattern = re.compile(r"`([^`\n]+)`")
    has_math_context = file_has_math_context(filepath)
    for line_no, line, in_fence, in_display_math in iter_text_lines(filepath):
        if in_fence or in_display_math:
            continue
        if inline_pattern.search(line):
            issues.append((line_no, "Inline math must use `$...$`, not `\\(...\\)`"))
        if display_pattern.search(line):
            issues.append((line_no, "Display math must use `$$...$$`, not `\\[...\\]`"))
        for match in code_span_pattern.finditer(line):
            content = match.group(1)
            if looks_like_math_code_span(content, file_has_context=has_math_context):
                issues.append(
                    (
                        line_no,
                        f"Likely math notation must use `$...$`, not backticks: `{content}`",
                    )
                )
    return issues


def report(issues_by_file: dict[str, list[Issue]]) -> int:
    """Print a human-readable report and return the exit code."""
    if not issues_by_file:
        print("✅ No markdown math notation issues found!")
        return 0

    total = sum(len(issues) for issues in issues_by_file.values())
    print(f"Found {total} markdown math notation issue(s) in {len(issues_by_file)} file(s):\n")
    for filepath, issues in issues_by_file.items():
        rel_path = filepath.replace("/workspace/", "")
        print(f"📄 {rel_path}:")
        for line_no, message in issues:
            print(f"  Line {line_no}: {message}")
        print()
    return 1


def main() -> int:
    """Parse CLI arguments, scan files, and report issues."""
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
    sys.exit(main())
