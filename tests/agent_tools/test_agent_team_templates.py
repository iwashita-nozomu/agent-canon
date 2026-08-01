# @dependency-start
# contract test
# responsibility Tests agent team template rendering behavior.
# upstream design ../../templates/agents/README.md template partial contract
# downstream implementation ../../tools/agent_tools/manifest_rendering.py renders templates and partials
# downstream implementation ../../tools/agent_tools/agent_team.py owns facade orchestration
# @dependency-end

"""Tests for run artifact template rendering."""

from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from implementation_dispatch import dispatch_fixed_implementation  # noqa: E402
from manifest_rendering import render_template, suggested_public_skills  # noqa: E402
from packets import resolve_active_design_packet_config  # noqa: E402
from team_config import load_team_config  # noqa: E402


class AgentTeamTemplateTest(unittest.TestCase):
    """Verify reusable template partial expansion."""

    def test_active_design_packet_normalizer_rejects_unknown_mapping_fields(
        self,
    ) -> None:
        """Workflow and config mappings share the closed packet field set."""
        config = load_team_config()
        base_packet = config.artifact_registry["active_design_packet"]
        self.assertIsInstance(base_packet, dict)
        packet_with_unknown = {
            **base_packet,
            "unexpected_contract": True,
        }

        with self.assertRaisesRegex(
            RuntimeError,
            r"^workflow_family\.active_design_packet:field_unknown:unexpected_contract$",
        ):
            resolve_active_design_packet_config(
                config,
                {"active_design_packet": packet_with_unknown},
            )

        config_with_unknown = replace(
            config,
            artifact_registry={
                **config.artifact_registry,
                "active_design_packet": packet_with_unknown,
            },
        )
        with self.assertRaisesRegex(
            RuntimeError,
            r"^artifacts\.active_design_packet:field_unknown:unexpected_contract$",
        ):
            resolve_active_design_packet_config(config_with_unknown)

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

    def test_fixed_implementation_dispatch_uses_typed_route_and_registry_prompt(
        self,
    ) -> None:
        """Malformed fixed packets fail closed at the owner dispatch boundary."""
        calls: list[tuple[str, str]] = []
        dispatch = dispatch_fixed_implementation(
            {"fixed_implementation_packet": {"packet_id": "P3"}},
            "materialize P3",
            lambda role, prompt: calls.append((role, prompt)) or "spark-1",
            workspace_root=PROJECT_ROOT,
        )
        self.assertEqual(dispatch.status, "blocked")
        self.assertEqual(dispatch.spawn_count, 0)
        self.assertEqual(dispatch.worker_agent_id, None)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
