"""Tests for task-local contract observation collection and evaluation."""

# @dependency-start
# contract test
# responsibility Verifies task contract observation schema, identity, and state transitions.
# upstream implementation ../../tools/runtime/lifecycle/task_contract_observation.py owns collection and evaluation
# upstream implementation ../../tools/runtime/lifecycle/task_contract_observation_core.py owns schema and transitions
# upstream design ../../documents/runtime/task-contract-observation.md defines the state machine
# @dependency-end

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from tools.runtime.lifecycle.task_contract_observation import run_self_check, summary_event  # noqa: E402
from tools.runtime.lifecycle.task_contract_observation_core import (  # noqa: E402
    ARCHIVE_ROUTE,
    KIND_KEY,
    OBSERVED_KIND,
    SCHEMA,
    SCHEMA_KEY,
    ParsedRecord,
    derived_observation_id,
    evaluate_payloads,
    normalize_record_argument,
)


def observed(
    *,
    outcome: str,
    sequence: int = 1,
    observation_id: str = "contract-alpha",
    contract_id: str = "AGENTS.md#repository",
    contract_source: str = "AGENTS.md",
    evidence_ref: str = "verification.txt",
    response: str = "preserve-contract",
) -> str:
    """Return one valid observed contract record."""

    return " ".join(
        (
            f"{SCHEMA_KEY}={SCHEMA}",
            f"{KIND_KEY}={OBSERVED_KIND}",
            f"observation_id={observation_id}",
            f"sequence={sequence}",
            f"contract_id={contract_id}",
            f"contract_source={contract_source}",
            "phase=implementation",
            "trigger=guardrail",
            f"outcome={outcome}",
            "owner=implementer",
            f"evidence_ref={evidence_ref}",
            f"response={response}",
        )
    )


class TaskContractObservationTest(unittest.TestCase):
    """Validate task contract observation invariants."""

    def test_satisfied_observation_passes(self) -> None:
        """One terminal observation should provide complete coverage."""

        result = evaluate_payloads((observed(outcome="satisfied"),))

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.observation_count, 1)
        self.assertEqual(result.unresolved_ids, ())
        self.assertEqual(result.states[0].outcome, "satisfied")

    def test_blocked_then_satisfied_passes(self) -> None:
        """An open state should close only through the next monotonic sequence."""

        result = evaluate_payloads(
            (
                observed(outcome="blocked"),
                observed(
                    outcome="satisfied",
                    sequence=2,
                    evidence_ref="verification.txt#targeted-check",
                    response="repair-applied",
                ),
            )
        )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.states[0].sequence, 2)
        self.assertEqual(result.states[0].response, "repair-applied")

    def test_unresolved_observation_fails(self) -> None:
        """Open blocked or violated observations cannot pass closeout evaluation."""

        result = evaluate_payloads((observed(outcome="blocked"),))

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.unresolved_ids, ("contract-alpha",))
        self.assertIn(
            "unresolved_observation",
            {finding.code for finding in result.findings},
        )

    def test_identity_collision_fails(self) -> None:
        """One observation id cannot be rebound to another canonical contract."""

        result = evaluate_payloads(
            (
                observed(outcome="blocked"),
                observed(
                    outcome="satisfied",
                    sequence=2,
                    contract_id="OTHER.md#repository",
                    contract_source="OTHER.md",
                ),
            )
        )

        self.assertEqual(result.status, "fail")
        self.assertIn(
            "identity_collision",
            {finding.code for finding in result.findings},
        )

    def test_sequence_gap_fails(self) -> None:
        """Append-only observation sequences must not skip intermediate values."""

        result = evaluate_payloads(
            (
                observed(outcome="blocked"),
                observed(outcome="satisfied", sequence=3),
            )
        )

        self.assertEqual(result.status, "fail")
        self.assertIn(
            "sequence_gap",
            {finding.code for finding in result.findings},
        )

    def test_explicit_none_passes_but_cannot_mix_with_observed(self) -> None:
        """No-observation evidence is explicit and mutually exclusive."""

        none = (
            f"{SCHEMA_KEY}={SCHEMA} {KIND_KEY}=none "
            "owner=manager reason=no-contract-triggered"
        )
        self.assertEqual(evaluate_payloads((none,)).status, "pass")

        mixed = evaluate_payloads((none, observed(outcome="satisfied")))
        self.assertEqual(mixed.status, "fail")
        self.assertIn(
            "coverage_ambiguous",
            {finding.code for finding in mixed.findings},
        )

    def test_record_normalization_derives_identity_and_sequence(self) -> None:
        """The recorder should derive deterministic ids and monotonic sequences."""

        raw = (
            "contract_id=AGENTS.md#repository contract_source=AGENTS.md "
            "phase=implementation trigger=guardrail outcome=blocked "
            "owner=implementer evidence_ref=verification.txt "
            "response=repair-planned"
        )
        first = normalize_record_argument(raw, ())
        first_fields = dict(token.split("=", 1) for token in first.split())
        expected_id = derived_observation_id(first_fields)
        self.assertEqual(first_fields["observation_id"], expected_id)
        self.assertEqual(first_fields["sequence"], "1")

        existing = (ParsedRecord(1, first_fields),)
        second = normalize_record_argument(
            raw.replace("outcome=blocked", "outcome=satisfied").replace(
                "response=repair-planned",
                "response=repair-applied",
            ),
            existing,
        )
        second_fields = dict(token.split("=", 1) for token in second.split())
        self.assertEqual(second_fields["observation_id"], expected_id)
        self.assertEqual(second_fields["sequence"], "2")

    def test_summary_exposes_eval_and_archive_route(self) -> None:
        """The behavior summary should carry the closeout scoring tokens."""

        result = evaluate_payloads((observed(outcome="satisfied"),))
        summary = summary_event(result)

        self.assertIn("task_contract_observation_eval_status=pass", summary)
        self.assertIn("task_contract_observation_coverage=complete", summary)
        self.assertIn("task_contract_observation_digest=", summary)
        self.assertIn("task_contract_resolution=terminal", summary)
        self.assertIn(f"contract_archive_route={ARCHIVE_ROUTE}", summary)

    def test_built_in_self_check_covers_positive_and_negative_cases(self) -> None:
        """The tool's deterministic conformance suite should remain green."""

        passed, lines = run_self_check()

        self.assertTrue(passed)
        self.assertGreaterEqual(len(lines), 6)
        self.assertTrue(
            all(":pass:" in line for line in lines),
            lines,
        )


if __name__ == "__main__":
    unittest.main()
