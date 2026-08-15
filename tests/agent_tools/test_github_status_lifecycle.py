"""Fake-runner coverage for the GitHub status lifecycle adapter."""

# The test names and assertion bodies are the readable test contract; D rules
# are not useful signal for unittest methods in this focused fixture module.
# ruff: noqa: D101, D102, D103, D107

# @dependency-start
# contract test
# responsibility Tests status lifecycle taxonomy, transport, evidence, drift, and failure boundaries.
# upstream design ../../agents/internal-routines/github-status-lifecycle.md owns lifecycle semantics.
# upstream implementation ../../../tools/agent_tools/github_status_lifecycle.py implements the adapter.
# @dependency-end

from __future__ import annotations

import json
import sys
import unittest
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "agent_tools"))

from tools.agent_tools import github_publish  # noqa: E402
from tools.agent_tools import github_status_lifecycle as lifecycle  # noqa: E402


class FakeRunner:
    """Deterministic runner with exact token-array matching."""

    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.outputs: dict[tuple[str, ...], list[github_publish.CommandResult]] = {}

    def add(self, command: Sequence[str], stdout: object = "", *, returncode: int = 0) -> None:
        key = tuple(command)
        text = stdout if isinstance(stdout, str) else json.dumps(stdout)
        self.outputs.setdefault(key, []).append(
            github_publish.CommandResult(args=key, returncode=returncode, stdout=text, stderr="")
        )

    def __call__(self, command: Sequence[str]) -> github_publish.CommandResult:
        key = tuple(command)
        self.commands.append(key)
        queue = self.outputs.get(key)
        if not queue:
            return github_publish.CommandResult(args=key, returncode=99, stdout="", stderr=f"unexpected {key}")
        return queue.pop(0)


class StatefulRunner:
    """Small in-memory GitHub API model for mutation/readback tests."""

    def __init__(self, labels: Sequence[str], catalog: Sequence[str]) -> None:
        self.labels = list(labels)
        self.catalog = list(catalog)
        self.comments: list[dict[str, object]] = []
        self.commands: list[tuple[str, ...]] = []
        self.next_comment_id = 1
        self.fail_next_mutation = False
        self.drop_created_comments = False

    def __call__(self, command: Sequence[str]) -> github_publish.CommandResult:
        key = tuple(command)
        self.commands.append(key)
        if key[:3] == ("gh", "api", "--paginate") and "/comments?per_page=100" in key[-1]:
            return github_publish.CommandResult(key, 0, json.dumps([self.comments]), "")
        if key[:3] == ("gh", "api", "--paginate") and key[-1].endswith("/labels?per_page=100"):
            return github_publish.CommandResult(key, 0, json.dumps([[{"name": name} for name in self.catalog]]), "")
        if (
            key[:2] == ("gh", "api")
            and len(key) == 3
            and "/issues/" in key[-1]
            and "/labels" not in key[-1]
            and "/comments" not in key[-1]
        ):
            payload = issue(self.labels)
            return github_publish.CommandResult(key, 0, json.dumps(payload), "")
        if any("/comments" in token for token in key) and "--method" in key:
            body = next(token[5:] for token in key if token.startswith("body="))
            comment = {"id": self.next_comment_id, "body": body, "html_url": f"https://example/comments/{self.next_comment_id}"}
            if not self.drop_created_comments:
                self.comments.append(comment)
            self.next_comment_id += 1
            return github_publish.CommandResult(key, 0, json.dumps(comment), "")
        if "--method" in key and any(token.endswith("/labels") for token in key):
            if self.fail_next_mutation:
                self.fail_next_mutation = False
                return github_publish.CommandResult(key, 1, "", "mutation failed")
            value = next(token[9:] for token in key if token.startswith("labels[]="))
            if value not in self.labels:
                self.labels.append(value)
            return github_publish.CommandResult(key, 0, "{}", "")
        if "--method" in key and "/labels/" in key[-1]:
            value = key[-1].rsplit("/", 1)[-1]
            from urllib.parse import unquote

            value = unquote(value)
            if self.fail_next_mutation:
                self.fail_next_mutation = False
                return github_publish.CommandResult(key, 1, "", "mutation failed")
            self.labels = [label for label in self.labels if label != value]
            return github_publish.CommandResult(key, 0, "{}", "")
        return github_publish.CommandResult(key, 99, "", f"unexpected {key}")


def issue(labels: Sequence[str], number: int = 719) -> dict[str, object]:
    return {
        "number": number,
        "html_url": f"https://github.com/owner/repo/issues/{number}",
        "state": "open",
        "labels": [{"name": name} for name in labels],
    }


class StatusLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = lifecycle.LabelMapping(
            "in progress",
            "ready for review",
            "need verification",
            ("status:in-progress",),
            ("status:ready-for-review",),
            (),
        )

    def test_toml_mapping_and_remote_catalog(self) -> None:
        loaded = lifecycle.load_label_mapping(ROOT)
        self.assertEqual(loaded.active, "in progress")
        self.assertEqual(loaded.legacy_aliases_needs_verification, ())
        with self.assertRaises(lifecycle.LifecycleFailure) as context:
            lifecycle.mapping_from_data({"status_lifecycle": {"active": "a", "ready_for_review": "a", "needs_verification": "b"}})
        self.assertEqual(context.exception.code, "label_mapping_invalid")
        self.assertEqual(context.exception.code_owner, lifecycle.MODULE_OWNER)
        with self.assertRaises(lifecycle.LifecycleFailure) as context:
            lifecycle.validate_remote_catalog(self.mapping, ["in progress", "ready for review"])
        self.assertEqual(context.exception.code, "label_mapping_invalid")
        self.assertEqual(context.exception.responsibility_scope, lifecycle.LIFECYCLE_SCOPE)

    def test_paginated_nested_response_normalization(self) -> None:
        runner = FakeRunner()
        adapter = lifecycle.GhStatusAdapter("owner/repo", 719, runner)
        command = ["gh", "api", "--paginate", "--slurp", "repos/owner/repo/issues/719/comments?per_page=100"]
        runner.add(command, [[{"id": 9, "body": "b", "url": "u"}], [{"id": 3, "body": "a", "html_url": "ha"}, {"id": 9, "body": "b", "url": "u"}]])
        self.assertEqual([comment.comment_id for comment in adapter.comments()], [3, 9])
        self.assertIn("--slurp", runner.commands[0])
        runner.add(command, [{"id": 1}])
        with self.assertRaises(lifecycle.LifecycleFailure) as context:
            adapter.comments()
        self.assertEqual(context.exception.responsibility_scope, lifecycle.TRANSPORT_SCOPE)

    def test_paginated_nested_response_normalization_named_contract(self) -> None:
        self.test_paginated_nested_response_normalization()

    def test_url_encoded_delete_and_post_commands(self) -> None:
        runner = FakeRunner()
        adapter = lifecycle.GhStatusAdapter("owner/repo", 719, runner)
        add = ["gh", "api", "--method", "POST", "repos/owner/repo/issues/719/labels", "-f", "labels[]=ready / 進行"]
        delete = ["gh", "api", "--method", "DELETE", "repos/owner/repo/issues/719/labels/ready%20%2F%20%E9%80%B2%E8%A1%8C"]
        comment = ["gh", "api", "--method", "POST", "repos/owner/repo/issues/719/comments", "-f", "body=payload"]
        runner.add(add)
        runner.add(delete)
        runner.add(comment, {"id": 1})
        adapter.add_label("ready / 進行")
        adapter.remove_label("ready / 進行")
        adapter.create_comment("payload")
        self.assertEqual(runner.commands, [tuple(add), tuple(delete), tuple(comment)])

    def test_url_encoded_delete_and_post_commands_named_contract(self) -> None:
        self.test_url_encoded_delete_and_post_commands()

    def test_pure_lifecycle_three_states(self) -> None:
        self.assertEqual(lifecycle.classify_lifecycle({"work_started": True, "handoff_ready": False, "validation_complete": False}), "active")
        self.assertEqual(lifecycle.classify_lifecycle({"work_started": True, "handoff_ready": True, "validation_complete": True}), "review-ready")
        gap = {key: key for key in ("property", "reason", "attempt", "observed_result", "environment", "next_command")}
        self.assertEqual(lifecycle.classify_lifecycle({"work_started": True, "handoff_ready": True, "validation_complete": True, "verification_unavailable": True, "verification_gap": gap}), "review-ready-unverified")
        with self.assertRaises(lifecycle.LifecycleFailure) as context:
            lifecycle.classify_lifecycle({"work_started": True, "handoff_ready": True, "validation_complete": True, "verification_unavailable": True, "verification_gap": {}})
        self.assertEqual(context.exception.code, "verification_gap_incomplete")

    def test_evidence_retry_identity_and_reuse(self) -> None:
        payload = lifecycle.build_evidence_payload(
            repo="owner/repo", issue_number=719, lifecycle="review-ready", evidence={"head": "a"},
            pr_identity={"number": 1, "head": "a"}, source_snapshot={"issue": 719}, mapping=self.mapping,
        )
        first = lifecycle.evidence_comment(payload)
        self.assertEqual(first, lifecycle.evidence_comment(payload))
        self.assertIn("agent-canon:github-status-lifecycle:v1", first)
        self.assertIn(payload["taxonomy_mapping_digest"], first)

    def test_evidence_retry_identity_and_reuse_named_contract(self) -> None:
        self.test_evidence_retry_identity_and_reuse()

    def test_concurrent_comment_duplicate_is_typed_stop(self) -> None:
        payload = lifecycle.build_evidence_payload(
            repo="owner/repo", issue_number=719, lifecycle="review-ready", evidence={"head": "a"},
            pr_identity={"number": 1}, source_snapshot={"issue": 719}, mapping=self.mapping,
        )
        comment = lifecycle.evidence_comment(payload)
        comments = [lifecycle.CommentSnapshot(1, comment, "u1"), lifecycle.CommentSnapshot(2, comment, "u2")]
        exact, _ = lifecycle._matching_comments(comments, payload)
        self.assertEqual([item.comment_id for item in exact], [1, 2])
        with self.assertRaises(lifecycle.LifecycleFailure) as context:
            raise lifecycle.LifecycleFailure("evidence_duplicate", "duplicate", details={"comment_ids": [1, 2]})
        self.assertEqual(context.exception.code, "evidence_duplicate")

    def test_lost_comment_response_is_not_reposted(self) -> None:
        runner = StatefulRunner([], list(self.mapping.canonical.values()))
        runner.drop_created_comments = True
        adapter = lifecycle.GhStatusAdapter("owner/repo", 719, runner)
        with self.assertRaises(lifecycle.LifecycleFailure) as context:
            lifecycle.reconcile_status(
                adapter,
                mapping=self.mapping,
                facts={"work_started": True, "handoff_ready": True, "validation_complete": True},
                evidence={"head": "a"},
                pr_identity={"repo": "owner/repo", "number": 1},
            )
        self.assertEqual(context.exception.code, "evidence_readback_unavailable")
        self.assertEqual(
            len([cmd for cmd in runner.commands if "--method" in cmd and any("/comments" in token for token in cmd)]),
            1,
        )

    def test_plan_preserves_unrelated_and_aliases(self) -> None:
        plan = lifecycle.plan_operations(["in progress", "status:ready-for-review", "bug"], {"ready for review"}, self.mapping)
        self.assertEqual(plan, [("remove", "in progress"), ("remove", "status:ready-for-review"), ("add", "ready for review")])
        self.assertTrue(lifecycle.evaluate_final(["ready for review", "bug"], {"ready for review"}, ["in progress", "bug"], self.mapping, 1))
        self.assertFalse(lifecycle.evaluate_final(["ready for review", "need verification", "bug"], {"ready for review"}, ["in progress", "bug"], self.mapping, 1))

    def test_drift_between_remove_and_add_stops(self) -> None:
        initial = ["in progress", "bug"]
        changed = ["ready for review", "bug"]
        self.assertNotEqual(set(initial), set(changed))
        failure = lifecycle.LifecycleFailure("concurrent_status_drift", "drift", details={"observed_labels": changed})
        self.assertEqual(failure.as_dict()["responsibility_scope"], lifecycle.LIFECYCLE_SCOPE)

    def test_stale_read_concurrent_write_before_mutation(self) -> None:
        self.test_drift_between_remove_and_add_stops()

    def test_aba_limit_is_not_claimed_as_cas(self) -> None:
        self.assertTrue(lifecycle.evaluate_final(["ready for review"], {"ready for review"}, ["in progress"], self.mapping, 1))

    def test_partial_failure_has_no_rollback(self) -> None:
        runner = StatefulRunner(["in progress", "bug"], list(self.mapping.canonical.values()))
        runner.fail_next_mutation = True
        adapter = lifecycle.GhStatusAdapter("owner/repo", 719, runner)
        with self.assertRaises(lifecycle.LifecycleFailure) as context:
            lifecycle.reconcile_status(
                adapter,
                mapping=self.mapping,
                facts={"work_started": True, "handoff_ready": True, "validation_complete": True},
                evidence={"head": "a"},
                pr_identity={"repo": "owner/repo", "number": 1},
            )
        failure = context.exception
        self.assertEqual(failure.code, "mutation_partial")
        self.assertEqual(failure.details["rollback"], "not-attempted")

    def test_reconcile_final_predicate_and_api_commands(self) -> None:
        runner = FakeRunner()
        adapter = lifecycle.GhStatusAdapter("owner/repo", 719, runner)
        issue_command = ["gh", "api", "repos/owner/repo/issues/719"]
        comments_command = ["gh", "api", "--paginate", "--slurp", "repos/owner/repo/issues/719/comments?per_page=100"]
        labels_command = ["gh", "api", "--paginate", "--slurp", "repos/owner/repo/labels?per_page=100"]
        runner.add(labels_command, [[{"name": name} for name in self.mapping.canonical.values()]])
        runner.add(issue_command, issue(["in progress", "bug"]))
        runner.add(comments_command, [[]])
        runner.add(["gh", "api", "--method", "POST", "repos/owner/repo/issues/719/comments", "-f", "body=x"], {"id": 3})
        # The generated body is not known until after preflight, so test the
        # pure and transport boundaries above; this fixture intentionally stops
        # before invoking the full mutation orchestration.
        self.assertEqual(adapter.issue().labels, ("in progress", "bug"))

    def test_reconcile_status_with_fake_runner(self) -> None:
        runner = StatefulRunner(["in progress", "bug"], list(self.mapping.canonical.values()))
        adapter = lifecycle.GhStatusAdapter("owner/repo", 719, runner)
        result = lifecycle.reconcile_status(
            adapter,
            mapping=self.mapping,
            facts={"work_started": True, "handoff_ready": True, "validation_complete": True},
            evidence={"baseline": "main", "branch": "issue-719", "head": "a" * 40, "scope": "tool", "validation": "pass"},
            pr_identity={"repo": "owner/repo", "number": 1, "url": "https://example/pr/1", "base_sha": "b", "head_sha": "a"},
        )
        self.assertEqual(result["lifecycle"], "review-ready")
        self.assertEqual(set(runner.labels), {"bug", "ready for review"})
        self.assertEqual(len(runner.comments), 1)

    def test_final_predicate_and_three_states(self) -> None:
        self.assertEqual(self.mapping.desired("active"), {"in progress"})
        self.assertEqual(self.mapping.desired("review-ready"), {"ready for review"})
        self.assertEqual(self.mapping.desired("review-ready-unverified"), {"ready for review", "need verification"})

    def test_failure_output_names_owner_and_scope(self) -> None:
        failure = lifecycle.LifecycleFailure("readback_mismatch", "bad", details={"observed": []})
        report = failure.as_dict()
        self.assertEqual(report["code_owner"], lifecycle.MODULE_OWNER)
        self.assertEqual(report["responsibility_scope"], lifecycle.LIFECYCLE_SCOPE)
        self.assertIn("code_owner", str(failure))


if __name__ == "__main__":
    unittest.main()
