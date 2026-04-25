# @dependency-start
# @dependency-end

"""Tests for the skill shim mirror helper."""

# Dependency Files:
# - vendor/agent-canon/tools/docs/mirror_skill_shims.py

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "docs" / "mirror_skill_shims.py"


def skill_text(name: str) -> str:
    """Return one valid SKILL.md body."""
    return "\n".join(
        [
            "---",
            f"name: {name}",
            f"description: {name} skill.",
            "---",
            "",
            f"# {name}",
            "",
        ]
    )


class MirrorSkillShimsTest(unittest.TestCase):
    """Exercise the mirror helper through its CLI."""

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the mirror helper and capture its output."""
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_file(self, path: Path, contents: str) -> None:
        """Create a file with parent directories as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def test_check_reports_pending_changes(self) -> None:
        """The check mode should report missing, changed, and stale files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source"
            target = root / "target"

            self.write_file(source / "skill-a" / "SKILL.md", skill_text("skill-a"))
            self.write_file(source / "skill-a" / "references" / "guide.md", "guide v2\n")
            self.write_file(source / "skill-b" / "SKILL.md", skill_text("skill-b"))

            self.write_file(target / "skill-a" / "SKILL.md", skill_text("skill-a-old"))
            self.write_file(target / "skill-a" / "stale.txt", "remove me\n")
            self.write_file(target / "skill-old" / "SKILL.md", skill_text("skill-old"))

            result = self.run_cli(
                "--source",
                str(source),
                "--target",
                str(target),
                "--prune",
                "--check",
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("update", result.stdout)
            self.assertIn("create", result.stdout)
            self.assertIn("remove", result.stdout)

    def test_sync_and_prune_make_target_match_source(self) -> None:
        """A sync run should copy nested files and prune stale content."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source"
            target = root / "target"

            self.write_file(source / "skill-a" / "SKILL.md", skill_text("skill-a"))
            self.write_file(source / "skill-a" / "references" / "guide.md", "guide v2\n")
            self.write_file(source / "skill-b" / "SKILL.md", skill_text("skill-b"))

            self.write_file(target / "skill-a" / "SKILL.md", skill_text("skill-a-old"))
            self.write_file(target / "skill-a" / "stale.txt", "remove me\n")
            self.write_file(target / "skill-old" / "SKILL.md", skill_text("skill-old"))

            sync_result = self.run_cli(
                "--source",
                str(source),
                "--target",
                str(target),
                "--prune",
            )
            self.assertEqual(sync_result.returncode, 0, sync_result.stderr)

            self.assertEqual(
                (target / "skill-a" / "SKILL.md").read_text(encoding="utf-8"),
                skill_text("skill-a"),
            )
            self.assertEqual(
                (target / "skill-a" / "references" / "guide.md").read_text(encoding="utf-8"),
                "guide v2\n",
            )
            self.assertEqual(
                (target / "skill-b" / "SKILL.md").read_text(encoding="utf-8"),
                skill_text("skill-b"),
            )
            self.assertFalse((target / "skill-a" / "stale.txt").exists())
            self.assertFalse((target / "skill-old").exists())

            check_result = self.run_cli(
                "--source",
                str(source),
                "--target",
                str(target),
                "--prune",
                "--check",
            )
            self.assertEqual(check_result.returncode, 0, check_result.stdout)
            self.assertIn("skill mirrors are in sync", check_result.stdout)

    def test_check_rejects_missing_skill_frontmatter(self) -> None:
        """Check mode should reject SKILL.md files that the runtime would skip."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source"
            target = root / "target"
            self.write_file(source / "broken" / "SKILL.md", "# Broken\n")
            self.write_file(target / "broken" / "SKILL.md", "# Broken\n")

            result = self.run_cli(
                "--source",
                str(source),
                "--target",
                str(target),
                "--check",
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("missing YAML frontmatter", result.stdout)


if __name__ == "__main__":
    unittest.main()
