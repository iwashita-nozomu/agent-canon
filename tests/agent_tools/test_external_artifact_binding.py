"""Tests for external review projection acknowledgement binding."""

# @dependency-start
# contract test
# responsibility Tests provider mapping, candidate binding, and null rules.
# upstream implementation ../../tools/runtime/artifacts/external_artifact_binding.py materializes and verifies external acknowledgements
# @dependency-end

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from tools.runtime.artifacts.external_artifact_binding import (  # noqa: E402
    LOCAL_EVENT_SCHEMA,
    ExternalProjectionError,
    materialize_external_projection_acknowledgement,
    verify_external_projection_acknowledgement,
)


def local_event() -> dict[str, object]:
    """Return one complete Codex dispatch event fixture."""
    return {
        "schema": LOCAL_EVENT_SCHEMA,
        "aggregate_identity": "aggregate-1",
        "event_kind": "terminal_resume_dispatch_observed",
        "resume_event_id": "resume-event-1",
        "resume_event_body_sha256": "event-hash-1",
        "event_order_index": 1,
        "review_lineage_id": "lineage-1",
        "review_request_id": "request-1",
        "review_context_id": "context-1",
        "review_frame_id": None,
        "candidate_id": "candidate-1",
        "candidate_revision": 1,
        "candidate_body_sha256": "candidate-hash-1",
        "candidate_commit": "a" * 40,
        "candidate_tree": "b" * 40,
    }


def codex_readback() -> dict[str, object]:
    """Return provider fields required by the Codex mapping contract."""
    return {
        "provider_kind": "codex_runtime",
        "provider_status": "running",
        "provider_instance_id": "reviewer-instance-1",
        "provider_object_id": "runtime-object-1",
        "provider_object_version": "1",
        "provider_object_kind": "review_dispatch",
        "provider_parent_object_id": "runtime-parent-1",
        "acknowledgement_order_index": 1,
    }


class ExternalArtifactBindingTest(unittest.TestCase):
    """Verify external projections stay subordinate to local event identity."""

    def test_codex_dispatch_round_trips_without_receipt_bytes(self) -> None:
        """A provider readback maps to one locally bound acknowledgement."""
        event = local_event()
        acknowledgement = materialize_external_projection_acknowledgement(
            event,
            codex_readback(),
        )

        verified = verify_external_projection_acknowledgement(event, acknowledgement)

        self.assertTrue(verified["ok"])
        self.assertEqual(verified["provider_status"], "running")
        self.assertNotIn("provider_receipt_bytes_sha256", acknowledgement)

    def test_receipt_byte_identity_is_rejected(self) -> None:
        """External acknowledgement cannot become a second receipt authority."""
        provider = codex_readback()
        provider["provider_receipt_bytes_sha256"] = "forbidden"

        with self.assertRaises(ExternalProjectionError) as raised:
            materialize_external_projection_acknowledgement(local_event(), provider)

        self.assertEqual(
            raised.exception.code,
            "external_projection:receipt_byte_identity_forbidden",
        )


if __name__ == "__main__":
    unittest.main()
