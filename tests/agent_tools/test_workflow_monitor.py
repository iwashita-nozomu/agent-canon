"""Tests for workflow monitoring accumulation."""

# @dependency-start
# contract test
# responsibility Tests workflow monitor accumulation behavior.
# upstream implementation ../../tools/runtime/lifecycle/workflow_monitor.py appends evidence
# upstream implementation ../../tools/runtime/lifecycle/bootstrap_agent_run.py seeds evidence
# upstream implementation ../../tools/runtime/lifecycle/update_lifecycle_contract.py owns update lifecycle evidence identities
# @dependency-end

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Protocol, cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from tools.runtime.artifacts.runtime_artifacts import RuntimeSymlinkEscape  # noqa: E402

MONITOR_SCRIPT = (
    PROJECT_ROOT / "tools" / "runtime" / "lifecycle" / "workflow_monitor.py"
)
BOOTSTRAP_SCRIPT = (
    PROJECT_ROOT / "tools" / "runtime" / "lifecycle" / "bootstrap_agent_run.py"
)
RUNTIME_PROFILE_INVENTORY = (
    PROJECT_ROOT / "documents" / "runtime" / "runtime-profiles-and-check-matrix.json"
)


def seed_bootstrap_workspace(workspace_root: Path) -> None:
    """Copy the canonical runtime inputs required by the bootstrap fixture."""
    for relative_path in (
        ".codex/config.toml",
        "agents/model_profiles.toml",
        "agents/canonical/CODEX_WORKFLOW.md",
        "templates/agents/design_brief.md",
        "agents/skills/codex-task-workflow.md",
        "documents/design/dependency-manifest-design.md",
    ):
        destination = workspace_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((PROJECT_ROOT / relative_path).read_bytes())


class WorkflowMonitorModule(Protocol):
    """Loaded workflow_monitor constants used by regression tests."""

    VALIDATION_FAILURE_CAUSE_CLASSIFICATION_VALUES: frozenset[str]
    VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES: frozenset[str]


def load_monitor_module() -> WorkflowMonitorModule:
    """Load workflow_monitor.py for constant-level regression checks."""
    sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
    try:
        spec = importlib.util.spec_from_file_location(
            "workflow_monitor", MONITOR_SCRIPT
        )
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

    def test_monitor_records_pointer_only_update_lifecycle_evidence(self) -> None:
        """Monitoring keeps DSV/lifecycle/close refs without duplicating policy."""
        module = load_monitor_module()
        evidence_type = getattr(module, "LifecycleMonitoringEvidence")
        entries_type = getattr(module, "MonitoringEntries")
        append_monitoring = getattr(module, "append_monitoring")
        evidence_refs = (
            "evidence:" + "1" * 64,
            "evidence:" + "2" * 64,
        )
        evidence = evidence_type(
            decision_sufficiency_packet_ref="evidence:" + "3" * 64,
            decision_sufficiency_rejection_ref=None,
            lifecycle_state="closed",
            evidence_refs=evidence_refs,
            close_agent_tool_call_ref="close-token:" + "4" * 64,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = append_monitoring(
                Path(tmp_dir),
                entries_type(lifecycle_evidence=evidence),
            )
            text = path.read_text(encoding="utf-8")

        self.assertIn("## Update Lifecycle Evidence", text)
        self.assertIn('"schema":"agent-canon.update-lifecycle-monitoring.v1"', text)
        self.assertIn('"lifecycle_state":"closed"', text)
        self.assertIn(evidence_refs[0], text)
        self.assertNotIn("plausible repository state", text)

    def test_monitor_append_preserves_prepared_monitoring_prefix(self) -> None:
        """Post-move monitoring appends to prepared bytes instead of replacing them."""
        module = load_monitor_module()
        entries_type = getattr(module, "MonitoringEntries")
        append_monitoring = getattr(module, "append_monitoring")
        with tempfile.TemporaryDirectory(
            prefix="agent-canon-workflow-monitor-"
        ) as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            report_dir.mkdir(parents=True)
            prepared = "prepared-monitoring-prefix\n"
            (report_dir / "workflow_monitoring.md").write_text(
                prepared, encoding="utf-8"
            )
            append_monitoring(
                report_dir,
                entries_type(signals=("source=post-move",)),
                runtime_root=Path(tmp_dir),
            )
            text = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")

        self.assertTrue(text.startswith(prepared))
        self.assertIn("source=post-move", text)

    def test_monitor_rejects_duplicate_lifecycle_evidence_refs(self) -> None:
        """One evidence identity may be recorded only once in a monitor event."""
        module = load_monitor_module()
        evidence_type = getattr(module, "LifecycleMonitoringEvidence")
        lifecycle_record = getattr(module, "lifecycle_monitoring_record")
        repeated = "evidence:" + "5" * 64
        evidence = evidence_type(
            decision_sufficiency_packet_ref="evidence:" + "6" * 64,
            decision_sufficiency_rejection_ref=None,
            lifecycle_state="prepared",
            evidence_refs=(repeated, repeated),
            close_agent_tool_call_ref=None,
        )

        with self.assertRaisesRegex(ValueError, "evidence_ref_duplicate"):
            lifecycle_record(evidence)

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
                        "source=user target=.codex/personal/skills/agent-learning/SKILL.md "
                        "action=prompt_repair evidence=observed-drift"
                    ),
                    "--intervention",
                    "spawned reviewer",
                    "--decision",
                    "workflow_improvement_decision=applied",
                    "--decision",
                    "knowledge_learning_decision=not_applicable",
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
                "upstream design ../../../templates/agents/workflow_monitoring.md",
                text,
            )
            self.assertIn("skills=$agent-orchestration", text)
            self.assertIn("skill_invocation=$agent-orchestration status=observed", text)
            self.assertIn("runtime_feedback=observed", text)
            self.assertIn("target=.codex/personal/skills/agent-learning/SKILL.md", text)
            self.assertIn("action=prompt_repair", text)
            self.assertIn("## Tool Warnings", text)
            self.assertIn("- tool_warnings_status: pending", text)
            self.assertIn("spawned reviewer", text)
            self.assertIn("- workflow_improvement_decision: applied", text)
            self.assertIn("- knowledge_learning_decision: not_applicable", text)

    def test_monitor_uses_runtime_environment_for_feedback_capture(self) -> None:
        """The environment runtime route also spools structured feedback."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime = Path(tmp_dir) / "runtime"
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--run-id",
                    "env-runtime-run",
                    "--report-root",
                    "reports",
                    "--workspace-root",
                    str(Path(tmp_dir) / "workspace"),
                    "--runtime-feedback",
                    "source=user target=skill action=prompt_repair evidence=env",
                ],
                cwd=PROJECT_ROOT,
                env={**os.environ, "AGENT_CANON_RUNTIME_ROOT": str(runtime)},
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(
                (
                    runtime / "reports" / "env-runtime-run" / "workflow_monitoring.md"
                ).is_file()
            )
            request = runtime / "spool" / "private-feedback" / "sync-request.json"
            self.assertTrue(request.is_file())
            self.assertNotIn("prompt_repair", request.read_text(encoding="utf-8"))
            records = list(
                (runtime / "spool/private-feedback/feedback/runtime-feedback").glob(
                    "*.md"
                )
            )
            self.assertEqual(len(records), 1)
            captured = records[0].read_text(encoding="utf-8")
            self.assertIn("input_mode: structured-log", captured)
            self.assertIn("run: env-runtime-run", captured)
            self.assertIn(
                "source=user target=skill action=prompt_repair evidence=env", captured
            )
            self.assertNotIn("prompt_repair", result.stdout + result.stderr)

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

    def test_monitor_preserves_schema_owned_completion_evidence(self) -> None:
        """Monitor projection must retain typed gate, failure, resource, and binding fields."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            semantic_event = " ".join(
                [
                    "event_id=event-1",
                    "context_id=context-1",
                    "semantic_kind=validation",
                    "owner=writer",
                    "state_owner=writer",
                    "api_owner=writer",
                    "dependency_owner=writer",
                    "responsibility_unit=completion-coverage",
                    "intent_id=intent-1",
                    "outcome=pass",
                    "evidence_refs=source.md",
                    "artifact_refs=completion_coverage.json",
                    'gate_evidence={"gate_id":"oop_readability_guard","outcome":"pass"}',
                    'failure_response={"status":"none"}',
                    'resource_certificate={"certificate_id":"none","status":"none"}',
                    'source_binding={"run_id":"run-1","context_id":"context-1"}',
                ]
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--semantic-event",
                    semantic_event,
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            work_log = (report_dir / "work_log.md").read_text(encoding="utf-8")
            ledger_line = next(
                line
                for line in work_log.splitlines()
                if line.startswith("- ledger_event=")
            )
            event = json.loads(ledger_line.removeprefix("- ledger_event="))
            self.assertEqual(
                event["gate_evidence"],
                {"gate_id": "oop_readability_guard", "outcome": "pass"},
            )
            self.assertEqual(event["failure_response"], {"status": "none"})
            self.assertEqual(
                event["resource_certificate"],
                {"certificate_id": "none", "status": "none"},
            )
            self.assertEqual(
                event["source_binding"],
                {"run_id": "run-1", "context_id": "context-1"},
            )

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
                    "knowledge_learning_decision=not_applicable",
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
            self.assertIn(
                "tool_call=canonical-format-check code_checker=pass "
                "checker=markdown-math-mermaid scope=changed-paths",
                text,
            )
            self.assertIn(
                "hook_dispatcher=official schema=agent-canon.posttooluse-stop.v1 "
                "events=PostToolUse,Stop",
                text,
            )
            self.assertNotIn("pre_edit_rejection_prediction=", text)
            self.assertNotIn("predicted_tool_rejection_gates=", text)
            self.assertIn("static_analysis_feedback=recorded", text)
            self.assertIn("hook_tool_feedback=reviewed", text)
            self.assertIn("parent_protocol_update=not_required", text)
            self.assertIn("subagent_protocol_update=not_required", text)
            self.assertIn("protocol_feedback_reason=", text)
            self.assertIn(
                "validation_failure_not_observed reason=standard-closeout-preset",
                text,
            )
            self.assertIn("execution_path_comparison_not_required", text)
            self.assertIn("token_efficiency_not_required", text)
            self.assertNotIn("EVAL_RUN_ID=recorded", text)
            self.assertNotIn("EVAL_ACCUMULATED_REPORT=recorded", text)
            self.assertIn("runtime_feedback_not_observed", text)
            self.assertIn("diff_check_agent_decision=approve", text)

    def test_explicit_prediction_evidence_is_preserved(self) -> None:
        """Removing preset claims must not discard an explicitly supplied result."""
        evidence = "pre_edit_rejection_prediction=warn predicted_tool_rejection_gates=responsibility_scope"
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--behavior-event",
                    evidence,
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            text = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")
            self.assertIn(evidence, text)
            self.assertNotIn("pre_edit_rejection_prediction=reviewed", text)

    def test_bootstrap_seeds_monitoring_with_routing_evidence(self) -> None:
        """bootstrap_agent_run should seed workflow monitoring without manual edits."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True)
            seed_bootstrap_workspace(workspace_root)
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
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            monitor_path = report_root / "monitor-bootstrap" / "workflow_monitoring.md"
            text = monitor_path.read_text(encoding="utf-8")
            self.assertIn(
                "PRE_EDIT_REJECTION_PREDICTION_STATUS=optional_diagnostic",
                result.stdout,
            )
            self.assertNotIn(
                "PRE_EDIT_REJECTION_PREDICTION_STATUS=pending", result.stdout
            )
            self.assertIn("workflow=Owner-Bounded Change", text)
            self.assertIn("skills=$agent-orchestration", text)
            self.assertIn("stage owner routing active_roles=", text)
            self.assertIn("created run bundle", text)


def test_monitor_atomic_open_rejects_parent_path_replacement() -> None:
    """The monitor boundary rejects a replaced path component before opening it."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        outside = root / "outside"
        outside.mkdir()
        replaced = root / "reports"
        replaced.symlink_to(outside, target_is_directory=True)
        module = load_monitor_module()
        target = replaced / "workflow_monitoring.md"
        with unittest.TestCase().assertRaises(RuntimeSymlinkEscape):
            with module.locked_monitoring_artifact(target, runtime_root=root):
                pass
        assert not (outside / "workflow_monitoring.md").exists()


if __name__ == "__main__":
    unittest.main()
