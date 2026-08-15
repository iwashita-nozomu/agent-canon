"""Compatibility tests for the PR dependency gate's source/runtime boundary."""

# @dependency-start
# contract test
# responsibility Verifies the PR gate's source-gate delegation and receipt owner.
# upstream implementation ../../tools/ci/check_agent_canon_pr.sh owns PR dependency routing
# upstream implementation ../../tools/ci/run_pr_dependency_source_gate.sh owns source-only dependency validation
# upstream implementation ../../tools/ci/pr_gate_receipt.py owns source/skipped receipt semantics
# upstream design ../../documents/design/source-owned-dependency-validation.md owns dependency validation semantics
# upstream design ../../documents/design/dependency-manifest-design.md projects manifest semantics
# downstream implementation ./test_agent_canon_pr_dependency_source_gate.py exercises source-only fixture execution
# @dependency-end

from __future__ import annotations

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PR_CHECK = PROJECT_ROOT / "tools" / "ci" / "check_agent_canon_pr.sh"
RECEIPT = PROJECT_ROOT / "tools" / "ci" / "pr_gate_receipt.py"
RUN_ALL_CHECKS = PROJECT_ROOT / "tools" / "ci" / "run_all_checks.sh"


class AgentCanonPrGraphGateIntegrationTest(unittest.TestCase):
    """Keep the former integration path bound to the new source-owned contract."""

    def test_pr_gate_delegates_dependency_validation_to_source_gate(self) -> None:
        """The main PR shell selects scope but delegates validation to source."""
        text = PR_CHECK.read_text(encoding="utf-8")

        self.assertIn("run_pr_dependency_source_gate.sh", text)
        self.assertIn("AGENT_CANON_PR_DEPENDENCY_SOURCE", text)
        self.assertIn("dependency source completeness", text)

    def test_receipt_schema_is_the_single_status_boundary(self) -> None:
        """The producer and consumer share the executable receipt owner."""
        producer = PR_CHECK.read_text(encoding="utf-8")
        consumer = RUN_ALL_CHECKS.read_text(encoding="utf-8")
        receipt = RECEIPT.read_text(encoding="utf-8")

        self.assertIn('pr_gate_receipt.py" write', producer)
        self.assertIn('pr_gate_receipt.py" validate', consumer)
        self.assertIn("class PrGateDependencyStatus", receipt)
        self.assertIn('SOURCE = "source"', receipt)
        self.assertIn('SKIPPED = "skipped"', receipt)
        self.assertNotIn("prepared", receipt)
        self.assertNotIn("scoped", receipt)


if __name__ == "__main__":
    unittest.main()
