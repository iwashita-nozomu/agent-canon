# @dependency-start
# contract test
# responsibility Verifies canonical graph-backed dependency report projection.
# upstream implementation ../../tools/agent_tools/graph_client.py provides typed graph responses
# upstream implementation ../../tools/agent_tools/render_dependency_manifest_graph.py renders canonical graph facts
# upstream design ../../documents/tools/render_dependency_manifest_graph.md defines projection behavior
# @dependency-end

"""Tests for the canonical dependency graph report renderer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from tools.agent_tools.graph_client import GraphResponse
from tools.agent_tools import render_dependency_manifest_graph as renderer


def graph_response(*, status: str = "fresh", exit_code: int = 0) -> GraphResponse:
    """Return one canonical dependency query response."""
    payload: dict[str, object] = {
        "schema": "agent-canon.graph.query.v1",
        "command": "query",
        "status": status,
        "exit_code": exit_code,
        "graph_fingerprint": "a" * 64,
        "nodes": [
            {"id": "node-a", "path": "docs/a.md"},
            {"id": "node-b", "path": "README.md"},
        ],
        "facts": [
            {
                "id": "fact-a",
                "kind": "dependency",
                "inferred": False,
                "from": "node-a",
                "to": "node-b",
                "producer": "source-snapshot",
                "source_path": "docs/a.md",
                "source_span": {
                    "path": "docs/a.md",
                    "start_line": 4,
                    "start_column": 1,
                    "end_line": 4,
                    "end_column": 42,
                },
                "evidence_ref": "source-snapshot:docs/a.md:4",
                "authority": "ManifestParser",
                "dependency_detail": {
                    "direction": "upstream",
                    "kind": "design",
                    "reason": "repository entrypoint",
                },
            }
        ],
    }
    return GraphResponse(
        schema="agent-canon.graph.query.v1",
        command="query",
        status=status,
        payload=payload,
        exit_code=exit_code,
    )


class FakeGraphClient:
    """Record the exact query selected by the renderer."""

    calls: ClassVar[list[dict[str, object]]] = []
    response: ClassVar[GraphResponse] = graph_response()

    def __init__(self, root: Path, executable: Path) -> None:
        self.root = root
        self.executable = executable

    def query(self, **arguments: object) -> GraphResponse:
        self.calls.append(arguments)
        return self.response


class DependencyManifestGraphRendererTest(unittest.TestCase):
    """Exercise graph-backed projection and atomic bundle behavior."""

    def setUp(self) -> None:
        FakeGraphClient.calls = []
        FakeGraphClient.response = graph_response()

    def test_graph_query_is_the_only_dependency_input(self) -> None:
        """The renderer uses one all-dependency query and retains provenance."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "dependency_graph.tsv"
            with patch.object(renderer, "GraphClient", FakeGraphClient):
                graph_input = renderer.generate_graph_tsv(
                    root,
                    target,
                    scope="full",
                )

        self.assertEqual(
            FakeGraphClient.calls,
            [
                {
                    "all": True,
                    "relation": "dependency",
                    "direction": "both",
                    "depth": 0,
                }
            ],
        )
        self.assertEqual(graph_input.graph_status, "fresh")
        self.assertEqual(len(graph_input.edges), 1)
        edge = graph_input.edges[0]
        self.assertEqual(edge.fact_id, "fact-a")
        self.assertEqual(edge.producer, "source-snapshot")
        self.assertEqual(edge.evidence_ref, "source-snapshot:docs/a.md:4")
        self.assertEqual(edge.authority, "ManifestParser")

    def test_nonfresh_graph_does_not_write_projection(self) -> None:
        """A valid non-fresh graph response is forwarded without fallback output."""
        FakeGraphClient.response = graph_response(status="stale", exit_code=2)
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "dependency_graph.tsv"
            with (
                patch.object(renderer, "GraphClient", FakeGraphClient),
                self.assertRaisesRegex(SystemExit, "2"),
            ):
                renderer.generate_graph_tsv(Path(tmp_dir), target, scope="full")
            self.assertFalse(target.exists())

    def test_bundle_is_atomic_and_carries_graph_provenance(self) -> None:
        """A new bundle publishes all projections from the same typed fact."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "docs").mkdir()
            (root / "docs" / "a.md").write_text("# A\n", encoding="utf-8")
            (root / "README.md").write_text("# Root\n", encoding="utf-8")
            bundle = root / "bundle"
            with patch.object(renderer, "GraphClient", FakeGraphClient):
                manifest, report = renderer.write_bundle(
                    root=root,
                    scope="full",
                    bundle_dir=bundle,
                    title="Dependency Graph",
                )

            self.assertEqual(manifest["status"], "pass")
            self.assertEqual(manifest["checker"]["status"], "fresh")
            self.assertEqual(len(report.edges), 1)
            self.assertEqual(
                {path.name for path in bundle.iterdir()},
                {
                    "dependency_graph.tsv",
                    "dependency_graph.ir.json",
                    "dependency_graph.md",
                    "dependency_graph.dot",
                    "dependency_graph.html",
                    "manifest.json",
                },
            )
            graph_ir = json.loads(
                (bundle / "dependency_graph.ir.json").read_text(encoding="utf-8")
            )
            dependency_edge = next(
                edge for edge in graph_ir["edges"] if edge["kind"] == "design"
            )
            self.assertEqual(dependency_edge["id"], "fact-a")
            self.assertEqual(
                dependency_edge["payload_json"]["producer"],
                "source-snapshot",
            )
            self.assertEqual(
                dependency_edge["payload_json"]["source_span"]["start_line"],
                4,
            )

            with (
                patch.object(renderer, "GraphClient", FakeGraphClient),
                self.assertRaisesRegex(SystemExit, "2"),
            ):
                renderer.write_bundle(
                    root=root,
                    scope="full",
                    bundle_dir=bundle,
                    title="Dependency Graph",
                )

    def test_supplied_tsv_route_is_not_public(self) -> None:
        """The parser rejects the removed alternate fact-input route."""
        parser = renderer.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--graph-tsv", "dependency_graph.tsv"])

    def test_html_projection_is_self_contained(self) -> None:
        """HTML projection embeds graph data without network dependencies."""
        report = renderer.build_report(
            Path("."),
            (
                renderer.Edge(
                    "upstream",
                    "design",
                    "docs/a.md",
                    "README.md",
                    fact_id="fact-a",
                    producer="source-snapshot",
                    evidence_ref="source-snapshot:docs/a.md:4",
                    authority="ManifestParser",
                ),
            ),
        )
        html = renderer.render_html(
            report,
            title="Dependency Graph",
            source_locator="canonical-graph:a",
        )
        self.assertIn('id="graph-data"', html)
        self.assertNotIn('<script src="http', html)
        self.assertNotIn('<link href="http', html)
        self.assertIn('http://www.w3.org/2000/svg', html)


if __name__ == "__main__":
    unittest.main()
