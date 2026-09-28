"""R1 regression at the existing PostToolUse entrypoint and spool boundary."""

# @dependency-start
# contract test
# responsibility Tests argument privacy for projection-independent hook observations.
# upstream implementation ../../.codex/hooks/hook_dispatcher.py owns dispatch and projection.
# upstream implementation ../../tools/agent/orchestration/tool_selection.py owns command evidence.
# upstream implementation test_codex_hooks.py owns isolated hook fixtures.
# @dependency-end

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_single_append_and_monitor_never_receive_command_arguments(self) -> None:
        dispatcher = hooks.hook_dispatcher
        for marker in ("private-command-value", "ghp_" + "A" * 36):
            payload = {
                "hookEventName": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": f"/usr/bin/printf '%s' {marker}"},
                "tool_response": {
                    "exit_code": 0,
                    "stdout": "private-stdout",
                    "stderr": "private-stderr",
                },
                "metadata": "private-metadata-value",
            }
            for append_status in ("spooled", "duplicate", "failed", "exception"):
                with (
                    self.subTest(status=append_status, marker_kind=marker[:4]),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    root = Path(tmp)
                    context = mock.Mock()
                    context.run_id.return_value = "hook-command-privacy"
                    if append_status == "exception":
                        context.append.side_effect = OSError("fixture append failure")
                    else:
                        context.append.return_value = mock.Mock(status=append_status)
                    with (
                        mock.patch.object(
                            dispatcher,
                            "hook_root",
                            return_value=dispatcher.HookRootState(
                                root, False, dispatcher.HookRootStatus.OVERRIDE
                            ),
                        ),
                        mock.patch.object(
                            dispatcher, "resolve_report_target", return_value=root / "report"
                        ),
                        mock.patch.object(
                            dispatcher, "HookLogContext", return_value=context
                        ),
                        mock.patch.object(dispatcher, "emit_behavior_projection") as emit,
                        mock.patch("sys.stdout", new_callable=io.StringIO) as output,
                    ):
                        self.assertEqual(
                            dispatcher.dispatch_event(
                                "PostToolUse", json.dumps(payload).encode("utf-8")
                            ),
                            0,
                        )
                    self.assertEqual(output.getvalue(), "")
                    context.append.assert_called_once()
                    event = context.append.call_args.args[0]
                    self.assertEqual(event["record_kind"], "behavior_event")
                    self.assertEqual(event["status"], "invalid_projection")
                    self.assertEqual(event["tool_name"], "Bash")
                    self.assertEqual(event["tool_command_verb"], "")
                    self.assertRegex(
                        event["tool_input_fingerprint"], r"^[0-9a-f]{12}$"
                    )
                    if append_status == "spooled":
                        emit.assert_called_once()
                        projection = emit.call_args.args[1]
                        self.assertEqual(projection["tool_command_verb"], "")
                        for key, value in projection.items():
                            self.assertEqual(event[key], value)
                    else:
                        emit.assert_not_called()
                    for value in (
                        marker, "private-stdout", "private-stderr", "private-metadata-value"
                    ):
                        self.assertNotIn(value, json.dumps(event))


if __name__ == "__main__":
    unittest.main()
