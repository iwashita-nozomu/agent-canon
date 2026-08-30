"""Tests for runtime skill tool-command packets."""

# @dependency-start
# contract test
# responsibility Tests skill tool-command packet production and read-only validation.
# upstream implementation ../../tools/agent/skills/skill_tool_commands.py command packet tool
# upstream design ../../agents/skills/task-routing.md deterministic skill routing contract
# upstream design ../../agents/skills/catalog.yaml public skill identity and trigger catalog
# upstream design ../../agents/skills/skill-dependencies.yaml canonical dependency-derived candidates
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from tools.runtime.source.agent_canon_source_root import RootResolution  # noqa: E402
from tools.agent.skills.skill_tool_commands import project_public_command  # noqa: E402
TOOL = PROJECT_ROOT / "tools" / "agent" / "skills" / "skill_tool_commands.py"
STANDALONE_CATALOG = """version: 1
skill_families:
"""


class SkillToolCommandsTest(unittest.TestCase):
    """Verify materialized skill tool command sections."""

    def test_public_projection_keeps_logical_plan_and_layout_prefix(self) -> None:
        """Derived public argv is separate from the source execution spelling."""
        logical = (
            "PYTHONPATH=tools python3 tools/runtime/lifecycle/workflow_monitor.py "
            "--root . --contract documents/structure/repo-structure-contract.toml"
        )
        standalone = project_public_command(
            logical,
            RootResolution(Path("."), Path("."), "standalone", Path(".")),
        )
        derived = project_public_command(
            logical,
            RootResolution(Path("."), Path("."), "external", Path(".")),
        )
        self.assertEqual(standalone.public_argv[1], "tools/runtime/lifecycle/workflow_monitor.py")
        self.assertEqual(derived.public_argv[1], "tools/runtime/lifecycle/workflow_monitor.py")
        self.assertEqual(
            standalone.public_argv[2:],
            ("--root", ".", "--contract", "documents/structure/repo-structure-contract.toml"),
        )
        self.assertEqual(derived.public_argv[2:], standalone.public_argv[2:])
        self.assertEqual(derived.public_env, (("PYTHONPATH", "tools"),))

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
        runtime = root / ".codex" / "personal" / "skills" / skill / "SKILL.md"
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_text(f"# {skill}\n\n{body}", encoding="utf-8")
        canon = root / "agents" / "skills" / f"{skill}.md"
        canon.parent.mkdir(parents=True, exist_ok=True)
        canon.write_text(
            f"# {skill}\n\n```bash\npython3 tools/runtime/lifecycle/workflow_monitor.py\n```\n",
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
                    f"    shim: .codex/personal/skills/{skill}/SKILL.md",
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

    def test_sync_is_rejected_and_does_not_write(self) -> None:
        """The removed sync surface is not a compatibility writer."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            skill = self.write_skill(root, "example-skill", "Use the canon.\n")
            before = skill.read_bytes()

            sync = self.run_tool(root, "sync")

            self.assertNotEqual(sync.returncode, 0)
            self.assertIn("invalid choice", sync.stderr)
            self.assertEqual(before, skill.read_bytes())

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
            "python3 tools/runtime/lifecycle/workflow_monitor.py",
            payload["discovered_commands"],
        )

    def test_show_includes_resolved_command_plans(self) -> None:
        """Start-repository plans resolve scripts without pathifying Bash options."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(
                root,
                "start-repository",
                "```bash\npython3 tools/runtime/lifecycle/workflow_monitor.py\n```\n",
            )
            (root / "agents" / "skills" / "start-repository.md").write_text(
                (
                    "```bash\n"
                    "bash scripts/start_repository.sh --validate-only\n"
                    "bash -c 'scripts/start_repository.sh --validate-only'\n"
                    "python3 tools/runtime/lifecycle/workflow_monitor.py --root .\n"
                    "bash ./tools/validation/ci/runners/run_all_checks.sh --root .\n"
                    "PYTHONPATH=tools python3 tools/runtime/lifecycle/workflow_monitor.py check\n"
                    "python3 tools/runtime/lifecycle/workflow_monitor.py .\n"
                    "bash ./tools/validation/ci/runners/run_all_checks.sh .\n"
                    "python3 tools/runtime/lifecycle/workflow_monitor.py --root /tmp/explicit\n"
                    "python3 tools/runtime/lifecycle/workflow_monitor.py --root=.\n"
                    "python3 tools/runtime/lifecycle/workflow_monitor.py --root=. .\n"
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
                "python3 tools/runtime/lifecycle/workflow_monitor.py --root .",
                resolved,
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root ."][0],
                "python3 tools/runtime/lifecycle/workflow_monitor.py --root .",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root ."][1],
                expected_root,
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root ."][2],
                expected_root,
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root ."][4][0],
                "python3",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root ."][4][1],
                f"{expected_root}/tools/runtime/lifecycle/workflow_monitor.py",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root ."][4][2],
                "--root",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root ."][4][3],
                expected_root,
            )
            self.assertEqual(
                resolved["bash ./tools/validation/ci/runners/run_all_checks.sh --root ."][4][0],
                "bash",
            )
            self.assertEqual(
                resolved["bash ./tools/validation/ci/runners/run_all_checks.sh --root ."][4][1],
                f"{expected_root}/tools/validation/ci/runners/run_all_checks.sh",
            )
            self.assertIn(
                "python3 tools/runtime/lifecycle/workflow_monitor.py --root /tmp/explicit",
                resolved,
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root /tmp/explicit"][4][0],
                "python3",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root /tmp/explicit"][4][1],
                f"{expected_root}/tools/runtime/lifecycle/workflow_monitor.py",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root /tmp/explicit"][4][2],
                "--root",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root /tmp/explicit"][4][3],
                "/tmp/explicit",
            )
            self.assertEqual(
                len(resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root /tmp/explicit"][4]),
                4,
            )
            self.assertIn(
                "python3 tools/runtime/lifecycle/workflow_monitor.py --root=.",
                resolved,
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root=."][4][0],
                "python3",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root=."][4][1],
                f"{expected_root}/tools/runtime/lifecycle/workflow_monitor.py",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root=."][4][2],
                f"--root={expected_root}",
            )
            self.assertIn(
                "python3 tools/runtime/lifecycle/workflow_monitor.py --root=. .",
                resolved,
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root=. ."][4][0],
                "python3",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root=. ."][4][1],
                f"{expected_root}/tools/runtime/lifecycle/workflow_monitor.py",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root=. ."][4][2],
                f"--root={expected_root}",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py --root=. ."][4][3],
                ".",
            )
            self.assertIn(
                "python3 tools/runtime/lifecycle/workflow_monitor.py .",
                resolved,
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py ."][4][0],
                "python3",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py ."][4][1],
                f"{expected_root}/tools/runtime/lifecycle/workflow_monitor.py",
            )
            self.assertEqual(
                resolved["python3 tools/runtime/lifecycle/workflow_monitor.py ."][4][2],
                ".",
            )
            self.assertIn(
                "bash ./tools/validation/ci/runners/run_all_checks.sh .",
                resolved,
            )
            self.assertEqual(
                resolved["bash ./tools/validation/ci/runners/run_all_checks.sh ."][4][0],
                "bash",
            )
            self.assertEqual(
                resolved["bash ./tools/validation/ci/runners/run_all_checks.sh ."][4][1],
                f"{expected_root}/tools/validation/ci/runners/run_all_checks.sh",
            )
            self.assertEqual(
                resolved["bash ./tools/validation/ci/runners/run_all_checks.sh ."][4][2],
                ".",
            )
            self.assertIn(
                "PYTHONPATH=tools python3 tools/runtime/lifecycle/workflow_monitor.py check",
                resolved,
            )
            self.assertEqual(
                resolved["PYTHONPATH=tools python3 tools/runtime/lifecycle/workflow_monitor.py check"][3],
                [["PYTHONPATH", "tools"]],
            )
            self.assertEqual(
                resolved["PYTHONPATH=tools python3 tools/runtime/lifecycle/workflow_monitor.py check"][4],
                [
                    "python3",
                    f"{expected_root}/tools/runtime/lifecycle/workflow_monitor.py",
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
                "python3 tools/agent/orchestration/route.py --prompt '<user request>' --format json",
            )
            self.assertEqual(source_root, expected_root)
            self.assertEqual(execution_env, [])
            self.assertEqual(execution_cwd, expected_root)
            self.assertEqual(argv[0], "python3")
            self.assertEqual(argv[1], f"{expected_root}/tools/agent/orchestration/route.py")
            self.assertEqual(argv[2:], ["--prompt", "<user request>", "--format", "json"])

    def test_generated_entry_is_a_read_only_packet_projection(self) -> None:
        """The materialized adapter exposes a read-only packet path."""
        runtime = (PROJECT_ROOT / ".codex/personal/skills/agent-orchestration/SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Canonical workflow and policy:", runtime)
        self.assertIn("skill_tool_commands.py show --skill agent-orchestration --format text", runtime)
        self.assertNotIn("skill_tool_commands.py sync", runtime)

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
                "python3 tools/analysis/dependencies/render_dependency_manifest_graph.py --root . --scope full --bundle-dir reports/dependency-graph --format json",
                "python3 tools/analysis/dependencies/render_dependency_manifest_graph.py --root . --scope changed --bundle-dir reports/dependency-graph --format json",
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
                "python3 tools/validation/semantic/orchestration/check_execution_time_aware_orchestration.py --root ."
            ],
        )
        shim = (PROJECT_ROOT / ".codex/personal/skills/agent-orchestration/SKILL.md").read_text(
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
                    "    shim: .codex/personal/skills/example-skill/SKILL.md",
                    "  - id: review-skill",
                    "    canonical_doc: agents/skills/review-skill.md",
                    "    shim: .codex/personal/skills/review-skill/SKILL.md",
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
            result = self.run_tool(root, "check")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("bare-runtime-log-archive-push:present", result.stdout)

    def test_check_requires_project_owned_bootstrap_document_markers(self) -> None:
        """Check keeps default repository startup on project-owned static contracts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(
                root,
                "start-repository",
                (
                    "Read `documents/contracts/template-bootstrap.md` and "
                    "`documents/contracts/static-seed-export.md`.\n"
                ),
            )
            result = self.run_tool(root, "check")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("remote-doc-project-path:missing", result.stdout)
            self.assertNotIn("profile-doc-template-path", result.stdout)

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
            result = self.run_tool(root, "check")

            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("workflow_monitoring.md:present", result.stdout)


if __name__ == "__main__":
    unittest.main()
