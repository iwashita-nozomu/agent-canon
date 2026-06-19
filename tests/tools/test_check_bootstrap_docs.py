# @dependency-start
# contract test
# responsibility Tests bootstrap docs checker behavior.
# upstream implementation ../../tools/docs/check_bootstrap_docs.py bootstrap docs checker under test
# upstream design ../../documents/template-bootstrap.md bootstrap documentation contract
# @dependency-end
"""Tests for the bootstrap-facing doc validator."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "docs" / "check_bootstrap_docs.py"


class CheckBootstrapDocsTest(unittest.TestCase):
    """Exercise bootstrap-doc validation through the CLI."""

    def run_cli(self, root: Path) -> subprocess.CompletedProcess[str]:
        """Run the validator in one temporary repository root."""
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_file(self, path: Path, contents: str) -> None:
        """Create one file with parent directories as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def write_minimal_bootstrap_docs(self, root: Path) -> None:
        """Create the bootstrap-facing files the validator scans."""
        for relative_path in (
            "README.md",
            "QUICK_START.md",
            "docker/README.md",
            "scripts/README.md",
            "documents/template-bootstrap.md",
            "documents/linux-wsl-host-requirements.md",
        ):
            self.write_file(root / relative_path, "# Doc\n")

    def test_fails_on_workspace_absolute_links(self) -> None:
        """Workspace-absolute markdown links should be rejected everywhere."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "pyproject.toml", '[project]\nname = "project-template"\n')
            self.write_minimal_bootstrap_docs(root)
            self.write_file(
                root / "README.md",
                "[doc](/mnt/l/workspace/project_template/README.md)\n",
            )

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("replace workspace-absolute markdown links", result.stdout)

    def test_fails_on_stale_template_strings_in_derived_repo(self) -> None:
        """Derived repos should not keep template bootstrap identifiers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "pyproject.toml", '[project]\nname = "derived-project"\n')
            self.write_minimal_bootstrap_docs(root)
            self.write_file(
                root / "QUICK_START.md",
                "docker build -t project-template -f docker/Dockerfile .\n",
            )

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("stale template bootstrap text remains: project-template", result.stdout)

    def test_skips_shared_template_bootstrap_doc_in_derived_repo(self) -> None:
        """Derived repos may expose the shared template bootstrap doc as a symlink."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            shared_doc = root / "vendor" / "agent-canon" / "documents" / "template-bootstrap.md"
            self.write_file(root / "pyproject.toml", '[project]\nname = "derived-project"\n')
            self.write_minimal_bootstrap_docs(root)
            self.write_file(
                shared_doc,
                "Project Template\nlegacy template remote\n",
            )
            (root / "documents" / "template-bootstrap.md").unlink()
            (root / "documents" / "template-bootstrap.md").symlink_to(
                Path("../vendor/agent-canon/documents/template-bootstrap.md")
            )

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("Bootstrap docs check passed", result.stdout)

    def test_passes_when_template_strings_are_replaced(self) -> None:
        """Derived repos should pass once bootstrap-facing docs are rendered."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "pyproject.toml", '[project]\nname = "derived-project"\n')
            self.write_minimal_bootstrap_docs(root)
            self.write_file(
                root / "README.md",
                "# Derived Project\n\n[quick-start](QUICK_START.md)\n",
            )
            self.write_file(
                root / "QUICK_START.md",
                "docker build -t derived-project -f docker/Dockerfile .\n",
            )

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("Bootstrap docs check passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
