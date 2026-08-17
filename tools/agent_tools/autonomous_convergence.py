#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Enforces finite autonomous review and implementation convergence for exact candidate epochs.
# upstream design ../../agents/skills/agent-orchestration.execution-contract.toml machine-readable convergence owner
# upstream design ../../agents/skills/agent-orchestration.md canonical convergence semantics
# downstream implementation ./task_close.py consumes the terminal closeout projection
# downstream implementation ../../tests/agent_tools/test_autonomous_convergence.py exercises transition and closeout invariants
# @dependency-end
"""Finite-state autonomous execution convergence validator."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

SCHEMA = "agent-canon.execution-time-aware-orchestration.v3"
CONTRACT_PATH = Path("agents/skills/agent-orchestration.execution-contract.toml")
CONVERGENCE_CLOSEOUT_SCHEMA = "agent-canon.review-convergence.v1"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
FINDING_ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]*-[0-9]+$")
STATE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
ACTION_CLASSES = frozenset(
    {
        "initial_review",
        "repair",
        "focused_recheck",
        "clause_resolution",
        "validation",
        "advisory",
        "epoch_reopen",
        "ship",
    }
)
EPOCH_ACTION_CLASSES = frozenset({"repair", "epoch_reopen"})
DECISION_EVIDENCE_KINDS = frozenset(
    {
        "owner_change",
        "implementation_mechanism_change",
        "validation_route_change",
        "ship_state_change",
    }
)
NEW_EPOCH_EVIDENCE_KINDS = frozenset(
    {"none", "contract_change", "reachable_behavior_change", "structural_contradiction"}
)
TERMINAL_STATES = frozenset({"active", "ship", "handoff", "non_convergent_cycle"})
REVIEW_STATUSES = frozenset({"not_started", "complete"})
VALIDATION_STATUSES = frozenset({"pending", "pass", "fail", "not_applicable"})
VALIDATION_TERMINAL_STATUSES = frozenset({"pass", "not_applicable"})


class ConvergenceContractError(ValueError):
    """Malformed or contradictory convergence state."""


@dataclass(frozen=True)
class DecisionTuple:
    owner: str
    implementation_mechanism: str
    validation_route: str
    ship_state: str


@dataclass(frozen=True)
class ConvergenceState:
    request_digest: str
    candidate_digest: str
    candidate_epoch: int
    owner: str
    implementation_mechanism: str
    validation_route: str
    review_status: str
    blocking_finding_ids: frozenset[str]
    unresolved_validation_ids: frozenset[str]
    unresolved_request_clause_ids: frozenset[str]
    selected_validation_status: str
    terminal_state: str = "active"

    def unresolved_measure(self) -> int:
        """Return μ(S) exactly as the cardinality sum owned by the contract."""
        return (
            len(self.blocking_finding_ids)
            + len(self.unresolved_validation_ids)
            + len(self.unresolved_request_clause_ids)
        )

    def epoch_fingerprint(self) -> str:
        """Identify one exact request/candidate evaluation epoch."""
        payload = {
            "request_digest": self.request_digest,
            "candidate_digest": self.candidate_digest,
        }
        return _digest_payload(payload)

    def ship_state(self) -> str:
        """Return the exact terminal-decision projection for this candidate."""
        if self.terminal_state != "active":
            return self.terminal_state
        payload = {
            "request_digest": self.request_digest,
            "candidate_digest": self.candidate_digest,
            "review_status": self.review_status,
            "blocking_finding_ids": sorted(self.blocking_finding_ids),
            "unresolved_validation_ids": sorted(self.unresolved_validation_ids),
            "unresolved_request_clause_ids": sorted(self.unresolved_request_clause_ids),
            "selected_validation_status": self.selected_validation_status,
        }
        return "active:" + _digest_payload(payload).removeprefix("sha256:")

    def decision_tuple(self) -> DecisionTuple:
        return DecisionTuple(
            self.owner,
            self.implementation_mechanism,
            self.validation_route,
            self.ship_state(),
        )

    def fingerprint(self) -> str:
        payload = {
            "request_digest": self.request_digest,
            "candidate_digest": self.candidate_digest,
            "candidate_epoch": self.candidate_epoch,
            "owner": self.owner,
            "implementation_mechanism": self.implementation_mechanism,
            "validation_route": self.validation_route,
            "review_status": self.review_status,
            "blocking_finding_ids": sorted(self.blocking_finding_ids),
            "unresolved_validation_ids": sorted(self.unresolved_validation_ids),
            "unresolved_request_clause_ids": sorted(self.unresolved_request_clause_ids),
            "selected_validation_status": self.selected_validation_status,
            "terminal_state": self.terminal_state,
        }
        return _digest_payload(payload)


@dataclass(frozen=True)
class ConvergenceAction:
    action_class: str
    target_ids: frozenset[str] = frozenset()
    affected_validation_ids: frozenset[str] = frozenset()
    decision_evidence_kinds: frozenset[str] = frozenset()
    new_epoch_evidence_kind: str = "none"
    evidence_ref: str = "none"


@dataclass(frozen=True)
class TransitionDecision:
    admitted: bool
    reason: str
    action_fingerprint: str
    prior_measure: int
    next_measure: int
    resulting_terminal_state: str


@dataclass(frozen=True)
class CloseoutProjectionDecision:
    ready: bool
    reasons: tuple[str, ...]


def _digest_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validate_digest(value: str, field: str) -> None:
    if not DIGEST_RE.fullmatch(value):
        raise ConvergenceContractError(f"{field}:must_be_sha256_digest")


def _validate_finding_ids(values: Iterable[str], field: str) -> None:
    for value in values:
        if not FINDING_ID_RE.fullmatch(value):
            raise ConvergenceContractError(f"{field}:invalid_finding_id:{value}")


def _validate_state_ids(values: Iterable[str], field: str) -> None:
    for value in values:
        if not STATE_ID_RE.fullmatch(value):
            raise ConvergenceContractError(f"{field}:invalid_id:{value}")


def validate_state(
    state: ConvergenceState,
    *,
    enforce_terminal_gate: bool = True,
) -> None:
    _validate_digest(state.request_digest, "request_digest")
    _validate_digest(state.candidate_digest, "candidate_digest")
    if state.candidate_epoch <= 0:
        raise ConvergenceContractError("candidate_epoch:must_be_positive")
    for field in ("owner", "implementation_mechanism", "validation_route"):
        if not getattr(state, field).strip():
            raise ConvergenceContractError(f"{field}:must_be_nonempty")
    if state.review_status not in REVIEW_STATUSES:
        raise ConvergenceContractError("review_status:invalid")
    if state.terminal_state not in TERMINAL_STATES:
        raise ConvergenceContractError("terminal_state:invalid")
    if state.selected_validation_status not in VALIDATION_STATUSES:
        raise ConvergenceContractError("selected_validation_status:invalid")
    _validate_finding_ids(state.blocking_finding_ids, "blocking_finding_ids")
    _validate_state_ids(
        state.unresolved_validation_ids,
        "unresolved_validation_ids",
    )
    _validate_state_ids(
        state.unresolved_request_clause_ids,
        "unresolved_request_clause_ids",
    )

    if state.review_status == "not_started" and state.blocking_finding_ids:
        raise ConvergenceContractError(
            "blocking_finding_ids:must_be_empty_before_initial_review"
        )

    if state.selected_validation_status in VALIDATION_TERMINAL_STATUSES:
        if state.unresolved_validation_ids:
            raise ConvergenceContractError(
                "unresolved_validation_ids:must_be_empty_for_terminal_validation_status"
            )
    elif not state.unresolved_validation_ids:
        raise ConvergenceContractError(
            "unresolved_validation_ids:required_for_nonterminal_validation_status"
        )

    if (
        enforce_terminal_gate
        and state.terminal_state in {"ship", "handoff"}
        and not _terminal_ready(state)
    ):
        raise ConvergenceContractError("terminal_state:terminal_gate_not_satisfied")


def action_fingerprint(
    state: ConvergenceState,
    action: ConvergenceAction,
) -> str:
    """Fingerprint exact state plus action class, excluding mutable evidence."""
    return _digest_payload(
        {
            "state": state.fingerprint(),
            "action_class": action.action_class,
        }
    )


def _changed_fields(
    previous: ConvergenceState,
    proposed: ConvergenceState,
) -> frozenset[str]:
    return frozenset(
        field.name
        for field in fields(ConvergenceState)
        if getattr(previous, field.name) != getattr(proposed, field.name)
    )


def _same_except(
    previous: ConvergenceState,
    proposed: ConvergenceState,
    allowed_changes: frozenset[str],
) -> bool:
    return _changed_fields(previous, proposed).issubset(allowed_changes)


def _decision(
    admitted: bool,
    reason: str,
    fingerprint: str,
    previous: ConvergenceState,
    proposed: ConvergenceState,
    *,
    terminal_state: str | None = None,
) -> TransitionDecision:
    return TransitionDecision(
        admitted=admitted,
        reason=reason,
        action_fingerprint=fingerprint,
        prior_measure=previous.unresolved_measure(),
        next_measure=proposed.unresolved_measure(),
        resulting_terminal_state=terminal_state or proposed.terminal_state,
    )


def _require_evidence(action: ConvergenceAction) -> bool:
    return bool(action.evidence_ref.strip()) and action.evidence_ref != "none"


def _metadata_error(
    action: ConvergenceAction,
    *,
    allow_targets: bool = False,
    allow_affected_validation: bool = False,
    allowed_decision_evidence: frozenset[str] = frozenset(),
    allowed_new_epoch_evidence: frozenset[str] = frozenset({"none"}),
) -> str | None:
    if action.target_ids and not allow_targets:
        return "action_target_ids:not_allowed"
    if action.affected_validation_ids and not allow_affected_validation:
        return "affected_validation_ids:not_allowed"
    if not action.decision_evidence_kinds.issubset(allowed_decision_evidence):
        return "decision_evidence_kinds:not_allowed_for_action"
    if action.new_epoch_evidence_kind not in allowed_new_epoch_evidence:
        return "new_epoch_evidence_kind:not_allowed_for_action"
    return None


def _expected_decision_evidence(
    previous: ConvergenceState,
    proposed: ConvergenceState,
) -> frozenset[str]:
    expected: set[str] = set()
    if previous.owner != proposed.owner:
        expected.add("owner_change")
    if previous.implementation_mechanism != proposed.implementation_mechanism:
        expected.add("implementation_mechanism_change")
    if previous.validation_route != proposed.validation_route:
        expected.add("validation_route_change")
    if previous.ship_state() != proposed.ship_state():
        expected.add("ship_state_change")
    return frozenset(expected)


def _terminal_ready(state: ConvergenceState) -> bool:
    return (
        state.review_status == "complete"
        and state.unresolved_measure() == 0
        and state.selected_validation_status in VALIDATION_TERMINAL_STATUSES
    )


def _admit_initial_review(
    previous: ConvergenceState,
    proposed: ConvergenceState,
    action: ConvergenceAction,
    fingerprint: str,
) -> TransitionDecision:
    metadata_error = _metadata_error(action)
    if metadata_error:
        return _decision(False, metadata_error, fingerprint, previous, proposed)
    if not _require_evidence(action):
        return _decision(
            False,
            "initial_review_requires_evidence",
            fingerprint,
            previous,
            proposed,
        )
    if previous.review_status != "not_started" or proposed.review_status != "complete":
        return _decision(
            False,
            "initial_review_not_once_per_epoch",
            fingerprint,
            previous,
            proposed,
        )
    if previous.blocking_finding_ids:
        return _decision(
            False,
            "initial_review_requires_empty_prior_blockers",
            fingerprint,
            previous,
            proposed,
        )
    if not _same_except(
        previous,
        proposed,
        frozenset({"review_status", "blocking_finding_ids"}),
    ):
        return _decision(
            False,
            "initial_review_may_only_classify_findings",
            fingerprint,
            previous,
            proposed,
        )
    return _decision(
        True,
        "one_initial_review_for_candidate_epoch",
        fingerprint,
        previous,
        proposed,
    )


def _admit_advisory(
    previous: ConvergenceState,
    proposed: ConvergenceState,
    action: ConvergenceAction,
    fingerprint: str,
) -> TransitionDecision:
    metadata_error = _metadata_error(action)
    if metadata_error:
        return _decision(False, metadata_error, fingerprint, previous, proposed)
    if not _require_evidence(action):
        return _decision(
            False,
            "advisory_requires_evidence",
            fingerprint,
            previous,
            proposed,
        )
    if proposed != previous:
        return _decision(
            False,
            "advisory_must_not_reopen_or_change_state",
            fingerprint,
            previous,
            proposed,
        )
    return _decision(
        True,
        "advisory_record_without_rework",
        fingerprint,
        previous,
        proposed,
    )


def _admit_repair(
    previous: ConvergenceState,
    proposed: ConvergenceState,
    action: ConvergenceAction,
    fingerprint: str,
) -> TransitionDecision:
    metadata_error = _metadata_error(
        action,
        allow_targets=True,
        allow_affected_validation=True,
        allowed_decision_evidence=frozenset({"ship_state_change"}),
        allowed_new_epoch_evidence=frozenset({"reachable_behavior_change"}),
    )
    if metadata_error:
        return _decision(False, metadata_error, fingerprint, previous, proposed)
    if not _require_evidence(action):
        return _decision(
            False,
            "repair_requires_evidence",
            fingerprint,
            previous,
            proposed,
        )
    if action.decision_evidence_kinds != frozenset({"ship_state_change"}):
        return _decision(
            False,
            "repair_requires_ship_state_change_evidence",
            fingerprint,
            previous,
            proposed,
        )
    if action.new_epoch_evidence_kind != "reachable_behavior_change":
        return _decision(
            False,
            "repair_requires_reachable_behavior_epoch_evidence",
            fingerprint,
            previous,
            proposed,
        )
    _validate_finding_ids(action.target_ids, "target_ids")
    if previous.review_status != "complete":
        return _decision(
            False,
            "repair_requires_completed_initial_review",
            fingerprint,
            previous,
            proposed,
        )
    if not action.target_ids:
        return _decision(
            False,
            "repair_requires_blocker_ids",
            fingerprint,
            previous,
            proposed,
        )
    if not action.target_ids.issubset(previous.blocking_finding_ids):
        return _decision(
            False,
            "repair_must_target_existing_blockers",
            fingerprint,
            previous,
            proposed,
        )
    if not _same_except(
        previous,
        proposed,
        frozenset(
            {
                "candidate_digest",
                "candidate_epoch",
                "unresolved_validation_ids",
                "selected_validation_status",
            }
        ),
    ):
        return _decision(
            False,
            "repair_may_only_change_candidate_epoch_and_affected_validation",
            fingerprint,
            previous,
            proposed,
        )
    if proposed.blocking_finding_ids != previous.blocking_finding_ids:
        return _decision(
            False,
            "repair_cannot_close_blocker_before_focused_recheck",
            fingerprint,
            previous,
            proposed,
        )
    expected_validation_ids = (
        previous.unresolved_validation_ids | action.affected_validation_ids
    )
    if proposed.unresolved_validation_ids != expected_validation_ids:
        return _decision(
            False,
            "repair_validation_reopen_must_equal_affected_ids",
            fingerprint,
            previous,
            proposed,
        )
    if previous.selected_validation_status == "not_applicable":
        if (
            action.affected_validation_ids
            or proposed.selected_validation_status != "not_applicable"
        ):
            return _decision(
                False,
                "not_applicable_validation_cannot_be_implicitly_reopened",
                fingerprint,
                previous,
                proposed,
            )
    else:
        if not action.affected_validation_ids:
            return _decision(
                False,
                "repair_requires_affected_validation_ids",
                fingerprint,
                previous,
                proposed,
            )
        if proposed.selected_validation_status != "pending":
            return _decision(
                False,
                "repair_must_reset_selected_validation_to_pending",
                fingerprint,
                previous,
                proposed,
            )
    if _expected_decision_evidence(previous, proposed) != frozenset(
        {"ship_state_change"}
    ):
        return _decision(
            False,
            "repair_evidence_does_not_match_decision_change",
            fingerprint,
            previous,
            proposed,
        )
    return _decision(
        True,
        "typed_candidate_epoch_repair",
        fingerprint,
        previous,
        proposed,
    )


def _admit_focused_recheck(
    previous: ConvergenceState,
    proposed: ConvergenceState,
    action: ConvergenceAction,
    fingerprint: str,
) -> TransitionDecision:
    metadata_error = _metadata_error(action, allow_targets=True)
    if metadata_error:
        return _decision(False, metadata_error, fingerprint, previous, proposed)
    if not _require_evidence(action):
        return _decision(
            False,
            "focused_recheck_requires_evidence",
            fingerprint,
            previous,
            proposed,
        )
    _validate_finding_ids(action.target_ids, "target_ids")
    if previous.review_status != "complete":
        return _decision(
            False,
            "focused_recheck_requires_completed_initial_review",
            fingerprint,
            previous,
            proposed,
        )
    if not action.target_ids:
        return _decision(
            False,
            "focused_recheck_requires_blocker_ids",
            fingerprint,
            previous,
            proposed,
        )
    if not action.target_ids.issubset(previous.blocking_finding_ids):
        return _decision(
            False,
            "focused_recheck_must_target_existing_blockers",
            fingerprint,
            previous,
            proposed,
        )
    if not _same_except(
        previous,
        proposed,
        frozenset({"blocking_finding_ids"}),
    ):
        return _decision(
            False,
            "focused_recheck_may_only_change_targeted_blockers",
            fingerprint,
            previous,
            proposed,
        )
    added = proposed.blocking_finding_ids - previous.blocking_finding_ids
    removed = previous.blocking_finding_ids - proposed.blocking_finding_ids
    if added:
        return _decision(
            False,
            "new_blocker_requires_new_epoch_evidence",
            fingerprint,
            previous,
            proposed,
        )
    if not removed:
        return _decision(
            False,
            "focused_recheck_requires_strict_measure_decrease",
            fingerprint,
            previous,
            proposed,
        )
    if not removed.issubset(action.target_ids):
        return _decision(
            False,
            "focused_recheck_closed_unassigned_blocker",
            fingerprint,
            previous,
            proposed,
        )
    return _decision(
        True,
        "strict_unresolved_measure_decrease",
        fingerprint,
        previous,
        proposed,
    )


def _admit_clause_resolution(
    previous: ConvergenceState,
    proposed: ConvergenceState,
    action: ConvergenceAction,
    fingerprint: str,
) -> TransitionDecision:
    metadata_error = _metadata_error(action, allow_targets=True)
    if metadata_error:
        return _decision(False, metadata_error, fingerprint, previous, proposed)
    if not _require_evidence(action):
        return _decision(
            False,
            "clause_resolution_requires_evidence",
            fingerprint,
            previous,
            proposed,
        )
    if not action.target_ids:
        return _decision(
            False,
            "clause_resolution_requires_clause_ids",
            fingerprint,
            previous,
            proposed,
        )
    if not action.target_ids.issubset(previous.unresolved_request_clause_ids):
        return _decision(
            False,
            "clause_resolution_must_target_unresolved_clauses",
            fingerprint,
            previous,
            proposed,
        )
    if not _same_except(
        previous,
        proposed,
        frozenset({"unresolved_request_clause_ids"}),
    ):
        return _decision(
            False,
            "clause_resolution_may_only_change_targeted_clauses",
            fingerprint,
            previous,
            proposed,
        )
    added = (
        proposed.unresolved_request_clause_ids - previous.unresolved_request_clause_ids
    )
    removed = (
        previous.unresolved_request_clause_ids - proposed.unresolved_request_clause_ids
    )
    if added or not removed or not removed.issubset(action.target_ids):
        return _decision(
            False,
            "clause_resolution_requires_targeted_strict_decrease",
            fingerprint,
            previous,
            proposed,
        )
    return _decision(
        True,
        "strict_unresolved_measure_decrease",
        fingerprint,
        previous,
        proposed,
    )


def _admit_validation(
    previous: ConvergenceState,
    proposed: ConvergenceState,
    action: ConvergenceAction,
    fingerprint: str,
) -> TransitionDecision:
    metadata_error = _metadata_error(
        action,
        allow_targets=True,
        allowed_decision_evidence=frozenset({"ship_state_change"}),
    )
    if metadata_error:
        return _decision(False, metadata_error, fingerprint, previous, proposed)
    if not _require_evidence(action):
        return _decision(
            False,
            "validation_requires_evidence",
            fingerprint,
            previous,
            proposed,
        )
    if previous.review_status != "complete":
        return _decision(
            False,
            "validation_requires_completed_initial_review",
            fingerprint,
            previous,
            proposed,
        )
    if not action.target_ids:
        return _decision(
            False,
            "validation_requires_validation_ids",
            fingerprint,
            previous,
            proposed,
        )
    if not _same_except(
        previous,
        proposed,
        frozenset({"unresolved_validation_ids", "selected_validation_status"}),
    ):
        return _decision(
            False,
            "validation_may_only_change_affected_validation_state",
            fingerprint,
            previous,
            proposed,
        )
    changed_ids = (
        previous.unresolved_validation_ids ^ proposed.unresolved_validation_ids
    )
    known_ids = previous.unresolved_validation_ids | proposed.unresolved_validation_ids
    if not action.target_ids.issubset(known_ids):
        return _decision(
            False,
            "validation_targets_must_name_known_validation_ids",
            fingerprint,
            previous,
            proposed,
        )
    if not changed_ids.issubset(action.target_ids):
        return _decision(
            False,
            "validation_reopen_or_close_exceeded_target_ids",
            fingerprint,
            previous,
            proposed,
        )

    expected_evidence = _expected_decision_evidence(previous, proposed)
    prior_measure = previous.unresolved_measure()
    next_measure = proposed.unresolved_measure()
    if next_measure < prior_measure:
        if action.decision_evidence_kinds not in (
            frozenset(),
            expected_evidence,
        ):
            return _decision(
                False,
                "validation_decision_evidence_does_not_match_change",
                fingerprint,
                previous,
                proposed,
            )
        return _decision(
            True,
            "strict_unresolved_measure_decrease",
            fingerprint,
            previous,
            proposed,
        )
    if (
        expected_evidence == frozenset({"ship_state_change"})
        and action.decision_evidence_kinds == expected_evidence
    ):
        return _decision(
            True,
            "new_decision_evidence",
            fingerprint,
            previous,
            proposed,
        )
    return _decision(
        False,
        "validation_requires_decision_change_or_strict_measure_decrease",
        fingerprint,
        previous,
        proposed,
    )


def _admit_epoch_reopen(
    previous: ConvergenceState,
    proposed: ConvergenceState,
    action: ConvergenceAction,
    fingerprint: str,
) -> TransitionDecision:
    metadata_error = _metadata_error(
        action,
        allowed_decision_evidence=DECISION_EVIDENCE_KINDS,
        allowed_new_epoch_evidence=NEW_EPOCH_EVIDENCE_KINDS - {"none"},
    )
    if metadata_error:
        return _decision(False, metadata_error, fingerprint, previous, proposed)
    if not _require_evidence(action):
        return _decision(
            False,
            "new_epoch_requires_evidence",
            fingerprint,
            previous,
            proposed,
        )
    if (
        proposed.review_status != "not_started"
        or proposed.blocking_finding_ids
        or proposed.terminal_state != "active"
    ):
        return _decision(
            False,
            "new_epoch_requires_unreviewed_reset_state",
            fingerprint,
            previous,
            proposed,
        )

    reason = action.new_epoch_evidence_kind
    if reason == "contract_change":
        reason_supported = previous.request_digest != proposed.request_digest
    elif reason == "reachable_behavior_change":
        reason_supported = previous.candidate_digest != proposed.candidate_digest
    else:
        reason_supported = (
            previous.candidate_digest != proposed.candidate_digest
            and bool(
                _changed_fields(previous, proposed)
                & frozenset(
                    {
                        "owner",
                        "implementation_mechanism",
                        "validation_route",
                    }
                )
            )
        )
    if not reason_supported:
        return _decision(
            False,
            "new_epoch_reason_not_supported_by_state_change",
            fingerprint,
            previous,
            proposed,
        )

    expected_evidence = _expected_decision_evidence(previous, proposed)
    if not expected_evidence or action.decision_evidence_kinds != expected_evidence:
        return _decision(
            False,
            "new_epoch_decision_evidence_does_not_match_change",
            fingerprint,
            previous,
            proposed,
        )
    return _decision(
        True,
        "typed_new_epoch_evidence",
        fingerprint,
        previous,
        proposed,
    )


def _admit_ship(
    previous: ConvergenceState,
    proposed: ConvergenceState,
    action: ConvergenceAction,
    fingerprint: str,
) -> TransitionDecision:
    metadata_error = _metadata_error(
        action,
        allowed_decision_evidence=frozenset({"ship_state_change"}),
    )
    if metadata_error:
        return _decision(False, metadata_error, fingerprint, previous, proposed)
    if not _require_evidence(action):
        return _decision(
            False,
            "ship_requires_evidence",
            fingerprint,
            previous,
            proposed,
        )
    if action.decision_evidence_kinds != frozenset({"ship_state_change"}):
        return _decision(
            False,
            "ship_requires_ship_state_change_evidence",
            fingerprint,
            previous,
            proposed,
        )
    if not _same_except(
        previous,
        proposed,
        frozenset({"terminal_state"}),
    ):
        return _decision(
            False,
            "ship_may_only_change_terminal_state",
            fingerprint,
            previous,
            proposed,
        )
    if proposed.terminal_state not in {"ship", "handoff"}:
        return _decision(
            False,
            "ship_requires_terminal_target",
            fingerprint,
            previous,
            proposed,
        )
    if not _terminal_ready(previous):
        return _decision(
            False,
            "terminal_gate_not_satisfied",
            fingerprint,
            previous,
            proposed,
        )
    if _expected_decision_evidence(previous, proposed) != frozenset(
        {"ship_state_change"}
    ):
        return _decision(
            False,
            "ship_evidence_does_not_match_decision_change",
            fingerprint,
            previous,
            proposed,
        )
    return _decision(
        True,
        "terminal_zero_measure",
        fingerprint,
        previous,
        proposed,
    )


def admit_transition(
    previous: ConvergenceState,
    proposed: ConvergenceState,
    action: ConvergenceAction,
    *,
    seen_action_fingerprints: Iterable[str] = (),
    seen_epoch_fingerprints: Iterable[str] = (),
) -> TransitionDecision:
    """Admit typed transitions and stop repeated state/action or epoch cycles."""
    validate_state(previous)
    validate_state(proposed, enforce_terminal_gate=False)
    if action.action_class not in ACTION_CLASSES:
        raise ConvergenceContractError("action_class:invalid")
    if not action.decision_evidence_kinds.issubset(DECISION_EVIDENCE_KINDS):
        raise ConvergenceContractError("decision_evidence_kinds:invalid")
    if action.new_epoch_evidence_kind not in NEW_EPOCH_EVIDENCE_KINDS:
        raise ConvergenceContractError("new_epoch_evidence_kind:invalid")
    _validate_state_ids(action.target_ids, "target_ids")
    _validate_state_ids(
        action.affected_validation_ids,
        "affected_validation_ids",
    )

    fingerprint = action_fingerprint(previous, action)
    if previous.terminal_state != "active":
        return _decision(
            False,
            "terminal_state_is_absorbing",
            fingerprint,
            previous,
            proposed,
        )

    seen_actions = frozenset(seen_action_fingerprints)
    for item in seen_actions:
        _validate_digest(item, "seen_action_fingerprint")
    if fingerprint in seen_actions:
        return _decision(
            False,
            "non_convergent_cycle",
            fingerprint,
            previous,
            proposed,
            terminal_state="non_convergent_cycle",
        )
    if proposed.terminal_state == "non_convergent_cycle":
        return _decision(
            False,
            "non_convergent_cycle_requires_repeated_state_action",
            fingerprint,
            previous,
            proposed,
        )

    seen_epochs = frozenset(seen_epoch_fingerprints)
    for item in seen_epochs:
        _validate_digest(item, "seen_epoch_fingerprint")
    if action.action_class in EPOCH_ACTION_CLASSES:
        if proposed.candidate_epoch != previous.candidate_epoch + 1:
            return _decision(
                False,
                "candidate_epoch_transition_must_increment_once",
                fingerprint,
                previous,
                proposed,
            )
        if proposed.epoch_fingerprint() == previous.epoch_fingerprint():
            return _decision(
                False,
                "candidate_epoch_requires_new_identity",
                fingerprint,
                previous,
                proposed,
            )
        if proposed.epoch_fingerprint() in seen_epochs:
            return _decision(
                False,
                "non_convergent_cycle",
                fingerprint,
                previous,
                proposed,
                terminal_state="non_convergent_cycle",
            )
    else:
        if proposed.candidate_epoch != previous.candidate_epoch:
            return _decision(
                False,
                "candidate_epoch_change_requires_epoch_action",
                fingerprint,
                previous,
                proposed,
            )
        if proposed.request_digest != previous.request_digest:
            return _decision(
                False,
                "request_digest_change_requires_epoch_reopen",
                fingerprint,
                previous,
                proposed,
            )
        if proposed.candidate_digest != previous.candidate_digest:
            return _decision(
                False,
                "candidate_digest_change_requires_epoch_action",
                fingerprint,
                previous,
                proposed,
            )
    if action.action_class != "ship" and proposed.terminal_state != "active":
        return _decision(
            False,
            "terminal_state_change_requires_ship",
            fingerprint,
            previous,
            proposed,
        )

    handlers = {
        "initial_review": _admit_initial_review,
        "repair": _admit_repair,
        "focused_recheck": _admit_focused_recheck,
        "clause_resolution": _admit_clause_resolution,
        "validation": _admit_validation,
        "advisory": _admit_advisory,
        "epoch_reopen": _admit_epoch_reopen,
        "ship": _admit_ship,
    }
    return handlers[action.action_class](
        previous,
        proposed,
        action,
        fingerprint,
    )


def _parse_ids(
    value: str,
    field: str,
    *,
    findings: bool = False,
) -> frozenset[str]:
    normalized = value.strip()
    if normalized in {"", "none", "not_applicable"}:
        return frozenset()
    values = frozenset(item.strip() for item in normalized.split(",") if item.strip())
    if findings:
        _validate_finding_ids(values, field)
    else:
        _validate_state_ids(values, field)
    return values


def _parse_positive_int(
    value: str,
    field: str,
    *,
    allow_zero: bool = False,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConvergenceContractError(f"{field}:must_be_integer") from exc
    minimum = 0 if allow_zero else 1
    if parsed < minimum:
        raise ConvergenceContractError(f"{field}:out_of_range")
    return parsed


def validate_closeout_projection(
    projection: Mapping[str, str],
) -> CloseoutProjectionDecision:
    """Validate the terminal review-convergence projection in closeout_gate.md."""
    required = (
        "convergence_schema",
        "candidate_epoch",
        "candidate_digest",
        "initial_review_status",
        "initial_blocking_finding_ids",
        "focused_recheck_finding_ids",
        "open_blocking_finding_ids",
        "advisory_finding_ids",
        "unresolved_request_clause_ids",
        "unresolved_validation_ids",
        "unresolved_measure_initial",
        "unresolved_measure_final",
        "selected_validation_status",
        "same_state_action_repeated",
        "terminal_state",
        "new_epoch_reason",
    )
    reasons: list[str] = []
    missing = [field for field in required if not projection.get(field, "").strip()]
    if missing:
        return CloseoutProjectionDecision(
            False,
            tuple(f"missing:{field}" for field in missing),
        )
    try:
        if projection["convergence_schema"] != CONVERGENCE_CLOSEOUT_SCHEMA:
            reasons.append("convergence_schema:mismatch")
        _parse_positive_int(projection["candidate_epoch"], "candidate_epoch")
        _validate_digest(projection["candidate_digest"], "candidate_digest")
        if projection["initial_review_status"] != "complete":
            reasons.append("initial_review_status:not_complete")
        initial_blockers = _parse_ids(
            projection["initial_blocking_finding_ids"],
            "initial_blocking_finding_ids",
            findings=True,
        )
        focused = _parse_ids(
            projection["focused_recheck_finding_ids"],
            "focused_recheck_finding_ids",
            findings=True,
        )
        open_blockers = _parse_ids(
            projection["open_blocking_finding_ids"],
            "open_blocking_finding_ids",
            findings=True,
        )
        _parse_ids(
            projection["advisory_finding_ids"],
            "advisory_finding_ids",
            findings=True,
        )
        unresolved_clauses = _parse_ids(
            projection["unresolved_request_clause_ids"],
            "unresolved_request_clause_ids",
        )
        unresolved_validation = _parse_ids(
            projection["unresolved_validation_ids"],
            "unresolved_validation_ids",
        )
        initial_measure = _parse_positive_int(
            projection["unresolved_measure_initial"],
            "unresolved_measure_initial",
            allow_zero=True,
        )
        final_measure = _parse_positive_int(
            projection["unresolved_measure_final"],
            "unresolved_measure_final",
            allow_zero=True,
        )
        computed_final = (
            len(open_blockers) + len(unresolved_clauses) + len(unresolved_validation)
        )
        if final_measure != computed_final:
            reasons.append("unresolved_measure_final:mismatch")
        if final_measure != 0:
            reasons.append("unresolved_measure_final:not_zero")
        if initial_measure < len(initial_blockers):
            reasons.append("unresolved_measure_initial:below_initial_blockers")
        if final_measure > initial_measure:
            reasons.append("unresolved_measure:not_monotone")
        if not focused.issubset(initial_blockers):
            reasons.append("focused_recheck:not_subset_of_initial_blockers")
        if not open_blockers.issubset(initial_blockers):
            reasons.append("open_blocker:not_stable_in_epoch")
        closed_initial = initial_blockers - open_blockers
        if not closed_initial.issubset(focused):
            reasons.append("closed_blocker:missing_focused_recheck")
        if focused and final_measure >= initial_measure:
            reasons.append("focused_recheck:did_not_reduce_measure")
        if open_blockers:
            reasons.append("open_blocking_findings:nonempty")
        if unresolved_clauses:
            reasons.append("unresolved_request_clauses:nonempty")
        if unresolved_validation:
            reasons.append("unresolved_validation:nonempty")
        if projection["selected_validation_status"] not in VALIDATION_TERMINAL_STATUSES:
            reasons.append("selected_validation_status:not_terminal")
        if projection["same_state_action_repeated"] != "no":
            reasons.append("same_state_action_repeated")
        if projection["terminal_state"] not in {"ship", "handoff"}:
            reasons.append("terminal_state:not_terminal")
        if projection["new_epoch_reason"] not in NEW_EPOCH_EVIDENCE_KINDS:
            reasons.append("new_epoch_reason:invalid")
    except ConvergenceContractError as exc:
        reasons.append(str(exc))
    return CloseoutProjectionDecision(
        not reasons,
        tuple(dict.fromkeys(reasons)),
    )


EXPECTED_CONVERGENCE = {
    "state_fields": [
        "request_digest",
        "candidate_digest",
        "candidate_epoch",
        "owner",
        "implementation_mechanism",
        "validation_route",
        "review_status",
        "blocking_finding_ids",
        "unresolved_validation_ids",
        "unresolved_request_clause_ids",
        "selected_validation_status",
        "terminal_state",
    ],
    "action_classes": [
        "initial_review",
        "repair",
        "focused_recheck",
        "clause_resolution",
        "validation",
        "advisory",
        "epoch_reopen",
        "ship",
    ],
    "decision_evidence_kinds": [
        "owner_change",
        "implementation_mechanism_change",
        "validation_route_change",
        "ship_state_change",
    ],
    "new_epoch_evidence_kinds": [
        "contract_change",
        "reachable_behavior_change",
        "structural_contradiction",
    ],
    "action_admission": [
        "one_initial_review_for_candidate_epoch",
        "typed_candidate_epoch_repair",
        "strict_unresolved_measure_decrease",
        "typed_new_epoch_evidence",
        "advisory_record_without_rework",
        "terminal_zero_measure",
    ],
    "action_fingerprint": "state_fingerprint_plus_action_class",
    "epoch_fingerprint": "request_digest_plus_candidate_digest",
    "repair_scope": "next_candidate_epoch_assigned_blockers_and_affected_validation_ids_only",
    "focused_recheck_scope": "targeted_blocker_ids_only",
    "validation_reopen_scope": "affected_validation_ids_only",
    "terminal_conditions": [
        "zero_open_blocking_findings",
        "zero_unresolved_request_clauses",
        "zero_unresolved_validation_ids",
        "selected_validation_pass_or_not_applicable",
    ],
    "cycle_stop": "non_convergent_cycle",
}


EXPECTED_INVARIANTS = {
    "dag": "complete_dependency_dag_with_owner_and_consumer_closure",
    "objective": "lexicographic_completeness_correctness_then_decision_relevant_total_work_then_makespan",
    "dispatch": "all_non_conflicting_admissible_ready_nodes",
    "wait": "only_when_useful_ready_set_is_empty",
    "evidence": "warm_context_reuse_and_affected_evidence_only_invalidation",
    "review": "one_initial_review_per_candidate_epoch_then_focused_recheck",
    "candidate_epoch": "exact_request_candidate_identity_with_no_repeated_epoch",
    "convergence": "state_action_class_or_epoch_cycle_else_strict_measure_or_typed_decision_evidence",
    "terminal": "zero_blockers_clauses_and_validations_with_selected_validation_pass",
}


def validate_contract(root: Path) -> tuple[str, ...]:
    path = root / CONTRACT_PATH
    try:
        contract = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return (f"contract_unreadable:{exc}",)
    reasons: list[str] = []
    if contract.get("schema") != SCHEMA:
        reasons.append("schema:mismatch")
    if contract.get("convergence") != EXPECTED_CONVERGENCE:
        reasons.append("convergence:mismatch")
    if contract.get("invariants") != EXPECTED_INVARIANTS:
        reasons.append("invariants:mismatch")
    return tuple(reasons)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--check-contract", action="store_true")
    args = parser.parse_args(argv)
    reasons = validate_contract(args.root.resolve())
    if reasons:
        for reason in reasons:
            print(f"AUTONOMOUS_CONVERGENCE_FINDING={reason}")
        return 1
    print("AUTONOMOUS_CONVERGENCE=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
