"""Tests for Codex runtime summary export."""

# @dependency-start
# contract test
# responsibility Tests Codex runtime summary export into the AgentCanon log archive.
# upstream implementation ../../tools/agent_tools/export_codex_runtime_summary.py exports bounded Codex runtime summaries
# upstream implementation ../../tools/agent_tools/runtime_log_paths.py resolves codex-runtime archive paths
# upstream design ../../documents/runtime-log-archive.md documents runtime log archive ownership
# @dependency-end

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "export_codex_runtime_summary.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from runtime_log_paths import (  # noqa: E402
    codex_runtime_index_path,
    codex_runtime_summary_path,
    mounted_log_archive_root,
    repo_log_key,
)


class ExportCodexRuntimeSummaryTest(unittest.TestCase):
    """Validate bounded Codex runtime summary export."""

    def test_exports_idempotent_summary_without_prompt_text(self) -> None:
        """Exporter should write one bounded JSONL summary per unique observation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            mounted_log_archive_root(canon).mkdir(parents=True)
            thread_id = "019e64a8-041d-7080-a5d6-09fa11cc0435"
            history = root / "history.jsonl"
            sqlite_log = root / "logs_2.sqlite"
            write_history(history, thread_id)
            write_sqlite(sqlite_log, thread_id)

            first = run_exporter(
                source=source,
                canon=canon,
                history=history,
                sqlite_log=sqlite_log,
                thread_id=thread_id,
            )
            second = run_exporter(
                source=source,
                canon=canon,
                history=history,
                sqlite_log=sqlite_log,
                thread_id=thread_id,
            )

            output = codex_runtime_summary_path(source, canon, thread_id)
            records = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            index = [
                json.loads(line)
                for line in codex_runtime_index_path(source, canon).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("CODEX_RUNTIME_SUMMARY_STATUS=appended", first.stdout)
        self.assertIn("CODEX_RUNTIME_SUMMARY_INDEX_STATUS=appended", first.stdout)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("CODEX_RUNTIME_SUMMARY_STATUS=already-present", second.stdout)
        self.assertIn("CODEX_RUNTIME_SUMMARY_INDEX_STATUS=already-present", second.stdout)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(index), 1)
        record = records[0]
        self.assertEqual(record["schema"], "codex-runtime-summary.v1")
        self.assertEqual(record["conversation_id"], thread_id)
        self.assertEqual(record["session_id"], thread_id)
        self.assertEqual(record["thread_id"], thread_id)
        self.assertEqual(record["source_repo_key"], repo_log_key(source))
        self.assertEqual(record["agent_canon_git_head"], "")
        self.assertEqual(record["history"]["entry_count"], 1)
        self.assertEqual(record["sqlite"]["row_count"], 3)
        self.assertEqual(record["tokens"]["live_turn_count"], 1)
        self.assertEqual(record["tokens"]["live_total_usage_tokens"], 123456)
        self.assertEqual(record["tokens"]["latest_estimated_token_count"], 110000)
        self.assertEqual(record["runtime"]["tool_call_counts"]["exec_command"], 1)
        self.assertNotIn("secret prompt text", json.dumps(record, sort_keys=True))
        self.assertEqual(index[0]["schema"], "codex-runtime-summary-index.v1")
        self.assertEqual(index[0]["conversation_id"], thread_id)
        self.assertEqual(index[0]["session_id"], thread_id)
        self.assertEqual(index[0]["summary_path"], f"chats/{thread_id}/summary-no-git-head.jsonl")

    def test_all_threads_exports_discovered_history_and_sqlite_threads(self) -> None:
        """Bulk rescue should export every bounded thread discovered in runtime logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            mounted_log_archive_root(canon).mkdir(parents=True)
            history_thread = "019e64a8-041d-7080-a5d6-09fa11cc0001"
            sqlite_thread = "019e64a8-041d-7080-a5d6-09fa11cc0002"
            history = root / "history.jsonl"
            sqlite_log = root / "logs_2.sqlite"
            write_history(history, history_thread)
            write_sqlite(sqlite_log, sqlite_thread)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(source),
                    "--canon-root",
                    str(canon),
                    "--all-threads",
                    "--history-jsonl",
                    str(history),
                    "--sqlite-log",
                    str(sqlite_log),
                    "--recent-days",
                    "5",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            output_dir = codex_runtime_index_path(source, canon).parent / "chats"
            exported = sorted(path.name for path in output_dir.iterdir() if path.is_dir())
            index_records = [
                json.loads(line)
                for line in codex_runtime_index_path(source, canon).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CODEX_RUNTIME_SUMMARY_THREADS=2", result.stdout)
        self.assertEqual(exported, [history_thread, sqlite_thread])
        self.assertEqual(len(index_records), 2)

    def test_missing_thread_id_skips_without_writing(self) -> None:
        """Hook callers can run exporter safely before CODEX_THREAD_ID exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(source),
                    "--canon-root",
                    str(canon),
                    "--thread-id",
                    "",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CODEX_RUNTIME_SUMMARY=skip", result.stdout)


def run_exporter(
    *,
    source: Path,
    canon: Path,
    history: Path,
    sqlite_log: Path,
    thread_id: str,
) -> subprocess.CompletedProcess[str]:
    """Run the exporter against test fixtures."""
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-root",
            str(source),
            "--canon-root",
            str(canon),
            "--thread-id",
            thread_id,
            "--history-jsonl",
            str(history),
            "--sqlite-log",
            str(sqlite_log),
            "--recent-days",
            "5",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def write_history(path: Path, thread_id: str) -> None:
    """Write minimal Codex history without exporting prompt text."""
    path.write_text(
        json.dumps(
            {
                "session_id": thread_id,
                "ts": int(time.time()),
                "text": "secret prompt text",
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def write_sqlite(path: Path, thread_id: str) -> None:
    """Write a minimal Codex logs_2.sqlite fixture."""
    now = int(time.time())
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY,
                ts INTEGER NOT NULL,
                ts_nanos INTEGER NOT NULL,
                level TEXT NOT NULL,
                target TEXT NOT NULL,
                feedback_log_body TEXT,
                module_path TEXT,
                file TEXT,
                line INTEGER,
                thread_id TEXT,
                process_uuid TEXT,
                estimated_bytes INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        rows = [
            (
                "INFO",
                "codex_core::session::turn",
                "post sampling token usage turn_id=turn-a "
                "total_usage_tokens=123456 estimated_token_count=110000 "
                "token_limit_reached=false model=gpt-5.5 "
                "codex.turn.reasoning_effort=xhigh",
                1200,
            ),
            (
                "INFO",
                "codex_core::stream_events_utils",
                "ToolCall: exec_command {'cmd': 'true'} turn.id=turn-a model=gpt-5.5",
                100,
            ),
            (
                "TRACE",
                "codex_api::endpoint::responses_websocket",
                "model=gpt-5.5 codex.turn.reasoning_effort=xhigh",
                50,
            ),
        ]
        for level, target, body, estimated_bytes in rows:
            connection.execute(
                """
                INSERT INTO logs (
                    ts, ts_nanos, level, target, feedback_log_body, thread_id, estimated_bytes
                ) VALUES (?, 0, ?, ?, ?, ?, ?)
                """,
                (now, level, target, body, thread_id, estimated_bytes),
            )


if __name__ == "__main__":
    unittest.main()
