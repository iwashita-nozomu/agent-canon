"""Tests for dependency header validation."""

# Dependency Files:
# - vendor/agent-canon/tools/agent_tools/check_dependency_headers.py

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

    def test_accepts_markdown_dependency_block(self) -> None:
        """Markdown files may declare dependencies immediately after the title."""
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

    def test_rejects_missing_dependency_block(self) -> None:
        """Checkable text files must declare dependency files near the top."""
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
            self.assertIn("missing top Dependency Files block", result.stdout)

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


if __name__ == "__main__":
    unittest.main()
