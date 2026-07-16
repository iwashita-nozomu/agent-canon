#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides report artifact checks agent workflow automation.
# upstream design ../README.md shared automation index
# upstream implementation ./work_log.py reconstructs the canonical logical ledger
# upstream implementation ./mid_task_user_input_policy.py defines mid-task user input evidence policy
# downstream implementation ./task_close.py consumes checked CompletionCoverage at closeout
# downstream implementation ./agent_canon_preflight.py blocks task-entry updates on eval transient captures
# @dependency-end

"""Shared checks for run-bundle artifact completeness."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from mid_task_user_input_policy import (
    MID_TASK_CLASSIFICATION_ACTIONS,
    MID_TASK_CLASSIFICATION_SCOPE_STATUS,
    MID_TASK_EVIDENCE_FIELDS,
    MID_TASK_REQUIRED_WAVE_FIELDS,
    MID_TASK_REUSE_MARKERS,
    MID_TASK_SPAWN_AUTHORITY,
    MID_TASK_SPAWNED_ROLES_REQUIRED_CLASSIFICATIONS,
    MID_TASK_TARGET_REQUIRED_CLASSIFICATIONS,
    has_reuse_marker,
    is_empty_policy_value,
)

PLACEHOLDER_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
APPROVE_DECISION_PATTERN = re.compile(
    r"^(?:[-*]\s*)?(?:decision\s*:\s*)?approve\s*$",
    re.IGNORECASE,
)
REQUIRED_ACTUAL_WAVE_FIELDS = (
    "wave_event",
    "wave_id",
    "event_kind",
    "spawn_authority",
    "trigger",
    "budget_before",
    "budget_after",
    "runtime_max_threads",
    "runtime_max_depth",
    "spawned_roles",
    "role_instances",
    "skipped_roles",
    "allowed_paths",
    "do_not_read",
    "write_scope",
    "validation_route",
    "review_gate",
    "handoff_artifacts",
    "status",
)
WAVE_COMPARISON_FIELDS = (
    ("Spawn Authority", "spawn_authority"),
    ("Trigger", "trigger"),
    ("Budget Before", "budget_before"),
    ("Budget After", "budget_after"),
    ("Runtime Max Threads", "runtime_max_threads"),
    ("Runtime Max Depth", "runtime_max_depth"),
    ("Role Instances", "role_instances"),
    ("Allowed Paths", "allowed_paths"),
    ("Do Not Read", "do_not_read"),
    ("Write Scope", "write_scope"),
    ("Validation Route", "validation_route"),
    ("Review Gate", "review_gate"),
    ("Handoff Artifacts", "handoff_artifacts"),
    ("Status", "status"),
)
MECHANICALLY_REGENERATED_REPORT_ROOTS = (
    PurePosixPath("reports/agent-eval-runs"),
    PurePosixPath("reports/agent-improvement-guide"),
    PurePosixPath("reports/agent-runtime-dashboard"),
    PurePosixPath("reports/dependency-review"),
    PurePosixPath("reports/hooks"),
    PurePosixPath("reports/.cache"),
)
MECHANICALLY_REGENERATED_REPORT_FILE_PATTERNS = (
    re.compile(r"^reports/[^/]+\.(?:json|patch|txt)$"),
)
EVAL_TRANSIENT_CAPTURE_PATTERN = re.compile(
    r"^reports/agent-eval-runs/[^/]+/[^/]+\.(?:stdout|stderr)\.txt$"
)

# W2 completion coverage is a read model over the existing run ledger.  Keep
# these contracts here, beside the artifact checker, so task_close remains a
# consumer and no second persistence or closeout authority is introduced.
COMPLETION_COVERAGE_SCHEMA = "agent-canon.completion-coverage.v1"
COMPLETION_COVERAGE_TAXONOMY_REFS = (
    "documents/runtime-profiles-and-check-matrix.json",
    "documents/runtime-profiles-and-check-matrix.md",
)
RUNTIME_PROFILE_TAXONOMY_PATH = (
    Path(__file__).resolve().parents[2]
    / "documents"
    / "runtime-profiles-and-check-matrix.json"
)
COMPLETION_SEMANTIC_KINDS = (
    "request_clause",
    "responsibility_unit",
    "decision",
    "change",
    "review_finding",
    "validation",
    "failure",
    "publication_state",
    "deferral",
)
NON_GROUPABLE_SEMANTIC_KINDS = frozenset(
    {"responsibility_unit", "decision", "failure", "deferral", "publication_state"}
)
LEDGER_EVENT_REQUIRED_FIELDS = (
    "run_id",
    "context_id",
    "event_id",
    "semantic_kind",
    "owner",
    "state_owner",
    "api_owner",
    "dependency_owner",
    "responsibility_unit",
    "outcome",
    "intent_id",
    "evidence_refs",
    "artifact_refs",
)
GPU_CERTIFICATE_SEQUENCE = (
    "caller_candidate_uuid_set_A",
    "process_held_O_t_pid_start_identities",
    "active_reservations_R_t",
    "selected_uuids",
    "atomic_lock_lease_and_post_lock_readback",
    "effective_environment",
    "actual_terminal_gpu_process_identities",
    "release_or_retained_for_descendant_disposition",
    "typed_insufficient_eligible_or_mismatch_failure",
)
W1_CERTIFICATE_REQUIRED_FIELDS = (
    "run_id",
    "context_id",
    "producer_owner",
    "certificate_id",
    "sequence",
    "source_refs",
    "artifact_refs",
    "terminal_outcome",
)


@dataclass(frozen=True)
class TypedOwnerBoundaryEvidence:
    """Typed ownership evidence replacing scalar OOP heuristics."""

    owner: str
    state_owner: str
    api_owner: str
    dependency_owner: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ValidationFailureResponse:
    """Canonical pointer-only validation failure response."""

    failing_contract: str
    observation_level: str
    cause_classification: str
    intent_preservation: str
    evidence: tuple[str, ...]
    taxonomy_refs: tuple[str, ...]
    same_intent_repair_or_escalation: str
    repair_or_escalation_owner: str
    repair_or_escalation_result: str
    result_artifact_refs: tuple[str, ...]


def _nonempty_text(value: object) -> str:
    """Return one required text field or raise a contract error."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("completion coverage required text is empty")
    return value.strip()


def _text_tuple(value: object, field_name: str) -> tuple[str, ...]:
    """Return a deterministic tuple of non-empty string references."""
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list of strings")
    result = tuple(_nonempty_text(item) for item in value)
    if not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


def _taxonomy_values(field: str) -> frozenset[str]:
    """Read one canonical validation taxonomy set without copying its values."""
    raw = json.loads(RUNTIME_PROFILE_TAXONOMY_PATH.read_text(encoding="utf-8"))
    policy = raw.get("validation_failure_response") if isinstance(raw, dict) else None
    values = policy.get(field) if isinstance(policy, Mapping) else None
    if not isinstance(values, list) or not values:
        raise ValueError(f"validation taxonomy missing {field}")
    return frozenset(_nonempty_text(value) for value in values)


def _validate_failure_taxonomy_values(
    cause_classification: str,
    intent_preservation: str,
) -> None:
    """Validate failure slugs against the JSON-owned taxonomy."""
    if cause_classification not in _taxonomy_values("cause_classes"):
        raise ValueError(f"unsupported cause_classification: {cause_classification}")
    if intent_preservation not in _taxonomy_values("intent_preservation"):
        raise ValueError(f"unsupported intent_preservation: {intent_preservation}")


def _event_records(ledger_snapshot: object) -> tuple[dict[str, object], ...]:
    """Read the existing logical ledger snapshot without creating a store."""
    raw_events: object = ledger_snapshot
    if isinstance(ledger_snapshot, Mapping):
        raw_events = ledger_snapshot.get("events")
    if not isinstance(raw_events, (list, tuple)):
        raise ValueError("ledger_snapshot.events must be a list")
    events: list[dict[str, object]] = []
    identities: set[str] = set()
    for index, raw_event in enumerate(raw_events):
        if not isinstance(raw_event, Mapping):
            raise ValueError(f"ledger event {index} must be an object")
        event = dict(raw_event)
        identity = _nonempty_text(event.get("event_id", event.get("sequence", "")))
        if identity in identities:
            raise ValueError(f"duplicate ledger event identity: {identity}")
        identities.add(identity)
        semantic_kind = _nonempty_text(event.get("semantic_kind"))
        if semantic_kind not in COMPLETION_SEMANTIC_KINDS:
            raise ValueError(f"unsupported semantic_kind: {semantic_kind}")
        for field in LEDGER_EVENT_REQUIRED_FIELDS:
            if field in {"event_id", "semantic_kind"}:
                continue
            if field.endswith("_refs"):
                _text_tuple(event.get(field), field)
            else:
                _nonempty_text(event.get(field))
        if event.get("clause_id") is not None:
            _nonempty_text(event.get("clause_id"))
        events.append(event)
    return tuple(
        sorted(
            events,
            key=lambda event: (
                str(event.get("sequence", "")),
                str(event.get("event_id", "")),
            ),
        )
    )


def _owner_evidence(event: Mapping[str, object]) -> dict[str, object]:
    """Project typed owner/state/API/dependency evidence from one event."""
    evidence = TypedOwnerBoundaryEvidence(
        owner=_nonempty_text(event.get("owner")),
        state_owner=_nonempty_text(event.get("state_owner")),
        api_owner=_nonempty_text(event.get("api_owner")),
        dependency_owner=_nonempty_text(event.get("dependency_owner")),
        evidence_refs=_text_tuple(event.get("evidence_refs"), "evidence_refs"),
    )
    return {
        "owner": evidence.owner,
        "state_owner": evidence.state_owner,
        "api_owner": evidence.api_owner,
        "dependency_owner": evidence.dependency_owner,
        "evidence_refs": list(evidence.evidence_refs),
    }


def _mapping_from_event(event: Mapping[str, object]) -> dict[str, object] | None:
    """Return one direct/group clause mapping when the event carries a clause."""
    clause_id = event.get("clause_id")
    if clause_id is None:
        return None
    mapping_mode = _nonempty_text(event.get("mapping_mode", "direct"))
    member_clause_ids = event.get("member_clause_ids", [clause_id])
    members = _text_tuple(member_clause_ids, "member_clause_ids")
    semantic_kind = _nonempty_text(event.get("semantic_kind"))
    if mapping_mode == "group" and semantic_kind in NON_GROUPABLE_SEMANTIC_KINDS:
        raise ValueError(f"{semantic_kind} mappings cannot be grouped")
    if mapping_mode not in {"direct", "group"}:
        raise ValueError(f"unsupported mapping_mode: {mapping_mode}")
    if mapping_mode == "direct" and members != (_nonempty_text(clause_id),):
        raise ValueError("direct mappings must contain exactly their clause_id")
    if mapping_mode == "group" and len(set(members)) < 2:
        raise ValueError("group mappings require at least two distinct member clauses")
    return {
        "clause_id": _nonempty_text(clause_id),
        "mapping_mode": mapping_mode,
        "owner": _nonempty_text(event.get("owner")),
        "responsibility_unit": _nonempty_text(event.get("responsibility_unit")),
        "outcome": _nonempty_text(event.get("outcome")),
        "member_clause_ids": list(members),
        "semantic_kind": semantic_kind,
        "evidence_refs": list(_text_tuple(event.get("evidence_refs"), "evidence_refs")),
        "source_event_ref": _nonempty_text(
            event.get("event_id", event.get("sequence", ""))
        ),
    }


def _resource_certificate_errors(
    certificate: Mapping[str, object],
    source_binding: Mapping[str, object],
) -> list[str]:
    """Validate W1 certificate shape without recomputing resource semantics."""
    errors: list[str] = []
    for field in W1_CERTIFICATE_REQUIRED_FIELDS:
        if not certificate.get(field):
            errors.append(f"missing:{field}")
    if certificate.get("producer_owner") != "W1":
        errors.append("producer_owner")
    for field in ("run_id", "context_id"):
        if certificate.get(field) != source_binding.get(
            "run_id" if field == "run_id" else "context_id"
        ):
            errors.append(f"binding:{field}")
    for field in (
        "applicability",
        "plan",
        "actual",
        "readback",
        "environment",
        "terminal",
        "cleanup",
        "failure",
    ):
        if not isinstance(certificate.get(field), Mapping):
            errors.append(f"missing:{field}")
    gpu_items = certificate.get("gpu_semantics")
    if gpu_items is not None:
        if not isinstance(gpu_items, list):
            errors.append("gpu_semantics")
        else:
            if any(not isinstance(item, Mapping) for item in gpu_items):
                errors.append("gpu_semantics:item_shape")
            observed = [item.get("item") for item in gpu_items if isinstance(item, Mapping)]
            if observed != list(GPU_CERTIFICATE_SEQUENCE) or len(gpu_items) != len(
                GPU_CERTIFICATE_SEQUENCE
            ):
                errors.append("gpu_semantics:ordered_nine_items")
            for item in gpu_items:
                if not isinstance(item, Mapping) or any(
                    not item.get(field)
                    for field in ("item", "semantic_identity", "consumer_rule", "evidence_refs")
                ):
                    errors.append("gpu_semantics:item_evidence")
    return sorted(set(errors))


def project_completion_coverage(
    ledger_snapshot: object,
    source_binding: Mapping[str, object],
    schema_version: str = COMPLETION_COVERAGE_SCHEMA,
) -> dict[str, object]:
    """Generate the deterministic v1 reader model from one ledger snapshot."""
    if schema_version != COMPLETION_COVERAGE_SCHEMA:
        raise ValueError(f"unsupported completion coverage schema: {schema_version}")
    binding = {key: value for key, value in source_binding.items()}
    for field in (
        "run_id",
        "context_id",
        "organizer_context_id",
        "parent",
        "component_manager",
        "assigned_unit",
        "source_binding",
        "source_refs",
    ):
        if field == "source_refs":
            binding[field] = list(_text_tuple(binding.get(field), field))
        elif field == "source_binding":
            if not isinstance(binding.get(field), Mapping) or not binding[field]:
                raise ValueError("source_binding must be a non-empty object")
        else:
            binding[field] = _nonempty_text(binding.get(field))
    events = _event_records(ledger_snapshot)
    for event in events:
        if event.get("run_id") != binding["run_id"]:
            raise ValueError("ledger event run_id does not match source binding")
        if event.get("context_id") != binding["context_id"]:
            raise ValueError("ledger event context_id does not match source binding")
        event_binding = event.get("source_binding")
        if event_binding is not None and event_binding != binding["source_binding"]:
            raise ValueError("ledger event source_binding does not match source binding")
    mappings = [mapping for event in events if (mapping := _mapping_from_event(event))]
    resource_certificates = []
    for event in events:
        certificate = event.get("resource_certificate")
        if not isinstance(certificate, Mapping):
            continue
        certificate_record = dict(certificate)
        certificate_record["source_event_ref"] = _nonempty_text(
            event.get("event_id", event.get("sequence", ""))
        )
        certificate_record["source_clause_id"] = event.get("clause_id")
        resource_certificates.append(certificate_record)
    semantic_events = [
        {
            "event_id": _nonempty_text(event.get("event_id", event.get("sequence", ""))),
            "sequence": str(event.get("sequence", "")),
            "semantic_kind": _nonempty_text(event.get("semantic_kind")),
            "owner_evidence": _owner_evidence(event),
            "intent_id": _nonempty_text(event.get("intent_id")),
            "outcome": _nonempty_text(event.get("outcome")),
            "artifact_refs": list(_text_tuple(event.get("artifact_refs"), "artifact_refs")),
        }
        for event in events
    ]
    return {
        "schema": COMPLETION_COVERAGE_SCHEMA,
        "source_binding": binding,
        "projection_metadata": {
            "deterministic_order": "sequence,event_id",
            "ledger_snapshot_identity": _nonempty_text(
                ledger_snapshot.get("snapshot_identity")
                if isinstance(ledger_snapshot, Mapping)
                else "in_memory_snapshot"
            ),
            "generated_artifact_identity": f"{binding['run_id']}:{binding['context_id']}",
            "semantic_kinds": list(COMPLETION_SEMANTIC_KINDS),
            "source_refs": list(binding["source_refs"]),
        },
        "semantic_events": semantic_events,
        "coverage_map": mappings,
        "owner_boundary_evidence": [
            event["owner_evidence"] for event in semantic_events
        ],
        "gate_evidence": [
            dict(event.get("gate_evidence", {}))
            for event in events
            if isinstance(event.get("gate_evidence"), Mapping)
        ],
        "failure_event_refs": [
            _nonempty_text(event.get("event_id", event.get("sequence", "")))
            for event in events
            if event.get("semantic_kind") == "failure"
        ],
        "failure_responses": [
            {
                **dict(event["failure_response"]),
                "source_event_ref": _nonempty_text(
                    event.get("event_id", event.get("sequence", ""))
                ),
            }
            for event in events
            if isinstance(event.get("failure_response"), Mapping)
        ],
        "resource_certificates": resource_certificates,
        "resource_certificate_errors": [
            {
                "certificate_id": certificate.get("certificate_id", ""),
                "source_event_ref": certificate.get("source_event_ref", ""),
                "errors": _resource_certificate_errors(certificate, binding),
            }
            for certificate in resource_certificates
        ],
    }


def _empty_error_sets() -> dict[str, list[str]]:
    """Return the five explicit mapping error sets."""
    return {
        "uncovered": [],
        "multiply_mapped": [],
        "orphan": [],
        "redundant": [],
        "empty": [],
    }


def check_completion_coverage(
    completion_coverage: Mapping[str, object],
    active_clause_ids: Sequence[str],
    owner_contract: Mapping[str, object],
    taxonomy_refs: Sequence[str] = COMPLETION_COVERAGE_TAXONOMY_REFS,
) -> dict[str, object]:
    """Check exact mappings and typed gate evidence without scalar heuristics."""
    errors = _empty_error_sets()
    if completion_coverage.get("schema") != COMPLETION_COVERAGE_SCHEMA:
        errors["empty"].append("schema")
    if not isinstance(completion_coverage.get("source_binding"), Mapping):
        errors["empty"].append("source_binding")
    expected = tuple(_nonempty_text(clause_id) for clause_id in active_clause_ids)
    expected_set = set(expected)
    raw_mappings = completion_coverage.get("coverage_map", [])
    if not isinstance(raw_mappings, list):
        errors["empty"].append("coverage_map")
        raw_mappings = []
    by_clause: dict[str, list[Mapping[str, object]]] = {}
    for raw_mapping in raw_mappings:
        if not isinstance(raw_mapping, Mapping):
            errors["empty"].append("mapping")
            continue
        clause_id = str(raw_mapping.get("clause_id", ""))
        members = raw_mapping.get("member_clause_ids")
        mode = raw_mapping.get("mapping_mode")
        if not isinstance(members, list) or not members or any(
            not isinstance(member, str) or not member.strip() for member in members
        ):
            errors["empty"].append(clause_id or "mapping")
            members = []
        member_ids = [str(member) for member in members]
        if len(set(member_ids)) != len(member_ids):
            errors["redundant"].append(clause_id or "mapping")
        if mode == "direct":
            if member_ids != [clause_id]:
                errors["redundant"].append(clause_id or "mapping")
        elif mode == "group":
            if len(member_ids) < 2:
                errors["redundant"].append(clause_id or "mapping")
            if raw_mapping.get("semantic_kind") in NON_GROUPABLE_SEMANTIC_KINDS:
                errors["empty"].append(f"group:{clause_id or 'mapping'}")
            if clause_id not in member_ids:
                errors["redundant"].append(clause_id or "mapping")
        else:
            errors["empty"].append(clause_id or "mapping")
        required = (
            "owner",
            "responsibility_unit",
            "outcome",
            "semantic_kind",
            "source_event_ref",
            "evidence_refs",
        )
        if any(not raw_mapping.get(field) for field in required):
            errors["empty"].append(clause_id or "mapping")
        for member_id in member_ids:
            by_clause.setdefault(member_id, []).append(raw_mapping)
            if member_id not in expected_set:
                errors["orphan"].append(member_id)
        if clause_id and clause_id not in expected_set:
            errors["orphan"].append(clause_id)
    for clause_id in expected:
        matches = by_clause.get(clause_id, [])
        if not matches:
            errors["uncovered"].append(clause_id)
        elif len(matches) != 1:
            errors["multiply_mapped"].append(clause_id)
    owner_fields = ("owner", "state_owner", "api_owner", "dependency_owner")
    if not all(_nonempty_text(owner_contract.get(field, "")) for field in owner_fields):
        errors["empty"].append("owner_contract")
    owner_evidence = completion_coverage.get("owner_boundary_evidence", [])
    if not isinstance(owner_evidence, list) or not owner_evidence:
        errors["empty"].append("owner_boundary_evidence")
    for evidence in owner_evidence if isinstance(owner_evidence, list) else []:
        if not isinstance(evidence, Mapping) or any(
            not evidence.get(field)
            for field in ("owner", "state_owner", "api_owner", "dependency_owner", "evidence_refs")
        ):
            errors["empty"].append("owner_boundary_evidence")
    gate_evidence = completion_coverage.get("gate_evidence", [])
    if not isinstance(gate_evidence, list) or not gate_evidence:
        errors["empty"].append("gate_evidence")
    for evidence in gate_evidence if isinstance(gate_evidence, list) else []:
        if not isinstance(evidence, Mapping) or any(
            not evidence.get(field)
            for field in (
                "gate_id",
                "stage",
                "owner",
                "outcome",
                "artifact_refs",
                "source_event_refs",
            )
        ):
            errors["empty"].append("gate_evidence")
    if tuple(taxonomy_refs) != COMPLETION_COVERAGE_TAXONOMY_REFS:
        errors["empty"].append("taxonomy_refs")
    certificate_results = completion_coverage.get("resource_certificate_errors", [])
    if not isinstance(certificate_results, list):
        errors["empty"].append("resource_certificate_errors")
        certificate_results = []
    certificate_ids: set[str] = set()
    for certificate_result in certificate_results:
        if not isinstance(certificate_result, Mapping):
            errors["empty"].append("resource_certificate")
            continue
        certificate_id = str(certificate_result.get("certificate_id", ""))
        if certificate_id in certificate_ids:
            errors["redundant"].append(f"resource_certificate:{certificate_id}")
        certificate_ids.add(certificate_id)
    for certificate_result in certificate_results:
        if isinstance(certificate_result, Mapping) and certificate_result.get("errors"):
            errors["empty"].append(
                f"resource_certificate:{certificate_result.get('certificate_id', '')}"
            )
    mappings_by_clause = {
        str(mapping.get("clause_id")): mapping
        for mapping in raw_mappings
        if isinstance(mapping, Mapping)
    }
    certificates_by_event = {
        str(result.get("source_event_ref")): result
        for result in certificate_results
        if isinstance(result, Mapping)
    }
    resource_mapping_event_refs: dict[str, str] = {}
    for clause_id in ("W2-12", "W2-19"):
        if clause_id not in expected_set:
            continue
        mapping = mappings_by_clause.get(clause_id)
        if not isinstance(mapping, Mapping) or mapping.get("mapping_mode") != "direct":
            errors["empty"].append(f"resource_mapping:{clause_id}")
            continue
        source_event_ref = str(mapping.get("source_event_ref", ""))
        resource_mapping_event_refs[clause_id] = source_event_ref
        if source_event_ref not in certificates_by_event:
            errors["empty"].append(f"resource_mapping:{clause_id}")
        certificate = next(
            (
                item
                for item in completion_coverage.get("resource_certificates", [])
                if isinstance(item, Mapping)
                and item.get("source_event_ref") == source_event_ref
            ),
            None,
        )
        if not isinstance(certificate, Mapping) or certificate.get("source_clause_id") != clause_id:
            errors["empty"].append(f"resource_mapping:{clause_id}:source_clause")
        if clause_id == "W2-19":
            if not isinstance(certificate, Mapping) or not isinstance(
                certificate.get("gpu_semantics"), list
            ):
                errors["empty"].append("resource_mapping:W2-19:gpu_semantics")
    if len(resource_mapping_event_refs) == 2 and len(
        set(resource_mapping_event_refs.values())
    ) != 2:
        errors["empty"].append("resource_mapping:distinct_source_events")
    responses = completion_coverage.get("failure_responses", [])
    if not isinstance(responses, list):
        errors["empty"].append("failure_responses")
        responses = []
    for response in responses:
        if not isinstance(response, Mapping):
            errors["empty"].append("failure_response")
            continue
        if tuple(response.get("taxonomy_refs", ())) != COMPLETION_COVERAGE_TAXONOMY_REFS:
            errors["empty"].append("failure_response:taxonomy_refs")
        try:
            _validate_failure_taxonomy_values(
                str(response.get("cause_classification", "")),
                str(response.get("intent_preservation", "")),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            errors["empty"].append("failure_response:taxonomy_values")
        if any(
            not response.get(field)
            for field in (
                "failing_contract",
                "observation_level",
                "cause_classification",
                "intent_preservation",
                "evidence",
                "same_intent_repair_or_escalation",
                "repair_or_escalation_owner",
                "repair_or_escalation_result",
                "result_artifact_refs",
            )
        ):
            errors["empty"].append("failure_response")
    response_refs = {
        str(response.get("source_event_ref"))
        for response in responses
        if isinstance(response, Mapping) and response.get("source_event_ref")
    }
    failure_event_refs = completion_coverage.get("failure_event_refs", [])
    if not isinstance(failure_event_refs, list):
        errors["empty"].append("failure_event_refs")
        failure_event_refs = []
    for event_ref in failure_event_refs:
        if not isinstance(event_ref, str) or event_ref not in response_refs:
            errors["empty"].append(f"failure_response:{event_ref}")
    errors = {key: sorted(set(value)) for key, value in errors.items()}
    failure_response_errors = tuple(
        item
        for item in errors["empty"]
        if item == "failure_response" or item.startswith("failure_response:")
    )
    owner_boundary_error = any(
        item in {"owner_contract", "owner_boundary_evidence"}
        for item in errors["empty"]
    )
    gate_results = {
        "G1_CLAUSE_COVERAGE": not any(errors.values()),
        "G2_OWNER_BOUNDARY": not owner_boundary_error,
        "G3_STAGE_EVIDENCE": bool(gate_evidence)
        and "gate_evidence" not in errors["empty"],
        "G4_VALIDATION_RESPONSE": not failure_response_errors and all(
            all(
                response.get(field)
                for field in (
                    "failing_contract",
                    "observation_level",
                    "cause_classification",
                    "intent_preservation",
                    "evidence",
                    "taxonomy_refs",
                    "same_intent_repair_or_escalation",
                    "repair_or_escalation_owner",
                    "repair_or_escalation_result",
                    "result_artifact_refs",
                )
            )
            for response in responses
            if isinstance(response, Mapping)
        ),
        "G5_DELIVERY_BOUNDARY": False,
    }
    return {
        "schema": "agent-canon.completion-coverage-check.v1",
        "source_binding": dict(completion_coverage.get("source_binding", {})),
        "ok": not any(errors.values()) and all(gate_results[key] for key in gate_results if key != "G5_DELIVERY_BOUNDARY"),
        "error_sets": errors,
        "gate_results": gate_results,
        "taxonomy_refs": list(COMPLETION_COVERAGE_TAXONOMY_REFS),
        "owner_contract": dict(owner_contract),
    }


def write_completion_coverage_artifact(
    report_dir: Path,
    ledger_snapshot: object,
    source_binding: Mapping[str, object],
    active_clause_ids: Sequence[str],
    owner_contract: Mapping[str, object],
    schedule_state_non_routing: Mapping[str, object],
    open_work_state_non_routing: Mapping[str, object],
    repair_state_non_routing: Mapping[str, object],
    crossing_edge_state_non_routing: Mapping[str, object],
    control_topology_ledger_snapshot: Mapping[str, object],
    taxonomy_refs: Sequence[str] = COMPLETION_COVERAGE_TAXONOMY_REFS,
) -> Path:
    """Materialize one deterministic checked projection from one ledger snapshot."""
    coverage = project_completion_coverage(ledger_snapshot, source_binding)
    coverage_check = check_completion_coverage(
        coverage,
        active_clause_ids,
        owner_contract,
        taxonomy_refs,
    )
    completion_boundary = evaluate_completion_boundary(
        coverage_check,
        schedule_state_non_routing,
        open_work_state_non_routing,
        repair_state_non_routing,
        crossing_edge_state_non_routing,
        control_topology_ledger_snapshot,
    )
    artifact = {
        **coverage,
        "coverage_check": coverage_check,
        "completion_boundary": completion_boundary,
    }
    serialized = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    artifact_path = report_dir / "completion_coverage.json"
    report_dir.mkdir(parents=True, exist_ok=True)
    if artifact_path.exists():
        existing = artifact_path.read_text(encoding="utf-8")
        if existing != serialized:
            raise ValueError(f"completion coverage artifact conflict: {artifact_path}")
        return artifact_path
    artifact_path.write_text(serialized, encoding="utf-8")
    return artifact_path


def record_validation_failure_response(
    failing_contract: str,
    observation_level: str,
    cause_classification: str,
    intent_preservation: str,
    evidence: Sequence[str],
    same_intent_repair_or_escalation: str,
    repair_or_escalation_owner: str = "",
    repair_or_escalation_result: str = "",
    result_artifact_refs: Sequence[str] = (),
) -> dict[str, object]:
    """Create the canonical pointer-only validation failure record."""
    _validate_failure_taxonomy_values(cause_classification, intent_preservation)
    response = ValidationFailureResponse(
        failing_contract=_nonempty_text(failing_contract),
        observation_level=_nonempty_text(observation_level),
        cause_classification=_nonempty_text(cause_classification),
        intent_preservation=_nonempty_text(intent_preservation),
        evidence=_text_tuple(evidence, "evidence"),
        taxonomy_refs=COMPLETION_COVERAGE_TAXONOMY_REFS,
        same_intent_repair_or_escalation=_nonempty_text(
            same_intent_repair_or_escalation
        ),
        repair_or_escalation_owner=_nonempty_text(repair_or_escalation_owner),
        repair_or_escalation_result=_nonempty_text(repair_or_escalation_result),
        result_artifact_refs=_text_tuple(result_artifact_refs, "result_artifact_refs"),
    )
    return {
        "schema": "agent-canon.validation-failure-response.v1",
        "failing_contract": response.failing_contract,
        "observation_level": response.observation_level,
        "cause_classification": response.cause_classification,
        "intent_preservation": response.intent_preservation,
        "evidence": list(response.evidence),
        "taxonomy_refs": list(response.taxonomy_refs),
        "same_intent_repair_or_escalation": response.same_intent_repair_or_escalation,
        "repair_or_escalation_owner": response.repair_or_escalation_owner,
        "repair_or_escalation_result": response.repair_or_escalation_result,
        "result_artifact_refs": list(response.result_artifact_refs),
    }


def evaluate_completion_boundary(
    coverage_check: Mapping[str, object],
    schedule_state_non_routing: Mapping[str, object],
    open_work_state_non_routing: Mapping[str, object],
    repair_state_non_routing: Mapping[str, object],
    crossing_edge_state_non_routing: Mapping[str, object],
    control_topology_ledger_snapshot: Mapping[str, object],
) -> dict[str, object]:
    """Derive planned-work and delivery predicates from one topology snapshot."""
    open_repairs = list(repair_state_non_routing.get("open_repairs", []))
    open_edges = list(crossing_edge_state_non_routing.get("open_crossing_edges", []))
    _nonempty_text(control_topology_ledger_snapshot.get("observation_ref"))
    planned = bool(
        schedule_state_non_routing.get("w2_implementation_complete")
        and schedule_state_non_routing.get("w2_review_complete")
        and schedule_state_non_routing.get("source_freeze_review_complete")
        and open_work_state_non_routing.get("planned_work_complete")
        and not open_repairs
        and not open_edges
        and control_topology_ledger_snapshot.get("writer_release_order_complete")
    )
    delivery = bool(
        coverage_check.get("ok")
        and control_topology_ledger_snapshot.get("global_publication_state")
        == "publication_ready"
        and control_topology_ledger_snapshot.get("final_review_approved")
        and control_topology_ledger_snapshot.get("closeout_unlocked")
        and control_topology_ledger_snapshot.get("routing_gate") == "verified"
        and schedule_state_non_routing.get("formatter_and_static_checks_pass")
        and not open_repairs
        and not open_edges
    )
    return {
        "schema": "agent-canon.completion-boundary.v1",
        "all_planned_chunks_complete": planned,
        "overall_delivery_complete": delivery,
        "open_repairs": open_repairs,
        "open_crossing_edges": open_edges,
        "control_topology_observation_ref": _nonempty_text(
            control_topology_ledger_snapshot.get("observation_ref")
        ),
    }


def consume_checked_completion_coverage(
    completion_coverage_v1: Mapping[str, object],
    coverage_check: Mapping[str, object],
    completion_boundary: Mapping[str, object],
) -> dict[str, object]:
    """Consume the checked projection without rebuilding coverage or state."""
    if completion_coverage_v1.get("schema") != COMPLETION_COVERAGE_SCHEMA:
        raise ValueError("closeout requires agent-canon.completion-coverage.v1")
    if not coverage_check.get("ok"):
        return {"ready": False, "reason": "coverage_check_failed"}
    return {
        "ready": bool(completion_boundary.get("overall_delivery_complete")),
        "all_planned_chunks_complete": bool(
            completion_boundary.get("all_planned_chunks_complete")
        ),
        "overall_delivery_complete": bool(
            completion_boundary.get("overall_delivery_complete")
        ),
        "coverage_check": dict(coverage_check),
        "completion_boundary": dict(completion_boundary),
    }


def is_placeholder_only_section(text: str) -> bool:
    """Return whether the artifact still looks like an untouched template."""
    stripped = PLACEHOLDER_PATTERN.sub("", text).strip()
    stripped = "\n".join(
        line
        for line in stripped.splitlines()
        if line.strip()
        and not line.strip().startswith("#")
        and not line.strip().startswith("- Run ID:")
        and not line.strip().startswith("- Task:")
        and not line.strip().startswith("- Owner:")
        and not line.strip().startswith("- Created At")
        and not line.strip().startswith("|")
    ).strip()
    return not stripped


def section_has_content(text: str, heading: str) -> bool:
    """Return whether a markdown section exists and has non-placeholder content."""
    lines = text.splitlines()
    in_section = False
    body: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_section:
                break
            in_section = stripped == heading
            continue
        if in_section:
            body.append(line)
    if not in_section:
        return False
    body_text = PLACEHOLDER_PATTERN.sub("", "\n".join(body))
    body_text = "\n".join(line for line in body_text.splitlines() if line.strip()).strip()
    return bool(body_text)


def table_body_rows(text: str, heading: str) -> list[str]:
    """Return non-header table rows under one markdown section."""
    rows: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == heading
            continue
        if not in_section or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(not cell or set(cell) <= {"-"} for cell in cells):
            continue
        if any(
            cell in {"Clause ID", "Source Bucket", "Stage", "Unit ID", "Wave ID", "Time"}
            for cell in cells
        ):
            continue
        rows.append(stripped)
    return rows


def markdown_table_dict_rows(text: str, heading: str) -> list[dict[str, str]]:
    """Return markdown table rows as dictionaries under one level-2 heading."""
    rows: list[dict[str, str]] = []
    headers: list[str] | None = None
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == heading
            headers = None
            continue
        if not in_section or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(not cell or set(cell) <= {"-"} for cell in cells):
            continue
        if headers is None:
            headers = cells
            continue
        padded = cells + [""] * max(0, len(headers) - len(cells))
        rows.append({header: padded[index] for index, header in enumerate(headers)})
    return rows


def bullet_rows(text: str, heading: str) -> list[str]:
    """Return bullet rows under one markdown section."""
    rows: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == heading
            continue
        if not in_section:
            continue
        if stripped.startswith("- "):
            rows.append(stripped)
    return rows


def token_fields(line: str) -> dict[str, str]:
    """Parse whitespace-separated key=value fields from one evidence line."""
    data: dict[str, str] = {}
    for token in line.strip().strip("-").strip("`").split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        data[key.strip()] = value.strip("`'\"")
    return data


def _git_report_paths(workspace: Path, args: tuple[str, ...]) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", *args, "-z", "--", "reports"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        return []
    return [
        raw_path.decode("utf-8", errors="surrogateescape")
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    ]


def _normalized_git_path(path: str) -> str:
    """Return a POSIX-style Git path for classification."""
    return path.replace("\\", "/").strip("/")


def _is_relative_to(path: PurePosixPath, root: PurePosixPath) -> bool:
    """Return whether a POSIX path is equal to or nested under root."""
    return path == root or path.is_relative_to(root)


def is_mechanically_regenerated_report_path(path: str) -> bool:
    """Return whether one report path is a known mechanically regenerated output."""
    normalized = _normalized_git_path(path)
    candidate = PurePosixPath(normalized)
    if any(
        _is_relative_to(candidate, root)
        for root in MECHANICALLY_REGENERATED_REPORT_ROOTS
    ):
        return True
    return any(
        pattern.match(normalized)
        for pattern in MECHANICALLY_REGENERATED_REPORT_FILE_PATTERNS
    )


def generated_report_artifact_blockers(workspace: Path) -> list[str]:
    """Return regenerated report outputs that should not remain in the tree."""
    report_paths = {
        path: "tracked"
        for path in _git_report_paths(workspace, ())
        if is_mechanically_regenerated_report_path(path)
    }
    for path in _git_report_paths(
        workspace,
        ("--others", "--exclude-standard"),
    ):
        if is_mechanically_regenerated_report_path(path):
            report_paths.setdefault(path, "untracked")
    for path in _git_report_paths(
        workspace,
        ("--others", "--ignored", "--exclude-standard"),
    ):
        if is_mechanically_regenerated_report_path(path):
            report_paths.setdefault(path, "ignored")
    return [
        f"generated_report_artifact_{state}_left_in_tree:{path}"
        for path, state in sorted(report_paths.items())
    ]


def generated_eval_transient_blockers(workspace: Path) -> list[str]:
    """Return exact two-level eval producer stdout/stderr captures in the tree."""
    report_paths = {
        path: "tracked"
        for path in _git_report_paths(workspace, ())
        if EVAL_TRANSIENT_CAPTURE_PATTERN.fullmatch(_normalized_git_path(path))
    }
    for path in _git_report_paths(
        workspace,
        ("--others", "--exclude-standard"),
    ):
        if EVAL_TRANSIENT_CAPTURE_PATTERN.fullmatch(_normalized_git_path(path)):
            report_paths.setdefault(path, "untracked")
    for path in _git_report_paths(
        workspace,
        ("--others", "--ignored", "--exclude-standard"),
    ):
        if EVAL_TRANSIENT_CAPTURE_PATTERN.fullmatch(_normalized_git_path(path)):
            report_paths.setdefault(path, "ignored")
    return [
        f"generated_report_artifact_{state}_left_in_tree:{path}"
        for path, state in sorted(report_paths.items())
    ]


def join_artifact_blockers(blockers: Sequence[str]) -> str:
    """Render blockers for compact shell output."""
    return "|".join(blockers) if blockers else "none"


def report_artifact_placement_blockers(workspace: Path, report_dir: Path) -> list[str]:
    """Return generated report artifacts outside the active run bundle.

    Tracked durable reports are allowed. Tracked generated report roots and tracked
    agent run bundles outside the current run are blockers. Untracked generated
    report files are allowed only under the current run directory because runtime
    archive tooling collects one active run bundle at closeout. Ignored non-
    generated report paths are local cache and do not block closeout.
    """
    if not report_dir.resolve().is_relative_to(workspace.resolve()):
        return []
    report_paths = {}
    for path in _git_report_paths(workspace, ()):
        normalized = _normalized_git_path(path)
        if normalized.startswith("reports/agents/") or is_mechanically_regenerated_report_path(path):
            report_paths[path] = "tracked"
    for path in _git_report_paths(
        workspace,
        ("--others", "--exclude-standard"),
    ):
        report_paths.setdefault(path, "untracked")
    for path in _git_report_paths(
        workspace,
        ("--others", "--ignored", "--exclude-standard"),
    ):
        report_paths.setdefault(path, "ignored")

    blockers: list[str] = []
    report_root_metadata = {
        (report_dir.parent / ".active_run").resolve(),
        (report_dir.parent / ".active_run.sha256").resolve(),
    }
    for path, state in sorted(report_paths.items()):
        candidate = workspace / path
        if candidate.resolve() in report_root_metadata:
            continue
        if candidate.resolve().is_relative_to(report_dir.resolve()):
            continue
        if state == "ignored" and not is_mechanically_regenerated_report_path(path):
            continue
        blockers.append(f"report_artifact_{state}_outside_current_run:{path}")
    return blockers


def actual_wave_event_fields(workflow_monitoring_text: str) -> list[dict[str, str]]:
    """Return structured Actual Wave Events rows from workflow_monitoring.md."""
    rows: list[dict[str, str]] = []
    in_section = False
    for line in workflow_monitoring_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == "## Actual Wave Events"
            continue
        if not in_section or not stripped.startswith("- wave_event="):
            continue
        rows.append(token_fields(stripped))
    return rows


def _split_csv_field(value: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in value.split(",")
        if item.strip() and item.strip().lower() != "none"
    )


def _candidate_evidence_paths(
    value: str,
    report_dir: Path | None,
    workspace: Path | None,
    evidence_field: str,
) -> tuple[Path, ...]:
    """Return policy-allowed filesystem paths for one evidence token."""
    if is_empty_policy_value(value):
        return ()
    path = Path(value)
    raw_candidates: list[Path] = []
    if path.is_absolute():
        raw_candidates.append(path)
    else:
        if workspace is not None:
            raw_candidates.append(workspace / path)
        if report_dir is not None:
            raw_candidates.append(report_dir / path)
            raw_candidates.append(report_dir.parent / path)
            if len(path.parts) == 1:
                raw_candidates.append(report_dir.parent / path.name)
    if report_dir is None:
        return ()
    current_run_root = report_dir.resolve()
    report_root = report_dir.parent.resolve()
    candidates: list[Path] = []
    for candidate in raw_candidates:
        resolved = candidate.resolve()
        if evidence_field == "fresh_wave_evidence":
            if resolved.is_relative_to(current_run_root):
                candidates.append(candidate)
        elif (
            evidence_field == "fresh_run_bundle"
            and resolved.parent == report_root
            and resolved != current_run_root
        ):
            candidates.append(candidate)
    return tuple(dict.fromkeys(candidates))


def _raw_evidence_paths(
    value: str,
    report_dir: Path | None,
    workspace: Path | None,
) -> tuple[Path, ...]:
    """Return unfiltered path interpretations for diagnostics."""
    if is_empty_policy_value(value):
        return ()
    path = Path(value)
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        if workspace is not None:
            candidates.append(workspace / path)
        if report_dir is not None:
            candidates.append(report_dir / path)
            candidates.append(report_dir.parent / path)
    if report_dir is not None:
        if len(path.parts) == 1:
            candidates.append(report_dir.parent / path.name)
    return tuple(dict.fromkeys(candidates))


def _evidence_path_exists(
    value: str,
    report_dir: Path | None,
    workspace: Path | None,
    *,
    require_dir: bool = False,
    evidence_field: str,
) -> bool:
    """Return whether one evidence token points at an existing artifact."""
    candidates = _candidate_evidence_paths(value, report_dir, workspace, evidence_field)
    if not candidates:
        return False
    if require_dir:
        return any(candidate.is_dir() for candidate in candidates)
    return any(candidate.exists() for candidate in candidates)


def _evidence_path_outside_scope(
    value: str,
    report_dir: Path | None,
    workspace: Path | None,
    evidence_field: str,
) -> bool:
    """Return whether evidence exists but outside the allowed run-artifact scope."""
    raw_existing = any(
        candidate.exists()
        for candidate in _raw_evidence_paths(value, report_dir, workspace)
    )
    if not raw_existing:
        return False
    return not _candidate_evidence_paths(value, report_dir, workspace, evidence_field)


def _actual_waves_by_id(
    actual_rows: list[dict[str, str]],
) -> tuple[dict[str, dict[str, str]], list[str]]:
    actual_by_id: dict[str, dict[str, str]] = {}
    blockers: list[str] = []
    for row in actual_rows:
        wave_id = row.get("wave_id", "").strip()
        if not wave_id:
            blockers.append("workflow_monitoring.md:actual_wave_missing:wave_id")
            continue
        if wave_id in actual_by_id:
            blockers.append(f"workflow_monitoring.md:actual_wave_duplicate:{wave_id}")
            continue
        actual_by_id[wave_id] = row
    return actual_by_id, blockers


def _actual_wave_field_blockers(
    wave_id: str,
    actual: dict[str, str],
    report_dir: Path | None = None,
    workspace: Path | None = None,
) -> list[str]:
    blockers = [
        f"workflow_monitoring.md:actual_wave_field_missing:{wave_id}:{field}"
        for field in REQUIRED_ACTUAL_WAVE_FIELDS
        if actual.get(field, "").strip() in {"", "missing"}
    ]
    if actual.get("event_kind") == "mid_task_user_input":
        blockers.extend(
            _mid_task_user_input_blockers(wave_id, actual, report_dir, workspace)
        )
    return blockers


def _mid_task_user_input_blockers(
    wave_id: str,
    actual: dict[str, str],
    report_dir: Path | None = None,
    workspace: Path | None = None,
) -> list[str]:
    """Return blockers for mid-task user input wave checkpoints."""
    blockers = [
        f"workflow_monitoring.md:mid_task_user_input_field_missing:{wave_id}:{field}"
        for field in MID_TASK_REQUIRED_WAVE_FIELDS
        if actual.get(field, "").strip().lower() in {"", "missing"}
    ]
    if is_empty_policy_value(actual.get("updated_packet", "")):
        blockers.append(
            f"workflow_monitoring.md:mid_task_user_input_field_missing:{wave_id}:updated_packet"
        )
    classification = actual.get("input_classification", "").strip()
    if not classification:
        return blockers
    if classification not in MID_TASK_CLASSIFICATION_ACTIONS:
        blockers.append(
            "workflow_monitoring.md:mid_task_user_input_invalid_classification:"
            f"{wave_id}:{classification}"
        )
        return blockers
    expected_spawn_authority = MID_TASK_SPAWN_AUTHORITY[classification]
    if actual.get("spawn_authority", "").strip() != expected_spawn_authority:
        blockers.append(
            "workflow_monitoring.md:mid_task_user_input_invalid_spawn_authority:"
            f"{wave_id}:expected={expected_spawn_authority}"
        )
    expected_action = MID_TASK_CLASSIFICATION_ACTIONS[classification]
    if actual.get("redispatch_action", "").strip() != expected_action:
        blockers.append(
            "workflow_monitoring.md:mid_task_user_input_invalid_redispatch_action:"
            f"{wave_id}:expected={expected_action}"
        )
    expected_scope = MID_TASK_CLASSIFICATION_SCOPE_STATUS[classification]
    if actual.get("scope_status", "").strip() != expected_scope:
        blockers.append(
            "workflow_monitoring.md:mid_task_user_input_invalid_scope_status:"
            f"{wave_id}:expected={expected_scope}"
        )
    target_agents = actual.get("target_agents", "").strip()
    if classification in MID_TASK_TARGET_REQUIRED_CLASSIFICATIONS and is_empty_policy_value(
        target_agents
    ):
        blockers.append(
            f"workflow_monitoring.md:mid_task_user_input_field_missing:{wave_id}:target_agents"
        )
    spawned_roles = actual.get("spawned_roles", "").strip()
    if classification in MID_TASK_SPAWNED_ROLES_REQUIRED_CLASSIFICATIONS:
        if is_empty_policy_value(spawned_roles):
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_field_missing:"
                f"{wave_id}:spawned_roles"
            )
    if classification in MID_TASK_EVIDENCE_FIELDS:
        skipped_roles = actual.get("skipped_roles", "")
        if has_reuse_marker(skipped_roles):
            markers = ",".join(MID_TASK_REUSE_MARKERS)
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_reused_agent_forbidden:"
                f"{wave_id}:{markers}"
            )
    evidence_field = MID_TASK_EVIDENCE_FIELDS.get(classification)
    if evidence_field:
        evidence_value = actual.get(evidence_field, "").strip()
        if is_empty_policy_value(evidence_value):
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_field_missing:"
                f"{wave_id}:{evidence_field}"
            )
        elif _evidence_path_outside_scope(
            evidence_value,
            report_dir,
            workspace,
            evidence_field,
        ):
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_evidence_outside_scope:"
                f"{wave_id}:{evidence_field}:{evidence_value}"
            )
        elif not _evidence_path_exists(
            evidence_value,
            report_dir,
            workspace,
            require_dir=evidence_field == "fresh_run_bundle",
            evidence_field=evidence_field,
        ):
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_evidence_missing:"
                f"{wave_id}:{evidence_field}:{evidence_value}"
            )
    return blockers


def _actual_wave_mismatch_blockers(
    wave_id: str,
    planned: dict[str, str],
    actual: dict[str, str],
) -> list[str]:
    blockers: list[str] = []
    for schedule_field, event_field in WAVE_COMPARISON_FIELDS:
        planned_value = planned.get(schedule_field, "").strip()
        if planned_value and planned_value != actual.get(event_field, "").strip():
            blockers.append(
                "workflow_monitoring.md:actual_wave_mismatch:"
                f"{wave_id}:{event_field}"
            )
    if _split_csv_field(planned.get("Spawned Roles", "")) != _split_csv_field(
        actual.get("spawned_roles", "")
    ):
        blockers.append(f"workflow_monitoring.md:actual_wave_mismatch:{wave_id}:spawned_roles")
    if _split_csv_field(planned.get("Role Instances", "")) != _split_csv_field(
        actual.get("role_instances", "")
    ):
        blockers.append(f"workflow_monitoring.md:actual_wave_mismatch:{wave_id}:role_instances")
    return blockers


def wave_reconciliation_blockers(
    schedule_text: str,
    workflow_monitoring_text: str,
    lifecycle_status: dict[str, str],
    report_dir: Path | None = None,
    workspace: Path | None = None,
) -> list[str]:
    """Return blockers when planned subagent waves do not match observed events."""
    planned_rows = markdown_table_dict_rows(schedule_text, "## Agent Wave Ledger")
    planned_by_id = {
        row.get("Wave ID", "").strip(): row
        for row in planned_rows
        if row.get("Wave ID", "").strip()
    }
    blockers: list[str] = []

    if lifecycle_status.get("agent_wave_ledger_status") == "not_applicable":
        actual_rows = actual_wave_event_fields(workflow_monitoring_text)
        if planned_by_id or actual_rows:
            blockers.append("subagent_lifecycle:not_applicable_but_wave_evidence_present")
        return blockers

    actual_by_id, actual_id_blockers = _actual_waves_by_id(
        actual_wave_event_fields(workflow_monitoring_text)
    )
    blockers.extend(actual_id_blockers)

    for wave_id, planned in planned_by_id.items():
        actual = actual_by_id.get(wave_id)
        if actual is None:
            blockers.append(f"workflow_monitoring.md:actual_wave_missing:{wave_id}")
            continue
        blockers.extend(
            _actual_wave_field_blockers(wave_id, actual, report_dir, workspace)
        )
        blockers.extend(_actual_wave_mismatch_blockers(wave_id, planned, actual))
    for wave_id in sorted(set(actual_by_id) - set(planned_by_id)):
        blockers.append(f"workflow_monitoring.md:actual_wave_without_plan:{wave_id}")
    return blockers


def check_schedule_artifact(text: str) -> list[str]:
    """Return blockers for schedule.md."""
    blockers: list[str] = []
    required_tables = (
        ("## Stage Plan", "stage_plan_empty"),
        ("## Clause Coverage", "clause_coverage_empty"),
        ("## Planned Work Units", "planned_work_units_empty"),
        ("## Agent Wave Ledger", "agent_wave_ledger_empty"),
    )
    for heading, slug in required_tables:
        if not table_body_rows(text, heading):
            blockers.append(f"schedule.md:{slug}")
    return blockers


def check_work_log_artifact(text: str) -> list[str]:
    """Return blockers for work_log.md."""
    blockers: list[str] = []
    if not section_has_content(text, "## Entries"):
        blockers.append("work_log.md:section_empty_or_missing:entries")
        return blockers
    if not bullet_rows(text, "## Entries"):
        blockers.append("work_log.md:entries_empty")
    return blockers


def final_review_decision_lines(text: str) -> list[str]:
    """Return normalized non-placeholder lines from a final-review Decision section."""
    lines: list[str] = []
    in_decision = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_decision:
                break
            in_decision = stripped == "## Decision"
            continue
        if in_decision:
            normalized = PLACEHOLDER_PATTERN.sub("", line).strip()
            if normalized:
                lines.append(normalized)
    return lines


def has_approve_decision(text: str) -> bool:
    """Return whether a final-review Decision section contains an exact approve decision."""
    return any(APPROVE_DECISION_PATTERN.fullmatch(line) for line in final_review_decision_lines(text))


def check_final_review_artifact(text: str) -> list[str]:
    """Return blockers for final_review.md."""
    blockers: list[str] = []
    if is_placeholder_only_section(text):
        blockers.append("final_review.md:placeholder_only")
    if not section_has_content(text, "## Decision"):
        blockers.append("final_review.md:section_empty_or_missing:decision")
        return blockers
    if not has_approve_decision(text):
        blockers.append("final_review.md:decision_not_approve")
    return blockers
