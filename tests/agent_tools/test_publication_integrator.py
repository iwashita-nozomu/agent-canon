"""Tests for APPROVE-only publication eligibility."""

# @dependency-start
# contract test
# responsibility Tests publication eligibility refuses CAS ingress without current approval.
# upstream implementation ../../tools/agent_tools/publication_integrator.py resolves publication authority and CAS eligibility
# @dependency-end

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from publication_integrator import (  # noqa: E402
    _construct_result_commit,
    _publication_gate,
    PublicationError,
    integrate_publication,
    resolve_publication_eligibility,
    subprocess_runner,
)


def lifecycle_binding() -> dict[str, object]:
    """Return one exact identity reused across publication boundary receipts."""
    return {
        "transaction_id": "tx:" + "1" * 64,
        "snapshot_id": "snapshot:" + "2" * 64,
        "candidate_sha": "3" * 40,
        "tree_sha": "4" * 40,
        "input_digest": "sha256:" + "5" * 64,
        "tool_id": "publication-integrator",
        "tool_version": "test.v1",
        "evidence_ref": "evidence:" + "6" * 64,
        "evidence_digest": "sha256:" + "7" * 64,
        "timing": {
            "started_at": "2026-07-18T00:00:00Z",
            "finished_at": "2026-07-18T00:00:00Z",
            "last_attempt_at": "2026-07-18T00:00:00Z",
            "duration_ms": 0,
            "attempt": 1,
            "replayed": False,
        },
    }


class PublicationIntegratorTest(unittest.TestCase):
    """Verify review state remains a prerequisite for publication CAS."""

    def test_ineligible_review_never_produces_publication_authority(self) -> None:
        """A non-eligible review fails closed before authority derivation."""
        with patch(
            "publication_integrator.resolve_review_eligibility",
            return_value={"outcome": "ineligible"},
        ):
            projection = resolve_publication_eligibility(PROJECT_ROOT)

        self.assertEqual(projection["outcome"], "ineligible")
        self.assertIsNone(projection["publication_authority"])
        self.assertEqual(
            projection["failure_codes"],
            ["publication_eligibility:review_not_eligible"],
        )

    def test_pull_request_result_starts_from_the_reviewed_head(self) -> None:
        """A PR route delegates the server result instead of predicting its SHA."""
        authority = {
            "target": {
                "route": "pull_request",
                "mode": "merge",
                "expected_target_oid": "a" * 40,
            },
            "source": {"commit": "b" * 40},
            "candidate_authority": {"candidate_commit": "c" * 40},
            "candidate_attestation": {},
        }

        self.assertEqual(
            _construct_result_commit(PROJECT_ROOT, authority, runner=subprocess_runner),
            "c" * 40,
        )

    def test_pull_request_receipt_binds_server_result_readback(self) -> None:
        """A PR receipt records the actual merge result and post-CAS readback."""
        expected_base = "a" * 40
        expected_tree = "b" * 40
        candidate = "c" * 40
        server_result = "d" * 40
        authority = {
            "publication_id": "w2-publication:test",
            "selection_sha256": "e" * 64,
            "target": {
                "route": "pull_request",
                "target_ref": "refs/heads/main",
                "mode": "merge",
                "expected_target_oid": expected_base,
                "expected_target_tree": expected_tree,
            },
            "candidate_authority": {"candidate_commit": candidate},
        }

        def read_git(_workspace: Path, command: list[str], **_kwargs: object) -> str:
            if command[-1] == "refs/heads/main":
                return expected_base
            if command[-1] == f"{expected_base}^{{tree}}":
                return expected_tree
            raise AssertionError(command)

        with (
            patch(
                "publication_integrator.resolve_publication_authority",
                side_effect=[authority, authority],
            ),
            patch("publication_integrator._git_text", side_effect=read_git),
            patch("publication_integrator._worktree_status", return_value=""),
            patch(
                "publication_integrator._construct_result_commit",
                return_value=candidate,
            ),
        ):
            receipt = integrate_publication(
                PROJECT_ROOT,
                pr_merge_adapter=lambda _request: {
                    "status": "merged",
                    "result_oid": server_result,
                    "post_cas_ref_oid": server_result,
                },
                lifecycle_binding=lifecycle_binding(),
                ordered_input_evidence_refs=["evidence:" + "8" * 64],
            )

        self.assertEqual(receipt["candidate_oid"], candidate)
        self.assertEqual(receipt["result_oid"], server_result)
        self.assertEqual(receipt["post_cas_ref_oid"], server_result)
        gate = receipt["remote_publication_readback_gate"]
        self.assertIsInstance(gate, dict)
        self.assertEqual(gate["gate_id"], "G5")

    def test_boundary_gate_identity_is_distinct_and_replay_stable(self) -> None:
        """G1, G3, and G5 reuse identity while retaining separate evidence IDs."""
        binding = lifecycle_binding()
        gates = [
            _publication_gate(
                binding=binding,
                gate_id=gate_id,
                ordered_input_evidence_refs=["evidence:" + "8" * 64],
                invariant=invariant,
                owner_symbol="test_boundary_gate_identity_is_distinct_and_replay_stable",
                output={"candidate": "3" * 40},
                verdict="pass",
            )
            for gate_id, invariant in (
                ("G1", "source_correctness"),
                ("G3", "pr_identity_cas"),
                ("G5", "remote_publication_readback"),
            )
        ]
        replay = _publication_gate(
            binding=binding,
            gate_id="G3",
            ordered_input_evidence_refs=["evidence:" + "8" * 64],
            invariant="pr_identity_cas",
            owner_symbol="test_boundary_gate_identity_is_distinct_and_replay_stable",
            output={"candidate": "3" * 40},
            verdict="pass",
        )

        evidence_refs = [gate["binding"]["evidence_ref"] for gate in gates]
        self.assertEqual(len(set(evidence_refs)), 3)
        self.assertEqual(replay["binding"]["evidence_ref"], evidence_refs[1])

    def test_pull_request_post_cas_readback_mismatch_fails_closed(self) -> None:
        """A server result and publication readback mismatch cannot emit G5."""
        expected_base = "a" * 40
        expected_tree = "b" * 40
        candidate = "c" * 40
        authority = {
            "publication_id": "w2-publication:test",
            "selection_sha256": "e" * 64,
            "target": {
                "route": "pull_request",
                "target_ref": "refs/heads/main",
                "mode": "merge",
                "expected_target_oid": expected_base,
                "expected_target_tree": expected_tree,
            },
            "candidate_authority": {"candidate_commit": candidate},
        }

        def read_git(_workspace: Path, command: list[str], **_kwargs: object) -> str:
            return expected_tree if command[-1].endswith("^{tree}") else expected_base

        with (
            patch("publication_integrator.resolve_publication_authority", return_value=authority),
            patch("publication_integrator._git_text", side_effect=read_git),
            patch("publication_integrator._worktree_status", return_value=""),
            patch("publication_integrator._construct_result_commit", return_value=candidate),
            self.assertRaises(PublicationError) as raised,
        ):
            integrate_publication(
                PROJECT_ROOT,
                pr_merge_adapter=lambda _request: {
                    "status": "merged",
                    "result_oid": "d" * 40,
                    "post_cas_ref_oid": "f" * 40,
                },
                lifecycle_binding=lifecycle_binding(),
            )

        self.assertEqual(
            raised.exception.code,
            "publication_integrator:post_cas_readback_mismatch",
        )


if __name__ == "__main__":
    unittest.main()
