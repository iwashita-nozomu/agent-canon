# @dependency-start
# responsibility Tests Codex token footprint comparison behavior.
# upstream implementation ../../tools/agent_tools/compare_codex_token_footprints.py compares session logs
# upstream design ../../agents/workflows/token-efficient-codex-workflow.md defines the token comparison protocol
# @dependency-end
"""Tests for Codex session token footprint comparison."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "compare_codex_token_footprints.py"


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
                    sys.executable,
                    str(SCRIPT),
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
            self.assertIn("token footprint measured from Codex session logs", monitor_text)

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
                    sys.executable,
                    str(SCRIPT),
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


if __name__ == "__main__":
    unittest.main()
