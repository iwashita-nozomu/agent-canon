"""Tests for finite autonomous review and implementation convergence."""

# @dependency-start
# contract test
# responsibility Tests the autonomous convergence state transition and closeout projection.
# upstream design ../../agents/skills/agent-orchestration.execution-contract.toml machine-readable owner
# upstream implementation ../../tools/agent_tools/autonomous_convergence.py transition validator
# @dependency-end

from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from autonomous_convergence import (  # noqa: E402
    CONVERGENCE_CLOSEOUT_SCHEMA,
    ConvergenceAction,
    ConvergenceState,
    admit_transition,
    validate_closeout_projection,
    validate_contract,
)


def digest(char: str) -> str:
    return "sha256:" + char * 64


class AutonomousConvergenceTests(unittest.TestCase):
    def base_state(self) -> ConvergenceState:
        return ConvergenceState(
            request_digest=digest("1"),
            candidate_digest=digest("2"),
            candidate_epoch=1,
            owner="owner",
            implementation_mechanism="mechanism",
            validation_route="targeted",
            review_status="not_started",
            blocking_finding_ids=frozenset(),
            unresolved_validation_ids=frozenset({"VAL-1"}),
            unresolved_request_clause_ids=frozenset({"REQ-1"}),
        )

    def test_contract_projection_matches_runtime(self) -> None:
        self.assertEqual(validate_contract(PROJECT_ROOT), ())

    def test_initial_review_is_admitted_once(self) -> None:
        before = self.base_state()
        after = replace(
            before,
            review_status="complete",
            blocking_finding_ids=frozenset({"BLOCK-1"}),
        )
        decision = admit_transition(
            before,
            after,
            ConvergenceAction("initial_review"),
        )
        self.assertTrue(decision.admitted)
        repeated = admit_transition(
            after,
            after,
            ConvergenceAction("initial_review"),
        )
        self.assertFalse(repeated.admitted)
        self.assertEqual(repeated.reason, "initial_review_not_once_per_epoch")

    def test_same_state_same_action_is_typed_cycle_stop(self) -> None:
        state = replace(self.base_state(), review_status="complete")
        action = ConvergenceAction("validation", evidence_ref="validation:1")
        first = admit_transition(state, state, action)
        repeated = admit_transition(
            state,
            state,
            action,
            seen_action_fingerprints={first.action_fingerprint},
        )
        self.assertFalse(repeated.admitted)
        self.assertEqual(repeated.reason, "non_convergent_cycle")

    def test_advisory_never_reopens_implementation(self) -> None:
        state = replace(self.base_state(), review_status="complete")
        decision = admit_transition(
            state,
            state,
            ConvergenceAction("advisory", evidence_ref="note:1"),
        )
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.reason, "advisory_record_without_rework")

    def test_focused_recheck_closes_only_stable_blocker_ids(self) -> None:
        before = replace(
            self.base_state(),
            review_status="complete",
            blocking_finding_ids=frozenset({"BLOCK-1", "BLOCK-2"}),
        )
        after = replace(
            before,
            blocking_finding_ids=frozenset({"BLOCK-2"}),
        )
        decision = admit_transition(
            before,
            after,
            ConvergenceAction(
                "focused_recheck",
                target_ids=frozenset({"BLOCK-1"}),
                evidence_ref="review:focused:1",
            ),
        )
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.reason, "strict_unresolved_measure_decrease")

        broad_reopen = replace(after, blocking_finding_ids=frozenset({"BLOCK-2", "BLOCK-3"}))
        rejected = admit_transition(
            after,
            broad_reopen,
            ConvergenceAction(
                "focused_recheck",
                target_ids=frozenset({"BLOCK-2"}),
                evidence_ref="review:focused:2",
            ),
        )
        self.assertFalse(rejected.admitted)
        self.assertEqual(rejected.reason, "new_blocker_requires_new_epoch_evidence")

    def test_new_epoch_requires_typed_evidence_and_new_candidate(self) -> None:
        before = replace(self.base_state(), review_status="complete")
        after = replace(
            before,
            candidate_epoch=2,
            candidate_digest=digest("3"),
            review_status="not_started",
        )
        rejected = admit_transition(
            before,
            after,
            ConvergenceAction("repair"),
        )
        self.assertFalse(rejected.admitted)
        admitted = admit_transition(
            before,
            after,
            ConvergenceAction(
                "repair",
                new_epoch_evidence_kind="reachable_behavior_change",
                evidence_ref="behavior:witness:1",
            ),
        )
        self.assertTrue(admitted.admitted)

    def test_zero_measure_selected_validation_is_terminal(self) -> None:
        before = replace(
            self.base_state(),
            review_status="complete",
            unresolved_validation_ids=frozenset(),
            unresolved_request_clause_ids=frozenset(),
        )
        after = replace(before, terminal_state="ship")
        decision = admit_transition(
            before,
            after,
            ConvergenceAction(
                "ship",
                decision_evidence_kind="ship_state_change",
                evidence_ref="ship:gate:1",
            ),
        )
        self.assertTrue(decision.admitted)

    def test_closeout_projection_requires_monotone_zero_measure(self) -> None:
        projection = {
            "convergence_schema": CONVERGENCE_CLOSEOUT_SCHEMA,
            "candidate_epoch": "1",
            "candidate_digest": digest("4"),
            "initial_review_status": "complete",
            "initial_blocking_finding_ids": "BLOCK-1",
            "focused_recheck_finding_ids": "BLOCK-1",
            "open_blocking_finding_ids": "none",
            "advisory_finding_ids": "ADVISORY-1",
            "unresolved_request_clause_ids": "none",
            "unresolved_validation_ids": "none",
            "unresolved_measure_initial": "1",
            "unresolved_measure_final": "0",
            "selected_validation_status": "pass",
            "same_state_action_repeated": "no",
            "terminal_state": "ship",
            "new_epoch_reason": "none",
        }
        self.assertTrue(validate_closeout_projection(projection).ready)
        projection["same_state_action_repeated"] = "yes"
        decision = validate_closeout_projection(projection)
        self.assertFalse(decision.ready)
        self.assertIn("same_state_action_repeated", decision.reasons)


if __name__ == "__main__":
    unittest.main()
