# @dependency-start
# contract test
# responsibility Tests exact math delimiter residuals and standard-provider docs checks.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/docs.rs owns docs checks.
# @dependency-end
"""Tests the Markdown docs command's composed native checks."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.agent_tools.rust_cli_fixture import standalone_agent_canon

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON = standalone_agent_canon()
LYCHEE_CONFIG = Path("tools/validation/documentation/config/lychee.toml")


class CheckMarkdownMathTest(unittest.TestCase):
    """Exercise the retained delimiter policy through the docs command."""

    def run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the docs command with its existing project configuration."""
        config = root / LYCHEE_CONFIG
        config.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / ".markdownlint-cli2.jsonc", root / ".markdownlint-cli2.jsonc")
        shutil.copyfile(PROJECT_ROOT / LYCHEE_CONFIG, config)
        return subprocess.run(
            [str(AGENT_CANON), "docs", "check", "--root", str(root), *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_file(self, path: Path, contents: str) -> None:
        """Create a Markdown fixture."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def test_accepts_dollar_inline_and_double_dollar_display_math(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "# Doc\n\nInline math uses $x + y$ in a sentence.\n\n$$\nx + y = z\n$$\n",
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_alternate_delimiters_and_inline_double_dollars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "# Doc\n\nInline \\(x + y\\).\n\\[x + y = z\\]\nInline $$z$$.\n",
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn("inline math must use", result.stderr)
            self.assertIn("display math must use", result.stderr)

    def test_does_not_treat_arbitrary_plaintext_fence_contents_as_math(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "# Doc\n\n```text\nminimize x <= y\n```\n",
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("mathematical notation", result.stderr)

    def test_uses_markdownlint_native_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "doc.md", "# Doc\n\n### Skipped heading\n")

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn("MD001", result.stdout + result.stderr)

    def test_uses_lychee_for_missing_local_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "doc.md", "# Doc\n\n[Missing](missing.md)\n")

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn("missing.md", result.stdout + result.stderr)

    def test_uses_lychee_for_absolute_inputs_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent = Path(tmp_dir)
            root = parent / "repo"
            document = parent / "outside" / "doc.md"
            self.write_file(document, "# Doc\n\n[Missing](missing.md)\n")

            result = self.run_cli(root, str(document))

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("missing.md", result.stdout + result.stderr)

    def test_flags_existing_workspace_absolute_ast_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.md"
            self.write_file(target, "# Target\n")
            self.write_file(root / "doc.md", f"# Doc\n\n[Target]({target})\n")

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn("workspace-absolute Markdown target should be relative", result.stderr)


if __name__ == "__main__":
    unittest.main()
