"""Tests for the graph-backed tool/convention drift checker."""

# @dependency-start
# contract test
# responsibility Tests tool drift from canonical graph facts and structured catalog evidence.
# upstream implementation ../../tools/agent_tools/tool_drift.py graph-backed checker
# upstream implementation ../../tools/agent_tools/graph_client.py canonical graph adapter
# upstream design ../../documents/dependency-manifest-design.md graph relation contract
# @dependency-end

from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

from tools.agent_tools import tool_drift


def fact(
    source: str,
    target: str,
    *,
    direction: str,
    kind: str,
    identifier: str = "fact",
) -> tool_drift.GraphDependencyFact:
    """Return one provenance-complete canonical dependency fact."""
    return tool_drift.GraphDependencyFact(
        id=identifier,
        direction=direction,
        kind=kind,
        source=source,
        target=target,
        reason="fixture contract",
        producer="source-snapshot",
        source_path=source,
        source_span={
            "path": source,
            "start_line": 1,
            "start_column": 1,
            "end_line": 1,
            "end_column": 10,
        },
        evidence_ref=f"{source}:1",
        authority="ManifestParser",
    )


@dataclass(frozen=True)
class FakeGraphResult:
    """Minimal result surface consumed by tool_drift."""

    status: str
    exit_code: int
    dependency_facts: tuple[tool_drift.GraphDependencyFact, ...]
    payload: dict[str, object]


class RecordingGraphClient:
    """Record the sole all-dependency query."""

    def __init__(self, result: FakeGraphResult) -> None:
        """Initialize one canned query result."""
        self.result = result
        self.calls: list[dict[str, object]] = []

    def query(self, **arguments: object) -> FakeGraphResult:
        """Record and return one query."""
        self.calls.append(arguments)
        return self.result


class CheckToolConventionDriftTest(unittest.TestCase):
    """Exercise graph relation and catalog closure without source parsing."""

    def test_link_finding_matrix_preserves_existing_contracts(self) -> None:
        """Missing, directional, reverse, and kind mismatch findings stay stable."""
        direct_required = tool_drift.ToolContract(
            "fixture",
            "tool.py",
            (tool_drift.LinkCheck("target.md"),),
        )
        reverse_required = tool_drift.ToolContract(
            "fixture",
            "tool.py",
            (tool_drift.LinkCheck("target.md", reverse_required=True),),
        )
        direct = fact(
            "tool.py", "target.md", direction="upstream", kind="design"
        )
        reverse = fact(
            "target.md",
            "tool.py",
            direction="downstream",
            kind="implementation",
            identifier="reverse",
        )
        wrong_reverse = fact(
            "target.md",
            "tool.py",
            direction="downstream",
            kind="environment",
            identifier="wrong-reverse",
        )

        missing = tool_drift.check_link(
            direct_required, direct_required.links[0], ()
        )
        missing_direct = tool_drift.check_link(
            direct_required, direct_required.links[0], (reverse,)
        )
        missing_reverse = tool_drift.check_link(
            reverse_required, reverse_required.links[0], (direct,)
        )
        mismatch = tool_drift.check_link(
            reverse_required, reverse_required.links[0], (direct, wrong_reverse)
        )

        self.assertEqual([item.kind for item in missing], ["missing-manifest-link"])
        self.assertEqual(
            [item.kind for item in missing_direct], ["missing-direct-manifest-link"]
        )
        self.assertEqual(
            [item.kind for item in missing_reverse],
            ["missing-reverse-manifest-link"],
        )
        self.assertEqual([item.kind for item in mismatch], ["kind-mismatch"])

    def test_run_checks_uses_one_exact_graph_query_for_all_contracts(self) -> None:
        """One canonical query supplies every selected link contract."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "tool.py").write_text("tool\n", encoding="utf-8")
            (root / "target.md").write_text("target\n", encoding="utf-8")
            contract = tool_drift.ToolContract(
                "fixture",
                "tool.py",
                (tool_drift.LinkCheck("target.md", reverse_required=True),),
            )
            client = RecordingGraphClient(
                FakeGraphResult(
                    status="fresh",
                    exit_code=0,
                    dependency_facts=(
                        fact(
                            "tool.py",
                            "target.md",
                            direction="upstream",
                            kind="design",
                        ),
                        fact(
                            "target.md",
                            "tool.py",
                            direction="downstream",
                            kind="implementation",
                            identifier="reverse",
                        ),
                    ),
                    payload={"graph_fingerprint": "fixture"},
                )
            )
            with (
                mock.patch.object(tool_drift, "CONTRACTS", (contract,)),
                mock.patch.object(
                    tool_drift, "GraphClient", return_value=client
                ) as constructor,
            ):
                findings = tool_drift.run_checks(root, ())

        self.assertEqual(findings, [])
        constructor.assert_called_once_with(
            root.resolve(), tool_drift.CANONICAL_GRAPH_EXECUTABLE
        )
        self.assertEqual(
            client.calls,
            [
                {
                    "all": True,
                    "relation": "dependency",
                    "direction": "both",
                    "depth": 0,
                }
            ],
        )

    def test_nonfresh_graph_fails_without_empty_edge_fallback(self) -> None:
        """A nonfresh query is a typed failure, not an empty contract graph."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            contract = tool_drift.ToolContract("fixture", "tool.py", ())
            client = RecordingGraphClient(
                FakeGraphResult(
                    status="stale",
                    exit_code=3,
                    dependency_facts=(),
                    payload={"reason": "fingerprint differs"},
                )
            )
            with (
                mock.patch.object(tool_drift, "CONTRACTS", (contract,)),
                mock.patch.object(tool_drift, "GraphClient", return_value=client),
            ):
                with self.assertRaisesRegex(
                    tool_drift.GraphClientError,
                    "status=stale reason=fingerprint differs",
                ):
                    tool_drift.run_checks(root, ())

        self.assertEqual(len(client.calls), 1)

    def test_catalog_findings_remain_structured_without_header_finding(self) -> None:
        """YAML, stale, and retired findings remain catalog-owned."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog = root / "tools/catalog.yaml"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(
                "\n".join(
                    [
                        "version: 1",
                        "entries:",
                        "  - id: stale",
                        "    path: tools/missing.py",
                        "    status: canonical",
                        "  - id: retired",
                        "    path: tools/legacy/old.py",
                        "    status: legacy_provenance",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            findings = tool_drift.check_catalog_entries(root)

        kinds = [item.kind for item in findings]
        self.assertEqual(kinds.count("stale-catalog-entry"), 2)
        self.assertEqual(kinds.count("retired-legacy-tool"), 1)
        self.assertNotIn("missing-dependency-header", kinds)

    def test_invalid_catalog_shape_remains_a_yaml_finding(self) -> None:
        """Catalog structure remains YAML-owned and independent of graph facts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog = root / "tools/catalog.yaml"
            catalog.parent.mkdir(parents=True)
            catalog.write_text("entries: not-a-list\n", encoding="utf-8")

            findings = tool_drift.check_catalog_entries(root)

        self.assertEqual([item.kind for item in findings], ["invalid-catalog"])

    def test_source_has_graph_symbols_and_no_legacy_parser_symbols(self) -> None:
        """Static symbol closure rejects the removed manifest parser route."""
        source = (PROJECT_ROOT / "tools/agent_tools/tool_drift.py").read_text(
            encoding="utf-8"
        )
        for required in ("GraphClient", "GraphDependencyFact", "dependency_facts"):
            self.assertIn(required, source)
        for forbidden in (
            "ManifestEdge",
            "HEADER_SCAN_LINES",
            "MANIFEST_FIELD_COUNT",
            "MANIFEST_REASON_MAX_SPLIT",
            "has_dependency_manifest",
            "strip_manifest_line",
            "normalize_target",
            "manifest_edges",
        ):
            self.assertNotIn(forbidden, source)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


if __name__ == "__main__":
    unittest.main()
