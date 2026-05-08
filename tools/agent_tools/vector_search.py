#!/usr/bin/env python3
# @dependency-start
# responsibility Searches AgentCanon text surfaces with a dependency-free TF-IDF vector model.
# upstream design ../../tools/README.md shared tool index
# upstream design ../../documents/tools/README.md operator guide for shared tools
# downstream implementation ../../tests/agent_tools/test_vector_search.py regression tests
# @dependency-end
"""Search repo text surfaces with a lightweight TF-IDF vector model."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

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
TOKEN_RE = re.compile(r"[0-9A-Za-z_\u0080-\uFFFF]+")
CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


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


def print_text(hits: Sequence[SearchHit], indexed_count: int) -> None:
    """Print stable machine-readable text output."""
    print("VECTOR_SEARCH=pass")
    print(f"VECTOR_SEARCH_INDEXED_FILES={indexed_count}")
    print(f"VECTOR_SEARCH_HITS={len(hits)}")
    for hit in hits:
        print(f"HIT={hit.score:.6f}\t{hit.relative_path}\t{hit.snippet}")


def print_json(hits: Sequence[SearchHit], indexed_count: int) -> None:
    """Print JSON output."""
    payload: Mapping[str, object] = {
        "status": "pass",
        "indexed_files": indexed_count,
        "hits": [hit.as_json() for hit in hits],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: Sequence[str]) -> int:
    """Run the vector-search CLI."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    surfaces = tuple(args.surface) if args.surface else DEFAULT_SURFACES
    excluded_parts = set(EXCLUDED_PARTS)
    documents = read_documents(root, surfaces, args.exclude, excluded_parts)
    hits = search(documents, args.query, max(args.top, 0))
    if args.format == "json":
        print_json(hits, len(documents))
    else:
        print_text(hits, len(documents))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
