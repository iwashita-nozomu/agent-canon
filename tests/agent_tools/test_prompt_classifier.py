# @dependency-start
# contract test
# responsibility Tests pure prompt routing classification.
# upstream implementation ../../tools/agent_tools/prompt_classifier.py owns prompt classification.
# @dependency-end
"""Focused tests for injected prompt classification."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from prompt_classifier import PromptClassifierInputs, prompt_intake_signals  # noqa: E402


class PromptClassifierTest(unittest.TestCase):
    def test_declared_skill_is_selected_without_io(self) -> None:
        signals = prompt_intake_signals(PromptClassifierInputs("use $task-routing", Path("."), {}, {}))
        self.assertEqual(signals.skills, ("task-routing",))


if __name__ == "__main__":
    unittest.main()
