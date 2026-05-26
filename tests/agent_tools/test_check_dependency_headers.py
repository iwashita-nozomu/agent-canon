"""Tests for dependency header validation."""

# @dependency-start
# responsibility Tests changed-file dependency header detection.
# upstream implementation ../../tools/agent_tools/check_dependency_headers.py changed-file checks
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "check_dependency_headers.py"


class DependencyHeaderCheckTest(unittest.TestCase):
    """Exercise dependency header checks through the CLI."""

    def test_accepts_markdown_dependency_manifest(self) -> None:
        """Markdown files may declare dependency manifest markers near the top."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            doc = Path(tmp_dir) / "doc.md"
            doc.write_text(
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "<!--",
                        "@dependency-start",
                        "responsibility Documents a markdown file under test.",
                        "upstream design README.md repo overview",
                        "@dependency-end",
                        "-->",
                        "",
                        "Body.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(doc)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_accepts_skill_frontmatter_before_dependency_manifest(self) -> None:
        """SKILL.md may keep YAML frontmatter before the dependency manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            skill = Path(tmp_dir) / "SKILL.md"
            skill.write_text(
                "\n".join(
                    [
                        "---",
                        "name: demo-skill",
                        "description: Demonstrates frontmatter before the dependency manifest.",
                        "---",
                        "<!--",
                        "@dependency-start",
                        "responsibility Documents a skill under test.",
                        "upstream design README.md repo overview",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--allow-frontmatter", str(skill)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_rejects_missing_dependency_manifest(self) -> None:
        """Checkable text files must declare dependency manifest markers near the top."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            script = Path(tmp_dir) / "tool.py"
            script.write_text(
                "\n".join(
                    [
                        '"""Missing dependency header."""',
                        "",
                        "from __future__ import annotations",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(script)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)
            self.assertIn("missing top dependency manifest block", result.stdout)

    def test_rejects_legacy_dependency_files_block(self) -> None:
        """Legacy Dependency Files blocks are no longer sufficient."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            doc = Path(tmp_dir) / "doc.md"
            doc.write_text(
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "Dependency Files:",
                        "- README.md",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(doc)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)

    def test_skips_commentless_json(self) -> None:
        """JSON files are skipped because adding a comment header would break syntax."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            data = Path(tmp_dir) / "data.json"
            data.write_text('{"ok": true}\n', encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(data)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_skips_dependency_review_artifacts(self) -> None:
        """Generated dependency-review artifacts are not source manifest targets."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            artifact = root / "reports" / "dependency-review" / "run" / "search_hits.txt"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("README.md\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "reports/dependency-review/run/search_hits.txt",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)


if __name__ == "__main__":
    unittest.main()
