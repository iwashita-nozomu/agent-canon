# @dependency-start
# contract test
# responsibility Tests the Rust markdown math fixer CLI behavior.
# upstream implementation ../../rust/agent-canon/src/docs.rs implements docs fix-math.
# upstream design ../../tools/README.md validated automation surface
# @dependency-end

"""Tests for the markdown math fixer."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON = PROJECT_ROOT / "tools" / "bin" / "agent-canon"


class FixMarkdownMathTest(unittest.TestCase):
    """Exercise the markdown math fixer through the CLI."""

    def run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the fixer and capture output."""
        return subprocess.run(
            [str(AGENT_CANON), "docs", "fix-math", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_file(self, path: Path, contents: str) -> None:
        """Create one markdown file with parent directories as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def test_rewrites_legacy_inline_and_display_delimiters(self) -> None:
        """Legacy LaTeX delimiters should be rewritten to dollars."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            doc = root / "doc.md"
            self.write_file(
                doc,
                "# Doc\n\nInline \\(x + y\\) text.\n\n\\[\nx + y = z\n\\]\n",
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DOCS_FIX_MATH=wrote", result.stdout)
            self.assertIn("DOCS_CHECK=pass", result.stdout)
            rewritten = doc.read_text(encoding="utf-8")
            self.assertIn("Inline $x + y$ text.", rewritten)
            self.assertIn("$$\nx + y = z\n$$", rewritten)

    def test_rewrites_standalone_single_dollar_and_block_delimiters(self) -> None:
        """Standalone `$...$` and `$` block delimiters should become `$$`."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            doc = root / "doc.md"
            self.write_file(
                doc,
                "# Doc\n\n$x + y = z$\n\n$\na + b = c\n$\n",
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DOCS_FIX_MATH=wrote", result.stdout)
            self.assertIn("DOCS_CHECK=pass", result.stdout)
            rewritten = doc.read_text(encoding="utf-8")
            self.assertIn("$$x + y = z$$", rewritten)
            self.assertIn("$$\na + b = c\n$$", rewritten)

    def test_preserves_code_fence_contents(self) -> None:
        """Math-like delimiters inside fenced code blocks should stay untouched."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            doc = root / "doc.md"
            self.write_file(
                doc,
                "# Doc\n\n```text\n\\(x + y\\)\n\\[\na + b = c\n\\]\n```\n",
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DOCS_CHECK=pass", result.stdout)
            rewritten = doc.read_text(encoding="utf-8")
            self.assertIn("\\(x + y\\)", rewritten)
            self.assertIn("\\[", rewritten)
            self.assertIn("\\]", rewritten)


if __name__ == "__main__":
    unittest.main()
