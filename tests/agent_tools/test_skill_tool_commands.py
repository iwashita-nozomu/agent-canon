"""Tests for runtime skill tool-command packets."""

# @dependency-start
# contract test
# responsibility Tests skill tool-command packet sync and validation.
# upstream implementation ../../tools/agent_tools/skill_tool_commands.py command packet tool
# upstream design ../../agents/skills/task-routing.md deterministic skill routing contract
# upstream design ../../agents/skills/catalog.yaml public skill identity and trigger catalog
# upstream design ../../agents/skills/skill-dependencies.yaml canonical dependency-derived candidates
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
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "skill_tool_commands.py"
STANDALONE_CATALOG = """version: 1
skill_families:
"""


class SkillToolCommandsTest(unittest.TestCase):
    """Verify materialized skill tool command sections."""

    def run_tool(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the skill command tool against a root."""
        return subprocess.run(
            [sys.executable, str(TOOL), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def run_tool_from_cwd(
        self,
        cwd: Path,
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        """Run the skill command tool from a specific working directory."""
        return subprocess.run(
            [sys.executable, str(TOOL), *args],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
        )

    def write_skill(self, root: Path, skill: str, body: str) -> Path:
        """Create one runtime and human-facing skill pair."""
        runtime = root / ".agents" / "skills" / skill / "SKILL.md"
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_text(f"# {skill}\n\n{body}", encoding="utf-8")
        canon = root / "agents" / "skills" / f"{skill}.md"
        canon.parent.mkdir(parents=True, exist_ok=True)
        canon.write_text(
            f"# {skill}\n\n```bash\npython3 tools/agent_tools/example.py\n```\n",
            encoding="utf-8",
        )
        self.write_dependency_map(
            root,
            [
                f"  {skill}:",
                "    responsibility_group: fixture",
                "    required_prerequisites: []",
                "    successors: []",
                "    order_constraints: []",
                "    parallel_independent: []",
            ],
        )
        catalog = root / "agents" / "skills" / "catalog.yaml"
        catalog.parent.mkdir(parents=True, exist_ok=True)
        catalog.write_text(
            "\n".join(
                [
                    "version: 1",
                    "skill_families:",
                    f"  - id: {skill}",
                    f"    canonical_doc: agents/skills/{skill}.md",
                    f"    shim: .agents/skills/{skill}/SKILL.md",
                    "    routing:",
                    "      stage_policy: active",
                    "      reason: test fixture",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return runtime

    def write_catalog(self, root: Path, entries: list[str]) -> None:
        """Create one public skill catalog fixture."""
        catalog = root / "agents" / "skills" / "catalog.yaml"
        catalog.parent.mkdir(parents=True, exist_ok=True)
        catalog.write_text(
            "\n".join(["version: 1", "skill_families:", *entries]),
            encoding="utf-8",
        )
        skill_ids = [
            line.strip()[len("- id: ") :]
            for line in entries
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
        self.write_dependency_map(root, dependency_lines[2:])

    def write_dependency_map(self, root: Path, lines: list[str]) -> None:
        """Create one dependency dictionary fixture."""
        path = root / "agents" / "skills" / "skill-dependencies.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(["version: 1", "skill_dependencies:", *lines]),
            encoding="utf-8",
        )

    def test_sync_adds_command_section_and_check_passes(self) -> None:
        """Sync materializes the show command for every runtime skill."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            skill = self.write_skill(root, "example-skill", "Use the canon.\n")

            sync = self.run_tool(root, "sync")
            check = self.run_tool(root, "check")

            self.assertEqual(sync.returncode, 0, sync.stdout + sync.stderr)
            self.assertIn("SKILL_TOOL_COMMANDS_SYNC=pass", sync.stdout)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertIn(
                "python3 tools/agent_tools/skill_tool_commands.py show "
                "--skill example-skill --format text",
                skill.read_text(encoding="utf-8"),
            )

    def test_show_returns_discovered_commands(self) -> None:
        """Show prints commands discovered from the runtime and canon docs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(
                root,
                "example-skill",
                "```bash\nmake check-matrix\n```\n",
            )

            result = self.run_tool(root, "show", "--skill", "example-skill", "--format", "json")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["skill"], "example-skill")
        self.assertEqual(payload["required_commands"], [])
        self.assertIn("make check-matrix", payload["discovered_commands"])
        self.assertIn(
            "python3 tools/agent_tools/example.py",
            payload["discovered_commands"],
        )

    def test_show_includes_resolved_command_plans(self) -> None:
        """Start-repository plans resolve scripts without pathifying Bash options."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(
                root,
                "start-repository",
                "```bash\npython3 tools/agent_tools/example.py\n```\n",
            )
            (root / "agents" / "skills" / "start-repository.md").write_text(
                (
                    "```bash\n"
                    "bash scripts/start_repository.sh --validate-only\n"
                    "bash -c 'scripts/start_repository.sh --validate-only'\n"
                    "python3 tools/agent_tools/example.py --root .\n"
                    "bash ./tools/agent_tools/example.sh --root .\n"
                    "PYTHONPATH=tools python3 tools/agent_tools/example.py check\n"
                    "python3 tools/agent_tools/example.py .\n"
                    "bash ./tools/agent_tools/example.sh .\n"
                    "python3 tools/agent_tools/example.py --root /tmp/explicit\n"
                    "python3 tools/agent_tools/example.py --root=.\n"
                    "python3 tools/agent_tools/example.py --root=. .\n"
                    "```\n"
                ),
                encoding="utf-8",
            )

            result = self.run_tool(
                root,
                "show",
                "--skill",
                "start-repository",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            resolved = {
                row[0]: row for row in payload["resolved_discovered_commands"]
            }
            expected_root = str(root.resolve())
            self.assertEqual(
                resolved["bash scripts/start_repository.sh --validate-only"][4],
                [
                    "bash",
                    f"{expected_root}/scripts/start_repository.sh",
                    "--validate-only",
                ],
            )
            self.assertEqual(
                resolved["bash -c 'scripts/start_repository.sh --validate-only'"][4],
                ["bash", "-c", "scripts/start_repository.sh --validate-only"],
            )
            self.assertIn(
                "python3 tools/agent_tools/example.py --root .",
                resolved,
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root ."][0],
                "python3 tools/agent_tools/example.py --root .",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root ."][1],
                expected_root,
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root ."][2],
                expected_root,
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root ."][4][0],
                "python3",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root ."][4][1],
                f"{expected_root}/tools/agent_tools/example.py",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root ."][4][2],
                "--root",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root ."][4][3],
                expected_root,
            )
            self.assertEqual(
                resolved["bash ./tools/agent_tools/example.sh --root ."][4][0],
                "bash",
            )
            self.assertEqual(
                resolved["bash ./tools/agent_tools/example.sh --root ."][4][1],
                f"{expected_root}/tools/agent_tools/example.sh",
            )
            self.assertIn(
                "python3 tools/agent_tools/example.py --root /tmp/explicit",
                resolved,
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root /tmp/explicit"][4][0],
                "python3",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root /tmp/explicit"][4][1],
                f"{expected_root}/tools/agent_tools/example.py",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root /tmp/explicit"][4][2],
                "--root",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root /tmp/explicit"][4][3],
                "/tmp/explicit",
            )
            self.assertEqual(
                len(resolved["python3 tools/agent_tools/example.py --root /tmp/explicit"][4]),
                4,
            )
            self.assertIn(
                "python3 tools/agent_tools/example.py --root=.",
                resolved,
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root=."][4][0],
                "python3",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root=."][4][1],
                f"{expected_root}/tools/agent_tools/example.py",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root=."][4][2],
                f"--root={expected_root}",
            )
            self.assertIn(
                "python3 tools/agent_tools/example.py --root=. .",
                resolved,
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root=. ."][4][0],
                "python3",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root=. ."][4][1],
                f"{expected_root}/tools/agent_tools/example.py",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root=. ."][4][2],
                f"--root={expected_root}",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py --root=. ."][4][3],
                ".",
            )
            self.assertIn(
                "python3 tools/agent_tools/example.py .",
                resolved,
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py ."][4][0],
                "python3",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py ."][4][1],
                f"{expected_root}/tools/agent_tools/example.py",
            )
            self.assertEqual(
                resolved["python3 tools/agent_tools/example.py ."][4][2],
                ".",
            )
            self.assertIn(
                "bash ./tools/agent_tools/example.sh .",
                resolved,
            )
            self.assertEqual(
                resolved["bash ./tools/agent_tools/example.sh ."][4][0],
                "bash",
            )
            self.assertEqual(
                resolved["bash ./tools/agent_tools/example.sh ."][4][1],
                f"{expected_root}/tools/agent_tools/example.sh",
            )
            self.assertEqual(
                resolved["bash ./tools/agent_tools/example.sh ."][4][2],
                ".",
            )
            self.assertIn(
                "PYTHONPATH=tools python3 tools/agent_tools/example.py check",
                resolved,
            )
            self.assertEqual(
                resolved["PYTHONPATH=tools python3 tools/agent_tools/example.py check"][3],
                [["PYTHONPATH", "tools"]],
            )
            self.assertEqual(
                resolved["PYTHONPATH=tools python3 tools/agent_tools/example.py check"][4],
                [
                    "python3",
                    f"{expected_root}/tools/agent_tools/example.py",
                    "check",
                ],
            )

    def test_show_resolves_fallback_only_skill_with_command_plan(self) -> None:
        """Fallback packets preserve complete Python script resolution."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(root, "fallback-skill", "No executable command is documented.\n")
            (root / "agents" / "skills" / "fallback-skill.md").write_text(
                "# fallback-skill\n\nNo executable command is documented.\n",
                encoding="utf-8",
            )

            result = self.run_tool(
                root,
                "show",
                "--skill",
                "fallback-skill",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["discovered_commands"], [])
            self.assertEqual(len(payload["resolved_discovered_commands"]), 1)
            logical, source_root, execution_cwd, execution_env, argv = payload[
                "resolved_discovered_commands"
            ][0]
            expected_root = str(root.resolve())
            self.assertEqual(
                logical,
                "python3 tools/agent_tools/route.py --prompt '<user request>' --format json",
            )
            self.assertEqual(source_root, expected_root)
            self.assertEqual(execution_env, [])
            self.assertEqual(execution_cwd, expected_root)
            self.assertEqual(argv[0], "python3")
            self.assertEqual(argv[1], f"{expected_root}/tools/agent_tools/route.py")
            self.assertEqual(argv[2:], ["--prompt", "<user request>", "--format", "json"])

    def test_show_deduplicates_parent_agents_symlink_view(self) -> None:
        """A real parent agents symlink view uses the vendored source root once."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent_root = Path(tmp_dir)
            (parent_root / ".git").touch()
            source_root = parent_root / "source" / "agent-canon"
            self.write_skill(source_root, "example-skill", "Use the canon.\n")
            vendor_link = parent_root / "vendor" / "agent-canon"
            vendor_link.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(source_root, vendor_link, target_is_directory=True)
            os.symlink(
                vendor_link / "agents",
                parent_root / "agents",
                target_is_directory=True,
            )

            result = self.run_tool(
                parent_root,
                "show",
                "--skill",
                "example-skill",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["runtime_skill"], ".agents/skills/example-skill/SKILL.md")
            self.assertEqual(
                {
                    row[1] for row in payload["resolved_discovered_commands"]
                },
                {str(source_root.resolve())},
            )

    def test_show_rejects_different_symlink_view_entity(self) -> None:
        """A parent symlink view to a different source remains ambiguous."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent_root = Path(tmp_dir)
            (parent_root / ".git").touch()
            standalone_root = parent_root / "standalone"
            self.write_skill(standalone_root, "example-skill", "Use the standalone canon.\n")
            vendor_root = parent_root / "vendor" / "agent-canon"
            self.write_skill(vendor_root, "example-skill", "Use the vendored canon.\n")
            os.symlink(
                standalone_root / "agents",
                parent_root / "agents",
                target_is_directory=True,
            )

            result = self.run_tool(
                parent_root,
                "show",
                "--skill",
                "example-skill",
                "--format",
                "text",
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn(
                "SKILL_TOOL_COMMANDS_SOURCE_ROOT_FAILURE=agent_canon_source_root_ambiguous",
                result.stdout + result.stderr,
            )

    def test_show_rejects_external_vendor_symlink(self) -> None:
        """A vendor symlink outside the parent repository is a typed failure."""
        with tempfile.TemporaryDirectory() as tmp_dir, tempfile.TemporaryDirectory() as outside_dir:
            parent_root = Path(tmp_dir)
            (parent_root / ".git").touch()
            outside_root = Path(outside_dir) / "agent-canon"
            self.write_skill(outside_root, "example-skill", "Use the external canon.\n")
            vendor_link = parent_root / "vendor" / "agent-canon"
            vendor_link.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(outside_root, vendor_link, target_is_directory=True)

            result = self.run_tool(
                parent_root,
                "show",
                "--skill",
                "example-skill",
                "--format",
                "text",
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn(
                "SKILL_TOOL_COMMANDS_SOURCE_ROOT_FAILURE=agent_canon_source_root_vendor_outside_repository",
                result.stdout + result.stderr,
            )

    def test_common_entry_wording_is_synced(self) -> None:
        """Canonical and generated skill entries state the source-root contract."""
        source_root_wording = (
            "論理コマンドは、実行前に AgentCanon source root を基準として解決します。"
        )
        generated_wording = (
            "この skill の workflow を適用する前に、次の command packet を使用してください。",
            source_root_wording,
            "packet が出力した必須 command と、task に該当する conditional command を実行してください。",
        )
        canonical = (PROJECT_ROOT / "agents/skills/agent-orchestration.md").read_text(
            encoding="utf-8"
        )
        runtime = (PROJECT_ROOT / ".agents/skills/agent-orchestration/SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(source_root_wording, canonical)
        for wording in generated_wording:
            self.assertIn(wording, runtime)

    def test_resolve_source_root_fails_with_missing_catalog(self) -> None:
        """The command tool returns typed failure when no source root is detectable."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            result = self.run_tool(
                root,
                "show",
                "--skill",
                "example-skill",
                "--format",
                "text",
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn(
                "SKILL_TOOL_COMMANDS_SOURCE_ROOT_FAILURE=agent_canon_source_root_missing",
                result.stdout + result.stderr,
            )

    def test_resolve_source_root_rejects_ambiguous_catalogs(self) -> None:
        """Ambiguous standalone and vendored catalog roots are rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "agents" / "skills").mkdir(parents=True, exist_ok=True)
            (root / "agents" / "skills" / "catalog.yaml").write_text(
                STANDALONE_CATALOG,
                encoding="utf-8",
            )
            (root / "vendor" / "agent-canon" / "agents" / "skills" / "catalog.yaml").parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            (root / "vendor" / "agent-canon" / "agents" / "skills").mkdir(parents=True, exist_ok=True)
            (root / "vendor" / "agent-canon" / "agents" / "skills" / "catalog.yaml").write_text(
                STANDALONE_CATALOG,
                encoding="utf-8",
            )

            result = self.run_tool(
                root,
                "show",
                "--skill",
                "example-skill",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn(
                "SKILL_TOOL_COMMANDS_SOURCE_ROOT_FAILURE=agent_canon_source_root_ambiguous",
                result.stdout + result.stderr,
            )

    def test_show_resolves_source_root_from_cwd(self) -> None:
        """Show command resolves source root from parent root and child directories."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").touch()
            (root / "agents" / "skills").mkdir(parents=True, exist_ok=True)
            (root / "agents" / "skills" / "catalog.yaml").write_text(
                STANDALONE_CATALOG,
                encoding="utf-8",
            )
            (root / "agents" / "skills" / "skill-dependencies.yaml").write_text(
                "version: 1\nskill_dependencies: {}\n",
                encoding="utf-8",
            )
            self.write_skill(
                root,
                "example-skill",
                "```bash\nmake check-matrix\n```\n",
            )
            child = root / "workspace" / "subdir"
            child.mkdir(parents=True, exist_ok=True)
            standalone_child = root / "agents" / "standalone" / "child"
            standalone_child.mkdir(parents=True, exist_ok=True)

            for cwd in (root, child, standalone_child):
                result = self.run_tool_from_cwd(
                    cwd,
                    "show",
                    "--skill",
                    "example-skill",
                    "--format",
                    "json",
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_code_visualization_packet_contains_only_renderer_variants(self) -> None:
        """The code-visualization packet exposes exactly its two graph renderers."""
        result = self.run_tool(
            PROJECT_ROOT,
            "show",
            "--skill",
            "code-visualization",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["required_commands"], [])
        self.assertEqual(
            payload["discovered_commands"],
            [
                "python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope full --bundle-dir reports/dependency-graph --format json",
                "python3 tools/agent_tools/render_dependency_manifest_graph.py --root . --scope changed --bundle-dir reports/dependency-graph --format json",
            ],
        )
        for command in payload["discovered_commands"]:
            self.assertIn(" --root . ", command)
            self.assertTrue(command.endswith(" --format json"))
        for forbidden in ("route.py", "scan_code_dependencies.py", "helper_function_inventory.py"):
            self.assertNotIn(forbidden, payload["discovered_commands"])
        self.assertNotIn("sed -n", result.stdout)

    def test_agent_orchestration_packet_requires_execution_contract_checker(self) -> None:
        """The canonical skill catalog supplies the required owner checker."""
        result = self.run_tool(
            PROJECT_ROOT,
            "show",
            "--skill",
            "agent-orchestration",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["required_commands"],
            [
                "python3 tools/agent_tools/check_execution_time_aware_orchestration.py --root ."
            ],
        )
        shim = (PROJECT_ROOT / ".agents/skills/agent-orchestration/SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(payload["required_commands"][0], shim)

    def test_show_marks_validation_as_maintenance_only(self) -> None:
        """Show keeps validation commands out of the default action path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(root, "example-skill", "Use the canon.\n")

            result = self.run_tool(root, "show", "--skill", "example-skill")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SKILL_TOOL_COMMANDS_MAINTENANCE_ONLY:", result.stdout)
            self.assertIn("Run these only when editing skill command sections", result.stdout)

    def test_show_returns_dependency_derived_related_skills(self) -> None:
        """Show projects related skills from routing candidates, not successors."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(root, "example-skill", "Use the canon.\n")
            self.write_skill(root, "review-skill", "Use the canon.\n")
            self.write_catalog(
                root,
                [
                    "  - id: example-skill",
                    "    canonical_doc: agents/skills/example-skill.md",
                    "    shim: .agents/skills/example-skill/SKILL.md",
                    "  - id: review-skill",
                    "    canonical_doc: agents/skills/review-skill.md",
                    "    shim: .agents/skills/review-skill/SKILL.md",
                ],
            )
            self.write_dependency_map(
                root,
                [
                    "  example-skill:",
                    "    responsibility_group: fixture",
                    "    required_prerequisites: []",
                    "    routing_candidates:",
                    "      - review-skill",
                    "    successors: []",
                    "    order_constraints: []",
                    "    parallel_independent: []",
                    "  review-skill:",
                    "    responsibility_group: fixture",
                    "    required_prerequisites: []",
                    "    routing_candidates: []",
                    "    successors: []",
                    "    order_constraints: []",
                    "    parallel_independent: []",
                ],
            )

            json_result = self.run_tool(
                root,
                "show",
                "--skill",
                "example-skill",
                "--format",
                "json",
            )
            text_result = self.run_tool(root, "show", "--skill", "example-skill")

            self.assertEqual(json_result.returncode, 0, json_result.stdout + json_result.stderr)
            self.assertEqual(text_result.returncode, 0, text_result.stdout + text_result.stderr)
            payload = json.loads(json_result.stdout)
            self.assertEqual(payload["related_skills"], ["review-skill"])
            self.assertIn("SKILL_TOOL_COMMANDS_RELATED_SKILLS=$review-skill", text_result.stdout)

    def test_show_ignores_directory_literals(self) -> None:
        """Show excludes directory paths that are not executable commands."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(
                root,
                "example-skill",
                "Shared automation lives in `tools/`.\n",
            )

            result = self.run_tool(root, "show", "--skill", "example-skill", "--format", "json")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertNotIn("tools/", payload["discovered_commands"])

    def test_check_rejects_bare_internal_tool_command(self) -> None:
        """Check reports issue-backed bare internal tool command drift."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(
                root,
                "result-artifact-writeout",
                "Run `runtime_log_archive_git.py push` after archiving.\n",
            )
            sync = self.run_tool(root, "sync")

            result = self.run_tool(root, "check")

            self.assertIn("SKILL_TOOL_COMMANDS_SYNC_CHANGED=1", sync.stdout)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("bare-runtime-log-archive-push:present", result.stdout)

    def test_check_requires_template_root_document_resolution_marker(self) -> None:
        """Check reports issue-backed AgentCanon document path resolution drift."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(
                root,
                "start-repository",
                "Read `documents/agent-canon/agent-canon-github-remote.md`.\n",
            )
            sync = self.run_tool(root, "sync")

            result = self.run_tool(root, "check")

            self.assertIn("SKILL_TOOL_COMMANDS_SYNC_CHANGED=1", sync.stdout)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("remote-doc-template-path:missing", result.stdout)

    def test_check_accepts_qualified_workflow_monitoring_paths(self) -> None:
        """Check allows run-local and template workflow monitoring paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(
                root,
                "tool-finding-report",
                (
                    "Register warnings in `reports/agents/123/workflow_monitoring.md` "
                    "using template `templates/agents/workflow_monitoring.md`.\n"
                ),
            )
            sync = self.run_tool(root, "sync")

            result = self.run_tool(root, "check")

            self.assertEqual(sync.returncode, 0, sync.stdout + sync.stderr)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
