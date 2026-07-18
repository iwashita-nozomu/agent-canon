# @dependency-start
# contract test
# responsibility Tests agent team template rendering behavior.
# upstream design ../../agents/templates/README.md template partial contract
# downstream implementation ../../tools/agent_tools/agent_team.py renders templates and partials
# @dependency-end

"""Tests for run artifact template rendering."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

import agent_team  # noqa: E402
from agent_team import render_template, suggested_public_skills  # noqa: E402
from tools.agent_tools import implementation_route  # noqa: E402


class AgentTeamTemplateTest(unittest.TestCase):
    """Verify reusable template partial expansion."""

    def test_review_template_expands_partials_and_replacements(self) -> None:
        """Rendered review artifacts should contain expanded tables and run metadata."""
        rendered = render_template(
            "artifact_review.md",
            {
                "RUN_ID": "test-run",
                "TASK": "template refactor",
                "OWNER": "codex",
                "CREATED_AT": "2026-05-24T00:00:00Z",
            },
        )

        self.assertNotIn("{{>", rendered)
        self.assertIn("- Run ID: test-run", rendered)
        self.assertIn("- Task: template refactor", rendered)
        self.assertIn("| Finding | Severity | Required Change | Evidence | Status |", rendered)
        self.assertEqual(rendered.count("@dependency-start"), 1)

    def test_decision_partial_expands_without_manifest_leak(self) -> None:
        """Decision partials should render as normal sections inside top-level templates."""
        rendered = render_template(
            "research_review.md",
            {
                "RUN_ID": "test-run",
                "TASK": "research review",
                "OWNER": "codex",
                "CREATED_AT": "2026-05-24T00:00:00Z",
            },
        )

        self.assertNotIn("{{>", rendered)
        self.assertIn("## Decision", rendered)
        self.assertIn("<!-- Record approve, revise, or escalate. -->", rendered)
        self.assertEqual(rendered.count("@dependency-start"), 1)

    def test_research_driven_skill_calls_literature_survey_first(self) -> None:
        """Research-driven run bundles should call literature-survey before research-workflow."""
        skills = suggested_public_skills(None, "research_driven_change")

        self.assertIn("$literature-survey", skills)
        self.assertIn("$research-workflow", skills)
        self.assertLess(
            skills.index("$literature-survey"),
            skills.index("$research-workflow"),
        )

    def test_fixed_implementation_dispatch_uses_typed_route_and_registry_prompt(self) -> None:
        """Eligible implementation dispatch launches one Spark and one owning gate."""
        result = implementation_route.ImplementationRouteResult(
            result_version=1,
            decision_ref="decision:P3",
            selected_agent_type="spark_worker",
            selected_profile_id="spark_implementation_low",
            packet_ref="packet:P3",
            packet_sha256="a" * 64,
            capacity_action="reserve_on_successful_spawn",
            resume_worker_agent_id=None,
            next_gate="implementation_route_gate",
            failure=None,
            status="completed",
        )
        original = agent_team.implementation_route.route_implementation
        calls: list[tuple[str, str]] = []
        agent_team.implementation_route.route_implementation = lambda request: result
        try:
            dispatch = agent_team.dispatch_fixed_implementation(
                {"fixed_implementation_packet": {"packet_id": "P3"}},
                "materialize P3",
                lambda role, prompt: calls.append((role, prompt)) or "spark-1",
                workspace_root=PROJECT_ROOT,
            )
        finally:
            agent_team.implementation_route.route_implementation = original
        self.assertEqual(dispatch.status, "spawned")
        self.assertEqual(dispatch.spawn_count, 1)
        self.assertEqual(dispatch.owner_gate_count, 1)
        self.assertEqual(dispatch.worker_agent_id, "spark-1")
        self.assertEqual(calls[0][0], "spark_worker")
        self.assertIn("SPARK::", calls[0][1])
        self.assertEqual(
            dispatch.close_agent_token.arguments,
            {"terminal_agent_id": "spark-1"},
        )


if __name__ == "__main__":
    unittest.main()
