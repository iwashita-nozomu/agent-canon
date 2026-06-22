# @dependency-start
# contract test
# responsibility Tests runtime skill frontmatter validation.
# upstream implementation ../../tools/agent_tools/check_skill_frontmatter.py validates SKILL.md frontmatter
# upstream design ../../agents/canonical/skills.md skill runtime registry contract
# @dependency-end
"""Tests for runtime skill frontmatter validation."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "check_skill_frontmatter.py"


def skill_text(name: str, description: str) -> str:
    """Return one runtime skill shim body."""
    return "\n".join(
        [
            "---",
            f"name: {name}",
            f"description: {description}",
            "---",
            "",
            f"# {name}",
            "",
        ]
    )


class CheckSkillFrontmatterTest(unittest.TestCase):
    """Verify skill frontmatter validation behavior."""

    def run_cli(self, root: Path) -> subprocess.CompletedProcess[str]:
        """Run the frontmatter validator against a root."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_skill(self, root: Path, name: str, body: str) -> None:
        """Write one SKILL.md file below the runtime skill directory."""
        path = root / ".agents" / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_current_repository_frontmatter_passes(self) -> None:
        """Current runtime skill shims should all have parseable YAML."""
        result = self.run_cli(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SKILL_FRONTMATTER=pass", result.stdout)

    def test_unquoted_description_colon_fails(self) -> None:
        """A colon in an unquoted description should fail as invalid YAML."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(
                root,
                "broken-skill",
                skill_text("broken-skill", "Use when processing queues: inventory items."),
            )

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("SKILL_FRONTMATTER=fail", result.stdout)
            self.assertIn(".agents/skills/broken-skill/SKILL.md", result.stdout)
            self.assertIn("invalid-yaml", result.stdout)

    def test_quoted_description_colon_passes(self) -> None:
        """A quoted description containing a colon should pass."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(
                root,
                "quoted-skill",
                textwrap.dedent(
                    '''\
                    ---
                    name: quoted-skill
                    description: "Use when processing queues: inventory items."
                    ---

                    # quoted-skill
                    '''
                ),
            )

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SKILL_FRONTMATTER=pass", result.stdout)

    def test_private_underscore_prefixed_skill_name_passes(self) -> None:
        """Private runtime skill shims use a leading underscore in the skill name."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(
                root,
                "_internal-skill",
                skill_text("_internal-skill", "Use for internal runtime routing."),
            )

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SKILL_FRONTMATTER=pass", result.stdout)

    def test_internal_underscore_skill_name_fails(self) -> None:
        """Skill names use hyphens after the optional private prefix."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_skill(
                root,
                "internal_skill",
                skill_text("internal_skill", "Use for invalid runtime routing."),
            )

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("SKILL_FRONTMATTER=fail", result.stdout)
            self.assertIn("invalid-name:internal_skill", result.stdout)


if __name__ == "__main__":
    unittest.main()
