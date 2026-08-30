"""Tests for current automatic-review state projection."""

# @dependency-start
# contract test
# responsibility Tests current candidate review state and APPROVE-only unlock.
# upstream implementation ../../tools/agent/orchestration/review_dispatch.py materializes automatic-review state and routing
# @dependency-end

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.agent.orchestration import review_dispatch  # noqa: E402
from tools.runtime.artifacts.artifact_identity import canonical_body_sha256  # noqa: E402


def candidate() -> dict[str, object]:
    """Return one immutable candidate fixture."""
    value: dict[str, object] = {"candidate_id": "candidate-1"}
    value["candidate_body_sha256"] = canonical_body_sha256(
        value,
        "candidate_body_sha256",
    )
    return value


def decision(name: str) -> dict[str, object]:
    """Return one body-hashed decision fixture."""
    value: dict[str, object] = {
        "candidate_id": "candidate-1",
        "candidate_body_sha256": candidate()["candidate_body_sha256"],
        "decision": name,
    }
    value["event_body_sha256"] = canonical_body_sha256(value, "event_body_sha256")
    return value


class ReviewDispatchTest(unittest.TestCase):
    """Verify only the current candidate's explicit decision unlocks publication."""

    def project(self, review_decision: dict[str, object]) -> dict[str, object]:
        """Project a patched canonical state without caller identity overrides."""
        with (
            patch.object(
                review_dispatch, "_active_report_dir", return_value=PROJECT_ROOT
            ),
            patch.object(
                review_dispatch, "_current_candidate", return_value=candidate()
            ),
            patch.object(
                review_dispatch,
                "_automatic_payloads",
                side_effect=lambda _report_dir, kind=None: (
                    [review_decision] if kind == "decision" else []
                ),
            ),
        ):
            return review_dispatch.resolve_current_review_state(PROJECT_ROOT)

    def test_revise_keeps_publication_locked(self) -> None:
        """REVISE remains a terminal repair state, never an approval."""
        state = self.project(decision("REVISE"))

        self.assertFalse(state["publication_unlocked"])

    def test_approve_unlocks_current_candidate_only(self) -> None:
        """Only an explicit APPROVE for the current candidate unlocks state."""
        state = self.project(decision("APPROVE"))

        self.assertTrue(state["publication_unlocked"])

    def test_publication_projection_accepts_only_canonical_approve(self) -> None:
        """Publication remains locked if an uncanonical alias reaches the ledger."""
        self.assertFalse(self.project(decision("ACCEPT"))["publication_unlocked"])
        self.assertFalse(
            self.project(decision("CHANGES-REQUIRED"))["publication_unlocked"]
        )
        self.assertFalse(self.project(decision("ESCALATE"))["publication_unlocked"])

    def test_nonblocking_findings_are_accepted(self) -> None:
        """Non-blocking findings do not force a changes-required outcome."""
        self.assertEqual(
            review_dispatch.derive_review_outcome(
                [
                    {"status": "non-blocking"},
                    {"status": "question"},
                    {"status": "accepted-risk"},
                ]
            ),
            "accept",
        )

    def test_only_unresolved_blocking_finding_requires_changes(self) -> None:
        """The owning decision is derived from finding status, not style severity."""
        self.assertEqual(
            review_dispatch.derive_review_outcome(
                [{"severity": "style", "status": "non-blocking"}, {"status": "blocking"}]
            ),
            "changes-required",
        )

    def test_finding_table_rows_are_normalized(self) -> None:
        """Existing Markdown finding tables feed the shared status contract."""
        rows = review_dispatch.parse_finding_rows(
            "| Chunk | Finding | Severity | Status | Evidence |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| docs | wording | style | non-blocking | docs.md |\n"
        )
        self.assertEqual(rows[0]["status"], "non-blocking")

    def test_status_column_is_header_aware_for_python_review_shape(self) -> None:
        """Status is read by header name when Evidence follows it."""
        rows = review_dispatch.parse_finding_rows(
            "| File | Finding | Severity | Status | Evidence |\n"
            "| ---- | ------- | -------- | ------ | -------- |\n"
            "| tool.py | broken path | high | blocking | test.py:10 |\n"
        )
        self.assertEqual(rows[0]["status"], "blocking")
        self.assertEqual(
            review_dispatch.derive_review_outcome(rows),
            "changes-required",
        )

    def test_decision_aliases_are_canonicalized_at_dispatch(self) -> None:
        """All canonical decisions and template aliases share one boundary."""
        for value in ("APPROVE", "REVISE", "ESCALATE"):
            with self.subTest(value=value):
                self.assertEqual(
                    review_dispatch.canonicalize_review_decision(value.lower()),
                    value,
                )
        self.assertEqual(
            review_dispatch.canonicalize_review_decision("ACCEPT"),
            "APPROVE",
        )
        self.assertEqual(
            review_dispatch.canonicalize_review_decision("CHANGES-REQUIRED"),
            "REVISE",
        )

    def test_invalid_review_decisions_fail_closed(self) -> None:
        """Unknown and mistyped review decisions cannot enter the ledger."""
        for value in (None, "", "BLOCK", "APPROVED"):
            with self.subTest(value=value), self.assertRaises(
                review_dispatch.AutomaticReviewError
            ):
                review_dispatch.canonicalize_review_decision(value)

    def test_record_decision_canonicalizes_aliases_and_blocking_derived_state(self) -> None:
        """Recorded events retain APPROVE/REVISE for publication consumers."""
        candidate_payload = {
            "candidate_id": "candidate-1",
            "candidate_revision": 1,
            "candidate_body_sha256": "candidate-hash",
            "candidate_commit": "a" * 40,
            "candidate_tree": "b" * 40,
        }
        frame = {
            "review_role_id": "change_reviewer",
            "candidate_id": "candidate-1",
            "review_frame_id": "frame-1",
            "review_request_id": "request-1",
            "review_context_id": "context-1",
            "review_lineage_id": "lineage-1",
            "reviewer_assignment_id": "assignment-1",
            "review_frame_body_sha256": "frame-hash",
            "event_order_index": 1,
        }
        resume_event = {
            "review_frame_id": "frame-1",
            "observed_result": {"nested_runtime_agent_id": "reviewer-1"},
        }

        def record(text: str) -> dict[str, object]:
            with tempfile.TemporaryDirectory() as temp_dir:
                report_dir = Path(temp_dir)
                (report_dir / "change_review.md").write_text(text, encoding="utf-8")
                captured: list[dict[str, object]] = []

                def payloads(_report_dir: Path, kind: str | None = None) -> list[dict[str, object]]:
                    if kind == "frame":
                        return [frame]
                    if kind == "resume_event":
                        return [resume_event]
                    return [frame, resume_event]

                with (
                    patch.object(review_dispatch, "_active_report_dir", return_value=report_dir),
                    patch.object(review_dispatch, "_current_candidate", return_value=candidate_payload),
                    patch.object(review_dispatch, "_automatic_payloads", side_effect=payloads),
                    patch.object(
                        review_dispatch,
                        "_review_route",
                        return_value={"review_artifact": "change_review.md"},
                    ),
                    patch.object(
                        review_dispatch,
                        "materialize_artifact_identity",
                        return_value={
                            "identity_record_id": "identity-1",
                            "identity_record_body_sha256": "identity-hash",
                            "artifact_path": "change_review.md",
                            "sha256": "artifact-hash",
                            "git_blob": "blob-hash",
                        },
                    ),
                    patch.object(
                        review_dispatch,
                        "_append_automatic_event",
                        side_effect=lambda _path, payload, outcome: captured.append(payload),
                    ),
                ):
                    review_dispatch.record_current_review_decision(report_dir)
                self.assertEqual(len(captured), 1)
                return captured[0]

        accepted = record(
            "| Chunk | Finding | Severity | Status | Evidence |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| docs | wording | style | non-blocking | docs.md |\n"
            "\nDecision: ACCEPT\n"
        )
        self.assertEqual(accepted["decision"], "APPROVE")

        escalated_question = record(
            "| Chunk | Finding | Severity | Status | Evidence |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| docs | clarification | style | question | docs.md |\n"
            "\nDecision: ESCALATE\n"
        )
        self.assertEqual(escalated_question["decision"], "ESCALATE")

        revise_normalized_to_approve = record(
            "| Chunk | Finding | Severity | Status | Evidence |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| docs | style note | style | non-blocking | docs.md |\n"
            "\nDecision: REVISE\n"
        )
        self.assertEqual(revise_normalized_to_approve["decision"], "APPROVE")

        required = record(
            "| File | Finding | Severity | Status | Evidence |\n"
            "| ---- | ------- | -------- | ------ | -------- |\n"
            "| tool.py | broken path | high | blocking | test.py:10 |\n"
            "\nDecision: CHANGES-REQUIRED\n"
        )
        self.assertEqual(required["decision"], "REVISE")


if __name__ == "__main__":
    unittest.main()
