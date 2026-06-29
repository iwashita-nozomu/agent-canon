"""Tests for runtime skill tool-command packets."""

# @dependency-start
# contract test
# responsibility Tests skill tool-command packet sync and validation.
# upstream implementation ../../tools/agent_tools/skill_tool_commands.py command packet tool
# upstream design ../../agents/skills/task-routing.md deterministic skill routing contract
# upstream design ../../agents/skills/catalog.yaml public skill related-skill metadata
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "skill_tool_commands.py"


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
        return runtime

    def write_catalog(self, root: Path, entries: list[str]) -> None:
        """Create one public skill catalog fixture."""
        catalog = root / "agents" / "skills" / "catalog.yaml"
        catalog.parent.mkdir(parents=True, exist_ok=True)
        catalog.write_text(
            "\n".join(["version: 1", "skill_families:", *entries]),
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
            self.assertIn("make check-matrix", payload["discovered_commands"])
            self.assertIn(
                "python3 tools/agent_tools/example.py",
                payload["discovered_commands"],
            )

    def test_show_marks_validation_as_maintenance_only(self) -> None:
        """Show keeps validation commands out of the default action path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(root, "example-skill", "Use the canon.\n")

            result = self.run_tool(root, "show", "--skill", "example-skill")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SKILL_TOOL_COMMANDS_MAINTENANCE_ONLY:", result.stdout)
            self.assertIn("Run these only when editing skill command sections", result.stdout)

    def test_show_returns_related_skills_from_catalog(self) -> None:
        """Show prints related skills from the public skill catalog."""
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
                    "    related_skills:",
                    "      - review-skill",
                    "  - id: review-skill",
                    "    canonical_doc: agents/skills/review-skill.md",
                    "    shim: .agents/skills/review-skill/SKILL.md",
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
                "Read `documents/agent-canon-github-remote.md`.\n",
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
                    "using template `agents/templates/workflow_monitoring.md`.\n"
                ),
            )
            sync = self.run_tool(root, "sync")

            result = self.run_tool(root, "check")

            self.assertEqual(sync.returncode, 0, sync.stdout + sync.stderr)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
