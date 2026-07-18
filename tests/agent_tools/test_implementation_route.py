from __future__ import annotations

import dataclasses

import pytest

from tools.agent_tools import implementation_route as impl
from tools.agent_tools import model_profile_registry


def _fake_registry(monkeypatch):
    class _Registry:
        def by_profile(self, profile_id: str):
            if profile_id != "spark_implementation_low":
                raise model_profile_registry.StructuralDesignGap()

    class _Profile:
        pass

    monkeypatch.setattr(impl.model_profile_registry, "load_model_profile_registry", lambda: _Registry())
    return _Registry()


def _packet_payload(
    *,
    unresolved=(),
    exact_write_set=("tools/agent_tools/implementation_route.py", "tests/agent_tools/test_implementation_route.py"),
    dep_dirs=(
        "implementation_route->model_profile_registry",
        "implementation_route->capacity_handshake",
        "implementation_route-X->route",
        "implementation_route-X->capability_route",
        "implementation_route-X->skill_route_catalog",
    ),
):
    return {
        "packet_version": 1,
        "packet_id": "P3_implementation_route",
        "static_packet_sha256": "f2514c31409a5be8e04fedc67e2b6f76497213e28a0136967ebc6d1f72d64eb8",
        "packet_set_ref": "design://packet-set",
        "packet_set_sha256": "e1",
        "request_clause_ids": (
            "RC-01",
            "RC-02",
        ),
        "target_state_contract_ref": "documents/target_state.json",
        "target_state_contract_sha256": "tsha",
        "implementation_execution_contract_ref": "implementation_execution_contract_v1",
        "materialization_mode": "one_direct_pass",
        "decision_sufficiency_ref": "P3_implementation_route_decision_sufficiency_v1",
        "decision_sufficiency_sha256": "dsha",
        "abstract_design_frame_ref": "documents/design/codex-spark-implementation-routing.md",
        "exact_owner": "implementation_route",
        "exact_write_set": exact_write_set,
        "forbidden_write_set": (),
        "deletion_replacement_set_ref": "repl",
        "immutable_source_packet_ref": "fix-payload:impl-route",
        "immutable_source_packet_sha256": "ips",
        "approved_identifiers_and_names": ("ImplementationRouteRequest", "ImplementationRouteResult"),
        "fixed_public_shape_ids": (
            "fixed_implementation_packet_v1",
            "spark_eligibility_evidence_v1",
            "implementation_route_request_v1",
            "implementation_route_result_v1",
            "structural_design_gap_v1",
            "implementation_feedback_v1",
        ),
        "acceptance_checks": (),
        "static_validation_commands": ("python3 -m py_compile tools/agent_tools/implementation_route.py",),
        "unresolved_algorithm_decisions": tuple(unresolved),
        "unresolved_api_decisions": tuple(unresolved),
        "unresolved_schema_decisions": tuple(unresolved),
        "unresolved_oracle_decisions": tuple(unresolved),
        "causal_repair_required": False,
        "cross_owner_integration_required": False,
        "deterministic_acceptance_fixed": True,
        "public_shape_fixed": True,
        "dependency_change_required": False,
        "context_continuity_decision_ref": "design://continuity",
        "capacity_snapshot_ref": "runtime://current-spawn/P3_implementation_route",
        "capacity_reservation_ref": "runtime://current-spawn/P2_capacity_handshake",
        "owner_gate_id": "implementation_route_gate",
        "parent_lineage_id": "sol-parent/model-team-capacity/404678e1/P3",
        "dependency_import_direction": dep_dirs,
    }


def _request_payload(
    packet,
    *,
    continuity=None,
    snapshot=None,
    fixed_decision=None,
    resume_worker=None,
    structural_design_gap_ref=None,
):
    return {
        "request_version": 1,
        "request_clause_ids": ("RC-01", "RC-02"),
        "fixed_implementation_packet_ref": "fix:P3",
        "fixed_implementation_packet_sha256": packet["static_packet_sha256"],
        "target_state_contract_ref": "documents/target_state.json",
        "target_state_contract_sha256": "tsha",
        "implementation_execution_contract_ref": "implementation_execution_contract_v1",
        "decision_sufficiency_ref": "P3_implementation_route_decision_sufficiency_v1",
        "decision_sufficiency_sha256": "dsha",
        "context_continuity_decision_ref": "design://continuity",
        "capacity_snapshot_ref": "runtime://current-spawn/P3_implementation_route",
        "parent_lineage_id": "sol-parent/model-team-capacity/404678e1/P3",
        "resume_worker_agent_id": resume_worker,
        "structural_design_gap_ref": structural_design_gap_ref,
        "fixed_implementation_packet": packet,
        "fixed_decision_sufficiency": fixed_decision,
        "continuity_decision": continuity,
        "capacity_snapshot": snapshot,
    }


def test_resolve_candidate_prefers_spark_when_resolvable(monkeypatch):
    _fake_registry(monkeypatch)
    packet = _packet_payload()
    req = {
        "record_id": "ds-1",
        "plausible_state_ids": (
            "suitable_reasoning_context_exists",
            "fresh_fixed_spark_context_is_cheaper",
            "same_packet_spark_context_already_launched",
        ),
        "fixed_action": dataclasses.asdict(
            impl.FixedImplementationPacket(
                packet_version=1,
                packet_id="x",
                static_packet_sha256="y",
                packet_set_ref="",
                packet_set_sha256="",
                request_clause_ids=(),
                target_state_contract_ref="",
                target_state_contract_sha256="",
                implementation_execution_contract_ref="",
                materialization_mode="one_direct_pass",
                decision_sufficiency_ref="",
                decision_sufficiency_sha256="",
                abstract_design_frame_ref="",
                exact_owner="implementation_route",
                exact_write_set=(),
                forbidden_write_set=(),
                deletion_replacement_set_ref="",
                immutable_source_packet_ref="",
                immutable_source_packet_sha256="",
                immutable_source_anchors=(),
                approved_identifiers_and_names=(),
                fixed_public_shape_ids=(),
                acceptance_checks=(),
                static_validation_commands=(),
                unresolved_algorithm_decisions=(),
                unresolved_api_decisions=(),
                unresolved_schema_decisions=(),
                unresolved_oracle_decisions=(),
                causal_repair_required=False,
                cross_owner_integration_required=False,
                deterministic_acceptance_fixed=True,
                public_shape_fixed=True,
                dependency_change_required=False,
                context_continuity_decision_ref="",
                capacity_snapshot_ref="",
                capacity_reservation_ref="",
                owner_gate_id="implementation_route_gate",
                parent_lineage_id="",
            )
        ),
        "action_equivalence": "identical",
        "further_investigation": "forbidden",
        "authorized_evidence_request_ids": (),
    }
    decision = impl.resolve_implementation_candidate(
        packet,
        {"requested_capacity": 2, "configured_max_threads": 2},
        {
            "decision_sufficiency": req,
            "fresh_packet_cheaper_than_suitable_continuation": True,
        },
    )
    assert decision.eligibility == "eligible"
    assert decision.selected_agent_type == "spark_worker"
    assert decision.capacity_action == "reserve"


def test_route_implementation_continuity_gap_reuses_same_spark(monkeypatch):
    _fake_registry(monkeypatch)
    packet = _packet_payload()
    req = _request_payload(
        packet,
        continuity={
            "decision_sufficiency": {
                "record_id": "ds-1",
                "plausible_state_ids": (),
                "fixed_action": {},
                "action_equivalence": "identical",
                "further_investigation": "forbidden",
                "authorized_evidence_request_ids": (),
            },
            "continue_existing": True,
            "resume_packet_sha256": packet["static_packet_sha256"],
            "resume_worker_agent_id": "spark-1",
            "fresh_packet_cheaper_than_suitable_continuation": True,
        },
        resume_worker="spark-1",
        structural_design_gap_ref="gd1",
    )
    result = impl.route_implementation(req)
    assert result.status == "completed"
    assert result.selected_agent_type == "spark_worker"
    assert result.capacity_action == "continue_existing"
    assert result.resume_worker_agent_id == "spark-1"


def test_route_implementation_queues_when_saturated(monkeypatch):
    _fake_registry(monkeypatch)
    packet = _packet_payload()
    req = _request_payload(
        packet,
        continuity={
            "decision_sufficiency": {
                "record_id": "ds-1",
                "plausible_state_ids": (),
                "fixed_action": {},
                "action_equivalence": "identical",
                "further_investigation": "forbidden",
                "authorized_evidence_request_ids": (),
            },
            "fresh_packet_cheaper_than_suitable_continuation": True,
        },
        snapshot={
            "requested_capacity": 1,
            "configured_max_threads": 1,
            "currently_available_runtime_slots": 0,
        },
    )
    result = impl.route_implementation(req)
    assert result.status == "queued"
    assert result.capacity_action == "queue"
    assert result.selected_agent_type == "spark_worker"


def test_route_implementation_stale_snapshot_without_packet_is_rejected():
    req = {
        "request_version": 1,
        "request_clause_ids": ("RC-01",),
        "fixed_implementation_packet_ref": "fix:P3",
        "fixed_implementation_packet_sha256": "x",
        "target_state_contract_ref": "documents/target_state.json",
        "target_state_contract_sha256": "tsha",
        "implementation_execution_contract_ref": "implementation_execution_contract_v1",
        "decision_sufficiency_ref": "P3_implementation_route_decision_sufficiency_v1",
        "decision_sufficiency_sha256": "dsha",
        "context_continuity_decision_ref": "design://continuity",
        "capacity_snapshot_ref": "runtime://current-spawn/P3_implementation_route",
        "parent_lineage_id": "sol-parent/model-team-capacity/404678e1/P3",
        "resume_worker_agent_id": None,
        "fixed_decision_sufficiency": None,
    }
    result = impl.route_implementation(req)
    assert result.status == "blocked"
    assert result.failure is not None
    assert result.failure.code == "stale_packet"


def test_route_implementation_rejects_mismatched_resume_after_gap(monkeypatch):
    _fake_registry(monkeypatch)
    packet = _packet_payload()
    req = _request_payload(
        packet,
        continuity={
            "decision_sufficiency": {
                "record_id": "ds-1",
                "plausible_state_ids": (),
                "fixed_action": {},
                "action_equivalence": "identical",
                "further_investigation": "forbidden",
                "authorized_evidence_request_ids": (),
            },
            "continue_existing": True,
            "resume_worker_id": "spark-1",
            "resume_packet_sha256": "other",
            "fresh_packet_cheaper_than_suitable_continuation": True,
        },
        resume_worker="spark-1",
    )
    result = impl.route_implementation(req)
    assert result.status == "blocked"
    assert result.failure is not None
    assert result.failure.code == "same_worker_resume_mismatch"
