"""Tests for finite autonomous review and implementation convergence."""

# @dependency-start
# contract test
# responsibility Tests autonomous convergence transitions, cycle stops, and closeout projection.
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

from autonomous_convergence import (
    CONVERGENCE_CLOSEOUT_SCHEMA,
    ConvergenceAction,
    ConvergenceContractError,
    ConvergenceState,
    action_fingerprint,
    admit_transition,
    validate_closeout_projection,
    validate_contract,
    validate_state,
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
            selected_validation_status="pending",
        )

    def reviewed_state(self) -> ConvergenceState:
        return replace(
            self.base_state(),
            review_status="complete",
            blocking_finding_ids=frozenset({"BLOCK-1", "BLOCK-2"}),
        )

    def repair_action(self) -> ConvergenceAction:
        return ConvergenceAction(
            "repair",
            target_ids=frozenset({"BLOCK-1"}),
            affected_validation_ids=frozenset({"VAL-2"}),
            decision_evidence_kinds=frozenset({"ship_state_change"}),
            new_epoch_evidence_kind="reachable_behavior_change",
            evidence_ref="repair:BLOCK-1:candidate-3",
        )

    def repaired_state(self) -> ConvergenceState:
        return replace(
            self.reviewed_state(),
            candidate_digest=digest("3"),
            candidate_epoch=2,
            unresolved_validation_ids=frozenset({"VAL-1", "VAL-2"}),
        )

    def test_contract_projection_matches_runtime(self) -> None:
        self.assertEqual(validate_contract(PROJECT_ROOT), ())

    def test_initial_review_is_admitted_once_and_only_classifies_findings(
        self,
    ) -> None:
        before = self.base_state()
        after = replace(
            before,
            review_status="complete",
            blocking_finding_ids=frozenset({"BLOCK-1"}),
        )
        decision = admit_transition(
            before,
            after,
            ConvergenceAction(
                "initial_review",
                evidence_ref="review:initial:1",
            ),
        )
        self.assertTrue(decision.admitted)
        self.assertEqual(
            decision.reason,
            "one_initial_review_for_candidate_epoch",
        )

        repeated = admit_transition(
            after,
            after,
            ConvergenceAction(
                "initial_review",
                evidence_ref="review:initial:2",
            ),
        )
        self.assertFalse(repeated.admitted)
        self.assertEqual(
            repeated.reason,
            "initial_review_not_once_per_epoch",
        )

        mutated_candidate = replace(after, candidate_digest=digest("3"))
        rejected = admit_transition(
            before,
            mutated_candidate,
            ConvergenceAction(
                "initial_review",
                evidence_ref="review:mutated",
            ),
        )
        self.assertFalse(rejected.admitted)
        self.assertEqual(
            rejected.reason,
            "candidate_digest_change_requires_epoch_action",
        )

    def test_action_fingerprint_is_state_plus_action_class_only(self) -> None:
        state = self.reviewed_state()
        first = ConvergenceAction(
            "repair",
            target_ids=frozenset({"BLOCK-1"}),
            affected_validation_ids=frozenset({"VAL-1"}),
            decision_evidence_kinds=frozenset({"ship_state_change"}),
            new_epoch_evidence_kind="reachable_behavior_change",
            evidence_ref="repair:first",
        )
        second = ConvergenceAction(
            "repair",
            target_ids=frozenset({"BLOCK-2"}),
            affected_validation_ids=frozenset({"VAL-9"}),
            decision_evidence_kinds=frozenset(),
            new_epoch_evidence_kind="none",
            evidence_ref="repair:renamed-evidence",
        )
        self.assertEqual(
            action_fingerprint(state, first),
            action_fingerprint(state, second),
        )
        self.assertNotEqual(
            action_fingerprint(state, first),
            action_fingerprint(
                state,
                ConvergenceAction("focused_recheck"),
            ),
        )

    def test_same_state_same_action_class_is_typed_cycle_stop(self) -> None:
        state = self.reviewed_state()
        action = self.repair_action()
        fingerprint = action_fingerprint(state, action)
        decision = admit_transition(
            state,
            self.repaired_state(),
            action,
            seen_action_fingerprints={fingerprint},
        )
        self.assertFalse(decision.admitted)
        self.assertEqual(decision.reason, "non_convergent_cycle")
        self.assertEqual(
            decision.resulting_terminal_state,
            "non_convergent_cycle",
        )

    def test_repeated_request_candidate_epoch_is_typed_cycle_stop(self) -> None:
        before = self.reviewed_state()
        proposed = self.repaired_state()
        decision = admit_transition(
            before,
            proposed,
            self.repair_action(),
            seen_epoch_fingerprints={proposed.epoch_fingerprint()},
        )
        self.assertFalse(decision.admitted)
        self.assertEqual(decision.reason, "non_convergent_cycle")
        self.assertEqual(
            decision.resulting_terminal_state,
            "non_convergent_cycle",
        )

    def test_advisory_never_reopens_implementation(self) -> None:
        state = self.reviewed_state()
        decision = admit_transition(
            state,
            state,
            ConvergenceAction(
                "advisory",
                evidence_ref="advisory:A-1",
            ),
        )
        self.assertTrue(decision.admitted)
        self.assertEqual(
            decision.reason,
            "advisory_record_without_rework",
        )

        changed = replace(state, candidate_digest=digest("3"))
        rejected = admit_transition(
            state,
            changed,
            ConvergenceAction(
                "advisory",
                evidence_ref="advisory:A-2",
            ),
        )
        self.assertFalse(rejected.admitted)
        self.assertEqual(
            rejected.reason,
            "candidate_digest_change_requires_epoch_action",
        )

    def test_repair_opens_exact_next_candidate_epoch_without_new_review(
        self,
    ) -> None:
        before = self.reviewed_state()
        after = self.repaired_state()
        decision = admit_transition(
            before,
            after,
            self.repair_action(),
            seen_epoch_fingerprints={before.epoch_fingerprint()},
        )
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.reason, "typed_candidate_epoch_repair")
        self.assertEqual(after.review_status, "complete")
        self.assertEqual(
            after.blocking_finding_ids,
            before.blocking_finding_ids,
        )
        self.assertNotEqual(
            before.decision_tuple(),
            after.decision_tuple(),
        )

        stale_epoch = replace(after, candidate_epoch=before.candidate_epoch)
        rejected = admit_transition(
            before,
            stale_epoch,
            self.repair_action(),
        )
        self.assertFalse(rejected.admitted)
        self.assertEqual(
            rejected.reason,
            "candidate_epoch_transition_must_increment_once",
        )

    def test_repair_invalidates_only_declared_validation_evidence(self) -> None:
        before = self.reviewed_state()
        widened = replace(
            self.repaired_state(),
            unresolved_validation_ids=frozenset({"VAL-1", "VAL-2", "VAL-UNRELATED"}),
        )
        rejected = admit_transition(
            before,
            widened,
            self.repair_action(),
        )
        self.assertFalse(rejected.admitted)
        self.assertEqual(
            rejected.reason,
            "repair_validation_reopen_must_equal_affected_ids",
        )

        premature_close = replace(
            self.repaired_state(),
            blocking_finding_ids=frozenset({"BLOCK-2"}),
        )
        rejected = admit_transition(
            before,
            premature_close,
            self.repair_action(),
        )
        self.assertFalse(rejected.admitted)
        self.assertIn("repair_", rejected.reason)

        wrong_epoch_evidence = replace(
            self.repair_action(),
            new_epoch_evidence_kind="contract_change",
        )
        rejected = admit_transition(
            before,
            self.repaired_state(),
            wrong_epoch_evidence,
        )
        self.assertFalse(rejected.admitted)
        self.assertEqual(
            rejected.reason,
            "new_epoch_evidence_kind:not_allowed_for_action",
        )

    def test_focused_recheck_closes_only_targeted_stable_blockers(
        self,
    ) -> None:
        before = self.repaired_state()
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
                evidence_ref="recheck:BLOCK-1",
            ),
        )
        self.assertTrue(decision.admitted)
        self.assertEqual(
            decision.reason,
            "strict_unresolved_measure_decrease",
        )
        self.assertEqual(
            decision.next_measure,
            decision.prior_measure - 1,
        )

        unassigned = replace(
            before,
            blocking_finding_ids=frozenset({"BLOCK-1"}),
        )
        rejected = admit_transition(
            before,
            unassigned,
            ConvergenceAction(
                "focused_recheck",
                target_ids=frozenset({"BLOCK-1"}),
                evidence_ref="recheck:wrong-blocker",
            ),
        )
        self.assertFalse(rejected.admitted)
        self.assertEqual(
            rejected.reason,
            "focused_recheck_closed_unassigned_blocker",
        )

        added = replace(
            before,
            blocking_finding_ids=frozenset({"BLOCK-1", "BLOCK-2", "BLOCK-3"}),
        )
        rejected = admit_transition(
            before,
            added,
            ConvergenceAction(
                "focused_recheck",
                target_ids=frozenset({"BLOCK-1"}),
                evidence_ref="recheck:add",
            ),
        )
        self.assertFalse(rejected.admitted)
        self.assertEqual(
            rejected.reason,
            "new_blocker_requires_new_epoch_evidence",
        )

    def test_clause_resolution_is_a_targeted_strict_decrease(self) -> None:
        before = self.reviewed_state()
        after = replace(
            before,
            unresolved_request_clause_ids=frozenset(),
        )
        decision = admit_transition(
            before,
            after,
            ConvergenceAction(
                "clause_resolution",
                target_ids=frozenset({"REQ-1"}),
                evidence_ref="clause:REQ-1",
            ),
        )
        self.assertTrue(decision.admitted)
        self.assertEqual(
            decision.reason,
            "strict_unresolved_measure_decrease",
        )

        reopened = replace(
            before,
            unresolved_request_clause_ids=frozenset({"REQ-1", "REQ-2"}),
        )
        rejected = admit_transition(
            before,
            reopened,
            ConvergenceAction(
                "clause_resolution",
                target_ids=frozenset({"REQ-1"}),
                evidence_ref="clause:reopen",
            ),
        )
        self.assertFalse(rejected.admitted)
        self.assertEqual(
            rejected.reason,
            "clause_resolution_requires_targeted_strict_decrease",
        )

    def test_validation_closes_or_reclassifies_only_targeted_evidence(
        self,
    ) -> None:
        before = replace(
            self.reviewed_state(),
            blocking_finding_ids=frozenset(),
            unresolved_request_clause_ids=frozenset(),
            unresolved_validation_ids=frozenset({"VAL-1", "VAL-2"}),
        )
        after = replace(
            before,
            unresolved_validation_ids=frozenset({"VAL-2"}),
        )
        decision = admit_transition(
            before,
            after,
            ConvergenceAction(
                "validation",
                target_ids=frozenset({"VAL-1"}),
                evidence_ref="validation:VAL-1:pass",
            ),
        )
        self.assertTrue(decision.admitted)
        self.assertEqual(
            decision.reason,
            "strict_unresolved_measure_decrease",
        )

        swapped = replace(
            after,
            unresolved_validation_ids=frozenset({"VAL-3"}),
        )
        decision = admit_transition(
            after,
            swapped,
            ConvergenceAction(
                "validation",
                target_ids=frozenset({"VAL-2", "VAL-3"}),
                decision_evidence_kinds=frozenset({"ship_state_change"}),
                evidence_ref="validation:reclassify",
            ),
        )
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.reason, "new_decision_evidence")

        widened = replace(
            after,
            unresolved_validation_ids=frozenset({"VAL-2", "VAL-3"}),
        )
        rejected = admit_transition(
            after,
            widened,
            ConvergenceAction(
                "validation",
                target_ids=frozenset({"VAL-2"}),
                decision_evidence_kinds=frozenset({"ship_state_change"}),
                evidence_ref="validation:widened",
            ),
        )
        self.assertFalse(rejected.admitted)
        self.assertEqual(
            rejected.reason,
            "validation_reopen_or_close_exceeded_target_ids",
        )

    def test_new_epoch_requires_supported_typed_evidence_and_reset_review(
        self,
    ) -> None:
        before = self.reviewed_state()
        contract_epoch = replace(
            before,
            request_digest=digest("4"),
            candidate_epoch=2,
            review_status="not_started",
            blocking_finding_ids=frozenset(),
        )
        decision = admit_transition(
            before,
            contract_epoch,
            ConvergenceAction(
                "epoch_reopen",
                decision_evidence_kinds=frozenset({"ship_state_change"}),
                new_epoch_evidence_kind="contract_change",
                evidence_ref="epoch:contract-change",
            ),
            seen_epoch_fingerprints={before.epoch_fingerprint()},
        )
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.reason, "typed_new_epoch_evidence")

        structural_epoch = replace(
            before,
            candidate_digest=digest("5"),
            candidate_epoch=2,
            owner="new-owner",
            review_status="not_started",
            blocking_finding_ids=frozenset(),
        )
        rejected = admit_transition(
            before,
            structural_epoch,
            ConvergenceAction(
                "epoch_reopen",
                decision_evidence_kinds=frozenset({"ship_state_change"}),
                new_epoch_evidence_kind="structural_contradiction",
                evidence_ref="epoch:structural",
            ),
        )
        self.assertFalse(rejected.admitted)
        self.assertEqual(
            rejected.reason,
            "new_epoch_decision_evidence_does_not_match_change",
        )

        unsupported = replace(
            before,
            candidate_epoch=2,
            review_status="not_started",
            blocking_finding_ids=frozenset(),
        )
        rejected = admit_transition(
            before,
            unsupported,
            ConvergenceAction(
                "epoch_reopen",
                decision_evidence_kinds=frozenset({"ship_state_change"}),
                new_epoch_evidence_kind="contract_change",
                evidence_ref="epoch:unsupported",
            ),
        )
        self.assertFalse(rejected.admitted)
        self.assertEqual(
            rejected.reason,
            "candidate_epoch_requires_new_identity",
        )

    def test_ship_gate_is_checked_before_typed_decision_evidence(self) -> None:
        before = self.reviewed_state()
        proposed = replace(before, terminal_state="ship")
        decision = admit_transition(
            before,
            proposed,
            ConvergenceAction(
                "ship",
                decision_evidence_kinds=frozenset({"ship_state_change"}),
                evidence_ref="ship:blocked",
            ),
        )
        self.assertFalse(decision.admitted)
        self.assertEqual(decision.reason, "terminal_gate_not_satisfied")

    def test_zero_measure_selected_validation_is_terminal_and_absorbing(
        self,
    ) -> None:
        ready = replace(
            self.reviewed_state(),
            blocking_finding_ids=frozenset(),
            unresolved_validation_ids=frozenset(),
            unresolved_request_clause_ids=frozenset(),
            selected_validation_status="pass",
        )
        terminal = replace(ready, terminal_state="ship")
        action = ConvergenceAction(
            "ship",
            decision_evidence_kinds=frozenset({"ship_state_change"}),
            evidence_ref="ship:terminal",
        )
        decision = admit_transition(ready, terminal, action)
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.reason, "terminal_zero_measure")

        absorbing = admit_transition(
            terminal,
            terminal,
            action,
            seen_action_fingerprints={action_fingerprint(terminal, action)},
        )
        self.assertFalse(absorbing.admitted)
        self.assertEqual(absorbing.reason, "terminal_state_is_absorbing")

    def test_validation_status_and_unresolved_ids_are_consistent(self) -> None:
        with self.assertRaisesRegex(
            ConvergenceContractError,
            "required_for_nonterminal_validation_status",
        ):
            validate_state(
                replace(
                    self.base_state(),
                    unresolved_validation_ids=frozenset(),
                    selected_validation_status="pending",
                )
            )
        with self.assertRaisesRegex(
            ConvergenceContractError,
            "must_be_empty_for_terminal_validation_status",
        ):
            validate_state(
                replace(
                    self.base_state(),
                    selected_validation_status="pass",
                )
            )

    def test_closeout_projection_requires_focused_zero_measure_terminal_gate(
        self,
    ) -> None:
        projection = {
            "convergence_schema": CONVERGENCE_CLOSEOUT_SCHEMA,
            "candidate_epoch": "2",
            "candidate_digest": digest("3"),
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
            "new_epoch_reason": "reachable_behavior_change",
        }
        self.assertTrue(validate_closeout_projection(projection).ready)

        projection["focused_recheck_finding_ids"] = "none"
        decision = validate_closeout_projection(projection)
        self.assertFalse(decision.ready)
        self.assertIn(
            "closed_blocker:missing_focused_recheck",
            decision.reasons,
        )

        projection["focused_recheck_finding_ids"] = "BLOCK-1"
        projection["same_state_action_repeated"] = "yes"
        decision = validate_closeout_projection(projection)
        self.assertFalse(decision.ready)
        self.assertIn("same_state_action_repeated", decision.reasons)


if __name__ == "__main__":
    unittest.main()
