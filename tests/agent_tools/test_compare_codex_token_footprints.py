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
import re
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

    def test_complete_cli_and_report_bytes_match_frozen_python_outputs(self) -> None:
        """Only the declared report-owner locator and clock input may differ."""
        fixture = PROJECT_ROOT / "tests/fixtures/token_footprints/python_golden.json"
        cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]
        old_owner = "../../eval/checkers/compare_codex_token_footprints.py"
        native_owner = (
            "../../tools/runtime/dispatch/agent-canon/src/token_footprints.rs"
        )

        def normalize(text: str, root: Path) -> str:
            text = text.replace(str(root), "{case}").replace(old_owner, native_owner)
            return re.sub(r"`\d{4}-\d{2}-\d{2} \d{2}:\d{2} JST`", "`{timestamp}`", text)

        for case in cases:
            with self.subTest(case=case["name"]), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for relative, contents in case["sessions"].items():
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(contents, encoding="utf-8")
                if case["name"] == "recent":
                    old = root / "sessions/a.jsonl"
                    timestamp = time.time() - 10 * 24 * 60 * 60
                    os.utime(old, (timestamp, timestamp))
                arguments = [
                    value.replace("{case}", str(root)) for value in case["args"]
                ]
                result = subprocess.run(
                    [NATIVE_CLI, "compare-codex-token-footprints", *arguments],
                    cwd=PROJECT_ROOT,
                    env={**os.environ, "AGENT_CANON_RUNTIME_ROOT": str(root)},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, case["exit"], result.stderr)
                self.assertEqual(
                    normalize(result.stdout, root), normalize(case["stdout"], root)
                )
                self.assertEqual(
                    normalize(result.stderr, root), normalize(case["stderr"], root)
                )
                if "report" in case:
                    report = (root / "report.md").read_text(encoding="utf-8")
                    self.assertEqual(
                        normalize(report, root), normalize(case["report"], root)
                    )
                if "monitor_raw" in case:
                    monitor = (
                        root / "reports/agents/run-1/workflow_monitoring.md"
                    ).read_text(encoding="utf-8")
                    self.assertEqual(
                        normalize(monitor, root), normalize(case["monitor_raw"], root)
                    )

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
