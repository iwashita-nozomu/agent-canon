"""Tests for responsibility scope validation."""

# @dependency-start
# responsibility Tests responsibility scope validation.
# upstream implementation ../../tools/agent_tools/responsibility_scope.py validates scope manifest
# upstream design ../../responsibility-scope.toml scope fixture contract
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "responsibility_scope.py"


class ResponsibilityScopeTest(unittest.TestCase):
    """Exercise the responsibility scope checker."""

    def run_checker(self, root: Path) -> subprocess.CompletedProcess[str]:
        """Run the checker against a root."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_current_repository_passes(self) -> None:
        """The canonical repository has complete responsibility scope metadata."""
        result = self.run_checker(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RESPONSIBILITY_SCOPE=pass", result.stdout)

    def test_missing_protecting_tool_fails(self) -> None:
        """A scope cannot name a missing protecting tool."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            manifest = root / "responsibility-scope.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "tools/agent_tools/responsibility_scope.py",
                    "tools/agent_tools/missing_scope_tool.py",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("missing:tools/agent_tools/missing_scope_tool.py", result.stdout)
            self.assertIn("uncataloged:tools/agent_tools/missing_scope_tool.py", result.stdout)

    def test_uncovered_required_path_fails(self) -> None:
        """Required top-level coverage must be claimed by a scope."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            manifest = root / "responsibility-scope.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    'required_coverage = ["tools"]',
                    'required_coverage = ["tools", "issues"]',
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("coverage:issues:uncovered-required-path", result.stdout)

    def test_parent_repository_requires_top_level_manifest(self) -> None:
        """A parent repo must not fall back to a vendored AgentCanon manifest."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_file(root, "tools/catalog.yaml", "version: 1\nentries: []\n")
            self.write_file(root, "vendor/agent-canon/responsibility-scope.toml", "catalog_kind = \"agent_canon_responsibility_scope\"\n")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("manifest:", result.stdout)
            self.assertIn("responsibility-scope.toml:missing-file", result.stdout)

    def write_fixture(self, root: Path) -> None:
        """Write a small responsibility-scope fixture repository."""
        self.write_file(root, "tools/agent_tools/responsibility_scope.py", "# tool\n")
        self.write_file(root, "tests/agent_tools/test_responsibility_scope.py", "# test\n")
        self.write_file(
            root,
            "tools/catalog.yaml",
            "\n".join(
                [
                    "version: 1",
                    "entries:",
                    "  - id: responsibility-scope",
                    "    path: tools/agent_tools/responsibility_scope.py",
                    "",
                ]
            ),
        )
        self.write_file(
            root,
            "responsibility-scope.toml",
            "\n".join(
                [
                    'catalog_kind = "agent_canon_responsibility_scope"',
                    "version = 1",
                    'owner_values = ["agent-canon"]',
                    'class_values = ["tooling"]',
                    'required_coverage = ["tools"]',
                    "[[scope]]",
                    'id = "tools"',
                    'owner = "agent-canon"',
                    'class = "tooling"',
                    'description = "Fixture tools."',
                    'paths = ["tools/**"]',
                    'protecting_tools = ["tools/agent_tools/responsibility_scope.py"]',
                    'issues = []',
                    "",
                ]
            ),
        )

    def write_file(self, root: Path, relative: str, text: str) -> None:
        """Write one fixture file."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
