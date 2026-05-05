#!/usr/bin/env python3
# @dependency-start
# responsibility Rejects explicit Python Any usage in static-analysis surfaces.
# upstream design ../../documents/conventions/python/04_type_annotations.md type annotation policy
# upstream design ../../documents/conventions/python/07_type_checker.md pyright policy
# downstream implementation ../../tests/agent_tools/test_check_static_any.py tests checker
# @dependency-end
"""Reject explicit ``Any`` usage in Python source files."""

from __future__ import annotations

import argparse
import ast
import fnmatch
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATHS = ("python", "tests", "tools", "mcp")
DEFAULT_EXCLUDES = (
    ".git",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "reports",
    "tools/legacy",
    "vendor",
)


@dataclass(frozen=True)
class Finding:
    """One explicit Any finding."""

    path: str
    line: int
    kind: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return (
            "STATIC_ANY_FINDING="
            f"{self.path}:{self.line}:{self.kind}:{self.detail}"
        )


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Fail when Python source files use explicit typing.Any."
    )
    parser.add_argument("paths", nargs="*", help="Files or directories to scan.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--exclude",
        action="append",
        default=list(DEFAULT_EXCLUDES),
        help="Path, path prefix, path part, or glob to exclude. Repeatable.",
    )
    return parser


def path_is_excluded(relative: Path, exclude_patterns: list[str]) -> bool:
    """Return true when a root-relative path matches an exclude pattern."""
    relative_posix = relative.as_posix()
    for raw_pattern in exclude_patterns:
        pattern = raw_pattern.strip().strip("/")
        if not pattern:
            continue
        if any(char in pattern for char in "*?[]"):
            if fnmatch.fnmatch(relative_posix, pattern):
                return True
            continue
        if (
            relative_posix == pattern
            or relative_posix.startswith(f"{pattern}/")
            or pattern in relative.parts
        ):
            return True
    return False


def iter_python_files(
    root: Path,
    paths: list[str],
    exclude_patterns: list[str],
) -> list[Path]:
    """Return Python files to scan."""
    selected = paths or list(DEFAULT_PATHS)
    files: list[Path] = []
    for raw_path in selected:
        target = (root / raw_path).resolve()
        if not target.exists():
            continue
        candidates = [target] if target.is_file() else sorted(target.rglob("*.py"))
        for candidate in candidates:
            if candidate.suffix != ".py":
                continue
            try:
                relative = candidate.relative_to(root)
            except ValueError:
                continue
            if path_is_excluded(relative, exclude_patterns):
                continue
            files.append(candidate)
    return sorted(set(files))


def is_typing_any_import(node: ast.AST) -> bool:
    """Return true when an import binds typing.Any."""
    if isinstance(node, ast.ImportFrom) and node.module == "typing":
        return any(alias.name == "Any" for alias in node.names)
    return False


def any_name_findings(tree: ast.AST, relative: str) -> list[Finding]:
    """Return findings for explicit Any names or attributes."""
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if is_typing_any_import(node):
            findings.append(
                Finding(
                    path=relative,
                    line=getattr(node, "lineno", 1),
                    kind="typing_any_import",
                    detail="replace-Any-with-specific-type-or-object-boundary",
                )
            )
        elif isinstance(node, ast.Name) and node.id == "Any":
            findings.append(
                Finding(
                    path=relative,
                    line=node.lineno,
                    kind="any_annotation",
                    detail="explicit-Any-name",
                )
            )
        elif isinstance(node, ast.Attribute) and node.attr == "Any":
            findings.append(
                Finding(
                    path=relative,
                    line=node.lineno,
                    kind="any_annotation",
                    detail="explicit-typing-Any-attribute",
                )
            )
    return findings


def scan_file(root: Path, path: Path) -> list[Finding]:
    """Scan one Python file for explicit Any usage."""
    relative = path.relative_to(root).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
    except SyntaxError as exc:
        return [
            Finding(
                path=relative,
                line=exc.lineno or 1,
                kind="syntax_error",
                detail="cannot-parse-source",
            )
        ]
    return any_name_findings(tree, relative)


def main() -> int:
    """Run the checker."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    files = iter_python_files(root, list(args.paths), list(args.exclude))
    findings: list[Finding] = []
    for path in files:
        findings.extend(scan_file(root, path))
    findings.sort(key=lambda item: (item.path, item.line, item.kind, item.detail))
    print(f"STATIC_ANY_FILES={len(files)}")
    print(f"STATIC_ANY_FINDINGS={len(findings)}")
    for finding in findings:
        print(finding.render())
    print(f"STATIC_ANY={'pass' if not findings else 'fail'}")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
