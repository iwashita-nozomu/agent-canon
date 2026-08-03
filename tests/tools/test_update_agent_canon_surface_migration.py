"""Tests for AgentCanon shared surface migration correctness."""

# @dependency-start
# contract test
# responsibility Verifies parent submodule readiness and non-destructive root-surface migration.
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md shared surface ownership policy
# upstream implementation ../../tools/sync_agent_canon.sh root-surface synchronization
# upstream implementation ../../tools/agent_tools/agent_canon_source_root.py RootResolution contract
# @dependency-end

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT_RESOLUTION = PROJECT_ROOT / "tools" / "agent_tools" / "agent_canon_source_root.py"


def load_root_resolution_module() -> ModuleType:
    """Load the current RootResolution implementation."""
    spec = importlib.util.spec_from_file_location("agent_canon_source_root", ROOT_RESOLUTION)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {ROOT_RESOLUTION}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SurfaceMigrationTest(unittest.TestCase):
    """Verify migration behavior for legacy parent root surfaces."""

    def git(self, root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run one Git command in a fixture repository."""
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=check,
            capture_output=True,
            text=True,
        )

    def configure_git(self, root: Path) -> None:
        """Configure an isolated fixture repository."""
        self.git(root, "config", "user.email", "agent-canon-test@example.invalid")
        self.git(root, "config", "user.name", "AgentCanon test")

    def clone_parent_fixture(self) -> Path:
        """Return a parent fixture with a real main-branch AgentCanon submodule."""
        tmp_root = Path(tempfile.mkdtemp())
        source = tmp_root / "source"
        parent = tmp_root / "parent"

        shutil.copytree(
            PROJECT_ROOT,
            source,
            symlinks=True,
            ignore=shutil.ignore_patterns(
                ".git",
                ".agent-canon",
                "__pycache__",
                ".pytest_cache",
                ".ruff_cache",
            ),
        )
        self.git(source, "init")
        self.configure_git(source)
        self.git(source, "branch", "-M", "main")
        self.git(source, "add", "-A")
        self.git(source, "commit", "-m", "fixture AgentCanon source")

        parent.mkdir()
        self.git(parent, "init")
        self.configure_git(parent)
        self.git(
            parent,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "--branch",
            "main",
            str(source),
            "vendor/agent-canon",
        )
        self.git(parent / "vendor" / "agent-canon", "checkout", "-B", "main")
        self.git(parent, "add", ".gitmodules", "vendor/agent-canon")
        self.git(parent, "commit", "-m", "fixture parent submodule")
        return parent

    def run_sync(self, root: Path, *commands: str) -> subprocess.CompletedProcess[str]:
        """Run one sync command in the fixture root."""
        return subprocess.run(
            [
                "bash",
                str(root / "vendor" / "agent-canon" / "tools" / "sync_agent_canon.sh"),
                *commands,
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "AGENT_CANON_COMMIT_REQUEST_EVIDENCE": "evidence:" + ("0" * 64),
                "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY": "user_request",
                "AGENT_CANON_BRANCH_WORKTREE_REASON": "AgentCanon root surface repair requested by user",
                "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY": "explicit_user_approval",
                "AGENT_CANON_DESTRUCTIVE_GIT_REASON": "Fixture-only legacy surface pruning",
                "AGENT_CANON_FORCE_RELINK": "1",
            },
        )

    def write_file(self, path: Path, text: str) -> None:
        """Write a file for the fixture."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_parent_root_resolution_and_devcontainer_migration(self) -> None:
        """RootResolution and link-root preserve parent-owned regular paths."""
        root = self.clone_parent_fixture()
        root_resolution = load_root_resolution_module()
        resolution = root_resolution.resolve_agent_canon_source_root(root)
        self.assertEqual(resolution.layout, root_resolution.LAYOUT_VENDORED)
        self.assertEqual(resolution.current_repository_root, root.resolve())
        self.assertEqual(
            resolution.source_root,
            (root / "vendor" / "agent-canon").resolve(),
        )
        parent_templates = root / "templates"
        parent_templates.mkdir()
        template_sentinel = parent_templates / "parent-owned.txt"
        template_sentinel.write_text("keep parent templates\n", encoding="utf-8")
        parent_tools = root / "tools"
        parent_tools.mkdir()
        tools_sentinel = parent_tools / "parent-local-tool.sh"
        tools_sentinel.write_text("keep parent tools\n", encoding="utf-8")

        devcontainer = root / ".devcontainer"
        devcontainer.mkdir()
        custom_hook = devcontainer / "post-create-parent.sh"
        unknown_file = devcontainer / "parent-local-marker.txt"
        custom_hook.write_text("#!/usr/bin/env bash\necho parent hook\n", encoding="utf-8")
        custom_hook.chmod(0o755)
        unknown_file.write_text("keep this parent-owned file\n", encoding="utf-8")
        for name in (
            "bootstrap-shared-runtime.sh",
            "finalize-shared-runtime.sh",
            "generate-runtime-compose.sh",
            "docker-compose.generated.yml",
            "post-attach.sh",
            "post-create.sh",
        ):
            self.write_file(devcontainer / name, "legacy wrapper\n")

        result = self.run_sync(root, "link-root")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("agent_canon_parent_submodule=projection_ready", result.stdout)
        self.assertTrue(parent_templates.is_dir())
        self.assertFalse(parent_templates.is_symlink())
        self.assertEqual(
            template_sentinel.read_text(encoding="utf-8"),
            "keep parent templates\n",
        )
        self.assertEqual(
            tools_sentinel.read_text(encoding="utf-8"),
            "keep parent tools\n",
        )
        self.assertFalse((root / "tools" / "sync_agent_canon.sh").exists())
        self.assertFalse((root / "tools" / "agent_tools").exists())
        self.assertTrue((root / "tools" / "agent-canon").is_symlink())
        self.assertTrue(
            (
                root
                / "vendor"
                / "agent-canon"
                / "templates"
                / "documents"
                / "github"
            ).is_dir()
        )
        self.assertTrue(
            (
                root
                / ".github"
                / "PULL_REQUEST_TEMPLATE"
                / "agent_canon.md"
            ).is_file()
        )
        consumer = subprocess.run(
            [
                sys.executable,
                str(
                    root
                    / "vendor"
                    / "agent-canon"
                    / "tools"
                    / "experiments"
                    / "create_experiment_topic.py"
                ),
                "projection-consumer",
                "--repo-root",
                str(root),
                "--dry-run",
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(consumer.returncode, 0, consumer.stdout + consumer.stderr)
        self.assertIn(
            f"template_dir={root / 'vendor' / 'agent-canon' / 'templates' / 'experiments' / '_template'}",
            consumer.stdout,
        )
        self.assertIn(
            "canonical_readme_template="
            f"{root / 'vendor' / 'agent-canon' / 'templates' / 'documents' / 'experiment' / 'README.template.md'}",
            consumer.stdout,
        )
        self.assertTrue(devcontainer.is_dir() and not devcontainer.is_symlink())
        self.assertTrue((devcontainer / "devcontainer.json").is_symlink())
        self.assertEqual(
            os.readlink(devcontainer / "devcontainer.json"),
            "../vendor/agent-canon/.devcontainer/devcontainer.json",
        )
        self.assertEqual(custom_hook.read_text(encoding="utf-8"), "#!/usr/bin/env bash\necho parent hook\n")
        self.assertTrue(os.access(custom_hook, os.X_OK))
        self.assertEqual(unknown_file.read_text(encoding="utf-8"), "keep this parent-owned file\n")
        for name in (
            "bootstrap-shared-runtime.sh",
            "finalize-shared-runtime.sh",
            "generate-runtime-compose.sh",
            "docker-compose.generated.yml",
            "post-attach.sh",
            "post-create.sh",
        ):
            self.assertFalse((devcontainer / name).exists(), name)

        check = self.run_sync(root, "check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("shared surface is in sync", check.stdout)
        self.assertEqual(
            template_sentinel.read_text(encoding="utf-8"),
            "keep parent templates\n",
        )
        self.assertEqual(
            tools_sentinel.read_text(encoding="utf-8"),
            "keep parent tools\n",
        )

    def test_removed_legacy_surface_preserves_unknown_mirror(self) -> None:
        """Known retired mirrors are removed while unknown mirrors remain untouched."""
        root = self.clone_parent_fixture()
        retired = root / "tests" / "tools" / "test_fix_markdown_math.py"
        retired.parent.mkdir(parents=True, exist_ok=True)
        retired.symlink_to(
            root / "vendor" / "agent-canon" / "tests" / "tools" / "test_fix_markdown_math.py"
        )
        unknown = root / "tests" / "tools" / "test_unknown_mirror.py"
        unknown.symlink_to(
            root / "vendor" / "agent-canon" / "tests" / "tools" / "test_fix_markdown_math.py"
        )

        result = self.run_sync(root, "link-root")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(retired.exists(), "retired mirror must be removed")
        self.assertTrue(unknown.is_symlink(), "unknown mirror must not be removed")

        check = self.run_sync(root, "check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)


if __name__ == "__main__":
    unittest.main()
