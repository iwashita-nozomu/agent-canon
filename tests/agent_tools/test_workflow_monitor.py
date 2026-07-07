"""Tests for workflow monitoring accumulation."""

# @dependency-start
# contract test
# responsibility Tests workflow monitor accumulation behavior.
# upstream implementation ../../tools/agent_tools/workflow_monitor.py appends evidence
# upstream implementation ../../tools/agent_tools/bootstrap_agent_run.py seeds evidence
# upstream implementation ../../tools/agent_tools/task_start.py seeds evidence
# @dependency-end

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
MONITOR_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "workflow_monitor.py"
BOOTSTRAP_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "bootstrap_agent_run.py"
TASK_START_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "task_start.py"
RUNTIME_PROFILE_INVENTORY = (
    PROJECT_ROOT / "documents" / "runtime-profiles-and-check-matrix.json"
)


class WorkflowMonitorModule(Protocol):
    """Loaded workflow_monitor constants used by regression tests."""

    VALIDATION_FAILURE_CAUSE_CLASSIFICATION_VALUES: frozenset[str]
    VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES: frozenset[str]


def load_monitor_module() -> WorkflowMonitorModule:
    """Load workflow_monitor.py for constant-level regression checks."""
    sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
    try:
        spec = importlib.util.spec_from_file_location("workflow_monitor", MONITOR_SCRIPT)
        if spec is None or spec.loader is None:
            raise AssertionError("failed to load workflow_monitor module spec")
        module = importlib.util.module_from_spec(spec)
        prior_module = sys.modules.get(spec.name)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            return cast(WorkflowMonitorModule, module)
        finally:
            if prior_module is None:
                sys.modules.pop(spec.name, None)
            else:
                sys.modules[spec.name] = prior_module
    finally:
        sys.path.pop(0)


class WorkflowMonitorTest(unittest.TestCase):
    """Verify workflow monitoring is updated mechanically."""

    def test_monitor_validation_failure_taxonomy_comes_from_runtime_inventory(
        self,
    ) -> None:
        """Validation-failure slugs should be owned by the JSON inventory."""
        data = json.loads(RUNTIME_PROFILE_INVENTORY.read_text(encoding="utf-8"))
        response = data["validation_failure_response"]
        module = load_monitor_module()

        self.assertEqual(
            module.VALIDATION_FAILURE_CAUSE_CLASSIFICATION_VALUES,
            frozenset(response["cause_classes"]),
        )
        self.assertEqual(
            module.VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES,
            frozenset(response["intent_preservation"]),
        )

    def test_monitor_appends_signals_interventions_and_decisions(self) -> None:
        """The monitor CLI should update all monitored sections."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--signal",
                    "skills=$agent-orchestration",
                    "--behavior-event",
                    "skill_invocation=$agent-orchestration status=observed",
                    "--runtime-feedback",
                    (
                        "source=user target=.agents/skills/agent-learning/SKILL.md "
                        "action=prompt_repair evidence=observed-drift"
                    ),
                    "--intervention",
                    "spawned reviewer",
                    "--decision",
                    "workflow_improvement_decision=applied",
                    "--decision",
                    "memory_learning_decision=not_applicable",
                    "--timestamp",
                    "2026-04-30 12:00 JST",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            text = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")
            self.assertIn(
                "upstream design ../../../agents/templates/workflow_monitoring.md",
                text,
            )
            self.assertIn("skills=$agent-orchestration", text)
            self.assertIn("skill_invocation=$agent-orchestration status=observed", text)
            self.assertIn("runtime_feedback=observed", text)
            self.assertIn("target=.agents/skills/agent-learning/SKILL.md", text)
            self.assertIn("action=prompt_repair", text)
            self.assertIn("## Tool Warnings", text)
            self.assertIn("- tool_warnings_status: pending", text)
            self.assertIn("spawned reviewer", text)
            self.assertIn("- workflow_improvement_decision: applied", text)
            self.assertIn("- memory_learning_decision: not_applicable", text)

    def test_monitor_appends_structured_tool_warning(self) -> None:
        """Tool warnings should be recorded as closeout-obligating ledger rows."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--tool-warning",
                    (
                        "warning_id=W1 source_tool=legacy-forwarder "
                        "severity=fix-now status=open message=deprecated_wrapper "
                        "repair_command=agent-canon_cli"
                    ),
                    "--timestamp",
                    "2026-04-30 12:00 JST",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            text = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")
            self.assertIn("## Tool Warnings", text)
            self.assertIn("tool_warning=recorded", text)
            self.assertIn("warning_id=W1", text)
            self.assertIn("status=open", text)
            self.assertIn("- tool_warnings_status: open", text)

    def test_monitor_sets_no_tool_warning_status(self) -> None:
        """Runs with no observed warning should mark the ledger explicitly none."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--tool-warning-status",
                    "none",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            text = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")
            self.assertIn("- tool_warnings_status: none", text)

    def test_monitor_appends_mid_task_user_input_to_wave_artifacts(self) -> None:
        """Mid-task user additions should checkpoint schedule and monitoring rows."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            (report_dir / "schedule.md").write_text(
                "\n".join(
                    [
                        "# Schedule",
                        "",
                        "## Agent Wave Ledger",
                        (
                            "| Wave ID | Parent Or Delegate | Spawn Authority | Trigger | "
                            "Budget Before | Budget After | Runtime Max Threads | "
                            "Runtime Max Depth | Spawned Roles | Role Instances | Skipped Roles / "
                            "Rationale | Allowed Paths | Do Not Read | Write Scope | "
                            "Validation Route | Review Gate | Handoff Artifacts | "
                            "Delegated Policy Ref | Status |"
                        ),
                        (
                            "| ------- | ------------------ | --------------- | ------- | "
                            "------------- | ------------ | ------------------- | "
                            "----------------- | ------------- | -------------- | ------------------------- | "
                            "------------- | ----------- | ----------- | ---------------- | "
                            "----------- | ----------------- | -------------------- | ------ |"
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--mid-task-user-input",
                    (
                        "wave_id=WAVE-2 input_classification=same_active_task_delta "
                        "updated_packet=reports/agents/run-1/user_delta_001.md "
                        "target_agents=explorer scope_status=unchanged "
                        "budget_before=3/12 budget_after=3/12 runtime_max_threads=24 "
                        "runtime_max_depth=2 allowed_paths=reports/agents/run-1 "
                        "do_not_read=reports/agents/other write_scope=read-only "
                        "validation_route=pytest review_gate=parent_review "
                        "handoff_artifacts=reports/agents/run-1/user_delta_001.md"
                    ),
                    "--timestamp",
                    "2026-04-30 12:00 JST",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            schedule_text = (report_dir / "schedule.md").read_text(encoding="utf-8")
            monitoring_text = (report_dir / "workflow_monitoring.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("| WAVE-2 | parent | parent_checkpoint_then_send_input |", schedule_text)
            self.assertIn("event_kind=mid_task_user_input", monitoring_text)
            self.assertIn("input_classification=same_active_task_delta", monitoring_text)
            self.assertIn("redispatch_action=send_input", monitoring_text)
            self.assertIn("updated_packet=reports/agents/run-1/user_delta_001.md", monitoring_text)
            self.assertIn("mid_task_user_input=checkpointed", monitoring_text)

    def test_monitor_replaces_initial_blocker_with_actual_subagent_wave(self) -> None:
        """A real parent wave should replace the bootstrap authority blocker."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True)
            bootstrap = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "nested wave monitor",
                    "--task-id",
                    "T1",
                    "--owner",
                    "codex",
                    "--run-id",
                    "run-1",
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
            self.assertEqual(bootstrap.returncode, 0, bootstrap.stderr)

            report_dir = report_root / "run-1"
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--subagent-wave",
                    (
                        "wave_id=WAVE-1 parent_or_delegate=parent "
                        "spawn_authority=parent_runtime_authority "
                        "trigger=initial_intake_spawn budget_before=4/4 "
                        "budget_after=1/4 runtime_max_threads=24 runtime_max_depth=2 "
                        "spawned_roles=requirements_organizer,explorer,execution_planner "
                        "role_instances=requirements_organizer:intake:team_manifest.yaml#requirements,"
                        "explorer:intake:team_manifest.yaml#explore,"
                        "execution_planner:intake:team_manifest.yaml#plan "
                        "skipped_roles=none allowed_paths=reports/agents/run-1,team_manifest.yaml "
                        "do_not_read=.agent-canon/log-archive,reports/agents/other "
                        "write_scope=read_only validation_route=parent_review "
                        "review_gate=parent_integration "
                        "handoff_artifacts=team_manifest.yaml#run.spawn_wave_recommendation "
                        "status=completed"
                    ),
                    "--timestamp",
                    "2026-04-30 12:00 JST",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            schedule_text = (report_dir / "schedule.md").read_text(encoding="utf-8")
            monitoring_text = (report_dir / "workflow_monitoring.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual(schedule_text.count("| WAVE-1 |"), 1)
            self.assertIn("| WAVE-1 | parent | parent_runtime_authority |", schedule_text)
            self.assertNotIn("blocked_authority_required", schedule_text)
            self.assertIn("event_kind=spawned", monitoring_text)
            self.assertIn("subagent_wave=recorded wave_id=WAVE-1", monitoring_text)
            self.assertNotIn("event_kind=authority_blocker", monitoring_text)

    def test_monitor_rejects_delegated_child_wave_without_budget(self) -> None:
        """Delegated child waves must preserve bounded budget evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--subagent-wave",
                    (
                        "wave_id=WAVE-2 parent_or_delegate=worker "
                        "event_kind=delegated_child_spawn "
                        "spawn_authority=delegated_stage_owner "
                        "trigger=validation_failure_requires_parallel_triage "
                        "budget_before=1/4 budget_after=2/4 "
                        "runtime_max_threads=24 runtime_max_depth=2 "
                        "spawned_roles=python_reviewer "
                        "role_instances=python_reviewer:triage:test_plan.md "
                        "skipped_roles=none allowed_paths=tests/agent_tools "
                        "do_not_read=reports/agents/other write_scope=read_only "
                        "validation_route=pytest review_gate=parent_integration "
                        "handoff_artifacts=reports/agents/run-1/triage_packet.md "
                        "status=completed"
                    ),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("remaining_spawn_budget", result.stderr)

    def test_monitor_records_read_only_validation_failure_triage_wave(self) -> None:
        """Validation-failure triage may stay read-only before cause evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            (report_dir / "schedule.md").write_text(
                "\n".join(
                    [
                        "# Schedule",
                        "",
                        "## Agent Wave Ledger",
                        (
                            "| Wave ID | Parent Or Delegate | Spawn Authority | Trigger | "
                            "Budget Before | Budget After | Runtime Max Threads | "
                            "Runtime Max Depth | Spawned Roles | Role Instances | Skipped Roles / "
                            "Rationale | Allowed Paths | Do Not Read | Write Scope | "
                            "Validation Route | Review Gate | Handoff Artifacts | "
                            "Delegated Policy Ref | Status |"
                        ),
                        (
                            "| ------- | ------------------ | --------------- | ------- | "
                            "------------- | ------------ | ------------------- | "
                            "----------------- | ------------- | -------------- | ------------------------- | "
                            "------------- | ----------- | ----------- | ---------------- | "
                            "----------- | ----------------- | -------------------- | ------ |"
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--subagent-wave",
                    (
                        "wave_id=WAVE-2 parent_or_delegate=parent "
                        "spawn_authority=parent_runtime_authority "
                        "trigger=validation_failure_requires_parallel_triage "
                        "budget_before=2/4 budget_after=1/4 "
                        "runtime_max_threads=24 runtime_max_depth=2 "
                        "spawned_roles=test_designer "
                        "role_instances=test_designer:triage:test_plan.md "
                        "skipped_roles=none allowed_paths=tests/agent_tools "
                        "do_not_read=reports/agents/other write_scope=read_only "
                        "validation_route=pytest review_gate=parent_integration "
                        "handoff_artifacts=reports/agents/run-1/triage_packet.md "
                        "status=completed"
                    ),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            monitoring_text = (report_dir / "workflow_monitoring.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "trigger=validation_failure_requires_parallel_triage",
                monitoring_text,
            )
            self.assertIn("write_scope=read_only", monitoring_text)

    def test_monitor_accepts_generated_read_only_until_cause_identified_scope(
        self,
    ) -> None:
        """Generated manifest read-only triage value should be accepted."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            (report_dir / "schedule.md").write_text(
                "\n".join(
                    [
                        "# Schedule",
                        "",
                        "## Agent Wave Ledger",
                        (
                            "| Wave ID | Parent Or Delegate | Spawn Authority | Trigger | "
                            "Budget Before | Budget After | Runtime Max Threads | "
                            "Runtime Max Depth | Spawned Roles | Role Instances | Skipped Roles / "
                            "Rationale | Allowed Paths | Do Not Read | Write Scope | "
                            "Validation Route | Review Gate | Handoff Artifacts | "
                            "Delegated Policy Ref | Status |"
                        ),
                        (
                            "| ------- | ------------------ | --------------- | ------- | "
                            "------------- | ------------ | ------------------- | "
                            "----------------- | ------------- | -------------- | ------------------------- | "
                            "------------- | ----------- | ----------- | ---------------- | "
                            "----------- | ----------------- | -------------------- | ------ |"
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--subagent-wave",
                    (
                        "wave_id=WAVE-2 parent_or_delegate=parent "
                        "spawn_authority=parent_runtime_authority "
                        "trigger=validation_failure_requires_parallel_triage "
                        "budget_before=2/4 budget_after=1/4 "
                        "runtime_max_threads=24 runtime_max_depth=2 "
                        "spawned_roles=test_designer "
                        "role_instances=test_designer:triage:test_plan.md "
                        "skipped_roles=none allowed_paths=tests/agent_tools "
                        "do_not_read=reports/agents/other "
                        "write_scope=read_only_until_cause_identified "
                        "validation_route=pytest review_gate=parent_integration "
                        "handoff_artifacts=reports/agents/run-1/triage_packet.md "
                        "status=completed"
                    ),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            monitoring_text = (report_dir / "workflow_monitoring.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "write_scope=read_only_until_cause_identified",
                monitoring_text,
            )

    def test_monitor_rejects_validation_failure_repair_without_cause_evidence(
        self,
    ) -> None:
        """Write-capable validation repair requires cause-classification evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--subagent-wave",
                    (
                        "wave_id=WAVE-2 parent_or_delegate=parent "
                        "spawn_authority=parent_runtime_authority "
                        "trigger=validation_failure_requires_parallel_triage "
                        "budget_before=2/4 budget_after=1/4 "
                        "runtime_max_threads=24 runtime_max_depth=2 "
                        "spawned_roles=worker "
                        "role_instances=worker:repair:team_manifest.yaml#repair "
                        "skipped_roles=none allowed_paths=tools/agent_tools "
                        "do_not_read=reports/agents/other write_scope=tools/agent_tools "
                        "validation_route=pytest review_gate=change_reviewer "
                        "handoff_artifacts=reports/agents/run-1/repair_packet.md "
                        "status=completed"
                    ),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("validation failure repair wave", result.stderr)
            self.assertIn("failing_contract", result.stderr)
            self.assertIn("cause_classification", result.stderr)

    def test_monitor_records_validation_failure_repair_evidence(self) -> None:
        """Write-capable validation repair should emit preserved-intent tokens."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            (report_dir / "schedule.md").write_text(
                "\n".join(
                    [
                        "# Schedule",
                        "",
                        "## Agent Wave Ledger",
                        (
                            "| Wave ID | Parent Or Delegate | Spawn Authority | Trigger | "
                            "Budget Before | Budget After | Runtime Max Threads | "
                            "Runtime Max Depth | Spawned Roles | Role Instances | Skipped Roles / "
                            "Rationale | Allowed Paths | Do Not Read | Write Scope | "
                            "Validation Route | Review Gate | Handoff Artifacts | "
                            "Delegated Policy Ref | Status |"
                        ),
                        (
                            "| ------- | ------------------ | --------------- | ------- | "
                            "------------- | ------------ | ------------------- | "
                            "----------------- | ------------- | -------------- | ------------------------- | "
                            "------------- | ----------- | ----------- | ---------------- | "
                            "----------- | ----------------- | -------------------- | ------ |"
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--subagent-wave",
                    (
                        "wave_id=WAVE-3 parent_or_delegate=parent "
                        "spawn_authority=parent_runtime_authority "
                        "trigger=validation_failure_requires_parallel_triage "
                        "budget_before=2/4 budget_after=1/4 "
                        "runtime_max_threads=24 runtime_max_depth=2 "
                        "spawned_roles=worker "
                        "role_instances=worker:repair:team_manifest.yaml#repair "
                        "skipped_roles=none allowed_paths=tools/agent_tools "
                        "do_not_read=reports/agents/other write_scope=tools/agent_tools "
                        "validation_route=pytest review_gate=change_reviewer "
                        "handoff_artifacts=reports/agents/run-1/repair_packet.md "
                        "failing_contract=pytest "
                        "observation_level=public_cli "
                        "cause_classification=implementation_bug "
                        "intent_preservation=repair_same_intent "
                        "evidence=reports/agents/run-1/cause_investigation.md "
                        "status=completed"
                    ),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            monitoring_text = (report_dir / "workflow_monitoring.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("failing_contract=pytest", monitoring_text)
            self.assertIn("observation_level=public_cli", monitoring_text)
            self.assertIn("cause_classification=implementation_bug", monitoring_text)
            self.assertIn("intent_preservation=repair_same_intent", monitoring_text)

    def test_monitor_rejects_noncanonical_validation_failure_cause_slug(self) -> None:
        """Validation failure cause_classification must use token-safe slugs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--subagent-wave",
                    (
                        "wave_id=WAVE-3 parent_or_delegate=parent "
                        "spawn_authority=parent_runtime_authority "
                        "trigger=validation_failure_requires_parallel_triage "
                        "budget_before=2/4 budget_after=1/4 "
                        "runtime_max_threads=24 runtime_max_depth=2 "
                        "spawned_roles=worker "
                        "role_instances=worker:repair:team_manifest.yaml#repair "
                        "skipped_roles=none allowed_paths=tools/agent_tools "
                        "do_not_read=reports/agents/other write_scope=tools/agent_tools "
                        "validation_route=pytest review_gate=change_reviewer "
                        "handoff_artifacts=reports/agents/run-1/repair_packet.md "
                        "failing_contract=pytest "
                        "observation_level=public_cli "
                        "cause_classification=test_oracle/spec_mismatch "
                        "intent_preservation=repair_same_intent "
                        "evidence=reports/agents/run-1/cause_investigation.md "
                        "status=completed"
                    ),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cause_classification", result.stderr)
            self.assertIn("test_oracle_spec_mismatch", result.stderr)

    def test_monitor_rejects_mid_task_user_input_with_wrong_action(self) -> None:
        """Classification and redispatch action should be mechanically consistent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--mid-task-user-input",
                    (
                        "wave_id=WAVE-2 input_classification=same_active_task_delta "
                        "redispatch_action=fresh_followup_wave "
                        "updated_packet=reports/agents/run-1/user_delta_001.md "
                        "target_agents=explorer scope_status=unchanged "
                        "budget_before=3/12 budget_after=3/12 runtime_max_threads=24 "
                        "runtime_max_depth=2 allowed_paths=reports/agents/run-1 "
                        "do_not_read=reports/agents/other write_scope=read-only "
                        "validation_route=pytest review_gate=parent_review "
                        "handoff_artifacts=reports/agents/run-1/user_delta_001.md"
                    ),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("redispatch_action", result.stderr)

    def test_monitor_requires_scope_change_fresh_wave_evidence(self) -> None:
        """Scope-changing user additions should name fresh follow-up wave evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--mid-task-user-input",
                    (
                        "wave_id=WAVE-2 input_classification=scope_or_contract_change "
                        "updated_packet=reports/agents/run-1/user_delta_001.md "
                        "target_agents=worker scope_status=changed "
                        "budget_before=3/12 budget_after=4/12 runtime_max_threads=24 "
                        "runtime_max_depth=2 spawned_roles=worker "
                        "role_instances=worker:followup:reports/agents/run-1/user_delta_001.md "
                        "allowed_paths=tools/agent_tools "
                        "do_not_read=reports/agents/other write_scope=tools/agent_tools "
                        "validation_route=pytest review_gate=python_review "
                        "handoff_artifacts=reports/agents/run-1/user_delta_001.md"
                    ),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("fresh_wave_evidence", result.stderr)

    def test_monitor_records_scope_change_fresh_wave_evidence(self) -> None:
        """Fresh follow-up wave evidence should be emitted as machine-readable tokens."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            (report_dir / "schedule.md").write_text(
                "\n".join(
                    [
                        "# Schedule",
                        "",
                        "## Agent Wave Ledger",
                        (
                            "| Wave ID | Parent Or Delegate | Spawn Authority | Trigger | "
                            "Budget Before | Budget After | Runtime Max Threads | "
                            "Runtime Max Depth | Spawned Roles | Role Instances | Skipped Roles / "
                            "Rationale | Allowed Paths | Do Not Read | Write Scope | "
                            "Validation Route | Review Gate | Handoff Artifacts | "
                            "Delegated Policy Ref | Status |"
                        ),
                        (
                            "| ------- | ------------------ | --------------- | ------- | "
                            "------------- | ------------ | ------------------- | "
                            "----------------- | ------------- | -------------- | ------------------------- | "
                            "------------- | ----------- | ----------- | ---------------- | "
                            "----------- | ----------------- | -------------------- | ------ |"
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--mid-task-user-input",
                    (
                        "wave_id=WAVE-2 input_classification=scope_or_contract_change "
                        "updated_packet=reports/agents/run-1/user_delta_001.md "
                        "target_agents=worker scope_status=changed "
                        "budget_before=3/12 budget_after=4/12 runtime_max_threads=24 "
                        "runtime_max_depth=2 spawned_roles=worker "
                        "role_instances=worker:followup:reports/agents/run-1/user_delta_001.md "
                        "allowed_paths=tools/agent_tools "
                        "do_not_read=reports/agents/other write_scope=tools/agent_tools "
                        "validation_route=pytest review_gate=python_review "
                        "handoff_artifacts=reports/agents/run-1/user_delta_001.md "
                        "fresh_wave_evidence=reports/agents/run-1/fresh_wave.md"
                    ),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            monitoring_text = (report_dir / "workflow_monitoring.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("redispatch_action=fresh_followup_wave", monitoring_text)
            self.assertIn(
                "fresh_wave_evidence=reports/agents/run-1/fresh_wave.md",
                monitoring_text,
            )

    def test_monitor_rejects_mid_task_input_with_wrong_spawn_authority(self) -> None:
        """Classification should own spawn authority, not caller-supplied overrides."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--mid-task-user-input",
                    (
                        "wave_id=WAVE-2 input_classification=new_task "
                        "spawn_authority=parent_checkpoint_then_send_input "
                        "updated_packet=reports/agents/run-1/user_delta_001.md "
                        "target_agents=none scope_status=new_task "
                        "budget_before=3/12 budget_after=3/12 runtime_max_threads=24 "
                        "runtime_max_depth=2 allowed_paths=reports/agents/run-2 "
                        "do_not_read=reports/agents/run-1 write_scope=none "
                        "validation_route=task_start review_gate=manager_review "
                        "handoff_artifacts=reports/agents/run-1/user_delta_001.md "
                        "fresh_run_bundle=reports/agents/run-2"
                    ),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("spawn_authority", result.stderr)

    def test_monitor_preserves_parallel_tool_warning_updates(self) -> None:
        """Concurrent tool warning updates should not lose ledger rows."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            processes = [
                subprocess.Popen(
                    [
                        sys.executable,
                        str(MONITOR_SCRIPT),
                        "--report-dir",
                        str(report_dir),
                        "--tool-warning",
                        (
                            f"warning_id=W{index} source_tool=checker "
                            "severity=warning status=open message=warning "
                            "repair_command=repair"
                        ),
                    ],
                    cwd=PROJECT_ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for index in range(6)
            ]

            for process in processes:
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stdout + stderr)

            text = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")
            for index in range(6):
                self.assertIn(f"warning_id=W{index}", text)
            self.assertIn("- tool_warnings_status: open", text)

    def test_monitor_rejects_tool_warning_without_routeable_fields(self) -> None:
        """Tool warning rows should have enough fields to repair or defer."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--tool-warning",
                    "warning_id=W1 source_tool=checker status=open",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("tool warning must include required keys", result.stderr)

    def test_monitor_rejects_runtime_feedback_without_target_action(self) -> None:
        """Runtime feedback should be routeable to a concrete update surface."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--runtime-feedback",
                    "source=user evidence=unclear",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("target=", result.stderr)

    def test_closeout_token_preset_records_behavior_eval_tokens(self) -> None:
        """The closeout preset should append the standard behavior tokens."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--closeout-token-preset",
                    "--decision",
                    "skill_improvement_decision=recorded",
                    "--decision",
                    "config_improvement_decision=not_applicable",
                    "--decision",
                    "workflow_improvement_decision=recorded",
                    "--decision",
                    "memory_learning_decision=not_applicable",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            text = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")
            self.assertIn("skill_invocation=$agent-orchestration", text)
            self.assertIn("repo_dependency_review=pass", text)
            self.assertIn("tool_call=pyright code_checker=pass", text)
            self.assertIn("tool_call=ruff code_checker=pass", text)
            self.assertIn("tool_call=oop-readability-check code_checker=pass", text)
            self.assertIn("static_analysis_feedback=recorded", text)
            self.assertIn("hook_tool_feedback=reviewed", text)
            self.assertIn("parent_protocol_update=not_required", text)
            self.assertIn("subagent_protocol_update=not_required", text)
            self.assertIn("protocol_feedback_reason=", text)
            self.assertIn("execution_path_comparison_not_required", text)
            self.assertIn("token_efficiency_not_required", text)
            self.assertIn("prompt_eval_required", text)
            self.assertNotIn("EVAL_RUN_ID=recorded", text)
            self.assertNotIn("EVAL_ACCUMULATED_REPORT=recorded", text)
            self.assertIn("runtime_feedback_not_observed", text)
            self.assertIn("diff_check_agent_decision=approve", text)

    def test_bootstrap_seeds_monitoring_with_routing_evidence(self) -> None:
        """bootstrap_agent_run should seed workflow monitoring without manual edits."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "monitor bootstrap",
                    "--task-id",
                    "T1",
                    "--owner",
                    "codex",
                    "--run-id",
                    "monitor-bootstrap",
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
            monitor_path = report_root / "monitor-bootstrap" / "workflow_monitoring.md"
            text = monitor_path.read_text(encoding="utf-8")
            self.assertIn("workflow=Owner-Bounded Change", text)
            self.assertIn("skills=$agent-orchestration", text)
            self.assertIn("stage owner routing active_roles=", text)
            self.assertIn("created run bundle", text)

    def test_task_start_seeds_monitoring_with_routing_evidence(self) -> None:
        """task_start should seed workflow monitoring without manual edits."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_START_SCRIPT),
                    "--task",
                    "monitor task start",
                    "--task-id",
                    "T1",
                    "--owner",
                    "codex",
                    "--run-id",
                    "monitor-task-start",
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
            monitor_path = report_root / "monitor-task-start" / "workflow_monitoring.md"
            text = monitor_path.read_text(encoding="utf-8")
            self.assertIn("workflow=Owner-Bounded Change", text)
            self.assertIn("skills=$agent-orchestration", text)
            self.assertIn("stage owner routing active_roles=", text)
            self.assertIn("created run bundle", text)


if __name__ == "__main__":
    unittest.main()
