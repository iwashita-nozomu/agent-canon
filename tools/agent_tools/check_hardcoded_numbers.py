#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Detects unexplained numeric literals in Python and C++ sources.
# upstream design ../../documents/conventions/common/01_principles.md magic-number policy
# upstream design ../../documents/coding-conventions-python.md Python convention entrypoint
# upstream design ../../documents/coding-conventions-cpp.md C++ convention entrypoint
# downstream implementation ../../tests/agent_tools/test_check_hardcoded_numbers.py tests checker
# @dependency-end
"""Check Python and C++ sources for unexplained hardcoded numeric literals."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

PYTHON_SUFFIXES = {".py"}
CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh", ".hxx"}
SOURCE_SUFFIXES = PYTHON_SUFFIXES | CPP_SUFFIXES
DEFAULT_ALLOWED_NUMBERS = frozenset(
    {"-1", "-1.0", "-0.5", "0", "0.0", "0.5", "1", "1.0", "2", "2.0"}
)
ALLOW_MARKERS = ("hardcoded-number-ok", "allow-hardcoded-number", "noqa: HCN001")
PYTHON_CONSTANT_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
CPP_LITERAL_RE = re.compile(
    r"(?<![\w.])"
    r"(?P<sign>[+-]?)"
    r"(?P<body>(?:0[xX][0-9A-Fa-f]+)|(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)"
    r"(?P<suffix>[uUlLfF]*)"
    r"(?![\w.])"
)
CPP_NAMED_CONSTANT_RE = re.compile(
    r"\b(?:constexpr|const|static\s+constexpr|inline\s+constexpr)\b.*\b[A-Z][A-Z0-9_]*\b.*="
)


@dataclass(frozen=True)
class Finding:
    """One hardcoded numeric literal finding."""

    path: str
    line: int
    language: str
    literal: str
    context: str
    guidance: str

    def render(self) -> str:
        """Render a stable machine-readable finding line."""
        return (
            f"HARDCODED_NUMBER_FINDING={self.path}:{self.line}:"
            f"{self.language}:literal:{self.literal}:{self.context}:{self.guidance}"
        )


class ParentMapBuilder(ast.NodeVisitor):
    """Attach parent links to AST nodes for local context checks."""

    def generic_visit(self, node: ast.AST) -> None:
        """Visit children while storing parent pointers."""
        for child in ast.iter_child_nodes(node):
            setattr(child, "_parent", node)
        super().generic_visit(node)


class PythonNumberVisitor(ast.NodeVisitor):
    """Find numeric literals that are not named constants or explicit exceptions."""

    def __init__(
        self,
        *,
        root: Path,
        source_path: Path,
        source_lines: Sequence[str],
        allowed_numbers: set[str],
    ) -> None:
        self.root = root
        self.source_path = source_path
        self.source_lines = source_lines
        self.allowed_numbers = allowed_numbers
        self.findings: list[Finding] = []

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        """Record numeric constants that are not explained by their context."""
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float, complex)):
            return
        literal = python_literal_text(node)
        if self._is_allowed(node, literal):
            return
        self.findings.append(
            Finding(
                path=relative_path(self.root, self.source_path),
                line=node.lineno,
                language="python",
                literal=literal,
                context=context_name(node),
                guidance="name-the-constant-or-pass-it-through-a-typed-configuration",
            )
        )

    def _is_allowed(self, node: ast.Constant, literal: str) -> bool:
        if literal in self.allowed_numbers:
            return True
        if line_has_allow_marker(self.source_lines, node.lineno):
            return True
        if is_python_named_constant(node):
            return True
        return False


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Check Python and C++ sources for hardcoded numeric literals."
    )
    parser.add_argument("paths", nargs="*", help="Files or directories to check.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Check tracked files changed from HEAD instead of explicit paths.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Path, path prefix, path part, or glob to exclude. Repeat as needed.",
    )
    parser.add_argument(
        "--allowed-number",
        action="append",
        default=[],
        help="Additional literal value to allow globally, for example --allowed-number 10.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--fail-on-findings",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Return non-zero when findings exist. Defaults to true.",
    )
    return parser


def python_literal_text(node: ast.Constant) -> str:
    """Return a stable literal text for a Python numeric constant."""
    value = node.value
    parent = getattr(node, "_parent", None)
    if isinstance(parent, ast.UnaryOp) and isinstance(parent.op, ast.USub):
        return f"-{value}"
    return str(value)


def context_name(node: ast.AST) -> str:
    """Return the nearest function, class, or assignment context for a node."""
    current = getattr(node, "_parent", None)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return current.name
        if isinstance(current, ast.Assign):
            names = [target.id for target in current.targets if isinstance(target, ast.Name)]
            if names:
                return ",".join(names)
        if isinstance(current, ast.AnnAssign) and isinstance(current.target, ast.Name):
            return current.target.id
        current = getattr(current, "_parent", None)
    return "<module>"


def is_python_named_constant(node: ast.Constant) -> bool:
    """Return true when a literal initializes a module-level uppercase constant."""
    current = getattr(node, "_parent", None)
    while isinstance(current, (ast.UnaryOp, ast.BinOp, ast.Tuple, ast.List, ast.Set, ast.Dict)):
        current = getattr(current, "_parent", None)
    if isinstance(current, ast.Assign):
        parent = getattr(current, "_parent", None)
        return isinstance(parent, ast.Module) and any(
            isinstance(target, ast.Name) and PYTHON_CONSTANT_NAME.fullmatch(target.id)
            for target in current.targets
        )
    if isinstance(current, ast.AnnAssign):
        parent = getattr(current, "_parent", None)
        return (
            isinstance(parent, ast.Module)
            and isinstance(current.target, ast.Name)
            and PYTHON_CONSTANT_NAME.fullmatch(current.target.id) is not None
        )
    return False


def line_has_allow_marker(source_lines: Sequence[str], line_number: int) -> bool:
    """Return true if a source line carries an explicit hardcoded-number allowance."""
    if line_number < 1 or line_number > len(source_lines):
        return False
    line = source_lines[line_number - 1]
    return any(marker in line for marker in ALLOW_MARKERS)


def relative_path(root: Path, path: Path) -> str:
    """Return path relative to root when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def matches_exclude(relative: str, excludes: Sequence[str]) -> bool:
    """Return true when a relative path matches any exclude selector."""
    parts = set(Path(relative).parts)
    for exclude in excludes:
        normalized = exclude.strip("/")
        if not normalized:
            continue
        if (
            relative == normalized
            or relative.startswith(f"{normalized}/")
            or normalized in parts
            or fnmatch.fnmatch(relative, normalized)
        ):
            return True
    return False


def iter_changed_files(root: Path) -> list[Path]:
    """Return files changed relative to HEAD, including untracked files."""
    tracked = subprocess.run(
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
    paths = set(tracked.stdout.splitlines()) | set(untracked.stdout.splitlines())
    return [root / path for path in sorted(paths)]


def iter_explicit_files(root: Path, paths: Sequence[str]) -> list[Path]:
    """Expand explicit files and directories into source files."""
    if not paths:
        paths = ["python", "include", "src"]
    files: list[Path] = []
    for raw_path in paths:
        path = (root / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path)
        if path.is_dir():
            files.extend(child for child in path.rglob("*") if child.is_file())
        elif path.is_file():
            files.append(path)
    return sorted(set(files))


def select_source_files(root: Path, paths: Iterable[Path], excludes: Sequence[str]) -> list[Path]:
    """Filter input paths to supported source files not excluded from analysis."""
    selected: list[Path] = []
    for path in paths:
        if path.suffix not in SOURCE_SUFFIXES or not path.exists() or not path.is_file():
            continue
        relative = relative_path(root, path)
        if matches_exclude(relative, excludes):
            continue
        selected.append(path)
    return sorted(set(selected))


def check_python_file(root: Path, path: Path, allowed_numbers: set[str]) -> list[Finding]:
    """Check one Python file."""
    source = path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [
            Finding(
                path=relative_path(root, path),
                line=exc.lineno or 1,
                language="python",
                literal="<syntax-error>",
                context="<parse>",
                guidance="fix-syntax-before-hardcoded-number-analysis",
            )
        ]
    ParentMapBuilder().visit(tree)
    visitor = PythonNumberVisitor(
        root=root,
        source_path=path,
        source_lines=source_lines,
        allowed_numbers=allowed_numbers,
    )
    visitor.visit(tree)
    return visitor.findings


def check_cpp_file(root: Path, path: Path, allowed_numbers: set[str]) -> list[Finding]:
    """Check one C++ source/header file with a lightweight line scanner."""
    findings: list[Finding] = []
    in_block_comment = False
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line_has_allow_marker([raw_line], 1):
            continue
        line, in_block_comment = strip_cpp_comments(raw_line, in_block_comment)
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if CPP_NAMED_CONSTANT_RE.search(line):
            continue
        for match in CPP_LITERAL_RE.finditer(strip_cpp_strings(line)):
            literal = normalize_cpp_literal(match.group(0))
            if literal in allowed_numbers:
                continue
            findings.append(
                Finding(
                    path=relative_path(root, path),
                    line=line_number,
                    language="cpp",
                    literal=literal,
                    context="<line>",
                    guidance="name-the-constant-or-pass-it-through-a-typed-configuration",
                )
            )
    return findings


def strip_cpp_comments(line: str, in_block_comment: bool) -> tuple[str, bool]:
    """Remove C++ comments from one line while tracking block comment state."""
    output: list[str] = []
    index = 0
    while index < len(line):
        if in_block_comment:
            end = line.find("*/", index)
            if end == -1:
                return "".join(output), True
            index = end + 2
            in_block_comment = False
            continue
        if line.startswith("//", index):
            break
        if line.startswith("/*", index):
            in_block_comment = True
            index += 2
            continue
        output.append(line[index])
        index += 1
    return "".join(output), in_block_comment


def strip_cpp_strings(line: str) -> str:
    """Mask simple C++ string and character literals before number scanning."""
    result: list[str] = []
    quote: str | None = None
    escaped = False
    for char in line:
        if quote is not None:
            result.append(" ")
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
            result.append(" ")
        else:
            result.append(char)
    return "".join(result)


def normalize_cpp_literal(raw_literal: str) -> str:
    """Normalize C++ literal suffixes for comparison and reporting."""
    literal = re.sub(r"[uUlLfF]+$", "", raw_literal)
    if literal.startswith("+"):
        literal = literal[1:]
    return literal


def render_json(files: Sequence[Path], findings: Sequence[Finding]) -> str:
    """Render JSON output."""
    payload = {
        "files": len(files),
        "findings": [asdict(finding) for finding in findings],
        "status": "pass" if not findings else "fail",
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the hardcoded-number checker."""
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    allowed_numbers = set(DEFAULT_ALLOWED_NUMBERS) | set(args.allowed_number)
    candidate_files = iter_changed_files(root) if args.changed else iter_explicit_files(root, args.paths)
    files = select_source_files(root, candidate_files, args.exclude)

    findings: list[Finding] = []
    for path in files:
        if path.suffix in PYTHON_SUFFIXES:
            findings.extend(check_python_file(root, path, allowed_numbers))
        elif path.suffix in CPP_SUFFIXES:
            findings.extend(check_cpp_file(root, path, allowed_numbers))

    findings.sort(key=lambda finding: (finding.path, finding.line, finding.literal))
    if args.format == "json":
        print(render_json(files, findings))
    else:
        for finding in findings:
            print(finding.render())
        print(f"HARDCODED_NUMBERS_FILES={len(files)}")
        print(f"HARDCODED_NUMBERS_FINDINGS={len(findings)}")
        print(f"HARDCODED_NUMBERS={'pass' if not findings else 'fail'}")

    if findings and args.fail_on_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
