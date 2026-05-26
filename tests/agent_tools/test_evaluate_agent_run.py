# @dependency-start
# responsibility Tests test evaluate agent run behavior.
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


def write_lines(path: Path, lines: list[str]) -> None:
    """Write one fixture artifact from lines."""
    path.write_text("\n".join(lines), encoding="utf-8")


def write_prompt_eval_report(report_dir: Path) -> None:
    """Write the prompt eval fixture."""
    write_lines(
        report_dir / "prompt-eval-report.md",
        [
            "# Skill Workflow Prompt Eval",
            "",
            "## Summary",
            "",
            "- eval_run_id: `skill-eval-test`",
            "- run_id: `unit-run`",
            "- used_skills: `agent-orchestration, codex-task-workflow`",
            "- EVAL_STATUS=pass",
            "",
        ],
    )


def write_planning_artifacts(report_dir: Path) -> None:
    """Write request, schedule, and work-log fixtures."""
    write_lines(
        report_dir / "user_request_contract.md",
        [
            "# User Request Contract",
            "- all_clauses_resolved: yes",
            "- forbidden_drift_detected: no",
            "- unresolved_clause_ids:",
            "",
        ],
    )
    write_lines(
        report_dir / "schedule.md",
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
        ],
    )
    write_lines(
        report_dir / "work_log.md",
        [
            "# Work Log",
            "## Purpose",
            "- Record meaningful execution.",
            "## Entries",
            (
                "- kickoff: request_clause_ids=C1 "
                "skills=$agent-orchestration,$codex-task-workflow "
                "stage owner=codex subagent=worker mcp_preflight_not_required "
                "web_research_not_required next=implementation"
            ),
            "- validation: request_clause_ids=C1 repo_dependency_review=pass next=closeout",
            "",
        ],
    )


def write_workflow_monitoring(report_dir: Path) -> None:
    """Write the monitoring fixture used by behavior eval tests."""
    write_lines(
        report_dir / "workflow_monitoring.md",
        [
            "# Workflow Monitoring",
            "## Signals",
            "- skills=$agent-orchestration,$codex-task-workflow",
            "- stage owner=codex subagent=worker parent_direct_reason=small test run",
            "- mcp_preflight_not_required: no MCP tool needed for this unit test",
            "- repo_dependency_review=pass path_count=12",
            "- web_research_not_required: local deterministic test",
            "- review_status=approve",
            "- validation_status=pass",
            "- drift_risk=none",
            "## Behavior Events",
            "- skill_invocation=$agent-orchestration status=observed",
            "- subagent_routing=worker stage=implementation status=observed",
            "- tool_call=run_repo_dependency_review.sh status=pass",
            "- tool_call=pyright code_checker=pass checker=pyright scope=repo-wide",
            "- tool_call=ruff code_checker=pass checker=ruff scope=repo-wide",
            (
                "- tool_call=oop-readability-check code_checker=pass "
                "checker=oop-readability scope=changed-paths"
            ),
            (
                "- execution_path_comparison=pass execution_path=reuse-first "
                "route_efficiency=efficient selected_inefficient_route=no"
            ),
            "- static_analysis_feedback=applied target=$adaptive-improvement-loop",
            (
                "- hook_tool_feedback=reviewed parent_protocol_update=applied "
                "subagent_protocol_update=applied "
                "protocol_feedback_reason=unit-test-protocol-routing"
            ),
            (
                "- tool_call=evaluate_skill_workflow_prompts.py prompt_eval=pass "
                "EVAL_STATUS=pass EVAL_RUN_ID=skill-eval-test "
                "EVAL_USED_SKILLS=agent-orchestration,codex-task-workflow "
                "EVAL_ACCUMULATED_REPORT=prompt-eval-report.md"
            ),
            (
                "- runtime_feedback=observed source=user "
                "target=.agents/skills/agent-learning/SKILL.md "
                "action=prompt_repair evidence=unit-test"
            ),
            "- review_decision=approve feedback_actions_resolved=yes",
            "- subagent_lifecycle=closed subagents_closed=yes",
            "- diff_check_not_required reason=unit-test-run-bundle",
            "- token_efficiency_not_required reason=unit-test-run-bundle",
            "## Interventions",
            (
                "- Monitoring kept implementation local and required dependency review "
                "evidence before closeout."
            ),
            "## Improvement Decisions",
            "- skill_improvement_decision: not_applicable",
            "- config_improvement_decision: not_applicable",
            "- workflow_improvement_decision: not_applicable",
            "- memory_learning_decision: not_applicable",
            "",
        ],
    )


def write_review_closeout_artifacts(report_dir: Path) -> None:
    """Write review, verification, and closeout fixtures."""
    write_lines(
        report_dir / "change_review.md",
        [
            "# Change Review",
            "<!-- template text may mention revise, but comments are not findings -->",
            "",
            "## Chunk Findings",
            "",
            "No fix-now findings are open.",
            "",
        ],
    )
    (report_dir / "final_review.md").write_text(
        "# Final Review\n\n## Decision\n\napprove\n",
        encoding="utf-8",
    )
    (report_dir / "verification.txt").write_text("status=pass\n", encoding="utf-8")
    write_lines(
        report_dir / "closeout_gate.md",
        [
            "# Closeout Gate",
            "- validation_complete: yes",
            "- dependency_headers_complete: yes",
            "- repo_wide_dependency_tools_complete: yes",
            "- repo_wide_static_analysis_complete: yes",
            "- canonical_tree_head_complete: yes",
            "- commit_created: yes",
            "- push_completed: yes",
            "",
        ],
    )
    write_lines(
        report_dir / "retrospective.md",
        [
            "# Retrospective",
            "## What Worked",
            "- Tooling caught the issue.",
            "## What Hurt",
            "- None.",
            "## Follow-ups",
            "- None.",
            "",
        ],
    )


def write_ready_run(report_dir: Path) -> None:
    """Write a minimal passing run bundle."""
    report_dir.mkdir(parents=True, exist_ok=True)
    write_prompt_eval_report(report_dir)
    write_planning_artifacts(report_dir)
    write_workflow_monitoring(report_dir)
    write_review_closeout_artifacts(report_dir)


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
            self.assertIn("- learning_capture_complete: yes", report)

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

    def test_evaluate_missing_required_signal_fails(self) -> None:
        """Required monitoring signals must cover review, validation, and drift."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace("- review_status=approve\n", ""),
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
            self.assertIn("review status", result.stdout)

    def test_evaluate_missing_behavior_events_fail(self) -> None:
        """Run behavior events are required, not only final prose summaries."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")
            before, _, after = monitoring.partition("## Behavior Events")
            _, _, tail = after.partition("## Interventions")
            (report_dir / "workflow_monitoring.md").write_text(
                before + "## Behavior Events\n\n## Interventions" + tail,
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
            self.assertIn("Record the selected skills", result.stdout)

    def test_evaluate_missing_accumulated_prompt_eval_report_fails(self) -> None:
        """Prompt eval evidence must point to a real accumulated report."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "EVAL_ACCUMULATED_REPORT=prompt-eval-report.md",
                    "EVAL_ACCUMULATED_REPORT=missing-prompt-eval-report.md",
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
            self.assertIn("accumulated prompt eval report missing", result.stdout)

    def test_evaluate_mismatched_accumulated_prompt_eval_run_id_fails(self) -> None:
        """Prompt eval report run ids must match the monitoring event."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            report_path = report_dir / "prompt-eval-report.md"
            report_path.write_text(
                report_path.read_text(encoding="utf-8").replace(
                    "skill-eval-test",
                    "skill-eval-other",
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
            self.assertIn("accumulated prompt eval run-id mismatch", result.stdout)

    def test_evaluate_inefficient_execution_path_fails(self) -> None:
        """Known inefficient route selection should trigger behavior eval feedback."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "route_efficiency=efficient selected_inefficient_route=no",
                    "route_efficiency=inefficient selected_inefficient_route=yes",
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
            self.assertIn("inefficient route", result.stdout.lower())

    def test_evaluate_missing_runtime_feedback_event_fails(self) -> None:
        """Run evaluation should require runtime feedback capture or explicit opt-out."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    (
                        "- runtime_feedback=observed source=user "
                        "target=.agents/skills/agent-learning/SKILL.md "
                        "action=prompt_repair evidence=unit-test\n"
                    ),
                    "",
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
            self.assertIn("runtime feedback", result.stdout.lower())

    def test_evaluate_missing_hook_tool_protocol_feedback_fails(self) -> None:
        """Hook and tool outcomes must route into protocol feedback decisions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    (
                        "- hook_tool_feedback=reviewed parent_protocol_update=applied "
                        "subagent_protocol_update=applied "
                        "protocol_feedback_reason=unit-test-protocol-routing\n"
                    ),
                    "",
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
            self.assertIn("hook and tool results", result.stdout.lower())

    def test_evaluate_missing_code_checker_results_fail(self) -> None:
        """Run evaluation should require code checker behavior evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                "\n".join(
                    line
                    for line in monitoring.splitlines()
                    if "code_checker=pass" not in line
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
            self.assertIn("code checker results", result.stdout.lower())

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
