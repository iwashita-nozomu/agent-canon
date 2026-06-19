#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Coordinates purpose-based search across text, local LLM cards, tool catalog, dependency headers, and Python code facts.
# upstream design ../../documents/search-coordination.md coordinated search provider contract
# upstream implementation ./vector_search.py provides text surfaces, TF-IDF search, dependency headers, and Python code facts
# upstream implementation ./search_index.py builds repo-local local-LLM semantic search cards
# downstream implementation ../../tests/agent_tools/test_search.py validates coordinated search providers
# @dependency-end
"""Coordinate AgentCanon search providers from one purpose string."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import search_index  # noqa: E402
import vector_search  # noqa: E402

DEFAULT_PROVIDERS = ("text", "llm", "vector", "tool", "header-deps", "code-deps")
DEFAULT_INDEX_DIR = search_index.DEFAULT_INDEX_DIR
DEFAULT_TOP = 12
PROVIDER_BONUS = 0.15
PHRASE_MATCH_BONUS = 0.35
HEADER_TARGET_SCORE_MULTIPLIER = 0.95
JSON_SCORE_DECIMALS = 6
SNIPPET_ELLIPSIS_CHARS = 3
TEXT_EVIDENCE_LIMIT = 3
SNIPPET_LIMIT = 180


@dataclass(frozen=True)
class QueryProfile:
    """Normalized search purpose."""

    raw: str
    terms: frozenset[str]

    def score_text(self, text: str) -> float:
        """Score text by phrase and token overlap."""
        normalized = text.lower()
        tokens = frozenset(search_index.tokenize(text))
        overlap = len(self.terms & tokens) / max(len(self.terms), 1)
        phrase_bonus = PHRASE_MATCH_BONUS if self.raw.lower() in normalized else 0.0
        return overlap + phrase_bonus


@dataclass(frozen=True)
class SearchRequest:
    """Inputs for one coordinated search."""

    root: Path
    query: QueryProfile
    providers: tuple[str, ...]
    surfaces: tuple[str, ...]
    excludes: tuple[str, ...]
    index_dir: Path
    top: int
    refresh_index: bool
    run_llm: bool
    llama_cli: str
    model: str
    max_llm_files: int
    max_bytes: int


@dataclass(frozen=True)
class SearchCorpus:
    """Loaded repository facts shared by providers."""

    documents: tuple[vector_search.Document, ...]
    tool_entries: Mapping[str, search_index.ToolEntry]
    cards: tuple[search_index.SearchCard, ...]
    dependency_edges: tuple[vector_search.DependencyEdge, ...]
    python_symbols: tuple[vector_search.PythonSymbol, ...]
    python_edges: tuple[vector_search.PythonCallEdge, ...]


@dataclass(frozen=True)
class ProviderHit:
    """One provider-specific search hit before aggregation."""

    provider: str
    path: str
    score: float
    reason: str
    evidence: str

    def as_json(self) -> Mapping[str, object]:
        """Return a stable JSON mapping."""
        return {
            "provider": self.provider,
            "path": self.path,
            "score": round(self.score, JSON_SCORE_DECIMALS),
            "reason": self.reason,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class Candidate:
    """Aggregated search candidate."""

    path: str
    score: float
    providers: tuple[str, ...]
    reasons: tuple[str, ...]
    evidence: tuple[ProviderHit, ...]

    def as_json(self) -> Mapping[str, object]:
        """Return a stable JSON mapping."""
        return {
            "path": self.path,
            "score": round(self.score, JSON_SCORE_DECIMALS),
            "providers": list(self.providers),
            "reasons": list(self.reasons),
            "evidence": [hit.as_json() for hit in self.evidence],
        }


@dataclass(frozen=True)
class SearchReport:
    """Complete search result."""

    query: str
    providers: tuple[str, ...]
    candidates: tuple[Candidate, ...]
    provider_hits: tuple[ProviderHit, ...]

    def as_json(self) -> Mapping[str, object]:
        """Return a stable JSON mapping."""
        return {
            "status": "pass",
            "query": self.query,
            "providers": list(self.providers),
            "candidates": [candidate.as_json() for candidate in self.candidates],
            "provider_hits": [hit.as_json() for hit in self.provider_hits],
        }


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--query", default="")
    parser.add_argument("--query-file", type=Path, default=None)
    parser.add_argument("--query-stdin", action="store_true")
    parser.add_argument("--purpose", default="")
    parser.add_argument("--providers", default=",".join(DEFAULT_PROVIDERS))
    parser.add_argument("--surface", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--index-dir", default=DEFAULT_INDEX_DIR)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument("--refresh-index", action="store_true")
    parser.add_argument("--run-llm", action="store_true")
    parser.add_argument("--llama-cli", default="")
    parser.add_argument("--model", default=search_index.DEFAULT_MODEL)
    parser.add_argument("--max-llm-files", type=int, default=search_index.DEFAULT_LLM_FILES)
    parser.add_argument("--max-bytes", type=int, default=search_index.DEFAULT_MAX_BYTES)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def query_profile(query: str) -> QueryProfile:
    """Normalize a user purpose into terms."""
    terms = frozenset(token for token in search_index.tokenize(query) if len(token) > 1)
    return QueryProfile(raw=query.strip(), terms=terms)


def selected_providers(raw: str) -> tuple[str, ...]:
    """Parse provider names."""
    names = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
    return names or DEFAULT_PROVIDERS


def snippet(text: str, limit: int = SNIPPET_LIMIT) -> str:
    """Return compact evidence text."""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - SNIPPET_ELLIPSIS_CHARS]}..."


def load_index_cards(request: SearchRequest) -> tuple[search_index.SearchCard, ...]:
    """Load or build local LLM search cards."""
    card_file = request.index_dir / search_index.DEFAULT_CARD_FILE
    if request.refresh_index:
        cards, llm_used, llm_unavailable = search_index.build_cards(
            search_index.BuildOptions(
                root=request.root,
                surfaces=request.surfaces,
                excludes=request.excludes,
                run_llm=request.run_llm,
                require_llm=False,
                llama_cli_arg=request.llama_cli,
                model=request.model,
                max_llm_files=request.max_llm_files,
                max_bytes=request.max_bytes,
            )
        )
        report = search_index.BuildReport(
            index_dir=request.index_dir,
            card_file=card_file,
            state_file=request.index_dir / search_index.DEFAULT_STATE_FILE,
            cards=cards,
            llm_requested=request.run_llm,
            llm_used=llm_used,
            llm_unavailable=llm_unavailable,
        )
        search_index.write_jsonl(report.card_file, cards)
        search_index.write_state(report.state_file, report, request.root, request.model)
        return cards
    loaded_cards = search_index.load_cards(card_file)
    if loaded_cards:
        return loaded_cards
    cards, _, _ = search_index.build_cards(
        search_index.BuildOptions(
            root=request.root,
            surfaces=request.surfaces,
            excludes=request.excludes,
            run_llm=False,
            require_llm=False,
            llama_cli_arg="",
            model=request.model,
            max_llm_files=0,
            max_bytes=request.max_bytes,
        )
    )
    return cards


def load_corpus(request: SearchRequest) -> SearchCorpus:
    """Load shared facts for providers."""
    documents = tuple(
        vector_search.read_documents(
            request.root,
            request.surfaces or vector_search.DEFAULT_SURFACES,
            request.excludes,
            set(vector_search.EXCLUDED_PARTS),
        )
    )
    symbols = vector_search.read_python_symbols(documents)
    return SearchCorpus(
        documents=documents,
        tool_entries=search_index.load_tool_entries(request.root),
        cards=load_index_cards(request),
        dependency_edges=tuple(vector_search.parse_dependency_edges(request.root, documents)),
        python_symbols=symbols,
        python_edges=vector_search.build_python_call_edges(symbols),
    )


ProviderFunction = Callable[[SearchRequest, SearchCorpus], tuple[ProviderHit, ...]]


def text_hits(request: SearchRequest, corpus: SearchCorpus) -> tuple[ProviderHit, ...]:
    """Return raw text search hits."""
    hits: list[ProviderHit] = []
    for document in corpus.documents:
        score = request.query.score_text(f"{document.relative_path}\n{document.text}")
        if score <= 0.0:
            continue
        hits.append(
            ProviderHit(
                provider="text",
                path=document.relative_path,
                score=score,
                reason="text-token-overlap",
                evidence=snippet(document.text),
            )
        )
    return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.path))[: request.top])


def vector_hits(request: SearchRequest, corpus: SearchCorpus) -> tuple[ProviderHit, ...]:
    """Return TF-IDF vector search hits."""
    hits = vector_search.search(corpus.documents, request.query.raw, request.top)
    return tuple(
        ProviderHit(
            provider="vector",
            path=hit.relative_path,
            score=hit.score,
            reason="tfidf-vector",
            evidence=hit.snippet,
        )
        for hit in hits
    )


def llm_hits(request: SearchRequest, corpus: SearchCorpus) -> tuple[ProviderHit, ...]:
    """Return local LLM semantic card hits."""
    hits: list[ProviderHit] = []
    for card in corpus.cards:
        score = request.query.score_text(card.searchable_text())
        if score <= 0.0:
            continue
        hits.append(
            ProviderHit(
                provider="llm",
                path=card.path,
                score=score,
                reason=f"semantic-card:{card.generated_by}",
                evidence=snippet(card.summary or card.responsibility),
            )
        )
    return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.path))[: request.top])


def tool_hits(request: SearchRequest, corpus: SearchCorpus) -> tuple[ProviderHit, ...]:
    """Return structured tool-catalog hits."""
    hits: list[ProviderHit] = []
    for entry in corpus.tool_entries.values():
        searchable = f"{entry.path}\n{entry.searchable_text()}"
        score = request.query.score_text(searchable)
        if score <= 0.0:
            continue
        hits.append(
            ProviderHit(
                provider="tool",
                path=entry.path,
                score=score,
                reason=f"tool-catalog:{entry.tool_id}",
                evidence=snippet(entry.summary),
            )
        )
    return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.path))[: request.top])


def header_dependency_hits(request: SearchRequest, corpus: SearchCorpus) -> tuple[ProviderHit, ...]:
    """Return dependency-header hits."""
    hits: list[ProviderHit] = []
    for edge in corpus.dependency_edges:
        searchable = f"{edge.source} {edge.target} {edge.direction} {edge.kind} {edge.reason}"
        score = request.query.score_text(searchable)
        if score <= 0.0:
            continue
        evidence = f"{edge.source} {edge.direction} {edge.kind} {edge.target} {edge.reason}"
        hits.append(
            ProviderHit(
                provider="header-deps",
                path=edge.source,
                score=score,
                reason="declared-dependency-source",
                evidence=snippet(evidence),
            )
        )
        hits.append(
            ProviderHit(
                provider="header-deps",
                path=edge.target,
                    score=score * HEADER_TARGET_SCORE_MULTIPLIER,
                reason="declared-dependency-target",
                evidence=snippet(evidence),
            )
        )
    return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.path))[: request.top])


def code_symbol_hits(
    request: SearchRequest,
    symbols: Sequence[vector_search.PythonSymbol],
) -> tuple[ProviderHit, ...]:
    """Return Python symbol hits."""
    hits: list[ProviderHit] = []
    for symbol in symbols:
        searchable = f"{symbol.relative_path} {symbol.name} {symbol.qualname} {symbol.kind} {' '.join(symbol.calls)}"
        score = request.query.score_text(searchable)
        if score <= 0.0:
            continue
        hits.append(
            ProviderHit(
                provider="code-deps",
                path=symbol.relative_path,
                score=score,
                reason=f"python-symbol:{symbol.qualname}",
                evidence=snippet(searchable),
            )
        )
    return tuple(hits)


def code_edge_hits(
    request: SearchRequest,
    symbols: Sequence[vector_search.PythonSymbol],
    edges: Sequence[vector_search.PythonCallEdge],
) -> tuple[ProviderHit, ...]:
    """Return Python call-edge hits."""
    by_id = {symbol.symbol_id: symbol for symbol in symbols}
    hits: list[ProviderHit] = []
    for edge in edges:
        caller = by_id[edge.caller]
        callee = by_id[edge.callee]
        searchable = f"{caller.relative_path} {caller.qualname} calls {callee.qualname} {edge.call_name}"
        score = request.query.score_text(searchable)
        if score <= 0.0:
            continue
        hits.append(
            ProviderHit(
                provider="code-deps",
                path=caller.relative_path,
                score=score,
                reason="python-call-edge",
                evidence=snippet(searchable),
            )
        )
    return tuple(hits)


def code_dependency_hits(request: SearchRequest, corpus: SearchCorpus) -> tuple[ProviderHit, ...]:
    """Return code dependency hits."""
    hits = (
        *code_symbol_hits(request, corpus.python_symbols),
        *code_edge_hits(request, corpus.python_symbols, corpus.python_edges),
    )
    return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.path))[: request.top])


def provider_registry() -> Mapping[str, ProviderFunction]:
    """Return provider instances keyed by name."""
    return {
        "text": text_hits,
        "vector": vector_hits,
        "llm": llm_hits,
        "tool": tool_hits,
        "header-deps": header_dependency_hits,
        "code-deps": code_dependency_hits,
    }


def provider_hits(request: SearchRequest, corpus: SearchCorpus) -> tuple[ProviderHit, ...]:
    """Run selected providers."""
    registry = provider_registry()
    hits: list[ProviderHit] = []
    for name in request.providers:
        provider = registry.get(name)
        if provider is None:
            continue
        hits.extend(provider(request, corpus))
    return tuple(hits)


def build_candidates(hits: Sequence[ProviderHit], top: int) -> tuple[Candidate, ...]:
    """Aggregate provider hits into path candidates."""
    grouped: dict[str, list[ProviderHit]] = defaultdict(list)
    for hit in hits:
        grouped[hit.path].append(hit)
    candidates: list[Candidate] = []
    for path, path_hits in grouped.items():
        providers = tuple(dict.fromkeys(hit.provider for hit in path_hits))
        reasons = tuple(dict.fromkeys(hit.reason for hit in path_hits))
        score = sum(hit.score for hit in path_hits) + (len(providers) - 1) * PROVIDER_BONUS
        candidates.append(
            Candidate(
                path=path,
                score=score,
                providers=providers,
                reasons=reasons,
                evidence=tuple(sorted(path_hits, key=lambda hit: (-hit.score, hit.provider))),
            )
        )
    return tuple(sorted(candidates, key=lambda item: (-item.score, item.path))[:top])


def query_text_from_args(args: argparse.Namespace) -> str:
    """Resolve the query source while preserving purpose/query precedence."""
    if args.query_file is not None and bool(args.query_stdin):
        raise ValueError("query-file-and-query-stdin-are-mutually-exclusive")
    inline_query = str(args.purpose or args.query).strip()
    if inline_query:
        return inline_query
    if args.query_file is not None:
        try:
            return args.query_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError(f"query-file-read-failed:{args.query_file}") from exc
        except UnicodeDecodeError as exc:
            raise ValueError(f"query-file-decode-failed:{args.query_file}") from exc
    if bool(args.query_stdin):
        return sys.stdin.read().strip()
    return ""


def build_request(args: argparse.Namespace) -> SearchRequest:
    """Build a search request from CLI args."""
    query = query_text_from_args(args)
    if not query:
        raise ValueError("query-or-purpose-required")
    root = args.root.resolve()
    return SearchRequest(
        root=root,
        query=query_profile(query),
        providers=selected_providers(str(args.providers)),
        surfaces=tuple(args.surface),
        excludes=tuple(args.exclude),
        index_dir=(root / str(args.index_dir)).resolve(),
        top=max(int(args.top), 1),
        refresh_index=bool(args.refresh_index),
        run_llm=bool(args.run_llm),
        llama_cli=str(args.llama_cli),
        model=str(args.model),
        max_llm_files=int(args.max_llm_files),
        max_bytes=int(args.max_bytes),
    )


def run_search(request: SearchRequest) -> SearchReport:
    """Run coordinated search."""
    corpus = load_corpus(request)
    hits = provider_hits(request, corpus)
    return SearchReport(
        query=request.query.raw,
        providers=request.providers,
        candidates=build_candidates(hits, request.top),
        provider_hits=hits,
    )


def print_text(report: SearchReport) -> None:
    """Print stable machine-readable text output."""
    print("AGENT_SEARCH=pass")
    print(f"AGENT_SEARCH_QUERY={json.dumps(report.query, ensure_ascii=False)}")
    print(f"AGENT_SEARCH_PROVIDERS={','.join(report.providers)}")
    print(f"AGENT_SEARCH_CANDIDATES={len(report.candidates)}")
    for candidate in report.candidates:
        print(
            "CANDIDATE="
            f"{candidate.score:.6f}\t{candidate.path}\tproviders={','.join(candidate.providers)}"
        )
        for hit in candidate.evidence[:TEXT_EVIDENCE_LIMIT]:
            print(
                "EVIDENCE="
                f"{hit.provider}\t{hit.score:.6f}\t{hit.reason}\t{json.dumps(hit.evidence, ensure_ascii=False)}"
            )


def print_json(report: SearchReport) -> None:
    """Print JSON output."""
    print(json.dumps(report.as_json(), ensure_ascii=False, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the coordinated search CLI."""
    args = build_parser().parse_args(argv)
    try:
        request = build_request(args)
    except ValueError as exc:
        print("AGENT_SEARCH=fail", file=sys.stderr)
        print(f"AGENT_SEARCH_ERROR={exc}", file=sys.stderr)
        return 2
    report = run_search(request)
    if args.format == "json":
        print_json(report)
    else:
        print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
