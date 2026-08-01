#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns the machine-readable AgentCanon update lifecycle schemas, identity guards, receipts, and close token mechanics.
# upstream design ../../agents/skills/agent-orchestration.md owns Decision Sufficiency meaning and validation.
# upstream design ../../documents/agent-canon/agent-canon-update-route.md owns the source update and projection transaction.
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md owns the source PR sequence.
# upstream implementation ./artifact_identity.py provides canonical JSON serialization.
# upstream implementation ../../tools/ci/check_agent_canon_pr.py provides the authoritative G2 owner API consumed through SourceProjectionGateOwnerApis.
# upstream implementation ./github_publish.py provides the authoritative G3 owner API consumed through SourceProjectionGateOwnerApis.
# downstream implementation ./tool_calls.py materializes lifecycle-bound subagent and close ToolCall packets.
# downstream implementation ./github_publish.py consumes immutable pull-request lifecycle and gate evidence.
# downstream implementation ./publication_integrator.py consumes candidate CAS and publication receipts.
# downstream implementation ./task_close.py consumes closeout coverage without revalidating upstream gates.
# downstream implementation ../../tools/update_agent_canon.sh consumes queue and dependency-frontier receipts.
# downstream implementation ../../tests/agent_tools/test_publication_integrator.py validates lifecycle mechanics.
# downstream implementation ../../tests/agent_tools/test_task_start_and_close.py validates terminal cleanup guards.
# @dependency-end
"""Canonical mechanics for resumable AgentCanon update transactions.

Decision Sufficiency policy deliberately does not live here.  This module only
preserves an orchestration-owner verdict and implements the downstream update,
publication, projection, and nested-agent lifecycle records.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from artifact_identity import canonical_body_sha256, canonical_json_bytes


@dataclass(frozen=True)
class SourceMainReadbackIdentity:
    """Authoritative source-main commit/tree observed after publication."""

    commit_sha: str
    tree_sha: str


@dataclass(frozen=True)
class SourceProjectionGateOwnerApis:
    """Authoritative G2/G3 owner APIs consumed by lifecycle aggregation."""

    generated_completeness_check_ids: tuple[str, ...]
    materialize_generated_completeness_receipt: Callable[..., dict[str, object]]
    materialize_pr_identity_gate: Callable[..., dict[str, object]]

DECISION_SUFFICIENCY_SCHEMA = "agent-canon.decision-sufficiency.v1"
SNAPSHOT_SCHEMA = "agent-canon.snapshot.v1"
EVIDENCE_IDENTITY_SCHEMA = "agent-canon.evidence-identity.v1"
UPDATE_TRANSACTION_SCHEMA = "agent-canon.update-transaction.v1"
CHECKPOINT_RECEIPT_SCHEMA = "agent-canon.checkpoint-receipt.v1"
GATE_VERDICT_SCHEMA = "agent-canon.gate-verdict.v1"
SOURCE_MAIN_REBIND_SCHEMA = "agent-canon.source-main-rebind-receipt.v1"
CANDIDATE_FREEZE_SCHEMA = "agent-canon.candidate-freeze-receipt.v1"
CANDIDATE_REVIEW_SCHEMA = "agent-canon.candidate-review-receipt.v1"
CANDIDATE_CAS_SCHEMA = "agent-canon.candidate-cas-receipt.v1"
PUBLICATION_READBACK_SCHEMA = "agent-canon.publication-readback-receipt.v1"
SOURCE_PROJECTION_PACKET_SCHEMA = "agent-canon.source-projection-packet.v1"
QUEUE_RECEIPT_SCHEMA = "agent-canon.queue-receipt.v1"
DEPENDENCY_FRONTIER_SCHEMA = "agent-canon.dependency-frontier.v1"
PULL_REQUEST_LIFECYCLE_SCHEMA = "agent-canon.pull-request-lifecycle.v1"
DURABLE_HANDBACK_SCHEMA = "agent-canon.durable-handback.v1"
DESCENDANT_CLOSE_RECEIPT_SCHEMA = "agent-canon.descendant-close-receipt.v1"
RESERVATION_RELEASE_RECEIPT_SCHEMA = "agent-canon.reservation-release-receipt.v1"
CLEANUP_PROOF_SCHEMA = "agent-canon.cleanup-proof.v1"
CLOSE_AGENT_TOOL_CALL_SCHEMA = "agent-canon.close-agent-tool-call.v1"
CLOSE_AGENT_ARGS_SCHEMA = "agent-canon.close-agent.args.v1"

GATE_IDS = ("G1", "G2", "G3", "G4", "G5", "G6")
CHECKPOINT_IDS = (
    "prepare",
    "generate",
    "G1",
    "G2",
    "G3",
    "source_main_readback",
    "queue",
    "frontier",
    "G4",
    "remote_readback",
    "G5",
    "handback",
    "descendants",
    "reservations",
    "cleanup",
    "G6",
    "nested_lifecycle_cleanup",
)
TRANSACTION_STATES = (
    "created",
    "prepared",
    "generated",
    "gates_ready",
    "reviewed",
    "pr_open",
    "pr_merged",
    "source_main_readback",
    "queue_enqueued",
    "frontier_accepted",
    "remote_readback",
    "durable_handback",
    "descendants_closed",
    "reservations_released",
    "cleanup_proven",
    "nested_lifecycle_cleanup",
    "closed",
    "failed",
    "successor_required",
)
CLOSE_LIFECYCLE_STATES = (
    "durable_handback",
    "descendants_closed",
    "reservations_released",
    "cleanup_proven",
    "nested_lifecycle_cleanup",
    "terminal",
)
PR_KINDS = ("user", "fork", "contributor")
PR_STATES = (
    "draft",
    "ready",
    "permission_unknown",
    "permission_denied",
    "changes_requested",
    "external_review",
    "merged",
    "closed_head",
    "multiple_remotes",
    "conflict_successor",
)
PR_OPEN_STATES = frozenset(
    {
        "draft",
        "ready",
        "permission_unknown",
        "permission_denied",
        "changes_requested",
        "external_review",
    }
)
PR_REVIEWABLE_STATES = frozenset(
    {"ready", "changes_requested", "external_review"}
)
PULL_REQUEST_BRANCH_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "user": {
        "required": ("user_identity",),
        "forbidden": (
            "fork_identity",
            "contributor_identity",
            "contributor_diff",
        ),
    },
    "fork": {
        "required": ("fork_identity",),
        "forbidden": (
            "user_identity",
            "contributor_identity",
            "contributor_diff",
        ),
    },
    "contributor": {
        "required": ("contributor_identity", "contributor_diff"),
        "forbidden": ("user_identity", "fork_identity"),
    },
}

GATE_CONTRACTS: dict[str, dict[str, object]] = {
    "G1": {
        "invariant": "source_correctness",
        "owners": (
            "tools/agent_tools/publication_integrator.py#resolve_publication_eligibility",
        ),
    },
    "G2": {
        "invariant": "generated_completeness",
        "owners": (
            "tools/ci/check_agent_canon_pr.py#materialize_generated_completeness_receipt",
        ),
    },
    "G3": {
        "invariant": "pr_identity_cas",
        "owners": (
            "tools/agent_tools/publication_integrator.py#resolve_publication_authority",
            "tools/agent_tools/github_publish.py#materialize_pr_identity_gate",
        ),
    },
    "G4": {
        "invariant": "parent_projection_integrity",
        "owners": ("tools/update_agent_canon.sh#accept_dependency_frontier",),
    },
    "G5": {
        "invariant": "remote_publication_readback",
        "owners": (
            "tools/agent_tools/publication_integrator.py#integrate_publication",
        ),
    },
    "G6": {
        "invariant": "nested_lifecycle_cleanup",
        "owners": (
            "tools/agent_tools/tool_calls.py#materialize_close_agent_tool_call",
        ),
    },
}

_STATE_CHECKPOINT_PREFIX: dict[str, int] = {
    "created": 0,
    "prepared": 1,
    "generated": 2,
    "gates_ready": 4,
    "reviewed": 4,
    "pr_open": 5,
    "pr_merged": 5,
    "source_main_readback": 6,
    "queue_enqueued": 7,
    "frontier_accepted": 9,
    "remote_readback": 11,
    "durable_handback": 12,
    "descendants_closed": 13,
    "reservations_released": 14,
    "cleanup_proven": 15,
    "nested_lifecycle_cleanup": 17,
    "closed": len(CHECKPOINT_IDS),
}

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_EVIDENCE = re.compile(r"^evidence:[0-9a-f]{64}$")
_HASH_ID = re.compile(
    r"^(?:tx|snapshot|rebind|freeze|review|cas|publication-readback|queue|"
    r"queue-key|frontier|frontier-key|pr-successor|close-token):[0-9a-f]{64}$"
)


class LifecycleContractError(ValueError):
    """Stable machine failure for one lifecycle contract violation."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}:{detail}")


def _fail(code: str, detail: str = "") -> None:
    raise LifecycleContractError(code, detail)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str) for key in value
    ):
        _fail("lifecycle:mapping_required", field)
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, (list, tuple)):
        _fail("lifecycle:sequence_required", field)
    return cast(Sequence[object], value)


def _exact_keys(
    record: Mapping[str, object],
    required: Sequence[str],
    *,
    optional: Sequence[str] = (),
    field: str,
) -> None:
    required_set = set(required)
    actual = set(record)
    missing = sorted(required_set - actual)
    extra = sorted(actual - required_set - set(optional))
    if missing:
        _fail("lifecycle:field_missing", f"{field}:{','.join(missing)}")
    if extra:
        _fail("lifecycle:field_forbidden", f"{field}:{','.join(extra)}")


def _string(value: object, field: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        _fail("lifecycle:string_invalid", field)
    return value


def _one_of(value: object, allowed: Sequence[str], field: str) -> str:
    rendered = _string(value, field)
    if rendered not in allowed:
        _fail("lifecycle:enum_invalid", field)
    return rendered


def _pattern(value: object, pattern: re.Pattern[str], field: str) -> str:
    rendered = _string(value, field)
    if pattern.fullmatch(rendered) is None:
        _fail("lifecycle:identity_invalid", field)
    return rendered


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        _fail("lifecycle:boolean_invalid", field)
    return value


def _positive_int(value: object, field: str, *, zero_allowed: bool = False) -> int:
    minimum = 0 if zero_allowed else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail("lifecycle:integer_invalid", field)
    return value


def _rfc3339(value: object, field: str) -> str:
    rendered = _string(value, field)
    try:
        datetime.fromisoformat(rendered.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LifecycleContractError("lifecycle:timestamp_invalid", field) from exc
    return rendered


def _string_list(
    value: object,
    field: str,
    *,
    pattern: re.Pattern[str] | None = None,
    nonempty: bool = False,
    unique: bool = True,
) -> tuple[str, ...]:
    items = _sequence(value, field)
    if nonempty and not items:
        _fail("lifecycle:sequence_empty", field)
    rendered: list[str] = []
    for index, item in enumerate(items):
        text = _string(item, f"{field}[{index}]")
        if pattern is not None and pattern.fullmatch(text) is None:
            _fail("lifecycle:identity_invalid", f"{field}[{index}]")
        rendered.append(text)
    if unique and len(rendered) != len(set(rendered)):
        _fail("lifecycle:duplicate_value", field)
    return tuple(rendered)


def _schema(record: Mapping[str, object], expected: str) -> None:
    if record.get("schema") != expected:
        _fail("lifecycle:schema_invalid", expected)


def _clone(record: Mapping[str, object]) -> dict[str, object]:
    return cast(dict[str, object], json.loads(canonical_json_bytes(record)))


def _validate_timing(value: object) -> Mapping[str, object]:
    timing = _mapping(value, "binding.timing")
    _exact_keys(
        timing,
        (
            "started_at",
            "finished_at",
            "last_attempt_at",
            "duration_ms",
            "attempt",
            "replayed",
        ),
        field="binding.timing",
    )
    _rfc3339(timing["started_at"], "binding.timing.started_at")
    if timing["finished_at"] is not None:
        _rfc3339(timing["finished_at"], "binding.timing.finished_at")
    _rfc3339(timing["last_attempt_at"], "binding.timing.last_attempt_at")
    _positive_int(timing["duration_ms"], "binding.timing.duration_ms", zero_allowed=True)
    _positive_int(timing["attempt"], "binding.timing.attempt")
    _bool(timing["replayed"], "binding.timing.replayed")
    return timing


def validate_record_binding(value: object) -> dict[str, object]:
    """Validate and return the sole immutable record identity envelope."""
    binding = _mapping(value, "binding")
    _exact_keys(
        binding,
        (
            "transaction_id",
            "snapshot_id",
            "candidate_sha",
            "tree_sha",
            "input_digest",
            "tool_id",
            "tool_version",
            "evidence_ref",
            "evidence_digest",
            "timing",
        ),
        field="binding",
    )
    transaction_id = _pattern(binding["transaction_id"], _HASH_ID, "binding.transaction_id")
    snapshot_id = _pattern(binding["snapshot_id"], _HASH_ID, "binding.snapshot_id")
    if not transaction_id.startswith("tx:"):
        _fail("lifecycle:identity_invalid", "binding.transaction_id")
    if not snapshot_id.startswith("snapshot:"):
        _fail("lifecycle:identity_invalid", "binding.snapshot_id")
    _pattern(binding["candidate_sha"], _HEX40, "binding.candidate_sha")
    _pattern(binding["tree_sha"], _HEX40, "binding.tree_sha")
    _pattern(binding["input_digest"], _SHA256, "binding.input_digest")
    _string(binding["tool_id"], "binding.tool_id")
    _string(binding["tool_version"], "binding.tool_version")
    _pattern(binding["evidence_ref"], _EVIDENCE, "binding.evidence_ref")
    _pattern(binding["evidence_digest"], _SHA256, "binding.evidence_digest")
    _validate_timing(binding["timing"])
    return _clone(binding)


def binding_identity(value: object) -> tuple[str, ...]:
    """Return the fields that remain stable across retries and evidence stages."""
    binding = validate_record_binding(value)
    return tuple(
        cast(str, binding[field])
        for field in (
            "transaction_id",
            "snapshot_id",
            "candidate_sha",
            "tree_sha",
            "input_digest",
            "tool_id",
            "tool_version",
        )
    )


def _same_binding(left: object, right: object, field: str) -> None:
    if binding_identity(left) != binding_identity(right):
        _fail("input_identity_mismatch", field)


def _dsv_envelope(value: object) -> Mapping[str, object]:
    packet = _mapping(value, "decision_sufficiency_packet")
    if packet.get("schema") != DECISION_SUFFICIENCY_SCHEMA:
        _fail("decision_sufficiency:envelope_schema_invalid")
    return packet


def parse_decision_sufficiency_verdict(
    payload: str | bytes | Mapping[str, object],
) -> dict[str, object]:
    """Parse an owner-produced DSV verdict without interpreting its policy."""
    if isinstance(payload, Mapping):
        parsed: object = payload
    else:
        try:
            parsed = json.loads(payload)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LifecycleContractError(
                "decision_sufficiency:envelope_json_invalid"
            ) from exc
    return _clone(_dsv_envelope(parsed))


def serialize_decision_sufficiency_verdict(packet: Mapping[str, object]) -> bytes:
    """Serialize an owner-produced DSV verdict using canonical JSON bytes."""
    return canonical_json_bytes(_dsv_envelope(packet))


def import_decision_sufficiency_verdict(
    payload: str | bytes | Mapping[str, object],
    *,
    expected_digest: str | None = None,
) -> dict[str, object]:
    """Import a DSV envelope and optionally prove its exact byte identity."""
    packet = parse_decision_sufficiency_verdict(payload)
    digest = "sha256:" + hashlib.sha256(canonical_json_bytes(packet)).hexdigest()
    if expected_digest is not None and digest != expected_digest:
        _fail("decision_sufficiency:envelope_digest_mismatch")
    return packet


def validate_snapshot(value: object) -> dict[str, object]:
    snapshot = _mapping(value, "snapshot")
    _exact_keys(
        snapshot,
        ("schema", "binding", "source_namespace", "base_identity"),
        field="snapshot",
    )
    _schema(snapshot, SNAPSHOT_SCHEMA)
    validate_record_binding(snapshot["binding"])
    source_namespace = Path(_string(snapshot["source_namespace"], "snapshot.source_namespace"))
    if not source_namespace.is_absolute():
        _fail("lifecycle:path_not_absolute", "snapshot.source_namespace")
    _validate_git_identity(snapshot["base_identity"], "snapshot.base_identity", remote=True)
    return _clone(snapshot)


def validate_evidence_identity(value: object) -> dict[str, object]:
    evidence = _mapping(value, "evidence_identity")
    _exact_keys(
        evidence,
        ("schema", "binding", "producer_path", "producer_symbol", "observed_at", "sequence"),
        field="evidence_identity",
    )
    _schema(evidence, EVIDENCE_IDENTITY_SCHEMA)
    validate_record_binding(evidence["binding"])
    if not Path(_string(evidence["producer_path"], "evidence_identity.producer_path")).is_absolute():
        _fail("lifecycle:path_not_absolute", "evidence_identity.producer_path")
    _string(evidence["producer_symbol"], "evidence_identity.producer_symbol")
    _rfc3339(evidence["observed_at"], "evidence_identity.observed_at")
    _positive_int(evidence["sequence"], "evidence_identity.sequence")
    return _clone(evidence)


def validate_checkpoint_receipt(value: object) -> dict[str, object]:
    receipt = _mapping(value, "checkpoint_receipt")
    _exact_keys(
        receipt,
        ("schema", "binding", "checkpoint_id", "verdict", "failure_code"),
        field="checkpoint_receipt",
    )
    _schema(receipt, CHECKPOINT_RECEIPT_SCHEMA)
    validate_record_binding(receipt["binding"])
    _one_of(receipt["checkpoint_id"], CHECKPOINT_IDS, "checkpoint_receipt.checkpoint_id")
    verdict = _one_of(receipt["verdict"], ("pass", "fail", "skip"), "checkpoint_receipt.verdict")
    failure = receipt["failure_code"]
    if verdict == "fail":
        _string(failure, "checkpoint_receipt.failure_code")
    elif failure is not None:
        _fail("lifecycle:failure_code_forbidden", "checkpoint_receipt")
    return _clone(receipt)


def validate_gate_verdict(value: object) -> dict[str, object]:
    verdict = _mapping(value, "gate_verdict")
    _exact_keys(
        verdict,
        (
            "schema",
            "binding",
            "gate_id",
            "ordered_input_evidence_refs",
            "invariant",
            "output_digest",
            "owner",
            "verdict",
            "retry_reason",
            "next_checkpoint",
        ),
        field="gate_verdict",
    )
    _schema(verdict, GATE_VERDICT_SCHEMA)
    validate_record_binding(verdict["binding"])
    gate_id = _one_of(verdict["gate_id"], GATE_IDS, "gate_verdict.gate_id")
    _string_list(
        verdict["ordered_input_evidence_refs"],
        "gate_verdict.ordered_input_evidence_refs",
        pattern=_EVIDENCE,
        nonempty=True,
    )
    invariant = _string(verdict["invariant"], "gate_verdict.invariant")
    _pattern(verdict["output_digest"], _SHA256, "gate_verdict.output_digest")
    owner = _string(verdict["owner"], "gate_verdict.owner")
    if not owner.startswith("/") or "#" not in owner:
        _fail("lifecycle:owner_invalid", "gate_verdict.owner")
    contract = GATE_CONTRACTS[gate_id]
    if invariant != contract["invariant"]:
        _fail("lifecycle:gate_invariant_mismatch", gate_id)
    owners = cast(tuple[str, ...], contract["owners"])
    if not any(owner.endswith(expected) for expected in owners):
        _fail("lifecycle:gate_owner_mismatch", gate_id)
    state = _one_of(verdict["verdict"], ("pass", "fail", "retry"), "gate_verdict.verdict")
    retry_reason = verdict["retry_reason"]
    if state == "retry":
        _string(retry_reason, "gate_verdict.retry_reason")
    elif retry_reason is not None:
        _fail("lifecycle:retry_reason_forbidden", "gate_verdict")
    if verdict["next_checkpoint"] is not None:
        _one_of(verdict["next_checkpoint"], CHECKPOINT_IDS, "gate_verdict.next_checkpoint")
    return _clone(verdict)


def validate_gate_chain(
    values: Sequence[object],
    *,
    expected_gate_ids: Sequence[str] | None = None,
    require_pass: bool = True,
) -> tuple[dict[str, object], ...]:
    """Validate one canonical gate slice and its ordered evidence linkage."""
    gates = tuple(validate_gate_verdict(value) for value in values)
    gate_ids = tuple(cast(str, gate["gate_id"]) for gate in gates)
    if expected_gate_ids is not None and gate_ids != tuple(expected_gate_ids):
        _fail("lifecycle:gate_order_invalid")
    if not gates:
        _fail("lifecycle:gate_sequence_empty")
    identity = binding_identity(gates[0]["binding"])
    if any(binding_identity(gate["binding"]) != identity for gate in gates[1:]):
        _fail("lifecycle:gate_identity_mismatch")
    if require_pass and any(gate["verdict"] != "pass" for gate in gates):
        _fail("lifecycle:gate_not_passed")

    by_id = {cast(str, gate["gate_id"]): gate for gate in gates}
    evidence = {
        gate_id: cast(Mapping[str, object], gate["binding"])["evidence_ref"]
        for gate_id, gate in by_id.items()
    }

    def require_prefix(gate_id: str, prefix: Sequence[object]) -> None:
        if gate_id not in by_id:
            return
        refs = tuple(
            cast(Sequence[object], by_id[gate_id]["ordered_input_evidence_refs"])
        )
        if refs[: len(prefix)] != tuple(prefix):
            _fail("lifecycle:gate_predecessor_mismatch", gate_id)

    if "G1" in by_id and not cast(
        Sequence[object], by_id["G1"]["ordered_input_evidence_refs"]
    ):
        _fail("lifecycle:gate_predecessor_missing", "G1")
    if "G1" in evidence:
        require_prefix("G2", (evidence["G1"],))
    if "G1" in evidence and "G2" in evidence:
        require_prefix("G3", (evidence["G1"], evidence["G2"]))
    if "G3" in evidence:
        require_prefix("G4", (evidence["G3"],))
    if "G4" in evidence:
        require_prefix("G5", (evidence["G4"],))
    if all(gate_id in evidence for gate_id in GATE_IDS[:5]):
        require_prefix("G6", tuple(evidence[gate_id] for gate_id in GATE_IDS[:5]))
    if len(set(evidence.values())) != len(evidence):
        _fail("lifecycle:gate_evidence_reused")
    return gates


def materialize_gate_verdict(
    *,
    binding: Mapping[str, object],
    gate_id: str,
    ordered_input_evidence_refs: Sequence[str],
    invariant: str,
    output_digest: str,
    owner: str,
    verdict: str,
    retry_reason: str | None = None,
    next_checkpoint: str | None = None,
) -> dict[str, object]:
    checked_binding = validate_record_binding(binding)
    evidence_seed = {
        "identity": {
            field: checked_binding[field]
            for field in (
                "transaction_id",
                "snapshot_id",
                "candidate_sha",
                "tree_sha",
                "input_digest",
                "tool_id",
                "tool_version",
            )
        },
        "gate_id": gate_id,
        "ordered_input_evidence_refs": list(ordered_input_evidence_refs),
        "invariant": invariant,
        "output_digest": output_digest,
        "owner": owner,
        "verdict": verdict,
        "retry_reason": retry_reason,
        "next_checkpoint": next_checkpoint,
    }
    evidence_digest = "sha256:" + hashlib.sha256(
        canonical_json_bytes(evidence_seed)
    ).hexdigest()
    gate_binding = dict(checked_binding)
    gate_binding["evidence_ref"] = "evidence:" + evidence_digest.removeprefix(
        "sha256:"
    )
    gate_binding["evidence_digest"] = evidence_digest
    record: dict[str, object] = {
        "schema": GATE_VERDICT_SCHEMA,
        "binding": gate_binding,
        "gate_id": gate_id,
        "ordered_input_evidence_refs": list(ordered_input_evidence_refs),
        "invariant": invariant,
        "output_digest": output_digest,
        "owner": owner,
        "verdict": verdict,
        "retry_reason": retry_reason,
        "next_checkpoint": next_checkpoint,
    }
    return validate_gate_verdict(record)


def validate_update_transaction(value: object) -> dict[str, object]:
    transaction = _mapping(value, "update_transaction")
    _exact_keys(
        transaction,
        (
            "schema",
            "binding",
            "state",
            "checkpoints",
            "first_missing_checkpoint",
            "gate_verdict_evidence_refs",
            "queue_receipt_id",
            "frontier_id",
            "successor_transaction_id",
            "source_main_rebind_receipt_id",
        ),
        field="update_transaction",
    )
    _schema(transaction, UPDATE_TRANSACTION_SCHEMA)
    binding = validate_record_binding(transaction["binding"])
    state = _one_of(transaction["state"], TRANSACTION_STATES, "update_transaction.state")
    checkpoints = [validate_checkpoint_receipt(item) for item in _sequence(transaction["checkpoints"], "update_transaction.checkpoints")]
    seen: dict[str, dict[str, object]] = {}
    for receipt in checkpoints:
        _same_binding(binding, receipt["binding"], "update_transaction.checkpoints")
        checkpoint_id = cast(str, receipt["checkpoint_id"])
        if checkpoint_id in seen:
            _fail("lifecycle:checkpoint_duplicate", checkpoint_id)
        seen[checkpoint_id] = receipt
    passed = {
        checkpoint_id
        for checkpoint_id, receipt in seen.items()
        if receipt["verdict"] in {"pass", "skip"}
    }
    passed_prefix = 0
    for checkpoint_id in CHECKPOINT_IDS:
        if checkpoint_id not in passed:
            break
        passed_prefix += 1
    if any(
        checkpoint_id in passed
        for checkpoint_id in CHECKPOINT_IDS[passed_prefix + 1 :]
    ):
        _fail("lifecycle:checkpoint_out_of_order")
    computed_missing = next(
        (
            checkpoint
            for checkpoint in CHECKPOINT_IDS
            if checkpoint not in seen or seen[checkpoint]["verdict"] not in {"pass", "skip"}
        ),
        None,
    )
    if transaction["first_missing_checkpoint"] != computed_missing:
        _fail("lifecycle:first_missing_checkpoint_mismatch")
    gate_refs = _string_list(
        transaction["gate_verdict_evidence_refs"],
        "update_transaction.gate_verdict_evidence_refs",
        pattern=_EVIDENCE,
    )
    if len(gate_refs) > len(GATE_IDS):
        _fail("lifecycle:gate_evidence_count_invalid")
    passed_gate_refs = tuple(
        cast(Mapping[str, object], seen[gate_id]["binding"])["evidence_ref"]
        for gate_id in GATE_IDS
        if gate_id in passed
    )
    if gate_refs != passed_gate_refs:
        _fail("lifecycle:gate_evidence_mismatch")
    _nullable_hash_id(transaction["queue_receipt_id"], "queue:", "update_transaction.queue_receipt_id")
    _nullable_hash_id(transaction["frontier_id"], "frontier:", "update_transaction.frontier_id")
    _nullable_hash_id(transaction["successor_transaction_id"], "tx:", "update_transaction.successor_transaction_id")
    _nullable_hash_id(transaction["source_main_rebind_receipt_id"], "rebind:", "update_transaction.source_main_rebind_receipt_id")
    if state == "successor_required" and transaction["successor_transaction_id"] is None:
        _fail("lifecycle:successor_missing")
    if state != "successor_required" and transaction["successor_transaction_id"] is not None:
        _fail("lifecycle:successor_forbidden")
    required_prefix = _STATE_CHECKPOINT_PREFIX.get(state)
    if required_prefix is not None and passed_prefix != required_prefix:
        _fail("lifecycle:state_checkpoint_mismatch", state)
    if state in {
        "reviewed",
        "pr_open",
        "pr_merged",
        "source_main_readback",
        "queue_enqueued",
        "frontier_accepted",
        "remote_readback",
        "durable_handback",
        "descendants_closed",
        "reservations_released",
        "cleanup_proven",
        "nested_lifecycle_cleanup",
        "closed",
    } and transaction["source_main_rebind_receipt_id"] is None:
        _fail("lifecycle:rebind_receipt_required", state)
    if state in {
        "queue_enqueued",
        "frontier_accepted",
        "remote_readback",
        "durable_handback",
        "descendants_closed",
        "reservations_released",
        "cleanup_proven",
        "nested_lifecycle_cleanup",
        "closed",
    } and transaction["queue_receipt_id"] is None:
        _fail("lifecycle:queue_receipt_required", state)
    if state in {
        "frontier_accepted",
        "remote_readback",
        "durable_handback",
        "descendants_closed",
        "reservations_released",
        "cleanup_proven",
        "nested_lifecycle_cleanup",
        "closed",
    } and transaction["frontier_id"] is None:
        _fail("lifecycle:frontier_required", state)
    return _clone(transaction)


def _nullable_hash_id(value: object, prefix: str, field: str) -> None:
    if value is None:
        return
    rendered = _pattern(value, _HASH_ID, field)
    if not rendered.startswith(prefix):
        _fail("lifecycle:identity_invalid", field)


def _validate_git_identity(value: object, field: str, *, remote: bool = False) -> dict[str, object]:
    identity = _mapping(value, field)
    required = ("remote", "ref", "commit_sha", "tree_sha") if remote else ("commit_sha", "tree_sha")
    _exact_keys(identity, required, field=field)
    if remote:
        _string(identity["remote"], f"{field}.remote")
        ref = _string(identity["ref"], f"{field}.ref")
        if not ref.startswith("refs/"):
            _fail("lifecycle:ref_invalid", f"{field}.ref")
    _pattern(identity["commit_sha"], _HEX40, f"{field}.commit_sha")
    _pattern(identity["tree_sha"], _HEX40, f"{field}.tree_sha")
    return _clone(identity)


def _candidate_identity(value: object, field: str) -> dict[str, object]:
    identity = _mapping(value, field)
    _exact_keys(identity, ("candidate_sha", "tree_sha"), field=field)
    _pattern(identity["candidate_sha"], _HEX40, f"{field}.candidate_sha")
    _pattern(identity["tree_sha"], _HEX40, f"{field}.tree_sha")
    return _clone(identity)


def _candidate_matches_binding(candidate: Mapping[str, object], binding: object, field: str) -> None:
    checked = validate_record_binding(binding)
    if (
        candidate["candidate_sha"] != checked["candidate_sha"]
        or candidate["tree_sha"] != checked["tree_sha"]
    ):
        _fail("lifecycle:candidate_identity_mismatch", field)


def validate_source_main_rebind_receipt(value: object) -> dict[str, object]:
    receipt = _mapping(value, "source_main_rebind_receipt")
    _exact_keys(
        receipt,
        (
            "schema",
            "rebind_receipt_id",
            "binding",
            "input_identity",
            "old_base_identity",
            "new_base_identity",
            "origin_main_readback",
        ),
        field="source_main_rebind_receipt",
    )
    _schema(receipt, SOURCE_MAIN_REBIND_SCHEMA)
    rebind_id = _pattern(receipt["rebind_receipt_id"], _HASH_ID, "source_main_rebind_receipt.rebind_receipt_id")
    if not rebind_id.startswith("rebind:"):
        _fail("lifecycle:identity_invalid", "source_main_rebind_receipt.rebind_receipt_id")
    binding = validate_record_binding(receipt["binding"])
    input_identity = _mapping(receipt["input_identity"], "source_main_rebind_receipt.input_identity")
    _exact_keys(input_identity, ("tool", "input_digest"), field="source_main_rebind_receipt.input_identity")
    if input_identity["tool"] != "cmd_latest":
        _fail("lifecycle:tool_id_invalid", "source_main_rebind_receipt.input_identity.tool")
    _pattern(input_identity["input_digest"], _SHA256, "source_main_rebind_receipt.input_identity.input_digest")
    if input_identity["input_digest"] != binding["input_digest"]:
        _fail("input_identity_mismatch", "source_main_rebind_receipt.input_identity")
    old_base = _validate_git_identity(receipt["old_base_identity"], "source_main_rebind_receipt.old_base_identity", remote=True)
    new_base = _validate_git_identity(receipt["new_base_identity"], "source_main_rebind_receipt.new_base_identity", remote=True)
    for field, identity in (("old_base_identity", old_base), ("new_base_identity", new_base)):
        if identity["remote"] != "origin" or identity["ref"] != "refs/heads/main":
            _fail("lifecycle:source_main_identity_invalid", field)
    readback = _mapping(receipt["origin_main_readback"], "source_main_rebind_receipt.origin_main_readback")
    _exact_keys(readback, ("remote", "ref", "commit_sha", "command", "evidence_ref"), field="source_main_rebind_receipt.origin_main_readback")
    _string(readback["remote"], "source_main_rebind_receipt.origin_main_readback.remote")
    _string(readback["ref"], "source_main_rebind_receipt.origin_main_readback.ref")
    _pattern(readback["commit_sha"], _HEX40, "source_main_rebind_receipt.origin_main_readback.commit_sha")
    if readback["command"] != "git ls-remote origin refs/heads/main":
        _fail("lifecycle:readback_command_invalid")
    _pattern(readback["evidence_ref"], _EVIDENCE, "source_main_rebind_receipt.origin_main_readback.evidence_ref")
    if any(readback[key] != new_base[key] for key in ("remote", "ref", "commit_sha")):
        _fail("lifecycle:source_main_readback_mismatch")
    return _clone(receipt)


def materialize_source_main_rebind_receipt(
    *,
    binding: Mapping[str, object],
    old_base_identity: Mapping[str, object],
    new_base_identity: Mapping[str, object],
    origin_main_readback_evidence_ref: str,
) -> dict[str, object]:
    checked_binding = validate_record_binding(binding)
    key = {
        "transaction_id": checked_binding["transaction_id"],
        "snapshot_id": checked_binding["snapshot_id"],
        "input_identity": {
            "tool": "cmd_latest",
            "input_digest": checked_binding["input_digest"],
        },
        "old_base_identity": dict(old_base_identity),
        "new_base_identity": dict(new_base_identity),
    }
    receipt_id = "rebind:" + hashlib.sha256(canonical_json_bytes(key)).hexdigest()
    record: dict[str, object] = {
        "schema": SOURCE_MAIN_REBIND_SCHEMA,
        "rebind_receipt_id": receipt_id,
        "binding": checked_binding,
        "input_identity": key["input_identity"],
        "old_base_identity": dict(old_base_identity),
        "new_base_identity": dict(new_base_identity),
        "origin_main_readback": {
            "remote": new_base_identity["remote"],
            "ref": new_base_identity["ref"],
            "commit_sha": new_base_identity["commit_sha"],
            "command": "git ls-remote origin refs/heads/main",
            "evidence_ref": origin_main_readback_evidence_ref,
        },
    }
    return validate_source_main_rebind_receipt(record)


def _validate_stage_receipt(
    value: object,
    *,
    field: str,
    schema: str,
    receipt_id_field: str,
    receipt_id_prefix: str,
    stage_field: str,
    stage_value: str,
    extra_fields: Sequence[str] = (),
) -> dict[str, object]:
    receipt = _mapping(value, field)
    _exact_keys(
        receipt,
        (
            "schema",
            receipt_id_field,
            "binding",
            "predecessor_evidence_id",
            "rebind_receipt_evidence_id",
            "candidate_identity",
            *extra_fields,
            stage_field,
        ),
        field=field,
    )
    _schema(receipt, schema)
    receipt_id = _pattern(receipt[receipt_id_field], _HASH_ID, f"{field}.{receipt_id_field}")
    if not receipt_id.startswith(receipt_id_prefix):
        _fail("lifecycle:identity_invalid", f"{field}.{receipt_id_field}")
    binding = validate_record_binding(receipt["binding"])
    _pattern(receipt["predecessor_evidence_id"], _EVIDENCE, f"{field}.predecessor_evidence_id")
    rebind_id = _pattern(receipt["rebind_receipt_evidence_id"], _HASH_ID, f"{field}.rebind_receipt_evidence_id")
    if not rebind_id.startswith("rebind:"):
        _fail("lifecycle:identity_invalid", f"{field}.rebind_receipt_evidence_id")
    candidate = _candidate_identity(receipt["candidate_identity"], f"{field}.candidate_identity")
    _candidate_matches_binding(candidate, binding, field)
    if receipt[stage_field] != stage_value:
        _fail("lifecycle:stage_invalid", field)
    return _clone(receipt)


def validate_candidate_freeze_receipt(value: object) -> dict[str, object]:
    receipt = _validate_stage_receipt(
        value,
        field="candidate_freeze_receipt",
        schema=CANDIDATE_FREEZE_SCHEMA,
        receipt_id_field="freeze_receipt_id",
        receipt_id_prefix="freeze:",
        stage_field="freeze_stage",
        stage_value="candidate_freeze",
        extra_fields=("freeze_evidence_ref",),
    )
    _pattern(receipt["freeze_evidence_ref"], _EVIDENCE, "candidate_freeze_receipt.freeze_evidence_ref")
    return receipt


def validate_candidate_review_receipt(value: object) -> dict[str, object]:
    receipt = _validate_stage_receipt(
        value,
        field="candidate_review_receipt",
        schema=CANDIDATE_REVIEW_SCHEMA,
        receipt_id_field="review_receipt_id",
        receipt_id_prefix="review:",
        stage_field="review_stage",
        stage_value="independent_exact_review",
        extra_fields=("reviewer_id", "independent_review_evidence_ref"),
    )
    reviewer_id = _string(receipt["reviewer_id"], "candidate_review_receipt.reviewer_id")
    if not reviewer_id.startswith("reviewer:"):
        _fail("lifecycle:identity_invalid", "candidate_review_receipt.reviewer_id")
    _pattern(receipt["independent_review_evidence_ref"], _EVIDENCE, "candidate_review_receipt.independent_review_evidence_ref")
    return receipt


def validate_candidate_cas_receipt(value: object) -> dict[str, object]:
    receipt = _validate_stage_receipt(
        value,
        field="candidate_cas_receipt",
        schema=CANDIDATE_CAS_SCHEMA,
        receipt_id_field="cas_receipt_id",
        receipt_id_prefix="cas:",
        stage_field="cas_stage",
        stage_value="cas",
        extra_fields=("cas_base_identity", "cas_evidence_ref"),
    )
    _validate_git_identity(receipt["cas_base_identity"], "candidate_cas_receipt.cas_base_identity")
    _pattern(receipt["cas_evidence_ref"], _EVIDENCE, "candidate_cas_receipt.cas_evidence_ref")
    return receipt


def materialize_candidate_cas_receipt(
    *,
    candidate_review_receipt: Mapping[str, object],
    source_main_rebind_receipt: Mapping[str, object],
    cas_evidence_ref: str,
) -> dict[str, object]:
    """Append CAS using only the reviewed rebind's exact origin/main base."""
    review = validate_candidate_review_receipt(candidate_review_receipt)
    rebind = validate_source_main_rebind_receipt(source_main_rebind_receipt)
    _same_binding(review["binding"], rebind["binding"], "candidate_cas.rebind")
    if review["rebind_receipt_evidence_id"] != rebind["rebind_receipt_id"]:
        _fail("lifecycle:rebind_mismatch", "candidate_cas")
    rebind_base = cast(Mapping[str, object], rebind["new_base_identity"])
    cas_base_identity = {
        "commit_sha": rebind_base["commit_sha"],
        "tree_sha": rebind_base["tree_sha"],
    }
    _pattern(cas_evidence_ref, _EVIDENCE, "candidate_cas_receipt.cas_evidence_ref")
    review_binding = cast(Mapping[str, object], review["binding"])
    binding = dict(review_binding)
    evidence_hex = cas_evidence_ref.removeprefix("evidence:")
    binding["evidence_ref"] = cas_evidence_ref
    binding["evidence_digest"] = "sha256:" + evidence_hex
    key = {
        "binding_identity": binding_identity(binding),
        "predecessor_evidence_id": review_binding["evidence_ref"],
        "rebind_receipt_evidence_id": review["rebind_receipt_evidence_id"],
        "candidate_identity": review["candidate_identity"],
        "cas_base_identity": dict(cas_base_identity),
        "cas_evidence_ref": cas_evidence_ref,
    }
    receipt = {
        "schema": CANDIDATE_CAS_SCHEMA,
        "cas_receipt_id": "cas:"
        + hashlib.sha256(canonical_json_bytes(key)).hexdigest(),
        "binding": binding,
        "predecessor_evidence_id": review_binding["evidence_ref"],
        "rebind_receipt_evidence_id": review["rebind_receipt_evidence_id"],
        "candidate_identity": review["candidate_identity"],
        "cas_base_identity": dict(cas_base_identity),
        "cas_evidence_ref": cas_evidence_ref,
        "cas_stage": "cas",
    }
    checked = validate_candidate_cas_transition(review, receipt)
    return validate_candidate_cas_rebind_transition(rebind, checked)


def validate_candidate_freeze_transition(rebind: object, freeze: object) -> dict[str, object]:
    checked_rebind = validate_source_main_rebind_receipt(rebind)
    checked_freeze = validate_candidate_freeze_receipt(freeze)
    _same_binding(checked_rebind["binding"], checked_freeze["binding"], "candidate_freeze")
    if checked_freeze["predecessor_evidence_id"] != cast(Mapping[str, object], checked_rebind["binding"])["evidence_ref"]:
        _fail("lifecycle:predecessor_mismatch", "candidate_freeze")
    if checked_freeze["rebind_receipt_evidence_id"] != checked_rebind["rebind_receipt_id"]:
        _fail("lifecycle:rebind_mismatch", "candidate_freeze")
    return checked_freeze


def _validate_candidate_stage_transition(
    previous: Mapping[str, object],
    current: Mapping[str, object],
    *,
    field: str,
    rebind_receipt_id: str | None = None,
) -> dict[str, object]:
    _same_binding(previous["binding"], current["binding"], field)
    if previous["candidate_identity"] != current["candidate_identity"]:
        _fail("lifecycle:candidate_identity_mismatch", field)
    previous_binding = cast(Mapping[str, object], previous["binding"])
    if current["predecessor_evidence_id"] != previous_binding["evidence_ref"]:
        _fail("lifecycle:predecessor_mismatch", field)
    expected_rebind = rebind_receipt_id or cast(str, previous["rebind_receipt_evidence_id"])
    if current["rebind_receipt_evidence_id"] != expected_rebind:
        _fail("lifecycle:rebind_mismatch", field)
    return dict(current)


def validate_candidate_review_transition(freeze: object, review: object) -> dict[str, object]:
    return _validate_candidate_stage_transition(
        validate_candidate_freeze_receipt(freeze),
        validate_candidate_review_receipt(review),
        field="candidate_review",
    )


def validate_candidate_cas_transition(review: object, cas: object) -> dict[str, object]:
    return _validate_candidate_stage_transition(
        validate_candidate_review_receipt(review),
        validate_candidate_cas_receipt(cas),
        field="candidate_cas",
    )


def validate_candidate_cas_rebind_transition(
    rebind: object,
    cas: object,
) -> dict[str, object]:
    """Require CAS to use the exact new origin/main identity from rebind."""
    checked_rebind = validate_source_main_rebind_receipt(rebind)
    checked_cas = validate_candidate_cas_receipt(cas)
    _same_binding(checked_rebind["binding"], checked_cas["binding"], "candidate_cas.rebind")
    if checked_cas["rebind_receipt_evidence_id"] != checked_rebind["rebind_receipt_id"]:
        _fail("lifecycle:rebind_mismatch", "candidate_cas")
    rebind_base = cast(Mapping[str, object], checked_rebind["new_base_identity"])
    cas_base = cast(Mapping[str, object], checked_cas["cas_base_identity"])
    if (
        rebind_base["remote"] != "origin"
        or rebind_base["ref"] != "refs/heads/main"
        or cas_base["commit_sha"] != rebind_base["commit_sha"]
        or cas_base["tree_sha"] != rebind_base["tree_sha"]
    ):
        _fail("lifecycle:rebind_cas_base_identity_mismatch")
    return checked_cas


def validate_candidate_cas_pr_transition(
    cas: object,
    pr_lifecycle: object,
) -> dict[str, object]:
    """Bind one CAS base and exact candidate to one immutable PR topology."""
    checked_cas = validate_candidate_cas_receipt(cas)
    checked_pr = validate_pull_request_lifecycle(pr_lifecycle)
    _same_binding(checked_cas["binding"], checked_pr["binding"], "candidate_cas.pr")
    candidate = cast(Mapping[str, object], checked_cas["candidate_identity"])
    head = cast(Mapping[str, object], checked_pr["head_identity"])
    if (
        candidate["candidate_sha"] != head["commit_sha"]
        or candidate["tree_sha"] != head["tree_sha"]
    ):
        _fail("lifecycle:candidate_identity_mismatch", "candidate_cas.pr")
    cas_base = cast(Mapping[str, object], checked_cas["cas_base_identity"])
    pr_base = cast(Mapping[str, object], checked_pr["base_identity"])
    if (
        cas_base["commit_sha"] != pr_base["commit_sha"]
        or cas_base["tree_sha"] != pr_base["tree_sha"]
    ):
        _fail("lifecycle:cas_base_identity_mismatch")
    return checked_pr


def _validate_repo_identity(value: object, field: str, *, remote: bool = False) -> dict[str, object]:
    identity = _mapping(value, field)
    required = ["repo_owner", "repo_name", "ref", "commit_sha", "tree_sha"]
    if remote:
        required[2:2] = ["remote_name", "url_digest"]
    _exact_keys(identity, required, field=field)
    for key in ("repo_owner", "repo_name", "ref"):
        _string(identity[key], f"{field}.{key}")
    if remote:
        _string(identity["remote_name"], f"{field}.remote_name")
        _pattern(identity["url_digest"], _SHA256, f"{field}.url_digest")
    _pattern(identity["commit_sha"], _HEX40, f"{field}.commit_sha")
    _pattern(identity["tree_sha"], _HEX40, f"{field}.tree_sha")
    return _clone(identity)


def _validate_actor(value: object, field: str) -> dict[str, object]:
    actor = _mapping(value, field)
    _exact_keys(actor, ("actor_id", "display_name"), field=field)
    _string(actor["actor_id"], f"{field}.actor_id")
    _string(actor["display_name"], f"{field}.display_name")
    return _clone(actor)


def _validate_branch_table(value: object) -> None:
    table = _mapping(value, "pull_request_lifecycle.branch")
    _exact_keys(table, PR_KINDS, field="pull_request_lifecycle.branch")
    for kind, expected in PULL_REQUEST_BRANCH_RULES.items():
        rule = _mapping(table[kind], f"pull_request_lifecycle.branch.{kind}")
        _exact_keys(rule, ("required", "forbidden"), field=f"pull_request_lifecycle.branch.{kind}")
        required = _string_list(rule["required"], f"pull_request_lifecycle.branch.{kind}.required")
        forbidden = _string_list(rule["forbidden"], f"pull_request_lifecycle.branch.{kind}.forbidden")
        if required != expected["required"] or forbidden != expected["forbidden"]:
            _fail("pr_lifecycle:branch_rule_mismatch", kind)


def pull_request_branch_table() -> dict[str, object]:
    """Return the canonical executable branch discriminator table."""
    return {
        kind: {
            "required": list(rule["required"]),
            "forbidden": list(rule["forbidden"]),
        }
        for kind, rule in PULL_REQUEST_BRANCH_RULES.items()
    }


def validate_pull_request_lifecycle(value: object) -> dict[str, object]:
    lifecycle = _mapping(value, "pull_request_lifecycle")
    common = (
        "schema",
        "kind",
        "binding",
        "state",
        "remote_identity",
        "base_identity",
        "head_identity",
        "branch",
        "permission_identity",
        "pr_essence",
        "reviews",
    )
    identity_fields = ("user_identity", "fork_identity", "contributor_identity", "contributor_diff")
    _exact_keys(
        lifecycle,
        common,
        optional=(*identity_fields, "successor_ref"),
        field="pull_request_lifecycle",
    )
    _schema(lifecycle, PULL_REQUEST_LIFECYCLE_SCHEMA)
    kind = _one_of(lifecycle["kind"], PR_KINDS, "pull_request_lifecycle.kind")
    state = _one_of(lifecycle["state"], PR_STATES, "pull_request_lifecycle.state")
    binding = validate_record_binding(lifecycle["binding"])
    remote = _validate_repo_identity(lifecycle["remote_identity"], "pull_request_lifecycle.remote_identity", remote=True)
    base = _validate_repo_identity(lifecycle["base_identity"], "pull_request_lifecycle.base_identity")
    head = _validate_repo_identity(lifecycle["head_identity"], "pull_request_lifecycle.head_identity")
    if head["commit_sha"] != binding["candidate_sha"] or head["tree_sha"] != binding["tree_sha"]:
        _fail("pr_lifecycle:head_binding_mismatch")
    if any(
        remote[field] != head[field]
        for field in ("repo_owner", "repo_name", "ref", "commit_sha", "tree_sha")
    ):
        _fail("pr_lifecycle:remote_head_identity_mismatch")
    _validate_branch_table(lifecycle["branch"])
    rules = PULL_REQUEST_BRANCH_RULES[kind]
    for field in rules["required"]:
        if field not in lifecycle:
            _fail("pr_lifecycle:branch_field_missing", field)
    for field in rules["forbidden"]:
        if field in lifecycle:
            _fail("pr_lifecycle:branch_field_forbidden", field)
    user_identity: dict[str, object] | None = None
    if kind == "user":
        user_identity = _validate_actor(
            lifecycle["user_identity"], "pull_request_lifecycle.user_identity"
        )
        if any(base[field] != head[field] for field in ("repo_owner", "repo_name")):
            _fail("pr_lifecycle:user_repository_mismatch")
    elif kind == "fork":
        fork = _mapping(lifecycle["fork_identity"], "pull_request_lifecycle.fork_identity")
        _exact_keys(fork, ("repo_owner", "repo_name", "parent_repo_owner", "parent_repo_name", "ref"), field="pull_request_lifecycle.fork_identity")
        for field in fork:
            _string(fork[field], f"pull_request_lifecycle.fork_identity.{field}")
        if (
            fork["repo_owner"] != head["repo_owner"]
            or fork["repo_name"] != head["repo_name"]
            or fork["parent_repo_owner"] != base["repo_owner"]
            or fork["parent_repo_name"] != base["repo_name"]
            or fork["ref"] != head["ref"]
        ):
            _fail("pr_lifecycle:fork_identity_mismatch")
    else:
        _validate_actor(lifecycle["contributor_identity"], "pull_request_lifecycle.contributor_identity")
        diff = _mapping(lifecycle["contributor_diff"], "pull_request_lifecycle.contributor_diff")
        _exact_keys(diff, ("commit_sha", "tree_sha", "diff_sha256"), field="pull_request_lifecycle.contributor_diff")
        _pattern(diff["commit_sha"], _HEX40, "pull_request_lifecycle.contributor_diff.commit_sha")
        _pattern(diff["tree_sha"], _HEX40, "pull_request_lifecycle.contributor_diff.tree_sha")
        _pattern(diff["diff_sha256"], _SHA256, "pull_request_lifecycle.contributor_diff.diff_sha256")
        if (
            diff["commit_sha"] != head["commit_sha"]
            or diff["tree_sha"] != head["tree_sha"]
        ):
            _fail("pr_lifecycle:contributor_diff_identity_mismatch")
    permission = _mapping(lifecycle["permission_identity"], "pull_request_lifecycle.permission_identity")
    _exact_keys(permission, ("actor_id", "permission_state", "permission_evidence_id", "authority_source", "assumption_forbidden"), field="pull_request_lifecycle.permission_identity")
    _string(permission["actor_id"], "pull_request_lifecycle.permission_identity.actor_id")
    permission_state = _one_of(permission["permission_state"], ("unknown", "verified_true", "verified_false"), "pull_request_lifecycle.permission_identity.permission_state")
    _pattern(permission["permission_evidence_id"], _EVIDENCE, "pull_request_lifecycle.permission_identity.permission_evidence_id")
    _string(permission["authority_source"], "pull_request_lifecycle.permission_identity.authority_source")
    if permission["assumption_forbidden"] is not True:
        _fail("pr_lifecycle:permission_assumption_forbidden")
    if (
        kind == "user"
        and user_identity is not None
        and user_identity["actor_id"] != permission["actor_id"]
    ):
        _fail("pr_lifecycle:actor_identity_mismatch")
    if state == "permission_unknown" and permission_state != "unknown":
        _fail("pr_lifecycle:permission_state_mismatch")
    if state == "permission_denied" and permission_state != "verified_false":
        _fail("pr_lifecycle:permission_state_mismatch")
    if state in PR_REVIEWABLE_STATES | {"merged"} and permission_state != "verified_true":
        _fail("pr_lifecycle:verified_permission_required", state)
    essence = _mapping(lifecycle["pr_essence"], "pull_request_lifecycle.pr_essence")
    _exact_keys(essence, ("problem", "intent", "canonical_owner", "contract_delta", "evidence_refs"), field="pull_request_lifecycle.pr_essence")
    for field in ("problem", "intent", "canonical_owner", "contract_delta"):
        _string(essence[field], f"pull_request_lifecycle.pr_essence.{field}")
    _string_list(essence["evidence_refs"], "pull_request_lifecycle.pr_essence.evidence_refs", pattern=_EVIDENCE, nonempty=True)
    for index, review_value in enumerate(_sequence(lifecycle["reviews"], "pull_request_lifecycle.reviews")):
        review = _mapping(review_value, f"pull_request_lifecycle.reviews[{index}]")
        _exact_keys(review, ("review_id", "reviewer_id", "state", "body_digest"), field=f"pull_request_lifecycle.reviews[{index}]")
        _string(review["review_id"], f"pull_request_lifecycle.reviews[{index}].review_id")
        _string(review["reviewer_id"], f"pull_request_lifecycle.reviews[{index}].reviewer_id")
        _one_of(review["state"], ("approved", "changes_requested", "commented", "dismissed"), f"pull_request_lifecycle.reviews[{index}].state")
        _pattern(review["body_digest"], _SHA256, f"pull_request_lifecycle.reviews[{index}].body_digest")
    successor = lifecycle.get("successor_ref")
    if state == "conflict_successor":
        rendered = _pattern(successor, _HASH_ID, "pull_request_lifecycle.successor_ref")
        if not rendered.startswith("pr-successor:"):
            _fail("lifecycle:identity_invalid", "pull_request_lifecycle.successor_ref")
    elif successor is not None:
        _fail("pr_lifecycle:successor_forbidden")
    return _clone(lifecycle)


_PR_TRANSITIONS = {
    ("draft", "ready"),
    ("draft", "permission_unknown"),
    ("permission_unknown", "permission_denied"),
    ("permission_unknown", "ready"),
    ("permission_denied", "ready"),
    ("ready", "changes_requested"),
    ("ready", "external_review"),
    ("changes_requested", "ready"),
    ("external_review", "ready"),
    ("multiple_remotes", "ready"),
    ("ready", "merged"),
}


def validate_pull_request_transition(previous: object, current: object) -> dict[str, object]:
    old = validate_pull_request_lifecycle(previous)
    new = validate_pull_request_lifecycle(current)
    old_state = cast(str, old["state"])
    new_state = cast(str, new["state"])
    _same_binding(old["binding"], new["binding"], "pull_request_lifecycle")
    allowed = (old_state, new_state) in _PR_TRANSITIONS or (
        old_state == new_state and old_state in PR_OPEN_STATES
    )
    if old_state in PR_OPEN_STATES and new_state in {"closed_head", "multiple_remotes"}:
        allowed = True
    if old_state in PR_REVIEWABLE_STATES and new_state == "conflict_successor":
        allowed = True
    if not allowed:
        _fail("pr_lifecycle:transition_invalid", f"{old_state}->{new_state}")
    immutable_fields = (
        "kind",
        "remote_identity",
        "base_identity",
        "head_identity",
        "branch",
        "permission_identity",
    )
    for field in immutable_fields:
        if old[field] != new[field]:
            permission_refresh = field == "permission_identity" and (
                (
                    old_state
                    in {"permission_unknown", "permission_denied", "multiple_remotes"}
                    and new_state == "ready"
                )
                or (old_state == "permission_unknown" and new_state == "permission_denied")
            )
            if not permission_refresh:
                _fail("pr_lifecycle:immutable_identity_changed", field)
    for field in ("pr_essence", "reviews"):
        if field == "reviews":
            old_reviews = cast(list[object], old[field])
            new_reviews = cast(list[object], new[field])
            if new_reviews[: len(old_reviews)] != old_reviews:
                _fail("pr_lifecycle:retained_field_changed", field)
        elif old[field] != new[field]:
            _fail("pr_lifecycle:retained_field_changed", field)
    if old["kind"] == "contributor" and old["contributor_diff"] != new["contributor_diff"]:
        _fail("pr_lifecycle:retained_field_changed", "contributor_diff")
    return new


def validate_publication_readback_receipt(value: object) -> dict[str, object]:
    receipt = _validate_stage_receipt(
        value,
        field="publication_readback_receipt",
        schema=PUBLICATION_READBACK_SCHEMA,
        receipt_id_field="readback_receipt_id",
        receipt_id_prefix="publication-readback:",
        stage_field="readback_stage",
        stage_value="publication_readback",
        extra_fields=(
            "pr_identity",
            "publication_evidence_ref",
            "authoritative_readback_digest",
        ),
    )
    pr = _mapping(receipt["pr_identity"], "publication_readback_receipt.pr_identity")
    _exact_keys(
        pr,
        (
            "number",
            "remote_name",
            "base_ref",
            "head_ref",
            "head_repo_owner",
            "head_repo_name",
            "post_merge_base_ref_sha",
            "merge_cas_base_sha",
            "merge_cas_base_tree_sha",
            "head_sha",
            "merge_commit_sha",
            "merge_tree_sha",
        ),
        field="publication_readback_receipt.pr_identity",
    )
    _positive_int(pr["number"], "publication_readback_receipt.pr_identity.number")
    if pr["remote_name"] != "origin" or pr["base_ref"] != "refs/heads/main":
        _fail("lifecycle:publication_remote_identity_mismatch")
    for field in ("head_ref", "head_repo_owner", "head_repo_name"):
        _string(pr[field], f"publication_readback_receipt.pr_identity.{field}")
    for field in (
        "post_merge_base_ref_sha",
        "merge_cas_base_sha",
        "merge_cas_base_tree_sha",
        "head_sha",
        "merge_commit_sha",
        "merge_tree_sha",
    ):
        _pattern(pr[field], _HEX40, f"publication_readback_receipt.pr_identity.{field}")
    candidate = cast(Mapping[str, object], receipt["candidate_identity"])
    if pr["head_sha"] != candidate["candidate_sha"]:
        _fail("lifecycle:publication_candidate_mismatch")
    _pattern(receipt["publication_evidence_ref"], _EVIDENCE, "publication_readback_receipt.publication_evidence_ref")
    _pattern(
        receipt["authoritative_readback_digest"],
        _SHA256,
        "publication_readback_receipt.authoritative_readback_digest",
    )
    return receipt


def validate_publication_readback_transition(
    cas: object,
    pr_lifecycle: object,
    readback: object,
) -> dict[str, object]:
    checked_cas = validate_candidate_cas_receipt(cas)
    checked_pr = validate_pull_request_lifecycle(pr_lifecycle)
    checked_readback = validate_publication_readback_receipt(readback)
    if checked_pr["state"] != "merged":
        _fail("lifecycle:pr_not_merged")
    _same_binding(checked_cas["binding"], checked_pr["binding"], "publication_readback.pr")
    _same_binding(checked_pr["binding"], checked_readback["binding"], "publication_readback")
    if checked_cas["candidate_identity"] != checked_readback["candidate_identity"]:
        _fail("lifecycle:candidate_identity_mismatch", "publication_readback")
    cas_base = cast(Mapping[str, object], checked_cas["cas_base_identity"])
    pr_base = cast(Mapping[str, object], checked_pr["base_identity"])
    pr_head = cast(Mapping[str, object], checked_pr["head_identity"])
    readback_pr = cast(Mapping[str, object], checked_readback["pr_identity"])
    if (
        cas_base["commit_sha"] != pr_base["commit_sha"]
        or cas_base["tree_sha"] != pr_base["tree_sha"]
        or readback_pr["merge_cas_base_sha"] != cas_base["commit_sha"]
        or readback_pr["merge_cas_base_tree_sha"] != cas_base["tree_sha"]
    ):
        _fail("lifecycle:cas_base_identity_mismatch")
    if readback_pr["head_sha"] != pr_head["commit_sha"]:
        _fail("lifecycle:publication_head_identity_mismatch")
    remote = cast(Mapping[str, object], checked_pr["remote_identity"])
    if (
        readback_pr["remote_name"] != remote["remote_name"]
        or readback_pr["base_ref"] != pr_base["ref"]
        or readback_pr["head_ref"] != pr_head["ref"]
        or readback_pr["head_repo_owner"] != pr_head["repo_owner"]
        or readback_pr["head_repo_name"] != pr_head["repo_name"]
    ):
        _fail("lifecycle:publication_remote_identity_mismatch")
    pr_binding = cast(Mapping[str, object], checked_pr["binding"])
    if checked_readback["predecessor_evidence_id"] != pr_binding["evidence_ref"]:
        _fail("lifecycle:predecessor_mismatch", "publication_readback")
    if checked_readback["rebind_receipt_evidence_id"] != checked_cas["rebind_receipt_evidence_id"]:
        _fail("lifecycle:rebind_mismatch", "publication_readback")
    return checked_readback


def materialize_publication_readback_receipt(
    *,
    candidate_cas_receipt: Mapping[str, object],
    pull_request_lifecycle: Mapping[str, object],
    authoritative_pr_readback: Mapping[str, object],
) -> dict[str, object]:
    """Append PR/base/head/merge identity from one authoritative readback."""
    cas = validate_candidate_cas_receipt(candidate_cas_receipt)
    lifecycle = validate_candidate_cas_pr_transition(
        cas, pull_request_lifecycle
    )
    if lifecycle["state"] != "merged":
        _fail("lifecycle:pr_not_merged")
    readback = _mapping(authoritative_pr_readback, "authoritative_pr_readback")
    pr_number = _positive_int(
        readback.get("number"), "authoritative_pr_readback.number"
    )
    if str(readback.get("state", "")).upper() != "MERGED":
        _fail("lifecycle:pr_not_merged")
    lifecycle_binding = cast(Mapping[str, object], lifecycle["binding"])
    candidate = cast(Mapping[str, object], cas["candidate_identity"])
    base = cast(Mapping[str, object], lifecycle["base_identity"])
    head = cast(Mapping[str, object], lifecycle["head_identity"])
    remote = cast(Mapping[str, object], lifecycle["remote_identity"])
    head_repository = _mapping(
        readback.get("headRepository"), "authoritative_pr_readback.headRepository"
    )
    head_repo = _string(
        head_repository.get("nameWithOwner"),
        "authoritative_pr_readback.headRepository.nameWithOwner",
    )
    expected_head_repo = f"{head['repo_owner']}/{head['repo_name']}"
    merge_commit = _mapping(
        readback.get("mergeCommit"), "authoritative_pr_readback.mergeCommit"
    )
    merge_commit_sha = _pattern(
        merge_commit.get("oid"), _HEX40, "authoritative_pr_readback.mergeCommit.oid"
    )
    merge_tree_sha = _pattern(
        readback.get("mergeTreeOid"),
        _HEX40,
        "authoritative_pr_readback.mergeTreeOid",
    )
    post_merge_base_ref_sha = _pattern(
        readback.get("baseRefOid"),
        _HEX40,
        "authoritative_pr_readback.baseRefOid",
    )
    merge_cas_base_sha = _pattern(
        readback.get("mergeCasBaseOid"),
        _HEX40,
        "authoritative_pr_readback.mergeCasBaseOid",
    )
    merge_cas_base_tree_sha = _pattern(
        readback.get("mergeCasBaseTreeOid"),
        _HEX40,
        "authoritative_pr_readback.mergeCasBaseTreeOid",
    )
    head_sha = _pattern(
        readback.get("headRefOid"),
        _HEX40,
        "authoritative_pr_readback.headRefOid",
    )
    if (
        readback.get("baseRefName") != str(base["ref"]).removeprefix("refs/heads/")
        or readback.get("headRefName") != str(head["ref"]).removeprefix("refs/heads/")
        or head_sha != head["commit_sha"]
        or head_repo != expected_head_repo
        or merge_cas_base_sha != base["commit_sha"]
        or merge_cas_base_tree_sha != base["tree_sha"]
    ):
        _fail("lifecycle:authoritative_pr_readback_mismatch")
    pr_identity = {
        "number": pr_number,
        "remote_name": remote["remote_name"],
        "base_ref": base["ref"],
        "head_ref": head["ref"],
        "head_repo_owner": head["repo_owner"],
        "head_repo_name": head["repo_name"],
        "post_merge_base_ref_sha": post_merge_base_ref_sha,
        "merge_cas_base_sha": merge_cas_base_sha,
        "merge_cas_base_tree_sha": merge_cas_base_tree_sha,
        "head_sha": head_sha,
        "merge_commit_sha": merge_commit_sha,
        "merge_tree_sha": merge_tree_sha,
    }
    authoritative_readback_digest = "sha256:" + hashlib.sha256(
        canonical_json_bytes(pr_identity)
    ).hexdigest()
    publication_evidence_ref = "evidence:" + authoritative_readback_digest.removeprefix(
        "sha256:"
    )
    binding = dict(lifecycle_binding)
    binding["evidence_ref"] = publication_evidence_ref
    binding["evidence_digest"] = authoritative_readback_digest
    key = {
        "binding_identity": binding_identity(binding),
        "predecessor_evidence_id": lifecycle_binding["evidence_ref"],
        "rebind_receipt_evidence_id": cas["rebind_receipt_evidence_id"],
        "candidate_identity": candidate,
        "pr_identity": pr_identity,
        "publication_evidence_ref": publication_evidence_ref,
        "authoritative_readback_digest": authoritative_readback_digest,
    }
    receipt = {
        "schema": PUBLICATION_READBACK_SCHEMA,
        "readback_receipt_id": "publication-readback:"
        + hashlib.sha256(canonical_json_bytes(key)).hexdigest(),
        "binding": binding,
        "predecessor_evidence_id": lifecycle_binding["evidence_ref"],
        "rebind_receipt_evidence_id": cas["rebind_receipt_evidence_id"],
        "candidate_identity": candidate,
        "pr_identity": pr_identity,
        "publication_evidence_ref": publication_evidence_ref,
        "authoritative_readback_digest": authoritative_readback_digest,
        "readback_stage": "publication_readback",
    }
    return validate_publication_readback_transition(cas, lifecycle, receipt)


def validate_source_projection_packet(value: object) -> dict[str, object]:
    """Validate the sole post-publication input consumed by update `latest`."""
    packet = _mapping(value, "source_projection_packet")
    _exact_keys(
        packet,
        (
            "schema",
            "binding",
            "source_main_rebind_receipt",
            "candidate_cas_receipt",
            "pull_request_lifecycle",
            "publication_readback_receipt",
            "source_gate_verdicts",
            "ordered_predecessor_evidence",
            "acceptance_evidence_ref",
        ),
        field="source_projection_packet",
    )
    _schema(packet, SOURCE_PROJECTION_PACKET_SCHEMA)
    binding = validate_record_binding(packet["binding"])
    rebind = validate_source_main_rebind_receipt(
        packet["source_main_rebind_receipt"]
    )
    cas = validate_candidate_cas_receipt(packet["candidate_cas_receipt"])
    lifecycle = validate_candidate_cas_pr_transition(
        cas, packet["pull_request_lifecycle"]
    )
    readback = validate_publication_readback_transition(
        cas, lifecycle, packet["publication_readback_receipt"]
    )
    source_gates = validate_gate_chain(
        _sequence(
            packet["source_gate_verdicts"],
            "source_projection_packet.source_gate_verdicts",
        ),
        expected_gate_ids=("G1", "G2", "G3"),
        require_pass=True,
    )
    for field, record_binding in (
        ("rebind", rebind["binding"]),
        ("cas", cas["binding"]),
        ("pr", lifecycle["binding"]),
        ("readback", readback["binding"]),
    ):
        _same_binding(binding, record_binding, f"source_projection_packet.{field}")
    validate_candidate_cas_rebind_transition(rebind, cas)
    if any(
        binding_identity(gate["binding"]) != binding_identity(binding)
        for gate in source_gates
    ):
        _fail("lifecycle:gate_identity_mismatch")
    g3_inputs = cast(Sequence[object], source_gates[2]["ordered_input_evidence_refs"])
    cas_binding = cast(Mapping[str, object], cas["binding"])
    if cas_binding["evidence_ref"] not in g3_inputs:
        _fail("lifecycle:gate_predecessor_mismatch", "G3")
    if readback["rebind_receipt_evidence_id"] != rebind["rebind_receipt_id"]:
        _fail("lifecycle:rebind_mismatch", "source_projection_packet")
    predecessors = _sequence(
        packet["ordered_predecessor_evidence"],
        "source_projection_packet.ordered_predecessor_evidence",
    )
    if len(predecessors) != 2:
        _fail("frontier:predecessor_order_invalid")
    expected = ((388, "#388"), (389, "#389"))
    for index, (value_item, expected_item) in enumerate(
        zip(predecessors, expected, strict=True)
    ):
        item = _mapping(
            value_item,
            f"source_projection_packet.ordered_predecessor_evidence[{index}]",
        )
        _exact_keys(
            item,
            ("queue_number", "source_pr", "publication_evidence_id"),
            optional=("source_pr_sha",) if expected_item[0] == 389 else (),
            field=f"source_projection_packet.ordered_predecessor_evidence[{index}]",
        )
        if (item["queue_number"], item["source_pr"]) != expected_item:
            _fail("frontier:predecessor_order_invalid")
        _pattern(
            item["publication_evidence_id"],
            _EVIDENCE,
            f"source_projection_packet.ordered_predecessor_evidence[{index}].publication_evidence_id",
        )
        if expected_item[0] == 389:
            _pattern(
                item.get("source_pr_sha"),
                _HEX40,
                "source_projection_packet.ordered_predecessor_evidence[1].source_pr_sha",
            )
    _pattern(
        packet["acceptance_evidence_ref"],
        _EVIDENCE,
        "source_projection_packet.acceptance_evidence_ref",
    )
    return _clone(packet)


def materialize_source_projection_packet(
    *,
    binding: Mapping[str, object],
    source_main_rebind_receipt: Mapping[str, object],
    candidate_cas_receipt: Mapping[str, object],
    pull_request_lifecycle: Mapping[str, object],
    publication_readback_receipt: Mapping[str, object],
    source_gate_verdicts: Sequence[Mapping[str, object]],
    ordered_predecessor_evidence: Sequence[Mapping[str, object]],
    acceptance_evidence_ref: str,
) -> dict[str, object]:
    """Materialize the sole state packet consumed by update `latest`."""
    return validate_source_projection_packet(
        {
            "schema": SOURCE_PROJECTION_PACKET_SCHEMA,
            "binding": dict(binding),
            "source_main_rebind_receipt": dict(source_main_rebind_receipt),
            "candidate_cas_receipt": dict(candidate_cas_receipt),
            "pull_request_lifecycle": dict(pull_request_lifecycle),
            "publication_readback_receipt": dict(publication_readback_receipt),
            "source_gate_verdicts": [dict(item) for item in source_gate_verdicts],
            "ordered_predecessor_evidence": [
                dict(item) for item in ordered_predecessor_evidence
            ],
            "acceptance_evidence_ref": acceptance_evidence_ref,
        }
    )


def materialize_fresh_clone_source_projection_packet(
    *,
    candidate_sha: str,
    candidate_tree_sha: str,
    publication_sha: str,
    publication_tree_sha: str,
    gate_owner_apis: SourceProjectionGateOwnerApis,
) -> dict[str, object]:
    """Materialize the canonical accepted-source fixture for fresh-clone CI.

    Fresh-clone acceptance has no source PR transaction to consume, but its
    parent projection must still consume the same source-publication packet as
    a normal update.  This owner-owned materializer derives every identity and
    evidence value from the two observed Git identities.  The aggregate owns
    lifecycle semantics while consuming G2/G3 only through their authoritative
    owner APIs, then validates the complete packet before it is handed to the
    update CLI.
    """

    def digest(label: str, value: object) -> str:
        return hashlib.sha256(
            canonical_json_bytes({"label": label, "value": value})
        ).hexdigest()

    def evidence(label: str, value: object) -> str:
        return "evidence:" + digest(label, value)

    _pattern(candidate_sha, _HEX40, "fresh_clone.candidate_sha")
    _pattern(candidate_tree_sha, _HEX40, "fresh_clone.candidate_tree_sha")
    _pattern(publication_sha, _HEX40, "fresh_clone.publication_sha")
    _pattern(publication_tree_sha, _HEX40, "fresh_clone.publication_tree_sha")

    identity = {
        "candidate_sha": candidate_sha,
        "candidate_tree_sha": candidate_tree_sha,
        "publication_sha": publication_sha,
        "publication_tree_sha": publication_tree_sha,
    }
    input_digest = "sha256:" + digest("fresh-clone-input", identity)
    transaction_id = "tx:" + digest("fresh-clone-transaction", identity)
    snapshot_id = "snapshot:" + digest("fresh-clone-snapshot", identity)
    binding = {
        "transaction_id": transaction_id,
        "snapshot_id": snapshot_id,
        "candidate_sha": candidate_sha,
        "tree_sha": candidate_tree_sha,
        "input_digest": input_digest,
        "tool_id": "update-agent-canon",
        "tool_version": "fresh-clone-acceptance.v1",
        "evidence_ref": evidence("fresh-clone-binding", identity),
        "evidence_digest": "sha256:" + digest("fresh-clone-binding", identity),
        "timing": {
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:00:00Z",
            "last_attempt_at": "2026-01-01T00:00:00Z",
            "duration_ms": 0,
            "attempt": 1,
            "replayed": False,
        },
    }
    checked_binding = validate_record_binding(binding)
    base_identity = {
        "remote": "origin",
        "ref": "refs/heads/main",
        "commit_sha": candidate_sha,
        "tree_sha": candidate_tree_sha,
    }
    rebind = materialize_source_main_rebind_receipt(
        binding=checked_binding,
        old_base_identity=base_identity,
        new_base_identity=base_identity,
        origin_main_readback_evidence_ref=evidence(
            "fresh-clone-origin-main-readback", identity
        ),
    )

    cas_evidence_ref = evidence("fresh-clone-cas", identity)
    cas_binding = dict(checked_binding)
    cas_binding["evidence_ref"] = cas_evidence_ref
    cas_binding["evidence_digest"] = "sha256:" + digest(
        "fresh-clone-cas", identity
    )
    cas = validate_candidate_cas_rebind_transition(
        rebind,
        {
            "schema": CANDIDATE_CAS_SCHEMA,
            "cas_receipt_id": "cas:" + digest("fresh-clone-cas-id", identity),
            "binding": cas_binding,
            "predecessor_evidence_id": checked_binding["evidence_ref"],
            "rebind_receipt_evidence_id": rebind["rebind_receipt_id"],
            "candidate_identity": {
                "candidate_sha": candidate_sha,
                "tree_sha": candidate_tree_sha,
            },
            "cas_base_identity": {
                "commit_sha": candidate_sha,
                "tree_sha": candidate_tree_sha,
            },
            "cas_evidence_ref": cas_evidence_ref,
            "cas_stage": "cas",
        },
    )

    repository_digest = "sha256:" + digest(
        "fresh-clone-remote-url", identity
    )
    branch_ref = "refs/heads/canon/fresh-clone-acceptance"
    lifecycle_binding = dict(checked_binding)
    lifecycle_binding["evidence_ref"] = evidence(
        "fresh-clone-pr-lifecycle", identity
    )
    lifecycle_binding["evidence_digest"] = "sha256:" + digest(
        "fresh-clone-pr-lifecycle", identity
    )
    lifecycle = {
        "schema": PULL_REQUEST_LIFECYCLE_SCHEMA,
        "kind": "user",
        "binding": lifecycle_binding,
        "state": "merged",
        "remote_identity": {
            "repo_owner": "fresh-clone-acceptance",
            "repo_name": "agent-canon",
            "remote_name": "origin",
            "url_digest": repository_digest,
            "ref": branch_ref,
            "commit_sha": candidate_sha,
            "tree_sha": candidate_tree_sha,
        },
        "base_identity": {
            "repo_owner": "fresh-clone-acceptance",
            "repo_name": "agent-canon",
            "ref": "refs/heads/main",
            "commit_sha": candidate_sha,
            "tree_sha": candidate_tree_sha,
        },
        "head_identity": {
            "repo_owner": "fresh-clone-acceptance",
            "repo_name": "agent-canon",
            "ref": branch_ref,
            "commit_sha": candidate_sha,
            "tree_sha": candidate_tree_sha,
        },
        "branch": pull_request_branch_table(),
        "permission_identity": {
            "actor_id": "fresh-clone-acceptance",
            "permission_state": "verified_true",
            "permission_evidence_id": evidence(
                "fresh-clone-permission", identity
            ),
            "authority_source": "canonical fresh-clone acceptance fixture",
            "assumption_forbidden": True,
        },
        "pr_essence": {
            "problem": "exercise parent projection from a fresh clone",
            "intent": "queue the observed AgentCanon source update",
            "canonical_owner": "tools/update_agent_canon.sh",
            "contract_delta": "fresh-clone source projection",
            "evidence_refs": [evidence("fresh-clone-pr-essence", identity)],
        },
        "reviews": [],
        "user_identity": {
            "actor_id": "fresh-clone-acceptance",
            "display_name": "Fresh Clone Acceptance",
        },
    }
    checked_lifecycle = validate_candidate_cas_pr_transition(cas, lifecycle)
    readback = materialize_publication_readback_receipt(
        candidate_cas_receipt=cas,
        pull_request_lifecycle=checked_lifecycle,
        authoritative_pr_readback={
            "number": 1,
            "state": "MERGED",
            "baseRefName": "main",
            "baseRefOid": publication_sha,
            "mergeCasBaseOid": candidate_sha,
            "mergeCasBaseTreeOid": candidate_tree_sha,
            "headRefName": "canon/fresh-clone-acceptance",
            "headRefOid": candidate_sha,
            "headRepository": {
                "nameWithOwner": "fresh-clone-acceptance/agent-canon"
            },
            "mergeCommit": {"oid": publication_sha},
            "mergeTreeOid": publication_tree_sha,
        },
    )

    g1 = materialize_gate_verdict(
        binding=checked_binding,
        gate_id="G1",
        ordered_input_evidence_refs=[checked_binding["evidence_ref"]],
        invariant="source_correctness",
        output_digest="sha256:" + digest("fresh-clone-g1", identity),
        owner=f"{Path(__file__).resolve().with_name('publication_integrator.py')}#resolve_publication_eligibility",
        verdict="pass",
    )
    g2 = gate_owner_apis.materialize_generated_completeness_receipt(
        g1_gate=g1,
        candidate_sha=candidate_sha,
        tree_sha=candidate_tree_sha,
        check_results=[
            {"check_id": check_id, "status": "pass"}
            for check_id in gate_owner_apis.generated_completeness_check_ids
        ],
    )
    g3 = gate_owner_apis.materialize_pr_identity_gate(
        checked_lifecycle,
        cas,
        rebind,
        [g1, g2],
    )
    return materialize_source_projection_packet(
        binding=checked_binding,
        source_main_rebind_receipt=rebind,
        candidate_cas_receipt=cas,
        pull_request_lifecycle=checked_lifecycle,
        publication_readback_receipt=readback,
        source_gate_verdicts=[g1, g2, g3],
        ordered_predecessor_evidence=[
            {
                "queue_number": 388,
                "source_pr": "#388",
                "publication_evidence_id": evidence(
                    "fresh-clone-predecessor-388", identity
                ),
            },
            {
                "queue_number": 389,
                "source_pr": "#389",
                "source_pr_sha": digest("fresh-clone-predecessor-389", identity)[:40],
                "publication_evidence_id": evidence(
                    "fresh-clone-predecessor-389", identity
                ),
            },
        ],
        acceptance_evidence_ref=evidence(
            "fresh-clone-frontier-acceptance", identity
        ),
    )


def source_publication_identity(value: object) -> dict[str, object]:
    """Return the authoritative merge identity carried into projection."""
    readback = validate_publication_readback_receipt(value)
    pr = cast(Mapping[str, object], readback["pr_identity"])
    return {
        "readback_receipt_id": readback["readback_receipt_id"],
        "merge_commit_sha": pr["merge_commit_sha"],
        "merge_tree_sha": pr["merge_tree_sha"],
        "publication_evidence_ref": readback["publication_evidence_ref"],
    }


def _validate_source_publication_identity(value: object, field: str) -> dict[str, object]:
    identity = _mapping(value, field)
    _exact_keys(
        identity,
        (
            "readback_receipt_id",
            "merge_commit_sha",
            "merge_tree_sha",
            "publication_evidence_ref",
        ),
        field=field,
    )
    readback_id = _pattern(
        identity["readback_receipt_id"], _HASH_ID, f"{field}.readback_receipt_id"
    )
    if not readback_id.startswith("publication-readback:"):
        _fail("lifecycle:identity_invalid", f"{field}.readback_receipt_id")
    _pattern(identity["merge_commit_sha"], _HEX40, f"{field}.merge_commit_sha")
    _pattern(identity["merge_tree_sha"], _HEX40, f"{field}.merge_tree_sha")
    _pattern(
        identity["publication_evidence_ref"],
        _EVIDENCE,
        f"{field}.publication_evidence_ref",
    )
    return _clone(identity)


def queue_once_key(
    source_namespace: str,
    binding: Mapping[str, object],
    publication_identity: Mapping[str, object],
) -> str:
    checked = validate_record_binding(binding)
    publication = _validate_source_publication_identity(
        publication_identity, "queue_once_key.publication_identity"
    )
    body = "|".join(
        (
            source_namespace,
            cast(str, checked["candidate_sha"]),
            cast(str, checked["tree_sha"]),
            cast(str, checked["input_digest"]),
            cast(str, publication["merge_commit_sha"]),
            cast(str, publication["merge_tree_sha"]),
        )
    )
    return "queue-key:" + hashlib.sha256(body.encode()).hexdigest()


def validate_queue_receipt(value: object) -> dict[str, object]:
    receipt = _mapping(value, "queue_receipt")
    _exact_keys(
        receipt,
        (
            "schema",
            "queue_receipt_id",
            "binding",
            "source_namespace",
            "source_main_rebind_receipt_id",
            "source_main_readback_evidence_ref",
            "source_publication_identity",
            "enqueue_once_key",
            "state",
        ),
        field="queue_receipt",
    )
    _schema(receipt, QUEUE_RECEIPT_SCHEMA)
    queue_id = _pattern(receipt["queue_receipt_id"], _HASH_ID, "queue_receipt.queue_receipt_id")
    if not queue_id.startswith("queue:"):
        _fail("lifecycle:identity_invalid", "queue_receipt.queue_receipt_id")
    binding = validate_record_binding(receipt["binding"])
    namespace = _string(receipt["source_namespace"], "queue_receipt.source_namespace")
    if not Path(namespace).is_absolute():
        _fail("lifecycle:path_not_absolute", "queue_receipt.source_namespace")
    rebind_id = _pattern(receipt["source_main_rebind_receipt_id"], _HASH_ID, "queue_receipt.source_main_rebind_receipt_id")
    if not rebind_id.startswith("rebind:"):
        _fail("lifecycle:identity_invalid", "queue_receipt.source_main_rebind_receipt_id")
    _pattern(receipt["source_main_readback_evidence_ref"], _EVIDENCE, "queue_receipt.source_main_readback_evidence_ref")
    publication = _validate_source_publication_identity(
        receipt["source_publication_identity"],
        "queue_receipt.source_publication_identity",
    )
    if receipt["enqueue_once_key"] != queue_once_key(namespace, binding, publication):
        _fail("lifecycle:queue_key_mismatch")
    _one_of(receipt["state"], ("accepted", "retry_pending", "failed"), "queue_receipt.state")
    return _clone(receipt)


def materialize_queue_receipt(
    *,
    binding: Mapping[str, object],
    source_namespace: str,
    source_main_rebind_receipt_id: str,
    source_main_readback_evidence_ref: str,
    publication_readback_receipt: Mapping[str, object],
    state: str,
) -> dict[str, object]:
    checked = validate_record_binding(binding)
    publication = source_publication_identity(publication_readback_receipt)
    key = queue_once_key(source_namespace, checked, publication)
    receipt_id = "queue:" + hashlib.sha256(key.encode()).hexdigest()
    return validate_queue_receipt(
        {
            "schema": QUEUE_RECEIPT_SCHEMA,
            "queue_receipt_id": receipt_id,
            "binding": checked,
            "source_namespace": source_namespace,
            "source_main_rebind_receipt_id": source_main_rebind_receipt_id,
            "source_main_readback_evidence_ref": source_main_readback_evidence_ref,
            "source_publication_identity": publication,
            "enqueue_once_key": key,
            "state": state,
        }
    )


def validate_immutable_replay(
    existing: object,
    requested: object,
    *,
    field: str,
) -> None:
    """Reject replay when any immutable receipt field changed."""

    def immutable(record: object) -> dict[str, object]:
        cloned = _clone(_mapping(record, field))
        binding = _mapping(cloned.get("binding"), f"{field}.binding")
        binding_copy = dict(binding)
        binding_copy.pop("timing", None)
        cloned["binding"] = binding_copy
        return cloned

    if immutable(existing) != immutable(requested):
        _fail("input_identity_mismatch", field)


def frontier_key(
    source_namespace: str,
    binding: Mapping[str, object],
    publication_identity: Mapping[str, object],
) -> str:
    checked = validate_record_binding(binding)
    publication = _validate_source_publication_identity(
        publication_identity, "frontier_key.publication_identity"
    )
    body = "|".join(
        (
            source_namespace,
            cast(str, checked["candidate_sha"]),
            cast(str, checked["tree_sha"]),
            cast(str, checked["input_digest"]),
            cast(str, publication["merge_commit_sha"]),
            cast(str, publication["merge_tree_sha"]),
        )
    )
    return "frontier-key:" + hashlib.sha256(body.encode()).hexdigest()


def validate_dependency_frontier(value: object) -> dict[str, object]:
    frontier = _mapping(value, "dependency_frontier")
    _exact_keys(
        frontier,
        (
            "schema",
            "frontier_id",
            "binding",
            "frontier_state",
            "queue_receipt_id",
            "source_namespace",
            "source_main_rebind_receipt_id",
            "source_main_rebind_evidence_ref",
            "source_main_readback_evidence_ref",
            "source_publication_identity",
            "ordered_predecessor_evidence",
            "frontier_key",
            "preceding_frontier_evidence_id",
            "acceptance_evidence_ref",
            "parent_projection_evidence_ref",
        ),
        field="dependency_frontier",
    )
    _schema(frontier, DEPENDENCY_FRONTIER_SCHEMA)
    frontier_id = _pattern(frontier["frontier_id"], _HASH_ID, "dependency_frontier.frontier_id")
    if not frontier_id.startswith("frontier:"):
        _fail("lifecycle:identity_invalid", "dependency_frontier.frontier_id")
    binding = validate_record_binding(frontier["binding"])
    state = _one_of(frontier["frontier_state"], ("pending", "accepted", "failed"), "dependency_frontier.frontier_state")
    queue_id = _pattern(frontier["queue_receipt_id"], _HASH_ID, "dependency_frontier.queue_receipt_id")
    if not queue_id.startswith("queue:"):
        _fail("lifecycle:identity_invalid", "dependency_frontier.queue_receipt_id")
    namespace = _string(frontier["source_namespace"], "dependency_frontier.source_namespace")
    if not Path(namespace).is_absolute():
        _fail("lifecycle:path_not_absolute", "dependency_frontier.source_namespace")
    rebind_id = _pattern(frontier["source_main_rebind_receipt_id"], _HASH_ID, "dependency_frontier.source_main_rebind_receipt_id")
    if not rebind_id.startswith("rebind:"):
        _fail("lifecycle:identity_invalid", "dependency_frontier.source_main_rebind_receipt_id")
    _pattern(frontier["source_main_rebind_evidence_ref"], _EVIDENCE, "dependency_frontier.source_main_rebind_evidence_ref")
    _pattern(frontier["source_main_readback_evidence_ref"], _EVIDENCE, "dependency_frontier.source_main_readback_evidence_ref")
    publication = _validate_source_publication_identity(
        frontier["source_publication_identity"],
        "dependency_frontier.source_publication_identity",
    )
    predecessors = _sequence(frontier["ordered_predecessor_evidence"], "dependency_frontier.ordered_predecessor_evidence")
    if len(predecessors) != 2:
        _fail("frontier:predecessor_order_invalid")
    expected = ((388, "#388"), (389, "#389"))
    for index, (item, (number, source_pr)) in enumerate(zip(predecessors, expected, strict=True)):
        record = _mapping(item, f"dependency_frontier.ordered_predecessor_evidence[{index}]")
        required = ("queue_number", "source_pr", "publication_evidence_id")
        optional = ("source_pr_sha",) if number == 389 else ()
        _exact_keys(record, required, optional=optional, field=f"dependency_frontier.ordered_predecessor_evidence[{index}]")
        if record["queue_number"] != number or record["source_pr"] != source_pr:
            _fail("frontier:predecessor_order_invalid")
        _pattern(record["publication_evidence_id"], _EVIDENCE, f"dependency_frontier.ordered_predecessor_evidence[{index}].publication_evidence_id")
        if number == 389:
            _pattern(record.get("source_pr_sha"), _HEX40, "dependency_frontier.ordered_predecessor_evidence[1].source_pr_sha")
    if frontier["frontier_key"] != frontier_key(namespace, binding, publication):
        _fail("frontier:key_mismatch")
    preceding = frontier["preceding_frontier_evidence_id"]
    acceptance = frontier["acceptance_evidence_ref"]
    if state == "pending":
        if acceptance is not None or preceding is not None:
            _fail("frontier:pending_evidence_forbidden")
    elif state == "accepted":
        _pattern(acceptance, _EVIDENCE, "dependency_frontier.acceptance_evidence_ref")
        _pattern(preceding, _EVIDENCE, "dependency_frontier.preceding_frontier_evidence_id")
    elif acceptance is not None:
        _pattern(acceptance, _EVIDENCE, "dependency_frontier.acceptance_evidence_ref")
    if frontier["parent_projection_evidence_ref"] is not None:
        _fail("frontier:parent_projection_before_acceptance")
    return _clone(frontier)


def materialize_dependency_frontier(
    *,
    binding: Mapping[str, object],
    queue_receipt: Mapping[str, object],
    rebind_receipt: Mapping[str, object],
    source_main_readback_evidence_ref: str,
    ordered_predecessor_evidence: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Materialize the immutable pending frontier before acceptance evidence."""
    checked_binding = validate_record_binding(binding)
    queue = validate_queue_receipt(queue_receipt)
    rebind = validate_source_main_rebind_receipt(rebind_receipt)
    _same_binding(checked_binding, queue["binding"], "dependency_frontier.queue")
    _same_binding(checked_binding, rebind["binding"], "dependency_frontier.rebind")
    if queue["state"] != "accepted":
        _fail("frontier:queue_not_accepted")
    if queue["source_main_rebind_receipt_id"] != rebind["rebind_receipt_id"]:
        _fail("frontier:rebind_mismatch")
    publication = _validate_source_publication_identity(
        queue["source_publication_identity"],
        "dependency_frontier.queue.source_publication_identity",
    )
    key = frontier_key(
        cast(str, queue["source_namespace"]), checked_binding, publication
    )
    frontier_id = "frontier:" + hashlib.sha256(key.encode()).hexdigest()
    rebind_binding = cast(Mapping[str, object], rebind["binding"])
    return validate_dependency_frontier(
        {
            "schema": DEPENDENCY_FRONTIER_SCHEMA,
            "frontier_id": frontier_id,
            "binding": checked_binding,
            "frontier_state": "pending",
            "queue_receipt_id": queue["queue_receipt_id"],
            "source_namespace": queue["source_namespace"],
            "source_main_rebind_receipt_id": rebind["rebind_receipt_id"],
            "source_main_rebind_evidence_ref": rebind_binding["evidence_ref"],
            "source_main_readback_evidence_ref": source_main_readback_evidence_ref,
            "source_publication_identity": publication,
            "ordered_predecessor_evidence": [
                dict(item) for item in ordered_predecessor_evidence
            ],
            "frontier_key": key,
            "preceding_frontier_evidence_id": None,
            "acceptance_evidence_ref": None,
            "parent_projection_evidence_ref": None,
        }
    )


def validate_dependency_frontier_transition(
    pending: object,
    accepted: object,
    *,
    queue_receipt: object,
    rebind_receipt: object,
    origin_main_readback: SourceMainReadbackIdentity,
    ordered_oracle: Sequence[str],
) -> dict[str, object]:
    before = validate_dependency_frontier(pending)
    after = validate_dependency_frontier(accepted)
    queue = validate_queue_receipt(queue_receipt)
    rebind = validate_source_main_rebind_receipt(rebind_receipt)
    if before["frontier_state"] != "pending" or after["frontier_state"] != "accepted":
        _fail("frontier:transition_invalid")
    _same_binding(before["binding"], after["binding"], "dependency_frontier")
    immutable = (
        "frontier_id",
        "queue_receipt_id",
        "source_namespace",
        "source_main_rebind_receipt_id",
        "source_main_rebind_evidence_ref",
        "source_main_readback_evidence_ref",
        "source_publication_identity",
        "ordered_predecessor_evidence",
        "frontier_key",
        "parent_projection_evidence_ref",
    )
    for field in immutable:
        if before[field] != after[field]:
            _fail("frontier:immutable_field_changed", field)
    before_binding = cast(Mapping[str, object], before["binding"])
    if after["preceding_frontier_evidence_id"] != before_binding["evidence_ref"]:
        _fail("frontier:preceding_evidence_mismatch")
    if queue["state"] != "accepted" or queue["queue_receipt_id"] != after["queue_receipt_id"]:
        _fail("frontier:queue_not_accepted")
    _same_binding(queue["binding"], after["binding"], "dependency_frontier.queue")
    if rebind["rebind_receipt_id"] != after["source_main_rebind_receipt_id"]:
        _fail("frontier:rebind_mismatch")
    rebind_binding = cast(Mapping[str, object], rebind["binding"])
    if rebind_binding["evidence_ref"] != after["source_main_rebind_evidence_ref"]:
        _fail("frontier:rebind_evidence_mismatch")
    publication = cast(Mapping[str, object], after["source_publication_identity"])
    origin_main_commit_sha = _pattern(
        origin_main_readback.commit_sha,
        _HEX40,
        "dependency_frontier.origin_main_readback.commit_sha",
    )
    origin_main_tree_sha = _pattern(
        origin_main_readback.tree_sha,
        _HEX40,
        "dependency_frontier.origin_main_readback.tree_sha",
    )
    if (
        publication["merge_commit_sha"] != origin_main_commit_sha
        or publication["merge_tree_sha"] != origin_main_tree_sha
    ):
        _fail("frontier:origin_main_readback_mismatch")
    expected_oracle = (
        "source_pr:#388",
        "source_pr:#389",
        f"transaction:{after_binding_transaction(after)}",
    )
    if tuple(ordered_oracle) != expected_oracle:
        _fail("frontier:ordered_oracle_mismatch")
    return after


def after_binding_transaction(frontier: Mapping[str, object]) -> str:
    binding = cast(Mapping[str, object], frontier["binding"])
    transaction_id = cast(str, binding["transaction_id"])
    return transaction_id


def validate_durable_handback(value: object) -> dict[str, object]:
    handback = _mapping(value, "durable_handback")
    _exact_keys(handback, ("schema", "binding", "agent_id", "descendant_ids", "reservation_ids", "evidence_ref", "state"), field="durable_handback")
    _schema(handback, DURABLE_HANDBACK_SCHEMA)
    validate_record_binding(handback["binding"])
    agent_id = _string(handback["agent_id"], "durable_handback.agent_id")
    if not agent_id.startswith("agent:"):
        _fail("lifecycle:identity_invalid", "durable_handback.agent_id")
    descendants = _string_list(handback["descendant_ids"], "durable_handback.descendant_ids")
    reservations = _string_list(handback["reservation_ids"], "durable_handback.reservation_ids")
    if any(not item.startswith("agent:") for item in descendants):
        _fail("lifecycle:identity_invalid", "durable_handback.descendant_ids")
    if any(not item.startswith("reservation:") for item in reservations):
        _fail("lifecycle:identity_invalid", "durable_handback.reservation_ids")
    _pattern(handback["evidence_ref"], _EVIDENCE, "durable_handback.evidence_ref")
    if handback["state"] != "durable_handback":
        _fail("lifecycle:state_invalid", "durable_handback")
    return _clone(handback)


def validate_descendant_close_receipt(value: object) -> dict[str, object]:
    """Validate one transaction-bound descendant terminal receipt."""
    receipt = _mapping(value, "descendant_close_receipt")
    _exact_keys(
        receipt,
        (
            "schema",
            "binding",
            "agent_id",
            "state",
            "durable_handback_evidence_ref",
            "evidence_ref",
        ),
        field="descendant_close_receipt",
    )
    _schema(receipt, DESCENDANT_CLOSE_RECEIPT_SCHEMA)
    validate_record_binding(receipt["binding"])
    agent_id = _string(receipt["agent_id"], "descendant_close_receipt.agent_id")
    if not agent_id.startswith("agent:"):
        _fail("lifecycle:identity_invalid", "descendant_close_receipt.agent_id")
    if receipt["state"] != "closed":
        _fail("close_agent:descendant_not_closed")
    _pattern(
        receipt["durable_handback_evidence_ref"],
        _EVIDENCE,
        "descendant_close_receipt.durable_handback_evidence_ref",
    )
    _pattern(receipt["evidence_ref"], _EVIDENCE, "descendant_close_receipt.evidence_ref")
    return _clone(receipt)


def materialize_descendant_close_receipt(
    *,
    binding: Mapping[str, object],
    durable_handback: Mapping[str, object],
    agent_id: str,
    evidence_ref: str,
) -> dict[str, object]:
    """Materialize one close receipt only for a declared descendant."""
    checked_binding = validate_record_binding(binding)
    handback = validate_durable_handback(durable_handback)
    _same_binding(checked_binding, handback["binding"], "descendant_close")
    if agent_id not in cast(Sequence[object], handback["descendant_ids"]):
        _fail("close_agent:unknown_descendant")
    return validate_descendant_close_receipt(
        {
            "schema": DESCENDANT_CLOSE_RECEIPT_SCHEMA,
            "binding": checked_binding,
            "agent_id": agent_id,
            "state": "closed",
            "durable_handback_evidence_ref": handback["evidence_ref"],
            "evidence_ref": evidence_ref,
        }
    )


def validate_reservation_release_receipt(value: object) -> dict[str, object]:
    """Validate one transaction-bound reservation release receipt."""
    receipt = _mapping(value, "reservation_release_receipt")
    _exact_keys(
        receipt,
        (
            "schema",
            "binding",
            "reservation_id",
            "state",
            "durable_handback_evidence_ref",
            "evidence_ref",
        ),
        field="reservation_release_receipt",
    )
    _schema(receipt, RESERVATION_RELEASE_RECEIPT_SCHEMA)
    validate_record_binding(receipt["binding"])
    reservation_id = _string(
        receipt["reservation_id"], "reservation_release_receipt.reservation_id"
    )
    if not reservation_id.startswith("reservation:"):
        _fail("lifecycle:identity_invalid", "reservation_release_receipt.reservation_id")
    if receipt["state"] != "released":
        _fail("close_agent:reservation_leak")
    _pattern(
        receipt["durable_handback_evidence_ref"],
        _EVIDENCE,
        "reservation_release_receipt.durable_handback_evidence_ref",
    )
    _pattern(
        receipt["evidence_ref"], _EVIDENCE, "reservation_release_receipt.evidence_ref"
    )
    return _clone(receipt)


def materialize_reservation_release_receipt(
    *,
    binding: Mapping[str, object],
    durable_handback: Mapping[str, object],
    reservation_id: str,
    evidence_ref: str,
) -> dict[str, object]:
    """Materialize one release receipt only for a declared reservation."""
    checked_binding = validate_record_binding(binding)
    handback = validate_durable_handback(durable_handback)
    _same_binding(checked_binding, handback["binding"], "reservation_release")
    if reservation_id not in cast(Sequence[object], handback["reservation_ids"]):
        _fail("close_agent:reservation_leak")
    return validate_reservation_release_receipt(
        {
            "schema": RESERVATION_RELEASE_RECEIPT_SCHEMA,
            "binding": checked_binding,
            "reservation_id": reservation_id,
            "state": "released",
            "durable_handback_evidence_ref": handback["evidence_ref"],
            "evidence_ref": evidence_ref,
        }
    )


def validate_cleanup_proof(value: object) -> dict[str, object]:
    proof = _mapping(value, "cleanup_proof")
    _exact_keys(
        proof,
        (
            "schema",
            "binding",
            "remote_readback_evidence_ref",
            "task_owned_paths",
            "task_owned_state_before",
            "task_owned_state_after",
            "cleaned_paths",
            "unknown_shared_state_before_digest",
            "unknown_shared_state_after_digest",
            "unknown_shared_state_unchanged_evidence_ref",
            "evidence_ref",
            "state",
        ),
        field="cleanup_proof",
    )
    _schema(proof, CLEANUP_PROOF_SCHEMA)
    validate_record_binding(proof["binding"])
    _pattern(proof["remote_readback_evidence_ref"], _EVIDENCE, "cleanup_proof.remote_readback_evidence_ref")
    owned_paths = _string_list(proof["task_owned_paths"], "cleanup_proof.task_owned_paths")
    cleaned_paths = _string_list(proof["cleaned_paths"], "cleanup_proof.cleaned_paths")
    if any(not Path(path).is_absolute() for path in (*owned_paths, *cleaned_paths)):
        _fail("lifecycle:path_not_absolute", "cleanup_proof")
    if not set(cleaned_paths).issubset(owned_paths):
        _fail("cleanup:non_task_owned_path")
    before = _mapping(proof["task_owned_state_before"], "cleanup_proof.task_owned_state_before")
    after = _mapping(proof["task_owned_state_after"], "cleanup_proof.task_owned_state_after")
    if set(before) != set(owned_paths) or set(after) != set(owned_paths):
        _fail("cleanup:task_owned_state_incomplete")
    for path in owned_paths:
        _string(before[path], f"cleanup_proof.task_owned_state_before.{path}")
        _string(after[path], f"cleanup_proof.task_owned_state_after.{path}")
    before_digest = _pattern(proof["unknown_shared_state_before_digest"], _SHA256, "cleanup_proof.unknown_shared_state_before_digest")
    after_digest = _pattern(proof["unknown_shared_state_after_digest"], _SHA256, "cleanup_proof.unknown_shared_state_after_digest")
    if before_digest != after_digest:
        _fail("cleanup:unknown_shared_state_changed")
    _pattern(proof["unknown_shared_state_unchanged_evidence_ref"], _EVIDENCE, "cleanup_proof.unknown_shared_state_unchanged_evidence_ref")
    _pattern(proof["evidence_ref"], _EVIDENCE, "cleanup_proof.evidence_ref")
    if proof["state"] != "cleanup_proven":
        _fail("lifecycle:state_invalid", "cleanup_proof")
    return _clone(proof)


def _validate_gate_sequence(values: Sequence[object], binding: object) -> tuple[dict[str, object], ...]:
    try:
        gates = validate_gate_chain(
            values,
            expected_gate_ids=GATE_IDS,
            require_pass=True,
        )
    except LifecycleContractError as exc:
        if exc.code in {
            "lifecycle:gate_order_invalid",
            "lifecycle:gate_sequence_empty",
        }:
            _fail("close_agent:all_six_gate_evidence_required")
        raise
    for gate in gates:
        _same_binding(binding, gate["binding"], "close_agent.gates")
    return gates


def validate_close_agent_tool_call(value: object) -> dict[str, object]:
    token = _mapping(value, "close_agent_tool_call")
    _exact_keys(
        token,
        (
            "schema",
            "binding",
            "tool_id",
            "state",
            "agent_id",
            "args_schema",
            "args",
            "terminal_guard",
            "token_id",
            "token_body_sha256",
        ),
        field="close_agent_tool_call",
    )
    _schema(token, CLOSE_AGENT_TOOL_CALL_SCHEMA)
    binding = validate_record_binding(token["binding"])
    if token["tool_id"] != "close_agent":
        _fail("close_agent:tool_id_invalid")
    if token["state"] != "terminal":
        _fail("close_agent:not_terminal")
    agent_id = _string(token["agent_id"], "close_agent_tool_call.agent_id")
    if not agent_id.startswith("agent:"):
        _fail("lifecycle:identity_invalid", "close_agent_tool_call.agent_id")
    if token["args_schema"] != CLOSE_AGENT_ARGS_SCHEMA:
        _fail("close_agent:args_schema_invalid")
    args = _mapping(token["args"], "close_agent_tool_call.args")
    _exact_keys(args, ("run_id", "gate_verdict_evidence_refs", "cleanup_proof_evidence_ref", "durable_handback_evidence_ref", "descendants_closed_evidence_ref", "reservations_released_evidence_ref"), field="close_agent_tool_call.args")
    _string(args["run_id"], "close_agent_tool_call.args.run_id")
    refs = _string_list(args["gate_verdict_evidence_refs"], "close_agent_tool_call.args.gate_verdict_evidence_refs", pattern=_EVIDENCE, nonempty=True)
    if len(refs) != len(GATE_IDS):
        _fail("close_agent:all_six_gate_evidence_required")
    for field in ("cleanup_proof_evidence_ref", "durable_handback_evidence_ref", "descendants_closed_evidence_ref", "reservations_released_evidence_ref"):
        _pattern(args[field], _EVIDENCE, f"close_agent_tool_call.args.{field}")
    guard = _mapping(token["terminal_guard"], "close_agent_tool_call.terminal_guard")
    _exact_keys(guard, ("all_six_gates_pass", "lifecycle_state", "completed_but_open", "unknown_descendants", "reservation_leak", "remote_readback_before_cleanup", "identity_match"), field="close_agent_tool_call.terminal_guard")
    expected_guard = {
        "all_six_gates_pass": True,
        "lifecycle_state": "terminal",
        "completed_but_open": False,
        "unknown_descendants": False,
        "reservation_leak": False,
        "remote_readback_before_cleanup": True,
        "identity_match": True,
    }
    if dict(guard) != expected_guard:
        if guard.get("completed_but_open") is True:
            _fail("close_agent:completed_but_open")
        if guard.get("unknown_descendants") is True:
            _fail("close_agent:unknown_descendant")
        if guard.get("reservation_leak") is True:
            _fail("close_agent:reservation_leak")
        if guard.get("remote_readback_before_cleanup") is not True:
            _fail("close_agent:cleanup_before_remote_readback")
        _fail("close_agent:terminal_guard_failed")
    token_id = _pattern(token["token_id"], _HASH_ID, "close_agent_tool_call.token_id")
    if not token_id.startswith("close-token:"):
        _fail("lifecycle:identity_invalid", "close_agent_tool_call.token_id")
    expected_id = "close-token:" + hashlib.sha256(
        canonical_json_bytes({key: item for key, item in token.items() if key not in {"token_id", "token_body_sha256"}})
    ).hexdigest()
    if token_id != expected_id:
        _fail("close_agent:token_id_mismatch")
    expected_body = "sha256:" + canonical_body_sha256(token, "token_body_sha256")
    if token["token_body_sha256"] != expected_body:
        _fail("close_agent:token_body_mismatch")
    return _clone(token)


def materialize_close_agent_tool_call(
    *,
    binding: Mapping[str, object],
    run_id: str,
    agent_id: str,
    gate_verdicts: Sequence[Mapping[str, object]],
    cleanup_proof: Mapping[str, object],
    durable_handback: Mapping[str, object],
    descendants_closed_evidence_ref: str,
    reservations_released_evidence_ref: str,
    completed_but_open: bool = False,
    unknown_descendants: bool = False,
    reservation_leak: bool = False,
) -> dict[str, object]:
    checked_binding = validate_record_binding(binding)
    gates = _validate_gate_sequence(list(gate_verdicts), checked_binding)
    proof = validate_cleanup_proof(cleanup_proof)
    handback = validate_durable_handback(durable_handback)
    _same_binding(checked_binding, proof["binding"], "close_agent.cleanup_proof")
    _same_binding(checked_binding, handback["binding"], "close_agent.durable_handback")
    if proof["remote_readback_evidence_ref"] is None:
        _fail("close_agent:cleanup_before_remote_readback")
    record: dict[str, object] = {
        "schema": CLOSE_AGENT_TOOL_CALL_SCHEMA,
        "binding": checked_binding,
        "tool_id": "close_agent",
        "state": "terminal",
        "agent_id": agent_id,
        "args_schema": CLOSE_AGENT_ARGS_SCHEMA,
        "args": {
            "run_id": run_id,
            "gate_verdict_evidence_refs": [
                cast(Mapping[str, object], gate["binding"])["evidence_ref"]
                for gate in gates
            ],
            "cleanup_proof_evidence_ref": proof["evidence_ref"],
            "durable_handback_evidence_ref": handback["evidence_ref"],
            "descendants_closed_evidence_ref": descendants_closed_evidence_ref,
            "reservations_released_evidence_ref": reservations_released_evidence_ref,
        },
        "terminal_guard": {
            "all_six_gates_pass": True,
            "lifecycle_state": "terminal",
            "completed_but_open": completed_but_open,
            "unknown_descendants": unknown_descendants,
            "reservation_leak": reservation_leak,
            "remote_readback_before_cleanup": True,
            "identity_match": True,
        },
    }
    record["token_id"] = "close-token:" + hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    record["token_body_sha256"] = "sha256:" + canonical_body_sha256(record, "token_body_sha256")
    return validate_close_agent_tool_call(record)


_TRANSACTION_TRANSITIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("created", "prepared"): ("prepare_receipt",),
    ("prepared", "generated"): ("generate_receipt",),
    ("generated", "gates_ready"): ("gate_verdicts",),
    ("gates_ready", "reviewed"): ("candidate_review_receipt", "candidate_cas_receipt"),
    ("reviewed", "pr_open"): ("pr_lifecycle",),
    ("pr_open", "pr_merged"): ("pr_lifecycle",),
    ("pr_merged", "source_main_readback"): ("publication_readback_receipt",),
    ("source_main_readback", "queue_enqueued"): ("queue_receipt",),
    ("queue_enqueued", "frontier_accepted"): ("dependency_frontier",),
    ("frontier_accepted", "remote_readback"): ("gate_verdicts",),
    ("remote_readback", "durable_handback"): ("durable_handback",),
    ("durable_handback", "descendants_closed"): ("descendants_closed_evidence_ref",),
    ("descendants_closed", "reservations_released"): ("reservations_released_evidence_ref",),
    ("reservations_released", "cleanup_proven"): ("cleanup_proof",),
    ("cleanup_proven", "nested_lifecycle_cleanup"): ("gate_verdicts", "cleanup_proof"),
    ("nested_lifecycle_cleanup", "closed"): ("close_agent_tool_call",),
}


def guard_transition(
    current_state: str,
    next_state: str,
    *,
    evidence: Mapping[str, object],
) -> None:
    """Reject an out-of-order transaction transition before side effects."""
    _one_of(current_state, TRANSACTION_STATES, "transition.current_state")
    _one_of(next_state, TRANSACTION_STATES, "transition.next_state")
    if next_state in {"failed", "successor_required"}:
        required = "failure_code" if next_state == "failed" else "successor_transaction_id"
        _string(evidence.get(required), f"transition.{required}")
        return
    required_fields = _TRANSACTION_TRANSITIONS.get((current_state, next_state))
    if required_fields is None:
        _fail("lifecycle:transition_invalid", f"{current_state}->{next_state}")
    for field in required_fields:
        if field not in evidence:
            _fail("lifecycle:transition_evidence_missing", field)
    if (current_state, next_state) == ("generated", "gates_ready"):
        try:
            validate_gate_chain(
                _sequence(evidence["gate_verdicts"], "transition.gate_verdicts"),
                expected_gate_ids=("G1", "G2"),
                require_pass=True,
            )
        except LifecycleContractError:
            _fail("lifecycle:gates_not_ready")
    elif (current_state, next_state) == ("reviewed", "pr_open"):
        pr = validate_pull_request_lifecycle(evidence["pr_lifecycle"])
        if pr["state"] not in {"ready", "external_review"}:
            _fail("lifecycle:pr_not_open_ready")
    elif (current_state, next_state) == ("pr_open", "pr_merged"):
        if validate_pull_request_lifecycle(evidence["pr_lifecycle"])["state"] != "merged":
            _fail("lifecycle:pr_not_merged")
    elif (current_state, next_state) == ("source_main_readback", "queue_enqueued"):
        if validate_queue_receipt(evidence["queue_receipt"])["state"] != "accepted":
            _fail("lifecycle:queue_not_accepted")
    elif (current_state, next_state) == ("queue_enqueued", "frontier_accepted"):
        if validate_dependency_frontier(evidence["dependency_frontier"])["frontier_state"] != "accepted":
            _fail("lifecycle:frontier_not_accepted")
    elif (current_state, next_state) == ("remote_readback", "durable_handback"):
        validate_durable_handback(evidence["durable_handback"])
    elif (current_state, next_state) == ("reservations_released", "cleanup_proven"):
        validate_cleanup_proof(evidence["cleanup_proof"])
    elif (current_state, next_state) == ("cleanup_proven", "nested_lifecycle_cleanup"):
        gates = tuple(validate_gate_verdict(item) for item in _sequence(evidence["gate_verdicts"], "transition.gate_verdicts"))
        if not gates or gates[-1]["gate_id"] != "G6" or gates[-1]["verdict"] != "pass":
            _fail("lifecycle:g6_not_passed")
        validate_cleanup_proof(evidence["cleanup_proof"])
    elif (current_state, next_state) == ("nested_lifecycle_cleanup", "closed"):
        validate_close_agent_tool_call(evidence["close_agent_tool_call"])


__all__ = [
    "CHECKPOINT_IDS",
    "CLOSE_LIFECYCLE_STATES",
    "GATE_CONTRACTS",
    "GATE_IDS",
    "LifecycleContractError",
    "PULL_REQUEST_BRANCH_RULES",
    "PR_KINDS",
    "PR_STATES",
    "SourceMainReadbackIdentity",
    "SourceProjectionGateOwnerApis",
    "TRANSACTION_STATES",
    "binding_identity",
    "frontier_key",
    "guard_transition",
    "import_decision_sufficiency_verdict",
    "materialize_close_agent_tool_call",
    "materialize_candidate_cas_receipt",
    "materialize_dependency_frontier",
    "materialize_descendant_close_receipt",
    "materialize_fresh_clone_source_projection_packet",
    "materialize_gate_verdict",
    "materialize_queue_receipt",
    "materialize_reservation_release_receipt",
    "materialize_publication_readback_receipt",
    "materialize_source_main_rebind_receipt",
    "materialize_source_projection_packet",
    "parse_decision_sufficiency_verdict",
    "pull_request_branch_table",
    "queue_once_key",
    "serialize_decision_sufficiency_verdict",
    "source_publication_identity",
    "validate_candidate_cas_receipt",
    "validate_candidate_cas_rebind_transition",
    "validate_candidate_cas_pr_transition",
    "validate_candidate_cas_transition",
    "validate_candidate_freeze_receipt",
    "validate_candidate_freeze_transition",
    "validate_candidate_review_receipt",
    "validate_candidate_review_transition",
    "validate_checkpoint_receipt",
    "validate_cleanup_proof",
    "validate_close_agent_tool_call",
    "validate_dependency_frontier",
    "validate_dependency_frontier_transition",
    "validate_descendant_close_receipt",
    "validate_durable_handback",
    "validate_evidence_identity",
    "validate_gate_verdict",
    "validate_gate_chain",
    "validate_immutable_replay",
    "validate_publication_readback_receipt",
    "validate_publication_readback_transition",
    "validate_pull_request_lifecycle",
    "validate_pull_request_transition",
    "validate_queue_receipt",
    "validate_record_binding",
    "validate_reservation_release_receipt",
    "validate_snapshot",
    "validate_source_projection_packet",
    "validate_source_main_rebind_receipt",
    "validate_update_transaction",
]
