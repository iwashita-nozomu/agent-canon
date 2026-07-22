"""Tests for current automatic-review state projection."""

# @dependency-start
# contract test
# responsibility Tests current candidate review state and APPROVE-only unlock.
# upstream implementation ../../tools/agent_tools/review_dispatch.py materializes automatic-review state and routing
# @dependency-end

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

import review_dispatch  # noqa: E402
from artifact_identity import canonical_body_sha256  # noqa: E402


def candidate() -> dict[str, object]:
    """Return one immutable candidate fixture."""
    value: dict[str, object] = {"candidate_id": "candidate-1"}
    value["candidate_body_sha256"] = canonical_body_sha256(
        value,
        "candidate_body_sha256",
    )
    return value


def decision(name: str) -> dict[str, object]:
    """Return one body-hashed decision fixture."""
    value: dict[str, object] = {
        "candidate_id": "candidate-1",
        "candidate_body_sha256": candidate()["candidate_body_sha256"],
        "decision": name,
    }
    value["event_body_sha256"] = canonical_body_sha256(value, "event_body_sha256")
    return value


class ReviewDispatchTest(unittest.TestCase):
    """Verify only the current candidate's explicit decision unlocks publication."""

    def project(self, review_decision: dict[str, object]) -> dict[str, object]:
        """Project a patched canonical state without caller identity overrides."""
        with (
            patch.object(
                review_dispatch, "_active_report_dir", return_value=PROJECT_ROOT
            ),
            patch.object(
                review_dispatch, "_current_candidate", return_value=candidate()
            ),
            patch.object(
                review_dispatch,
                "_automatic_payloads",
                side_effect=lambda _report_dir, kind=None: (
                    [review_decision] if kind == "decision" else []
                ),
            ),
        ):
            return review_dispatch.resolve_current_review_state(PROJECT_ROOT)

    def test_revise_keeps_publication_locked(self) -> None:
        """REVISE remains a terminal repair state, never an approval."""
        state = self.project(decision("REVISE"))

        self.assertFalse(state["publication_unlocked"])

    def test_approve_unlocks_current_candidate_only(self) -> None:
        """Only an explicit APPROVE for the current candidate unlocks state."""
        state = self.project(decision("APPROVE"))

        self.assertTrue(state["publication_unlocked"])


if __name__ == "__main__":
    unittest.main()
