"""Tests for parent repository readiness checker."""

# @dependency-start
# responsibility Tests AgentCanon parent repository readiness checks.
# upstream implementation ../../tools/agent_tools/parent_repo_readiness.py checks parent repo surfaces
# upstream implementation ../../tools/agent_tools/surface_manifest.py parses shared surface manifest
# upstream design ../../documents/shared-runtime-surfaces.toml shared runtime surface manifest
# @dependency-end

from __future__ import annotations

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

from surface_manifest import load_manifest, target_for_entry  # noqa: E402


class ParentRepoReadinessTest(unittest.TestCase):
    """Exercise parent repository readiness checks."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
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
        )

    def test_materialized_parent_fixture_passes(self) -> None:
        """A correctly materialized parent fixture should pass."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PARENT_REPO_READINESS=pass", result.stdout)

    def test_missing_active_contract_fails(self) -> None:
        """Template-owned active contract files are required at the parent root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            (root / "documents" / "server-host-contract.md").unlink()

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=error:active_contract:"
                "documents/server-host-contract.md:missing-regular-file",
                result.stdout,
            )

    def test_stale_github_copy_fails(self) -> None:
        """Copied GitHub path constraint files must match their AgentCanon source."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            (root / ".github" / "scripts" / "checkout_agent_canon_submodule.sh").write_text(
                "# stale\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=error:github_copy:"
                ".github/scripts/checkout_agent_canon_submodule.sh:"
                "copy-differs-from-agent-canon-source",
                result.stdout,
            )

    def test_standalone_only_root_document_fails(self) -> None:
        """Standalone-only AgentCanon docs must not leak into parent root docs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_parent_fixture(root)
            self.write_file(root, "documents/SHARED_RUNTIME_SURFACES.md", "stale root copy\n")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "PARENT_REPO_READINESS_FINDING=error:standalone_only_leak:"
                "documents/SHARED_RUNTIME_SURFACES.md:must-not-exist-in-parent-root",
                result.stdout,
            )

    def write_parent_fixture(self, root: Path) -> None:
        """Create a synthetic template-derived parent repo."""
        agent_canon = root / "vendor" / "agent-canon"
        agent_canon.parent.mkdir(parents=True)
        os.symlink(PROJECT_ROOT, agent_canon, target_is_directory=True)
        self.write_required_parent_files(root)
        manifest = load_manifest(root, "vendor/agent-canon", "documents/shared-runtime-surfaces.toml")
        for entry in manifest.entries:
            target = root / entry.path
            if entry.mode == "symlink":
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() or target.is_symlink():
                    continue
                os.symlink(target_for_entry(root, manifest.prefix, entry), target)
            elif entry.mode == "copy":
                source = root / manifest.prefix / entry.source_or_default()
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            elif entry.mode == "regular":
                if not target.exists():
                    self.write_file(root, entry.path, f"{entry.path}\n")

    def write_required_parent_files(self, root: Path) -> None:
        """Write parent-owned files that are outside the shared surface manifest."""
        files = {
            "README.md": "readme\n",
            "QUICK_START.md": "quick start\n",
            "Makefile": "ci:\n\t@true\n",
            ".gitmodules": "[submodule \"vendor/agent-canon\"]\n\tpath = vendor/agent-canon\n\turl = https://github.com/iwashita-nozomu/agent-canon.git\n",
            "goal.md": "goal\n",
            "responsibility-scope.toml": 'catalog_kind = "agent_canon_responsibility_scope"\n',
            ".agent-canon/update-state.toml": "tasks_applied_through = \"fixture\"\n",
            "scripts/README.md": "scripts\n",
            ".dockerignore": ".git\n",
            "docker/README.md": "docker\n",
            "docker/Dockerfile": "FROM ubuntu:24.04\n",
            "docker/requirements.txt": "pytest\n",
            "docker/install_python_dependencies.sh": "#!/usr/bin/env bash\n",
            "docker/register_safe_directories.sh": "#!/usr/bin/env bash\n",
            "docker/packs/default.toml": "[pack]\nname = \"default\"\n",
            "docker/packs/default-host-docker.toml": "[pack]\nname = \"default-host-docker\"\n",
            ".github/workflows/ci.yml": "name: CI\n",
            ".github/workflows/docker-build.yml": "name: Docker Build\n",
        }
        for path, text in files.items():
            self.write_file(root, path, text)
        for relative in [
            "docker/install_python_dependencies.sh",
            "docker/register_safe_directories.sh",
        ]:
            (root / relative).chmod(0o755)

    def write_file(self, root: Path, relative: str, text: str) -> None:
        """Write one fixture file."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
