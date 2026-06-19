#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks Python log helper function naming.
# upstream design ../../documents/coding-conventions-logging.md logging helper naming policy
# upstream design ../../documents/conventions/common/02_naming.md shared naming policy
# downstream implementation ../../tests/agent_tools/test_check_log_helper_names.py tests checker
# @dependency-end
"""Check that Python log helper functions start with ``_log``."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATHS = ("python", "tests", "tools", "mcp")
DEFAULT_EXCLUDES = (
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "reports",
    "vendor",
)
LOG_ACTION_PREFIXES = (
    "append_log",
    "build_log",
    "collect_log",
    "emit_log",
    "format_log",
    "persist_log",
    "record_log",
    "render_log",
    "save_log",
    "write_log",
)
LOG_WRITE_METHODS = {
    "debug",
    "error",
    "exception",
    "info",
    "print",
    "warning",
    "write",
    "write_text",
}


@dataclass(frozen=True)
class Finding:
    """One log helper naming finding."""

    path: str
    line: int
    function: str
    guidance: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return (
            "LOG_HELPER_NAME_FINDING="
            f"{self.path}:{self.line}:function:{self.function}:{self.guidance}"
        )


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Fail when Python log helper functions do not start with _log."
    )
    parser.add_argument("paths", nargs="*", help="Files or directories to scan.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Check tracked files changed from HEAD instead of explicit paths.",
    )
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


def iter_changed_files(root: Path) -> list[Path]:
    """Return changed Python files relative to HEAD, including untracked files."""
    diff = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRT", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    files = set(diff.stdout.splitlines()) | set(untracked.stdout.splitlines())
    return sorted((root / path).resolve() for path in files if path.endswith(".py"))


def iter_python_files(
    root: Path,
    paths: list[str],
    exclude_patterns: list[str],
    *,
    changed: bool,
) -> list[Path]:
    """Return Python files to scan."""
    candidates = iter_changed_files(root) if changed else iter_selected_files(root, paths)
    files: list[Path] = []
    for candidate in candidates:
        if candidate.suffix != ".py" or not candidate.is_file():
            continue
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            continue
        if path_is_excluded(relative, exclude_patterns):
            continue
        files.append(candidate)
    return sorted(set(files))


def iter_selected_files(root: Path, paths: list[str]) -> list[Path]:
    """Return Python files from explicit paths or default source directories."""
    selected = paths or list(DEFAULT_PATHS)
    files: list[Path] = []
    for raw_path in selected:
        target = (root / raw_path).resolve()
        if not target.exists():
            continue
        files.extend([target] if target.is_file() else sorted(target.rglob("*.py")))
    return files


def is_log_helper_name(name: str, node: ast.AST) -> bool:
    """Return true when a function name denotes a logging helper."""
    if name.startswith("test_"):
        return False
    if name.startswith("_log"):
        return False
    if name.startswith("log_") or name.startswith(LOG_ACTION_PREFIXES):
        return True
    if name.startswith("_") and "_log" in name:
        return True
    return "log" in name and has_logging_side_effect(node)


def has_logging_side_effect(node: ast.AST) -> bool:
    """Return true when a function body appears to emit or persist log output."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and is_log_write_call(child.func):
            return True
    return False


def is_log_write_call(node: ast.AST) -> bool:
    """Return true when a call target is a common logging or write operation."""
    if isinstance(node, ast.Name):
        return node.id in LOG_WRITE_METHODS
    if isinstance(node, ast.Attribute):
        return node.attr in LOG_WRITE_METHODS
    return False


def replacement_hint(name: str) -> str:
    """Return a conventional replacement hint for a log helper name."""
    if name.startswith("_"):
        stripped = name.lstrip("_")
    else:
        stripped = name
    if stripped.startswith("log_"):
        return f"_log_{stripped.removeprefix('log_')}"
    return f"_log_{stripped}"


def scan_file(root: Path, path: Path) -> list[Finding]:
    """Scan one Python file for log helper naming findings."""
    relative = path.relative_to(root).as_posix()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
    except SyntaxError as exc:
        return [
            Finding(
                path=relative,
                line=exc.lineno or 1,
                function="<syntax-error>",
                guidance="fix-syntax-before-log-helper-name-check",
            )
        ]
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if is_log_helper_name(node.name, node):
            findings.append(
                Finding(
                    path=relative,
                    line=node.lineno,
                    function=node.name,
                    guidance=f"rename-to-{replacement_hint(node.name)}",
                )
            )
    return findings


def main() -> int:
    """Run the checker."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    files = iter_python_files(
        root,
        list(args.paths),
        list(args.exclude),
        changed=args.changed,
    )
    findings: list[Finding] = []
    for path in files:
        findings.extend(scan_file(root, path))
    findings.sort(key=lambda item: (item.path, item.line, item.function))
    print(f"LOG_HELPER_NAME_FILES={len(files)}")
    print(f"LOG_HELPER_NAME_FINDINGS={len(findings)}")
    for finding in findings:
        print(finding.render())
    print(f"LOG_HELPER_NAMES={'pass' if not findings else 'fail'}")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
