"""Tests for the gh-backed GitHub publish tool.

CI fresh-clone fixtures cover bootstrap/update behavior; they are not evidence
of ordinary source-branch publication.
"""

# @dependency-start
# contract test
# responsibility Tests GitHub publish tool command construction and failure boundaries.
# upstream implementation ../../tools/agent_tools/github_publish.py implements gh-backed publish.
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines publish workflow policy.
# @dependency-end

from __future__ import annotations

import argparse
import copy
import sys
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from tools.agent_tools import github_publish  # noqa: E402
from tools.agent_tools.update_lifecycle_contract import (  # noqa: E402
    materialize_gate_verdict,
    materialize_source_main_rebind_receipt,
    validate_pull_request_lifecycle,
    validate_pull_request_transition,
)  # noqa: E402
from tools.ci.check_agent_canon_pr import (  # noqa: E402
    GENERATED_COMPLETENESS_CHECK_IDS,
    materialize_generated_completeness_receipt,
)  # noqa: E402

CANDIDATE_SHA = "a" * 40
CANDIDATE_TREE = "b" * 40
BASE_SHA = "c" * 40
BASE_TREE = "d" * 40
MERGE_SHA = "1" * 40
MERGE_TREE = "2" * 40


class FakeRunner:
    """Small command runner fixture."""

    def __init__(self) -> None:
        """Initialize empty command fixtures."""
        self.commands: list[tuple[str, ...]] = []
        self.outputs: dict[tuple[str, ...], github_publish.CommandResult] = {}
        self.sequences: dict[tuple[str, ...], list[github_publish.CommandResult]] = {}

    def add(self, command: Sequence[str], stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        """Register a command result."""
        key = tuple(command)
        self.outputs[key] = github_publish.CommandResult(
            args=key,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def add_sequence(
        self,
        command: Sequence[str],
        results: Sequence[github_publish.CommandResult],
    ) -> None:
        """Register successive results for a command used before and after push."""
        self.sequences[tuple(command)] = list(results)

    def __call__(self, command: Sequence[str]) -> github_publish.CommandResult:
        """Return the registered result for a command."""
        key = tuple(command)
        self.commands.append(key)
        sequence = self.sequences.get(key)
        if sequence:
            result = sequence.pop(0)
            if not sequence:
                self.sequences.pop(key)
            return result
        if key not in self.outputs:
            return github_publish.CommandResult(
                args=key,
                returncode=99,
                stdout="",
                stderr=f"unexpected command: {key}",
            )
        return self.outputs[key]

    def add_publication_identity(self, branch: str = "topic", base: str = "main") -> None:
        """Register the exact candidate and base identities used by one lifecycle."""
        self.add(["git", "rev-parse", branch], stdout=CANDIDATE_SHA + "\n")
        self.add(
            ["git", "rev-parse", f"{CANDIDATE_SHA}^{{tree}}"],
            stdout=CANDIDATE_TREE + "\n",
        )
        self.add(["git", "rev-parse", f"origin/{base}"], stdout=BASE_SHA + "\n")
        self.add(
            ["git", "rev-parse", f"{BASE_SHA}^{{tree}}"],
            stdout=BASE_TREE + "\n",
        )

    def add_verified_actor(self) -> None:
        """Register one immutable authenticated GitHub actor readback."""
        self.add(
            ["gh", "api", "user", "--jq", "{id: .id, login: .login, name: .name}"],
            stdout='{"id":7,"login":"owner","name":"Owner"}',
        )

    def add_local_identity(
        self,
        *,
        branch: str = "topic",
        commit_sha: str = CANDIDATE_SHA,
        tree_sha: str = CANDIDATE_TREE,
    ) -> None:
        """Register the local branch, HEAD, and tree readback."""
        self.add(
            ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
            stdout=branch + "\n",
        )
        self.add(["git", "rev-parse", "HEAD"], stdout=commit_sha + "\n")
        self.add(
            ["git", "rev-parse", "HEAD^{tree}"],
            stdout=tree_sha + "\n",
        )


class GithubPublishTest(unittest.TestCase):
    """Exercise the GitHub publish command planner."""

    def test_failure_wrappers_keep_mutable_fields_and_exception_chaining(self) -> None:
        """Command and user failures expose typed fields without frozen dataclasses."""
        result = github_publish.CommandResult(("gh", "pr", "create"), 1, "", "failed")
        command_failure = github_publish.CommandFailure(result, "retry")
        self.assertEqual(command_failure.args, (result, "retry"))
        command_failure.next_action = "inspect"
        self.assertEqual(command_failure.next_action, "inspect")
        cause = RuntimeError("cause")
        try:
            raise command_failure from cause
        except github_publish.CommandFailure as raised:
            self.assertIs(raised.__cause__, cause)
            self.assertIsNotNone(raised.__traceback__)

        user_failure = github_publish.UserVisibleFailure("message", "next")
        self.assertEqual(user_failure.args, ("message", "next"))
        user_failure.message = "updated"
        self.assertEqual(user_failure.message, "updated")

    def lifecycle_fixture(
        self,
        *,
        permission_state: str = "verified_true",
        state: str | None = None,
    ) -> dict[str, object]:
        """Build one exact user lifecycle without a remote mutation."""
        runner = FakeRunner()
        runner.add_publication_identity()
        args = argparse.Namespace(
            user_task="typed PR lifecycle",
            title="Typed lifecycle",
            body_file=None,
            base="main",
            draft=False,
        )
        verification = github_publish.RemoteVerification(
            repo="owner/repo",
            remote="origin",
            remote_url="git@github.com:owner/repo.git",
            remote_slug="owner/repo",
            permission_state=permission_state,
            permission_evidence_id="evidence:" + "e" * 64,
            actor_id="viewer:test",
        )
        return github_publish.build_pull_request_lifecycle(
            args,
            runner,
            verification,
            "topic",
            state=state,
        )

    def publication_components(
        self,
        lifecycle: dict[str, object],
    ) -> tuple[
        dict[str, object], dict[str, object], list[dict[str, object]]
    ]:
        """Build exact reviewed-CAS and canonical G1/G2 fixtures."""
        binding = dict(lifecycle["binding"])
        head = lifecycle["head_identity"]
        base = lifecycle["base_identity"]
        assert isinstance(head, dict)
        assert isinstance(base, dict)
        rebind = materialize_source_main_rebind_receipt(
            binding=binding,
            old_base_identity={
                "remote": "origin",
                "ref": "refs/heads/main",
                "commit_sha": base["commit_sha"],
                "tree_sha": base["tree_sha"],
            },
            new_base_identity={
                "remote": "origin",
                "ref": "refs/heads/main",
                "commit_sha": base["commit_sha"],
                "tree_sha": base["tree_sha"],
            },
            origin_main_readback_evidence_ref="evidence:" + "7" * 64,
        )
        cas_evidence_ref = "evidence:" + "8" * 64
        cas_binding = dict(binding)
        cas_binding["evidence_ref"] = cas_evidence_ref
        cas_binding["evidence_digest"] = "sha256:" + "8" * 64
        cas = {
            "schema": "agent-canon.candidate-cas-receipt.v1",
            "cas_receipt_id": "cas:" + "9" * 64,
            "binding": cas_binding,
            "predecessor_evidence_id": binding["evidence_ref"],
            "rebind_receipt_evidence_id": rebind["rebind_receipt_id"],
            "candidate_identity": {
                "candidate_sha": head["commit_sha"],
                "tree_sha": head["tree_sha"],
            },
            "cas_base_identity": {
                "commit_sha": base["commit_sha"],
                "tree_sha": base["tree_sha"],
            },
            "cas_evidence_ref": cas_evidence_ref,
            "cas_stage": "cas",
        }
        g1 = materialize_gate_verdict(
            binding=binding,
            gate_id="G1",
            ordered_input_evidence_refs=[str(binding["evidence_ref"])],
            invariant="source_correctness",
            output_digest="sha256:" + "b" * 64,
            owner=str(
                PROJECT_ROOT / "tools"
                / "agent_tools"
                / "publication_integrator.py"
            )
            + "#resolve_publication_eligibility",
            verdict="pass",
        )
        g2 = materialize_generated_completeness_receipt(
            g1_gate=g1,
            candidate_sha=str(head["commit_sha"]),
            tree_sha=str(head["tree_sha"]),
            check_results=[
                {"check_id": check_id, "status": "pass"}
                for check_id in GENERATED_COMPLETENESS_CHECK_IDS
            ],
        )
        return rebind, cas, [g1, g2]

    def publication_packet(
        self,
        args: argparse.Namespace,
        runner: FakeRunner,
    ) -> dict[str, object]:
        """Materialize the sole packet accepted by a GitHub mutation."""
        verification = github_publish.verify_remote(
            runner,
            repo=args.repo,
            remote=args.remote,
        )
        branch = args.branch or "topic"
        lifecycle = github_publish.build_pull_request_lifecycle(
            args,
            runner,
            verification,
            branch,
        )
        rebind, cas, upstream = self.publication_components(lifecycle)
        return github_publish.materialize_github_publication_packet(
            lifecycle=lifecycle,
            candidate_cas_receipt=cas,
            source_main_rebind_receipt=rebind,
            upstream_gate_verdicts=upstream,
        )

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
            ["gh", "repo", "view", "owner/repo", "--json", "nameWithOwner,url,sshUrl,viewerPermission"],
            stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git","viewerPermission":"WRITE"}',
        )
        runner.add(["git", "remote", "get-url", "origin"], stdout="git@github.com:other/repo.git\n")
        runner.add(
            [
                "gh",
                "repo",
                "view",
                "other/repo",
                "--json",
                "nameWithOwner,url,sshUrl,viewerPermission,parent",
            ],
            stdout=(
                '{"nameWithOwner":"other/repo","url":"https://github.com/other/repo",'
                '"sshUrl":"git@github.com:other/repo.git","viewerPermission":"WRITE",'
                '"parent":null}'
            ),
        )

        with self.assertRaises(github_publish.UserVisibleFailure) as context:
            github_publish.verify_remote(runner, repo="owner/repo", remote="origin")

        self.assertEqual(
            context.exception.next_action,
            "materialize_the_typed_multiple_remotes_or_contributor_lifecycle",
        )

    def test_push_uses_sealed_sha_ref_and_exact_remote_readback(self) -> None:
        """Push preserves the sealed local identity and reads back the exact SHA."""
        runner = FakeRunner()
        runner.add(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], stdout="topic\n")
        runner.add(
            ["gh", "repo", "view", "owner/repo", "--json", "nameWithOwner,url,sshUrl,viewerPermission"],
            stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git","viewerPermission":"WRITE"}',
        )
        runner.add(["git", "remote", "get-url", "origin"], stdout="git@github.com:owner/repo.git\n")
        runner.add_verified_actor()
        runner.add_publication_identity()
        runner.add_local_identity()
        runner.add(["git", "status", "--short", "--untracked-files=all"], stdout=" M file.py\n")
        runner.add(
            [
                "git",
                "push",
                "-u",
                "origin",
                f"{CANDIDATE_SHA}:refs/heads/topic",
            ],
            stderr="pushed\n",
        )
        runner.add(
            ["git", "ls-remote", "origin", "refs/heads/topic"],
            stdout=f"{CANDIDATE_SHA}\trefs/heads/topic\n",
        )
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

        packet = self.publication_packet(args, runner)
        summary = github_publish.run(args, runner, publication_packet=packet)

        self.assertEqual(summary["status"], "ok")
        self.assertTrue(summary["worktree_dirty"])
        self.assertEqual(summary["local_commit_sha"], CANDIDATE_SHA)
        self.assertEqual(summary["local_tree_sha"], CANDIDATE_TREE)
        self.assertEqual(summary["remote_readback_sha"], CANDIDATE_SHA)
        self.assertIn(
            (
                "git",
                "push",
                "-u",
                "origin",
                f"{CANDIDATE_SHA}:refs/heads/topic",
            ),
            runner.commands,
        )
        self.assertIn(
            ("git", "ls-remote", "origin", "refs/heads/topic"),
            runner.commands,
        )

    def test_cli_push_is_transport_only_when_packet_file_is_absent(self) -> None:
        """Standalone push uses transport identity without fake publication gates."""
        runner = FakeRunner()
        runner.add(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], stdout="topic\n")
        runner.add(
            [
                "gh",
                "repo",
                "view",
                "owner/repo",
                "--json",
                "nameWithOwner,url,sshUrl,viewerPermission",
            ],
            stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git","viewerPermission":"WRITE"}',
        )
        runner.add(["git", "remote", "get-url", "origin"], stdout="git@github.com:owner/repo.git\n")
        runner.add_verified_actor()
        runner.add(["git", "status", "--short", "--untracked-files=all"], stdout="")
        runner.add_local_identity()
        runner.add(
            [
                "git",
                "push",
                "-u",
                "origin",
                f"{CANDIDATE_SHA}:refs/heads/topic",
            ],
            stderr="pushed\n",
        )
        runner.add(
            ["git", "ls-remote", "origin", "refs/heads/topic"],
            stdout=f"{CANDIDATE_SHA}\trefs/heads/topic\n",
        )
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
        self.assertEqual(summary["local_commit_sha"], CANDIDATE_SHA)
        self.assertEqual(summary["local_tree_sha"], CANDIDATE_TREE)
        self.assertEqual(summary["remote_readback_sha"], CANDIDATE_SHA)
        self.assertEqual(summary["publication_boundary"], "branch_transport_only")
        self.assertNotIn("pull_request_lifecycle", summary)
        self.assertNotIn("g3_gate", summary)
        self.assertIn(
            [
                "git",
                "push",
                "-u",
                "origin",
                f"{CANDIDATE_SHA}:refs/heads/topic",
            ],
            [list(command) for command in runner.commands],
        )

    def test_https_push_uses_process_local_gh_credential_helper(self) -> None:
        """HTTPS push uses gh credentials without changing Git config."""
        runner = FakeRunner()
        runner.add(["git", "status", "--short", "--untracked-files=all"], stdout="")
        runner.add_local_identity()
        push = [
            "git",
            "-c",
            "credential.helper=!gh auth git-credential",
            "push",
            "-u",
            "origin",
            f"{CANDIDATE_SHA}:refs/heads/topic",
        ]
        runner.add(push, stderr="pushed\n")
        runner.add(
            ["git", "ls-remote", "origin", "refs/heads/topic"],
            stdout=f"{CANDIDATE_SHA}\trefs/heads/topic\n",
        )
        args = argparse.Namespace(
            action="push",
            root=".",
            user_task="publish topic branch",
            allow_main=False,
            summary_out=None,
        )
        verification = github_publish.RemoteVerification(
            repo="owner/repo",
            remote="origin",
            remote_url="https://github.com/owner/repo.git",
            remote_slug="owner/repo",
        )

        summary = github_publish.perform_push(
            args,
            runner,
            verification,
            "topic",
        )

        self.assertEqual(summary["status"], "ok")
        self.assertIn(tuple(push), runner.commands)
        self.assertNotIn("--force-with-lease", push)

    def test_publish_pr_without_packet_reaches_body_validation(self) -> None:
        """PR mutation derives its lifecycle without requiring a packet file."""
        runner = FakeRunner()
        runner.add(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], stdout="topic\n")
        runner.add(
            [
                "gh",
                "repo",
                "view",
                "owner/repo",
                "--json",
                "nameWithOwner,url,sshUrl,viewerPermission",
            ],
            stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git","viewerPermission":"WRITE"}',
        )
        runner.add(["git", "remote", "get-url", "origin"], stdout="git@github.com:owner/repo.git\n")
        runner.add_verified_actor()
        runner.add_publication_identity()
        args = argparse.Namespace(
            action="publish-pr",
            root=".",
            user_task="publish topic branch",
            repo="owner/repo",
            remote="origin",
            branch=None,
            base="main",
            title="Title",
            body_file="missing-body.md",
            draft=False,
            update_existing=False,
            allow_main=False,
            summary_out=None,
        )

        with self.assertRaises(github_publish.UserVisibleFailure) as raised:
            github_publish.run(args, runner)

        self.assertIn("PR body file does not exist", raised.exception.message)
        self.assertFalse(any(command[1] == "push" for command in runner.commands))

    def test_push_rejects_local_candidate_mismatch_without_push_fallback(self) -> None:
        """A local HEAD/tree mismatch is typed and cannot trigger another route."""
        runner = FakeRunner()
        runner.add(
            [
                "gh",
                "repo",
                "view",
                "owner/repo",
                "--json",
                "nameWithOwner,url,sshUrl,viewerPermission",
            ],
            stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git","viewerPermission":"WRITE"}',
        )
        runner.add(["git", "remote", "get-url", "origin"], stdout="git@github.com:owner/repo.git\n")
        runner.add_verified_actor()
        runner.add_publication_identity()
        args = argparse.Namespace(
            action="push",
            root=".",
            user_task="publish topic branch",
            repo="owner/repo",
            remote="origin",
            branch="topic",
            allow_main=False,
            summary_out=None,
        )
        packet = self.publication_packet(args, runner)
        authority = github_publish.GithubPublicationAuthority.from_packet(packet)
        runner.add(["git", "status", "--short", "--untracked-files=all"], stdout="")
        runner.add_local_identity(commit_sha="e" * 40, tree_sha="f" * 40)
        verification = github_publish.RemoteVerification(
            repo="owner/repo",
            remote="origin",
            remote_url="git@github.com:owner/repo.git",
            remote_slug="owner/repo",
        )

        with self.assertRaises(github_publish.UserVisibleFailure) as raised:
            github_publish.perform_push(
                args,
                runner,
                verification,
                "topic",
                authority=authority,
            )

        self.assertIn("differs from the sealed lifecycle", raised.exception.message)
        self.assertFalse(any(command[1] == "push" for command in runner.commands))
        self.assertFalse(any(command[1] == "ls-remote" for command in runner.commands))

    def test_push_rejects_remote_readback_mismatch(self) -> None:
        """A different remote SHA is a typed failure after the one exact push."""
        runner = FakeRunner()
        runner.add_local_identity()
        runner.add(["git", "status", "--short", "--untracked-files=all"], stdout="")
        lifecycle = self.lifecycle_fixture()
        rebind, cas, upstream = self.publication_components(lifecycle)
        packet = github_publish.materialize_github_publication_packet(
            lifecycle=lifecycle,
            candidate_cas_receipt=cas,
            source_main_rebind_receipt=rebind,
            upstream_gate_verdicts=upstream,
        )
        authority = github_publish.GithubPublicationAuthority.from_packet(packet)
        args = argparse.Namespace(
            action="push",
            root=".",
            user_task="publish topic branch",
            repo="owner/repo",
            remote="origin",
            branch="topic",
            allow_main=False,
            summary_out=None,
        )
        verification = github_publish.RemoteVerification(
            repo="owner/repo",
            remote="origin",
            remote_url="git@github.com:owner/repo.git",
            remote_slug="owner/repo",
        )
        runner.add(
            [
                "git",
                "push",
                "-u",
                "origin",
                f"{CANDIDATE_SHA}:refs/heads/topic",
            ],
            stderr="pushed\n",
        )
        runner.add(
            ["git", "ls-remote", "origin", "refs/heads/topic"],
            stdout=f"{'e' * 40}\trefs/heads/topic\n",
        )

        with self.assertRaises(github_publish.UserVisibleFailure) as raised:
            github_publish.perform_push(
                args,
                runner,
                verification,
                "topic",
                authority=authority,
            )

        self.assertIn("readback SHA differs", raised.exception.message)
        self.assertIn(
            ("git", "ls-remote", "origin", "refs/heads/topic"),
            runner.commands,
        )

    def test_push_rejects_branch_ref_mismatch_without_push(self) -> None:
        """The selected branch must equal the sealed lifecycle ref."""
        runner = FakeRunner()
        runner.add_publication_identity()
        args = argparse.Namespace(
            action="push",
            root=".",
            user_task="publish topic branch",
            repo="owner/repo",
            remote="origin",
            branch="topic",
            allow_main=False,
            summary_out=None,
        )
        lifecycle = self.lifecycle_fixture()
        rebind, cas, upstream = self.publication_components(lifecycle)
        packet = github_publish.materialize_github_publication_packet(
            lifecycle=lifecycle,
            candidate_cas_receipt=cas,
            source_main_rebind_receipt=rebind,
            upstream_gate_verdicts=upstream,
        )
        authority = github_publish.GithubPublicationAuthority.from_packet(packet)
        verification = github_publish.RemoteVerification(
            repo="owner/repo",
            remote="origin",
            remote_url="git@github.com:owner/repo.git",
            remote_slug="owner/repo",
        )

        with self.assertRaises(github_publish.UserVisibleFailure) as raised:
            github_publish.perform_push(
                args,
                runner,
                verification,
                "other",
                authority=authority,
            )

        self.assertIn("sealed lifecycle head identity", raised.exception.message)
        self.assertFalse(any(command[1] == "push" for command in runner.commands))

    def test_push_rejects_post_push_local_identity_change(self) -> None:
        """A local branch/HEAD/tree change across push is a typed failure."""
        runner = FakeRunner()
        runner.add_publication_identity()
        lifecycle = self.lifecycle_fixture()
        rebind, cas, upstream = self.publication_components(lifecycle)
        packet = github_publish.materialize_github_publication_packet(
            lifecycle=lifecycle,
            candidate_cas_receipt=cas,
            source_main_rebind_receipt=rebind,
            upstream_gate_verdicts=upstream,
        )
        authority = github_publish.GithubPublicationAuthority.from_packet(packet)
        args = argparse.Namespace(
            action="push",
            root=".",
            user_task="publish topic branch",
            repo="owner/repo",
            remote="origin",
            branch="topic",
            allow_main=False,
            summary_out=None,
        )
        verification = github_publish.RemoteVerification(
            repo="owner/repo",
            remote="origin",
            remote_url="git@github.com:owner/repo.git",
            remote_slug="owner/repo",
        )
        runner.add(["git", "status", "--short", "--untracked-files=all"], stdout="")
        runner.add_sequence(
            ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
            [
                github_publish.CommandResult(
                    args=("git", "symbolic-ref", "--quiet", "--short", "HEAD"),
                    returncode=0,
                    stdout="topic\n",
                    stderr="",
                ),
                github_publish.CommandResult(
                    args=("git", "symbolic-ref", "--quiet", "--short", "HEAD"),
                    returncode=0,
                    stdout="other\n",
                    stderr="",
                ),
            ],
        )
        runner.add_sequence(
            ["git", "rev-parse", "HEAD"],
            [
                github_publish.CommandResult(
                    args=("git", "rev-parse", "HEAD"),
                    returncode=0,
                    stdout=CANDIDATE_SHA + "\n",
                    stderr="",
                ),
                github_publish.CommandResult(
                    args=("git", "rev-parse", "HEAD"),
                    returncode=0,
                    stdout=CANDIDATE_SHA + "\n",
                    stderr="",
                ),
            ],
        )
        runner.add_sequence(
            ["git", "rev-parse", "HEAD^{tree}"],
            [
                github_publish.CommandResult(
                    args=("git", "rev-parse", "HEAD^{tree}"),
                    returncode=0,
                    stdout=CANDIDATE_TREE + "\n",
                    stderr="",
                ),
                github_publish.CommandResult(
                    args=("git", "rev-parse", "HEAD^{tree}"),
                    returncode=0,
                    stdout=CANDIDATE_TREE + "\n",
                    stderr="",
                ),
            ],
        )
        runner.add(
            [
                "git",
                "push",
                "-u",
                "origin",
                f"{CANDIDATE_SHA}:refs/heads/topic",
            ],
            stderr="pushed\n",
        )
        runner.add(
            ["git", "ls-remote", "origin", "refs/heads/topic"],
            stdout=f"{CANDIDATE_SHA}\trefs/heads/topic\n",
        )

        with self.assertRaises(github_publish.UserVisibleFailure) as raised:
            github_publish.perform_push(
                args,
                runner,
                verification,
                "topic",
                authority=authority,
            )

        self.assertIn("changed across the push", raised.exception.message)

    def test_pr_create_uses_gh_after_branch_pr_check(self) -> None:
        """PR creation should use gh with explicit repo, base, head, and body file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            body = Path(temp_dir) / "body.md"
            body.write_text("body\n", encoding="utf-8")
            runner = FakeRunner()
            runner.add(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], stdout="topic\n")
            runner.add(
                ["gh", "repo", "view", "owner/repo", "--json", "nameWithOwner,url,sshUrl,viewerPermission"],
                stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git","viewerPermission":"WRITE"}',
            )
            runner.add(["git", "remote", "get-url", "origin"], stdout="https://github.com/owner/repo.git\n")
            runner.add_verified_actor()
            runner.add_publication_identity()
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
            runner.add(
                [
                    "gh",
                    "pr",
                    "view",
                    "topic",
                    "--repo",
                    "owner/repo",
                    "--json",
                    "number,url,state,isDraft,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,reviewDecision,reviews,mergeCommit",
                ],
                stdout=(
                    '{"number":1,"url":"https://github.com/owner/repo/pull/1",'
                    f'"state":"OPEN","isDraft":false,"baseRefName":"main","baseRefOid":"{BASE_SHA}",'
                    f'"headRefName":"topic","headRefOid":"{CANDIDATE_SHA}",'
                    '"headRepository":{"nameWithOwner":"owner/repo"},'
                    '"reviewDecision":"","reviews":[],"mergeCommit":null}'
                ),
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
        self.assertNotIn("g3_gate", summary)

    def test_pr_update_without_packet_uses_direct_lifecycle(self) -> None:
        """PR update accepts exact local/base evidence without G1/G2/G3."""
        with tempfile.TemporaryDirectory() as temp_dir:
            body = Path(temp_dir) / "body.md"
            body.write_text("updated body\n", encoding="utf-8")
            runner = FakeRunner()
            runner.add(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], stdout="topic\n")
            runner.add(
                [
                    "gh",
                    "repo",
                    "view",
                    "owner/repo",
                    "--json",
                    "nameWithOwner,url,sshUrl,viewerPermission",
                ],
                stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git","viewerPermission":"WRITE"}',
            )
            runner.add(["git", "remote", "get-url", "origin"], stdout="git@github.com:owner/repo.git\n")
            runner.add_verified_actor()
            runner.add_publication_identity()
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
                stdout='[{"number":3,"url":"https://github.com/owner/repo/pull/3","title":"Old","headRefName":"topic","baseRefName":"main"}]',
            )
            runner.add(
                [
                    "gh",
                    "pr",
                    "edit",
                    "3",
                    "--repo",
                    "owner/repo",
                    "--title",
                    "Title",
                    "--body-file",
                    str(body),
                ],
                stdout="updated\n",
            )
            runner.add(
                [
                    "gh",
                    "pr",
                    "view",
                    "3",
                    "--repo",
                    "owner/repo",
                    "--json",
                    "number,url,state,isDraft,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,reviewDecision,reviews,mergeCommit",
                ],
                stdout=(
                    '{"number":3,"url":"https://github.com/owner/repo/pull/3",'
                    f'"state":"OPEN","isDraft":false,"baseRefName":"main","baseRefOid":"{BASE_SHA}",'
                    f'"headRefName":"topic","headRefOid":"{CANDIDATE_SHA}",'
                    '"headRepository":{"nameWithOwner":"owner/repo"},'
                    '"reviewDecision":"","reviews":[],"mergeCommit":null}'
                ),
            )
            args = argparse.Namespace(
                action="pr",
                root=".",
                user_task="update PR",
                repo="owner/repo",
                remote="origin",
                branch=None,
                base="main",
                title="Title",
                body_file=str(body),
                draft=False,
                update_existing=True,
                summary_out=None,
            )

            summary = github_publish.run(args, runner)

        self.assertEqual(summary["action"], "pr-update")
        self.assertNotIn("g3_gate", summary)

    def test_publish_pr_without_packet_pushes_and_creates_pr(self) -> None:
        """publish-pr derives lifecycle directly and performs one normal push."""
        with tempfile.TemporaryDirectory() as temp_dir:
            body = Path(temp_dir) / "body.md"
            body.write_text("body\n", encoding="utf-8")
            runner = FakeRunner()
            runner.add(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], stdout="topic\n")
            runner.add(
                [
                    "gh",
                    "repo",
                    "view",
                    "owner/repo",
                    "--json",
                    "nameWithOwner,url,sshUrl,viewerPermission",
                ],
                stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git","viewerPermission":"WRITE"}',
            )
            runner.add(["git", "remote", "get-url", "origin"], stdout="git@github.com:owner/repo.git\n")
            runner.add_verified_actor()
            runner.add_publication_identity()
            runner.add(["git", "status", "--short", "--untracked-files=all"], stdout="")
            runner.add_local_identity()
            runner.add(
                ["git", "push", "-u", "origin", f"{CANDIDATE_SHA}:refs/heads/topic"],
                stderr="pushed\n",
            )
            runner.add(
                ["git", "ls-remote", "origin", "refs/heads/topic"],
                stdout=f"{CANDIDATE_SHA}\trefs/heads/topic\n",
            )
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
                stdout="https://github.com/owner/repo/pull/4\n",
            )
            runner.add(
                [
                    "gh",
                    "pr",
                    "view",
                    "topic",
                    "--repo",
                    "owner/repo",
                    "--json",
                    "number,url,state,isDraft,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,reviewDecision,reviews,mergeCommit",
                ],
                stdout=(
                    '{"number":4,"url":"https://github.com/owner/repo/pull/4",'
                    f'"state":"OPEN","isDraft":false,"baseRefName":"main","baseRefOid":"{BASE_SHA}",'
                    f'"headRefName":"topic","headRefOid":"{CANDIDATE_SHA}",'
                    '"headRepository":{"nameWithOwner":"owner/repo"},'
                    '"reviewDecision":"","reviews":[],"mergeCommit":null}'
                ),
            )
            args = argparse.Namespace(
                action="publish-pr",
                root=".",
                user_task="publish PR",
                repo="owner/repo",
                remote="origin",
                branch=None,
                base="main",
                title="Title",
                body_file=str(body),
                draft=False,
                update_existing=False,
                allow_main=False,
                summary_out=None,
            )

            summary = github_publish.run(args, runner)

        self.assertEqual(summary["action"], "publish-pr")
        self.assertEqual(summary["push"]["publication_boundary"], "verified_lifecycle")
        self.assertNotIn("g3_gate", summary)

    def test_checks_reports_pending_without_failure(self) -> None:
        """Pending GitHub checks should be a state, not a tool failure."""
        runner = FakeRunner()
        runner.add(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], stdout="topic\n")
        runner.add(
            ["gh", "repo", "view", "owner/repo", "--json", "nameWithOwner,url,sshUrl,viewerPermission"],
            stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git","viewerPermission":"WRITE"}',
        )
        runner.add(["git", "remote", "get-url", "origin"], stdout="git@github.com:owner/repo.git\n")
        runner.add_verified_actor()
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
        self.assertNotIn("pull_request_lifecycle", summary)
        self.assertNotIn("g3_gate", summary)

    def test_mutation_adapter_rejects_unsealed_publication_authority(self) -> None:
        """Direct mutation calls cannot fabricate lifecycle or G3 authority."""
        args = argparse.Namespace(allow_main=False, user_task="reject forged push")
        verification = github_publish.RemoteVerification(
            repo="owner/repo",
            remote="origin",
            remote_url="git@github.com:owner/repo.git",
            remote_slug="owner/repo",
        )
        forged = github_publish.GithubPublicationAuthority()
        runner = FakeRunner()

        with self.assertRaises(github_publish.UserVisibleFailure) as raised:
            github_publish.perform_push(
                args,
                runner,
                verification,
                "topic",
                authority=forged,
            )

        self.assertIn("owner-materialized", raised.exception.message)
        self.assertEqual(runner.commands, [])

    def test_post_publication_checks_consume_same_binding_g5(self) -> None:
        """Post-publication checks retain a passing exact-identity G5 receipt."""
        lifecycle = self.lifecycle_fixture()
        rebind, cas, upstream = self.publication_components(lifecycle)
        packet = github_publish.materialize_github_publication_packet(
            lifecycle=lifecycle,
            candidate_cas_receipt=cas,
            source_main_rebind_receipt=rebind,
            upstream_gate_verdicts=upstream,
        )
        publication = github_publish.GithubPublicationAuthority.from_packet(packet)
        g3 = packet["g3_gate"]
        assert isinstance(g3, dict)
        g5 = materialize_gate_verdict(
            binding=lifecycle["binding"],
            gate_id="G5",
            ordered_input_evidence_refs=[str(g3["binding"]["evidence_ref"])],
            invariant="remote_publication_readback",
            output_digest="sha256:" + "5" * 64,
            owner=str(
                PROJECT_ROOT / "tools" / "agent_tools" / "publication_integrator.py"
            )
            + "#integrate_publication",
            verdict="pass",
        )
        authority = github_publish.GithubPostPublicationChecksAuthority.from_publication(
            publication, g5
        )
        runner = FakeRunner()
        runner.add(
            ["gh", "pr", "checks", "7", "--repo", "owner/repo", "--watch=false"],
            stdout="all\tpass\t0\turl\t\n",
        )
        args = argparse.Namespace(
            user_task="post-publication checks",
            pr="7",
            watch=False,
        )
        verification = github_publish.RemoteVerification(
            repo="owner/repo",
            remote="origin",
            remote_url="git@github.com:owner/repo.git",
            remote_slug="owner/repo",
        )

        result = github_publish.perform_checks(
            args,
            runner,
            verification,
            "topic",
            authority=authority,
        )

        self.assertEqual(result["g5_gate"], g5)

    def test_unknown_push_permission_is_a_typed_refusal(self) -> None:
        """GitHub mutation cannot infer authority from repository topology."""
        lifecycle = self.lifecycle_fixture(
            permission_state="unknown",
            state="permission_unknown",
        )

        rebind, cas, upstream = self.publication_components(lifecycle)
        with self.assertRaises(github_publish.UserVisibleFailure) as raised:
            github_publish.materialize_pr_identity_gate(
                lifecycle, cas, rebind, upstream
            )

        self.assertIn("permission", raised.exception.message)

    def test_publication_packet_rejects_cas_base_not_owned_by_rebind(self) -> None:
        """G3 cannot accept a CAS base independent of SourceMainRebindReceipt."""
        lifecycle = self.lifecycle_fixture()
        rebind, cas, upstream = self.publication_components(lifecycle)
        moved_rebind = copy.deepcopy(rebind)
        moved_base = moved_rebind["new_base_identity"]
        moved_readback = moved_rebind["origin_main_readback"]
        assert isinstance(moved_base, dict)
        assert isinstance(moved_readback, dict)
        moved_base["commit_sha"] = "f" * 40
        moved_readback["commit_sha"] = "f" * 40

        with self.assertRaises(ValueError) as raised:
            github_publish.materialize_github_publication_packet(
                lifecycle=lifecycle,
                candidate_cas_receipt=cas,
                source_main_rebind_receipt=moved_rebind,
                upstream_gate_verdicts=upstream,
            )

        self.assertIn("rebind_cas_base_identity_mismatch", str(raised.exception))

    def test_publication_packet_carries_predecessor_graph_materialization(self) -> None:
        """G3 binds the predecessor graph projection to the CAS base identity."""
        lifecycle = self.lifecycle_fixture()
        rebind, cas, upstream = self.publication_components(lifecycle)
        predecessor = {
            "schema": "waterfall.active_design_packet_materialization.v1",
            "packet_sha256": "e" * 64,
            "predecessor_source_oid": BASE_SHA,
            "source_results": [{"declared_ref": "repo:agents/TASK_WORKFLOWS.md"}],
            "dependency_results": [{"declared_ref": "header:upstream:design:repo:a->repo:b"}],
        }

        packet = github_publish.materialize_github_publication_packet(
            lifecycle=lifecycle,
            candidate_cas_receipt=cas,
            source_main_rebind_receipt=rebind,
            upstream_gate_verdicts=upstream,
            predecessor_graph_materialization=predecessor,
        )

        self.assertEqual(packet["predecessor_graph_materialization"], predecessor)
        validated = github_publish.validate_github_publication_packet(packet)
        self.assertEqual(
            validated["predecessor_graph_materialization"],
            predecessor,
        )
        mismatched = copy.deepcopy(predecessor)
        mismatched["predecessor_source_oid"] = "f" * 40
        with self.assertRaises(github_publish.UserVisibleFailure) as raised:
            github_publish.materialize_github_publication_packet(
                lifecycle=lifecycle,
                candidate_cas_receipt=cas,
                source_main_rebind_receipt=rebind,
                upstream_gate_verdicts=upstream,
                predecessor_graph_materialization=mismatched,
            )
        self.assertIn("does not match the CAS base", raised.exception.message)

    def test_reviewable_state_requires_verified_permission(self) -> None:
        """Review/merge-authorizing states cannot retain false permission."""
        with self.assertRaises(ValueError) as raised:
            self.lifecycle_fixture(
                permission_state="verified_false",
                state="external_review",
            )

        self.assertIn("verified_permission_required", str(raised.exception))

    def test_user_fork_and_contributor_topologies_preserve_typed_identity(self) -> None:
        """All three discriminated PR kinds retain Essence, reviews, and diff state."""
        user = self.lifecycle_fixture()
        args = argparse.Namespace(
            user_task="typed PR lifecycle",
            title="Typed lifecycle",
            body_file=None,
            base="main",
            draft=False,
        )
        runner = FakeRunner()
        runner.add_publication_identity()
        runner.add(
            [
                "gh",
                "api",
                "repos/owner/repo/commits/main",
                "--jq",
                "{commit_sha: .sha, tree_sha: .commit.tree.sha}",
            ],
            stdout=(
                f'{{"commit_sha":"{BASE_SHA}","tree_sha":"{BASE_TREE}"}}'
            ),
        )
        fork = github_publish.build_pull_request_lifecycle(
            args,
            runner,
            github_publish.RemoteVerification(
                repo="owner/repo",
                remote="origin",
                remote_url="git@github.com:fork-owner/repo.git",
                remote_slug="fork-owner/repo",
                topology_kind="fork",
                head_repo="fork-owner/repo",
                fork_parent_repo="owner/repo",
                permission_state="verified_true",
                permission_evidence_id="evidence:" + "e" * 64,
                actor_id="github-user:7",
                actor_display_name="Fork Owner",
            ),
            "topic",
        )
        contributor_diff = {
            "commit_sha": CANDIDATE_SHA,
            "tree_sha": CANDIDATE_TREE,
            "diff_sha256": "sha256:" + "f" * 64,
        }
        contributor = github_publish.build_pull_request_lifecycle(
            args,
            runner,
            github_publish.RemoteVerification(
                repo="owner/repo",
                remote="origin",
                remote_url="git@github.com:contributor/repo.git",
                remote_slug="contributor/repo",
                topology_kind="contributor",
                head_repo="contributor/repo",
                permission_state="verified_true",
                permission_evidence_id="evidence:" + "d" * 64,
                actor_id="github-user:7",
                actor_display_name="Owner",
            ),
            "topic",
            contributor_identity={
                "actor_id": "contributor:test",
                "display_name": "Contributor",
            },
            contributor_diff=contributor_diff,
            state="external_review",
        )

        checked = [
            validate_pull_request_lifecycle(value)
            for value in (user, fork, contributor)
        ]
        self.assertEqual([item["kind"] for item in checked], ["user", "fork", "contributor"])
        self.assertEqual(
            checked[2]["contributor_diff"], contributor_diff
        )
        self.assertEqual(
            [item["pr_essence"] for item in checked],
            [user["pr_essence"], user["pr_essence"], user["pr_essence"]],
        )

    def test_typed_pr_state_machine_handles_remote_and_review_states(self) -> None:
        """Draft/review/closed/multi-remote/conflict states use one transition graph."""
        ready = self.lifecycle_fixture()
        draft = self.lifecycle_fixture(state="draft")
        self.assertEqual(
            validate_pull_request_transition(draft, ready)["state"],
            "ready",
        )
        for state in (
            "changes_requested",
            "external_review",
            "merged",
            "closed_head",
            "multiple_remotes",
        ):
            successor = copy.deepcopy(ready)
            successor["state"] = state
            with self.subTest(state=state):
                self.assertEqual(
                    validate_pull_request_transition(ready, successor)["state"],
                    state,
                )
        conflict = copy.deepcopy(ready)
        conflict["state"] = "conflict_successor"
        conflict["successor_ref"] = "pr-successor:" + "9" * 64
        self.assertEqual(
            validate_pull_request_transition(ready, conflict)["state"],
            "conflict_successor",
        )

        unknown = self.lifecycle_fixture(
            permission_state="unknown",
            state="permission_unknown",
        )
        denied = self.lifecycle_fixture(
            permission_state="verified_false",
            state="permission_denied",
        )
        self.assertEqual(
            validate_pull_request_transition(unknown, denied)["state"],
            "permission_denied",
        )

    def test_readback_keeps_essence_and_appends_external_review(self) -> None:
        """Remote changes-requested evidence cannot replace the original PR Essence."""
        lifecycle = self.lifecycle_fixture()
        updated = github_publish.lifecycle_with_pr_readback(
            lifecycle,
            {
                "number": 7,
                "state": "OPEN",
                "isDraft": False,
                "baseRefName": "main",
                "baseRefOid": BASE_SHA,
                "headRefName": "topic",
                "headRefOid": CANDIDATE_SHA,
                "headRepository": {"nameWithOwner": "owner/repo"},
                "reviewDecision": "CHANGES_REQUESTED",
                "reviews": [
                    {
                        "id": "review-7",
                        "author": {"login": "external-reviewer"},
                        "state": "CHANGES_REQUESTED",
                        "body": "please revise",
                    }
                ],
            },
        )

        self.assertEqual(updated["state"], "changes_requested")
        self.assertEqual(updated["pr_essence"], lifecycle["pr_essence"])
        self.assertEqual(updated["reviews"][0]["reviewer_id"], "external-reviewer")

    def test_merged_publication_uses_authoritative_pr_and_merge_tree_readback(self) -> None:
        """Merged identity comes from gh PR/API readback, not caller merge fields."""
        lifecycle = self.lifecycle_fixture()
        _rebind, cas, _upstream = self.publication_components(lifecycle)
        runner = FakeRunner()
        runner.add(
            [
                "gh",
                "pr",
                "view",
                "7",
                "--repo",
                "owner/repo",
                "--json",
                "number,url,state,isDraft,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,reviewDecision,reviews,mergeCommit",
            ],
            stdout=(
                '{"number":7,"url":"https://github.com/owner/repo/pull/7",'
                f'"state":"MERGED","isDraft":false,"baseRefName":"main",'
                f'"baseRefOid":"{MERGE_SHA}","headRefName":"topic",'
                f'"headRefOid":"{CANDIDATE_SHA}",'
                '"headRepository":{"nameWithOwner":"owner/repo"},'
                f'"reviewDecision":"APPROVED","reviews":[],"mergeCommit":{{"oid":"{MERGE_SHA}"}}}}'
            ),
        )
        runner.add(
            [
                "gh",
                "api",
                f"repos/owner/repo/git/commits/{MERGE_SHA}",
                "--jq",
                "{commit_sha: .sha, tree_sha: .tree.sha, parents: [.parents[].sha]}",
            ],
            stdout=(
                f'{{"commit_sha":"{MERGE_SHA}","tree_sha":"{MERGE_TREE}",'
                f'"parents":["{BASE_SHA}"]}}'
            ),
        )
        runner.add(
            [
                "gh",
                "api",
                f"repos/owner/repo/git/commits/{BASE_SHA}",
                "--jq",
                "{commit_sha: .sha, tree_sha: .tree.sha}",
            ],
            stdout=f'{{"commit_sha":"{BASE_SHA}","tree_sha":"{BASE_TREE}"}}',
        )

        result = github_publish.authoritative_publication_readback(
            runner,
            repo="owner/repo",
            selector="7",
            candidate_cas_receipt=cas,
            pull_request_lifecycle=lifecycle,
        )

        receipt = result["publication_readback_receipt"]
        assert isinstance(receipt, dict)
        identity = receipt["pr_identity"]
        assert isinstance(identity, dict)
        self.assertEqual(identity["head_sha"], CANDIDATE_SHA)
        self.assertEqual(identity["post_merge_base_ref_sha"], MERGE_SHA)
        self.assertEqual(identity["merge_cas_base_sha"], BASE_SHA)
        self.assertEqual(identity["merge_cas_base_tree_sha"], BASE_TREE)
        self.assertEqual(identity["merge_commit_sha"], MERGE_SHA)
        self.assertEqual(identity["merge_tree_sha"], MERGE_TREE)


if __name__ == "__main__":
    unittest.main()
