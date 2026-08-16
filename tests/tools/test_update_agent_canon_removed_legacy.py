"""Regression tests for removed-legacy update write-set isolation."""

# @dependency-start
# contract test
# responsibility Verifies AgentCanon updates preserve user-owned state outside the current projection transaction.
# upstream implementation ../../tools/agent_tools/surface_manifest.py excludes root-absence fixed points from sync pathspecs
# upstream implementation ../../tools/sync_agent_canon.sh consumes root-absence specs during update staging and commit
# upstream design ../../documents/agent-canon/agent-canon-update-route.md owns update materialization acceptance
# @dependency-end

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RemovedLegacyUpdateWriteSetTest(unittest.TestCase):
    """Verify removed-legacy paths do not widen the update write set."""

    def git(
        self,
        root: Path,
        *args: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
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

    def copy_source_fixture(self, destination: Path) -> None:
        """Copy the current AgentCanon source without repository-local outputs."""
        shutil.copytree(
            PROJECT_ROOT,
            destination,
            symlinks=True,
            ignore=shutil.ignore_patterns(
                ".git",
                ".agent-canon",
                "__pycache__",
                ".pytest_cache",
                ".ruff_cache",
                "reports",
            ),
        )
        self.git(destination, "init")
        self.configure_git(destination)
        self.git(destination, "branch", "-M", "main")
        self.git(destination, "add", "-A")
        self.git(
            destination,
            "update-index",
            "--chmod=+x",
            "tools/sync_agent_canon.sh",
        )
        self.git(destination, "commit", "-m", "fixture AgentCanon source")

    def parent_fixture(self) -> tuple[Path, Path]:
        """Create a parent repository with a main-branch AgentCanon submodule."""
        tmp_handle = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_handle.cleanup)
        tmp_root = Path(tmp_handle.name)
        source = tmp_root / "source"
        parent = tmp_root / "parent"

        self.copy_source_fixture(source)
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
        return source, parent

    def run_sync(
        self,
        root: Path,
        *commands: str,
    ) -> subprocess.CompletedProcess[str]:
        """Run one protected sync command in the fixture parent."""
        environment = {
            **os.environ,
            "AGENT_CANON_COMMIT_REQUEST_EVIDENCE": "evidence:" + ("0" * 64),
            "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY": "user_request",
            "AGENT_CANON_BRANCH_WORKTREE_REASON": (
                "AgentCanon update regression requested by user"
            ),
            "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY": "explicit_user_approval",
            "AGENT_CANON_DESTRUCTIVE_GIT_REASON": (
                "Fixture-only AgentCanon update"
            ),
            "AGENT_CANON_FORCE_RELINK": "1",
        }
        return subprocess.run(
            [
                "bash",
                str(
                    root
                    / "vendor"
                    / "agent-canon"
                    / "tools"
                    / "sync_agent_canon.sh"
                ),
                *commands,
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def test_ensure_latest_preserves_preexisting_parent_state(self) -> None:
        """A staged retired deletion never becomes an AgentCanon-owned path."""
        source, parent = self.parent_fixture()

        initial_projection = self.run_sync(parent, "link-root")
        self.assertEqual(
            initial_projection.returncode,
            0,
            initial_projection.stdout + initial_projection.stderr,
        )
        self.git(parent, "add", "-A")
        self.git(parent, "commit", "-m", "materialize initial root projection")

        retired = parent / ".agents"
        retired.symlink_to("vendor/agent-canon/README.md")
        unrelated = parent / "parent-owned.txt"
        unrelated.write_text("baseline\n", encoding="utf-8")
        self.git(parent, "add", ".agents", "parent-owned.txt")
        self.git(parent, "commit", "-m", "add parent-owned state")

        self.git(parent, "rm", ".agents")
        unrelated.write_text("dirty parent state\n", encoding="utf-8")
        experiment = parent / "experiment.txt"
        experiment.write_text("untracked experiment\n", encoding="utf-8")

        readme = source / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\nAgentCanon removed-legacy update fixture.\n",
            encoding="utf-8",
        )
        self.git(source, "add", "README.md")
        self.git(source, "commit", "-m", "advance fixture AgentCanon main")
        remote_sha = self.git(source, "rev-parse", "HEAD").stdout.strip()

        result = self.run_sync(parent, "ensure-latest", "main")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("pathspec '.agents'", result.stderr)
        self.assertEqual(
            result.stdout.count("agent_canon_parent_submodule=projection_ready"),
            1,
            result.stdout,
        )
        self.assertEqual(
            self.git(parent, "rev-parse", "HEAD:vendor/agent-canon").stdout.strip(),
            remote_sha,
        )
        self.assertEqual(
            self.git(parent, "status", "--short", "--", ".agents").stdout,
            "D  .agents\n",
        )
        self.assertIn(
            ".agents",
            self.git(parent, "diff", "--cached", "--name-only").stdout.splitlines(),
        )
        self.assertIn(
            "parent-owned.txt",
            self.git(parent, "diff", "--name-only").stdout.splitlines(),
        )
        self.assertIn(
            "?? experiment.txt",
            self.git(
                parent,
                "status",
                "--short",
                "--untracked-files=all",
            ).stdout.splitlines(),
        )
        self.assertNotIn(
            ".agents",
            self.git(
                parent,
                "show",
                "--pretty=",
                "--name-only",
                "HEAD",
            ).stdout.splitlines(),
        )

        check = self.run_sync(parent, "check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertEqual(
            self.git(parent, "status", "--short", "--", ".agents").stdout,
            "D  .agents\n",
        )
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "dirty parent state\n")
        self.assertEqual(experiment.read_text(encoding="utf-8"), "untracked experiment\n")


if __name__ == "__main__":
    unittest.main()
