"""Tests for Codex runtime summary export."""

# @dependency-start
# contract test
# responsibility Tests Codex runtime summary export into the AgentCanon log archive.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/codex_runtime_summary.rs exports bounded Codex runtime summaries
# upstream implementation ../../tools/runtime/archive/runtime_log_paths.py resolves codex-runtime archive paths
# upstream design ../../documents/runtime/runtime-log-archive.md documents runtime log archive ownership
# upstream reference ../fixtures/codex_runtime_summary/python_golden.json freezes original CLI inputs and complete output
# upstream reference ../fixtures/codex_runtime_summary/python_cli_arguments.json freezes help and argument errors
# @dependency-end

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NATIVE_CLI = (
    os.environ.get("AGENT_CANON_NATIVE_BIN")
    or os.environ.get("AGENT_CANON_CLI")
    or str(PROJECT_ROOT / "tools" / "bin" / "agent-canon")
)
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from tools.runtime.archive.runtime_log_paths import (  # noqa: E402
    codex_runtime_index_path,
    codex_runtime_summary_path,
    mounted_log_archive_root,
    repo_log_key,
)


class ExportCodexRuntimeSummaryTest(unittest.TestCase):
    """Validate bounded Codex runtime summary export."""

    def setUp(self) -> None:
        self._runtime_temp = tempfile.TemporaryDirectory()
        self._previous_runtime = os.environ.get("AGENT_CANON_RUNTIME_ROOT")
        runtime = Path(self._runtime_temp.name) / "runtime"
        runtime.mkdir()
        os.environ["AGENT_CANON_RUNTIME_ROOT"] = str(runtime)

    def tearDown(self) -> None:
        if self._previous_runtime is None:
            os.environ.pop("AGENT_CANON_RUNTIME_ROOT", None)
        else:
            os.environ["AGENT_CANON_RUNTIME_ROOT"] = self._previous_runtime
        self._runtime_temp.cleanup()

    def test_help_and_argument_errors_match_the_original_cli(self) -> None:
        """Match the captured help and argument-error responses."""
        golden = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/codex_runtime_summary/python_cli_arguments.json"
            ).read_text()
        )
        self.assertEqual(golden["source"], "cdf54b674130cd9b058e6848b8fd815b6ea8bfa6")
        environment = os.environ.copy()
        environment["COLUMNS"] = str(golden["columns"])
        for case in golden["cases"]:
            with self.subTest(case=case["name"]):
                result = subprocess.run(
                    [NATIVE_CLI, "export-codex-runtime-summary", *case["argv"]],
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, case["exit"])
                self.assertEqual(result.stdout, case["stdout"])
                self.assertEqual(result.stderr, case["stderr"])

    def test_complete_all_time_output_matches_frozen_python_cli(self) -> None:
        """Compare both real CLI runs and every stored byte with the old producer."""
        golden = json.loads(
            (
                PROJECT_ROOT / "tests/fixtures/codex_runtime_summary/python_golden.json"
            ).read_text()
        )
        self.assertEqual(golden["source"], "cdf54b674130cd9b058e6848b8fd815b6ea8bfa6")
        self.assertEqual(
            golden["script_sha256"],
            "9d32bb15e3143c679ad3bea08297d4992dece34ff75bf9d5c914fb748f46fe8e",
        )
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary)
            source, canon, runtime = (
                case / "project",
                case / "agent-canon",
                case / "runtime",
            )
            source.mkdir()
            canon.mkdir()
            runtime.mkdir()
            for item in golden["input_files"]:
                self.assertIn(item["path"], {"history.jsonl", "logs_2.sqlite"})
                (case / item["path"]).write_bytes(base64.b64decode(item["base64"]))
            environment = os.environ.copy()
            for name in ("AGENT_CANON_HOOK_ARCHIVE_DIR", "AGENT_CANON_LOG_ROOT"):
                environment.pop(name, None)
            environment["AGENT_CANON_RUNTIME_ROOT"] = str(runtime)
            environment["CODEX_HOME"] = str(case / "empty-codex-home")
            command = [
                NATIVE_CLI,
                "export-codex-runtime-summary",
                "--source-root",
                str(source),
                "--canon-root",
                str(canon),
                "--thread-id",
                golden["thread_id"],
                "--history-jsonl",
                str(case / "history.jsonl"),
                "--sqlite-log",
                str(case / "logs_2.sqlite"),
                "--all-time",
                "--session-glob",
                str(case / "no-sessions/*.jsonl"),
            ]
            for old in golden["runs"]:
                result = subprocess.run(
                    command,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, old["exit"], result.stderr)
                self.assertEqual(result.stderr, old["stderr"])
                self.assertEqual(
                    result.stdout,
                    old["stdout"].replace(golden["runtime_root"], str(runtime)),
                )
            expected_files = {
                item["path"]: base64.b64decode(item["base64"])
                for item in golden["files"]
            }
            self.assertEqual(
                {
                    p.relative_to(runtime).as_posix()
                    for p in runtime.rglob("*")
                    if p.is_file()
                },
                set(expected_files),
            )
            old_records = {
                name: json.loads(data)
                for name, data in expected_files.items()
                if name.endswith(".jsonl")
            }

            def relocate(value: object) -> object:
                if isinstance(value, str):
                    return value.replace(golden["case_root"], case.as_posix())
                if isinstance(value, dict):
                    return {key: relocate(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [relocate(item) for item in value]
                return value

            expected_records = {
                name: relocate(record) for name, record in old_records.items()
            }
            summary_name = next(name for name in old_records if "/chats/" in name)
            summary = expected_records[summary_name]
            assert isinstance(summary, dict)
            stable = {
                key: value
                for key, value in summary.items()
                if key not in {"recorded_at", "summary_id"}
            }
            expected_id = hashlib.sha256(
                json.dumps(
                    stable, sort_keys=True, separators=(",", ":"), default=str
                ).encode()
            ).hexdigest()[:16]
            observed_times = []
            for name, old_bytes in expected_files.items():
                actual_bytes = (runtime / name).read_bytes()
                if not name.endswith(".jsonl"):
                    self.assertEqual(actual_bytes, old_bytes)
                    continue
                old_record = old_records[name]
                self.assertEqual(
                    old_bytes, (json.dumps(old_record, sort_keys=True, separators=(",", ":")) + "\n").encode()
                )
                expected = expected_records[name]
                assert isinstance(expected, dict)
                expected["summary_id"] = expected_id
                actual = json.loads(actual_bytes)
                recorded_at = actual["recorded_at"]
                self.assertRegex(
                    recorded_at, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{6})?Z$"
                )
                datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
                observed_times.append(recorded_at)
                self.assertEqual(
                    actual_bytes, (json.dumps(actual, sort_keys=True, separators=(",", ":")) + "\n").encode()
                )
                actual["recorded_at"] = old_record["recorded_at"]
                self.assertEqual(actual, expected)
            self.assertEqual(len(set(observed_times)), 1)

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
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

            output = codex_runtime_summary_path(source, canon, thread_id)
            records = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            index = [
                json.loads(line)
                for line in codex_runtime_index_path(source, canon)
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]

        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("CODEX_RUNTIME_SUMMARY_STATUS=appended", first.stdout)
        self.assertIn("CODEX_RUNTIME_SUMMARY_INDEX_STATUS=appended", first.stdout)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("CODEX_RUNTIME_SUMMARY_STATUS=already-present", second.stdout)
        self.assertIn(
            "CODEX_RUNTIME_SUMMARY_INDEX_STATUS=already-present", second.stdout
        )
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
        self.assertEqual(
            index[0]["summary_path"], f"chats/{thread_id}/summary-no-git-head.jsonl"
        )

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
                    NATIVE_CLI,
                    "export-codex-runtime-summary",
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
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output_dir = codex_runtime_index_path(source, canon).parent / "chats"
            exported = sorted(
                path.name for path in output_dir.iterdir() if path.is_dir()
            )
            index_records = [
                json.loads(line)
                for line in codex_runtime_index_path(source, canon)
                .read_text(encoding="utf-8")
                .splitlines()
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
                    NATIVE_CLI,
                    "export-codex-runtime-summary",
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
            NATIVE_CLI,
            "export-codex-runtime-summary",
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
