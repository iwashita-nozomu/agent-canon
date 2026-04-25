# @dependency-start
# @dependency-end

"""Tests for machine-driven task start and close commands."""

# Dependency Files:
# - vendor/agent-canon/tools/agent_tools/bootstrap_agent_run.py
# - vendor/agent-canon/tools/agent_tools/task_close.py
# - vendor/agent-canon/agents/templates/closeout_gate.md

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


def write_ready_schedule(report_dir: Path) -> None:
    """Write a filled schedule artifact."""
    (report_dir / "schedule.md").write_text(
        "\n".join(
            [
                "# Schedule",
                "",
                "## Stage Plan",
                "| Stage | Owner Agent | Review Agent | Inputs | Exit Criteria | Status |",
                "| ----- | ----------- | ------------ | ------ | ------------- | ------ |",
                "| requirements | manager | manager_reviewer | contract | fixed | done |",
                "## Clause Coverage",
                "| Clause ID | Covered By Stage | Review Gate | Status |",
                "| --------- | ---------------- | ----------- | ------ |",
                "| T1-C1 | requirements | requirements | done |",
                "## Planned Work Units",
                "| Unit ID | Clause IDs | Owner | Completion Evidence | Next Gate | Status |",
                "| ------- | ---------- | ----- | ------------------- | --------- | ------ |",
                "| W1 | T1-C1 | codex | tests | final | done |",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_ready_work_log(report_dir: Path) -> None:
    """Write a filled work-log artifact."""
    (report_dir / "work_log.md").write_text(
        "\n".join(
            [
                "# Work Log",
                "",
                "## Purpose",
                "- Record meaningful execution steps.",
                "",
                "## Entries",
                (
                    "- `2026-04-08 09:00 JST | kickoff | fixed request clauses | "
                    "request_clause_ids: T1-C1 | next: implement`"
                ),
                (
                    "- `2026-04-08 09:30 JST | test | passed closeout checks | "
                    "request_clause_ids: T1-C1 | next: close`"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


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
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_COMMAND=make agent-canon-ensure-latest", result.stdout
            )
            self.assertIn("AGENT_CANON_PREFLIGHT_STATUS=skipped_by_flag", result.stdout)
            self.assertIn("RUNTIME_MAX_THREADS=24", result.stdout)
            self.assertIn("WORKFLOW_FAMILY=comprehensive_development", result.stdout)
            self.assertIn(
                "WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet",
                result.stdout,
            )
            self.assertIn("WORKFLOW_ACTIVE_SPAWN_BUDGET=12", result.stdout)
            self.assertIn("WORKFLOW_MAX_WRITE_SUBAGENTS=1", result.stdout)
            self.assertIn(
                "SUGGESTED_SKILLS=$agent-orchestration,$codex-task-workflow,$subagent-bootstrap,$comprehensive-development",
                result.stdout,
            )
            self.assertIn("AUTO_SPECIALISTS=cpp_reviewer", result.stdout)
            self.assertIn("IMPLEMENTATION_CODEX_AGENTS=spark_worker,worker", result.stdout)
            self.assertIn("CROSS_CUTTING_DOCUMENT_PACKET=", result.stdout)
            self.assertIn("/documents/REVIEW_PROCESS.md", result.stdout)
            self.assertIn("/notes/guardrails/README.md", result.stdout)
            self.assertIn("/docker/README.md", result.stdout)
            self.assertIn("/agents/workflows/implementation-waterfall-workflow.md", result.stdout)
            self.assertIn("DESIGN_DOCUMENT_PACKET=", result.stdout)
            self.assertIn("IMPLEMENTATION_DOCUMENT_PACKET=", result.stdout)
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
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RUNTIME_MAX_THREADS=24", result.stdout)
            self.assertIn(
                "WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet",
                result.stdout,
            )
            self.assertIn("WORKFLOW_ACTIVE_SPAWN_BUDGET=10", result.stdout)
            self.assertIn("WORKFLOW_MAX_WRITE_SUBAGENTS=1", result.stdout)
            self.assertIn(
                "SUGGESTED_SKILLS=$agent-orchestration,$codex-task-workflow,$subagent-bootstrap,$behavior-preserving-refactor",
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
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("AGENT_CANON_PREFLIGHT_STATUS=skipped_by_flag", result.stdout)
            self.assertIn("RUNTIME_MAX_THREADS=24", result.stdout)
            report_dir = workspace_root / "reports" / "agents" / run_id
            self.assertIn(f"REPORT_DIR={report_dir}", result.stdout)
            self.assertTrue(report_dir.is_dir())
            self.assertTrue((report_dir / "work_log.md").is_file())
            self.assertIn("CROSS_CUTTING_DOCUMENT_PACKET=", result.stdout)
            self.assertIn("/documents/REVIEW_PROCESS.md", result.stdout)
            self.assertIn("/notes/guardrails/README.md", result.stdout)
            self.assertIn("/docker/README.md", result.stdout)
            self.assertIn("/agents/workflows/implementation-waterfall-workflow.md", result.stdout)
            self.assertIn("DESIGN_DOCUMENT_PACKET=", result.stdout)
            self.assertIn("IMPLEMENTATION_DOCUMENT_PACKET=", result.stdout)
            manifest_text = (report_dir / "team_manifest.yaml").read_text(encoding="utf-8")
            self.assertIn("cross_cutting_document_packet:", manifest_text)
            self.assertIn("document_packet:", manifest_text)
            self.assertNotIn("subagent_prompt_packet:", manifest_text)
            self.assertIn("must_cite_before_edit: true", manifest_text)
            self.assertIn(str(report_dir / "design_brief.md"), manifest_text)
            self.assertIn("/documents/REVIEW_PROCESS.md", manifest_text)
            self.assertIn("/notes/guardrails/README.md", manifest_text)
            self.assertIn("/docker/README.md", manifest_text)
            self.assertIn("/agents/workflows/implementation-waterfall-workflow.md", manifest_text)

    def test_bootstrap_emits_mechanical_spawn_budget_for_task(self) -> None:
        """bootstrap_agent_run should emit runtime and workflow spawn limits for machine use."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "mechanical spawn budget",
                    "--task-id",
                    "T8",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-bootstrap-spawn-budget",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RUNTIME_MAX_THREADS=24", result.stdout)
            self.assertIn(
                "WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet",
                result.stdout,
            )
            self.assertIn("WORKFLOW_ACTIVE_SPAWN_BUDGET=10", result.stdout)
            self.assertIn("WORKFLOW_MAX_WRITE_SUBAGENTS=1", result.stdout)
            manifest_text = (
                report_root / "test-bootstrap-spawn-budget" / "team_manifest.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("workflow_family:", manifest_text)
            self.assertIn("subagent_prompt_packet:", manifest_text)
            self.assertIn("prompt_contract:", manifest_text)

    def test_all_task_ids_bootstrap_with_prompt_packet(self) -> None:
        """Every catalog task should create a workflow-specific subagent prompt packet."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)

            for task_id in [f"T{index}" for index in range(1, 14)]:
                run_id = f"test-prompt-{task_id.lower()}"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(BOOTSTRAP_SCRIPT),
                        "--task",
                        f"prompt packet {task_id}",
                        "--task-id",
                        task_id,
                        "--owner",
                        "codex",
                        "--run-id",
                        run_id,
                        "--workspace-root",
                        str(workspace_root),
                        "--report-root",
                        str(report_root),
                        "--skip-agent-canon-preflight",
                    ],
                    cwd=PROJECT_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(
                    "WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet",
                    result.stdout,
                )
                manifest_text = (report_root / run_id / "team_manifest.yaml").read_text(
                    encoding="utf-8",
                )
                self.assertIn("subagent_prompt_packet:", manifest_text)
                self.assertIn("prompt_preamble:", manifest_text)
                self.assertIn("workflow_focus:", manifest_text)
                self.assertIn("reviewer_prompt:", manifest_text)
                self.assertIn("prompt_contract:", manifest_text)

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
                    "--skip-agent-canon-preflight",
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
                    "--skip-agent-canon-preflight",
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
                        "- unfinished_tasks_absent: yes",
                        "- dependency_headers_complete: yes",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
                        "- post_fix_full_review_complete: yes",
                        "- canonical_tree_head_complete: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)
            write_ready_work_log(report_dir)

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
                    "--skip-agent-canon-preflight",
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
                        "- unfinished_tasks_absent: yes",
                        "- dependency_headers_complete: yes",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
                        "- post_fix_full_review_complete: yes",
                        "- canonical_tree_head_complete: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)
            write_ready_work_log(report_dir)

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
            self.assertIn("POST_FIX_FULL_REVIEW_COMPLETE=yes", result.stdout)
            self.assertIn("CANONICAL_TREE_HEAD_COMPLETE=yes", result.stdout)
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
                        "- unfinished_tasks_absent: no",
                        "- dependency_headers_complete: yes",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
                        "- post_fix_full_review_complete: yes",
                        "- canonical_tree_head_complete: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)
            write_ready_work_log(report_dir)

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
            self.assertIn("unfinished_tasks_absent", result.stdout)

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
                        "- unfinished_tasks_absent: yes",
                        "- dependency_headers_complete: yes",
                        "- spec_product_coverage_complete: no",
                        "- review_findings_integrated: no",
                        "- post_fix_full_review_complete: no",
                        "- canonical_tree_head_complete: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)
            write_ready_work_log(report_dir)

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

    def test_task_close_rejects_missing_post_fix_full_review_completion(self) -> None:
        """task_close should fail when review-driven fixes skipped the final full rerun."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-missing-post-fix-review"
            report_dir = report_root / run_id
            subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "closeout missing post-fix full review",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
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
                        "task=closeout missing post-fix full review",
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
                        "- unfinished_tasks_absent: yes",
                        "- dependency_headers_complete: yes",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
                        "- post_fix_full_review_complete: no",
                        "- canonical_tree_head_complete: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)
            write_ready_work_log(report_dir)

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
            self.assertIn("post_fix_full_review_complete", result.stdout)

    def test_task_close_rejects_missing_canonical_tree_head_completion(self) -> None:
        """task_close should fail when canonical tree-head cleanup is incomplete."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-missing-canonical-tree-head"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "verification.txt").write_text(
                "\n".join(
                    [
                        f"run_id={run_id}",
                        "task=closeout missing canonical tree head completion",
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
                        "- unfinished_tasks_absent: yes",
                        "- dependency_headers_complete: yes",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
                        "- post_fix_full_review_complete: yes",
                        "- canonical_tree_head_complete: no",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)
            write_ready_work_log(report_dir)

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
            self.assertIn("canonical_tree_head_complete", result.stdout)

    def test_task_close_rejects_empty_work_log(self) -> None:
        """task_close should fail when the run-local work log is still empty."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-empty-work-log"
            report_dir = report_root / run_id
            subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "closeout ready except work log",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
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
                        "task=closeout ready except work log",
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
                        "- unfinished_tasks_absent: yes",
                        "- dependency_headers_complete: yes",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
                        "- post_fix_full_review_complete: yes",
                        "- canonical_tree_head_complete: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)

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
            self.assertIn("WORK_LOG_COMPLETE=no", result.stdout)
            self.assertIn("work_log_complete", result.stdout)


if __name__ == "__main__":
    unittest.main()
