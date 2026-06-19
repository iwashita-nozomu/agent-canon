"""Tests for AgentCanon repository structure contract checks."""

# @dependency-start
# contract test
# responsibility Tests repo structure contract comparison from filesystem and tree JSON input.
# upstream implementation ../../tools/agent_tools/repo_structure_contract.py compares repo trees with contract profiles
# upstream design ../../documents/repo-structure-contract.toml defines expected repository structure profiles
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "repo_structure_contract.py"
CONTRACT = PROJECT_ROOT / "documents" / "repo-structure-contract.toml"


class RepoStructureContractTest(unittest.TestCase):
    """Exercise structure contract validation."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a fixture root."""
        return subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                "--root",
                str(root),
                "--contract",
                str(CONTRACT),
                *args,
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_standalone_fixture_passes_tree_command(self) -> None:
        """A minimal standalone AgentCanon shape should satisfy the contract."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_standalone_fixture(root)

            result = self.run_checker(root, "--profile", "agent_canon_standalone")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPO_STRUCTURE=pass", result.stdout)
            self.assertIn("REPO_STRUCTURE_PROFILE=agent_canon_standalone", result.stdout)
            self.assertIn("REPO_STRUCTURE_TREE_SOURCE=tree-command:", result.stdout)

    def test_missing_required_path_fails(self) -> None:
        """Missing required paths should be reported as errors."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_standalone_fixture(root)
            (root / "tools" / "catalog.yaml").unlink()

            result = self.run_checker(root, "--profile", "agent_canon_standalone")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "REPO_STRUCTURE_FINDING=error:tooling:tools/catalog.yaml:missing-file",
                result.stdout,
            )

    def test_tree_json_input_is_compared(self) -> None:
        """The checker should accept JSON emitted by tree -J."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tree_json = root / "tree.json"
            tree_json.write_text(json.dumps([self.tree_fixture()]), encoding="utf-8")

            result = self.run_checker(
                PROJECT_ROOT,
                "--profile",
                "agent_canon_standalone",
                "--tree-json",
                str(tree_json),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPO_STRUCTURE_TREE_SOURCE=tree-json:", result.stdout)

    def test_unexpected_top_level_is_warning_by_default(self) -> None:
        """Top-level paths not classified by the profile should be visible."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_standalone_fixture(root)
            self.write_file(root, "scratch.txt", "scratch\n")

            result = self.run_checker(root, "--profile", "agent_canon_standalone")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "REPO_STRUCTURE_FINDING=warn:unexpected_top_level:scratch.txt:not-in-profile-contract",
                result.stdout,
            )

    def test_unexpected_top_level_can_be_strict(self) -> None:
        """Strict mode should fail on unclassified top-level paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_standalone_fixture(root)
            self.write_file(root, "scratch.txt", "scratch\n")

            result = self.run_checker(
                root,
                "--profile",
                "agent_canon_standalone",
                "--strict-extra-top-level",
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "REPO_STRUCTURE_FINDING=error:unexpected_top_level:scratch.txt:not-in-profile-contract",
                result.stdout,
            )

    def test_standalone_profile_allows_runtime_and_evidence_support_dirs(self) -> None:
        """Standalone AgentCanon should classify shared runtime support dirs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_standalone_fixture(root)
            (root / ".vscode").mkdir()
            (root / "evidence").mkdir()

            result = self.run_checker(root, "--profile", "agent_canon_standalone")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("unexpected_top_level:.vscode", result.stdout)
            self.assertNotIn("unexpected_top_level:evidence", result.stdout)

    def test_template_profile_allows_evidence_root_view(self) -> None:
        """Template roots should classify the shared evidence symlink view."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_template_fixture(root)
            (root / "evidence").mkdir()

            result = self.run_checker(root, "--profile", "template_or_derived_repo")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("unexpected_top_level:evidence", result.stdout)

    def write_standalone_fixture(self, root: Path) -> None:
        """Create the minimal standalone structure required by the contract."""
        for file_path in [
            "README.md",
            "ROOT_AGENTS.md",
            "AGENTS.md",
            "agents/TASK_WORKFLOWS.md",
            "documents/shared-runtime-surfaces.toml",
            "documents/repo-structure-contract.toml",
            "tools/catalog.yaml",
            "rust/agent-canon/Cargo.toml",
        ]:
            self.write_file(root, file_path, f"{file_path}\n")
        for dir_path in [
            "agents/skills",
            "agents/internal-routines",
            "agents/workflows",
            "agents/canonical",
            "documents/tools",
            "tools/agent_tools",
            "tools/user",
            "tools/internal",
            "tools/ci",
            "tests/agent_tools",
            "memory",
            "notes",
            "issues",
        ]:
            (root / dir_path).mkdir(parents=True, exist_ok=True)

    def write_template_fixture(self, root: Path) -> None:
        """Create the minimal template structure required by the contract."""
        for file_path in [
            "README.md",
            "AGENTS.md",
            ".gitmodules",
            "documents/README.md",
            "goal.md",
            "responsibility-scope.toml",
        ]:
            self.write_file(root, file_path, f"{file_path}\n")
        for dir_path in [
            "vendor/agent-canon",
            "tools",
            "agents",
            ".codex",
            ".devcontainer",
            ".vscode",
        ]:
            (root / dir_path).mkdir(parents=True, exist_ok=True)

    def write_file(self, root: Path, relative: str, text: str) -> None:
        """Write one fixture file."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def tree_fixture(self) -> dict[str, object]:
        """Return a minimal tree -J style fixture."""
        return {
            "type": "directory",
            "name": ".",
            "contents": [
                {"type": "file", "name": "README.md"},
                {"type": "file", "name": "ROOT_AGENTS.md"},
                {"type": "file", "name": "AGENTS.md"},
                {
                    "type": "directory",
                    "name": "agents",
                    "contents": [
                        {"type": "file", "name": "TASK_WORKFLOWS.md"},
                        {"type": "directory", "name": "skills"},
                        {"type": "directory", "name": "internal-routines"},
                        {"type": "directory", "name": "workflows"},
                        {"type": "directory", "name": "canonical"},
                    ],
                },
                {
                    "type": "directory",
                    "name": "documents",
                    "contents": [
                        {"type": "directory", "name": "tools"},
                        {"type": "file", "name": "shared-runtime-surfaces.toml"},
                        {"type": "file", "name": "repo-structure-contract.toml"},
                    ],
                },
                {
                    "type": "directory",
                    "name": "tools",
                    "contents": [
                        {"type": "file", "name": "catalog.yaml"},
                        {"type": "directory", "name": "agent_tools"},
                        {"type": "directory", "name": "user"},
                        {"type": "directory", "name": "internal"},
                        {"type": "directory", "name": "ci"},
                    ],
                },
                {
                    "type": "directory",
                    "name": "rust",
                    "contents": [
                        {
                            "type": "directory",
                            "name": "agent-canon",
                            "contents": [{"type": "file", "name": "Cargo.toml"}],
                        }
                    ],
                },
                {
                    "type": "directory",
                    "name": "tests",
                    "contents": [{"type": "directory", "name": "agent_tools"}],
                },
                {"type": "directory", "name": "memory"},
                {"type": "directory", "name": "notes"},
                {"type": "directory", "name": "issues"},
            ],
        }


if __name__ == "__main__":
    unittest.main()
