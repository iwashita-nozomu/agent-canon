#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Exports bounded Codex runtime summaries from local Codex raw logs to the AgentCanon log archive.
# upstream design ../../documents/runtime-log-archive.md runtime log archive ownership and mount policy
# upstream implementation ./runtime_log_paths.py resolves codex-runtime archive paths
# downstream implementation ../../.codex/hooks/codex_runtime_summary_logger.py calls this exporter from Stop hooks
# downstream implementation ../../tests/agent_tools/test_export_codex_runtime_summary.py validates summary extraction
# @dependency-end
"""Export bounded Codex runtime summaries into the AgentCanon log archive."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtime_log_paths import (  # noqa: E402
    agent_canon_root,
    codex_runtime_index_path,
    codex_runtime_summary_path,
    repo_log_key,
    source_git_head,
)

POST_SAMPLING_RE = re.compile(r"turn_id=(?P<turn_id>\S+).*?total_usage_tokens=(?P<total>\d+)")
ESTIMATED_TOKEN_RE = re.compile(r"estimated_token_count=(?:Some\()?(?P<estimated>\d+)\)?")
TOKEN_LIMIT_RE = re.compile(r"token_limit_reached=(?P<limit>\w+)")
TURN_ID_RE = re.compile(r"turn\.id=(?P<turn_id>[0-9a-f-]+)")
MODEL_RE = re.compile(r"\bmodel=(?P<model>[A-Za-z0-9._-]+)")
REASONING_RE = re.compile(r"codex\.turn\.reasoning_effort=(?P<effort>[A-Za-z0-9._-]+)")
TOOL_CALL_RE = re.compile(r"ToolCall:\s*(?P<tool>[A-Za-z0-9_.-]+)")
SESSION_THREAD_ID_RE = re.compile(
    r"(?P<thread_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)
DEFAULT_RECENT_DAYS = 5
MAX_COUNTER_ITEMS = 20
MAX_TURN_ITEMS = 40
HOURS_PER_DAY = 24
MINUTES_PER_HOUR = 60
SECONDS_PER_MINUTE = 60
SUMMARY_ID_DIGEST_LENGTH = 16
INDEX_SCHEMA = "codex-runtime-summary-index.v1"


@dataclass(frozen=True)
class HistorySummary:
    """Prompt-history counters for one Codex thread."""

    entry_count: int
    first_ts: int | None
    last_ts: int | None


@dataclass(frozen=True)
class TokenTurn:
    """One per-turn token observation from Codex SQLite logs."""

    turn_id: str
    timestamp: int
    total_usage_tokens: int
    estimated_token_count: int | None
    token_limit_reached: bool | None


@dataclass(frozen=True)
class SqliteSummary:
    """Bounded runtime counters from Codex SQLite logs."""

    row_count: int
    estimated_bytes: int
    first_ts: int | None
    last_ts: int | None
    post_sampling_rows: int
    token_turns: tuple[TokenTurn, ...]
    targets: Counter[str]
    levels: Counter[str]
    tools: Counter[str]
    models: Counter[str]
    reasoning_efforts: Counter[str]


@dataclass(frozen=True)
class SessionSummary:
    """Token counters from legacy Codex session JSONL files."""

    file_count: int
    token_event_count: int
    total_tokens: int


def utc_now() -> str:
    """Return current UTC timestamp."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def epoch_to_utc(value: int | None) -> str | None:
    """Return ISO UTC timestamp for an epoch second."""
    if value is None:
        return None
    return datetime.fromtimestamp(value, UTC).isoformat().replace("+00:00", "Z")


def recent_cutoff(recent_days: int | None) -> int | None:
    """Return epoch cutoff for a recent-day window."""
    if recent_days is None:
        return None
    return (
        int(time.time())
        - max(0, recent_days) * HOURS_PER_DAY * MINUTES_PER_HOUR * SECONDS_PER_MINUTE
    )


def inside_cutoff(timestamp: int, cutoff: int | None) -> bool:
    """Return whether an epoch timestamp is inside the requested window."""
    return cutoff is None or timestamp >= cutoff


def compact_counter(counter: Counter[str]) -> dict[str, int]:
    """Return a bounded counter as a plain dict."""
    return dict(counter.most_common(MAX_COUNTER_ITEMS))


def default_codex_home() -> Path:
    """Return the local Codex state directory."""
    override = os.environ.get("CODEX_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    home = os.environ.get("HOME", "").strip()
    return Path(home).expanduser() / ".codex" if home else Path(".codex")


def default_history_path() -> Path:
    """Return the default Codex prompt history path."""
    return default_codex_home() / "history.jsonl"


def default_sqlite_path() -> Path:
    """Return the default Codex SQLite runtime log path."""
    return default_codex_home() / "logs_2.sqlite"


def read_history(path: Path, thread_id: str, cutoff: int | None) -> HistorySummary:
    """Return prompt-history counters for one thread."""
    if not path.is_file():
        return HistorySummary(0, None, None)
    entry_count = 0
    first_ts: int | None = None
    last_ts: int | None = None
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                loaded = cast(object, json.loads(line))
            except json.JSONDecodeError:
                continue
            record = cast(dict[str, object], loaded) if isinstance(loaded, dict) else {}
            if record.get("session_id") != thread_id:
                continue
            timestamp = record.get("ts")
            if not isinstance(timestamp, int) or not inside_cutoff(timestamp, cutoff):
                continue
            entry_count += 1
            first_ts = timestamp if first_ts is None else min(first_ts, timestamp)
            last_ts = timestamp if last_ts is None else max(last_ts, timestamp)
    return HistorySummary(entry_count, first_ts, last_ts)


def read_history_thread_ids(path: Path, cutoff: int | None) -> set[str]:
    """Return thread ids present in Codex prompt history."""
    if not path.is_file():
        return set()
    thread_ids: set[str] = set()
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                loaded = cast(object, json.loads(line))
            except json.JSONDecodeError:
                continue
            record = cast(dict[str, object], loaded) if isinstance(loaded, dict) else {}
            thread_id = record.get("session_id")
            timestamp = record.get("ts")
            if (
                isinstance(thread_id, str)
                and thread_id
                and isinstance(timestamp, int)
                and inside_cutoff(timestamp, cutoff)
            ):
                thread_ids.add(thread_id)
    return thread_ids


def update_token_turn(
    turns: dict[str, TokenTurn],
    *,
    body: str,
    timestamp: int,
    match: re.Match[str],
) -> None:
    """Keep the largest token observation for one turn."""
    turn_id = match.group("turn_id")
    total = int(match.group("total"))
    estimated_match = ESTIMATED_TOKEN_RE.search(body)
    limit_match = TOKEN_LIMIT_RE.search(body)
    estimated_text = estimated_match.group("estimated") if estimated_match else None
    limit_text = limit_match.group("limit") if limit_match else None
    token_limit_reached = (
        None if limit_text is None else limit_text.casefold() == "true"
    )
    candidate = TokenTurn(
        turn_id=turn_id,
        timestamp=timestamp,
        total_usage_tokens=total,
        estimated_token_count=int(estimated_text) if estimated_text else None,
        token_limit_reached=token_limit_reached,
    )
    existing = turns.get(turn_id)
    if existing is None or candidate.total_usage_tokens >= existing.total_usage_tokens:
        turns[turn_id] = candidate


def read_sqlite(path: Path, thread_id: str, cutoff: int | None) -> SqliteSummary:
    """Return bounded runtime counters from Codex SQLite logs."""
    if not path.is_file():
        return SqliteSummary(
            row_count=0,
            estimated_bytes=0,
            first_ts=None,
            last_ts=None,
            post_sampling_rows=0,
            token_turns=(),
            targets=Counter(),
            levels=Counter(),
            tools=Counter(),
            models=Counter(),
            reasoning_efforts=Counter(),
        )
    row_count = 0
    estimated_bytes = 0
    first_ts: int | None = None
    last_ts: int | None = None
    post_sampling_rows = 0
    turns: dict[str, TokenTurn] = {}
    targets: Counter[str] = Counter()
    levels: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    models: Counter[str] = Counter()
    reasoning_efforts: Counter[str] = Counter()
    uri = f"file:{path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=1.0) as connection:
        for row in connection.execute(
            "SELECT ts, level, target, feedback_log_body, estimated_bytes "
            "FROM logs WHERE thread_id=?",
            (thread_id,),
        ):
            timestamp, level, target, body, raw_estimated_bytes = row
            if not isinstance(timestamp, int) or not inside_cutoff(timestamp, cutoff):
                continue
            row_count += 1
            first_ts = timestamp if first_ts is None else min(first_ts, timestamp)
            last_ts = timestamp if last_ts is None else max(last_ts, timestamp)
            if isinstance(raw_estimated_bytes, int):
                estimated_bytes += raw_estimated_bytes
            if isinstance(level, str) and level:
                levels[level] += 1
            if isinstance(target, str) and target:
                targets[target] += 1
            if not isinstance(body, str):
                continue
            for match in TOOL_CALL_RE.finditer(body):
                tools[match.group("tool")] += 1
            for match in MODEL_RE.finditer(body):
                models[match.group("model")] += 1
            for match in REASONING_RE.finditer(body):
                reasoning_efforts[match.group("effort")] += 1
            if "post sampling token usage" not in body:
                continue
            post_sampling_rows += 1
            match = POST_SAMPLING_RE.search(body)
            if match is not None:
                update_token_turn(turns, body=body, timestamp=timestamp, match=match)
            elif (turn_match := TURN_ID_RE.search(body)) is not None:
                tools[f"post_sampling_unparsed:{turn_match.group('turn_id')}"] += 1
    return SqliteSummary(
        row_count=row_count,
        estimated_bytes=estimated_bytes,
        first_ts=first_ts,
        last_ts=last_ts,
        post_sampling_rows=post_sampling_rows,
        token_turns=tuple(
            sorted(
                turns.values(),
                key=lambda item: (item.timestamp, item.turn_id),
            )[-MAX_TURN_ITEMS:]
        ),
        targets=targets,
        levels=levels,
        tools=tools,
        models=models,
        reasoning_efforts=reasoning_efforts,
    )


def read_sqlite_thread_ids(path: Path, cutoff: int | None) -> set[str]:
    """Return thread ids present in Codex SQLite logs."""
    if not path.is_file():
        return set()
    query = "SELECT DISTINCT thread_id FROM logs WHERE thread_id IS NOT NULL AND thread_id != ''"
    params: tuple[int, ...] = ()
    if cutoff is not None:
        query += " AND ts >= ?"
        params = (cutoff,)
    uri = f"file:{path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=1.0) as connection:
        return {
            cast(str, row[0])
            for row in connection.execute(query, params)
            if isinstance(row[0], str) and row[0]
        }


def iter_session_paths(patterns: Iterable[str], cutoff: int | None) -> tuple[Path, ...]:
    """Return legacy Codex session JSONL paths."""
    paths: set[Path] = set()
    for pattern in patterns:
        paths.update(Path(path).expanduser().resolve() for path in glob.glob(pattern, recursive=True))
    return tuple(
        sorted(
            path
            for path in paths
            if path.is_file() and (cutoff is None or int(path.stat().st_mtime) >= cutoff)
        )
    )


def session_thread_id(path: Path) -> str | None:
    """Return the thread id embedded in a legacy session filename."""
    match = SESSION_THREAD_ID_RE.search(path.name)
    return match.group("thread_id") if match else None


def session_paths_by_thread(paths: Iterable[Path]) -> dict[str, tuple[Path, ...]]:
    """Group legacy session JSONL paths by embedded thread id."""
    grouped: dict[str, list[Path]] = {}
    for path in paths:
        thread_id = session_thread_id(path)
        if thread_id is not None:
            grouped.setdefault(thread_id, []).append(path)
    return {thread_id: tuple(sorted(items)) for thread_id, items in grouped.items()}


def discover_thread_ids(
    *,
    history_path: Path,
    sqlite_path: Path,
    session_paths: Iterable[Path],
    cutoff: int | None,
) -> tuple[str, ...]:
    """Return all thread ids discoverable from bounded Codex runtime sources."""
    thread_ids = read_history_thread_ids(history_path, cutoff)
    thread_ids.update(read_sqlite_thread_ids(sqlite_path, cutoff))
    for path in session_paths:
        thread_id = session_thread_id(path)
        if thread_id is not None:
            thread_ids.add(thread_id)
    return tuple(sorted(thread_ids))


def read_sessions(paths: Sequence[Path]) -> SessionSummary:
    """Return token summary from legacy Codex session files."""
    token_event_count = 0
    total_tokens = 0
    file_count = 0
    for path in paths:
        file_events = 0
        last_total = 0
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    loaded = cast(object, json.loads(line))
                except json.JSONDecodeError:
                    continue
                event = cast(dict[str, object], loaded) if isinstance(loaded, dict) else {}
                if event.get("type") != "event_msg":
                    continue
                payload_obj = event.get("payload")
                payload = (
                    cast(dict[str, object], payload_obj) if isinstance(payload_obj, dict) else {}
                )
                if payload.get("type") != "token_count":
                    continue
                info_obj = payload.get("info")
                info = cast(dict[str, object], info_obj) if isinstance(info_obj, dict) else {}
                if not info:
                    continue
                usage_obj = info.get("total_token_usage")
                usage = cast(dict[str, object], usage_obj) if isinstance(usage_obj, dict) else {}
                if not usage:
                    continue
                total = usage.get("total_tokens")
                if isinstance(total, int):
                    file_events += 1
                    last_total = total
        if file_events:
            file_count += 1
            token_event_count += file_events
            total_tokens += last_total
    return SessionSummary(file_count, token_event_count, total_tokens)


def summary_payload(
    *,
    source_root: Path,
    canon_root: Path,
    thread_id: str,
    history_path: Path,
    sqlite_path: Path,
    history: HistorySummary,
    sqlite_summary: SqliteSummary,
    sessions: SessionSummary,
    recent_days: int | None,
) -> dict[str, object]:
    """Return a stable JSON summary payload."""
    token_total = sum(turn.total_usage_tokens for turn in sqlite_summary.token_turns)
    latest_turn = sqlite_summary.token_turns[-1] if sqlite_summary.token_turns else None
    payload: dict[str, object] = {
        "schema": "codex-runtime-summary.v1",
        "recorded_at": utc_now(),
        "source_repo_key": repo_log_key(source_root),
        "source_root": source_root.resolve().as_posix(),
        "canon_root": canon_root.resolve().as_posix(),
        "agent_canon_git_head": source_git_head(canon_root),
        "conversation_id": thread_id,
        "session_id": thread_id,
        "thread_id": thread_id,
        "recent_days": recent_days if recent_days is not None else "all",
        "history": {
            "entry_count": history.entry_count,
            "first_timestamp": epoch_to_utc(history.first_ts),
            "last_timestamp": epoch_to_utc(history.last_ts),
        },
        "sqlite": {
            "row_count": sqlite_summary.row_count,
            "estimated_bytes": sqlite_summary.estimated_bytes,
            "first_timestamp": epoch_to_utc(sqlite_summary.first_ts),
            "last_timestamp": epoch_to_utc(sqlite_summary.last_ts),
            "post_sampling_rows": sqlite_summary.post_sampling_rows,
            "target_counts": compact_counter(sqlite_summary.targets),
            "level_counts": compact_counter(sqlite_summary.levels),
        },
        "tokens": {
            "live_turn_count": len(sqlite_summary.token_turns),
            "live_total_usage_tokens": token_total,
            "latest_turn_id": latest_turn.turn_id if latest_turn else "",
            "latest_total_usage_tokens": latest_turn.total_usage_tokens if latest_turn else 0,
            "latest_estimated_token_count": latest_turn.estimated_token_count if latest_turn else None,
            "legacy_session_count": sessions.file_count,
            "legacy_session_token_events": sessions.token_event_count,
            "legacy_session_total_tokens": sessions.total_tokens,
        },
        "runtime": {
            "model_counts": compact_counter(sqlite_summary.models),
            "reasoning_effort_counts": compact_counter(sqlite_summary.reasoning_efforts),
            "tool_call_counts": compact_counter(sqlite_summary.tools),
        },
        "token_turns": [
            {
                "turn_id": turn.turn_id,
                "timestamp": epoch_to_utc(turn.timestamp),
                "total_usage_tokens": turn.total_usage_tokens,
                "estimated_token_count": turn.estimated_token_count,
                "token_limit_reached": turn.token_limit_reached,
            }
            for turn in sqlite_summary.token_turns
        ],
        "sources": {
            "history_jsonl": history_path.expanduser().as_posix(),
            "sqlite_log": sqlite_path.expanduser().as_posix(),
        },
    }
    payload["summary_id"] = payload_fingerprint(payload)
    return payload


def payload_fingerprint(payload: dict[str, object]) -> str:
    """Return a stable summary id that ignores record write time."""
    stable = {key: value for key, value in payload.items() if key not in {"recorded_at", "summary_id"}}
    text = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:SUMMARY_ID_DIGEST_LENGTH]


def read_existing_summary_ids(path: Path) -> set[str]:
    """Return summary ids already present in one JSONL file."""
    if not path.is_file():
        return set()
    ids: set[str] = set()
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                loaded = cast(object, json.loads(line))
            except json.JSONDecodeError:
                continue
            record = cast(dict[str, object], loaded) if isinstance(loaded, dict) else {}
            if isinstance(record.get("summary_id"), str):
                ids.add(cast(str, record["summary_id"]))
    return ids


def summary_index_payload(
    payload: dict[str, object],
    *,
    summary_path: Path,
    index_path: Path,
) -> dict[str, object]:
    """Return a compact cross-chat index record for one runtime summary."""
    tokens = cast(dict[str, object], payload.get("tokens", {}))
    history = cast(dict[str, object], payload.get("history", {}))
    sqlite_summary = cast(dict[str, object], payload.get("sqlite", {}))
    try:
        relative_summary_path = summary_path.relative_to(index_path.parent).as_posix()
    except ValueError:
        relative_summary_path = summary_path.as_posix()
    return {
        "schema": INDEX_SCHEMA,
        "summary_id": payload["summary_id"],
        "recorded_at": payload["recorded_at"],
        "source_repo_key": payload["source_repo_key"],
        "conversation_id": payload["conversation_id"],
        "session_id": payload["session_id"],
        "thread_id": payload["thread_id"],
        "summary_path": relative_summary_path,
        "history_entry_count": history.get("entry_count", 0),
        "sqlite_row_count": sqlite_summary.get("row_count", 0),
        "live_total_usage_tokens": tokens.get("live_total_usage_tokens", 0),
        "live_turn_count": tokens.get("live_turn_count", 0),
        "latest_turn_id": tokens.get("latest_turn_id", ""),
    }


def write_summary_index(path: Path, record: dict[str, object], *, dry_run: bool = False) -> str:
    """Append one idempotent cross-chat index record."""
    if record["summary_id"] in read_existing_summary_ids(path):
        return "already-present"
    if dry_run:
        return "dry-run"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        json.dump(record, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
    return "appended"


def write_summary(path: Path, payload: dict[str, object], *, dry_run: bool = False) -> str:
    """Append one idempotent JSONL summary and return the write status."""
    if payload["summary_id"] in read_existing_summary_ids(path):
        return "already-present"
    if dry_run:
        return "dry-run"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
    return "appended"


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--canon-root", type=Path)
    parser.add_argument("--thread-id", default=os.environ.get("CODEX_THREAD_ID", ""))
    parser.add_argument("--all-threads", action="store_true")
    parser.add_argument("--history-jsonl", type=Path, default=default_history_path())
    parser.add_argument("--sqlite-log", type=Path, default=default_sqlite_path())
    parser.add_argument("--session-glob", action="append", default=[])
    parser.add_argument("--recent-days", type=int, default=DEFAULT_RECENT_DAYS)
    parser.add_argument("--all-time", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-json", action="store_true")
    return parser


def export_summary(
    *,
    source_root: Path,
    canon_root: Path,
    thread_id: str,
    history_path: Path,
    sqlite_path: Path,
    session_paths: Sequence[Path],
    recent_days: int | None,
    output: Path | None,
    dry_run: bool,
) -> tuple[str, str, Path, Path | None, dict[str, object], HistorySummary, SqliteSummary]:
    """Export one Codex runtime summary and return status evidence."""
    cutoff = recent_cutoff(recent_days)
    history = read_history(history_path.expanduser(), thread_id, cutoff)
    sqlite_summary = read_sqlite(sqlite_path.expanduser(), thread_id, cutoff)
    sessions = read_sessions(session_paths)
    payload = summary_payload(
        source_root=source_root,
        canon_root=canon_root,
        thread_id=thread_id,
        history_path=history_path,
        sqlite_path=sqlite_path,
        history=history,
        sqlite_summary=sqlite_summary,
        sessions=sessions,
        recent_days=recent_days,
    )
    output_path = output or codex_runtime_summary_path(source_root, canon_root, thread_id)
    status = write_summary(output_path, payload, dry_run=dry_run)
    index_path: Path | None = None
    index_status = "skipped-output-override"
    if output is None:
        index_path = codex_runtime_index_path(source_root, canon_root)
        index_status = write_summary_index(
            index_path,
            summary_index_payload(payload, summary_path=output_path, index_path=index_path),
            dry_run=dry_run,
        )
    return status, index_status, output_path, index_path, payload, history, sqlite_summary


def main(argv: Sequence[str] | None = None) -> int:
    """Export one or more Codex runtime summaries."""
    args = build_parser().parse_args(argv)
    source_root = args.source_root.resolve()
    canon_root = (args.canon_root.resolve() if args.canon_root else agent_canon_root(source_root))
    recent_days = None if args.all_time else args.recent_days
    cutoff = recent_cutoff(recent_days)
    history_path = args.history_jsonl.expanduser()
    sqlite_path = args.sqlite_log.expanduser()
    session_paths = iter_session_paths(args.session_glob, cutoff)
    grouped_session_paths = session_paths_by_thread(session_paths)
    if args.all_threads:
        thread_ids = discover_thread_ids(
            history_path=history_path,
            sqlite_path=sqlite_path,
            session_paths=session_paths,
            cutoff=cutoff,
        )
    else:
        thread_id = args.thread_id.strip()
        if not thread_id:
            print("CODEX_RUNTIME_SUMMARY=skip")
            print("CODEX_RUNTIME_SUMMARY_REASON=missing_thread_id")
            return 0
        thread_ids = (thread_id,)
    if not thread_ids:
        print("CODEX_RUNTIME_SUMMARY=skip")
        print("CODEX_RUNTIME_SUMMARY_REASON=no_threads")
        return 0
    if args.output and len(thread_ids) > 1:
        print("CODEX_RUNTIME_SUMMARY=skip")
        print("CODEX_RUNTIME_SUMMARY_REASON=output_requires_single_thread")
        return 2

    statuses: Counter[str] = Counter()
    payloads: list[dict[str, object]] = []
    last_output: Path | None = None
    last_index: Path | None = None
    index_statuses: Counter[str] = Counter()
    total_history_entries = 0
    total_sqlite_rows = 0
    total_live_token_turns = 0
    total_live_tokens = 0
    for thread_id in thread_ids:
        status, index_status, output, index_path, payload, history, sqlite_summary = export_summary(
            source_root=source_root,
            canon_root=canon_root,
            thread_id=thread_id,
            history_path=history_path,
            sqlite_path=sqlite_path,
            session_paths=grouped_session_paths.get(thread_id, ()),
            recent_days=recent_days,
            output=args.output,
            dry_run=args.dry_run,
        )
        statuses[status] += 1
        index_statuses[index_status] += 1
        payloads.append(payload)
        last_output = output
        last_index = index_path or last_index
        total_history_entries += history.entry_count
        total_sqlite_rows += sqlite_summary.row_count
        total_live_token_turns += len(sqlite_summary.token_turns)
        tokens = cast(dict[str, object], payload["tokens"])
        total_live_tokens += cast(int, tokens["live_total_usage_tokens"])

    if args.print_json:
        json_payload: dict[str, object] | list[dict[str, object]]
        json_payload = payloads[0] if len(payloads) == 1 else {"summaries": payloads}
        json.dump(json_payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    print("CODEX_RUNTIME_SUMMARY=pass")
    status_text = (
        next(iter(statuses))
        if len(thread_ids) == 1 and len(statuses) == 1
        else ",".join(f"{key}:{value}" for key, value in sorted(statuses.items()))
    )
    print(f"CODEX_RUNTIME_SUMMARY_STATUS={status_text}")
    print(f"CODEX_RUNTIME_SUMMARY_OUTPUT={last_output or ''}")
    index_status_text = (
        next(iter(index_statuses))
        if len(thread_ids) == 1 and len(index_statuses) == 1
        else ",".join(f"{key}:{value}" for key, value in sorted(index_statuses.items()))
    )
    print(f"CODEX_RUNTIME_SUMMARY_INDEX_STATUS={index_status_text}")
    print(f"CODEX_RUNTIME_SUMMARY_INDEX={last_index or ''}")
    print(f"CODEX_RUNTIME_SUMMARY_THREADS={len(thread_ids)}")
    print(f"CODEX_RUNTIME_SUMMARY_HISTORY_ENTRIES={total_history_entries}")
    print(f"CODEX_RUNTIME_SUMMARY_SQLITE_ROWS={total_sqlite_rows}")
    print(f"CODEX_RUNTIME_SUMMARY_LIVE_TOKEN_TURNS={total_live_token_turns}")
    print(f"CODEX_RUNTIME_SUMMARY_LIVE_TOTAL_TOKENS={total_live_tokens}")
    if len(thread_ids) == 1:
        print(f"CODEX_RUNTIME_SUMMARY_THREAD_ID={thread_ids[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
