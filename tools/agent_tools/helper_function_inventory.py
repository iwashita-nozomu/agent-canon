#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Inventories Python helper symbols with deterministic static role analysis.
# upstream design ../../documents/tools/README.md AgentCanon tool entrypoint policy
# upstream design ../../documents/coding-conventions-python.md helper and role naming policy
# downstream implementation ../../tests/agent_tools/test_helper_function_inventory.py tests inventory behavior
# @dependency-end
"""Inventory Python helper functions/classes and infer their static roles."""

from __future__ import annotations

import argparse
import ast
import copy
import itertools
import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_EXCLUDED_PARTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "reports",
        "vendor",
    }
)
DEFAULT_EXCLUDED_SUFFIXES = (".pyi",)
PUBLIC_LOCAL_HELPER_ROLES = frozenset(
    {
        "adapter_bridge",
        "collector_inventory",
        "converter_normalizer",
        "cli_parser",
        "command_runner",
        "factory_builder",
        "formatter_reporter",
        "parser_loader",
        "predicate",
        "static_analyzer",
        "validator_checker",
        "writer_mutator",
    }
)
CLASS_LOCAL_HELPER_ROLES = frozenset(
    {
        "adapter_bridge",
        "collector_inventory",
        "command_runner",
        "converter_normalizer",
        "data_container",
        "factory_builder",
        "formatter_reporter",
        "parser_loader",
        "state_holder",
        "static_analyzer",
        "validator_checker",
        "writer_mutator",
    }
)
LOCAL_SPECIALIZATIONS = frozenset({"single_caller_helper", "file_local_helper_cluster"})
LOW_SIGNAL_HELPER_ROLES = frozenset(
    {
        "general_helper",
        "numeric_kernel",
        "protocol_interface",
        "test_support",
        "workflow_tooling",
    }
)
MUTATING_METHODS = frozenset(
    {
        "add",
        "append",
        "clear",
        "discard",
        "extend",
        "insert",
        "pop",
        "remove",
        "setdefault",
        "sort",
        "update",
        "write",
        "writelines",
    }
)
ROLE_SCORE_WEAK = 1
ROLE_SCORE_STANDARD = 2
ROLE_SCORE_STRONG = 3
ROLE_SCORE_DOMINANT = 4
ROLE_SCORE_BOUNDARY = 5
SINGLE_STATEMENT_BODY_COUNT = 1
BASE_HELPER_CONFIDENCE = 0.35
PRIVATE_NAME_CONFIDENCE_BONUS = 0.25
NESTED_SCOPE_CONFIDENCE_BONUS = 0.2
ROLE_SCORE_CONFIDENCE_CAP = 0.2
ROLE_SCORE_CONFIDENCE_DIVISOR = 20.0
DEFAULT_HALF_CONFIDENCE = 0.5
CALL_CONFIDENCE_BONUS = 0.05
FEATURE_CONFIDENCE_BONUS = 0.05
MAX_HELPER_CONFIDENCE = 0.99
JUDGMENT_CONFIDENCE = 0.4
SECONDARY_ROLE_SLICE_STOP = 4
DOC_SUMMARY_LIMIT = 140
LOCAL_CALLER_CLUSTER_LIMIT = 3
EVIDENCE_RENDER_LIMIT = 6
MARKDOWN_EVIDENCE_LIMIT = 4
REDUNDANT_WITH_EVIDENCE_LIMIT = 3
ROLE_NAME_TOKENS = {
    "adapter_bridge": (
        "adapt",
        "adapter",
        "bridge",
        "connect",
        "forward",
        "proxy",
        "route",
        "shim",
        "wrap",
        "wrapper",
    ),
    "cli_parser": ("arg", "args", "cli", "option", "parse", "parser"),
    "collector_inventory": (
        "collect",
        "enumerate",
        "extract",
        "find",
        "gather",
        "inventory",
        "list",
        "scan",
        "summary",
        "summarize",
    ),
    "command_runner": (
        "call",
        "command",
        "exec",
        "execute",
        "invoke",
        "launch",
        "run",
        "spawn",
    ),
    "converter_normalizer": (
        "adapt",
        "coerce",
        "convert",
        "map",
        "materialize",
        "normalize",
        "render",
        "resolve",
        "transform",
        "translate",
    ),
    "data_container": (
        "config",
        "context",
        "data",
        "info",
        "metadata",
        "metrics",
        "model",
        "options",
        "packet",
        "params",
        "record",
        "result",
        "state",
    ),
    "exception_type": ("error", "exception", "failure"),
    "factory_builder": (
        "build",
        "construct",
        "create",
        "factory",
        "make",
        "new",
    ),
    "formatter_reporter": (
        "describe",
        "emit",
        "format",
        "render",
        "report",
        "summary",
        "summarize",
        "write",
    ),
    "general_helper": ("helper", "support"),
    "numeric_kernel": (
        "compute",
        "kernel",
        "linear",
        "metric",
        "numeric",
        "residual",
        "score",
        "solve",
    ),
    "parser_loader": (
        "discover",
        "load",
        "materialize",
        "parse",
        "read",
        "resolve",
    ),
    "predicate": (
        "allow",
        "allows",
        "can",
        "check",
        "contains",
        "exists",
        "has",
        "is",
        "match",
        "matches",
        "needs",
        "ready",
        "should",
        "valid",
    ),
    "protocol_interface": ("interface", "port", "protocol"),
    "state_holder": ("cache", "holder", "registry", "session", "state", "store"),
    "static_analyzer": (
        "analyze",
        "ast",
        "classify",
        "detect",
        "infer",
        "inspect",
        "parse",
        "scan",
    ),
    "test_support": ("fixture", "reference", "sample", "support", "test"),
    "validator_checker": (
        "assert",
        "check",
        "ensure",
        "guard",
        "lint",
        "validate",
        "verify",
    ),
    "workflow_tooling": ("agent", "route", "task", "tool", "workflow"),
    "writer_mutator": (
        "append",
        "emit",
        "persist",
        "record",
        "save",
        "store",
        "update",
        "write",
    ),
}
IDENTIFIER_TOKEN_RE = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[0-9]+"
)


@dataclass(frozen=True)
class BodyFacts:
    """Static facts collected from one function body."""

    calls: tuple[str, ...]
    call_locations: tuple[tuple[str, int], ...]
    features: tuple[str, ...]


@dataclass
class FunctionRecord:
    """One Python function or method with inferred helper metadata."""

    path: str
    line: int
    end_line: int
    kind: str
    domain: str
    name: str
    qualname: str
    scope: str
    visibility: str
    role: str
    secondary_roles: list[str]
    name_tokens: list[str]
    role_name_tokens: list[str]
    matched_role_name_tokens: list[str]
    searchable_name: bool
    name_search_rule: str
    confidence: float
    helper_candidate: bool
    candidate_rule: str
    needs_user_judgment: bool
    judgment_rule: str
    redundant_helper: bool
    redundancy_rule: str
    redundant_with: list[str]
    implementation_signature: str
    incoming_count: int
    incoming_callers: list[str]
    incoming_call_sites: list[str]
    outgoing_internal: list[str]
    outgoing_call_sites: list[str]
    specialized_helper: bool
    specialization: str
    side_effects: list[str]
    features: list[str]
    calls: list[str]
    args: list[str]
    bases: list[str]
    method_count: int
    public_method_count: int
    decorators: list[str]
    returns_annotation: str
    doc_summary: str
    evidence: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class Inventory:
    """Complete helper inventory report."""

    root: str
    changed_only: bool
    baseline_ref: str
    baseline_symbols_seen: int
    baseline_filtered: int
    files_scanned: int
    symbols_seen: int
    functions_seen: int
    classes_seen: int
    symbols_reported: int
    helpers_reported: int
    judgment_required_reported: int
    name_gaps_reported: int
    role_counts: dict[str, int]
    verdict_counts: dict[str, int]
    records: list[FunctionRecord]


@dataclass(frozen=True)
class InventoryBuildOptions:
    """Options controlling inventory construction."""

    paths: list[str]
    all_functions: bool
    only_auto_helpers: bool
    only_user_judgment: bool
    only_name_gaps: bool
    changed_only: bool
    baseline_ref: str
    include_vendor: bool
    include_hidden: bool
    include_pyi: bool
    min_confidence: float


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Files or directories to scan.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--all-functions",
        action="store_true",
        help="Report every function, not only helper candidates.",
    )
    parser.add_argument(
        "--only-auto-helpers",
        action="store_true",
        help="Report only high-confidence helper verdicts.",
    )
    parser.add_argument(
        "--only-user-judgment",
        action="store_true",
        help="Report only symbols that need user design judgment.",
    )
    parser.add_argument(
        "--only-name-gaps",
        action="store_true",
        help=(
            "Report helper or design-judgment symbols selected for role/action "
            "token review in responsibility search."
        ),
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help=(
            "Report only changed Python files while preserving whole-repo call graph "
            "context when changed files exist."
        ),
    )
    parser.add_argument(
        "--baseline-ref",
        default="",
        help=(
            "Only report findings absent from this git ref. Use with --changed for "
            "hook-friendly new-finding output."
        ),
    )
    parser.add_argument(
        "--include-vendor",
        action="store_true",
        help="Include vendor/ paths reached directly. Root symlink views such as tools/ still scan.",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden directories other than .git.",
    )
    parser.add_argument(
        "--include-pyi",
        action="store_true",
        help="Include .pyi stubs. Defaults to runtime .py files only.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Only print helpers with at least this confidence.",
    )
    return parser


def logical_excluded(
    relative: Path,
    *,
    include_vendor: bool,
    include_hidden: bool,
) -> bool:
    """Return whether a logical path should be skipped."""
    parts = set(relative.parts)
    excluded = set(DEFAULT_EXCLUDED_PARTS)
    if include_vendor:
        excluded.discard("vendor")
    if parts & excluded:
        return True
    if not include_hidden and any(part.startswith(".") for part in relative.parts):
        return True
    if relative.parts[:2] == ("python", "typings"):
        return True
    return False


def iter_python_files(
    root: Path,
    raw_paths: list[str],
    *,
    include_vendor: bool,
    include_hidden: bool,
    include_pyi: bool,
) -> list[Path]:
    """Return Python source files, following root symlink views once."""
    suffixes = source_suffixes(include_pyi)
    targets = [root / raw_path for raw_path in raw_paths] if raw_paths else [root]
    walk_state = FileWalkState(
        root=root,
        files=[],
        seen_dirs=set(),
        seen_files=set(),
        suffixes=suffixes,
        include_vendor=include_vendor,
        include_hidden=include_hidden,
    )
    for target in targets:
        if target.is_file():
            append_source_once(walk_state.files, walk_state.seen_files, target, suffixes)
            continue
        for current_root, dirnames, filenames in os.walk(target, followlinks=True):
            append_walk_sources(
                walk_state,
                Path(current_root),
                dirnames,
                filenames,
            )
    return sorted(walk_state.files, key=lambda path: stable_relative(root, path))


@dataclass
class FileWalkState:
    """Mutable state for a Python source tree walk."""

    root: Path
    files: list[Path]
    seen_dirs: set[Path]
    seen_files: set[Path]
    suffixes: set[str]
    include_vendor: bool
    include_hidden: bool


def source_suffixes(include_pyi: bool) -> set[str]:
    """Return source suffixes included in the scan."""
    suffixes = {".py"}
    if include_pyi:
        suffixes.add(".pyi")
    return suffixes


def append_source_once(
    files: list[Path],
    seen_files: set[Path],
    path: Path,
    suffixes: set[str],
) -> None:
    """Append one source file if its resolved path was not already seen."""
    if path.suffix not in suffixes:
        return
    resolved = path.resolve()
    if resolved in seen_files:
        return
    seen_files.add(resolved)
    files.append(path)


def root_relative_or_self(root: Path, path: Path) -> Path:
    """Return root-relative path when possible."""
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def append_walk_sources(
    state: FileWalkState,
    current: Path,
    dirnames: list[str],
    filenames: list[str],
) -> None:
    """Append source files from one os.walk directory step."""
    real_current = current.resolve()
    if real_current in state.seen_dirs:
        dirnames[:] = []
        return
    state.seen_dirs.add(real_current)
    dirnames[:] = retained_dirnames(
        state.root,
        current,
        dirnames,
        include_vendor=state.include_vendor,
        include_hidden=state.include_hidden,
    )
    if logical_excluded(
        root_relative_or_self(state.root, current),
        include_vendor=state.include_vendor,
        include_hidden=state.include_hidden,
    ):
        dirnames[:] = []
        return
    for filename in filenames:
        append_source_once(state.files, state.seen_files, current / filename, state.suffixes)


def retained_dirnames(
    root: Path,
    current: Path,
    dirnames: list[str],
    *,
    include_vendor: bool,
    include_hidden: bool,
) -> list[str]:
    """Return child directory names that should remain in an os.walk traversal."""
    kept: list[str] = []
    for dirname in dirnames:
        relative_child = root_relative_or_self(root, current / dirname)
        if logical_excluded(
            relative_child,
            include_vendor=include_vendor,
            include_hidden=include_hidden,
        ):
            continue
        kept.append(dirname)
    return kept


def git_lines(root: Path, args: list[str]) -> list[str]:
    """Return non-empty git output lines for one repository command."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_python_files(
    root: Path,
    *,
    include_vendor: bool,
    include_hidden: bool,
    include_pyi: bool,
) -> list[Path]:
    """Return changed Python files that pass inventory path filters."""
    names: set[str] = set()
    for args in (
        ["diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "--"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        names.update(git_lines(root, args))
    suffixes = {".py"}
    if include_pyi:
        suffixes.add(".pyi")
    files: list[Path] = []
    for name in sorted(names):
        path = root / name
        relative = Path(name)
        if path.suffix not in suffixes:
            continue
        if path.suffix in DEFAULT_EXCLUDED_SUFFIXES and not include_pyi:
            continue
        if logical_excluded(relative, include_vendor=include_vendor, include_hidden=include_hidden):
            continue
        if path.is_file():
            files.append(path)
    return files


def requested_relative_paths(
    root: Path,
    raw_paths: list[str],
    *,
    include_vendor: bool,
    include_hidden: bool,
    include_pyi: bool,
) -> set[str]:
    """Return root-relative Python paths requested by positional paths."""
    if not raw_paths:
        return set()
    return {
        stable_relative(root, path)
        for path in iter_python_files(
            root,
            raw_paths,
            include_vendor=include_vendor,
            include_hidden=include_hidden,
            include_pyi=include_pyi,
        )
    }


def git_ref_text(root: Path, ref: str, relative_path: str) -> str | None:
    """Return one file's text at a git ref, or None when absent."""
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{ref}:{relative_path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def git_renamed_paths(root: Path, ref: str) -> dict[str, str]:
    """Return current-path to baseline-path mappings for renamed files."""
    if not ref:
        return {}
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-status", "--find-renames", ref, "--"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    renamed: dict[str, str] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0].startswith("R"):
            old_path, new_path = parts[1], parts[2]
            renamed[new_path] = old_path
    return renamed


def stable_relative(root: Path, path: Path) -> str:
    """Return a stable root-relative path when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def path_domain(path: str) -> str:
    """Classify repository area for deterministic helper rules."""
    parts = tuple(Path(path).parts)
    if any(part in {"tests", "test"} or part.startswith("test_") for part in parts):
        return "test"
    if any(
        part in {"benchmarks", "experiments", "notebooks"}
        or part.startswith(("bench", "experiment"))
        for part in parts
    ):
        return "experiment"
    if any(part in {"agent_tools", "scripts", "tools"} for part in parts):
        return "tooling"
    return "main"


def _annotation_text(node: ast.AST | None) -> str:
    """Return a compact source rendering for one annotation node."""
    if node is None:
        return ""
    return ast.unparse(node)


def dotted_name(node: ast.AST) -> str:
    """Return a best-effort dotted name for a call or decorator expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return dotted_name(node.func)
    if isinstance(node, ast.Subscript):
        return dotted_name(node.value)
    return ""


def contains_string_literal(node: ast.AST) -> bool:
    """Return whether one expression subtree contains a string literal."""
    return any(isinstance(child, ast.Constant) and isinstance(child.value, str) for child in ast.walk(node))


class FunctionBodyVisitor(ast.NodeVisitor):
    """Collect calls and role features from one function body."""

    def __init__(self, root: ast.AST) -> None:
        """Initialize body fact collection for one function node."""
        self.root = root
        self.calls: Counter[str] = Counter()
        self.call_locations: list[tuple[str, int]] = []
        self.features: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Skip nested function bodies while analyzing the outer function."""
        if node is self.root:
            self.generic_visit(node)
        else:
            self.features.add("nested_function_definition")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Skip nested async function bodies while analyzing the outer function."""
        if node is self.root:
            self.generic_visit(node)
        else:
            self.features.add("nested_function_definition")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Do not mix class-local method calls into an enclosing function."""
        if node is self.root:
            self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Record calls and side-effect-like features."""
        name = dotted_name(node.func)
        if name:
            self._record_call(name, node.lineno)
        self.generic_visit(node)

    def _record_call(self, name: str, line: int) -> None:
        """Record one call and dispatch feature classifiers."""
        self.calls[name] += 1
        self.call_locations.append((name, line))
        leaf = name.rsplit(".", maxsplit=1)[-1]
        record_effect_call_features(self.features, name, leaf)
        record_transform_call_features(self.features, name, leaf)
        record_analysis_call_features(self.features, name, leaf)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Record attribute-only feature references."""
        name = dotted_name(node)
        if name == "sys.platform":
            self.features.add("environment")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        """Record operator-based path composition."""
        if isinstance(node.op, ast.Div):
            self.features.add("path_operation")
        if isinstance(node.op, (ast.Add, ast.MatMult, ast.Mult, ast.Pow, ast.Sub)):
            self.features.add("operator_expression")
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        """Record f-string text formatting."""
        self.features.add("text_transform")
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        """Record callable construction."""
        self.features.add("nested_function_definition")
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        """Record return-shape features without using function names."""
        value = node.value
        if value is not None and any(isinstance(child, ast.Call) for child in ast.walk(value)):
            self.features.add("call_return")
        if isinstance(value, ast.Call):
            self.features.add("direct_call_return")
            if call_passes_parameters_through(self.root, value):
                self.features.add("pass_through_call_return")
        if value is not None and returned_parameter_name(self.root, value):
            self.features.add("identity_return")
        if isinstance(value, ast.IfExp):
            self.features.add("conditional_return")
        if isinstance(value, (ast.Dict, ast.DictComp)):
            self.features.add("mapping_return")
        if isinstance(value, (ast.List, ast.ListComp, ast.Set, ast.SetComp, ast.Tuple)):
            self.features.add("collection_return")
        if isinstance(value, (ast.BoolOp, ast.Compare, ast.UnaryOp)):
            self.features.add("predicate_return")
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        """Record expression-level call delegation."""
        if isinstance(node.value, ast.Call):
            self.features.add("call_statement")
            if call_passes_parameters_through(self.root, node.value):
                self.features.add("pass_through_call_statement")
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        """Record conditional return behavior."""
        if any(isinstance(child, ast.Return) for child in ast.walk(node)):
            self.features.add("conditional_return")
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        """Record context-manager resource lifecycle behavior."""
        self.features.add("resource_lifecycle")
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        """Record async context-manager resource lifecycle behavior."""
        self.features.add("resource_lifecycle")
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        """Record iteration-heavy behavior."""
        self.features.add("iteration")
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        """Record async iteration-heavy behavior."""
        self.features.add("iteration")
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        """Record comprehension iteration."""
        self.features.add("iteration")
        self.generic_visit(node)

    def visit_Yield(self, node: ast.Yield) -> None:
        """Record generator behavior."""
        self.features.add("generator")
        self.generic_visit(node)

    def visit_YieldFrom(self, node: ast.YieldFrom) -> None:
        """Record generator behavior."""
        self.features.add("generator")
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        """Record validation/error behavior."""
        self.features.add("raises")
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Record local imports."""
        self.features.add("local_import")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Record local imports."""
        self.features.add("local_import")
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        """Record module-global mutation intent."""
        self.features.add("state_mutation")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Record attribute or subscript mutation."""
        for target in node.targets:
            if isinstance(target, (ast.Attribute, ast.Subscript)):
                self.features.add("state_mutation")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Record attribute or subscript mutation."""
        if isinstance(node.target, (ast.Attribute, ast.Subscript)):
            self.features.add("state_mutation")
        self.generic_visit(node)

    def facts(self) -> BodyFacts:
        """Return immutable facts."""
        expanded_calls: list[str] = []
        for name, count in sorted(self.calls.items()):
            expanded_calls.extend([name] * count)
        features = set(self.features)
        if has_single_executable_statement(self.root):
            features.add("single_statement_body")
        return BodyFacts(
            calls=tuple(expanded_calls),
            call_locations=tuple(sorted(self.call_locations)),
            features=tuple(sorted(features)),
        )


def record_effect_call_features(features: set[str], name: str, leaf: str) -> None:
    """Record effect-oriented call features."""
    if leaf in MUTATING_METHODS:
        features.add("mutation_call")
    if leaf in {"close", "cleanup", "release", "shutdown"}:
        features.add("resource_lifecycle")
    if name.startswith("subprocess.") or leaf in {"Popen", "run"}:
        features.add("subprocess")
    if name in {"print", "sys.stdout.write", "sys.stderr.write"}:
        features.add("stdio")
    if name.startswith("logging.") or leaf in {"debug", "info", "warning", "error"}:
        features.add("logging")
    if leaf in {"write", "write_text", "write_bytes", "dump", "dumps"}:
        features.add("write")
    if leaf in {"mkdir", "unlink", "rename", "replace", "copy", "copy2", "rmtree"}:
        features.add("filesystem_mutation")
    if name == "progress_callback":
        features.add("callback_emission")


def record_transform_call_features(features: set[str], name: str, leaf: str) -> None:
    """Record transform, parsing, and normalization call features."""
    if leaf in {"read", "read_text", "read_bytes", "load", "loads"}:
        features.add("read")
    if name.startswith(("json.", "tomllib.", "tomli.", "yaml.")):
        features.add("serialization")
    if name.startswith("base64."):
        features.add("encoding_transform")
    if name.startswith("re."):
        features.add("text_transform")
    if name == "Path" or name.startswith(("pathlib.", "os.path.")):
        features.add("path_operation")
    if leaf in {"absolute", "expanduser", "joinpath", "relative_to", "resolve", "with_name", "with_suffix"}:
        features.add("path_operation")
    if leaf in {"format", "join", "lower", "removeprefix", "removesuffix", "replace", "rstrip", "split", "strip", "upper"}:
        features.add("text_transform")
    if name.startswith(("hashlib.", "hmac.")) or leaf in {"digest", "hexdigest"}:
        features.add("digest_transform")
    if leaf in {"decrypt", "encrypt"}:
        features.add("security_transform")


def record_analysis_call_features(features: set[str], name: str, leaf: str) -> None:
    """Record static-analysis, numeric, interop, and environment call features."""
    if name.startswith("os.environ") or name in {"os.getenv", "getenv"}:
        features.add("environment")
    if name.startswith("platform."):
        features.add("environment")
    if name.startswith(("ctypes.", "cffi.")) or leaf in {"byref", "cast", "c_void_p"}:
        features.add("pointer_interop")
    if leaf in {"getattr", "hasattr", "isinstance", "issubclass", "type"}:
        features.add("type_introspection")
    if name.startswith(("ast.", "libcst.")):
        features.add("static_analysis")
    if name.startswith(("jax.", "jnp.", "np.", "numpy.", "math.", "lax.")):
        features.add("numeric")
    if leaf in {
        "array",
        "asarray",
        "ascontiguousarray",
        "flatten",
        "ravel",
        "reshape",
        "tolist",
        "tree_flatten",
        "tree_leaves",
        "tree_map",
        "tree_unflatten",
    }:
        features.add("data_shape_transform")
    if name.startswith(("argparse.",)) or leaf == "ArgumentParser":
        features.add("cli_parser")
    if name.startswith(("requests.", "urllib.")):
        features.add("network")


def returned_parameter_name(root: ast.AST, value: ast.AST) -> str:
    """Return a parameter name when a function returns it unchanged."""
    if not isinstance(root, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""
    if not isinstance(value, ast.Name):
        return ""
    parameter_names = function_parameter_names(root)
    return value.id if value.id in parameter_names else ""


def function_parameter_names(root: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Return every parameter name accepted by one function definition."""
    return set(function_parameter_sequence(root))


def function_parameter_sequence(root: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Return parameter names in function-signature order."""
    parameter_names = [
        arg.arg for arg in [*root.args.posonlyargs, *root.args.args, *root.args.kwonlyargs]
    ]
    if root.args.vararg is not None:
        parameter_names.append(root.args.vararg.arg)
    if root.args.kwarg is not None:
        parameter_names.append(root.args.kwarg.arg)
    return parameter_names


def call_passes_parameters_through(root: ast.AST, call: ast.Call) -> bool:
    """Return whether a call forwards only parameters from the current function."""
    if not isinstance(root, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    parameter_names = function_parameter_names(root)
    if not call.args and not call.keywords:
        return False
    return all(
        call_argument_passes_parameter_through(argument, parameter_names)
        for argument in call.args
    ) and all(
        call_keyword_passes_parameter_through(keyword, parameter_names)
        for keyword in call.keywords
    )


def call_argument_passes_parameter_through(
    argument: ast.expr,
    parameter_names: set[str],
) -> bool:
    """Return whether one positional call argument forwards a parameter."""
    if isinstance(argument, ast.Starred):
        return isinstance(argument.value, ast.Name) and argument.value.id in parameter_names
    return isinstance(argument, ast.Name) and argument.id in parameter_names


def call_keyword_passes_parameter_through(
    keyword: ast.keyword,
    parameter_names: set[str],
) -> bool:
    """Return whether one keyword call argument forwards a parameter."""
    return isinstance(keyword.value, ast.Name) and keyword.value.id in parameter_names


def body_facts(node: ast.AST) -> BodyFacts:
    """Collect facts for one function body."""
    visitor = FunctionBodyVisitor(node)
    visitor.visit(node)
    return visitor.facts()


class ParameterNameNormalizer(ast.NodeTransformer):
    """Normalize parameter names so duplicate bodies can be compared."""

    def __init__(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Create a normalizer for one function definition."""
        self.parameter_names = {
            name: f"arg{index}"
            for index, name in enumerate(function_parameter_sequence(node))
        }

    def visit_Name(self, node: ast.Name) -> ast.AST:
        """Normalize references to parameters while preserving other names."""
        if node.id in self.parameter_names:
            return ast.copy_location(ast.Name(id=self.parameter_names[node.id], ctx=node.ctx), node)
        return node

    def visit_arg(self, node: ast.arg) -> ast.arg:
        """Normalize parameter declarations."""
        if node.arg in self.parameter_names:
            node.arg = self.parameter_names[node.arg]
        return node


def implementation_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Return a normalized implementation signature for redundancy comparison."""
    body = copy.deepcopy(function_body_without_docstring(node))
    if not body:
        return ""
    normalized = ast.Module(body=body, type_ignores=[])
    normalized = ParameterNameNormalizer(node).visit(normalized)
    ast.fix_missing_locations(normalized)
    return ast.dump(normalized, include_attributes=False)


def function_body_without_docstring(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.stmt]:
    """Return function body statements excluding a leading docstring."""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and contains_string_literal(body[0]):
        return body[1:]
    return body


def has_single_executable_statement(root: ast.AST) -> bool:
    """Return whether one function body has exactly one executable statement."""
    if not isinstance(root, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return len(function_body_without_docstring(root)) == SINGLE_STATEMENT_BODY_COUNT


def class_body_facts(node: ast.ClassDef) -> BodyFacts:
    """Collect aggregate static facts from direct class methods and class body."""
    calls: Counter[str] = Counter()
    call_locations: list[tuple[str, int]] = []
    features: set[str] = set()

    class_facts = body_facts(node)
    calls.update(class_facts.calls)
    call_locations.extend(class_facts.call_locations)
    features.update(class_facts.features)

    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_facts = body_facts(item)
            calls.update(method_facts.calls)
            call_locations.extend(method_facts.call_locations)
            features.update(method_facts.features)

    expanded_calls: list[str] = []
    for name, count in sorted(calls.items()):
        expanded_calls.extend([name] * count)
    return BodyFacts(
        calls=tuple(expanded_calls),
        call_locations=tuple(sorted(call_locations)),
        features=tuple(sorted(features)),
    )


def role_scores(
    *,
    path: str,
    returns_annotation: str,
    facts: BodyFacts,
) -> tuple[Counter[str], list[str]]:
    """Infer possible roles from path, annotations, calls, and body features."""
    path_parts = tuple(Path(path).parts)
    calls = set(facts.calls)
    features = set(facts.features)
    scores: Counter[str] = Counter()
    evidence: list[str] = []

    add_path_role_scores(scores, evidence, path_parts)
    if returns_annotation == "bool" or "predicate_return" in features:
        add_role_score(scores, evidence, "predicate", ROLE_SCORE_STRONG, "predicate-shape")
    if collection_annotation(returns_annotation):
        add_role_score(scores, evidence, "collector_inventory", 2, "collection-annotation")
    add_common_body_role_scores(scores, evidence, calls, features)
    add_function_body_role_scores(scores, evidence, features)
    if not scores:
        add_role_score(scores, evidence, "general_helper", 1, "unclassified")
    return scores, evidence


def add_role_score(
    scores: Counter[str],
    evidence: list[str],
    role: str,
    points: int,
    reason: str,
) -> None:
    """Add one role score and evidence token."""
    scores[role] += points
    evidence.append(f"{role}:{reason}")


def add_path_role_scores(
    scores: Counter[str],
    evidence: list[str],
    path_parts: tuple[str, ...],
) -> None:
    """Add role scores implied by repository path domain."""
    if "tools" in path_parts or "agent_tools" in path_parts:
        add_role_score(scores, evidence, "workflow_tooling", 1, "tool-path")
    if "tests" in path_parts:
        add_role_score(scores, evidence, "test_support", 1, "test-path")


def add_common_body_role_scores(
    scores: Counter[str],
    evidence: list[str],
    calls: set[str],
    features: set[str],
) -> None:
    """Add role scores shared by function and class body facts."""
    add_effect_role_scores(scores, evidence, features)
    add_transform_role_scores(scores, evidence, features)
    add_structure_role_scores(scores, evidence, calls, features)


def add_effect_role_scores(
    scores: Counter[str],
    evidence: list[str],
    features: set[str],
) -> None:
    """Add role scores for effect and reporting behavior."""
    if "subprocess" in features:
        add_role_score(scores, evidence, "command_runner", ROLE_SCORE_STRONG, "subprocess-call")
    if "network" in features:
        add_role_score(scores, evidence, "command_runner", 1, "network-call")
    if "cli_parser" in features:
        add_role_score(scores, evidence, "cli_parser", ROLE_SCORE_DOMINANT, "argparse-call")
    if "write" in features or "filesystem_mutation" in features:
        add_role_score(scores, evidence, "writer_mutator", 2, "write-or-filesystem-call")
    if "resource_lifecycle" in features:
        add_role_score(scores, evidence, "writer_mutator", ROLE_SCORE_STRONG, "resource-lifecycle")
    if "callback_emission" in features:
        add_role_score(scores, evidence, "formatter_reporter", ROLE_SCORE_STRONG, "callback-emission")
    if "call_statement" in features:
        add_role_score(scores, evidence, "adapter_bridge", 2, "call-statement")
    if "logging" in features or "stdio" in features:
        add_role_score(scores, evidence, "formatter_reporter", 1, "human-output")


def add_transform_role_scores(
    scores: Counter[str],
    evidence: list[str],
    features: set[str],
) -> None:
    """Add role scores for conversion and parsing behavior."""
    if "serialization" in features and "read" in features:
        add_role_score(scores, evidence, "parser_loader", 2, "serialization-read")
    elif "serialization" in features:
        add_role_score(scores, evidence, "formatter_reporter", 2, "serialization-transform")
    if "path_operation" in features:
        add_role_score(scores, evidence, "converter_normalizer", ROLE_SCORE_STRONG, "path-operation")
    if "text_transform" in features or "encoding_transform" in features:
        add_role_score(scores, evidence, "converter_normalizer", 2, "text-or-encoding-transform")
    if "type_introspection" in features:
        add_role_score(scores, evidence, "converter_normalizer", 2, "type-introspection")
    if "conditional_return" in features or "environment" in features:
        add_role_score(scores, evidence, "converter_normalizer", 2, "conditional-or-environment-normalization")
    if "identity_return" in features:
        add_role_score(scores, evidence, "converter_normalizer", 2, "identity-return")
    if "digest_transform" in features or "security_transform" in features:
        add_role_score(scores, evidence, "converter_normalizer", ROLE_SCORE_STRONG, "digest-or-security-transform")
    if "pointer_interop" in features or "data_shape_transform" in features:
        add_role_score(scores, evidence, "converter_normalizer", ROLE_SCORE_DOMINANT, "interop-or-shape-transform")
    if "read" in features:
        add_role_score(scores, evidence, "parser_loader", 2, "read-call")


def add_structure_role_scores(
    scores: Counter[str],
    evidence: list[str],
    calls: set[str],
    features: set[str],
) -> None:
    """Add role scores for static, numeric, and return-shape behavior."""
    if "static_analysis" in features or any(call.startswith("ast.") for call in calls):
        add_role_score(scores, evidence, "static_analyzer", ROLE_SCORE_BOUNDARY, "ast-call")
    if "numeric" in features:
        add_role_score(scores, evidence, "numeric_kernel", ROLE_SCORE_STRONG, "numeric-call")
    if "operator_expression" in features:
        add_role_score(scores, evidence, "numeric_kernel", 2, "operator-expression")
    if "mapping_return" in features:
        add_role_score(scores, evidence, "formatter_reporter", 2, "mapping-return")
    if "collection_return" in features or "generator" in features or "iteration" in features:
        add_role_score(scores, evidence, "collector_inventory", 2, "collection-or-iteration")
    if "nested_function_definition" in features:
        add_role_score(scores, evidence, "factory_builder", ROLE_SCORE_DOMINANT, "nested-callable-definition")
    if "raises" in features:
        add_role_score(scores, evidence, "validator_checker", 2, "raises")


def add_function_body_role_scores(
    scores: Counter[str],
    evidence: list[str],
    features: set[str],
) -> None:
    """Add function-only role scores."""
    if "state_mutation" in features or "mutation_call" in features:
        add_role_score(scores, evidence, "writer_mutator", 1, "mutation-call")
    if "call_return" in features and not ({"read", "write", "numeric", "static_analysis"} & features):
        add_role_score(scores, evidence, "factory_builder", 1, "call-return")


def collection_annotation(annotation: str) -> bool:
    """Return whether an annotation describes a collection-like return."""
    lowered = annotation.lower()
    return lowered.startswith(("tuple", "list", "set", "frozenset")) or "sequence" in lowered


def class_role_scores(
    *,
    path: str,
    bases: tuple[str, ...],
    decorators: tuple[str, ...],
    annotated_field_count: int,
    facts: BodyFacts,
) -> tuple[Counter[str], list[str]]:
    """Infer class roles from inheritance, decorators, fields, and bodies."""
    path_parts = tuple(Path(path).parts)
    calls = set(facts.calls)
    features = set(facts.features)
    scores: Counter[str] = Counter()
    evidence: list[str] = []

    add_path_role_scores(scores, evidence, path_parts)
    add_class_boundary_role_scores(scores, evidence, bases, decorators, annotated_field_count)
    add_common_body_role_scores(scores, evidence, calls, features)
    add_class_body_role_scores(scores, evidence, features)
    if not scores:
        add_role_score(scores, evidence, "general_helper", 1, "unclassified")
    return scores, evidence


def add_class_boundary_role_scores(
    scores: Counter[str],
    evidence: list[str],
    bases: tuple[str, ...],
    decorators: tuple[str, ...],
    annotated_field_count: int,
) -> None:
    """Add class role scores from inheritance, decorators, and fields."""
    if any(base == "Protocol" or base.endswith(".Protocol") for base in bases):
        add_role_score(scores, evidence, "protocol_interface", ROLE_SCORE_DOMINANT, "protocol-base")
    if any(base.endswith(("Exception", "Error")) or base in {"BaseException", "Exception"} for base in bases):
        add_role_score(scores, evidence, "exception_type", ROLE_SCORE_BOUNDARY, "exception-base")
    if any(base.endswith(("Answer", "Config", "Info", "Problem", "SolveConfig", "State")) for base in bases):
        add_role_score(scores, evidence, "data_container", ROLE_SCORE_DOMINANT, "algorithm-data-container-base")
    if any(decorator.endswith(("dataclass", "define")) for decorator in decorators):
        add_role_score(scores, evidence, "data_container", ROLE_SCORE_DOMINANT, "data-class-decorator")
    if annotated_field_count:
        add_role_score(scores, evidence, "data_container", 2, "annotated-fields")


def add_class_body_role_scores(
    scores: Counter[str],
    evidence: list[str],
    features: set[str],
) -> None:
    """Add class-only role scores from body facts."""
    if "state_mutation" in features or "mutation_call" in features:
        add_role_score(scores, evidence, "state_holder", 1, "state-mutation")


def is_candidate_symbol(
    *,
    kind: str,
    name: str,
    scope: str,
    role: str,
) -> bool:
    """Return whether a symbol initially looks helper-like before usage filtering."""
    if name.startswith("__") and name.endswith("__"):
        return False
    if scope == "nested":
        return True
    if name.startswith("_") and not (name.startswith("__") and name.endswith("__")):
        return True
    if kind == "function" and role in PUBLIC_LOCAL_HELPER_ROLES:
        return True
    if kind == "class" and role in CLASS_LOCAL_HELPER_ROLES:
        return True
    return False


def confidence(
    *,
    name: str,
    scope: str,
    scores: Counter[str],
    facts: BodyFacts,
    candidate: bool,
) -> float:
    """Return a conservative helper confidence score."""
    if not candidate:
        return 0.0
    score = BASE_HELPER_CONFIDENCE
    if name.startswith("_"):
        score += PRIVATE_NAME_CONFIDENCE_BONUS
    if scope == "nested":
        score += NESTED_SCOPE_CONFIDENCE_BONUS
    if scores:
        score += min(ROLE_SCORE_CONFIDENCE_CAP, max(scores.values()) / ROLE_SCORE_CONFIDENCE_DIVISOR)
    if facts.calls:
        score += CALL_CONFIDENCE_BONUS
    if facts.features:
        score += FEATURE_CONFIDENCE_BONUS
    return round(min(score, MAX_HELPER_CONFIDENCE), 2)


def collect_identifier_tokens(name: str) -> list[str]:
    """Return searchable lowercase tokens from one Python identifier."""
    stripped = name.strip("_")
    if not stripped:
        return []
    tokens: list[str] = []
    for part in re.split(r"[^0-9A-Za-z]+|_", stripped):
        if not part:
            continue
        tokens.extend(match.group(0).lower() for match in IDENTIFIER_TOKEN_RE.finditer(part))
    return tokens


def collect_role_name_tokens(role: str) -> list[str]:
    """Return the role/action vocabulary that should make a name searchable."""
    if role in ROLE_NAME_TOKENS:
        return sorted(set(ROLE_NAME_TOKENS[role]))
    return sorted(set(collect_identifier_tokens(role)))


def collect_name_search_metadata(
    name: str,
    role: str,
) -> tuple[list[str], list[str], list[str], bool, str]:
    """Return identifier tokens and role-token alignment metadata."""
    name_parts = collect_identifier_tokens(name)
    role_parts = collect_role_name_tokens(role)
    matches = sorted(set(name_parts) & set(role_parts))
    if matches:
        return name_parts, role_parts, matches, True, "role-token-match:" + ",".join(matches)
    return name_parts, role_parts, [], False, f"role-token-review:{role}"


class DefinitionCollector(ast.NodeVisitor):
    """Collect Python function definitions from one AST."""

    def __init__(self, root: Path, path: Path) -> None:
        """Initialize definition collection for one source file."""
        self.root = root
        self.path = path
        self.relative_path = stable_relative(root, path)
        self.stack: list[str] = []
        self.records: list[FunctionRecord] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Collect methods under class-qualified names."""
        self._record_class(node)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Collect one function."""
        self._record_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Collect one async function."""
        self._record_function(node, is_async=True)

    def _record_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        is_async: bool,
    ) -> None:
        parent_stack = tuple(self.stack)
        qualname, scope = function_qualname_and_scope(parent_stack, node.name)
        facts = body_facts(node)
        domain = path_domain(self.relative_path)
        returns_annotation = _annotation_text(node.returns)
        scores, evidence = role_scores(
            path=self.relative_path,
            returns_annotation=returns_annotation,
            facts=facts,
        )
        ordered_roles = [role for role, _count in scores.most_common()]
        role = ordered_roles[0]
        (
            name_tokens,
            expected_name_tokens,
            matched_name_tokens,
            searchable_name,
            name_search_rule,
        ) = collect_name_search_metadata(node.name, role)
        candidate = is_candidate_symbol(
            kind="function",
            name=node.name,
            scope=scope,
            role=role,
        )
        decorators = tuple(filter(None, (dotted_name(item) for item in node.decorator_list)))
        if is_async:
            evidence.append("async:function")
        self.records.append(
            FunctionRecord(
                path=self.relative_path,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                kind="function",
                domain=domain,
                name=node.name,
                qualname=qualname,
                scope=scope,
                visibility="private" if node.name.startswith("_") else "public",
                role=role,
                secondary_roles=ordered_roles[1:SECONDARY_ROLE_SLICE_STOP],
                name_tokens=name_tokens,
                role_name_tokens=expected_name_tokens,
                matched_role_name_tokens=matched_name_tokens,
                searchable_name=searchable_name,
                name_search_rule=name_search_rule,
                confidence=0.0,
                helper_candidate=candidate,
                candidate_rule="",
                needs_user_judgment=False,
                judgment_rule="",
                redundant_helper=False, redundancy_rule="", redundant_with=[],
                implementation_signature=implementation_signature(node),
                incoming_count=0,
                incoming_callers=[],
                incoming_call_sites=[],
                outgoing_internal=[],
                outgoing_call_sites=[f"{call}@{line}" for call, line in facts.call_locations],
                specialized_helper=False,
                specialization="not_evaluated",
                side_effects=sorted(feature for feature in facts.features if is_side_effect(feature)),
                features=sorted(facts.features),
                calls=sorted(set(facts.calls)),
                args=[arg.arg for arg in node.args.args],
                bases=[],
                method_count=0,
                public_method_count=0,
                decorators=list(decorators),
                returns_annotation=returns_annotation,
                doc_summary=_doc_summary(ast.get_docstring(node)),
                evidence=evidence,
            )
        )
        record = self.records[-1]
        record.confidence = confidence(
            name=node.name,
            scope=scope,
            scores=scores,
            facts=facts,
            candidate=candidate,
        )
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _record_class(self, node: ast.ClassDef) -> None:
        """Collect one class as a possible helper symbol."""
        parent_stack = tuple(self.stack)
        qualname = ".".join((*parent_stack, node.name)) if parent_stack else node.name
        scope = "module" if not parent_stack else "nested"
        domain = path_domain(self.relative_path)
        facts = class_body_facts(node)
        bases = tuple(filter(None, (dotted_name(item) for item in node.bases)))
        decorators = tuple(filter(None, (dotted_name(item) for item in node.decorator_list)))
        method_names = tuple(
            item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        annotated_field_count = sum(
            1 for item in node.body if isinstance(item, (ast.AnnAssign, ast.Assign))
        )
        scores, evidence = class_role_scores(
            path=self.relative_path,
            bases=bases,
            decorators=decorators,
            annotated_field_count=annotated_field_count,
            facts=facts,
        )
        ordered_roles = [role for role, _count in scores.most_common()]
        role = ordered_roles[0]
        (
            name_tokens,
            expected_name_tokens,
            matched_name_tokens,
            searchable_name,
            name_search_rule,
        ) = collect_name_search_metadata(node.name, role)
        candidate = is_candidate_symbol(
            kind="class",
            name=node.name,
            scope=scope,
            role=role,
        )
        self.records.append(
            FunctionRecord(
                path=self.relative_path,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                kind="class",
                domain=domain,
                name=node.name,
                qualname=qualname,
                scope=scope,
                visibility="private" if node.name.startswith("_") else "public",
                role=role,
                secondary_roles=ordered_roles[1:SECONDARY_ROLE_SLICE_STOP],
                name_tokens=name_tokens,
                role_name_tokens=expected_name_tokens,
                matched_role_name_tokens=matched_name_tokens,
                searchable_name=searchable_name,
                name_search_rule=name_search_rule,
                confidence=0.0,
                helper_candidate=candidate,
                candidate_rule="",
                needs_user_judgment=False,
                judgment_rule="",
                redundant_helper=False, redundancy_rule="", redundant_with=[],
                implementation_signature="",
                incoming_count=0,
                incoming_callers=[],
                incoming_call_sites=[],
                outgoing_internal=[],
                outgoing_call_sites=[f"{call}@{line}" for call, line in facts.call_locations],
                specialized_helper=False,
                specialization="not_evaluated",
                side_effects=sorted(feature for feature in facts.features if is_side_effect(feature)),
                features=sorted(facts.features),
                calls=sorted(set(facts.calls)),
                args=[],
                bases=list(bases),
                method_count=len(method_names),
                public_method_count=sum(1 for name in method_names if not name.startswith("_")),
                decorators=list(decorators),
                returns_annotation="",
                doc_summary=_doc_summary(ast.get_docstring(node)),
                evidence=evidence,
            )
        )
        record = self.records[-1]
        record.confidence = confidence(
            name=node.name,
            scope=scope,
            scores=scores,
            facts=facts,
            candidate=candidate,
        )


def function_qualname_and_scope(parent_stack: tuple[str, ...], name: str) -> tuple[str, str]:
    """Return a function qualname and module/method/nested scope."""
    qualname = ".".join((*parent_stack, name)) if parent_stack else name
    if parent_stack and parent_stack[-1][0].isupper():
        return qualname, "method"
    if parent_stack:
        return qualname, "nested"
    return qualname, "module"


def is_side_effect(feature: str) -> bool:
    """Return whether a feature represents visible side effects."""
    return feature in {
        "environment",
        "filesystem_mutation",
        "local_import",
        "logging",
        "mutation_call",
        "network",
        "state_mutation",
        "stdio",
        "subprocess",
        "write",
    }


def _doc_summary(docstring: str | None) -> str:
    """Return the first sentence-ish fragment from a docstring."""
    if not docstring:
        return ""
    compact = " ".join(docstring.strip().split())
    for separator in (". ", "。"):
        if separator in compact:
            return compact.split(separator, maxsplit=1)[0].strip() + separator.strip()
    return compact[:DOC_SUMMARY_LIMIT]


def analyze_file(root: Path, path: Path) -> list[FunctionRecord]:
    """Analyze one Python file."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return analyze_source(root, path, source)


def analyze_source(root: Path, path: Path, source: str) -> list[FunctionRecord]:
    """Analyze Python source text for one logical path."""
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    collector = DefinitionCollector(root, path)
    collector.visit(tree)
    return collector.records


def candidate_rule(record: FunctionRecord) -> str:
    """Return the deterministic rule that keeps a helper candidate."""
    if record.name.startswith("__") and record.name.endswith("__"):
        return ""
    if is_interface_boundary(record):
        return ""

    if record.scope == "nested":
        return nested_candidate_rule(record)

    local_symbol = record.specialization in LOCAL_SPECIALIZATIONS and record.incoming_count > 0
    if record.domain == "test":
        return test_candidate_rule(record, local_symbol)
    if record.domain == "experiment":
        return experiment_candidate_rule(record, local_symbol)
    if record.domain == "tooling":
        return tooling_candidate_rule(record, local_symbol)
    return main_candidate_rule(record, local_symbol)


def nested_candidate_rule(record: FunctionRecord) -> str:
    """Return a deterministic nested-symbol helper rule."""
    if (
        record.kind == "function"
        and record.role in PUBLIC_LOCAL_HELPER_ROLES
        and record.role not in LOW_SIGNAL_HELPER_ROLES
    ):
        return f"{record.domain}:nested-{record.role}"
    if record.kind == "class" and record.role in CLASS_LOCAL_HELPER_ROLES:
        return f"{record.domain}:nested-{record.role}"
    return ""


def test_candidate_rule(record: FunctionRecord, local_symbol: bool) -> str:
    """Return a deterministic test-directory helper rule."""
    decorator_names = {decorator.rsplit(".", maxsplit=1)[-1] for decorator in record.decorators}
    if record.kind == "function" and record.name.startswith("test_"):
        return ""
    if record.visibility == "private" and local_symbol:
        return f"test:private-local-{record.role}"
    if record.kind == "function":
        if "fixture" in decorator_names:
            return "test:fixture-function"
        if local_symbol and record.role in PUBLIC_LOCAL_HELPER_ROLES:
            return f"test:local-{record.role}"
        return ""
    if local_symbol:
        return "test:local-test-class"
    return ""


def experiment_candidate_rule(record: FunctionRecord, local_symbol: bool) -> str:
    """Return a deterministic experiment-directory helper rule."""
    if record.visibility == "private" and local_symbol and record.role not in LOW_SIGNAL_HELPER_ROLES:
        return f"experiment:private-local-{record.role}"
    if not local_symbol:
        return ""
    if record.kind == "function" and record.role in PUBLIC_LOCAL_HELPER_ROLES:
        return f"experiment:local-{record.role}"
    if record.kind == "class" and record.role in CLASS_LOCAL_HELPER_ROLES:
        return f"experiment:local-{record.role}"
    return ""


def tooling_candidate_rule(record: FunctionRecord, local_symbol: bool) -> str:
    """Return a deterministic tooling-directory helper rule."""
    if record.visibility == "private" and local_symbol and record.role not in LOW_SIGNAL_HELPER_ROLES:
        return f"tooling:private-local-{record.role}"
    if not local_symbol:
        return ""
    if record.kind == "function" and record.role in PUBLIC_LOCAL_HELPER_ROLES:
        return f"tooling:local-{record.role}"
    if record.kind == "class" and record.role in CLASS_LOCAL_HELPER_ROLES:
        return f"tooling:local-{record.role}"
    return ""


def main_candidate_rule(record: FunctionRecord, local_symbol: bool) -> str:
    """Return a deterministic main-code helper rule."""
    if record.visibility == "private" and local_symbol and record.role not in LOW_SIGNAL_HELPER_ROLES:
        return f"main:private-local-{record.role}"
    return ""


def design_judgment_rule(record: FunctionRecord) -> str:
    """Return the deterministic reason a symbol needs human design judgment."""
    if record.name.startswith("__") and record.name.endswith("__"):
        return ""
    if is_interface_boundary(record):
        return ""

    local_symbol = record.specialization in LOCAL_SPECIALIZATIONS and record.incoming_count > 0
    if record.domain == "main":
        return main_design_judgment_rule(record, local_symbol)
    if record.domain == "experiment":
        return experiment_design_judgment_rule(record, local_symbol)
    if record.domain == "test":
        return test_design_judgment_rule(record, local_symbol)
    if record.domain == "tooling":
        return tooling_design_judgment_rule(record, local_symbol)
    return ""


def main_design_judgment_rule(record: FunctionRecord, local_symbol: bool) -> str:
    """Return main-code symbols that look helper-like but need semantics."""
    if local_symbol and record.visibility == "public":
        if record.kind == "function" and record.role in PUBLIC_LOCAL_HELPER_ROLES:
            return f"main:public-local-{record.role}"
        if record.kind == "class" and record.role in CLASS_LOCAL_HELPER_ROLES:
            return f"main:public-local-{record.role}"
    if local_symbol and record.role in LOW_SIGNAL_HELPER_ROLES:
        return f"main:low-signal-local-{record.role}"
    if record.visibility == "private" and record.incoming_count > 0:
        if shared_private_numeric_contract(record):
            return ""
        return f"main:shared-private-{record.role}"
    return ""


def shared_private_numeric_contract(record: FunctionRecord) -> bool:
    """Return whether a private numeric primitive has enough local ownership."""
    return (
        record.kind == "function"
        and record.incoming_count > LOCAL_CALLER_CLUSTER_LIMIT
        and (
            record.role == "numeric_kernel"
            or "numeric_kernel" in record.secondary_roles
        )
        and not record.redundant_helper
    )


def experiment_design_judgment_rule(record: FunctionRecord, local_symbol: bool) -> str:
    """Return experiment symbols that need semantics after static analysis."""
    if local_symbol and record.role in {"general_helper", "numeric_kernel"}:
        return f"experiment:low-signal-local-{record.role}"
    return ""


def test_design_judgment_rule(record: FunctionRecord, local_symbol: bool) -> str:
    """Return test symbols that need human review after static analysis."""
    if record.kind == "function" and record.name.startswith("test_"):
        return ""
    if local_symbol and record.role in {"general_helper", "numeric_kernel"}:
        return f"test:low-signal-local-{record.role}"
    return ""


def tooling_design_judgment_rule(record: FunctionRecord, local_symbol: bool) -> str:
    """Return tooling symbols that need human review after static analysis."""
    if local_symbol and record.role in {"general_helper", "numeric_kernel"}:
        return f"tooling:low-signal-local-{record.role}"
    return ""


def is_interface_boundary(record: FunctionRecord) -> bool:
    """Return whether a class is a type/interface boundary rather than a helper."""
    return record.kind == "class" and record.role == "protocol_interface"


def verdict(record: FunctionRecord) -> str:
    """Return the final deterministic inventory verdict."""
    if record.redundant_helper:
        return "redundant_helper"
    if record.helper_candidate:
        return "auto_helper"
    if record.needs_user_judgment:
        return "needs_user_judgment"
    return "not_helper"


def should_report_name_gap(record: FunctionRecord) -> bool:
    """Return whether a helper symbol is selected for role/action name review."""
    return (
        not record.searchable_name
        and (
            record.helper_candidate
            or record.needs_user_judgment
            or record.redundant_helper
        )
    )


def apply_call_graph(records: list[FunctionRecord]) -> None:
    """Attach simple static incoming and outgoing call counts."""
    maps = call_graph_maps(records)
    edges = collect_call_edges(records, maps)
    for index, record in enumerate(records):
        attach_call_edges(record, index, edges)
    attach_redundancy(records)
    for record in records:
        attach_verdict(record)


@dataclass
class CallGraphMaps:
    """Internal call lookup maps."""

    by_name: dict[str, list[FunctionRecord]]
    by_qualname: dict[str, FunctionRecord]


@dataclass
class CallGraphEdges:
    """Internal call graph edge accumulator."""

    incoming_sites: dict[int, set[str]]
    incoming_callers: dict[int, set[str]]
    outgoing: dict[int, set[str]]


def call_graph_maps(records: list[FunctionRecord]) -> CallGraphMaps:
    """Return name and qualname lookup maps for records."""
    by_name: dict[str, list[FunctionRecord]] = {}
    by_qualname: dict[str, FunctionRecord] = {}
    for record in records:
        bucket = by_name.setdefault(record.name, [])
        bucket.append(record)
        by_qualname[record.qualname] = record
    return CallGraphMaps(by_name=by_name, by_qualname=by_qualname)


def collect_call_edges(records: list[FunctionRecord], maps: CallGraphMaps) -> CallGraphEdges:
    """Return internal call graph edges for all records."""
    edges = CallGraphEdges(incoming_sites={}, incoming_callers={}, outgoing={})
    for index, record in enumerate(records):
        matches: set[str] = set()
        for call_site in record.outgoing_call_sites:
            add_call_site_edges(record, call_site, maps, matches, edges)
        edges.outgoing[index] = matches
    return edges


def add_call_site_edges(
    record: FunctionRecord,
    call_site: str,
    maps: CallGraphMaps,
    matches: set[str],
    edges: CallGraphEdges,
) -> None:
    """Record internal edges produced by one outgoing call site."""
    call, _separator, line_text = call_site.partition("@")
    line = int(line_text) if line_text.isdigit() else record.line
    candidates = internal_call_candidates(maps.by_name, maps.by_qualname, record, call)
    for candidate in candidates:
        if accepts_internal_candidate(record, candidate, candidates):
            matches.add(candidate.qualname)
            edges.incoming_sites.setdefault(id(candidate), set()).add(
                f"{record.path}:{line}:{record.qualname}"
            )
            edges.incoming_callers.setdefault(id(candidate), set()).add(
                f"{record.path}:{record.qualname}"
            )


def accepts_internal_candidate(
    record: FunctionRecord,
    candidate: FunctionRecord,
    candidates: list[FunctionRecord],
) -> bool:
    """Return whether one candidate should count as an internal call target."""
    if candidate is record:
        return False
    return candidate.path == record.path or len(candidates) == 1


def attach_call_edges(record: FunctionRecord, index: int, edges: CallGraphEdges) -> None:
    """Attach incoming and outgoing edge facts to one record."""
    sites = sorted(edges.incoming_sites.get(id(record), set()))
    callers = sorted(edges.incoming_callers.get(id(record), set()))
    record.incoming_count = len(sites)
    record.incoming_callers = callers
    record.incoming_call_sites = sites
    record.outgoing_internal = sorted(edges.outgoing[index])
    record.specialized_helper, record.specialization = specialization(record)


def attach_verdict(record: FunctionRecord) -> None:
    """Attach final candidate and judgment facts to one record."""
    rule = candidate_rule(record)
    if record.redundant_helper and not rule:
        judgment = f"{record.domain}:{record.redundancy_rule}"
    else:
        judgment = "" if rule else design_judgment_rule(record)
    record.helper_candidate = bool(rule)
    record.candidate_rule = rule
    record.needs_user_judgment = bool(judgment)
    record.judgment_rule = judgment
    if rule:
        record.evidence.insert(0, f"candidate-rule:{rule}")
        if record.confidence == 0.0:
            record.confidence = DEFAULT_HALF_CONFIDENCE
    elif judgment:
        record.evidence.insert(0, f"judgment-rule:{judgment}")
        if record.confidence == 0.0:
            record.confidence = JUDGMENT_CONFIDENCE
    else:
        record.confidence = 0.0
        record.specialized_helper = False
        record.specialization = "not_helper_candidate"
    if record.helper_candidate and record.visibility == "private" and record.incoming_count == 0:
        record.evidence.append("usage:no-internal-callers")
    if record.specialized_helper:
        record.evidence.append(f"usage:{record.specialization}")
    if record.redundant_helper:
        record.evidence.append(f"redundant:{record.redundancy_rule}")
        if record.redundant_with:
            record.evidence.append(
                "redundant-with:" + ";".join(record.redundant_with[:REDUNDANT_WITH_EVIDENCE_LIMIT])
            )
    if record.helper_candidate or record.needs_user_judgment or record.redundant_helper:
        record.evidence.append(f"name-search:{record.name_search_rule}")


def attach_redundancy(records: list[FunctionRecord]) -> None:
    """Attach redundant helper shape facts before final verdict assignment."""
    duplicate_groups = implementation_duplicate_groups(records)
    for record in records:
        duplicate_peers = duplicate_groups.get(record.implementation_signature, ())
        record.redundant_with = [
            peer.qualname for peer in duplicate_peers if peer is not record
        ]
        rule = redundancy_rule(record)
        record.redundant_helper = bool(rule)
        record.redundancy_rule = rule


def implementation_duplicate_groups(
    records: list[FunctionRecord],
) -> dict[str, tuple[FunctionRecord, ...]]:
    """Return duplicated function implementation groups."""
    return duplicate_implementation_groups(implementation_signature_groups(records))


def implementation_signature_groups(
    records: list[FunctionRecord],
) -> dict[str, list[FunctionRecord]]:
    """Group function records by normalized implementation signature."""
    signature_records = sorted(
        (
            (record.implementation_signature, record)
            for record in records
            if duplicate_group_record(record)
        ),
        key=lambda item: item[0],
    )
    return {
        signature: [record for _signature, record in grouped_records]
        for signature, grouped_records in itertools.groupby(
            signature_records,
            key=lambda item: item[0],
        )
    }


def duplicate_group_record(record: FunctionRecord) -> bool:
    """Return whether one record participates in duplicate body grouping."""
    if record.kind != "function" or not record.implementation_signature:
        return False
    return record.scope != "method" and record.domain != "test"


def duplicate_implementation_groups(
    grouped: dict[str, list[FunctionRecord]],
) -> dict[str, tuple[FunctionRecord, ...]]:
    """Filter implementation signature groups down to duplicates."""
    return {
        signature: tuple(items)
        for signature, items in grouped.items()
        if len(items) > 1
    }


def redundancy_rule(record: FunctionRecord) -> str:
    """Return deterministic redundant-helper rule for one record."""
    if record.kind != "function":
        return ""
    if not redundancy_eligible_symbol(record):
        return ""
    features = set(record.features)
    simple_body = "single_statement_body" in features
    if simple_body and "identity_return" in features:
        return "identity-return"
    if simple_body and "pass_through_call_return" in features:
        return pass_through_redundancy_rule(record, "return")
    if simple_body and "pass_through_call_statement" in features:
        return pass_through_redundancy_rule(record, "statement")
    if record.redundant_with:
        return "duplicate-implementation"
    return ""


def redundancy_eligible_symbol(record: FunctionRecord) -> bool:
    """Return whether a function belongs to the helper-like redundancy surface."""
    if record.scope == "nested" or record.visibility == "private":
        return True
    local_symbol = record.specialization in LOCAL_SPECIALIZATIONS and record.incoming_count > 0
    return local_symbol and record.role in PUBLIC_LOCAL_HELPER_ROLES


def pass_through_redundancy_rule(record: FunctionRecord, shape: str) -> str:
    """Return a pass-through wrapper redundancy rule."""
    if record.outgoing_internal:
        return f"pass-through-{shape}-internal"
    return f"pass-through-{shape}-external"


def internal_call_candidates(
    by_name: dict[str, list[FunctionRecord]],
    by_qualname: dict[str, FunctionRecord],
    caller: FunctionRecord,
    call: str,
) -> list[FunctionRecord]:
    """Return internal function candidates for one call expression."""
    if "." not in call:
        return by_name.get(call, [])
    if call in by_qualname:
        return [by_qualname[call]]
    if call.startswith(("self.", "cls.")):
        method_name = call.split(".", maxsplit=1)[1]
        if "." in method_name:
            return []
        class_name = enclosing_class(caller.qualname)
        if not class_name:
            return []
        return [
            candidate
            for candidate in by_name.get(method_name, [])
            if candidate.scope == "method"
            and enclosing_class(candidate.qualname) == class_name
        ]
    return []


def enclosing_class(qualname: str) -> str:
    """Return the nearest class-looking qualifier."""
    parts = qualname.split(".")
    for part in reversed(parts[:-1]):
        if part[:1].isupper():
            return part
    return ""


def specialization(record: FunctionRecord) -> tuple[bool, str]:
    """Return whether helper usage looks caller-specific."""
    if record.scope == "nested":
        return True, "nested_local_helper"
    if not record.incoming_call_sites:
        return False, "no_internal_call_sites"
    if len(record.incoming_callers) == 1:
        return True, "single_caller_helper"
    caller_files = {caller.split(":", maxsplit=1)[0] for caller in record.incoming_callers}
    if len(caller_files) == 1 and len(record.incoming_callers) <= LOCAL_CALLER_CLUSTER_LIMIT:
        return True, "file_local_helper_cluster"
    return False, "shared_helper"


def build_inventory(root: Path, options: InventoryBuildOptions) -> Inventory:
    """Build the helper inventory."""
    files, report_paths = inventory_files(root, options)
    baseline_records = baseline_inventory_records(root, files, options.baseline_ref)
    all_records: list[FunctionRecord] = []
    for path in files:
        all_records.extend(analyze_file(root, path))
    apply_call_graph(all_records)
    include_auto_symbols = not options.only_user_judgment
    include_judgment_symbols = not options.only_auto_helpers
    selected = select_records(
        all_records,
        all_functions=options.all_functions,
        include_auto_helpers=include_auto_symbols,
        include_user_judgment=include_judgment_symbols,
        only_name_gaps=options.only_name_gaps,
        min_confidence=options.min_confidence,
        report_paths=report_paths,
    )
    baseline_selected = select_records(
        baseline_records,
        all_functions=options.all_functions,
        include_auto_helpers=include_auto_symbols,
        include_user_judgment=include_judgment_symbols,
        only_name_gaps=options.only_name_gaps,
        min_confidence=options.min_confidence,
        report_paths=report_paths,
    )
    baseline_keys = {record_key(record) for record in baseline_selected}
    before_baseline_filter = len(selected)
    if options.baseline_ref:
        selected = [record for record in selected if record_key(record) not in baseline_keys]
    selected.sort(key=lambda item: (item.path, item.line, item.qualname))
    role_counts = Counter(record.role for record in selected)
    verdict_counts = Counter(verdict(record) for record in selected)
    return Inventory(
        root=root.as_posix(),
        changed_only=options.changed_only,
        baseline_ref=options.baseline_ref,
        baseline_symbols_seen=len(baseline_records),
        baseline_filtered=before_baseline_filter - len(selected),
        files_scanned=len(files),
        symbols_seen=len(all_records),
        functions_seen=sum(1 for record in all_records if record.kind == "function"),
        classes_seen=sum(1 for record in all_records if record.kind == "class"),
        symbols_reported=len(selected),
        helpers_reported=sum(1 for record in selected if record.helper_candidate),
        judgment_required_reported=sum(1 for record in selected if record.needs_user_judgment),
        name_gaps_reported=sum(1 for record in selected if should_report_name_gap(record)),
        role_counts=dict(sorted(role_counts.items())),
        verdict_counts=dict(sorted(verdict_counts.items())),
        records=selected,
    )


def inventory_files(root: Path, options: InventoryBuildOptions) -> tuple[list[Path], set[str]]:
    """Return files to analyze and changed-only report path filter."""
    if not options.changed_only:
        files = iter_python_files(
            root,
            options.paths,
            include_vendor=options.include_vendor,
            include_hidden=options.include_hidden,
            include_pyi=options.include_pyi,
        )
        return files, set()
    changed_files = filtered_changed_python_files(root, options)
    report_paths = {stable_relative(root, path) for path in changed_files}
    if not changed_files:
        return [], report_paths
    files = iter_python_files(
        root,
        [],
        include_vendor=options.include_vendor,
        include_hidden=options.include_hidden,
        include_pyi=options.include_pyi,
    )
    return files, report_paths


def filtered_changed_python_files(root: Path, options: InventoryBuildOptions) -> list[Path]:
    """Return changed Python files constrained by requested paths."""
    changed_files = changed_python_files(
        root,
        include_vendor=options.include_vendor,
        include_hidden=options.include_hidden,
        include_pyi=options.include_pyi,
    )
    requested_paths = requested_relative_paths(
        root,
        options.paths,
        include_vendor=options.include_vendor,
        include_hidden=options.include_hidden,
        include_pyi=options.include_pyi,
    )
    if not requested_paths:
        return changed_files
    return [path for path in changed_files if stable_relative(root, path) in requested_paths]


def baseline_inventory_records(
    root: Path,
    files: list[Path],
    baseline_ref: str,
) -> list[FunctionRecord]:
    """Return baseline records for the same logical files."""
    records: list[FunctionRecord] = []
    if not baseline_ref:
        return records
    renamed_paths = git_renamed_paths(root, baseline_ref)
    for path in files:
        relative = stable_relative(root, path)
        source = git_ref_text(root, baseline_ref, relative)
        if source is None and relative in renamed_paths:
            source = git_ref_text(root, baseline_ref, renamed_paths[relative])
        if source is None:
            continue
        records.extend(analyze_source(root, path, source))
    apply_call_graph(records)
    return records


def select_records(
    records: list[FunctionRecord],
    *,
    all_functions: bool,
    include_auto_helpers: bool,
    include_user_judgment: bool,
    only_name_gaps: bool,
    min_confidence: float,
    report_paths: set[str],
) -> list[FunctionRecord]:
    """Return records matching report filters."""
    selected = [
        record
        for record in records
        if (
            all_functions
            or (include_auto_helpers and record.helper_candidate)
            or (include_user_judgment and record.needs_user_judgment)
        )
        and (not only_name_gaps or should_report_name_gap(record))
        and record.confidence >= min_confidence
        and (not report_paths or record.path in report_paths)
    ]
    return sorted(selected, key=lambda item: (item.path, item.line, item.qualname))


def record_key(record: FunctionRecord) -> tuple[str, str, str, str, str, str, str]:
    """Return a stable key for baseline finding comparison."""
    return (
        record.path,
        record.kind,
        record.qualname,
        verdict(record),
        record.role,
        record.candidate_rule,
        record.judgment_rule,
    )


def render_text(inventory: Inventory) -> str:
    """Render stable text output."""
    lines: list[str] = []
    for record in inventory.records:
        side_effects = ",".join(record.side_effects) if record.side_effects else "none"
        features = ",".join(record.features) if record.features else "none"
        outgoing = ",".join(record.outgoing_internal) if record.outgoing_internal else "none"
        evidence = ",".join(record.evidence[:EVIDENCE_RENDER_LIMIT]) if record.evidence else "none"
        matched_name_tokens = (
            ",".join(record.matched_role_name_tokens)
            if record.matched_role_name_tokens
            else "none"
        )
        lines.append(
            "SYMBOL="
            f"{record.path}:{record.line}:{record.qualname} "
            f"kind={record.kind} domain={record.domain} "
            f"verdict={verdict(record)} "
            f"role={record.role} confidence={record.confidence:.2f} "
            f"searchable_name={str(record.searchable_name).lower()} "
            f"name_search_rule={record.name_search_rule} "
            f"matched_name_tokens={matched_name_tokens} "
            f"candidate_rule={record.candidate_rule or 'none'} "
            f"judgment_rule={record.judgment_rule or 'none'} "
            f"redundant={str(record.redundant_helper).lower()} "
            f"redundancy_rule={record.redundancy_rule or 'none'} "
            f"redundant_with={';'.join(record.redundant_with) or 'none'} "
            f"scope={record.scope} visibility={record.visibility} "
            f"incoming={record.incoming_count} outgoing={outgoing} "
            f"specialization={record.specialization} "
            f"callers={';'.join(record.incoming_callers) or 'none'} "
            f"side_effects={side_effects} features={features} evidence={evidence}"
        )
    role_summary = ",".join(f"{role}:{count}" for role, count in inventory.role_counts.items())
    verdict_summary = ",".join(
        f"{item}:{count}" for item, count in inventory.verdict_counts.items()
    )
    lines.extend(
        [
            f"HELPER_INVENTORY_FILES={inventory.files_scanned}",
            f"HELPER_INVENTORY_SYMBOLS={inventory.symbols_seen}",
            f"HELPER_INVENTORY_FUNCTIONS={inventory.functions_seen}",
            f"HELPER_INVENTORY_CLASSES={inventory.classes_seen}",
            f"HELPER_INVENTORY_SYMBOLS_REPORTED={inventory.symbols_reported}",
            f"HELPER_INVENTORY_HELPERS={inventory.helpers_reported}",
            f"HELPER_INVENTORY_JUDGMENT_REQUIRED={inventory.judgment_required_reported}",
            f"HELPER_INVENTORY_NAME_GAPS={inventory.name_gaps_reported}",
            f"HELPER_INVENTORY_CHANGED_ONLY={str(inventory.changed_only).lower()}",
            f"HELPER_INVENTORY_BASELINE_REF={inventory.baseline_ref or 'none'}",
            f"HELPER_INVENTORY_BASELINE_SYMBOLS={inventory.baseline_symbols_seen}",
            f"HELPER_INVENTORY_BASELINE_FILTERED={inventory.baseline_filtered}",
            f"HELPER_INVENTORY_ROLES={role_summary}",
            f"HELPER_INVENTORY_VERDICTS={verdict_summary}",
            "HELPER_INVENTORY=pass",
        ]
    )
    return "\n".join(lines) + "\n"


def markdown_cell(value: object) -> str:
    """Escape a Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(inventory: Inventory) -> str:
    """Render Markdown output."""
    summary_rows = [
        ["files scanned", inventory.files_scanned],
        ["symbols seen", inventory.symbols_seen],
        ["functions seen", inventory.functions_seen],
        ["classes seen", inventory.classes_seen],
        ["symbols reported", inventory.symbols_reported],
        ["auto helpers reported", inventory.helpers_reported],
        ["user judgment required", inventory.judgment_required_reported],
        ["name gaps reported", inventory.name_gaps_reported],
        ["changed only", str(inventory.changed_only).lower()],
        ["baseline ref", inventory.baseline_ref or "none"],
        ["baseline symbols seen", inventory.baseline_symbols_seen],
        ["baseline filtered", inventory.baseline_filtered],
    ]
    verdict_rows: list[list[object]] = [
        [name, count] for name, count in sorted(inventory.verdict_counts.items())
    ] or [["none", 0]]
    role_rows: list[list[object]] = [
        [name, count] for name, count in sorted(inventory.role_counts.items())
    ] or [["none", 0]]
    lines = [
        "# Helper Symbol Inventory",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    lines.extend(
        f"| {markdown_cell(metric)} | {markdown_cell(value)} |"
        for metric, value in summary_rows
    )
    lines.extend(["", "## Verdict Counts", "", "| Verdict | Count |", "| --- | --- |"])
    lines.extend(
        f"| {markdown_cell(item)} | {markdown_cell(count)} |"
        for item, count in verdict_rows
    )
    lines.extend(["", "## Role Counts", "", "| Role | Count |", "| --- | --- |"])
    lines.extend(
        f"| {markdown_cell(role)} | {markdown_cell(count)} |"
        for role, count in role_rows
    )
    lines.extend(
        [
            "",
            "## Records",
            "",
            "| Path | Line | Kind | Domain | Verdict | Helper | Role | Searchable name | Name search rule | Matched name tokens | Candidate rule | Judgment rule | Redundancy rule | Redundant with | Confidence | Incoming | Specialization | Side effects | Features | Evidence |",
            "| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for record in inventory.records:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(record.path),
                    str(record.line),
                    markdown_cell(record.kind),
                    markdown_cell(record.domain),
                    markdown_cell(verdict(record)),
                    markdown_cell(record.qualname),
                    markdown_cell(record.role),
                    markdown_cell(str(record.searchable_name).lower()),
                    markdown_cell(record.name_search_rule),
                    markdown_cell(", ".join(record.matched_role_name_tokens) or "none"),
                    markdown_cell(record.candidate_rule or "none"),
                    markdown_cell(record.judgment_rule or "none"),
                    markdown_cell(record.redundancy_rule or "none"),
                    markdown_cell(", ".join(record.redundant_with) or "none"),
                    f"{record.confidence:.2f}",
                    str(record.incoming_count),
                    markdown_cell(record.specialization),
                    markdown_cell(", ".join(record.side_effects) or "none"),
                    markdown_cell(", ".join(record.features) or "none"),
                    markdown_cell(", ".join(record.evidence[:MARKDOWN_EVIDENCE_LIMIT]) or "none"),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def git_sha(root: Path) -> str:
    """Return current HEAD when available for JSON provenance."""
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def main() -> int:
    """Run the helper inventory."""
    parser = build_parser()
    args = parser.parse_args()
    if args.only_auto_helpers and args.only_user_judgment:
        parser.error("--only-auto-helpers and --only-user-judgment are mutually exclusive.")
    root = Path(args.root).resolve()
    inventory = build_inventory(
        root,
        InventoryBuildOptions(
            paths=args.paths,
            all_functions=args.all_functions,
            only_auto_helpers=args.only_auto_helpers,
            only_user_judgment=args.only_user_judgment,
            only_name_gaps=args.only_name_gaps,
            changed_only=args.changed,
            baseline_ref=args.baseline_ref,
            include_vendor=args.include_vendor,
            include_hidden=args.include_hidden,
            include_pyi=args.include_pyi,
            min_confidence=args.min_confidence,
        ),
    )
    if args.format == "json":
        payload = asdict(inventory)
        payload["head"] = git_sha(root)
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif args.format == "markdown":
        print(render_markdown(inventory), end="")
    else:
        print(render_text(inventory), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
