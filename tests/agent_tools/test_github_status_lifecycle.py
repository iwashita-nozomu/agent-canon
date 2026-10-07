"""Status reconciliation uses native comment IDs, without remote test writes."""
# @dependency-start
# contract test
# responsibility Verifies ordinary evidence comments, bounded label mutation, and uncertain-write handling.
# upstream implementation ../../tools/repository/github/github_status_lifecycle.py owns status reconciliation
# @dependency-end

from __future__ import annotations

import json
import unittest
from urllib.parse import unquote

from tools.repository.github.github_publish import CommandResult
from tools.repository.github.github_status_lifecycle import (
    GhStatusAdapter,
    LabelMapping,
    LifecycleFailure,
    classify_lifecycle,
    evaluate_final,
    load_label_mapping,
    mapping_from_data,
    plan_operations,
    reconcile_status,
    validate_remote_catalog,
)


class StatefulRunner:
    """A fake native API; comments are addressed individually, not by history."""

    def __init__(self) -> None:
        self.labels = {"bug", "in progress"}
        self.catalog = ["in progress", "ready for review", "need verification"]
        self.comments = {}
        self.calls = []
        self.next_id = 10
        self.fail_label = False
        self.lose_post_response = False
        self.hide_comment = False
        self.issue_reads = 0
        self.comment_reads = 0
        self.on_issue_read = lambda runner: None
        self.on_comment_read = lambda runner: None

    def add_comment(self, body, issue=719):
        identity = self.next_id
        self.next_id += 1
        self.comments[identity] = {
            "id": identity,
            "body": body,
            "html_url": f"https://github.com/owner/repo/issues/{issue}#issuecomment-{identity}",
            "issue_url": f"https://api.github.com/repos/owner/repo/issues/{issue}",
        }
        return dict(self.comments[identity])

    def __call__(self, args, cwd=None):
        args = list(args)
        self.calls.append(args)
        method = args[args.index("--method") + 1] if "--method" in args else "GET"
        endpoint = next(arg for arg in args if arg.startswith("repos/"))
        status = 0
        if method == "GET" and endpoint.endswith("/labels?per_page=100"):
            body = [
                [{"name": name} for name in self.catalog[:2]],
                [{"name": name} for name in self.catalog[2:]],
            ]
        elif method == "GET" and "/issues/comments/" in endpoint:
            self.comment_reads += 1
            self.on_comment_read(self)
            identity = int(endpoint.rsplit("/", 1)[1])
            if self.hide_comment or identity not in self.comments:
                status, body = 1, {"message": "Not Found"}
            else:
                body = self.comments[identity]
        elif method == "GET" and endpoint == "repos/owner/repo/issues/719":
            self.issue_reads += 1
            self.on_issue_read(self)
            body = {
                "number": 719,
                "html_url": "https://github.com/owner/repo/issues/719",
                "state": "open",
                "labels": [{"name": name} for name in sorted(self.labels)],
            }
        elif method == "POST" and endpoint.endswith("/comments"):
            body = self.add_comment(args[args.index("-f") + 1].removeprefix("body="))
            if self.lose_post_response:
                status, body = 1, {"message": "connection lost after acceptance"}
        elif method in {"POST", "DELETE"} and "/labels" in endpoint:
            if self.fail_label:
                status, body = 1, {"message": "write outcome unknown"}
            elif method == "POST":
                self.labels.add(args[args.index("-f") + 1].removeprefix("labels[]="))
                body = [{"name": name} for name in self.labels]
            else:
                self.labels.remove(unquote(endpoint.rsplit("/", 1)[1]))
                return CommandResult(args, 0, "", "")
        else:
            raise AssertionError(f"unexpected API call: {args}")
        return CommandResult(args, status, json.dumps(body), "")

    def writes(self):
        return [args for args in self.calls if "--method" in args]

    def comment_posts(self):
        return [
            args
            for args in self.writes()
            if "POST" in args and "repos/owner/repo/issues/719/comments" in args
        ]


class StatusLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = LabelMapping(
            "in progress",
            "ready for review",
            "need verification",
            legacy_active=("working",),
        )
        self.runner = StatefulRunner()
        self.adapter = GhStatusAdapter("owner/repo", 719, runner=self.runner)
        self.facts = {
            "work_started": True,
            "handoff_ready": True,
            "validation_complete": True,
        }
        self.body = "修正を公開。対象テストは成功。変更と根拠は同じIssueに記録済み。"

    def reconcile(self, **overrides):
        values = {
            "mapping": self.mapping,
            "facts": self.facts,
            "comment_body": self.body,
        }
        values.update(overrides)
        return reconcile_status(self.adapter, **values)

    def assert_failure(self, code, action):
        with self.assertRaises(LifecycleFailure) as caught:
            action()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_taxonomy_is_loaded_from_existing_owner(self):
        self.assertEqual(load_label_mapping().active, "in progress")
        self.assertEqual(mapping_from_data(self.mapping.as_dict()), self.mapping)
        self.assertEqual(
            validate_remote_catalog(self.mapping, self.runner.catalog),
            frozenset(self.runner.catalog),
        )
        self.assert_failure(
            "label_mapping_missing",
            lambda: validate_remote_catalog(self.mapping, ["in progress"]),
        )

    def test_invalid_taxonomy_does_not_mutate(self):
        for table in (
            {},
            {"status_lifecycle": {}},
            {
                "status_lifecycle": {
                    "active": "x",
                    "ready_for_review": "x",
                    "needs_verification": "y",
                }
            },
        ):
            with self.subTest(table=table):
                self.assert_failure(
                    "taxonomy_invalid", lambda: mapping_from_data(table)
                )
        bad = self.mapping.as_dict()
        bad["status_lifecycle"]["legacy_aliases"]["active"] = ["ready for review"]
        self.assert_failure("taxonomy_invalid", lambda: mapping_from_data(bad))
        self.assertEqual(self.runner.writes(), [])

    def test_native_issue_and_comment_ids_are_positive(self):
        for identity in (True, 0, -1, "1?x", "../1"):
            with self.subTest(identity=identity):
                self.assert_failure(
                    "identity_invalid", lambda: GhStatusAdapter("owner/repo", identity)
                )
        for identity in (False, 0, -1, "10"):
            self.assert_failure(
                "identity_invalid",
                lambda: self.reconcile(comment_body=None, comment_id=identity),
            )
        self.assertEqual(self.runner.calls, [])

    def test_one_ordinary_comment_needs_no_pr_record_or_marker(self):
        result = self.reconcile()
        self.assertEqual(result["kind"], "success")
        self.assertEqual(result["evidence"]["body"], self.body)
        self.assertEqual(result["evidence"]["id"], 10)
        self.assertEqual(self.runner.labels, {"bug", "ready for review"})
        self.assertEqual(len(self.runner.comment_posts()), 1)
        self.assertFalse(
            any("comments?" in arg for args in self.runner.calls for arg in args)
        )

    def test_selected_existing_id_is_reused_without_post(self):
        selected = self.runner.add_comment(self.body)
        self.runner.add_comment(self.body)
        result = self.reconcile(comment_body=None, comment_id=selected["id"])
        self.assertEqual(result["evidence"]["id"], selected["id"])
        self.assertEqual(self.runner.comment_posts(), [])

    def test_other_comments_and_identical_prose_do_not_gate_labels(self):
        self.runner.add_comment(self.body)
        self.runner.add_comment("unrelated discussion")

        def concurrent_comment(runner):
            if runner.comment_reads == 2:
                runner.add_comment(self.body)

        self.runner.on_comment_read = concurrent_comment
        self.assertEqual(self.reconcile()["kind"], "success")
        self.assertEqual(len(self.runner.comment_posts()), 1)

    def test_foreign_issue_comment_is_not_evidence(self):
        foreign = self.runner.add_comment(self.body, issue=720)
        self.assert_failure(
            "evidence_readback_mismatch",
            lambda: self.reconcile(comment_body=None, comment_id=foreign["id"]),
        )
        self.assertEqual(self.runner.writes(), [])

    def test_empty_or_ambiguous_evidence_is_rejected_before_transport(self):
        for options in (
            {"comment_body": None},
            {"comment_body": " "},
            {"comment_id": 10},
        ):
            self.assert_failure("evidence_missing", lambda: self.reconcile(**options))
        self.assertEqual(self.runner.calls, [])

    def test_uncertain_post_is_not_retried_or_rolled_back(self):
        self.runner.lose_post_response = True
        self.assert_failure("mutation_partial", self.reconcile)
        self.assertEqual(len(self.runner.comment_posts()), 1)
        self.assertEqual(len(self.runner.writes()), 1)
        self.assertEqual(len(self.runner.comments), 1)
        self.assertEqual(self.runner.labels, {"bug", "in progress"})

    def test_missing_created_comment_blocks_label_writes(self):
        self.runner.hide_comment = True
        self.assert_failure("readback_unavailable", self.reconcile)
        self.assertEqual(len(self.runner.writes()), 1)
        self.assertEqual(self.runner.labels, {"bug", "in progress"})

    def test_concurrent_selected_comment_edit_is_not_success(self):
        def edit(runner):
            if runner.comment_reads == 2:
                runner.comments[10]["body"] = "changed by another writer"

        self.runner.on_comment_read = edit
        self.assert_failure("evidence_readback_mismatch", self.reconcile)
        self.assertEqual(len(self.runner.comment_posts()), 1)

    def test_three_states_preserve_unrelated_labels(self):
        for changes, expected in (
            ({"handoff_ready": False}, {"in progress"}),
            ({}, {"ready for review"}),
            (
                {"verification_unavailable": True},
                {"ready for review", "need verification"},
            ),
        ):
            with self.subTest(changes=changes):
                runner = StatefulRunner()
                result = reconcile_status(
                    GhStatusAdapter("owner/repo", 719, runner=runner),
                    mapping=self.mapping,
                    facts={**self.facts, **changes},
                    comment_body="対象変更の説明。実機検証は接続がなく未実施。既存実行ownerへ引継ぎ。",
                )
                self.assertEqual(result["kind"], "success")
                self.assertEqual(runner.labels, {"bug", *expected})

    def test_failures_remain_active_not_external_verification(self):
        for field in ("implementation_failure", "validation_failed"):
            self.assertEqual(
                classify_lifecycle(
                    {**self.facts, field: True, "verification_unavailable": True}
                ),
                "active",
            )
        self.assert_failure(
            "lifecycle_facts_incomplete",
            lambda: classify_lifecycle({**self.facts, "handoff_ready": "yes"}),
        )

    def test_plan_removes_only_undesired_managed_names(self):
        desired = self.mapping.desired("review-ready-unverified")
        operations = plan_operations(
            ("bug", "working", "in progress"), desired, self.mapping
        )
        self.assertEqual(
            operations,
            (
                ("remove", "in progress"),
                ("remove", "working"),
                ("add", "ready for review"),
                ("add", "need verification"),
            ),
        )
        self.assertTrue(
            evaluate_final(("bug", *desired), desired, ("bug", "working"), self.mapping)
        )
        self.assertFalse(
            evaluate_final(tuple(desired), desired, ("bug",), self.mapping)
        )
        self.assertFalse(
            evaluate_final(
                ("bug", "working", *desired), desired, ("bug",), self.mapping
            )
        )

    def test_fresh_label_drift_stops_before_first_mutation(self):
        def drift(runner):
            if runner.issue_reads == 2:
                runner.labels.add("other-owner")

        self.runner.on_issue_read = drift
        self.assert_failure("fresh_state_changed", self.reconcile)
        self.assertEqual(len(self.runner.writes()), 1)
        self.assertIn("other-owner", self.runner.labels)

    def test_between_mutation_drift_keeps_completed_prefix(self):
        def drift(runner):
            if runner.issue_reads == 4:
                runner.labels.add("other-owner")

        self.runner.on_issue_read = drift
        failure = self.assert_failure("fresh_state_changed", self.reconcile)
        self.assertEqual(
            failure.details["completed_prefix"],
            [{"action": "remove", "label": "in progress"}],
        )
        self.assertEqual(self.runner.labels, {"bug", "other-owner"})

    def test_unknown_label_write_is_not_retried(self):
        self.runner.fail_label = True
        failure = self.assert_failure("mutation_partial", self.reconcile)
        self.assertEqual(failure.details["completed_prefix"], [])
        self.assertEqual(failure.details["rollback"], "not-attempted")
        self.assertEqual(len(self.runner.writes()), 2)

    def test_label_delete_uses_encoded_native_path_and_no_body(self):
        self.runner.labels.add("status/old state")
        self.adapter.remove_label("status/old state")
        self.assertEqual(
            self.runner.calls[-1],
            [
                "gh",
                "api",
                "--method",
                "DELETE",
                "repos/owner/repo/issues/719/labels/status%2Fold%20state",
            ],
        )

    def test_readback_does_not_claim_to_detect_unobserved_aba(self):
        def aba(runner):
            if runner.issue_reads == 2:
                runner.labels.add("temporary")
                runner.labels.remove("temporary")

        self.runner.on_issue_read = aba
        self.assertEqual(self.reconcile()["kind"], "success")


if __name__ == "__main__":
    unittest.main()
