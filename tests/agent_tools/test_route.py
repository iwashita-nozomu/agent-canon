"""Tests for the short task routing helper."""

# @dependency-start
# responsibility Tests short task routing helper behavior.
# upstream implementation ../../tools/agent_tools/route.py selects short tool and skill routes
# upstream design ../../documents/tool-skill-routing-refactor.md defines naming policy
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTE = PROJECT_ROOT / "tools" / "agent_tools" / "route.py"


class RouteToolTest(unittest.TestCase):
    """Exercise route.py output and compatibility aliases."""

    def run_route(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run route.py with arguments."""
        return subprocess.run(
            [sys.executable, str(ROUTE), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_area_outputs_short_tool_and_skill(self) -> None:
        """Area routing should keep names short and machine-readable."""
        result = self.run_route("--area", "checks", "--risk", "focused", "--changed", "README.md")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ROUTE=task-routing", result.stdout)
        self.assertIn("AREA=checks", result.stdout)
        self.assertIn("TOOL=route.py", result.stdout)
        self.assertIn("SKILL=task-routing", result.stdout)
        self.assertIn("COMMANDS=make check-matrix", result.stdout)
        self.assertIn("changed=README.md", result.stdout)

    def test_long_proposed_tool_name_resolves_to_short_area(self) -> None:
        """Long candidate-list tool names should become aliases."""
        result = self.run_route("--name", "profile_surface_resolver.py")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("STATUS=alias", result.stdout)
        self.assertIn("CANONICAL_AREA=surface", result.stdout)
        self.assertIn("CANONICAL_TOOL=route.py --area surface", result.stdout)
        self.assertIn("CANONICAL_SKILL=task-routing", result.stdout)

    def test_long_proposed_skill_name_resolves_to_task_routing(self) -> None:
        """Long candidate-list skill names should become aliases."""
        result = self.run_route("--name", "$runtime-capability-routing")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CANONICAL_AREA=runtime", result.stdout)
        self.assertIn("CANONICAL_SKILL=task-routing", result.stdout)

    def test_search_area_exposes_coordinated_search_tools(self) -> None:
        """Search routing should expose the purpose-based search entrypoint."""
        result = self.run_route("--area", "search", "--risk", "focused")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AREA=search", result.stdout)
        self.assertIn("NEXT_ACTION=run_coordinated_search", result.stdout)
        self.assertIn("agent-canon local-llm search --purpose", result.stdout)
        self.assertIn("agent-canon local-llm build-index", result.stdout)

    def test_search_alias_resolves_to_search_area(self) -> None:
        """Legacy vector-search names should route to coordinated search."""
        result = self.run_route("--name", "vector_search.py")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CANONICAL_AREA=search", result.stdout)
        self.assertIn("CANONICAL_TOOL=route.py --area search", result.stdout)

    def test_prompt_routes_repo_changing_skill_set(self) -> None:
        """Prompt routing should expose concrete public skills, not only area aliases."""
        result = self.run_route(
            "--prompt",
            (
                "スキル選択ルーティングも含めて修正してください。"
                "マルチエージェントでログのレポートを残す。"
            ),
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertEqual(decision["route"], "skill-selection")
        self.assertEqual(decision["mode"], "repo-changing")
        self.assertEqual(decision["skills"][0], "agent-orchestration")
        self.assertIn("codex-task-workflow", decision["skills"])
        self.assertIn("subagent-bootstrap", decision["skills"])
        self.assertIn("agent-orchestration", decision["matched_skills"])
        self.assertIn("result-artifact-writeout", decision["matched_skills"])

    def test_prompt_routes_agent_learning_and_oop_readability(self) -> None:
        """Weak historical skill surfaces should be recommended from contextual prompts."""
        result = self.run_route(
            "--prompt",
            "こういう止まり方の再発防止と OOP readability check を見直す",
            "--mode",
            "routing-only",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertEqual(decision["mode"], "repo-changing")
        self.assertIn("agent-learning", decision["skills"])
        self.assertIn("oop-readability-check", decision["skills"])

    def test_prompt_routes_plain_public_skill_names(self) -> None:
        """Plain public skill ids in user text should count as explicit skill routing."""
        result = self.run_route(
            "--prompt",
            "md-style-check と agent-learning の routing gap を直して",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("md-style-check", decision["skills"])
        self.assertIn("agent-learning", decision["skills"])
        self.assertIn("md-style-check", decision["matched_skills"])
        self.assertIn("agent-learning", decision["matched_skills"])

    def test_unknown_name_fails_closed(self) -> None:
        """Unknown aliases should be explicit failures."""
        result = self.run_route("--name", "unknown_super_router.py")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("STATUS=unknown", result.stdout)

    def test_unknown_markdown_does_not_suggest_skill(self) -> None:
        """Markdown output should not imply a canonical skill for unknown names."""
        result = self.run_route("--name", "unknown_super_router.py", "--format", "markdown")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("| `unknown_super_router.py` | `unknown` | `` | `` | `` |", result.stdout)

    def test_json_list_is_parseable(self) -> None:
        """JSON list output should be usable by other tools."""
        result = self.run_route("--list", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = json.loads(result.stdout)
        areas = {row["key"] for row in rows}
        self.assertIn("checks", areas)
        self.assertIn("search", areas)
        self.assertIn("surface", areas)


if __name__ == "__main__":
    unittest.main()
