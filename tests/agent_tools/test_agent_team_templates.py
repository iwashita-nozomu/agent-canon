# @dependency-start
# contract test
# responsibility Tests agent team template rendering behavior.
# upstream design ../../templates/agents/README.md template partial contract
# downstream implementation ../../tools/agent_tools/manifest_rendering.py renders templates and partials
# downstream implementation ../../templates/code/python/docstring_template.py is the materializable code source
# downstream implementation ../../tools/agent_tools/agent_team.py owns facade orchestration
# @dependency-end

"""Tests for run artifact template rendering."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

import capacity_handshake  # noqa: E402
import task_close  # noqa: E402
import update_lifecycle_contract  # noqa: E402
from implementation_dispatch import dispatch_fixed_implementation  # noqa: E402
from manifest_rendering import (  # noqa: E402
    render_code_template,
    render_template,
    suggested_public_skills,
)
from packets import resolve_active_design_packet_config  # noqa: E402
from team_config import load_team_config  # noqa: E402


class AgentTeamTemplateTest(unittest.TestCase):
    """Verify reusable template partial expansion."""

    def test_code_template_renderer_returns_materializable_python_source(self) -> None:
        """The code owner exposes a parseable module/class/function source."""
        rendered = render_code_template("python/docstring_template.py")

        self.assertIn("class ExampleState", rendered)
        self.assertIn("def build_example_state", rendered)
        self.assertIn("Args:", rendered)
        self.assertIn("Ownership:", rendered)
        self.assertNotIn("return None", rendered)

    def test_code_template_renderer_works_from_repo_root_package_route(self) -> None:
        """repo root の canonical package invocation が source を読み戻せる。"""
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(PROJECT_ROOT / "tools")
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from agent_tools.code_template_rendering import "
                    "render_code_template; "
                    "source = render_code_template('python/docstring_template.py'); "
                    "assert 'class ExampleState' in source"
                ),
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_active_design_packet_normalizer_rejects_unknown_mapping_fields(
        self,
    ) -> None:
        """Workflow and config mappings share the closed packet field set."""
        config = load_team_config()
        base_packet = config.artifact_registry["active_design_packet"]
        self.assertIsInstance(base_packet, dict)
        packet_with_unknown = {
            **base_packet,
            "unexpected_contract": True,
        }

        with self.assertRaisesRegex(
            RuntimeError,
            r"^workflow_family\.active_design_packet:field_unknown:unexpected_contract$",
        ):
            resolve_active_design_packet_config(
                config,
                {"active_design_packet": packet_with_unknown},
            )

        config_with_unknown = replace(
            config,
            artifact_registry={
                **config.artifact_registry,
                "active_design_packet": packet_with_unknown,
            },
        )
        with self.assertRaisesRegex(
            RuntimeError,
            r"^artifacts\.active_design_packet:field_unknown:unexpected_contract$",
        ):
            resolve_active_design_packet_config(config_with_unknown)

    def test_review_template_expands_partials_and_replacements(self) -> None:
        """Rendered review artifacts should contain expanded tables and run metadata."""
        rendered = render_template(
            "artifact_review.md",
            {
                "RUN_ID": "test-run",
                "TASK": "template refactor",
                "OWNER": "codex",
                "CREATED_AT": "2026-05-24T00:00:00Z",
            },
        )

        self.assertNotIn("{{>", rendered)
        self.assertIn("- Run ID: test-run", rendered)
        self.assertIn("- Task: template refactor", rendered)
        self.assertIn(
            "| Finding | Severity | Required Change | Evidence | Status |", rendered
        )
        self.assertEqual(rendered.count("@dependency-start"), 1)

    def test_decision_partial_expands_without_manifest_leak(self) -> None:
        """Decision partials should render as normal sections inside top-level templates."""
        rendered = render_template(
            "research_review.md",
            {
                "RUN_ID": "test-run",
                "TASK": "research review",
                "OWNER": "codex",
                "CREATED_AT": "2026-05-24T00:00:00Z",
            },
        )

        self.assertNotIn("{{>", rendered)
        self.assertIn("## 判定（Decision）", rendered)
        self.assertIn("<!-- approve、revise、escalate のいずれかを記録します。 -->", rendered)
        self.assertEqual(rendered.count("@dependency-start"), 1)

    def test_research_driven_skill_calls_literature_survey_first(self) -> None:
        """Research-driven run bundles should call literature-survey before research-workflow."""
        skills = suggested_public_skills(None, "research_driven_change")

        self.assertIn("$literature-survey", skills)
        self.assertIn("$research-workflow", skills)
        self.assertLess(
            skills.index("$literature-survey"),
            skills.index("$research-workflow"),
        )

    def test_fixed_implementation_dispatch_uses_typed_route_and_registry_prompt(
        self,
    ) -> None:
        """Eligible fixed packets launch one Spark through the owner dispatch API."""
        sha = "a" * 64
        packet_sha = "b" * 64
        packet_ref = "packet://P3_implementation_route"
        decision_ref = "dsv:" + "d" * 64
        decision = {
            "schema": "agent-canon.decision-sufficiency.v1",
            "decision_id": decision_ref,
            "request_clause_ids": ["RC-1", "RC-2"],
            "H": [
                {
                    "state_id": "h-1",
                    "description": "owner-produced",
                    "evidence_refs": ["evidence:" + sha],
                }
            ],
            "downstream_decision": "owner_edit_validation_route",
            "possible_branches": [
                {
                    "branch_id": "b-1",
                    "condition": "owner policy",
                    "owner": "opaque",
                    "edit_surface": "opaque",
                    "validation": "opaque",
                    "terminal": False,
                }
            ],
            "invariant": {
                "owner": "implementation_route",
                "owner_path": "tools/agent_tools/implementation_route.py",
                "owner_symbol": "route_implementation",
                "edit": "replacement://generic-route",
                "validation": "implementation-execution://v1",
                "request_clause_ids": ["RC-1", "RC-2"],
            },
            "value_of_information": [],
            "route_verdict": {
                "route": "spark_worker",
                "owner_gate": "S6",
                "reason_code": "fixed_contract",
            },
            "irrelevant_unknowns": [],
            "rejection": None,
        }
        decision_sha = hashlib.sha256(
            update_lifecycle_contract.serialize_decision_sufficiency_verdict(decision)
        ).hexdigest()
        packet = {
            "schema_id": "fixed_implementation_packet_v1",
            "packet_version": 1,
            "packet_id": "P3_implementation_route",
            "static_packet_sha256": packet_sha,
            "packet_set_ref": "packet-set://v1",
            "packet_set_sha256": sha,
            "request_clause_ids": ["RC-1", "RC-2"],
            "target_state_contract_ref": "target-state://v1",
            "target_state_contract_sha256": sha,
            "implementation_execution_contract_ref": "implementation-execution://v1",
            "materialization_mode": "one_direct_pass",
            "decision_sufficiency_ref": decision_ref,
            "decision_sufficiency_sha256": decision_sha,
            "abstract_design_frame_ref": "design://abstract-frame",
            "abstract_design_frame_sha256": sha,
            "exact_owner": "implementation_route",
            "exact_write_set": [
                "tools/agent_tools/implementation_route.py",
                "tests/agent_tools/test_implementation_route.py",
            ],
            "forbidden_write_set": [],
            "deletion_replacement_set_ref": "replacement://generic-route",
            "immutable_source_packet_ref": packet_ref,
            "immutable_source_packet_sha256": sha,
            "immutable_source_anchors": [
                {
                    "anchor_purpose": "approved-design",
                    "ref": "design://section-2.4",
                    "selector": "2.4",
                    "sha256": sha,
                    "manifest_sha256": None,
                    "manifest_canonicalization": None,
                    "path_count": None,
                    "base_state": None,
                    "required_predecessor_gate": None,
                    "required_gate": "design-approved",
                },
                {
                    "anchor_purpose": "write-set-manifest",
                    "ref": "manifest://writes",
                    "selector": None,
                    "sha256": None,
                    "manifest_sha256": sha,
                    "manifest_canonicalization": "sorted-paths-v1",
                    "path_count": 2,
                    "base_state": "base-tree",
                    "required_predecessor_gate": "P2:pass",
                    "required_gate": None,
                },
            ],
            "approved_identifiers_and_names": [
                "ImplementationRouteRequest",
                "ImplementationRouteResult",
            ],
            "fixed_public_shape_ids": [
                "fixed_implementation_packet_v1",
                "spark_eligibility_evidence_v1",
                "implementation_route_request_v1",
                "implementation_route_result_v1",
                "structural_design_gap_v1",
                "implementation_feedback_v1",
            ],
            "acceptance_checks": [
                {
                    "command": "python3 -m pytest tests/agent_tools/test_implementation_route.py",
                    "oracle": "pytest exits zero",
                }
            ],
            "static_validation_commands": [
                "python3 -m py_compile tools/agent_tools/implementation_route.py"
            ],
            "unresolved_algorithm_decisions": [],
            "unresolved_api_decisions": [],
            "unresolved_schema_decisions": [],
            "unresolved_oracle_decisions": [],
            "causal_repair_required": False,
            "cross_owner_integration_required": False,
            "deterministic_acceptance_fixed": True,
            "public_shape_fixed": True,
            "dependency_change_required": False,
            "context_continuity_decision_ref": "continuity://P3",
            "capacity_snapshot_ref": "capacity://current",
            "capacity_reservation_ref": "reservation://on-success",
            "owner_gate_id": "implementation_route_gate",
            "parent_lineage_id": "parent/P3",
            "resume_worker_agent_id": None,
            "dependency_import_direction": [
                "implementation_route->model_profile_registry",
                "implementation_route->capacity_handshake",
                "implementation_route->update_lifecycle_contract",
                "implementation_route-X->route",
                "implementation_route-X->capability_route",
                "implementation_route-X->skill_route_catalog",
            ],
            "status": "ready",
        }
        request = {
            "schema_id": "implementation_route_request_v1",
            "request_version": 1,
            "request_clause_ids": ["RC-1", "RC-2"],
            "fixed_implementation_packet_ref": packet_ref,
            "fixed_implementation_packet_sha256": packet_sha,
            "target_state_contract_ref": "target-state://v1",
            "target_state_contract_sha256": sha,
            "implementation_execution_contract_ref": "implementation-execution://v1",
            "decision_sufficiency_ref": decision_ref,
            "decision_sufficiency_sha256": decision_sha,
            "context_continuity_decision_ref": "continuity://P3",
            "capacity_snapshot_ref": "capacity://current",
            "parent_lineage_id": "parent/P3",
            "resume_worker_agent_id": None,
            "structural_design_gap_ref": None,
            "fixed_implementation_packet": packet,
            "fixed_decision_sufficiency": decision,
            "capacity_snapshot": {
                "shape_id": "capacity_snapshot_projection_v1",
                "requested_total_capacity": 26,
                "effective_total_capacity": 26,
                "available_total_capacity": 2,
                "requested_write_capacity": 1,
                "effective_write_capacity": 1,
                "available_write_capacity": 1,
                "input_provenance": [
                    "capacity://configured",
                    "capacity://platform",
                    "capacity://current",
                    "capacity://dag",
                    "capacity://write",
                    "capacity://nested",
                ],
            },
            "continuity_decision": {
                "decision_sufficiency": decision,
                "continue_existing": False,
                "resume_worker_agent_id": None,
                "resume_packet_sha256": None,
                "fresh_packet_cheaper_than_suitable_continuation": True,
                "structural_gap_repair_count": 0,
            },
        }
        calls: list[tuple[str, str]] = []
        dispatch = dispatch_fixed_implementation(
            request,
            "materialize P3",
            lambda role, prompt: calls.append((role, prompt)) or "spark-1",
            workspace_root=PROJECT_ROOT,
        )
        self.assertEqual(dispatch.status, "spawned")
        self.assertEqual(dispatch.spawn_count, 1)
        self.assertEqual(dispatch.owner_gate_count, 1)
        self.assertEqual(dispatch.worker_agent_id, "spark-1")
        self.assertEqual(calls[0][0], "spark_worker")
        self.assertIn("SPARK::", calls[0][1])
        self.assertIsNotNone(dispatch.close_agent_token)
        self.assertEqual(
            dispatch.close_agent_token.arguments,
            {"terminal_agent_id": "spark-1"},
        )

    def test_closeout_provider_orders_child_before_parent(self) -> None:
        """The public closeout validator enforces provider child-before-parent order."""
        ledger = capacity_handshake.CapacityLedger(
            topology=capacity_handshake.DescendantTopologyReadback("run", ())
        )
        snapshot = cast(
            capacity_handshake.CapacitySnapshot,
            SimpleNamespace(remaining_total_slots=2, remaining_write_slots=0),
        )

        def successful_terminal(work_id: str, parent_work_id: str) -> None:
            reservation = capacity_handshake.record_successful_spawn(
                snapshot,
                ledger,
                capacity_handshake.ReadyWorkItem(
                    work_id=work_id,
                    packet_sha256=f"packet://{work_id}",
                    profile_id="spark_implementation_low",
                ),
                spawn_succeeded=True,
                parent_work_id=parent_work_id,
            )
            self.assertEqual(reservation.status, "granted")
            record = ledger.open_records[work_id]
            record.status = capacity_handshake.LifecycleStatus.READBACK_VERIFIED
            record.durable_result_evidence_ref = f"result://{work_id}"
            record.durable_handback = True
            record.descendants_closed = True
            record.close_readback = True

        successful_terminal("parent", "run")
        successful_terminal("child", "parent")
        calls = [
            {
                "agent_id": "child",
                "tool_call_token": {
                    "tool_id": "close_agent",
                    "arguments": {"terminal_agent_id": "child"},
                },
            },
            {
                "agent_id": "parent",
                "tool_call_token": {
                    "tool_id": "close_agent",
                    "arguments": {"terminal_agent_id": "parent"},
                },
            },
        ]
        self.assertEqual(
            task_close.validate_capacity_lifecycle_closeout(ledger, calls),
            (True, ()),
        )


if __name__ == "__main__":
    unittest.main()
