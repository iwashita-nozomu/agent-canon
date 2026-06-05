#!/usr/bin/env python3
# @dependency-start
# responsibility Builds and reports SQLite-backed prose reasoning graphs.
# upstream design ../../documents/prose-reasoning-graph/dsl-spec.md normative graph and DSL contract
# upstream design ../../agents/skills/prose-reasoning-graph.md prose graph skill contract
# upstream design ../../agents/workflows/workflow-references.md writing and discourse prior art
# upstream implementation ../../rust/agent-canon/src/local_llm.rs extracts LocalLLM prose IR
# downstream implementation ../../tests/agent_tools/test_prose_reasoning_graph.py tests CLI behavior
# downstream design ../../documents/tools/prose_reasoning_graph.md documents tool contract
# @dependency-end
"""Build and report SQLite-backed prose reasoning graphs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
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
    "$formal-proof-workflow",
    "logic-gap-review",
    "citation-evidence-review",
    "$experiment-lifecycle",
    "$result-artifact-writeout",
)
ASCII_SENTENCE_ABBREVIATIONS = frozenset(
    {
        "dr",
        "e.g",
        "fig",
        "figs",
        "i.e",
        "mr",
        "mrs",
        "ms",
        "no",
        "prof",
        "sec",
        "vs",
    }
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
    "したがって",
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
    "仮説",
    "実験",
    "指標",
    "ベースライン",
    "期待",
)
EXPERIMENT_ACTIVITY_CUES = ("experiment", "protocol", "実験")
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
DEFAULT_DB_HOME_ENV = "AGENT_CANON_PROSE_GRAPH_HOME"
DEFAULT_DB_NAME = "prose_graph.sqlite"
DEFAULT_CACHE_HASH_LENGTH = 12
VERIFICATION_RECURSION_MAX_DEPTH = 3
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
STRUCTURED_ANALYSIS_INVENTORY_STDOUT_KEY = "STRUCTURED_ANALYSIS_DOCUMENT_INVENTORY_JSON"
LOCAL_LLM_PROSE_IR_STDOUT_KEY = "LOCAL_LLM_PROSE_IR_JSON"


@dataclass(frozen=True)
class Node:
    """One graph node used in projections."""

    node_id: str
    document_id: str
    layer: str
    kind: str
    label: str
    text: str
    payload: dict[str, object]
    source_start: int = 0
    source_end: int = 0


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
    action: dict[str, object]


@dataclass(frozen=True)
class EditOperation:
    """One proposed graph edit operation."""

    operation_id: str
    kind: str
    target_ids: tuple[str, ...]
    reason: str
    payload: dict[str, object]


@dataclass(frozen=True)
class ProjectionView:
    """One derived macro prose view over canonical graph anchors."""

    view_id: str
    profile: str
    members: tuple[str, ...]
    role: str
    reader_state_before: str
    reader_state_after: str
    abstraction_level: str
    recommended_format: str
    format_reason: str
    inference_basis: dict[str, object]
    confidence: float


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
    ingest.add_argument("--db", type=Path, help="Graph DB path. Defaults to the user-home prose graph cache.")
    ingest.add_argument("--kind", default="document")
    ingest.add_argument("--prompt", default="", help="Optional user prompt text for corpus/domain inference.")
    ingest.add_argument("--prompt-file", type=Path, help="Optional user prompt file for corpus/domain inference.")
    add_local_llm_ir_args(ingest)
    add_stats_out(ingest)

    ingest_set = subparsers.add_parser("ingest-set", help="Ingest multiple Markdown/plain text files into one graph DB.")
    ingest_set.add_argument("inputs", nargs="+", type=Path)
    ingest_set.add_argument("--db", type=Path, help="Graph DB path. Defaults to the user-home prose graph cache.")
    ingest_set.add_argument("--kind", default="document")
    ingest_set.add_argument("--recursive", action="store_true", help="Recurse into input directories.")
    ingest_set.add_argument("--prompt", default="", help="Optional user prompt text for corpus/domain inference.")
    ingest_set.add_argument("--prompt-file", type=Path, help="Optional user prompt file for corpus/domain inference.")
    add_local_llm_ir_args(ingest_set)
    add_stats_out(ingest_set)

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

    check_document = subparsers.add_parser(
        "check-document",
        help="Run prose graph analysis and structured-analysis document-canon checks for one document.",
    )
    check_document.add_argument("input", type=Path)
    check_document.add_argument("--db", type=Path, help="Graph DB path. Defaults to the user-home prose graph cache.")
    check_document.add_argument("--repo-root", type=Path, help="Root for structured-analysis. Defaults from the input path.")
    check_document.add_argument("--out-dir", type=Path, required=True)
    check_document.add_argument("--profile", choices=PROFILES, default="all")
    check_document.add_argument("--structured-profile", default="manual")
    check_document.add_argument(
        "--structured-inventory-json",
        type=Path,
        help="Use an existing structured-analysis document inventory JSON instead of running build.",
    )
    check_document.add_argument("--kind", default="document")
    check_document.add_argument("--prompt", default="", help="Optional user prompt text for corpus/domain inference.")
    check_document.add_argument("--prompt-file", type=Path, help="Optional user prompt file for corpus/domain inference.")
    add_local_llm_ir_args(check_document)
    add_stats_out(check_document)

    return parser


def add_db_profile(parser: argparse.ArgumentParser) -> None:
    """Add DB and profile arguments."""
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--profile", choices=PROFILES, default=DEFAULT_PROFILE)


def add_stats_out(parser: argparse.ArgumentParser) -> None:
    """Add the compact stats artifact argument."""
    parser.add_argument("--stats-out", type=Path, help="Write compact command stats JSON.")


def add_local_llm_ir_args(parser: argparse.ArgumentParser) -> None:
    """Add LocalLLM prose IR extraction arguments."""
    parser.add_argument(
        "--local-llm-ir-json",
        type=Path,
        help="Use an existing LocalLLM prose IR JSON instead of running local-llm extract-prose-ir.",
    )
    parser.add_argument(
        "--local-llm-root",
        type=Path,
        help="Root for local-llm extract-prose-ir. Defaults from the input path.",
    )
    parser.add_argument(
        "--term",
        action="append",
        default=[],
        help="Term to include in the LocalLLM prose IR batch. May be repeated.",
    )
    parser.add_argument(
        "--terms-file",
        action="append",
        type=Path,
        default=[],
        help="File containing additional terms for the LocalLLM prose IR batch. May be repeated.",
    )
    parser.add_argument(
        "--local-llm-document-batch-size",
        type=int,
        default=4,
        help="Maximum documents per LocalLLM prose IR part.",
    )
    parser.add_argument(
        "--local-llm-term-batch-size",
        type=int,
        default=32,
        help="Maximum terms per LocalLLM prose IR part.",
    )


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


def graph_db_path(args: argparse.Namespace, inputs: Sequence[Path]) -> Path:
    """Return the explicit or default graph DB path for DB-creating commands."""
    explicit_db = getattr(args, "db", None)
    if isinstance(explicit_db, Path):
        return explicit_db
    db_path = default_graph_db_path(inputs)
    args.db = db_path
    return db_path


def default_graph_db_path(inputs: Sequence[Path]) -> Path:
    """Return the user-home cache path for an ingested source set."""
    return default_graph_home().joinpath(repo_cache_key(), source_cache_key(inputs), DEFAULT_DB_NAME)


def default_graph_home() -> Path:
    """Return the root directory for generated prose graph DBs."""
    configured = os.environ.get(DEFAULT_DB_HOME_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "agent-canon" / "prose-reasoning-graph"


def repo_cache_key() -> str:
    """Return a stable cache key for the current repository/workspace."""
    root = Path.cwd().resolve()
    label = sanitize_cache_segment(root.name or "workspace")
    return f"{label}-{short_hash(root.as_posix())}"


def source_cache_key(inputs: Sequence[Path]) -> str:
    """Return a stable cache key for one source or a multi-source ingest set."""
    if len(inputs) == 1:
        first_input = inputs[0]
        label = first_input.stem if first_input.is_file() else first_input.name
    else:
        label = "ingest-set"
    digest_basis = "\n".join(resolved_path_text(input_path) for input_path in inputs)
    return f"{sanitize_cache_segment(label)}-{short_hash(digest_basis)}"


def resolved_path_text(path: Path) -> str:
    """Return a normalized path string for cache hashing."""
    try:
        return path.resolve().as_posix()
    except OSError:
        return path.absolute().as_posix()


def short_hash(value: str) -> str:
    """Return a short stable hash for cache path disambiguation."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:DEFAULT_CACHE_HASH_LENGTH]


def sanitize_cache_segment(value: str) -> str:
    """Return a filesystem-safe cache path segment."""
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return sanitized or "workspace"


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


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    """Return true when the connected graph DB has a table."""
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


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


def clear_database(connection: sqlite3.Connection) -> None:
    """Remove all graph data before a fresh ingest."""
    connection.executescript(
        """
        DELETE FROM metadata;
        DELETE FROM judgements;
        DELETE FROM edit_operations;
        DELETE FROM diagnostics;
        DELETE FROM edges;
        DELETE FROM nodes;
        DELETE FROM documents;
        """
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


def verification_action_for_rule(rule: str) -> dict[str, object]:
    """Return a verification route for uncertain logic, evidence, or connections."""
    if rule in {"unsupported_claim", "claim_without_evidence_layer"}:
        return {
            "add": "evidence, warrant, limitation, or verification result",
            "verification_route": "claim_support_verification",
            "verification_question": "Is the claim supported by source evidence, a valid warrant, a formal proof obligation, or a stated limitation?",
            "verification_targets": ["logic-gap-review", "$literature-survey", "citation-evidence-review"],
            "conditional_verification_targets": [
                {
                    "target": "$formal-proof-workflow",
                    "when": "the claim is mathematical, proof-like, or implementation-derived",
                }
            ],
            "evidence_required": ["source packet", "citation or measured result", "explicit warrant or proof obligation"],
            "recursive_verification": recursive_verification_for_route("claim_support_verification"),
        }
    if rule == "topic_jump_without_bridge":
        return {
            "add": "verified bridge, explicit relation, reorder decision, or separation",
            "verification_route": "connection_verification",
            "verification_question": "Do the adjacent units share a valid discourse relation, missing premise, or reader-state transition?",
            "verification_targets": ["$structure-planning", "logic-gap-review"],
            "conditional_verification_targets": [
                {
                    "target": "$literature-survey",
                    "when": "the bridge depends on an external factual or scholarly premise",
                }
            ],
            "evidence_required": ["relation label", "shared question or warrant", "reader-state before/after"],
            "recursive_verification": recursive_verification_for_route("connection_verification"),
        }
    if rule.startswith("experiment_") or rule == "metric_without_baseline":
        return {
            "add": "experiment-plan field or documented not-applicable decision",
            "verification_route": "experiment_plan_verification",
            "verification_question": "Is the experiment claim testable with a hypothesis, metric, baseline, and expected result?",
            "verification_targets": ["$experiment-lifecycle", "$report-writing"],
            "evidence_required": ["hypothesis", "metric", "baseline", "expected result", "run or rerun decision"],
            "recursive_verification": recursive_verification_for_route("experiment_plan_verification"),
        }
    if rule == "non_llm_experiment_plan_fallback":
        return {
            "add": "LocalLLM IR analysis_intents or subagent verification packet",
            "verification_route": "local_llm_or_subagent_intent_verification",
            "verification_question": "Can experiment-plan applicability be classified by LocalLLM IR or a subagent instead of non-LLM fallback?",
            "verification_targets": ["$prose-reasoning-graph", "subagent-fallback"],
            "evidence_required": ["local_llm_prose_ir.analysis_intents", "subagent judgement or explicit fallback acceptance"],
        }
    return {}


def recursive_verification_for_route(route: str) -> dict[str, object]:
    """Return recursive verification expansion rules for one route."""
    common: dict[str, object] = {
        "max_depth": VERIFICATION_RECURSION_MAX_DEPTH,
        "closure_condition": "all child questions have evidence, checked proof/experiment evidence, an explicit limitation, or an unresolved-leaf record",
        "unresolved_leaf_policy": "do not rewrite as settled prose; record blocker/warn with owner, route, missing evidence, and next verification command",
    }
    if route == "claim_support_verification":
        return {
            **common,
            "steps": [
                {
                    "id": "decompose_claim",
                    "route": "logic-gap-review",
                    "question": "What are the atomic claim, assumptions, warrants, and evidence requirements?",
                    "if_unresolved": "create child claim_support_verification items for each missing premise or warrant",
                },
                {
                    "id": "verify_external_support",
                    "route": "$literature-survey / citation-evidence-review",
                    "question": "Does a source packet, citation, measurement, or contrary source settle each atomic claim?",
                    "if_unresolved": "record missing source packet or limitation and keep the child open",
                },
                {
                    "id": "verify_formal_obligation",
                    "route": "$formal-proof-workflow",
                    "question": "If the claim is mathematical, proof-like, or implementation-derived, can a proof obligation be checked?",
                    "if_unresolved": "record proof_status and the exact missing checker, command, lemma, or environment",
                },
            ],
        }
    if route == "connection_verification":
        return {
            **common,
            "steps": [
                {
                    "id": "classify_relation",
                    "route": "$structure-planning",
                    "question": "What discourse relation or reader-state transition is claimed between the adjacent units?",
                    "if_unresolved": "try reorder, separation, or explicit limitation before adding a bridge",
                },
                {
                    "id": "verify_missing_premise",
                    "route": "logic-gap-review",
                    "question": "Does the connection require an unstated premise or warrant?",
                    "if_unresolved": "create child claim_support_verification items for the missing premise",
                },
                {
                    "id": "verify_external_bridge",
                    "route": "$literature-survey",
                    "question": "Does the bridge depend on external factual or scholarly support?",
                    "if_unresolved": "record missing source packet or remove the bridge claim",
                },
            ],
        }
    if route == "experiment_plan_verification":
        return {
            **common,
            "steps": [
                {
                    "id": "decompose_empirical_claim",
                    "route": "$experiment-lifecycle",
                    "question": "What hypothesis, metric, baseline, expected result, and stop condition are required?",
                    "if_unresolved": "create child experiment_plan_verification items for each missing field",
                },
                {
                    "id": "verify_measurement_contract",
                    "route": "$experiment-lifecycle",
                    "question": "Can the metric be measured with a valid denominator, directionality, and comparison?",
                    "if_unresolved": "record rerun or protocol-design blocker",
                },
                {
                    "id": "verify_report_claim",
                    "route": "$report-writing",
                    "question": "Does the report claim stay within the verified experiment result and limitations?",
                    "if_unresolved": "downgrade to limitation or keep the claim out of prose",
                },
            ],
        }
    return common


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
    db_path = graph_db_path(args, [input_path])
    text = input_path.read_text(encoding="utf-8")
    prompt_text = prompt_context(args)
    local_llm_ir = local_llm_prose_ir_payload(args, [input_path], prompt_text, db_path)
    corpus_hints = corpus_hints_from_local_llm_ir(local_llm_ir)
    with connect(db_path) as connection:
        initialize_schema(connection)
        clear_database(connection)
        set_metadata(connection, "local_llm_prose_ir", local_llm_ir)
        set_metadata(connection, "corpus_hints", corpus_hints)
        set_metadata(
            connection,
            "corpus_hint_inputs",
            {
                "source": "local_llm_prose_ir",
                "document_path": str(input_path),
                "prompt_supplied": bool(prompt_text.strip()),
                "ir_schema": local_llm_ir.get("schema", ""),
            },
        )
        ingest_document(
            connection,
            input_path,
            text,
            document_id="doc:1",
            source_node_id="src:1",
            kind=cast(str, args.kind),
        )
    emit_command_stats(
        args,
        "PROSE_REASONING_GRAPH_INGEST",
        {
            "PROSE_REASONING_GRAPH_DB": str(db_path),
            "PROSE_REASONING_GRAPH_LOCAL_LLM_IR": str(local_llm_ir.get("artifact_path", "")),
        },
    )
    return 0


def command_ingest_set(args: argparse.Namespace) -> int:
    """Run multi-document ingest command."""
    input_args = cast(Sequence[Path], args.inputs)
    db_path = graph_db_path(args, input_args)
    input_paths = expand_ingest_inputs(input_args, bool(args.recursive))
    prompt_text = prompt_context(args)
    documents = [(path, path.read_text(encoding="utf-8")) for path in input_paths]
    local_llm_ir = local_llm_prose_ir_payload(args, input_paths, prompt_text, db_path)
    corpus_hints = corpus_hints_from_local_llm_ir(local_llm_ir)
    with connect(db_path) as connection:
        initialize_schema(connection)
        clear_database(connection)
        set_metadata(connection, "local_llm_prose_ir", local_llm_ir)
        set_metadata(connection, "corpus_hints", corpus_hints)
        set_metadata(
            connection,
            "corpus_hint_inputs",
            {
                "source": "local_llm_prose_ir",
                "document_paths": [str(path) for path, _ in documents],
                "prompt_supplied": bool(prompt_text.strip()),
                "ir_schema": local_llm_ir.get("schema", ""),
            },
        )
        connection.execute(
            "INSERT INTO documents(id, path, title, kind, created_at) VALUES (?, ?, ?, ?, ?)",
            ("doc:analysis", "analysis://collection", "Document collection analysis", "analysis", utc_now()),
        )
        for index, (path, text) in enumerate(documents, start=1):
            ingest_document(
                connection,
                path,
                text,
                document_id=f"doc:{index}",
                source_node_id=f"src:{index}",
                kind=cast(str, args.kind),
                node_prefix=f"d{index}:",
            )
    emit_command_stats(
        args,
        "PROSE_REASONING_GRAPH_INGEST_SET",
        {
            "PROSE_REASONING_GRAPH_DB": str(db_path),
            "PROSE_REASONING_GRAPH_DOCUMENTS": len(documents),
            "PROSE_REASONING_GRAPH_LOCAL_LLM_IR": str(local_llm_ir.get("artifact_path", "")),
        },
    )
    return 0


def expand_ingest_inputs(inputs: Sequence[Path], recursive: bool) -> list[Path]:
    """Expand file and directory inputs for multi-document ingest."""
    output: list[Path] = []
    for input_path in inputs:
        if input_path.is_dir():
            pattern = "**/*" if recursive else "*"
            output.extend(
                path
                for path in sorted(input_path.glob(pattern))
                if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}
            )
            continue
        if input_path.is_file():
            output.append(input_path)
            continue
        raise ValueError(f"ingest input does not exist: {input_path}")
    if not output:
        raise ValueError("ingest-set found no input files")
    return output


def ingest_document(
    connection: sqlite3.Connection,
    input_path: Path,
    text: str,
    *,
    document_id: str,
    source_node_id: str,
    kind: str,
    node_prefix: str = "",
) -> None:
    """Insert one source document and its source/form nodes."""
    title = infer_title(text, input_path)
    connection.execute(
        "INSERT INTO documents(id, path, title, kind, created_at) VALUES (?, ?, ?, ?, ?)",
        (document_id, str(input_path), title, kind, utc_now()),
    )
    insert_node(
        connection,
        source_node_id,
        document_id,
        "source",
        "document",
        title,
        text,
        0,
        len(text),
        payload={
            "path": str(input_path),
            "kind": kind,
        },
    )
    ingest_blocks(connection, document_id, text, str(input_path), node_prefix=node_prefix)


def prompt_context(args: argparse.Namespace) -> str:
    """Return optional user prompt context for corpus inference."""
    prompt_parts: list[str] = []
    prompt = getattr(args, "prompt", "")
    if isinstance(prompt, str) and prompt:
        prompt_parts.append(prompt)
    prompt_file = getattr(args, "prompt_file", None)
    if isinstance(prompt_file, Path):
        if not prompt_file.is_file():
            raise ValueError(f"prompt file does not exist: {prompt_file}")
        prompt_parts.append(prompt_file.read_text(encoding="utf-8"))
    return "\n".join(prompt_parts)


def local_llm_prose_ir_payload(
    args: argparse.Namespace,
    input_paths: Sequence[Path],
    prompt_text: str,
    db_path: Path,
) -> dict[str, object]:
    """Return LocalLLM-extracted prose intermediate representation."""
    explicit_ir = getattr(args, "local_llm_ir_json", None)
    if isinstance(explicit_ir, Path):
        if not explicit_ir.is_file():
            raise ValueError(f"LocalLLM prose IR JSON does not exist: {explicit_ir}")
        payload = read_json_file(explicit_ir)
        payload.setdefault("artifact_path", str(explicit_ir))
        return payload

    repo_root = local_llm_root(args, input_paths[0])
    ir_path = db_path.parent / "local_llm_prose_ir.json"
    command = [
        str(agent_canon_cli(repo_root)),
        "local-llm",
        "extract-prose-ir",
        "--root",
        str(repo_root),
        "--json-out",
        str(ir_path),
        "--document-batch-size",
        str(getattr(args, "local_llm_document_batch_size", 4)),
        "--term-batch-size",
        str(getattr(args, "local_llm_term_batch_size", 32)),
    ]
    if prompt_text.strip():
        command.extend(["--prompt", prompt_text])
    for term in cast(list[str], getattr(args, "term", [])):
        command.extend(["--term", term])
    for terms_file in cast(list[Path], getattr(args, "terms_file", [])):
        command.extend(["--terms-file", str(terms_file.resolve())])
    command.extend(str(path.resolve()) for path in input_paths)
    result = subprocess.run(
        command,
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(
            "local-llm extract-prose-ir failed: "
            f"exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    emitted_ir = stdout_field(result.stdout, LOCAL_LLM_PROSE_IR_STDOUT_KEY)
    if emitted_ir:
        ir_path = Path(emitted_ir)
    if not ir_path.is_file():
        raise ValueError(f"local-llm prose IR JSON was not created: {ir_path}")
    payload = read_json_file(ir_path)
    payload.setdefault("artifact_path", str(ir_path))
    payload.setdefault("source_command", "agent-canon local-llm extract-prose-ir")
    return payload


def local_llm_root(args: argparse.Namespace, input_path: Path) -> Path:
    """Return the LocalLLM root for IR extraction."""
    explicit_root = getattr(args, "local_llm_root", None)
    if isinstance(explicit_root, Path):
        return explicit_root.resolve()
    return structured_repo_root(args, input_path)


def agent_canon_cli(repo_root: Path) -> Path | str:
    """Return the preferred AgentCanon Rust CLI entrypoint."""
    candidates = [
        repo_root / "rust" / "agent-canon" / "target" / "debug" / "agent-canon",
        Path.cwd() / "rust" / "agent-canon" / "target" / "debug" / "agent-canon",
        Path.cwd() / "vendor" / "agent-canon" / "rust" / "agent-canon" / "target" / "debug" / "agent-canon",
        repo_root / "tools" / "bin" / "agent-canon",
        Path.cwd() / "tools" / "bin" / "agent-canon",
        Path.cwd() / "vendor" / "agent-canon" / "tools" / "bin" / "agent-canon",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return "agent-canon"


def corpus_hints_from_local_llm_ir(payload: dict[str, object]) -> list[dict[str, object]]:
    """Return corpus hints extracted by LocalLLM prose IR."""
    hints = object_list(payload.get("corpus_hints"))
    if hints:
        return hints
    return [
        {
            "corpus_id": "general_prose",
            "label": "General prose and document-structure corpus",
            "score": 0,
            "selected": True,
            "basis": {"source": "local_llm_prose_ir", "signals": []},
        }
    ]


def set_metadata(connection: sqlite3.Connection, key: str, value: object) -> None:
    """Store one JSON metadata value."""
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        (key, write_json(value)),
    )


def metadata_json(connection: sqlite3.Connection, key: str, default: object) -> object:
    """Return one JSON metadata value."""
    row = connection.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return json.loads(str(row["value"]))


def infer_title(text: str, path: Path) -> str:
    """Infer a title from Markdown or path."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("_", " ").replace("-", " ").strip() or "document"


def ingest_blocks(
    connection: sqlite3.Connection,
    document_id: str,
    text: str,
    source_locator: str,
    *,
    node_prefix: str = "",
) -> None:
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
            node_id = f"{node_prefix}sec:{index}"
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
                payload=anchor_payload(
                    "section",
                    source_locator,
                    "markdown_heading",
                    {"level": level, "section_path": section_stack.copy()},
                ),
            )
        else:
            paragraph_index += 1
            node_id = f"{node_prefix}p:{paragraph_index}"
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
                payload=anchor_payload(
                    "paragraph",
                    source_locator,
                    "markdown_block",
                    {"section_path": section_stack.copy(), "ordinal": paragraph_index},
                ),
            )
            if previous_block_id:
                insert_edge(
                    connection,
                    f"{node_prefix}order:{previous_block_id}->{node_id}",
                    "presentation",
                    "precedes",
                    previous_block_id,
                    node_id,
                    order_kind="hard_before",
                    payload={
                        "source": "ingest_order",
                        "participates_in_ordering_dag": True,
                        "ordering_subgraph": "presentation",
                    },
                )
            previous_block_id = node_id
            for sentence in split_sentences(block_text):
                sentence_index += 1
                sentence_start = text.find(sentence, start, end)
                sentence_end = sentence_start + len(sentence) if sentence_start >= 0 else end
                sentence_id = f"{node_prefix}s:{sentence_index}"
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
                    payload=anchor_payload(
                        "sentence",
                        source_locator,
                        "sentence_split",
                        {"paragraph_id": node_id, "ordinal": sentence_index},
                    ),
                )
                insert_edge(
                    connection,
                    f"{node_prefix}contains:{node_id}->{sentence_id}",
                    "form",
                    "contains",
                    node_id,
                    sentence_id,
                    payload={
                        "source": "sentence_split",
                        "participates_in_projection_order": True,
                        "ordering_subgraph": "form_containment",
                    },
                )


def anchor_payload(
    span_kind: str,
    source_locator: str,
    segmentation_basis: str,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return canonical source-anchor payload fields."""
    payload: dict[str, object] = {
        "span_kind": span_kind,
        "source_locator": source_locator,
        "segmentation_basis": segmentation_basis,
    }
    if extra:
        payload.update(extra)
    return payload


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
    stripped = text.strip()
    if not stripped:
        return ()

    sentences: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in "。！？":
            end = index + 1
        elif char in ".!?" and is_ascii_sentence_boundary(text, index):
            end = include_closing_punctuation(text, index + 1)
        else:
            index += 1
            continue

        candidate = text[start:end].strip()
        if candidate:
            sentences.append(candidate)
        start = skip_sentence_gap(text, end)
        index = start

    remainder = text[start:].strip()
    if remainder:
        sentences.append(remainder)
    return tuple(sentences or (stripped,))


def is_ascii_sentence_boundary(text: str, index: int) -> bool:
    """Return whether ASCII punctuation marks a sentence boundary."""
    char = text[index]
    next_index = include_closing_punctuation(text, index + 1)
    if next_index < len(text) and not text[next_index].isspace():
        return False
    if char != ".":
        return True
    if index > 0 and index + 1 < len(text) and text[index - 1].isdigit() and text[index + 1].isdigit():
        return False
    return not is_ascii_abbreviation_period(text, index)


def is_ascii_abbreviation_period(text: str, index: int) -> bool:
    """Return whether a period belongs to a common abbreviation."""
    before = text[:index].rstrip()
    if not before:
        return False
    token = re.split(r"\s+", before)[-1].strip("\"'([{<")
    normalized = token.lower()
    if normalized in ASCII_SENTENCE_ABBREVIATIONS:
        return True
    if len(token) == 1 and token.isupper():
        return True
    return bool(re.search(r"[A-Za-z]\d+(?:\.\d+)*$", token))


def include_closing_punctuation(text: str, index: int) -> int:
    """Include closing quotes and brackets after sentence punctuation."""
    while index < len(text) and text[index] in "\"')]}”’":
        index += 1
    return index


def skip_sentence_gap(text: str, index: int) -> int:
    """Return the next non-space index after a sentence boundary."""
    while index < len(text) and text[index].isspace():
        index += 1
    return index


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
    add_experiment_layer(connection, document_id, sentences, profile)
    add_explanation_layer(connection, document_id, profile)
    add_section_edges(connection, sections, paragraphs)
    add_diagnostics(connection, paragraphs, claims, evidence, profile)
    add_edit_operations(connection, paragraphs)


def fetch_document_id(connection: sqlite3.Connection) -> str:
    """Return the document id that should own analysis overlays."""
    analysis_row = connection.execute("SELECT id FROM documents WHERE id = ?", ("doc:analysis",)).fetchone()
    if analysis_row is not None:
        return str(analysis_row["id"])
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
        f"SELECT * FROM nodes {where} ORDER BY document_id, source_start, id", values
    ).fetchall()
    return tuple(
        Node(
            node_id=str(row["id"]),
            document_id=str(row["document_id"]),
            layer=str(row["layer"]),
            kind=str(row["kind"]),
            label=str(row["label"]),
            text=str(row["text"]),
            payload=read_json_object(str(row["payload_json"])),
            source_start=int(row["source_start"]),
            source_end=int(row["source_end"]),
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
        payload={
            "profile": profile,
            "canonical_graph": "text_anchored_semantic_graph",
            "projection_view_export": "projection_views",
            "outputs": ["yaml", "json", "markdown"],
        },
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
                "participates_in_ordering_dag": True,
                "ordering_subgraph": "discourse_adjacency",
            },
        )


def infer_discourse_relation(text: str) -> str:
    """Infer a coarse discourse relation."""
    lowered = text.lower()
    if any(cue in lowered for cue in ("however", "but", "although", "ただし", "一方")):
        return "contrasts"
    if any(cue in lowered for cue in ("because", "therefore", "thus", "so ", "なので", "したがって", "このため", "根拠")):
        return "causes"
    if any(cue in lowered for cue in ("for example", "e.g.", "例えば", "具体例")):
        return "exemplifies"
    if any(cue in lowered for cue in ("limitation", "risk", "制限", "リスク")):
        return "limits"
    return "elaborates"


def first_discourse_signal(text: str) -> str:
    """Return the first explicit discourse cue."""
    lowered = text.lower()
    cues = (
        "however",
        "because",
        "therefore",
        "for example",
        "limitation",
        "ただし",
        "一方",
        "例えば",
        "具体例",
        "このため",
        "この図",
        "また",
        "次は",
        "根拠",
        "制限",
    )
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
                sentence.source_start,
                sentence.source_end,
                confidence=EXTRACTED_NODE_CONFIDENCE,
                payload=derived_anchor_payload(sentence.node_id, "cue_heuristic"),
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
                    document_id,
                    "argument",
                    "claim",
                    first_words(sentence.text, EXTRACTED_NODE_LABEL_WORD_LIMIT),
                    sentence.text,
                    derived_anchor_payload(sentence.node_id, "cue_heuristic"),
                    sentence.source_start,
                    sentence.source_end,
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
                sentence.source_start,
                sentence.source_end,
                confidence=EXTRACTED_NODE_CONFIDENCE,
                payload={
                    **derived_anchor_payload(sentence.node_id, "evidence_cue"),
                    "strength": "candidate",
                },
            )
            evidence_nodes.append(
                Node(
                    evidence_id,
                    document_id,
                    "evidence",
                    "evidence",
                    first_words(sentence.text, EXTRACTED_NODE_LABEL_WORD_LIMIT),
                    sentence.text,
                    {
                        **derived_anchor_payload(sentence.node_id, "evidence_cue"),
                        "strength": "candidate",
                    },
                    sentence.source_start,
                    sentence.source_end,
                )
            )
    for claim in claims:
        evidence = best_supporting_evidence(claim, evidence_nodes)
        if evidence is not None:
            basis = "document_neighborhood"
            insert_edge(
                connection,
                f"support:{evidence.node_id}->{claim.node_id}",
                "evidence",
                "supports",
                evidence.node_id,
                claim.node_id,
                confidence=0.5,
                payload={"basis": basis, "member_anchor_ids": member_anchor_ids(evidence, claim)},
            )
            evidence_anchor = anchor_id_for_derived_node(evidence)
            claim_anchor = anchor_id_for_derived_node(claim)
            if evidence_anchor and claim_anchor and evidence_anchor != claim_anchor:
                insert_edge(
                    connection,
                    f"anchor-support:{evidence_anchor}->{claim_anchor}",
                    "evidence",
                    "supports",
                    evidence_anchor,
                    claim_anchor,
                    confidence=0.5,
                    evidence_node_id=evidence.node_id,
                    payload={
                        "basis": basis,
                        "claim_node_id": claim.node_id,
                        "evidence_node_id": evidence.node_id,
                        "participates_in_ordering_dag": False,
                    },
                )
    return tuple(evidence_nodes)


def derived_anchor_payload(anchor_id: str, basis: str) -> dict[str, object]:
    """Return payload fields for analysis nodes derived from source anchors."""
    return {
        "sentence_id": anchor_id,
        "member_anchor_ids": [anchor_id],
        "source_anchor_id": anchor_id,
        "derivation_basis": basis,
    }


def anchor_id_for_derived_node(node: Node) -> str:
    """Return the source anchor id for a derived analysis node."""
    anchor = node.payload.get("source_anchor_id", node.payload.get("sentence_id", ""))
    return anchor if isinstance(anchor, str) else ""


def member_anchor_ids(*nodes: Node) -> list[str]:
    """Return unique source anchor ids from derived nodes."""
    output: list[str] = []
    for node in nodes:
        anchor = anchor_id_for_derived_node(node)
        if anchor and anchor not in output:
            output.append(anchor)
    return output


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


def add_experiment_layer(
    connection: sqlite3.Connection,
    document_id: str,
    sentences: Sequence[Node],
    profile: str,
) -> None:
    """Extract experiment-planning nodes."""
    if not experiment_plan_applicable_for_graph(connection, [sentence.text for sentence in sentences], profile):
        return
    counters: Counter[str] = Counter()
    for sentence in sentences:
        for kind in experiment_sentence_kinds(sentence.text):
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
                sentence.source_start,
                sentence.source_end,
                confidence=EXTRACTED_NODE_CONFIDENCE,
                payload=derived_anchor_payload(sentence.node_id, f"experiment_{kind}_cue"),
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
                    payload={
                        "source": "markdown_heading",
                        "participates_in_projection_order": True,
                        "ordering_subgraph": "form_containment",
                    },
                )


def has_any(text: str, cues: Iterable[str]) -> bool:
    """Return true when text contains any cue."""
    lowered = text.lower()
    return any(cue_present(lowered, cue) for cue in cues)


def cue_present(lowered_text: str, cue: str) -> bool:
    """Return true when cue appears as a standalone cue."""
    lowered_cue = cue.lower()
    if lowered_cue.isascii() and re.fullmatch(r"[a-z0-9_-]+", lowered_cue):
        return bool(
            re.search(
                rf"(?<![a-z0-9_-]){re.escape(lowered_cue)}(?![a-z0-9_-])",
                lowered_text,
            )
        )
    return lowered_cue in lowered_text


def add_diagnostics(
    connection: sqlite3.Connection,
    paragraphs: Sequence[Node],
    claims: Sequence[Node],
    evidence_nodes: Sequence[Node],
    profile: str,
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
                action=verification_action_for_rule("unsupported_claim"),
            )
    if experiment_plan_applicable_for_graph(connection, [paragraph.text for paragraph in paragraphs], profile):
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
        if left.document_id != right.document_id:
            continue
        if section_path(left) != section_path(right):
            continue
        if (
            lexical_overlap(left.text, right.text) < TOPIC_JUMP_MAX_OVERLAP
            and not first_discourse_signal(right.text)
            and not is_structured_presentation_block(left.text)
            and not is_structured_presentation_block(right.text)
        ):
            insert_diagnostic(
                connection,
                f"diag:topic-jump:{index}",
                "discourse",
                right.node_id,
                "warn",
                "topic_jump_without_bridge",
                f"Paragraph `{left.node_id}` to `{right.node_id}` has low shared terms and no bridge cue.",
                action=verification_action_for_rule("topic_jump_without_bridge"),
            )
    if claims and not evidence_nodes:
        insert_document_diagnostic(connection, "claim_without_evidence_layer", "Claims exist but the evidence layer has no evidence nodes.")
    add_layer_coverage_diagnostic(connection, profile)


def is_structured_presentation_block(text: str) -> bool:
    """Return true for blocks whose boundary is expected to be visually abrupt."""
    stripped = text.lstrip()
    return bool(
        re.match(r"(?:```|\||[-*]\s+|\d+[.]\s+)", stripped)
        or stripped.startswith("<!--")
        or re.match(r"[A-Za-z0-9_]+\s*(?:-->|==>|-.->|---|--)", stripped)
        or re.match(r"(?:flowchart|graph|subgraph|end\b)", stripped)
        or re.match(r"[A-Za-z0-9_]+\[", stripped)
    )


def safe_identifier(value: str) -> str:
    """Return a compact id-safe suffix."""
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value)


def section_path(node: Node) -> tuple[str, ...]:
    """Return a node's section path from source-anchor payload."""
    raw_path = node.payload.get("section_path", [])
    if not isinstance(raw_path, list):
        return ()
    return tuple(str(item) for item in cast(list[object], raw_path))


def insert_document_diagnostic(
    connection: sqlite3.Connection,
    rule: str,
    message: str,
    action: dict[str, object] | None = None,
) -> None:
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
        action=action if action is not None else verification_action_for_rule(rule),
    )


def add_layer_coverage_diagnostic(connection: sqlite3.Connection, profile: str) -> None:
    """Record layer coverage as diagnostic metadata."""
    counts = layer_counts(connection)
    missing = [
        layer
        for layer in required_layers_for_profile(
            profile,
            experiment_applicable=experiment_layer_applicable(connection),
        )
        if counts.get(layer, 0) == 0
    ]
    if missing:
        insert_document_diagnostic(
            connection,
            "missing_layer_representation",
            f"Missing graph layer representations: {', '.join(missing)}.",
        )


def experiment_layer_applicable(connection: sqlite3.Connection) -> bool:
    """Return true when the document actually contains experiment-plan language."""
    if layer_counts(connection).get("experiment", 0) > 0:
        return True
    rows = connection.execute(
        """
        SELECT text
        FROM nodes
        WHERE layer IN ('source', 'form')
          AND kind IN ('document', 'section', 'paragraph', 'sentence')
        """
    ).fetchall()
    return experiment_plan_applicable_for_graph(connection, [str(row["text"]) for row in rows], "all")


def experiment_plan_applicable_for_graph(
    connection: sqlite3.Connection,
    texts: Iterable[str],
    profile: str,
) -> bool:
    """Return true when LocalLLM IR says experiment-plan analysis is applicable."""
    local_status = local_llm_experiment_plan_status(connection)
    if local_status == "present":
        return True
    if local_status in {"absent", "vocabulary_only"}:
        return False
    fallback_applicable = non_llm_experiment_plan_fallback_applicable(texts, profile)
    insert_document_diagnostic(
        connection,
        "non_llm_experiment_plan_fallback",
        (
            "LocalLLM experiment-plan intent was unavailable; "
            "non-LLM fallback check was used."
        ),
    )
    return fallback_applicable


def local_llm_experiment_plan_status(connection: sqlite3.Connection) -> str:
    """Return LocalLLM IR's experiment-plan intent status."""
    payload = metadata_json(connection, "local_llm_prose_ir", {})
    if not isinstance(payload, dict):
        return ""
    intents = object_list(payload.get("analysis_intents"))
    statuses = [
        str(intent.get("status", ""))
        for intent in intents
        if str(intent.get("intent", "")) == "experiment_plan"
    ]
    if "present" in statuses:
        return "present"
    if "vocabulary_only" in statuses:
        return "vocabulary_only"
    if "absent" in statuses:
        return "absent"
    return ""


def non_llm_experiment_plan_fallback_applicable(texts: Iterable[str], profile: str) -> bool:
    """Return a fallback experiment-plan decision when LocalLLM IR is unavailable."""
    text_values = list(texts)
    if profile == "experiment":
        return any(has_any(text, EXPERIMENT_CUES) for text in text_values)
    field_kinds = experiment_plan_assignment_kinds(text_values)
    if len(field_kinds) >= 2:
        return True
    activity_present = any(has_any(text, EXPERIMENT_ACTIVITY_CUES) for text in text_values)
    field_vocabulary_present = any(
        has_any(text, ("hypothesis", "metric", "baseline", "expected", "仮説", "指標", "ベースライン", "期待"))
        for text in text_values
    )
    return (bool(field_kinds) and activity_present) or (
        activity_present and not field_vocabulary_present
    )


def experiment_sentence_kinds(text: str) -> list[str]:
    """Return all experiment-plan node kinds named in one source sentence."""
    kinds: list[str] = []
    for kind, cues in (
        ("hypothesis", ("hypothesis", "仮説")),
        ("metric", ("metric", "指標")),
        ("baseline", ("baseline", "ベースライン")),
        ("experiment", EXPERIMENT_ACTIVITY_CUES),
        ("expected_result", ("expected", "期待")),
    ):
        if has_any(text, cues):
            kinds.append(kind)
    return kinds


def experiment_plan_assignment_kinds(texts: Iterable[str]) -> set[str]:
    """Return experiment field kinds stated as actual plan assignments."""
    kinds: set[str] = set()
    for text in texts:
        lowered = text.lower()
        if re.search(r"\bhypothesis\s+(?:is|=|:)", lowered) or re.search(r"仮説\s*は", text):
            kinds.add("hypothesis")
        if re.search(r"\bmetric\s+(?:is|=|:)", lowered) or re.search(r"指標\s*は", text):
            kinds.add("metric")
        if re.search(r"\bbaseline\s+(?:is|=|:)", lowered) or re.search(r"ベースライン\s*は", text):
            kinds.add("baseline")
        if re.search(r"\bexpected(?: result)?\s+(?:is|=|:)", lowered) or re.search(r"期待(?:結果)?\s*は", text):
            kinds.add("expected_result")
    return kinds


def required_layers_for_profile(profile: str, *, experiment_applicable: bool = False) -> tuple[str, ...]:
    """Return layers expected for one analysis profile."""
    base_layers = (
        "source",
        "form",
        "concept",
        "phase",
        "discourse",
        "presentation",
        "projection",
        "explanation",
    )
    if profile == "experiment":
        return (*base_layers, "experiment")
    if profile in {"logic", "academic", "paper"}:
        return (*base_layers, "argument", "evidence")
    if profile == "all":
        layers = (*base_layers, "argument", "evidence")
        if experiment_applicable:
            return (*layers, "experiment")
        return layers
    return base_layers


def add_edit_operations(connection: sqlite3.Connection, paragraphs: Sequence[Node]) -> None:
    """Add split/merge/bridge/reorder operation candidates."""
    prose_paragraphs = [paragraph for paragraph in paragraphs if not is_structured_presentation_block(paragraph.text)]
    for paragraph in prose_paragraphs:
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
    for left, right in zip(prose_paragraphs, prose_paragraphs[1:]):
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
    topic_jump_targets = diagnostic_targets_for_rule(connection, "topic_jump_without_bridge")
    for left, right in zip(prose_paragraphs, prose_paragraphs[1:]):
        if right.node_id in topic_jump_targets:
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
    if len(prose_paragraphs) > 2 and topic_jump_targets:
        insert_operation(
            connection,
            "op:reorder:presentation",
            "reorder_paragraphs",
            [paragraph.node_id for paragraph in prose_paragraphs],
            "Presentation order can be checked against phase order and hard-before edges.",
            operation_payload({"strategy": "priority topological sort with phase preference"}),
        )


def diagnostic_targets_for_rule(connection: sqlite3.Connection, rule: str) -> set[str]:
    """Return node targets for one diagnostic rule."""
    rows = connection.execute("SELECT target_node_id FROM diagnostics WHERE rule = ?", (rule,)).fetchall()
    return {str(row["target_node_id"]) for row in rows}


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
    counts["diagnostics"] += int(diagnostics_count["count"]) if diagnostics_count else 0
    if table_exists(connection, "edit_operations"):
        operations_count = connection.execute("SELECT COUNT(*) AS count FROM edit_operations").fetchone()
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
            verification_suffix = diagnostic_verification_summary(item)
            lines.append(
                f"- `{item.severity}` `{item.rule}` target=`{item.target_node_id or item.target_edge_id}`: "
                f"{item.message}{verification_suffix}"
            )
    lines.append("")
    return "\n".join(lines)


def diagnostic_verification_summary(diagnostic: Diagnostic) -> str:
    """Return a compact verification route suffix for one diagnostic."""
    route = diagnostic.action.get("verification_route")
    if not route:
        return ""
    targets = diagnostic.action.get("verification_targets", [])
    target_text = ", ".join(str(target) for target in cast(list[object], targets)) if isinstance(targets, list) else ""
    if target_text:
        return f" verification_route=`{route}` targets=`{target_text}`"
    return f" verification_route=`{route}`"


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
            action=read_json_object(str(row["suggested_action_json"])),
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
    graph_nodes = fetch_nodes(connection)
    nodes = [asdict(node) for node in graph_nodes]
    edges = [asdict(edge) for edge in fetch_edges(connection)]
    diagnostics = [asdict(item) for item in fetch_diagnostics(connection)]
    operations = [asdict(item) for item in fetch_operations(connection)]
    projection_views = [asdict(item) for item in build_projection_views(connection, profile)]
    return {
        "profile": profile,
        "graph_db": str(db_path),
        "canonical_graph": "text_anchored_semantic_graph",
        "documents": fetch_document_records(connection),
        "local_llm_prose_ir": metadata_json(connection, "local_llm_prose_ir", {}),
        "corpus_hints": metadata_json(connection, "corpus_hints", []),
        "layers": {layer: counts.get(layer, 0) for layer in LAYERS},
        "skill_handoffs": skill_handoffs(profile, db_path),
        "source_anchors": [asdict(node) for node in source_anchor_nodes(graph_nodes)],
        "projection_views": projection_views,
        "nodes": nodes,
        "edges": edges,
        "diagnostics": diagnostics,
        "edit_operations": operations,
    }


def fetch_document_records(connection: sqlite3.Connection) -> list[dict[str, object]]:
    """Return document records in projection-friendly form."""
    rows = connection.execute("SELECT id, path, title, kind, created_at FROM documents ORDER BY id").fetchall()
    return [
        {
            "document_id": str(row["id"]),
            "path": str(row["path"]),
            "title": str(row["title"]),
            "kind": str(row["kind"]),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]


def source_anchor_nodes(nodes: Sequence[Node]) -> tuple[Node, ...]:
    """Return canonical text anchors from graph nodes."""
    return tuple(
        node
        for node in nodes
        if node.layer == "form" and node.kind in {"section", "paragraph", "sentence", "edu"}
    )


def build_projection_views(connection: sqlite3.Connection, profile: str) -> tuple[ProjectionView, ...]:
    """Build derived macro prose views over canonical graph anchors."""
    paragraphs = fetch_nodes(connection, layer="form", kind="paragraph")
    sentences = fetch_nodes(connection, layer="form", kind="sentence")
    phases = fetch_nodes(connection, layer="phase", kind="move")
    phase_by_paragraph: dict[str, Node] = {}
    for phase in phases:
        paragraph_id = phase.payload.get("paragraph_id")
        if isinstance(paragraph_id, str):
            phase_by_paragraph[paragraph_id] = phase

    sentences_by_paragraph: dict[str, list[str]] = {}
    for sentence in sentences:
        paragraph_id = sentence.payload.get("paragraph_id")
        if isinstance(paragraph_id, str):
            sentences_by_paragraph.setdefault(paragraph_id, []).append(sentence.node_id)

    views: list[ProjectionView] = []
    for index, paragraph in enumerate(paragraphs, start=1):
        role = str(phase_by_paragraph.get(paragraph.node_id, paragraph).label)
        sentence_ids = sentences_by_paragraph.get(paragraph.node_id, [])
        members = tuple([paragraph.node_id, *sentence_ids])
        recommended_format, format_reason = presentation_recommendation(
            paragraph.text,
            role,
            len(sentence_ids),
        )
        views.append(
            ProjectionView(
                view_id=f"view:{profile}:{index}",
                profile=profile,
                members=members,
                role=role,
                reader_state_before=reader_state_before(role),
                reader_state_after=reader_state_after(role),
                abstraction_level=abstraction_level_for_role(role),
                recommended_format=recommended_format,
                format_reason=format_reason,
                inference_basis={
                    "source": "canonical_graph_projection",
                    "member_anchor_ids": list(members),
                    "basis_edges": basis_edges_for_members(connection, members),
                    "basis_nodes": [phase_by_paragraph[paragraph.node_id].node_id]
                    if paragraph.node_id in phase_by_paragraph
                    else [],
                },
                confidence=PHASE_INFERENCE_CONFIDENCE if paragraph.node_id in phase_by_paragraph else 0.4,
            )
        )
    return tuple(views)


def presentation_recommendation(text: str, role: str, sentence_count: int) -> tuple[str, str]:
    """Recommend a reader-facing presentation form for one projection view."""
    lowered = text.lower()
    if has_formula_signal(text):
        return ("equation", "formula-like symbols or quantitative relation detected")
    if role == "operationalization" or any(
        cue in lowered for cue in ("metric", "baseline", "expected", "指標", "ベースライン", "期待")
    ):
        return ("table", "structured planning or comparison fields detected")
    if any(
        cue in lowered
        for cue in (
            "graph",
            "dag",
            "node",
            "edge",
            "anchor",
            "projection view",
            "グラフ",
            "ノード",
            "エッジ",
            "図",
        )
    ):
        return ("figure", "graph or spatial-relation vocabulary detected")
    if role == "recommendation" or any(cue in lowered for cue in ("option", "choice", "選択肢", "次の選択")):
        return ("ordered_list", "decision options or action order detected")
    if sentence_count > SPLIT_PARAGRAPH_SENTENCE_LIMIT:
        return ("bulleted_list", "multiple sentence units can be scanned as sibling points")
    return ("prose", "continuous explanation preserves local flow")


def has_formula_signal(text: str) -> bool:
    """Return true when text looks better represented as a formula."""
    return bool(re.search(r"[∑∏√≤≥≈→↦]|(?:[A-Za-z_][A-Za-z0-9_]*\s*(?:=|<=|>=|<|>))", text))


def basis_edges_for_members(connection: sqlite3.Connection, members: Sequence[str]) -> list[str]:
    """Return relation ids that support one projection view."""
    if not members:
        return []
    placeholders = ", ".join("?" for _ in members)
    rows = connection.execute(
        f"""
        SELECT id FROM edges
        WHERE from_node_id IN ({placeholders}) OR to_node_id IN ({placeholders})
        ORDER BY id
        """,
        [*members, *members],
    ).fetchall()
    return [str(row["id"]) for row in rows]


def reader_state_before(role: str) -> str:
    """Return a compact reader-state input label for a projection role."""
    if role == "context":
        return "topic not yet framed"
    if role == "operationalization":
        return "claim not yet measurable"
    if role == "recommendation":
        return "decision not yet stated"
    if role == "limitation":
        return "risk not yet bounded"
    return "current thread established"


def reader_state_after(role: str) -> str:
    """Return a compact reader-state output label for a projection role."""
    if role == "context":
        return "topic framed"
    if role == "operationalization":
        return "claim mapped to observable terms"
    if role == "recommendation":
        return "next decision stated"
    if role == "limitation":
        return "risk or boundary introduced"
    return "thread developed"


def abstraction_level_for_role(role: str) -> str:
    """Return projection abstraction level for a role."""
    if role in {"operationalization", "hypothesis"}:
        return "operational"
    if role in {"recommendation", "limitation"}:
        return "meta"
    if role == "context":
        return "conceptual"
    return "surface"


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
    if not table_exists(connection, "edit_operations"):
        return ()
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
            "projection_fields": [
                "canonical_graph",
                "source_anchors",
                "projection_views",
                "projection_views[].recommended_format",
                "projection_views[].format_reason",
                "corpus_hints",
                "diagnostics",
                "edit_operations",
            ],
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
        verification_suffix = diagnostic_verification_summary(diagnostic)
        lines.append(
            f"- `{diagnostic.severity}` `{diagnostic.rule}` on `{diagnostic.target_node_id}`: "
            f"{diagnostic.message}{verification_suffix}"
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
    diagnostics = fetch_diagnostics(connection)
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
    lines.extend(render_verification_routes(diagnostics))
    return "\n".join(lines)


def render_verification_routes(diagnostics: Sequence[Diagnostic]) -> list[str]:
    """Render verification routes for uncertain logic, evidence, or connections."""
    routed = [diagnostic for diagnostic in diagnostics if diagnostic.action.get("verification_route")]
    lines = ["", "## Verification Routes", ""]
    if not routed:
        lines.append("No verification routes recorded.")
        return lines
    for diagnostic in routed:
        action = diagnostic.action
        targets = action.get("verification_targets", [])
        conditional_targets = action.get("conditional_verification_targets", [])
        evidence_required = action.get("evidence_required", [])
        lines.extend(
            [
                f"### `{diagnostic.rule}` on `{diagnostic.target_node_id or diagnostic.target_edge_id}`",
                "",
                f"- route: `{action.get('verification_route')}`",
                f"- question: {action.get('verification_question')}",
                f"- targets: {format_list(targets)}",
                f"- conditional_targets: {format_conditional_targets(conditional_targets)}",
                f"- evidence_required: {format_list(evidence_required)}",
            ]
        )
        lines.extend(format_recursive_verification(action.get("recursive_verification")))
        lines.append("")
    return lines


def format_list(value: object) -> str:
    """Format a JSON list as Markdown text."""
    if isinstance(value, list) and value:
        return ", ".join(f"`{item}`" for item in cast(list[object], value))
    return "`not_recorded`"


def format_conditional_targets(value: object) -> str:
    """Format conditional target payloads as Markdown text."""
    if not isinstance(value, list) or not value:
        return "`not_recorded`"
    parts: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, dict):
            payload = cast(dict[str, object], item)
            target = payload.get("target", "unknown")
            condition = payload.get("when", "unspecified")
            parts.append(f"`{target}` when {condition}")
    return "; ".join(parts) if parts else "`not_recorded`"


def format_recursive_verification(value: object) -> list[str]:
    """Format recursive verification payload as Markdown lines."""
    if not isinstance(value, dict):
        return ["- recursive_verification: `not_recorded`"]
    payload = cast(dict[str, object], value)
    lines = [
        f"- recursive_max_depth: `{payload.get('max_depth', 'not_recorded')}`",
        f"- closure_condition: {payload.get('closure_condition', 'not_recorded')}",
        f"- unresolved_leaf_policy: {payload.get('unresolved_leaf_policy', 'not_recorded')}",
        "- recursive_steps:",
    ]
    steps = payload.get("steps", [])
    if not isinstance(steps, list) or not steps:
        lines.append("  - `not_recorded`")
        return lines
    for item in cast(list[object], steps):
        if not isinstance(item, dict):
            continue
        step = cast(dict[str, object], item)
        lines.append(
            "  - "
            f"`{step.get('id', 'step')}` route=`{step.get('route', 'not_recorded')}` "
            f"question={step.get('question', 'not_recorded')} "
            f"if_unresolved={step.get('if_unresolved', 'not_recorded')}"
        )
    return lines


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
    if not table_exists(connection, "edit_operations"):
        raise ValueError("graph DB has no edit_operations table; run analyze on an ingest DB before rewrite-packet")
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


def command_check_document(args: argparse.Namespace) -> int:
    """Run prose and document-canon checks through one bounded tool path."""
    input_path = cast(Path, args.input)
    db_path = graph_db_path(args, [input_path])
    out_dir = cast(Path, args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    repo_root = structured_repo_root(args, input_path)
    inventory_json = structured_inventory_path(args, repo_root)
    prompt_text = prompt_context(args)
    source_text = input_path.read_text(encoding="utf-8")
    local_llm_ir = local_llm_prose_ir_payload(args, [input_path], prompt_text, db_path)
    corpus_hints = corpus_hints_from_local_llm_ir(local_llm_ir)

    diagnostics_path = out_dir / "prose_diagnostics.md"
    explanation_path = out_dir / "prose_explanation.md"
    integration_path = out_dir / "prose_integration.md"
    handoff_path = out_dir / "prose_handoff.md"
    report_path = out_dir / "document_check.md"

    with connect(db_path) as connection:
        initialize_schema(connection)
        clear_database(connection)
        set_metadata(connection, "local_llm_prose_ir", local_llm_ir)
        set_metadata(connection, "corpus_hints", corpus_hints)
        set_metadata(
            connection,
            "corpus_hint_inputs",
            {
                "source": "local_llm_prose_ir",
                "document_path": str(input_path),
                "prompt_supplied": bool(prompt_text.strip()),
                "ir_schema": local_llm_ir.get("schema", ""),
            },
        )
        ingest_document(
            connection,
            input_path,
            source_text,
            document_id="doc:1",
            source_node_id="src:1",
            kind=cast(str, args.kind),
        )
        clear_analysis(connection)
        analyze_graph(connection, cast(str, args.profile))
        document_canon_findings = import_target_document_canon_findings(
            connection,
            inventory_json,
            repo_root,
            input_path,
        )
        diagnostics = fetch_diagnostics(connection)
        operations = fetch_operations(connection)
        prose_diagnostics = tuple(item for item in diagnostics if item.layer != "document-canon")
        write_output(diagnostics_path, render_diagnostics(connection, cast(str, args.profile)))
        write_output(explanation_path, render_explanation(connection, cast(str, args.profile), db_path))
        write_output(integration_path, render_integration_plan(connection, cast(str, args.profile)))

    write_output(handoff_path, render_skill_handoff(cast(str, args.profile), db_path))
    write_output(
        report_path,
        render_document_check_report(
            input_path,
            repo_root,
            db_path,
            cast(str, args.profile),
            inventory_json,
            diagnostics_path,
            explanation_path,
            integration_path,
            handoff_path,
            len(prose_diagnostics),
            len(operations),
            document_canon_findings,
        ),
    )
    emit_command_stats(
        args,
        "PROSE_REASONING_GRAPH_CHECK_DOCUMENT",
        {
            "PROSE_REASONING_GRAPH_DB": str(db_path),
            "PROSE_REASONING_GRAPH_DOCUMENT_CHECK": str(report_path),
            "PROSE_REASONING_GRAPH_DIAGNOSTICS": str(diagnostics_path),
            "PROSE_REASONING_GRAPH_EXPLANATION": str(explanation_path),
            "PROSE_REASONING_GRAPH_INTEGRATION_PLAN": str(integration_path),
            "PROSE_REASONING_GRAPH_SKILL_HANDOFF": str(handoff_path),
            "PROSE_REASONING_GRAPH_STRUCTURED_ANALYSIS_INVENTORY": str(inventory_json),
            "PROSE_REASONING_GRAPH_LOCAL_LLM_IR": str(local_llm_ir.get("artifact_path", "")),
            "PROSE_REASONING_GRAPH_PROSE_DIAGNOSTICS": len(prose_diagnostics),
            "PROSE_REASONING_GRAPH_EDIT_OPERATIONS": len(operations),
            "PROSE_REASONING_GRAPH_DOCUMENT_CANON_FINDINGS": len(document_canon_findings),
        },
    )
    return 0


def render_skill_handoff(profile: str, db_path: Path) -> str:
    """Render skill handoff Markdown."""
    handoffs = skill_handoffs(profile, db_path)
    with connect(db_path) as connection:
        diagnostics = fetch_diagnostics(connection)
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
                f"- projection_fields: `{', '.join(cast(list[str], item['projection_fields']))}`",
                "",
            ]
        )
    lines.extend(render_verification_routes(diagnostics))
    lines.extend(
        [
            "## Authority Boundary",
            "",
            "This handoff gives graph-derived evidence to existing skills and reviewers. It does not replace their review gates or source-packet responsibilities.",
            "",
        ]
    )
    return "\n".join(lines)


def structured_repo_root(args: argparse.Namespace, input_path: Path) -> Path:
    """Return the structured-analysis root for a document check."""
    explicit_root = getattr(args, "repo_root", None)
    if isinstance(explicit_root, Path):
        return explicit_root.resolve()
    resolved = input_path.resolve()
    parts = resolved.parts
    for index in range(len(parts) - 1):
        if parts[index] == "vendor" and parts[index + 1] == "agent-canon":
            return Path(*parts[: index + 2]).resolve()
    return Path.cwd().resolve()


def structured_inventory_path(args: argparse.Namespace, repo_root: Path) -> Path:
    """Return a structured-analysis inventory path, running Rust build when needed."""
    explicit_inventory = getattr(args, "structured_inventory_json", None)
    if isinstance(explicit_inventory, Path):
        if not explicit_inventory.is_file():
            raise ValueError(f"structured inventory JSON does not exist: {explicit_inventory}")
        return explicit_inventory
    return run_structured_analysis_build(repo_root, cast(str, args.structured_profile))


def run_structured_analysis_build(repo_root: Path, profile: str) -> Path:
    """Run Rust structured-analysis build and return the emitted inventory JSON."""
    cli = structured_analysis_cli(repo_root)
    result = subprocess.run(
        [str(cli), "structured-analysis", "build", "--root", str(repo_root), "--profile", profile],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(
            "structured-analysis build failed: "
            f"exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    inventory_text = stdout_field(result.stdout, STRUCTURED_ANALYSIS_INVENTORY_STDOUT_KEY)
    if not inventory_text:
        raise ValueError(f"structured-analysis build did not emit {STRUCTURED_ANALYSIS_INVENTORY_STDOUT_KEY}")
    inventory_path = Path(inventory_text)
    if not inventory_path.is_file():
        raise ValueError(f"structured-analysis inventory JSON was not created: {inventory_path}")
    return inventory_path


def structured_analysis_cli(repo_root: Path) -> Path | str:
    """Return the preferred local Rust CLI entrypoint."""
    local_cli = repo_root / "tools" / "bin" / "agent-canon"
    if local_cli.is_file():
        return local_cli
    parent_cli = Path.cwd() / "vendor" / "agent-canon" / "tools" / "bin" / "agent-canon"
    if parent_cli.is_file():
        return parent_cli
    return "agent-canon"


def stdout_field(stdout: str, key: str) -> str:
    """Return one KEY=value field from stdout."""
    prefix = f"{key}="
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return ""


def import_target_document_canon_findings(
    connection: sqlite3.Connection,
    inventory_json: Path,
    repo_root: Path,
    input_path: Path,
) -> list[dict[str, object]]:
    """Import target-related document-canon findings into the current graph DB."""
    payload = read_json_file(inventory_json)
    documents = object_list(payload.get("documents"))
    findings = object_list(payload.get("findings"))
    candidates = target_path_candidates(input_path, repo_root)
    target_findings = [finding for finding in findings if finding_matches_target(finding, candidates)]
    connection.execute("DELETE FROM diagnostics WHERE layer = 'document-canon'")
    connection.execute("DELETE FROM edges WHERE layer = 'document-canon'")
    connection.execute("DELETE FROM nodes WHERE layer = 'document-canon'")

    document_id = fetch_document_id(connection)
    relevant_paths = relevant_document_paths(target_findings, documents, candidates)
    path_to_node: dict[str, str] = {}
    for index, record in enumerate(relevant_document_records(documents, relevant_paths), start=1):
        path = string_value(record.get("path"))
        title = string_value(record.get("title")) or path
        responsibility = string_value(record.get("responsibility")) or path
        node_id = f"doccanon:document:{index}"
        insert_node(
            connection,
            node_id,
            document_id,
            "document-canon",
            "document_record",
            title,
            responsibility,
            0,
            0,
            payload={
                "path": path,
                "title": title,
                "responsibility": responsibility,
                "has_dependency_manifest": bool(record.get("has_dependency_manifest")),
                "inventory_path": str(inventory_json),
            },
        )
        path_to_node[path] = node_id

    for index, finding in enumerate(target_findings, start=1):
        path = string_value(finding.get("path"))
        kind = string_value(finding.get("kind"))
        canonical_path = string_value(finding.get("canonical_path"))
        action = string_value(finding.get("action"))
        reason = string_value(finding.get("reason"))
        node_id = f"doccanon:finding:{index}"
        message = f"{kind}: `{path}` -> `{canonical_path}`. {reason}"
        insert_node(
            connection,
            node_id,
            document_id,
            "document-canon",
            "finding",
            kind,
            message,
            0,
            0,
            confidence=0.8,
            payload={
                "path": path,
                "kind": kind,
                "canonical_path": canonical_path,
                "action": action,
                "reason": reason,
                "inventory_path": str(inventory_json),
            },
        )
        if path in path_to_node:
            insert_edge(
                connection,
                f"doccanon:target:{index}",
                "document-canon",
                "targets_document",
                node_id,
                path_to_node[path],
                payload={"path": path},
            )
        if canonical_path in path_to_node:
            insert_edge(
                connection,
                f"doccanon:canonical:{index}",
                "document-canon",
                "references_canonical",
                node_id,
                path_to_node[canonical_path],
                payload={"canonical_path": canonical_path},
            )
        insert_diagnostic(
            connection,
            f"diag:document-canon:{index}",
            "document-canon",
            node_id,
            document_canon_severity(kind),
            kind,
            message,
            action=document_canon_action(kind, action, path, canonical_path, reason),
        )

    set_metadata(
        connection,
        "document_canon_inventory",
        {
            "inventory_path": str(inventory_json),
            "repo_root": str(repo_root),
            "target_candidates": sorted(candidates),
            "document_count": len(relevant_paths),
            "finding_count": len(target_findings),
        },
    )
    return target_findings


def read_json_file(path: Path) -> dict[str, object]:
    """Read a JSON object from disk."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return cast(dict[str, object], raw)


def object_list(value: object) -> list[dict[str, object]]:
    """Return a list containing only dictionary items."""
    if not isinstance(value, list):
        return []
    return [cast(dict[str, object], item) for item in cast(list[object], value) if isinstance(item, dict)]


def target_path_candidates(input_path: Path, repo_root: Path) -> set[str]:
    """Return inventory path spellings that may identify the input document."""
    candidates = {input_path.as_posix(), input_path.name}
    try:
        resolved_input = input_path.resolve()
        candidates.add(resolved_input.as_posix())
        candidates.add(resolved_input.relative_to(repo_root.resolve()).as_posix())
    except (OSError, ValueError):
        pass
    cwd = Path.cwd().resolve()
    try:
        candidates.add(input_path.resolve().relative_to(cwd).as_posix())
    except (OSError, ValueError):
        pass
    return {candidate for candidate in candidates if candidate}


def finding_matches_target(finding: dict[str, object], candidates: set[str]) -> bool:
    """Return true when a finding is relevant to the checked document."""
    path = string_value(finding.get("path"))
    canonical_path = string_value(finding.get("canonical_path"))
    return path in candidates or canonical_path in candidates


def relevant_document_paths(
    findings: Sequence[dict[str, object]],
    documents: Sequence[dict[str, object]],
    candidates: set[str],
) -> set[str]:
    """Return document paths needed for imported target findings."""
    paths = {
        string_value(finding.get("path"))
        for finding in findings
        if string_value(finding.get("path"))
    }
    paths.update(
        string_value(finding.get("canonical_path"))
        for finding in findings
        if string_value(finding.get("canonical_path"))
    )
    paths.update(
        string_value(record.get("path"))
        for record in documents
        if string_value(record.get("path")) in candidates
    )
    return {path for path in paths if path}


def relevant_document_records(
    documents: Sequence[dict[str, object]],
    paths: set[str],
) -> list[dict[str, object]]:
    """Return document records, creating minimal records for paths absent from inventory."""
    records = [record for record in documents if string_value(record.get("path")) in paths]
    seen = {string_value(record.get("path")) for record in records}
    for path in sorted(paths - seen):
        records.append({"path": path, "title": path, "responsibility": path, "has_dependency_manifest": False})
    return records


def string_value(value: object) -> str:
    """Return a string value from loose JSON input."""
    return value if isinstance(value, str) else ""


def document_canon_severity(kind: str) -> str:
    """Return structured-analysis compatible severity for a document-canon finding kind."""
    if kind in {"missing_dependency_manifest", "broken_dependency_target"}:
        return "blocker"
    if kind in {
        "duplicate_heading_candidate",
        "stale_name_candidate",
        "missing_reverse_edge",
        "document_responsibility_gap",
    }:
        return "warn"
    return "info"


def document_canon_action(kind: str, action: str, path: str, canonical_path: str, reason: str) -> dict[str, object]:
    """Return suggested-action payload for imported document-canon diagnostics."""
    if kind == "document_responsibility_gap":
        return {
            "action": action,
            "path": path,
            "canonical_path": canonical_path,
            "reason": reason,
            "verification_route": "document_responsibility_verification",
            "verification_question": "Does the downstream document cover the upstream design responsibility declared by its dependency manifest?",
            "verification_targets": [path, canonical_path],
            "evidence_required": [
                "upstream coverage rule",
                "downstream document wording",
                "dependency header edge",
            ],
            "recursive_verification": {
                "max_depth": VERIFICATION_RECURSION_MAX_DEPTH,
                "closure_condition": "every declared coverage group is covered, explicitly out of scope, or recorded as an unresolved document-canon finding",
                "unresolved_leaf_policy": "keep document_responsibility_gap active and route the leaf to the owning document",
                "steps": [
                    {
                        "id": "expand_coverage_rule",
                        "route": "document-canon",
                        "question": "Which upstream coverage groups are missing from the downstream document?",
                        "if_unresolved": "preserve the responsibility gap finding",
                    },
                    {
                        "id": "trace_downstream_claim",
                        "route": "prose-reasoning-graph",
                        "question": "Which downstream paragraph, sentence, or graph node should carry the missing responsibility?",
                        "if_unresolved": "create a child document-canon finding for the target document",
                    },
                    {
                        "id": "verify_rewritten_contract",
                        "route": "structured-analysis",
                        "question": "Does rerunning structured-analysis close the coverage gap without introducing a new graph or document responsibility gap?",
                        "if_unresolved": "record the remaining gap as blocker or warn",
                    },
                ],
            },
        }
    return {"action": action, "path": path, "canonical_path": canonical_path, "reason": reason}


def render_document_check_report(
    input_path: Path,
    repo_root: Path,
    db_path: Path,
    profile: str,
    inventory_json: Path,
    diagnostics_path: Path,
    explanation_path: Path,
    integration_path: Path,
    handoff_path: Path,
    prose_diagnostic_count: int,
    operation_count: int,
    document_canon_findings: Sequence[dict[str, object]],
) -> str:
    """Render a bounded report for the integrated document check."""
    lines = [
        "# Prose Reasoning Graph Document Check",
        "",
        f"- target: `{input_path}`",
        f"- structured_root: `{repo_root}`",
        f"- profile: `{profile}`",
        f"- prose_graph_db: `{db_path}`",
        f"- structured_inventory: `{inventory_json}`",
        f"- prose diagnostics: `{prose_diagnostic_count}`",
        f"- edit operations: `{operation_count}`",
        f"- document-canon findings: `{len(document_canon_findings)}`",
        "",
        "## Tool Path",
        "",
        "This command runs the prose graph path and the Rust structured-analysis document-canon path for the same target before writing result artifacts.",
        "",
        "## Artifacts",
        "",
        f"- diagnostics: `{diagnostics_path}`",
        f"- explanation: `{explanation_path}`",
        f"- integration plan: `{integration_path}`",
        f"- skill handoff: `{handoff_path}`",
        "",
        "## Document-Canon Findings",
        "",
    ]
    if not document_canon_findings:
        lines.append("No target document-canon findings were recorded.")
    else:
        for finding in document_canon_findings:
            lines.append(
                "- "
                f"`{string_value(finding.get('kind'))}` "
                f"path=`{string_value(finding.get('path'))}` "
                f"canonical=`{string_value(finding.get('canonical_path'))}` "
                f"action=`{string_value(finding.get('action'))}`: "
                f"{string_value(finding.get('reason'))}"
            )
    lines.extend(
        [
            "",
            "## Next Route",
            "",
            "Use the diagnostics and integration artifacts first. If a diagnostic carries a verification route, verify and rerun this command before writing settled prose.",
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
        if args.command == "ingest-set":
            return command_ingest_set(args)
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
        if args.command == "check-document":
            return command_check_document(args)
    except ValueError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
