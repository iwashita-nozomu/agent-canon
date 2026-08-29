#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Materializes typed external projection acknowledgements for canonical local review events.
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md owns external projection acknowledgement schemas.
# upstream implementation ./artifact_identity.py provides canonical JSON and body hashing.
# downstream implementation ./review_dispatch.py binds Codex reviewer dispatch projections.
# downstream implementation ./github_publish.py binds GitHub PR-head and review-state projections.
# downstream implementation ./publication_integrator.py verifies current external projections before CAS.
# downstream implementation ../../tests/agent_tools/test_external_artifact_binding.py validates mapping and null rules.
# @dependency-end
"""Map provider readback to one canonical local review event without authority inversion."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from tools.runtime.artifacts.artifact_identity import canonical_body_sha256, canonical_json_bytes

ACK_SCHEMA = "agent-canon.external-projection-acknowledgement.v1"
LOCAL_EVENT_SCHEMA = "agent-canon.terminal-resume-event.v3"
FORBIDDEN_RECEIPT_FIELDS = frozenset(
    {
        "provider_receipt_bytes_sha256",
        "receipt_artifact_identity_record_id",
        "receipt_artifact_identity_record_body_sha256",
        "dispatch_receipt_path",
        "dispatch_receipt_sha256",
        "dispatch_receipt_blob",
    }
)
CODEX_STATUS_MAP = {
    "running": ("dispatch_pending", "dispatched"),
    "completed": ("review_pending", "review_returned"),
    "errored": ("dispatch_pending", "dispatch_blocked"),
    "shutdown": ("dispatch_pending", "dispatch_blocked"),
}
GITHUB_STATUS_MAP = {
    "pending": ("review_pending", "review_pending"),
    "approved": ("review_pending", "approved"),
    "changes_requested": ("review_pending", "revise"),
    "dismissed": ("review_pending", "review_pending"),
}


class ExternalProjectionError(ValueError):
    """Typed external projection failure."""

    def __init__(self, code: str, detail: str = "") -> None:
        """Initialize one stable failure."""
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}:{detail}")


def _contains_forbidden_field(value: object) -> str | None:
    """Return the first forbidden receipt-byte field found recursively."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in FORBIDDEN_RECEIPT_FIELDS:
                return str(key)
            nested = _contains_forbidden_field(item)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for item in value:
            nested = _contains_forbidden_field(item)
            if nested is not None:
                return nested
    return None


def _required_text(mapping: Mapping[str, object], field: str) -> str:
    """Return one required non-empty field."""
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ExternalProjectionError("external_projection:field_missing", field)
    return value.strip()


def _required_int(mapping: Mapping[str, object], field: str) -> int:
    """Return one required positive integer."""
    value = mapping.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ExternalProjectionError("external_projection:field_invalid", field)
    return value


def _candidate_fields(local_event: Mapping[str, object]) -> dict[str, object]:
    """Return exact candidate fields from the local authority event."""
    return {
        "candidate_id": _required_text(local_event, "candidate_id"),
        "candidate_revision": _required_int(local_event, "candidate_revision"),
        "candidate_body_sha256": _required_text(
            local_event,
            "candidate_body_sha256",
        ),
        "candidate_commit": _required_text(local_event, "candidate_commit"),
        "candidate_tree": _required_text(local_event, "candidate_tree"),
    }


def _projection_kind(
    local_event: Mapping[str, object], provider: Mapping[str, object]
) -> str:
    """Derive the closed projection kind from event and provider facts."""
    provider_kind = _required_text(provider, "provider_kind")
    event_kind = _required_text(local_event, "event_kind")
    if (
        provider_kind == "codex_runtime"
        and event_kind == "terminal_resume_dispatch_observed"
    ):
        return "codex_review_dispatch"
    if provider_kind == "github" and event_kind == "review_decision_recorded":
        return "github_review_decision"
    if provider_kind == "github" and event_kind == "candidate_materialized":
        return "github_pr_head"
    raise ExternalProjectionError("external_projection:projection_kind_mismatch")


def _mapped_status(
    projection_kind: str,
    provider_status: str,
) -> tuple[str, str, str]:
    """Return exact local transition and mapping rule."""
    if projection_kind == "codex_review_dispatch":
        if provider_status not in CODEX_STATUS_MAP:
            raise ExternalProjectionError("external_projection:provider_status_invalid")
        before, after = CODEX_STATUS_MAP[provider_status]
        return before, after, "agent-canon.projection-map.codex-dispatch.v1"
    if provider_status not in GITHUB_STATUS_MAP:
        raise ExternalProjectionError("external_projection:provider_status_invalid")
    before, after = GITHUB_STATUS_MAP[provider_status]
    rule = (
        "agent-canon.projection-map.github-review.v1"
        if projection_kind == "github_review_decision"
        else "agent-canon.projection-map.github-pr-head.v1"
    )
    return before, after, rule


def materialize_external_projection_acknowledgement(
    local_event: Mapping[str, object],
    provider_readback: Mapping[str, object],
) -> dict[str, object]:
    """Materialize one external acknowledgement bound to a prior local event."""
    forbidden = _contains_forbidden_field(local_event) or _contains_forbidden_field(
        provider_readback
    )
    if forbidden is not None:
        raise ExternalProjectionError(
            "external_projection:receipt_byte_identity_forbidden",
            forbidden,
        )
    if local_event.get("schema") not in {
        LOCAL_EVENT_SCHEMA,
        "agent-canon.review-decision-event.v1",
        "agent-canon.review-candidate-event.v1",
    }:
        raise ExternalProjectionError("external_projection:local_event_mismatch")
    projection_kind = _projection_kind(local_event, provider_readback)
    provider_status = _required_text(provider_readback, "provider_status")
    local_from, local_to, rule = _mapped_status(projection_kind, provider_status)
    candidate = _candidate_fields(local_event)
    provider_kind = _required_text(provider_readback, "provider_kind")
    provider_object_id = _required_text(provider_readback, "provider_object_id")
    provider_object_version = _required_text(
        provider_readback,
        "provider_object_version",
    )
    provider_object_kind = _required_text(
        provider_readback,
        "provider_object_kind",
    )
    provider_readback_payload = {
        key: value
        for key, value in provider_readback.items()
        if key != "provider_readback_sha256"
    }
    readback_sha256 = hashlib.sha256(
        canonical_json_bytes(provider_readback_payload)
    ).hexdigest()
    supplied_readback_hash = provider_readback.get("provider_readback_sha256")
    if supplied_readback_hash not in {None, readback_sha256}:
        raise ExternalProjectionError(
            "external_projection:provider_readback_hash_mismatch"
        )
    record: dict[str, object] = {
        "schema": ACK_SCHEMA,
        "schema_version": 1,
        "external_projection_ack_id": "",
        "projection_kind": projection_kind,
        "aggregate_identity": _required_text(local_event, "aggregate_identity"),
        "local_event_schema": _required_text(local_event, "schema"),
        "local_event_kind": _required_text(local_event, "event_kind"),
        "local_event_id": _required_text(
            local_event,
            "resume_event_id"
            if local_event.get("schema") == LOCAL_EVENT_SCHEMA
            else "event_id",
        ),
        "local_event_body_sha256": _required_text(
            local_event,
            "resume_event_body_sha256"
            if local_event.get("schema") == LOCAL_EVENT_SCHEMA
            else "event_body_sha256",
        ),
        "local_event_order_index": _required_int(
            local_event,
            "event_order_index",
        ),
        "review_lineage_id": _required_text(local_event, "review_lineage_id"),
        "review_request_id": _required_text(local_event, "review_request_id"),
        "review_context_id": _required_text(local_event, "review_context_id"),
        "review_frame_id": local_event.get("review_frame_id"),
        **candidate,
        "provider_kind": provider_kind,
        "provider_instance_id": provider_readback.get("provider_instance_id"),
        "provider_account_id": provider_readback.get("provider_account_id"),
        "provider_repository_id": provider_readback.get("provider_repository_id"),
        "provider_object_kind": provider_object_kind,
        "provider_object_id": provider_object_id,
        "provider_object_version": provider_object_version,
        "provider_parent_object_id": provider_readback.get("provider_parent_object_id"),
        "provider_operation_id": provider_readback.get("provider_operation_id"),
        "head_ref": provider_readback.get("head_ref"),
        "head_oid": provider_readback.get("head_oid"),
        "head_tree": provider_readback.get("head_tree"),
        "local_from_status": local_from,
        "local_to_status": local_to,
        "provider_status": provider_status,
        "status_mapping_rule_id": rule,
        "provider_readback_sha256": readback_sha256,
        "acknowledgement_order_index": _required_int(
            provider_readback,
            "acknowledgement_order_index",
        ),
        "external_projection_ack_body_sha256": "",
    }
    if provider_kind == "codex_runtime":
        for field in ("head_ref", "head_oid", "head_tree"):
            if record[field] is not None:
                raise ExternalProjectionError(
                    "external_projection:null_rule_mismatch", field
                )
        if (
            record["provider_instance_id"] is None
            or record["provider_parent_object_id"] is None
        ):
            raise ExternalProjectionError("external_projection:null_rule_mismatch")
    else:
        if record["provider_repository_id"] is None:
            raise ExternalProjectionError("external_projection:null_rule_mismatch")
        if projection_kind == "github_pr_head":
            for field in ("head_ref", "head_oid", "head_tree"):
                if not isinstance(record[field], str) or not record[field]:
                    raise ExternalProjectionError(
                        "external_projection:null_rule_mismatch",
                        field,
                    )
            if (
                record["head_oid"] != candidate["candidate_commit"]
                or record["head_tree"] != candidate["candidate_tree"]
            ):
                raise ExternalProjectionError("external_projection:head_mismatch")
    seed = {
        key: value
        for key, value in record.items()
        if key
        not in {
            "external_projection_ack_id",
            "external_projection_ack_body_sha256",
        }
    }
    record["external_projection_ack_id"] = (
        "external-projection-ack:"
        + hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    )
    record["external_projection_ack_body_sha256"] = canonical_body_sha256(
        record,
        "external_projection_ack_body_sha256",
    )
    return record


def verify_external_projection_acknowledgement(
    local_event: Mapping[str, object],
    acknowledgement: Mapping[str, object],
) -> dict[str, object]:
    """Verify one acknowledgement against its local event and stored readback."""
    if (
        acknowledgement.get("schema") != ACK_SCHEMA
        or acknowledgement.get("schema_version") != 1
    ):
        raise ExternalProjectionError("external_projection:schema_mismatch")
    forbidden = _contains_forbidden_field(acknowledgement)
    if forbidden is not None:
        raise ExternalProjectionError(
            "external_projection:receipt_byte_identity_forbidden",
            forbidden,
        )
    local_id_field = (
        "resume_event_id"
        if local_event.get("schema") == LOCAL_EVENT_SCHEMA
        else "event_id"
    )
    local_hash_field = (
        "resume_event_body_sha256"
        if local_event.get("schema") == LOCAL_EVENT_SCHEMA
        else "event_body_sha256"
    )
    if acknowledgement.get("local_event_id") != local_event.get(local_id_field):
        raise ExternalProjectionError("external_projection:local_event_mismatch")
    if acknowledgement.get("local_event_body_sha256") != local_event.get(
        local_hash_field
    ):
        raise ExternalProjectionError("external_projection:local_event_hash_mismatch")
    candidate = _candidate_fields(local_event)
    for field, expected in candidate.items():
        if acknowledgement.get(field) != expected:
            raise ExternalProjectionError(
                "external_projection:candidate_mismatch", field
            )
    if acknowledgement.get(
        "external_projection_ack_body_sha256"
    ) != canonical_body_sha256(
        acknowledgement,
        "external_projection_ack_body_sha256",
    ):
        raise ExternalProjectionError("external_projection:body_hash_mismatch")
    seed = {
        key: value
        for key, value in acknowledgement.items()
        if key
        not in {
            "external_projection_ack_id",
            "external_projection_ack_body_sha256",
        }
    }
    expected_id = (
        "external-projection-ack:"
        + hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    )
    if acknowledgement.get("external_projection_ack_id") != expected_id:
        raise ExternalProjectionError("external_projection:id_mismatch")
    return {
        "schema": "agent-canon.external-projection-verification.v1",
        "ok": True,
        "external_projection_ack_id": expected_id,
        "local_event_id": acknowledgement["local_event_id"],
        "provider_object_id": acknowledgement["provider_object_id"],
        "provider_status": acknowledgement["provider_status"],
    }
