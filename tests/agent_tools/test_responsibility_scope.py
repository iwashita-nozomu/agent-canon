"""Tests for responsibility scope validation."""

# @dependency-start
# contract test
# responsibility Tests the total single-owner relation for tracked repository paths.
# upstream implementation ../../tools/agent_tools/responsibility_scope.py validates scope manifest
# upstream design ../../responsibility-scope.toml scope fixture contract
# @dependency-end

from __future__ import annotations

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
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "responsibility_scope.py"
STARTER_MANIFEST = (
    PROJECT_ROOT / "templates" / "documents" / "responsibility-scope.template.toml"
)

sys.path.insert(0, str(SCRIPT.parent))

from responsibility_scope import scope_covers, scope_from_mapping


class ResponsibilityScopeTest(unittest.TestCase):
    """Exercise the responsibility scope checker."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a root."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
        )

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

    def test_unowned_tracked_path_fails(self) -> None:
        """Every existing tracked path must have exactly one owning scope."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.write_file(root, "README.md", "unowned\n")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("scope_unowned:README.md:no-owning-scope", result.stdout)

    def test_empty_scope_patterns_do_not_impose_existence(self) -> None:
        """Ownership patterns may denote an empty set in the current tracked tree."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            manifest = root / "responsibility-scope.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    'paths = ["tools/**", "tests/**", "responsibility-scope.toml"]',
                    'paths = ["tools/**", "tests/**", "responsibility-scope.toml", ".agents/**", "agents/**", "examples/**"]\nexclude_paths = ["tools/retired/**"]',
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("no-match", result.stdout)

    def test_parent_repository_requires_top_level_manifest(self) -> None:
        """A parent repo must require its own responsibility manifest."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_file(root, "tools/catalog.yaml", "version: 1\nentries: []\n")
            self.write_file(
                root,
                "vendor/agent-canon/responsibility-scope.toml",
                'catalog_kind = "agent_canon_responsibility_scope"\n',
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("manifest:", result.stdout)
            self.assertIn("responsibility-scope.toml:missing-file", result.stdout)

    def test_eval_and_hook_evidence_includes_log_archive_control_plane(self) -> None:
        """The canonical manifest assigns log-archive control-plane paths once."""
        data = tomllib.loads(
            (PROJECT_ROOT / "responsibility-scope.toml").read_text(encoding="utf-8")
        )
        scopes = {str(raw["id"]): raw for raw in data["scope"]}
        paths = set(scopes["eval-and-hook-evidence"]["paths"])
        runtime_paths = set(scopes["runtime-entrypoints"]["paths"])

        self.assertIn("evidence", paths)
        self.assertIn("evidence/**", paths)
        self.assertIn("documents/runtime/runtime-log-archive.md", paths)
        self.assertIn("documents/runtime/runtime-log-archive-migration.md", paths)
        self.assertIn("tools/agent_tools/runtime_log_paths.py", paths)
        self.assertIn("tools/agent_tools/runtime_log_archive_git.py", paths)
        self.assertNotIn(
            "evidence/agent-evals/**",
            scopes["runtime-entrypoints"].get("exclude_paths", []),
        )
        self.assertIn(
            "tools/agent_tools/runtime_log_paths.py",
            scopes["shared-tooling"]["exclude_paths"],
        )
        self.assertIn(
            "documents/runtime/runtime-log-archive.md",
            scopes["shared-policy-documents"]["exclude_paths"],
        )
        self.assertIn(".vscode/**", runtime_paths)

    def test_scope_overlap_fails_without_exclusion(self) -> None:
        """A tracked file must not be claimed by multiple responsibility scopes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.write_file(root, "tools/evidence.py", "# evidence\n")
            manifest = root / "responsibility-scope.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                + '\n[[scope]]\nid = "evidence"\nowner = "agent-canon"\nclass = "tooling"\ndescription = "Fixture evidence."\npaths = ["tools/evidence.py"]\nprotecting_tools = ["tools/agent_tools/responsibility_scope.py"]\nissues = []\n',
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("scope_overlap:tools/evidence.py:scopes:fixture,evidence", result.stdout)

    def test_starter_manifest_partitions_parent_tools_from_agent_canon_view(self) -> None:
        """Keep only active AgentCanon views in the starter runtime scope."""
        data = tomllib.loads(STARTER_MANIFEST.read_text(encoding="utf-8"))
        scopes = {str(raw["id"]): scope_from_mapping(raw) for raw in data["scope"]}
        agent_canon = scopes["agent-canon-runtime-view"]
        parent = scopes["parent-repo-active-contract"]
        durable = scopes["project-durable-state"]

        ownership = {
            path: tuple(
                scope.scope_id
                for scope in (agent_canon, parent, durable)
                if scope_covers(scope, path)
            )
            for path in (
                "vendor/agent-canon/tools/sync_agent_canon.sh",
                "tools/agent-canon/sync_agent_canon.sh",
                "tools/project_check.py",
                "tools/team/local.sh",
                ".codex/config.toml",
                "agents/skills/local.md",
                ".agents/skills/local.md",
                ".devcontainer/devcontainer.json",
                ".vscode/settings.json",
                "evidence/run.json",
            )
        }

        self.assertEqual(
            ownership["vendor/agent-canon/tools/sync_agent_canon.sh"],
            ("agent-canon-runtime-view",),
        )
        self.assertEqual(
            ownership["tools/agent-canon/sync_agent_canon.sh"],
            ("parent-repo-active-contract",),
        )
        self.assertEqual(
            ownership["tools/project_check.py"],
            ("parent-repo-active-contract",),
        )
        self.assertEqual(
            ownership["tools/team/local.sh"],
            ("parent-repo-active-contract",),
        )
        self.assertEqual(ownership[".codex/config.toml"], ("agent-canon-runtime-view",))
        for path in (
            "agents/skills/local.md",
            ".agents/skills/local.md",
            ".devcontainer/devcontainer.json",
            ".vscode/settings.json",
        ):
            self.assertEqual(ownership[path], ("parent-repo-active-contract",))
        self.assertEqual(ownership["evidence/run.json"], ("project-durable-state",))

    def write_fixture(self, root: Path) -> None:
        """Write a bounded responsibility-scope fixture repository."""
        self.write_file(root, "tools/agent_tools/responsibility_scope.py", "# tool\n")
        self.write_file(root, "tests/agent_tools/test_responsibility_scope.py", "# test\n")
        self.write_file(
            root,
            "tools/catalog.yaml",
            "version: 1\nentries:\n  - id: responsibility-scope\n    path: tools/agent_tools/responsibility_scope.py\n",
        )
        self.write_file(
            root,
            "responsibility-scope.toml",
            'catalog_kind = "agent_canon_responsibility_scope"\nversion = 1\nowner_values = ["agent-canon"]\nclass_values = ["tooling"]\n[[scope]]\nid = "fixture"\nowner = "agent-canon"\nclass = "tooling"\ndescription = "Fixture paths."\npaths = ["tools/**", "tests/**", "responsibility-scope.toml"]\nprotecting_tools = ["tools/agent_tools/responsibility_scope.py"]\nissues = []\n',
        )

    def write_file(self, root: Path, relative: str, text: str) -> None:
        """Write one fixture file."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
