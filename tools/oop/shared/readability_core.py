#!/usr/bin/env python3
# @dependency-start
# contract tool
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
signals that are fast to compute and aligned with the local OOP policy: focused
responsibility boundaries, explicit state ownership, role-specific public surfaces, and
avoiding vague class shapes.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

BAD_CLASS_NAME_PARTS = ("Manager", "Helper", "Util", "Thing")
BAD_SYMBOL_NAME_PARTS = ("helper", "util", "misc", "tmp")
PRESENTATION_FUNCTION_PARTS = ("format", "render", "stringify", "to_string", "display", "label")
CPP_LOCAL_MUTATION_METHODS = {
    "append",
    "assign",
    "clear",
    "emplace",
    "emplace_back",
    "emplace_front",
    "erase",
    "insert",
    "pop",
    "pop_back",
    "pop_front",
    "push",
    "push_back",
    "push_front",
    "remove",
    "resize",
    "swap",
}
EFFECT_ADAPTER_NAMES = {
    "agent_canon_update_surface_status",
    "default_log_path",
    "default_oop_min_score",
    "is_git_worktree",
    "main",
    "project_root_from_script",
    "repo_root",
    "surface_manifest_paths",
    "utc_now",
}
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
DEFAULT_MAX_PUBLIC_METHODS = 12
DEFAULT_MAX_INSTANCE_ATTRIBUTES = 10
DEFAULT_MAX_PARAMETERS = 6
DEFAULT_MAX_COGNITIVE_COMPLEXITY = 25
DEFAULT_MAX_PUBLIC_FIELDS = 8
DEFAULT_MAX_BASE_CLASSES = 2
DEFAULT_MAX_MODULE_HELPERS = 8
GIT_BASELINE_TIMEOUT_SECONDS = 20
MAX_READABILITY_SCORE = 100
UNKNOWN_SEVERITY_FINDING_RANK = 9
KLOC_NORMALIZER = 1000
MILLISECONDS_PER_SECOND = 1000
MODERATE_RISK_WARN_OR_ERROR_PER_KLOC = 3
HIGH_RISK_WARN_OR_ERROR_PER_KLOC = 6
WORKFLOW_MONITOR_REPORT_DIR_ENV = "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR"
WORKFLOW_MONITOR_TIMEOUT_SECONDS = 5
TOP_FILES_SUMMARY_LIMIT = 20
CPP_CONSTRUCTOR_PREFIX_LOOKBACK_CHARS = 16
CPP_ABI_MARKER_LOOKBACK_LINES = 4
PYTHON_SUFFIXES = {".py"}
CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh", ".hxx"}
CPP_AGGREGATE_VALUE_OBJECT_SUFFIXES = (
    "Argument1D",
    "Binding",
    "Buffers",
    "Cache",
    "Comparison",
    "Config",
    "Contract",
    "Criterion",
    "Decision",
    "Descriptor",
    "DescriptorV3",
    "Eligibility",
    "Entry",
    "Functions",
    "Handle",
    "Header",
    "Identity",
    "Info",
    "Key",
    "Layout",
    "Manifest",
    "Metrics",
    "Norms",
    "Parameter",
    "Paths",
    "Point",
    "Problem",
    "Record",
    "Result",
    "Rule1D",
    "Selection",
    "Segment",
    "Set",
    "Shape",
    "Slice",
    "Snapshot",
    "Spec",
    "State",
    "Stats",
    "Storage",
    "Tape",
    "Triangle",
    "Views",
    "Workspace",
)
CPP_AGGREGATE_VALUE_OBJECT_NAMES = (
    "Add",
    "Answer",
    "Cos",
    "Divide",
    "EvaluationContext",
    "Exp",
    "FunctionIr",
    "Literal",
    "Log",
    "LoweringOpcodeFor",
    "Multiply",
    "Negate",
    "Sin",
    "StateFunction",
    "StateFunctionResult",
    "Step",
    "Subtract",
    "operator_vector_leaf_traits",
    "two_float",
)
CPP_DOMAIN_IDENTITY_FUNCTION_NAMES = {"apply_compile_bindings"}
CPP_SCALAR_OPERATOR_VALUE_OBJECT_RE = re.compile(
    r"^(?:bfloat|float|int|uint)\d+x\d+$"
)
CPP_ABI_FUNCTION_PREFIXES = ("__nad_",)
CPP_ABI_MARKER_MACROS = (
    "NATIVE_AD_AUGMENT",
    "NATIVE_AD_JVP",
    "NATIVE_AD_PRIMAL",
    "NATIVE_AD_VJP",
)
LANGUAGE_SUFFIXES = {
    "all": PYTHON_SUFFIXES | CPP_SUFFIXES,
    "python": PYTHON_SUFFIXES,
    "cpp": CPP_SUFFIXES,
}
SIGNAL_CLASS_ERROR = "error"
SIGNAL_CLASS_GATE = "gate"
SIGNAL_CLASS_REVIEW = "review"
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
REVIEW_SIGNAL_KINDS = frozenset(
    {
        "cognitive_complexity",
        "public_methods",
        "instance_attributes",
        "parameters",
        "module_helper_bucket",
    }
)

KIND_FACTS: dict[str, tuple[str, str, str]] = {
    "vague_class_name": (
        "responsibility naming",
        "The public type name does not expose a domain responsibility.",
        "Rename the boundary around the domain concept it owns.",
    ),
    "cognitive_complexity": (
        "control-flow readability",
        "Nested control flow makes the operation hard to compose mentally.",
        "Review whether branch meaning can be named or flattened without adding accidental boundaries.",
    ),
    "public_methods": (
        "public surface width",
        "The public API is wide enough to suggest more than one class responsibility.",
        "Review caller roles and refine the interface only when responsibilities are independent.",
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
        "Review whether the existing state has a stable value object or state-owner boundary.",
    ),
    "parameters": (
        "input boundary",
        "The callable takes enough inputs that the domain shape is not explicit.",
        "Review whether the inputs form a stable named domain shape before grouping them.",
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
    "redundant_class_boundary": (
        "class necessity",
        "Dependency sources only construct the class and never use it as a type boundary.",
        "Inline the boundary, use a function, or document the missing lifecycle contract.",
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
        "Review whether helpers can stay local to callers or whether an existing domain service boundary is missing.",
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

SOLID_PRINCIPLES = {
    "single_responsibility": "single responsibility",
    "open_closed": "open/closed",
    "liskov_substitution": "liskov substitution",
    "interface_segregation": "interface segregation",
    "dependency_inversion": "dependency inversion",
}

SOLID_PRINCIPLES_BY_KIND: dict[str, tuple[str, ...]] = {
    "vague_class_name": ("single_responsibility",),
    "cognitive_complexity": ("single_responsibility", "open_closed"),
    "public_methods": ("single_responsibility", "interface_segregation"),
    "public_fields": ("single_responsibility", "interface_segregation"),
    "state_heavy_public_surface": ("single_responsibility",),
    "instance_attributes": ("single_responsibility",),
    "parameters": ("interface_segregation",),
    "base_classes": ("liskov_substitution",),
    "static_method_namespace": ("single_responsibility",),
    "thin_class": ("single_responsibility",),
    "redundant_class_boundary": ("single_responsibility",),
    "method_without_self_use": ("single_responsibility",),
    "module_helper_name": ("single_responsibility",),
    "module_helper_bucket": ("single_responsibility",),
    "missing_public_annotations": ("dependency_inversion",),
    "optional_boundary": (
        "open_closed",
        "interface_segregation",
        "dependency_inversion",
    ),
    "none_runtime_branch": ("open_closed",),
    "null_runtime_branch": ("open_closed",),
    "mixed_morphism_effect": ("single_responsibility",),
    "identity_function": ("single_responsibility",),
    "pass_through_function": ("single_responsibility",),
    "stateless_callable_class": ("single_responsibility",),
    "trivial_format_function": ("single_responsibility",),
}


@dataclass(frozen=True)
class Thresholds:
    """Thresholds that turn static observations into findings."""

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
class PythonClassDef:
    """One Python class definition known to the project analyzer."""

    key: str
    module: str
    name: str
    path: Path


@dataclass
class PythonClassUsage:
    """Dependency-source observations for one Python class."""

    constructor_calls: int = 0
    annotation_refs: int = 0
    inheritance_refs: int = 0
    isinstance_refs: int = 0
    instance_method_calls: int = 0
    instance_attribute_refs: int = 0
    source_files: set[str] | None = None

    def mark_source(self, root: Path, path: Path) -> None:
        """Record the file that produced one usage observation."""
        if self.source_files is None:
            self.source_files = set()
        resolved_path = path.resolve()
        try:
            source_name = str(resolved_path.relative_to(root))
        except ValueError:
            source_name = str(resolved_path)
        self.source_files.add(source_name)

    def boundary_refs(self) -> int:
        """Return usage count that proves the class is a type boundary."""
        return self.annotation_refs + self.inheritance_refs + self.isinstance_refs

    def usage_summary(self) -> str:
        """Return a compact usage summary for findings."""
        file_count = len(self.source_files) if self.source_files is not None else 0
        return (
            f"construct={self.constructor_calls},type={self.boundary_refs()},"
            f"method={self.instance_method_calls},attr={self.instance_attribute_refs},"
            f"files={file_count}"
        )


@dataclass(frozen=True)
class PythonUsageIndex:
    """Project-level Python class definition and dependency-source index."""

    class_defs: dict[str, PythonClassDef]
    usage_by_key: dict[str, PythonClassUsage]
    unique_name_to_key: dict[str, str]
    module_names: dict[Path, str]

    def usage_for(self, path: Path, class_name: str) -> PythonClassUsage | None:
        """Return dependency-source facts for a class in one source file."""
        module = self.module_names.get(path.resolve())
        if module is not None:
            key = f"{module}.{class_name}"
            if key in self.usage_by_key:
                return self.usage_by_key[key]
        key = self.unique_name_to_key.get(class_name)
        return self.usage_by_key.get(key) if key is not None else None


@dataclass(frozen=True)
class PythonUsageSourceSet:
    """Python files and source roots used only for dependency-source context."""

    files: list[Path]
    source_roots: tuple[Path, ...]


@dataclass(frozen=True)
class CppClassDef:
    """One C++ class or struct definition known to the project analyzer."""

    key: str
    name: str
    path: Path


@dataclass
class CppClassUsage:
    """Dependency-source observations for one C++ class or struct."""

    constructor_calls: int = 0
    type_refs: int = 0
    inheritance_refs: int = 0
    source_files: set[str] | None = None

    def mark_source(self, root: Path, path: Path) -> None:
        """Record the file that produced one usage observation."""
        if self.source_files is None:
            self.source_files = set()
        resolved_path = path.resolve()
        try:
            source_name = str(resolved_path.relative_to(root))
        except ValueError:
            source_name = str(resolved_path)
        self.source_files.add(source_name)

    def boundary_refs(self) -> int:
        """Return usage count that proves the class is a type boundary."""
        return self.type_refs + self.inheritance_refs

    def usage_summary(self) -> str:
        """Return a compact usage summary for findings."""
        file_count = len(self.source_files) if self.source_files is not None else 0
        return (
            f"construct={self.constructor_calls},type={self.type_refs},"
            f"inherit={self.inheritance_refs},files={file_count}"
        )


@dataclass(frozen=True)
class CppUsageIndex:
    """Project-level C++ class definitions and dependency-source usage facts."""

    class_defs: dict[str, CppClassDef]
    usage_by_key: dict[str, CppClassUsage]
    unique_name_to_key: dict[str, str]
    path_name_to_key: dict[tuple[Path, str], str]

    def usage_for(self, path: Path, class_name: str) -> CppClassUsage | None:
        """Return dependency-source facts for a class in one source file."""
        key = self.path_name_to_key.get((path.resolve(), class_name))
        if key is not None and key in self.usage_by_key:
            return self.usage_by_key[key]
        key = self.unique_name_to_key.get(class_name)
        return self.usage_by_key.get(key) if key is not None else None


@dataclass(frozen=True)
class CppUsageSourceSet:
    """C++ files used only for dependency-source context."""

    files: list[Path]


@dataclass(frozen=True)
class DependencyUsageContext:
    """Additional source context used for class dependency-source analysis."""

    usage_roots: tuple[str, ...] = ()
    dependency_modules: tuple[str, ...] = ()


@dataclass(frozen=True)
class BaselineComparisonSpec:
    """Inputs that control baseline finding filtering."""

    language: str
    baseline_ref: str
    dependency_context: DependencyUsageContext


@dataclass(frozen=True)
class PythonUsageBuildContext:
    """Inputs shared while building Python project usage facts."""

    root: Path
    path: Path
    module_name: str
    class_defs: dict[str, PythonClassDef]
    unique_name_to_key: dict[str, str]
    usage_by_key: dict[str, PythonClassUsage]


@dataclass(frozen=True)
class PythonClassShape:
    """Precomputed Python class metrics used by class rules."""

    direct_methods: list[ast.FunctionDef | ast.AsyncFunctionDef]
    public_methods: list[ast.FunctionDef | ast.AsyncFunctionDef]
    attrs: set[str]


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
    add_target_arguments(parser, default_language)
    add_report_arguments(parser)
    add_dependency_context_arguments(parser)
    add_threshold_arguments(parser)
    return parser


def add_target_arguments(parser: argparse.ArgumentParser, default_language: str) -> None:
    """Add source selection and scoring arguments."""
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


def add_report_arguments(parser: argparse.ArgumentParser) -> None:
    """Add output formatting arguments."""
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


def add_dependency_context_arguments(parser: argparse.ArgumentParser) -> None:
    """Add baseline and dependency-source context arguments."""
    parser.add_argument(
        "--baseline-ref",
        default="",
        help=(
            "Only report findings absent from this git ref. Intended for changed-file hooks "
            "that should block new OOP risks without re-blocking existing debt."
        ),
    )
    parser.add_argument(
        "--usage-root",
        "--dependency-root",
        action="append",
        dest="usage_roots",
        default=[],
        help=(
            "Additional Python or C++ source root to include in class dependency-source "
            "analysis without emitting findings for that root. Repeat for downstream "
            "or sibling modules."
        ),
    )
    parser.add_argument(
        "--dependency-module",
        action="append",
        dest="dependency_modules",
        default=[],
        help=(
            "Importable Python module or package to include in Python class dependency-source "
            "analysis without emitting findings for that module. Repeat for multiple modules."
        ),
    )


def add_threshold_arguments(parser: argparse.ArgumentParser) -> None:
    """Add analyzer threshold arguments."""
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


def source_loc(text: str) -> int:
    """Count nonblank noncomment-ish source lines for normalized metrics."""
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", "/*", "*")):
            continue
        count += 1
    return count


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
    if is_python_ast_visitor_class(node):
        return [
            item
            for item in direct_method_nodes(node)
            if not item.name.startswith("_") and not item.name.startswith("visit_")
        ]
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


def class_field_annotation_names(node: ast.ClassDef) -> set[str]:
    """Collect typed fields declared directly in a class body."""
    names: set[str] = set()
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            names.add(item.target.id)
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


def is_protocol_class(node: ast.ClassDef) -> bool:
    """Return true for classes whose primary responsibility is a typing Protocol."""
    return any(base_class_name(base) in {"Protocol", "typing.Protocol"} for base in node.bases)


def is_python_ast_visitor_class(node: ast.ClassDef) -> bool:
    """Return true for Python AST visitor hook classes."""
    return any(base_class_name(base) in {"NodeVisitor", "ast.NodeVisitor"} for base in node.bases)


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


def analyze_python_file(
    root: Path,
    path: Path,
    thresholds: Thresholds,
    usage_index: PythonUsageIndex,
) -> list[Finding]:
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
            analyze_python_class(context, node, findings, usage_index)
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


def python_module_name(
    root: Path,
    path: Path,
    source_roots: Sequence[Path] = (),
) -> str:
    """Return a dotted module name for a Python file below the analysis root."""
    resolved = path.resolve()
    candidate_roots = sorted(
        {root.resolve(), *(source_root.resolve() for source_root in source_roots)},
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for source_root in candidate_roots:
        try:
            relative = resolved.relative_to(source_root).with_suffix("")
        except ValueError:
            continue
        parts = list(relative.parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)
    try:
        relative = resolved.relative_to(root.resolve()).with_suffix("")
    except ValueError:
        relative = resolved.with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def build_python_usage_index(
    root: Path,
    source_set: PythonUsageSourceSet,
) -> PythonUsageIndex:
    """Build project-level class definitions and dependency-source usage facts."""
    python_files = [path for path in source_set.files if path.suffix in PYTHON_SUFFIXES]
    parsed: dict[Path, ast.Module] = {}
    module_names: dict[Path, str] = {}
    class_defs: dict[str, PythonClassDef] = {}
    simple_to_keys: dict[str, list[str]] = {}
    for path in python_files:
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        resolved = path.resolve()
        module = python_module_name(root, resolved, source_set.source_roots)
        parsed[resolved] = tree
        module_names[resolved] = module
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            key = f"{module}.{node.name}"
            class_defs[key] = PythonClassDef(key=key, module=module, name=node.name, path=resolved)
            simple_to_keys.setdefault(node.name, []).append(key)
    unique_name_to_key = {
        name: keys[0] for name, keys in simple_to_keys.items() if len(keys) == 1
    }
    usage_by_key = {key: PythonClassUsage() for key in class_defs}
    for path, tree in parsed.items():
        build_context = PythonUsageBuildContext(
            root=root,
            path=path,
            module_name=module_names[path],
            class_defs=class_defs,
            unique_name_to_key=unique_name_to_key,
            usage_by_key=usage_by_key,
        )
        collect_python_class_usage(
            build_context,
            tree,
        )
    return PythonUsageIndex(
        class_defs=class_defs,
        usage_by_key=usage_by_key,
        unique_name_to_key=unique_name_to_key,
        module_names=module_names,
    )


def python_usage_source_files(
    root: Path,
    selected_files: list[Path],
    exclude_patterns: Sequence[str],
    usage_roots: Sequence[str] = (),
    dependency_modules: Sequence[str] = (),
) -> PythonUsageSourceSet:
    """Return Python files used to resolve dependency-source class usage."""
    source_roots: set[Path] = {root.resolve()}
    selected_python_files = [path.resolve() for path in selected_files if path.suffix in PYTHON_SUFFIXES]
    root_python_files = iter_directory_sources(
        root,
        root,
        list(exclude_patterns),
        "python",
    )
    usage_files: set[Path] = set(selected_python_files) | set(root_python_files)
    for usage_root in usage_roots:
        extra_sources = dependency_root_source_set(root, usage_root, exclude_patterns)
        source_roots.update(extra_sources.source_roots)
        usage_files.update(extra_sources.files)
    for module_name in dependency_modules:
        module_sources = dependency_module_source_set(module_name, exclude_patterns)
        source_roots.update(module_sources.source_roots)
        usage_files.update(module_sources.files)
    return PythonUsageSourceSet(
        files=sorted(usage_files),
        source_roots=tuple(sorted(source_roots, key=str)),
    )


def dependency_root_source_set(
    root: Path,
    raw_usage_root: str,
    exclude_patterns: Sequence[str],
) -> PythonUsageSourceSet:
    """Return Python source files below one additional usage root."""
    usage_root = Path(raw_usage_root)
    if not usage_root.is_absolute():
        usage_root = root / usage_root
    resolved = usage_root.resolve()
    if resolved.is_file():
        if not visible_source_path(resolved.parent, resolved, list(exclude_patterns), "python"):
            return PythonUsageSourceSet(files=[], source_roots=())
        return PythonUsageSourceSet(files=[resolved], source_roots=(resolved.parent,))
    if not resolved.is_dir():
        return PythonUsageSourceSet(files=[], source_roots=())
    return PythonUsageSourceSet(
        files=iter_directory_sources(resolved, resolved, list(exclude_patterns), "python"),
        source_roots=(resolved,),
    )


def dependency_module_source_set(
    module_name: str,
    exclude_patterns: Sequence[str],
) -> PythonUsageSourceSet:
    """Return Python source files for one importable module or package."""
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return PythonUsageSourceSet(files=[], source_roots=())
    if spec.submodule_search_locations:
        package_dirs = [Path(location).resolve() for location in spec.submodule_search_locations]
        files: set[Path] = set()
        source_roots: set[Path] = set()
        for package_dir in package_dirs:
            source_roots.add(dependency_package_source_root(package_dir, module_name))
            files.update(iter_directory_sources(package_dir, package_dir, list(exclude_patterns), "python"))
        return PythonUsageSourceSet(
            files=sorted(files),
            source_roots=tuple(sorted(source_roots, key=str)),
        )
    if spec.origin is None:
        return PythonUsageSourceSet(files=[], source_roots=())
    module_path = Path(spec.origin).resolve()
    if module_path.suffix not in PYTHON_SUFFIXES or not module_path.is_file():
        return PythonUsageSourceSet(files=[], source_roots=())
    source_root = dependency_module_source_root(module_path, module_name)
    if not visible_source_path(source_root, module_path, list(exclude_patterns), "python"):
        return PythonUsageSourceSet(files=[], source_roots=())
    return PythonUsageSourceSet(files=[module_path], source_roots=(source_root,))


def dependency_package_source_root(package_dir: Path, module_name: str) -> Path:
    """Return the source root that gives a package its importable module name."""
    source_root = package_dir.resolve()
    for _ in module_name.split("."):
        source_root = source_root.parent
    return source_root


def dependency_module_source_root(module_path: Path, module_name: str) -> Path:
    """Return the source root that gives a module file its importable module name."""
    source_root = module_path.resolve().parent
    for _ in module_name.split(".")[:-1]:
        source_root = source_root.parent
    return source_root


def empty_python_usage_index() -> PythonUsageIndex:
    """Return an empty usage index for runs without Python source files."""
    return PythonUsageIndex(
        class_defs={},
        usage_by_key={},
        unique_name_to_key={},
        module_names={},
    )


def cpp_class_key(root: Path, path: Path, class_name: str) -> str:
    """Return a stable key for one C++ class definition."""
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative = path.resolve().as_posix()
    return f"{relative}::{class_name}"


def build_cpp_usage_index(
    root: Path,
    source_set: CppUsageSourceSet,
) -> CppUsageIndex:
    """Build project-level C++ class definitions and dependency-source usage facts."""
    cpp_files = [path for path in source_set.files if path.suffix in CPP_SUFFIXES]
    analysis_by_path: dict[Path, str] = {}
    class_defs: dict[str, CppClassDef] = {}
    simple_to_keys: dict[str, list[str]] = {}
    path_name_to_key: dict[tuple[Path, str], str] = {}
    for path in cpp_files:
        resolved = path.resolve()
        text = path.read_text(encoding="utf-8", errors="ignore")
        analysis_text = cpp_text_without_comments_or_literals(text)
        analysis_by_path[resolved] = analysis_text
        for match in CLASS_RE.finditer(analysis_text):
            name = match.group("name")
            key = cpp_class_key(root, resolved, name)
            class_defs[key] = CppClassDef(key=key, name=name, path=resolved)
            simple_to_keys.setdefault(name, []).append(key)
            path_name_to_key[(resolved, name)] = key
    unique_name_to_key = {
        name: keys[0] for name, keys in simple_to_keys.items() if len(keys) == 1
    }
    usage_by_key = {key: CppClassUsage() for key in class_defs}
    resolver = CppClassResolver(
        class_defs=class_defs,
        unique_name_to_key=unique_name_to_key,
    )
    for path, analysis_text in analysis_by_path.items():
        collect_cpp_class_usage(root, path, analysis_text, resolver, usage_by_key)
    return CppUsageIndex(
        class_defs=class_defs,
        usage_by_key=usage_by_key,
        unique_name_to_key=unique_name_to_key,
        path_name_to_key=path_name_to_key,
    )


def cpp_usage_source_files(
    root: Path,
    selected_files: list[Path],
    exclude_patterns: Sequence[str],
    usage_roots: Sequence[str] = (),
) -> CppUsageSourceSet:
    """Return C++ files used to resolve dependency-source class usage."""
    selected_cpp_files = [path.resolve() for path in selected_files if path.suffix in CPP_SUFFIXES]
    root_cpp_files = iter_directory_sources(
        root,
        root,
        list(exclude_patterns),
        "cpp",
    )
    usage_files: set[Path] = set(selected_cpp_files) | set(root_cpp_files)
    for usage_root in usage_roots:
        usage_files.update(cpp_dependency_root_source_files(root, usage_root, exclude_patterns))
    return CppUsageSourceSet(files=sorted(usage_files))


def cpp_dependency_root_source_files(
    root: Path,
    raw_usage_root: str,
    exclude_patterns: Sequence[str],
) -> list[Path]:
    """Return C++ source files below one additional usage root."""
    usage_root = Path(raw_usage_root)
    if not usage_root.is_absolute():
        usage_root = root / usage_root
    resolved = usage_root.resolve()
    if resolved.is_file():
        if not visible_source_path(resolved.parent, resolved, list(exclude_patterns), "cpp"):
            return []
        return [resolved]
    if not resolved.is_dir():
        return []
    return iter_directory_sources(resolved, resolved, list(exclude_patterns), "cpp")


def empty_cpp_usage_index() -> CppUsageIndex:
    """Return an empty usage index for runs without C++ source files."""
    return CppUsageIndex(
        class_defs={},
        usage_by_key={},
        unique_name_to_key={},
        path_name_to_key={},
    )


@dataclass(frozen=True)
class CppClassResolver:
    """Resolve simple C++ type references to known project classes."""

    class_defs: dict[str, CppClassDef]
    unique_name_to_key: dict[str, str]

    def resolve_name(self, name: str) -> str | None:
        """Resolve a simple or qualified C++ type name to a known class key."""
        if name in self.unique_name_to_key:
            return self.unique_name_to_key[name]
        tail = name.rsplit("::", 1)[-1]
        return self.unique_name_to_key.get(tail)


CPP_TYPE_KEYWORDS = {
    "auto",
    "bool",
    "char",
    "class",
    "const",
    "constexpr",
    "double",
    "enum",
    "extern",
    "float",
    "inline",
    "int",
    "long",
    "mutable",
    "noexcept",
    "private",
    "protected",
    "public",
    "short",
    "signed",
    "static",
    "struct",
    "typename",
    "unsigned",
    "virtual",
    "void",
    "volatile",
}


def collect_cpp_class_usage(
    root: Path,
    path: Path,
    analysis_text: str,
    resolver: CppClassResolver,
    usage_by_key: dict[str, CppClassUsage],
) -> None:
    """Collect C++ class usage from one source file."""
    collect_cpp_inheritance_usage(root, path, analysis_text, resolver, usage_by_key)
    collect_cpp_signature_usage(root, path, analysis_text, resolver, usage_by_key)
    collect_cpp_constructor_usage(root, path, analysis_text, resolver, usage_by_key)


def collect_cpp_inheritance_usage(
    root: Path,
    path: Path,
    analysis_text: str,
    resolver: CppClassResolver,
    usage_by_key: dict[str, CppClassUsage],
) -> None:
    """Collect C++ base-class type-boundary observations."""
    for match in CLASS_RE.finditer(analysis_text):
        bases = match.group("bases") or ""
        for type_name in cpp_type_names_from_type_text(bases):
            key = resolver.resolve_name(type_name)
            if key is not None:
                record_cpp_class_ref(root, path, usage_by_key, key, "inheritance_refs")


def collect_cpp_signature_usage(
    root: Path,
    path: Path,
    analysis_text: str,
    resolver: CppClassResolver,
    usage_by_key: dict[str, CppClassUsage],
) -> None:
    """Collect C++ return-type and parameter type-boundary observations."""
    for match in FUNCTION_RE.finditer(analysis_text):
        for type_name in cpp_type_names_from_type_text(match.group("prefix")):
            key = resolver.resolve_name(type_name)
            if key is not None:
                record_cpp_class_ref(root, path, usage_by_key, key, "type_refs")
        for parameter in cpp_split_top_level(match.group("params")):
            for type_name in cpp_type_names_from_declaration(parameter):
                key = resolver.resolve_name(type_name)
                if key is not None:
                    record_cpp_class_ref(root, path, usage_by_key, key, "type_refs")


def collect_cpp_constructor_usage(
    root: Path,
    path: Path,
    analysis_text: str,
    resolver: CppClassResolver,
    usage_by_key: dict[str, CppClassUsage],
) -> None:
    """Collect common C++ construction observations."""
    for class_def in resolver.class_defs.values():
        constructor_count = cpp_constructor_usage_count(analysis_text, class_def.name)
        if constructor_count <= 0:
            continue
        usage = usage_by_key[class_def.key]
        usage.constructor_calls += constructor_count
        usage.mark_source(root, path)


def record_cpp_class_ref(
    root: Path,
    path: Path,
    usage_by_key: dict[str, CppClassUsage],
    key: str,
    attr: str,
) -> None:
    """Record one C++ class usage observation."""
    usage = usage_by_key.get(key)
    if usage is None:
        return
    setattr(usage, attr, getattr(usage, attr) + 1)
    usage.mark_source(root, path)


def cpp_type_names_from_type_text(text: str) -> list[str]:
    """Return candidate project class names from a C++ type expression."""
    names: list[str] = []
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_:]*", text):
        tail = token.rsplit("::", 1)[-1]
        if tail not in CPP_TYPE_KEYWORDS:
            names.append(token)
    return names


def cpp_type_names_from_declaration(declaration: str) -> list[str]:
    """Return candidate project class names from a parameter declaration."""
    before_default = declaration.split("=", 1)[0]
    names = cpp_type_names_from_type_text(before_default)
    if len(names) >= 2:
        return names[:-1]
    return names


def cpp_constructor_usage_count(analysis_text: str, class_name: str) -> int:
    """Count common C++ construction expressions for one class name."""
    escaped = re.escape(class_name)
    count = 0
    expression_pattern = re.compile(rf"\b{escaped}\s*(?:\(|\{{)")
    declaration_pattern = re.compile(
        rf"\b{escaped}\s+[a-z_][A-Za-z0-9_]*\s*(?:[;={{(])"
    )
    for match in expression_pattern.finditer(analysis_text):
        prefix = analysis_text[
            max(0, match.start() - CPP_CONSTRUCTOR_PREFIX_LOOKBACK_CHARS) : match.start()
        ]
        if re.search(r"(?:class|struct)\s+$", prefix):
            continue
        count += 1
    count += sum(1 for _ in declaration_pattern.finditer(analysis_text))
    return count


def collect_python_class_usage(
    build_context: PythonUsageBuildContext,
    tree: ast.Module,
) -> None:
    """Collect class dependency-source observations from one Python module."""
    imports = python_import_aliases(
        tree,
        build_context.class_defs,
        build_context.module_name,
    )
    resolver = PythonClassResolver(
        class_defs=build_context.class_defs,
        unique_name_to_key=build_context.unique_name_to_key,
        module_name=build_context.module_name,
        imports=imports,
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                key = resolver.resolve_expr(base)
                if key is not None:
                    record_python_class_ref(build_context, key, "inheritance_refs")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            collect_python_function_class_usage(build_context, node, resolver)
            continue
        if isinstance(node, ast.AnnAssign):
            collect_python_annotation_refs(build_context, node.annotation, resolver)


@dataclass(frozen=True)
class PythonClassResolver:
    """Resolve local import and simple-name references to known project classes."""

    class_defs: dict[str, PythonClassDef]
    unique_name_to_key: dict[str, str]
    module_name: str
    imports: dict[str, str]

    def resolve_expr(self, expression: ast.AST) -> str | None:
        """Resolve an AST expression to a known class key when deterministic."""
        if isinstance(expression, ast.Name):
            return self.resolve_name(expression.id)
        if isinstance(expression, ast.Attribute):
            dotted = dotted_name(expression)
            if dotted is None:
                return None
            return self.resolve_dotted_name(dotted)
        if isinstance(expression, ast.Subscript):
            return self.resolve_expr(expression.value)
        return None

    def resolve_name(self, name: str) -> str | None:
        """Resolve a simple name to a known class key."""
        imported = self.imports.get(name)
        if imported in self.class_defs:
            return imported
        local_key = f"{self.module_name}.{name}"
        if local_key in self.class_defs:
            return local_key
        return self.unique_name_to_key.get(name)

    def resolve_dotted_name(self, dotted: str) -> str | None:
        """Resolve a dotted reference through import aliases and known modules."""
        if dotted in self.class_defs:
            return dotted
        head, _, tail = dotted.partition(".")
        imported = self.imports.get(head)
        if imported is None:
            return None
        candidate = f"{imported}.{tail}" if tail else imported
        return candidate if candidate in self.class_defs else None


def dotted_name(expression: ast.AST) -> str | None:
    """Return a dotted name for a Name/Attribute expression."""
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        prefix = dotted_name(expression.value)
        return f"{prefix}.{expression.attr}" if prefix else expression.attr
    return None


def python_import_aliases(
    tree: ast.Module,
    class_defs: dict[str, PythonClassDef],
    module_name: str,
) -> dict[str, str]:
    """Return import aliases that can resolve to project classes or modules."""
    modules = project_module_names(class_defs)
    aliases: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            aliases.update(import_from_aliases(node, class_defs, modules, module_name))
            continue
        if isinstance(node, ast.Import):
            aliases.update(import_aliases(node, modules))
    return aliases


def project_module_names(class_defs: dict[str, PythonClassDef]) -> set[str]:
    """Return dotted module names that define project classes."""
    return {definition.module for definition in class_defs.values()}


def import_from_aliases(
    node: ast.ImportFrom,
    class_defs: dict[str, PythonClassDef],
    modules: set[str],
    module_name: str,
) -> dict[str, str]:
    """Return aliases created by one from-import statement."""
    import_module = resolved_import_from_module(node, module_name)
    aliases: dict[str, str] = {}
    for alias in node.names:
        imported_name = f"{import_module}.{alias.name}" if import_module else alias.name
        if imported_name in class_defs or imported_name in modules:
            aliases[alias.asname or alias.name] = imported_name
    return aliases


def resolved_import_from_module(node: ast.ImportFrom, module_name: str) -> str:
    """Resolve absolute and relative from-import module names."""
    if node.level == 0:
        return node.module or ""
    package_parts = module_name.split(".")[:-1]
    prefix_length = max(len(package_parts) - node.level + 1, 0)
    prefix = ".".join(package_parts[:prefix_length])
    if node.module is None:
        return prefix
    return f"{prefix}.{node.module}" if prefix else node.module


def import_aliases(node: ast.Import, modules: set[str]) -> dict[str, str]:
    """Return aliases created by one import statement."""
    aliases: dict[str, str] = {}
    for alias in node.names:
        if alias.name in modules:
            aliases[alias.asname or alias.name.split(".", 1)[0]] = alias.name
    return aliases


def collect_python_function_class_usage(
    build_context: PythonUsageBuildContext,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    resolver: PythonClassResolver,
) -> None:
    """Collect class usage inside one function or method."""
    variable_classes: dict[str, str] = {}
    for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
        if arg.annotation is not None:
            collect_python_annotation_refs(build_context, arg.annotation, resolver)
    if node.returns is not None:
        collect_python_annotation_refs(build_context, node.returns, resolver)
    for child in ast.walk(node):
        if isinstance(child, (ast.Assign, ast.AnnAssign)):
            collect_python_assignment_class_usage(
                child, resolver, variable_classes
            )
            continue
        if isinstance(child, ast.Call):
            collect_python_call_class_usage(
                build_context,
                child,
                resolver,
                variable_classes,
            )
        if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
            key = variable_classes.get(child.value.id)
            if key is not None:
                build_context.usage_by_key[key].instance_attribute_refs += 1
                build_context.usage_by_key[key].mark_source(
                    build_context.root,
                    build_context.path,
                )


def collect_python_assignment_class_usage(
    node: ast.Assign | ast.AnnAssign,
    resolver: PythonClassResolver,
    variable_classes: dict[str, str],
) -> None:
    """Collect class construction facts from one assignment statement."""
    value = node.value
    if not isinstance(value, ast.Call):
        return
    key = resolver.resolve_expr(value.func)
    if key is None:
        return
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    for target in targets:
        if isinstance(target, ast.Name):
            variable_classes[target.id] = key


def collect_python_call_class_usage(
    build_context: PythonUsageBuildContext,
    call: ast.Call,
    resolver: PythonClassResolver,
    variable_classes: dict[str, str],
) -> None:
    """Collect class references from one call expression."""
    call_name = dotted_name(call.func)
    if call_name in {"isinstance", "issubclass"} and len(call.args) >= 2:
        for key in class_refs_in_annotation(call.args[1], resolver):
            record_python_class_ref(build_context, key, "isinstance_refs")
        return
    key = resolver.resolve_expr(call.func)
    if key is not None:
        record_python_class_ref(build_context, key, "constructor_calls")
    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
        instance_key = variable_classes.get(call.func.value.id)
        if instance_key in build_context.usage_by_key:
            build_context.usage_by_key[instance_key].instance_method_calls += 1
            build_context.usage_by_key[instance_key].mark_source(
                build_context.root,
                build_context.path,
            )


def collect_python_annotation_refs(
    build_context: PythonUsageBuildContext,
    annotation: ast.AST,
    resolver: PythonClassResolver,
) -> None:
    """Collect class references from one annotation expression."""
    for key in class_refs_in_annotation(annotation, resolver):
        record_python_class_ref(build_context, key, "annotation_refs")


def class_refs_in_annotation(annotation: ast.AST, resolver: PythonClassResolver) -> set[str]:
    """Return known project class references contained in an annotation-like expression."""
    refs: set[str] = set()
    resolved = resolver.resolve_expr(annotation)
    if resolved is not None:
        refs.add(resolved)
    for child in ast.iter_child_nodes(annotation):
        refs.update(class_refs_in_annotation(child, resolver))
    return refs


def record_python_class_ref(
    build_context: PythonUsageBuildContext,
    key: str,
    field: str,
) -> None:
    """Increment one usage field for a known class key."""
    if key not in build_context.usage_by_key:
        return
    usage = build_context.usage_by_key[key]
    setattr(usage, field, cast(int, getattr(usage, field)) + 1)
    usage.mark_source(build_context.root, build_context.path)


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
    usage_index: PythonUsageIndex,
) -> None:
    """Record class-level readability findings for one Python class."""
    shape = PythonClassShape(
        direct_methods=direct_method_nodes(node),
        public_methods=public_method_nodes(node),
        attrs=self_attribute_names(node) | class_field_annotation_names(node),
    )
    add_python_class_shape_findings(context, node, shape.public_methods, shape.attrs, findings)
    add_python_class_contract_findings(
        context,
        node,
        shape,
        findings,
        usage_index,
    )
    add_python_method_cohesion_findings(context, node, shape.public_methods, findings)


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
    """Record public API and state findings."""
    thresholds = context.thresholds
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
            "review-caller-roles-before-refining-api",
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
            "review-stable-value-object-or-state-owner-boundary",
        )


def add_python_class_contract_findings(
    context: SourceContext,
    node: ast.ClassDef,
    shape: PythonClassShape,
    findings: list[Finding],
    usage_index: PythonUsageIndex,
) -> None:
    """Record findings for class necessity and contract shape."""
    if is_test_case_class(context.path, node):
        return
    static_methods = static_method_nodes(node)
    if static_methods and len(static_methods) == len(shape.direct_methods) and not is_algorithm_contract_class(node):
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
        len(shape.public_methods) <= 1
        and not shape.attrs
        and not is_dataclass(node)
        and not is_algorithm_contract_class(node)
        and not is_protocol_class(node)
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
            len(shape.public_methods),
            "state-or-contract",
            "confirm-class-is-needed-or-use-function-value-object",
        )
    if (
        len(shape.direct_methods) == 1
        and shape.direct_methods[0].name == "__call__"
        and not shape.attrs
        and not node.bases
    ):
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
    add_python_dependency_source_class_findings(
        context,
        node,
        shape,
        findings,
        usage_index,
    )


def add_python_dependency_source_class_findings(
    context: SourceContext,
    node: ast.ClassDef,
    shape: PythonClassShape,
    findings: list[Finding],
    usage_index: PythonUsageIndex,
) -> None:
    """Record class redundancy that depends on project-level use sites."""
    if not is_redundant_class_shape(context.path, node, shape):
        return
    usage = usage_index.usage_for(context.path, node.name)
    if usage is None or usage.constructor_calls == 0 or usage.boundary_refs() > 0:
        return
    add_finding(
        findings,
        context.root,
        context.path,
        node.lineno,
        context.language,
        "warn",
        "redundant_class_boundary",
        node.name,
        usage.usage_summary(),
        "type-boundary-or-owned-lifecycle",
        "replace-with-function-or-document-class-lifecycle-contract",
    )


def is_redundant_class_shape(
    path: Path,
    node: ast.ClassDef,
    shape: PythonClassShape,
) -> bool:
    """Return true for classes whose shape needs dependency-source confirmation."""
    if (
        is_test_case_class(path, node)
        or is_dataclass(node)
        or is_algorithm_contract_class(node)
        or is_protocol_class(node)
        or node.bases
    ):
        return False
    if len(shape.direct_methods) == 1 and shape.direct_methods[0].name == "__call__" and not shape.attrs:
        return True
    return len(shape.public_methods) <= 1 and len(shape.attrs) <= 1


def add_python_method_cohesion_findings(
    context: SourceContext,
    node: ast.ClassDef,
    public_methods: list[ast.FunctionDef | ast.AsyncFunctionDef],
    findings: list[Finding],
) -> None:
    """Record method-level class cohesion findings."""
    if is_test_case_class(context.path, node) or is_protocol_class(node):
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
    """Record parameter and control-flow findings."""
    thresholds = context.thresholds
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
            "review-stable-input-domain-shape",
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
            "review-branch-meaning-before-extraction",
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
        "review-helper-locality-or-existing-domain-service",
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


def matching_brace(text: str, open_index: int) -> int | None:
    """Return matching brace index, or None when unmatched."""
    if open_index < 0:
        return None
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


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


def cpp_brace_delta(line: str) -> int:
    """Return the net brace nesting change for one C++ source line."""
    return line.count("{") - line.count("}")


def cpp_skippable_public_line(line: str) -> bool:
    """Return whether a public-section line cannot declare a member."""
    return not line or line.startswith("//") or line.startswith("#")


def cpp_member_candidate_start(line: str) -> bool:
    """Return whether a top-level line can start a C++ member declaration."""
    if line.startswith(("using ", "typedef ")):
        return False
    return "(" in line or line.endswith(";")


def cpp_member_candidate_text(pending: str, line: str) -> str:
    """Return the current accumulated top-level member candidate."""
    if pending:
        return f"{pending} {line}"
    if cpp_member_candidate_start(line):
        return line
    return ""


def cpp_member_candidate_complete(candidate: str, line: str) -> bool:
    """Return whether the current line terminates a member candidate."""
    return bool(candidate) and (";" in line or "{" in line)


def cpp_member_candidate_is_member(candidate: str) -> bool:
    """Return whether an accumulated candidate looks like a field or method."""
    return ("(" in candidate and ")" in candidate) or candidate.endswith(";")


def cpp_member_candidates(public_body: str) -> list[str]:
    """Return rough top-level public member declarations."""
    members: list[str] = []
    pending = ""
    depth = 0
    for line in public_body.splitlines():
        stripped = line.strip()
        if cpp_skippable_public_line(stripped):
            depth = max(0, depth + cpp_brace_delta(stripped))
            continue
        if depth == 0:
            pending = cpp_member_candidate_text(pending, stripped)
            if cpp_member_candidate_complete(pending, stripped):
                if cpp_member_candidate_is_member(pending):
                    members.append(pending)
                pending = ""
        depth = max(0, depth + cpp_brace_delta(stripped))
    return members


def cpp_scalar_operator_value_object(name: str) -> bool:
    """Return true for compact numeric scalar wrappers with operator-heavy APIs."""
    return CPP_SCALAR_OPERATOR_VALUE_OBJECT_RE.fullmatch(name) is not None


def cpp_aggregate_value_object_name(name: str) -> bool:
    """Return true for C++ aggregate names that carry schema or DSL values."""
    return name in CPP_AGGREGATE_VALUE_OBJECT_NAMES or name.endswith(
        CPP_AGGREGATE_VALUE_OBJECT_SUFFIXES
    )


def cpp_preceding_lines(text: str, start: int, line_count: int) -> str:
    """Return a bounded source window immediately before an index."""
    return "\n".join(text[:start].splitlines()[-line_count:])


def cpp_abi_boundary_function(
    analysis_text: str,
    start: int,
    prefix: str,
    name: str,
) -> bool:
    """Return true for C++ functions whose signature is a compiler/runtime ABI."""
    if name.startswith(CPP_ABI_FUNCTION_PREFIXES):
        return True
    if "extern" in prefix and name.startswith(CPP_ABI_FUNCTION_PREFIXES):
        return True
    preceding = cpp_preceding_lines(analysis_text, start, CPP_ABI_MARKER_LOOKBACK_LINES)
    return any(marker in preceding for marker in CPP_ABI_MARKER_MACROS)


def cpp_parameter_count(params: str) -> int:
    """Count C++ function parameters approximately."""
    return len(cpp_split_top_level(params))


def cpp_split_top_level(text: str) -> list[str]:
    """Split a C++ comma list while preserving simple template arguments."""
    text = text.strip()
    if not text or text == "void":
        return []
    parts: list[str] = []
    start = 0
    depths = (0, 0, 0, 0)
    for index, char in enumerate(text):
        if char == "," and cpp_at_top_level(depths):
            parts.append(text[start:index].strip())
            start = index + 1
            continue
        depths = cpp_delimiter_depths_after(char, depths)
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def cpp_at_top_level(depths: tuple[int, int, int, int]) -> bool:
    """Return true when no C++ delimiter depth is currently open."""
    return not any(depths)


def cpp_delimiter_depths_after(
    char: str,
    depths: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """Update delimiter depths after consuming one C++ character."""
    open_index = "<([{".find(char)
    if open_index != -1:
        return cpp_depth_tuple_with_delta(depths, open_index, 1)
    close_index = ">)]}".find(char)
    if close_index != -1:
        return cpp_depth_tuple_with_delta(depths, close_index, -1)
    return depths


def cpp_depth_tuple_with_delta(
    depths: tuple[int, int, int, int],
    index: int,
    delta: int,
) -> tuple[int, int, int, int]:
    """Return delimiter depths after changing one depth slot."""
    items = list(depths)
    items[index] = max(0, items[index] + delta)
    return cast(tuple[int, int, int, int], tuple(items))


def cpp_parameter_names(params: str) -> list[str]:
    """Return approximate C++ parameter names for redundancy checks."""
    names: list[str] = []
    for param in cpp_split_top_level(params):
        name = cpp_parameter_name(param)
        if name is not None:
            names.append(name)
    return names


def cpp_parameter_name(param: str) -> str | None:
    """Return the declared parameter name from one C++ parameter."""
    normalized = param.split("=", 1)[0].strip()
    normalized = re.sub(r"\s*\[[^\]]*\]\s*$", "", normalized).strip()
    identifiers = list(re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", normalized))
    if len(identifiers) < 2:
        return None
    last = identifiers[-1]
    if normalized[last.end() :].strip():
        return None
    prefix = normalized[: last.start()]
    if prefix.rstrip().endswith("::"):
        return None
    if not re.search(r"[\s*&>]", prefix):
        return None
    return last.group(0)


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


def cpp_meaningful_statements(body: str) -> list[str]:
    """Return nonblank C++ body lines after comments and literals are masked."""
    return [
        line.strip()
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def cpp_single_return_statement(body: str) -> str | None:
    """Return the single return statement for a trivial C++ function."""
    statements = cpp_meaningful_statements(body)
    if len(statements) != 1 or not statements[0].startswith("return "):
        return None
    return statements[0]


def cpp_return_expression(statement: str) -> str:
    """Return the expression inside a C++ return statement."""
    expression = statement.removeprefix("return ").strip()
    if expression.endswith(";"):
        expression = expression[:-1].strip()
    while expression.startswith("(") and expression.endswith(")"):
        expression = expression[1:-1].strip()
    return expression


def cpp_identity_parameter(params: str, body: str) -> str | None:
    """Return parameter name when a C++ function only returns that parameter."""
    statement = cpp_single_return_statement(body)
    if statement is None:
        return None
    expression = cpp_return_expression(statement)
    parameter_names = set(cpp_parameter_names(params))
    return expression if expression in parameter_names else None


def cpp_forwarded_argument_name(argument: str, parameter_names: set[str]) -> str | None:
    """Return parameter name when one C++ call argument forwards it unchanged."""
    argument = argument.strip()
    if argument in parameter_names:
        return argument
    move_match = re.fullmatch(r"(?:std::)?move\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", argument)
    if move_match and move_match.group(1) in parameter_names:
        return move_match.group(1)
    forward_match = re.fullmatch(
        r"(?:std::)?forward\s*<[^>]+>\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
        argument,
    )
    if forward_match and forward_match.group(1) in parameter_names:
        return forward_match.group(1)
    return None


def cpp_passthrough_call(params: str, body: str) -> tuple[str, int] | None:
    """Return callee and forwarded parameter count for a C++ pass-through wrapper."""
    parameter_names = cpp_parameter_names(params)
    if not parameter_names:
        return None
    statement = cpp_single_return_statement(body)
    if statement is None:
        return None
    call_match = re.fullmatch(r"return\s+(.+?)\((.*)\)\s*;", statement)
    if call_match is None:
        return None
    callee = call_match.group(1).strip()
    if re.search(r"\s", callee) or callee.startswith(
        ("static_cast", "dynamic_cast", "reinterpret_cast", "const_cast")
    ):
        return None
    parameter_set = set(parameter_names)
    arguments = cpp_split_top_level(call_match.group(2))
    forwarded = [
        forwarded_name
        for argument in arguments
        if (forwarded_name := cpp_forwarded_argument_name(argument, parameter_set)) is not None
    ]
    if len(forwarded) != len(parameter_names) or set(forwarded) != parameter_set:
        return None
    return callee, len(forwarded)


def cpp_returns_value(body: str) -> bool:
    """Return true when a C++ body contains a value-return statement."""
    return bool(re.search(r"\breturn\s+[^;\s][^;]*;", body))


def cpp_external_effect_call(body: str) -> bool:
    """Return true when a C++ body appears to cross an external effect boundary."""
    patterns = (
        r"\bstd::(?:cout|cerr|clog)\s*<<",
        r"\b(?:printf|fprintf|system|popen|remove|rename)\s*\(",
        r"\b(?:std::print|fmt::print)\s*\(",
        r"\.\s*(?:open|close|flush|write)\s*\(",
        r"\bstd::filesystem::(?:copy|copy_file|create_directories|remove|remove_all|rename)\s*\(",
        r"\bstd::ofstream\b",
        r"\bstd::ifstream\b",
        r"\bstd::fstream\b",
    )
    return any(re.search(pattern, body) for pattern in patterns)


def cpp_parameter_mutation_call(body: str, parameter_names: Sequence[str]) -> bool:
    """Return true when a C++ body mutates a parameter-owned object."""
    method_pattern = "|".join(sorted(CPP_LOCAL_MUTATION_METHODS))
    for name in parameter_names:
        escaped = re.escape(name)
        if re.search(rf"\b{escaped}\s*(?:\.|->)\s*(?:{method_pattern})\s*\(", body):
            return True
        if re.search(rf"\*\s*{escaped}\s*=", body):
            return True
    return False


def cpp_has_side_effect(params: str, body: str) -> bool:
    """Return true when a C++ function likely mixes return values with effects."""
    return cpp_external_effect_call(body) or cpp_parameter_mutation_call(
        body,
        cpp_parameter_names(params),
    )


def cpp_mixed_effect_function(name: str, params: str, body: str) -> bool:
    """Return true when a C++ function returns a value while crossing effects."""
    return cpp_returns_value(body) and cpp_has_side_effect(params, body) and not is_effect_adapter_name(name)


def cpp_trivial_format_function(name: str, body: str) -> str | None:
    """Return a label when a C++ function is only a thin presentation wrapper."""
    if not symbol_has_presentation_name(name):
        return None
    statement = cpp_single_return_statement(body)
    if statement is None:
        return None
    for marker in ("std::to_string", "std::format", "fmt::format"):
        if marker in statement:
            return marker
    return None


def analyze_cpp_file(
    root: Path,
    path: Path,
    thresholds: Thresholds,
    usage_index: CppUsageIndex,
) -> list[Finding]:
    """Analyze one C or C++ source file with lightweight text heuristics."""
    findings: list[Finding] = []
    context = SourceContext(root=root, path=path, language="cpp", thresholds=thresholds)
    text = path.read_text(encoding="utf-8", errors="ignore")
    analysis_text = cpp_text_without_comments_or_literals(text)
    for match in CLASS_RE.finditer(analysis_text):
        analyze_cpp_class(context, analysis_text, match, findings, usage_index)
    for match in FUNCTION_RE.finditer(analysis_text):
        analyze_cpp_function(context, analysis_text, match, findings)
    return findings


@dataclass(frozen=True)
class CppClassShape:
    """Precomputed class metrics used by the C++ analyzer."""

    name: str
    line: int
    public_methods: int
    public_fields: int
    base_count: int
    aggregate_value_object: bool
    scalar_operator_value_object: bool


@dataclass(frozen=True)
class CppFunctionShape:
    """Precomputed function metrics used by the C++ analyzer."""

    name: str
    line: int
    parameters: int
    complexity: int
    null_checks: int
    mixed_effect: bool
    identity_parameter: str | None
    passthrough: tuple[str, int] | None
    trivial_format: str | None
    abi_boundary: bool
    domain_identity_boundary: bool


def analyze_cpp_class(
    context: SourceContext,
    analysis_text: str,
    match: re.Match[str],
    findings: list[Finding],
    usage_index: CppUsageIndex,
) -> None:
    """Record class-level C++ readability findings for one regex match."""
    shape = cpp_class_shape(analysis_text, match)
    if shape is None:
        add_cpp_syntax_error(context, analysis_text, match, findings)
        return
    add_cpp_class_identity_findings(context, shape, findings)
    add_cpp_class_surface_findings(context, shape, findings)
    add_cpp_dependency_source_class_findings(context, shape, findings, usage_index)


def cpp_class_shape(
    analysis_text: str,
    match: re.Match[str],
) -> CppClassShape | None:
    """Return C++ class metrics without recording findings."""
    class_kind = match.group("kind")
    bases = match.group("bases") or ""
    open_index = analysis_text.find("{", match.end() - 1)
    close_index = matching_brace(analysis_text, open_index)
    if close_index is None:
        return None
    body = analysis_text[open_index + 1 : close_index]
    public_body = cpp_public_section(class_kind, body)
    public_members = cpp_member_candidates(public_body)
    public_methods = [item for item in public_members if "(" in item and ")" in item]
    public_fields = [item for item in public_members if item not in public_methods]
    name = match.group("name")
    aggregate_value_object = bool(public_fields) and cpp_aggregate_value_object_name(name)
    return CppClassShape(
        name=name,
        line=line_at(analysis_text, match.start()),
        public_methods=len(public_methods),
        public_fields=len(public_fields),
        base_count=len([part for part in bases.split(",") if part.strip()]),
        aggregate_value_object=aggregate_value_object,
        scalar_operator_value_object=cpp_scalar_operator_value_object(name),
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
    """Record public-surface findings for one C++ class."""
    thresholds = context.thresholds
    if (
        not shape.scalar_operator_value_object
        and shape.public_methods > thresholds.max_public_methods
    ):
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
            "review-caller-roles-before-refining-api",
        )
    if (
        not shape.aggregate_value_object
        and shape.public_fields > thresholds.max_public_fields
    ):
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
    if (
        not shape.aggregate_value_object
        and shape.public_fields
        and shape.public_fields > shape.public_methods
    ):
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


def add_cpp_dependency_source_class_findings(
    context: SourceContext,
    shape: CppClassShape,
    findings: list[Finding],
    usage_index: CppUsageIndex,
) -> None:
    """Record C++ class redundancy that depends on project-level use sites."""
    if not is_redundant_cpp_class_shape(shape):
        return
    usage = usage_index.usage_for(context.path, shape.name)
    if usage is None or usage.constructor_calls == 0 or usage.boundary_refs() > 0:
        return
    add_finding(
        findings,
        context.root,
        context.path,
        shape.line,
        context.language,
        "warn",
        "redundant_class_boundary",
        shape.name,
        usage.usage_summary(),
        "type-boundary-or-owned-lifecycle",
        "replace-with-function-or-document-class-lifecycle-contract",
    )


def is_redundant_cpp_class_shape(shape: CppClassShape) -> bool:
    """Return true for C++ classes whose shape needs dependency-source confirmation."""
    if shape.base_count > 0 or shape.aggregate_value_object or shape.scalar_operator_value_object:
        return False
    return shape.public_methods <= 1 and shape.public_fields <= 1


def analyze_cpp_function(
    context: SourceContext,
    analysis_text: str,
    match: re.Match[str],
    findings: list[Finding],
) -> None:
    """Record function-level C++ readability findings for one regex match."""
    shape = cpp_function_shape(analysis_text, match)
    if shape is None:
        add_cpp_syntax_error(context, analysis_text, match, findings)
        return
    add_cpp_function_shape_findings(context, shape, findings)
    add_cpp_function_type_findings(context, shape, findings)


def cpp_function_shape(
    analysis_text: str,
    match: re.Match[str],
) -> CppFunctionShape | None:
    """Return C++ function metrics without recording findings."""
    name = match.group("name")
    open_index = analysis_text.find("{", match.end() - 1)
    close_index = matching_brace(analysis_text, open_index)
    if close_index is None:
        return None
    body = analysis_text[open_index + 1 : close_index]
    return CppFunctionShape(
        name=name,
        line=line_at(analysis_text, match.start()),
        parameters=cpp_parameter_count(match.group("params")),
        complexity=cpp_cognitive_complexity(body),
        null_checks=cpp_null_runtime_checks(body),
        mixed_effect=cpp_mixed_effect_function(name, match.group("params"), body),
        identity_parameter=cpp_identity_parameter(match.group("params"), body),
        passthrough=cpp_passthrough_call(match.group("params"), body),
        trivial_format=cpp_trivial_format_function(name, body),
        abi_boundary=cpp_abi_boundary_function(
            analysis_text,
            match.start(),
            match.group("prefix"),
            name,
        ),
        domain_identity_boundary=name in CPP_DOMAIN_IDENTITY_FUNCTION_NAMES,
    )


def add_cpp_syntax_error(
    context: SourceContext,
    analysis_text: str,
    match: re.Match[str],
    findings: list[Finding],
) -> None:
    """Record a parseability finding for an unmatched C++ brace body."""
    add_finding(
        findings,
        context.root,
        context.path,
        line_at(analysis_text, match.start()),
        context.language,
        "error",
        "syntax_error",
        match.group("name"),
        "unmatched-brace",
        "parseable-cpp",
        "fix-cpp-brace-structure-before-readability-analysis",
    )


def add_cpp_function_shape_findings(
    context: SourceContext,
    shape: CppFunctionShape,
    findings: list[Finding],
) -> None:
    """Record parameter and control-flow findings for one C++ function."""
    thresholds = context.thresholds
    if shape.parameters > thresholds.max_parameters and not shape.abi_boundary:
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
            "review-stable-input-domain-shape",
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
            "review-branch-meaning-before-extraction",
        )


def add_cpp_function_type_findings(
    context: SourceContext,
    shape: CppFunctionShape,
    findings: list[Finding],
) -> None:
    """Record typed-boundary, effect, and redundancy findings for one C++ function."""
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
    if shape.mixed_effect:
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "warn",
            "mixed_morphism_effect",
            shape.name,
            "return+effect",
            "pure-or-effect-boundary",
            "separate-value-transform-from-io-or-mutation",
        )
    if shape.identity_parameter is not None and not shape.domain_identity_boundary:
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "warn",
            "identity_function",
            shape.name,
            f"returns {shape.identity_parameter}",
            "non-identity-domain-transform",
            "remove-wrapper-or-document-domain-contract",
        )
    if shape.passthrough is not None:
        callee, forwarded_count = shape.passthrough
        add_finding(
            findings,
            context.root,
            context.path,
            shape.line,
            context.language,
            "warn",
            "pass_through_function",
            shape.name,
            f"{callee}/{forwarded_count}",
            "adds-domain-or-adapter-contract",
            "inline-call-or-document-adapter-contract",
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


def finding_signal_class(finding: Finding) -> str:
    """Return the decision class for one finding."""
    if finding.severity == "error":
        return SIGNAL_CLASS_ERROR
    if finding.kind in REVIEW_SIGNAL_KINDS:
        return SIGNAL_CLASS_REVIEW
    return SIGNAL_CLASS_GATE


def signal_counts(findings: Sequence[Finding]) -> Counter[str]:
    """Return decision signal counts for findings."""
    return Counter(finding_signal_class(finding) for finding in findings)


def status_from_signal_counts(counts: Counter[str]) -> tuple[str, str]:
    """Return pass/fail status and a stable reason from signal classes."""
    if counts.get(SIGNAL_CLASS_ERROR, 0):
        return STATUS_FAIL, "error-signal"
    if counts.get(SIGNAL_CLASS_GATE, 0):
        return STATUS_FAIL, "gate-signal"
    if counts.get(SIGNAL_CLASS_REVIEW, 0):
        return STATUS_PASS, "review-only"
    return STATUS_PASS, "clean"


def status_from_score_and_signals(
    counts: Counter[str],
    final_score: int,
    min_score: int,
) -> tuple[str, str]:
    """Return status using signal classes, with explicit survey and strict-score modes."""
    if min_score <= 0:
        return STATUS_PASS, "survey-score-floor"
    if min_score > DEFAULT_MIN_SCORE and final_score < min_score:
        return STATUS_FAIL, "score-floor"
    return status_from_signal_counts(counts)


def score_floor_status(final_score: int, min_score: int) -> str:
    """Return whether the diagnostic score clears the requested floor."""
    return STATUS_PASS if final_score >= min_score else STATUS_FAIL


def score(findings: list[Finding]) -> int:
    """Calculate a diagnostic signal score independent of pass/fail status."""
    counts = signal_counts(findings)
    if not findings:
        return MAX_READABILITY_SCORE
    review_kinds = {
        finding.kind
        for finding in findings
        if finding_signal_class(finding) == SIGNAL_CLASS_REVIEW
    }
    gate_kinds = {
        finding.kind
        for finding in findings
        if finding_signal_class(finding) == SIGNAL_CLASS_GATE
    }
    hotspot_count = len({finding.path for finding in findings})
    if counts.get(SIGNAL_CLASS_ERROR, 0):
        base = 40
        penalty = counts[SIGNAL_CLASS_ERROR] * 10 + len(gate_kinds) * 4 + hotspot_count
    elif counts.get(SIGNAL_CLASS_GATE, 0):
        base = 80
        penalty = counts[SIGNAL_CLASS_GATE] * 4 + len(gate_kinds) * 3 + len(review_kinds)
    else:
        base = 95
        penalty = counts[SIGNAL_CLASS_REVIEW] + len(review_kinds) * 2 + hotspot_count
    return max(0, base - min(base, penalty))


def finding_identity(finding: Finding) -> tuple[str, str, str, str, str, str, str, str]:
    """Return a line-stable identity for baseline finding comparison."""
    return (
        finding.path,
        finding.language,
        finding.severity,
        finding.kind,
        finding.symbol,
        str(finding.actual),
        str(finding.limit),
        finding.guidance,
    )


def new_findings_since_baseline(
    current_findings: list[Finding],
    baseline_findings: list[Finding],
) -> list[Finding]:
    """Return findings not already present in the baseline analysis."""
    baseline_identities = {finding_identity(finding) for finding in baseline_findings}
    return [
        finding
        for finding in current_findings
        if finding_identity(finding) not in baseline_identities
    ]


def finding_rank(finding: Finding) -> tuple[int, str, int, str]:
    """Sort findings by review priority and location."""
    severity_rank = {"error": 0, "warn": 1, "info": 2}
    return (
        severity_rank.get(finding.severity, UNKNOWN_SEVERITY_FINDING_RANK),
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


def solid_principles_for_kind(kind: str) -> tuple[str, ...]:
    """Return SOLID principle names mechanically associated with a finding kind."""
    principle_keys = SOLID_PRINCIPLES_BY_KIND.get(kind, ())
    return tuple(SOLID_PRINCIPLES[key] for key in principle_keys)


def solid_principles_for_finding(finding: Finding) -> tuple[str, ...]:
    """Return SOLID principle names mechanically associated with a finding."""
    return solid_principles_for_kind(finding.kind)


def finding_payload(finding: Finding) -> dict[str, object]:
    """Return JSON payload with mechanical interpretation attached."""
    payload = asdict(finding)
    payload.update(finding_facts(finding))
    payload["solid_principles"] = list(solid_principles_for_finding(finding))
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
    decision_counts = signal_counts(findings)
    status, status_reason = status_from_score_and_signals(
        decision_counts,
        final_score,
        min_score,
    )
    review_signal_count = decision_counts.get(SIGNAL_CLASS_REVIEW, 0)
    gate_signal_count = decision_counts.get(SIGNAL_CLASS_GATE, 0)
    error_signal_count = decision_counts.get(SIGNAL_CLASS_ERROR, 0)
    dimension_counts = Counter(finding_facts(finding)["dimension"] for finding in findings)
    solid_counts = Counter(
        principle
        for finding in findings
        for principle in solid_principles_for_finding(finding)
    )
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
        "scanned_paths": selected_relative_paths(root, files),
        "source_loc": loc,
        "findings": len(findings),
        "score": final_score,
        "min_score": min_score,
        "score_status": score_floor_status(final_score, min_score),
        "excluded_patterns": list(exclude_patterns or []),
        "status": status,
        "status_reason": status_reason,
        "mechanical_grade": grade,
        "warn_or_error_per_kloc": round(per_kloc, 2),
        "severity_counts": dict(severity_counts),
        "kind_counts": dict(kind_counts),
        "review_signal_findings": review_signal_count,
        "gate_signal_findings": gate_signal_count,
        "error_signal_findings": error_signal_count,
        "signal_counts": dict(decision_counts),
        "dimension_counts": dict(dimension_counts),
        "solid_counts": dict(solid_counts),
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
    lines.extend(markdown_solid_lines(summary))
    lines.extend(markdown_dimension_lines(summary))
    lines.extend(markdown_hotspot_lines(summary))
    lines.extend(
        markdown_finding_detail_lines(spec.findings, snippets, spec.max_report_findings)
    )
    return "\n".join(lines).rstrip() + "\n"


def markdown_summary_lines(summary: dict[str, object]) -> list[str]:
    """Render Markdown summary lines."""
    excluded_patterns_summary = cast(list[str], summary["excluded_patterns"])
    scanned_paths = cast(list[str], summary["scanned_paths"])
    return [
        "# OOP Readability Mechanical Report",
        "",
        (
            "This report is generated by static heuristics. Findings are reported "
            "signals, not agent judgment or accepted design defects."
        ),
        "",
        "## Summary",
        "",
        f"- status: `{summary['status']}`",
        f"- status_reason: `{summary['status_reason']}`",
        f"- mechanical_grade: `{summary['mechanical_grade']}`",
        f"- score: `{summary['score']}` / floor `{summary['min_score']}`",
        f"- score_status: `{summary['score_status']}`",
        f"- files: `{summary['files']}`",
        f"- scanned_paths: `{', '.join(scanned_paths) or 'none'}`",
        f"- source_loc: `{summary['source_loc']}`",
        f"- findings: `{summary['findings']}`",
        f"- error_signal_findings: `{summary['error_signal_findings']}`",
        f"- gate_signal_findings: `{summary['gate_signal_findings']}`",
        f"- review_signal_findings: `{summary['review_signal_findings']}`",
        f"- warn_or_error_per_kloc: `{summary['warn_or_error_per_kloc']}`",
        f"- excluded_patterns: `{', '.join(excluded_patterns_summary) or 'none'}`",
        "",
    ]


def markdown_solid_lines(summary: dict[str, object]) -> list[str]:
    """Render SOLID principle signal counts."""
    solid_counts = cast(dict[str, int], summary["solid_counts"])
    lines = ["## SOLID Principle Signals", ""]
    if not solid_counts:
        lines.append("- none")
    for principle, count in Counter(solid_counts).most_common():
        lines.append(f"- `{principle}`: {count}")
    lines.append("")
    return lines


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
        solid_principles = ", ".join(solid_principles_for_finding(finding)) or "none"
        lines.extend(
            [
                (
                    f"### `{finding.path}:{finding.line}` "
                    f"`{finding.kind}` `{finding.severity}`"
                ),
                "",
                f"- symbol: `{finding.symbol}`",
                f"- dimension: `{facts['dimension']}`",
                f"- solid_principles: `{solid_principles}`",
                f"- actual_vs_limit: `{finding.actual}` > `{finding.limit}`",
                f"- mechanical_explanation: {facts['explanation']}",
                f"- reported_action_signal: {facts['recommended_action']}",
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
                (
                    "- Treat mechanical findings as reported signals; preserve tool "
                    "facts separately from reviewer judgment."
                ),
                (
                    "- Size, public-surface, parameter-count, and complexity findings "
                    "are boundary review signals, not accepted design defects or "
                    "split/extract instructions."
                ),
                "- Separate false-positive candidates from accepted design risks.",
                "- Group comments by the report's SOLID Principle Signals section first.",
                "- Then cite the OOP dimension for each accepted mechanical finding.",
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
    started_at = time.perf_counter()
    parser = build_parser(default_language=default_language)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    run = build_analyzer_run(root, args)
    emit_report(run, args)
    if args.review_prompt_out:
        write_review_prompt(Path(args.review_prompt_out), "")
    status = str(run.summary["status"])
    append_workflow_monitor_timing(root, args, status, started_at)
    return 0 if status == STATUS_PASS else 1


def append_workflow_monitor_timing(
    root: Path,
    args: argparse.Namespace,
    status: str,
    started_at: float,
) -> None:
    """Append OOP checker timing to workflow monitoring when a run bundle is active."""
    report_dir = os.environ.get(WORKFLOW_MONITOR_REPORT_DIR_ENV, "").strip()
    monitor = root / "tools" / "agent_tools" / "workflow_monitor.py"
    if not report_dir or not monitor.is_file():
        return
    duration_ms = int((time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND)
    scope = ",".join(str(path) for path in args.paths) if args.paths else "."
    output_path = str(args.review_prompt_out) if args.review_prompt_out else "stdout"
    event = (
        "tool_call=oop-readability-check "
        f"command={Path(sys.argv[0]).as_posix()} "
        f"duration_ms={duration_ms} "
        f"status={status} "
        f"scope={scope} "
        f"output_path={output_path}"
    )
    subprocess.run(
        [
            sys.executable,
            str(monitor),
            "--report-dir",
            report_dir,
            "--behavior-event",
            event,
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=WORKFLOW_MONITOR_TIMEOUT_SECONDS,
    )


def build_thresholds(args: argparse.Namespace) -> Thresholds:
    """Build thresholds from parsed command-line arguments."""
    return Thresholds(
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
    dependency_context = DependencyUsageContext(
        usage_roots=tuple(str(item) for item in args.usage_roots),
        dependency_modules=tuple(str(item) for item in args.dependency_modules),
    )
    findings = collect_findings(
        root,
        files,
        thresholds,
        args.exclude,
        dependency_context,
    )
    baseline_ref = str(args.baseline_ref or "").strip()
    if baseline_ref:
        baseline_findings = collect_baseline_findings(
            root,
            files,
            thresholds,
            args.exclude,
            BaselineComparisonSpec(
                language=args.language,
                baseline_ref=baseline_ref,
                dependency_context=dependency_context,
            ),
        )
        if baseline_findings is not None:
            findings = new_findings_since_baseline(findings, baseline_findings)
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


def collect_baseline_findings(
    root: Path,
    files: list[Path],
    thresholds: Thresholds,
    exclude_patterns: Sequence[str],
    spec: BaselineComparisonSpec,
) -> list[Finding] | None:
    """Analyze requested files as they existed at one git baseline ref."""
    relative_sources = git_baseline_source_paths(
        root,
        spec.baseline_ref,
        spec.language,
        exclude_patterns,
    )
    if relative_sources is None:
        return None
    selected_relatives = selected_relative_paths(root, files)
    materialized_relatives = sorted(set(relative_sources) | set(selected_relatives))
    with tempfile.TemporaryDirectory() as tmp_dir:
        baseline_root = Path(tmp_dir)
        materialize_git_baseline(root, spec.baseline_ref, baseline_root, materialized_relatives)
        baseline_files = [
            (baseline_root / relative).resolve()
            for relative in selected_relatives
            if (baseline_root / relative).is_file()
        ]
        return collect_findings(
            baseline_root,
            baseline_files,
            thresholds,
            exclude_patterns,
            spec.dependency_context,
        )


def selected_relative_paths(root: Path, files: list[Path]) -> list[str]:
    """Return selected files as root-relative POSIX paths."""
    relatives: list[str] = []
    for path in files:
        try:
            relatives.append(path.resolve().relative_to(root).as_posix())
        except ValueError:
            continue
    return sorted(set(relatives))


def git_baseline_source_paths(
    root: Path,
    baseline_ref: str,
    language: str,
    exclude_patterns: Sequence[str],
) -> list[str] | None:
    """Return source paths present in a git baseline tree."""
    output = git_text(root, ["ls-tree", "-r", "--name-only", baseline_ref, "--"])
    if output is None:
        return None
    relative_paths: list[str] = []
    for line in output.splitlines():
        relative = Path(line.strip())
        if not line.strip() or is_hidden(relative) or "__pycache__" in relative.parts:
            continue
        if relative.suffix not in LANGUAGE_SUFFIXES[language]:
            continue
        if path_is_excluded(relative, list(exclude_patterns)):
            continue
        relative_paths.append(relative.as_posix())
    return sorted(set(relative_paths))


def materialize_git_baseline(
    root: Path,
    baseline_ref: str,
    destination: Path,
    relative_paths: Sequence[str],
) -> None:
    """Write selected files from a git baseline tree into a temporary root."""
    for relative_path in relative_paths:
        content = git_blob(root, baseline_ref, relative_path)
        if content is None:
            continue
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def git_text(root: Path, args: Sequence[str]) -> str | None:
    """Return git command stdout text, or None when unavailable."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_BASELINE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def git_blob(root: Path, baseline_ref: str, relative_path: str) -> bytes | None:
    """Return one file blob from a git baseline tree."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "show", f"{baseline_ref}:{relative_path}"],
            check=False,
            capture_output=True,
            timeout=GIT_BASELINE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def collect_findings(
    root: Path,
    files: list[Path],
    thresholds: Thresholds,
    exclude_patterns: Sequence[str],
    dependency_context: DependencyUsageContext = DependencyUsageContext(),
) -> list[Finding]:
    """Collect findings for every selected source file."""
    findings: list[Finding] = []
    python_files = [path for path in files if path.suffix in PYTHON_SUFFIXES]
    cpp_files = [path for path in files if path.suffix in CPP_SUFFIXES]
    python_usage_index = (
        build_python_usage_index(
            root,
            python_usage_source_files(
                root,
                python_files,
                exclude_patterns,
                usage_roots=dependency_context.usage_roots,
                dependency_modules=dependency_context.dependency_modules,
            ),
        )
        if python_files
        else empty_python_usage_index()
    )
    cpp_usage_index = (
        build_cpp_usage_index(
            root,
            cpp_usage_source_files(
                root,
                cpp_files,
                exclude_patterns,
                usage_roots=dependency_context.usage_roots,
            ),
        )
        if cpp_files
        else empty_cpp_usage_index()
    )
    for path in files:
        if path.suffix in PYTHON_SUFFIXES:
            findings.extend(analyze_python_file(root, path, thresholds, python_usage_index))
        elif path.suffix in CPP_SUFFIXES:
            findings.extend(analyze_cpp_file(root, path, thresholds, cpp_usage_index))
    return findings


def emit_report(run: AnalyzerRun, args: argparse.Namespace) -> None:
    """Print the requested output format."""
    if args.format == "json":
        emit_json_report(run, args)
        return
    if args.format == "markdown":
        emit_markdown_report(run, args)
        return
    emit_text_report(run)


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


def emit_text_report(run: AnalyzerRun) -> None:
    """Print line-oriented text output."""
    for finding in sorted(run.findings, key=lambda item: (item.path, item.line, item.kind)):
        print(finding.render())
    print(f"OOP_READABILITY_FILES={len(run.files)}")
    print(f"OOP_READABILITY_FINDINGS={len(run.findings)}")
    print(f"OOP_READABILITY_SCORE={run.final_score}")
    print(f"OOP_READABILITY_SCORE_STATUS={run.summary['score_status']}")
    print(f"OOP_READABILITY_GRADE={run.summary['mechanical_grade']}")
    print(f"OOP_READABILITY_STATUS_REASON={run.summary['status_reason']}")
    print(f"OOP_READABILITY_WARN_OR_ERROR_PER_KLOC={run.summary['warn_or_error_per_kloc']}")
    print(f"OOP_READABILITY_ERROR_SIGNAL_FINDINGS={run.summary['error_signal_findings']}")
    print(f"OOP_READABILITY_GATE_SIGNAL_FINDINGS={run.summary['gate_signal_findings']}")
    print(f"OOP_READABILITY_REVIEW_SIGNAL_FINDINGS={run.summary['review_signal_findings']}")
    print(f"OOP_READABILITY={run.summary['status']}")


if __name__ == "__main__":
    raise SystemExit(main())
