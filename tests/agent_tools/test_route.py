"""Tests for the short task routing helper."""

# @dependency-start
# contract test
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
AGENT_CANON_CLI = PROJECT_ROOT / "tools" / "bin" / "agent-canon"


class RouteToolTest(unittest.TestCase):
    """Exercise route.py output and routing aliases."""

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
        result = self.run_route(
            "--area", "checks", "--risk", "focused", "--changed", "README.md"
        )

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

    def test_prompt_routes_related_skill_candidates_without_activating(self) -> None:
        """Related skill metadata should guide later waves without expanding active skills."""
        result = self.run_route(
            "--prompt",
            "スキルが重いので分割し、関連スキルを明示して実行時に適切なスキルを使う",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("task-routing", decision["matched_skills"])
        self.assertIn("task-routing", decision["active_skills"])
        self.assertIn("owner-bounded-routing", decision["related_skill_candidates"])
        self.assertNotIn("owner-bounded-routing", decision["active_skills"])
        self.assertIn("task-routing", decision["related_skills"])
        self.assertIn(
            "owner-bounded-routing", decision["related_skills"]["task-routing"]
        )

    def test_prompt_routes_repo_owned_tool_routing_feedback(self) -> None:
        """Repo-owned tool routing feedback should activate task-routing."""
        result = self.run_route(
            "--prompt",
            (
                "レポ内の自作ツールへの自動ルーティングが全くされません。"
                "ツールを逐次呼ぶこととスキルの動的ルーティングも直して。"
            ),
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("task-routing", decision["matched_skills"])
        self.assertIn("task-routing", decision["active_skills"])
        self.assertIn("tool-finding-report", decision["related_skill_candidates"])
        self.assertIn("agent-log-analysis", decision["related_skill_candidates"])

    def test_prompt_routes_code_visualization_selection(self) -> None:
        """Code visualization prompts should enter the diagram selector skill."""
        prompts = (
            (
                "コードの可視化にはフローチャート、コールグラフ、制御フローグラフ、"
                "シーケンス図、状態遷移図、データフロー図、依存関係図、"
                "タイミング図など色々な図示があるので適切に選択して"
            ),
            "HTML dashboardでコードの依存グラフを見たい",
            "文書に埋め込む図も文脈から適切に選んで",
            "READMEのvisual_planにMermaid図を入れる",
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result = self.run_route("--prompt", prompt, "--format", "json")

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                decision = json.loads(result.stdout)
                self.assertIn("code-visualization", decision["matched_skills"])
                self.assertIn("code-visualization", decision["active_skills"])
                self.assertIn(
                    "dependency-analysis", decision["related_skill_candidates"]
                )
                self.assertIn(
                    "structure-planning", decision["related_skill_candidates"]
                )
                self.assertIn(
                    "algorithm-flowchart", decision["related_skill_candidates"]
                )
                self.assertIn("html-output", decision["related_skill_candidates"])
                self.assertIn("md-style-check", decision["related_skill_candidates"])
                self.assertNotEqual(
                    decision["evidence"], "mode=repo-changing;matched=none"
                )

    def test_prompt_file_routes_through_python_owner(self) -> None:
        """Prompt files should use the Python routing owner."""
        prompt = "スキルとツールのルーティングが遅すぎるので改善して"
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompt_path = Path(tmp_dir) / "prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            python_result = self.run_route(
                "--prompt-file",
                str(prompt_path),
                "--format",
                "json",
            )

        self.assertEqual(
            python_result.returncode, 0, python_result.stdout + python_result.stderr
        )
        python_decision = json.loads(python_result.stdout)
        self.assertEqual(python_decision["schema"], "agent_canon.route.skill_route.v1")
        self.assertIn("task-routing", python_decision["active_skills"])
        for key in ("skills", "active_skills", "deferred_skills", "matched_skills"):
            self.assertIn(key, python_decision)

    def test_prompt_routes_old_tool_document_cleanup(self) -> None:
        """Old tool and document cleanup requests should enter document-canon cleanup."""
        result = self.run_route(
            "--prompt", "古いツール，文書の掃除を", "--format", "json"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("document-canon-cleanup", decision["matched_skills"])
        self.assertIn("document-canon-cleanup", decision["active_skills"])
        self.assertNotEqual(decision["evidence"], "mode=repo-changing;matched=none")

    def test_prompt_routes_gpu_execution(self) -> None:
        """GPU execution prompts should activate the managed GPU execution skill."""
        result = self.run_route(
            "--prompt",
            "Python実行はExperimentRunnerに移譲し，GPU利用では先取無効を追加して実行",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("gpu-execution", decision["matched_skills"])
        self.assertIn("gpu-execution", decision["active_skills"])
        self.assertIn("experiment-lifecycle", decision["related_skill_candidates"])
        self.assertIn("computational-optimization", decision["related_skill_candidates"])

    def test_prompt_routes_codex_report_document_repo_optimization(self) -> None:
        """Codex report and document based repo optimization should not fall through."""
        result = self.run_route(
            "--prompt",
            "Codexのレポとか文書とか見ながら，ここのレポの最適化を行ってください",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        for skill in (
            "agent-log-analysis",
            "document-canon-cleanup",
            "structure-refactor",
        ):
            self.assertIn(skill, decision["matched_skills"])
            self.assertIn(skill, decision["active_skills"])
        self.assertIn("report-writing", decision["related_skill_candidates"])
        self.assertNotEqual(decision["evidence"], "mode=repo-changing;matched=none")

    def test_prompt_routes_explicit_reader_report_to_report_writing(self) -> None:
        """Explicit reader-facing report requests should activate report-writing."""
        result = self.run_route(
            "--prompt",
            "評価レポートを作り，source packet と limitations を含めて",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("report-writing", decision["matched_skills"])
        self.assertIn("report-writing", decision["active_skills"])
        self.assertIn("structure-planning", decision["related_skill_candidates"])
        self.assertIn("result-artifact-writeout", decision["related_skill_candidates"])

    def test_legacy_local_llm_route_skill_alias_is_removed(self) -> None:
        """The shell wrapper must not preserve a local-llm route-skill alias."""
        result = subprocess.run(
            [
                str(AGENT_CANON_CLI),
                "local-llm",
                "route-skill",
                "--prompt",
                "x",
                "--format",
                "json",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn(
            "LOCAL_LLM_CLI_ERROR=unknown local-llm command route-skill", result.stderr
        )

    def test_prompt_router_rejects_private_skill_in_public_catalog(self) -> None:
        """Underscore-prefixed skills are private and stay out of public routing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog = root / "agents" / "skills" / "catalog.yaml"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(
                "\n".join(
                    [
                        "version: 1",
                        "skill_families:",
                        "  - id: _private-skill",
                        "    purpose: Private skill.",
                        "    canonical_doc: agents/skills/_private-skill.md",
                        "    shim: .agents/skills/_private-skill/SKILL.md",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_route(
                "--root",
                str(root),
                "--prompt",
                "private skill",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("must be public", result.stderr)

    def test_prompt_routes_skill_visibility_naming_to_task_routing(self) -> None:
        """Skill visibility naming requests belong to the routing skill surface."""
        prompt = "UserFacingなスキルとそうでないものを命名で分ける。private skill は _ 始まりにする"
        result = self.run_route("--prompt", prompt, "--format", "json")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("task-routing", decision["matched_skills"])
        self.assertIn("task-routing", decision["active_skills"])

    def test_prompt_routes_official_skill_delegation_to_task_routing(self) -> None:
        """Official skill delegation prompts should enter the deterministic router."""
        prompt = "公式スキルで賄えるところを移譲して"
        python_result = self.run_route(
            "--prompt",
            prompt,
            "--mode",
            "routing-only",
            "--format",
            "json",
        )

        self.assertEqual(
            python_result.returncode, 0, python_result.stdout + python_result.stderr
        )
        python_decision = json.loads(python_result.stdout)
        self.assertEqual(python_decision["mode"], "repo-changing")
        self.assertIn("task-routing", python_decision["matched_skills"])
        self.assertIn("task-routing", python_decision["active_skills"])
        self.assertNotEqual(
            python_decision["evidence"], "mode=repo-changing;matched=none"
        )

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
        prompts = (
            "ToolCall と SkillCall が50%くらいなのでルーティング coverage を調査して実装して",
            "ログを確認して，スキル修正",
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result = self.run_route("--prompt", prompt, "--format", "json")

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                decision = json.loads(result.stdout)
                self.assertIn("agent-log-analysis", decision["skills"])
                self.assertIn("agent-log-analysis", decision["matched_skills"])
                self.assertIn("agent-log-analysis", decision["active_skills"])

    def test_prompt_routes_missed_skill_invocation_feedback(self) -> None:
        """Missed skill feedback should reach routing, log analysis, and learning surfaces."""
        result = self.run_route(
            "--prompt",
            "適切にスキルが呼ばれないです．関連スキルの記述を絞りすぎ",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        for skill in ("task-routing", "agent-log-analysis", "agent-learning"):
            self.assertIn(skill, decision["matched_skills"])
            self.assertIn(skill, decision["skills"])
        self.assertIn("task-routing", decision["active_skills"])
        self.assertIn("agent-log-analysis", decision["active_skills"])
        self.assertIn("agent-learning", decision["deferred_skills"])
        self.assertIn("issue-finding-report", decision["related_skill_candidates"])
        self.assertIn("result-artifact-writeout", decision["related_skill_candidates"])
        self.assertNotEqual(decision["evidence"], "mode=repo-changing;matched=none")

    def test_prompt_routes_source_file_order_feedback(self) -> None:
        """Source file order feedback should reach bounded and Python review routes."""
        result = self.run_route(
            "--prompt",
            "コードファイル内の順序がわかりにくいです",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("owner-bounded-routing", decision["matched_skills"])
        self.assertIn("owner-bounded-routing", decision["active_skills"])
        self.assertIn("python-review", decision["matched_skills"])
        self.assertIn("python-review", decision["deferred_skills"])
        self.assertNotEqual(decision["evidence"], "mode=repo-changing;matched=none")

    def test_prompt_routes_adaptive_improvement_loop_from_iterative_work(self) -> None:
        """Iterative execution and tuning prompts should activate adaptive loop routing."""
        prompts = (
            "反復実行系のスキルがうまく作動してない。原因を探して",
            (
                "experiments research tuning iterative code improvement "
                "managed as one backlog-driven agile outer loop"
            ),
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                python_result = self.run_route("--prompt", prompt, "--format", "json")

                self.assertEqual(
                    python_result.returncode,
                    0,
                    python_result.stdout + python_result.stderr,
                )
                python_decision = json.loads(python_result.stdout)
                self.assertIn("adaptive-improvement-loop", python_decision["skills"])
                self.assertIn(
                    "adaptive-improvement-loop", python_decision["matched_skills"]
                )
                self.assertIn(
                    "adaptive-improvement-loop", python_decision["active_skills"]
                )
                self.assertNotEqual(
                    python_decision["evidence"], "mode=repo-changing;matched=none"
                )

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

    def test_prompt_routes_agent_growth_responsibility_migration(self) -> None:
        """Agent-growth responsibility migration should route to repair skills."""
        prompt = (
            "エージェントの成長のために欠落しているスキル・動線，ツールを探索して実装し，"
            "AGENTS.md と skill の重複を削って skill 側へ責務移行する"
        )
        python_result = self.run_route("--prompt", prompt, "--format", "json")

        self.assertEqual(
            python_result.returncode, 0, python_result.stdout + python_result.stderr
        )
        python_decision = json.loads(python_result.stdout)
        for skill in (
            "task-routing",
            "agent-log-analysis",
            "structure-refactor",
            "comprehensive-development",
            "agent-learning",
        ):
            self.assertIn(skill, python_decision["matched_skills"])
            self.assertIn(skill, python_decision["skills"])
        self.assertIn("task-routing", python_decision["active_skills"])
        self.assertIn("agent-log-analysis", python_decision["active_skills"])
        self.assertIn("structure-refactor", python_decision["active_skills"])
        self.assertIn("comprehensive-development", python_decision["deferred_skills"])
        self.assertIn("agent-learning", python_decision["deferred_skills"])
        self.assertNotEqual(
            python_decision["evidence"], "mode=repo-changing;matched=none"
        )

    def test_prompt_routes_repo_wide_responsibility_deduplication(self) -> None:
        """Repo-wide over-splitting and responsibility overlap should route to structure repair."""
        prompt = "レポ全体をレビューしながら過剰分割，責務重複を排除してください"
        python_result = self.run_route("--prompt", prompt, "--format", "json")

        self.assertEqual(
            python_result.returncode, 0, python_result.stdout + python_result.stderr
        )
        python_decision = json.loads(python_result.stdout)
        self.assertIn("structure-refactor", python_decision["matched_skills"])
        self.assertIn("structure-refactor", python_decision["active_skills"])
        self.assertIn("comprehensive-development", python_decision["matched_skills"])
        self.assertIn("comprehensive-development", python_decision["deferred_skills"])
        self.assertNotEqual(
            python_decision["evidence"], "mode=repo-changing;matched=none"
        )

    def test_prompt_routes_settings_skill_duplicate_management(self) -> None:
        """Settings and skill duplicate-management prompts should not fall through."""
        prompts = (
            "設定，スキルの二重管理を洗い出して，修正してください",
            ".codex/.agents と skill catalog の ownership を直して",
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result = self.run_route("--prompt", prompt, "--format", "json")

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                decision = json.loads(result.stdout)
                for skill in (
                    "task-routing",
                    "structure-refactor",
                    "agent-canon-update",
                ):
                    self.assertIn(skill, decision["matched_skills"])
                    self.assertIn(skill, decision["active_skills"])
                self.assertNotEqual(
                    decision["evidence"], "mode=repo-changing;matched=none"
                )

    def test_prompt_routes_all_skill_tool_command_repair(self) -> None:
        """All-skill command packet repair should not fall through."""
        prompt = (
            "スキル内で明示的にツールの起動コマンドが書いていないから，"
            "ミスることが多発しています．すべてのスキルを修正してください"
        )
        python_result = self.run_route("--prompt", prompt, "--format", "json")

        self.assertEqual(
            python_result.returncode, 0, python_result.stdout + python_result.stderr
        )
        python_decision = json.loads(python_result.stdout)
        for skill in (
            "task-routing",
            "structure-refactor",
            "comprehensive-development",
            "agent-learning",
        ):
            self.assertIn(skill, python_decision["matched_skills"])
            self.assertIn(skill, python_decision["skills"])
        self.assertIn("task-routing", python_decision["active_skills"])
        self.assertIn("structure-refactor", python_decision["active_skills"])
        self.assertIn("comprehensive-development", python_decision["deferred_skills"])
        self.assertIn("agent-learning", python_decision["deferred_skills"])
        self.assertNotEqual(
            python_decision["evidence"], "mode=repo-changing;matched=none"
        )

    def test_prompt_routes_repo_refactor_and_personal_codex_to_structure_refactor(
        self,
    ) -> None:
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
        self.assertEqual(
            slash_result.returncode, 0, slash_result.stdout + slash_result.stderr
        )
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
        for alias in (
            "structure-review",
            "structure-review-skill",
            "structural-review",
        ):
            with self.subTest(alias=alias):
                result = self.run_route("--name", alias)

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("CANONICAL_AREA=structure", result.stdout)
                self.assertIn("CANONICAL_TOOL=route.py --area structure", result.stdout)

    def test_prompt_routes_contextual_routing_redesign_to_architecture_stack(
        self,
    ) -> None:
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

    def test_prompt_does_not_route_standalone_toolcall_work_to_log_analysis(
        self,
    ) -> None:
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

    def test_prompt_route_invalid_catalog_fails_structured(self) -> None:
        """Invalid catalog routing should return a structured router error."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog = root / "agents" / "skills" / "catalog.yaml"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(
                "\n".join(
                    [
                        "version: 1",
                        "skill_families:",
                        "  - id: task-routing",
                        "    routing:",
                        "      stage_policy: someday",
                        "      reason: bad fixture",
                    ]
                ),
                encoding="utf-8",
            )
            result = self.run_route(
                "--root",
                str(root),
                "--prompt",
                "routing",
                "--format",
                "json",
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("SKILL_ROUTER_ERROR=", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_prompt_route_malformed_catalog_yaml_fails_structured(self) -> None:
        """Malformed catalog YAML should return a structured router error."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog = root / "agents" / "skills" / "catalog.yaml"
            catalog.parent.mkdir(parents=True)
            catalog.write_text("skill_families: [unterminated\n", encoding="utf-8")
            result = self.run_route(
                "--root",
                str(root),
                "--prompt",
                "routing",
                "--format",
                "json",
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("SKILL_ROUTER_ERROR=", result.stderr)
        self.assertIn("YAML parse failed", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_prompt_route_duplicate_catalog_skill_fails_structured(self) -> None:
        """Duplicate catalog skill IDs should fail before route selection."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog = root / "agents" / "skills" / "catalog.yaml"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(
                "\n".join(
                    [
                        "version: 1",
                        "skill_families:",
                        "  - id: task-routing",
                        "  - id: task-routing",
                    ]
                ),
                encoding="utf-8",
            )
            result = self.run_route(
                "--root",
                str(root),
                "--prompt",
                "routing",
                "--format",
                "json",
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "SKILL_ROUTER_ERROR=duplicate skill catalog id: task-routing", result.stderr
        )
        self.assertNotIn("Traceback", result.stderr)

    def test_prompt_route_unknown_related_skill_fails_structured(self) -> None:
        """Related skill metadata should reference public catalog entries."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog = root / "agents" / "skills" / "catalog.yaml"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(
                "\n".join(
                    [
                        "version: 1",
                        "skill_families:",
                        "  - id: task-routing",
                        "    related_skills:",
                        "      - missing-skill",
                    ]
                ),
                encoding="utf-8",
            )
            result = self.run_route(
                "--root",
                str(root),
                "--prompt",
                "routing",
                "--format",
                "json",
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "task-routing.related_skills unknown skill: missing-skill", result.stderr
        )
        self.assertNotIn("Traceback", result.stderr)

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

    def test_prompt_routes_pr_skill_scan_routing_refactor(self) -> None:
        """PR intake followed by skill scan and routing refactor should not fall through."""
        prompt = (
            "PRをすべて取り込み、その後、Skillを一つずつ走査し"
            "ルーティングも含めてリファクタリング。実装時の抽象化不足も修正対象。"
        )
        python_result = self.run_route("--prompt", prompt, "--format", "json")

        self.assertEqual(
            python_result.returncode, 0, python_result.stdout + python_result.stderr
        )
        python_decision = json.loads(python_result.stdout)
        for skill in ("task-routing", "pr-processing", "refactor-loop"):
            self.assertIn(skill, python_decision["matched_skills"])
            self.assertIn(skill, python_decision["active_skills"])
        self.assertNotEqual(
            python_decision["evidence"], "mode=repo-changing;matched=none"
        )

    def test_prompt_routes_unneeded_numerical_tests_to_test_design(self) -> None:
        """Unneeded numerical-test complaints should activate test-design routing."""
        prompt = "不要な数値テストを入れるのをやめさせてください"
        python_result = self.run_route("--prompt", prompt, "--format", "json")

        self.assertEqual(
            python_result.returncode, 0, python_result.stdout + python_result.stderr
        )
        python_decision = json.loads(python_result.stdout)
        self.assertIn("test-design", python_decision["matched_skills"])
        self.assertIn("test-design", python_decision["active_skills"])

    def test_prompt_routes_english_unneeded_numerical_tests_to_test_design(
        self,
    ) -> None:
        """English unneeded numerical-test prompts should route to test design."""
        prompt = "Stop adding unnecessary numerical tests; use the test-design gate"
        python_result = self.run_route("--prompt", prompt, "--format", "json")

        self.assertEqual(
            python_result.returncode, 0, python_result.stdout + python_result.stderr
        )
        python_decision = json.loads(python_result.stdout)
        self.assertIn("test-design", python_decision["matched_skills"])
        self.assertIn("test-design", python_decision["active_skills"])

    def test_prompt_skill_route_schema_and_wave_fields(self) -> None:
        """Prompt routing should emit the route-owned schema and wave fields."""
        prompt = (
            "スキルとツールのルーティングを根本の設計から見直し、"
            "マルチエージェントでログのレポートを残す"
        )
        python_result = self.run_route("--prompt", prompt, "--format", "json")

        self.assertEqual(
            python_result.returncode, 0, python_result.stdout + python_result.stderr
        )
        python_decision = json.loads(python_result.stdout)
        self.assertEqual(python_decision["schema"], "agent_canon.route.skill_route.v1")
        self.assertEqual(python_decision["route"], "skill-selection")
        for key in ("active_skills", "deferred_skills", "matched_skills"):
            self.assertIsInstance(python_decision[key], list)

    def test_unknown_name_fails_closed(self) -> None:
        """Unknown aliases should be explicit failures."""
        result = self.run_route("--name", "unknown_super_router.py")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("STATUS=unknown", result.stdout)

    def test_unknown_markdown_does_not_suggest_skill(self) -> None:
        """Markdown output should not imply a canonical skill for unknown names."""
        result = self.run_route(
            "--name", "unknown_super_router.py", "--format", "markdown"
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "| `unknown_super_router.py` | `unknown` | `` | `` | `` |", result.stdout
        )

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
