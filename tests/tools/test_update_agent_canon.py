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
AGENT_CANON_IS_SUBMODULE = bool(
    subprocess.run(
        [
            "git",
            "config",
            "-f",
            ".gitmodules",
            "--get",
            "submodule.vendor/agent-canon.path",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
)
OVERLAY_EXCLUDED_NAMES = {".git", ".pytest_cache", ".ruff_cache", "reports"}
SUBMODULE_GITFILE = Path("vendor") / "agent-canon" / ".git"


@unittest.skipIf(
    AGENT_CANON_IS_SUBMODULE,
    "subtree snapshot wrapper tests do not apply when vendor/agent-canon is a submodule",
)
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
        submodule_gitfile = target / SUBMODULE_GITFILE
        if submodule_gitfile.is_file():
            submodule_gitfile.unlink()

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

    def test_link_root_converts_shared_goal_symlink_to_repo_local_file(self) -> None:
        """goal.md is repo-local state and must not be a shared canon symlink."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            clone_dir = root / "clone"
            self.clone_repo(clone_dir)
            goal_path = clone_dir / "goal.md"
            if goal_path.exists() or goal_path.is_symlink():
                goal_path.unlink()
            os.symlink("vendor/agent-canon/goal.md", goal_path)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            check = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "check"],
                cwd=clone_dir,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(goal_path.is_symlink())
            self.assertIn("repo-local goal", goal_path.read_text(encoding="utf-8"))
            self.assertEqual(check.returncode, 0, check.stderr)

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


@unittest.skipUnless(
    AGENT_CANON_IS_SUBMODULE,
    "submodule wrapper tests only apply when vendor/agent-canon is a submodule",
)
class SubmoduleUpdateAgentCanonTest(unittest.TestCase):
    """Exercise submodule-specific update routes."""

    def make_agent_canon_remote(self, root: Path) -> tuple[Path, Path]:
        """Create one bare AgentCanon remote and working clone."""
        root.mkdir(parents=True, exist_ok=True)
        bare_repo = root / "agent-canon.git"
        work_dir = root / "agent-canon-work"
        subprocess.run(["git", "init", "--bare", str(bare_repo)], check=True)
        subprocess.run(["git", "clone", str(bare_repo), str(work_dir)], check=True)
        subprocess.run(["git", "switch", "-c", "main"], cwd=work_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Submodule Test"], cwd=work_dir, check=True)
        subprocess.run(
            ["git", "config", "user.email", "submodule-test@example.invalid"],
            cwd=work_dir,
            check=True,
        )
        (work_dir / "README.md").write_text("# AgentCanon\n", encoding="utf-8")
        (work_dir / "ROOT_AGENTS.md").write_text("# Root agents\n", encoding="utf-8")
        (work_dir / "CLAUDE.md").write_text("# Claude\n", encoding="utf-8")
        (work_dir / "tools" / "agent_tools").mkdir(parents=True)
        shutil.copy2(
            REPO_ROOT / "tools" / "agent_tools" / "surface_manifest.py",
            work_dir / "tools" / "agent_tools" / "surface_manifest.py",
        )
        (work_dir / "documents").mkdir()
        (work_dir / "documents" / "shared-runtime-surfaces.toml").write_text(
            "\n".join(
                [
                    'version = 1',
                    'prefix = "vendor/agent-canon"',
                    '',
                    '[[surface]]',
                    'path = "AGENTS.md"',
                    'mode = "symlink"',
                    'source = "ROOT_AGENTS.md"',
                    'owner = "agent-canon"',
                    'class = "runtime_surface"',
                    '',
                    '[[group]]',
                    'mode = "symlink"',
                    'owner = "agent-canon"',
                    'class = "runtime_surface"',
                    'paths = [',
                    '  "CLAUDE.md",',
                    '  ".github/AGENTS.md",',
                    '  ".github/copilot-instructions.md",',
                    ']',
                    '',
                    '[[group]]',
                    'mode = "copy"',
                    'owner = "github-path-constraint"',
                    'class = "github_copy"',
                    'local_override_allowed = false',
                    'paths = [',
                    '  ".github/workflows/agent-coordination.yml",',
                    '  ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",',
                    ']',
                    '',
                    '[[group]]',
                    'mode = "regular"',
                    'owner = "template-or-derived-repo"',
                    'class = "active_contract"',
                    'local_override_allowed = true',
                    'source_prefix = ""',
                    'paths = [',
                    '  "documents/README.md",',
                    ']',
                    '',
                    '[[surface]]',
                    'path = "goal.md"',
                    'mode = "repo_state"',
                    'owner = "project"',
                    'class = "durable_state"',
                    'local_override_allowed = true',
                    '',
                ]
            ),
            encoding="utf-8",
        )
        (work_dir / ".github" / "workflows").mkdir(parents=True)
        (work_dir / ".github" / "PULL_REQUEST_TEMPLATE").mkdir(parents=True)
        (work_dir / "documents" / "README.md").write_text(
            "# Derived Documents Seed\n",
            encoding="utf-8",
        )
        (work_dir / ".github" / "AGENTS.md").write_text(
            "# GitHub agents\n",
            encoding="utf-8",
        )
        (work_dir / ".github" / "copilot-instructions.md").write_text(
            "# Copilot instructions\n",
            encoding="utf-8",
        )
        (work_dir / ".github" / "workflows" / "agent-coordination.yml").write_text(
            "name: agent coordination\n",
            encoding="utf-8",
        )
        (work_dir / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md").write_text(
            "# AgentCanon PR\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                "git",
                "add",
                "README.md",
                "ROOT_AGENTS.md",
                "CLAUDE.md",
                ".github",
                "documents",
                "tools",
            ],
            cwd=work_dir,
            check=True,
        )
        subprocess.run(["git", "commit", "-m", "initial agent canon"], cwd=work_dir, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
        subprocess.run(
            ["git", "--git-dir", str(bare_repo), "symbolic-ref", "HEAD", "refs/heads/main"],
            check=True,
        )
        return bare_repo, work_dir

    def make_superproject(self, root: Path, bare_repo: Path) -> Path:
        """Create one derived repo with AgentCanon as a submodule."""
        repo = root / "derived"
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Submodule Test"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "submodule-test@example.invalid"],
            cwd=repo,
            check=True,
        )
        (repo / "tools").mkdir()
        shutil.copy2(REPO_ROOT / "tools" / "sync_agent_canon.sh", repo / "tools")
        shutil.copy2(REPO_ROOT / "tools" / "update_agent_canon.sh", repo / "tools")
        subprocess.run(
            [
                "git",
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                "-b",
                "main",
                str(bare_repo),
                "vendor/agent-canon",
            ],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "add", ".gitmodules", "tools", "vendor/agent-canon"],
            cwd=repo,
            check=True,
        )
        subprocess.run(["git", "commit", "-m", "add submodule"], cwd=repo, check=True)
        return repo

    def test_ensure_latest_reports_already_current_submodule(self) -> None:
        """Ensure-latest should no-op when the parent pin already matches remote main."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_latest=already_current_submodule", result.stdout)

    def test_pull_redirects_to_ensure_latest_for_submodules(self) -> None:
        """The legacy pull command should use submodule ensure-latest semantics."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "pull"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_latest=updating_submodule", result.stdout)
            self.assertTrue((repo / "vendor" / "agent-canon" / "remote-marker.txt").is_file())

    def test_status_reports_submodule_mode_and_pin(self) -> None:
        """Status output should expose submodule mode, URL, and pin evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "status"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("prefix_mode_name=submodule", result.stdout)
            self.assertIn(f"submodule_url={bare_repo}", result.stdout)
            self.assertRegex(result.stdout, r"submodule_pin=[0-9a-f]{40}")

    def test_snapshot_alias_reports_deprecation(self) -> None:
        """The legacy snapshot alias should advertise link-root as the replacement."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "snapshot"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_snapshot_alias=deprecated_use_link_root", result.stdout)

    def test_link_root_keeps_goal_local_and_syncs_copy_surfaces(self) -> None:
        """Link-root should restore root views without copying standalone-only PR templates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            goal_path = repo / "goal.md"
            os.symlink("vendor/agent-canon/goal.md", goal_path)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(goal_path.is_symlink())
            self.assertIn("repo-local goal", goal_path.read_text(encoding="utf-8"))
            self.assertEqual(
                (repo / ".github" / "workflows" / "agent-coordination.yml").read_text(
                    encoding="utf-8"
                ),
                (
                    repo
                    / "vendor"
                    / "agent-canon"
                    / ".github"
                    / "workflows"
                    / "agent-coordination.yml"
                ).read_text(encoding="utf-8"),
            )
            self.assertEqual(
                (repo / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md").read_text(
                    encoding="utf-8"
                ),
                (
                    repo
                    / "vendor"
                    / "agent-canon"
                    / ".github"
                    / "PULL_REQUEST_TEMPLATE"
                    / "agent_canon.md"
                ).read_text(encoding="utf-8"),
            )
            self.assertEqual(
                (repo / ".github" / "copilot-instructions.md").readlink().as_posix(),
                "../vendor/agent-canon/.github/copilot-instructions.md",
            )
            self.assertFalse((repo / ".github" / "PULL_REQUEST_TEMPLATE.md").exists())

    def test_link_root_materializes_missing_and_legacy_regular_active_contracts(self) -> None:
        """Link-root should seed active-contract docs without keeping legacy symlinks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            documents_dir = repo / "documents"
            documents_dir.mkdir()
            readme_path = documents_dir / "README.md"

            result_missing = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result_missing.returncode, 0, result_missing.stderr)
            self.assertFalse(readme_path.is_symlink())
            self.assertIn(
                "Derived Documents Seed",
                readme_path.read_text(encoding="utf-8"),
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            documents_dir = repo / "documents"
            documents_dir.mkdir()
            readme_path = documents_dir / "README.md"
            os.symlink("../vendor/agent-canon/documents/README.md", readme_path)
            result_symlink = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result_symlink.returncode, 0, result_symlink.stderr)
            self.assertFalse(readme_path.is_symlink())
            self.assertIn(
                "Derived Documents Seed",
                readme_path.read_text(encoding="utf-8"),
            )

    def test_plan_reports_submodule_update_without_root_commit_lookup_errors(self) -> None:
        """Plan should compare submodule commits inside the submodule repo."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertNotIn("Not a valid commit name", plan.stderr)
            self.assertIn("agent_canon_plan_prefix_mode=submodule", plan.stdout)
            self.assertIn("agent_canon_plan_route=submodule_update", plan.stdout)

    def test_plan_honors_source_repo_override_for_submodule_remote(self) -> None:
        """Submodule plan should fetch the resolved source repo instead of origin."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_bare_repo, _old_work_dir = self.make_agent_canon_remote(root / "old")
            new_work_dir = root / "new" / "agent-canon-work"
            subprocess.run(
                ["git", "clone", str(old_bare_repo), str(new_work_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "config", "user.name", "Submodule Test"], cwd=new_work_dir, check=True)
            subprocess.run(
                ["git", "config", "user.email", "submodule-test@example.invalid"],
                cwd=new_work_dir,
                check=True,
            )
            repo = self.make_superproject(root, old_bare_repo)
            (new_work_dir / "source-marker.txt").write_text("source\n", encoding="utf-8")
            subprocess.run(["git", "add", "source-marker.txt"], cwd=new_work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance source"], cwd=new_work_dir, check=True)

            env = {
                **os.environ,
                "AGENT_CANON_SOURCE_REPO": str(new_work_dir),
                "AGENT_CANON_REMOTE_URL": str(old_bare_repo),
            }
            plan = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "plan"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn(f"agent_canon_plan_effective_remote_url={new_work_dir}", plan.stdout)
            self.assertIn("agent_canon_plan_remote_source=plan_override", plan.stdout)
            self.assertIn(f"agent_canon_plan_remote_url={new_work_dir}", plan.stdout)
            self.assertIn("agent_canon_plan_route=submodule_update", plan.stdout)

    def test_latest_check_fails_clean_submodule_worktree_at_remote_with_stale_parent_pin(
        self,
    ) -> None:
        """Latest gate should not pass until the parent gitlink is committed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (repo / "tools" / "ci").mkdir()
            shutil.copy2(
                REPO_ROOT / "tools" / "ci" / "check_agent_canon_latest.sh",
                repo / "tools" / "ci" / "check_agent_canon_latest.sh",
            )
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            submodule = repo / "vendor" / "agent-canon"
            subprocess.run(["git", "fetch", "origin", "main"], cwd=submodule, check=True)
            subprocess.run(["git", "checkout", "FETCH_HEAD"], cwd=submodule, check=True)
            (repo / "UNRELATED_ROOT_FILE").write_text("dirty parent\n", encoding="utf-8")

            result = subprocess.run(
                ["bash", "tools/ci/check_agent_canon_latest.sh"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AGENT_CANON_LATEST=fail", result.stdout)
            self.assertIn("AGENT_CANON_LATEST_ROUTE=submodule_update", result.stdout)
            self.assertIn(
                "AGENT_CANON_LATEST_SUBMODULE_WORKTREE_REMOTE_MATCH=yes",
                result.stdout,
            )
            self.assertIn("AGENT_CANON_LATEST_PARENT_PIN_PENDING=yes", result.stdout)
            self.assertIn("AGENT_CANON_LATEST_NEXT_ACTION=commit_updated_submodule_pin", result.stdout)

    def test_latest_check_fails_local_ahead_submodule_pin_as_proposal_required(self) -> None:
        """A parent pin ahead of shared canon main is proposal work, not latest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (repo / "tools" / "ci").mkdir()
            shutil.copy2(
                REPO_ROOT / "tools" / "ci" / "check_agent_canon_latest.sh",
                repo / "tools" / "ci" / "check_agent_canon_latest.sh",
            )
            submodule = repo / "vendor" / "agent-canon"
            (submodule / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "proposal marker",
                ],
                cwd=submodule,
                check=True,
            )
            subprocess.run(["git", "add", "vendor/agent-canon"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "pin local proposal"], cwd=repo, check=True)

            result = subprocess.run(
                ["bash", "tools/ci/check_agent_canon_latest.sh"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AGENT_CANON_LATEST=fail", result.stdout)
            self.assertIn("AGENT_CANON_LATEST_ROUTE=local_contains_remote", result.stdout)
            self.assertIn("AGENT_CANON_LATEST_PROPOSAL_COMMAND=bash tools/update_agent_canon.sh push-proposal", result.stdout)
            self.assertIn("proposal or AgentCanon PR", result.stderr)

    def test_apply_updates_submodule_pin_with_untracked_root_file(self) -> None:
        """Apply should update the gitlink without requiring unrelated root cleanup."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            (repo / "UNTRACKED_ROOT_FILE").write_text("root dirty\n", encoding="utf-8")

            apply = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "apply"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(apply.returncode, 0, apply.stderr)
            self.assertIn("agent_canon_latest=updating_submodule", apply.stdout)
            self.assertTrue((repo / "vendor" / "agent-canon" / "remote-marker.txt").is_file())
            status = subprocess.run(
                ["git", "status", "--short"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn("?? UNTRACKED_ROOT_FILE", status)

    def test_ensure_latest_does_not_commit_dirty_regular_active_contract(self) -> None:
        """Submodule updates should not sweep template-owned active contracts into sync commits."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            link_root = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "link-root"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(link_root.returncode, 0, link_root.stderr)
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "add generated root views"],
                cwd=repo,
                check=True,
            )
            (repo / "documents" / "README.md").write_text(
                "# Locally Edited Documents\n",
                encoding="utf-8",
            )
            (work_dir / "remote-marker.txt").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(["git", "commit", "-m", "advance remote"], cwd=work_dir, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            status = subprocess.run(
                ["git", "status", "--porcelain=v1", "--", "documents/README.md"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            committed_paths = subprocess.run(
                ["git", "show", "--name-only", "--format=", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_latest=updating_submodule", result.stdout)
            self.assertEqual(status, " M documents/README.md\n")
            self.assertNotIn("documents/README.md", committed_paths)

    def test_ensure_latest_refuses_unpinned_local_submodule_commits(self) -> None:
        """Ensure-latest should not overwrite local submodule commits silently."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            (submodule / "local-marker.txt").write_text("local\n", encoding="utf-8")
            subprocess.run(["git", "add", "local-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "local marker",
                ],
                cwd=submodule,
                check=True,
            )
            local_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            after_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=submodule,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "agent_canon_latest=local_submodule_worktree_differs_from_parent_pin",
                result.stdout,
            )
            self.assertIn("worktree HEAD differs from parent gitlink", result.stderr)
            self.assertEqual(after_head, local_head)

    def test_ensure_latest_uses_gitmodules_url_when_origin_differs(self) -> None:
        """Ensure-latest should follow .gitmodules instead of stale submodule origin."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_bare_repo, _old_work_dir = self.make_agent_canon_remote(root / "old")
            new_bare_repo, new_work_dir = self.make_agent_canon_remote(root / "new")
            repo = self.make_superproject(root, old_bare_repo)
            subprocess.run(
                [
                    "git",
                    "config",
                    "-f",
                    ".gitmodules",
                    "submodule.vendor/agent-canon.url",
                    str(new_bare_repo),
                ],
                cwd=repo,
                check=True,
            )
            (new_work_dir / "new-remote-marker.txt").write_text("new remote\n", encoding="utf-8")
            subprocess.run(["git", "add", "new-remote-marker.txt"], cwd=new_work_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "advance new remote"],
                cwd=new_work_dir,
                check=True,
            )
            subprocess.run(["git", "push", "origin", "main"], cwd=new_work_dir, check=True)

            result = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "ensure-latest"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("agent_canon_latest=updating_submodule", result.stdout)
            self.assertTrue((repo / "vendor" / "agent-canon" / "new-remote-marker.txt").is_file())

    def test_push_proposal_pushes_submodule_head_even_when_root_has_untracked_files(self) -> None:
        """Proposal push should use the submodule HEAD instead of subtree split."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            (submodule / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "proposal marker",
                ],
                cwd=submodule,
                check=True,
            )
            (repo / "UNTRACKED_ROOT_FILE").write_text("root dirty\n", encoding="utf-8")

            push = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "push-proposal", "canon-proposal/test"],
                cwd=repo,
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
                    "canon-proposal/test",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn("proposal-marker.txt", proposal_tree)

    def test_sync_push_refuses_default_branch_for_submodule(self) -> None:
        """Low-level sync push should not directly update AgentCanon main by default."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)

            push = subprocess.run(
                ["bash", "tools/sync_agent_canon.sh", "push", "main"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(push.returncode, 0)
            self.assertIn("submodule push to 'main' is forbidden", push.stderr)

    def test_review_submodule_reports_local_proposal_requirement(self) -> None:
        """Review should classify clean local submodule commits as proposal work."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, _work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            (submodule / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "proposal marker",
                ],
                cwd=submodule,
                check=True,
            )

            review = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "review-submodule"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(review.returncode, 0, review.stderr)
            self.assertIn("agent_canon_submodule_history_status=ahead_of_remote", review.stdout)
            self.assertIn("agent_canon_submodule_proposal_required=yes", review.stdout)
            self.assertIn("agent_canon_submodule_next=push_proposal", review.stdout)

    def test_align_main_accepts_tree_equivalent_merged_proposal(self) -> None:
        """Align-main may reset to main when a previous proposal tree is present there."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bare_repo, work_dir = self.make_agent_canon_remote(root)
            repo = self.make_superproject(root, bare_repo)
            submodule = repo / "vendor" / "agent-canon"
            (submodule / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=submodule, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Submodule Test",
                    "-c",
                    "user.email=submodule-test@example.invalid",
                    "commit",
                    "-m",
                    "proposal marker",
                ],
                cwd=submodule,
                check=True,
            )
            (work_dir / "proposal-marker.txt").write_text("proposal\n", encoding="utf-8")
            subprocess.run(["git", "add", "proposal-marker.txt"], cwd=work_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "merge proposal marker"],
                cwd=work_dir,
                check=True,
            )
            subprocess.run(["git", "push", "origin", "main"], cwd=work_dir, check=True)
            remote_sha = subprocess.run(
                ["git", "-C", str(work_dir), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            review = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "review-submodule"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            align = subprocess.run(
                ["bash", "tools/update_agent_canon.sh", "align-main"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            pinned_sha = subprocess.run(
                ["git", "rev-parse", "HEAD:vendor/agent-canon"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertEqual(review.returncode, 0, review.stderr)
            self.assertIn(
                "agent_canon_submodule_history_status=local_changes_already_in_remote",
                review.stdout,
            )
            self.assertIn("agent_canon_submodule_align_main_allowed=yes", review.stdout)
            self.assertEqual(align.returncode, 0, align.stderr)
            self.assertIn("agent_canon_align_main=updated_to_remote", align.stdout)
            self.assertEqual(pinned_sha, remote_sha)


if __name__ == "__main__":
    unittest.main()
