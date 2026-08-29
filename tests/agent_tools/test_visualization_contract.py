"""Tests for the exact executable D2.4 visualization contract."""

# @dependency-start
# contract test
# responsibility Tests exact source-universe, manifest, ToolCall, final-artifact readback, and coverage records.
# upstream implementation ../../tools/validation/semantic/tools/visualization_contract.py executable contract under test
# downstream implementation ../../agents/skills/catalog.yaml contract owner and router consume this contract
# @dependency-end

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
import tools.validation.semantic.tools.visualization_contract as contract  # noqa: E402


def source_item(
    item_id: str,
    kind: contract.SourceItemKind,
    origin: contract.SourceItemOrigin,
    ordinal: int,
) -> contract.VisualizationSourceItem:
    """Build one canonical source item."""
    return {
        "item_id": item_id,
        "kind": kind,
        "origin": origin,
        "source_locator": f"source/{item_id}",
        "source_start": ordinal,
        "source_end": ordinal + 1,
        "ordinal": ordinal,
        "payload_json": f'{{"label":"{item_id}"}}',
    }


def source_buckets() -> tuple[
    list[contract.VisualizationSourceItem],
    list[contract.VisualizationSourceItem],
    list[contract.VisualizationSourceItem],
]:
    """Return all eight kinds across the three exact source buckets."""
    literal = [
        source_item("identity:entry", "identity", "literal_request", 0),
        source_item("module:root", "module", "literal_request", 1),
    ]
    owner = [
        source_item("field:name", "field", "owner_closure", 2),
        source_item("phase:render", "phase", "owner_closure", 3),
    ]
    dependency = [
        source_item("edge:a-b", "edge", "dependency_closure", 4),
        source_item("branch:accept", "branch", "dependency_closure", 5),
        source_item("evidence:proof", "evidence", "dependency_closure", 6),
        source_item("time:step-1", "time", "dependency_closure", 7),
    ]
    return literal, owner, dependency


def build_universe() -> contract.VisualizationSourceUniverse:
    """Build one complete exact universe."""
    literal, owner, dependency = source_buckets()
    return contract.build_source_universe(
        request_id="request-1",
        literal_request="visualize the complete implementation",
        literal_items=literal,
        owner_closure=owner,
        dependency_closure=dependency,
        filters=[
            {
                "filter_id": "focus",
                "mode": "view_only",
                "enabled": True,
                "selected_item_ids": ["identity:entry"],
            }
        ],
    )


def coverage_entries(
    universe: contract.VisualizationSourceUniverse,
    *,
    renderer_id: str = "renderer-1",
) -> list[contract.ProjectionCoverageEntry]:
    """Map every source identity one-to-one to final syntax tokens."""
    return [
        {
            "source_item_id": item["item_id"],
            "source_kind": item["kind"],
            "rendered_identity": f"rendered:{item['item_id']}",
            "artifact_locator": [
                contract.serialize_projection_identity(f"rendered:{item['item_id']}")
            ],
            "renderer_id": renderer_id,
            "readback_identity": f"readback:{item['item_id']}",
            "payload_json": '{"projection":"one_to_one"}',
            "view_state": "hidden_view_only" if item["item_id"] == "identity:entry" else "visible",
        }
        for item in universe["items"]
    ]


def expected_readback(
    entries: list[contract.ProjectionCoverageEntry],
    *,
    artifact_id: str = "artifact-1",
    artifact_format: contract.ArtifactFormat = "markdown_mermaid",
    renderer_id: str = "renderer-1",
) -> contract.ReadbackProjection:
    """Build the pre-marker expected projection used to construct a manifest."""
    counts = {kind: 0 for kind in contract.SOURCE_ITEM_KINDS}
    for entry in entries:
        counts[entry["source_kind"]] += 1
    return {
        "artifact_id": artifact_id,
        "artifact_format": artifact_format,
        "renderer_id": renderer_id,
        "identities": {entry["readback_identity"]: entry for entry in entries},
        "readback_counts": counts,
        "coverage_digest": "",
        "status": "pass",
        "violations": [],
    }


def complete_manifest() -> tuple[
    contract.VisualizationSourceUniverse,
    contract.ProjectionCoverageManifest,
]:
    """Build one complete manifest with all eight count-map keys."""
    universe = build_universe()
    entries = coverage_entries(universe)
    manifest = contract.build_projection_coverage_manifest(
        universe,
        artifact_id="artifact-1",
        renderer_id="renderer-1",
        artifact_format="markdown_mermaid",
        entries=entries,
        readback=expected_readback(entries),
    )
    return universe, manifest


def projection_tool_calls(
    universe: contract.VisualizationSourceUniverse,
    *,
    artifact_id: str = "artifact-1",
    renderer_id: str = "renderer-1",
    artifact_format: contract.ArtifactFormat = "markdown_mermaid",
    adapter_tool_id: contract.ToolID = (
        "agent_canon.visualization.adapter.document_mermaid"
    ),
    adapter_fields: dict[str, contract.JsonValue] | None = None,
) -> tuple[contract.ToolCall, contract.ToolCall]:
    """Return one exact owner-first ToolCall pair for a projection."""
    shared: dict[str, contract.JsonValue] = {
        "request_id": universe["request_id"],
        "literal_request": universe["literal_request"],
        "literal_items": [
            item for item in universe["items"] if item["origin"] == "literal_request"
        ],
        "owner_closure": universe["owner_closure"],
        "dependency_closure": universe["dependency_closure"],
        "artifact_id": artifact_id,
        "renderer_id": renderer_id,
        "artifact_format": artifact_format,
        "filters": universe["filters"],
    }
    owner: contract.ToolCall = {
        "schema": "agent_canon.visualization_tool_call.v1",
        "tool_id": "agent_canon.visualization.coverage",
        "argument_schema": "agent_canon.visualization.arguments.coverage.v1",
        "arguments": dict(shared),
    }
    adapter_arguments = dict(shared)
    adapter_arguments.update(adapter_fields or {"document_locator": "artifact.md"})
    adapter: contract.ToolCall = {
        "schema": "agent_canon.visualization_tool_call.v1",
        "tool_id": adapter_tool_id,
        "argument_schema": contract.TOOL_ARGUMENT_SCHEMAS[adapter_tool_id],
        "arguments": adapter_arguments,
    }
    return owner, adapter


class VisualizationContractTest(unittest.TestCase):
    """Verify the exact D2.4 contract and deterministic failure behavior."""

    def test_public_api_has_seven_required_owner_functions(self) -> None:
        """The public API exposes the seven required owner functions."""
        for function_name in (
            "build_source_universe",
            "build_projection_coverage_manifest",
            "validate_projection_coverage",
            "serialize_tool_call",
            "serialize_projection_identity",
            "serialize_projection_coverage_manifest",
            "readback_projection",
        ):
            self.assertTrue(callable(getattr(contract, function_name)))

    def test_universe_preserves_three_buckets_and_deterministic_identity(self) -> None:
        """Literal, owner, and dependency records form one sorted immutable set."""
        first = build_universe()
        literal, owner, dependency = source_buckets()
        second = contract.build_source_universe(
            request_id="request-1",
            literal_request="visualize the complete implementation",
            literal_items=list(reversed(literal)),
            owner_closure=list(reversed(owner)),
            dependency_closure=list(reversed(dependency)),
            filters=[
                {
                    "filter_id": "focus",
                    "mode": "view_only",
                    "enabled": True,
                    "selected_item_ids": ["identity:entry"],
                }
            ],
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first["items"]), 8)
        self.assertEqual(first["source_fingerprint"], second["source_fingerprint"])

    def test_manifest_has_complete_eight_kind_counts_and_no_omission(self) -> None:
        """Every count map has all eight kinds and every identity maps one-to-one."""
        _, manifest = complete_manifest()
        expected_keys = set(contract.SOURCE_ITEM_KINDS)
        self.assertEqual(set(manifest["source_counts"]), expected_keys)
        self.assertEqual(set(manifest["rendered_counts"]), expected_keys)
        self.assertEqual(set(manifest["readback_counts"]), expected_keys)
        self.assertEqual(manifest["omitted_item_ids"], [])
        self.assertEqual(manifest["violations"], [])
        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(len(manifest["coverage_digest"]), 64)

    def test_final_artifact_readback_reconstructs_every_identity(self) -> None:
        """Marker data alone is insufficient; all final syntax tokens are read back."""
        universe, manifest = complete_manifest()
        owner_call, adapter_call = projection_tool_calls(universe)
        marker = contract.serialize_projection_coverage_manifest(
            manifest,
            owner_tool_call=owner_call,
            adapter_tool_call=adapter_call,
        )
        tokens = "\n".join(
            f"    %% {locator}"
            for entry in manifest["entries"]
            for locator in entry["artifact_locator"]
        )
        artifact = (
            f"<!-- {marker} -->\n"
            "```mermaid\n"
            "flowchart TD\n"
            f"{tokens}\n"
            "```\n"
        )
        readback = contract.readback_projection(
            artifact,
            "markdown_mermaid",
            artifact_id="artifact-1",
            renderer_id="renderer-1",
        )
        report = contract.validate_projection_coverage(
            universe,
            manifest,
            readback=readback,
        )
        self.assertEqual(readback["status"], "pass")
        self.assertEqual(len(readback["identities"]), 8)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["source_counts"], report["readback_counts"])

    def test_missing_final_token_returns_complete_typed_failure(self) -> None:
        """A formatted artifact that loses tokens fails without pruning violations."""
        universe, manifest = complete_manifest()
        owner_call, adapter_call = projection_tool_calls(universe)
        marker = contract.serialize_projection_coverage_manifest(
            manifest,
            owner_tool_call=owner_call,
            adapter_tool_call=adapter_call,
        )
        artifact = (
            f"<!-- {marker} -->\n"
            "```mermaid\nflowchart TD\n```\n"
        )
        readback = contract.readback_projection(
            artifact,
            "markdown_mermaid",
            artifact_id="artifact-1",
            renderer_id="renderer-1",
        )
        report = contract.validate_projection_coverage(
            universe,
            manifest,
            readback=readback,
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            sum(violation["code"] == "missing_token" for violation in report["violations"]),
            8,
        )

    def test_all_six_tool_id_schema_pairs_serialize_canonically(self) -> None:
        """Every fixed ToolID accepts only its paired schema and exact argument record."""
        locator_fields = {
            "agent_canon.visualization.coverage": {},
            "agent_canon.visualization.adapter.dependency_manifest": {
                "dependency_manifest_locator": "dependency_graph.tsv"
            },
            "agent_canon.visualization.adapter.algorithm_flowchart": {
                "jit_ir_locator": "jit-ir.json",
                "lean_evidence_locator": "Evidence.lean",
                "theorem_graph_locator": "theorem-graph.json",
            },
            "agent_canon.visualization.adapter.document_mermaid": {
                "document_locator": "document.md"
            },
            "agent_canon.visualization.adapter.repository_graph": {
                "repository_locator": "."
            },
            "agent_canon.visualization.adapter.knowledge_graph": {
                "graph_locator": "knowledge.sqlite"
            },
        }
        for tool_id, argument_schema in contract.TOOL_ARGUMENT_SCHEMAS.items():
            with self.subTest(tool_id=tool_id):
                arguments: dict[str, contract.JsonValue] = {
                    "request_id": "route-1",
                    "literal_request": "$code-visualization",
                    "literal_items": [],
                    "owner_closure": [],
                    "dependency_closure": [],
                    "artifact_id": "artifact-1",
                    "renderer_id": "renderer-1",
                    "artifact_format": "html",
                    "filters": [],
                    **locator_fields[tool_id],
                }
                call: contract.ToolCall = {
                    "schema": "agent_canon.visualization_tool_call.v1",
                    "tool_id": tool_id,
                    "argument_schema": argument_schema,
                    "arguments": arguments,
                }
                serialized = contract.serialize_tool_call(call)
                self.assertIn(tool_id, serialized)
                self.assertIn(argument_schema, serialized)
                self.assertNotIn("render_dependency_manifest_graph.py", serialized)

    def test_tool_call_shape_and_argument_rejections_are_typed(self) -> None:
        """Every malformed runtime shape raises one deterministic ValueError."""
        valid_arguments: dict[str, object] = {
            "request_id": "route-1",
            "literal_request": "visualize",
            "literal_items": [],
            "owner_closure": [],
            "dependency_closure": [],
            "artifact_id": "artifact-1",
            "renderer_id": "renderer-1",
            "artifact_format": "html",
        }
        valid: dict[str, object] = {
            "schema": "agent_canon.visualization_tool_call.v1",
            "tool_id": "agent_canon.visualization.coverage",
            "argument_schema": "agent_canon.visualization.arguments.coverage.v1",
            "arguments": valid_arguments,
        }
        cases: tuple[tuple[object, str], ...] = (
            (None, "invalid_tool_call:tool_call"),
            ({}, "invalid_tool_call:fields"),
            ({**valid, "extra": True}, "invalid_tool_call:fields"),
            ({**valid, "schema": 1}, "invalid_tool_call:schema"),
            ({**valid, "tool_id": ["unhashable"]}, "invalid_tool_call:tool_id"),
            (
                {**valid, "argument_schema": 1},
                "invalid_tool_call:argument_schema",
            ),
            ({**valid, "arguments": []}, "invalid_tool_call:arguments"),
            (
                {
                    **valid,
                    "arguments": {
                        **valid_arguments,
                        "unexpected": True,
                    },
                },
                "invalid_tool_call:argument_fields",
            ),
        )
        for supplied, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, f"^{message}$"):
                    contract.serialize_tool_call(supplied)

    def test_projection_serializers_require_owner_first_complete_manifest(self) -> None:
        """Identity and marker serialization expose only the gated public API."""
        universe, manifest = complete_manifest()
        owner_call, adapter_call = projection_tool_calls(universe)
        marker = contract.serialize_projection_coverage_manifest(
            manifest,
            owner_tool_call=owner_call,
            adapter_tool_call=adapter_call,
        )
        self.assertTrue(marker.startswith("agent_canon_visualization_coverage_v1:"))
        self.assertTrue(
            contract.serialize_projection_identity("rendered:item").startswith(
                "agent_canon_visualization_identity_v1:"
            )
        )
        for invalid_identity in ("", None, 1):
            with self.subTest(invalid_identity=invalid_identity):
                with self.assertRaisesRegex(
                    ValueError,
                    "^invalid_identity:projection$",
                ):
                    contract.serialize_projection_identity(invalid_identity)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "^invalid_tool_call:owner_tool_id$"):
            contract.serialize_projection_coverage_manifest(
                manifest,
                owner_tool_call=adapter_call,
                adapter_tool_call=owner_call,
            )
        mismatched_adapter = {
            **adapter_call,
            "arguments": {
                **adapter_call["arguments"],
                "artifact_id": "other-artifact",
            },
        }
        with self.assertRaisesRegex(ValueError, "^invalid_tool_call:artifact_id$"):
            contract.serialize_projection_coverage_manifest(
                manifest,
                owner_tool_call=owner_call,
                adapter_tool_call=mismatched_adapter,  # type: ignore[arg-type]
            )

    def test_algorithm_readback_enforces_one_mermaid_and_no_table(self) -> None:
        """Algorithm structure failures are typed by canonical final readback."""
        renderer_id = "agent_canon.visualization.adapter.algorithm_flowchart"
        universe = build_universe()
        entries = coverage_entries(universe, renderer_id=renderer_id)
        manifest = contract.build_projection_coverage_manifest(
            universe,
            artifact_id="algorithm.md",
            renderer_id=renderer_id,
            artifact_format="markdown_mermaid",
            entries=entries,
            readback=expected_readback(
                entries,
                artifact_id="algorithm.md",
                renderer_id=renderer_id,
            ),
        )
        owner_call, adapter_call = projection_tool_calls(
            universe,
            artifact_id="algorithm.md",
            renderer_id=renderer_id,
            adapter_tool_id=(
                "agent_canon.visualization.adapter.algorithm_flowchart"
            ),
            adapter_fields={
                "jit_ir_locator": "jit-ir.json",
                "lean_evidence_locator": "Evidence.lean",
                "theorem_graph_locator": "theorem-graph.json",
            },
        )
        marker = contract.serialize_projection_coverage_manifest(
            manifest,
            owner_tool_call=owner_call,
            adapter_tool_call=adapter_call,
        )
        tokens = "\n".join(
            f"  %% {locator}"
            for entry in entries
            for locator in entry["artifact_locator"]
        )
        valid_diagram = f"<!-- {marker} -->\n```mermaid\nflowchart LR\n{tokens}\n```\n"
        valid = contract.readback_projection(
            valid_diagram,
            "markdown_mermaid",
            artifact_id="algorithm.md",
            renderer_id=renderer_id,
        )
        self.assertEqual(valid["status"], "pass")

        two_diagrams = valid_diagram + "\n```mermaid\nflowchart LR\n  extra[Extra]\n```\n"
        diagram_failure = contract.readback_projection(
            two_diagrams,
            "markdown_mermaid",
            artifact_id="algorithm.md",
            renderer_id=renderer_id,
        )
        self.assertIn(
            "diagram_count_mismatch",
            {violation["code"] for violation in diagram_failure["violations"]},
        )

        table_failure = contract.readback_projection(
            valid_diagram + "\n| Step | State |\n| --- | --- |\n| 1 | start |\n",
            "markdown_mermaid",
            artifact_id="algorithm.md",
            renderer_id=renderer_id,
        )
        self.assertIn(
            "table_fallback",
            {violation["code"] for violation in table_failure["violations"]},
        )

        one_column_table_failure = contract.readback_projection(
            valid_diagram + "\n| Step |\n| --- |\n| start |\n",
            "markdown_mermaid",
            artifact_id="algorithm.md",
            renderer_id=renderer_id,
        )
        self.assertIn(
            "table_fallback",
            {
                violation["code"]
                for violation in one_column_table_failure["violations"]
            },
        )

    def test_tsv_readback_requires_exact_sidecar_and_sibling_final_artifact(self) -> None:
        """TSV readback consumes an external sidecar and scans the sibling TSV."""
        universe = contract.build_source_universe(
            request_id="tsv-1",
            literal_request="render TSV",
            literal_items=[source_item("identity:a", "identity", "literal_request", 0)],
            owner_closure=[],
            dependency_closure=[],
        )
        entry: contract.ProjectionCoverageEntry = {
            "source_item_id": "identity:a",
            "source_kind": "identity",
            "rendered_identity": "rendered:a",
            "artifact_locator": ["a.md"],
            "renderer_id": "renderer-1",
            "readback_identity": "readback:a",
            "payload_json": '{"projection":"one_to_one"}',
            "view_state": "visible",
        }
        expected: contract.ReadbackProjection = {
            "artifact_id": "dependency_graph",
            "artifact_format": "tsv",
            "renderer_id": "renderer-1",
            "identities": {"readback:a": entry},
            "readback_counts": {
                **{kind: 0 for kind in contract.SOURCE_ITEM_KINDS},
                "identity": 1,
            },
            "coverage_digest": "",
            "status": "pass",
            "violations": [],
        }
        manifest = contract.build_projection_coverage_manifest(
            universe,
            artifact_id="dependency_graph",
            renderer_id="renderer-1",
            artifact_format="tsv",
            entries=[entry],
            readback=expected,
        )
        owner_call, adapter_call = projection_tool_calls(
            universe,
            artifact_id="dependency_graph",
            artifact_format="tsv",
            adapter_tool_id=(
                "agent_canon.visualization.adapter.dependency_manifest"
            ),
            adapter_fields={"dependency_manifest_locator": "dependency_graph.tsv"},
        )
        marker = contract.serialize_projection_coverage_manifest(
            manifest,
            owner_tool_call=owner_call,
            adapter_tool_call=adapter_call,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "dependency_graph.tsv").write_text(
                "direction\tkind\tsource\ttarget\nupstream\tdesign\ta.md\tb.md\n",
                encoding="utf-8",
            )
            sidecar = root / "dependency_graph.coverage.json"
            sidecar.write_text(
                f'"{marker}"',
                encoding="utf-8",
            )
            readback = contract.readback_projection(
                sidecar,
                "tsv",
                artifact_id="dependency_graph",
                renderer_id="renderer-1",
            )
        self.assertEqual(readback["status"], "pass")

    def test_issue694_resource_parser_distinguishes_data_from_resource_context(self) -> None:
        """Offline resource checks inspect DOM/CSS/executable JS contexts only."""
        ordinary = contract._HTMLReadbackParser()
        ordinary.feed(
            "<p>https://example.invalid fetch( XMLHttpRequest import(</p>"
            '<script>const text = "fetch(https://example.invalid)";</script>'
            "<style>/* url(https://example.invalid/comment) */ .x { content: 'url(https://example.invalid/string)' }</style>"
        )
        ordinary.close()
        self.assertEqual(ordinary.violations, [])

        external = contract._HTMLReadbackParser()
        external.feed(
            '<img src="https://example.invalid/image.png">'
            '<style>.x { background: url(https://example.invalid/image.png) }</style>'
            '<script>fetch("https://example.invalid/api");</script>'
        )
        external.close()
        self.assertIn("external_resource", {v["code"] for v in external.violations})
        self.assertIn("script_network_api", {v["code"] for v in external.violations})

        local = contract._HTMLReadbackParser()
        local.feed(
            '<img src="#embedded">'
            '<style>.x { background: url(data:image/png;base64,AAAA) }</style>'
            '<script>const value = /fetch\\(/;</script>'
        )
        local.close()
        self.assertEqual(local.violations, [])

    def test_issue694_svg_descendant_resources_and_module_imports_are_contextual(self) -> None:
        """SVG descendants and static module imports are resource-graph inputs."""
        svg_external = contract._HTMLReadbackParser()
        svg_external.feed('<svg><g><path fill="url(https://example.invalid/x.svg)"></path></g></svg>')
        svg_external.close()
        self.assertIn(
            "external_resource",
            {violation["code"] for violation in svg_external.violations},
        )

        svg_local = contract._HTMLReadbackParser()
        svg_local.feed('<svg><g><path fill="url(#local-marker)"></path></g></svg>')
        svg_local.close()
        self.assertEqual(svg_local.violations, [])

        svg_scalars = contract._HTMLReadbackParser()
        svg_scalars.feed('<svg><path fill="red" stroke="none"></path></svg>')
        svg_scalars.close()
        self.assertEqual(svg_scalars.violations, [])

        module_import = contract._HTMLReadbackParser()
        module_import.feed('<script type="module">import "./other.js";</script>')
        module_import.close()
        self.assertIn(
            "script_network_api",
            {violation["code"] for violation in module_import.violations},
        )

        module_data = contract._HTMLReadbackParser()
        module_data.feed(
            '<script type="module">'
            '// import "./comment.js";\n'
            'const label = "import \'./string.js\'";\n'
            "import.meta.url;"
            "</script>"
        )
        module_data.close()
        self.assertEqual(module_data.violations, [])

        non_executable = contract._HTMLReadbackParser()
        non_executable.feed(
            '<script type="text/plain">fetch("https://example.invalid");</script>'
            '<script type="application/xml">import "./data.js";</script>'
        )
        non_executable.close()
        self.assertEqual(non_executable.violations, [])

        regex_context = contract._HTMLReadbackParser()
        regex_context.feed(
            '<script>return /fetch\\(/; if (ready) /XMLHttpRequest/.test(value);</script>'
        )
        regex_context.close()
        self.assertEqual(regex_context.violations, [])


if __name__ == "__main__":
    unittest.main()
