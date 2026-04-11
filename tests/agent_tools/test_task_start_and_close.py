"""Tests for machine-driven task start and close commands."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASK_START_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "task_start.py"
TASK_CLOSE_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "task_close.py"
BOOTSTRAP_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "bootstrap_agent_run.py"


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
            self.assertIn(
                "SUGGESTED_SKILLS=$codex-task-workflow,$agent-orchestration,$subagent-bootstrap,$comprehensive-development",
                result.stdout,
            )
            self.assertIn("AUTO_SPECIALISTS=cpp_reviewer", result.stdout)
            self.assertIn("IMPLEMENTATION_CODEX_AGENTS=spark_worker,worker", result.stdout)
            self.assertIn("REQUEST_CONTRACT_REQUIRED=yes", result.stdout)
            self.assertIn("REQUEST_CONTRACT=", result.stdout)
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
                "SUGGESTED_SKILLS=$codex-task-workflow,$agent-orchestration,$subagent-bootstrap,$behavior-preserving-refactor",
                result.stdout,
            )

    def test_bootstrap_defaults_report_root_to_workspace_reports_agents(self) -> None:
        """bootstrap_agent_run should default report output under the workspace root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            run_id = "test-default-workspace-report-root"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "workspace-local report root",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(workspace_root),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report_dir = workspace_root / "reports" / "agents" / run_id
            self.assertIn(f"REPORT_DIR={report_dir}", result.stdout)
            self.assertTrue(report_dir.is_dir())

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
            (report_dir / "user_request_contract.md").write_text(
                "\n".join(
                    [
                        "# User Request Contract",
                        "",
                        "- all_clauses_resolved: yes",
                        "- forbidden_drift_detected: no",
                        "- deferred_clause_ids:",
                        "- unresolved_clause_ids:",
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
                        "- request_contract_complete: yes",
                        "- all_planned_chunks_complete: yes",
                        "- overall_delivery_complete: yes",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
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

    def test_task_close_defaults_report_root_to_workspace_cwd(self) -> None:
        """task_close --run-id should resolve reports/agents under the current workspace."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            run_id = "test-task-close-workspace-default"
            subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "workspace closeout ready",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(workspace_root),
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            report_dir = workspace_root / "reports" / "agents" / run_id
            (report_dir / "verification.txt").write_text(
                "\n".join(
                    [
                        f"run_id={run_id}",
                        "task=workspace closeout ready",
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
            (report_dir / "user_request_contract.md").write_text(
                "\n".join(
                    [
                        "# User Request Contract",
                        "",
                        "- all_clauses_resolved: yes",
                        "- forbidden_drift_detected: no",
                        "- deferred_clause_ids:",
                        "- unresolved_clause_ids:",
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
                        "- request_contract_complete: yes",
                        "- all_planned_chunks_complete: yes",
                        "- overall_delivery_complete: yes",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
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
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)
            self.assertIn("ALL_PLANNED_CHUNKS_COMPLETE=yes", result.stdout)
            self.assertIn("OVERALL_DELIVERY_COMPLETE=yes", result.stdout)
            self.assertIn("SPEC_PRODUCT_COVERAGE_COMPLETE=yes", result.stdout)
            self.assertIn("REVIEW_FINDINGS_INTEGRATED=yes", result.stdout)
            self.assertIn("REQUEST_CONTRACT_RESOLVED=yes", result.stdout)

    def test_task_close_rejects_chunk_only_completion(self) -> None:
        """task_close should fail when only a chunk is complete."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-chunk-only"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "verification.txt").write_text(
                "\n".join(
                    [
                        f"run_id={run_id}",
                        "task=chunk only closeout smoke",
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
            (report_dir / "user_request_contract.md").write_text(
                "\n".join(
                    [
                        "# User Request Contract",
                        "",
                        "- all_clauses_resolved: yes",
                        "- forbidden_drift_detected: no",
                        "- deferred_clause_ids:",
                        "- unresolved_clause_ids:",
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
                        "- request_contract_complete: yes",
                        "- all_planned_chunks_complete: no",
                        "- overall_delivery_complete: no",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("all_planned_chunks_complete", result.stdout)
            self.assertIn("overall_delivery_complete", result.stdout)

    def test_task_close_rejects_partial_spec_or_ignored_review_findings(self) -> None:
        """task_close should fail when spec coverage or review integration is incomplete."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-partial-spec"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "verification.txt").write_text(
                "\n".join(
                    [
                        f"run_id={run_id}",
                        "task=partial spec closeout smoke",
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
            (report_dir / "user_request_contract.md").write_text(
                "\n".join(
                    [
                        "# User Request Contract",
                        "",
                        "- all_clauses_resolved: yes",
                        "- forbidden_drift_detected: no",
                        "- deferred_clause_ids:",
                        "- unresolved_clause_ids:",
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
                        "- request_contract_complete: yes",
                        "- all_planned_chunks_complete: yes",
                        "- overall_delivery_complete: yes",
                        "- spec_product_coverage_complete: no",
                        "- review_findings_integrated: no",
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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("spec_product_coverage_complete", result.stdout)
            self.assertIn("review_findings_integrated", result.stdout)


if __name__ == "__main__":
    unittest.main()
