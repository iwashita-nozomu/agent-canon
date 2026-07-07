# @dependency-start
# contract test
# responsibility Tests test evaluate agent run behavior.
# upstream design ../../agents/workflows/agent-learning-workflow.md agent feedback workflow
# upstream implementation ../../tools/agent_tools/evaluate_agent_run.py evaluates run bundles
# downstream implementation ../../tools/agent_tools/task_close.py consumes agent evaluation status
# @dependency-end

"""Tests for agent run evaluation."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Protocol, cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "evaluate_agent_run.py"
RUNTIME_PROFILE_INVENTORY = (
    PROJECT_ROOT / "documents" / "runtime-profiles-and-check-matrix.json"
)


class EvaluateAgentRunModule(Protocol):
    """Loaded evaluate_agent_run constants used by regression tests."""

    VALIDATION_FAILURE_CAUSE_CLASSIFICATION_VALUES: frozenset[str]
    VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES: frozenset[str]


def load_evaluate_module() -> EvaluateAgentRunModule:
    """Load evaluate_agent_run.py for constant-level regression checks."""
    sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
    try:
        spec = importlib.util.spec_from_file_location("evaluate_agent_run", SCRIPT)
        if spec is None or spec.loader is None:
            raise AssertionError("failed to load evaluate_agent_run module spec")
        module = importlib.util.module_from_spec(spec)
        prior_module = sys.modules.get(spec.name)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            return cast(EvaluateAgentRunModule, module)
        finally:
            if prior_module is None:
                sys.modules.pop(spec.name, None)
            else:
                sys.modules[spec.name] = prior_module
    finally:
        sys.path.pop(0)


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
            "## Agent Wave Ledger",
            (
                "| Wave ID | Spawn Authority | Trigger | Budget Before | Budget After | "
                "Runtime Max Threads | Runtime Max Depth | Spawned Roles | Skipped Roles | "
                "Allowed Paths | Do Not Read | Write Scope | Validation Route | Review Gate | "
                "Handoff Artifacts | Status |"
            ),
            (
                "| ------- | --------------- | ------- | ------------- | ------------ | "
                "------------------- | ----------------- | ------------- | ------------- | "
                "------------- | ----------- | ----------- | ---------------- | ----------- | "
                "----------------- | ------ |"
            ),
            (
                "| WAVE-1 | parent | unit-test | 4 | 3 | 24 | 2 | worker | none | "
                "tests/agent_tools/test_evaluate_agent_run.py | none | read-only | "
                "pytest | final_review.md | workflow_monitoring.md | complete |"
            ),
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
                "stage owner=codex subagent=worker "
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
            "- validation_failure_not_observed reason=unit-test-run-bundle",
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
            "## Tool Warnings",
            "- tool_warnings_status: none",
            "## Interventions",
            (
                "- Monitoring kept implementation local and required dependency review "
                "evidence before closeout."
            ),
            "## Improvement Decisions",
            "- skill_improvement_decision: recorded",
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

    def test_validation_failure_taxonomy_comes_from_runtime_inventory(self) -> None:
        """Validation-failure slugs should be owned by the JSON inventory."""
        data = json.loads(RUNTIME_PROFILE_INVENTORY.read_text(encoding="utf-8"))
        response = data["validation_failure_response"]
        module = load_evaluate_module()

        self.assertEqual(
            module.VALIDATION_FAILURE_CAUSE_CLASSIFICATION_VALUES,
            frozenset(response["cause_classes"]),
        )
        self.assertEqual(
            module.VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES,
            frozenset(response["intent_preservation"]),
        )

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

    def test_evaluate_rejects_negative_final_review_decision_text(self) -> None:
        """Final review decisions containing approve as a substring must not pass."""
        cases = {
            "revise-do-not-approve": "revise: do not approve",
            "not-approved": "not approved",
        }
        for case_id, decision in cases.items():
            with self.subTest(case_id=case_id), tempfile.TemporaryDirectory() as tmp_dir:
                report_dir = Path(tmp_dir) / "run"
                write_ready_run(report_dir)
                (report_dir / "final_review.md").write_text(
                    f"# Final Review\n\n## Decision\n\n{decision}\n",
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
                self.assertIn(
                    "concrete approving final review decision",
                    result.stdout,
                )

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

    def test_evaluate_open_tool_warning_fails(self) -> None:
        """An observed tool warning must be closed before agent evaluation passes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "- tool_warnings_status: none",
                    "\n".join(
                        [
                            "- tool_warnings_status: resolved",
                            (
                                "- tool_warning=recorded warning_id=W1 "
                                "source_tool=legacy-forwarder severity=warning "
                                "status=open message=deprecated_wrapper "
                                "repair_command=agent-canon_cli"
                            ),
                        ]
                    ),
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
            self.assertIn("tool warning remains open: W1", result.stdout)

    def test_evaluate_fix_now_tool_warning_requires_resolution(self) -> None:
        """Fix-now tool warnings cannot be closed by deferral."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "- tool_warnings_status: none",
                    "\n".join(
                        [
                            "- tool_warnings_status: resolved",
                            (
                                "- tool_warning=recorded warning_id=W1 "
                                "source_tool=legacy-forwarder severity=fix-now "
                                "status=deferred_with_issue "
                                "message=deprecated_wrapper "
                                "repair_command=agent-canon_cli issue=issues/open/W1.md"
                            ),
                        ]
                    ),
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
            self.assertIn("fix-now tool warning must be resolved: W1", result.stdout)

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

    def test_evaluate_observed_runtime_feedback_requires_improvement_decision(self) -> None:
        """Observed user feedback should not pass with all improvements not applicable."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "- skill_improvement_decision: recorded",
                    "- skill_improvement_decision: not_applicable",
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
            self.assertIn("runtime_feedback=observed", result.stdout)
            self.assertIn("applied or recorded", result.stdout)

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

    def test_evaluate_unresolved_implementation_bug_checker_failure_revises(
        self,
    ) -> None:
        """Same-intent implementation-bug checker failures require a later pass."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "- validation_failure_not_observed reason=unit-test-run-bundle",
                    (
                        "- check_failure=observed tool_call=pyright "
                        "code_checker=fail failing_contract=type-check "
                        "observation_level=public-cli-output "
                        "cause_classification=implementation_bug "
                        "intent_preservation=repair_same_intent "
                        "evidence=reports/agents/run/cause.md"
                    ),
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
            self.assertIn("pyright still reports code_checker=fail", result.stdout)
            self.assertIn("repair_same_intent", result.stdout)

    def test_evaluate_checker_failure_passes_after_later_same_checker_pass(
        self,
    ) -> None:
        """A same-check pass after repair resolves the checker failure route."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "- validation_failure_not_observed reason=unit-test-run-bundle",
                    (
                        "- check_failure=observed tool_call=pyright "
                        "code_checker=fail failing_contract=type-check "
                        "observation_level=public-cli-output "
                        "cause_classification=implementation_bug "
                        "intent_preservation=repair_same_intent "
                        "evidence=reports/agents/run/cause.md\n"
                        "- tool_call=pyright code_checker=pass checker=pyright "
                        "scope=repo-wide evidence=reports/agents/run/pyright-after.txt"
                    ),
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

    def test_evaluate_pre_existing_checker_failure_passes_with_residual_evidence(
        self,
    ) -> None:
        """Explicit residual failures may pass when evidence routes them away."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "- validation_failure_not_observed reason=unit-test-run-bundle",
                    (
                        "- check_failure=observed tool_call=pyright "
                        "code_checker=fail failing_contract=type-check "
                        "observation_level=public-cli-output "
                        "cause_classification=pre_existing_unrelated_failure "
                        "intent_preservation=repair_same_intent "
                        "evidence=reports/agents/run/residual.md"
                    ),
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

    def test_evaluate_oracle_weakening_without_failure_response_revises(self) -> None:
        """Oracle weakening tokens require complete failure response evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "- validation_failure_not_observed reason=unit-test-run-bundle",
                    "- check_failure=observed code_checker=fail oracle_weakening=yes",
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
            self.assertIn("failing_contract", result.stdout)

    def test_evaluate_validation_not_observed_then_checker_failure_fails(
        self,
    ) -> None:
        """A later checker failure contradicts validation_failure_not_observed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "tool_call=pyright code_checker=pass",
                    "tool_call=pyright code_checker=fail",
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
            self.assertIn("validation_failure_not_observed", result.stdout)
            self.assertIn("later failure evidence", result.stdout)

    def test_evaluate_later_validation_failure_without_packet_revises(
        self,
    ) -> None:
        """Every observed validation failure needs its own evidence packet."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "- validation_failure_not_observed reason=unit-test-run-bundle",
                    (
                        "- check_failure=observed failing_contract=pytest "
                        "observation_level=public_cli "
                        "cause_classification=fixture_environment_issue "
                        "intent_preservation=repair_same_intent "
                        "evidence=reports/agents/run/cause.md\n"
                        "- validation_status=fail"
                    ),
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
            self.assertIn("failing_contract=", result.stdout)
            self.assertIn("observation_level=", result.stdout)

    def test_evaluate_later_checker_failure_without_packet_revises(
        self,
    ) -> None:
        """A later code_checker=fail without the five fields remains blocking."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "- validation_failure_not_observed reason=unit-test-run-bundle",
                    (
                        "- check_failure=observed tool_call=pyright "
                        "code_checker=fail failing_contract=type-check "
                        "observation_level=public-cli-output "
                        "cause_classification=fixture_environment_issue "
                        "intent_preservation=repair_same_intent "
                        "evidence=reports/agents/run/cause.md\n"
                        "- tool_call=ruff code_checker=fail checker=ruff "
                        "scope=repo-wide"
                    ),
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
            self.assertIn("ruff code_checker=fail missing validation-failure", result.stdout)
            self.assertIn("intent_preservation=<canonical_slug>", result.stdout)

    def test_evaluate_missing_validation_failure_observation_fails(self) -> None:
        """The validation failure criterion needs an explicit observation state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "- validation_failure_not_observed reason=unit-test-run-bundle",
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
            self.assertIn("validation_failure_not_observed", result.stdout)
            self.assertIn("observed validation failure token", result.stdout)

    def test_evaluate_oracle_weakening_with_same_intent_repair_fails(self) -> None:
        """Forbidden oracle weakening is not justified by same-intent repair."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "- validation_failure_not_observed reason=unit-test-run-bundle",
                    (
                        "- check_failure=observed failing_contract=pytest "
                        "observation_level=public_cli "
                        "cause_classification=implementation_bug "
                        "intent_preservation=repair_same_intent "
                        "evidence=reports/agents/run/cause.md "
                        "oracle_weakening=attempted"
                    ),
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
            self.assertIn("oracle_weakening=", result.stdout)
            self.assertIn("escalate_design_conflict", result.stdout)

    def test_evaluate_forbidden_validation_repairs_fail_without_escalation(
        self,
    ) -> None:
        """Deletion, simplification, and validation downscope require escalation."""
        forbidden_tokens = ("test_deleted=", "behavior_simplified=", "validation_downscope=")
        for token in forbidden_tokens:
            with self.subTest(token=token), tempfile.TemporaryDirectory() as tmp_dir:
                report_dir = Path(tmp_dir) / "run"
                write_ready_run(report_dir)
                monitoring_path = report_dir / "workflow_monitoring.md"
                monitoring = monitoring_path.read_text(encoding="utf-8")
                monitoring_path.write_text(
                    monitoring.replace(
                        "- validation_failure_not_observed reason=unit-test-run-bundle",
                        (
                            "- check_failure=observed failing_contract=pytest "
                            "observation_level=public_cli "
                            "cause_classification=implementation_bug "
                            "intent_preservation=repair_same_intent "
                            "evidence=reports/agents/run/cause.md "
                            f"{token}attempted"
                        ),
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
                self.assertIn(token, result.stdout)
                self.assertIn("approved_design_user_request_conflict", result.stdout)

    def test_evaluate_explicit_design_conflict_escalation_allows_oracle_change(
        self,
    ) -> None:
        """Escalated design/user conflict may carry an oracle-change token."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "- validation_failure_not_observed reason=unit-test-run-bundle",
                    (
                        "- check_failure=observed failing_contract=pytest "
                        "observation_level=public_cli "
                        "cause_classification=approved_design_user_request_conflict "
                        "intent_preservation=escalate_design_conflict "
                        "evidence=reports/agents/run/design_escalation.md "
                        "oracle_weakening=escalated"
                    ),
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

    def test_evaluate_mixed_escalation_does_not_allow_later_test_deletion(
        self,
    ) -> None:
        """Escalation applies only to forbidden tokens in the same event."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)
            monitoring_path = report_dir / "workflow_monitoring.md"
            monitoring = monitoring_path.read_text(encoding="utf-8")
            monitoring_path.write_text(
                monitoring.replace(
                    "- validation_failure_not_observed reason=unit-test-run-bundle",
                    (
                        "- check_failure=observed failing_contract=pytest "
                        "observation_level=public_cli "
                        "cause_classification=approved_design_user_request_conflict "
                        "intent_preservation=escalate_design_conflict "
                        "evidence=reports/agents/run/design_escalation.md "
                        "oracle_weakening=escalated\n"
                        "- check_failure=observed failing_contract=pytest "
                        "observation_level=public_cli "
                        "cause_classification=implementation_bug "
                        "intent_preservation=repair_same_intent "
                        "evidence=reports/agents/run/cause.md "
                        "test_deleted=attempted"
                    ),
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
            self.assertIn("test_deleted=", result.stdout)
            self.assertIn("same event", result.stdout)

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
