#!/usr/bin/env python3
# @dependency-start
# responsibility Scores Python and C++ OOP readability risks using lightweight static heuristics.
# upstream design ../../documents/object-oriented-design.md OOP boundary policy
# upstream design ../../documents/coding-conventions-house-style.md shared readability and responsibility rules
# upstream design ../../agents/workflows/comprehensive-refactoring-workflow.md static score gate policy
# downstream implementation ../../tests/agent_tools/test_analyze_oop_readability.py verifies OOP readability analyzer
# @dependency-end
"""Evaluate OOP readability risks for Python and C++ source files.

The score is a review aid, not a substitute for human design review. It focuses on
signals that are cheap to compute and aligned with the local OOP policy: small
responsibility boundaries, explicit state ownership, narrow public surfaces, and
avoiding vague class shapes.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BAD_CLASS_NAME_PARTS = ("Manager", "Helper", "Util", "Thing")
BAD_SYMBOL_NAME_PARTS = ("helper", "util", "misc", "tmp")
PYTHON_SUFFIXES = {".py"}
CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh", ".hxx"}


@dataclass(frozen=True)
class Thresholds:
    """Thresholds that turn static observations into findings."""

    max_function_lines: int = 80
    max_class_lines: int = 220
    max_public_methods: int = 12
    max_instance_attributes: int = 10
    max_parameters: int = 6
    max_cognitive_complexity: int = 25
    max_public_fields: int = 8
    max_base_classes: int = 2
    max_module_helpers: int = 8


@dataclass(frozen=True)
class Finding:
    """One OOP readability finding."""

    path: str
    line: int
    language: str
    severity: str
    kind: str
    symbol: str
    actual: int | str
    limit: int | str
    guidance: str

    def render(self) -> str:
        """Render a stable line for CI and agent review artifacts."""
        return (
            f"OOP_READABILITY_FINDING={self.path}:{self.line}:"
            f"{self.language}:{self.severity}:{self.kind}:{self.symbol}:"
            f"{self.actual}>{self.limit}:{self.guidance}"
        )


def build_parser() -> argparse.ArgumentParser:
    """Create command-line parser."""
    parser = argparse.ArgumentParser(
        description="Analyze Python and C++ OOP readability risks."
    )
    parser.add_argument("paths", nargs="*", help="Files or directories to analyze.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--min-score", type=int, default=85, help="Minimum accepted score.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--max-function-lines", type=int, default=80)
    parser.add_argument("--max-class-lines", type=int, default=220)
    parser.add_argument("--max-public-methods", type=int, default=12)
    parser.add_argument("--max-instance-attributes", type=int, default=10)
    parser.add_argument("--max-parameters", type=int, default=6)
    parser.add_argument("--max-cognitive-complexity", type=int, default=25)
    parser.add_argument("--max-public-fields", type=int, default=8)
    parser.add_argument("--max-base-classes", type=int, default=2)
    parser.add_argument("--max-module-helpers", type=int, default=8)
    return parser


def is_hidden(path: Path) -> bool:
    """Return true when any path part is hidden."""
    return any(part.startswith(".") for part in path.parts)


def iter_source_files(root: Path, raw_paths: list[str]) -> list[Path]:
    """Expand files and directories into supported source files."""
    targets = [root / raw_path for raw_path in raw_paths] if raw_paths else [root]
    files: list[Path] = []
    for target in targets:
        if target.is_file() and target.suffix in PYTHON_SUFFIXES | CPP_SUFFIXES:
            files.append(target.resolve())
            continue
        if target.is_dir():
            for path in sorted(target.rglob("*")):
                if not path.is_file() or path.suffix not in PYTHON_SUFFIXES | CPP_SUFFIXES:
                    continue
                try:
                    relative = path.relative_to(root)
                except ValueError:
                    relative = path
                if is_hidden(relative) or "__pycache__" in relative.parts:
                    continue
                files.append(path.resolve())
    return sorted(set(files))


def line_count(text: str) -> int:
    """Count source lines in a stable way."""
    return len(text.splitlines())


def node_length(node: ast.AST) -> int:
    """Return source-line length for an AST node."""
    lineno = getattr(node, "lineno", 0)
    end_lineno = getattr(node, "end_lineno", lineno)
    return max(1, end_lineno - lineno + 1)


def python_cognitive_complexity(node: ast.AST) -> int:
    """Estimate cognitive complexity for Python using branch and nesting signals."""

    branch_nodes = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.ExceptHandler,
        ast.With,
        ast.AsyncWith,
        ast.BoolOp,
        ast.IfExp,
        ast.Match,
    )

    def visit(current: ast.AST, nesting: int) -> int:
        score = 0
        is_branch = isinstance(current, branch_nodes)
        if is_branch:
            score += 1 + nesting
            nesting += 1
        for child in ast.iter_child_nodes(current):
            score += visit(child, nesting)
        return score

    return visit(node, 0)


def public_method_nodes(node: ast.ClassDef) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Return directly declared public Python methods."""
    return [
        item
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not item.name.startswith("_")
    ]


def self_attribute_names(node: ast.ClassDef) -> set[str]:
    """Collect attributes assigned on self in a class."""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
            if child.value.id == "self" and isinstance(child.ctx, ast.Store):
                names.add(child.attr)
    return names


def method_uses_self(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return true when method body uses self or cls."""
    if not node.args.args:
        return True
    first = node.args.args[0].arg
    if first not in {"self", "cls"}:
        return True
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, ast.Name) and child.id == first:
            return True
    return False


def python_parameter_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count user-facing parameters, excluding self/cls."""
    positional = list(node.args.posonlyargs) + list(node.args.args)
    if positional and positional[0].arg in {"self", "cls"}:
        positional = positional[1:]
    return (
        len(positional)
        + len(node.args.kwonlyargs)
        + (1 if node.args.vararg else 0)
        + (1 if node.args.kwarg else 0)
    )


def annotation_missing(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return true when public boundary annotations are incomplete."""
    args = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
    for index, arg in enumerate(args):
        if index == 0 and arg.arg in {"self", "cls"}:
            continue
        if arg.annotation is None:
            return True
    return node.returns is None


def returns_value(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return true when a Python function explicitly returns a value."""
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and child.value is not None:
            return True
    return False


def has_side_effect_call(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return true when a function appears to cross an IO or mutation boundary."""
    side_effect_names = {
        "append",
        "extend",
        "insert",
        "pop",
        "remove",
        "clear",
        "update",
        "write",
        "writelines",
        "write_text",
        "write_bytes",
        "mkdir",
        "unlink",
        "rename",
        "replace",
        "open",
        "print",
        "run",
        "call",
        "check_call",
        "check_output",
    }
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name) and func.id in side_effect_names:
                return True
            if isinstance(func, ast.Attribute) and func.attr in side_effect_names:
                return True
    return False


def none_runtime_checks(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count explicit None checks inside a Python function."""
    count = 0
    for child in ast.walk(node):
        if isinstance(child, ast.Compare):
            values = [child.left, *child.comparators]
            if any(isinstance(value, ast.Constant) and value.value is None for value in values):
                count += 1
    return count


def optional_boundary_annotations(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count parameters annotated as Optional or union-with-None."""
    args = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)

    def is_optional(annotation: ast.AST | None) -> bool:
        if annotation is None:
            return False
        if isinstance(annotation, ast.Name):
            return annotation.id in {"Optional", "Any"}
        if isinstance(annotation, ast.Attribute):
            return annotation.attr in {"Optional", "Any"}
        if isinstance(annotation, ast.Subscript):
            base = annotation.value
            if isinstance(base, ast.Name) and base.id == "Optional":
                return True
            if isinstance(base, ast.Attribute) and base.attr == "Optional":
                return True
        if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            return is_optional(annotation.left) or is_optional(annotation.right)
        if isinstance(annotation, ast.Constant) and annotation.value is None:
            return True
        return False

    return sum(1 for arg in args if is_optional(arg.annotation))


def symbol_has_vague_helper_name(name: str) -> bool:
    """Return true when a symbol name reads like an unowned helper bucket."""
    lowered = name.lower()
    return any(part in lowered for part in BAD_SYMBOL_NAME_PARTS)


def is_dataclass(node: ast.ClassDef) -> bool:
    """Return true when a Python class is decorated as a dataclass."""
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "dataclass":
            return True
        if isinstance(decorator, ast.Call):
            func = decorator.func
            if isinstance(func, ast.Name) and func.id == "dataclass":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "dataclass":
                return True
    return False


def parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    """Build a parent map for top-level and nested function classification."""
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def is_top_level_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, parents: dict[ast.AST, ast.AST]
) -> bool:
    """Return true when a function belongs directly to the module."""
    return isinstance(parents.get(node), ast.Module)


def is_direct_method(
    node: ast.FunctionDef | ast.AsyncFunctionDef, parents: dict[ast.AST, ast.AST]
) -> bool:
    """Return true when a function belongs directly to a class."""
    return isinstance(parents.get(node), ast.ClassDef)


def add_finding(
    findings: list[Finding],
    root: Path,
    path: Path,
    line: int,
    language: str,
    severity: str,
    kind: str,
    symbol: str,
    actual: int | str,
    limit: int | str,
    guidance: str,
) -> None:
    """Append a normalized finding."""
    findings.append(
        Finding(
            path=str(path.relative_to(root)),
            line=line,
            language=language,
            severity=severity,
            kind=kind,
            symbol=symbol,
            actual=actual,
            limit=limit,
            guidance=guidance,
        )
    )


def analyze_python_file(root: Path, path: Path, thresholds: Thresholds) -> list[Finding]:
    """Analyze one Python source file."""
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        add_finding(
            findings,
            root,
            path,
            exc.lineno or 1,
            "python",
            "error",
            "syntax_error",
            path.name,
            "syntax-error",
            "parseable",
            "fix-syntax-before-readability-analysis",
        )
        return findings
    parents = parent_map(tree)
    module_helper_count = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_lines = node_length(node)
            public_methods = public_method_nodes(node)
            attrs = self_attribute_names(node)
            base_count = len(node.bases)
            static_methods = [
                item
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and any(
                    isinstance(decorator, ast.Name) and decorator.id == "staticmethod"
                    for decorator in item.decorator_list
                )
            ]

            if node.name.endswith(BAD_CLASS_NAME_PARTS):
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "warn",
                    "vague_class_name",
                    node.name,
                    node.name,
                    "responsibility-name",
                    "rename-public-boundary-to-domain-responsibility",
                )
            if class_lines > thresholds.max_class_lines:
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "warn",
                    "class_lines",
                    node.name,
                    class_lines,
                    thresholds.max_class_lines,
                    "split-class-by-state-contract-or-adapter-boundary",
                )
            if len(public_methods) > thresholds.max_public_methods:
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "warn",
                    "public_methods",
                    node.name,
                    len(public_methods),
                    thresholds.max_public_methods,
                    "narrow-public-api-or-split-responsibilities",
                )
            if len(attrs) > thresholds.max_instance_attributes:
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "warn",
                    "instance_attributes",
                    node.name,
                    len(attrs),
                    thresholds.max_instance_attributes,
                    "extract-value-object-or-state-owner",
                )
            if base_count > thresholds.max_base_classes:
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "warn",
                    "base_classes",
                    node.name,
                    base_count,
                    thresholds.max_base_classes,
                    "prefer-composition-over-wide-inheritance",
                )
            if static_methods and len(static_methods) == len(
                [
                    item
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
            ):
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "warn",
                    "static_method_namespace",
                    node.name,
                    len(static_methods),
                    0,
                    "replace-namespace-class-with-module-functions",
                )
            if len(public_methods) <= 1 and not attrs and not is_dataclass(node):
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "info",
                    "thin_class",
                    node.name,
                    len(public_methods),
                    "state-or-contract",
                    "confirm-class-is-needed-or-use-function-value-object",
                )
            for method in public_methods:
                if not method_uses_self(method):
                    add_finding(
                        findings,
                        root,
                        path,
                        method.lineno,
                        "python",
                        "info",
                        "method_without_self_use",
                        f"{node.name}.{method.name}",
                        "no-self-use",
                        "uses-state-or-contract",
                        "move-pure-operation-to-function-or-service",
                    )

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = node_length(node)
            params = python_parameter_count(node)
            complexity = python_cognitive_complexity(node)
            none_checks = none_runtime_checks(node)
            optional_annotations = optional_boundary_annotations(node)
            is_top_level = is_top_level_function(node, parents)
            is_method = is_direct_method(node, parents)
            is_nested = not is_top_level and not is_method
            if is_top_level and symbol_has_vague_helper_name(node.name):
                module_helper_count += 1
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "warn",
                    "module_helper_name",
                    node.name,
                    node.name,
                    "domain-responsibility-name-or-local-helper",
                    "inline-local-helper-or-rename-to-explicit-morphism",
                )
            if length > thresholds.max_function_lines:
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "warn",
                    "function_lines",
                    node.name,
                    length,
                    thresholds.max_function_lines,
                    "split-decision-transform-and-side-effect-responsibilities",
                )
            if params > thresholds.max_parameters and not is_nested:
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "warn",
                    "parameters",
                    node.name,
                    params,
                    thresholds.max_parameters,
                    "group-stable-inputs-into-value-object",
                )
            if complexity > thresholds.max_cognitive_complexity:
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "warn",
                    "cognitive_complexity",
                    node.name,
                    complexity,
                    thresholds.max_cognitive_complexity,
                    "flatten-control-flow-and-extract-named-steps",
                )
            if not node.name.startswith("_") and annotation_missing(node):
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "info",
                    "missing_public_annotations",
                    node.name,
                    "missing",
                    "complete",
                    "add-public-boundary-types",
                )
            if is_top_level and optional_annotations > 0:
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "warn",
                    "optional_boundary",
                    node.name,
                    optional_annotations,
                    0,
                    "split-input-variants-so-static-analysis-knows-the-shape",
                )
            if none_checks > 0 and optional_annotations > 0:
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "warn",
                    "none_runtime_branch",
                    node.name,
                    none_checks,
                    "typed-variant-boundary",
                    "replace-none-driven-runtime-branch-with-explicit-type-boundary",
                )
            if is_top_level and returns_value(node) and has_side_effect_call(node):
                add_finding(
                    findings,
                    root,
                    path,
                    node.lineno,
                    "python",
                    "info",
                    "mixed_morphism_effect",
                    node.name,
                    "return+effect",
                    "pure-or-effect-boundary",
                    "separate-value-transform-from-io-or-mutation",
                )
    if module_helper_count > thresholds.max_module_helpers:
        add_finding(
            findings,
            root,
            path,
            1,
            "python",
            "warn",
            "module_helper_bucket",
            path.name,
            module_helper_count,
            thresholds.max_module_helpers,
            "inline-local-helpers-or-split-domain-services",
        )
    return findings


CLASS_RE = re.compile(
    r"(?P<kind>class|struct)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"\s*(?::(?P<bases>[^{]+))?\{",
    re.MULTILINE,
)
FUNCTION_RE = re.compile(
    r"(?P<prefix>[A-Za-z_][A-Za-z0-9_:<>\s*&~,\[\]]+?)"
    r"\s+(?P<name>[A-Za-z_~][A-Za-z0-9_:~]*)\s*"
    r"\((?P<params>[^;{}()]*)\)\s*(?:const\s*)?(?:noexcept\s*)?\{",
    re.MULTILINE,
)


def matching_brace(text: str, open_index: int) -> int:
    """Return matching brace index or end of text when unmatched."""
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return len(text)


def line_at(text: str, index: int) -> int:
    """Return 1-based source line for a text offset."""
    return text.count("\n", 0, index) + 1


def cpp_public_section(class_kind: str, body: str) -> str:
    """Return the approximate public section for a C++ class/struct body."""
    current_public = class_kind == "struct"
    lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped in {"public:", "protected:", "private:"}:
            current_public = stripped == "public:"
            continue
        if current_public:
            lines.append(line)
    return "\n".join(lines)


def cpp_member_candidates(public_body: str) -> list[str]:
    """Return rough public member declarations."""
    members: list[str] = []
    for line in public_body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue
        if "(" in stripped and ")" in stripped:
            members.append(stripped)
        elif stripped.endswith(";") and not stripped.startswith(("using ", "typedef ")):
            members.append(stripped)
    return members


def cpp_parameter_count(params: str) -> int:
    """Count C++ function parameters approximately."""
    params = params.strip()
    if not params or params == "void":
        return 0
    return len([part for part in params.split(",") if part.strip()])


def cpp_cognitive_complexity(body: str) -> int:
    """Estimate C++ cognitive complexity from control-flow tokens and nesting."""
    score = 0
    nesting = 0
    for raw in body.splitlines():
        line = raw.split("//", 1)[0]
        stripped = line.strip()
        if re.search(r"\b(if|for|while|switch|case|catch)\b", stripped):
            score += 1 + nesting
        score += stripped.count("&&") + stripped.count("||") + stripped.count("?")
        nesting += stripped.count("{")
        nesting = max(0, nesting - stripped.count("}"))
    return score


def cpp_null_runtime_checks(body: str) -> int:
    """Count C++ null checks that may indicate optional runtime routing."""
    patterns = (r"==\s*nullptr", r"!=\s*nullptr", r"==\s*NULL", r"!=\s*NULL")
    return sum(len(re.findall(pattern, body)) for pattern in patterns)


def analyze_cpp_file(root: Path, path: Path, thresholds: Thresholds) -> list[Finding]:
    """Analyze one C or C++ source file with lightweight text heuristics."""
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    for match in CLASS_RE.finditer(text):
        name = match.group("name")
        class_kind = match.group("kind")
        bases = match.group("bases") or ""
        open_index = text.find("{", match.end() - 1)
        close_index = matching_brace(text, open_index)
        body = text[open_index + 1 : close_index]
        line = line_at(text, match.start())
        public_body = cpp_public_section(class_kind, body)
        public_members = cpp_member_candidates(public_body)
        public_methods = [item for item in public_members if "(" in item and ")" in item]
        public_fields = [item for item in public_members if item not in public_methods]
        base_count = len([part for part in bases.split(",") if part.strip()])
        class_lines = line_count(text[match.start() : close_index])

        if name.endswith(BAD_CLASS_NAME_PARTS):
            add_finding(
                findings,
                root,
                path,
                line,
                "cpp",
                "warn",
                "vague_class_name",
                name,
                name,
                "responsibility-name",
                "rename-public-boundary-to-domain-responsibility",
            )
        if class_lines > thresholds.max_class_lines:
            add_finding(
                findings,
                root,
                path,
                line,
                "cpp",
                "warn",
                "class_lines",
                name,
                class_lines,
                thresholds.max_class_lines,
                "split-class-by-state-contract-or-adapter-boundary",
            )
        if len(public_methods) > thresholds.max_public_methods:
            add_finding(
                findings,
                root,
                path,
                line,
                "cpp",
                "warn",
                "public_methods",
                name,
                len(public_methods),
                thresholds.max_public_methods,
                "narrow-public-api-or-split-responsibilities",
            )
        if len(public_fields) > thresholds.max_public_fields:
            add_finding(
                findings,
                root,
                path,
                line,
                "cpp",
                "warn",
                "public_fields",
                name,
                len(public_fields),
                thresholds.max_public_fields,
                "hide-mutable-state-behind-explicit-boundary",
            )
        if public_fields and len(public_fields) > len(public_methods):
            add_finding(
                findings,
                root,
                path,
                line,
                "cpp",
                "info",
                "state_heavy_public_surface",
                name,
                len(public_fields),
                "public-behavior-boundary",
                "avoid-carrying-members-that-can-be-owned-by-value-object-or-private-state",
            )
        if base_count > thresholds.max_base_classes:
            add_finding(
                findings,
                root,
                path,
                line,
                "cpp",
                "warn",
                "base_classes",
                name,
                base_count,
                thresholds.max_base_classes,
                "prefer-composition-over-wide-inheritance",
            )

    for match in FUNCTION_RE.finditer(text):
        name = match.group("name")
        params = match.group("params")
        open_index = text.find("{", match.end() - 1)
        close_index = matching_brace(text, open_index)
        body = text[open_index + 1 : close_index]
        line = line_at(text, match.start())
        function_lines = line_count(text[match.start() : close_index])
        param_count = cpp_parameter_count(params)
        complexity = cpp_cognitive_complexity(body)
        null_checks = cpp_null_runtime_checks(body)
        if function_lines > thresholds.max_function_lines:
            add_finding(
                findings,
                root,
                path,
                line,
                "cpp",
                "warn",
                "function_lines",
                name,
                function_lines,
                thresholds.max_function_lines,
                "split-decision-transform-and-side-effect-responsibilities",
            )
        if param_count > thresholds.max_parameters:
            add_finding(
                findings,
                root,
                path,
                line,
                "cpp",
                "warn",
                "parameters",
                name,
                param_count,
                thresholds.max_parameters,
                "group-stable-inputs-into-value-object",
            )
        if complexity > thresholds.max_cognitive_complexity:
            add_finding(
                findings,
                root,
                path,
                line,
                "cpp",
                "warn",
                "cognitive_complexity",
                name,
                complexity,
                thresholds.max_cognitive_complexity,
                "flatten-control-flow-and-extract-named-steps",
            )
        if null_checks > 0:
            add_finding(
                findings,
                root,
                path,
                line,
                "cpp",
                "info",
                "null_runtime_branch",
                name,
                null_checks,
                "typed-reference-or-variant-boundary",
                "prefer-reference-optional-or-variant-boundary-over-null-driven-routing",
            )
    return findings


def score(findings: list[Finding]) -> int:
    """Calculate a conservative 0-100 score."""
    weights = {"error": 25, "warn": 5, "info": 2}
    penalty = sum(weights.get(finding.severity, 3) for finding in findings)
    return max(0, 100 - min(100, penalty))


def main() -> int:
    """Run the analyzer."""
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).resolve()
    thresholds = Thresholds(
        max_function_lines=args.max_function_lines,
        max_class_lines=args.max_class_lines,
        max_public_methods=args.max_public_methods,
        max_instance_attributes=args.max_instance_attributes,
        max_parameters=args.max_parameters,
        max_cognitive_complexity=args.max_cognitive_complexity,
        max_public_fields=args.max_public_fields,
        max_base_classes=args.max_base_classes,
        max_module_helpers=args.max_module_helpers,
    )
    files = iter_source_files(root, args.paths)
    findings: list[Finding] = []
    for path in files:
        if path.suffix in PYTHON_SUFFIXES:
            findings.extend(analyze_python_file(root, path, thresholds))
        elif path.suffix in CPP_SUFFIXES:
            findings.extend(analyze_cpp_file(root, path, thresholds))

    final_score = score(findings)
    if args.format == "json":
        payload: dict[str, Any] = {
            "files": len(files),
            "findings": [asdict(finding) for finding in findings],
            "score": final_score,
            "status": "pass" if final_score >= args.min_score else "fail",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for finding in sorted(findings, key=lambda item: (item.path, item.line, item.kind)):
            print(finding.render())
        print(f"OOP_READABILITY_FILES={len(files)}")
        print(f"OOP_READABILITY_FINDINGS={len(findings)}")
        print(f"OOP_READABILITY_SCORE={final_score}")
        print(f"OOP_READABILITY={'pass' if final_score >= args.min_score else 'fail'}")

    return 0 if final_score >= args.min_score else 1


if __name__ == "__main__":
    raise SystemExit(main())
