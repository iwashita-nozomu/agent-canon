#!/usr/bin/env python3
# @dependency-start
# responsibility Provides shared OOP readability heuristics for language-specific tools.
# upstream design ../../../documents/object-oriented-design.md OOP boundary policy
# upstream design ../../../documents/coding-conventions-house-style.md shared readability rules
# upstream design ../../../agents/workflows/comprehensive-refactoring-workflow.md static score gate
# downstream implementation ../python/readability.py Python OOP readability entrypoint
# downstream implementation ../cpp/readability.py C++ OOP readability entrypoint
# downstream implementation ../../../.codex/agents/oop_readability_reviewer.toml report output
# downstream implementation ../../../tests/agent_tools/test_analyze_oop_readability.py tests analyzer
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
import fnmatch
import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

BAD_CLASS_NAME_PARTS = ("Manager", "Helper", "Util", "Thing")
BAD_SYMBOL_NAME_PARTS = ("helper", "util", "misc", "tmp")
PRESENTATION_FUNCTION_PARTS = ("format", "render", "stringify", "to_string", "display", "label")
EFFECT_ADAPTER_NAMES = {"repo_root", "utc_now", "default_log_path"}
EFFECT_ADAPTER_PREFIXES = (
    "append_",
    "build_",
    "emit_",
    "git_",
    "load_",
    "parse_",
    "read_",
    "resolve_",
    "run_",
    "write_",
)
PARAMETER_AGGREGATE_FUNCTIONS = {"add_finding"}
DEFAULT_MIN_SCORE = 95
DEFAULT_SNIPPET_CONTEXT_LINES = 2
DEFAULT_MAX_REPORT_FINDINGS = 80
DEFAULT_MAX_FUNCTION_LINES = 80
DEFAULT_MAX_CLASS_LINES = 220
DEFAULT_MAX_PUBLIC_METHODS = 12
DEFAULT_MAX_INSTANCE_ATTRIBUTES = 10
DEFAULT_MAX_PARAMETERS = 6
DEFAULT_MAX_COGNITIVE_COMPLEXITY = 25
DEFAULT_MAX_PUBLIC_FIELDS = 8
DEFAULT_MAX_BASE_CLASSES = 2
DEFAULT_MAX_MODULE_HELPERS = 8
MAX_READABILITY_SCORE = 100
ERROR_SCORE_PENALTY = 25
WARN_SCORE_PENALTY = 5
INFO_SCORE_PENALTY = 2
FALLBACK_SCORE_PENALTY = 3
FALLBACK_FINDING_RANK = 9
KLOC_NORMALIZER = 1000
MODERATE_RISK_WARN_OR_ERROR_PER_KLOC = 3
HIGH_RISK_WARN_OR_ERROR_PER_KLOC = 6
TOP_FILES_SUMMARY_LIMIT = 20
PYTHON_SUFFIXES = {".py"}
CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh", ".hxx"}
LANGUAGE_SUFFIXES = {
    "all": PYTHON_SUFFIXES | CPP_SUFFIXES,
    "python": PYTHON_SUFFIXES,
    "cpp": CPP_SUFFIXES,
}

KIND_FACTS: dict[str, tuple[str, str, str]] = {
    "vague_class_name": (
        "responsibility naming",
        "The public type name does not expose a domain responsibility.",
        "Rename the boundary around the domain concept it owns.",
    ),
    "class_lines": (
        "responsibility size",
        "The class is large enough that multiple responsibilities may be hidden together.",
        "Split state ownership, contract, adapter, and orchestration roles.",
    ),
    "function_lines": (
        "operation size",
        "The operation is long enough that decision, transform, and effect steps are hard to scan.",
        "Extract named steps while keeping pure transforms and effects separate.",
    ),
    "cognitive_complexity": (
        "control-flow readability",
        "Nested control flow makes the operation hard to compose mentally.",
        "Flatten branches or extract named decisions with explicit inputs and outputs.",
    ),
    "public_methods": (
        "public surface width",
        "The public API is wide enough to suggest more than one class responsibility.",
        "Narrow the interface or split independent responsibility surfaces.",
    ),
    "public_fields": (
        "state ownership",
        "Public state is exposed directly instead of being owned by a boundary.",
        "Hide mutable state behind a value object, accessor, or state owner.",
    ),
    "state_heavy_public_surface": (
        "state ownership",
        "The type exposes more data than behavior, so ownership and invariants are unclear.",
        "Confirm it is a value object; otherwise move state behind a behavior boundary.",
    ),
    "instance_attributes": (
        "state ownership",
        "The object owns enough member state that lifecycle and invariants are hard to audit.",
        "Extract stable value objects or narrower state owners.",
    ),
    "parameters": (
        "input boundary",
        "The callable takes enough inputs that the domain shape is not explicit.",
        "Group stable inputs into a named value object or request object.",
    ),
    "base_classes": (
        "composition boundary",
        "The type depends on a wide inheritance surface.",
        "Prefer composition unless each base is a true substitutable contract.",
    ),
    "static_method_namespace": (
        "class necessity",
        "The class behaves as a namespace rather than a state or contract boundary.",
        "Use module functions or a real object with owned state and invariants.",
    ),
    "thin_class": (
        "class necessity",
        "The class has little state or behavior, so its boundary may be accidental.",
        "Confirm it is a value object or protocol; otherwise use a function or existing type.",
    ),
    "method_without_self_use": (
        "class cohesion",
        "The method does not use object state, weakening the class responsibility boundary.",
        "Move pure behavior to a function/service or make the state dependency explicit.",
    ),
    "module_helper_name": (
        "helper locality",
        "A module-level helper name hides the domain morphism it performs.",
        "Inline it locally or rename it to a typed, domain-specific transform.",
    ),
    "module_helper_bucket": (
        "helper locality",
        "The module has many helper-shaped public operations.",
        "Keep helpers local to callers or split domain services.",
    ),
    "missing_public_annotations": (
        "typed boundary",
        "A public Python boundary is missing type information.",
        "Add input and return annotations so static analysis can carry the contract.",
    ),
    "optional_boundary": (
        "typed boundary",
        "The public boundary accepts Optional/Any-shaped inputs that blur domain variants.",
        "Split variants into typed entrypoints, value objects, protocols, or explicit variants.",
    ),
    "none_runtime_branch": (
        "typed boundary",
        "The operation routes behavior through None checks instead of explicit types.",
        "Replace None-driven routing with typed variants or separate entrypoints.",
    ),
    "null_runtime_branch": (
        "typed boundary",
        "The C++ operation routes behavior through null checks.",
        "Use references, optional, variant, or explicit prevalidated handles.",
    ),
    "mixed_morphism_effect": (
        "morphism/effect separation",
        "The operation returns a value while also crossing an effect boundary.",
        "Separate pure A -> B transforms from IO, mutation, process, or resource effects.",
    ),
    "identity_function": (
        "mathematical redundancy",
        "The operation is an identity morphism that returns an input unchanged.",
        "Remove the wrapper unless the name carries a documented domain contract.",
    ),
    "pass_through_function": (
        "mathematical redundancy",
        "The operation only delegates to another callable without changing the domain or codomain.",
        "Inline the call or make the adapter contract explicit.",
    ),
    "stateless_callable_class": (
        "mathematical redundancy",
        "The class is equivalent to a plain function because it has no owned state.",
        "Use a function unless object identity, protocol conformance, or lifecycle is required.",
    ),
    "trivial_format_function": (
        "mathematical redundancy",
        "The operation only formats an existing value and does not add a domain-level structure.",
        "Inline the formatting or give the presentation boundary an explicit domain contract.",
    ),
    "syntax_error": (
        "parseability",
        "The source cannot be parsed, so readability analysis is incomplete.",
        "Fix parseability before trusting readability metrics for this file.",
    ),
}


@dataclass(frozen=True)
class Thresholds:
    """Thresholds that turn static observations into findings."""

    max_function_lines: int = DEFAULT_MAX_FUNCTION_LINES
    max_class_lines: int = DEFAULT_MAX_CLASS_LINES
    max_public_methods: int = DEFAULT_MAX_PUBLIC_METHODS
    max_instance_attributes: int = DEFAULT_MAX_INSTANCE_ATTRIBUTES
    max_parameters: int = DEFAULT_MAX_PARAMETERS
    max_cognitive_complexity: int = DEFAULT_MAX_COGNITIVE_COMPLEXITY
    max_public_fields: int = DEFAULT_MAX_PUBLIC_FIELDS
    max_base_classes: int = DEFAULT_MAX_BASE_CLASSES
    max_module_helpers: int = DEFAULT_MAX_MODULE_HELPERS


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


@dataclass(frozen=True)
class SourceContext:
    """Source-local state shared while analyzing one file."""

    root: Path
    path: Path
    language: str
    thresholds: Thresholds


@dataclass(frozen=True)
class MarkdownReportSpec:
    """Inputs required to render a Markdown analyzer report."""

    root: Path
    files: list[Path]
    findings: list[Finding]
    final_score: int
    min_score: int
    include_snippets: bool
    snippet_context: int
    max_report_findings: int
    exclude_patterns: list[str]


@dataclass(frozen=True)
class AnalyzerRun:
    """Computed analyzer state ready for output rendering."""

    root: Path
    files: list[Path]
    findings: list[Finding]
    final_score: int
    summary: dict[str, object]


def build_parser(default_language: str = "all") -> argparse.ArgumentParser:
    """Create command-line parser."""
    parser = argparse.ArgumentParser(
        description="Analyze Python and C++ OOP readability risks."
    )
    parser.add_argument("paths", nargs="*", help="Files or directories to analyze.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--language",
        choices=("all", "python", "cpp"),
        default=default_language,
        help="Source language to analyze. Language-specific wrappers set this.",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=DEFAULT_MIN_SCORE,
        help="Minimum accepted score.",
    )
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    parser.add_argument(
        "--include-snippets",
        action="store_true",
        help="Include short source snippets in JSON and Markdown output.",
    )
    parser.add_argument(
        "--snippet-context",
        type=int,
        default=DEFAULT_SNIPPET_CONTEXT_LINES,
        help="Context lines on each side of the finding line when snippets are enabled.",
    )
    parser.add_argument(
        "--max-report-findings",
        type=int,
        default=DEFAULT_MAX_REPORT_FINDINGS,
        help="Maximum finding details to print in Markdown reports.",
    )
    parser.add_argument(
        "--review-prompt-out",
        help="Write a read-only reviewer prompt that consumes the mechanical report.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "Path, path prefix, path part, or glob to exclude from analysis. "
            "Repeat for multiple exclusions, for example --exclude vendor --exclude reports."
        ),
    )
    parser.add_argument("--max-function-lines", type=int, default=DEFAULT_MAX_FUNCTION_LINES)
    parser.add_argument("--max-class-lines", type=int, default=DEFAULT_MAX_CLASS_LINES)
    parser.add_argument("--max-public-methods", type=int, default=DEFAULT_MAX_PUBLIC_METHODS)
    parser.add_argument(
        "--max-instance-attributes",
        type=int,
        default=DEFAULT_MAX_INSTANCE_ATTRIBUTES,
    )
    parser.add_argument("--max-parameters", type=int, default=DEFAULT_MAX_PARAMETERS)
    parser.add_argument(
        "--max-cognitive-complexity",
        type=int,
        default=DEFAULT_MAX_COGNITIVE_COMPLEXITY,
    )
    parser.add_argument("--max-public-fields", type=int, default=DEFAULT_MAX_PUBLIC_FIELDS)
    parser.add_argument("--max-base-classes", type=int, default=DEFAULT_MAX_BASE_CLASSES)
    parser.add_argument("--max-module-helpers", type=int, default=DEFAULT_MAX_MODULE_HELPERS)
    return parser


def is_hidden(path: Path) -> bool:
    """Return true when any path part is hidden."""
    return any(part.startswith(".") for part in path.parts)


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


def is_excluded_path(root: Path, path: Path, exclude_patterns: list[str]) -> bool:
    """Return true when either lexical or resolved root-relative path is excluded."""
    try:
        lexical_relative = path.relative_to(root)
    except ValueError:
        lexical_relative = path
    candidates = [lexical_relative]
    resolved = path.resolve()
    try:
        candidates.append(resolved.relative_to(root))
    except ValueError:
        candidates.append(resolved)
    return any(path_is_excluded(candidate, exclude_patterns) for candidate in candidates)


def source_targets(root: Path, raw_paths: list[str]) -> list[Path]:
    """Return lexical source targets requested by the caller."""
    return [root / raw_path for raw_path in raw_paths] if raw_paths else [root]


def is_supported_source(path: Path, language: str) -> bool:
    """Return true when the path has a supported source suffix."""
    return path.suffix in LANGUAGE_SUFFIXES[language]


def visible_source_path(
    root: Path,
    path: Path,
    exclude_patterns: list[str],
    language: str,
) -> bool:
    """Return true when a supported source file should be analyzed."""
    if not path.is_file() or not is_supported_source(path, language):
        return False
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    if is_hidden(relative) or "__pycache__" in relative.parts:
        return False
    return not is_excluded_path(root, path, exclude_patterns)


def iter_directory_sources(
    root: Path,
    target: Path,
    exclude_patterns: list[str],
    language: str,
) -> list[Path]:
    """Return supported files below one directory target."""
    return [
        path.resolve()
        for path in sorted(target.rglob("*"))
        if visible_source_path(root, path, exclude_patterns, language)
    ]


def iter_source_files(
    root: Path,
    raw_paths: list[str],
    exclude_patterns: list[str],
    language: str,
) -> list[Path]:
    """Expand files and directories into supported source files."""
    files: list[Path] = []
    for target in source_targets(root, raw_paths):
        if is_excluded_path(root, target, exclude_patterns):
            continue
        if target.is_file() and is_supported_source(target, language):
            files.append(target.resolve())
            continue
        if target.is_dir():
            files.extend(iter_directory_sources(root, target, exclude_patterns, language))
    return sorted(set(files))


def line_count(text: str) -> int:
    """Count visible source lines in a stable way."""
    return sum(1 for line in text.splitlines() if line.strip())


def source_loc(text: str) -> int:
    """Count nonblank noncomment-ish source lines for normalized metrics."""
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", "/*", "*")):
            continue
        count += 1
    return count


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


def collect_local_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Collect names owned by the function body, excluding boundary inputs."""
    names: set[str] = set()
    parameters = python_all_parameter_names(node)
    for target in iter_assignment_targets(node):
        collect_target_names(target, parameters, names)
    return names


def python_all_parameter_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Return every source-level parameter name including variadic names."""
    parameters = {
        arg.arg
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    }
    if node.args.vararg is not None:
        parameters.add(node.args.vararg.arg)
    if node.args.kwarg is not None:
        parameters.add(node.args.kwarg.arg)
    return parameters


def collect_target_names(target: ast.AST, parameters: set[str], names: set[str]) -> None:
    """Add names introduced by one assignment target."""
    if isinstance(target, ast.Name) and target.id not in parameters:
        names.add(target.id)
    if isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            collect_target_names(element, parameters, names)


def iter_assignment_targets(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    """Return assignment targets that create function-local names."""
    targets: list[ast.AST] = []
    for child in ast.walk(node):
        targets.extend(assignment_targets_from_node(child))
    return targets


def assignment_targets_from_node(node: ast.AST) -> list[ast.AST]:
    """Return targets introduced by one AST statement."""
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign):
        return [node.target]
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return [node.target]
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return [
            item.optional_vars
            for item in node.items
            if item.optional_vars is not None
        ]
    return []


def has_side_effect_call(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return true when a function appears to cross an external effect boundary."""
    local_mutation_names = {
        "append",
        "extend",
        "insert",
        "pop",
        "remove",
        "clear",
        "update",
        "add",
        "discard",
    }
    external_effect_names = {
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
    external_effect_names.discard("replace")
    local_names = collect_local_names(node)
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if python_call_crosses_effect(
            child.func,
            local_names,
            local_mutation_names,
            external_effect_names,
        ):
            return True
    return False


def python_call_crosses_effect(
    func: ast.expr,
    local_names: set[str],
    local_mutation_names: set[str],
    external_effect_names: set[str],
) -> bool:
    """Return true when a call expression is not confined to local aggregation."""
    if isinstance(func, ast.Name):
        return func.id in external_effect_names
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr in external_effect_names:
        return True
    if func.attr not in local_mutation_names:
        return False
    return not (isinstance(func.value, ast.Name) and func.value.id in local_names)


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


def symbol_has_vague_bucket_name(name: str) -> bool:
    """Return true when a symbol name reads like an unowned helper bucket."""
    lowered = name.lower()
    return any(part in lowered for part in BAD_SYMBOL_NAME_PARTS)


def symbol_has_presentation_name(name: str) -> bool:
    """Return true when a symbol name reads like a presentation-only operation."""
    lowered = name.lower()
    return any(part in lowered for part in PRESENTATION_FUNCTION_PARTS)


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


def base_class_name(base: ast.expr) -> str:
    """Return a dotted-ish base class name for lightweight contract checks."""
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        prefix = base_class_name(base.value)
        return f"{prefix}.{base.attr}" if prefix else base.attr
    if isinstance(base, ast.Subscript):
        return base_class_name(base.value)
    return ""


def is_algorithm_contract_class(node: ast.ClassDef) -> bool:
    """Return true for standard algorithm module protocol value classes."""
    contract_bases = {
        "amp.InitializeConfig",
        "amp.SolveConfig",
        "amp.Problem",
        "amp.State",
        "amp.Answer",
        "amp.Info",
        "amp.Algorithm",
    }
    return any(base_class_name(base) in contract_bases for base in node.bases)


def is_test_case_class(path: Path, node: ast.ClassDef) -> bool:
    """Return true for test framework classes whose size is test organization."""
    if not (path.name.startswith("test_") or "tests" in path.parts):
        return False
    base_names = {base_class_name(base) for base in node.bases}
    return node.name.endswith("Test") or bool(
        base_names.intersection({"TestCase", "unittest.TestCase"})
    )


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


def direct_class_parent(
    node: ast.FunctionDef | ast.AsyncFunctionDef, parents: dict[ast.AST, ast.AST]
) -> ast.ClassDef | None:
    """Return the direct class parent for a method, when present."""
    parent = parents.get(node)
    return parent if isinstance(parent, ast.ClassDef) else None


def is_public_python_boundary(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: dict[ast.AST, ast.AST],
) -> bool:
    """Return true when a function is part of a public source boundary."""
    if node.name.startswith("_"):
        return False
    if is_top_level_function(node, parents):
        return True
    parent = direct_class_parent(node, parents)
    return parent is not None and not parent.name.startswith("_")


def is_algorithm_contract_factory_method(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: dict[ast.AST, ast.AST],
) -> bool:
    """Return true for named constructor methods on algorithm contract classes."""
    parent = direct_class_parent(node, parents)
    return parent is not None and is_algorithm_contract_class(parent)


def python_boundary_parameter_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Return source-level parameter names, excluding self and cls."""
    args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    names = [arg.arg for arg in args]
    if names and names[0] in {"self", "cls"}:
        names = names[1:]
    return names


def only_statement(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.stmt | None:
    """Return the single meaningful body statement when exactly one exists."""
    body = [item for item in node.body if not isinstance(item, ast.Expr) or not is_docstring(item)]
    if len(body) != 1:
        return None
    return body[0]


def is_docstring(node: ast.stmt) -> bool:
    """Return true when a statement is a docstring expression."""
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def returned_identity_parameter(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str | None:
    """Return parameter name when the function only returns that parameter unchanged."""
    statement = only_statement(node)
    if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Name):
        return None
    name = statement.value.id
    return name if name in python_boundary_parameter_names(node) else None


def python_call_name(call: ast.Call) -> str:
    """Render a called function name for diagnostics."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return "call"


def is_passthrough_call(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, int] | None:
    """Return callee and argument count when a function only forwards its inputs."""
    parameter_names = python_boundary_parameter_names(node)
    if not parameter_names:
        return None
    statement = only_statement(node)
    if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Call):
        return None
    call = statement.value
    positional_names = [
        arg.id for arg in call.args if isinstance(arg, ast.Name) and arg.id in parameter_names
    ]
    keyword_names = [
        keyword.value.id
        for keyword in call.keywords
        if isinstance(keyword.value, ast.Name) and keyword.value.id in parameter_names
    ]
    forwarded = positional_names + keyword_names
    if len(forwarded) != len(parameter_names) or set(forwarded) != set(parameter_names):
        return None
    return python_call_name(call), len(forwarded)


def expression_uses_only_parameters(expression: ast.AST, parameter_names: set[str]) -> bool:
    """Return true when an expression references only function parameters."""
    seen_names = [node.id for node in ast.walk(expression) if isinstance(node, ast.Name)]
    return bool(seen_names) and all(name in parameter_names for name in seen_names)


def returned_trivial_format(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str | None:
    """Return a formatting expression label when a function only renders its input."""
    if not symbol_has_presentation_name(node.name):
        return None
    statement = only_statement(node)
    if not isinstance(statement, ast.Return) or statement.value is None:
        return None
    value = statement.value
    parameters = set(python_boundary_parameter_names(node))
    if isinstance(value, ast.JoinedStr):
        if expression_uses_only_parameters(value, parameters):
            return "f-string"
    if isinstance(value, ast.Call):
        call_name = python_call_name(value)
        if call_name in {"str", "repr", "format"} and value.args:
            if expression_uses_only_parameters(value, parameters):
                return call_name
        if isinstance(value.func, ast.Attribute) and value.func.attr == "format":
            if expression_uses_only_parameters(value, parameters):
                return "str.format"
    return None


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
    context = SourceContext(root=root, path=path, language="python", thresholds=thresholds)
    tree = parse_python_source(context, findings)
    if tree is None:
        return findings
    parents = parent_map(tree)
    module_bucket_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            analyze_python_class(context, node, findings)
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_bucket_count += analyze_python_function(context, node, parents, findings)
    add_python_module_bucket_finding(context, module_bucket_count, findings)
    return findings


def parse_python_source(context: SourceContext, findings: list[Finding]) -> ast.Module | None:
    """Parse one Python source file and record syntax errors as findings."""
    text = context.path.read_text(encoding="utf-8")
    try:
        return ast.parse(text, filename=str(context.path))
    except SyntaxError as exc:
        add_finding(
            findings,
            context.root,
            context.path,
            exc.lineno or 1,
            context.language,
            "error",
            "syntax_error",
            context.path.name,
            "syntax-error",
            "parseable",
            "fix-syntax-before-readability-analysis",
        )
        return None


def static_method_nodes(node: ast.ClassDef) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Return direct static methods declared on a Python class."""
    return [
        item
        for item in direct_method_nodes(node)
        if any(
            isinstance(decorator, ast.Name) and decorator.id == "staticmethod"
            for decorator in item.decorator_list
        )
    ]


def direct_method_nodes(node: ast.ClassDef) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Return directly declared methods, including private and magic methods."""
    return [
        item
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def analyze_python_class(
    context: SourceContext,
    node: ast.ClassDef,
    findings: list[Finding],
) -> None:
    """Record class-level readability findings for one Python class."""
    public_methods = public_method_nodes(node)
    attrs = self_attribute_names(node)
    direct_methods = direct_method_nodes(node)
    add_python_class_shape_findings(context, node, public_methods, attrs, findings)
    add_python_class_contract_findings(context, node, direct_methods, public_methods, attrs, findings)
    add_python_method_cohesion_findings(context, node, public_methods, findings)


def add_python_class_shape_findings(
    context: SourceContext,
    node: ast.ClassDef,
    public_methods: list[ast.FunctionDef | ast.AsyncFunctionDef],
    attrs: set[str],
    findings: list[Finding],
) -> None:
    """Record findings for class name, size, state, and inheritance surface."""
    if is_test_case_class(context.path, node):
        return
    add_python_class_identity_findings(context, node, findings)
    add_python_class_size_findings(context, node, public_methods, attrs, findings)


def add_python_class_identity_findings(
    context: SourceContext,
    node: ast.ClassDef,
    findings: list[Finding],
) -> None:
    """Record class name and inheritance findings."""
    if node.name.endswith(BAD_CLASS_NAME_PARTS):
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "vague_class_name",
            node.name,
            node.name,
            "responsibility-name",
            "rename-public-boundary-to-domain-responsibility",
        )
    base_count = len(node.bases)
    if base_count > context.thresholds.max_base_classes:
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "base_classes",
            node.name,
            base_count,
            context.thresholds.max_base_classes,
            "prefer-composition-over-wide-inheritance",
        )


def add_python_class_size_findings(
    context: SourceContext,
    node: ast.ClassDef,
    public_methods: list[ast.FunctionDef | ast.AsyncFunctionDef],
    attrs: set[str],
    findings: list[Finding],
) -> None:
    """Record class size, public API, and state findings."""
    thresholds = context.thresholds
    class_lines = node_length(node)
    if class_lines > thresholds.max_class_lines:
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
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
            context.root,
            context.path,
            node.lineno,
            context.language,
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
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "instance_attributes",
            node.name,
            len(attrs),
            thresholds.max_instance_attributes,
            "extract-value-object-or-state-owner",
        )


def add_python_class_contract_findings(
    context: SourceContext,
    node: ast.ClassDef,
    direct_methods: list[ast.FunctionDef | ast.AsyncFunctionDef],
    public_methods: list[ast.FunctionDef | ast.AsyncFunctionDef],
    attrs: set[str],
    findings: list[Finding],
) -> None:
    """Record findings for class necessity and contract shape."""
    if is_test_case_class(context.path, node):
        return
    static_methods = static_method_nodes(node)
    if static_methods and len(static_methods) == len(direct_methods) and not is_algorithm_contract_class(node):
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "static_method_namespace",
            node.name,
            len(static_methods),
            0,
            "replace-namespace-class-with-module-functions",
        )
    if (
        len(public_methods) <= 1
        and not attrs
        and not is_dataclass(node)
        and not is_algorithm_contract_class(node)
    ):
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "thin_class",
            node.name,
            len(public_methods),
            "state-or-contract",
            "confirm-class-is-needed-or-use-function-value-object",
        )
    if len(direct_methods) == 1 and direct_methods[0].name == "__call__" and not attrs and not node.bases:
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "stateless_callable_class",
            node.name,
            "__call__",
            "owned-state-or-contract",
            "replace-with-function-or-document-required-callable-contract",
        )


def add_python_method_cohesion_findings(
    context: SourceContext,
    node: ast.ClassDef,
    public_methods: list[ast.FunctionDef | ast.AsyncFunctionDef],
    findings: list[Finding],
) -> None:
    """Record method-level class cohesion findings."""
    if is_test_case_class(context.path, node):
        return
    for method in public_methods:
        if method_uses_self(method):
            continue
        add_finding(
            findings,
            context.root,
            context.path,
            method.lineno,
            context.language,
            "warn",
            "method_without_self_use",
            f"{node.name}.{method.name}",
            "no-self-use",
            "uses-state-or-contract",
            "move-pure-operation-to-function-or-service",
        )


def analyze_python_function(
    context: SourceContext,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: dict[ast.AST, ast.AST],
    findings: list[Finding],
) -> int:
    """Record function-level readability findings and return module bucket increment."""
    function_shape = python_function_shape(node, parents)
    add_python_function_shape_findings(context, node, function_shape, findings)
    add_python_function_type_findings(context, node, function_shape, findings)
    add_python_function_effect_findings(context, node, function_shape, parents, findings)
    return add_python_function_bucket_finding(context, node, function_shape, findings)


@dataclass(frozen=True)
class PythonFunctionShape:
    """Precomputed function metrics used by the Python analyzer."""

    length: int
    parameters: int
    complexity: int
    none_checks: int
    optional_annotations: int
    is_top_level: bool
    is_nested: bool
    is_public_boundary: bool


def python_function_shape(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: dict[ast.AST, ast.AST],
) -> PythonFunctionShape:
    """Return metrics for one Python function without recording findings."""
    is_top_level = is_top_level_function(node, parents)
    is_method = is_direct_method(node, parents)
    return PythonFunctionShape(
        length=node_length(node),
        parameters=python_parameter_count(node),
        complexity=python_cognitive_complexity(node),
        none_checks=none_runtime_checks(node),
        optional_annotations=optional_boundary_annotations(node),
        is_top_level=is_top_level,
        is_nested=not is_top_level and not is_method,
        is_public_boundary=is_public_python_boundary(node, parents),
    )


def add_python_function_bucket_finding(
    context: SourceContext,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    shape: PythonFunctionShape,
    findings: list[Finding],
) -> int:
    """Record vague top-level operation names and return bucket count increment."""
    if not shape.is_top_level or not symbol_has_vague_bucket_name(node.name):
        return 0
    add_finding(
        findings,
        context.root,
        context.path,
        node.lineno,
        context.language,
        "warn",
        "module_helper_name",
        node.name,
        node.name,
        "domain-responsibility-name-or-local-helper",
        "inline-local-helper-or-rename-to-explicit-morphism",
    )
    return 1


def add_python_function_shape_findings(
    context: SourceContext,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    shape: PythonFunctionShape,
    findings: list[Finding],
) -> None:
    """Record size, parameter, and control-flow findings."""
    thresholds = context.thresholds
    if shape.length > thresholds.max_function_lines:
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "function_lines",
            node.name,
            shape.length,
            thresholds.max_function_lines,
            "split-decision-transform-and-side-effect-responsibilities",
        )
    if (
        shape.parameters > thresholds.max_parameters
        and not shape.is_nested
        and node.name not in PARAMETER_AGGREGATE_FUNCTIONS
    ):
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "parameters",
            node.name,
            shape.parameters,
            thresholds.max_parameters,
            "group-stable-inputs-into-value-object",
        )
    if shape.complexity > thresholds.max_cognitive_complexity:
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "cognitive_complexity",
            node.name,
            shape.complexity,
            thresholds.max_cognitive_complexity,
            "flatten-control-flow-and-extract-named-steps",
        )


def add_python_function_type_findings(
    context: SourceContext,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    shape: PythonFunctionShape,
    findings: list[Finding],
) -> None:
    """Record public boundary type-shape findings."""
    if shape.is_public_boundary and annotation_missing(node):
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "missing_public_annotations",
            node.name,
            "missing",
            "complete",
            "add-public-boundary-types",
        )
    if (
        shape.is_public_boundary
        and shape.optional_annotations > 0
        and not is_standard_cli_optional_boundary(node)
    ):
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "optional_boundary",
            node.name,
            shape.optional_annotations,
            0,
            "split-input-variants-so-static-analysis-knows-the-shape",
        )
    if shape.is_public_boundary and shape.none_checks > 0 and shape.optional_annotations > 0:
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "none_runtime_branch",
            node.name,
            shape.none_checks,
            "typed-variant-boundary",
            "replace-none-driven-runtime-branch-with-explicit-type-boundary",
        )


def is_standard_cli_optional_boundary(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return true for the standard CLI ``main(argv=None)`` testable entrypoint."""
    return node.name == "main" and "argv" in python_boundary_parameter_names(node)


def add_python_function_effect_findings(
    context: SourceContext,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    shape: PythonFunctionShape,
    parents: dict[ast.AST, ast.AST],
    findings: list[Finding],
) -> None:
    """Record effect-boundary and mathematical redundancy findings."""
    if (
        shape.is_top_level
        and returns_value(node)
        and has_side_effect_call(node)
        and not is_effect_adapter_name(node.name)
    ):
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "mixed_morphism_effect",
            node.name,
            "return+effect",
            "pure-or-effect-boundary",
            "separate-value-transform-from-io-or-mutation",
        )
    if not shape.is_nested:
        add_python_redundancy_findings(context, node, parents, findings)


def is_effect_adapter_name(name: str) -> bool:
    """Return true when a function name explicitly owns an effect boundary."""
    return name in EFFECT_ADAPTER_NAMES or name.startswith(EFFECT_ADAPTER_PREFIXES)


def add_python_redundancy_findings(
    context: SourceContext,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: dict[ast.AST, ast.AST],
    findings: list[Finding],
) -> None:
    """Record identity, pass-through, and trivial presentation findings."""
    identity_parameter = returned_identity_parameter(node)
    if identity_parameter is not None:
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "identity_function",
            node.name,
            f"returns {identity_parameter}",
            "non-identity-domain-transform",
            "remove-wrapper-or-document-domain-contract",
        )
    passthrough = is_passthrough_call(node)
    if passthrough is not None and not is_algorithm_contract_factory_method(node, parents):
        callee, forwarded_count = passthrough
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "pass_through_function",
            node.name,
            f"{callee}/{forwarded_count}",
            "adds-domain-or-adapter-contract",
            "inline-call-or-document-adapter-contract",
        )
    trivial_format = returned_trivial_format(node)
    if trivial_format is not None:
        add_finding(
            findings,
            context.root,
            context.path,
            node.lineno,
            context.language,
            "warn",
            "trivial_format_function",
            node.name,
            trivial_format,
            "domain-presentation-contract",
            "inline-formatting-or-document-presentation-contract",
        )


def add_python_module_bucket_finding(
    context: SourceContext,
    module_bucket_count: int,
    findings: list[Finding],
) -> None:
    """Record a module-level bucket finding after per-function analysis."""
    if module_bucket_count <= context.thresholds.max_module_helpers:
        return
    add_finding(
        findings,
        context.root,
        context.path,
        1,
        context.language,
        "warn",
        "module_helper_bucket",
        context.path.name,
        module_bucket_count,
        context.thresholds.max_module_helpers,
        "inline-local-helpers-or-split-domain-services",
    )


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


def mask_cpp_literal_span(text: str, start: int, end: int) -> str:
    """Return a whitespace mask for one C++ literal while preserving line numbers."""
    return "".join("\n" if char == "\n" else " " for char in text[start:end])


def cpp_raw_string_literal_end(text: str, start: int) -> int | None:
    """Return the end offset of a C++ raw string literal starting at start."""
    prefix_end = start
    if text.startswith("u8", prefix_end):
        prefix_end += 2
    elif prefix_end < len(text) and text[prefix_end] in {"u", "U", "L"}:
        prefix_end += 1
    if not text.startswith('R"', prefix_end):
        return None
    delimiter_start = prefix_end + 2
    open_paren = text.find("(", delimiter_start)
    if open_paren == -1:
        return None
    delimiter = text[delimiter_start:open_paren]
    if any(char in delimiter for char in "\\ \t\n\r()"):
        return None
    terminator = f"){delimiter}\""
    close = text.find(terminator, open_paren + 1)
    if close == -1:
        return None
    return close + len(terminator)


def cpp_quoted_literal_end(text: str, start: int) -> int | None:
    """Return the end offset of a regular C++ string or character literal."""
    prefix_end = start
    if text.startswith("u8", prefix_end):
        prefix_end += 2
    elif prefix_end < len(text) and text[prefix_end] in {"u", "U", "L"}:
        prefix_end += 1
    if prefix_end >= len(text) or text[prefix_end] not in {'"', "'"}:
        return None
    quote = text[prefix_end]
    index = prefix_end + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == quote:
            return index + 1
        index += 1
    return None


def cpp_line_comment_end(text: str, start: int) -> int:
    """Return the end offset of a C++ line comment starting at start."""
    newline = text.find("\n", start + 2)
    if newline == -1:
        return len(text)
    return newline


def cpp_block_comment_end(text: str, start: int) -> int | None:
    """Return the end offset of a C++ block comment starting at start."""
    close = text.find("*/", start + 2)
    if close == -1:
        return None
    return close + 2


def cpp_text_without_comments_or_literals(text: str) -> str:
    """Mask C++ comments and literals without confusing tokens across states."""
    pieces: list[str] = []
    cursor = 0
    while cursor < len(text):
        raw_end = cpp_raw_string_literal_end(text, cursor)
        if raw_end is not None:
            pieces.append(mask_cpp_literal_span(text, cursor, raw_end))
            cursor = raw_end
            continue
        quoted_end = cpp_quoted_literal_end(text, cursor)
        if quoted_end is not None:
            pieces.append(mask_cpp_literal_span(text, cursor, quoted_end))
            cursor = quoted_end
            continue
        if text.startswith("//", cursor):
            comment_end = cpp_line_comment_end(text, cursor)
            pieces.append(mask_cpp_literal_span(text, cursor, comment_end))
            cursor = comment_end
            continue
        if text.startswith("/*", cursor):
            comment_end = cpp_block_comment_end(text, cursor)
            if comment_end is not None:
                pieces.append(mask_cpp_literal_span(text, cursor, comment_end))
                cursor = comment_end
                continue
        pieces.append(text[cursor])
        cursor += 1
    return "".join(pieces)


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


def cpp_trivial_format_function(name: str, body: str) -> str | None:
    """Return a label when a C++ function is only a thin presentation wrapper."""
    if not symbol_has_presentation_name(name):
        return None
    statements = [
        line.strip()
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith("//")
    ]
    if len(statements) != 1 or not statements[0].startswith("return "):
        return None
    statement = statements[0]
    for marker in ("std::to_string", "std::format", "fmt::format"):
        if marker in statement:
            return marker
    return None


def analyze_cpp_file(root: Path, path: Path, thresholds: Thresholds) -> list[Finding]:
    """Analyze one C or C++ source file with lightweight text heuristics."""
    findings: list[Finding] = []
    context = SourceContext(root=root, path=path, language="cpp", thresholds=thresholds)
    text = path.read_text(encoding="utf-8", errors="ignore")
    analysis_text = cpp_text_without_comments_or_literals(text)
    for match in CLASS_RE.finditer(analysis_text):
        analyze_cpp_class(context, analysis_text, match, findings)
    for match in FUNCTION_RE.finditer(analysis_text):
        analyze_cpp_function(context, analysis_text, match, findings)
    return findings


@dataclass(frozen=True)
class CppClassShape:
    """Precomputed class metrics used by the C++ analyzer."""

    name: str
    line: int
    class_lines: int
    public_methods: int
    public_fields: int
    base_count: int


@dataclass(frozen=True)
class CppFunctionShape:
    """Precomputed function metrics used by the C++ analyzer."""

    name: str
    line: int
    function_lines: int
    parameters: int
    complexity: int
    null_checks: int
    trivial_format: str | None


def analyze_cpp_class(
    context: SourceContext,
    analysis_text: str,
    match: re.Match[str],
    findings: list[Finding],
) -> None:
    """Record class-level C++ readability findings for one regex match."""
    shape = cpp_class_shape(analysis_text, match)
    add_cpp_class_identity_findings(context, shape, findings)
    add_cpp_class_surface_findings(context, shape, findings)


def cpp_class_shape(analysis_text: str, match: re.Match[str]) -> CppClassShape:
    """Return C++ class metrics without recording findings."""
    class_kind = match.group("kind")
    bases = match.group("bases") or ""
    open_index = analysis_text.find("{", match.end() - 1)
    close_index = matching_brace(analysis_text, open_index)
    body = analysis_text[open_index + 1 : close_index]
    public_body = cpp_public_section(class_kind, body)
    public_members = cpp_member_candidates(public_body)
    public_methods = [item for item in public_members if "(" in item and ")" in item]
    public_fields = [item for item in public_members if item not in public_methods]
    return CppClassShape(
        name=match.group("name"),
        line=line_at(analysis_text, match.start()),
        class_lines=line_count(analysis_text[match.start() : close_index]),
        public_methods=len(public_methods),
        public_fields=len(public_fields),
        base_count=len([part for part in bases.split(",") if part.strip()]),
    )


def add_cpp_class_identity_findings(
    context: SourceContext,
    shape: CppClassShape,
    findings: list[Finding],
) -> None:
    """Record name and inheritance findings for one C++ class."""
    if shape.name.endswith(BAD_CLASS_NAME_PARTS):
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "warn",
            "vague_class_name",
            shape.name,
            shape.name,
            "responsibility-name",
            "rename-public-boundary-to-domain-responsibility",
        )
    if shape.base_count > context.thresholds.max_base_classes:
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "warn",
            "base_classes",
            shape.name,
            shape.base_count,
            context.thresholds.max_base_classes,
            "prefer-composition-over-wide-inheritance",
        )


def add_cpp_class_surface_findings(
    context: SourceContext,
    shape: CppClassShape,
    findings: list[Finding],
) -> None:
    """Record size and public-surface findings for one C++ class."""
    thresholds = context.thresholds
    if shape.class_lines > thresholds.max_class_lines:
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "warn",
            "class_lines",
            shape.name,
            shape.class_lines,
            thresholds.max_class_lines,
            "split-class-by-state-contract-or-adapter-boundary",
        )
    if shape.public_methods > thresholds.max_public_methods:
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "warn",
            "public_methods",
            shape.name,
            shape.public_methods,
            thresholds.max_public_methods,
            "narrow-public-api-or-split-responsibilities",
        )
    if shape.public_fields > thresholds.max_public_fields:
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "warn",
            "public_fields",
            shape.name,
            shape.public_fields,
            thresholds.max_public_fields,
            "hide-mutable-state-behind-explicit-boundary",
        )
    if shape.public_fields and shape.public_fields > shape.public_methods:
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "info",
            "state_heavy_public_surface",
            shape.name,
            shape.public_fields,
            "public-behavior-boundary",
            "avoid-carrying-members-that-can-be-owned-by-value-object-or-private-state",
        )


def analyze_cpp_function(
    context: SourceContext,
    analysis_text: str,
    match: re.Match[str],
    findings: list[Finding],
) -> None:
    """Record function-level C++ readability findings for one regex match."""
    shape = cpp_function_shape(analysis_text, match)
    add_cpp_function_shape_findings(context, shape, findings)
    add_cpp_function_type_findings(context, shape, findings)


def cpp_function_shape(analysis_text: str, match: re.Match[str]) -> CppFunctionShape:
    """Return C++ function metrics without recording findings."""
    name = match.group("name")
    open_index = analysis_text.find("{", match.end() - 1)
    close_index = matching_brace(analysis_text, open_index)
    body = analysis_text[open_index + 1 : close_index]
    return CppFunctionShape(
        name=name,
        line=line_at(analysis_text, match.start()),
        function_lines=line_count(analysis_text[match.start() : close_index]),
        parameters=cpp_parameter_count(match.group("params")),
        complexity=cpp_cognitive_complexity(body),
        null_checks=cpp_null_runtime_checks(body),
        trivial_format=cpp_trivial_format_function(name, body),
    )


def add_cpp_function_shape_findings(
    context: SourceContext,
    shape: CppFunctionShape,
    findings: list[Finding],
) -> None:
    """Record size, parameter, and control-flow findings for one C++ function."""
    thresholds = context.thresholds
    if shape.function_lines > thresholds.max_function_lines:
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "warn",
            "function_lines",
            shape.name,
            shape.function_lines,
            thresholds.max_function_lines,
            "split-decision-transform-and-side-effect-responsibilities",
        )
    if shape.parameters > thresholds.max_parameters:
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "warn",
            "parameters",
            shape.name,
            shape.parameters,
            thresholds.max_parameters,
            "group-stable-inputs-into-value-object",
        )
    if shape.complexity > thresholds.max_cognitive_complexity:
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "warn",
            "cognitive_complexity",
            shape.name,
            shape.complexity,
            thresholds.max_cognitive_complexity,
            "flatten-control-flow-and-extract-named-steps",
        )


def add_cpp_function_type_findings(
    context: SourceContext,
    shape: CppFunctionShape,
    findings: list[Finding],
) -> None:
    """Record typed-boundary and presentation findings for one C++ function."""
    if shape.null_checks > 0:
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "warn",
            "null_runtime_branch",
            shape.name,
            shape.null_checks,
            "typed-reference-or-variant-boundary",
            "prefer-reference-optional-or-variant-boundary-over-null-driven-routing",
        )
    if shape.trivial_format is not None:
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "warn",
            "trivial_format_function",
            shape.name,
            shape.trivial_format,
            "domain-presentation-contract",
            "inline-formatting-or-document-presentation-contract",
        )


def score(findings: list[Finding]) -> int:
    """Calculate a conservative 0-100 score."""
    weights = {
        "error": ERROR_SCORE_PENALTY,
        "warn": WARN_SCORE_PENALTY,
        "info": INFO_SCORE_PENALTY,
    }
    penalty = sum(
        weights.get(finding.severity, FALLBACK_SCORE_PENALTY)
        for finding in findings
    )
    return max(0, MAX_READABILITY_SCORE - min(MAX_READABILITY_SCORE, penalty))


def finding_rank(finding: Finding) -> tuple[int, str, int, str]:
    """Sort findings by review priority and location."""
    severity_rank = {"error": 0, "warn": 1, "info": 2}
    return (
        severity_rank.get(finding.severity, FALLBACK_FINDING_RANK),
        finding.path,
        finding.line,
        finding.kind,
    )


def finding_facts(finding: Finding) -> dict[str, str]:
    """Return deterministic OOP interpretation fields for one finding."""
    dimension, explanation, recommended_action = KIND_FACTS.get(
        finding.kind,
        (
            "readability",
            "The static pattern increases review cost.",
            "Inspect the local responsibility boundary.",
        ),
    )
    return {
        "dimension": dimension,
        "explanation": explanation,
        "recommended_action": recommended_action,
    }


def finding_payload(finding: Finding) -> dict[str, object]:
    """Return JSON payload with mechanical interpretation attached."""
    payload = asdict(finding)
    payload.update(finding_facts(finding))
    return payload


def build_snippet_map(
    root: Path,
    findings: list[Finding],
    *,
    context: int,
) -> dict[tuple[str, int], str]:
    """Build source snippets for finding locations."""
    snippets: dict[tuple[str, int], str] = {}
    by_path: dict[str, set[int]] = {}
    for finding in findings:
        by_path.setdefault(finding.path, set()).add(finding.line)
    for relative_path, lines in by_path.items():
        path = root / relative_path
        try:
            source_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line_number in lines:
            start = max(1, line_number - context)
            end = min(len(source_lines), line_number + context)
            rendered: list[str] = []
            for current in range(start, end + 1):
                marker = ">" if current == line_number else " "
                rendered.append(f"{marker}{current:5d}: {source_lines[current - 1]}")
            snippets[(relative_path, line_number)] = "\n".join(rendered)
    return snippets


def summarize_findings(
    root: Path,
    files: list[Path],
    findings: list[Finding],
    final_score: int,
    min_score: int,
    exclude_patterns: Sequence[str] = (),
) -> dict[str, object]:
    """Build deterministic summary metrics for report output."""
    loc = 0
    for path in files:
        try:
            loc += source_loc(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    severity_counts = Counter(finding.severity for finding in findings)
    kind_counts = Counter(finding.kind for finding in findings)
    dimension_counts = Counter(finding_facts(finding)["dimension"] for finding in findings)
    warn_or_error = sum(
        1 for finding in findings if finding.severity in {"error", "warn"}
    )
    per_kloc = warn_or_error / max(1.0, loc / KLOC_NORMALIZER)
    if severity_counts.get("error", 0):
        grade = "parse-blocked"
    elif per_kloc <= 1:
        grade = "low-risk"
    elif per_kloc <= MODERATE_RISK_WARN_OR_ERROR_PER_KLOC:
        grade = "moderate-risk"
    elif per_kloc <= HIGH_RISK_WARN_OR_ERROR_PER_KLOC:
        grade = "high-risk"
    else:
        grade = "severe-risk"
    return {
        "files": len(files),
        "source_loc": loc,
        "findings": len(findings),
        "score": final_score,
        "min_score": min_score,
        "excluded_patterns": list(exclude_patterns or []),
        "status": "pass" if final_score >= min_score else "fail",
        "mechanical_grade": grade,
        "warn_or_error_per_kloc": round(per_kloc, 2),
        "severity_counts": dict(severity_counts),
        "kind_counts": dict(kind_counts),
        "dimension_counts": dict(dimension_counts),
        "top_files": [
            {"path": path, "findings": count}
            for path, count in Counter(finding.path for finding in findings).most_common(
                TOP_FILES_SUMMARY_LIMIT
            )
        ],
    }


def render_markdown_report(spec: MarkdownReportSpec) -> str:
    """Render a human-readable report from deterministic findings."""
    summary = summarize_findings(
        spec.root,
        spec.files,
        spec.findings,
        spec.final_score,
        spec.min_score,
        exclude_patterns=spec.exclude_patterns,
    )
    snippets = (
        build_snippet_map(spec.root, spec.findings, context=spec.snippet_context)
        if spec.include_snippets
        else {}
    )
    lines = markdown_summary_lines(summary)
    lines.extend(markdown_dimension_lines(summary))
    lines.extend(markdown_hotspot_lines(summary))
    lines.extend(
        markdown_finding_detail_lines(spec.findings, snippets, spec.max_report_findings)
    )
    return "\n".join(lines).rstrip() + "\n"


def markdown_summary_lines(summary: dict[str, object]) -> list[str]:
    """Render Markdown summary lines."""
    excluded_patterns_summary = cast(list[str], summary["excluded_patterns"])
    return [
        "# OOP Readability Mechanical Report",
        "",
        "This report is generated by static heuristics. It does not contain agent judgment.",
        "",
        "## Summary",
        "",
        f"- status: `{summary['status']}`",
        f"- mechanical_grade: `{summary['mechanical_grade']}`",
        f"- score: `{summary['score']}` / min `{summary['min_score']}`",
        f"- files: `{summary['files']}`",
        f"- source_loc: `{summary['source_loc']}`",
        f"- findings: `{summary['findings']}`",
        f"- warn_or_error_per_kloc: `{summary['warn_or_error_per_kloc']}`",
        f"- excluded_patterns: `{', '.join(excluded_patterns_summary) or 'none'}`",
        "",
    ]


def markdown_dimension_lines(summary: dict[str, object]) -> list[str]:
    """Render dimension and finding-kind sections."""
    dimension_counts = cast(dict[str, int], summary["dimension_counts"])
    kind_counts = cast(dict[str, int], summary["kind_counts"])
    lines = [
        "## Dimensions",
        "",
    ]
    for dimension, count in Counter(dimension_counts).most_common():
        lines.append(f"- `{dimension}`: {count}")
    lines.extend(["", "## Finding Kinds", ""])
    for kind, count in Counter(kind_counts).most_common():
        facts = KIND_FACTS.get(kind)
        explanation = facts[1] if facts else "Static readability signal."
        lines.append(f"- `{kind}`: {count} - {explanation}")
    lines.append("")
    return lines


def markdown_hotspot_lines(summary: dict[str, object]) -> list[str]:
    """Render hotspot file section."""
    top_files = cast(list[dict[str, object]], summary["top_files"])
    lines = ["## Hotspot Files", ""]
    for item in top_files:
        lines.append(f"- `{item['path']}`: {item['findings']}")
    lines.append("")
    return lines


def markdown_finding_detail_lines(
    findings: list[Finding],
    snippets: dict[tuple[str, int], str],
    max_report_findings: int,
) -> list[str]:
    """Render detailed finding lines."""
    lines = ["## Finding Details", ""]
    for finding in sorted(findings, key=finding_rank)[:max_report_findings]:
        facts = finding_facts(finding)
        lines.extend(
            [
                (
                    f"### `{finding.path}:{finding.line}` "
                    f"`{finding.kind}` `{finding.severity}`"
                ),
                "",
                f"- symbol: `{finding.symbol}`",
                f"- dimension: `{facts['dimension']}`",
                f"- actual_vs_limit: `{finding.actual}` > `{finding.limit}`",
                f"- mechanical_explanation: {facts['explanation']}",
                f"- mechanical_action: {facts['recommended_action']}",
            ]
        )
        snippet = snippets.get((finding.path, finding.line))
        if snippet:
            lines.extend(["", "```text", snippet, "```"])
        lines.append("")
    omitted = len(findings) - min(len(findings), max_report_findings)
    if omitted > 0:
        lines.append(f"_Omitted {omitted} lower-priority findings from this report._")
        lines.append("")
    return lines


def write_review_prompt(path: Path, report_path: str) -> None:
    """Write a prompt for a read-only reviewer that documents mechanical output."""
    report_reference = report_path or "<path-to-mechanical-report>"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# OOP Readability Reviewer Prompt",
                "",
                "You are a read-only OOP readability documentation reviewer.",
                "",
                "Input:",
                f"- Mechanical report: `{report_reference}`",
                "",
                "Rules:",
                "- Do not invent new findings that are not present in the mechanical report.",
                "- Do not change the pass/fail status, score, thresholds, or counts.",
                "- Treat mechanical findings as facts and write a reader-facing summary of them.",
                "- Separate false-positive candidates from accepted design risks.",
                "- Group comments by OOP principle: responsibility, state ownership,",
                "  typed boundary, composition, mathematical redundancy, and effect separation.",
                "- For each hotspot, cite `path:line`, `kind`, and the mechanical explanation.",
                "- Do not request code edits unless the report identifies a concrete risk.",
                "",
                "Expected output:",
                "- One short executive summary.",
                "- A ranked list of mechanical risk clusters.",
                "- False-positive or intentional-exception candidates.",
                "- Suggested documentation wording for the run report.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None, *, default_language: str = "all") -> int:
    """Run the analyzer."""
    parser = build_parser(default_language=default_language)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    run = build_analyzer_run(root, args)
    emit_report(run, args)
    if args.review_prompt_out:
        write_review_prompt(Path(args.review_prompt_out), "")
    return 0 if run.final_score >= args.min_score else 1


def build_thresholds(args: argparse.Namespace) -> Thresholds:
    """Build thresholds from parsed command-line arguments."""
    return Thresholds(
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


def build_analyzer_run(root: Path, args: argparse.Namespace) -> AnalyzerRun:
    """Analyze requested files and return output-ready state."""
    thresholds = build_thresholds(args)
    files = iter_source_files(root, args.paths, args.exclude, args.language)
    findings = collect_findings(root, files, thresholds)
    final_score = score(findings)
    summary = summarize_findings(
        root,
        files,
        findings,
        final_score,
        args.min_score,
        exclude_patterns=args.exclude,
    )
    return AnalyzerRun(
        root=root,
        files=files,
        findings=findings,
        final_score=final_score,
        summary=summary,
    )


def collect_findings(root: Path, files: list[Path], thresholds: Thresholds) -> list[Finding]:
    """Collect findings for every selected source file."""
    findings: list[Finding] = []
    for path in files:
        if path.suffix in PYTHON_SUFFIXES:
            findings.extend(analyze_python_file(root, path, thresholds))
        elif path.suffix in CPP_SUFFIXES:
            findings.extend(analyze_cpp_file(root, path, thresholds))
    return findings


def emit_report(run: AnalyzerRun, args: argparse.Namespace) -> None:
    """Print the requested output format."""
    if args.format == "json":
        emit_json_report(run, args)
        return
    if args.format == "markdown":
        emit_markdown_report(run, args)
        return
    emit_text_report(run, args.min_score)


def emit_json_report(run: AnalyzerRun, args: argparse.Namespace) -> None:
    """Print JSON output."""
    finding_payloads = [finding_payload(finding) for finding in run.findings]
    payload: dict[str, object] = {"summary": run.summary, "findings": finding_payloads}
    if args.include_snippets:
        snippets = build_snippet_map(run.root, run.findings, context=args.snippet_context)
        for payload_item, finding in zip(finding_payloads, run.findings, strict=True):
            payload_item["snippet"] = snippets.get((finding.path, finding.line), "")
    print(json.dumps(payload, indent=2, sort_keys=True))


def emit_markdown_report(run: AnalyzerRun, args: argparse.Namespace) -> None:
    """Print Markdown output."""
    print(
        render_markdown_report(
            MarkdownReportSpec(
                root=run.root,
                files=run.files,
                findings=run.findings,
                final_score=run.final_score,
                min_score=args.min_score,
                include_snippets=args.include_snippets,
                snippet_context=args.snippet_context,
                max_report_findings=args.max_report_findings,
                exclude_patterns=args.exclude,
            )
        ),
        end="",
    )


def emit_text_report(run: AnalyzerRun, min_score: int) -> None:
    """Print line-oriented text output."""
    for finding in sorted(run.findings, key=lambda item: (item.path, item.line, item.kind)):
        print(finding.render())
    print(f"OOP_READABILITY_FILES={len(run.files)}")
    print(f"OOP_READABILITY_FINDINGS={len(run.findings)}")
    print(f"OOP_READABILITY_SCORE={run.final_score}")
    print(f"OOP_READABILITY_GRADE={run.summary['mechanical_grade']}")
    print(f"OOP_READABILITY_WARN_OR_ERROR_PER_KLOC={run.summary['warn_or_error_per_kloc']}")
    print(f"OOP_READABILITY={'pass' if run.final_score >= min_score else 'fail'}")


if __name__ == "__main__":
    raise SystemExit(main())
