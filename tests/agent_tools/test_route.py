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
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTE = PROJECT_ROOT / "tools" / "agent_tools" / "route.py"
AGENT_CANON_DEBUG = PROJECT_ROOT / "rust" / "agent-canon" / "target" / "debug" / "agent-canon"


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

    def run_rust_skill_route(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the Rust-backed skill router."""
        if not AGENT_CANON_DEBUG.is_file():
            self.skipTest("Rust agent-canon debug binary is not built")
        return subprocess.run(
            [str(AGENT_CANON_DEBUG), "local-llm", "route-skill", *args],
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

    def test_unknown_legacy_search_alias_fails(self) -> None:
        """Unknown legacy-like search names must not silently resolve."""
        result = self.run_route("--name", "search_legacy.py")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("STATUS=unknown", result.stdout)
        self.assertIn("CANONICAL_AREA=", result.stdout)

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
        self.assertIn("agent-orchestration", decision["active_skills"])
        self.assertIn("task-routing", decision["active_skills"])
        self.assertNotIn("subagent-bootstrap", decision["active_skills"])
        self.assertIn("subagent-bootstrap", decision["deferred_skills"])
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

    def test_prompt_routes_skill_tool_call_coverage_to_log_analysis(self) -> None:
        """Toolcall and Skillcall coverage requests should route to runtime log analysis."""
        result = self.run_route(
            "--prompt",
            "ToolCall と SkillCall が50%くらいなのでルーティング coverage を調査して実装して",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("agent-log-analysis", decision["skills"])
        self.assertIn("agent-log-analysis", decision["matched_skills"])

    def test_prompt_routes_root_design_followup_to_task_routing(self) -> None:
        """Broad follow-up redesign prompts should not fall through to matched=none."""
        result = self.run_route(
            "--prompt",
            "根本の設計から見直してください",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertEqual(decision["mode"], "repo-changing")
        self.assertIn("task-routing", decision["matched_skills"])
        self.assertNotIn("comprehensive-development", decision["matched_skills"])
        self.assertNotIn("change-review", decision["matched_skills"])
        self.assertNotEqual(decision["evidence"], "mode=repo-changing;matched=none")

    def test_prompt_routes_repo_refactor_and_personal_codex_to_structure_refactor(self) -> None:
        """Repo-refactor and ~/.codex boundary prompts should route deterministically."""
        result = self.run_route(
            "--prompt",
            "レポのリファクタスキルを定義して ~/.codex も見て修正して",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertEqual(decision["mode"], "repo-changing")
        self.assertIn("structure-refactor", decision["matched_skills"])
        self.assertIn("structure-refactor", decision["active_skills"])

    def test_repo_refactor_name_alias_routes_to_structure_area(self) -> None:
        """Proposed repo/refactor helper names should not create a new public skill."""
        result = self.run_route("--name", "repo_refactor_skill.py")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CANONICAL_AREA=structure", result.stdout)
        self.assertIn("CANONICAL_SKILL=task-routing", result.stdout)

        slash_result = self.run_route("--name", "repo/refactor")
        self.assertEqual(slash_result.returncode, 0, slash_result.stdout + slash_result.stderr)
        self.assertIn("CANONICAL_AREA=structure", slash_result.stdout)

    def test_structure_review_routes_to_structure_refactor(self) -> None:
        """Structure review weakness should route to the structure refactor skill."""
        result = self.run_route(
            "--prompt",
            "構造のレビュースキルが弱いので見直して",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("structure-refactor", decision["matched_skills"])
        self.assertIn("structure-refactor", decision["active_skills"])

    def test_structure_review_name_alias_routes_to_structure_area(self) -> None:
        """Structure-review aliases should resolve to the structure area."""
        for alias in ("structure-review", "structure-review-skill", "structural-review"):
            with self.subTest(alias=alias):
                result = self.run_route("--name", alias)

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("CANONICAL_AREA=structure", result.stdout)
                self.assertIn("CANONICAL_TOOL=route.py --area structure", result.stdout)

    def test_prompt_routes_contextual_routing_redesign_to_architecture_stack(self) -> None:
        """Routing-context redesign prompts should activate the broader review stack."""
        result = self.run_route(
            "--prompt",
            (
                "スキルとツールのルーティングを根本の設計から見直し、"
                "全体レビューして修正し、構造解析も行う"
            ),
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertEqual(decision["mode"], "repo-changing")
        self.assertIn("task-routing", decision["matched_skills"])
        self.assertIn("comprehensive-development", decision["matched_skills"])
        self.assertIn("structure-planning", decision["matched_skills"])
        self.assertIn("change-review", decision["matched_skills"])
        self.assertNotEqual(decision["evidence"], "mode=repo-changing;matched=none")

    def test_prompt_does_not_route_standalone_toolcall_work_to_log_analysis(self) -> None:
        """Standalone ToolCall implementation text should not imply log analysis."""
        result = self.run_route(
            "--prompt",
            "Implement ToolCall parser support in the runtime adapter",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertNotIn("agent-log-analysis", decision["skills"])
        self.assertNotIn("agent-log-analysis", decision["matched_skills"])

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

    def test_prompt_routes_formatter_adjacent_checks_to_markdown_style(self) -> None:
        """Formatter-adjacent check complaints should route to Markdown style checks."""
        result = self.run_route(
            "--prompt",
            "フォーマッタ系の周辺チェックを通してすらないことが多い",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("md-style-check", decision["skills"])
        self.assertIn("md-style-check", decision["matched_skills"])

    def test_prompt_routes_prose_reasoning_graph(self) -> None:
        """Prose graph requests should route to the public graph skill."""
        result = self.run_route(
            "--prompt",
            "既存文章を文章構造グラフにして段落接続と統合 rewrite packet を作りたい",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("prose-reasoning-graph", decision["skills"])
        self.assertIn("prose-reasoning-graph", decision["matched_skills"])

    def test_prompt_routes_explicit_prose_reasoning_graph(self) -> None:
        """Explicit public graph skill mention should route directly."""
        result = self.run_route(
            "--prompt",
            "$prose-reasoning-graph で既存文章を解析して",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("prose-reasoning-graph", decision["skills"])
        self.assertIn("prose-reasoning-graph", decision["matched_skills"])

    def test_prompt_routes_pr_processing(self) -> None:
        """PR queue work should route to the public PR processing skill."""
        result = self.run_route(
            "--prompt",
            "PRの処理をスキル化して、conflict 解消と Issue triage まで扱って",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("pr-processing", decision["skills"])
        self.assertIn("pr-processing", decision["matched_skills"])

    def test_prompt_routes_unneeded_numerical_tests_to_test_design(self) -> None:
        """Unneeded numerical-test complaints should activate test-design routing."""
        prompt = "不要な数値テストを入れるのをやめさせてください"
        python_result = self.run_route("--prompt", prompt, "--format", "json")
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompt_path = Path(tmp_dir) / "prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            rust_result = self.run_rust_skill_route(
                "--prompt-file",
                str(prompt_path),
                "--format",
                "json",
            )

        self.assertEqual(python_result.returncode, 0, python_result.stdout + python_result.stderr)
        self.assertEqual(rust_result.returncode, 0, rust_result.stdout + rust_result.stderr)
        python_decision = json.loads(python_result.stdout)
        rust_decision = json.loads(rust_result.stdout)
        self.assertIn("test-design", python_decision["matched_skills"])
        self.assertIn("test-design", python_decision["active_skills"])
        self.assertEqual(python_decision["skills"], rust_decision["skills"])
        self.assertEqual(python_decision["active_skills"], rust_decision["active_skills"])
        self.assertEqual(python_decision["matched_skills"], rust_decision["matched_skills"])

    def test_prompt_routes_english_unneeded_numerical_tests_to_test_design(self) -> None:
        """English unneeded numerical-test prompts should match the Rust router."""
        prompt = "Stop adding unnecessary numerical tests; use the test-design gate"
        python_result = self.run_route("--prompt", prompt, "--format", "json")
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompt_path = Path(tmp_dir) / "prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            rust_result = self.run_rust_skill_route(
                "--prompt-file",
                str(prompt_path),
                "--format",
                "json",
            )

        self.assertEqual(python_result.returncode, 0, python_result.stdout + python_result.stderr)
        self.assertEqual(rust_result.returncode, 0, rust_result.stdout + rust_result.stderr)
        python_decision = json.loads(python_result.stdout)
        rust_decision = json.loads(rust_result.stdout)
        self.assertIn("test-design", python_decision["matched_skills"])
        self.assertIn("test-design", python_decision["active_skills"])
        self.assertEqual(python_decision["skills"], rust_decision["skills"])
        self.assertEqual(python_decision["active_skills"], rust_decision["active_skills"])
        self.assertEqual(python_decision["matched_skills"], rust_decision["matched_skills"])

    def test_prompt_skill_route_matches_rust_harness(self) -> None:
        """Python compatibility prompt routing should match the Rust skill router."""
        prompt = (
            "スキルとツールのルーティングを根本の設計から見直し、"
            "マルチエージェントでログのレポートを残す"
        )
        python_result = self.run_route("--prompt", prompt, "--format", "json")
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompt_path = Path(tmp_dir) / "prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            rust_result = self.run_rust_skill_route(
                "--prompt-file",
                str(prompt_path),
                "--format",
                "json",
            )

        self.assertEqual(python_result.returncode, 0, python_result.stdout + python_result.stderr)
        self.assertEqual(rust_result.returncode, 0, rust_result.stdout + rust_result.stderr)
        python_decision = json.loads(python_result.stdout)
        rust_decision = json.loads(rust_result.stdout)
        for key in (
            "route",
            "mode",
            "skills",
            "active_skills",
            "deferred_skills",
            "matched_skills",
        ):
            self.assertEqual(python_decision[key], rust_decision[key], key)

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
