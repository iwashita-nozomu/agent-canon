"""Focused tests for pure subagent selection."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from subagent_selection import select_subagents  # noqa: E402


class SubagentSelectionTest(unittest.TestCase):
    def test_spawn_is_observed(self) -> None:
        result = select_subagents({"tool_name": "spawn_agent", "subagent_target": "worker"})
        self.assertTrue(result.invoked)
        self.assertEqual(result.action, "spawn")


if __name__ == "__main__":
    unittest.main()
