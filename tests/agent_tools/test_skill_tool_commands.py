"""Tests for runtime skill tool-command packets."""

# @dependency-start
# responsibility Tests skill tool-command packet sync and validation.
# upstream implementation ../../tools/agent_tools/skill_tool_commands.py command packet tool
# upstream design ../../agents/skills/task-routing.md deterministic skill routing contract
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

    def test_sync_adds_command_section_and_check_passes(self) -> None:
        """sync materializes the show command for every runtime skill."""
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
        """show prints commands discovered from the runtime and canon docs."""
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


if __name__ == "__main__":
    unittest.main()
