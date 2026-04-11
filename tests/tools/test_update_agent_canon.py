"""Tests for the derived-repo agent-canon update wrapper."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


def resolve_repo_root() -> Path:
    """Return the repository root for both vendored and mirrored test paths."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists() and (candidate / "vendor" / "agent-canon").exists():
            return candidate
    raise RuntimeError("repository root not found")


REPO_ROOT = resolve_repo_root()


class UpdateAgentCanonTest(unittest.TestCase):
    """Exercise the wrapper through a cloned repository."""

    def clone_repo(self, target: Path) -> None:
        """Clone the current repository into one temporary target."""
        subprocess.run(
            ["git", "clone", "--no-local", str(REPO_ROOT), str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["rsync", "-a", "--delete", "--exclude", ".git", f"{REPO_ROOT}/", str(target)],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_register_local_bare_seeds_remote_and_plan_uses_configured_remote(self) -> None:
        """register-local-bare should seed the bare repo and wire the remote."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "derived-agent-canon.git"
            self.clone_repo(clone_dir)

            register = subprocess.run(
                [
                    "bash",
                    str(clone_dir / "tools" / "update_agent_canon.sh"),
                    "register-local-bare",
                    "--bare-repo",
                    str(bare_repo),
                ],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(register.returncode, 0, register.stderr)
            self.assertIn("agent_canon_remote_", register.stdout)
            self.assertTrue(bare_repo.is_dir())
            self.assertEqual(
                subprocess.run(
                    ["git", "--git-dir", str(bare_repo), "rev-parse", "--verify", "refs/heads/main"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).returncode,
                0,
            )
            remote_url = subprocess.run(
                ["git", "remote", "get-url", "agent-canon"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(remote_url, str(bare_repo))

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_remote_source=configured", plan.stdout)

    def test_plan_reports_snapshot_import_without_subtree_binary(self) -> None:
        """Plan should report the no-subtree route when git-subtree is unavailable."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            work_dir = root / "agent-canon-work"
            missing_exec = root / "missing-git-exec"
            self.clone_repo(clone_dir)

            split_sha = subprocess.run(
                ["git", "subtree", "split", "--prefix=vendor/agent-canon", "HEAD"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(["git", "init", "--bare", str(bare_repo)], check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "push", str(bare_repo), f"{split_sha}:refs/heads/main"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "--git-dir", str(bare_repo), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "clone", str(bare_repo), str(work_dir)], check=True, capture_output=True, text=True)
            marker = work_dir / ".plan-no-subtree-marker"
            marker.write_text("marker\n", encoding="utf-8")
            subprocess.run(["git", "add", marker.name], cwd=work_dir, check=True, capture_output=True, text=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: advance agent canon",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True, capture_output=True, text=True)
            subprocess.run(["git", "remote", "add", "agent-canon", str(bare_repo)], cwd=clone_dir, check=True, capture_output=True, text=True)
            missing_exec.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env["GIT_EXEC_PATH"] = str(missing_exec)

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=snapshot_import_no_subtree", plan.stdout)


if __name__ == "__main__":
    unittest.main()
