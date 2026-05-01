# @dependency-start
# responsibility Tests test update agent canon behavior.
# upstream design ../../tools/README.md validated automation surface
# @dependency-end

"""Tests for the derived-repo agent-canon update wrapper."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


def resolve_repo_root() -> Path:
    """Return the repository root for both vendored and mirrored test paths."""
    git_root = None
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists():
            git_root = candidate
            if (candidate / "vendor" / "agent-canon").exists():
                return candidate
    if git_root is not None:
        raise unittest.SkipTest("derived-repo agent-canon wrapper tests require vendor/agent-canon")
    raise RuntimeError("git repository root not found")


REPO_ROOT = resolve_repo_root()
OVERLAY_EXCLUDED_NAMES = {".git", ".pytest_cache", ".ruff_cache", "reports"}


class UpdateAgentCanonTest(unittest.TestCase):
    """Exercise the wrapper through a cloned repository."""

    def overlay_working_tree(self, target: Path) -> None:
        """Mirror the current working tree into one clone without external tools."""
        for child in target.iterdir():
            if child.name in OVERLAY_EXCLUDED_NAMES:
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()

        for child in REPO_ROOT.iterdir():
            if child.name in OVERLAY_EXCLUDED_NAMES:
                continue
            destination = target / child.name
            subprocess.run(
                ["cp", "-a", str(child), str(destination)],
                check=True,
                capture_output=True,
                text=True,
            )

    def clone_repo(self, target: Path) -> None:
        """Clone the current repository into one temporary target."""
        subprocess.run(
            ["git", "clone", "--no-local", str(REPO_ROOT), str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
        self.overlay_working_tree(target)
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=target,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if status:
            subprocess.run(
                ["git", "config", "user.name", "Update Agent Canon Test"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "update-agent-canon@example.invalid"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "add", "-A"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "test: overlay current working tree"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
            )

    def split_agent_canon_snapshot(self, repo: Path) -> str:
        """Return a split commit for fresh clones that may not have subtree join objects."""
        plain = subprocess.run(
            ["git", "subtree", "split", "--prefix=vendor/agent-canon", "HEAD"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
        if plain.returncode == 0 and plain.stdout.strip():
            return plain.stdout.strip()

        ignore_joins = subprocess.run(
            ["git", "subtree", "split", "--ignore-joins", "--prefix=vendor/agent-canon", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return ignore_joins.stdout.strip()

    def replace_tree(self, source: Path, target: Path) -> None:
        """Replace target contents without depending on rsync in minimal containers."""
        for child in target.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()

        for child in source.iterdir():
            if child.name == ".git":
                continue
            destination = target / child.name
            if child.is_symlink():
                os.symlink(os.readlink(child), destination)
            elif child.is_dir():
                shutil.copytree(child, destination, symlinks=True)
            else:
                shutil.copy2(child, destination, follow_symlinks=False)

    def test_register_local_bare_seeds_remote_and_plan_uses_configured_remote(self) -> None:
        """Register-local-bare should seed the bare repo and wire the remote."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "derived-agent-canon.git"
            source_repo = root / "shared-agent-canon"
            proposal_branch = "canon-proposal/derived-agent-canon"
            self.clone_repo(clone_dir)

            register = subprocess.run(
                [
                    "bash",
                    str(clone_dir / "tools" / "update_agent_canon.sh"),
                    "register-local-bare",
                    "--bare-repo",
                    str(bare_repo),
                    "--proposal-branch",
                    proposal_branch,
                    "--source-repo",
                    str(source_repo),
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
                    [
                        "git",
                        "--git-dir",
                        str(bare_repo),
                        "rev-parse",
                        "--verify",
                        "refs/heads/main",
                    ],
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
            subprocess.run(
                ["git", "clone", str(bare_repo), str(source_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "checkout", "-B", "main", "origin/main"],
                cwd=source_repo,
                check=True,
                capture_output=True,
                text=True,
            )
            stored_branch = subprocess.run(
                ["git", "config", "--get", "agent-canon.proposalBranch"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(stored_branch, proposal_branch)
            stored_source = subprocess.run(
                ["git", "config", "--get", "agent-canon.sourceRepo"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(stored_source, str(source_repo))
            self.assertEqual(
                subprocess.run(
                    [
                        "git",
                        "--git-dir",
                        str(bare_repo),
                        "rev-parse",
                        "--verify",
                        f"refs/heads/{proposal_branch}",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                ).returncode,
                0,
            )

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_remote_source=plan_override", plan.stdout)
            self.assertIn(
                "agent_canon_plan_apply_order=refresh_remote_snapshot_then_local_sync", plan.stdout
            )

    def test_register_local_bare_clears_implicit_source_repo_for_daily_validation(self) -> None:
        """Register-local-bare should default derived repos back to local-sync-only."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "derived-agent-canon.git"
            self.clone_repo(clone_dir)

            env = os.environ.copy()
            env["AGENT_CANON_SOURCE_REPO"] = str(root / "shared-agent-canon")

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
                env=env,
            )
            self.assertEqual(register.returncode, 0, register.stderr)
            self.assertIn("agent_canon_source_repo=<unset>", register.stdout)

            stored_source = subprocess.run(
                ["git", "config", "--get", "agent-canon.sourceRepo"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(stored_source.returncode, 0)
            self.assertEqual(stored_source.stdout.strip(), "")

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_source_repo=<unset>", plan.stdout)
            self.assertIn("agent_canon_plan_apply_order=local_sync_only", plan.stdout)

    def test_push_proposal_uses_configured_proposal_branch(self) -> None:
        """Push-proposal should update the configured remote branch."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "derived-agent-canon.git"
            proposal_branch = "canon-proposal/test-derived"
            self.clone_repo(clone_dir)

            subprocess.run(
                [
                    "bash",
                    str(clone_dir / "tools" / "update_agent_canon.sh"),
                    "register-local-bare",
                    "--bare-repo",
                    str(bare_repo),
                    "--proposal-branch",
                    proposal_branch,
                ],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            marker = clone_dir / "vendor" / "agent-canon" / ".proposal-branch-marker"
            marker.write_text("proposal\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", str(marker.relative_to(clone_dir))],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: update proposal branch snapshot",
                ],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            push = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "push-proposal"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(push.returncode, 0, push.stderr)
            proposal_tree = subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(bare_repo),
                    "ls-tree",
                    "-r",
                    "--name-only",
                    proposal_branch,
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn(".proposal-branch-marker", proposal_tree)

    def test_plan_reports_snapshot_import_without_subtree_binary(self) -> None:
        """Plan should report the no-subtree route when git-subtree is unavailable."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            work_dir = root / "agent-canon-work"
            missing_exec = root / "missing-git-exec"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
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
            subprocess.run(
                ["git", "clone", str(bare_repo), str(work_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            marker = work_dir / ".plan-no-subtree-marker"
            marker.write_text("marker\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", marker.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
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
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            missing_exec.mkdir(parents=True, exist_ok=True)
            git_binary = shutil.which("git")
            self.assertIsNotNone(git_binary)
            git_wrapper = missing_exec / "git"
            git_wrapper.write_text(
                "#!/usr/bin/env bash\n"
                "for arg in \"$@\"; do\n"
                "  if [[ \"$arg\" == \"subtree\" ]]; then\n"
                "    echo 'git: subtree unavailable in test' >&2\n"
                "    exit 1\n"
                "  fi\n"
                "done\n"
                f"exec {git_binary} \"$@\"\n",
                encoding="utf-8",
            )
            git_wrapper.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{missing_exec}{os.pathsep}{env['PATH']}"

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertRegex(
                plan.stdout,
                r"agent_canon_plan_route=(snapshot_import_tree_match|snapshot_import_no_subtree)",
            )

    def test_plan_prefers_subtree_pull_when_local_split_is_remote_ancestor(self) -> None:
        """Plan should prefer subtree_pull over tree-match fallback when subtree metadata exists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            work_dir = root / "agent-canon-work"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
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
            subprocess.run(
                ["git", "clone", str(bare_repo), str(work_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            marker = work_dir / ".subtree-pull-marker"
            marker.write_text("marker\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", marker.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: advance agent canon with subtree metadata available",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=subtree_pull", plan.stdout)

    def test_apply_succeeds_when_local_history_diverged_but_tree_matches_remote_history(
        self,
    ) -> None:
        """Apply should recover when local split diverged but the current tree exists upstream."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            work_dir = root / "agent-canon-work"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
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
            subprocess.run(
                ["git", "remote", "remove", "agent-canon"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "clone", str(bare_repo), str(work_dir)],
                check=True,
                capture_output=True,
                text=True,
            )

            remote_marker_a = work_dir / ".remote-tree-match-marker"
            remote_marker_a.write_text("remote-a\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", remote_marker_a.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: remote tree match base",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            local_diverged_marker = clone_dir / "vendor" / "agent-canon" / ".diverged-local-marker"
            local_diverged_marker.write_text("diverged\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", str(local_diverged_marker.relative_to(clone_dir))],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: diverge local shared canon",
                ],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            self.replace_tree(work_dir, clone_dir / "vendor" / "agent-canon")
            subprocess.run(
                ["git", "add", "-A"], cwd=clone_dir, check=True, capture_output=True, text=True
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: realign local tree to remote history",
                ],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            remote_marker_b = work_dir / ".remote-after-tree-match-marker"
            remote_marker_b.write_text("remote-b\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", remote_marker_b.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: remote advance after tree match",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=snapshot_import_tree_match", plan.stdout)

            apply = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "apply"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(apply.returncode, 0, apply.stderr)
            combined_output = f"{apply.stdout}\n{apply.stderr}"
            self.assertIn(
                "agent_canon_snapshot_import=tree_match_in_remote_history", combined_output
            )
            self.assertIn(
                "agent_canon_update_method=snapshot_import_after_subtree_pull_failure",
                combined_output,
            )

    def test_apply_fails_closed_when_local_shared_canon_history_diverges(self) -> None:
        """Apply should stop before mutating the worktree when local vendor history diverges."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            work_dir = root / "agent-canon-work"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
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
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "clone", str(bare_repo), str(work_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            remote_marker = work_dir / ".remote-diverged-marker"
            remote_marker.write_text("remote-diverged\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", remote_marker.name],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: diverge remote shared canon",
                ],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            diverged_marker = clone_dir / "vendor" / "agent-canon" / ".diverged-local-marker"
            diverged_marker.write_text("diverged\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", str(diverged_marker.relative_to(clone_dir))],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Update Agent Canon Test",
                    "-c",
                    "user.email=update-agent-canon@example.invalid",
                    "commit",
                    "-m",
                    "test: diverge local shared canon",
                ],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn("agent_canon_plan_route=diverged_local_history", plan.stdout)

            apply = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "apply"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(apply.returncode, 0)
            combined_output = f"{apply.stdout}\n{apply.stderr}"
            self.assertIn("agent_canon_snapshot_import=diverged_history", combined_output)
            self.assertIn("diverged", combined_output)

            status = subprocess.run(
                ["git", "status", "--short"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(status, "")

    def test_apply_refreshes_remote_snapshot_before_local_sync(self) -> None:
        """Apply should refresh the configured remote from source repo before local import."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            source_repo = root / "agent-canon-source"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
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
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "clone", str(bare_repo), str(source_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Update Agent Canon Test"],
                cwd=source_repo,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "update-agent-canon@example.invalid"],
                cwd=source_repo,
                check=True,
                capture_output=True,
                text=True,
            )

            source_marker = source_repo / ".refresh-first-marker"
            source_marker.write_text("source-refresh\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", source_marker.name],
                cwd=source_repo,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "test: advance source snapshot"],
                cwd=source_repo,
                check=True,
                capture_output=True,
                text=True,
            )

            subprocess.run(
                ["git", "config", "agent-canon.sourceRepo", str(source_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            plan = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "plan"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn(
                "agent_canon_plan_apply_order=refresh_remote_snapshot_then_local_sync", plan.stdout
            )
            self.assertIn(f"agent_canon_plan_source_repo={source_repo}", plan.stdout)

            apply = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "apply"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(apply.returncode, 0, apply.stderr)
            combined_output = f"{apply.stdout}\n{apply.stderr}"
            self.assertIn("agent_canon_refresh_status=updated_remote_snapshot", combined_output)

            self.assertTrue(
                (clone_dir / "vendor" / "agent-canon" / ".refresh-first-marker").is_file()
            )
            remote_tree = subprocess.run(
                ["git", "--git-dir", str(bare_repo), "ls-tree", "-r", "--name-only", "main"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn(".refresh-first-marker", remote_tree)

    def test_apply_fails_closed_when_source_repo_is_dirty(self) -> None:
        """Apply should stop before local mutation when the configured source repo is dirty."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            bare_repo = root / "agent-canon-upstream.git"
            source_repo = root / "agent-canon-source"
            self.clone_repo(clone_dir)

            split_sha = self.split_agent_canon_snapshot(clone_dir)
            subprocess.run(
                ["git", "init", "--bare", str(bare_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
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
            subprocess.run(
                ["git", "remote", "add", "agent-canon", str(bare_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "clone", str(bare_repo), str(source_repo)],
                check=True,
                capture_output=True,
                text=True,
            )
            dirty_marker = source_repo / ".dirty-source-marker"
            dirty_marker.write_text("dirty\n", encoding="utf-8")
            subprocess.run(
                ["git", "config", "agent-canon.sourceRepo", str(source_repo)],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            apply = subprocess.run(
                ["bash", str(clone_dir / "tools" / "update_agent_canon.sh"), "apply"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(apply.returncode, 0)
            combined_output = f"{apply.stdout}\n{apply.stderr}"
            self.assertIn("source repo is dirty", combined_output)
            self.assertFalse(
                (clone_dir / "vendor" / "agent-canon" / ".dirty-source-marker").exists()
            )

            status = subprocess.run(
                ["git", "status", "--short"],
                cwd=clone_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(status, "")


if __name__ == "__main__":
    unittest.main()
