# @dependency-start
# upstream design ../../agents/workflows/agent-learning-workflow.md agent feedback workflow
# upstream implementation ../../tools/agent_tools/evaluate_agent_run.py evaluates run bundles
# downstream implementation ../../tools/agent_tools/task_close.py consumes agent evaluation status
# @dependency-end

"""Tests for agent run evaluation."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "evaluate_agent_run.py"


def write_ready_run(report_dir: Path) -> None:
    """Write a minimal passing run bundle."""
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "user_request_contract.md").write_text(
        "\n".join(
            [
                "# User Request Contract",
                "- all_clauses_resolved: yes",
                "- forbidden_drift_detected: no",
                "- unresolved_clause_ids:",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (report_dir / "schedule.md").write_text(
        "\n".join(
            [
                "# Schedule",
                "## Stage Plan",
                "| Stage | Owner Agent | Review Agent | Inputs | Exit Criteria | Status |",
                "| ----- | ----------- | ------------ | ------ | ------------- | ------ |",
                "| requirements | manager | reviewer | request | fixed | complete |",
                "## Clause Coverage",
                "| Clause ID | Covered By Stage | Review Gate | Status |",
                "| --------- | ---------------- | ----------- | ------ |",
                "| C1 | requirements | review | complete |",
                "## Planned Work Units",
                "| Unit ID | Clause IDs | Owner | Completion Evidence | Next Gate | Status |",
                "| ------- | ---------- | ----- | ------------------- | --------- | ------ |",
                "| W1 | C1 | codex | tests | closeout | complete |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (report_dir / "work_log.md").write_text(
        "\n".join(
            [
                "# Work Log",
                "## Purpose",
                "- Record meaningful execution.",
                "## Entries",
                "- kickoff: request_clause_ids=C1 skills=$agent-orchestration,$codex-task-workflow stage owner=codex subagent=worker mcp_preflight_not_required web_research_not_required next=implementation",
                "- validation: request_clause_ids=C1 repo_dependency_review=pass next=closeout",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (report_dir / "workflow_monitoring.md").write_text(
        "\n".join(
            [
                "# Workflow Monitoring",
                "## Signals",
                "- skills=$agent-orchestration,$codex-task-workflow",
                "- stage owner=codex subagent=worker parent_direct_reason=small test run",
                "- mcp_preflight_not_required: no MCP tool needed for this unit test",
                "- repo_dependency_review=pass path_count=12",
                "- web_research_not_required: local deterministic test",
                "## Interventions",
                "- Monitoring kept implementation local and required dependency review evidence before closeout.",
                "## Improvement Decisions",
                "- skill_improvement_decision: not_applicable",
                "- config_improvement_decision: not_applicable",
                "- workflow_improvement_decision: not_applicable",
                "- memory_learning_decision: not_applicable",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (report_dir / "change_review.md").write_text(
        "\n".join(
            [
                "# Change Review",
                "<!-- template text may mention revise, but comments are not findings -->",
                "",
                "## Chunk Findings",
                "",
                "No fix-now findings are open.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (report_dir / "final_review.md").write_text(
        "# Final Review\n\n## Decision\n\napprove\n",
        encoding="utf-8",
    )
    (report_dir / "verification.txt").write_text("status=pass\n", encoding="utf-8")
    (report_dir / "closeout_gate.md").write_text(
        "\n".join(
            [
                "# Closeout Gate",
                "- validation_complete: yes",
                "- dependency_headers_complete: yes",
                "- repo_wide_dependency_tools_complete: yes",
                "- canonical_tree_head_complete: yes",
                "- commit_created: yes",
                "- push_completed: yes",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (report_dir / "retrospective.md").write_text(
        "\n".join(
            [
                "# Retrospective",
                "## What Worked",
                "- Tooling caught the issue.",
                "## What Hurt",
                "- None.",
                "## Follow-ups",
                "- None.",
                "",
            ]
        ),
        encoding="utf-8",
    )


class EvaluateAgentRunTest(unittest.TestCase):
    """Verify the run evaluation helper."""

    def test_evaluate_ready_run_writes_pass_report(self) -> None:
        """A complete run should receive a passing agent evaluation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--write",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("AGENT_EVALUATION_STATUS=pass", result.stdout)
            report = (report_dir / "agent_evaluation.md").read_text(encoding="utf-8")
            self.assertIn("- evaluation_status: pass", report)
            self.assertIn("- feedback_actions_resolved: yes", report)

    def test_evaluate_ready_run_ignores_template_comment_revise_text(self) -> None:
        """Template comments containing revise should not be treated as open findings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            (report_dir / "change_review.md").write_text(
                "\n".join(
                    [
                        "# Change Review",
                        "<!-- If decision is revise, record fix-now findings here. -->",
                        "",
                        "## Chunk Findings",
                        "",
                        "No blocking findings.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("AGENT_EVALUATION_STATUS=pass", result.stdout)

    def test_evaluate_missing_workflow_monitoring_fails(self) -> None:
        """Workflow monitoring is required for closeout-quality evaluation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            (report_dir / "workflow_monitoring.md").unlink()

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--write",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AGENT_EVALUATION_STATUS=revise", result.stdout)
            report = (report_dir / "agent_evaluation.md").read_text(encoding="utf-8")
            self.assertIn("workflow_monitoring", report)

    def test_evaluate_pending_improvement_decisions_fail(self) -> None:
        """Skill/config/workflow/memory improvement decisions must be closed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")
            (report_dir / "workflow_monitoring.md").write_text(
                monitoring.replace(
                    "- workflow_improvement_decision: not_applicable",
                    "- workflow_improvement_decision: pending",
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AGENT_EVALUATION_STATUS=revise", result.stdout)

    def test_evaluate_incomplete_run_fails_with_feedback(self) -> None:
        """Missing evidence should create fix-now feedback actions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            report_dir.mkdir(parents=True)
            (report_dir / "user_request_contract.md").write_text(
                "- all_clauses_resolved: no\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--write",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AGENT_EVALUATION_STATUS=revise", result.stdout)
            self.assertIn("AGENT_EVALUATION_FEEDBACK_ACTIONS_OPEN=", result.stdout)
            report = (report_dir / "agent_evaluation.md").read_text(encoding="utf-8")
            self.assertIn("| F1 | fix-now |", report)
