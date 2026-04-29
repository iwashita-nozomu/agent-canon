#!/usr/bin/env python3
# @dependency-start
# responsibility Provides analyze refactor surface agent workflow automation.
# upstream design ../../agents/workflows/comprehensive-refactoring-workflow.md analyzer gate
# upstream design ../../documents/object-oriented-design.md OOP boundary policy
# downstream implementation ../../tests/agent_tools/test_analyze_refactor_surface.py analyzer tests
# @dependency-end
"""Score Python refactor surfaces using AST-level size and OOP-boundary heuristics."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_FUNCTION_LINES = 80
DEFAULT_MAX_CLASS_LINES = 220
DEFAULT_MAX_FILE_LINES = 500
DEFAULT_MAX_PUBLIC_METHODS = 12


@dataclass(frozen=True)
class Thresholds:
    """Thresholds used to classify refactor surface warnings."""

    max_function_lines: int = DEFAULT_MAX_FUNCTION_LINES
    max_class_lines: int = DEFAULT_MAX_CLASS_LINES
    max_file_lines: int = DEFAULT_MAX_FILE_LINES
    max_public_methods: int = DEFAULT_MAX_PUBLIC_METHODS


@dataclass(frozen=True)
class Violation:
    """One analyzer finding."""

    path: Path
    line: int
    kind: str
    name: str
    actual: int
    limit: int

    def render(self, root: Path) -> str:
        """Render a stable machine-readable finding line."""
        rel_path = self.path.relative_to(root)
        return (
            f"VIOLATION={rel_path}:{self.line}:{self.kind}:"
            f"{self.name}:{self.actual}>{self.limit}"
        )


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Analyze Python files for refactor surface size and OOP boundary risk."
    )
    parser.add_argument("paths", nargs="*", help="Files or directories to analyze.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--max-function-lines",
        type=int,
        default=DEFAULT_MAX_FUNCTION_LINES,
        help=f"Maximum allowed function or method length. Default: {DEFAULT_MAX_FUNCTION_LINES}.",
    )
    parser.add_argument(
        "--max-class-lines",
        type=int,
        default=DEFAULT_MAX_CLASS_LINES,
        help=f"Maximum allowed class length. Default: {DEFAULT_MAX_CLASS_LINES}.",
    )
    parser.add_argument(
        "--max-file-lines",
        type=int,
        default=DEFAULT_MAX_FILE_LINES,
        help=f"Maximum allowed Python file length. Default: {DEFAULT_MAX_FILE_LINES}.",
    )
    parser.add_argument(
        "--max-public-methods",
        type=int,
        default=DEFAULT_MAX_PUBLIC_METHODS,
        help=f"Maximum public methods on one class. Default: {DEFAULT_MAX_PUBLIC_METHODS}.",
    )
    parser.add_argument("--min-score", type=int, default=85, help="Minimum score.")
    return parser


def is_hidden(path: Path) -> bool:
    """Return true when any path part is hidden."""
    return any(part.startswith(".") for part in path.parts)


def iter_python_files(root: Path, raw_paths: list[str]) -> list[Path]:
    """Expand file and directory arguments into Python source files."""
    targets = [root / raw_path for raw_path in raw_paths] if raw_paths else [root]
    files: list[Path] = []
    for target in targets:
        if target.is_file() and target.suffix == ".py":
            files.append(target.resolve())
            continue
        if target.is_dir():
            for path in sorted(target.rglob("*.py")):
                try:
                    relative = path.relative_to(root)
                except ValueError:
                    relative = path
                if is_hidden(relative) or "__pycache__" in relative.parts:
                    continue
                files.append(path.resolve())
    return sorted(set(files))


def node_length(node: ast.AST) -> int:
    """Return source-line length for an AST node."""
    lineno = getattr(node, "lineno", 0)
    end_lineno = getattr(node, "end_lineno", lineno)
    return max(1, end_lineno - lineno + 1)


def public_method_count(node: ast.ClassDef) -> int:
    """Count public methods declared directly on a class."""
    count = 0
    for item in node.body:
        if (
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not item.name.startswith("_")
        ):
            count += 1
    return count


def analyze_file(path: Path, thresholds: Thresholds) -> list[Violation]:
    """Analyze one Python file."""
    text = path.read_text(encoding="utf-8")
    violations: list[Violation] = []
    line_count = len(text.splitlines())
    if line_count > thresholds.max_file_lines:
        violations.append(
            Violation(path, 1, "file_lines", path.name, line_count, thresholds.max_file_lines)
        )

    tree = ast.parse(text, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_lines = node_length(node)
            if class_lines > thresholds.max_class_lines:
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "class_lines",
                        node.name,
                        class_lines,
                        thresholds.max_class_lines,
                    )
                )
            methods = public_method_count(node)
            if methods > thresholds.max_public_methods:
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "public_methods",
                        node.name,
                        methods,
                        thresholds.max_public_methods,
                    )
                )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_lines = node_length(node)
            if function_lines > thresholds.max_function_lines:
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "function_lines",
                        node.name,
                        function_lines,
                        thresholds.max_function_lines,
                    )
                )
    return violations


def score(files: list[Path], violations: list[Violation]) -> int:
    """Calculate a conservative 0-100 score."""
    if not files:
        return 100
    penalty = min(100, len(violations) * 5)
    return max(0, 100 - penalty)


def main() -> int:
    """Run the analyzer."""
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).resolve()
    thresholds = Thresholds(
        max_function_lines=args.max_function_lines,
        max_class_lines=args.max_class_lines,
        max_file_lines=args.max_file_lines,
        max_public_methods=args.max_public_methods,
    )
    files = iter_python_files(root, args.paths)
    violations: list[Violation] = []
    for path in files:
        violations.extend(analyze_file(path, thresholds))

    final_score = score(files, violations)
    for violation in sorted(violations, key=lambda item: (item.path, item.line, item.kind)):
        print(violation.render(root))
    print(f"REFACTOR_SURFACE_FILES={len(files)}")
    print(f"REFACTOR_SURFACE_VIOLATIONS={len(violations)}")
    print(f"REFACTOR_SURFACE_SCORE={final_score}")
    if final_score >= args.min_score:
        print("REFACTOR_SURFACE=pass")
        return 0
    print("REFACTOR_SURFACE=fail")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
