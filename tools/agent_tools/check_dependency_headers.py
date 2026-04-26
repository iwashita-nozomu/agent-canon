#!/usr/bin/env python3
# Dependency Files:
# - vendor/agent-canon/agents/canonical/CODEX_WORKFLOW.md
# - vendor/agent-canon/agents/templates/closeout_gate.md
"""Check that changed human-authored text files declare dependency files."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

CHECKABLE_SUFFIXES = {
    ".bash",
    ".cfg",
    ".css",
    ".html",
    ".md",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
    ".zsh",
}
SKIP_PREFIXES = (
    ".git/",
    ".pytest_cache/",
    ".ruff_cache/",
    "reports/agents/",
)
HEADER_SCAN_LINES = 40


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Require a top-of-file Dependency Files block in changed human-authored text files."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Specific files to check. When omitted, use --changed.",
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Check files changed relative to HEAD plus untracked files.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root. Defaults to the current directory.",
    )
    return parser


def git_lines(root: Path, args: list[str]) -> list[str]:
    """Return stdout lines from one git command."""
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def changed_paths(root: Path) -> list[Path]:
    """Return changed and untracked paths relative to one repository root."""
    changed = git_lines(root, ["diff", "--name-only", "--diff-filter=ACMRT", "HEAD", "--"])
    untracked = git_lines(root, ["ls-files", "--others", "--exclude-standard"])
    return [root / path for path in [*changed, *untracked]]


def repo_relative(root: Path, path: Path) -> str:
    """Return a stable repository-relative path for diagnostics."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def is_binary(path: Path) -> bool:
    """Return whether a file appears to be binary."""
    try:
        return b"\0" in path.read_bytes()[:4096]
    except OSError:
        return True


def should_check(root: Path, path: Path) -> bool:
    """Return whether one file is in scope for dependency header validation."""
    if not path.is_file() or path.is_symlink() or is_binary(path):
        return False
    relative = repo_relative(root, path)
    if any(relative.startswith(prefix) for prefix in SKIP_PREFIXES):
        return False
    return path.suffix.lower() in CHECKABLE_SUFFIXES


def has_dependency_header(path: Path) -> bool:
    """Return whether a file declares dependency files near the top."""
    lines = path.read_text(encoding="utf-8").splitlines()[:HEADER_SCAN_LINES]
    for index, line in enumerate(lines):
        normalized = line.lower()
        if "dependency files:" not in normalized and "依存ファイル:" not in line:
            continue
        after_colon = line.split(":", 1)[1].strip() if ":" in line else ""
        if after_colon:
            return True
        following = lines[index + 1 : index + 7]
        return any(stripped_list_item(candidate) for candidate in following)
    return False


def stripped_list_item(line: str) -> bool:
    """Return whether one line looks like a dependency list item."""
    stripped = line.strip()
    for prefix in ("#", "//", ";"):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :].strip()
    return stripped.startswith("- ") and len(stripped) > 2


def main() -> int:
    """Run dependency header validation."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    paths = (
        changed_paths(root)
        if args.changed or not args.paths
        else [Path(path) for path in args.paths]
    )
    findings: list[str] = []

    for path in paths:
        resolved = path if path.is_absolute() else root / path
        if not should_check(root, resolved):
            continue
        if not has_dependency_header(resolved):
            findings.append(f"{repo_relative(root, resolved)}: missing top Dependency Files block")

    if findings:
        print("DEPENDENCY_HEADERS=fail")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("DEPENDENCY_HEADERS=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
