# @dependency-start
# contract test
# responsibility Tests report quality eval automation.
# upstream implementation ../../eval/producers/evaluate_report_quality.py report quality eval helper
# upstream design ../../eval/definitions/report_quality_eval.toml report quality eval manifest
# upstream design ../../documents/runtime/runtime-log-archive.md accumulated result archive contract
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
SCRIPT = PROJECT_ROOT / "eval" / "producers" / "evaluate_report_quality.py"


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


def external_runtime(root: Path) -> Path:
    """Return an explicit runtime directory outside the source fixture."""
    runtime = root.parent / f"{root.name}-agent-canon-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime


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
            runtime = external_runtime(Path(tmp_dir) / "source")
            results_dir = runtime / "report-quality"

            result = run_eval(
                "--runtime-root", str(runtime), "--accumulate", "--results-dir", str(results_dir)
            )

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

    def test_canonical_target_supplies_generated_shim_policy(self) -> None:
        """A thin runtime shim is evaluated with its canonical policy owner."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "shim.md").write_text("adapter\n", encoding="utf-8")
            (root / "owner.md").write_text("required policy\n", encoding="utf-8")
            manifest = root / "eval.toml"
            manifest.write_text(
                textwrap.dedent(
                    """
                    version = 1

                    [[evals]]
                    id = "canonical"
                    target = "shim.md"
                    canonical_target = "owner.md"

                    [[evals.checklist]]
                    id = "Q1"
                    required_regex = ["required policy"]
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = run_eval("--root", str(root), "--manifest", str(manifest))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
