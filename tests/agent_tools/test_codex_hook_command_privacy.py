"""R1 regression at the existing PostToolUse entrypoint and spool boundary."""

# @dependency-start
# contract test
# responsibility Tests argument privacy for projection-independent hook observations.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/hook_dispatcher.rs owns native dispatch and projection.
# upstream implementation ../../tools/agent/orchestration/tool_selection.py owns command evidence.
# upstream implementation test_codex_hooks.py owns isolated hook fixtures.
# @dependency-end

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import test_codex_hooks as hooks


class CodexHookCommandPrivacyTest(unittest.TestCase):
    def test_absolute_command_arguments_are_absent_from_the_spool(self) -> None:
        fixture = hooks.CodexHooksTest()
        for marker in ("private-command-value", "ghp_" + "A" * 36):
            with (
                self.subTest(marker_kind=marker[:4]),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp) / "source"
                root.mkdir()
                result = fixture._run_hook_in_root(
                    root,
                    "PostToolUse",
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"command": f"/usr/bin/printf '%s' {marker}"},
                        "tool_response": {
                            "exit_code": 0,
                            "stdout": "private-stdout",
                            "stderr": "private-stderr",
                        },
                    },
                )
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")
                event = fixture._spooled_event(root)
                self.assertEqual(event["status"], "invalid_projection")
                self.assertEqual(event["record_kind"], "behavior_event")
                self.assertEqual(event["tool_name"], "Bash")
                self.assertEqual(event["selected_tools"], ["Bash"])
                self.assertEqual(event["tool_command_verb"], "")
                self.assertRegex(event["tool_input_fingerprint"], r"^[0-9a-f]{12}$")
                for value in (marker, "private-stdout", "private-stderr"):
                    self.assertNotIn(value, json.dumps(event))
                self.assertNotIn("tool_response", event)

if __name__ == "__main__":
    unittest.main()
