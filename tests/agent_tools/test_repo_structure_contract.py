"""Tests for AgentCanon repository structure contract checks."""

# @dependency-start
# contract test
# responsibility Tests path existence/kind comparison without duplicating responsibility owner/class.
# upstream implementation ../../tools/agent_tools/repo_structure_contract.py compares repo trees with contract profiles
# upstream design ../../documents/structure/repo-structure-contract.toml defines expected repository structure profiles
# upstream design ../../responsibility-scope.toml owns path owner and class
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "repo_structure_contract.py"
CONTRACT = PROJECT_ROOT / "documents" / "structure" / "repo-structure-contract.toml"


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

    def test_contract_rows_only_store_path_and_kind(self) -> None:
        """Structure rows must not duplicate owner/class/category metadata."""
        data = tomllib.loads(CONTRACT.read_text(encoding="utf-8"))
        for profile in data["profile"]:
            for row_kind in ("required", "optional"):
                for row in profile.get(row_kind, []):
                    self.assertEqual(set(row), {"path", "kind"})

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

    def test_managed_results_are_excluded_by_exact_path(self) -> None:
        """Managed result bytes do not broaden into a global result-directory ignore."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_standalone_fixture(root)
            managed_artifact = root / "experiments" / "topic" / "result" / "run" / "artifact.json"
            source_artifact = root / "notes" / "result" / "source.md"
            self.write_file(root, str(managed_artifact.relative_to(root)), "generated\n")
            self.write_file(root, str(source_artifact.relative_to(root)), "source\n")

            with_source = self.run_checker(
                root,
                "--profile",
                "agent_canon_standalone",
                "--format",
                "json",
            )
            source_artifact.unlink()
            without_source = self.run_checker(
                root,
                "--profile",
                "agent_canon_standalone",
                "--format",
                "json",
            )

            self.assertEqual(with_source.returncode, 0, with_source.stdout + with_source.stderr)
            self.assertEqual(
                without_source.returncode,
                0,
                without_source.stdout + without_source.stderr,
            )
            with_report = json.loads(with_source.stdout)
            without_report = json.loads(without_source.stdout)
            self.assertEqual(
                with_report["checked_paths"],
                without_report["checked_paths"],
            )

    def test_missing_required_path_fails(self) -> None:
        """Missing required paths should be reported as errors."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_standalone_fixture(root)
            (root / "tools" / "catalog.yaml").unlink()

            result = self.run_checker(root, "--profile", "agent_canon_standalone")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "REPO_STRUCTURE_FINDING=error:required_path:tools/catalog.yaml:missing-file",
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

    def test_unlisted_top_level_is_outside_structure_contract(self) -> None:
        """Non-contract paths are left to the canonical ownership relation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_standalone_fixture(root)
            self.write_file(root, "scratch.txt", "scratch\n")

            result = self.run_checker(root, "--profile", "agent_canon_standalone")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("scratch.txt", result.stdout)

    def test_standalone_profile_allows_runtime_and_evidence_support_dirs(self) -> None:
        """Standalone AgentCanon should allow shared runtime support dirs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_standalone_fixture(root)
            (root / ".vscode").mkdir()
            (root / "evidence").mkdir()

            result = self.run_checker(root, "--profile", "agent_canon_standalone")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_template_profile_allows_evidence_root_view(self) -> None:
        """Template roots should allow parent-owned evidence content."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_template_fixture(root)
            (root / "evidence").mkdir()

            result = self.run_checker(root, "--profile", "template_or_derived_repo")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_template_parent_may_omit_agent_and_editor_directories(self) -> None:
        """Parent-owned agents and editor directories are optional structure."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_template_fixture(root)
            (root / "agents").rmdir()
            (root / ".vscode").rmdir()

            result = self.run_checker(root, "--profile", "template_or_derived_repo")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("missing-file", result.stdout)

    def write_standalone_fixture(self, root: Path) -> None:
        """Create the minimal standalone structure required by the contract."""
        for file_path in [
            "README.md",
            "ROOT_AGENTS.md",
            "AGENTS.md",
            "agents/TASK_WORKFLOWS.md",
            "templates/README.md",
            "documents/rule/README.md",
            "documents/rule/naming.md",
            "documents/rule/directory-structure.md",
            "documents/runtime/shared-runtime-surfaces.toml",
            "documents/structure/repo-structure-contract.toml",
            "tools/catalog.yaml",
            "rust/agent-canon/Cargo.toml",
            "tools/agent_tools/update_lifecycle_contract.py",
        ]:
            self.write_file(root, file_path, f"{file_path}\n")
        for dir_path in [
            "agents/skills",
            "agents/internal-routines",
            "agents/workflows",
            "agents/canonical",
            "documents/rule",
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
                    "name": "templates",
                    "contents": [{"type": "file", "name": "README.md"}],
                },
                {
                    "type": "directory",
                    "name": "documents",
                    "contents": [
                        {
                            "type": "directory",
                            "name": "rule",
                            "contents": [
                                {"type": "file", "name": "README.md"},
                                {"type": "file", "name": "naming.md"},
                                {"type": "file", "name": "directory-structure.md"},
                            ],
                        },
                        {"type": "directory", "name": "tools"},
                        {
                            "type": "directory",
                            "name": "runtime",
                            "contents": [
                                {"type": "file", "name": "shared-runtime-surfaces.toml"}
                            ],
                        },
                        {
                            "type": "directory",
                            "name": "structure",
                            "contents": [
                                {"type": "file", "name": "repo-structure-contract.toml"}
                            ],
                        },
                    ],
                },
                {
                    "type": "directory",
                    "name": "tools",
                    "contents": [
                        {"type": "file", "name": "catalog.yaml"},
                        {
                            "type": "directory",
                            "name": "agent_tools",
                            "contents": [
                                {"type": "file", "name": "update_lifecycle_contract.py"}
                            ],
                        },
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
