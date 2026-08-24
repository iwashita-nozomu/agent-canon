# @dependency-start
# contract test
# responsibility Tests normalized subagent-selection evidence.
# upstream implementation ../../tools/agent_tools/subagent_selection.py owns subagent selection.
# @dependency-end
"""Focused tests for pure subagent selection."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from subagent_selection import build_coordination_receipt, select_subagents  # noqa: E402


class SubagentSelectionTest(unittest.TestCase):
    def test_spawn_is_observed(self) -> None:
        result = select_subagents({"tool_name": "spawn_agent", "subagent_target": "worker"})
        self.assertTrue(result.invoked)
        self.assertEqual(result.action, "spawn")

    def test_runtime_collaboration_operations_are_normalized(self) -> None:
        for operation in (
            "send_message",
            "followup_task",
            "list_agents",
            "interrupt_agent",
        ):
            with self.subTest(operation=operation):
                result = select_subagents({"tool_name": f"tools.collaboration.{operation}"})
                self.assertTrue(result.invoked)
                self.assertEqual(result.action, operation)

    def test_hook_selection_ignores_synthetic_capability_fields(self) -> None:
        result = select_subagents(
            {
                "tool_name": "send_message",
                "coordination_capability_status": "available",
                "coordination_effective_operations": ["send_message"],
                "coordination_evidence_ref": "reports/runtime/capability.json",
                "coordination_mode": "direct_peer",
            }
        )
        self.assertEqual(result.action, "send_message")

    def test_coordination_receipt_uses_real_tool_result(self) -> None:
        selection = select_subagents({"tool_name": "send_message"})
        result = select_subagents(
            {
                "tool_name": "send_message",
                "coordination_mode": "parent_relay",
            }
        )
        self.assertEqual(result.action, "send_message")
        success = build_coordination_receipt(
            {
                "hookEventName": "PostToolUse",
                "tool_name": "send_message",
                "tool_input": {},
                "tool_response": {"exit_code": 0, "stderr": "", "stdout": "ok"},
            },
            selection,
            hook_event_name="PostToolUse",
        )
        self.assertIsNotNone(success)
        self.assertEqual(success["status"], "succeeded")
        self.assertFalse(success["direct_peer"])
        self.assertEqual(success["effective_operations"], [])
        failure = build_coordination_receipt(
            {
                "hookEventName": "PostToolUse",
                "tool_name": "send_message",
                "tool_input": {},
                "tool_response": {"exit_code": 1, "stderr": "error", "stdout": ""},
            },
            selection,
            hook_event_name="PostToolUse",
        )
        self.assertEqual(failure["status"], "failed")
        invalid = build_coordination_receipt(
            {"tool_name": "send_message"},
            selection,
            hook_event_name="PostToolUse",
        )
        self.assertEqual(invalid["status"], "invalid_tool_result")


if __name__ == "__main__":
    unittest.main()
