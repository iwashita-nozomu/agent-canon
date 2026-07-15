"""Tests for graph-backed dependency header validation."""

# @dependency-start
# contract test
# responsibility Tests changed-file dependency header detection through canonical graph status and context.
# upstream design ../../documents/dependency-manifest-design.md canonical graph dependency contract
# upstream implementation ../../tools/agent_tools/check_dependency_headers.py changed-file graph consumer
# upstream implementation ../../tools/agent_tools/graph_client.py canonical graph process adapter
# @dependency-end

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

import check_dependency_headers as checker  # noqa: E402
from graph_client import GraphClientError, GraphResponse  # noqa: E402


def response(
    command: str,
    *,
    status: str = "fresh",
    exit_code: int = 0,
    payload: dict[str, object] | None = None,
) -> GraphResponse:
    """Return one typed graph response used by the fake adapter."""
    return GraphResponse(
        schema=f"agent-canon.graph.{command}.v1",
        command=command,
        status=status,
        payload=payload or {},
        exit_code=exit_code,
    )


def fresh_status() -> GraphResponse:
    """Return the required public-default/producer-parent integration pair."""
    return response(
        "status",
        payload={
            "integration_record": {
                "schema": "agent-canon.graph.integration.v1",
                "profile": "default",
                "source_snapshot_profile": "parent",
                "verified": True,
            }
        },
    )


def manifest_context(
    path: str,
    *,
    present: str = "true",
    contract: tuple[str, ...] = ("tool",),
    responsibility: tuple[str, ...] = ("Owns one test surface.",),
    producer: str = "source-snapshot",
) -> GraphResponse:
    """Return canonical manifest metadata for one path."""
    items: list[dict[str, object]] = [
        {
            "kind": "manifest.present",
            "value": present,
            "source_store": "manifest",
            "producer": producer,
            "authority": "ManifestParser",
        }
    ]
    items.extend(
        {
            "kind": "manifest.contract",
            "value": value,
            "source_store": "manifest",
            "producer": producer,
            "authority": "ManifestParser",
        }
        for value in contract
    )
    items.extend(
        {
            "kind": "manifest.responsibility",
            "value": value,
            "source_store": "manifest",
            "producer": producer,
            "authority": "ManifestParser",
        }
        for value in responsibility
    )
    return response("context", payload={"claim_path": path, "items": items})


class RecordingGraphClient:
    """Fake canonical adapter that records the only permitted operations."""

    def __init__(
        self,
        status_response: GraphResponse | Exception,
        contexts: dict[str, GraphResponse | Exception],
    ) -> None:
        """Initialize canned responses and an empty operation ledger."""
        self.status_response = status_response
        self.contexts = contexts
        self.calls: list[tuple[str, ...]] = []

    def status(self) -> GraphResponse:
        """Record and return one status operation."""
        self.calls.append(("status",))
        if isinstance(self.status_response, Exception):
            raise self.status_response
        return self.status_response

    def context(self, path: str) -> GraphResponse:
        """Record and return one exact path context operation."""
        self.calls.append(("context", path))
        result = self.contexts[path]
        if isinstance(result, Exception):
            raise result
        return result


class DependencyHeaderCheckTest(unittest.TestCase):
    """Exercise the checker without any source-parser or fallback route."""

    def invoke(
        self,
        root: Path,
        client: RecordingGraphClient,
        *arguments: str,
    ) -> tuple[int, str]:
        """Invoke main with one injected graph adapter and capture text output."""
        stdout = io.StringIO()
        with (
            patch.object(checker, "GraphClient", return_value=client) as constructor,
            patch.object(
                sys,
                "argv",
                ["check_dependency_headers.py", "--root", str(root), *arguments],
            ),
            redirect_stdout(stdout),
        ):
            return_code = checker.main()
        constructor.assert_called_once_with(root.resolve(), checker.CANONICAL_GRAPH_EXECUTABLE)
        return return_code, stdout.getvalue()

    def test_uses_one_status_then_sorted_context_operations(self) -> None:
        """Every sorted checkable path receives exactly one canonical context call."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "b.md").write_text("ignored by graph consumer\n", encoding="utf-8")
            (root / "a.py").write_text("ignored by graph consumer\n", encoding="utf-8")
            client = RecordingGraphClient(
                fresh_status(),
                {
                    "a.py": manifest_context("a.py"),
                    "b.md": manifest_context("b.md", contract=("design",)),
                },
            )

            return_code, output = self.invoke(root, client, "b.md", "a.py")

        self.assertEqual(return_code, 0, output)
        self.assertEqual(
            client.calls,
            [("status",), ("context", "a.py"), ("context", "b.md")],
        )
        self.assertEqual(output, "DEPENDENCY_HEADERS=pass\n")

    def test_present_false_maps_to_missing_manifest(self) -> None:
        """The parser-owned absent value maps to the existing missing-block finding."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "tool.py").write_text("plain source\n", encoding="utf-8")
            client = RecordingGraphClient(
                fresh_status(),
                {"tool.py": manifest_context("tool.py", present="false", contract=(), responsibility=())},
            )

            return_code, output = self.invoke(root, client, "tool.py")

        self.assertEqual(return_code, 1)
        self.assertIn("tool.py: missing top dependency manifest block", output)
        self.assertEqual(client.calls, [("status",), ("context", "tool.py")])

    def test_malformed_duplicate_and_wrong_producer_are_findings(self) -> None:
        """Only exact parser-owned cardinality is accepted."""
        cases = {
            "duplicate": manifest_context("doc.md", contract=("design", "tool")),
            "missing": manifest_context("doc.md", responsibility=()),
            "wrong-producer": manifest_context("doc.md", producer="other-producer"),
        }
        for name, context_response in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                (root / "doc.md").write_text("source\n", encoding="utf-8")
                client = RecordingGraphClient(
                    fresh_status(), {"doc.md": context_response}
                )

                return_code, output = self.invoke(root, client, "doc.md")

                self.assertEqual(return_code, 1)
                self.assertIn("DEPENDENCY_HEADERS=fail", output)
                self.assertEqual(
                    client.calls, [("status",), ("context", "doc.md")]
                )

    def test_nonfresh_and_transport_failure_never_query_or_fallback(self) -> None:
        """Invalid graph state suppresses every context operation."""
        cases: tuple[tuple[str, GraphResponse | Exception], ...] = (
            (
                "stale",
                response(
                    "status",
                    status="stale",
                    exit_code=3,
                    payload={"reason": "input fingerprint differs"},
                ),
            ),
            ("transport", GraphClientError("process launch failed")),
        )
        for name, status_response in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                (root / "doc.md").write_text("source\n", encoding="utf-8")
                client = RecordingGraphClient(status_response, {})

                return_code, output = self.invoke(root, client, "doc.md")

                self.assertEqual(return_code, 1)
                self.assertIn("DEPENDENCY_HEADERS=fail", output)
                self.assertEqual(client.calls, [("status",)])

    def test_integration_profile_mismatch_stops_before_context(self) -> None:
        """The public default/source parent profile pair is closed."""
        invalid_status = fresh_status()
        invalid_status.payload["integration_record"]["source_snapshot_profile"] = "default"  # type: ignore[index]
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "doc.md").write_text("source\n", encoding="utf-8")
            client = RecordingGraphClient(invalid_status, {})

            return_code, output = self.invoke(root, client, "doc.md")

        self.assertEqual(return_code, 1)
        self.assertIn("canonical graph integration mismatch", output)
        self.assertEqual(client.calls, [("status",)])


if __name__ == "__main__":
    unittest.main()
