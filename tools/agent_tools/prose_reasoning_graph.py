#!/usr/bin/env python3
# @dependency-start
# responsibility Builds and reports SQLite-backed prose reasoning graphs.
# upstream design ../../documents/prose-reasoning-graph/dsl-spec.md normative graph and DSL contract
# upstream design ../../agents/skills/prose-reasoning-graph.md prose graph skill contract
# upstream design ../../agents/workflows/workflow-references.md writing and discourse prior art
# downstream implementation ../../tests/agent_tools/test_prose_reasoning_graph.py tests CLI behavior
# downstream design ../../documents/tools/prose_reasoning_graph.md documents tool contract
# @dependency-end
"""Build and report SQLite-backed prose reasoning graphs."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast
from urllib.parse import quote

import yaml

SCHEMA_VERSION = 1
DEFAULT_PROFILE = "writing"
PROFILES = ("writing", "logic", "experiment", "report", "academic", "paper", "all")
LAYERS = (
    "source",
    "form",
    "concept",
    "phase",
    "discourse",
    "argument",
    "evidence",
    "experiment",
    "presentation",
    "diagnostics",
    "edit-operation",
    "explanation",
    "projection",
)
SKILL_HANDOFF_TARGETS = (
    "$long-form-writing",
    "$report-writing",
    "$academic-writing",
    "$paper-writing",
    "$literature-survey",
    "$structure-planning",
    "logic-gap-review",
    "citation-evidence-review",
    "$experiment-lifecycle",
    "$result-artifact-writeout",
)
CLAIM_CUES = (
    "should",
    "must",
    "need",
    "needs",
    "necessary",
    "therefore",
    "thus",
    "so ",
    "重要",
    "必要",
    "べき",
    "はず",
)
EVIDENCE_CUES = (
    "because",
    "since",
    "evidence",
    "source",
    "shown",
    "measured",
    "doi",
    "http",
    "根拠",
    "出典",
    "証拠",
    "測定",
)
EXPERIMENT_CUES = (
    "hypothesis",
    "experiment",
    "metric",
    "baseline",
    "expected",
    "result",
    "仮説",
    "実験",
    "指標",
    "ベースライン",
    "期待",
    "結果",
)
STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "this",
    "with",
    "from",
    "into",
    "are",
    "is",
    "can",
    "not",
    "but",
    "you",
    "our",
    "their",
    "have",
    "has",
    "must",
    "should",
    "する",
    "です",
    "ます",
    "こと",
    "これ",
    "それ",
    "ため",
}
SQLITE_BUSY_TIMEOUT_SECONDS = 30
WSL_MOUNT_MIN_PATH_PARTS = 3
FORM_NODE_LABEL_WORD_LIMIT = 8
CONCEPT_CANDIDATE_LIMIT = 12
CONCEPT_MIN_TERM_LENGTH = 3
CONCEPT_NODE_CONFIDENCE = 0.6
CONCEPT_EDGE_CONFIDENCE = 0.4
PHASE_INFERENCE_CONFIDENCE = 0.55
DISCOURSE_CONFIDENCE_FLOOR = 0.25
DISCOURSE_CONFIDENCE_CEILING = 0.95
DISCOURSE_CONFIDENCE_OVERLAP_OFFSET = 0.35
DISCOURSE_SHARED_TERM_LIMIT = 8
EXTRACTED_NODE_LABEL_WORD_LIMIT = 10
EXTRACTED_NODE_CONFIDENCE = 0.65
EVIDENCE_SUPPORT_MIN_OVERLAP = 0.12
TOPIC_JUMP_MAX_OVERLAP = 0.05
SPLIT_PARAGRAPH_SENTENCE_LIMIT = 3
MERGE_PARAGRAPH_MIN_OVERLAP = 0.18
EXPLANATION_CLAIM_LIMIT = 5
EXPLANATION_DISCOURSE_EDGE_LIMIT = 6
EXPLANATION_DIAGNOSTIC_LIMIT = 8
EXPLANATION_OPERATION_LIMIT = 6


@dataclass(frozen=True)
class Node:
    """One graph node used in projections."""

    node_id: str
    layer: str
    kind: str
    label: str
    text: str
    payload: dict[str, object]


@dataclass(frozen=True)
class Edge:
    """One graph edge used in projections."""

    edge_id: str
    layer: str
    kind: str
    from_node_id: str
    to_node_id: str
    order_kind: str
    payload: dict[str, object]


@dataclass(frozen=True)
class Diagnostic:
    """One graph diagnostic."""

    diagnostic_id: str
    layer: str
    severity: str
    rule: str
    message: str
    target_node_id: str
    target_edge_id: str


@dataclass(frozen=True)
class EditOperation:
    """One proposed graph edit operation."""

    operation_id: str
    kind: str
    target_ids: tuple[str, ...]
    reason: str
    payload: dict[str, object]


class MarkdownBlock(TypedDict):
    """One Markdown block with source offsets."""

    text: str
    start: int
    end: int


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Ingest Markdown/plain text into a graph DB.")
    ingest.add_argument("input", type=Path)
    ingest.add_argument("--db", type=Path, required=True)
    ingest.add_argument("--kind", default="document")
    add_stats_out(ingest)

    analyze = subparsers.add_parser("analyze", help="Analyze graph layers.")
    add_db_profile(analyze)
    add_stats_out(analyze)

    lint = subparsers.add_parser("lint", help="Write diagnostics Markdown.")
    add_db_profile(lint)
    lint.add_argument("--out", type=Path, required=True)
    add_stats_out(lint)

    project = subparsers.add_parser("project", help="Project graph to YAML or JSON.")
    add_db_profile(project)
    project.add_argument("--format", choices=("yaml", "json"), default="yaml")
    project.add_argument("--out", type=Path, required=True)
    add_stats_out(project)

    outline = subparsers.add_parser("outline", help="Write graph outline Markdown.")
    outline.add_argument("--db", type=Path, required=True)
    outline.add_argument("--out", type=Path, required=True)
    add_stats_out(outline)

    explain = subparsers.add_parser("explain", help="Write natural-language graph explanation.")
    add_db_profile(explain)
    explain.add_argument("--out", type=Path, required=True)
    add_stats_out(explain)

    integrate = subparsers.add_parser("integrate", help="Write integration operation plan.")
    add_db_profile(integrate)
    integrate.add_argument("--out", type=Path, required=True)
    add_stats_out(integrate)

    rewrite = subparsers.add_parser("rewrite-packet", help="Write an LLM rewrite packet for one operation.")
    rewrite.add_argument("--db", type=Path, required=True)
    rewrite.add_argument("--op", required=True)
    rewrite.add_argument("--out", type=Path, required=True)
    add_stats_out(rewrite)

    handoff = subparsers.add_parser("skill-handoff", help="Write existing-skill handoff packet.")
    add_db_profile(handoff)
    handoff.add_argument("--out", type=Path, required=True)
    add_stats_out(handoff)

    return parser


def add_db_profile(parser: argparse.ArgumentParser) -> None:
    """Add DB and profile arguments."""
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--profile", choices=PROFILES, default=DEFAULT_PROFILE)


def add_stats_out(parser: argparse.ArgumentParser) -> None:
    """Add the compact stats artifact argument."""
    parser.add_argument("--stats-out", type=Path, help="Write compact command stats JSON.")


def emit_command_stats(args: argparse.Namespace, status_key: str, fields: dict[str, object]) -> None:
    """Emit compact stdout or write a stats artifact when requested."""
    stats_out = getattr(args, "stats_out", None)
    if isinstance(stats_out, Path):
        payload: dict[str, object] = {
            "schema": "prose_reasoning_graph.stats.v1",
            "status": "pass",
            "command": str(getattr(args, "command", "")),
            "fields": fields,
        }
        stats_out.parent.mkdir(parents=True, exist_ok=True)
        stats_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{status_key}=pass")
        print(f"PROSE_REASONING_GRAPH_STATS={stats_out}")
        return
    print(f"{status_key}=pass")
    for key, value in fields.items():
        print(f"{key}={value}")


def utc_now() -> str:
    """Return a stable UTC timestamp."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(path: Path) -> sqlite3.Connection:
    """Open a SQLite connection and enable foreign keys."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(sqlite_target(path), timeout=SQLITE_BUSY_TIMEOUT_SECONDS, uri=is_wsl_mount(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def sqlite_target(path: Path) -> str | Path:
    """Return a SQLite target path, using no-lock mode on WSL mounts."""
    if not is_wsl_mount(path):
        return path
    # DrvFs mounts can report false write locks for short-lived agent artifacts.
    # The graph DB is a single-writer intermediate file, so no-lock mode is acceptable here.
    quoted_path = quote(path.as_posix(), safe="/:")
    return f"file:{quoted_path}?mode=rwc&nolock=1"


def is_wsl_mount(path: Path) -> bool:
    """Return true for Linux paths under /mnt/*."""
    return path.is_absolute() and len(path.parts) >= WSL_MOUNT_MIN_PATH_PARTS and path.parts[1] == "mnt"


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create the graph schema if needed."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            layer TEXT NOT NULL,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            text TEXT NOT NULL,
            source_start INTEGER NOT NULL,
            source_end INTEGER NOT NULL,
            confidence REAL NOT NULL,
            payload_json TEXT NOT NULL,
            FOREIGN KEY(document_id) REFERENCES documents(id)
        );
        CREATE TABLE IF NOT EXISTS edges (
            id TEXT PRIMARY KEY,
            layer TEXT NOT NULL,
            kind TEXT NOT NULL,
            from_node_id TEXT NOT NULL,
            to_node_id TEXT NOT NULL,
            order_kind TEXT NOT NULL,
            confidence REAL NOT NULL,
            evidence_node_id TEXT,
            payload_json TEXT NOT NULL,
            FOREIGN KEY(from_node_id) REFERENCES nodes(id),
            FOREIGN KEY(to_node_id) REFERENCES nodes(id)
        );
        CREATE TABLE IF NOT EXISTS diagnostics (
            id TEXT PRIMARY KEY,
            layer TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            target_edge_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            rule TEXT NOT NULL,
            message TEXT NOT NULL,
            suggested_action_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS edit_operations (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            target_ids_json TEXT NOT NULL,
            reason TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS judgements (
            id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            source TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )


def write_json(value: object) -> str:
    """Serialize compact JSON."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def read_json_object(value: str) -> dict[str, object]:
    """Read a JSON object."""
    raw = json.loads(value)
    if isinstance(raw, dict):
        return cast(dict[str, object], raw)
    return {}


def clear_analysis(connection: sqlite3.Connection) -> None:
    """Remove analysis outputs while preserving source/form ingest."""
    connection.execute("DELETE FROM judgements")
    connection.execute("DELETE FROM edit_operations")
    connection.execute("DELETE FROM diagnostics")
    connection.execute("DELETE FROM edges WHERE layer NOT IN ('form', 'presentation')")
    connection.execute("DELETE FROM nodes WHERE layer NOT IN ('source', 'form')")


def insert_node(
    connection: sqlite3.Connection,
    node_id: str,
    document_id: str,
    layer: str,
    kind: str,
    label: str,
    text: str,
    source_start: int,
    source_end: int,
    confidence: float = 1.0,
    payload: dict[str, object] | None = None,
) -> None:
    """Insert one node."""
    connection.execute(
        """
        INSERT OR REPLACE INTO nodes(
            id, document_id, layer, kind, label, text, source_start, source_end,
            confidence, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            node_id,
            document_id,
            layer,
            kind,
            label,
            text,
            source_start,
            source_end,
            confidence,
            write_json(payload or {}),
        ),
    )


def insert_edge(
    connection: sqlite3.Connection,
    edge_id: str,
    layer: str,
    kind: str,
    from_node_id: str,
    to_node_id: str,
    order_kind: str = "",
    confidence: float = 1.0,
    evidence_node_id: str = "",
    payload: dict[str, object] | None = None,
) -> None:
    """Insert one edge."""
    connection.execute(
        """
        INSERT OR REPLACE INTO edges(
            id, layer, kind, from_node_id, to_node_id, order_kind,
            confidence, evidence_node_id, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            edge_id,
            layer,
            kind,
            from_node_id,
            to_node_id,
            order_kind,
            confidence,
            evidence_node_id or None,
            write_json(payload or {}),
        ),
    )


def insert_diagnostic(
    connection: sqlite3.Connection,
    diagnostic_id: str,
    layer: str,
    target_node_id: str,
    severity: str,
    rule: str,
    message: str,
    target_edge_id: str = "",
    action: dict[str, object] | None = None,
) -> None:
    """Insert one diagnostic."""
    connection.execute(
        """
        INSERT OR REPLACE INTO diagnostics(
            id, layer, target_node_id, target_edge_id, severity, rule, message,
            suggested_action_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            diagnostic_id,
            layer,
            target_node_id,
            target_edge_id,
            severity,
            rule,
            message,
            write_json(action or {}),
        ),
    )


def insert_operation(
    connection: sqlite3.Connection,
    operation_id: str,
    kind: str,
    target_ids: Sequence[str],
    reason: str,
    payload: dict[str, object] | None = None,
) -> None:
    """Insert one edit operation."""
    connection.execute(
        """
        INSERT OR REPLACE INTO edit_operations(
            id, kind, target_ids_json, reason, payload_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (operation_id, kind, write_json(list(target_ids)), reason, write_json(payload or {})),
    )


def command_ingest(args: argparse.Namespace) -> int:
    """Run ingest command."""
    input_path = cast(Path, args.input)
    text = input_path.read_text(encoding="utf-8")
    with connect(cast(Path, args.db)) as connection:
        initialize_schema(connection)
        connection.executescript(
            """
            DELETE FROM judgements;
            DELETE FROM edit_operations;
            DELETE FROM diagnostics;
            DELETE FROM edges;
            DELETE FROM nodes;
            DELETE FROM documents;
            """
        )
        document_id = "doc:1"
        title = infer_title(text, input_path)
        connection.execute(
            "INSERT INTO documents(id, path, title, kind, created_at) VALUES (?, ?, ?, ?, ?)",
            (document_id, str(input_path), title, cast(str, args.kind), utc_now()),
        )
        insert_node(
            connection,
            "src:1",
            document_id,
            "source",
            "document",
            title,
            text,
            0,
            len(text),
            payload={"path": str(input_path), "kind": cast(str, args.kind)},
        )
        ingest_blocks(connection, document_id, text)
    emit_command_stats(args, "PROSE_REASONING_GRAPH_INGEST", {"PROSE_REASONING_GRAPH_DB": str(args.db)})
    return 0


def infer_title(text: str, path: Path) -> str:
    """Infer a title from Markdown or path."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("_", " ").replace("-", " ").strip() or "document"


def ingest_blocks(connection: sqlite3.Connection, document_id: str, text: str) -> None:
    """Ingest headings, paragraphs, and sentences."""
    blocks = markdown_blocks(text)
    section_stack: list[str] = []
    paragraph_index = 0
    sentence_index = 0
    previous_block_id = ""
    for index, block in enumerate(blocks, start=1):
        block_text = block["text"]
        start = int(block["start"])
        end = int(block["end"])
        if block_text.startswith("#"):
            level = len(block_text) - len(block_text.lstrip("#"))
            label = block_text[level:].strip()
            node_id = f"sec:{index}"
            section_stack = section_stack[: max(level - 1, 0)]
            section_stack.append(node_id)
            insert_node(
                connection,
                node_id,
                document_id,
                "form",
                "section",
                label,
                block_text,
                start,
                end,
                payload={"level": level, "section_path": section_stack.copy()},
            )
        else:
            paragraph_index += 1
            node_id = f"p:{paragraph_index}"
            insert_node(
                connection,
                node_id,
                document_id,
                "form",
                "paragraph",
                first_words(block_text, FORM_NODE_LABEL_WORD_LIMIT),
                block_text,
                start,
                end,
                payload={"section_path": section_stack.copy(), "ordinal": paragraph_index},
            )
            if previous_block_id:
                insert_edge(
                    connection,
                    f"order:{previous_block_id}->{node_id}",
                    "presentation",
                    "precedes",
                    previous_block_id,
                    node_id,
                    order_kind="hard_before",
                    payload={"source": "ingest_order"},
                )
            previous_block_id = node_id
            for sentence in split_sentences(block_text):
                sentence_index += 1
                sentence_start = text.find(sentence, start, end)
                sentence_end = sentence_start + len(sentence) if sentence_start >= 0 else end
                sentence_id = f"s:{sentence_index}"
                insert_node(
                    connection,
                    sentence_id,
                    document_id,
                    "form",
                    "sentence",
                    first_words(sentence, FORM_NODE_LABEL_WORD_LIMIT),
                    sentence,
                    max(sentence_start, start),
                    sentence_end,
                    payload={"paragraph_id": node_id, "ordinal": sentence_index},
                )
                insert_edge(
                    connection,
                    f"contains:{node_id}->{sentence_id}",
                    "form",
                    "contains",
                    node_id,
                    sentence_id,
                    payload={"source": "sentence_split"},
                )


def markdown_blocks(text: str) -> list[MarkdownBlock]:
    """Split Markdown into heading and paragraph blocks with offsets."""
    blocks: list[MarkdownBlock] = []
    current: list[str] = []
    current_start = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped:
            if current:
                block_text = "".join(current).strip()
                blocks.append({"text": block_text, "start": current_start, "end": offset})
                current = []
            offset += len(line)
            continue
        if stripped.startswith("#"):
            if current:
                block_text = "".join(current).strip()
                blocks.append({"text": block_text, "start": current_start, "end": offset})
                current = []
            blocks.append({"text": stripped, "start": offset, "end": offset + len(line)})
        else:
            if not current:
                current_start = offset
            current.append(line)
        offset += len(line)
    if current:
        blocks.append({"text": "".join(current).strip(), "start": current_start, "end": offset})
    return blocks


def split_sentences(text: str) -> tuple[str, ...]:
    """Split paragraph text into simple sentence units."""
    sentences = [item.strip() for item in re.split(r"(?<=[.!?。！？])\s+", text) if item.strip()]
    return tuple(sentences or (text.strip(),))


def first_words(text: str, count: int) -> str:
    """Return a compact label."""
    words = text.replace("\n", " ").split()
    return " ".join(words[:count])


def command_analyze(args: argparse.Namespace) -> int:
    """Run analysis command."""
    with connect(cast(Path, args.db)) as connection:
        initialize_schema(connection)
        clear_analysis(connection)
        analyze_graph(connection, cast(str, args.profile))
    emit_command_stats(args, "PROSE_REASONING_GRAPH_ANALYZE", {"PROSE_REASONING_GRAPH_PROFILE": str(args.profile)})
    return 0


def analyze_graph(connection: sqlite3.Connection, profile: str) -> None:
    """Populate graph overlays."""
    document_id = fetch_document_id(connection)
    paragraphs = fetch_nodes(connection, layer="form", kind="paragraph")
    sentences = fetch_nodes(connection, layer="form", kind="sentence")
    sections = fetch_nodes(connection, layer="form", kind="section")
    add_projection_layer(connection, document_id, profile)
    add_concept_layer(connection, document_id, paragraphs)
    add_phase_layer(connection, document_id, paragraphs, profile)
    add_discourse_layer(connection, paragraphs)
    claims = add_argument_layer(connection, document_id, sentences)
    evidence = add_evidence_layer(connection, document_id, sentences, claims)
    add_experiment_layer(connection, document_id, sentences)
    add_edit_operations(connection, paragraphs)
    add_explanation_layer(connection, document_id, profile)
    add_section_edges(connection, sections, paragraphs)
    add_diagnostics(connection, paragraphs, claims, evidence)


def fetch_document_id(connection: sqlite3.Connection) -> str:
    """Return the single document id."""
    row = connection.execute("SELECT id FROM documents ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ValueError("database has no document; run ingest first")
    return str(row["id"])


def fetch_nodes(
    connection: sqlite3.Connection,
    *,
    layer: str | None = None,
    kind: str | None = None,
) -> tuple[Node, ...]:
    """Fetch nodes."""
    clauses: list[str] = []
    values: list[str] = []
    if layer is not None:
        clauses.append("layer = ?")
        values.append(layer)
    if kind is not None:
        clauses.append("kind = ?")
        values.append(kind)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        f"SELECT * FROM nodes {where} ORDER BY source_start, id", values
    ).fetchall()
    return tuple(
        Node(
            node_id=str(row["id"]),
            layer=str(row["layer"]),
            kind=str(row["kind"]),
            label=str(row["label"]),
            text=str(row["text"]),
            payload=read_json_object(str(row["payload_json"])),
        )
        for row in rows
    )


def add_projection_layer(connection: sqlite3.Connection, document_id: str, profile: str) -> None:
    """Add projection metadata node."""
    insert_node(
        connection,
        "projection:profile",
        document_id,
        "projection",
        "profile",
        profile,
        f"Projection profile: {profile}",
        0,
        0,
        payload={"profile": profile, "outputs": ["yaml", "json", "markdown"]},
    )


def add_concept_layer(connection: sqlite3.Connection, document_id: str, paragraphs: Sequence[Node]) -> None:
    """Extract concept nodes from repeated terms."""
    term_counts: Counter[str] = Counter()
    for paragraph in paragraphs:
        term_counts.update(tokens(paragraph.text))
    candidates = [
        term
        for term, count in term_counts.most_common(CONCEPT_CANDIDATE_LIMIT)
        if count > 1 and term not in STOPWORDS and len(term) > CONCEPT_MIN_TERM_LENGTH
    ]
    for index, term in enumerate(candidates, start=1):
        insert_node(
            connection,
            f"concept:{index}",
            document_id,
            "concept",
            "term",
            term,
            term,
            0,
            0,
            confidence=CONCEPT_NODE_CONFIDENCE,
            payload={"frequency": term_counts[term]},
        )
    for index, (left, right) in enumerate(zip(candidates, candidates[1:]), start=1):
        insert_edge(
            connection,
            f"concept-edge:{index}",
            "concept",
            "related_to",
            concept_id_for(candidates, left),
            concept_id_for(candidates, right),
            confidence=CONCEPT_EDGE_CONFIDENCE,
            payload={"basis": "term_cooccurrence"},
        )


def concept_id_for(candidates: Sequence[str], term: str) -> str:
    """Return concept id for a term."""
    return f"concept:{candidates.index(term) + 1}"


def tokens(text: str) -> tuple[str, ...]:
    """Tokenize prose into lowercase terms."""
    return tuple(token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[一-龥ぁ-んァ-ン]{2,}", text))


def add_phase_layer(
    connection: sqlite3.Connection,
    document_id: str,
    paragraphs: Sequence[Node],
    profile: str,
) -> None:
    """Assign genre move/phase nodes."""
    for index, paragraph in enumerate(paragraphs, start=1):
        phase = infer_phase(paragraph.text, index, profile)
        phase_id = f"phase:{index}"
        insert_node(
            connection,
            phase_id,
            document_id,
            "phase",
            "move",
            phase,
            paragraph.text,
            0,
            0,
            confidence=PHASE_INFERENCE_CONFIDENCE,
            payload={"paragraph_id": paragraph.node_id, "profile": profile},
        )
        insert_edge(
            connection,
            f"phase-map:{paragraph.node_id}->{phase_id}",
            "phase",
            "realizes_move",
            paragraph.node_id,
            phase_id,
            payload={"profile": profile},
        )


def infer_phase(text: str, index: int, profile: str) -> str:
    """Infer a phase/move label from keywords and profile."""
    lowered = text.lower()
    if profile in {"experiment", "all"} and any(cue in lowered for cue in ("hypothesis", "仮説")):
        return "hypothesis"
    if any(cue in lowered for cue in ("metric", "baseline", "protocol", "指標", "ベースライン")):
        return "operationalization"
    if any(cue in lowered for cue in ("risk", "limitation", "ただし", "制限", "限界")):
        return "limitation"
    if any(cue in lowered for cue in ("therefore", "recommend", "結論", "推奨")):
        return "recommendation"
    if index == 1:
        return "context"
    return "development"


def add_discourse_layer(connection: sqlite3.Connection, paragraphs: Sequence[Node]) -> None:
    """Add discourse edges between adjacent paragraphs."""
    for index, (left, right) in enumerate(zip(paragraphs, paragraphs[1:]), start=1):
        relation = infer_discourse_relation(right.text)
        overlap = lexical_overlap(left.text, right.text)
        insert_edge(
            connection,
            f"discourse:{index}",
            "discourse",
            relation,
            left.node_id,
            right.node_id,
            order_kind="adjacency_preferred",
            confidence=max(
                DISCOURSE_CONFIDENCE_FLOOR,
                min(DISCOURSE_CONFIDENCE_CEILING, overlap + DISCOURSE_CONFIDENCE_OVERLAP_OFFSET),
            ),
            payload={
                "shared_terms": sorted(set(tokens(left.text)) & set(tokens(right.text)))[:DISCOURSE_SHARED_TERM_LIMIT],
                "lexical_overlap": overlap,
                "surface_signal": first_discourse_signal(right.text),
            },
        )


def infer_discourse_relation(text: str) -> str:
    """Infer a coarse discourse relation."""
    lowered = text.lower()
    if any(cue in lowered for cue in ("however", "but", "although", "ただし", "一方")):
        return "contrasts"
    if any(cue in lowered for cue in ("because", "therefore", "thus", "so ", "なので", "したがって")):
        return "causes"
    if any(cue in lowered for cue in ("for example", "e.g.", "例えば")):
        return "exemplifies"
    if any(cue in lowered for cue in ("limitation", "risk", "制限", "リスク")):
        return "limits"
    return "elaborates"


def first_discourse_signal(text: str) -> str:
    """Return the first explicit discourse cue."""
    lowered = text.lower()
    cues = ("however", "because", "therefore", "for example", "limitation", "ただし", "例えば")
    for cue in cues:
        if cue in lowered:
            return cue
    return ""


def lexical_overlap(left: str, right: str) -> float:
    """Return token overlap ratio."""
    left_terms = set(tokens(left)) - STOPWORDS
    right_terms = set(tokens(right)) - STOPWORDS
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / max(len(left_terms | right_terms), 1)


def add_argument_layer(
    connection: sqlite3.Connection,
    document_id: str,
    sentences: Sequence[Node],
) -> tuple[Node, ...]:
    """Extract claim nodes from sentences."""
    claims: list[Node] = []
    for sentence in sentences:
        if has_any(sentence.text, CLAIM_CUES):
            claim_id = f"claim:{len(claims) + 1}"
            insert_node(
                connection,
                claim_id,
                document_id,
                "argument",
                "claim",
                first_words(sentence.text, EXTRACTED_NODE_LABEL_WORD_LIMIT),
                sentence.text,
                0,
                0,
                confidence=EXTRACTED_NODE_CONFIDENCE,
                payload={"sentence_id": sentence.node_id},
            )
            insert_edge(
                connection,
                f"claim-source:{claim_id}",
                "argument",
                "stated_in",
                claim_id,
                sentence.node_id,
                payload={"source": "cue_heuristic"},
            )
            claims.append(
                Node(
                    claim_id,
                    "argument",
                    "claim",
                    first_words(sentence.text, EXTRACTED_NODE_LABEL_WORD_LIMIT),
                    sentence.text,
                    {"sentence_id": sentence.node_id},
                )
            )
    return tuple(claims)


def add_evidence_layer(
    connection: sqlite3.Connection,
    document_id: str,
    sentences: Sequence[Node],
    claims: Sequence[Node],
) -> tuple[Node, ...]:
    """Extract evidence nodes and support nearby claims."""
    evidence_nodes: list[Node] = []
    for sentence in sentences:
        if has_any(sentence.text, EVIDENCE_CUES):
            evidence_id = f"evidence:{len(evidence_nodes) + 1}"
            insert_node(
                connection,
                evidence_id,
                document_id,
                "evidence",
                "evidence",
                first_words(sentence.text, EXTRACTED_NODE_LABEL_WORD_LIMIT),
                sentence.text,
                0,
                0,
                confidence=EXTRACTED_NODE_CONFIDENCE,
                payload={"sentence_id": sentence.node_id, "strength": "candidate"},
            )
            evidence_nodes.append(
                Node(
                    evidence_id,
                    "evidence",
                    "evidence",
                    first_words(sentence.text, EXTRACTED_NODE_LABEL_WORD_LIMIT),
                    sentence.text,
                    {"sentence_id": sentence.node_id},
                )
            )
    for claim in claims:
        evidence = best_supporting_evidence(claim, evidence_nodes)
        if evidence is not None:
            insert_edge(
                connection,
                f"support:{evidence.node_id}->{claim.node_id}",
                "evidence",
                "supports",
                evidence.node_id,
                claim.node_id,
                confidence=0.5,
                payload={"basis": "document_neighborhood"},
            )
    return tuple(evidence_nodes)


def best_supporting_evidence(claim: Node, evidence_nodes: Sequence[Node]) -> Node | None:
    """Choose evidence that has local relation to a claim."""
    claim_sentence_id = str(claim.payload.get("sentence_id", ""))
    for evidence in evidence_nodes:
        if str(evidence.payload.get("sentence_id", "")) == claim_sentence_id:
            return evidence
    for evidence in evidence_nodes:
        if lexical_overlap(claim.text, evidence.text) >= EVIDENCE_SUPPORT_MIN_OVERLAP:
            return evidence
    return None


def add_experiment_layer(connection: sqlite3.Connection, document_id: str, sentences: Sequence[Node]) -> None:
    """Extract experiment-planning nodes."""
    counters: Counter[str] = Counter()
    for sentence in sentences:
        lowered = sentence.text.lower()
        kind = ""
        if any(cue in lowered for cue in ("hypothesis", "仮説")):
            kind = "hypothesis"
        elif any(cue in lowered for cue in ("metric", "指標")):
            kind = "metric"
        elif any(cue in lowered for cue in ("baseline", "ベースライン")):
            kind = "baseline"
        elif any(cue in lowered for cue in ("experiment", "protocol", "実験")):
            kind = "experiment"
        elif any(cue in lowered for cue in ("expected", "期待")):
            kind = "expected_result"
        if kind:
            counters[kind] += 1
            node_id = f"experiment:{kind}:{counters[kind]}"
            insert_node(
                connection,
                node_id,
                document_id,
                "experiment",
                kind,
                first_words(sentence.text, EXTRACTED_NODE_LABEL_WORD_LIMIT),
                sentence.text,
                0,
                0,
                confidence=EXTRACTED_NODE_CONFIDENCE,
                payload={"sentence_id": sentence.node_id},
            )


def add_section_edges(connection: sqlite3.Connection, sections: Sequence[Node], paragraphs: Sequence[Node]) -> None:
    """Connect sections to paragraphs by recorded section paths."""
    section_ids = {section.node_id for section in sections}
    for paragraph in paragraphs:
        section_path = paragraph.payload.get("section_path", [])
        if isinstance(section_path, list) and section_path:
            raw_section_id = cast(list[object], section_path)[-1]
            if not isinstance(raw_section_id, str):
                continue
            section_id = raw_section_id
            if section_id in section_ids:
                insert_edge(
                    connection,
                    f"section-contains:{section_id}->{paragraph.node_id}",
                    "form",
                    "contains",
                    section_id,
                    paragraph.node_id,
                    payload={"source": "markdown_heading"},
                )


def has_any(text: str, cues: Iterable[str]) -> bool:
    """Return true when text contains any cue."""
    lowered = text.lower()
    return any(cue in lowered for cue in cues)


def add_diagnostics(
    connection: sqlite3.Connection,
    paragraphs: Sequence[Node],
    claims: Sequence[Node],
    evidence_nodes: Sequence[Node],
) -> None:
    """Add rule-based diagnostics."""
    support_edges = connection.execute(
        "SELECT to_node_id FROM edges WHERE layer = 'evidence' AND kind = 'supports'"
    ).fetchall()
    supported_claims = {str(row["to_node_id"]) for row in support_edges}
    for claim in claims:
        if claim.node_id not in supported_claims:
            insert_diagnostic(
                connection,
                f"diag:unsupported:{claim.node_id}",
                "argument",
                claim.node_id,
                "blocker",
                "unsupported_claim",
                f"Claim `{claim.node_id}` has no supporting evidence edge.",
                action={"add": "evidence or limitation"},
            )
    if any(has_any(paragraph.text, EXPERIMENT_CUES) for paragraph in paragraphs):
        experiment_kinds = {
            str(row["kind"])
            for row in connection.execute("SELECT kind FROM nodes WHERE layer = 'experiment'").fetchall()
        }
        if "hypothesis" not in experiment_kinds:
            insert_document_diagnostic(
                connection,
                "experiment_without_hypothesis",
                "Experiment language appears without a hypothesis node.",
            )
        if "metric" not in experiment_kinds:
            insert_document_diagnostic(
                connection,
                "experiment_without_metric",
                "Experiment planning lacks a metric node.",
            )
        if "baseline" not in experiment_kinds:
            insert_document_diagnostic(
                connection,
                "metric_without_baseline",
                "Experiment planning lacks a baseline node.",
            )
        if "expected_result" not in experiment_kinds:
            insert_document_diagnostic(
                connection,
                "experiment_without_expected_result",
                "Experiment planning lacks an expected-result node.",
            )
    for index, (left, right) in enumerate(zip(paragraphs, paragraphs[1:]), start=1):
        if lexical_overlap(left.text, right.text) < TOPIC_JUMP_MAX_OVERLAP and not first_discourse_signal(right.text):
            insert_diagnostic(
                connection,
                f"diag:topic-jump:{index}",
                "discourse",
                right.node_id,
                "warn",
                "topic_jump_without_bridge",
                f"Paragraph `{left.node_id}` to `{right.node_id}` has low shared terms and no bridge cue.",
                action={"add": "bridge sentence or explicit relation"},
            )
    if claims and not evidence_nodes:
        insert_document_diagnostic(connection, "claim_without_evidence_layer", "Claims exist but the evidence layer has no evidence nodes.")
    add_layer_coverage_diagnostic(connection)


def insert_document_diagnostic(connection: sqlite3.Connection, rule: str, message: str) -> None:
    """Insert a document-level diagnostic."""
    row = connection.execute("SELECT id FROM nodes WHERE layer = 'source' LIMIT 1").fetchone()
    target = str(row["id"]) if row else ""
    insert_diagnostic(
        connection,
        f"diag:{rule}",
        "diagnostics",
        target,
        "warn",
        rule,
        message,
    )


def add_layer_coverage_diagnostic(connection: sqlite3.Connection) -> None:
    """Record layer coverage as diagnostic metadata."""
    counts = layer_counts(connection)
    missing = [layer for layer in LAYERS if counts.get(layer, 0) == 0 and layer != "diagnostics"]
    if missing:
        insert_document_diagnostic(
            connection,
            "missing_layer_representation",
            f"Missing graph layer representations: {', '.join(missing)}.",
        )


def add_edit_operations(connection: sqlite3.Connection, paragraphs: Sequence[Node]) -> None:
    """Add split/merge/bridge/reorder operation candidates."""
    for paragraph in paragraphs:
        sentences = split_sentences(paragraph.text)
        if len(sentences) > SPLIT_PARAGRAPH_SENTENCE_LIMIT:
            insert_operation(
                connection,
                f"op:split:{paragraph.node_id}",
                "split_paragraph",
                [paragraph.node_id],
                f"`{paragraph.node_id}` has {len(sentences)} sentence units and may need a split.",
                operation_payload(
                    {
                        "preserve": "source spans and section path",
                        "sentence_count": len(sentences),
                    }
                ),
            )
            break
    for left, right in zip(paragraphs, paragraphs[1:]):
        overlap = lexical_overlap(left.text, right.text)
        if overlap > MERGE_PARAGRAPH_MIN_OVERLAP:
            insert_operation(
                connection,
                f"op:merge:{left.node_id}:{right.node_id}",
                "merge_paragraphs",
                [left.node_id, right.node_id],
                f"`{left.node_id}` and `{right.node_id}` share focus and may be integrated.",
                operation_payload(
                    {
                        "lexical_overlap": overlap,
                        "preserve": "claims and evidence from both paragraphs",
                    }
                ),
            )
            break
    for left, right in zip(paragraphs, paragraphs[1:]):
        if lexical_overlap(left.text, right.text) < TOPIC_JUMP_MAX_OVERLAP:
            insert_operation(
                connection,
                f"op:bridge:{left.node_id}:{right.node_id}",
                "add_bridge",
                [left.node_id, right.node_id],
                f"`{left.node_id}` to `{right.node_id}` needs an explicit bridge.",
                operation_payload(
                    {"bridge_intent": "state the discourse relation and shared question"}
                ),
            )
            break
    if len(paragraphs) > 2:
        insert_operation(
            connection,
            "op:reorder:presentation",
            "reorder_paragraphs",
            [paragraph.node_id for paragraph in paragraphs],
            "Presentation order can be checked against phase order and hard-before edges.",
            operation_payload({"strategy": "priority topological sort with phase preference"}),
        )


def operation_payload(values: dict[str, object]) -> dict[str, object]:
    """Return common payload fields for an edit operation candidate."""
    payload: dict[str, object] = {
        "provenance": "source_graph_nodes",
        "history_effect": "records_candidate_without_mutating_source",
    }
    payload.update(values)
    return payload


def add_explanation_layer(connection: sqlite3.Connection, document_id: str, profile: str) -> None:
    """Add explanation metadata node."""
    insert_node(
        connection,
        "explanation:summary",
        document_id,
        "explanation",
        "summary",
        "graph explanation",
        "Natural-language explanation generated from graph facts.",
        0,
        0,
        payload={"profile": profile, "source": "graph_facts"},
    )


def layer_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Return node/edge/diagnostic/operation counts by layer."""
    counts: Counter[str] = Counter()
    for row in connection.execute("SELECT layer, COUNT(*) AS count FROM nodes GROUP BY layer"):
        counts[str(row["layer"])] += int(row["count"])
    for row in connection.execute("SELECT layer, COUNT(*) AS count FROM edges GROUP BY layer"):
        counts[str(row["layer"])] += int(row["count"])
    diagnostics_count = connection.execute("SELECT COUNT(*) AS count FROM diagnostics").fetchone()
    operations_count = connection.execute("SELECT COUNT(*) AS count FROM edit_operations").fetchone()
    counts["diagnostics"] += int(diagnostics_count["count"]) if diagnostics_count else 0
    counts["edit-operation"] += int(operations_count["count"]) if operations_count else 0
    return dict(counts)


def command_lint(args: argparse.Namespace) -> int:
    """Run lint command."""
    with connect(cast(Path, args.db)) as connection:
        output = render_diagnostics(connection, cast(str, args.profile))
    write_output(cast(Path, args.out), output)
    emit_command_stats(args, "PROSE_REASONING_GRAPH_LINT", {"PROSE_REASONING_GRAPH_DIAGNOSTICS": str(args.out)})
    return 0


def render_diagnostics(connection: sqlite3.Connection, profile: str) -> str:
    """Render diagnostics Markdown."""
    diagnostics = fetch_diagnostics(connection)
    lines = [
        "# Prose Reasoning Graph Diagnostics",
        "",
        f"- profile: `{profile}`",
        f"- diagnostics: `{len(diagnostics)}`",
        "",
    ]
    if not diagnostics:
        lines.append("No diagnostics recorded.")
    else:
        for item in diagnostics:
            lines.append(
                f"- `{item.severity}` `{item.rule}` target=`{item.target_node_id or item.target_edge_id}`: {item.message}"
            )
    lines.append("")
    return "\n".join(lines)


def fetch_diagnostics(connection: sqlite3.Connection) -> tuple[Diagnostic, ...]:
    """Fetch diagnostics."""
    rows = connection.execute("SELECT * FROM diagnostics ORDER BY severity, id").fetchall()
    return tuple(
        Diagnostic(
            diagnostic_id=str(row["id"]),
            layer=str(row["layer"]),
            severity=str(row["severity"]),
            rule=str(row["rule"]),
            message=str(row["message"]),
            target_node_id=str(row["target_node_id"]),
            target_edge_id=str(row["target_edge_id"]),
        )
        for row in rows
    )


def command_project(args: argparse.Namespace) -> int:
    """Run project command."""
    with connect(cast(Path, args.db)) as connection:
        payload = projection_payload(connection, cast(str, args.profile), cast(Path, args.db))
    if args.format == "json":
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    write_output(cast(Path, args.out), text)
    emit_command_stats(args, "PROSE_REASONING_GRAPH_PROJECT", {"PROSE_REASONING_GRAPH_PROJECTION": str(args.out)})
    return 0


def projection_payload(connection: sqlite3.Connection, profile: str, db_path: Path) -> dict[str, object]:
    """Build a structured projection payload."""
    counts = layer_counts(connection)
    nodes = [asdict(node) for node in fetch_nodes(connection)]
    edges = [asdict(edge) for edge in fetch_edges(connection)]
    diagnostics = [asdict(item) for item in fetch_diagnostics(connection)]
    operations = [asdict(item) for item in fetch_operations(connection)]
    return {
        "profile": profile,
        "graph_db": str(db_path),
        "layers": {layer: counts.get(layer, 0) for layer in LAYERS},
        "skill_handoffs": skill_handoffs(profile, db_path),
        "nodes": nodes,
        "edges": edges,
        "diagnostics": diagnostics,
        "edit_operations": operations,
    }


def fetch_edges(connection: sqlite3.Connection) -> tuple[Edge, ...]:
    """Fetch edges."""
    rows = connection.execute("SELECT * FROM edges ORDER BY id").fetchall()
    return tuple(
        Edge(
            edge_id=str(row["id"]),
            layer=str(row["layer"]),
            kind=str(row["kind"]),
            from_node_id=str(row["from_node_id"]),
            to_node_id=str(row["to_node_id"]),
            order_kind=str(row["order_kind"] or ""),
            payload=read_json_object(str(row["payload_json"])),
        )
        for row in rows
    )


def fetch_operations(connection: sqlite3.Connection) -> tuple[EditOperation, ...]:
    """Fetch edit operations."""
    rows = connection.execute("SELECT * FROM edit_operations ORDER BY id").fetchall()
    output: list[EditOperation] = []
    for row in rows:
        target_ids = json.loads(str(row["target_ids_json"]))
        output.append(
            EditOperation(
                operation_id=str(row["id"]),
                kind=str(row["kind"]),
                target_ids=tuple(str(item) for item in target_ids),
                reason=str(row["reason"]),
                payload=read_json_object(str(row["payload_json"])),
            )
        )
    return tuple(output)


def skill_handoffs(profile: str, db_path: Path) -> list[dict[str, object]]:
    """Return existing-skill handoff metadata."""
    profile_map: dict[str, tuple[str, ...]] = {
        "writing": ("$long-form-writing", "$structure-planning"),
        "logic": ("logic-gap-review", "$academic-writing"),
        "experiment": ("$experiment-lifecycle", "$report-writing"),
        "report": ("$report-writing", "$result-artifact-writeout"),
        "academic": ("$academic-writing", "logic-gap-review", "citation-evidence-review"),
        "paper": ("$paper-writing", "citation-evidence-review", "logic-gap-review"),
        "all": SKILL_HANDOFF_TARGETS,
    }
    targets = profile_map.get(profile, SKILL_HANDOFF_TARGETS)
    return [
        {
            "target": target,
            "graph_db": str(db_path),
            "projection": "run prose_reasoning_graph.py project",
            "diagnostics": "run prose_reasoning_graph.py lint",
            "explanation": "run prose_reasoning_graph.py explain",
            "rewrite_plan": "run prose_reasoning_graph.py integrate",
        }
        for target in targets
    ]


def command_outline(args: argparse.Namespace) -> int:
    """Run outline command."""
    with connect(cast(Path, args.db)) as connection:
        paragraphs = fetch_nodes(connection, layer="form", kind="paragraph")
        sections = fetch_nodes(connection, layer="form", kind="section")
    lines = ["# Prose Reasoning Graph Outline", ""]
    for section in sections:
        lines.append(f"- section `{section.node_id}`: {section.label}")
    for paragraph in paragraphs:
        lines.append(f"- paragraph `{paragraph.node_id}`: {paragraph.label}")
    lines.append("")
    write_output(cast(Path, args.out), "\n".join(lines))
    emit_command_stats(args, "PROSE_REASONING_GRAPH_OUTLINE", {"PROSE_REASONING_GRAPH_OUTLINE_PATH": str(args.out)})
    return 0


def command_explain(args: argparse.Namespace) -> int:
    """Run explain command."""
    with connect(cast(Path, args.db)) as connection:
        text = render_explanation(connection, cast(str, args.profile), cast(Path, args.db))
    write_output(cast(Path, args.out), text)
    emit_command_stats(args, "PROSE_REASONING_GRAPH_EXPLAIN", {"PROSE_REASONING_GRAPH_EXPLANATION": str(args.out)})
    return 0


def render_explanation(connection: sqlite3.Connection, profile: str, db_path: Path) -> str:
    """Render graph explanation Markdown."""
    counts = layer_counts(connection)
    claims = fetch_nodes(connection, layer="argument", kind="claim")
    diagnostics = fetch_diagnostics(connection)
    operations = fetch_operations(connection)
    discourse_edges = [edge for edge in fetch_edges(connection) if edge.layer == "discourse"]
    lines = [
        "# Prose Reasoning Graph Explanation",
        "",
        "## Summary",
        "",
        (
            f"The graph for profile `{profile}` stores {sum(counts.values())} layer items "
            f"across {len([layer for layer in LAYERS if counts.get(layer, 0)])} requested layers. "
            f"The analysis DB is `{db_path}`."
        ),
        "",
        "## Main Claim Path",
        "",
    ]
    if claims:
        for claim in claims[:EXPLANATION_CLAIM_LIMIT]:
            lines.append(f"1. `{claim.node_id}` {claim.text}")
    else:
        lines.append("1. No explicit claim nodes were detected.")
    lines.extend(["", "## Discourse Edges", ""])
    for edge in discourse_edges[:EXPLANATION_DISCOURSE_EDGE_LIMIT]:
        lines.append(
            f"- `{edge.edge_id}` `{edge.from_node_id}` -> `{edge.to_node_id}` relation=`{edge.kind}`"
        )
    if not discourse_edges:
        lines.append("- No discourse edges recorded.")
    lines.extend(["", "## Gaps", ""])
    for diagnostic in diagnostics[:EXPLANATION_DIAGNOSTIC_LIMIT]:
        lines.append(
            f"- `{diagnostic.severity}` `{diagnostic.rule}` on `{diagnostic.target_node_id}`: {diagnostic.message}"
        )
    if not diagnostics:
        lines.append("- No graph diagnostics recorded.")
    lines.extend(["", "## Recommended Next Edits", ""])
    for operation in operations[:EXPLANATION_OPERATION_LIMIT]:
        lines.append(f"1. `{operation.operation_id}` `{operation.kind}`: {operation.reason}")
    if not operations:
        lines.append("1. No edit operations recorded.")
    lines.extend(
        [
            "",
            "## Provenance Boundary",
            "",
            "This explanation is generated from graph nodes, edges, diagnostics, and edit operations. It is advisory evidence for the receiving skill, not policy authority.",
            "",
        ]
    )
    return "\n".join(lines)


def command_integrate(args: argparse.Namespace) -> int:
    """Run integrate command."""
    with connect(cast(Path, args.db)) as connection:
        text = render_integration_plan(connection, cast(str, args.profile))
    write_output(cast(Path, args.out), text)
    emit_command_stats(
        args,
        "PROSE_REASONING_GRAPH_INTEGRATE",
        {"PROSE_REASONING_GRAPH_INTEGRATION_PLAN": str(args.out)},
    )
    return 0


def render_integration_plan(connection: sqlite3.Connection, profile: str) -> str:
    """Render edit operation plan."""
    operations = fetch_operations(connection)
    lines = [
        "# Prose Reasoning Graph Integration Plan",
        "",
        f"- profile: `{profile}`",
        f"- operations: `{len(operations)}`",
        "",
    ]
    for operation in operations:
        targets = ", ".join(f"`{target}`" for target in operation.target_ids)
        lines.extend(
            [
                f"## `{operation.operation_id}`",
                "",
                f"- kind: `{operation.kind}`",
                f"- targets: {targets}",
                f"- reason: {operation.reason}",
                f"- rewrite packet: `prose_reasoning_graph.py rewrite-packet --op {operation.operation_id}`",
                "",
            ]
        )
    if not operations:
        lines.append("No edit operations recorded.")
    return "\n".join(lines)


def command_rewrite_packet(args: argparse.Namespace) -> int:
    """Run rewrite packet command."""
    with connect(cast(Path, args.db)) as connection:
        operation = fetch_operation(connection, cast(str, args.op))
    text = render_rewrite_packet(operation)
    write_output(cast(Path, args.out), text)
    emit_command_stats(
        args,
        "PROSE_REASONING_GRAPH_REWRITE_PACKET",
        {"PROSE_REASONING_GRAPH_REWRITE_PACKET_PATH": str(args.out)},
    )
    return 0


def fetch_operation(connection: sqlite3.Connection, operation_id: str) -> EditOperation:
    """Fetch one operation."""
    row = connection.execute("SELECT * FROM edit_operations WHERE id = ?", (operation_id,)).fetchone()
    if row is None:
        raise ValueError(f"missing edit operation: {operation_id}")
    target_ids = json.loads(str(row["target_ids_json"]))
    return EditOperation(
        operation_id=str(row["id"]),
        kind=str(row["kind"]),
        target_ids=tuple(str(item) for item in target_ids),
        reason=str(row["reason"]),
        payload=read_json_object(str(row["payload_json"])),
    )


def render_rewrite_packet(operation: EditOperation) -> str:
    """Render LLM rewrite packet Markdown."""
    targets = ", ".join(f"`{target}`" for target in operation.target_ids)
    payload_lines = "\n".join(f"- {key}: {value}" for key, value in operation.payload.items())
    return "\n".join(
        [
            "# Prose Reasoning Graph Rewrite Packet",
            "",
            "## Rewrite Goal",
            "",
            f"Apply `{operation.kind}` for {targets}.",
            "",
            "## Reason",
            "",
            operation.reason,
            "",
            "## Preserve",
            "",
            "- source provenance",
            "- claim and evidence ids",
            "- existing skill authority boundaries",
            "",
            "## Change",
            "",
            payload_lines or "- Follow the operation kind and target ids.",
            "",
            "## Do Not",
            "",
            "- Do not invent new claims not present in graph nodes.",
            "- Do not change diagnostic severity without reviewer approval.",
            "- Do not replace the receiving skill's review responsibility.",
            "",
        ]
    )


def command_skill_handoff(args: argparse.Namespace) -> int:
    """Run skill handoff command."""
    text = render_skill_handoff(cast(str, args.profile), cast(Path, args.db))
    write_output(cast(Path, args.out), text)
    emit_command_stats(
        args,
        "PROSE_REASONING_GRAPH_SKILL_HANDOFF",
        {"PROSE_REASONING_GRAPH_SKILL_HANDOFF_PATH": str(args.out)},
    )
    return 0


def render_skill_handoff(profile: str, db_path: Path) -> str:
    """Render skill handoff Markdown."""
    handoffs = skill_handoffs(profile, db_path)
    lines = [
        "# Prose Reasoning Graph Skill Handoff",
        "",
        f"- profile: `{profile}`",
        f"- prose_graph_db: `{db_path}`",
        "",
        "## Targets",
        "",
    ]
    for item in handoffs:
        lines.extend(
            [
                f"### {item['target']}",
                "",
                f"- prose_graph_db: `{item['graph_db']}`",
                f"- prose_graph_projection: {item['projection']}",
                f"- prose_graph_diagnostics: {item['diagnostics']}",
                f"- prose_graph_explanation: {item['explanation']}",
                f"- prose_graph_rewrite_plan: {item['rewrite_plan']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Authority Boundary",
            "",
            "This handoff gives graph-derived evidence to existing skills and reviewers. It does not replace their review gates or source-packet responsibilities.",
            "",
        ]
    )
    return "\n".join(lines)


def write_output(path: Path, text: str) -> None:
    """Write text to one output path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            return command_ingest(args)
        if args.command == "analyze":
            return command_analyze(args)
        if args.command == "lint":
            return command_lint(args)
        if args.command == "project":
            return command_project(args)
        if args.command == "outline":
            return command_outline(args)
        if args.command == "explain":
            return command_explain(args)
        if args.command == "integrate":
            return command_integrate(args)
        if args.command == "rewrite-packet":
            return command_rewrite_packet(args)
        if args.command == "skill-handoff":
            return command_skill_handoff(args)
    except ValueError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
