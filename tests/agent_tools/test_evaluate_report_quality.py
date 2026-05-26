# @dependency-start
# responsibility Tests report quality eval automation.
# upstream implementation ../../tools/agent_tools/evaluate_report_quality.py report quality eval helper
# upstream design ../../agents/evals/report_quality_eval.toml report quality eval manifest
# upstream design ../../documents/runtime-log-archive.md accumulated result archive contract
# @dependency-end
"""Tests for report quality evals."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "evaluate_report_quality.py"


def run_eval(*args: str, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    """Run the report quality eval helper."""
    command = [sys.executable, str(SCRIPT), *args]
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed


class ReportQualityEvalTest(unittest.TestCase):
    """Verify report quality eval behavior."""

    def test_current_manifest_passes(self) -> None:
        """The canonical report quality eval manifest passes."""
        result = run_eval()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("REPORT_QUALITY_EVAL_STATUS=pass", result.stdout)
        self.assertIn("REPORT_QUALITY_EVAL_CRITICAL_FAILED=0", result.stdout)
        self.assertIn("REPORT_QUALITY_EVAL_RUN_ID=report-quality-eval-", result.stdout)

    def test_accumulate_writes_unique_report(self) -> None:
        """The runner writes a uniquely named accumulated Markdown report."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            results_dir = Path(tmp_dir) / "report-quality"

            result = run_eval("--accumulate", "--results-dir", str(results_dir))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            reports = sorted(results_dir.glob("*.md"))
            self.assertEqual(len(reports), 1)
            text = reports[0].read_text(encoding="utf-8")
            self.assertIn("# Report Quality Eval", text)
            self.assertIn("REPORT_QUALITY_EVAL_STATUS=pass", text)

    def test_missing_required_quality_item_fails(self) -> None:
        """A target missing required checklist language fails."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "report.md"
            manifest = root / "eval.toml"
            target.write_text("Audience only.\n", encoding="utf-8")
            manifest.write_text(
                textwrap.dedent(
                    """
                    # @dependency-start
                    # responsibility Defines test report quality evals.
                    # upstream design report.md test target
                    # @dependency-end
                    version = 1

                    [[evals]]
                    id = "sample"
                    target = "report.md"
                    description = "sample"

                    [[evals.checklist]]
                    id = "Q1"
                    critical = true
                    description = "requires limitations"
                    required_regex = ["limitations"]
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = run_eval("--root", str(root), "--manifest", str(manifest))

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("REPORT_QUALITY_EVAL_STATUS=fail", result.stdout)
            self.assertIn("REPORT_QUALITY_EVAL_CRITICAL_FAILED=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
