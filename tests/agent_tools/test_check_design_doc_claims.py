"""Tests for the graph-gated design claim consumer."""

# @dependency-start
# contract test
# responsibility Tests design-document claims against canonical graph status and context evidence.
# upstream design ../../documents/design/README.md design-document evidence policy
# upstream implementation ../../tools/agent_tools/check_design_doc_claims.py graph-gated claim consumer
# upstream implementation ../../tools/agent_tools/graph_client.py canonical graph adapter
# @dependency-end

from __future__ import annotations

import io
import json
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tools.agent_tools import check_design_doc_claims as checker


class FakeClaimConsumer:
    """Record graph-owned operations without parsing a dependency manifest."""

    def __init__(
        self,
        *,
        status_reason: str | None = None,
        supported_tokens: frozenset[str] = frozenset(),
        metadata_error: checker.GraphClientError | None = None,
    ) -> None:
        """Initialize one closed graph response scenario."""
        self._status_reason = status_reason
        self.supported_tokens = supported_tokens
        self.metadata_error = metadata_error
        self.calls: list[tuple[object, ...]] = []

    def status_reason(self) -> str | None:
        """Return one prerequisite graph-state result."""
        self.calls.append(("status_reason",))
        return self._status_reason

    def document_metadata(self, path: str) -> tuple[str, tuple[int, int]]:
        """Return parser-owned contract/span metadata from canonical context."""
        self.calls.append(("document_metadata", path))
        if self.metadata_error is not None:
            raise self.metadata_error
        return "design", (2, 7)

    def evidence_paths(
        self, path: str, recursive_depth: int
    ) -> tuple[set[str], set[str]]:
        """Return a canonical dependency projection for the document."""
        self.calls.append(("evidence_paths", path, recursive_depth))
        return {"tools/feature.py"}, set()

    def token_supported(self, path: str, token: str) -> tuple[bool, str | None]:
        """Return exact graph context support for one token."""
        self.calls.append(("token_supported", path, token))
        supported = token in self.supported_tokens
        return supported, None if supported else "graph_context_no_match"

    def context(self, path: str, token: str | None = None) -> None:
        """Reject unexpected parent-context requests in these fixtures."""
        self.calls.append(("context", path, token))
        raise AssertionError("parent context was not configured")


def write_design(root: Path, claim: str) -> Path:
    """Write one design document whose manifest span is graph-owned metadata."""
    path = root / "documents/design/feature.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        textwrap.dedent(
            f"""
            # Feature Design
            <!--
            @dependency-start
            contract design
            responsibility Documents one graph-gated fixture.
            downstream implementation ../../tools/feature.py implementation evidence
            @dependency-end
            -->

            ## Evidence And Assumption Ledger

            - Evidence sources: `tools/feature.py`.
            - Assumptions: canonical graph context is fresh.

            ## Claims

            {claim}
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return path


class DesignDocClaimCheckerTest(unittest.TestCase):
    """Exercise only the public graph-gated checker contract."""

    def invoke(
        self,
        root: Path,
        consumer: FakeClaimConsumer,
        *arguments: str,
    ) -> tuple[int, str]:
        """Run main with one injected canonical consumer."""
        stdout = io.StringIO()
        with (
            mock.patch.object(
                checker.GraphClaimConsumer,
                "load",
                return_value=consumer,
            ) as load,
            redirect_stdout(stdout),
        ):
            return_code = checker.main(
                ["--root", str(root), *arguments]
            )
        load.assert_called_once_with(root.resolve())
        return return_code, stdout.getvalue()

    def test_supported_claim_uses_metadata_dependency_and_token_context(self) -> None:
        """One supported claim passes through the fixed graph call sequence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_design(root, "- The design must call `run_feature`.")
            consumer = FakeClaimConsumer(
                supported_tokens=frozenset({"run_feature"})
            )

            return_code, output = self.invoke(
                root, consumer, "documents/design/feature.md"
            )

        self.assertEqual(return_code, 0, output)
        self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=1", output)
        self.assertIn("DESIGN_DOC_CLAIMS_SUPPORTED=1", output)
        self.assertIn("DESIGN_DOC_CLAIMS=pass", output)
        self.assertEqual(
            consumer.calls,
            [
                ("status_reason",),
                ("document_metadata", "documents/design/feature.md"),
                ("evidence_paths", "documents/design/feature.md", 3),
                (
                    "token_supported",
                    "documents/design/feature.md",
                    "run_feature",
                ),
            ],
        )

    def test_unsupported_claim_emits_graph_context_finding(self) -> None:
        """An unmatched token remains a typed claim finding without source fallback."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_design(root, "- The design must call `missing_symbol`.")
            consumer = FakeClaimConsumer()

            return_code, output = self.invoke(
                root, consumer, "documents/design/feature.md"
            )

        self.assertEqual(return_code, 1)
        self.assertIn("claim-token-without-evidence", output)
        self.assertIn("token=missing_symbol;graph_context_no_match", output)
        self.assertIn("DESIGN_DOC_CLAIMS=fail", output)

    def test_manifest_lines_are_excluded_by_graph_owned_span(self) -> None:
        """Manifest route text does not become a body claim or local parser input."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_design(root, "Descriptive text without a claim cue.")
            consumer = FakeClaimConsumer()

            return_code, output = self.invoke(
                root, consumer, "documents/design/feature.md"
            )

        self.assertEqual(return_code, 0, output)
        self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=0", output)
        self.assertFalse(
            any(call[0] == "token_supported" for call in consumer.calls)
        )

    def test_nonfresh_status_suppresses_every_context_operation(self) -> None:
        """A nonfresh graph yields one blocker and no partial claim result."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_design(root, "- The design must call `run_feature`.")
            consumer = FakeClaimConsumer(
                status_reason="graph_status:stale;reason=fingerprint"
            )

            return_code, output = self.invoke(
                root, consumer, "documents/design/feature.md"
            )

        self.assertEqual(return_code, 1)
        self.assertIn("graph-integration-unverified", output)
        self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=0", output)
        self.assertEqual(consumer.calls, [("status_reason",)])

    def test_integration_record_must_match_status_fingerprints(self) -> None:
        """Fresh status alone cannot authorize claim evaluation."""
        payload: dict[str, object] = {
            "input_fingerprint": "status-input",
            "graph_fingerprint": "status-graph",
            "integration_record": {
                "schema": "agent-canon.graph.integration.v1",
                "root": ".",
                "db_path": ".agent-canon/knowledge-graph/graph.sqlite",
                "schema_version": "graph_storage_core.v1",
                "profile": "default",
                "source_snapshot_profile": "parent",
                "snapshot_head": "0123456789abcdef",
                "input_fingerprint": "different-input",
                "graph_fingerprint": "status-graph",
                "producer_artifacts": [],
                "verified": True,
                "verification_code": "graph.integration.verified",
            },
        }
        response = checker.GraphResponse(
            schema="agent-canon.graph.status.v1",
            command="status",
            status="fresh",
            payload=payload,
            exit_code=0,
        )
        consumer = checker.GraphClaimConsumer(mock.Mock(), response)

        self.assertEqual(
            consumer.status_reason(),
            "graph_status:invalid;reason=integration-input_fingerprint-mismatch",
        )

    def test_context_transport_failure_suppresses_claim_output(self) -> None:
        """A typed adapter error becomes one graph-unavailable result."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_design(root, "- The design must call `run_feature`.")
            consumer = FakeClaimConsumer(
                metadata_error=checker.GraphClientError("malformed context")
            )

            return_code, output = self.invoke(
                root, consumer, "documents/design/feature.md"
            )

        self.assertEqual(return_code, 1)
        self.assertIn("graph-context:malformed context", output)
        self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=0", output)
        self.assertFalse(
            any(call[0] == "token_supported" for call in consumer.calls)
        )

    def test_json_output_is_canonical_result_projection(self) -> None:
        """JSON output reports graph evidence paths without embedding graph transport."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_design(root, "- The design must call `run_feature`.")
            consumer = FakeClaimConsumer(
                supported_tokens=frozenset({"run_feature"})
            )

            return_code, output = self.invoke(
                root,
                consumer,
                "--format",
                "json",
                "documents/design/feature.md",
            )

        self.assertEqual(return_code, 0, output)
        payload = json.loads(output)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["finding_count"], 0)
        self.assertEqual(
            payload["documents"][0]["evidence_paths"], ["tools/feature.py"]
        )


if __name__ == "__main__":
    unittest.main()
