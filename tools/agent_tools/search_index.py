#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Builds repo-local semantic search cards for coordinated AgentCanon search.
# upstream design ../../documents/search-coordination.md coordinated search provider contract
# upstream implementation ./vector_search.py scans shared text surfaces
# upstream implementation ./file_responsibility_llm.py resolves llama.cpp local model settings
# downstream implementation ./search.py consumes search cards as the LLM search provider
# downstream implementation ../../tests/agent_tools/test_search_index.py validates index generation
# @dependency-end
"""Build repo-local search cards for first-class LLM-backed search."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import vector_search  # noqa: E402
from file_responsibility_llm import DEFAULT_MODEL, find_llama_cli, local_llm_cpu_env  # noqa: E402

DEFAULT_INDEX_DIR = ".agent-canon/search-index"
DEFAULT_CARD_FILE = "llm-cards.jsonl"
DEFAULT_STATE_FILE = "index-state.json"
SCHEMA_VERSION = 1
DEFAULT_MAX_BYTES = 16_000
DEFAULT_LLM_FILES = 32
CONCEPT_LIMIT = 16
SUMMARY_CHARS = 220
DEFAULT_HASH_LENGTH = 12
ELLIPSIS_CHARS = 3
TOKEN_RE = re.compile(r"[0-9A-Za-z_\u0080-\uFFFF]+")


@dataclass(frozen=True)
class ToolEntry:
    """One structured tool-catalog entry relevant to search."""

    tool_id: str
    path: str
    summary: str
    family: str
    role: str
    docs: tuple[str, ...]
    tests: tuple[str, ...]
    present: bool = True

    def searchable_text(self) -> str:
        """Return compact metadata text for deterministic concept extraction."""
        return " ".join(
            (
                self.tool_id,
                self.summary,
                self.family,
                self.role,
                " ".join(self.docs),
                " ".join(self.tests),
            )
        )

    def related_tool_ids(self) -> tuple[str, ...]:
        """Return the related tool id tuple for cards."""
        if self.tool_id:
            return (self.tool_id,)
        return ()


EMPTY_TOOL_ENTRY = ToolEntry(
    tool_id="",
    path="",
    summary="",
    family="",
    role="",
    docs=(),
    tests=(),
    present=False,
)


@dataclass(frozen=True)
class SearchCard:
    """One searchable semantic card."""

    schema_version: int
    card_id: str
    path: str
    kind: str
    line_start: int
    line_end: int
    chunk_hash: str
    summary: str
    concepts: tuple[str, ...]
    aliases: tuple[str, ...]
    responsibility: str
    owner: str
    related_tools: tuple[str, ...]
    related_docs: tuple[str, ...]
    related_tests: tuple[str, ...]
    ambiguity_notes: tuple[str, ...]
    generated_by: str

    def as_json(self) -> dict[str, object]:
        """Return a JSON-serializable mapping."""
        return asdict(self)

    def searchable_text(self) -> str:
        """Return text used by search providers."""
        fields = (
            self.path,
            self.kind,
            self.summary,
            " ".join(self.concepts),
            " ".join(self.aliases),
            self.responsibility,
            " ".join(self.related_tools),
            " ".join(self.related_docs),
            " ".join(self.related_tests),
            " ".join(self.ambiguity_notes),
        )
        return "\n".join(field for field in fields if field)


@dataclass(frozen=True)
class BuildReport:
    """Search index build result."""

    index_dir: Path
    card_file: Path
    state_file: Path
    cards: tuple[SearchCard, ...]
    llm_requested: bool
    llm_used: int
    llm_unavailable: bool


@dataclass(frozen=True)
class BuildOptions:
    """Inputs that define one index build."""

    root: Path
    surfaces: tuple[str, ...]
    excludes: tuple[str, ...]
    run_llm: bool
    require_llm: bool
    llama_cli_arg: str
    model: str
    max_llm_files: int
    max_bytes: int


@dataclass(frozen=True)
class LlmInvocation:
    """One local LLM card-refinement request."""

    document: vector_search.Document
    base_card: SearchCard
    llama_cli: str
    model: str
    max_bytes: int


@dataclass(frozen=True)
class LlmCardResult:
    """Local LLM refinement result."""

    card: SearchCard
    used: bool


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "refresh"), help="Index operation.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--index-dir", default=DEFAULT_INDEX_DIR)
    parser.add_argument("--surface", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--run-llm", action="store_true")
    parser.add_argument("--require-llm", action="store_true")
    parser.add_argument("--llama-cli", default=os.environ.get("AGENT_CANON_LLAMA_CLI", ""))
    parser.add_argument("--model", default=os.environ.get("AGENT_CANON_LOCAL_LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--max-llm-files", type=int, default=DEFAULT_LLM_FILES)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def stable_hash(text: str, length: int = DEFAULT_HASH_LENGTH) -> str:
    """Return a short stable SHA-256 digest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def tokenize(text: str) -> tuple[str, ...]:
    """Tokenize text for deterministic card summaries."""
    return tuple(token.lower() for token in TOKEN_RE.findall(text.replace("-", " ")))


def compact(text: str, limit: int = SUMMARY_CHARS) -> str:
    """Return compact one-line text."""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - ELLIPSIS_CHARS]}..."


def owner_for_path(path: str) -> str:
    """Return the default owner class for a path."""
    if path.startswith(("tools/", "agents/", ".agents/", ".codex/", "mcp/")):
        return "agent-canon"
    if path.startswith("documents/"):
        return "agent-canon-doc"
    return "repo-local"


def kind_for_path(path: str, tool: ToolEntry) -> str:
    """Return the semantic card kind for a path."""
    if tool.present:
        return "tool"
    suffix = Path(path).suffix
    if suffix == ".py":
        return "python"
    if suffix == ".md":
        return "document"
    if suffix in {".toml", ".yaml", ".yml", ".json"}:
        return "config"
    if suffix == ".sh":
        return "shell"
    return "text"


def responsibility_from_text(text: str) -> str:
    """Extract dependency-header responsibility text when available."""
    for raw_line in text.splitlines()[: vector_search.HEADER_SCAN_LINES]:
        line = vector_search.strip_manifest_line(raw_line)
        if line.startswith("responsibility "):
            return line.removeprefix("responsibility ").strip()
    return ""


def heading_or_first_line(text: str) -> str:
    """Extract a compact heading or first meaningful line."""
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("#").strip()
        if line and not line.startswith(("@dependency", "<!--", "-->", "#!", "//")):
            return compact(line)
    return ""


def top_concepts(path: str, text: str, tool: ToolEntry) -> tuple[str, ...]:
    """Return deterministic concept tokens for one card."""
    seed = f"{path}\n{text}\n{tool.searchable_text()}"
    counts = Counter(token for token in tokenize(seed) if len(token) > 2)
    concepts = [token for token, _ in counts.most_common(CONCEPT_LIMIT)]
    return tuple(dict.fromkeys(concepts))


def path_aliases(path: str, tool: ToolEntry) -> tuple[str, ...]:
    """Return path-derived aliases."""
    parts: list[str] = []
    path_obj = Path(path)
    parts.extend(path_obj.parts)
    parts.append(path_obj.stem)
    parts.extend((tool.tool_id, tool.family, tool.role))
    aliases: list[str] = []
    for part in parts:
        aliases.extend(tokenize(part))
    return tuple(dict.fromkeys(alias for alias in aliases if alias))


def mapping_string(value: Mapping[str, object], key: str) -> str:
    """Read one string field from a mapping."""
    raw_value = value.get(key, "")
    return raw_value if isinstance(raw_value, str) else ""


def mapping_int(value: Mapping[str, object], key: str, default: int) -> int:
    """Read one integer field from a mapping."""
    raw_value = value.get(key, default)
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str):
        return int(raw_value)
    return default


def mapping_string_tuple(value: Mapping[str, object], key: str) -> tuple[str, ...]:
    """Read one string-list field from a mapping."""
    raw_value = value.get(key, ())
    if not isinstance(raw_value, list):
        return ()
    items = cast(list[object], raw_value)
    return tuple(item for item in items if isinstance(item, str))


def load_tool_entries(root: Path) -> dict[str, ToolEntry]:
    """Load structured tool catalog entries keyed by path."""
    catalog_path = root / "tools" / "catalog.yaml"
    if not catalog_path.is_file():
        return {}
    raw_data: object = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    data: Mapping[str, object] = cast(Mapping[str, object], raw_data) if isinstance(raw_data, dict) else {}
    raw_entries = data.get("entries", ())
    entries: list[object] = cast(list[object], raw_entries) if isinstance(raw_entries, list) else []
    result: dict[str, ToolEntry] = {}
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            continue
        entry = cast(Mapping[str, object], raw_entry)
        path = mapping_string(entry, "path")
        if not path:
            continue
        result[path] = ToolEntry(
            tool_id=mapping_string(entry, "id"),
            path=path,
            summary=mapping_string(entry, "summary"),
            family=mapping_string(entry, "family"),
            role=mapping_string(entry, "role"),
            docs=mapping_string_tuple(entry, "docs"),
            tests=mapping_string_tuple(entry, "tests"),
            present=True,
        )
    return result


def deterministic_card(document: vector_search.Document, tool: ToolEntry) -> SearchCard:
    """Build a search card without invoking a model."""
    text = document.text
    responsibility = responsibility_from_text(text)
    summary = tool.summary or responsibility or heading_or_first_line(text)
    chunk_hash = stable_hash(text)
    return SearchCard(
        schema_version=SCHEMA_VERSION,
        card_id=stable_hash(f"{document.relative_path}:{chunk_hash}"),
        path=document.relative_path,
        kind=kind_for_path(document.relative_path, tool),
        line_start=1,
        line_end=max(len(text.splitlines()), 1),
        chunk_hash=chunk_hash,
        summary=summary,
        concepts=top_concepts(document.relative_path, text, tool),
        aliases=path_aliases(document.relative_path, tool),
        responsibility=responsibility,
        owner=owner_for_path(document.relative_path),
        related_tools=tool.related_tool_ids(),
        related_docs=tool.docs,
        related_tests=tool.tests,
        ambiguity_notes=(),
        generated_by="heuristic",
    )


def llm_prompt(document: vector_search.Document, card: SearchCard, max_bytes: int) -> str:
    """Return a prompt that asks a local LLM to produce one search card."""
    text = document.text.encode("utf-8", errors="replace")[:max_bytes].decode(
        "utf-8",
        errors="replace",
    )
    return "\n".join(
        [
            "You create semantic search cards for a software repository.",
            "Return one compact JSON object only.",
            "Required keys: summary, concepts, aliases, responsibility, ambiguity_notes.",
            "Use short arrays of strings for concepts, aliases, and ambiguity_notes.",
            "The card is used for purpose-based search, tool search, and ambiguous code/document discovery.",
            "",
            f"Path: {document.relative_path}",
            f"Heuristic summary: {card.summary}",
            f"Heuristic concepts: {', '.join(card.concepts)}",
            "",
            "Content:",
            "```",
            text,
            "```",
        ]
    )


def extract_json_object(text: str) -> dict[str, object] | None:
    """Extract the first JSON object from model output."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return cast(dict[str, object], value) if isinstance(value, dict) else None


def string_tuple(value: object) -> tuple[str, ...]:
    """Return a tuple of string values from model JSON."""
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        items = cast(list[object], value)
        return tuple(item for item in items if isinstance(item, str))
    return ()


def card_from_llm_payload(base_card: SearchCard, payload: Mapping[str, object]) -> SearchCard:
    """Merge model JSON into a search card."""
    summary = str(payload.get("summary", base_card.summary)).strip() or base_card.summary
    responsibility = str(payload.get("responsibility", base_card.responsibility)).strip()
    concepts = string_tuple(payload.get("concepts")) or base_card.concepts
    aliases = string_tuple(payload.get("aliases")) or base_card.aliases
    ambiguity_notes = string_tuple(payload.get("ambiguity_notes"))
    return SearchCard(
        schema_version=base_card.schema_version,
        card_id=base_card.card_id,
        path=base_card.path,
        kind=base_card.kind,
        line_start=base_card.line_start,
        line_end=base_card.line_end,
        chunk_hash=base_card.chunk_hash,
        summary=summary,
        concepts=concepts,
        aliases=aliases,
        responsibility=responsibility,
        owner=base_card.owner,
        related_tools=base_card.related_tools,
        related_docs=base_card.related_docs,
        related_tests=base_card.related_tests,
        ambiguity_notes=ambiguity_notes,
        generated_by="local-llm",
    )


def card_from_llm_stdout(base_card: SearchCard, stdout: str) -> LlmCardResult:
    """Convert local LLM stdout into a card refinement result."""
    payload = extract_json_object(stdout)
    if payload is None:
        return LlmCardResult(card=base_card, used=False)
    return LlmCardResult(card=card_from_llm_payload(base_card, payload), used=True)


def run_llm_card(invocation: LlmInvocation) -> LlmCardResult:
    """Run local LLM refinement for one search card."""
    prompt = llm_prompt(invocation.document, invocation.base_card, invocation.max_bytes)
    result = subprocess.run(
        [invocation.llama_cli, "-hf", invocation.model, "-p", prompt, "-n", "512", "--temp", "0.1"],
        check=False,
        capture_output=True,
        text=True,
        env=local_llm_cpu_env(),
    )
    if result.returncode != 0:
        return LlmCardResult(card=invocation.base_card, used=False)
    return card_from_llm_stdout(invocation.base_card, result.stdout)


def build_cards(options: BuildOptions) -> tuple[tuple[SearchCard, ...], int, bool]:
    """Build search cards from indexed documents."""
    selected_surfaces = options.surfaces if options.surfaces else vector_search.DEFAULT_SURFACES
    documents = vector_search.read_documents(
        options.root,
        selected_surfaces,
        options.excludes,
        set(vector_search.EXCLUDED_PARTS),
    )
    tool_entries = load_tool_entries(options.root)
    executable = find_llama_cli(options.llama_cli_arg) if options.run_llm else ""
    if options.run_llm and options.require_llm and not executable:
        raise RuntimeError("llama-cli-not-found")

    cards: list[SearchCard] = []
    llm_used = 0
    for document in documents:
        tool = tool_entries.get(document.relative_path, EMPTY_TOOL_ENTRY)
        base_card = deterministic_card(document, tool)
        card = base_card
        if executable and llm_used < max(options.max_llm_files, 0):
            refined = run_llm_card(
                LlmInvocation(
                    document=document,
                    base_card=base_card,
                    llama_cli=executable,
                    model=options.model,
                    max_bytes=options.max_bytes,
                )
            )
            if refined.used:
                card = refined.card
                llm_used += 1
        cards.append(card)
    return tuple(cards), llm_used, bool(options.run_llm and not executable)


def write_jsonl(path: Path, cards: Sequence[SearchCard]) -> None:
    """Write search cards as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for card in cards:
            handle.write(json.dumps(card.as_json(), ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def write_state(path: Path, report: BuildReport, root: Path, model: str) -> None:
    """Write machine-readable index state."""
    state = {
        "schema_version": SCHEMA_VERSION,
        "root": str(root),
        "generated_at": datetime.now(UTC).isoformat(),
        "cards": len(report.cards),
        "llm_requested": report.llm_requested,
        "llm_used": report.llm_used,
        "llm_unavailable": report.llm_unavailable,
        "model": model,
    }
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def build_index(args: argparse.Namespace) -> BuildReport:
    """Build and write the search index."""
    root = args.root.resolve()
    index_dir = (root / args.index_dir).resolve()
    card_file = index_dir / DEFAULT_CARD_FILE
    state_file = index_dir / DEFAULT_STATE_FILE
    cards, llm_used, llm_unavailable = build_cards(
        BuildOptions(
            root=root,
            surfaces=tuple(args.surface),
            excludes=tuple(args.exclude),
            run_llm=bool(args.run_llm),
            require_llm=bool(args.require_llm),
            llama_cli_arg=str(args.llama_cli),
            model=str(args.model),
            max_llm_files=int(args.max_llm_files),
            max_bytes=int(args.max_bytes),
        )
    )
    report = BuildReport(
        index_dir=index_dir,
        card_file=card_file,
        state_file=state_file,
        cards=cards,
        llm_requested=bool(args.run_llm),
        llm_used=llm_used,
        llm_unavailable=llm_unavailable,
    )
    write_jsonl(card_file, cards)
    write_state(state_file, report, root, str(args.model))
    return report


def load_cards(path: Path) -> tuple[SearchCard, ...]:
    """Load search cards from a JSONL file."""
    if not path.is_file():
        return ()
    cards: list[SearchCard] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        if not isinstance(payload, dict):
            continue
        data = cast(dict[str, object], payload)
        cards.append(
            SearchCard(
                schema_version=mapping_int(data, "schema_version", SCHEMA_VERSION),
                card_id=mapping_string(data, "card_id"),
                path=mapping_string(data, "path"),
                kind=mapping_string(data, "kind"),
                line_start=mapping_int(data, "line_start", 1),
                line_end=mapping_int(data, "line_end", 1),
                chunk_hash=mapping_string(data, "chunk_hash"),
                summary=mapping_string(data, "summary"),
                concepts=string_tuple(data.get("concepts")),
                aliases=string_tuple(data.get("aliases")),
                responsibility=mapping_string(data, "responsibility"),
                owner=mapping_string(data, "owner"),
                related_tools=string_tuple(data.get("related_tools")),
                related_docs=string_tuple(data.get("related_docs")),
                related_tests=string_tuple(data.get("related_tests")),
                ambiguity_notes=string_tuple(data.get("ambiguity_notes")),
                generated_by=mapping_string(data, "generated_by"),
            )
        )
    return tuple(cards)


def print_text(report: BuildReport) -> None:
    """Print stable machine-readable text output."""
    print("SEARCH_INDEX=pass")
    print(f"SEARCH_INDEX_DIR={report.index_dir}")
    print(f"SEARCH_INDEX_CARD_FILE={report.card_file}")
    print(f"SEARCH_INDEX_CARDS={len(report.cards)}")
    print(f"SEARCH_INDEX_LLM_REQUESTED={str(report.llm_requested).lower()}")
    print(f"SEARCH_INDEX_LLM_USED={report.llm_used}")
    print(f"SEARCH_INDEX_LLM_UNAVAILABLE={str(report.llm_unavailable).lower()}")


def print_json(report: BuildReport) -> None:
    """Print JSON output."""
    payload: Mapping[str, object] = {
        "status": "pass",
        "index_dir": str(report.index_dir),
        "card_file": str(report.card_file),
        "state_file": str(report.state_file),
        "cards": len(report.cards),
        "llm_requested": report.llm_requested,
        "llm_used": report.llm_used,
        "llm_unavailable": report.llm_unavailable,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the search-index CLI."""
    args = build_parser().parse_args(argv)
    try:
        report = build_index(args)
    except RuntimeError as exc:
        print("SEARCH_INDEX=fail", file=sys.stderr)
        print(f"SEARCH_INDEX_ERROR={exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print_json(report)
    else:
        print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
