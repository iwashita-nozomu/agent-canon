"""Tests for AgentCanon shared surface migration correctness."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYNC = PROJECT_ROOT / "tools" / "sync_agent_canon.sh"


class SurfaceMigrationTest(unittest.TestCase):
    """Verify migration behavior for legacy parent root surfaces."""

    def clone_parent_fixture(self) -> Path:
        """Return a temporary parent-like fixture with vendor symlink projection."""
        tmp_root = Path(tempfile.mkdtemp())
        parent = tmp_root / "parent"
        subprocess.run(
            ["git", "clone", "--no-local", str(PROJECT_ROOT), str(parent)],
            check=True,
            capture_output=True,
            text=True,
        )
        (parent / "vendor").mkdir(parents=True, exist_ok=True)
        (parent / "tools").mkdir(parents=True, exist_ok=True)
        if (parent / "tools" / "agent-canon").exists():
            (parent / "tools" / "agent-canon").unlink()
        if (parent / "tools" / "agent-canon").is_symlink():
            (parent / "tools" / "agent-canon").unlink()
        os.symlink(
            "../vendor/agent-canon/tools",
            str(parent / "tools" / "agent-canon"),
            target_is_directory=True,
        )
        os.symlink(
            str(PROJECT_ROOT),
            str(parent / "vendor" / "agent-canon"),
            target_is_directory=True,
        )
        return parent

    def run_sync(self, root: Path, *commands: str) -> subprocess.CompletedProcess[str]:
        """Run one sync command in the fixture root."""
        sync_script = root / "tools" / "sync_agent_canon.sh"
        return subprocess.run(
            ["bash", str(sync_script), *commands],
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
                "AGENT_CANON_DESTRUCTIVE_GIT_REASON": "Remove temporary clone after pushed PR and verified remote refs",
                "AGENT_CANON_FORCE_RELINK": "1",
            },
        )

    def write_file(self, path: Path, text: str) -> None:
        """Write a file for the fixture."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_parent_link_root_rebuilds_devcontainer_shape(self) -> None:
        """Legacy .devcontainer materialization should become explicit minimal parent shape."""
        root = self.clone_parent_fixture()

        legacy_devcontainer = root / ".devcontainer"
        if legacy_devcontainer.exists() or legacy_devcontainer.is_symlink():
            if legacy_devcontainer.is_symlink() or legacy_devcontainer.is_file():
                legacy_devcontainer.unlink()
            else:
                for child in legacy_devcontainer.iterdir():
                    if child.is_file() or child.is_symlink():
                        child.unlink()
                    else:
                        # best-effort for fixture cleanup; not expected today.
                        if child.is_dir():
                            for item in child.rglob("*"):
                                if item.is_file() or item.is_symlink():
                                    item.unlink()
                                else:
                                    item.rmdir()
                            child.rmdir()
                legacy_devcontainer.rmdir()
        legacy_devcontainer.mkdir()
        for name in (
            "bootstrap-shared-runtime.sh",
            "finalize-shared-runtime.sh",
            "generate-runtime-compose.sh",
            "post-attach.sh",
            "post-create.sh",
        ):
            self.write_file(legacy_devcontainer / name, "legacy\n")
            os.chmod(legacy_devcontainer / name, 0o755)

        result = self.run_sync(root, "link-root")
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertTrue(legacy_devcontainer.is_dir() and not legacy_devcontainer.is_symlink())
        self.assertTrue((legacy_devcontainer / "devcontainer.json").is_symlink())
        self.assertEqual(
            os.readlink(legacy_devcontainer / "devcontainer.json"),
            "../vendor/agent-canon/.devcontainer/devcontainer.json",
        )
        self.assertTrue((legacy_devcontainer / "post-create-parent.sh").is_file())
        self.assertTrue(os.access(str(legacy_devcontainer / "post-create-parent.sh"), os.X_OK))
        for name in (
            "bootstrap-shared-runtime.sh",
            "finalize-shared-runtime.sh",
            "generate-runtime-compose.sh",
            "post-attach.sh",
            "post-create.sh",
        ):
            self.assertFalse((legacy_devcontainer / name).exists())

        check = self.run_sync(root, "check")
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_parent_status_uses_projected_copy_comparison(self) -> None:
        """status and check should agree for parent-projected GitHub copy surfaces."""
        root = self.clone_parent_fixture()

        result = self.run_sync(root, "link-root")
        self.assertEqual(result.returncode, 0, result.stderr)

        status = self.run_sync(root, "status")
        self.assertEqual(status.returncode, 0, status.stderr)

        for path in (
            ".github/workflows/agent-coordination.yml",
            ".github/workflows/agent-improvement-guide.yml",
            ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
            ".github/scripts/checkout_agent_canon_submodule.sh",
        ):
            self.assertNotIn(f"copy[{path}]=drift", status.stdout, status.stdout)

        check = self.run_sync(root, "check")
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_removed_legacy_surface_is_retired_without_pruning_unknown(self) -> None:
        """Known retired mirrors must be removed; unknown symlinks remain untouched."""
        root = self.clone_parent_fixture()

        retired = root / "tests" / "tools" / "test_fix_markdown_math.py"
        retired.parent.mkdir(parents=True, exist_ok=True)
        if retired.exists() or retired.is_symlink():
            retired.unlink()
        retired.symlink_to(
            str(root / "vendor" / "agent-canon" / "tests" / "tools" / "test_fix_markdown_math.py")
        )

        unknown = root / "tests" / "tools" / "test_unknown_mirror.py"
        unknown.parent.mkdir(parents=True, exist_ok=True)
        if unknown.exists() or unknown.is_symlink():
            unknown.unlink()
        unknown.symlink_to(
            str(
                root
                / "vendor"
                / "agent-canon"
                / "tests"
                / "tools"
                / "test_fix_markdown_math.py"
            )
        )

        result = self.run_sync(root, "link-root")
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertFalse(retired.exists(), "retired mirror must be removed")
        self.assertTrue(unknown.is_symlink(), "unknown mirror must not be removed")
        check = self.run_sync(root, "check")
        self.assertEqual(check.returncode, 0, check.stderr)


if __name__ == "__main__":
    unittest.main()
