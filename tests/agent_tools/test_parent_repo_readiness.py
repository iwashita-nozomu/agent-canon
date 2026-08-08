"""Tests for parent repository readiness checker."""

# @dependency-start
# contract test
# responsibility Tests AgentCanon parent repository readiness checks.
# upstream implementation ../../tools/agent_tools/parent_repo_readiness.py checks parent repo surfaces
# upstream implementation ../../tools/agent_tools/surface_manifest.py parses shared surface manifest
# upstream design ../../documents/runtime/shared-runtime-surfaces.toml shared runtime surface manifest
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md parent readiness boundary
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md default startup profile boundary
# upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md opt-in runtime identity and shared-surface test contract
# @dependency-end

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "parent_repo_readiness.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from surface_manifest import (  # noqa: E402
    load_manifest,
    render_copy_specs,
    render_regular_specs,
    render_root_absent_paths,
    target_for_entry,
)


class ParentRepoReadinessTest(unittest.TestCase):
    """Exercise parent repository readiness checks."""

    def run_checker(
        self,
        root: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the checker against a fixture parent root."""
        return subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                "--root",
                str(root),
                "--skip-container-config",
                "--skip-submodule-check",
                *args,
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_materialized_parent_fixture_passes(self) -> None:
        """A correctly materialized parent fixture should pass."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PARENT_REPO_READINESS=pass", result.stdout)
            self.assertFalse((root / ".codex" / "project-skills").exists())

    def test_skip_container_config_skips_parent_environment_semantics(self) -> None:
        """Readiness skip mode leaves parent-environment semantics to container_config."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            self.write_file(
                root,
                ".devcontainer/parent-environment.sh",
                "touch should-not-be-validated\n",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("container_config:skipped", result.stdout)

    def test_unconfigured_parent_environment_is_not_a_required_path(self) -> None:
        """Readiness accepts a parent that does not opt into environment projection."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            (root / ".devcontainer/parent-environment.sh").unlink()
            (root / ".devcontainer/parent-environment.toml").unlink()

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PARENT_REPO_READINESS=pass", result.stdout)

    def test_missing_parent_executable_capability_still_fails(self) -> None:
        """The optional environment change does not weaken executable sources."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            (root / ".devcontainer/post-create-parent.sh").chmod(0o644)

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                ".devcontainer/post-create-parent.sh:not-executable",
                result.stdout,
            )

    def test_shared_surface_receipt(self) -> None:
        """The manifest exposes only the minimal root projection surfaces."""
        manifest = load_manifest(
            PROJECT_ROOT,
            ".",
            "documents/runtime/shared-runtime-surfaces.toml",
        )
        active = {
            entry.path: entry
            for entry in manifest.entries
            if entry.mode in {"symlink", "repo_state"} and not entry.optional
        }
        self.assertEqual(
            set(active), {"AGENTS.md", ".codex/config.toml", "tools/agent-canon"}
        )
        for entry in active.values():
            self.assertEqual(entry.projection_producer, "agent-canon")
            self.assertEqual(entry.projection_kind, "runtime_surface")

    def test_materialized_minimal_projection(self) -> None:
        """Manifest materialization creates only the three active symlink views."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            for path, target in {
                "AGENTS.md": "vendor/agent-canon/ROOT_AGENTS.md",
                ".codex/config.toml": "vendor/agent-canon/.codex/config.toml",
                "tools/agent-canon": "vendor/agent-canon/tools",
            }.items():
                projection = root / path
                self.assertTrue(projection.is_symlink(), path)
                self.assertEqual(
                    os.readlink(projection),
                    os.path.relpath(root / target, projection.parent),
                    path,
                )

    def test_regular_specs_skip_optional_project_skill_lane(self) -> None:
        """Optional project content should not be materialized by link-root."""
        manifest = load_manifest(
            PROJECT_ROOT,
            ".",
            "documents/runtime/shared-runtime-surfaces.toml",
        )

        regular_specs = render_regular_specs(manifest.entries, manifest.prefix)

        self.assertNotIn(".codex/project-skills", regular_specs)
        self.assertNotIn(".codex/project-config.toml", regular_specs)

    def test_tree_present_adds_checked_token_and_command(self) -> None:
        """Tree availability should be reported without relying on the host tool."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            root.mkdir()
            self.write_parent_fixture(root)
            bin_dir = Path(tmp_dir) / "bin"
            bin_dir.mkdir()
            fake_tree = bin_dir / "tree"
            fake_tree.write_text(
                "#!/usr/bin/env sh\necho fake-tree\n", encoding="utf-8"
            )
            fake_tree.chmod(0o755)

            result = self.run_checker(
                root,
                "--tree-depth",
                "2",
                env={"PATH": str(bin_dir)},
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("tree_display:available:depth=2", result.stdout)
            self.assertIn(
                "PARENT_REPO_READINESS_TREE_COMMAND=tree -a -L 2 -I", result.stdout
            )
            self.assertIn(str(root), result.stdout)

    def test_tree_missing_is_warning_not_required_artifact(self) -> None:
        """Missing tree should warn without making generated tree output mandatory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            root.mkdir()
            self.write_parent_fixture(root)
            bin_dir = Path(tmp_dir) / "empty-bin"
            bin_dir.mkdir()

            result = self.run_checker(root, env={"PATH": str(bin_dir)})

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=warn:tree_display:tree:missing-command",
                result.stdout,
            )
            self.assertIn("tree_display:missing", result.stdout)
            self.assertIn("PARENT_REPO_READINESS=pass", result.stdout)

    def test_readme_documents_expected_parent_structure_and_tree_command(self) -> None:
        """The README should document the parent root shape and tree inspection route."""
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("documents/parent-repository/README.md", readme)
        self.assertIn("vendor/agent-canon/", readme)

    def test_missing_active_contract_fails(self) -> None:
        """Active AgentCanon projection views are required at the parent root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            (root / "AGENTS.md").unlink()

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=error:shared_surface:"
                "AGENTS.md:missing-symlink",
                result.stdout,
            )

    def test_missing_github_copy_fails(self) -> None:
        """The runtime config projection is required at the parent root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            (root / ".codex" / "config.toml").unlink()

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=error:shared_surface:"
                ".codex/config.toml:missing-symlink",
                result.stdout,
            )

    def test_standalone_only_root_document_absence_is_expected(self) -> None:
        """Standalone-only AgentCanon root docs should be absent in parent fixtures."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_standalone_only_entries_not_in_regular_specs_root_absent_paths(self) -> None:
        """Retired root views appear in root-absent, not regular specs."""
        manifest = load_manifest(
            PROJECT_ROOT,
            ".",
            "documents/runtime/shared-runtime-surfaces.toml",
        )
        regular_specs = render_regular_specs(manifest.entries, manifest.prefix)
        root_absent_specs = render_root_absent_paths(manifest.entries)

        self.assertNotIn("documents/runtime/SHARED_RUNTIME_SURFACES.md", regular_specs)
        self.assertNotIn(
            "documents/runtime/shared-runtime-surfaces.toml", regular_specs
        )
        self.assertIn(".agents", root_absent_specs)
        self.assertIn(".vscode", root_absent_specs)

    def test_agentcanon_workflow_sources_stay_standalone_only(self) -> None:
        """AgentCanon workflows remain source-owned but are never root copies."""
        manifest = load_manifest(
            PROJECT_ROOT,
            ".",
            "documents/runtime/shared-runtime-surfaces.toml",
        )
        root_absent_paths = set(render_root_absent_paths(manifest.entries).splitlines())
        copy_specs = render_copy_specs(manifest.entries, manifest.prefix)

        for workflow in (
            ".github/workflows/agent-improvement-guide.yml",
            ".github/workflows/agent-coordination.yml",
        ):
            self.assertIn(workflow, root_absent_paths)
            self.assertNotIn(f"{workflow}:", copy_specs)
            source = PROJECT_ROOT / workflow
            self.assertTrue(source.is_file(), workflow)
            self.assertIn("workflow_dispatch:", source.read_text(encoding="utf-8"))

    def write_parent_fixture(self, root: Path) -> None:
        """Create a synthetic template-derived parent repo."""
        agent_canon = root / "vendor" / "agent-canon"
        agent_canon.parent.mkdir(parents=True)
        os.symlink(PROJECT_ROOT, agent_canon, target_is_directory=True)
        self.write_required_parent_files(root)
        manifest = load_manifest(
            root, "vendor/agent-canon", "documents/runtime/shared-runtime-surfaces.toml"
        )
        for entry in manifest.entries:
            target = root / entry.path
            if entry.mode == "symlink":
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink() or target.is_file():
                    target.unlink()
                elif target.exists():
                    shutil.rmtree(target)
                os.symlink(target_for_entry(root, manifest.prefix, entry), target)
            elif entry.mode == "copy":
                source = root / manifest.prefix / entry.source_or_default()
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            elif entry.mode == "regular":
                if entry.optional:
                    continue
                if entry.projection_kind == "project_content":
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                source = root / manifest.prefix / entry.source_or_default()
                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not target.exists():
                    self.write_file(root, entry.path, f"{entry.path}\n")

    def write_required_parent_files(self, root: Path) -> None:
        """Write parent-owned files that are outside the shared surface manifest."""
        files = {
            "README.md": "readme\n",
            "QUICK_START.md": "quick start\n",
            "Makefile": "ci:\n\t@true\n",
            ".gitmodules": '[submodule "vendor/agent-canon"]\n\tpath = vendor/agent-canon\n\turl = https://github.com/iwashita-nozomu/agent-canon.git\n',
            "goal.md": "goal\n",
            "documents/README.md": "documents\n",
            "responsibility-scope.toml": 'catalog_kind = "agent_canon_responsibility_scope"\n',
            ".agent-canon/update-state.toml": 'tasks_applied_through = "fixture"\n',
            "scripts/README.md": "scripts\n",
            ".dockerignore": ".git\n",
            "docker/README.md": "docker\n",
            "docker/Dockerfile": "FROM ubuntu:24.04\n",
            "docker/requirements.txt": "pytest\n",
            "docker/install_python_dependencies.sh": "#!/usr/bin/env bash\n",
            "docker/register_safe_directories.sh": "#!/usr/bin/env bash\n",
            "docker/packs/default.toml": '[pack]\nname = "default"\n',
            "docker/packs/default-host-docker.toml": '[pack]\nname = "default-host-docker"\n',
            ".github/workflows/ci.yml": "name: CI\n",
            ".github/workflows/docker-build.yml": "name: Docker Build\n",
            ".devcontainer/devcontainer.json": "\n".join(
                [
                    "{",
                    '  "initializeCommand": "AGENT_CANON_DOCKER_COMPOSE_OUTPUT=.agent-canon/docker-compose.generated.yml python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/generate-runtime-compose.sh",',
                    '  "postCreateCommand": "python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/post-create-entrypoint.sh /workspace/${localWorkspaceFolderBasename}",',
                    '  "postAttachCommand": "python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/post-attach.sh",',
                    '  "dockerComposeFile": "../.agent-canon/docker-compose.generated.yml",',
                    '  "service": "workspace",',
                    '  "workspaceFolder": "/workspace/${localWorkspaceFolderBasename}",',
                    '  "name": "${localWorkspaceFolderBasename}-devcontainer"',
                    "}",
                ]
            )
            + "\n",
            ".devcontainer/post-create-parent.sh": "#!/usr/bin/env bash\nset -euo pipefail\n",
            ".devcontainer/parent-environment.sh": "",
            ".devcontainer/parent-environment.toml": "variables = []\n",
        }
        for path, text in files.items():
            self.write_file(root, path, text)
        for relative in [
            "docker/install_python_dependencies.sh",
            "docker/register_safe_directories.sh",
            ".devcontainer/post-create-parent.sh",
        ]:
            (root / relative).chmod(0o755)

    def write_file(self, root: Path, relative: str, text: str) -> None:
        """Write one fixture file."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
