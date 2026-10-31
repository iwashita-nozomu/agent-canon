"""Tests for responsibility scope validation."""

# @dependency-start
# contract test
# responsibility Tests the total single-owner relation for tracked repository paths.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/responsibility_scope.rs validates scope manifest and planned path ownership
# upstream design ../../responsibility-scope.toml scope fixture contract
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")
STARTER_MANIFEST = (
    PROJECT_ROOT / "templates" / "documents" / "responsibility-scope.template.toml"
)
NATIVE_TOOL = "tools/runtime/dispatch/agent-canon/src/responsibility_scope.rs"


class ResponsibilityScopeTest(unittest.TestCase):
    """Exercise the responsibility scope checker."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the selected native checker against a root."""
        self.assertIsNotNone(
            AGENT_CANON_CLI, "AGENT_CANON_CLI must select the current native executable"
        )
        executable = Path(str(AGENT_CANON_CLI))
        self.assertTrue(
            executable.is_absolute(),
            "AGENT_CANON_CLI must be an absolute executable path",
        )
        return subprocess.run(
            [str(executable), "responsibility-scope", "--root", str(root), *args],
            cwd=PROJECT_ROOT,
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
                    NATIVE_TOOL,
                    "tools/agent_tools/missing_scope_tool.py",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing:tools/agent_tools/missing_scope_tool.py", result.stdout
            )
            self.assertIn(
                "uncataloged:tools/agent_tools/missing_scope_tool.py", result.stdout
            )

    def test_default_json_report_keeps_existing_fields(self) -> None:
        """Path-owner query fields are omitted from the existing default report."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)

            result = self.run_checker(root, "--format", "json")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(set(report), {"status", "findings", "scopes"})
        self.assertEqual(report["status"], "pass")

    def test_unowned_tracked_path_fails(self) -> None:
        """Every existing tracked path must have exactly one owning scope."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.write_file(root, "README.md", "unowned\n")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("scope_unowned:README.md:no-owning-scope", result.stdout)
            owner_query = self.run_checker(root, "--format", "json", "--path=README.md")
            self.assertEqual(owner_query.returncode, 1, owner_query.stdout)
            self.assertEqual(
                json.loads(owner_query.stdout)["path_owners"],
                [{"path": "README.md", "scope_ids": []}],
            )

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
        """The native owner query preserves canonical path-to-scope assignments."""
        data = tomllib.loads(
            (PROJECT_ROOT / "responsibility-scope.toml").read_text(encoding="utf-8")
        )
        scopes = {str(raw["id"]): raw for raw in data["scope"]}
        paths = set(scopes["eval-and-hook-evidence"]["paths"])
        runtime_paths = set(scopes["runtime-entrypoints"]["paths"])

        self.assertIn("eval", paths)
        self.assertIn("eval/**", paths)
        self.assertIn("reports/**", paths)
        self.assertIn("documents/runtime/runtime-log-archive.md", paths)
        self.assertIn("documents/runtime/runtime-log-archive-migration.md", paths)
        self.assertIn("tools/runtime/archive/runtime_log_paths.py", paths)
        self.assertIn("tools/runtime/archive/runtime_log_archive_git.py", paths)
        self.assertNotIn(
            "evidence/agent-evals/**",
            scopes["runtime-entrypoints"].get("exclude_paths", []),
        )
        self.assertIn("eval/**", scopes["shared-tooling"]["exclude_paths"])
        self.assertIn(
            "documents/runtime/runtime-log-archive.md",
            scopes["shared-policy-documents"]["exclude_paths"],
        )
        self.assertIn(".vscode/**", runtime_paths)
        expected_owners = {
            "tools/runtime/archive/runtime_log_archive_git.py": "eval-and-hook-evidence",
            "tools/runtime/archive/runtime_log_paths.py": "eval-and-hook-evidence",
            "tests/agent_tools/test_eval_accumulation_check.py": "eval-and-hook-evidence",
            "tests/agent_tools/test_runtime_log_archive_git.py": "eval-and-hook-evidence",
            "tests/agent_tools/test_runtime_log_paths.py": "eval-and-hook-evidence",
            ".obsidian/app.json": "runtime-entrypoints",
            ".obsidian/appearance.json": "runtime-entrypoints",
            ".obsidian/core-plugins.json": "runtime-entrypoints",
            ".obsidian/graph.json": "runtime-entrypoints",
            ".obsidian/workspace.json": "runtime-entrypoints",
            "schemas/agent-canon/skill-catalog.schema.json": "shared-tooling",
            "schemas/agent-canon/skill-dependencies.schema.json": "shared-tooling",
            "schemas/agent-canon/tool-catalog.schema.json": "shared-tooling",
            "schemas/agent-canon/yamllint.yaml": "shared-tooling",
        }
        result = self.run_checker(
            PROJECT_ROOT,
            "--format",
            "json",
            *(f"--path={path}" for path in expected_owners),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "pass")
        actual_owners = {
            item["path"]: tuple(item["scope_ids"]) for item in payload["path_owners"]
        }
        self.assertEqual(
            actual_owners,
            {path: (owner,) for path, owner in expected_owners.items()},
        )

    def test_scope_overlap_fails_without_exclusion(self) -> None:
        """A tracked file must not be claimed by multiple responsibility scopes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.write_file(root, "tools/evidence.py", "# evidence\n")
            manifest = root / "responsibility-scope.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                + '\n[[scope]]\nid = "evidence"\nowner = "agent-canon"\nclass = "tooling"\ndescription = "Fixture evidence."\npaths = ["tools/evidence.py"]\nprotecting_tools = ["tools/runtime/dispatch/agent-canon/src/responsibility_scope.rs"]\nissues = []\n',
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "scope_overlap:tools/evidence.py:scopes:fixture,evidence", result.stdout
            )
            owner_query = self.run_checker(
                root, "--format", "json", "--path=tools/evidence.py"
            )
            self.assertEqual(owner_query.returncode, 1, owner_query.stdout)
            self.assertEqual(
                json.loads(owner_query.stdout)["path_owners"],
                [{"path": "tools/evidence.py", "scope_ids": ["fixture", "evidence"]}],
            )

    def test_starter_manifest_keeps_parent_paths_source_free(self) -> None:
        """The starter manifest must not require a vendor or root projection."""
        data = tomllib.loads(STARTER_MANIFEST.read_text(encoding="utf-8"))
        scopes = {str(raw["id"]): raw for raw in data["scope"]}
        self.assertIn("parent-repo-active-contract", scopes)
        self.assertIn("project-durable-state", scopes)
        self.assertNotIn("agent-canon-runtime-view", scopes)
        starter_text = STARTER_MANIFEST.read_text(encoding="utf-8")
        self.assertNotIn("vendor/agent-canon", starter_text)
        self.assertNotIn("tools/agent-canon", starter_text)

        expected_owners = {
            "AGENTS.md": ("parent-repo-active-contract",),
            "bootstrap.sh": ("parent-repo-active-contract",),
            "tools/project_check.py": ("parent-repo-active-contract",),
            "tools/team/local.sh": ("parent-repo-active-contract",),
            ".codex/config.toml": ("parent-repo-active-contract",),
            ".codex/agents/local.toml": ("parent-repo-active-contract",),
            "agents/skills/local.md": ("parent-repo-active-contract",),
            ".codex/personal/skills/local.md": ("parent-repo-active-contract",),
            ".devcontainer/devcontainer.json": ("parent-repo-active-contract",),
            ".vscode/settings.json": ("parent-repo-active-contract",),
            "evidence/run.json": ("project-durable-state",),
        }
        relative_manifest = STARTER_MANIFEST.relative_to(PROJECT_ROOT).as_posix()
        result = self.run_checker(
            PROJECT_ROOT,
            "--format",
            "json",
            "--manifest",
            relative_manifest,
            *(f"--path={path}" for path in expected_owners),
        )
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        actual_owners = {
            item["path"]: tuple(item["scope_ids"]) for item in payload["path_owners"]
        }
        self.assertEqual(actual_owners, expected_owners)

    def write_fixture(self, root: Path) -> None:
        """Write a bounded responsibility-scope fixture repository."""
        self.write_file(root, NATIVE_TOOL, "// tool\n")
        self.write_file(
            root, "tests/agent_tools/test_responsibility_scope.py", "# test\n"
        )
        self.write_file(
            root,
            "tools/catalog.yaml",
            "version: 1\nentries:\n  - id: responsibility-scope\n    path: tools/runtime/dispatch/agent-canon/src/responsibility_scope.rs\n",
        )
        self.write_file(
            root,
            "responsibility-scope.toml",
            'catalog_kind = "agent_canon_responsibility_scope"\nversion = 1\nowner_values = ["agent-canon"]\nclass_values = ["tooling"]\n[[scope]]\nid = "fixture"\nowner = "agent-canon"\nclass = "tooling"\ndescription = "Fixture paths."\npaths = ["tools/**", "tests/**", "responsibility-scope.toml"]\nprotecting_tools = ["tools/runtime/dispatch/agent-canon/src/responsibility_scope.rs"]\nissues = []\n',
        )

    def write_file(self, root: Path, relative: str, text: str) -> None:
        """Write one fixture file."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
