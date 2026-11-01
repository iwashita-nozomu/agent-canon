# @dependency-start
# contract implementation
# responsibility Tests Codex token footprint comparison behavior.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/token_footprints.rs token comparer
# upstream design ../../agents/skills/tokens.md token protocol
# @dependency-end
"""Tests for Codex session token footprint comparison."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NATIVE_CLI = (
    os.environ.get("AGENT_CANON_NATIVE_BIN")
    or os.environ.get("AGENT_CANON_CLI")
    or str(PROJECT_ROOT / "tools" / "bin" / "agent-canon")
)


def write_session(path: Path, total_tokens: int) -> None:
    """Write a minimal Codex session JSONL file with token_count events."""
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 10,
                                    "cached_input_tokens": 2,
                                    "output_tokens": 3,
                                    "reasoning_output_tokens": 1,
                                    "total_tokens": total_tokens,
                                },
                                "last_token_usage": {
                                    "input_tokens": 10,
                                    "cached_input_tokens": 2,
                                    "output_tokens": 3,
                                    "reasoning_output_tokens": 1,
                                    "total_tokens": total_tokens,
                                },
                                "model_context_window": 1000,
                            },
                        },
                    },
                    separators=(",", ":"),
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_two_event_session(path: Path, total_tokens: int) -> None:
    """Write a session with two token_count observations."""
    write_session(path, total_tokens=total_tokens // 2)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": total_tokens,
                                "cached_input_tokens": 2,
                                "output_tokens": 3,
                                "reasoning_output_tokens": 1,
                                "total_tokens": total_tokens,
                            }
                        },
                    },
                },
                separators=(",", ":"),
            )
        )
        stream.write("\n")


class CompareCodexTokenFootprintsTest(unittest.TestCase):
    """Verify session token footprint comparison status and evidence."""

    def test_candidate_token_footprint_below_half_passes(self) -> None:
        """A candidate at or below half the baseline should pass mechanically."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            baseline = root / "baseline.jsonl"
            candidate = root / "candidate.jsonl"
            report_dir = root / "reports" / "agents" / "run-1"
            report = root / "comparison.md"
            write_session(baseline, total_tokens=200)
            write_session(candidate, total_tokens=80)

            result = subprocess.run(
                [
                    NATIVE_CLI,
                    "compare-codex-token-footprints",
                    "--baseline-session",
                    str(baseline),
                    "--candidate-session",
                    str(candidate),
                    "--report-out",
                    str(report),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("TOKEN_FOOTPRINT_COMPARISON=pass", result.stdout)
            self.assertIn("TOKEN_FOOTPRINT_RATIO=0.400", result.stdout)
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("comparison_status: pass", report_text)
            monitor_text = (report_dir / "workflow_monitoring.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("token_footprint_comparison=pass", monitor_text)
            self.assertIn(
                "token footprint measured from Codex session logs", monitor_text
            )

    def test_candidate_token_footprint_above_half_fails(self) -> None:
        """A candidate above the target ratio should fail mechanically."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            baseline = root / "baseline.jsonl"
            candidate = root / "candidate.jsonl"
            write_session(baseline, total_tokens=200)
            write_session(candidate, total_tokens=120)

            result = subprocess.run(
                [
                    NATIVE_CLI,
                    "compare-codex-token-footprints",
                    "--baseline-session",
                    str(baseline),
                    "--candidate-session",
                    str(candidate),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("TOKEN_FOOTPRINT_COMPARISON=fail", result.stdout)
            self.assertIn("TOKEN_FOOTPRINT_BELOW_TARGET=no", result.stdout)

    def test_session_glob_summary_records_moving_average(self) -> None:
        """Summary mode should turn Codex sessions into moving-average evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sessions = root / "sessions"
            sessions.mkdir()
            write_two_event_session(sessions / "a.jsonl", total_tokens=100)
            write_session(sessions / "b.jsonl", total_tokens=200)
            report_dir = root / "reports" / "agents" / "run-1"
            report = root / "token-summary.md"

            result = subprocess.run(
                [
                    NATIVE_CLI,
                    "compare-codex-token-footprints",
                    "--session-glob",
                    str(sessions / "*.jsonl"),
                    "--moving-average-window",
                    "2",
                    "--report-out",
                    str(report),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("TOKEN_USAGE_SUMMARY=pass", result.stdout)
            self.assertIn("TOKEN_USAGE_SESSION_COUNT=2", result.stdout)
            self.assertIn("TOKEN_USAGE_TOKEN_EVENT_COUNT=3", result.stdout)
            self.assertIn(
                "TOKEN_USAGE_LATEST_MOVING_AVERAGE_TOTAL=150.000", result.stdout
            )
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("token_usage_summary_status: present", report_text)
            monitor_text = (report_dir / "workflow_monitoring.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("token_usage_summary=present", monitor_text)
            self.assertIn("latest_moving_average_total=150.000", monitor_text)

    def test_session_glob_summary_can_filter_recent_files(self) -> None:
        """Recent summary mode should use file mtime for long-running sessions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sessions = root / "sessions"
            sessions.mkdir()
            old_session = sessions / "old.jsonl"
            recent_session = sessions / "recent.jsonl"
            write_session(old_session, total_tokens=100)
            write_session(recent_session, total_tokens=300)
            old_timestamp = time.time() - 10 * 24 * 60 * 60
            os.utime(old_session, (old_timestamp, old_timestamp))

            result = subprocess.run(
                [
                    NATIVE_CLI,
                    "compare-codex-token-footprints",
                    "--session-glob",
                    str(sessions / "*.jsonl"),
                    "--recent-days",
                    "5",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("TOKEN_USAGE_SESSION_COUNT=1", result.stdout)
            self.assertIn("TOKEN_USAGE_TOTAL_TOKENS=300", result.stdout)
            self.assertIn("TOKEN_USAGE_RECENT_DAYS=5", result.stdout)

    def test_recursive_session_glob_preserves_hidden_symlink_dedup_and_order(
        self,
    ) -> None:
        """Recursive glob summaries skip hidden paths and resolve duplicate symlink matches."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sessions = root / "sessions"
            external = root / "external"
            hidden = sessions / ".private"
            sessions.mkdir()
            external.mkdir()
            hidden.mkdir()
            write_session(sessions / "session-b.jsonl", total_tokens=200)
            write_session(sessions / "session-a.jsonl", total_tokens=100)
            write_session(hidden / "session-c.jsonl", total_tokens=900)
            write_session(external / "session-c.jsonl", total_tokens=300)

            alias = sessions / "alias"
            has_directory_symlink = True
            try:
                alias.symlink_to(external, target_is_directory=True)
            except (NotImplementedError, OSError):
                has_directory_symlink = False

            pattern = str(sessions / "**" / "session-[abc].jsonl")
            report = root / "summary.md"
            result = subprocess.run(
                [
                    NATIVE_CLI,
                    "compare-codex-token-footprints",
                    "--session-glob",
                    pattern,
                    "--session-glob",
                    pattern,
                    "--report-out",
                    str(report),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            expected_count = 3 if has_directory_symlink else 2
            expected_total = 600 if has_directory_symlink else 300
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"TOKEN_USAGE_SESSION_COUNT={expected_count}", result.stdout)
            self.assertIn(f"TOKEN_USAGE_TOTAL_TOKENS={expected_total}", result.stdout)
            report_text = report.read_text(encoding="utf-8")
            self.assertNotIn(str(hidden / "session-c.jsonl"), report_text)
            first = str(external / "session-c.jsonl")
            second = str(sessions / "session-a.jsonl")
            if has_directory_symlink:
                self.assertIn(first, report_text)
                self.assertLess(report_text.index(first), report_text.index(second))
            self.assertLess(
                report_text.index(second),
                report_text.index(str(sessions / "session-b.jsonl")),
            )


if __name__ == "__main__":
    unittest.main()
