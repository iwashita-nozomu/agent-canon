"""Compatibility tests for the PR dependency gate's source/runtime boundary."""

# @dependency-start
# contract test
# responsibility Verifies the PR gate no longer orchestrates persisted dependency graph runtime state.
# upstream implementation ../../tools/ci/check_agent_canon_pr.sh owns PR dependency routing
# upstream implementation ../../tools/ci/run_pr_dependency_source_gate.sh owns source-only dependency validation
# upstream design ../../documents/design/dependency-manifest-design.md owns dependency validation semantics
# downstream implementation ./test_agent_canon_pr_dependency_source_gate.py exercises source-only fixture execution
# @dependency-end

from __future__ import annotations

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PR_CHECK = PROJECT_ROOT / "tools" / "ci" / "check_agent_canon_pr.sh"
SOURCE_GATE = PROJECT_ROOT / "tools" / "ci" / "run_pr_dependency_source_gate.sh"


class AgentCanonPrGraphGateIntegrationTest(unittest.TestCase):
    """Keep the former integration path bound to the new source-owned contract."""

    def test_pr_gate_delegates_dependency_validation_to_source_gate(self) -> None:
        """The main PR shell selects scope but delegates validation to source."""
        text = PR_CHECK.read_text(encoding="utf-8")

        self.assertIn("run_pr_dependency_source_gate.sh", text)
        self.assertIn("AGENT_CANON_PR_DEPENDENCY_SOURCE", text)
        self.assertIn("dependency source completeness", text)

    def test_pr_gate_does_not_execute_persisted_dependency_graph_commands(self) -> None:
        """Comments may name graph operations, but no executable command may remain."""
        text = PR_CHECK.read_text(encoding="utf-8")

        for command_fragment in (
            "graph build --root",
            "graph status --root",
            "graph query --root",
            "graph context --root",
        ):
            self.assertNotIn(command_fragment, text)
        self.assertNotIn("changed-responsibility-acceptance.json", text)

    def test_source_gate_has_no_graph_runtime_or_database_dependency(self) -> None:
        """The delegated gate operates only on tracked source and trusted diff evidence."""
        text = SOURCE_GATE.read_text(encoding="utf-8")

        self.assertIn("run_repo_dependency_review.sh", text)
        self.assertIn("tool_drift.py", text)
        self.assertIn("render_dependency_manifest_graph.py", text)
        for command_fragment in (
            "graph build --root",
            "graph status --root",
            "graph query --root",
            "graph context --root",
        ):
            self.assertNotIn(command_fragment, text)
        self.assertNotIn("knowledge-graph", text)
        self.assertNotIn("graph.sqlite", text)


if __name__ == "__main__":
    unittest.main()
