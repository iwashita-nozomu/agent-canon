#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Routes explicit repository-search requests to native text, semantic-index, catalog, dependency, and LSP owners without cross-provider ranking.
# upstream design ../../../documents/tools/search-coordination.md staged search owner contract
# upstream implementation ../../runtime/dispatch/agent-canon/src/semantic_index/mod.rs owns semantic-index search
# upstream implementation ../dependencies/graph_client.py owns source-derived dependency facts
# upstream implementation ../code/lsp_code_analysis.py owns LSP code facts and bounded file discovery
# upstream design ../../catalog.yaml owns structured tool metadata
# downstream implementation ../../../tests/agent_tools/test_search.py validates provider routing and failure semantics
# @dependency-end
"""Route explicit AgentCanon search requests to their owning native providers."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.analysis.code import lsp_code_analysis  # noqa: E402
from tools.analysis.dependencies.graph_client import (  # noqa: E402
    GraphClient,
    GraphClientError,
)

DEFAULT_TOP = 12
PROVIDERS = frozenset({"text", "semantic", "tool", "header-deps", "code-deps"})
SEMANTIC_INDEX_COMMAND = "agent-canon"


@dataclass(frozen=True)
class SearchRequest:
    """One provider-selected request and its original query source."""

    root: Path
    query: str
    providers: tuple[str, ...]
    surfaces: tuple[str, ...]
    excludes: tuple[str, ...]
    query_file: Path | None
    query_stdin: bool
    regex: bool
    word_regexp: bool
    case_sensitive: bool
    top: int


@dataclass(frozen=True)
class ProviderResult:
    """One provider-native result; providers are never scored together."""

    provider: str
    status: str
    exit_code: int
    result: object
    stderr: str = ""

    def as_json(self) -> Mapping[str, object]:
        """Return the provider result without normalizing its evidence."""
        return {
            "provider": self.provider,
            "status": self.status,
            "exit_code": self.exit_code,
            "result": self.result,
            "stderr": self.stderr,
        }


@dataclass(frozen=True)
class SearchReport:
    """Separate, unranked outputs for the selected provider routes."""

    query: str
    providers: tuple[str, ...]
    results: tuple[ProviderResult, ...]

    @property
    def status(self) -> str:
        """Return failure only when a selected provider failed to execute."""
        if any(result.status == "fail" for result in self.results):
            return "fail"
        return "pass"

    @property
    def exit_code(self) -> int:
        """Return the aggregate process result without hiding provider failures."""
        return 1 if self.status == "fail" else 0

    def as_json(self) -> Mapping[str, object]:
        """Return the separate provider results."""
        return {
            "status": self.status,
            "query": self.query,
            "providers": list(self.providers),
            "results": [result.as_json() for result in self.results],
        }


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--query", default="")
    parser.add_argument("--query-file", type=Path, default=None)
    parser.add_argument("--query-stdin", action="store_true")
    parser.add_argument("--purpose", default="")
    parser.add_argument(
        "--providers",
        default="text",
        help=(
            "Comma-separated explicit owners: text, semantic, tool, header-deps, "
            "code-deps. Defaults to stateless Git text search only."
        ),
    )
    parser.add_argument("--surface", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument(
        "--regex",
        action="store_true",
        help="Interpret Git-backed text/catalog patterns using Git extended regex.",
    )
    parser.add_argument(
        "--word-regexp",
        action="store_true",
        help="Pass Git's native whole-word matching option to text/catalog search.",
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Use Git's default case-sensitive matching instead of --ignore-case.",
    )
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def selected_providers(raw: str) -> tuple[str, ...]:
    """Parse and validate the explicit provider selection."""
    names = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
    if not names:
        raise ValueError("providers-required")
    unknown = tuple(name for name in names if name not in PROVIDERS)
    if unknown:
        raise ValueError(f"unknown-provider:{','.join(unknown)}")
    return names


def query_text_from_args(args: argparse.Namespace) -> tuple[str, Path | None, bool]:
    """Resolve query text while preserving inline/file/stdin precedence."""
    if args.query_file is not None and bool(args.query_stdin):
        raise ValueError("query-file-and-query-stdin-are-mutually-exclusive")
    inline_query = str(args.purpose or args.query)
    if inline_query.strip():
        return inline_query, None, False
    if args.query_file is not None:
        query_file = Path(args.query_file).expanduser().resolve()
        try:
            query = query_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"query-file-read-failed:{query_file}") from exc
        except UnicodeDecodeError as exc:
            raise ValueError(f"query-file-decode-failed:{query_file}") from exc
        if not query.strip():
            raise ValueError("query-or-purpose-required")
        return query, query_file, False
    if bool(args.query_stdin):
        query = sys.stdin.read()
        if not query.strip():
            raise ValueError("query-or-purpose-required")
        return query, None, True
    raise ValueError("query-or-purpose-required")


def build_request(args: argparse.Namespace) -> SearchRequest:
    """Build one request without enabling unselected search providers."""
    query, query_file, query_stdin = query_text_from_args(args)
    return SearchRequest(
        root=args.root.resolve(),
        query=query,
        providers=selected_providers(str(args.providers)),
        surfaces=tuple(str(value) for value in args.surface),
        excludes=tuple(str(value) for value in args.exclude),
        query_file=query_file,
        query_stdin=query_stdin,
        regex=bool(args.regex),
        word_regexp=bool(args.word_regexp),
        case_sensitive=bool(args.case_sensitive),
        top=max(int(args.top), 1),
    )


def git_search_argv(
    request: SearchRequest, pathspecs: Sequence[str]
) -> tuple[str, ...]:
    """Build native Git grep argv for the original query source."""
    argv = [
        "git",
        "grep",
        "--untracked",
        "--exclude-standard",
        "--no-color",
        "--full-name",
        "--line-number",
        "-I",
        "--max-count",
        str(request.top),
    ]
    if not request.case_sensitive:
        argv.append("--ignore-case")
    if request.regex:
        argv.append("--extended-regexp")
    else:
        argv.append("--fixed-strings")
    if request.word_regexp:
        argv.append("--word-regexp")
    if request.query_file is not None:
        argv.extend(("-f", str(request.query_file)))
    elif request.query_stdin:
        argv.extend(("-f", "-"))
    else:
        argv.extend(("-e", request.query))
    argv.append("--")
    argv.extend(pathspecs)
    argv.extend(f":(exclude){value}" for value in request.excludes)
    return tuple(argv)


def git_provider_result(
    request: SearchRequest,
    provider: str,
    pathspecs: Sequence[str],
) -> ProviderResult:
    """Run Git's native pattern search and preserve its raw output/status."""
    try:
        completed = subprocess.run(
            git_search_argv(request, pathspecs),
            cwd=request.root,
            check=False,
            capture_output=True,
            text=True,
            input=request.query if request.query_stdin else None,
        )
    except OSError as exc:
        return ProviderResult(provider, "fail", 127, "", str(exc))
    if completed.returncode == 0:
        status = "pass"
    elif completed.returncode == 1:
        status = "no_match"
    else:
        status = "fail"
    return ProviderResult(
        provider,
        status,
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )


def run_text_provider(request: SearchRequest) -> ProviderResult:
    """Search the selected paths or the current repository with Git."""
    return git_provider_result(request, "text", request.surfaces)


def run_tool_provider(request: SearchRequest) -> ProviderResult:
    """Search the canonical tool catalog with Git's native pattern contract."""
    return git_provider_result(request, "tool", ("tools/catalog.yaml",))


def run_semantic_provider(request: SearchRequest) -> ProviderResult:
    """Delegate ranked semantic search to the resident Rust semantic-index owner."""
    argv = [
        SEMANTIC_INDEX_COMMAND,
        "semantic-index",
        "search",
        "--root",
        str(request.root),
        "--top-k",
        str(request.top),
        "--format",
        "json",
    ]
    if request.query_file is not None:
        argv.extend(("--query-file", str(request.query_file)))
        query_stdin = None
    elif request.query_stdin:
        argv.append("--query-stdin")
        query_stdin = request.query
    else:
        argv.extend(("--query", request.query))
        query_stdin = None
    try:
        completed = subprocess.run(
            argv,
            cwd=request.root,
            check=False,
            capture_output=True,
            text=True,
            input=query_stdin,
        )
    except OSError as exc:
        return ProviderResult("semantic", "fail", 127, "", str(exc))
    status = "pass" if completed.returncode == 0 else "fail"
    return ProviderResult(
        "semantic",
        status,
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )


def run_dependency_provider(request: SearchRequest) -> ProviderResult:
    """Read source-bound dependency context for the selected paths."""
    paths = request.surfaces or (request.query,)
    try:
        client = GraphClient(request.root)
        contexts = [client.context(path).payload for path in paths]
    except GraphClientError as exc:
        return ProviderResult("header-deps", "fail", 1, [], str(exc))
    return ProviderResult("header-deps", "pass", 0, contexts)


def run_code_provider(request: SearchRequest) -> ProviderResult:
    """Return exact-query LSP facts for selected or bounded default code surfaces."""
    files = lsp_code_analysis.discover_lsp_files(
        request.root,
        request.surfaces,
        request.excludes,
    )
    report = lsp_code_analysis.analyze(request.root, files)
    status = "pass" if report.status == "complete" else "fail"
    payload = report.as_json(request.root)
    query = request.query.casefold()
    for field in ("symbols", "relations", "lexical_candidates"):
        values = payload.get(field)
        if isinstance(values, list):
            payload[field] = [
                item
                for item in values
                if query in json.dumps(item, ensure_ascii=False).casefold()
            ]
    return ProviderResult(
        "code-deps",
        status,
        0 if status == "pass" else 1,
        payload,
    )


def run_provider(request: SearchRequest, provider: str) -> ProviderResult:
    """Run exactly one selected owner and return its independent result."""
    if provider == "text":
        return run_text_provider(request)
    if provider == "semantic":
        return run_semantic_provider(request)
    if provider == "tool":
        return run_tool_provider(request)
    if provider == "header-deps":
        return run_dependency_provider(request)
    if provider == "code-deps":
        return run_code_provider(request)
    raise ValueError(f"unknown-provider:{provider}")


def run_search(request: SearchRequest) -> SearchReport:
    """Run only requested providers and preserve their independent results."""
    return SearchReport(
        query=request.query,
        providers=request.providers,
        results=tuple(run_provider(request, provider) for provider in request.providers),
    )


def print_text(report: SearchReport) -> None:
    """Print provider-native output without score or candidate fusion."""
    print(f"AGENT_SEARCH={report.status}")
    print(f"AGENT_SEARCH_QUERY={json.dumps(report.query, ensure_ascii=False)}")
    print(f"AGENT_SEARCH_PROVIDERS={','.join(report.providers)}")
    for result in report.results:
        print(
            f"PROVIDER_RESULT={result.provider}\tstatus={result.status}"
            f"\texit_code={result.exit_code}"
        )
        if isinstance(result.result, str):
            if result.result:
                sys.stdout.write(result.result)
                if not result.result.endswith("\n"):
                    sys.stdout.write("\n")
        else:
            print(json.dumps(result.result, ensure_ascii=False, indent=2))
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")


def print_json(report: SearchReport) -> None:
    """Print separate provider-native outputs as one transport envelope."""
    print(json.dumps(report.as_json(), ensure_ascii=False, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the explicit search-provider router."""
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
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
