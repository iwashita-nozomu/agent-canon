#!/usr/bin/env python3
"""Audit markdown links and optionally auto-fix resolvable local targets."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(".").resolve()
REPORT = ROOT / "reports" / "broken_links.txt"
DEFAULT_PATHS = [
    "README.md",
    "QUICK_START.md",
    "AGENTS.md",
    "CLAUDE.md",
    "agents",
    "documents",
    "scripts",
    ".github",
    ".agents/skills",
    ".codex/README.md",
]
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
SKIP_PARTS = {".git", ".worktrees", "__pycache__", "Archive"}


@dataclass(frozen=True)
class LinkIssue:
    """A markdown link that could not be resolved safely."""

    file_path: Path
    target: str
    candidates: tuple[Path, ...]


def find_markdown_links(text: str) -> list[tuple[str, str]]:
    """Return markdown links found in ``text``."""
    return LINK_PATTERN.findall(text)


def replace_link_targets(text: str, replacements: dict[str, str]) -> str:
    """Replace exact link targets with corrected targets."""

    def repl(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        replacement = replacements.get(target)
        if replacement is None:
            return match.group(0)
        return f"[{label}]({replacement})"

    return LINK_PATTERN.sub(repl, text)


def iter_markdown_files(paths: list[str]) -> list[Path]:
    """Expand paths into markdown files."""
    markdown_files: list[Path] = []
    for raw_path in paths:
        path = (ROOT / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path).resolve()
        if not path.exists():
            continue
        if path.is_dir():
            markdown_files.extend(path.rglob("*.md"))
            continue
        if path.suffix == ".md":
            markdown_files.append(path)

    seen: set[Path] = set()
    filtered: list[Path] = []
    for path in markdown_files:
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path in seen:
            continue
        seen.add(path)
        filtered.append(path)
    return sorted(filtered)


def build_name_index() -> dict[str, list[Path]]:
    """Build a filename index for fallback resolution."""
    name_index: dict[str, list[Path]] = {}
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        name_index.setdefault(path.name, []).append(path)
    return name_index


def is_external_target(target: str) -> bool:
    """Return whether ``target`` should be ignored by local link checks."""
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target)) or target.startswith(
        ("mailto:", "#")
    )


def split_anchor(target: str) -> tuple[str, str]:
    """Split a target into path and anchor components."""
    if "#" not in target:
        return target, ""
    target_path, anchor = target.split("#", 1)
    return target_path, anchor


def normalize_repo_absolute_path(target_path: Path) -> Path | None:
    """Map workspace-specific absolute paths back to the current checkout."""
    if not target_path.is_absolute():
        return None
    if target_path.exists():
        return target_path

    root_name = ROOT.name
    parts = list(target_path.parts)
    matching_indexes = [index for index, part in enumerate(parts) if part == root_name]
    for index in reversed(matching_indexes):
        candidate = ROOT.joinpath(*parts[index + 1 :])
        if candidate.exists():
            return candidate
    return None


def resolve_local_target(source_path: Path, target_path: str) -> Path | None:
    """Resolve a local markdown target relative to ``source_path``."""
    if not target_path:
        return None

    raw_path = Path(target_path)
    if raw_path.is_absolute():
        return normalize_repo_absolute_path(raw_path)

    candidate = (source_path.parent / raw_path).resolve()
    if candidate.exists():
        return candidate
    return None


def should_rewrite_to_relative(target_path: str, resolved: Path | None) -> bool:
    """Return whether one resolved local target should still be rewritten."""
    if resolved is None:
        return False
    raw_path = Path(target_path)
    if not raw_path.is_absolute():
        return False
    try:
        resolved.relative_to(ROOT)
    except ValueError:
        return False
    return True


def relative_target(source_path: Path, target_path: Path) -> str:
    """Return a portable relative path from ``source_path`` to ``target_path``."""
    return os.path.relpath(target_path, start=source_path.parent).replace(os.sep, "/")


def main() -> int:
    """Run the markdown link audit."""
    parser = argparse.ArgumentParser(description="Audit markdown links in repo docs.")
    parser.add_argument(
        "paths",
        nargs="*",
        default=DEFAULT_PATHS,
        help="Markdown files or directories to scan",
    )
    parser.add_argument("--apply", action="store_true", help="Apply uniquely resolvable fixes")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when unresolved or pending fixes remain",
    )
    args = parser.parse_args()

    md_files = iter_markdown_files(args.paths)
    name_index = build_name_index()
    unresolved: list[LinkIssue] = []
    fixes_made = 0
    pending_fixes = 0

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        replacements: dict[str, str] = {}
        for _, target in find_markdown_links(text):
            if is_external_target(target):
                continue

            target_path, anchor = split_anchor(target)
            resolved = resolve_local_target(md_file, target_path)
            if resolved is not None:
                if should_rewrite_to_relative(target_path, resolved):
                    new_target = relative_target(md_file, resolved)
                    if anchor:
                        new_target = f"{new_target}#{anchor}"
                    replacements[target] = new_target
                continue

            basename = Path(target_path).name
            if not basename:
                unresolved.append(LinkIssue(md_file, target, ()))
                continue

            candidates = tuple(
                candidate
                for candidate in name_index.get(basename, [])
                if not str(candidate).endswith(".bak")
            )
            if len(candidates) == 1:
                new_target = relative_target(md_file, candidates[0])
                if anchor:
                    new_target = f"{new_target}#{anchor}"
                replacements[target] = new_target
                continue

            unresolved.append(LinkIssue(md_file, target, candidates))

        if not replacements:
            continue

        if args.apply:
            md_file.write_text(replace_link_targets(text, replacements), encoding="utf-8")
            fixes_made += 1
            continue

        pending_fixes += len(replacements)
        print(f"Would fix links in {md_file}: {replacements}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for issue in unresolved:
        lines.append(f"File: {issue.file_path}")
        lines.append(f"  Missing: {issue.target}")
        if issue.candidates:
            lines.append("  Candidates:")
            for candidate in issue.candidates[:10]:
                lines.append(f"    {candidate}")
        else:
            lines.append("  Candidates: none")
        lines.append("")

    report_text = "\n".join(lines)
    if report_text:
        report_text += "\n"
    REPORT.write_text(report_text, encoding="utf-8")
    print(
        f"Report written to {REPORT} -- unresolved: {len(unresolved)}; "
        f"pending_fixes: {pending_fixes}; fixes_made: {fixes_made}"
    )

    if args.check and (unresolved or pending_fixes):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
