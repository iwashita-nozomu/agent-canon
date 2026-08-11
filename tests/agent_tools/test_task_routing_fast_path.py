"""Focused tests for task-routing's pre-routing boundary."""

# @dependency-start
# contract test
# responsibility Tests task-routing fast path without Decision Sufficiency.
# upstream design ../../agents/skills/task-routing.md task-routing fast-path contract
# upstream implementation ../../tools/agent_tools/route.py selects routes
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTE = PROJECT_ROOT / "tools" / "agent_tools" / "route.py"
TASK_ROUTING = PROJECT_ROOT / "agents" / "skills" / "task-routing.md"
DECISION_FIELDS = (
    "decision_sufficiency_packet_ref",
    "packet_ref",
    "owner",
    "replaceable_unit",
    "implementation_mechanism",
    "validation_route",
    "unresolved_branch",
)


class TaskRoutingFastPathTest(unittest.TestCase):
    """Keep route selection ahead of optional implementation sufficiency work."""

    def run_route(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run route.py with the repository catalog."""
        return subprocess.run(
            [sys.executable, str(ROUTE), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_no_decision_fields(self, payload: dict[str, object]) -> None:
        """Assert that ordinary routing emits no implementation decision record."""
        for field in DECISION_FIELDS:
            self.assertNotIn(field, payload)

    def test_prompt_route_needs_only_prompt_and_changed_path(self) -> None:
        """Prompt routing should select skills without a sufficiency packet."""
        result = self.run_route(
            "--prompt",
            "Which skill should handle task routing docs?",
            "--changed",
            "agents/skills/task-routing.md",
            "--mode",
            "routing-only",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "agent_canon.route.skill_route.v1")
        self.assertEqual(payload["route"], "skill-selection")
        self.assertTrue(payload["active_skills"])
        self.assert_no_decision_fields(payload)

    def test_changed_path_area_route_needs_no_sufficiency_packet(self) -> None:
        """Changed-path evidence should complete an ordinary area route directly."""
        result = self.run_route(
            "--area",
            "checks",
            "--changed",
            "agents/skills/task-routing.md",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["route"], "task-routing")
        self.assertEqual(payload["area"], "checks")
        self.assertIn("agents/skills/task-routing.md", payload["evidence"])
        self.assert_no_decision_fields(payload)

    def test_skill_contract_defers_decision_sufficiency_until_implementation(
        self,
    ) -> None:
        """The skill contract must not reintroduce a pre-routing packet."""
        text = TASK_ROUTING.read_text(encoding="utf-8")
        standard_command = text.split("## Standard Command", maxsplit=1)[1].split(
            "## Outputs", maxsplit=1
        )[0]
        outputs = text.split("## Outputs", maxsplit=1)[1].split(
            "## Activation Boundary", maxsplit=1
        )[0]
        normalized_command = " ".join(standard_command.split())

        self.assertIn(
            "Ordinary routing does not require a Decision Sufficiency packet",
            normalized_command,
        )
        self.assertIn(
            "high-risk or genuinely ambiguous implementation work",
            normalized_command,
        )
        self.assertNotIn(
            "Consume the semantic decision-sufficiency record before selecting a route",
            normalized_command,
        )
        self.assertNotIn("DECISION_SUFFICIENCY_PACKET_REF", outputs)
        self.assertNotIn("owner-produced semantic sufficiency fields", outputs)


if __name__ == "__main__":
    unittest.main()
