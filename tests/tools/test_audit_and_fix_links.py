# @dependency-start
# contract test
# responsibility Tests audit_and_fix_links forwarder behavior.
# upstream implementation ../../tools/docs/audit_and_fix_links.py link audit compatibility forwarder
# upstream implementation ../../rust/agent-canon/src/docs.rs Rust docs check link diagnostics
# @dependency-end
"""Tests for the markdown link audit compatibility forwarder."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "docs" / "audit_and_fix_links.py"


class AuditAndFixLinksTest(unittest.TestCase):
    """Exercise the link audit forwarder through its CLI."""

    def run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the link audit helper and capture its output."""
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_file(self, path: Path, contents: str) -> None:
        """Create a file with parent directories as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def test_check_fails_on_unresolved_links(self) -> None:
        """Check mode should fail when a link cannot be resolved."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "documents" / "guide.md",
                "# Guide\n\n[missing](./missing.md)\n",
            )

            result = self.run_cli(root, "--check", "documents")

            self.assertEqual(result.returncode, 1)
            self.assertIn("DOCS_CHECK_FINDING=markdown-links", result.stderr)
            self.assertIn("DOCS_CHECK_REPORT_BEGIN", result.stderr)
            self.assertIn("Open only the reported location", result.stderr)
            self.assertIn("missing.md", result.stderr)

    def test_apply_rewrites_uniquely_resolvable_relative_targets(self) -> None:
        """Apply mode should rewrite uniquely resolvable local targets."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "README.md", "# Root\n")
            self.write_file(
                root / "agents" / "guide.md",
                "# Guide\n\n[root](README.md)\n",
            )

            apply_result = self.run_cli(root, "--apply", "agents")
            self.assertEqual(apply_result.returncode, 0, apply_result.stderr)

            rewritten = (root / "agents" / "guide.md").read_text(encoding="utf-8")
            self.assertIn("[root](../README.md)", rewritten)

            check_result = self.run_cli(root, "--check", "agents")
            self.assertEqual(check_result.returncode, 0, check_result.stdout)
            self.assertIn("DOCS_CHECK=pass", check_result.stdout)

    def test_workspace_absolute_links_become_rust_findings(self) -> None:
        """Workspace absolute links should be reported by the Rust docs checker."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            absolute_readme = f"/tmp/workspace/{root.name}/README.md"
            self.write_file(root / "README.md", "# Root\n")
            self.write_file(
                root / "agents" / "guide.md",
                f"# Guide\n\n[root]({absolute_readme})\n",
            )

            check_result = self.run_cli(root, "--check", "agents")

            self.assertEqual(check_result.returncode, 1, check_result.stdout)
            self.assertIn("DOCS_CHECK_FINDING=markdown-links", check_result.stderr)
            self.assertIn("DOCS_CHECK_REPORT_BEGIN", check_result.stderr)
            self.assertIn(
                "workspace-absolute markdown link should be relative",
                check_result.stderr,
            )


if __name__ == "__main__":
    unittest.main()
