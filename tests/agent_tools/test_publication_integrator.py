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

from publication_integrator import resolve_publication_eligibility  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
