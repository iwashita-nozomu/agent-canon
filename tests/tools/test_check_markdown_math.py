"""Tests for the markdown math notation checker."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "docs" / "check_markdown_math.py"


class CheckMarkdownMathTest(unittest.TestCase):
    """Exercise markdown math notation checks through the CLI."""

    def run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker and capture output."""
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_file(self, path: Path, contents: str) -> None:
        """Create one markdown file with parent directories as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def test_passes_for_dollar_inline_and_double_dollar_display(self) -> None:
        """Inline math should use $...$ and display math should use $$...$$."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "Inline math uses $x + y$ in a sentence.",
                        "",
                        "$$",
                        "x + y = z",
                        "$$",
                        "",
                        "$$a^2 + b^2 = c^2$$",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("No markdown math notation issues found", result.stdout)

    def test_fails_on_legacy_latex_delimiters(self) -> None:
        """Legacy LaTeX delimiters should be rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        r"Inline \(x + y\) is not allowed.",
                        r"\[x + y = z\]",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn(r"Inline math must use `$...$`, not `\(...\)`", result.stdout)
            self.assertIn(r"Display math must use `$$...$$`, not `\[...\]`", result.stdout)

    def test_fails_on_inline_double_dollar_math(self) -> None:
        """Inline math should not use display delimiters."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "# Doc\n\nInline $$x + y$$ should fail.\n",
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn("Inline math must use `$...$`, not `$$...$$`", result.stdout)

    def test_fails_on_standalone_single_dollar_display(self) -> None:
        """Display math should not use single-dollar delimiters on its own line."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "# Doc\n\n$x + y = z$\n",
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn("Display math must use `$$...$$`, not `$...$` on its own line", result.stdout)

    def test_fails_on_single_dollar_block_delimiters(self) -> None:
        """Display blocks should not use single-dollar delimiter lines."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "# Doc\n\n$\nx + y = z\n$\n",
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn("Display math must use `$$...$$`, not `$` block delimiters", result.stdout)


if __name__ == "__main__":
    unittest.main()
