#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Enforces finite autonomous review and implementation convergence for one candidate epoch.
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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

SCHEMA = "agent-canon.execution-time-aware-orchestration.v2"
CONTRACT_PATH = Path("agents/skills/agent-orchestration.execution-contract.toml")
CONVERGENCE_CLOSEOUT_SCHEMA = "agent-canon.review-convergence.v1"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
FINDING_ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]*-[0-9]+$")
ACTION_CLASSES = frozenset(
    {"initial_review", "repair", "focused_recheck", "validation", "advisory", "ship"}
)
DECISION_EVIDENCE_KINDS = frozenset(
    {
        "none",
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
VALIDATION_TERMINAL_STATUSES = frozenset({"pass", "not_applicable"})


class ConvergenceContractError(ValueError):
    """Malformed or contradictory convergence state."""


@dataclass(frozen=True)
class DecisionTuple:
    owner: str
    implementation_mechanism: str
    validation_route: str
    terminal_state: str


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
    terminal_state: str = "active"

    def unresolved_measure(self) -> int:
        return (
            len(self.blocking_finding_ids)
            + len(self.unresolved_validation_ids)
            + len(self.unresolved_request_clause_ids)
        )

    def decision_tuple(self) -> DecisionTuple:
        return DecisionTuple(
            self.owner,
            self.implementation_mechanism,
            self.validation_route,
            self.terminal_state,
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
            "terminal_state": self.terminal_state,
        }
        return "sha256:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True)
class ConvergenceAction:
    action_class: str
    target_ids: frozenset[str] = frozenset()
    decision_evidence_kind: str = "none"
    new_epoch_evidence_kind: str = "none"
    evidence_ref: str = "none"


@dataclass(frozen=True)
class TransitionDecision:
    admitted: bool
    reason: str
    action_fingerprint: str
    prior_measure: int
    next_measure: int


@dataclass(frozen=True)
class CloseoutProjectionDecision:
    ready: bool
    reasons: tuple[str, ...]


def _validate_digest(value: str, field: str) -> None:
    if not DIGEST_RE.fullmatch(value):
        raise ConvergenceContractError(f"{field}:must_be_sha256_digest")


def _validate_finding_ids(values: Iterable[str], field: str) -> None:
    for value in values:
        if not FINDING_ID_RE.fullmatch(value):
            raise ConvergenceContractError(f"{field}:invalid_finding_id:{value}")


def validate_state(state: ConvergenceState) -> None:
    _validate_digest(state.request_digest, "request_digest")
    _validate_digest(state.candidate_digest, "candidate_digest")
    if state.candidate_epoch <= 0:
        raise ConvergenceContractError("candidate_epoch:must_be_positive")
    for field in ("owner", "implementation_mechanism", "validation_route", "review_status"):
        if not getattr(state, field).strip():
            raise ConvergenceContractError(f"{field}:must_be_nonempty")
    if state.terminal_state not in TERMINAL_STATES:
        raise ConvergenceContractError("terminal_state:invalid")
    _validate_finding_ids(state.blocking_finding_ids, "blocking_finding_ids")


def action_fingerprint(state: ConvergenceState, action: ConvergenceAction) -> str:
    payload = {
        "state": state.fingerprint(),
        "action_class": action.action_class,
        "target_ids": sorted(action.target_ids),
        "decision_evidence_kind": action.decision_evidence_kind,
        "new_epoch_evidence_kind": action.new_epoch_evidence_kind,
        "evidence_ref": action.evidence_ref,
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def admit_transition(
    previous: ConvergenceState,
    proposed: ConvergenceState,
    action: ConvergenceAction,
    *,
    seen_action_fingerprints: Iterable[str] = (),
) -> TransitionDecision:
    """Admit only decision-changing, measure-decreasing, or typed epoch transitions."""
    validate_state(previous)
    validate_state(proposed)
    if action.action_class not in ACTION_CLASSES:
        raise ConvergenceContractError("action_class:invalid")
    if action.decision_evidence_kind not in DECISION_EVIDENCE_KINDS:
        raise ConvergenceContractError("decision_evidence_kind:invalid")
    if action.new_epoch_evidence_kind not in NEW_EPOCH_EVIDENCE_KINDS:
        raise ConvergenceContractError("new_epoch_evidence_kind:invalid")
    _validate_finding_ids(action.target_ids, "target_ids")

    fingerprint = action_fingerprint(previous, action)
    prior_measure = previous.unresolved_measure()
    next_measure = proposed.unresolved_measure()
    if fingerprint in set(seen_action_fingerprints):
        return TransitionDecision(
            False,
            "non_convergent_cycle",
            fingerprint,
            prior_measure,
            next_measure,
        )

    same_epoch = proposed.candidate_epoch == previous.candidate_epoch
    next_epoch = proposed.candidate_epoch == previous.candidate_epoch + 1
    if not same_epoch and not next_epoch:
        return TransitionDecision(
            False, "candidate_epoch_must_stay_or_increment_once", fingerprint, prior_measure, next_measure
        )
    if next_epoch:
        if action.new_epoch_evidence_kind == "none":
            return TransitionDecision(
                False, "new_epoch_requires_typed_evidence", fingerprint, prior_measure, next_measure
            )
        if proposed.candidate_digest == previous.candidate_digest:
            return TransitionDecision(
                False, "new_epoch_requires_new_candidate_digest", fingerprint, prior_measure, next_measure
            )
        return TransitionDecision(
            True, "typed_new_epoch_evidence", fingerprint, prior_measure, next_measure
        )

    if proposed.request_digest != previous.request_digest:
        return TransitionDecision(
            False, "request_digest_change_requires_new_epoch", fingerprint, prior_measure, next_measure
        )
    if proposed.candidate_digest != previous.candidate_digest:
        return TransitionDecision(
            False, "candidate_digest_change_requires_new_epoch", fingerprint, prior_measure, next_measure
        )

    if action.action_class == "initial_review":
        if previous.review_status != "not_started" or proposed.review_status != "complete":
            return TransitionDecision(
                False, "initial_review_not_once_per_epoch", fingerprint, prior_measure, next_measure
            )
        return TransitionDecision(
            True, "one_initial_review_for_candidate_epoch", fingerprint, prior_measure, next_measure
        )

    if action.action_class == "advisory":
        if proposed != previous:
            return TransitionDecision(
                False, "advisory_must_not_reopen_or_change_state", fingerprint, prior_measure, next_measure
            )
        return TransitionDecision(
            True, "advisory_record_without_rework", fingerprint, prior_measure, next_measure
        )

    if action.action_class in {"repair", "focused_recheck"}:
        if not action.target_ids:
            return TransitionDecision(
                False, "repair_or_recheck_requires_blocker_ids", fingerprint, prior_measure, next_measure
            )
        if not action.target_ids.issubset(previous.blocking_finding_ids):
            return TransitionDecision(
                False, "repair_or_recheck_must_target_existing_blockers", fingerprint, prior_measure, next_measure
            )
        added = proposed.blocking_finding_ids - previous.blocking_finding_ids
        if added:
            return TransitionDecision(
                False, "new_blocker_requires_new_epoch_evidence", fingerprint, prior_measure, next_measure
            )

    decision_changed = proposed.decision_tuple() != previous.decision_tuple()
    if decision_changed and action.decision_evidence_kind == "none":
        return TransitionDecision(
            False, "decision_change_requires_typed_evidence", fingerprint, prior_measure, next_measure
        )
    if decision_changed:
        return TransitionDecision(
            True, "new_decision_evidence", fingerprint, prior_measure, next_measure
        )
    if next_measure < prior_measure:
        return TransitionDecision(
            True, "strict_unresolved_measure_decrease", fingerprint, prior_measure, next_measure
        )

    if action.action_class == "ship":
        terminal_ready = (
            proposed.terminal_state in {"ship", "handoff"}
            and not proposed.blocking_finding_ids
            and not proposed.unresolved_validation_ids
            and not proposed.unresolved_request_clause_ids
        )
        if terminal_ready:
            return TransitionDecision(
                True, "terminal_zero_measure", fingerprint, prior_measure, next_measure
            )
    return TransitionDecision(
        False, "no_decision_change_or_measure_decrease", fingerprint, prior_measure, next_measure
    )


def _parse_ids(value: str, field: str, *, findings: bool = False) -> frozenset[str]:
    normalized = value.strip()
    if normalized in {"", "none", "not_applicable"}:
        return frozenset()
    values = frozenset(item.strip() for item in normalized.split(",") if item.strip())
    if findings:
        _validate_finding_ids(values, field)
    return values


def _parse_positive_int(value: str, field: str, *, allow_zero: bool = False) -> int:
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
    """Validate one terminal review-convergence projection from closeout_gate.md."""
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
            False, tuple(f"missing:{field}" for field in missing)
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
        if final_measure > initial_measure:
            reasons.append("unresolved_measure:not_monotone")
        if focused and not focused.issubset(initial_blockers):
            reasons.append("focused_recheck:not_subset_of_initial_blockers")
        if open_blockers - initial_blockers:
            reasons.append("open_blocker:not_stable_in_epoch")
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
        if projection["new_epoch_reason"] not in {
            "none",
            "contract_change",
            "reachable_behavior_change",
            "structural_contradiction",
        }:
            reasons.append("new_epoch_reason:invalid")
    except ConvergenceContractError as exc:
        reasons.append(str(exc))
    return CloseoutProjectionDecision(not reasons, tuple(dict.fromkeys(reasons)))


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
        "terminal_state",
    ],
    "action_classes": [
        "initial_review",
        "repair",
        "focused_recheck",
        "validation",
        "advisory",
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
        "new_decision_evidence",
        "strict_unresolved_measure_decrease",
        "typed_new_epoch_evidence",
        "advisory_record_without_rework",
    ],
    "terminal_conditions": [
        "zero_open_blocking_findings",
        "zero_unresolved_request_clauses",
        "selected_validation_pass_or_not_applicable",
    ],
    "cycle_stop": "non_convergent_cycle",
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
    invariants = contract.get("invariants")
    if not isinstance(invariants, dict):
        reasons.append("invariants:missing")
    else:
        if invariants.get("convergence") != (
            "strict_unresolved_measure_decrease_or_new_decision_evidence"
        ):
            reasons.append("invariants.convergence:mismatch")
        if invariants.get("terminal") != (
            "zero_blockers_and_request_clauses_with_selected_validation_pass"
        ):
            reasons.append("invariants.terminal:mismatch")
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
