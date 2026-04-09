"""Tests for machine-driven task start and close commands."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASK_START_SCRIPT = PROJECT_ROOT / "scripts" / "agent_tools" / "task_start.py"
TASK_CLOSE_SCRIPT = PROJECT_ROOT / "scripts" / "agent_tools" / "task_close.py"
BOOTSTRAP_SCRIPT = PROJECT_ROOT / "scripts" / "agent_tools" / "bootstrap_agent_run.py"


class TaskStartAndCloseTest(unittest.TestCase):
    """Verify machine-driven task start and close behavior."""

    def test_task_start_emits_workflow_skills_and_auto_specialists(self) -> None:
        """task_start should emit machine-friendly workflow and reviewer data."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_START_SCRIPT),
                    "--task",
                    "comprehensive native change",
                    "--task-id",
                    "T12",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-task-start",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--changed-path",
                    "src/example.cpp",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("WORKFLOW_FAMILY=comprehensive_development", result.stdout)
            self.assertIn("SUGGESTED_SKILLS=$codex-task-workflow,$comprehensive-development", result.stdout)
            self.assertIn("AUTO_SPECIALISTS=cpp_reviewer", result.stdout)
            self.assertIn("START_DECLARATION=workflow=Comprehensive Development", result.stdout)
            self.assertIn("cpp_reviewer", result.stdout)

    def test_large_refactor_task_start_suggests_refactor_skill(self) -> None:
        """Large refactor should advertise the dedicated refactor skill."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_START_SCRIPT),
                    "--task",
                    "large refactor",
                    "--task-id",
                    "T6",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-large-refactor",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--changed-path",
                    "python/example.py",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "SUGGESTED_SKILLS=$codex-task-workflow,$behavior-preserving-refactor",
                result.stdout,
            )

    def test_task_close_rejects_locked_bundle(self) -> None:
        """task_close should fail while closeout is still locked."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "closeout lock smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-task-close-locked",
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_root / "test-task-close-locked"),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("CLOSEOUT_BLOCKERS=", result.stdout)

    def test_task_close_accepts_unlocked_bundle(self) -> None:
        """task_close should pass after verification and closeout statuses are resolved."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-ready"
            report_dir = report_root / run_id
            subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "closeout ready smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            (report_dir / "verification.txt").write_text(
                "\n".join(
                    [
                        f"run_id={run_id}",
                        "task=closeout ready smoke",
                        "owner=codex",
                        "created_at_utc=2026-04-08T00:00:00Z",
                        "status=pass",
                        "user_completion_report=unlocked",
                        "closeout_gate_status=resolved",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "closeout_gate.md").write_text(
                "\n".join(
                    [
                        "# Closeout Gate",
                        "",
                        "- verifier_status: pass",
                        "- auditor_status: resolved",
                        "- required_reviews_complete: yes",
                        "- validation_complete: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)


if __name__ == "__main__":
    unittest.main()
