"""Tests for the gh-backed GitHub publish tool."""

# @dependency-start
# contract test
# responsibility Tests GitHub publish tool command construction and failure boundaries.
# upstream implementation ../../tools/agent_tools/github_publish.py implements gh-backed publish.
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines publish workflow policy.
# @dependency-end

from __future__ import annotations

import argparse
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from tools.agent_tools import github_publish


class FakeRunner:
    """Small command runner fixture."""

    def __init__(self) -> None:
        """Initialize empty command fixtures."""
        self.commands: list[tuple[str, ...]] = []
        self.outputs: dict[tuple[str, ...], github_publish.CommandResult] = {}

    def add(self, command: Sequence[str], stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        """Register a command result."""
        key = tuple(command)
        self.outputs[key] = github_publish.CommandResult(
            args=key,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def __call__(self, command: Sequence[str]) -> github_publish.CommandResult:
        """Return the registered result for a command."""
        key = tuple(command)
        self.commands.append(key)
        if key not in self.outputs:
            return github_publish.CommandResult(
                args=key,
                returncode=99,
                stdout="",
                stderr=f"unexpected command: {key}",
            )
        return self.outputs[key]


class GithubPublishTest(unittest.TestCase):
    """Exercise the GitHub publish command planner."""

    def test_normalized_repo_slug_accepts_common_github_urls(self) -> None:
        """Remote URL parsing should support ssh, https, and owner/name."""
        self.assertEqual(
            github_publish.normalized_repo_slug("git@github.com:owner/repo.git"),
            "owner/repo",
        )
        self.assertEqual(
            github_publish.normalized_repo_slug("https://github.com/owner/repo.git"),
            "owner/repo",
        )
        self.assertEqual(
            github_publish.normalized_repo_slug("ssh://git@github.com/owner/repo.git"),
            "owner/repo",
        )
        self.assertEqual(github_publish.normalized_repo_slug("owner/repo"), "owner/repo")

    def test_push_requires_user_task_argument(self) -> None:
        """The CLI should not publish without a visible user task."""
        parser = github_publish.build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["push"])

    def test_verify_remote_rejects_repo_mismatch_when_verified_remote_required(self) -> None:
        """Mismatched gh repo and origin must fail instead of trying another push route."""
        runner = FakeRunner()
        runner.add(
            ["gh", "repo", "view", "owner/repo", "--json", "nameWithOwner,url,sshUrl"],
            stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git"}',
        )
        runner.add(["git", "remote", "get-url", "origin"], stdout="git@github.com:other/repo.git\n")

        with self.assertRaises(github_publish.UserVisibleFailure) as context:
            github_publish.verify_remote(runner, repo="owner/repo", remote="origin")

        self.assertIn("verified_remote_required", context.exception.next_action)

    def test_push_allows_dirty_worktree_and_uses_verified_origin(self) -> None:
        """Dirty worktree is warning evidence, not a push blocker."""
        runner = FakeRunner()
        runner.add(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], stdout="topic\n")
        runner.add(
            ["gh", "repo", "view", "owner/repo", "--json", "nameWithOwner,url,sshUrl"],
            stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git"}',
        )
        runner.add(["git", "remote", "get-url", "origin"], stdout="git@github.com:owner/repo.git\n")
        runner.add(["git", "status", "--short", "--untracked-files=all"], stdout=" M file.py\n")
        runner.add(["git", "push", "-u", "origin", "topic"], stderr="pushed\n")
        args = argparse.Namespace(
            action="push",
            root=".",
            user_task="publish topic branch",
            repo="owner/repo",
            remote="origin",
            branch=None,
            allow_main=False,
            summary_out=None,
        )

        summary = github_publish.run(args, runner)

        self.assertEqual(summary["status"], "ok")
        self.assertTrue(summary["worktree_dirty"])
        self.assertIn(("git", "push", "-u", "origin", "topic"), runner.commands)

    def test_pr_create_uses_gh_after_branch_pr_check(self) -> None:
        """PR creation should use gh with explicit repo, base, head, and body file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            body = Path(temp_dir) / "body.md"
            body.write_text("body\n", encoding="utf-8")
            runner = FakeRunner()
            runner.add(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], stdout="topic\n")
            runner.add(
                ["gh", "repo", "view", "owner/repo", "--json", "nameWithOwner,url,sshUrl"],
                stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git"}',
            )
            runner.add(["git", "remote", "get-url", "origin"], stdout="https://github.com/owner/repo.git\n")
            runner.add(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    "owner/repo",
                    "--head",
                    "topic",
                    "--state",
                    "open",
                    "--json",
                    "number,url,title,headRefName,baseRefName",
                ],
                stdout="[]",
            )
            runner.add(
                [
                    "gh",
                    "pr",
                    "create",
                    "--repo",
                    "owner/repo",
                    "--base",
                    "main",
                    "--head",
                    "topic",
                    "--title",
                    "Title",
                    "--body-file",
                    str(body),
                ],
                stdout="https://github.com/owner/repo/pull/1\n",
            )
            args = argparse.Namespace(
                action="pr",
                root=".",
                user_task="open PR",
                repo="owner/repo",
                remote="origin",
                branch=None,
                base="main",
                title="Title",
                body_file=str(body),
                draft=False,
                update_existing=False,
                summary_out=None,
            )

            summary = github_publish.run(args, runner)

        self.assertEqual(summary["action"], "pr-create")
        self.assertEqual(summary["pr_url"], "https://github.com/owner/repo/pull/1")

    def test_checks_reports_pending_without_failure(self) -> None:
        """Pending GitHub checks should be a state, not a tool failure."""
        runner = FakeRunner()
        runner.add(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], stdout="topic\n")
        runner.add(
            ["gh", "repo", "view", "owner/repo", "--json", "nameWithOwner,url,sshUrl"],
            stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git"}',
        )
        runner.add(["git", "remote", "get-url", "origin"], stdout="git@github.com:owner/repo.git\n")
        runner.add(
            ["gh", "pr", "checks", "1", "--repo", "owner/repo", "--watch=false"],
            stdout="static-gates\tpending\t0\turl\t\n",
            returncode=8,
        )
        args = argparse.Namespace(
            action="checks",
            root=".",
            user_task="inspect checks",
            repo="owner/repo",
            remote="origin",
            branch=None,
            pr="1",
            watch=False,
            summary_out=None,
        )

        summary = github_publish.run(args, runner)

        self.assertEqual(summary["status"], "pending")
        self.assertEqual(summary["next_action"], "wait_for_github_checks_or_rerun_with_--watch")


if __name__ == "__main__":
    unittest.main()
