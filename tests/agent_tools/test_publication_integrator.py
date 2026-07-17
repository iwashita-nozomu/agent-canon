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
    integrate_publication,
    resolve_publication_eligibility,
    subprocess_runner,
)


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
            )

        self.assertEqual(receipt["candidate_oid"], candidate)
        self.assertEqual(receipt["result_oid"], server_result)
        self.assertEqual(receipt["post_cas_ref_oid"], server_result)


if __name__ == "__main__":
    unittest.main()
