"""Tests for the gh-backed GitHub publish tool."""

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

from tools.agent_tools import github_publish
from tools.agent_tools.update_lifecycle_contract import (
    materialize_gate_verdict,
    materialize_source_main_rebind_receipt,
    validate_pull_request_lifecycle,
    validate_pull_request_transition,
)
from tools.ci.check_agent_canon_pr import (
    GENERATED_COMPLETENESS_CHECK_IDS,
    materialize_generated_completeness_receipt,
)

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


class GithubPublishTest(unittest.TestCase):
    """Exercise the GitHub publish command planner."""

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

    def test_push_allows_dirty_worktree_and_uses_verified_origin(self) -> None:
        """Dirty worktree is warning evidence, not a push blocker."""
        runner = FakeRunner()
        runner.add(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], stdout="topic\n")
        runner.add(
            ["gh", "repo", "view", "owner/repo", "--json", "nameWithOwner,url,sshUrl,viewerPermission"],
            stdout='{"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git","viewerPermission":"WRITE"}',
        )
        runner.add(["git", "remote", "get-url", "origin"], stdout="git@github.com:owner/repo.git\n")
        runner.add_verified_actor()
        runner.add_publication_identity()
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

        packet = self.publication_packet(args, runner)
        summary = github_publish.run(args, runner, publication_packet=packet)

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

            packet = self.publication_packet(args, runner)
            summary = github_publish.run(args, runner, publication_packet=packet)

        self.assertEqual(summary["action"], "pr-create")
        self.assertEqual(summary["pr_url"], "https://github.com/owner/repo/pull/1")

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
        runner.add_publication_identity()
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

        packet = self.publication_packet(args, runner)
        summary = github_publish.run(args, runner, publication_packet=packet)

        self.assertEqual(summary["status"], "pending")
        self.assertEqual(summary["next_action"], "wait_for_github_checks_or_rerun_with_--watch")

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
                "{commit_sha: .sha, tree_sha: .tree.sha}",
            ],
            stdout=f'{{"commit_sha":"{MERGE_SHA}","tree_sha":"{MERGE_TREE}"}}',
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
        self.assertEqual(identity["base_sha"], MERGE_SHA)
        self.assertEqual(identity["merge_commit_sha"], MERGE_SHA)
        self.assertEqual(identity["merge_tree_sha"], MERGE_TREE)


if __name__ == "__main__":
    unittest.main()
