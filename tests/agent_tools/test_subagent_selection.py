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
from subagent_selection import select_subagents  # noqa: E402


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
                self.assertEqual(result.capability_status, "unverified")
                self.assertEqual(result.coordination_mode, "durable_artifact")

    def test_direct_peer_requires_explicit_runtime_readback(self) -> None:
        result = select_subagents(
            {
                "tool_name": "send_message",
                "coordination_capability_status": "available",
                "coordination_effective_operations": ["send_message"],
                "coordination_evidence_ref": "reports/runtime/capability.json",
            }
        )
        self.assertEqual(result.coordination_mode, "direct_peer")

        matcher_only = select_subagents({"tool_name": "send_message"})
        self.assertNotEqual(matcher_only.coordination_mode, "direct_peer")

    def test_parent_relay_stays_distinct_from_direct_peer(self) -> None:
        result = select_subagents(
            {
                "tool_name": "send_message",
                "coordination_capability_status": "unavailable",
                "coordination_mode": "parent_relay",
            }
        )
        self.assertEqual(result.coordination_mode, "parent_relay")


if __name__ == "__main__":
    unittest.main()
