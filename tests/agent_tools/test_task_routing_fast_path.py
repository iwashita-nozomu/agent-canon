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

    def test_prompt_mode_is_caller_owned_and_missing_mode_stays_nonwrite(self) -> None:
        """Prompt words cannot promote an omitted or read-only mode."""
        route = (
            "On project_template agent-test, observe unnecessary exploration. "
            "Do not edit files."
        )
        for mode_args in ((), ("--mode", "routing-only")):
            with self.subTest(mode_args=mode_args):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROUTE),
                        "--prompt",
                        route,
                        *mode_args,
                        "--format",
                        "json",
                    ],
                    cwd=PROJECT_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["mode"], "routing-only")
                self.assertNotIn("test-design", payload["matched_skills"])
                self.assertNotIn("codex-task-workflow", payload["skills"])

    def test_explicit_repo_changing_mode_preserves_edit_route(self) -> None:
        """An explicitly typed write mode remains available to edit callers."""
        result = subprocess.run(
            [
                sys.executable,
                str(ROUTE),
                "--prompt",
                "Implement the requested routing fix.",
                "--mode",
                "repo-changing",
                "--format",
                "json",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "repo-changing")
        self.assertIn("codex-task-workflow", payload["skills"])

    def test_explicit_test_design_requires_bounded_risk_or_skill_id(self) -> None:
        """Test design remains available for explicit IDs and bounded risk evidence."""
        prompts = (
            "$test-design after the owning mechanism exists",
            "The unresolved oracle risk remains after the owning mechanism exists.",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROUTE),
                        "--prompt",
                        prompt,
                        "--mode",
                        "routing-only",
                        "--format",
                        "json",
                    ],
                    cwd=PROJECT_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                payload = json.loads(result.stdout)
                self.assertIn("test-design", payload["matched_skills"])

    def test_catalog_drops_obsolete_broad_test_trigger(self) -> None:
        """The cross-context unnecessary/test trigger is no longer authoritative."""
        catalog = (PROJECT_ROOT / "agents" / "skills" / "catalog.yaml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('["unnecessary", "test"]', catalog)


if __name__ == "__main__":
    unittest.main()
