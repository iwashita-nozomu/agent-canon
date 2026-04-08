"""Smoke-test coverage for the research perspective pack helper."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts" / "agent_tools" / "smoke_test_research_perspective_pack.py"
)
BOOTSTRAP_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "agent_tools" / "bootstrap_agent_run.py"


class ResearchPerspectivePackSmokeTest(unittest.TestCase):
    """Verify that the smoke-test helper exits successfully."""

    def test_smoke_script_passes(self) -> None:
        """The helper should report a passing smoke test on the checked-in config."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SMOKE_TEST=pass", result.stdout)

    def test_run_bundle_includes_document_flow_review_artifact(self) -> None:
        """The always-on bundle should create the document flow review artifact."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-document-flow-review"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT_PATH),
                    "--task",
                    "document flow reviewer smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--report-root",
                    str(report_root),
                    "--workspace-root",
                    str(PROJECT_ROOT),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            report_dir = report_root / run_id

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("document_flow_review.md", result.stdout)
            self.assertTrue((report_dir / "document_flow_review.md").is_file())

    def test_run_bundle_can_enable_academic_writing_reviewers(self) -> None:
        """Academic writing reviewers should create their review artifacts when enabled."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-academic-writing-reviewers"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT_PATH),
                    "--task",
                    "academic writing smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--report-root",
                    str(report_root),
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--enable",
                    "notation_definition_reviewer",
                    "--enable",
                    "logic_gap_reviewer",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            report_dir = report_root / run_id

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("notation_definition_review.md", result.stdout)
            self.assertIn("logic_gap_review.md", result.stdout)
            self.assertTrue((report_dir / "notation_definition_review.md").is_file())
            self.assertTrue((report_dir / "logic_gap_review.md").is_file())

    def test_task_id_expands_default_research_reviewers(self) -> None:
        """Task-id bootstrap should expand default research reviewers and review packs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-id-t4"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT_PATH),
                    "--task",
                    "research-backed change",
                    "--task-id",
                    "T4",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--report-root",
                    str(report_root),
                    "--workspace-root",
                    str(PROJECT_ROOT),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            report_dir = report_root / run_id

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("TASK_ID=T4", result.stdout)
            self.assertIn("report_reviewer", result.stdout)
            self.assertIn("python_reviewer", result.stdout)
            self.assertTrue((report_dir / "report_review.md").is_file())
            self.assertTrue((report_dir / "python_review.md").is_file())
            self.assertTrue((report_dir / "reproducibility_review.md").is_file())
            self.assertTrue((report_dir / "benchmark_review.md").is_file())


if __name__ == "__main__":
    unittest.main()
