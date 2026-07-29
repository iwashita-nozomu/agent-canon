"""Tests for the short task routing helper."""

# @dependency-start
# contract test
# responsibility Tests short task routing helper behavior and explicit capability owner partitions.
# upstream implementation ../../tools/agent_tools/route.py selects short tool and skill routes
# upstream implementation ../../tools/agent_tools/skill_route_catalog.py owns catalog/rule/index behavior
# upstream implementation ../../tools/agent_tools/capability_route.py owns capability preflight/decision behavior
# upstream implementation ../../tools/agent_tools/visualization_contract.py owns exact ToolCall validation
# upstream design ../../documents/design/tool-skill-routing-refactor.md defines naming policy
# upstream design ../../.agents/skills/code-visualization/SKILL.md owns the runtime direct-route text
# upstream design ../../agents/skills/code-visualization.md owns the canonical direct-route contract
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTE = PROJECT_ROOT / "tools" / "agent_tools" / "route.py"
AGENT_CANON_CLI = PROJECT_ROOT / "tools" / "bin" / "agent-canon"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
import agent_canon_source_root  # noqa: E402
import capability_route as capability_module  # noqa: E402
import route as route_module  # noqa: E402
import skill_route_catalog as catalog_module  # noqa: E402


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

    def run_route_from_cwd(
        self,
        cwd: Path,
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        """Run route.py from a given working directory."""
        return subprocess.run(
            [sys.executable, str(ROUTE), *args],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
        )

    def visualization_tool_call(
        self,
        *,
        tool_id: str = "agent_canon.visualization.coverage",
        argument_schema: str = "agent_canon.visualization.arguments.coverage.v1",
    ) -> dict[str, object]:
        """Return one complete schema-bearing visualization ToolCall fixture."""
        literal_item = {
            "item_id": "literal-route-item",
            "kind": "identity",
            "origin": "literal_request",
            "source_locator": "route:test",
            "source_start": None,
            "source_end": None,
            "ordinal": 0,
            "payload_json": "{}",
        }
        arguments: dict[str, object] = {
            "request_id": "route-test-request",
            "literal_request": "explicit route fixture",
            "literal_items": [literal_item],
            "owner_closure": [],
            "dependency_closure": [],
            "artifact_id": "route-test-artifact",
            "renderer_id": "route-test-renderer",
            "artifact_format": "graph_ir",
        }
        if tool_id == "agent_canon.visualization.adapter.dependency_manifest":
            arguments["dependency_manifest_locator"] = "reports/dependency_graph.tsv"
        return {
            "schema": "agent_canon.visualization_tool_call.v1",
            "tool_id": tool_id,
            "argument_schema": argument_schema,
            "arguments": arguments,
        }

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

    def test_route_resolves_standalone_source_root(self) -> None:
        """Prompt mode resolves standalone AgentCanon sources from parent and child dirs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").touch()
            (root / "agents" / "skills").mkdir(parents=True, exist_ok=True)
            (root / "agents" / "skills" / "catalog.yaml").write_text(
                "version: 1\nskill_families: []\n",
                encoding="utf-8",
            )
            (root / "agents" / "skills" / "skill-dependencies.yaml").write_text(
                "version: 1\nskill_dependencies: {}\n",
                encoding="utf-8",
            )
            child = root / "workspace" / "subdir"
            child.mkdir(parents=True, exist_ok=True)
            standalone_child = root / "agents" / "standalone" / "child"
            standalone_child.mkdir(parents=True, exist_ok=True)

            for root_candidate in (root, child):
                result = self.run_route(
                    "--root",
                    str(root_candidate),
                    "--prompt",
                    "小さなルーティング改善を提案してください",
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_route_resolves_standalone_from_cwd(self) -> None:
        """Prompt mode resolves from parent root, any child dir, and standalone child dirs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").touch()
            (root / "agents" / "skills").mkdir(parents=True, exist_ok=True)
            (root / "agents" / "skills" / "catalog.yaml").write_text(
                "version: 1\nskill_families: []\n",
                encoding="utf-8",
            )
            (root / "agents" / "skills" / "skill-dependencies.yaml").write_text(
                "version: 1\nskill_dependencies: {}\n",
                encoding="utf-8",
            )
            parent_child = root / "workspace" / "subdir"
            parent_child.mkdir(parents=True, exist_ok=True)
            standalone_child = root / "agents" / "standalone" / "child"
            standalone_child.mkdir(parents=True, exist_ok=True)

            for cwd in (root, parent_child, standalone_child):
                result = self.run_route_from_cwd(
                    cwd,
                    "--prompt",
                    "小さなルーティング改善を提案してください",
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_route_resolves_vendored_source_root(self) -> None:
        """Prompt mode resolves vendored AgentCanon sources when standalone is absent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "vendor" / "agent-canon"
            (root / "agents" / "skills").mkdir(parents=True, exist_ok=True)
            (root / "agents" / "skills" / "catalog.yaml").write_text(
                "version: 1\nskill_families: []\n",
                encoding="utf-8",
            )
            (root / "agents" / "skills" / "skill-dependencies.yaml").write_text(
                "version: 1\nskill_dependencies: {}\n",
                encoding="utf-8",
            )

            result = self.run_route(
                "--root",
                str(root.parent.parent),
                "--prompt",
                "小さなルーティング改善を提案してください",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_route_resolves_vendored_from_cwd(self) -> None:
        """Prompt mode resolves vendored sources from multiple cwd under the parent root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent_root = Path(tmp_dir)
            (parent_root / ".git").touch()
            root = parent_root / "vendor" / "agent-canon"
            (root / "agents" / "skills").mkdir(parents=True, exist_ok=True)
            (root / "agents" / "skills" / "catalog.yaml").write_text(
                "version: 1\nskill_families: []\n",
                encoding="utf-8",
            )
            (root / "agents" / "skills" / "skill-dependencies.yaml").write_text(
                "version: 1\nskill_dependencies: {}\n",
                encoding="utf-8",
            )
            parent_child = parent_root / "workspace" / "subdir"
            parent_child.mkdir(parents=True, exist_ok=True)

            for cwd in (parent_root, parent_child):
                result = self.run_route_from_cwd(
                    cwd,
                    "--prompt",
                    "小さなルーティング改善を提案してください",
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_route_deduplicates_parent_agents_symlink_view(self) -> None:
        """A parent root view symlink to its vendor source resolves as vendored."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent_root = Path(tmp_dir)
            (parent_root / ".git").touch()
            source_root = parent_root / "source" / "agent-canon"
            catalog = source_root / "agents" / "skills" / "catalog.yaml"
            catalog.parent.mkdir(parents=True, exist_ok=True)
            catalog.write_text("version: 1\nskill_families: []\n", encoding="utf-8")
            (source_root / "agents" / "skills" / "skill-dependencies.yaml").write_text(
                "version: 1\nskill_dependencies: {}\n",
                encoding="utf-8",
            )
            vendor_link = parent_root / "vendor" / "agent-canon"
            vendor_link.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(source_root, vendor_link, target_is_directory=True)
            os.symlink(
                vendor_link / "agents",
                parent_root / "agents",
                target_is_directory=True,
            )

            resolution = agent_canon_source_root.resolve_agent_canon_source_root(parent_root)

            self.assertEqual(resolution.layout, "vendored")
            self.assertEqual(resolution.current_repository_root, parent_root.resolve())
            self.assertEqual(resolution.source_root, source_root.resolve())
            result = self.run_route(
                "--root",
                str(parent_root),
                "--prompt",
                "ルーティング改善を提案してください",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_route_rejects_different_symlink_view_entity_as_ambiguous(self) -> None:
        """A root view symlink to another AgentCanon entity stays ambiguous."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent_root = Path(tmp_dir)
            (parent_root / ".git").touch()
            standalone_root = parent_root / "standalone"
            standalone_catalog = standalone_root / "agents" / "skills" / "catalog.yaml"
            standalone_catalog.parent.mkdir(parents=True, exist_ok=True)
            standalone_catalog.write_text(
                "version: 1\nskill_families: []\n",
                encoding="utf-8",
            )
            vendor_root = parent_root / "vendor" / "agent-canon"
            vendor_catalog = vendor_root / "agents" / "skills" / "catalog.yaml"
            vendor_catalog.parent.mkdir(parents=True, exist_ok=True)
            vendor_catalog.write_text("version: 1\nskill_families: []\n", encoding="utf-8")
            os.symlink(
                standalone_root / "agents",
                parent_root / "agents",
                target_is_directory=True,
            )

            with self.assertRaises(agent_canon_source_root.SourceRootFailure) as raised:
                agent_canon_source_root.resolve_agent_canon_source_root(parent_root)

            self.assertEqual(raised.exception.code, "agent_canon_source_root_ambiguous")

    def test_route_rejects_vendor_symlink_outside_repository(self) -> None:
        """A vendor symlink escaping the parent repository fails typed resolution."""
        with tempfile.TemporaryDirectory() as tmp_dir, tempfile.TemporaryDirectory() as outside_dir:
            parent_root = Path(tmp_dir)
            (parent_root / ".git").touch()
            outside_root = Path(outside_dir) / "agent-canon"
            catalog = outside_root / "agents" / "skills" / "catalog.yaml"
            catalog.parent.mkdir(parents=True, exist_ok=True)
            catalog.write_text("version: 1\nskill_families: []\n", encoding="utf-8")
            vendor_link = parent_root / "vendor" / "agent-canon"
            vendor_link.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(outside_root, vendor_link, target_is_directory=True)

            with self.assertRaises(agent_canon_source_root.SourceRootFailure) as raised:
                agent_canon_source_root.resolve_agent_canon_source_root(parent_root)

            self.assertEqual(
                raised.exception.code,
                "agent_canon_source_root_vendor_outside_repository",
            )
            result = self.run_route(
                "--root",
                str(parent_root),
                "--prompt",
                "ルーティング改善を提案してください",
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn(raised.exception.code, result.stderr)

    def test_route_rejects_ambiguous_source_root(self) -> None:
        """Two discoverable roots return a deterministic typed failure."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "agents" / "skills").mkdir(parents=True, exist_ok=True)
            (root / "agents" / "skills" / "catalog.yaml").write_text(
                "version: 1\nskill_families: []\n",
                encoding="utf-8",
            )
            (root / "vendor" / "agent-canon" / "agents" / "skills" / "catalog.yaml").parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            (root / "vendor" / "agent-canon" / "agents" / "skills" / "catalog.yaml").write_text(
                "version: 1\nskill_families: []\n",
                encoding="utf-8",
            )

            result = self.run_route(
                "--root",
                str(root),
                "--prompt",
                "小さなルーティング改善を提案してください",
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn(
                "ROUTE_SOURCE_ROOT_FAILURE=agent_canon_source_root_ambiguous",
                result.stderr,
            )

    def test_route_rejects_missing_source_root(self) -> None:
        """A root without any AgentCanon catalog emits typed source-root failure."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = self.run_route(
                "--root",
                tmp_dir,
                "--prompt",
                "小さなルーティング改善を提案してください",
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn(
                "ROUTE_SOURCE_ROOT_FAILURE=agent_canon_source_root_missing",
                result.stderr,
            )

    def test_source_root_resolution_utils_cover_shapes(self) -> None:
        """Unit tests cover direct source-root resolution edge cases."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "agents" / "skills").mkdir(parents=True, exist_ok=True)
            standalone = root / "agents" / "skills" / "catalog.yaml"
            standalone.parent.mkdir(parents=True, exist_ok=True)
            standalone.write_text("version: 1\nskill_families:\n", encoding="utf-8")
            resolution = agent_canon_source_root.resolve_agent_canon_source_root(root)
            self.assertEqual(resolution.layout, "standalone")
            self.assertEqual(resolution.source_root, root.resolve())
            self.assertEqual(resolution.current_repository_root, root.resolve())

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "vendor" / "agent-canon"
            (root / "agents" / "skills" / "catalog.yaml").parent.mkdir(parents=True, exist_ok=True)
            (root / "agents" / "skills" / "catalog.yaml").write_text(
                "version: 1\nskill_families:\n",
                encoding="utf-8",
            )
            resolution = agent_canon_source_root.resolve_agent_canon_source_root(root.parent.parent)
            self.assertEqual(resolution.layout, "vendored")
            self.assertEqual(resolution.source_root, root.resolve())
            self.assertEqual(
                resolution.current_repository_root,
                root.parent.parent.resolve(),
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(agent_canon_source_root.SourceRootFailure) as exc:
                agent_canon_source_root.resolve_agent_canon_source_root(Path(tmp_dir))
            self.assertEqual(exc.exception.code, "agent_canon_source_root_missing")

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "agents" / "skills" / "catalog.yaml").parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            (root / "agents" / "skills" / "catalog.yaml").write_text(
                "version: 1\nskill_families:\n",
                encoding="utf-8",
            )
            (root / "vendor" / "agent-canon" / "agents" / "skills" / "catalog.yaml").parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            (root / "vendor" / "agent-canon" / "agents" / "skills" / "catalog.yaml").write_text(
                "version: 1\nskill_families:\n",
                encoding="utf-8",
            )
            with self.assertRaises(agent_canon_source_root.SourceRootFailure) as exc:
                agent_canon_source_root.resolve_agent_canon_source_root(root)
            self.assertEqual(exc.exception.code, "agent_canon_source_root_ambiguous")

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
        self.assertIn("python3 tools/agent_tools/search.py --purpose", result.stdout)
        self.assertIn("python3 tools/agent_tools/search.py --purpose", result.stdout)

    def test_search_alias_resolves_to_search_area(self) -> None:
        """Legacy vector-search names should route to coordinated search."""
        result = self.run_route("--name", "vector_search.py")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CANONICAL_AREA=search", result.stdout)
        self.assertIn("CANONICAL_TOOL=route.py --area search", result.stdout)

    def test_private_subagent_startup_aliases_are_unknown_names(self) -> None:
        """Historical startup labels should not resolve as route aliases."""
        for alias in (
            "subagent-beginning",
            "_subagent-beginning",
            "subagent-startup",
            "_subagent-startup",
        ):
            with self.subTest(alias=alias):
                result = self.run_route("--name", alias, "--format", "text")

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("STATUS=unknown", result.stdout)
                self.assertIn("CANONICAL_AREA=", result.stdout)

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
        self.assertIn("subagent-bootstrap", decision["active_skills"])
        self.assertNotIn("subagent-bootstrap", decision["deferred_skills"])
        self.assertIn("agent-orchestration", decision["matched_skills"])
        self.assertIn("result-artifact-writeout", decision["matched_skills"])

    def test_prompt_routes_subagent_first_implementation_active(self) -> None:
        """Implementation, patch, and doc-edit prompts should activate bootstrap."""
        result = self.run_route(
            "--prompt",
            (
                "Repo-changing implementation patch doc-edit work should be "
                "subagent-first; parent only orchestrates and integrates."
            ),
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("subagent-bootstrap", decision["matched_skills"])
        self.assertIn("subagent-bootstrap", decision["active_skills"])
        self.assertNotIn("subagent-bootstrap", decision["deferred_skills"])

    def test_prompt_routes_plain_fix_to_active_subagent_bootstrap(self) -> None:
        """Plain fix prompts should activate write-capable handoff."""
        result = self.run_route(
            "--prompt",
            "Fix the failing tests in the repository.",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("subagent-bootstrap", decision["skills"])
        self.assertIn("subagent-bootstrap", decision["active_skills"])
        self.assertNotIn("subagent-bootstrap", decision["deferred_skills"])

    def test_prompt_routes_plain_refactor_to_active_subagent_bootstrap(self) -> None:
        """Plain refactor prompts should activate write-capable handoff."""
        result = self.run_route(
            "--prompt",
            "Refactor the repository routing helpers.",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("subagent-bootstrap", decision["skills"])
        self.assertIn("subagent-bootstrap", decision["active_skills"])
        self.assertNotIn("subagent-bootstrap", decision["deferred_skills"])

    def test_prompt_routes_review_only_subagent_without_bootstrap_activation(self) -> None:
        """Review-only or do-not-edit prompts should not activate bootstrap."""
        result = self.run_route(
            "--prompt",
            "Use subagents for review only; do not edit files.",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("subagent-bootstrap", decision["matched_skills"])
        self.assertIn("subagent-bootstrap", decision["skills"])
        self.assertNotIn("subagent-bootstrap", decision["active_skills"])
        self.assertIn("subagent-bootstrap", decision["deferred_skills"])

    def test_prompt_routes_explicit_japanese_delegation_to_subagent_bootstrap(self) -> None:
        """Explicit Japanese delegation prompts should activate bootstrap as write-capable."""
        result = self.run_route(
            "--prompt",
            (
                "作業はすべてサブエージェントに依頼し，"
                "親は監視，エージェント起動，追加指示に徹する"
            ),
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("subagent-bootstrap", decision["matched_skills"])
        self.assertIn("subagent-bootstrap", decision["active_skills"])
        self.assertNotIn("subagent-bootstrap", decision["deferred_skills"])

    def test_prompt_routes_review_request_without_subagent_markers_does_not_activate_bootstrap(
        self,
    ) -> None:
        """Review-only dependency words should not trigger write-capable handoff."""
        result = self.run_route(
            "--prompt",
            "レビューを依頼します",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertNotIn("subagent-bootstrap", decision["matched_skills"])
        self.assertNotIn("subagent-bootstrap", decision["active_skills"])
        self.assertNotIn("subagent-bootstrap", decision["deferred_skills"])

    def test_prompt_routes_direct_review_to_change_review_without_bootstrap(self) -> None:
        """Direct review prompts should activate change-review, not implementation handoff."""
        for prompt in ("レビューしてください", "変更レビューして"):
            with self.subTest(prompt=prompt):
                result = self.run_route("--prompt", prompt, "--format", "json")

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                decision = json.loads(result.stdout)
                self.assertIn("change-review", decision["matched_skills"])
                self.assertIn("change-review", decision["active_skills"])
                self.assertNotIn("subagent-bootstrap", decision["active_skills"])

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

    def test_prompt_preserves_test_design_related_skills_for_validation_failure(
        self,
    ) -> None:
        """Validation-failure routing should keep test-design as secondary."""
        result = self.run_route(
            "--prompt",
            "failed validation; do not delete tests or weaken oracle before repair",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("codex-task-workflow", decision["matched_skills"])
        self.assertIn("codex-task-workflow", decision["active_skills"])
        self.assertIn("test-design", decision["related_skill_candidates"])
        self.assertNotIn("test-design", decision["active_skills"])
        self.assertIn("change-review", decision["related_skill_candidates"])
        self.assertIn("codex-task-workflow", decision["related_skills"])

    def test_prompt_preserves_explicit_test_design_related_skills(self) -> None:
        """Explicit $test-design routing should keep its catalog metadata."""
        result = self.run_route(
            "--prompt",
            "$test-design で validation failure を診断して",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("test-design", decision["matched_skills"])
        self.assertIn("oop-readability-check", decision["related_skill_candidates"])
        self.assertIn("change-review", decision["related_skill_candidates"])

    def test_prompt_routes_user_guided_debugging_cadence(self) -> None:
        """PR 359 cadence prompts should select user-guided-debugging."""
        prompts = (
            "Use user-guided refactor cadence: show one concrete issue, patch only that target, and do not run validation unless I ask.",
            "Use user-guided debugging: one issue at a time with visible problem statements before each edit.",
            "ユーザー主導リファクタで、問題点を出してから1件ずつ修正して。",
            "Debug 1 issue 1 fix; no validation unless asked after the patch.",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result = self.run_route("--prompt", prompt, "--format", "json")

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                decision = json.loads(result.stdout)
                self.assertIn("user-guided-debugging", decision["matched_skills"])
                self.assertIn("user-guided-debugging", decision["active_skills"])
                self.assertNotIn("refactor-loop", decision["matched_skills"])
                self.assertNotIn("refactor-loop", decision["active_skills"])

    def test_prompt_routes_patch_only_no_validation_as_implementation(self) -> None:
        """No-validation clauses after patch-only work should not mean no patch."""
        result = self.run_route(
            "--prompt",
            (
                "Use user-guided refactor cadence: show one concrete issue, "
                "patch only that target, and do not run validation unless I ask."
            ),
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertEqual(decision["mode"], "repo-changing")
        self.assertIn("subagent-bootstrap", decision["skills"])
        self.assertIn("subagent-bootstrap", decision["active_skills"])
        self.assertNotIn("subagent-bootstrap", decision["deferred_skills"])

    def test_prompt_plain_refactor_does_not_route_user_guided_debugging(self) -> None:
        """Ordinary refactor prompts should not select user-guided-debugging."""
        result = self.run_route(
            "--prompt",
            "Refactor the repository routing helpers.",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertNotIn("user-guided-debugging", decision["matched_skills"])
        self.assertNotIn("user-guided-debugging", decision["active_skills"])
        self.assertIn("structure-refactor", decision["matched_skills"])
        self.assertIn("structure-refactor", decision["active_skills"])

    def test_prompt_docs_update_no_validation_preference_does_not_route_user_guided_debugging(self) -> None:
        """Ordinary validation preferences should not select user-guided cadence."""
        result = self.run_route(
            "--prompt",
            "Please update the docs; no validation unless asked.",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertNotIn("user-guided-debugging", decision["matched_skills"])
        self.assertNotIn("user-guided-debugging", decision["active_skills"])

    def test_prompt_path_only_agent_canon_review_does_not_route_update(self) -> None:
        """Path-only read-only review prompts should not select AgentCanon update."""
        result = self.run_route(
            "--prompt",
            "Review vendor/agent-canon for routing issues. Do not edit files.",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertNotIn("agent-canon-update", decision["matched_skills"])
        self.assertNotIn("agent-canon-update", decision["active_skills"])

    def test_prompt_routes_agent_canon_update_intent(self) -> None:
        """Update, sync, pin, or root-view prompts should still route update."""
        prompts = (
            "Update vendor/agent-canon submodule pin.",
            "Sync vendor/agent-canon and repair the root runtime view.",
            "Run agent-canon-ensure-latest and fix the parent pin.",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result = self.run_route("--prompt", prompt, "--format", "json")

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                decision = json.loads(result.stdout)
                self.assertIn("agent-canon-update", decision["matched_skills"])
                self.assertIn("agent-canon-update", decision["active_skills"])

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

    def test_prompt_routes_explicit_code_visualization_to_code_visualization_skill(self) -> None:
        """Explicit public id should select code-visualization."""
        result = self.run_route("--prompt", "$code-visualization で依存図を見たい", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("code-visualization", decision["matched_skills"])
        self.assertIn("code-visualization", decision["active_skills"])
        self.assertEqual(decision["visualization_owner_skill"], "code-visualization")
        self.assertIsNone(decision["visualization_rejection"])
        call = decision["visualization_tool_call"]
        self.assertEqual(call["schema"], "agent_canon.visualization_tool_call.v1")
        self.assertEqual(
            call["tool_id"],
            "agent_canon.visualization.coverage",
        )
        self.assertEqual(
            call["argument_schema"],
            "agent_canon.visualization.arguments.coverage.v1",
        )
        self.assertEqual(
            set(call["arguments"]),
            {
                "request_id",
                "literal_request",
                "literal_items",
                "owner_closure",
                "dependency_closure",
                "artifact_id",
                "renderer_id",
                "artifact_format",
            },
        )
        self.assertEqual(call["arguments"]["artifact_format"], "graph_ir")
        self.assertEqual(call["arguments"]["literal_items"][0]["origin"], "literal_request")
        self.assertEqual(call["arguments"]["owner_closure"][0]["origin"], "owner_closure")

    def test_prompt_routes_visualization_keyword_alone_should_not_select_code_visualization(self) -> None:
        """Prose keyword alone should not route to code-visualization."""
        result = self.run_route(
            "--prompt",
            "この可視化は、図の配色や見栄えが重要です。",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertNotIn("code-visualization", decision["matched_skills"])
        self.assertNotIn("code-visualization", decision["active_skills"])
        self.assertIsNone(decision["visualization_owner_skill"])
        self.assertIsNone(decision["visualization_tool_call"])
        self.assertEqual(decision["visualization_rejection"], "prose_only")

    def test_prompt_routes_code_visualization_public_name(self) -> None:
        """Calling the public skill name should select code-visualization."""
        result = self.run_route(
            "--prompt",
            "Please apply code-visualization to this dependency graph.",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("code-visualization", decision["matched_skills"])
        self.assertIn("code-visualization", decision["active_skills"])
        self.assertEqual(decision["visualization_owner_skill"], "code-visualization")
        self.assertIsNone(decision["visualization_rejection"])

    def test_prompt_routes_code_visualization_tool_call_visible_in_text_and_markdown(self) -> None:
        """Tool-call metadata remains visible in text and markdown render formats."""
        for output_format in ("text", "markdown"):
            with self.subTest(output_format=output_format):
                result = self.run_route(
                    "--prompt",
                    "$code-visualization を dependency graph で可視化して",
                    "--format",
                    output_format,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("agent_canon.visualization.coverage", result.stdout)
                self.assertIn(
                    "agent_canon.visualization.arguments.coverage.v1",
                    result.stdout,
                )
                self.assertIn("visualization", result.stdout.lower())

    def test_all_canonical_visualization_tool_ids_route_to_one_owner_call(self) -> None:
        """Every canonical owner/adapter ToolID normalizes to the sole owner."""
        for tool_id in (
            "agent_canon.visualization.coverage",
            "agent_canon.visualization.adapter.dependency_manifest",
            "agent_canon.visualization.adapter.algorithm_flowchart",
            "agent_canon.visualization.adapter.document_mermaid",
            "agent_canon.visualization.adapter.repository_graph",
            "agent_canon.visualization.adapter.knowledge_graph",
        ):
            with self.subTest(tool_id=tool_id):
                result = self.run_route("--prompt", tool_id, "--format", "json")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                decision = json.loads(result.stdout)
                self.assertEqual(
                    decision["visualization_owner_skill"], "code-visualization"
                )
                self.assertEqual(
                    decision["visualization_tool_call"]["tool_id"],
                    "agent_canon.visualization.coverage",
                )
                self.assertEqual(
                    decision["visualization_tool_call"]["argument_schema"],
                    "agent_canon.visualization.arguments.coverage.v1",
                )
                self.assertIsNone(decision["visualization_rejection"])

    def test_explicit_adapter_tool_call_normalizes_shared_arguments_to_owner(self) -> None:
        """A valid adapter call is validated but route emits only the owner call."""
        supplied = self.visualization_tool_call(
            tool_id="agent_canon.visualization.adapter.dependency_manifest",
            argument_schema=(
                "agent_canon.visualization.arguments.dependency_manifest.v1"
            ),
        )
        result = self.run_route(
            "--prompt",
            json.dumps(supplied, sort_keys=True),
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        call = decision["visualization_tool_call"]
        self.assertEqual(call["tool_id"], "agent_canon.visualization.coverage")
        self.assertEqual(
            call["argument_schema"],
            "agent_canon.visualization.arguments.coverage.v1",
        )
        self.assertNotIn("dependency_manifest_locator", call["arguments"])
        supplied_arguments = supplied["arguments"]
        self.assertIsInstance(supplied_arguments, dict)
        assert isinstance(supplied_arguments, dict)
        self.assertEqual(
            call["arguments"]["literal_items"],
            supplied_arguments["literal_items"],
        )
        self.assertIsNone(decision["visualization_rejection"])

    def test_renderer_skill_alias_keeps_code_visualization_as_owner(self) -> None:
        """An explicit renderer-only skill remains downstream of the public owner."""
        result = self.run_route(
            "--prompt",
            "$algorithm-flowchart",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertEqual(decision["visualization_owner_skill"], "code-visualization")
        self.assertEqual(
            decision["visualization_tool_call"]["tool_id"],
            "agent_canon.visualization.coverage",
        )
        self.assertIn("algorithm-flowchart", decision["matched_skills"])

    def test_visualization_tool_call_rejections_are_deterministic(self) -> None:
        """Unknown, schema, field, type, and format defects fail closed."""
        unknown = self.visualization_tool_call()
        unknown["tool_id"] = "agent_canon.visualization.adapter.unknown"

        bad_schema = self.visualization_tool_call()
        bad_schema["schema"] = "agent_canon.visualization_tool_call.v0"

        bad_argument_schema = self.visualization_tool_call()
        bad_argument_schema["argument_schema"] = (
            "agent_canon.visualization.arguments.dependency_manifest.v1"
        )

        missing_field = self.visualization_tool_call()
        del missing_field["arguments"]

        extra_field = self.visualization_tool_call()
        extra_field["unexpected"] = True

        wrong_json_type = self.visualization_tool_call()
        wrong_json_type["arguments"] = []

        unhashable_tool_id = self.visualization_tool_call()
        unhashable_tool_id["tool_id"] = ["agent_canon.visualization.coverage"]

        wrong_argument_type = self.visualization_tool_call()
        wrong_argument_values = wrong_argument_type["arguments"]
        self.assertIsInstance(wrong_argument_values, dict)
        assert isinstance(wrong_argument_values, dict)
        wrong_argument_values["literal_items"] = {}

        bad_artifact_format = self.visualization_tool_call()
        bad_format_values = bad_artifact_format["arguments"]
        self.assertIsInstance(bad_format_values, dict)
        assert isinstance(bad_format_values, dict)
        bad_format_values["artifact_format"] = "png"

        extra_argument = self.visualization_tool_call()
        extra_argument_values = extra_argument["arguments"]
        self.assertIsInstance(extra_argument_values, dict)
        assert isinstance(extra_argument_values, dict)
        extra_argument_values["unexpected"] = True

        cases = (
            (unknown, "invalid_tool_call"),
            (bad_schema, "schema_mismatch"),
            (bad_argument_schema, "schema_mismatch"),
            (missing_field, "invalid_tool_call"),
            (extra_field, "invalid_tool_call"),
            (wrong_json_type, "invalid_tool_call"),
            (unhashable_tool_id, "invalid_tool_call"),
            (wrong_argument_type, "invalid_tool_call"),
            (bad_artifact_format, "invalid_tool_call"),
            (extra_argument, "invalid_tool_call"),
        )
        for supplied, expected in cases:
            with self.subTest(expected=expected, supplied=supplied):
                result = self.run_route(
                    "--prompt",
                    json.dumps(supplied, sort_keys=True),
                    "--format",
                    "json",
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                decision = json.loads(result.stdout)
                self.assertIsNone(decision["visualization_owner_skill"])
                self.assertIsNone(decision["visualization_tool_call"])
                self.assertEqual(decision["visualization_rejection"], expected)

    def test_unknown_bare_visualization_tool_id_is_invalid(self) -> None:
        """A canonical-looking unknown ToolID is not treated as prose."""
        result = self.run_route(
            "--prompt",
            "agent_canon.visualization.adapter.unregistered",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertEqual(decision["visualization_rejection"], "invalid_tool_call")
        self.assertIsNone(decision["visualization_tool_call"])

    def test_explicit_visualization_without_owner_is_missing_owner(self) -> None:
        """A valid explicit ToolID fails closed when the catalog owner is absent."""
        decision = route_module.decide_skills(
            "agent_canon.visualization.coverage",
            "routing-only",
            (),
        )

        self.assertEqual(decision.visualization_rejection, "missing_owner")
        self.assertIsNone(decision.visualization_owner_skill)
        self.assertIsNone(decision.visualization_tool_call)

    def test_code_visualization_small_model_route_is_exact_and_early(self) -> None:
        """The runtime skill exposes the exact renderer route before generic guidance."""
        runtime_text = (PROJECT_ROOT / ".agents" / "skills" / "code-visualization" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        direct_start = runtime_text.index("## Small-Model Direct Route")
        canonical_read = runtime_text.index("1. Read `agents/skills/code-visualization.md`.")
        generic_tree = runtime_text.index("1. Infer the context question")
        direct_text = runtime_text[direct_start:canonical_read]
        self.assertLess(direct_start, canonical_read)
        self.assertLess(canonical_read, generic_tree)
        for command in (
            "python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope full --bundle-dir reports/dependency-graph --format json",
            "python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope changed --bundle-dir reports/dependency-graph --format json",
        ):
            self.assertIn(command, direct_text)
        self.assertNotIn("<path>", direct_text)
        self.assertNotIn("<provided-path>", direct_text)
        self.assertIn("--scope changed` only when the request explicitly asks for changed scope", direct_text)
        self.assertIn("`--json` is invalid", direct_text)
        direct_flat = " ".join(direct_text.split())
        for invariant in (
            "Treat these two commands as immutable flag templates.",
            "`--root .` and `--format json` are mandatory in both routes.",
            "Do not remove, add, or rename any flag.",
        ):
            self.assertIn(invariant, direct_flat)
        for boundary in (
            "The canonical graph owns dependency status and facts.",
            "The renderer performs one typed dependency query through `GraphClient` and owns only Graph IR, Markdown, DOT, HTML, and bundle/manifest projection creation.",
        ):
            self.assertIn(boundary, direct_flat)
        self.assertNotIn("tools/agent_tools/check_dependency_graph.sh", direct_flat)
        self.assertIn(
            "There is no supplied-input, raw-checker, scan, helper, or Mermaid fallback.",
            direct_flat,
        )
        packet_result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "tools" / "agent_tools" / "skill_tool_commands.py"),
                "show",
                "--skill",
                "code-visualization",
                "--format",
                "json",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(packet_result.returncode, 0, packet_result.stdout + packet_result.stderr)
        self.assertNotIn("check_dependency_graph.sh", packet_result.stdout)
        self.assertNotIn("sed -n", packet_result.stdout)
        packet_payload = json.loads(packet_result.stdout)
        self.assertEqual(packet_payload["required_commands"], [])
        self.assertEqual(
            packet_payload["discovered_commands"],
            [
                "python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope full --bundle-dir reports/dependency-graph --format json",
                "python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope changed --bundle-dir reports/dependency-graph --format json",
            ],
        )
        for forbidden in ("route.py", "scan_code_dependencies.py", "helper_function_inventory.py"):
            self.assertNotIn(forbidden, packet_payload["discovered_commands"])
        self.assertEqual(
            [
                "dependency_graph.tsv",
                "dependency_graph.ir.json",
                "dependency_graph.md",
                "dependency_graph.dot",
                "dependency_graph.html",
                "manifest.json",
            ],
            [
                line.split("`", 2)[1]
                for line in direct_text.splitlines()
                if line.strip().startswith(tuple(f"{index}." for index in range(1, 7)))
            ],
        )

    def test_code_visualization_canonical_skill_mirrors_renderer_invariant(self) -> None:
        """The canonical owner keeps full and changed graph routes synchronized."""
        canonical_text = (PROJECT_ROOT / "agents" / "skills" / "code-visualization.md").read_text(
            encoding="utf-8"
        )
        source_start = canonical_text.index("## Source Evidence Routes")
        source_text = canonical_text[source_start:]
        self.assertIn("changed-scope command only when changed scope is explicit", source_text)
        self.assertIn("--bundle-dir reports/dependency-graph", source_text)
        self.assertNotIn("<path>", source_text)
        self.assertNotIn("<provided-path>", source_text)
        self.assertIn("`--json` is invalid", source_text)
        source_flat = " ".join(source_text.split())
        for invariant in (
            "Treat these two commands as immutable flag templates.",
            "`--root .` and `--format json` are mandatory in both routes.",
            "Do not remove, add, or rename any flag.",
        ):
            self.assertIn(invariant, source_flat)
        for boundary in (
            "The canonical graph owns dependency status and facts.",
            "The renderer performs one typed dependency query through `GraphClient` and owns only Graph IR, Markdown, DOT, HTML, and bundle/manifest projection creation.",
        ):
            self.assertIn(boundary, source_flat)
        self.assertNotIn("tools/agent_tools/check_dependency_graph.sh", source_flat)
        self.assertIn(
            "There is no supplied-input, raw-checker, scan, helper, or Mermaid fallback.",
            source_flat,
        )
        self.assertNotIn(
            "renderer invokes the external checker and owns checker authority",
            source_flat,
        )
        for forbidden in ("route.py", "scan_code_dependencies.py", "helper_function_inventory.py"):
            self.assertNotIn(forbidden, source_text)
        for basename in (
            "dependency_graph.tsv",
            "dependency_graph.ir.json",
            "dependency_graph.md",
            "dependency_graph.dot",
            "dependency_graph.html",
            "manifest.json",
        ):
            self.assertIn(f"`{basename}`", source_text)

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
        self.assertLess(
            decision["skills"].index("structure-planning"),
            decision["skills"].index("report-writing"),
        )
        self.assertIn("result-artifact-writeout", decision["related_skill_candidates"])

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

    def test_prompt_private_startup_aliases_do_not_activate_public_skills(
        self,
    ) -> None:
        """Private startup route labels should not become public prompt skills."""
        private_aliases = (
            "subagent-beginning",
            "_subagent-beginning",
            "subagent-startup",
            "_subagent-startup",
        )
        result = self.run_route(
            "--prompt",
            " ".join(private_aliases),
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        for field in ("skills", "active_skills", "matched_skills"):
            for alias in private_aliases:
                self.assertNotIn(alias, decision[field])
            self.assertNotIn("subagent-bootstrap", decision[field])

    def test_prompt_structural_startup_fields_do_not_activate_subagent_bootstrap(
        self,
    ) -> None:
        """Generated structural route fields should stay out of public skill routing."""
        result = self.run_route(
            "--prompt",
            "\n".join(
                [
                    "subagent_startup_route: agents/internal-routines/subagent-startup.md",
                    "internal_skill_routes: agents/internal-routines/subagent-startup.md",
                ]
            ),
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertNotIn("subagent-bootstrap", decision["matched_skills"])
        self.assertNotIn("subagent-bootstrap", decision["active_skills"])

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

    def test_prompt_routes_current_dashboard_skillization_request(self) -> None:
        """Dashboard-driven skillization should route analysis, routing, and repair follow-up."""
        result = self.run_route(
            "--prompt",
            "ログをすべて解析して，頻発する作業をスキルにしてルーティングを改善",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("agent-log-analysis", decision["matched_skills"])
        self.assertIn("task-routing", decision["matched_skills"])
        self.assertIn("runtime-log-repair", decision["matched_skills"])
        self.assertIn("agent-log-analysis", decision["active_skills"])
        self.assertIn("task-routing", decision["active_skills"])
        self.assertIn("runtime-log-repair", decision["active_skills"])

    def test_prompt_routes_skill_miss_cause_repair_to_runtime_log_repair(self) -> None:
        """Skill-miss cause repair should not leave runtime-log-repair related-only."""
        result = self.run_route(
            "--prompt",
            "ログをすべて解析して，頻発する作業をスキルにしてルーティングを改善して下さい.スキルミスも原因を特定して修正",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("runtime-log-repair", decision["matched_skills"])
        self.assertIn("runtime-log-repair", decision["active_skills"])

    def test_prompt_routes_codex_loading_priority_document_sweep(self) -> None:
        """Codex loading-priority document sweeps should route structure and document canon."""
        result = self.run_route(
            "--prompt",
            "レポのルールを丁寧に見て，Codexの読み込みプライオリティを考えて上位文書から怪文書に至るまで漏らさず修正",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("structure-refactor", decision["matched_skills"])
        self.assertIn("document-canon-cleanup", decision["matched_skills"])
        self.assertIn("structure-refactor", decision["active_skills"])
        self.assertIn("document-canon-cleanup", decision["active_skills"])
        self.assertNotIn("agent-log-analysis", decision["matched_skills"])

    def test_prompt_routes_algorithm_test_first_feedback(self) -> None:
        """Algorithm repair feedback should route to algorithm owners before test design."""
        result = self.run_route(
            "--prompt",
            "アルゴリズム修正時にテストから直し始めるのをやめてください",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        for skill in (
            "computational-optimization",
            "algorithm-proof-exploration",
            "agent-learning",
        ):
            self.assertIn(skill, decision["matched_skills"])
        for skill in (
            "computational-optimization",
            "algorithm-proof-exploration",
        ):
            self.assertIn(skill, decision["active_skills"])
        self.assertNotIn("test-design", decision["matched_skills"])
        self.assertNotIn("test-design", decision["active_skills"])
        self.assertIn("agent-learning", decision["deferred_skills"])

    def test_prompt_routes_runtime_dashboard_repair_to_runtime_log_repair(self) -> None:
        """Runtime dashboard repair prompts should activate runtime-log-repair."""
        result = self.run_route(
            "--prompt",
            (
                "runtime dashboard next actions: repair failing hook evidence and "
                "AGENT_RUNTIME_DASHBOARD_WAVE_MISSING_ACTUAL"
            ),
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("runtime-log-repair", decision["matched_skills"])
        self.assertIn("runtime-log-repair", decision["active_skills"])

    def test_name_resolution_resolves_public_skill_ids(self) -> None:
        """Public skill ids should resolve through the skill catalog."""
        result = self.run_route("--name", "runtime-log-repair")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("NAME=runtime-log-repair", result.stdout)
        self.assertIn("STATUS=canonical", result.stdout)
        self.assertIn("CANONICAL_AREA=skills", result.stdout)
        self.assertIn("CANONICAL_SKILL=runtime-log-repair", result.stdout)

    def test_prompt_does_not_route_ordinary_url_or_report_text_to_runtime_log_repair(
        self,
    ) -> None:
        """Ordinary source URL and report wording should not trigger runtime-log repair."""
        prompts = (
            "consulted source URLs are missing from the literature survey notes",
            "Reference missing URLs in the README link list",
            "workflow attribution section in this report",
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result = self.run_route("--prompt", prompt, "--format", "json")

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                decision = json.loads(result.stdout)
                self.assertNotIn("runtime-log-repair", decision["matched_skills"])
                self.assertNotIn("runtime-log-repair", decision["active_skills"])
                self.assertNotIn("runtime-log-repair", decision["skills"])
                self.assertNotIn(
                    "runtime-log-repair",
                    decision["related_skill_candidates"],
                )

    def test_prompt_routes_pr_cleanup_to_pr_processing(self) -> None:
        """PR cleanup prompts should activate pr-processing."""
        result = self.run_route(
            "--prompt",
            "PRを片付けてください。LocalもMainに追従",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("pr-processing", decision["matched_skills"])
        self.assertIn("pr-processing", decision["active_skills"])

    def test_prompt_routes_docs_check_failure_to_md_style_check(self) -> None:
        """Docs check failures should activate md-style-check."""
        result = self.run_route(
            "--prompt",
            "docs check が失敗しているので直して",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("md-style-check", decision["matched_skills"])
        self.assertIn("md-style-check", decision["active_skills"])

    def test_prompt_routes_experiment_run_results_to_lifecycle(self) -> None:
        """Experiment run/result prompts should activate lifecycle and suggest writeout."""
        result = self.run_route(
            "--prompt",
            "experiment run artifacts を保存して実験結果をまとめて",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("experiment-lifecycle", decision["matched_skills"])
        self.assertIn("experiment-lifecycle", decision["active_skills"])
        self.assertLess(
            decision["skills"].index("result-artifact-writeout"),
            decision["skills"].index("experiment-lifecycle"),
        )

    def test_prompt_routes_result_save_export_to_writeout(self) -> None:
        """Result save/export prompts should activate result-artifact-writeout."""
        result = self.run_route(
            "--prompt",
            "save result and export result as a durable artifact with raw summary",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("result-artifact-writeout", decision["matched_skills"])
        self.assertIn("result-artifact-writeout", decision["active_skills"])

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
                ):
                    self.assertIn(skill, decision["matched_skills"])
                    self.assertIn(skill, decision["active_skills"])
                self.assertNotIn("agent-canon-update", decision["matched_skills"])
                self.assertNotIn("agent-canon-update", decision["active_skills"])
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

    def test_prompt_routes_parent_repo_specific_skill_lane_design(self) -> None:
        """Parent-repo-specific skill lane design should reach routing and structure."""
        result = self.run_route(
            "--prompt",
            "親レポに固有スキルを置けるようにする設計修正",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        self.assertIn("task-routing", decision["matched_skills"])
        self.assertIn("structure-refactor", decision["matched_skills"])
        self.assertNotIn("environment-maintenance", decision["matched_skills"])
        self.assertNotIn("environment-maintenance", decision["active_skills"])
        self.assertTrue(
            any(
                "task-routing:structural_concept=parent_repo_project_skill_lane"
                in reason
                for reason in decision["reasons"]
            )
        )
        self.assertTrue(
            any(
                "structure-refactor:structural_concept=parent_repo_project_skill_lane"
                in reason
                for reason in decision["reasons"]
            )
        )
        self.assertNotEqual(decision["evidence"], "mode=repo-changing;matched=none")

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

    def test_prompt_route_unknown_dependency_reference_fails_structured(self) -> None:
        """Dependency metadata should reference public catalog entries."""
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
                    ]
                ),
                encoding="utf-8",
            )
            dependency_map = root / "agents" / "skills" / "skill-dependencies.yaml"
            dependency_map.write_text(
                "\n".join(
                    [
                        "version: 1",
                        "skill_dependencies:",
                        "  task-routing:",
                        "    responsibility_group: orchestration",
                        "    required_prerequisites: []",
                        "    successors:",
                        "      - missing-skill",
                        "    order_constraints: []",
                        "    parallel_independent: []",
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
            "skill-dependency-map-unknown-reference:task-routing:successors:missing-skill",
            result.stderr,
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

    def test_prompt_routes_failed_validation_to_owning_repair_surface(
        self,
    ) -> None:
        """Failed validation prompts should not make test design the active owner."""
        prompt = (
            "Tests are failing; do not delete tests or weaken oracles just to pass. "
            "Diagnose the failing contract first."
        )
        python_result = self.run_route("--prompt", prompt, "--format", "json")

        self.assertEqual(
            python_result.returncode, 0, python_result.stdout + python_result.stderr
        )
        python_decision = json.loads(python_result.stdout)
        self.assertIn("codex-task-workflow", python_decision["matched_skills"])
        self.assertIn("codex-task-workflow", python_decision["active_skills"])
        self.assertIn("test-design", python_decision["related_skill_candidates"])
        self.assertNotIn("test-design", python_decision["active_skills"])
        self.assertIn("agent-orchestration", python_decision["active_skills"])
        self.assertTrue(
            any(
                "tests_are=validation_control_surface_not_default_work_owner"
                in reason
                for reason in python_decision["reasons"]
            )
        )

    def test_prompt_routes_oracle_spec_mismatch_to_test_design(self) -> None:
        """Oracle/spec mismatch prompts should still activate test-design."""
        prompt = "The test oracle has a spec mismatch; update the test design."
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


class CapabilityRouteTest(unittest.TestCase):
    """Exercise explicit capability routing and its immutable envelopes."""

    def run_route(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run route.py with arguments for one capability test."""
        return subprocess.run(
            [sys.executable, str(ROUTE), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_catalog(
        self,
        root: Path,
        entries: str,
    ) -> Path:
        """Write a minimal capability catalog fixture."""
        path = root / "agents" / "skills" / "catalog.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    "version: 1",
                    "skill_families:",
                    entries,
                ]
            ),
            encoding="utf-8",
        )
        skill_ids = [
            line.strip()[len("- id: ") :]
            for line in entries.splitlines()
            if line.startswith("  - id: ")
        ]
        dependency_lines = ["version: 1", "skill_dependencies:"]
        for skill_id in skill_ids:
            dependency_lines.extend(
                [
                    f"  {skill_id}:",
                    "    responsibility_group: fixture",
                    "    required_prerequisites: []",
                    "    successors: []",
                    "    order_constraints: []",
                    "    parallel_independent: []",
                ]
            )
        self.write_dependency_map(root, "\n".join(dependency_lines[2:]))
        return path

    def write_dependency_map(self, root: Path, body: str) -> Path:
        """Write one dependency dictionary fixture."""
        path = root / "agents" / "skills" / "skill-dependencies.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(["version: 1", "skill_dependencies:", body]),
            encoding="utf-8",
        )
        return path

    def capability_entry(
        self,
        skill: str = "oop-type-design",
        capability_id: str = "oop_type_design",
        *,
        owner: str = "pre_implementation_oop_type_design",
        extra: str = "",
    ) -> str:
        """Return one minimal capability family entry."""
        return "\n".join(
            [
                f"  - id: {skill}",
                "    purpose: Capability fixture.",
                f"    canonical_doc: agents/skills/{skill}.md",
                f"    shim: .agents/skills/{skill}/SKILL.md",
                "    routing:",
                "      stage_policy: active",
                "      reason: capability fixture",
                "      capabilities:",
                f"        - id: {capability_id}",
                f"          owner: {owner}",
                "          phase: pre_implementation_design",
                "          activation: explicit_capability",
                "          exclusive: true",
                *(extra.splitlines() if extra else []),
            ]
        )

    def assert_failure_code(
        self,
        result: subprocess.CompletedProcess[str],
        code: str,
        *,
        output_format: str = "json",
    ) -> dict[str, object] | str:
        """Assert the fixed capability failure envelope."""
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        if output_format == "json" and result.stdout.lstrip().startswith("{"):
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "fail")
            self.assertEqual(payload["error_code"], code)
            return payload
        if output_format == "markdown":
            self.assertIn("- Status: `fail`", result.stdout)
            self.assertIn(f"- Error code: `{code}`", result.stdout)
        else:
            self.assertIn("CAPABILITY_ROUTE_STATUS=fail", result.stdout)
            self.assertIn(f"CAPABILITY_ERROR_CODE={code}", result.stdout)
        return result.stdout

    def assert_route_source_root_failure(
        self,
        result: subprocess.CompletedProcess[str],
        code: str,
    ) -> None:
        """Assert typed root-resolution failure from route entry."""
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(f"ROUTE_SOURCE_ROOT_FAILURE={code}", result.stderr)

    def test_skill_routing_schema_rejects_unknown_stage_policy(self) -> None:
        """Catalog owner rejects stage-policy values outside its schema."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_catalog(
                root,
                "\n".join(
                    [
                        "  - id: task-routing",
                        "    purpose: Fixture.",
                        "    canonical_doc: agents/skills/task-routing.md",
                        "    shim: .agents/skills/task-routing/SKILL.md",
                        "    routing:",
                        "      stage_policy: explicit_only",
                        "      reason: fixture",
                        "      triggers:",
                        "        - [routing]",
                    ]
                ),
            )
            with self.assertRaisesRegex(ValueError, "routing.stage_policy"):
                catalog_module.load_skill_route_rules(root)

    def test_skill_routing_schema_rejects_non_string_reason(self) -> None:
        """Catalog owner rejects non-string routing reasons."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_catalog(
                root,
                "\n".join(
                    [
                        "  - id: task-routing",
                        "    purpose: Fixture.",
                        "    canonical_doc: agents/skills/task-routing.md",
                        "    shim: .agents/skills/task-routing/SKILL.md",
                        "    routing:",
                        "      stage_policy: active",
                        "      reason: 3",
                        "      triggers:",
                        "        - [routing]",
                    ]
                ),
            )
            with self.assertRaisesRegex(ValueError, "routing.reason"):
                catalog_module.load_skill_route_rules(root)

    def test_skill_dependency_schema_rejects_unknown_skill(self) -> None:
        """Dependency owner rejects references absent from the catalog."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_catalog(
                root,
                "\n".join(
                    [
                        "  - id: task-routing",
                        "    purpose: Fixture.",
                        "    canonical_doc: agents/skills/task-routing.md",
                        "    shim: .agents/skills/task-routing/SKILL.md",
                    ]
                ),
            )
            self.write_dependency_map(
                root,
                "\n".join(
                    [
                        "  task-routing:",
                        "    responsibility_group: fixture",
                        "    required_prerequisites: []",
                        "    successors:",
                        "      - missing-skill",
                        "    order_constraints: []",
                        "    parallel_independent: []",
                    ]
                ),
            )
            with self.assertRaisesRegex(
                ValueError, "skill-dependency-map-unknown-reference"
            ):
                catalog_module.load_skill_route_rules(root)

    def test_skill_dependency_schema_rejects_self_reference(self) -> None:
        """Dependency owner rejects self-referential relations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_catalog(
                root,
                "\n".join(
                    [
                        "  - id: task-routing",
                        "    purpose: Fixture.",
                        "    canonical_doc: agents/skills/task-routing.md",
                        "    shim: .agents/skills/task-routing/SKILL.md",
                    ]
                ),
            )
            self.write_dependency_map(
                root,
                "\n".join(
                    [
                        "  task-routing:",
                        "    responsibility_group: fixture",
                        "    required_prerequisites: []",
                        "    successors: []",
                        "    order_constraints: []",
                        "    parallel_independent:",
                        "      - task-routing",
                    ]
                ),
            )
            with self.assertRaisesRegex(
                ValueError, "skill-dependency-map-self-reference"
            ):
                catalog_module.load_skill_route_rules(root)

    def test_capability_route_selects_oop_type_design(self) -> None:
        """The explicit capability selects exactly the approved owner route."""
        result = self.run_route("--capability", "oop_type_design", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "agent_canon.route.capability_route.v1")
        self.assertEqual(payload["matches"][0]["skill"], "oop-type-design")
        self.assertEqual(payload["matches"][0]["owner"], "pre_implementation_oop_type_design")
        self.assertEqual(payload["matches"][0]["phase"], "pre_implementation_design")
        self.assertEqual(payload["matches"][0]["activation"], "explicit_capability")
        self.assertTrue(payload["matches"][0]["exclusive"])
        self.assertIsNone(payload["visualization_owner_skill"])
        self.assertIsNone(payload["visualization_tool_call"])
        self.assertIsNone(payload["visualization_rejection"])

    def test_capability_route_selects_dependency_visualization_owner(self) -> None:
        """Visualization capability maps to canonical code-visualization ownership."""
        result = self.run_route("--capability", "dependency_manifest_graph", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "agent_canon.route.capability_route.v1")
        self.assertEqual(payload["matches"][0]["skill"], "code-visualization")
        self.assertEqual(payload["matches"][0]["owner"], "code_visualization")
        self.assertEqual(payload["matches"][0]["phase"], "repo_changing")
        self.assertEqual(payload["matches"][0]["activation"], "explicit_capability")
        self.assertEqual(payload["visualization_owner_skill"], "code-visualization")
        self.assertEqual(
            payload["visualization_tool_call"]["tool_id"],
            "agent_canon.visualization.coverage",
        )
        self.assertEqual(
            payload["visualization_tool_call"]["argument_schema"],
            "agent_canon.visualization.arguments.coverage.v1",
        )
        self.assertIsNone(payload["visualization_rejection"])

    def test_capability_route_renders_all_formats(self) -> None:
        """JSON, text, and Markdown share the capability envelope fields."""
        for output_format in ("json", "text", "markdown"):
            with self.subTest(output_format=output_format):
                result = self.run_route(
                    "--capability",
                    "oop_type_design",
                    "--format",
                    output_format,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("capability_route.v1", result.stdout)
                self.assertIn("oop_type_design", result.stdout)
                self.assertIn("pre_implementation_oop_type_design", result.stdout)

    def test_capability_route_failure_envelope_all_formats(self) -> None:
        """Failure output keeps the same schema across renderer formats."""
        for output_format in ("json", "text", "markdown"):
            with self.subTest(output_format=output_format):
                result = self.run_route(
                    "--capability",
                    "unknown_capability",
                    "--format",
                    output_format,
                )
                self.assert_failure_code(result, "unknown-capability:unknown_capability", output_format=output_format)

    def test_capability_route_rejects_unknown_id(self) -> None:
        """Unknown capability IDs fail closed."""
        result = self.run_route("--capability", "unknown_capability", "--format", "json")
        self.assert_failure_code(result, "unknown-capability:unknown_capability")

    def test_capability_route_rejects_invalid_id(self) -> None:
        """Capability IDs outside the fixed grammar fail closed."""
        result = self.run_route("--capability", "oop-type-design", "--format", "json")
        payload = self.assert_failure_code(result, "invalid-capability-id:oop-type-design")
        self.assertEqual(payload["capability_ids"], [])

    def test_capability_route_rejects_duplicate_id(self) -> None:
        """Repeated explicit IDs are rejected before matching."""
        result = self.run_route(
            "--capability",
            "oop_type_design",
            "--capability",
            "oop_type_design",
        )
        self.assert_failure_code(result, "duplicate-capability:oop_type_design")

    def test_capability_route_rejects_owner_ambiguity(self) -> None:
        """A capability owned by two skills is ambiguous."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_catalog(
                root,
                self.capability_entry()
                + "\n"
                + self.capability_entry("other-skill", owner="other_owner"),
            )
            result = self.run_route("--root", str(root), "--capability", "oop_type_design")
        self.assert_failure_code(result, "capability-owner-ambiguity:oop_type_design")

    def test_capability_route_rejects_duplicate_definition(self) -> None:
        """A same-skill duplicate definition is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            duplicate = self.capability_entry() + "\n" + "        - id: oop_type_design\n          owner: pre_implementation_oop_type_design\n          phase: pre_implementation_design\n          activation: explicit_capability\n          exclusive: true"
            self.write_catalog(root, duplicate)
            result = self.run_route("--root", str(root), "--capability", "oop_type_design")
        self.assert_failure_code(result, "duplicate-capability-definition:oop_type_design")

    def test_capability_route_rejects_multiple_capabilities(self) -> None:
        """The first capability version does not arbitrate multiple IDs."""
        result = self.run_route(
            "--capability",
            "oop_type_design",
            "--capability",
            "other_capability",
        )
        self.assert_failure_code(result, "multiple-capabilities-not-supported")

    def test_capability_route_rejects_conflicting_prompt_input(self) -> None:
        """Capability mode cannot combine with prompt input."""
        result = self.run_route("--capability", "oop_type_design", "--prompt", "design")
        self.assert_failure_code(result, "capability-input-conflict:--prompt")

    def test_capability_route_rejects_bare_changed_flag(self) -> None:
        """A bare changed flag remains a capability conflict."""
        result = self.run_route("--capability", "oop_type_design", "--changed")
        self.assert_failure_code(result, "capability-input-conflict:--changed")

    def test_capability_route_rejects_missing_option_value(self) -> None:
        """A missing capability value uses the text fallback envelope."""
        result = self.run_route("--capability")
        self.assert_failure_code(result, "missing-capability-value", output_format="text")

    def test_capability_route_rejects_option_looking_capability_value(self) -> None:
        """An option token cannot become a capability ID."""
        result = self.run_route("--capability", "--format", "json")
        self.assert_failure_code(result, "missing-capability-value", output_format="text")

    def test_capability_route_rejects_unsupported_option(self) -> None:
        """Unknown raw options fail closed before argparse."""
        result = self.run_route("--capability", "oop_type_design", "--unsupported")
        self.assert_failure_code(result, "capability-unsupported-option:--unsupported")

    def test_capability_route_rejects_missing_root_value(self) -> None:
        """A missing custom-root value has a fixed preflight code."""
        result = self.run_route("--capability", "oop_type_design", "--root")
        self.assert_failure_code(result, "missing-root-value")

    def test_capability_route_accepts_root_equals_form(self) -> None:
        """The equals form resolves the supplied root before matching."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_catalog(root, self.capability_entry())
            result = self.run_route(
                f"--root={root}",
                "--capability=oop_type_design",
                "--format=json",
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["matches"][0]["skill"], "oop-type-design")

    def test_capability_route_rejects_missing_format_value(self) -> None:
        """A missing format value uses text output."""
        result = self.run_route("--capability", "oop_type_design", "--format")
        self.assert_failure_code(result, "missing-format-value", output_format="text")

    def test_capability_route_rejects_missing_mode_value(self) -> None:
        """A missing mode value uses repo-changing output."""
        result = self.run_route("--capability", "oop_type_design", "--mode")
        self.assert_failure_code(result, "missing-mode-value", output_format="text")

    def test_capability_route_rejects_missing_risk_value(self) -> None:
        """A missing risk value is rejected before catalog load."""
        result = self.run_route("--capability", "oop_type_design", "--risk")
        self.assert_failure_code(result, "missing-risk-value")

    def test_capability_route_rejects_forbidden_value_option(self) -> None:
        """A forbidden value-taking option reports its canonical flag."""
        result = self.run_route("--capability", "oop_type_design", "--name")
        self.assert_failure_code(result, "capability-input-conflict:--name")

    def test_capability_route_rejects_invalid_format(self) -> None:
        """Invalid formats preserve the raw code and use text output."""
        result = self.run_route("--capability", "oop_type_design", "--format", "xml")
        self.assert_failure_code(result, "invalid-capability-format:xml", output_format="text")

    def test_capability_route_rejects_invalid_mode(self) -> None:
        """Invalid modes preserve the raw code and use repo-changing output."""
        result = self.run_route("--capability", "oop_type_design", "--mode", "other")
        self.assert_failure_code(result, "invalid-capability-mode:other", output_format="text")

    def test_capability_route_rejects_risk_conflict(self) -> None:
        """Non-focused risk values are outside capability mode."""
        result = self.run_route("--capability", "oop_type_design", "--risk", "large")
        self.assert_failure_code(result, "capability-risk-conflict")

    def test_capability_root_uses_default_catalog_when_omitted(self) -> None:
        """Omitting root uses the current repository catalog."""
        result = self.run_route("--capability", "oop_type_design", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["capability_ids"], ["oop_type_design"])

    def test_capability_root_loads_catalog_from_resolved_root(self) -> None:
        """A custom root owns both capability and related-rule loading."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_catalog(root, self.capability_entry("custom-skill", "custom_capability"))
            result = self.run_route(
                "--root",
                str(root),
                "--capability",
                "custom_capability",
                "--format",
                "json",
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["matches"][0]["skill"], "custom-skill")

    def test_capability_root_rejects_missing_path(self) -> None:
        """A missing root is a typed root failure."""
        result = self.run_route(
            "--root",
            "/tmp/agentcanon-capability-root-does-not-exist",
            "--capability",
            "oop_type_design",
        )
        self.assert_route_source_root_failure(result, "agent_canon_source_root_missing")

    def test_capability_root_rejects_non_directory(self) -> None:
        """A file root is not accepted as a repository root."""
        with tempfile.NamedTemporaryFile() as file:
            result = self.run_route("--root", file.name, "--capability", "oop_type_design")
        self.assert_route_source_root_failure(result, "agent_canon_source_root_missing")

    def test_capability_root_rejects_missing_catalog(self) -> None:
        """A custom root without a catalog fails closed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = self.run_route("--root", tmp_dir, "--capability", "oop_type_design")
        self.assert_route_source_root_failure(result, "agent_canon_source_root_missing")

    def test_capability_root_rejects_invalid_catalog(self) -> None:
        """Malformed YAML at a custom root is a typed root failure."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog = root / "agents" / "skills" / "catalog.yaml"
            catalog.parent.mkdir(parents=True)
            catalog.write_text("skill_families: [unterminated\n", encoding="utf-8")
            result = self.run_route("--root", tmp_dir, "--capability", "oop_type_design")
        self.assert_failure_code(result, "capability-root-catalog-invalid")

    def test_capability_catalog_rejects_unknown_field(self) -> None:
        """An unknown capability record field is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_catalog(root, self.capability_entry(extra="          extra: true"))
            result = self.run_route("--root", str(root), "--capability", "oop_type_design")
        self.assert_failure_code(result, "capability-root-catalog-invalid")

    def test_capability_route_direct_unknown_id_is_fail_closed(self) -> None:
        """The direct helper has the same unknown-ID contract as the CLI."""
        rules = catalog_module.load_skill_route_rules(PROJECT_ROOT)
        index = catalog_module.build_capability_index(rules)
        with self.assertRaises(capability_module.CapabilityRouteError) as raised:
            capability_module.capability_skill_routes(("unknown_capability",), index)
        self.assertEqual(raised.exception.code, "unknown-capability:unknown_capability")

    def test_capability_route_failure_preserves_exact_error_fields(self) -> None:
        """Failure decisions keep the stable schema and empty match fields."""
        result = self.run_route("--capability", "unknown_capability", "--format", "json")
        payload = self.assert_failure_code(result, "unknown-capability:unknown_capability")
        self.assertEqual(payload["schema"], "agent_canon.route.capability_route.v1")
        self.assertEqual(payload["matches"], [])
        self.assertEqual(payload["skills"], [])
        self.assertEqual(payload["related_skills"], {})

    def test_capability_route_invalid_format_uses_text_fallback(self) -> None:
        """Invalid format diagnostics are rendered in text mode."""
        result = self.run_route("--capability", "unknown_capability", "--format", "xml")
        self.assert_failure_code(result, "invalid-capability-format:xml", output_format="text")
        self.assertTrue(result.stdout.startswith("CAPABILITY_ROUTE_SCHEMA="))

    def test_prompt_does_not_keyword_activate_oop_type_design(self) -> None:
        """Prompt mode preserves v1 behavior and does not keyword-activate the skill."""
        result = self.run_route(
            "--prompt",
            "Design OOP type boundaries before implementation.",
            "--format",
            "json",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertNotIn("oop-type-design", payload["skills"])

    def test_capability_route_freezes_related_skill_mapping(self) -> None:
        """Related skill mappings are copied into read-only views."""
        source = {"oop-type-design": ("python-review",)}
        frozen = catalog_module.freeze_related_skill_mapping(source, "related_skills")
        source["oop-type-design"] = ()
        self.assertEqual(frozen["oop-type-design"], ("python-review",))
        with self.assertRaises(TypeError):
            frozen["new"] = ()  # type: ignore[index]

    def test_capability_route_freezes_index_route_mapping(self) -> None:
        """Capability index routes cannot be mutated by callers."""
        rules = catalog_module.load_skill_route_rules(PROJECT_ROOT)
        index = catalog_module.build_capability_index(rules)
        with self.assertRaises(TypeError):
            index.routes["other"] = index.routes["oop_type_design"]  # type: ignore[index]

    def test_capability_route_freezes_index_rule_mapping(self) -> None:
        """Capability index skill rules cannot be mutated by callers."""
        rules = catalog_module.load_skill_route_rules(PROJECT_ROOT)
        index = catalog_module.build_capability_index(rules)
        with self.assertRaises(TypeError):
            index.rules_by_skill["other"] = index.rules_by_skill["oop-type-design"]  # type: ignore[index]

    def test_capability_route_json_serializes_immutable_mapping(self) -> None:
        """The JSON adapter converts immutable mappings without asdict()."""
        rules = catalog_module.load_skill_route_rules(PROJECT_ROOT)
        index = catalog_module.build_capability_index(rules)
        preflight = capability_module.CapabilityPreflight(
            ("oop_type_design",), "repo-changing", "json", "", None
        )
        decision = capability_module.decide_capabilities(
            ("oop_type_design",), "repo-changing", index, preflight
        )
        payload = route_module.capability_decision_to_json_data(decision)
        self.assertEqual(payload["related_skills"]["oop-type-design"], [
            "python-review",
            "cpp-review",
            "oop-readability-check",
        ])


if __name__ == "__main__":
    unittest.main()
