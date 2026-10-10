"""Focused tests for the v2 skill/tool invocation graph contract."""

# @dependency-start
# contract test
# responsibility Verifies skill/dependency graph identities and its generated projections.
# upstream design ../../documents/design/skill-tool-invocation-graph.md owns graph clauses SG-001..SG-015 and artifact readback
# upstream implementation ../../tools/agent/skills/skill_dependency_map.py materializes skill and capability identities, edges, and Mermaid
# upstream implementation ../../tools/validation/semantic/skills/check_skill_tool_invocation_graph.py validates generated JSON/Mermaid equality and stale artifacts
# downstream implementation ../../documents/runtime/skill-dependency-graph.json is the generated machine-readable graph projection
# downstream implementation ../../documents/runtime/skill-dependency-graph.md is the generated Mermaid reader projection
# @dependency-end

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.agent.skills import skill_dependency_map  # noqa: E402
from tools.agent.skills.skill_dependency_map import (  # noqa: E402
    GraphDigestMismatchError,
    GraphSourceMutationError,
    GraphIdentityCollisionError,
    _canonical_bytes,
    _IdentityStore,
    _json_digest_from_graph,
    _normalize_identifier,
    _validate_loaded_graph,
    build_graph,
    check_artifacts,
    DEFAULT_GRAPH_PATH,
    DEFAULT_JSON_PATH,
    readback_mermaid,
    render_graph_mermaid,
    write_artifacts,
)


class SkillToolInvocationGraphTests(unittest.TestCase):
    """Exercise production materialization and checker obligations."""

    def test_graph_requires_external_runtime_when_output_is_implicit(self) -> None:
        """An omitted output never falls back to documents/runtime in the checkout."""
        tracked = (
            PROJECT_ROOT / DEFAULT_GRAPH_PATH,
            PROJECT_ROOT / DEFAULT_JSON_PATH,
        )
        before = tuple(path.read_bytes() for path in tracked)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENT_CANON_RUNTIME_ROOT", None)
            with self.assertRaisesRegex(
                GraphSourceMutationError, "runtime_root_required"
            ):
                write_artifacts(PROJECT_ROOT)
        self.assertEqual(before, tuple(path.read_bytes() for path in tracked))

    def test_graph_default_output_is_external_and_preserves_source(self) -> None:
        """The normal graph route writes beneath an explicit runtime root only."""
        tracked = (
            PROJECT_ROOT / DEFAULT_GRAPH_PATH,
            PROJECT_ROOT / DEFAULT_JSON_PATH,
        )
        before = tuple(path.read_bytes() for path in tracked)
        with tempfile.TemporaryDirectory() as runtime_dir:
            markdown, json_path, _ = write_artifacts(
                PROJECT_ROOT, runtime_root=Path(runtime_dir)
            )
            self.assertTrue(markdown.is_file())
            self.assertTrue(json_path.is_file())
            self.assertTrue(markdown.is_relative_to(Path(runtime_dir)))
            self.assertTrue(json_path.is_relative_to(Path(runtime_dir)))
        self.assertEqual(before, tuple(path.read_bytes() for path in tracked))

    def test_tracked_graph_requires_exact_capability_and_external_evidence(
        self,
    ) -> None:
        """Tracked projection updates require the fixed pair and leave evidence outside it."""
        with (
            tempfile.TemporaryDirectory() as source_dir,
            tempfile.TemporaryDirectory() as runtime_dir,
        ):
            source = Path(source_dir)
            (source / DEFAULT_GRAPH_PATH).parent.mkdir(parents=True)
            (source / DEFAULT_GRAPH_PATH).write_text("before\n", encoding="utf-8")
            (source / DEFAULT_JSON_PATH).write_text("before\n", encoding="utf-8")
            capability_path = source / "capability.json"
            capability_path.write_text(
                json.dumps(
                    {
                        "allowed_paths": [
                            DEFAULT_JSON_PATH.as_posix(),
                            DEFAULT_GRAPH_PATH.as_posix(),
                        ],
                        "purpose": "refresh canonical reader projection",
                        "authority": "test-maintainer",
                    }
                ),
                encoding="utf-8",
            )
            graph = {"skill_count": 1, "commands": [], "tools": [], "edges": []}
            with (
                mock.patch.object(
                    skill_dependency_map, "build_graph", return_value=graph
                ),
                mock.patch(
                    "tools.agent.skills.skill_dependency_map.render_graph_mermaid",
                    return_value="graph\n",
                ),
                mock.patch.object(
                    skill_dependency_map, "_json_text", return_value="{}\n"
                ),
            ):
                write_artifacts(
                    source,
                    output=DEFAULT_GRAPH_PATH,
                    runtime_root=Path(runtime_dir),
                    source_mutation_capability=capability_path,
                )
            evidence = (
                Path(runtime_dir)
                / "graphs"
                / "skill-dependency-graph-source-mutation.json"
            )
            self.assertTrue(evidence.is_file())
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["schema"], "agent_canon.skill_graph_source_mutation.v1"
            )
            self.assertEqual(
                payload["allowed_paths"],
                [DEFAULT_GRAPH_PATH.as_posix(), DEFAULT_JSON_PATH.as_posix()],
            )
            self.assertEqual(payload["changed_paths"], list(payload["allowed_paths"]))
            self.assertTrue(payload["source_tree_unchanged_outside_allowed_paths"])

    def test_tracked_graph_rejects_capability_with_unrelated_target(self) -> None:
        """A capability cannot broaden graph publication beyond the canonical pair."""
        with (
            tempfile.TemporaryDirectory() as source_dir,
            tempfile.TemporaryDirectory() as runtime_dir,
        ):
            source = Path(source_dir)
            (source / DEFAULT_GRAPH_PATH).parent.mkdir(parents=True)
            capability = source / "capability.json"
            capability.write_text(
                json.dumps(
                    {
                        "allowed_paths": ["README.md"],
                        "purpose": "wrong target",
                        "authority": "test-maintainer",
                    }
                ),
                encoding="utf-8",
            )
            graph = {"skill_count": 1, "commands": [], "tools": [], "edges": []}
            with (
                mock.patch.object(
                    skill_dependency_map, "build_graph", return_value=graph
                ),
                mock.patch(
                    "tools.agent.skills.skill_dependency_map.render_graph_mermaid",
                    return_value="graph\n",
                ),
                mock.patch.object(
                    skill_dependency_map, "_json_text", return_value="{}\n"
                ),
            ):
                with self.assertRaisesRegex(
                    GraphSourceMutationError, "target_mismatch"
                ):
                    write_artifacts(
                        source,
                        output=DEFAULT_GRAPH_PATH,
                        runtime_root=Path(runtime_dir),
                        source_mutation_capability=capability,
                    )

    def test_graph_keeps_public_capability_and_dependency_identity(self) -> None:
        """Catalog capabilities remain independent of renderer ToolCall identities."""
        graph = build_graph(PROJECT_ROOT)
        self.assertEqual(graph["schema"], "agent_canon.skill_tool_invocation_graph.v2")
        self.assertEqual(graph["skill_count"], len(graph["skills"]))
        self.assertEqual(graph["phases"], [])
        self.assertEqual(graph["commands"], [])
        self.assertEqual(graph["tools"], [])
        correspondence = graph["design_correspondence"]
        self.assertEqual(len(correspondence["clause_ids"]), 15)
        self.assertEqual(len(correspondence["dic_clause_ids"]), 9)
        self.assertEqual(len(correspondence["implementation_target_paths"]), 11)
        self.assertNotIn("adapter_pairs", correspondence)
        self.assertEqual(
            set(graph["source_snapshot"]),
            {
                "catalog_sha256",
                "dependencies_sha256",
                "reader_index_sha256",
                "route_packet_sha256",
                "source_locators",
            },
        )
        self.assertNotIn("toolcalls", graph)
        self.assertNotIn("coverage", graph)
        self.assertNotIn("coverage_digest", graph)
        self.assertNotIn("toolcall_packet_sha256", graph["source_snapshot"])
        self.assertIn(
            "capability:code-visualization:dependency_manifest_graph",
            {item["ref"]["id"] for item in graph["capabilities"]},
        )
        self.assertNotIn(
            "toolcall", {record["kind"] for record in graph["identity_records"]}
        )
        self.assertNotIn(
            "coverage", {record["kind"] for record in graph["identity_records"]}
        )
        self.assertEqual(
            {edge["display_label"] for edge in graph["edges"]},
            {
                "prerequisite",
                "order",
                "routing",
                "parallel",
            },
        )
        self.assertNotIn(
            "successor", {edge["display_label"] for edge in graph["edges"]}
        )
        self.assertIn(
            "dependency-design", {item["display_label"] for item in graph["skills"]}
        )
        self.assertNotIn("coverage_refs", graph["manifest"])
        self.assertNotIn("coverage_ref", graph["readback"])

    def test_identity_payloads_are_unique_and_all_projections_are_refs(self) -> None:
        """Each full payload appears once and every envelope resolves through a Ref."""
        graph = build_graph(PROJECT_ROOT)
        records = graph["identity_records"]
        keys = {(record["kind"], record["id"]) for record in records}
        payloads = {
            (
                record["kind"],
                json.dumps(
                    record["canonical_payload"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            for record in records
        }
        self.assertEqual(len(keys), len(records))
        self.assertEqual(len(payloads), len(records))
        record_by_id = {record["id"]: record for record in records}
        for field in (
            "skills",
            "phases",
            "commands",
            "tools",
            "capabilities",
        ):
            for item in graph[field]:
                expected_keys = {"ref", "display_label"}
                if "order" in item:
                    expected_keys.add("order")
                if field == "skills":
                    expected_keys.add("kind")
                self.assertEqual(set(item), expected_keys)
                ref = item["ref"]
                self.assertEqual(record_by_id[ref["id"]]["digest"], ref["digest"])
                self.assertNotIn("canonical_payload", item)
        for edge in graph["edges"]:
            for key in ("edge_ref", "source_ref", "target_ref"):
                self.assertEqual(
                    record_by_id[edge[key]["id"]]["digest"], edge[key]["digest"]
                )

    def test_digest_collision_and_reference_failures_are_typed(self) -> None:
        """Identity collisions and tampered references fail with typed codes."""
        store = _IdentityStore()
        first = store.add("skill", "skill:sample", {"id": "sample"})
        self.assertEqual(first, store.add("skill", "skill:sample", {"id": "sample"}))
        with self.assertRaisesRegex(GraphIdentityCollisionError, "identity_collision"):
            store.add("skill", "skill:sample", {"id": "different"})
        with self.assertRaisesRegex(
            GraphIdentityCollisionError, "payload_duplicate:skill:skill:sample"
        ):
            store.add("phase", "phase:sample", {"id": "sample"})
        with self.assertRaisesRegex(GraphDigestMismatchError, "digest_mismatch"):
            store.require({"id": first["id"], "digest": "0" * 64})

    def test_canonical_bytes_sort_maps_and_normalize_identifier_aliases(self) -> None:
        """Nested insertion order and approved Unicode identifier aliases are stable."""
        first = {
            "z": {"b": 2, "a": 1},
            "id": "Ｆｏｏ",
            "alias": "ＦＯＯ",
        }
        second = {
            "alias": "foo",
            "id": "foo",
            "z": {"a": 1, "b": 2},
        }
        self.assertEqual(_canonical_bytes(first), _canonical_bytes(second))
        self.assertEqual(_normalize_identifier("Ｆｏｏ"), "foo")

    def test_cross_checkout_reproducibility_and_no_absolute_runtime_paths(self) -> None:
        """The logical graph is unchanged when the checkout root changes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            alias = Path(tmp_dir) / "checkout-alias"
            alias.symlink_to(PROJECT_ROOT, target_is_directory=True)
            first = build_graph(PROJECT_ROOT)
            second = build_graph(alias)
        self.assertEqual(first["graph_digest"], second["graph_digest"])
        self.assertEqual(first["json_digest"], second["json_digest"])
        serialized = json.dumps(first, ensure_ascii=False, separators=(",", ":"))
        self.assertNotIn(str(PROJECT_ROOT.resolve()), serialized)
        self.assertNotRegex(serialized, r"(?:^|[\" ])/(?:mnt|tmp|home)/")
        self.assertNotIn("execution_argv", serialized)
        self.assertNotIn('"source_root"', serialized)

    def test_mermaid_is_one_actual_readback_complete_block_without_base64(self) -> None:
        """The rendered block carries graph refs and actual source readback metadata."""
        graph = build_graph(PROJECT_ROOT)
        markdown = render_graph_mermaid(graph)
        self.assertEqual(markdown.count("```mermaid"), 1)
        self.assertIn("@dependency-start", markdown)
        self.assertIn(
            "upstream design ../../documents/design/skill-tool-invocation-graph.md",
            markdown,
        )
        self.assertIn(
            "downstream implementation ../../tools/validation/semantic/skills/check_skill_tool_invocation_graph.py",
            markdown,
        )
        self.assertNotIn("base64", markdown.lower())
        self.assertNotIn("coverage_digest", markdown)
        self.assertEqual(readback_mermaid(graph, markdown)["status"], "pass")

    def test_mermaid_syntax_removal_fails_even_when_comments_remain(self) -> None:
        """Actual node and edge statements, not comments, are the readback authority."""
        graph = build_graph(PROJECT_ROOT)
        markdown = render_graph_mermaid(graph)
        node_line = next(
            line
            for line in markdown.splitlines()
            if line.lstrip().startswith("n_skill_dependency_design[")
        )
        without_node = markdown.replace(node_line + "\n", "", 1)
        with self.assertRaisesRegex(ValueError, "actual_node"):
            readback_mermaid(graph, without_node)
        edge_line = next(
            line
            for line in markdown.splitlines()
            if line.strip().startswith("n_") and "-->" in line
        )
        without_edge = markdown.replace(edge_line + "\n", "", 1)
        with self.assertRaisesRegex(ValueError, "actual_edge"):
            readback_mermaid(graph, without_edge)

    def test_json_digest_preimage_excludes_downstream_artifact_fields(self) -> None:
        """JSON self/readback/Mermaid fields remain outside the acyclic preimage."""
        graph = build_graph(PROJECT_ROOT)
        baseline = _json_digest_from_graph(graph)
        changed = copy.deepcopy(graph)
        changed["mermaid_digest"] = "f" * 64
        changed["readback"]["mermaid_digest"] = "e" * 64
        changed["readback"]["json_digest"] = "d" * 64
        self.assertEqual(_json_digest_from_graph(changed), baseline)
        changed["artifact_id"] = "edited"
        self.assertNotEqual(_json_digest_from_graph(changed), baseline)

    def test_checker_rejects_stale_mermaid(self) -> None:
        """Edited Mermaid artifacts fail closed."""
        markdown_path = PROJECT_ROOT / "documents/runtime/skill-dependency-graph.md"
        json_path = PROJECT_ROOT / "documents/runtime/skill-dependency-graph.json"
        original_markdown = markdown_path.read_text(encoding="utf-8")
        original_json = json_path.read_text(encoding="utf-8")
        try:
            markdown_path.write_text(
                original_markdown.replace("%% Edge legend", "%% edited Edge legend", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "stale_artifact"):
                check_artifacts(PROJECT_ROOT)
        finally:
            markdown_path.write_text(original_markdown, encoding="utf-8")
            json_path.write_text(original_json, encoding="utf-8")

    def test_matching_count_rejects_dependency_design_omission(self) -> None:
        """A count-matching machine graph still requires dependency-design identity."""
        machine = copy.deepcopy(build_graph(PROJECT_ROOT))
        machine["skills"] = [
            item
            for item in machine["skills"]
            if item["ref"]["id"] != "skill:dependency-design"
        ]
        machine["skill_count"] = len(machine["skills"])
        machine["json_digest"] = _json_digest_from_graph(machine)
        with self.assertRaisesRegex(ValueError, "dependency-design:omission"):
            _validate_loaded_graph(machine)


if __name__ == "__main__":
    unittest.main()
