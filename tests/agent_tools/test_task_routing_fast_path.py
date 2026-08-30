"""Focused tests for task-routing's pre-routing boundary."""

# @dependency-start
# contract test
# responsibility Tests task-routing fast path without Decision Sufficiency.
# upstream design ../../agents/skills/task-routing.md task-routing fast-path contract
# upstream implementation ../../tools/agent/orchestration/route.py selects routes
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTE = PROJECT_ROOT / "tools" / "agent" / "orchestration" / "route.py"
TASK_ROUTING = PROJECT_ROOT / "agents" / "skills" / "task-routing.md"
DECISION_FIELDS = {
    "decision_sufficiency_packet_ref",
    "packet_ref",
    "owner",
    "replaceable_unit",
    "implementation_mechanism",
    "validation_route",
    "unresolved_branch",
}


class TaskRoutingFastPathTest(unittest.TestCase):
    """Keep route selection ahead of optional implementation sufficiency work."""

    def test_ordinary_routes_need_no_decision_packet(self) -> None:
        """Prompt and changed-path routes should complete from their direct inputs."""
        scenarios = (
            (
                (
                    "--prompt",
                    "Which skill should handle task routing docs?",
                    "--changed",
                    "agents/skills/task-routing.md",
                    "--mode",
                    "routing-only",
                    "--format",
                    "json",
                ),
                {
                    "schema": "agent_canon.route.skill_route.v1",
                    "route": "skill-selection",
                },
            ),
            (
                (
                    "--area",
                    "checks",
                    "--changed",
                    "agents/skills/task-routing.md",
                    "--format",
                    "json",
                ),
                {"route": "task-routing", "area": "checks"},
            ),
        )
        for arguments, expected in scenarios:
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [sys.executable, str(ROUTE), *arguments],
                    cwd=PROJECT_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                payload = json.loads(result.stdout)
                for key, value in expected.items():
                    self.assertEqual(payload[key], value)
                self.assertFalse(DECISION_FIELDS.intersection(payload))

    def test_contract_defers_decision_sufficiency_until_implementation(self) -> None:
        """The skill contract must not reintroduce a pre-routing packet."""
        text = TASK_ROUTING.read_text(encoding="utf-8")
        normalized = " ".join(text.split())

        self.assertIn(
            "Ordinary routing does not require a Decision Sufficiency packet",
            normalized,
        )
        self.assertIn(
            "high-risk or genuinely ambiguous implementation owners may invoke",
            normalized,
        )
        self.assertNotIn(
            "Consume the semantic decision-sufficiency record before selecting a route",
            text,
        )
        self.assertNotIn("DECISION_SUFFICIENCY_PACKET_REF", text)
        self.assertNotIn("owner-produced semantic sufficiency fields", text)


if __name__ == "__main__":
    unittest.main()
