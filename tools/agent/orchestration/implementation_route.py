#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Routes one immutable fixed implementation packet to Spark or the saturation queue.
# upstream implementation ./model_profile_registry.py owns profile and prompt materialization
# upstream implementation ./capacity_handshake.py owns typed capacity availability and queue semantics
# upstream implementation ./update_lifecycle_contract.py imports the canonical owner-produced Decision Sufficiency verdict
# upstream design ../../agents/canonical/CODEX_SUBAGENTS.md defines fixed Spark continuation policy
# downstream implementation ./implementation_dispatch.py performs actual typed implementation dispatch
# downstream implementation ../../tests/agent_tools/test_implementation_route.py tests fail-closed routing
# @dependency-end
"""Fail-closed implementation routing for fixed Spark packets."""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

if __package__:
    from tools.runtime.artifacts import artifact_identity as _artifact_identity
    from . import capacity_handshake
    from . import model_profile_registry

    _direct_artifact_identity = sys.modules.get("artifact_identity")
    sys.modules["artifact_identity"] = _artifact_identity
    from tools.runtime.lifecycle import update_lifecycle_contract
    if _direct_artifact_identity is None:
        del sys.modules["artifact_identity"]
    else:
        sys.modules["artifact_identity"] = _direct_artifact_identity
else:
    import tools.agent.orchestration.capacity_handshake
    import tools.agent.orchestration.model_profile_registry
    import tools.runtime.lifecycle.update_lifecycle_contract

SCHEMA_IDS = {
    "fixed_implementation_packet": "fixed_implementation_packet_v1",
    "spark_eligibility_evidence": "spark_eligibility_evidence_v1",
    "implementation_route_request": "implementation_route_request_v1",
    "implementation_route_result": "implementation_route_result_v1",
    "structural_design_gap": "structural_design_gap_v1",
    "implementation_feedback": "implementation_feedback_v1",
    "spark_implementation_result": "spark_implementation_result_v1",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_SHAPE_IDS = {
    "fixed_implementation_packet_v1",
    "spark_eligibility_evidence_v1",
    "implementation_route_request_v1",
    "implementation_route_result_v1",
    "structural_design_gap_v1",
    "implementation_feedback_v1",
}
_REQUIRED_DEPENDENCY_DIRECTIONS = {
    "implementation_route->model_profile_registry",
    "implementation_route->capacity_handshake",
    "implementation_route->update_lifecycle_contract",
    "implementation_route-X->route",
    "implementation_route-X->capability_route",
    "implementation_route-X->skill_route_catalog",
}
_PACKET_FIELDS = {
    "schema_id",
    "packet_version",
    "packet_id",
    "static_packet_sha256",
    "packet_set_ref",
    "packet_set_sha256",
    "request_clause_ids",
    "target_state_contract_ref",
    "target_state_contract_sha256",
    "implementation_execution_contract_ref",
    "materialization_mode",
    "decision_sufficiency_ref",
    "decision_sufficiency_sha256",
    "abstract_design_frame_ref",
    "abstract_design_frame_sha256",
    "exact_owner",
    "exact_write_set",
    "forbidden_write_set",
    "deletion_replacement_set_ref",
    "immutable_source_packet_ref",
    "immutable_source_packet_sha256",
    "immutable_source_anchors",
    "approved_identifiers_and_names",
    "fixed_public_shape_ids",
    "acceptance_checks",
    "static_validation_commands",
    "unresolved_algorithm_decisions",
    "unresolved_api_decisions",
    "unresolved_schema_decisions",
    "unresolved_oracle_decisions",
    "causal_repair_required",
    "cross_owner_integration_required",
    "deterministic_acceptance_fixed",
    "public_shape_fixed",
    "dependency_change_required",
    "context_continuity_decision_ref",
    "capacity_snapshot_ref",
    "capacity_reservation_ref",
    "owner_gate_id",
    "parent_lineage_id",
    "resume_worker_agent_id",
    "dependency_import_direction",
    "status",
}
_REQUEST_FIELDS = {
    "schema_id",
    "request_version",
    "request_clause_ids",
    "fixed_implementation_packet_ref",
    "fixed_implementation_packet_sha256",
    "target_state_contract_ref",
    "target_state_contract_sha256",
    "implementation_execution_contract_ref",
    "decision_sufficiency_ref",
    "decision_sufficiency_sha256",
    "context_continuity_decision_ref",
    "capacity_snapshot_ref",
    "parent_lineage_id",
    "resume_worker_agent_id",
    "structural_design_gap_ref",
    "fixed_implementation_packet",
    "fixed_decision_sufficiency",
    "capacity_snapshot",
    "continuity_decision",
}
_ANCHOR_FIELDS = {
    "anchor_purpose",
    "ref",
    "selector",
    "sha256",
    "manifest_sha256",
    "manifest_canonicalization",
    "path_count",
    "base_state",
    "required_predecessor_gate",
    "required_gate",
}
_CONTINUITY_FIELDS = {
    "decision_sufficiency",
    "continue_existing",
    "resume_worker_agent_id",
    "resume_packet_sha256",
    "fresh_packet_cheaper_than_suitable_continuation",
    "structural_gap_repair_count",
}
_CAPACITY_PROJECTION_FIELDS = {
    "shape_id",
    "requested_total_capacity",
    "effective_total_capacity",
    "available_total_capacity",
    "requested_write_capacity",
    "effective_write_capacity",
    "available_write_capacity",
    "input_provenance",
}


def _closed_mapping(value: object, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label}:must_be_mapping")
    keys = set(value)
    unknown = sorted(str(key) for key in keys - fields)
    missing = sorted(fields - keys)
    if unknown:
        raise ValueError(f"{label}:unknown_fields:{','.join(unknown)}")
    if missing:
        raise ValueError(f"{label}:missing_fields:{','.join(missing)}")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}:must_be_nonempty_string")
    return value


def _sha256(value: object, field: str) -> str:
    text = _text(value, field)
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{field}:must_be_sha256")
    return text


def _string_tuple(value: object, field: str, *, nonempty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{field}:must_be_string_sequence")
    result = tuple(value)
    if nonempty and not result:
        raise ValueError(f"{field}:must_be_nonempty")
    if len(result) != len(set(result)):
        raise ValueError(f"{field}:duplicate")
    return result


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field}:must_be_bool")
    return value


def _int(value: object, field: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{field}:must_be_int_gte_{minimum}")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _relative_paths(value: object, field: str, *, nonempty: bool) -> tuple[str, ...]:
    paths = _string_tuple(value, field, nonempty=nonempty)
    for path in paths:
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts or path.startswith("./"):
            raise ValueError(f"{field}:path_not_canonical:{path}")
    return paths


@dataclass(frozen=True)
class ImplementationPacketSet:
    packet_set_id: str
    packet_set_sha256: str
    packets: tuple[str, ...]


@dataclass(frozen=True)
class StaticImplementationPacket:
    packet_id: str
    packet_sha256: str
    source_anchor_refs: tuple[str, ...]


@dataclass(frozen=True)
class DesignSectionAnchor:
    section_id: str
    ref: str
    sha256: str


@dataclass(frozen=True)
class ToolCallTokenTemplate:
    tool_id: str
    target_argument: str


@dataclass(frozen=True)
class TopologyGeneratedCapacitySetting:
    requested_total_capacity: int
    direct_frontier_count: int
    nested_reservation_count: int


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
    verdict: Mapping[str, Any]
    owner_action: str
    edit_action: str
    validation_action: str


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
    abstract_design_frame_sha256: str
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
    resume_worker_agent_id: str | None
    dependency_import_direction: tuple[str, ...]
    schema_id: str = SCHEMA_IDS["fixed_implementation_packet"]
    status: str = "ready"

    @property
    def unresolved_design_count(self) -> int:
        return sum(
            len(values)
            for values in (
                self.unresolved_algorithm_decisions,
                self.unresolved_api_decisions,
                self.unresolved_schema_decisions,
                self.unresolved_oracle_decisions,
            )
        )


@dataclass(frozen=True)
class SparkEligibilityEvidence:
    evidence_version: int
    target_state_approved: bool
    target_state_implementation_executable: bool
    unresolved_design_decision_count: int
    responsibility_graph_complete: bool
    owner_write_set_exact: bool
    source_packet_immutable: bool
    all_design_blockers_resolved: bool
    deterministic_acceptance_fixed: bool
    static_validation_fixed: bool
    no_causal_repair: bool
    no_cross_owner_integration: bool
    public_shape_fixed: bool
    dependency_direction_fixed: bool
    decision_sufficiency_identical: bool
    fresh_packet_cheaper_than_suitable_continuation: bool
    capacity_slot_granted_or_queueable: bool
    evidence_refs: tuple[str, ...]
    source_anchors: tuple[SourceAnchor, ...]
    acceptance_checks: tuple[ValidationAction, ...]
    static_validation_commands: tuple[str, ...]
    schema_id: str = SCHEMA_IDS["spark_eligibility_evidence"]


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
    schema_id: str = "spark_eligibility_decision_v1"


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
    actions_that_could_change: tuple[str, str]
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
    resume_worker_agent_id: str | None
    structural_design_gap_ref: str | None
    fixed_implementation_packet: Mapping[str, Any] | FixedImplementationPacket
    fixed_decision_sufficiency: Mapping[str, Any]
    capacity_snapshot: Mapping[str, Any] | capacity_handshake.CapacitySnapshot
    continuity_decision: Mapping[str, Any]
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
    exact_write_set: tuple[str, ...] = ()
    source_anchors: tuple[SourceAnchor, ...] = ()
    acceptance_checks: tuple[ValidationAction, ...] = ()
    static_validation_commands: tuple[str, ...] = ()
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


def route_result_as_claim_evidence(result: ImplementationRouteResult) -> dict[str, object]:
    """Adapt the route result to the shared claim/evidence return contract.

    The route keeps its immutable packet schema IDs for transport compatibility; this
    adapter is the single common return boundary consumed by profile/runtime checks.
    """
    status = {
        "completed": "pass",
        "queued": "revise",
        "blocked": "blocked",
    }.get(result.status, "escalate")
    evidence: list[str] = [f"decision:{result.decision_ref}"]
    if result.packet_ref:
        evidence.append(f"packet:{result.packet_ref}")
    if result.packet_sha256:
        evidence.append(f"packet_sha256:{result.packet_sha256}")
    evidence.extend(f"acceptance:{check.command}" for check in result.acceptance_checks)
    evidence.extend(f"validation:{command}" for command in result.static_validation_commands)
    if result.failure:
        evidence.extend(f"failure:{item}" for item in result.failure.evidence_refs)
    return {
        "status": status,
        "claim": (
            f"implementation route {result.status}"
            f" for {result.selected_agent_type}/{result.selected_profile_id}"
        ),
        "evidence": evidence,
    }


def validate_route_result_common(result: ImplementationRouteResult) -> model_profile_registry.ValidationResult:
    """Validate the actual route output after common-contract adaptation."""
    return model_profile_registry.validate_claim_evidence_result(
        route_result_as_claim_evidence(result)
    )


def _ensure_common_return_contract(result: ImplementationRouteResult) -> ImplementationRouteResult:
    validation = validate_route_result_common(result)
    if not validation.valid:
        details = ";".join(issue.code for issue in validation.issues)
        raise RuntimeError(f"route_result_common_contract_invalid:{details}")
    return result


def _parse_source_anchor(value: object, index: int) -> SourceAnchor:
    anchor = _closed_mapping(value, _ANCHOR_FIELDS, f"immutable_source_anchors[{index}]")
    sha = None if anchor["sha256"] is None else _sha256(anchor["sha256"], "source_anchor.sha256")
    manifest_sha = None if anchor["manifest_sha256"] is None else _sha256(anchor["manifest_sha256"], "source_anchor.manifest_sha256")
    if sha is None and manifest_sha is None:
        raise ValueError("source_anchor:digest_required")
    path_count = anchor["path_count"]
    if path_count is not None:
        path_count = _int(path_count, "source_anchor.path_count", minimum=1)
    return SourceAnchor(
        anchor_purpose=_text(anchor["anchor_purpose"], "source_anchor.anchor_purpose"),
        ref=_text(anchor["ref"], "source_anchor.ref"),
        selector=_optional_text(anchor["selector"], "source_anchor.selector"),
        sha256=sha,
        manifest_sha256=manifest_sha,
        manifest_canonicalization=_optional_text(anchor["manifest_canonicalization"], "source_anchor.manifest_canonicalization"),
        path_count=path_count,
        base_state=_optional_text(anchor["base_state"], "source_anchor.base_state"),
        required_predecessor_gate=_optional_text(anchor["required_predecessor_gate"], "source_anchor.required_predecessor_gate"),
        required_gate=_optional_text(anchor["required_gate"], "source_anchor.required_gate"),
    )


def _parse_validation_action(value: object, index: int) -> ValidationAction:
    action = _closed_mapping(value, {"command", "oracle"}, f"acceptance_checks[{index}]")
    return ValidationAction(_text(action["command"], "validation.command"), _text(action["oracle"], "validation.oracle"))


def _validate_fixed_packet(packet: FixedImplementationPacket) -> None:
    if packet.schema_id != SCHEMA_IDS["fixed_implementation_packet"] or packet.packet_version != 1:
        raise ValueError("fixed_packet:schema_or_version_mismatch")
    if packet.status != "ready" or packet.materialization_mode != "one_direct_pass":
        raise ValueError("fixed_packet:not_ready_for_direct_pass")
    if packet.exact_owner != "implementation_route":
        raise ValueError("fixed_packet:owner_mismatch")
    if set(packet.exact_write_set) & set(packet.forbidden_write_set):
        raise ValueError("fixed_packet:write_set_forbidden_overlap")
    if set(packet.fixed_public_shape_ids) != _REQUIRED_SHAPE_IDS:
        raise ValueError("fixed_packet:public_shape_set_mismatch")
    if set(packet.dependency_import_direction) != _REQUIRED_DEPENDENCY_DIRECTIONS:
        raise ValueError("fixed_packet:dependency_direction_mismatch")
    if not packet.immutable_source_anchors or not packet.acceptance_checks or not packet.static_validation_commands:
        raise ValueError("fixed_packet:evidence_or_validation_empty")
    if packet.unresolved_design_count != 0:
        raise ValueError("fixed_packet:unresolved_design_decisions")
    if not packet.deterministic_acceptance_fixed or not packet.public_shape_fixed:
        raise ValueError("fixed_packet:acceptance_or_public_shape_not_fixed")
    if packet.causal_repair_required or packet.cross_owner_integration_required:
        raise ValueError("fixed_packet:not_spark_eligible_structure")


def _parse_fixed_packet(value: Mapping[str, Any] | FixedImplementationPacket) -> FixedImplementationPacket:
    if isinstance(value, FixedImplementationPacket):
        _validate_fixed_packet(value)
        return value
    packet = _closed_mapping(value, _PACKET_FIELDS, "fixed_implementation_packet")
    anchors_raw = packet["immutable_source_anchors"]
    checks_raw = packet["acceptance_checks"]
    if not isinstance(anchors_raw, (list, tuple)) or not isinstance(checks_raw, (list, tuple)):
        raise ValueError("fixed_packet:anchors_and_checks_must_be_sequences")
    parsed = FixedImplementationPacket(
        packet_version=_int(packet["packet_version"], "packet_version", minimum=1),
        packet_id=_text(packet["packet_id"], "packet_id"),
        static_packet_sha256=_sha256(packet["static_packet_sha256"], "static_packet_sha256"),
        packet_set_ref=_text(packet["packet_set_ref"], "packet_set_ref"),
        packet_set_sha256=_sha256(packet["packet_set_sha256"], "packet_set_sha256"),
        request_clause_ids=_string_tuple(packet["request_clause_ids"], "request_clause_ids"),
        target_state_contract_ref=_text(packet["target_state_contract_ref"], "target_state_contract_ref"),
        target_state_contract_sha256=_sha256(packet["target_state_contract_sha256"], "target_state_contract_sha256"),
        implementation_execution_contract_ref=_text(packet["implementation_execution_contract_ref"], "implementation_execution_contract_ref"),
        materialization_mode=_text(packet["materialization_mode"], "materialization_mode"),
        decision_sufficiency_ref=_text(packet["decision_sufficiency_ref"], "decision_sufficiency_ref"),
        decision_sufficiency_sha256=_sha256(packet["decision_sufficiency_sha256"], "decision_sufficiency_sha256"),
        abstract_design_frame_ref=_text(packet["abstract_design_frame_ref"], "abstract_design_frame_ref"),
        abstract_design_frame_sha256=_sha256(packet["abstract_design_frame_sha256"], "abstract_design_frame_sha256"),
        exact_owner=_text(packet["exact_owner"], "exact_owner"),
        exact_write_set=_relative_paths(packet["exact_write_set"], "exact_write_set", nonempty=True),
        forbidden_write_set=_relative_paths(packet["forbidden_write_set"], "forbidden_write_set", nonempty=False),
        deletion_replacement_set_ref=_text(packet["deletion_replacement_set_ref"], "deletion_replacement_set_ref"),
        immutable_source_packet_ref=_text(packet["immutable_source_packet_ref"], "immutable_source_packet_ref"),
        immutable_source_packet_sha256=_sha256(packet["immutable_source_packet_sha256"], "immutable_source_packet_sha256"),
        immutable_source_anchors=tuple(_parse_source_anchor(item, index) for index, item in enumerate(anchors_raw)),
        approved_identifiers_and_names=_string_tuple(packet["approved_identifiers_and_names"], "approved_identifiers_and_names"),
        fixed_public_shape_ids=_string_tuple(packet["fixed_public_shape_ids"], "fixed_public_shape_ids"),
        acceptance_checks=tuple(_parse_validation_action(item, index) for index, item in enumerate(checks_raw)),
        static_validation_commands=_string_tuple(packet["static_validation_commands"], "static_validation_commands"),
        unresolved_algorithm_decisions=_string_tuple(packet["unresolved_algorithm_decisions"], "unresolved_algorithm_decisions", nonempty=False),
        unresolved_api_decisions=_string_tuple(packet["unresolved_api_decisions"], "unresolved_api_decisions", nonempty=False),
        unresolved_schema_decisions=_string_tuple(packet["unresolved_schema_decisions"], "unresolved_schema_decisions", nonempty=False),
        unresolved_oracle_decisions=_string_tuple(packet["unresolved_oracle_decisions"], "unresolved_oracle_decisions", nonempty=False),
        causal_repair_required=_bool(packet["causal_repair_required"], "causal_repair_required"),
        cross_owner_integration_required=_bool(packet["cross_owner_integration_required"], "cross_owner_integration_required"),
        deterministic_acceptance_fixed=_bool(packet["deterministic_acceptance_fixed"], "deterministic_acceptance_fixed"),
        public_shape_fixed=_bool(packet["public_shape_fixed"], "public_shape_fixed"),
        dependency_change_required=_bool(packet["dependency_change_required"], "dependency_change_required"),
        context_continuity_decision_ref=_text(packet["context_continuity_decision_ref"], "context_continuity_decision_ref"),
        capacity_snapshot_ref=_text(packet["capacity_snapshot_ref"], "capacity_snapshot_ref"),
        capacity_reservation_ref=_text(packet["capacity_reservation_ref"], "capacity_reservation_ref"),
        owner_gate_id=_text(packet["owner_gate_id"], "owner_gate_id"),
        parent_lineage_id=_text(packet["parent_lineage_id"], "parent_lineage_id"),
        resume_worker_agent_id=_optional_text(packet["resume_worker_agent_id"], "resume_worker_agent_id"),
        dependency_import_direction=_string_tuple(packet["dependency_import_direction"], "dependency_import_direction"),
        schema_id=_text(packet["schema_id"], "schema_id"),
        status=_text(packet["status"], "status"),
    )
    _validate_fixed_packet(parsed)
    return parsed


def _parse_request(value: Mapping[str, Any] | ImplementationRouteRequest) -> ImplementationRouteRequest:
    if isinstance(value, ImplementationRouteRequest):
        return value
    request = _closed_mapping(value, _REQUEST_FIELDS, "implementation_route_request")
    if request["schema_id"] != SCHEMA_IDS["implementation_route_request"]:
        raise ValueError("implementation_route_request:schema_mismatch")
    if not isinstance(request["fixed_implementation_packet"], (Mapping, FixedImplementationPacket)):
        raise ValueError("implementation_route_request:fixed_packet_missing")
    if not isinstance(request["fixed_decision_sufficiency"], Mapping):
        raise ValueError("implementation_route_request:decision_sufficiency_missing")
    if not isinstance(request["continuity_decision"], Mapping):
        raise ValueError("implementation_route_request:continuity_missing")
    if not isinstance(request["capacity_snapshot"], (Mapping, capacity_handshake.CapacitySnapshot)):
        raise ValueError("implementation_route_request:capacity_snapshot_missing")
    return ImplementationRouteRequest(
        request_version=_int(request["request_version"], "request_version", minimum=1),
        request_clause_ids=_string_tuple(request["request_clause_ids"], "request_clause_ids"),
        fixed_implementation_packet_ref=_text(request["fixed_implementation_packet_ref"], "fixed_implementation_packet_ref"),
        fixed_implementation_packet_sha256=_sha256(request["fixed_implementation_packet_sha256"], "fixed_implementation_packet_sha256"),
        target_state_contract_ref=_text(request["target_state_contract_ref"], "target_state_contract_ref"),
        target_state_contract_sha256=_sha256(request["target_state_contract_sha256"], "target_state_contract_sha256"),
        implementation_execution_contract_ref=_text(request["implementation_execution_contract_ref"], "implementation_execution_contract_ref"),
        decision_sufficiency_ref=_text(request["decision_sufficiency_ref"], "decision_sufficiency_ref"),
        decision_sufficiency_sha256=_sha256(request["decision_sufficiency_sha256"], "decision_sufficiency_sha256"),
        context_continuity_decision_ref=_text(request["context_continuity_decision_ref"], "context_continuity_decision_ref"),
        capacity_snapshot_ref=_text(request["capacity_snapshot_ref"], "capacity_snapshot_ref"),
        parent_lineage_id=_text(request["parent_lineage_id"], "parent_lineage_id"),
        resume_worker_agent_id=_optional_text(request["resume_worker_agent_id"], "resume_worker_agent_id"),
        structural_design_gap_ref=_optional_text(request["structural_design_gap_ref"], "structural_design_gap_ref"),
        fixed_implementation_packet=request["fixed_implementation_packet"],
        fixed_decision_sufficiency=request["fixed_decision_sufficiency"],
        capacity_snapshot=request["capacity_snapshot"],
        continuity_decision=request["continuity_decision"],
    )


def _decision_projection(
    value: object,
    packet: FixedImplementationPacket,
) -> DecisionSufficiencyProjection:
    try:
        verdict = update_lifecycle_contract.import_decision_sufficiency_verdict(
            value,
            expected_digest=f"sha256:{packet.decision_sufficiency_sha256}",
        )
    except update_lifecycle_contract.LifecycleContractError as exc:
        raise ValueError(str(exc)) from exc
    if verdict.get("decision_id") != packet.decision_sufficiency_ref:
        raise ValueError("decision_sufficiency:decision_identity_mismatch")
    request_clause_ids = verdict.get("request_clause_ids")
    if (
        not isinstance(request_clause_ids, list)
        or tuple(request_clause_ids) != packet.request_clause_ids
    ):
        raise ValueError("decision_sufficiency:source_identity_mismatch")
    invariant = verdict.get("invariant")
    if not isinstance(invariant, Mapping):
        raise ValueError("decision_sufficiency:invariant_binding_missing")
    invariant_clause_ids = invariant.get("request_clause_ids")
    if (
        not isinstance(invariant_clause_ids, list)
        or tuple(invariant_clause_ids) != packet.request_clause_ids
    ):
        raise ValueError("decision_sufficiency:invariant_source_identity_mismatch")
    owner_action = invariant.get("owner")
    edit_action = invariant.get("edit")
    validation_action = invariant.get("validation")
    if (
        owner_action != packet.exact_owner
        or edit_action != packet.deletion_replacement_set_ref
        or validation_action != packet.implementation_execution_contract_ref
    ):
        raise ValueError("decision_sufficiency:packet_action_binding_mismatch")
    return DecisionSufficiencyProjection(
        verdict,
        str(owner_action),
        str(edit_action),
        str(validation_action),
    )


def _continuity(value: object) -> Mapping[str, Any]:
    continuity = _closed_mapping(value, _CONTINUITY_FIELDS, "continuity_decision")
    if not isinstance(continuity["continue_existing"], bool):
        raise ValueError("continuity_decision:continue_existing_must_be_bool")
    if not isinstance(continuity["fresh_packet_cheaper_than_suitable_continuation"], bool):
        raise ValueError("continuity_decision:fresh_cost_must_be_bool")
    _int(continuity["structural_gap_repair_count"], "structural_gap_repair_count")
    _optional_text(continuity["resume_worker_agent_id"], "continuity.resume_worker_agent_id")
    if continuity["resume_packet_sha256"] is not None:
        _sha256(continuity["resume_packet_sha256"], "continuity.resume_packet_sha256")
    return continuity


def _capacity_available(value: Mapping[str, Any] | capacity_handshake.CapacitySnapshot) -> tuple[int, int, tuple[str, ...]]:
    if isinstance(value, capacity_handshake.CapacitySnapshot):
        provenance = value.input_provenance
        required = {
            "requested_total_capacity",
            "configured_total_capacity",
            "platform_effective_total_capacity",
            "current_available_total_capacity",
            "workflow_dag_direct_demand",
            "nested_reservation_count",
            "write_scope_cap",
        }
        if not required.issubset({item.input_id for item in provenance}):
            raise ValueError("capacity_snapshot:provenance_incomplete")
        if any(item.value != item.readback_value for item in provenance):
            raise ValueError("capacity_snapshot:readback_mismatch")
        return value.available_total_capacity, value.available_write_capacity, tuple(item.source_ref for item in provenance)
    projection = _closed_mapping(value, _CAPACITY_PROJECTION_FIELDS, "capacity_snapshot_projection")
    if projection["shape_id"] != "capacity_snapshot_projection_v1":
        raise ValueError("capacity_snapshot_projection:schema_mismatch")
    for field in _CAPACITY_PROJECTION_FIELDS - {"shape_id", "input_provenance"}:
        _int(projection[field], f"capacity_snapshot_projection.{field}")
    provenance = projection["input_provenance"]
    if not isinstance(provenance, list) or not provenance or not all(isinstance(item, str) and item for item in provenance):
        raise ValueError("capacity_snapshot_projection:provenance_required")
    return int(projection["available_total_capacity"]), int(projection["available_write_capacity"]), tuple(provenance)


def _validate_identity(request: ImplementationRouteRequest, packet: FixedImplementationPacket) -> None:
    pairs = (
        (request.request_clause_ids, packet.request_clause_ids, "request_clause_ids"),
        (request.fixed_implementation_packet_ref, packet.immutable_source_packet_ref, "fixed_implementation_packet_ref"),
        (request.fixed_implementation_packet_sha256, packet.static_packet_sha256, "fixed_implementation_packet_sha256"),
        (request.target_state_contract_ref, packet.target_state_contract_ref, "target_state_contract_ref"),
        (request.target_state_contract_sha256, packet.target_state_contract_sha256, "target_state_contract_sha256"),
        (request.implementation_execution_contract_ref, packet.implementation_execution_contract_ref, "implementation_execution_contract_ref"),
        (request.decision_sufficiency_ref, packet.decision_sufficiency_ref, "decision_sufficiency_ref"),
        (request.decision_sufficiency_sha256, packet.decision_sufficiency_sha256, "decision_sufficiency_sha256"),
        (request.context_continuity_decision_ref, packet.context_continuity_decision_ref, "context_continuity_decision_ref"),
        (request.capacity_snapshot_ref, packet.capacity_snapshot_ref, "capacity_snapshot_ref"),
        (request.parent_lineage_id, packet.parent_lineage_id, "parent_lineage_id"),
    )
    mismatches = [label for actual, expected, label in pairs if actual != expected]
    if mismatches:
        raise ValueError(f"packet_identity_mismatch:{','.join(mismatches)}")


def _evidence(packet: FixedImplementationPacket, decision: DecisionSufficiencyProjection, fresh_cheaper: bool, capacity_refs: tuple[str, ...]) -> SparkEligibilityEvidence:
    return SparkEligibilityEvidence(
        evidence_version=1,
        target_state_approved=True,
        target_state_implementation_executable=True,
        unresolved_design_decision_count=packet.unresolved_design_count,
        responsibility_graph_complete=True,
        owner_write_set_exact=True,
        source_packet_immutable=True,
        all_design_blockers_resolved=True,
        deterministic_acceptance_fixed=packet.deterministic_acceptance_fixed,
        static_validation_fixed=bool(packet.static_validation_commands),
        no_causal_repair=not packet.causal_repair_required,
        no_cross_owner_integration=not packet.cross_owner_integration_required,
        public_shape_fixed=packet.public_shape_fixed,
        dependency_direction_fixed=True,
        decision_sufficiency_identical=True,
        fresh_packet_cheaper_than_suitable_continuation=fresh_cheaper,
        capacity_slot_granted_or_queueable=True,
        evidence_refs=(
            packet.abstract_design_frame_ref,
            packet.target_state_contract_ref,
            packet.immutable_source_packet_ref,
            str(decision.verdict["decision_id"]),
            f"sha256:{packet.decision_sufficiency_sha256}",
            decision.owner_action,
            decision.edit_action,
            decision.validation_action,
            *capacity_refs,
        ),
        source_anchors=packet.immutable_source_anchors,
        acceptance_checks=packet.acceptance_checks,
        static_validation_commands=packet.static_validation_commands,
    )


def resolve_implementation_candidate(
    fixed_implementation_packet: Mapping[str, Any] | FixedImplementationPacket,
    capacity_snapshot: Mapping[str, Any] | capacity_handshake.CapacitySnapshot,
    continuity_decision: Mapping[str, Any],
) -> SparkEligibilityDecision:
    packet = _parse_fixed_packet(fixed_implementation_packet)
    continuity = _continuity(continuity_decision)
    decision = _decision_projection(continuity["decision_sufficiency"], packet)
    available_total, available_write, capacity_refs = _capacity_available(capacity_snapshot)
    fresh_cheaper = bool(continuity["fresh_packet_cheaper_than_suitable_continuation"])
    evidence = _evidence(packet, decision, fresh_cheaper, capacity_refs)
    continue_existing = bool(continuity["continue_existing"])
    resume_worker = continuity["resume_worker_agent_id"]
    resume_sha = continuity["resume_packet_sha256"]
    repair_count = int(continuity["structural_gap_repair_count"])
    if continue_existing:
        if not isinstance(resume_worker, str) or resume_sha != packet.static_packet_sha256 or repair_count != 1:
            return SparkEligibilityDecision(
                1,
                f"{packet.packet_id}:blocked",
                "ineligible",
                "none",
                "none",
                ("same_worker_resume_mismatch",),
                packet.immutable_source_packet_ref,
                packet.context_continuity_decision_ref,
                "blocked",
                packet.parent_lineage_id,
                resume_worker if isinstance(resume_worker, str) else None,
                evidence,
            )
    elif resume_worker is not None or resume_sha is not None or repair_count != 0:
        raise ValueError("continuity_decision:inactive_resume_fields_must_be_empty")
    if not continue_existing and not fresh_cheaper:
        return SparkEligibilityDecision(
            1,
            f"{packet.packet_id}:blocked",
            "ineligible",
            "none",
            "none",
            ("fresh_spark_cost_not_lower",),
            packet.immutable_source_packet_ref,
            packet.context_continuity_decision_ref,
            "blocked",
            packet.parent_lineage_id,
            evidence=evidence,
        )
    profile_id = "spark_implementation_low"
    model_profile_registry.load_model_profile_registry().by_profile(profile_id)
    if continue_existing:
        return SparkEligibilityDecision(
            1,
            f"{packet.packet_id}:continue",
            "eligible",
            "spark_worker",
            profile_id,
            ("resume_same_spark_after_one_repaired_structural_gap",),
            packet.immutable_source_packet_ref,
            packet.context_continuity_decision_ref,
            "continue_existing",
            packet.parent_lineage_id,
            str(resume_worker),
            evidence,
        )
    if available_total < 1 or available_write < 1:
        return SparkEligibilityDecision(
            1,
            f"{packet.packet_id}:queued",
            "queued",
            "spark_worker",
            profile_id,
            ("capacity_saturated",),
            packet.immutable_source_packet_ref,
            packet.context_continuity_decision_ref,
            "queue",
            packet.parent_lineage_id,
            evidence=evidence,
        )
    return SparkEligibilityDecision(
        1,
        f"{packet.packet_id}:eligible",
        "eligible",
        "spark_worker",
        profile_id,
        ("fixed_packet_eligible",),
        packet.immutable_source_packet_ref,
        packet.context_continuity_decision_ref,
        "reserve_on_successful_spawn",
        packet.parent_lineage_id,
        evidence=evidence,
    )


def _blocked_result(code: str, evidence: str, *, packet: FixedImplementationPacket | None = None) -> ImplementationRouteResult:
    digest = hashlib.sha256(evidence.encode("utf-8")).hexdigest()[:16]
    return _ensure_common_return_contract(ImplementationRouteResult(
        result_version=1,
        decision_ref=f"{code}:{digest}",
        selected_agent_type="none",
        selected_profile_id="none",
        packet_ref=packet.immutable_source_packet_ref if packet else None,
        packet_sha256=packet.static_packet_sha256 if packet else None,
        capacity_action="blocked",
        resume_worker_agent_id=None,
        next_gate=packet.owner_gate_id if packet else "implementation_route_gate",
        failure=ImplementationRouteFailure(1, code, "implementation_route", (evidence,), False),
        status="blocked",
        exact_write_set=packet.exact_write_set if packet else (),
        source_anchors=packet.immutable_source_anchors if packet else (),
        acceptance_checks=packet.acceptance_checks if packet else (),
        static_validation_commands=packet.static_validation_commands if packet else (),
    ))


def route_implementation(request: Mapping[str, Any] | ImplementationRouteRequest) -> ImplementationRouteResult:
    packet: FixedImplementationPacket | None = None
    try:
        parsed_request = _parse_request(request)
        packet = _parse_fixed_packet(parsed_request.fixed_implementation_packet)
        _validate_identity(parsed_request, packet)
        route_continuity = _closed_mapping(parsed_request.continuity_decision, _CONTINUITY_FIELDS, "continuity_decision")
        if route_continuity["decision_sufficiency"] != parsed_request.fixed_decision_sufficiency:
            raise ValueError("decision_sufficiency:request_continuity_mismatch")
        if parsed_request.resume_worker_agent_id != route_continuity["resume_worker_agent_id"]:
            raise ValueError("continuity_decision:resume_worker_identity_mismatch")
        if bool(parsed_request.structural_design_gap_ref) != (int(route_continuity["structural_gap_repair_count"]) == 1):
            raise ValueError("continuity_decision:structural_gap_identity_mismatch")
        decision = resolve_implementation_candidate(packet, parsed_request.capacity_snapshot, route_continuity)
    except (ValueError, TypeError, model_profile_registry.ImplementationFeedback) as exc:
        return _blocked_result("stale_or_malformed_packet_evidence", str(exc), packet=packet)
    if decision.eligibility == "ineligible":
        return _blocked_result(decision.reason_codes[0], decision.evidence_ref, packet=packet)
    return _ensure_common_return_contract(ImplementationRouteResult(
        result_version=1,
        decision_ref=decision.decision_id,
        selected_agent_type=decision.selected_agent_type,
        selected_profile_id=decision.selected_profile_id,
        packet_ref=packet.immutable_source_packet_ref,
        packet_sha256=packet.static_packet_sha256,
        capacity_action=decision.capacity_action,
        resume_worker_agent_id=decision.resume_worker_agent_id,
        next_gate=packet.owner_gate_id,
        failure=None,
        status="queued" if decision.eligibility == "queued" else "completed",
        exact_write_set=packet.exact_write_set,
        source_anchors=packet.immutable_source_anchors,
        acceptance_checks=packet.acceptance_checks,
        static_validation_commands=packet.static_validation_commands,
    ))


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
        SCHEMA_IDS["spark_implementation_result"],
        packet_id,
        packet_sha256,
        status,
        tuple(changed_paths),
        tuple(acceptance_evidence),
        implementation_feedback,
        structural_design_gap,
        durable_result_summary,
    )
