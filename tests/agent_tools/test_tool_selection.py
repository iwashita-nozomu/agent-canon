# @dependency-start
# contract test
# responsibility Tests normalized tool-selection evidence.
# upstream implementation ../../tools/agent/orchestration/tool_selection.py owns tool selection.
# @dependency-end
"""Focused tests for pure tool selection."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from tools.agent.orchestration.tool_selection import select_tools  # noqa: E402


class ToolSelectionTest(unittest.TestCase):
    def test_bash_tool_is_normalized(self) -> None:
        result = select_tools({"tool_name": "Bash", "tool_input": {"cmd": "git status"}})
        self.assertEqual(result.selected_tools, ("Bash",))
        self.assertEqual(result.command_verb, "git")


if __name__ == "__main__":
    unittest.main()
