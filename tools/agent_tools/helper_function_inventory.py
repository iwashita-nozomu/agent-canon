#!/usr/bin/env python3
# @dependency-start
# responsibility Inventories Python helper functions with static role analysis.
# upstream design ../../documents/tools/README.md AgentCanon tool entrypoint policy
# upstream design ../../documents/coding-conventions-python.md helper and role naming policy
# downstream implementation ../../tests/agent_tools/test_helper_function_inventory.py tests inventory behavior
# @dependency-end
"""Inventory Python helper functions and infer their static roles."""

from __future__ import annotations

import argparse
import ast
import json
import os
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
HELPER_NAME_PREFIXES = (
    "add",
    "as",
    "build",
    "check",
    "collect",
    "convert",
    "copy",
    "create",
    "dump",
    "emit",
    "ensure",
    "extract",
    "find",
    "format",
    "gather",
    "get",
    "has",
    "infer",
    "is",
    "iter",
    "load",
    "make",
    "normalize",
    "parse",
    "read",
    "render",
    "resolve",
    "scan",
    "select",
    "serialize",
    "split",
    "update",
    "validate",
    "walk",
    "write",
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
    name: str
    qualname: str
    scope: str
    visibility: str
    role: str
    secondary_roles: list[str]
    confidence: float
    helper_candidate: bool
    incoming_count: int
    incoming_callers: list[str]
    incoming_call_sites: list[str]
    outgoing_internal: list[str]
    outgoing_call_sites: list[str]
    specialized_helper: bool
    specialization: str
    side_effects: list[str]
    calls: list[str]
    args: list[str]
    decorators: list[str]
    returns_annotation: str
    doc_summary: str
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Inventory:
    """Complete helper inventory report."""

    root: str
    files_scanned: int
    functions_seen: int
    helpers_reported: int
    role_counts: dict[str, int]
    records: list[FunctionRecord]


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
    suffixes = {".py"}
    if include_pyi:
        suffixes.add(".pyi")
    targets = [root / raw_path for raw_path in raw_paths] if raw_paths else [root]
    files: list[Path] = []
    seen_dirs: set[Path] = set()
    seen_files: set[Path] = set()
    for target in targets:
        if target.is_file() and target.suffix in suffixes:
            resolved = target.resolve()
            if resolved not in seen_files:
                files.append(target)
                seen_files.add(resolved)
            continue
        if not target.is_dir():
            continue
        for current_root, dirnames, filenames in os.walk(target, followlinks=True):
            current = Path(current_root)
            try:
                relative_current = current.relative_to(root)
            except ValueError:
                relative_current = current
            real_current = current.resolve()
            if real_current in seen_dirs:
                dirnames[:] = []
                continue
            seen_dirs.add(real_current)
            kept_dirnames: list[str] = []
            for dirname in dirnames:
                child = current / dirname
                try:
                    relative_child = child.relative_to(root)
                except ValueError:
                    relative_child = child
                if logical_excluded(
                    relative_child,
                    include_vendor=include_vendor,
                    include_hidden=include_hidden,
                ):
                    continue
                kept_dirnames.append(dirname)
            dirnames[:] = kept_dirnames
            if logical_excluded(
                relative_current,
                include_vendor=include_vendor,
                include_hidden=include_hidden,
            ):
                dirnames[:] = []
                continue
            for filename in filenames:
                path = current / filename
                if path.suffix not in suffixes:
                    continue
                if path.suffix in DEFAULT_EXCLUDED_SUFFIXES and not include_pyi:
                    continue
                resolved = path.resolve()
                if resolved in seen_files:
                    continue
                seen_files.add(resolved)
                files.append(path)
    return sorted(files, key=lambda path: stable_relative(root, path))


def stable_relative(root: Path, path: Path) -> str:
    """Return a stable root-relative path when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def unparse(node: ast.AST | None) -> str:
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

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Skip nested async function bodies while analyzing the outer function."""
        if node is self.root:
            self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Do not mix class-local method calls into an enclosing function."""
        if node is self.root:
            self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Record calls and side-effect-like features."""
        name = dotted_name(node.func)
        if name:
            self.calls[name] += 1
            self.call_locations.append((name, node.lineno))
            leaf = name.rsplit(".", maxsplit=1)[-1]
            if leaf in MUTATING_METHODS:
                self.features.add("mutation_call")
            if name.startswith("subprocess.") or leaf in {"Popen", "run"}:
                self.features.add("subprocess")
            if name in {"print", "sys.stdout.write", "sys.stderr.write"}:
                self.features.add("stdio")
            if name.startswith("logging.") or leaf in {"debug", "info", "warning", "error"}:
                self.features.add("logging")
            if leaf in {"read", "read_text", "read_bytes", "load", "loads"}:
                self.features.add("read")
            if leaf in {"write", "write_text", "write_bytes", "dump", "dumps"}:
                self.features.add("write")
            if leaf in {"mkdir", "unlink", "rename", "replace", "copy", "copy2", "rmtree"}:
                self.features.add("filesystem_mutation")
            if name.startswith("os.environ") or name in {"os.getenv", "getenv"}:
                self.features.add("environment")
            if name.startswith(("json.", "tomllib.", "tomli.", "yaml.")):
                self.features.add("serialization")
            if name.startswith(("ast.", "libcst.")):
                self.features.add("static_analysis")
            if name.startswith(("jax.", "jnp.", "np.", "numpy.", "math.", "lax.")):
                self.features.add("numeric")
            if name.startswith(("argparse.",)) or leaf == "ArgumentParser":
                self.features.add("cli_parser")
            if name.startswith(("requests.", "urllib.")):
                self.features.add("network")
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
        return BodyFacts(
            calls=tuple(expanded_calls),
            call_locations=tuple(sorted(self.call_locations)),
            features=tuple(sorted(self.features)),
        )


def body_facts(node: ast.AST) -> BodyFacts:
    """Collect facts for one function body."""
    visitor = FunctionBodyVisitor(node)
    visitor.visit(node)
    return visitor.facts()


def role_scores(
    *,
    path: str,
    name: str,
    returns_annotation: str,
    facts: BodyFacts,
) -> tuple[Counter[str], list[str]]:
    """Infer possible roles from name, path, calls, and body features."""
    lower_name = name.lower()
    path_parts = tuple(Path(path).parts)
    calls = set(facts.calls)
    features = set(facts.features)
    scores: Counter[str] = Counter()
    evidence: list[str] = []

    def add(role: str, points: int, reason: str) -> None:
        scores[role] += points
        evidence.append(f"{role}:{reason}")

    if "tests" in path_parts or lower_name.startswith(("fixture", "fake", "stub")):
        add("test_support", 2, "test-path-or-fixture-name")
    if "tools" in path_parts or "agent_tools" in path_parts:
        add("workflow_tooling", 1, "tool-path")
    if lower_name.startswith(("build", "create", "make", "default")):
        add("factory_builder", 3, "builder-prefix")
    if lower_name.startswith(("parse", "load", "read")):
        add("parser_loader", 3, "parser-loader-prefix")
    if lower_name.startswith(("format", "render", "dump", "serialize", "markdown")):
        add("formatter_reporter", 3, "formatter-prefix")
    if lower_name.startswith(("check", "validate", "ensure", "assert")):
        add("validator_checker", 3, "validator-prefix")
    if lower_name.startswith(("is", "has", "can", "should")) or returns_annotation == "bool":
        add("predicate", 3, "predicate-shape")
    if lower_name.startswith(("iter", "collect", "find", "scan", "walk", "gather", "list")):
        add("collector_inventory", 3, "collector-prefix")
    if lower_name.startswith(("normalize", "convert", "resolve", "relative", "as", "split")):
        add("converter_normalizer", 3, "converter-prefix")
    if lower_name.startswith(("write", "copy", "update", "emit", "log", "append", "remove")):
        add("writer_mutator", 3, "writer-prefix")
    if lower_name.startswith(("run", "main", "execute", "call")):
        add("command_runner", 2, "command-prefix")
    if "bridge" in lower_name or "adapter" in lower_name or "wrapper" in lower_name:
        add("adapter_bridge", 2, "adapter-name")
    if "inventory" in lower_name or "catalog" in lower_name:
        add("collector_inventory", 2, "inventory-name")
    if "diagnostic" in lower_name or "report" in lower_name:
        add("formatter_reporter", 2, "report-name")
    if "subprocess" in features:
        add("command_runner", 3, "subprocess-call")
    if "cli_parser" in features:
        add("cli_parser", 4, "argparse-call")
    if "serialization" in features:
        add("parser_loader", 1, "serialization-call")
        add("formatter_reporter", 1, "serialization-call")
    if "static_analysis" in features or any(call.startswith("ast.") for call in calls):
        add("static_analyzer", 4, "ast-call")
    if "numeric" in features:
        add("numeric_kernel", 3, "numeric-call")
    if "read" in features:
        add("parser_loader", 1, "read-call")
    if "write" in features or "filesystem_mutation" in features:
        add("writer_mutator", 2, "write-or-filesystem-call")
    if "raises" in features and not scores:
        add("validator_checker", 1, "raises")
    if not scores:
        add("general_helper", 1, "fallback")
    return scores, evidence


def helper_candidate(
    *,
    name: str,
    scope: str,
    path: str,
    role: str,
) -> bool:
    """Return whether a function looks like a helper rather than primary API."""
    lower_name = name.lower()
    if lower_name.startswith("test_"):
        return False
    if lower_name in {"main", "__init__"}:
        return False
    if scope == "nested":
        return True
    if name.startswith("_") and not (name.startswith("__") and name.endswith("__")):
        return True
    if lower_name.endswith("_helper") or "helper" in lower_name or "util" in lower_name:
        return True
    if lower_name.startswith(HELPER_NAME_PREFIXES):
        return True
    if role in {
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
    }:
        return True
    return "helper" in path or "utils" in path


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
    score = 0.35
    if name.startswith("_"):
        score += 0.25
    if scope == "nested":
        score += 0.2
    if any(name.lower().startswith(prefix) for prefix in HELPER_NAME_PREFIXES):
        score += 0.15
    if scores:
        score += min(0.2, max(scores.values()) / 20.0)
    if facts.calls:
        score += 0.05
    if facts.features:
        score += 0.05
    return round(min(score, 0.99), 2)


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
        qualname = ".".join((*parent_stack, node.name)) if parent_stack else node.name
        scope = "module"
        if parent_stack and parent_stack[-1][0].isupper():
            scope = "method"
        elif parent_stack:
            scope = "nested"
        facts = body_facts(node)
        returns_annotation = unparse(node.returns)
        scores, evidence = role_scores(
            path=self.relative_path,
            name=node.name,
            returns_annotation=returns_annotation,
            facts=facts,
        )
        ordered_roles = [role for role, _count in scores.most_common()]
        role = ordered_roles[0]
        candidate = helper_candidate(
            name=node.name,
            scope=scope,
            path=self.relative_path,
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
                name=node.name,
                qualname=qualname,
                scope=scope,
                visibility="private" if node.name.startswith("_") else "public",
                role=role,
                secondary_roles=ordered_roles[1:4],
                confidence=0.0,
                helper_candidate=candidate,
                incoming_count=0,
                incoming_callers=[],
                incoming_call_sites=[],
                outgoing_internal=[],
                outgoing_call_sites=[
                    f"{call}@{line}" for call, line in facts.call_locations
                ],
                specialized_helper=False,
                specialization="not_evaluated",
                side_effects=sorted(feature for feature in facts.features if is_side_effect(feature)),
                calls=sorted(set(facts.calls)),
                args=[arg.arg for arg in node.args.args],
                decorators=list(decorators),
                returns_annotation=returns_annotation,
                doc_summary=doc_summary(ast.get_docstring(node)),
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


def doc_summary(docstring: str | None) -> str:
    """Return the first sentence-ish fragment from a docstring."""
    if not docstring:
        return ""
    compact = " ".join(docstring.strip().split())
    for separator in (". ", "。"):
        if separator in compact:
            return compact.split(separator, maxsplit=1)[0].strip() + separator.strip()
    return compact[:140]


def analyze_file(root: Path, path: Path) -> list[FunctionRecord]:
    """Analyze one Python file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    collector = DefinitionCollector(root, path)
    collector.visit(tree)
    return collector.records


def apply_call_graph(records: list[FunctionRecord]) -> None:
    """Attach simple static incoming and outgoing call counts."""
    by_name: dict[str, list[FunctionRecord]] = {}
    by_qualname: dict[str, FunctionRecord] = {}
    for record in records:
        by_name.setdefault(record.name, []).append(record)
        by_qualname[record.qualname] = record
    incoming_sites: dict[int, set[str]] = {}
    incoming_callers: dict[int, set[str]] = {}
    outgoing: dict[int, set[str]] = {}
    for index, record in enumerate(records):
        matches: set[str] = set()
        for call_site in record.outgoing_call_sites:
            call, _separator, line_text = call_site.partition("@")
            line = int(line_text) if line_text.isdigit() else record.line
            candidates = internal_call_candidates(by_name, by_qualname, record, call)
            for candidate in candidates:
                if candidate is record:
                    continue
                if candidate.path == record.path or len(candidates) == 1:
                    matches.add(candidate.qualname)
                    incoming_sites.setdefault(id(candidate), set()).add(
                        f"{record.path}:{line}:{record.qualname}"
                    )
                    incoming_callers.setdefault(id(candidate), set()).add(
                        f"{record.path}:{record.qualname}"
                    )
        outgoing[index] = matches
    for index, record in enumerate(records):
        sites = sorted(incoming_sites.get(id(record), set()))
        callers = sorted(incoming_callers.get(id(record), set()))
        record.incoming_count = len(sites)
        record.incoming_callers = callers
        record.incoming_call_sites = sites
        record.outgoing_internal = sorted(outgoing[index])
        record.specialized_helper, record.specialization = specialization(record)
        if record.helper_candidate and record.visibility == "private" and record.incoming_count == 0:
            record.evidence.append("usage:no-internal-callers")
        if record.specialized_helper:
            record.evidence.append(f"usage:{record.specialization}")


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
    if not record.helper_candidate:
        return False, "not_helper_candidate"
    if record.scope == "nested":
        return True, "nested_local_helper"
    if not record.incoming_call_sites:
        return False, "no_internal_call_sites"
    if len(record.incoming_callers) == 1:
        return True, "single_caller_helper"
    caller_files = {caller.split(":", maxsplit=1)[0] for caller in record.incoming_callers}
    if len(caller_files) == 1 and len(record.incoming_callers) <= 3:
        return True, "file_local_helper_cluster"
    return False, "shared_helper"


def build_inventory(
    root: Path,
    paths: list[str],
    *,
    all_functions: bool,
    include_vendor: bool,
    include_hidden: bool,
    include_pyi: bool,
    min_confidence: float,
) -> Inventory:
    """Build the helper inventory."""
    files = iter_python_files(
        root,
        paths,
        include_vendor=include_vendor,
        include_hidden=include_hidden,
        include_pyi=include_pyi,
    )
    all_records: list[FunctionRecord] = []
    for path in files:
        all_records.extend(analyze_file(root, path))
    apply_call_graph(all_records)
    selected = [
        record
        for record in all_records
        if (all_functions or record.helper_candidate) and record.confidence >= min_confidence
    ]
    selected.sort(key=lambda item: (item.path, item.line, item.qualname))
    role_counts = Counter(record.role for record in selected)
    return Inventory(
        root=root.as_posix(),
        files_scanned=len(files),
        functions_seen=len(all_records),
        helpers_reported=len(selected),
        role_counts=dict(sorted(role_counts.items())),
        records=selected,
    )


def render_text(inventory: Inventory) -> str:
    """Render stable text output."""
    lines: list[str] = []
    for record in inventory.records:
        side_effects = ",".join(record.side_effects) if record.side_effects else "none"
        outgoing = ",".join(record.outgoing_internal) if record.outgoing_internal else "none"
        evidence = ",".join(record.evidence[:6]) if record.evidence else "none"
        lines.append(
            "HELPER="
            f"{record.path}:{record.line}:{record.qualname} "
            f"role={record.role} confidence={record.confidence:.2f} "
            f"scope={record.scope} visibility={record.visibility} "
            f"incoming={record.incoming_count} outgoing={outgoing} "
            f"specialization={record.specialization} "
            f"callers={';'.join(record.incoming_callers) or 'none'} "
            f"side_effects={side_effects} evidence={evidence}"
        )
    role_summary = ",".join(f"{role}:{count}" for role, count in inventory.role_counts.items())
    lines.extend(
        [
            f"HELPER_INVENTORY_FILES={inventory.files_scanned}",
            f"HELPER_INVENTORY_FUNCTIONS={inventory.functions_seen}",
            f"HELPER_INVENTORY_HELPERS={inventory.helpers_reported}",
            f"HELPER_INVENTORY_ROLES={role_summary}",
            "HELPER_INVENTORY=pass",
        ]
    )
    return "\n".join(lines) + "\n"


def markdown_cell(value: object) -> str:
    """Escape a Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(inventory: Inventory) -> str:
    """Render Markdown output."""
    lines = [
        "# Helper Function Inventory",
        "",
        f"- files scanned: {inventory.files_scanned}",
        f"- functions seen: {inventory.functions_seen}",
        f"- helpers reported: {inventory.helpers_reported}",
        "",
        "| Path | Line | Helper | Role | Confidence | Incoming | Specialization | Side effects | Evidence |",
        "| --- | ---: | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for record in inventory.records:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(record.path),
                    str(record.line),
                    markdown_cell(record.qualname),
                    markdown_cell(record.role),
                    f"{record.confidence:.2f}",
                    str(record.incoming_count),
                    markdown_cell(record.specialization),
                    markdown_cell(", ".join(record.side_effects) or "none"),
                    markdown_cell(", ".join(record.evidence[:4]) or "none"),
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
    root = Path(args.root).resolve()
    inventory = build_inventory(
        root,
        args.paths,
        all_functions=args.all_functions,
        include_vendor=args.include_vendor,
        include_hidden=args.include_hidden,
        include_pyi=args.include_pyi,
        min_confidence=args.min_confidence,
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
