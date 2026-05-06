# @dependency-start
# responsibility Tests GitHub workflow convention checker behavior.
# upstream implementation ../../tools/ci/check_github_workflows.py convention checker
# @dependency-end

"""Tests for GitHub workflow convention checks."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "ci" / "check_github_workflows.py"


class GitHubWorkflowCheckTest(unittest.TestCase):
    """Exercise the GitHub workflow checker."""

    def test_current_repository_passes(self) -> None:
        """The current repository should satisfy GitHub workflow conventions."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(REPO_ROOT)],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("GITHUB_WORKFLOWS=pass", result.stdout)

    def test_missing_submodule_checkout_fails(self) -> None:
        """Checkout steps must request submodules and disable credentials."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workflow_dir = root / ".github" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "ci.yml").write_text(
                "name: CI\n"
                "on: [push]\n"
                "permissions:\n"
                "  contents: read\n"
                "jobs:\n"
                "  test:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - uses: actions/checkout@v4\n"
                "        with:\n"
                "          persist-credentials: true\n",
                encoding="utf-8",
            )
            self.copy_required_surfaces(root)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checkout_1_missing_submodules_true", result.stdout)
            self.assertIn("checkout_1_missing_persist_credentials_false", result.stdout)

    def test_missing_pr_template_evidence_fails(self) -> None:
        """PR templates must retain validation and submodule evidence fields."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_valid_workflow(root)
            self.copy_required_surfaces(root)
            (root / ".github" / "PULL_REQUEST_TEMPLATE.md").write_text(
                "# Pull Request\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing_text:Validation Evidence", result.stdout)
            self.assertIn(
                "missing_text:expected template submodule SHA:",
                result.stdout,
            )

    def write_valid_workflow(self, root: Path) -> None:
        """Write one minimal valid workflow."""
        workflow_dir = root / ".github" / "workflows"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        (workflow_dir / "ci.yml").write_text(
            "name: CI\n"
            "on: [push]\n"
            "permissions:\n"
            "  contents: read\n"
            "concurrency:\n"
            "  group: ci-${{ github.ref }}\n"
            "jobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "        with:\n"
            "          submodules: true\n"
            "          persist-credentials: false\n",
            encoding="utf-8",
        )

    def copy_required_surfaces(self, root: Path) -> None:
        """Copy non-workflow surfaces required by the checker."""
        for relative in [
            ".github/AGENTS.md",
            ".github/copilot-instructions.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            "README.md",
        ]:
            source = REPO_ROOT / relative
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink():
                source = source.resolve()
            shutil.copy2(source, destination)


if __name__ == "__main__":
    unittest.main()
