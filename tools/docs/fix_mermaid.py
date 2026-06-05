#!/usr/bin/env python3
# @dependency-start
# responsibility Fixes Mermaid fenced code blocks in Markdown documents.
# upstream design ../README.md shared automation index
# downstream implementation ../../tests/tools/test_fix_mermaid.py validates Mermaid rewrites.
# downstream implementation ./format_markdown.py invokes this formatter for Markdown files.
# @dependency-end

"""Fix Mermaid fenced code blocks in Markdown documents."""

from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path

FENCE_PATTERN = re.compile(r"^(?P<indent>\s*)(?P<fence>`{3,}|~{3,})(?P<info>[^\n]*)$")
MERMAID_LANGS = {"mermaid", "mermeid"}
MERMAID_RESERVED_NODE_IDS = {
    "class",
    "classdef",
    "click",
    "direction",
    "end",
    "flowchart",
    "graph",
    "linkstyle",
    "style",
    "subgraph",
}
DIAGRAM_DIRECTIVES = {
    "flowchart",
    "graph",
    "sequencediagram",
    "classdiagram",
    "statediagram",
    "statediagram-v2",
    "erdiagram",
    "journey",
    "gantt",
    "pie",
    "mindmap",
    "timeline",
}
EDGE_PATTERN = r"(?:-->|---|==>|={2,3}|-\.\->|-\.-|~~~|~~|o--|x--)"
FLOW_DIRECTIONS = {"bt", "lr", "rl", "tb", "td"}


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
    return sorted(
        {
            path
            for path in files
            if path.endswith(".md")
            and not any(part in path for part in (".git/", ".worktrees/", "__pycache__/"))
        }
    )


def fix_mermaid_markdown(content: str) -> tuple[str, list[str]]:
    """Rewrite Mermaid fenced blocks and return change descriptions."""
    lines = content.splitlines()
    output: list[str] = []
    changes: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        fence = opening_mermaid_fence(line)
        if fence is None:
            output.append(line)
            index += 1
            continue

        indent, fence_marker, language, suffix = fence
        normalized_opening = f"{indent}{fence_marker}mermaid{suffix}"
        if language != "mermaid":
            changes.append(f"Line {index + 1}: normalize Mermaid fence language `{language}` to `mermaid`")
        output.append(normalized_opening)
        block_start = index + 1
        block_lines: list[str] = []
        index += 1
        while index < len(lines) and not closing_fence(lines[index], fence_marker):
            block_lines.append(lines[index])
            index += 1

        fixed_block, block_changes = fix_mermaid_block(block_lines, block_start)
        output.extend(fixed_block)
        changes.extend(block_changes)
        if index < len(lines):
            output.append(lines[index])
            index += 1

    fixed = "\n".join(output)
    if content.endswith("\n"):
        fixed += "\n"
    return fixed, changes


def opening_mermaid_fence(line: str) -> tuple[str, str, str, str] | None:
    """Return Mermaid fence parts for an opening fence."""
    match = FENCE_PATTERN.match(line)
    if match is None:
        return None
    info = match.group("info").strip()
    if not info:
        return None
    parts = info.split(maxsplit=1)
    language = parts[0].lower()
    if language not in MERMAID_LANGS:
        return None
    suffix = f" {parts[1]}" if len(parts) > 1 else ""
    return (match.group("indent"), match.group("fence"), language, suffix)


def closing_fence(line: str, opening_marker: str) -> bool:
    """Return whether line closes the active fence."""
    stripped = line.strip()
    fence_char = opening_marker[0]
    return bool(re.fullmatch(rf"{re.escape(fence_char)}{{{len(opening_marker)},}}\s*", stripped))


def fix_mermaid_block(lines: list[str], first_line_number: int) -> tuple[list[str], list[str]]:
    """Fix one Mermaid block."""
    rename_map = reserved_node_rename_map(lines)
    if not rename_map:
        return lines, []
    fixed_lines = [rewrite_mermaid_line(line, rename_map) for line in lines]
    changes = [
        f"Line {first_line_number + offset}: rename Mermaid reserved node id `{old}` to `{new}`"
        for offset, line in enumerate(lines)
        for old, new in sorted(rename_map.items())
        if line != fixed_lines[offset] and mermaid_node_id_used(line, old)
    ]
    return fixed_lines, changes


def reserved_node_rename_map(lines: list[str]) -> dict[str, str]:
    """Return reserved Mermaid ids that are used as node ids."""
    used: set[str] = set()
    for line in lines:
        for reserved in MERMAID_RESERVED_NODE_IDS:
            if mermaid_node_id_used(line, reserved):
                used.add(reserved)
    return {reserved: safe_node_id(reserved) for reserved in sorted(used)}


def mermaid_node_id_used(line: str, node_id: str) -> bool:
    """Return whether a reserved word appears in a node-id position."""
    stripped = line.strip()
    if not stripped or stripped.startswith("%%"):
        return False
    first = stripped.split(maxsplit=1)[0].lower()
    if first in DIAGRAM_DIRECTIVES and stripped.lower().startswith(first):
        if first in {"flowchart", "graph"} and first == node_id.lower():
            remainder = stripped[len(first) :].strip().split(maxsplit=1)
            if remainder and remainder[0].lower() in FLOW_DIRECTIONS:
                return False
        elif first == node_id.lower():
            return False
    escaped = re.escape(node_id)
    return bool(
        re.search(rf"\b{escaped}\b\s*(?=(?:\[|\(|\{{|{EDGE_PATTERN}))", line)
        or re.search(rf"({EDGE_PATTERN})\s*\|[^|]*\|\s*\b{escaped}\b", line)
        or re.search(rf"({EDGE_PATTERN})\s*\b{escaped}\b", line)
    )


def rewrite_mermaid_line(line: str, rename_map: dict[str, str]) -> str:
    """Rewrite reserved Mermaid node identifiers on one line."""
    output = line
    for old, new in sorted(rename_map.items(), key=lambda item: len(item[0]), reverse=True):
        output = rewrite_node_id(output, old, new)
    return output


def rewrite_node_id(line: str, old: str, new: str) -> str:
    """Rewrite one Mermaid node id without touching labels."""
    escaped = re.escape(old)
    line = re.sub(rf"\b{escaped}\b(?=\s*(?:\[|\(|\{{|{EDGE_PATTERN}))", new, line)
    line = re.sub(rf"(?P<edge>{EDGE_PATTERN}\s*\|[^|]*\|\s*)\b{escaped}\b", rf"\g<edge>{new}", line)
    return re.sub(rf"(?P<edge>{EDGE_PATTERN}\s*)\b{escaped}\b", rf"\g<edge>{new}", line)


def safe_node_id(value: str) -> str:
    """Return a safe replacement for a reserved node id."""
    if value == "graph":
        return "graph_node"
    return f"{value}_node"


def process_file(path: str) -> tuple[bool, list[str]]:
    """Rewrite one Markdown file in place when changes are needed."""
    try:
        original = Path(path).read_text(encoding="utf-8")
        fixed, changes = fix_mermaid_markdown(original)
        if fixed == original:
            return False, []
        Path(path).write_text(fixed, encoding="utf-8")
        return True, changes
    except Exception as exc:
        print(f"Error processing {path}: {exc}", file=sys.stderr)
        return False, []


def main() -> int:
    """Run the CLI."""
    parser = argparse.ArgumentParser(description="Fix Mermaid fenced code blocks in Markdown")
    parser.add_argument("files", nargs="*", default=["."], help="Files or directories to process")
    args = parser.parse_args()

    markdown_files = collect_markdown_files(args.files)
    changed_count = 0
    change_count = 0
    for path in markdown_files:
        changed, changes = process_file(path)
        if not changed:
            continue
        changed_count += 1
        change_count += len(changes)
        print(path)
        for change in changes:
            print(f"  {change}")
    print(f"Fixed {change_count} Mermaid issue(s) in {changed_count} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
