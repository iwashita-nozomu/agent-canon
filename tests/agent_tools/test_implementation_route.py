# @dependency-start
# contract test
# responsibility Tests fail-closed fixed-packet Spark eligibility, identity, continuity, and queue routing.
# upstream implementation ../../tools/agent_tools/implementation_route.py implements typed routing
# upstream implementation ../../tools/agent_tools/model_profile_registry.py owns Decision Sufficiency and profiles
# upstream implementation ../../tools/agent_tools/capacity_handshake.py owns capacity evidence
# @dependency-end

from __future__ import annotations

import dataclasses
import hashlib

from tools.agent_tools import capacity_handshake
from tools.agent_tools import implementation_route as route
from tools.agent_tools import update_lifecycle_contract

SHA = "a" * 64
PACKET_SHA = "b" * 64
PACKET_REF = "packet://P3_implementation_route"
DECISION_REF = "dsv:" + "d" * 64
WRITE_SET = (
    "tools/agent_tools/implementation_route.py",
    "tests/agent_tools/test_implementation_route.py",
)
VALIDATION = (
    "python3 -m pytest tests/agent_tools/test_implementation_route.py",
    "python3 -m py_compile tools/agent_tools/implementation_route.py",
)


def _packet() -> dict[str, object]:
    return {
        "schema_id": "fixed_implementation_packet_v1",
        "packet_version": 1,
        "packet_id": "P3_implementation_route",
        "static_packet_sha256": PACKET_SHA,
        "packet_set_ref": "packet-set://v1",
        "packet_set_sha256": SHA,
        "request_clause_ids": ["RC-1", "RC-2"],
        "target_state_contract_ref": "target-state://v1",
        "target_state_contract_sha256": SHA,
        "implementation_execution_contract_ref": "implementation-execution://v1",
        "materialization_mode": "one_direct_pass",
        "decision_sufficiency_ref": DECISION_REF,
        "decision_sufficiency_sha256": _decision_sha(_decision()),
        "abstract_design_frame_ref": "design://abstract-frame",
        "abstract_design_frame_sha256": SHA,
        "exact_owner": "implementation_route",
        "exact_write_set": list(WRITE_SET),
        "forbidden_write_set": [],
        "deletion_replacement_set_ref": "replacement://generic-route",
        "immutable_source_packet_ref": PACKET_REF,
        "immutable_source_packet_sha256": SHA,
        "immutable_source_anchors": [
            {
                "anchor_purpose": "approved-design",
                "ref": "design://section-2.4",
                "selector": "2.4",
                "sha256": SHA,
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
                "manifest_sha256": SHA,
                "manifest_canonicalization": "sorted-paths-v1",
                "path_count": 2,
                "base_state": "base-tree",
                "required_predecessor_gate": "P2:pass",
                "required_gate": None,
            },
        ],
        "approved_identifiers_and_names": ["ImplementationRouteRequest", "ImplementationRouteResult"],
        "fixed_public_shape_ids": [
            "fixed_implementation_packet_v1",
            "spark_eligibility_evidence_v1",
            "implementation_route_request_v1",
            "implementation_route_result_v1",
            "structural_design_gap_v1",
            "implementation_feedback_v1",
        ],
        "acceptance_checks": [{"command": VALIDATION[0], "oracle": "pytest exits zero"}],
        "static_validation_commands": [VALIDATION[1]],
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


def _decision() -> dict[str, object]:
    return {
        "schema": "agent-canon.decision-sufficiency.v1",
        "decision_id": DECISION_REF,
        "request_clause_ids": ["RC-1", "RC-2"],
        "H": [{"state_id": "h-1", "description": "owner-produced", "evidence_refs": ["evidence:" + SHA]}],
        "downstream_decision": "owner_edit_validation_route",
        "possible_branches": [
            {"branch_id": "b-1", "condition": "owner policy", "owner": "opaque", "edit_surface": "opaque", "validation": "opaque", "terminal": False},
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
        "route_verdict": {"route": "spark_worker", "owner_gate": "S6", "reason_code": "fixed_contract"},
        "irrelevant_unknowns": [],
        "rejection": None,
    }


def _decision_sha(decision: dict[str, object]) -> str:
    return hashlib.sha256(
        update_lifecycle_contract.serialize_decision_sufficiency_verdict(decision)
    ).hexdigest()


def _capacity(available: int = 2, write: int = 1) -> dict[str, object]:
    return {
        "shape_id": "capacity_snapshot_projection_v1",
        "requested_total_capacity": 26,
        "effective_total_capacity": 26,
        "available_total_capacity": available,
        "requested_write_capacity": 1,
        "effective_write_capacity": 1,
        "available_write_capacity": write,
        "input_provenance": ["capacity://configured", "capacity://platform", "capacity://current", "capacity://dag", "capacity://write", "capacity://nested"],
    }


def _continuity(*, resume: str | None = None, resume_sha: str | None = None, repair_count: int = 0) -> dict[str, object]:
    return {
        "decision_sufficiency": _decision(),
        "continue_existing": resume is not None,
        "resume_worker_agent_id": resume,
        "resume_packet_sha256": resume_sha,
        "fresh_packet_cheaper_than_suitable_continuation": True,
        "structural_gap_repair_count": repair_count,
    }


def _request(packet: dict[str, object], *, capacity=None, continuity=None, gap=None, decision=None) -> dict[str, object]:
    decision = decision or _decision()
    decision_sha256 = _decision_sha(decision)
    packet["decision_sufficiency_ref"] = DECISION_REF
    packet["decision_sufficiency_sha256"] = decision_sha256
    continuity = continuity or _continuity()
    continuity["decision_sufficiency"] = decision
    return {
        "schema_id": "implementation_route_request_v1",
        "request_version": 1,
        "request_clause_ids": ["RC-1", "RC-2"],
        "fixed_implementation_packet_ref": PACKET_REF,
        "fixed_implementation_packet_sha256": PACKET_SHA,
        "target_state_contract_ref": "target-state://v1",
        "target_state_contract_sha256": SHA,
        "implementation_execution_contract_ref": "implementation-execution://v1",
        "decision_sufficiency_ref": DECISION_REF,
        "decision_sufficiency_sha256": decision_sha256,
        "context_continuity_decision_ref": "continuity://P3",
        "capacity_snapshot_ref": "capacity://current",
        "parent_lineage_id": "parent/P3",
        "resume_worker_agent_id": continuity["resume_worker_agent_id"],
        "structural_design_gap_ref": gap,
        "fixed_implementation_packet": packet,
        "fixed_decision_sufficiency": decision,
        "capacity_snapshot": capacity or _capacity(),
        "continuity_decision": continuity,
    }


class _Registry:
    def by_profile(self, profile_id: str):
        assert profile_id == "spark_implementation_low"
        return object()


def _registry(monkeypatch) -> None:
    monkeypatch.setattr(route.model_profile_registry, "load_model_profile_registry", lambda: _Registry())


def test_closed_fixed_packet_routes_to_one_spark_and_preserves_evidence(monkeypatch) -> None:
    _registry(monkeypatch)
    packet = _packet()
    result = route.route_implementation(_request(packet))
    assert result.status == "completed"
    assert result.selected_agent_type == "spark_worker"
    assert result.selected_profile_id == "spark_implementation_low"
    assert result.capacity_action == "reserve_on_successful_spawn"
    assert result.exact_write_set == WRITE_SET
    assert len(result.source_anchors) == 2
    assert result.source_anchors[1].manifest_canonicalization == "sorted-paths-v1"
    assert result.acceptance_checks[0].command == VALIDATION[0]
    assert result.static_validation_commands == (VALIDATION[1],)
    eligibility = route.resolve_implementation_candidate(packet, _capacity(), _continuity())
    assert eligibility.evidence is not None
    assert eligibility.evidence.evidence_refs[3:8] == (
        DECISION_REF,
        f"sha256:{_decision_sha(_decision())}",
        "implementation_route",
        "replacement://generic-route",
        "implementation-execution://v1",
    )


def test_unknown_missing_empty_or_mismatched_packet_evidence_fails_before_profile(monkeypatch) -> None:
    selected = False

    def fail_if_selected():
        nonlocal selected
        selected = True
        return _Registry()

    monkeypatch.setattr(route.model_profile_registry, "load_model_profile_registry", fail_if_selected)
    cases = []
    unknown = _packet()
    unknown["fallback"] = "worker"
    cases.append(unknown)
    missing = _packet()
    del missing["immutable_source_anchors"]
    cases.append(missing)
    empty = _packet()
    empty["acceptance_checks"] = []
    cases.append(empty)
    for packet in cases:
        result = route.route_implementation(_request(packet))
        assert result.status == "blocked"
        assert result.failure is not None
        assert result.failure.code == "stale_or_malformed_packet_evidence"
    mismatch = _request(_packet())
    mismatch["target_state_contract_sha256"] = "c" * 64
    assert route.route_implementation(mismatch).status == "blocked"
    assert not selected


def test_saturation_queues_same_fixed_packet(monkeypatch) -> None:
    _registry(monkeypatch)
    result = route.route_implementation(_request(_packet(), capacity=_capacity(0, 0)))
    assert result.status == "queued"
    assert result.capacity_action == "queue"
    assert result.packet_sha256 == PACKET_SHA


def test_one_repaired_structural_gap_reuses_same_spark(monkeypatch) -> None:
    _registry(monkeypatch)
    continuity = _continuity(resume="spark-1", resume_sha=PACKET_SHA, repair_count=1)
    result = route.route_implementation(_request(_packet(), continuity=continuity, gap="gap://one"))
    assert result.status == "completed"
    assert result.capacity_action == "continue_existing"
    assert result.resume_worker_agent_id == "spark-1"


def test_second_gap_or_different_packet_never_selects_second_worker(monkeypatch) -> None:
    _registry(monkeypatch)
    continuity = _continuity(resume="spark-1", resume_sha="c" * 64, repair_count=2)
    request = _request(_packet(), continuity=continuity, gap="gap://two")
    result = route.route_implementation(request)
    assert result.status == "blocked"
    assert result.selected_agent_type == "none"


def test_typed_capacity_snapshot_requires_complete_readback(monkeypatch, tmp_path) -> None:
    _registry(monkeypatch)
    derivation = capacity_handshake.DeclaredTeamTopologyDerivation(
        1,
        "topology",
        "roles",
        "reviewer",
        "producer",
        "final",
        (),
        (),
        (capacity_handshake.DeclaredFamilyCapacity("f", ("d",), (), (), 1, 0, 1),),
    )
    node = capacity_handshake.TopologyCapacityNode("p", "parent", (), None, 1, 0, (), ())
    witness = capacity_handshake.TopologyCapacityWitness(
        declared_team_topology_sha256=SHA,
        node_records=(node,),
        legal_frontier_ids=("p",),
        requested_total_capacity=1,
        workflow_dag_peak_demand=1,
        nested_reservation_count=0,
        workflow_dag_budget=1,
        write_scope_cap=1,
        derivation=derivation,
    )
    config = tmp_path / "config.toml"
    config.write_text("[agents]\nmax_threads = 1\n", encoding="utf-8")
    contract = capacity_handshake.load_startup_contract(derivation, witness, str(config))
    snapshot = capacity_handshake.make_session_snapshot(contract, workflow_dag_demand=1, write_scope_cap=1)
    result = route.route_implementation(_request(_packet(), capacity=snapshot))
    assert result.status == "completed"


def test_owner_verdict_policy_fields_are_not_recomputed(monkeypatch) -> None:
    _registry(monkeypatch)
    decision = _decision()
    decision["H"] = []
    decision["possible_branches"] = [{"branch_id": "opaque", "owner": "different"}]
    decision["value_of_information"] = [{"decision_value": "changes_route"}]
    decision["route_verdict"] = {"route": "worker"}
    result = route.route_implementation(_request(_packet(), decision=decision))
    assert result.status == "completed"


def test_missing_or_mismatched_owner_verdict_binding_fails_closed(monkeypatch) -> None:
    _registry(monkeypatch)
    malformed = _request(_packet())
    decision = malformed["fixed_decision_sufficiency"]
    assert isinstance(decision, dict)
    decision["schema"] = "decision_sufficiency_record_v1"
    continuity = malformed["continuity_decision"]
    assert isinstance(continuity, dict)
    continuity["decision_sufficiency"] = decision
    assert route.route_implementation(malformed).status == "blocked"

    for field, value in (
        ("owner", "other-owner"),
        ("edit", "replacement://other"),
        ("validation", "implementation-execution://other"),
    ):
        decision = _decision()
        invariant = decision["invariant"]
        assert isinstance(invariant, dict)
        invariant[field] = value
        result = route.route_implementation(_request(_packet(), decision=decision))
        assert result.status == "blocked"
    assert result.status == "blocked"
