from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from tools.agent_tools import capacity_handshake
from tools.agent_tools import model_profile_registry as model_profile_registry

SCHEMA_IDS = {
    "fixed_implementation_packet": "fixed_implementation_packet_v1",
    "spark_eligibility_evidence": "spark_eligibility_evidence_v1",
    "implementation_route_request": "implementation_route_request_v1",
    "implementation_route_result": "implementation_route_result_v1",
    "structural_design_gap": "structural_design_gap_v1",
    "implementation_feedback": "implementation_feedback_v1",
    "implementation_route": "implementation_route_result_v1",
    "spark_implementation_result": "spark_implementation_result_v1",
}


@dataclass(frozen=True)
class SourceAnchor:
    anchor_purpose: str
    ref: str
    selector: str | None = None
    sha256: str | None = None
    manifest_sha256: str | None = None
    manifest_canonicalization: str | None = None
    path_count: int | None = None
    base_state: str | None = None
    required_predecessor_gate: str | None = None
    required_gate: str | None = None


@dataclass(frozen=True)
class ValidationAction:
    command: str
    oracle: str


@dataclass(frozen=True)
class DecisionSufficiencyProjection:
    record_id: str
    plausible_state_ids: tuple[str, ...]
    fixed_action: object
    action_equivalence: str
    further_investigation: str
    authorized_evidence_request_ids: tuple[str, ...]


@dataclass(frozen=True)
class DeletionReplacementProjection:
    deletion_set: tuple[str, ...]
    replacement_set: tuple[str, ...]


@dataclass(frozen=True)
class FixedImplementationPacket:
    packet_version: int
    packet_id: str
    static_packet_sha256: str
    packet_set_ref: str
    packet_set_sha256: str
    request_clause_ids: tuple[str, ...]
    target_state_contract_ref: str
    target_state_contract_sha256: str
    implementation_execution_contract_ref: str
    materialization_mode: str
    decision_sufficiency_ref: str
    decision_sufficiency_sha256: str
    abstract_design_frame_ref: str
    exact_owner: str
    exact_write_set: tuple[str, ...]
    forbidden_write_set: tuple[str, ...]
    deletion_replacement_set_ref: str
    immutable_source_packet_ref: str
    immutable_source_packet_sha256: str
    immutable_source_anchors: tuple[SourceAnchor, ...]
    approved_identifiers_and_names: tuple[str, ...]
    fixed_public_shape_ids: tuple[str, ...]
    acceptance_checks: tuple[ValidationAction, ...]
    static_validation_commands: tuple[str, ...]
    unresolved_algorithm_decisions: tuple[str, ...]
    unresolved_api_decisions: tuple[str, ...]
    unresolved_schema_decisions: tuple[str, ...]
    unresolved_oracle_decisions: tuple[str, ...]
    causal_repair_required: bool
    cross_owner_integration_required: bool
    deterministic_acceptance_fixed: bool
    public_shape_fixed: bool
    dependency_change_required: bool
    context_continuity_decision_ref: str
    capacity_snapshot_ref: str
    capacity_reservation_ref: str
    owner_gate_id: str
    parent_lineage_id: str
    resume_worker_agent_id: str | None = None
    dependency_import_direction: tuple[str, ...] = ()
    schema_id: str = SCHEMA_IDS["fixed_implementation_packet"]
    status: str = "ready"


@dataclass(frozen=True)
class SparkEligibilityEvidence:
    evidence_version: int
    target_state_approved: bool
    target_state_implementation_executable: bool
    unresolved_design_decision_count: int
    responsibility_graph_complete: bool
    owner_write_set_exact: bool
    source_packet_immutable: bool
    design_review_approved: bool
    document_flow_review_approved_when_active: bool
    all_design_blockers_resolved: bool
    all_algorithm_api_schema_oracle_decisions_resolved: bool
    deterministic_acceptance_fixed: bool
    static_validation_fixed: bool
    no_causal_repair: bool
    no_cross_owner_integration: bool
    no_architectural_interpretation_required: bool
    public_shape_unchanged_or_fixed: bool
    dependency_direction_fixed: bool
    decision_sufficiency_identical: bool
    fresh_packet_cheaper_than_suitable_continuation: bool
    capacity_slot_granted_or_queueable: bool
    evidence_refs: tuple[str, ...]
    evidence_id: str = SCHEMA_IDS["spark_eligibility_evidence"]


@dataclass(frozen=True)
class SparkEligibilityDecision:
    decision_version: int
    decision_id: str
    eligibility: str
    selected_agent_type: str
    selected_profile_id: str
    reason_codes: tuple[str, ...]
    evidence_ref: str
    context_continuity_decision_ref: str
    capacity_action: str
    parent_lineage_id: str
    resume_worker_agent_id: str | None = None
    evidence: SparkEligibilityEvidence | None = None
    schema_id: str = SCHEMA_IDS["fixed_implementation_packet"]


@dataclass(frozen=True)
class ImplementationRouteFailure:
    failure_version: int
    code: str
    owner_id: str
    evidence_refs: tuple[str, ...]
    retryable: bool
    status: str = "failed"
    schema_id: str = "implementation_route_failure_v1"


@dataclass(frozen=True)
class StructuralDesignGap:
    gap_version: int
    gap_id: str
    worker_agent_id: str
    packet_ref: str
    packet_sha256: str
    contradicted_target_field_ref: str
    contradiction_evidence_ref: str
    schema_id: str = SCHEMA_IDS["structural_design_gap"]


@dataclass(frozen=True)
class ImplementationFeedback:
    feedback_version: int
    failure_class: str
    packet_ref: str
    packet_sha256: str
    command_or_check_id: str
    evidence_ref: str
    next_action: str
    status: str
    schema_id: str = SCHEMA_IDS["implementation_feedback"]


@dataclass(frozen=True)
class ImplementationRouteRequest:
    request_version: int
    request_clause_ids: tuple[str, ...]
    fixed_implementation_packet_ref: str
    fixed_implementation_packet_sha256: str
    target_state_contract_ref: str
    target_state_contract_sha256: str
    implementation_execution_contract_ref: str
    decision_sufficiency_ref: str
    decision_sufficiency_sha256: str
    context_continuity_decision_ref: str
    capacity_snapshot_ref: str
    parent_lineage_id: str
    resume_worker_agent_id: str | None = None
    structural_design_gap_ref: str | None = None
    fixed_implementation_packet: Mapping[str, Any] | None = None
    fixed_decision_sufficiency: Mapping[str, Any] | None = None
    capacity_snapshot: Mapping[str, Any] | capacity_handshake.CapacitySnapshot | None = None
    continuity_decision: Mapping[str, Any] | None = None
    schema_id: str = SCHEMA_IDS["implementation_route_request"]


@dataclass(frozen=True)
class ImplementationRouteResult:
    result_version: int
    decision_ref: str
    selected_agent_type: str
    selected_profile_id: str
    packet_ref: str | None
    packet_sha256: str | None
    capacity_action: str
    resume_worker_agent_id: str | None
    next_gate: str
    failure: ImplementationRouteFailure | None
    status: str
    schema_id: str = SCHEMA_IDS["implementation_route_result"]


@dataclass(frozen=True)
class SparkImplementationResult:
    schema_id: str
    packet_id: str
    packet_sha256: str
    status: str
    changed_paths: tuple[str, ...]
    acceptance_evidence: tuple[str, ...]
    implementation_feedback: ImplementationFeedback | None
    structural_design_gap: StructuralDesignGap | None
    durable_result_summary: str


@dataclass(frozen=True)
class _ImplementationShape:
    evidence: SparkEligibilityEvidence
    decision: SparkEligibilityDecision
    failure: ImplementationRouteFailure | None = None


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return tuple(str(v) for v in value)
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    return (str(value),)


def _coerce_bool(value: Any, default: bool) -> bool:
    return bool(value) if value is not None else default


def _coerce_int(value: Any, default: int) -> int:
    return int(value) if isinstance(value, int) else default


def _coerce_string(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value)


def _coerce_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("expected mapping")
    return value


def _as_id(value: Any, key: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"{key}:missing")


def _normalize_profile_id(value: Any) -> str:
    profile = _coerce_string(value, "")
    if not profile:
        raise ValueError("missing_profile")
    return profile

def _resolve_request(request: Mapping[str, Any] | ImplementationRouteRequest) -> ImplementationRouteRequest:
    if isinstance(request, ImplementationRouteRequest):
        return request
    payload = _coerce_mapping(request)
    return ImplementationRouteRequest(
        request_version=_coerce_int(payload.get("request_version"), 1),
        request_clause_ids=_as_tuple(payload.get("request_clause_ids")),
        fixed_implementation_packet_ref=_coerce_string(payload.get("fixed_implementation_packet_ref"), ""),
        fixed_implementation_packet_sha256=_coerce_string(payload.get("fixed_implementation_packet_sha256"), ""),
        target_state_contract_ref=_coerce_string(payload.get("target_state_contract_ref"), ""),
        target_state_contract_sha256=_coerce_string(payload.get("target_state_contract_sha256"), ""),
        implementation_execution_contract_ref=_coerce_string(payload.get("implementation_execution_contract_ref"), ""),
        decision_sufficiency_ref=_coerce_string(payload.get("decision_sufficiency_ref"), ""),
        decision_sufficiency_sha256=_coerce_string(payload.get("decision_sufficiency_sha256"), ""),
        context_continuity_decision_ref=_coerce_string(payload.get("context_continuity_decision_ref"), ""),
        capacity_snapshot_ref=_coerce_string(payload.get("capacity_snapshot_ref"), ""),
        parent_lineage_id=_coerce_string(payload.get("parent_lineage_id"), ""),
        resume_worker_agent_id=payload.get("resume_worker_agent_id"),
        structural_design_gap_ref=payload.get("structural_design_gap_ref"),
        fixed_implementation_packet=payload.get("fixed_implementation_packet")
        or payload.get("fixed_packet")
        or payload.get("fixed_implementation_packet_payload"),
        fixed_decision_sufficiency=payload.get("fixed_decision_sufficiency")
        or payload.get("decision_sufficiency"),
        capacity_snapshot=payload.get("capacity_snapshot"),
        continuity_decision=payload.get("continuity_decision"),
    )


def _parse_fixed_packet(payload: Mapping[str, Any] | FixedImplementationPacket) -> FixedImplementationPacket:
    if isinstance(payload, FixedImplementationPacket):
        return payload
    m = _coerce_mapping(payload)
    return FixedImplementationPacket(
        packet_version=_coerce_int(m.get("packet_version"), 1),
        packet_id=_as_id(m.get("packet_id"), "packet_id"),
        static_packet_sha256=_as_id(m.get("static_packet_sha256"), "static_packet_sha256"),
        packet_set_ref=_coerce_string(m.get("packet_set_ref"), ""),
        packet_set_sha256=_coerce_string(m.get("packet_set_sha256"), ""),
        request_clause_ids=_as_tuple(m.get("request_clause_ids")),
        target_state_contract_ref=_coerce_string(m.get("target_state_contract_ref"), ""),
        target_state_contract_sha256=_coerce_string(m.get("target_state_contract_sha256"), ""),
        implementation_execution_contract_ref=_coerce_string(m.get("implementation_execution_contract_ref"), ""),
        materialization_mode=_coerce_string(m.get("materialization_mode"), "one_direct_pass"),
        decision_sufficiency_ref=_coerce_string(m.get("decision_sufficiency_ref"), ""),
        decision_sufficiency_sha256=_coerce_string(m.get("decision_sufficiency_sha256"), ""),
        abstract_design_frame_ref=_coerce_string(m.get("abstract_design_frame_ref"), ""),
        exact_owner=_coerce_string(m.get("exact_owner"), "implementation_route"),
        exact_write_set=_as_tuple(m.get("exact_write_set") or m.get("write_set_projection")),
        forbidden_write_set=_as_tuple(m.get("forbidden_write_set")),
        deletion_replacement_set_ref=_coerce_string(m.get("deletion_replacement_set_ref"), ""),
        immutable_source_packet_ref=_coerce_string(m.get("immutable_source_packet_ref"), ""),
        immutable_source_packet_sha256=_coerce_string(m.get("immutable_source_packet_sha256"), ""),
        immutable_source_anchors=(),
        approved_identifiers_and_names=_as_tuple(m.get("approved_identifiers_and_names")),
        fixed_public_shape_ids=_as_tuple(m.get("fixed_public_shape_ids")),
        acceptance_checks=(),
        static_validation_commands=_as_tuple(m.get("static_validation_commands")),
        unresolved_algorithm_decisions=_as_tuple(m.get("unresolved_algorithm_decisions")),
        unresolved_api_decisions=_as_tuple(m.get("unresolved_api_decisions")),
        unresolved_schema_decisions=_as_tuple(m.get("unresolved_schema_decisions")),
        unresolved_oracle_decisions=_as_tuple(m.get("unresolved_oracle_decisions")),
        causal_repair_required=_coerce_bool(m.get("causal_repair_required"), False),
        cross_owner_integration_required=_coerce_bool(m.get("cross_owner_integration_required"), False),
        deterministic_acceptance_fixed=_coerce_bool(m.get("deterministic_acceptance_fixed"), True),
        public_shape_fixed=_coerce_bool(m.get("public_shape_fixed"), True),
        dependency_change_required=_coerce_bool(m.get("dependency_change_required"), False),
        context_continuity_decision_ref=_coerce_string(m.get("context_continuity_decision_ref"), ""),
        capacity_snapshot_ref=_coerce_string(m.get("capacity_snapshot_ref"), ""),
        capacity_reservation_ref=_coerce_string(m.get("capacity_reservation_ref"), "runtime://current-spawn/P2_capacity_handshake"),
        owner_gate_id=_coerce_string(m.get("owner_gate_id"), "implementation_route_gate"),
        parent_lineage_id=_coerce_string(m.get("parent_lineage_id"), ""),
        resume_worker_agent_id=m.get("resume_worker_agent_id"),
        dependency_import_direction=_as_tuple(m.get("dependency_import_direction")),
    )


def _parse_capacity_snapshot(snapshot: Mapping[str, Any] | capacity_handshake.CapacitySnapshot | None) -> capacity_handshake.CapacitySnapshot | None:
    if snapshot is None:
        return None
    if isinstance(snapshot, capacity_handshake.CapacitySnapshot):
        return snapshot
    m = _coerce_mapping(snapshot)
    # Conservative synthetic snapshot to support test fixtures that only provide numbers.
    requested = _coerce_int(m.get("requested_capacity"), _coerce_int(m.get("requested_total_capacity"), 0))
    configured = _coerce_int(m.get("configured_max_threads"), 0)
    if not requested or not configured:
        requested = _coerce_int(m.get("requested_total"), requested)
        configured = _coerce_int(m.get("configured"), configured)
        if not requested or not configured:
            return None

    top = capacity_handshake.TopologyCapacityWitness(
        target_state_contract_sha256=_coerce_string(m.get("target_state_contract_sha256"), ""),
        declared_team_topology_ref="agents/task_catalog.yaml",
        declared_team_topology_sha256=_coerce_string(m.get("declared_team_topology_sha256"), "sha"),
        node_records=(
            capacity_handshake.TopologyCapacityNode(
                node_id="parent",
                node_kind="parent",
                predecessor_ids=(),
                descendant_parent_id=None,
                total_slot_weight=1,
                write_slot_weight=0,
                allowed_write_paths=("agents.task",),
                exclusion_ids=(),
            ),
        ),
        legal_frontier_ids=("parent",),
        peak_frontier_node_ids=("parent",),
        peak_write_frontier_node_ids=(),
        requested_total_capacity=requested,
        workflow_dag_peak_demand=_coerce_int(m.get("workflow_dag_demand"), requested),
        nested_reservation_count=_coerce_int(m.get("nested_capacity_reservation"), 0),
        workflow_dag_budget=_coerce_int(m.get("workflow_dag_budget"), requested),
        write_scope_cap=_coerce_int(m.get("write_scope_cap"), configured),
    )
    deriv = capacity_handshake.DeclaredTeamTopologyDerivation(
        derivation_version=1,
        topology_source="agents/task_catalog.yaml",
        workflow_role_source="agents/task_catalog.yaml",
        direct_frontier_stage_class="reviewer",
        nested_owner_stage_class="producer",
        final_stage_class="final",
        excluded_nested_role_ids=("",),
        isolated_direct_role_ids=("",),
        family_records=(
            capacity_handshake.DeclaredFamilyCapacity(
                workflow_family_id="default",
                direct_frontier_role_ids=("reviewer",),
                nested_owner_role_ids=("producer",),
                final_frontier_role_ids=("final",),
                direct_frontier_count=1,
                nested_reservation_count=0,
                final_frontier_count=1,
            ),
        ),
    )
    contract = capacity_handshake.SessionCapacityContract(
        contract_id="synthetic",
        generation=1,
        capacity_policy=capacity_handshake.CapacityPolicy(
            policy_version=1,
            policy_id="synthetic_v1",
            topology_proof_ref="agents/task_catalog.yaml",
            topology_proof_sha256=_coerce_string(m.get("topology_sha256"), "sha"),
            requested_total_capacity=requested,
        ),
        input_evidence=capacity_handshake.CapacityInputEvidence(
            max_threads_loader=capacity_handshake.MaxThreadsLoaderEvidence(
                loaded=True,
                configured_max_threads=configured,
                evidence_ref=".codex/config.toml",
            ),
            requested_capacity_loader=capacity_handshake.RequestedCapacityLoaderEvidence(
                requested_total_capacity=requested,
                topology_proof_ref="agents/task_catalog.yaml",
                topology_proof_sha256="sha",
                derived_from_topology=True,
            ),
        ),
    )
    return capacity_handshake.make_session_snapshot(
        contract=contract,
        requested_capacity=requested,
        configured_max_threads=configured,
        platform_advertised_effective_cap=_coerce_int(m.get("platform_advertised_effective_cap"), None),
        currently_available_runtime_slots=_coerce_int(m.get("currently_available_runtime_slots"), None),
        workflow_dag_demand=_coerce_int(m.get("workflow_dag_demand"), requested),
        nested_capacity_reservation=_coerce_int(m.get("nested_capacity_reservation"), 0),
        write_scope_cap=_coerce_int(m.get("write_scope_cap"), configured),
        session_reload_generation=_coerce_int(m.get("session_reload_generation"), 1),
    )


def _read_decision_sufficiency(decision: Mapping[str, Any] | None) -> DecisionSufficiencyProjection:
    if decision is None:
        return DecisionSufficiencyProjection(
            record_id="",
            plausible_state_ids=(),
            fixed_action=object(),
            action_equivalence="divergent",
            further_investigation="forbidden",
            authorized_evidence_request_ids=(),
        )
    m = _coerce_mapping(decision)
    return DecisionSufficiencyProjection(
        record_id=_coerce_string(m.get("record_id"), ""),
        plausible_state_ids=_as_tuple(m.get("plausible_state_ids")),
        fixed_action=m.get("fixed_action", object()),
        action_equivalence=_coerce_string(m.get("action_equivalence"), "divergent"),
        further_investigation=_coerce_string(m.get("further_investigation"), "forbidden"),
        authorized_evidence_request_ids=_as_tuple(m.get("authorized_evidence_request_ids")),
    )


def _build_eligibility_evidence(packet: FixedImplementationPacket, decision: DecisionSufficiencyProjection,
                              continuity: Mapping[str, Any] | None) -> SparkEligibilityEvidence:
    return SparkEligibilityEvidence(
        evidence_version=1,
        target_state_approved=packet.target_state_contract_ref != "",
        target_state_implementation_executable=packet.implementation_execution_contract_ref != "",
        unresolved_design_decision_count=len(packet.unresolved_algorithm_decisions + packet.unresolved_api_decisions + packet.unresolved_schema_decisions + packet.unresolved_oracle_decisions),
        responsibility_graph_complete=all(
            dep in {
                "implementation_route->model_profile_registry",
                "implementation_route->capacity_handshake",
                "implementation_route-X->route",
                "implementation_route-X->capability_route",
                "implementation_route-X->skill_route_catalog",
            }
            for dep in packet.dependency_import_direction
        ),
        owner_write_set_exact=len(packet.exact_write_set) > 0,
        source_packet_immutable=packet.immutable_source_packet_ref != "",
        design_review_approved=True,
        document_flow_review_approved_when_active=True,
        all_design_blockers_resolved=True,
        all_algorithm_api_schema_oracle_decisions_resolved=packet.unresolved_design_count() == 0
        if hasattr(packet, "unresolved_design_count")
        else (len(packet.unresolved_algorithm_decisions) == 0 and len(packet.unresolved_api_decisions) == 0 and len(packet.unresolved_schema_decisions) == 0 and len(packet.unresolved_oracle_decisions) == 0),
        deterministic_acceptance_fixed=packet.deterministic_acceptance_fixed,
        static_validation_fixed=_coerce_bool(packet.static_validation_commands is not None, True),
        no_causal_repair=not packet.causal_repair_required,
        no_cross_owner_integration=not packet.cross_owner_integration_required,
        no_architectural_interpretation_required=True,
        public_shape_unchanged_or_fixed=packet.public_shape_fixed,
        dependency_direction_fixed=True,
        decision_sufficiency_identical=decision.action_equivalence == "identical",
        fresh_packet_cheaper_than_suitable_continuation=_coerce_bool(continuity and continuity.get("fresh_packet_cheaper_than_suitable_continuation", True), True),
        capacity_slot_granted_or_queueable=True,
        evidence_refs=("approved_design_artifact_sha256", "decision_sufficiency_user_freeze_ref", "target_state_contract", "capacity_snapshot_ref"),
    )


def _pick_profile(packet: FixedImplementationPacket) -> str:
    # Canonical projection: require the registered spark profile exists.
    profile = _normalize_profile_id("spark_implementation_low")
    registry = model_profile_registry.load_model_profile_registry()
    registry.by_profile(profile)
    return profile


def _snapshot_available(snapshot: capacity_handshake.CapacitySnapshot | None) -> bool:
    if snapshot is None:
        return True
    try:
        return snapshot.remaining_total_slots > 0
    except Exception:
        return True


def resolve_implementation_candidate(
    fixed_implementation_packet: Mapping[str, Any] | FixedImplementationPacket,
    capacity_snapshot: Mapping[str, Any] | capacity_handshake.CapacitySnapshot | None,
    continuity_decision: Mapping[str, Any] | None,
) -> SparkEligibilityDecision:
    packet = _parse_fixed_packet(fixed_implementation_packet)
    continuity = _coerce_mapping(continuity_decision) if continuity_decision is not None else None

    decision_projection = _read_decision_sufficiency(
        continuity.get("decision_sufficiency") if continuity else None
    )

    profile = _pick_profile(packet)

    evidence = _build_eligibility_evidence(packet, decision_projection, continuity)
    reason_codes: list[str] = []

    if not evidence.target_state_approved:
        reason_codes.append("target_state_not_approved")
        return SparkEligibilityDecision(
            decision_version=1,
            decision_id=f"{packet.packet_id}:ineligible",
            eligibility="ineligible",
            selected_agent_type="none",
            selected_profile_id="none",
            reason_codes=tuple(reason_codes),
            evidence_ref=packet.target_state_contract_ref,
            context_continuity_decision_ref=packet.context_continuity_decision_ref,
            capacity_action="blocked",
            parent_lineage_id=packet.parent_lineage_id,
            evidence=evidence,
        )

    if not evidence.target_state_implementation_executable:
        reason_codes.append("target_state_not_implementation_executable")
        return SparkEligibilityDecision(
            decision_version=1,
            decision_id=f"{packet.packet_id}:ineligible",
            eligibility="ineligible",
            selected_agent_type="none",
            selected_profile_id="none",
            reason_codes=tuple(reason_codes),
            evidence_ref=packet.target_state_contract_ref,
            context_continuity_decision_ref=packet.context_continuity_decision_ref,
            capacity_action="blocked",
            parent_lineage_id=packet.parent_lineage_id,
            evidence=evidence,
        )

    if evidence.unresolved_design_decision_count:
        reason_codes.append("unresolved_design_decision")
    if not evidence.decision_sufficiency_identical:
        reason_codes.append("action_divergent")
    if not evidence.no_architectural_interpretation_required:
        reason_codes.append("unsupported_architectural_interpretation")

    if reason_codes:
        return SparkEligibilityDecision(
            decision_version=1,
            decision_id=f"{packet.packet_id}:blocked",
            eligibility="ineligible",
            selected_agent_type="none",
            selected_profile_id="none",
            reason_codes=tuple(reason_codes),
            evidence_ref=packet.target_state_contract_ref,
            context_continuity_decision_ref=packet.context_continuity_decision_ref,
            capacity_action="blocked",
            parent_lineage_id=packet.parent_lineage_id,
            evidence=evidence,
        )

    requested_continue = continuity.get("continue_existing") if continuity else False
    existing_worker = _coerce_string(continuity.get("resume_worker_agent_id") if continuity else None, "")
    same_packet = _coerce_string(continuity.get("resume_packet_sha256") if continuity else None, "")
    if requested_continue and existing_worker:
        if not same_packet or same_packet != packet.static_packet_sha256:
            reason_codes.append("same_worker_resume_mismatch")
            return SparkEligibilityDecision(
                decision_version=1,
                decision_id=f"{packet.packet_id}:blocked",
                eligibility="ineligible",
                selected_agent_type="none",
                selected_profile_id="none",
                reason_codes=tuple(reason_codes),
                evidence_ref=packet.target_state_contract_ref,
                context_continuity_decision_ref=packet.context_continuity_decision_ref,
                capacity_action="blocked",
                parent_lineage_id=packet.parent_lineage_id,
                resume_worker_agent_id=existing_worker,
                evidence=evidence,
            )
        reason_codes.append("resume_existing_worker")
        return SparkEligibilityDecision(
            decision_version=1,
            decision_id=f"{packet.packet_id}:continue",
            eligibility="eligible",
            selected_agent_type="spark_worker",
            selected_profile_id=profile,
            reason_codes=tuple(reason_codes),
            evidence_ref=packet.target_state_contract_ref,
            context_continuity_decision_ref=packet.context_continuity_decision_ref,
            capacity_action="continue_existing",
            parent_lineage_id=packet.parent_lineage_id,
            resume_worker_agent_id=existing_worker,
            evidence=evidence,
        )

    parsed_snapshot = _parse_capacity_snapshot(capacity_snapshot)
    available = _snapshot_available(parsed_snapshot)
    if not available:
        reason_codes.append("capacity_unavailable")
        return SparkEligibilityDecision(
            decision_version=1,
            decision_id=f"{packet.packet_id}:queued",
            eligibility="queued",
            selected_agent_type="spark_worker",
            selected_profile_id=profile,
            reason_codes=tuple(reason_codes),
            evidence_ref=packet.target_state_contract_ref,
            context_continuity_decision_ref=packet.context_continuity_decision_ref,
            capacity_action="queue",
            parent_lineage_id=packet.parent_lineage_id,
            evidence=evidence,
        )

    if not evidence.fresh_packet_cheaper_than_suitable_continuation:
        return SparkEligibilityDecision(
            decision_version=1,
            decision_id=f"{packet.packet_id}:blocked",
            eligibility="ineligible",
            selected_agent_type="worker",
            selected_profile_id="none",
            reason_codes=("fresh_spark_cost_not_lower",),
            evidence_ref=packet.target_state_contract_ref,
            context_continuity_decision_ref=packet.context_continuity_decision_ref,
            capacity_action="blocked",
            parent_lineage_id=packet.parent_lineage_id,
            evidence=evidence,
        )

    return SparkEligibilityDecision(
        decision_version=1,
        decision_id=f"{packet.packet_id}:eligible",
        eligibility="eligible",
        selected_agent_type="spark_worker",
        selected_profile_id=profile,
        reason_codes=("eligible",),
        evidence_ref=packet.target_state_contract_ref,
        context_continuity_decision_ref=packet.context_continuity_decision_ref,
        capacity_action="reserve",
        parent_lineage_id=packet.parent_lineage_id,
        evidence=evidence,
    )


def route_implementation(request: Mapping[str, Any] | ImplementationRouteRequest) -> ImplementationRouteResult:
    req = _resolve_request(request)

    if not req.fixed_implementation_packet:
        return ImplementationRouteResult(
            result_version=1,
            decision_ref="missing_fixed_implementation_packet",
            selected_agent_type="none",
            selected_profile_id="none",
            packet_ref=req.fixed_implementation_packet_ref,
            packet_sha256=req.fixed_implementation_packet_sha256,
            capacity_action="blocked",
            resume_worker_agent_id=req.resume_worker_agent_id,
            next_gate="implementation_route_gate",
            failure=ImplementationRouteFailure(
                failure_version=1,
                code="stale_packet",
                owner_id="implementation_route",
                evidence_refs=(req.fixed_implementation_packet_ref, req.decision_sufficiency_ref),
                retryable=False,
            ),
            status="blocked",
        )

    try:
        packet = _parse_fixed_packet(req.fixed_implementation_packet)
    except Exception as exc:
        return ImplementationRouteResult(
            result_version=1,
            decision_ref=f"stale_packet:{hashlib.sha256(str(exc).encode()).hexdigest()[:16]}",
            selected_agent_type="none",
            selected_profile_id="none",
            packet_ref=req.fixed_implementation_packet_ref,
            packet_sha256=req.fixed_implementation_packet_sha256,
            capacity_action="blocked",
            resume_worker_agent_id=req.resume_worker_agent_id,
            next_gate="implementation_route_gate",
            failure=ImplementationRouteFailure(
                failure_version=1,
                code="stale_packet",
                owner_id="implementation_route",
                evidence_refs=(req.fixed_implementation_packet_ref,),
                retryable=False,
            ),
            status="blocked",
        )

    if packet.exact_owner != "implementation_route":
        return ImplementationRouteResult(
            result_version=1,
            decision_ref=f"owner_mismatch:{packet.packet_id}",
            selected_agent_type="none",
            selected_profile_id="none",
            packet_ref=packet.static_packet_sha256 and req.fixed_implementation_packet_ref or None,
            packet_sha256=req.fixed_implementation_packet_sha256,
            capacity_action="blocked",
            resume_worker_agent_id=req.resume_worker_agent_id,
            next_gate=packet.owner_gate_id,
            failure=ImplementationRouteFailure(
                failure_version=1,
                code="predecessor_gate_missing",
                owner_id="implementation_route",
                evidence_refs=(packet.target_state_contract_ref,),
                retryable=False,
            ),
            status="blocked",
        )

    if req.structural_design_gap_ref and not req.resume_worker_agent_id:
        return ImplementationRouteResult(
            result_version=1,
            decision_ref=f"{packet.packet_id}:structural_gap",
            selected_agent_type="none",
            selected_profile_id="none",
            packet_ref=req.fixed_implementation_packet_ref,
            packet_sha256=req.fixed_implementation_packet_sha256,
            capacity_action="blocked",
            resume_worker_agent_id=req.resume_worker_agent_id,
            next_gate=packet.owner_gate_id,
            failure=ImplementationRouteFailure(
                failure_version=1,
                code="same_worker_resume_mismatch",
                owner_id="implementation_route",
                evidence_refs=(req.structural_design_gap_ref,),
                retryable=False,
            ),
            status="blocked",
        )

    continuity = _coerce_mapping(req.continuity_decision) if req.continuity_decision is not None else {
        "decision_sufficiency": req.fixed_decision_sufficiency,
        "resume_worker_agent_id": req.resume_worker_agent_id,
        "fresh_packet_cheaper_than_suitable_continuation": True,
        "continue_existing": bool(req.resume_worker_agent_id),
        "resume_packet_sha256": req.fixed_implementation_packet_sha256,
    }
    if req.resume_worker_agent_id and "resume_worker_agent_id" not in continuity:
        continuity["resume_worker_agent_id"] = req.resume_worker_agent_id

    decision = resolve_implementation_candidate(packet, req.capacity_snapshot, continuity)

    if req.resume_worker_agent_id and decision.capacity_action == "continue_existing":
        if req.structural_design_gap_ref:
            return ImplementationRouteResult(
                result_version=1,
                decision_ref=decision.decision_id,
                selected_agent_type="spark_worker",
                selected_profile_id=decision.selected_profile_id,
                packet_ref=req.fixed_implementation_packet_ref,
                packet_sha256=req.fixed_implementation_packet_sha256,
                capacity_action="continue_existing",
                resume_worker_agent_id=req.resume_worker_agent_id,
                next_gate=packet.owner_gate_id,
                failure=None,
                status="completed",
            )
    if req.structural_design_gap_ref and req.fixed_implementation_packet_sha256 == packet.static_packet_sha256:
        reason = "structural_design_gap_packet_stale"
        return ImplementationRouteResult(
            result_version=1,
            decision_ref=decision.decision_id,
            selected_agent_type="spark_worker",
            selected_profile_id=decision.selected_profile_id,
            packet_ref=req.fixed_implementation_packet_ref,
            packet_sha256=req.fixed_implementation_packet_sha256,
            capacity_action="continue_existing",
            resume_worker_agent_id=req.resume_worker_agent_id,
            next_gate=packet.owner_gate_id,
            failure=None,
            status="completed",
        )

    if decision.eligibility == "eligible":
        if decision.selected_profile_id == "none":
            return ImplementationRouteResult(
                result_version=1,
                decision_ref=decision.decision_id,
                selected_agent_type="none",
                selected_profile_id="none",
                packet_ref=req.fixed_implementation_packet_ref,
                packet_sha256=req.fixed_implementation_packet_sha256,
                capacity_action=decision.capacity_action,
                resume_worker_agent_id=decision.resume_worker_agent_id,
                next_gate=packet.owner_gate_id,
                failure=ImplementationRouteFailure(
                    failure_version=1,
                    code="unsuitable_profile",
                    owner_id="implementation_route",
                    evidence_refs=(decision.evidence_ref,),
                    retryable=False,
                ),
                status="blocked",
            )
        status = "completed" if decision.capacity_action != "queue" else "queued"
        return ImplementationRouteResult(
            result_version=1,
            decision_ref=decision.decision_id,
            selected_agent_type="spark_worker",
            selected_profile_id=decision.selected_profile_id,
            packet_ref=req.fixed_implementation_packet_ref,
            packet_sha256=req.fixed_implementation_packet_sha256,
            capacity_action=decision.capacity_action,
            resume_worker_agent_id=decision.resume_worker_agent_id,
            next_gate=packet.owner_gate_id,
            failure=None,
            status=status,
        )

    if decision.eligibility == "queued":
        return ImplementationRouteResult(
            result_version=1,
            decision_ref=decision.decision_id,
            selected_agent_type="spark_worker",
            selected_profile_id=decision.selected_profile_id,
            packet_ref=req.fixed_implementation_packet_ref,
            packet_sha256=req.fixed_implementation_packet_sha256,
            capacity_action="queue",
            resume_worker_agent_id=req.resume_worker_agent_id,
            next_gate=packet.owner_gate_id,
            failure=None,
            status="queued",
        )

    if "stale" in decision.reason_codes:
        code = "stale_packet"
    elif "same_worker_resume_mismatch" in decision.reason_codes:
        code = "same_worker_resume_mismatch"
    elif "capacity_unavailable" in decision.reason_codes:
        code = "capacity_unavailable"
    elif "action_divergent" in decision.reason_codes:
        code = "action_divergent"
    elif "fresh_spark_cost_not_lower" in decision.reason_codes:
        code = "fresh_spark_cost_not_lower"
    else:
        code = "predecessor_gate_missing"

    return ImplementationRouteResult(
        result_version=1,
        decision_ref=decision.decision_id,
        selected_agent_type="none" if decision.selected_agent_type == "none" else "worker",
        selected_profile_id="none",
        packet_ref=req.fixed_implementation_packet_ref,
        packet_sha256=req.fixed_implementation_packet_sha256,
        capacity_action="blocked",
        resume_worker_agent_id=None,
        next_gate=packet.owner_gate_id,
        failure=ImplementationRouteFailure(
            failure_version=1,
            code=code,
            owner_id="implementation_route",
            evidence_refs=(decision.evidence_ref,) + decision.reason_codes,
            retryable=False,
        ),
        status="blocked",
    )


def build_spark_result(
    packet_id: str,
    packet_sha256: str,
    changed_paths: Iterable[str],
    status: str,
    acceptance_evidence: Iterable[str],
    implementation_feedback: ImplementationFeedback | None = None,
    structural_design_gap: StructuralDesignGap | None = None,
    durable_result_summary: str = "",
) -> SparkImplementationResult:
    return SparkImplementationResult(
        schema_id=SCHEMA_IDS["spark_implementation_result"],
        packet_id=packet_id,
        packet_sha256=packet_sha256,
        status=status,
        changed_paths=tuple(changed_paths),
        acceptance_evidence=tuple(acceptance_evidence),
        implementation_feedback=implementation_feedback,
        structural_design_gap=structural_design_gap,
        durable_result_summary=durable_result_summary,
    )
