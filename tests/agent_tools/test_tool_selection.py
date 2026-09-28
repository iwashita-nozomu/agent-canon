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

    def test_only_the_leading_bare_command_is_retained(self) -> None:
        """Arguments, including wrapper arguments, are not command evidence."""
        for command, expected in (
            ("  printf '%s' private-command-value", "printf"),
            ("sudo printf '%s' private-command-value", "sudo"),
            ("sudo -p private-command-value /usr/bin/printf", "sudo"),
            ("env VALUE=private-command-value /usr/bin/printf", "env"),
        ):
            with self.subTest(command=command):
                result = select_tools(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertEqual(result.command_verb, expected)
                self.assertTrue(result.should_log())

    def test_unsupported_prefixes_never_fall_through_to_arguments(self) -> None:
        """R1: a path, quote, assignment or shell form must not expose its tail."""
        for marker in ("private-command-value", "ghp_" + "A" * 36):
            for prefix in (
                "/usr/bin/printf",
                "./printf",
                "'/usr/bin/printf'",
                '"/usr/bin/printf"',
                "VALUE=private-command-value /usr/bin/printf",
                "${COMMAND}",
                "printf; /usr/bin/printf",
            ):
                for key in ("command", "cmd"):
                    with self.subTest(prefix=prefix, key=key, marker_kind=marker[:4]):
                        result = select_tools(
                            {
                                "tool_name": "Bash",
                                "tool_input": {key: f"{prefix} '%s' {marker}"},
                            }
                        )
                        self.assertEqual(result.command_verb, "")
                        self.assertEqual(result.tool_name, "Bash")
                        self.assertEqual(result.selected_tools, ("Bash",))
                        self.assertRegex(
                            result.tool_input_fingerprint, r"^[0-9a-f]{12}$"
                        )
                        self.assertTrue(result.should_log())
                        self.assertNotIn(marker, str(result))

    def test_top_level_command_aliases_share_the_privacy_boundary(self) -> None:
        for key in ("command", "cmd"):
            with self.subTest(key=key):
                result = select_tools(
                    {
                        "tool_name": "Bash",
                        key: "/usr/bin/printf '%s' private-command-value",
                    }
                )
                self.assertEqual(result.command_verb, "")
                self.assertTrue(result.should_log())
                self.assertNotIn("private-command-value", str(result))


if __name__ == "__main__":
    unittest.main()
