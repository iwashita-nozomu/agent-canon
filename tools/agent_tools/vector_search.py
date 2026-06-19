#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Searches AgentCanon text surfaces and expands dependency-aware context.
# upstream design ../../tools/README.md shared tool index
# upstream design ../../documents/tools/README.md operator guide for shared tools
# upstream implementation ./tool_path_policy.py defines retired legacy path policy
# downstream implementation ../../tests/agent_tools/test_vector_search.py regression tests
# @dependency-end
"""Search repo text surfaces with a lightweight TF-IDF vector model."""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from tool_path_policy import is_retired_legacy_tool_path

DEFAULT_SURFACES = (
    "tools",
    "agents",
    ".agents",
    "documents",
    ".codex",
    "mcp",
)
TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".py",
        ".sh",
        ".toml",
        ".yaml",
        ".yml",
        ".json",
        ".txt",
    }
)
EXCLUDED_PARTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "legacy",
        "node_modules",
        "reports",
        "vendor",
    }
)
DEFAULT_TOP = 8
PATH_TOKEN_WEIGHT = 2
SNIPPET_CHARS = 180
SCORE_DECIMAL_PLACES = 6
HEADER_SCAN_LINES = 80
TOKEN_RE = re.compile(r"[0-9A-Za-z_\u0080-\uFFFF]+")
CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
DEPENDENCY_LINE_RE = re.compile(
    r"^(?P<direction>upstream|downstream)\s+"
    r"(?P<kind>design|implementation|environment)\s+"
    r"(?P<target>\S+)(?:\s+(?P<reason>.*))?$"
)
SHARED_SURFACE_PARTS = frozenset({"tools", "agents", ".agents", ".codex", "mcp"})


@dataclass(frozen=True)
class Document:
    """One indexed text document."""

    path: Path
    relative_path: str
    text: str
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class SearchHit:
    """One vector-search result."""

    relative_path: str
    score: float
    snippet: str

    def as_json(self) -> Mapping[str, object]:
        """Return a machine-readable result mapping."""
        return {
            "path": self.relative_path,
            "score": round(self.score, SCORE_DECIMAL_PLACES),
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class DependencyEdge:
    """One dependency-manifest edge parsed from a source file."""

    direction: str
    kind: str
    source: str
    target: str
    reason: str


@dataclass(frozen=True)
class ContextPath:
    """One path the agent should consider loading as context."""

    role: str
    path: str
    source: str
    depth: int
    kind: str

    def as_json(self) -> Mapping[str, object]:
        """Return a machine-readable context path mapping."""
        return {
            "role": self.role,
            "path": self.path,
            "source": self.source,
            "depth": self.depth,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class PythonSymbol:
    """One Python class, function, or method definition."""

    symbol_id: str
    name: str
    qualname: str
    kind: str
    relative_path: str
    line: int
    end_line: int
    calls: tuple[str, ...]

    def as_json(self, role: str, depth: int) -> Mapping[str, object]:
        """Return a machine-readable symbol mapping."""
        return {
            "role": role,
            "depth": depth,
            "id": self.symbol_id,
            "name": self.name,
            "qualname": self.qualname,
            "kind": self.kind,
            "path": self.relative_path,
            "line": self.line,
            "end_line": self.end_line,
        }


@dataclass(frozen=True)
class PythonSymbolContext:
    """One selected Python symbol plus why it was selected."""

    role: str
    depth: int
    symbol: PythonSymbol

    def as_json(self) -> Mapping[str, object]:
        """Return a machine-readable selected-symbol mapping."""
        return self.symbol.as_json(self.role, self.depth)


@dataclass(frozen=True)
class PythonCallEdge:
    """One resolved Python call dependency edge."""

    caller: str
    callee: str
    call_name: str


@dataclass(frozen=True)
class PythonCallContext:
    """One Python call dependency selected for output."""

    direction: str
    depth: int
    caller: PythonSymbol
    callee: PythonSymbol
    call_name: str

    def as_json(self) -> Mapping[str, object]:
        """Return a machine-readable call-context mapping."""
        return {
            "direction": self.direction,
            "depth": self.depth,
            "caller": self.caller.symbol_id,
            "callee": self.callee.symbol_id,
            "call": self.call_name,
            "caller_path": self.caller.relative_path,
            "caller_line": self.caller.line,
            "callee_path": self.callee.relative_path,
            "callee_line": self.callee.line,
        }


@dataclass(frozen=True)
class ContextExpansion:
    """Dependency-aware context generated for search hits and focus symbols."""

    paths: tuple[ContextPath, ...]
    python_symbols: tuple[PythonSymbolContext, ...]
    python_edges: tuple[PythonCallContext, ...]

    def as_json(self) -> Mapping[str, object]:
        """Return a machine-readable context expansion mapping."""
        return {
            "paths": [item.as_json() for item in self.paths],
            "python_symbols": [item.as_json() for item in self.python_symbols],
            "python_edges": [item.as_json() for item in self.python_edges],
        }


@dataclass(frozen=True)
class DependencyEdgeIndex:
    """Dependency edges indexed for graph expansion."""

    by_source: Mapping[str, Sequence[DependencyEdge]]
    by_target: Mapping[str, Sequence[DependencyEdge]]


@dataclass
class ContextPathAccumulator:
    """Mutable accumulator for dependency context paths."""

    results: list[ContextPath]
    seen_roles: set[tuple[str, str, str, int, str]]
    limit: int

    def add(self, role: str, path: str, source: str, current_depth: int, kind: str) -> None:
        """Append one context path unless it is duplicated or over limit."""
        key = (role, path, source, current_depth, kind)
        if key in self.seen_roles or len(self.results) >= self.limit:
            return
        self.seen_roles.add(key)
        self.results.append(
            ContextPath(
                role=role,
                path=path,
                source=source,
                depth=current_depth,
                kind=kind,
            )
        )


@dataclass(frozen=True)
class PythonCallIndexes:
    """Python symbols and call edges indexed for graph expansion."""

    symbol_by_id: Mapping[str, PythonSymbol]
    outgoing: Mapping[str, Sequence[PythonCallEdge]]
    incoming: Mapping[str, Sequence[PythonCallEdge]]


@dataclass
class PythonContextAccumulator:
    """Mutable accumulator for Python symbol and call-edge context."""

    symbol_contexts: list[PythonSymbolContext]
    edge_contexts: list[PythonCallContext]
    seen_symbols: set[str]
    seen_edges: set[tuple[str, int, str, str, str]]
    limit: int

    def add_symbol(
        self,
        indexes: PythonCallIndexes,
        role: str,
        symbol_id: str,
        current_depth: int,
    ) -> None:
        """Append one Python symbol context unless duplicated or over limit."""
        if symbol_id in self.seen_symbols or len(self.symbol_contexts) >= self.limit:
            return
        symbol = indexes.symbol_by_id.get(symbol_id)
        if symbol is None:
            return
        self.seen_symbols.add(symbol_id)
        self.symbol_contexts.append(
            PythonSymbolContext(role=role, depth=current_depth, symbol=symbol)
        )

    def add_edge(
        self,
        indexes: PythonCallIndexes,
        direction: str,
        current_depth: int,
        edge: PythonCallEdge,
    ) -> None:
        """Append one Python call edge context unless duplicated or over limit."""
        key = (direction, current_depth, edge.caller, edge.callee, edge.call_name)
        if key in self.seen_edges or len(self.edge_contexts) >= self.limit:
            return
        caller = indexes.symbol_by_id.get(edge.caller)
        callee = indexes.symbol_by_id.get(edge.callee)
        if caller is None or callee is None:
            return
        self.seen_edges.add(key)
        self.edge_contexts.append(
            PythonCallContext(
                direction=direction,
                depth=current_depth,
                caller=caller,
                callee=callee,
                call_name=edge.call_name,
            )
        )


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Search AgentCanon text surfaces with dependency-free TF-IDF vectors."
    )
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--query", required=True, help="Search query text.")
    parser.add_argument(
        "--surface",
        action="append",
        default=[],
        help="Top-level file or directory to index. Repeatable. Defaults to shared canon surfaces.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Path part, prefix, or glob to exclude. Repeatable.",
    )
    parser.add_argument("--top", type=int, default=DEFAULT_TOP, help="Number of hits to print.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--context",
        action="store_true",
        help=(
            "Expand hits into dependency-manifest context and Python call "
            "fan-in/fan-out context."
        ),
    )
    parser.add_argument(
        "--dependency-depth",
        type=int,
        default=1,
        help="Dependency context depth for --context. Defaults to 1.",
    )
    parser.add_argument(
        "--context-top",
        type=int,
        default=40,
        help="Maximum context paths, symbols, and call edges to print for --context.",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        default=[],
        help=(
            "Python symbol focus for --context. Repeatable. Matches name, "
            "qualname, path:name, path:qualname, or full symbol id."
        ),
    )
    parser.add_argument(
        "--no-callers",
        action="store_true",
        help="For --context, omit reverse Python caller context.",
    )
    return parser


def tokenize_text(text: str) -> tuple[str, ...]:
    """Tokenize prose and source text into lowercase terms."""
    normalized = text.replace("-", " ").replace("/", " ")
    raw_tokens = tuple(token.lower() for token in TOKEN_RE.findall(normalized))
    split_tokens = tuple(
        token.lower() for token in TOKEN_RE.findall(CAMEL_BOUNDARY_RE.sub(" ", normalized))
    )
    return raw_tokens + split_tokens


def relative_path(root: Path, path: Path) -> str:
    """Return a stable slash-separated path relative to root when possible."""
    try:
        return path.absolute().relative_to(root.absolute()).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()


def matches_exclude(relative: str, excludes: Sequence[str]) -> bool:
    """Return true when a relative path matches an exclude selector."""
    parts = set(Path(relative).parts)
    for raw_exclude in excludes:
        exclude = raw_exclude.strip("/")
        if not exclude:
            continue
        if (
            relative == exclude
            or relative.startswith(f"{exclude}/")
            or exclude in parts
            or Path(relative).match(exclude)
        ):
            return True
    return False


def is_indexable(
    root: Path,
    path: Path,
    excludes: Sequence[str],
    excluded_parts: set[str],
) -> bool:
    """Return true when a file should be included in the text index."""
    if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
        return False
    relative = relative_path(root, path)
    parts = set(Path(relative).parts)
    if parts & excluded_parts:
        return False
    if is_retired_legacy_tool_path(relative):
        return False
    return not matches_exclude(relative, excludes)


def iter_surface_files(
    root: Path,
    surfaces: Sequence[str],
    excludes: Sequence[str],
    excluded_parts: set[str],
) -> Iterable[Path]:
    """Yield indexable files from the requested surfaces."""
    for surface in surfaces:
        surface_path = root / surface
        if surface_path.is_file() and is_indexable(root, surface_path, excludes, excluded_parts):
            yield surface_path
        elif surface_path.is_dir():
            for current_root, _, filenames in os.walk(surface_path, followlinks=True):
                for filename in sorted(filenames):
                    candidate = Path(current_root) / filename
                    if is_indexable(root, candidate, excludes, excluded_parts):
                        yield candidate


def read_document(root: Path, path: Path) -> Document:
    """Read one document and add path terms to the vector text."""
    relative = relative_path(root, path)
    text = path.read_text(encoding="utf-8", errors="ignore")
    path_tokens = tokenize_text(relative)
    body_tokens = tokenize_text(text)
    weighted_path_tokens = tuple(path_tokens * PATH_TOKEN_WEIGHT)
    return Document(
        path=path,
        relative_path=relative,
        text=text,
        tokens=weighted_path_tokens + body_tokens,
    )


def read_documents(
    root: Path,
    surfaces: Sequence[str],
    excludes: Sequence[str],
    excluded_parts: set[str],
) -> list[Document]:
    """Read all documents from surfaces."""
    paths = sorted(set(iter_surface_files(root, surfaces, excludes, excluded_parts)))
    return [read_document(root, path) for path in paths]


def document_frequency(documents: Sequence[Document]) -> Counter[str]:
    """Build document-frequency counts for every term."""
    frequency: Counter[str] = Counter()
    for document in documents:
        frequency.update(set(document.tokens))
    return frequency


def tfidf_vector(
    terms: Sequence[str],
    frequency: Counter[str],
    corpus_size: int,
) -> dict[str, float]:
    """Build a normalized TF-IDF vector."""
    term_counts = Counter(terms)
    vector: dict[str, float] = {}
    for term, count in term_counts.items():
        inverse_document_frequency = (
            math.log((corpus_size + 1) / (frequency.get(term, 0) + 1)) + 1.0
        )
        vector[term] = (1.0 + math.log(count)) * inverse_document_frequency
    return vector


def cosine_similarity(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    """Return cosine similarity for sparse vectors."""
    if not left or not right:
        return 0.0
    numerator = sum(weight * right[term] for term, weight in left.items() if term in right)
    left_norm = math.sqrt(sum(weight * weight for weight in left.values()))
    right_norm = math.sqrt(sum(weight * weight for weight in right.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def compact_text(text: str) -> str:
    """Collapse whitespace for readable snippets."""
    return " ".join(text.split())


def make_snippet(text: str, query_terms: Sequence[str]) -> str:
    """Return a short snippet around the first matching query term."""
    compact = compact_text(text)
    lowered = compact.lower()
    first_match = min(
        (lowered.find(term) for term in query_terms if lowered.find(term) >= 0),
        default=0,
    )
    start = max(first_match - SNIPPET_CHARS // 2, 0)
    end = start + SNIPPET_CHARS
    snippet = compact[start:end]
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(compact):
        snippet = f"{snippet}..."
    return snippet


def search(documents: Sequence[Document], query: str, top: int) -> list[SearchHit]:
    """Search indexed documents and return ranked hits."""
    query_terms = tokenize_text(query)
    if not query_terms or not documents:
        return []
    frequency = document_frequency(documents)
    corpus_size = len(documents)
    query_vector = tfidf_vector(query_terms, frequency, corpus_size)
    scored: list[SearchHit] = []
    for document in documents:
        document_vector = tfidf_vector(document.tokens, frequency, corpus_size)
        score = cosine_similarity(query_vector, document_vector)
        if score > 0.0:
            scored.append(
                SearchHit(
                    relative_path=document.relative_path,
                    score=score,
                    snippet=make_snippet(document.text, query_terms),
                )
            )
    return sorted(scored, key=lambda hit: (-hit.score, hit.relative_path))[:top]


def strip_manifest_line(line: str) -> str:
    """Strip common comment markers from a dependency-manifest line."""
    stripped = line.rstrip("\r\n").strip()
    for prefix in ("<!--", "#", "//", "*"):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :].strip()
    if stripped.endswith("-->"):
        stripped = stripped[:-3].strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        stripped = stripped[1:-1].strip()
    return stripped.rstrip(",").strip()


def resolve_dependency_target(root: Path, source: Document, target: str) -> str:
    """Resolve a manifest target through root views and vendored canon source."""
    source_parts = Path(source.relative_path).parts
    source_context = source.path
    if source_parts and source_parts[0] in SHARED_SURFACE_PARTS:
        vendor_source = root / "vendor" / "agent-canon" / source.relative_path
        if vendor_source.exists():
            source_context = vendor_source
    candidate = source_context.parent / target
    return relative_path(root, candidate.resolve(strict=False))


def parse_dependency_edges(root: Path, documents: Sequence[Document]) -> list[DependencyEdge]:
    """Parse dependency-manifest edges from indexed documents."""
    edges: list[DependencyEdge] = []
    for document in documents:
        in_manifest = False
        for raw_line in document.text.splitlines()[:HEADER_SCAN_LINES]:
            line = strip_manifest_line(raw_line)
            if line == "@dependency-start":
                in_manifest = True
                continue
            if line == "@dependency-end":
                break
            if not in_manifest:
                continue
            match = DEPENDENCY_LINE_RE.fullmatch(line)
            if match is None:
                continue
            edges.append(
                DependencyEdge(
                    direction=match.group("direction"),
                    kind=match.group("kind"),
                    source=document.relative_path,
                    target=resolve_dependency_target(root, document, match.group("target")),
                    reason=match.group("reason") or "",
                )
            )
    return sorted(
        set(edges),
        key=lambda edge: (edge.source, edge.direction, edge.kind, edge.target, edge.reason),
    )


def dependency_edge_indexes(
    edges: Sequence[DependencyEdge],
) -> DependencyEdgeIndex:
    """Index dependency edges by source and target path."""
    by_source: dict[str, list[DependencyEdge]] = defaultdict(list)
    by_target: dict[str, list[DependencyEdge]] = defaultdict(list)
    for edge in edges:
        by_source[edge.source].append(edge)
        by_target[edge.target].append(edge)
    for buckets in (by_source, by_target):
        for path in buckets:
            buckets[path].sort(key=lambda edge: (edge.direction, edge.kind, edge.source, edge.target))
    return DependencyEdgeIndex(by_source=by_source, by_target=by_target)


def add_search_hit_context_paths(
    hits: Sequence[SearchHit],
    accumulator: ContextPathAccumulator,
) -> set[str]:
    """Record search-hit paths and return the initial frontier."""
    frontier = {hit.relative_path for hit in hits}
    for hit in hits:
        accumulator.add(
            "search_hit",
            hit.relative_path,
            hit.relative_path,
            0,
            "search",
        )
    return frontier


def dependency_frontier_step(
    frontier: set[str],
    index: DependencyEdgeIndex,
    accumulator: ContextPathAccumulator,
    seen_paths: set[str],
    current_depth: int,
) -> set[str]:
    """Expand one dependency-manifest frontier step."""
    next_frontier: set[str] = set()
    for path in sorted(frontier):
        for edge in index.by_source.get(path, ()):
            accumulator.add(
                f"declared_{edge.direction}",
                edge.target,
                edge.source,
                current_depth,
                edge.kind,
            )
            if edge.target not in seen_paths:
                next_frontier.add(edge.target)
        for edge in index.by_target.get(path, ()):
            accumulator.add(
                f"incoming_{edge.direction}",
                edge.source,
                edge.target,
                current_depth,
                edge.kind,
            )
            if edge.source not in seen_paths:
                next_frontier.add(edge.source)
    return next_frontier


def dependency_context_paths(
    hits: Sequence[SearchHit],
    edges: Sequence[DependencyEdge],
    depth: int,
    limit: int,
) -> tuple[ContextPath, ...]:
    """Expand search hits through dependency-manifest upstream/downstream edges."""
    if limit <= 0:
        return ()
    index = dependency_edge_indexes(edges)
    accumulator = ContextPathAccumulator(results=[], seen_roles=set(), limit=limit)
    frontier = add_search_hit_context_paths(hits, accumulator)
    seen_paths = set(frontier)
    for current_depth in range(1, max(depth, 0) + 1):
        next_frontier = dependency_frontier_step(
            frontier,
            index,
            accumulator,
            seen_paths,
            current_depth,
        )
        seen_paths.update(next_frontier)
        frontier = next_frontier
        if not frontier or len(accumulator.results) >= limit:
            break
    return tuple(accumulator.results)


def called_name(node: ast.AST) -> str | None:
    """Return the stable name portion of a call target when statically visible."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return called_name(node.func)
    if isinstance(node, ast.Subscript):
        return called_name(node.value)
    return None


class CallCollector(ast.NodeVisitor):
    """Collect direct call names without descending into nested definitions."""

    def __init__(self) -> None:
        """Initialize an empty call-name set."""
        self.calls: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        """Record one statically visible call target."""
        name = called_name(node.func)
        if name is not None:
            self.calls.add(name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Avoid mixing nested class-body calls into the parent symbol."""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Avoid mixing nested function-body calls into the parent symbol."""

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Avoid mixing nested async function-body calls into the parent symbol."""


def collect_calls(node: ast.AST) -> tuple[str, ...]:
    """Collect direct call names from one definition body."""
    collector = CallCollector()
    for child in getattr(node, "body", ()):
        collector.visit(child)
    return tuple(sorted(collector.calls))


class PythonDefinitionCollector(ast.NodeVisitor):
    """Collect Python definitions and their direct calls."""

    def __init__(self, relative: str) -> None:
        """Initialize collection state for one Python file."""
        self.relative = relative
        self.stack: list[str] = []
        self.symbols: list[PythonSymbol] = []

    def add_symbol(self, node: ast.AST, name: str, kind: str, calls: tuple[str, ...]) -> None:
        """Record one symbol."""
        qualname = ".".join((*self.stack, name))
        line = getattr(node, "lineno", 1)
        end_line = getattr(node, "end_lineno", line)
        self.symbols.append(
            PythonSymbol(
                symbol_id=f"{self.relative}:{qualname}",
                name=name,
                qualname=qualname,
                kind=kind,
                relative_path=self.relative,
                line=line,
                end_line=end_line,
                calls=calls,
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Record a class and descend into its methods."""
        base_calls = tuple(sorted(name for base in node.bases if (name := called_name(base))))
        self.add_symbol(node, node.name, "class", base_calls)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def record_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Record a function-like node and descend into nested definitions."""
        kind = "method" if self.stack else "function"
        self.add_symbol(node, node.name, kind, collect_calls(node))
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Record a function or method and descend into nested definitions."""
        self.record_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Record an async function or method and descend into nested definitions."""
        self.record_function(node)


def read_python_symbols(documents: Sequence[Document]) -> tuple[PythonSymbol, ...]:
    """Parse indexed Python documents into definitions and direct-call facts."""
    symbols: list[PythonSymbol] = []
    for document in documents:
        if document.path.suffix != ".py":
            continue
        try:
            tree = ast.parse(document.text, filename=document.relative_path)
        except SyntaxError:
            continue
        collector = PythonDefinitionCollector(document.relative_path)
        collector.visit(tree)
        symbols.extend(collector.symbols)
    return tuple(sorted(symbols, key=lambda symbol: symbol.symbol_id))


def build_python_call_edges(symbols: Sequence[PythonSymbol]) -> tuple[PythonCallEdge, ...]:
    """Resolve direct calls to unique local Python definitions."""
    by_name: dict[str, list[PythonSymbol]] = defaultdict(list)
    by_file_name: dict[tuple[str, str], list[PythonSymbol]] = defaultdict(list)
    for symbol in symbols:
        by_name[symbol.name].append(symbol)
        by_file_name[(symbol.relative_path, symbol.name)].append(symbol)

    edges: set[PythonCallEdge] = set()
    for caller in symbols:
        for call in caller.calls:
            same_file = [
                symbol
                for symbol in by_file_name.get((caller.relative_path, call), [])
                if symbol.symbol_id != caller.symbol_id
            ]
            candidates = same_file or [
                symbol for symbol in by_name.get(call, []) if symbol.symbol_id != caller.symbol_id
            ]
            unique_candidates = {symbol.symbol_id: symbol for symbol in candidates}
            if len(unique_candidates) == 1:
                callee = next(iter(unique_candidates.values()))
                edges.add(
                    PythonCallEdge(
                        caller=caller.symbol_id,
                        callee=callee.symbol_id,
                        call_name=call,
                    )
                )
    return tuple(sorted(edges, key=lambda edge: (edge.caller, edge.callee, edge.call_name)))


def selector_matches_symbol(selector: str, symbol: PythonSymbol) -> bool:
    """Return whether a user selector identifies a Python symbol."""
    return selector in {
        symbol.name,
        symbol.qualname,
        symbol.symbol_id,
        f"{symbol.relative_path}:{symbol.name}",
        f"{symbol.relative_path}:{symbol.qualname}",
    }


def select_python_symbols(
    symbols: Sequence[PythonSymbol],
    hits: Sequence[SearchHit],
    selectors: Sequence[str],
) -> tuple[PythonSymbol, ...]:
    """Select focus symbols from explicit selectors or Python hit files."""
    if selectors:
        selected = [
            symbol
            for symbol in symbols
            if any(selector_matches_symbol(selector, symbol) for selector in selectors)
        ]
        unique_symbols = {symbol.symbol_id: symbol for symbol in selected}
        return tuple(sorted(unique_symbols.values(), key=lambda symbol: symbol.symbol_id))

    hit_paths = {hit.relative_path for hit in hits}
    return tuple(symbol for symbol in symbols if symbol.relative_path in hit_paths)


def python_call_edge_indexes(
    symbol_by_id: Mapping[str, PythonSymbol],
    edges: Sequence[PythonCallEdge],
) -> PythonCallIndexes:
    """Index Python call edges by caller and callee."""
    outgoing: dict[str, list[PythonCallEdge]] = defaultdict(list)
    incoming: dict[str, list[PythonCallEdge]] = defaultdict(list)
    for edge in edges:
        outgoing[edge.caller].append(edge)
        incoming[edge.callee].append(edge)
    for buckets in (outgoing, incoming):
        for symbol_id in buckets:
            buckets[symbol_id].sort(key=lambda edge: (edge.caller, edge.callee, edge.call_name))
    return PythonCallIndexes(symbol_by_id=symbol_by_id, outgoing=outgoing, incoming=incoming)


def python_context_frontier_step(
    frontier: set[str],
    indexes: PythonCallIndexes,
    accumulator: PythonContextAccumulator,
    expanded_symbols: set[str],
    current_depth: int,
    include_callers: bool,
) -> set[str]:
    """Expand one Python call-graph frontier step."""
    next_frontier: set[str] = set()
    for symbol_id in sorted(frontier):
        for edge in indexes.outgoing.get(symbol_id, ()):
            accumulator.add_edge(
                indexes,
                "calls",
                current_depth,
                edge,
            )
            accumulator.add_symbol(
                indexes,
                "dependency",
                edge.callee,
                current_depth,
            )
            if edge.callee not in expanded_symbols:
                next_frontier.add(edge.callee)
        if include_callers:
            for edge in indexes.incoming.get(symbol_id, ()):
                accumulator.add_edge(
                    indexes,
                    "called_by",
                    current_depth,
                    edge,
                )
                accumulator.add_symbol(
                    indexes,
                    "dependent",
                    edge.caller,
                    current_depth,
                )
                if edge.caller not in expanded_symbols:
                    next_frontier.add(edge.caller)
    return next_frontier


def python_call_context(
    symbols: Sequence[PythonSymbol],
    seeds: Sequence[PythonSymbol],
    depth: int,
    limit: int,
    include_callers: bool,
) -> tuple[tuple[PythonSymbolContext, ...], tuple[PythonCallContext, ...]]:
    """Expand focus Python symbols through outgoing and incoming call edges."""
    if limit <= 0:
        return (), ()
    symbol_by_id = {symbol.symbol_id: symbol for symbol in symbols}
    indexes = python_call_edge_indexes(symbol_by_id, build_python_call_edges(symbols))
    accumulator = PythonContextAccumulator(
        symbol_contexts=[],
        edge_contexts=[],
        seen_symbols=set(),
        seen_edges=set(),
        limit=limit,
    )
    expanded_symbols: set[str] = set()
    frontier = {seed.symbol_id for seed in seeds}

    for seed in seeds:
        accumulator.add_symbol(
            indexes,
            "seed",
            seed.symbol_id,
            0,
        )
    for current_depth in range(1, max(depth, 0) + 1):
        next_frontier = python_context_frontier_step(
            frontier,
            indexes,
            accumulator,
            expanded_symbols,
            current_depth,
            include_callers,
        )
        expanded_symbols.update(frontier)
        frontier = next_frontier - expanded_symbols
        if not frontier:
            break
    return tuple(accumulator.symbol_contexts), tuple(accumulator.edge_contexts)


def build_context_expansion(
    root: Path,
    documents: Sequence[Document],
    hits: Sequence[SearchHit],
    symbols: Sequence[str],
    depth: int,
    limit: int,
    include_callers: bool,
) -> ContextExpansion:
    """Build dependency-aware context for the current search."""
    dependency_edges = parse_dependency_edges(root, documents)
    path_context = dependency_context_paths(hits, dependency_edges, depth, limit)
    python_symbols = read_python_symbols(documents)
    seed_symbols = select_python_symbols(python_symbols, hits, symbols)
    symbol_context, edge_context = python_call_context(
        python_symbols,
        seed_symbols,
        depth,
        limit,
        include_callers,
    )
    return ContextExpansion(
        paths=path_context,
        python_symbols=symbol_context,
        python_edges=edge_context,
    )


def print_text(
    hits: Sequence[SearchHit],
    indexed_count: int,
    context: ContextExpansion | None = None,
) -> None:
    """Print stable machine-readable text output."""
    print("VECTOR_SEARCH=pass")
    print(f"VECTOR_SEARCH_INDEXED_FILES={indexed_count}")
    print(f"VECTOR_SEARCH_HITS={len(hits)}")
    for hit in hits:
        print(f"HIT={hit.score:.6f}\t{hit.relative_path}\t{hit.snippet}")
    if context is None:
        return
    print(f"VECTOR_SEARCH_CONTEXT_PATHS={len(context.paths)}")
    for item in context.paths:
        print(
            f"CONTEXT_PATH={item.role}\t{item.path}\t"
            f"source={item.source}\tdepth={item.depth}\tkind={item.kind}"
        )
    print(f"VECTOR_SEARCH_PYTHON_SYMBOLS={len(context.python_symbols)}")
    for item in context.python_symbols:
        symbol = item.symbol
        print(
            f"PYTHON_SYMBOL={item.role}\t{symbol.symbol_id}\t"
            f"{symbol.kind}\tline={symbol.line}\tdepth={item.depth}"
        )
    print(f"VECTOR_SEARCH_PYTHON_EDGES={len(context.python_edges)}")
    for item in context.python_edges:
        print(
            f"PYTHON_EDGE={item.direction}\tdepth={item.depth}\t"
            f"{item.caller.symbol_id}\t{item.callee.symbol_id}\tcall={item.call_name}"
        )


def print_json(
    hits: Sequence[SearchHit],
    indexed_count: int,
    context: ContextExpansion | None = None,
) -> None:
    """Print JSON output."""
    payload: dict[str, object] = {
        "status": "pass",
        "indexed_files": indexed_count,
        "hits": [hit.as_json() for hit in hits],
    }
    if context is not None:
        payload["context"] = context.as_json()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: Sequence[str]) -> int:
    """Run the vector-search CLI."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    surfaces = tuple(args.surface) if args.surface else DEFAULT_SURFACES
    excluded_parts = set(EXCLUDED_PARTS)
    documents = read_documents(root, surfaces, args.exclude, excluded_parts)
    hits = search(documents, args.query, max(args.top, 0))
    context = None
    if args.context:
        context = build_context_expansion(
            root=root,
            documents=documents,
            hits=hits,
            symbols=tuple(args.symbol),
            depth=max(args.dependency_depth, 0),
            limit=max(args.context_top, 0),
            include_callers=not args.no_callers,
        )
    if args.format == "json":
        print_json(hits, len(documents), context)
    else:
        print_text(hits, len(documents), context)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
