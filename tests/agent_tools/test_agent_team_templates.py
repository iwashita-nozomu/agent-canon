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
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

import capacity_handshake  # noqa: E402
import task_close  # noqa: E402
import update_lifecycle_contract  # noqa: E402
from agent_team import (  # noqa: E402
    RunBundleSpec,
    create_run_bundle,
)
from implementation_dispatch import dispatch_fixed_implementation  # noqa: E402
from writer_target import WriterTarget  # noqa: E402
from manifest_rendering import (  # noqa: E402
    language_review_candidates,
    render_code_template,
    render_template,
    suggested_public_skills,
)
from packets import (  # noqa: E402
    iter_artifacts,
    resolve_active_design_packet_config,
    resolve_cross_cutting_document_packet,
    resolve_role_document_packet,
    _spec_source_root,
)
from team_config import load_task_catalog, load_team_config, resolve_role  # noqa: E402
from task_authority import hash_baseline_bytes  # noqa: E402
from runtime_artifacts import RuntimeArtifactBoundary  # noqa: E402
from checkout_identity import resolve_checkout_identity  # noqa: E402

class AgentTeamTemplateTest(unittest.TestCase):
    """Verify reusable template partial expansion."""

    def test_project_cpp_tests_select_cpp_reviewer_without_python_reviewer(self) -> None:
        """Out-of-tree project C++ tests route only to the native reviewer."""
        candidates = language_review_candidates(
            PROJECT_ROOT,
            ("tests/cpp/CMakeLists.txt", "tests/cpp/adapter.cpp"),
        )
        self.assertEqual(candidates, ("cpp_reviewer", "docs_workflow_steward"))

    def test_cppdev_owned_cpp_paths_select_cpp_reviewer(self) -> None:
        """Native production paths retain the C++ review route."""
        candidates = language_review_candidates(
            PROJECT_ROOT,
            ("cpp/src/model.cpp", "cpp/include/model.hpp"),
        )
        self.assertEqual(candidates, ("cpp_reviewer",))

    def test_packet_helpers_require_explicit_source_and_derived_source(self) -> None:
        """Packet helpers fail closed and resolve derived reads from the source root."""
        config = load_team_config()
        role = resolve_role(config, "change_reviewer")
        with self.assertRaisesRegex(
            RuntimeError,
            r"^runtime_roots_invalid:agentcanon_source_root_missing$",
        ):
            resolve_cross_cutting_document_packet(PROJECT_ROOT)
        with self.assertRaisesRegex(
            RuntimeError,
            r"^runtime_roots_invalid:agentcanon_source_root_missing$",
        ):
            resolve_role_document_packet(
                config=config,
                role=role,
                report_dir=Path(tempfile.gettempdir()) / "agent-canon-packet-test",
                workspace_root=PROJECT_ROOT,
            )
        with self.assertRaisesRegex(
            RuntimeError,
            r"^runtime_roots_invalid:agentcanon_source_root_missing$",
        ):
            _spec_source_root(
                RunBundleSpec(
                    config=config,
                    report_dir=Path(tempfile.gettempdir()) / "agent-canon-packet-test",
                    run_id="packet-test",
                    task="packet test",
                    owner="test",
                    created_at_iso="2026-08-14T00:00:00Z",
                    roles=(),
                    workspace_root=PROJECT_ROOT,
                )
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_dir = Path(tmp_dir) / "reports" / "packet-test"
            workspace_root.mkdir(parents=True)
            cross_cutting = resolve_cross_cutting_document_packet(
                workspace_root,
                PROJECT_ROOT,
            )
            role_packet = resolve_role_document_packet(
                config=config,
                role=role,
                report_dir=report_dir,
                workspace_root=workspace_root,
                agentcanon_source_root=PROJECT_ROOT,
            )
            source_paths = tuple(entry.path for entry in cross_cutting) + tuple(
                entry.path
                for entry in role_packet.read_before_work
                if "workspace doc:" in entry.rationale
                or "cross_cutting_doc:" in entry.rationale
            )
            self.assertTrue(source_paths)
            self.assertTrue(
                all(path.is_relative_to(PROJECT_ROOT) for path in source_paths)
            )
            self.assertTrue(
                all(not path.is_relative_to(workspace_root) for path in source_paths)
            )

    def test_create_run_bundle_uses_atomic_publication_and_rolls_back_injected_write(
        self,
    ) -> None:
        """The public facade leaves no partial run when stage writing fails."""
        config = load_team_config()
        task_catalog = load_task_catalog(config)
        active_packet = resolve_active_design_packet_config(config)

        def build_spec(report_root: Path, run_id: str) -> RunBundleSpec:
            return RunBundleSpec(
                config=config,
                report_dir=report_root / run_id,
                report_root=report_root,
                run_id=run_id,
                task="atomic bundle test",
                owner="test",
                created_at_iso="2026-08-14T00:00:00Z",
                roles=(),
                workspace_root=PROJECT_ROOT,
                agentcanon_source_root=PROJECT_ROOT,
                active_design_packet=active_packet,
                task_catalog=task_catalog,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            report_root.mkdir(parents=True)
            prior_run = report_root / "prior-run"
            prior_run.mkdir()
            prior_artifact = prior_run / "prior.txt"
            prior_artifact.write_bytes(b"prior\n")
            pointer = report_root / ".active_run"
            pointer_bytes = (str(prior_run.resolve()) + "\n").encode("utf-8")
            pointer.write_bytes(pointer_bytes)
            pointer_baseline = report_root / ".active_run.sha256"
            pointer_baseline_bytes = hash_baseline_bytes(pointer_bytes)
            pointer_baseline.write_bytes(pointer_baseline_bytes)

            mismatch_spec = replace(
                build_spec(report_root, "destination-mismatch"),
                report_dir=report_root / "wrong-destination",
            )
            with self.assertRaisesRegex(
                RuntimeError,
                r"^runtime_roots_invalid:report_dir_mismatch$",
            ):
                create_run_bundle(mismatch_spec)
            self.assertFalse(mismatch_spec.report_dir.exists())
            self.assertEqual(pointer.read_bytes(), pointer_bytes)
            self.assertEqual(pointer_baseline.read_bytes(), pointer_baseline_bytes)
            self.assertEqual(prior_artifact.read_bytes(), b"prior\n")
            self.assertEqual(tuple(report_root.glob(".stage-run.*")), ())

            spec = build_spec(report_root, "injected-failure")
            original_write = RuntimeArtifactBoundary.atomic_write_bytes
            atomic_writes = 0

            def fail_second_stage_write(
                boundary: RuntimeArtifactBoundary,
                path: Path,
                payload: bytes,
                *,
                mode: int = 0o600,
            ) -> Path:
                nonlocal atomic_writes
                atomic_writes += 1
                if atomic_writes == 2:
                    raise RuntimeError("injected-stage-write-failure")
                return original_write(boundary, path, payload, mode=mode)

            with patch.object(
                RuntimeArtifactBoundary,
                "atomic_write_bytes",
                new=fail_second_stage_write,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    r"^injected-stage-write-failure$",
                ):
                    create_run_bundle(spec)

            self.assertGreaterEqual(atomic_writes, 2)
            self.assertFalse(spec.report_dir.exists())
            self.assertEqual(pointer.read_bytes(), pointer_bytes)
            self.assertEqual(pointer_baseline.read_bytes(), pointer_baseline_bytes)
            self.assertEqual(prior_artifact.read_bytes(), b"prior\n")
            self.assertEqual(tuple(report_root.glob(".stage-run.*")), ())

            success_spec = build_spec(report_root, "successful-run")
            created_files = create_run_bundle(success_spec)
            self.assertEqual(
                tuple(path for path in created_files if path),
                created_files,
            )
            self.assertTrue(success_spec.report_dir.is_dir())
            self.assertTrue(
                all((success_spec.report_dir / path).is_file() for path in created_files)
            )
            self.assertEqual(tuple(report_root.glob(".stage-run.*")), ())
            self.assertEqual(
                pointer.read_text(encoding="utf-8"),
                str(success_spec.report_dir.resolve()) + "\n",
            )
            self.assertEqual(prior_artifact.read_bytes(), b"prior\n")

    def test_code_template_renderer_returns_materializable_python_source(self) -> None:
        """The code owner exposes a parseable module/class/function source."""
        rendered = render_code_template("python/docstring_template.py")

        self.assertIn("class ExampleState", rendered)
        self.assertIn("def build_example_state", rendered)
        self.assertIn("Args:", rendered)
        self.assertIn("Ownership:", rendered)
        self.assertNotIn("return None", rendered)

    def test_code_template_renderer_works_from_repo_root_package_route(self) -> None:
        """リポジトリ root の canonical package invocation が source を読み戻せます."""
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

    def test_template_renderer_uses_explicit_source_root(self) -> None:
        """Derived preparation reads templates from the selected source root only."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_root = Path(tmp_dir)
            template_root = source_root / "templates" / "agents"
            partial_root = template_root / "_partials"
            partial_root.mkdir(parents=True)
            (partial_root / "source_marker.md").write_text(
                "source-marker={{VALUE}}\n", encoding="utf-8"
            )
            (template_root / "source_template.md").write_text(
                "before\n{{> source_marker}}after\n", encoding="utf-8"
            )

            rendered = render_template(
                "source_template.md",
                {"VALUE": "selected-source"},
                source_root=source_root,
            )

        self.assertEqual(rendered, "before\nsource-marker=selected-source\nafter\n")

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

    def test_optional_review_templates_are_materialized_only_when_selected(self) -> None:
        """Core bundle artifacts stay available without empty review templates."""
        config = load_team_config()
        packet = resolve_active_design_packet_config(config)
        core_only = iter_artifacts(config, ())
        self.assertIn("team_manifest.yaml", core_only)
        self.assertNotIn(packet.design_artifact, core_only)
        self.assertNotIn(packet.design_review_artifact, core_only)
        selected = iter_artifacts(
            config,
            (resolve_role(config, "change_reviewer"),),
            packet,
        )
        self.assertIn("change_review.md", selected)
        self.assertNotIn("python_review.md", selected)

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
        missing_target = dispatch_fixed_implementation(
            request,
            "materialize P3",
            lambda role, prompt: calls.append((role, prompt)) or "missing-target",
            workspace_root=PROJECT_ROOT,
        )
        self.assertEqual(missing_target.status, "blocked")
        self.assertEqual(
            missing_target.owner_gate_id,
            "writer_target:required_before_spawn",
        )
        identity = resolve_checkout_identity(PROJECT_ROOT).as_dict()
        target = WriterTarget(
            str(PROJECT_ROOT),
            identity["branch"],
            identity["remote"],
            ("tools/agent_tools",),
        )
        math_blocked = dispatch_fixed_implementation(
            request,
            "materialize P3 math repair",
            lambda role, prompt: "must-not-spawn",
            workspace_root=PROJECT_ROOT,
            writer_target=target,
            selected_skills=("computational-optimization",),
        )
        self.assertEqual(math_blocked.status, "blocked")
        self.assertEqual(math_blocked.owner_gate_id, "math_packet_missing")
        nonmath_dispatch = dispatch_fixed_implementation(
            request,
            "materialize P3 math repair",
            lambda role, prompt: "must-not-spawn",
            workspace_root=PROJECT_ROOT,
            writer_target=target,
            selected_skills=(),
        )
        self.assertEqual(nonmath_dispatch.status, "spawned")
        with patch(
            "implementation_dispatch.resolve_checkout_identity",
            side_effect=AssertionError("checkout identity must be reused"),
        ):
            snapshot_dispatch = dispatch_fixed_implementation(
                request,
                "materialize P3",
                lambda role, prompt: "snapshot-worker",
                workspace_root=PROJECT_ROOT,
                writer_target=target,
                checkout_identity=identity,
            )
        self.assertEqual(snapshot_dispatch.status, "spawned")
        self.assertIn(identity["head"], snapshot_dispatch.prompt_capsule.body)
        dispatch = dispatch_fixed_implementation(
            request,
            "materialize P3",
            lambda role, prompt: calls.append((role, prompt)) or "spark-1",
            workspace_root=PROJECT_ROOT,
            writer_target=target,
        )
        self.assertEqual(dispatch.status, "spawned")
        self.assertEqual(dispatch.spawn_count, 1)
        self.assertEqual(dispatch.owner_gate_count, 1)
        self.assertEqual(dispatch.worker_agent_id, "spark-1")
        self.assertEqual(calls[0][0], "spark_worker")
        self.assertIn("SPARK::", calls[0][1])
        self.assertIn("checkout_identity", calls[0][1])
        self.assertIn("cwd", calls[0][1])
        self.assertIn("git_root", calls[0][1])
        self.assertIsNotNone(dispatch.close_agent_token)
        self.assertEqual(
            dispatch.close_agent_token.arguments,
            {"terminal_agent_id": "spark-1"},
        )
        blocked = dispatch_fixed_implementation(
            request,
            "materialize P3",
            lambda role, prompt: None,
            workspace_root=PROJECT_ROOT,
            writer_target=target,
        )
        self.assertEqual(blocked.status, "blocked")
        self.assertEqual(blocked.owner_gate_id, "WRITE_SUBAGENT_AUTHORIZATION=required")

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
