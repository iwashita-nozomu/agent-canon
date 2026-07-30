"""Focused tests for the v2 skill/tool invocation graph contract."""

# @dependency-start
# contract test
# responsibility Verifies the complete typed skill/tool invocation graph and its generated projections.
# upstream design ../../documents/design/skill-tool-invocation-graph.md owns graph clauses SG-001..SG-015 and artifact readback
# upstream implementation ../../tools/agent_tools/skill_dependency_map.py materializes identities, phases, commands, tools, edges, and Mermaid
# upstream implementation ../../tools/agent_tools/check_skill_tool_invocation_graph.py validates generated JSON/Mermaid equality and stale artifacts
# downstream implementation ../../documents/runtime/skill-dependency-graph.json is the generated machine-readable graph projection
# downstream implementation ../../documents/runtime/skill-dependency-graph.md is the generated Mermaid reader projection
# @dependency-end

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PROJECT_ROOT / "tools" / "agent_tools"
sys.path.insert(0, str(TOOLS_ROOT))

from agent_canon_source_root import resolve_agent_canon_source_root  # noqa: E402
from skill_dependency_map import (  # noqa: E402
    GraphDigestMismatchError,
    GraphIdentityCollisionError,
    _canonical_bytes,
    _IdentityStore,
    _json_digest_from_graph,
    _normalize_identifier,
    build_graph,
    check_artifacts,
    readback_mermaid,
    render_graph_mermaid,
)
from skill_route_catalog import (  # noqa: E402
    derive_skill_invocation_order,
    load_skill_route_rules,
)
from skill_tool_commands import packet_for_skill  # noqa: E402


class SkillToolInvocationGraphTests(unittest.TestCase):
    """Exercise production materialization and checker obligations."""

    def test_complete_v2_universe_and_edge_types(self) -> None:
        """All skills, phases, resolved commands, tools, and edge kinds are present."""
        graph = build_graph(PROJECT_ROOT)
        self.assertEqual(graph["schema"], "agent_canon.skill_tool_invocation_graph.v2")
        self.assertEqual(graph["skill_count"], 60)
        self.assertEqual(len(graph["skills"]), 60)
        self.assertEqual(len(graph["phases"]), 180)
        self.assertEqual(len(graph["commands"]), 387)
        self.assertGreater(len(graph["tools"]), 0)
        correspondence = graph["design_correspondence"]
        self.assertEqual(len(correspondence["clause_ids"]), 15)
        self.assertEqual(len(correspondence["dic_clause_ids"]), 9)
        self.assertEqual(len(correspondence["implementation_target_paths"]), 11)
        self.assertEqual(len(correspondence["adapter_pairs"]), 5)
        self.assertEqual(
            set(graph["source_snapshot"]),
            {
                "catalog_sha256",
                "dependencies_sha256",
                "reader_index_sha256",
                "route_packet_sha256",
                "command_packet_sha256",
                "toolcall_packet_sha256",
                "source_locators",
            },
        )
        self.assertEqual(
            {edge["display_label"] for edge in graph["edges"]},
            {
                "prerequisite",
                "successor",
                "order",
                "routing",
                "parallel",
                "invocation",
                "tool-resolution",
            },
        )
        self.assertIn(
            "dependency-design", {item["display_label"] for item in graph["skills"]}
        )
        edge_pairs = {
            (edge["display_label"], edge["source_ref"]["id"], edge["target_ref"]["id"])
            for edge in graph["edges"]
        }
        for skill in (item["display_label"] for item in graph["skills"]):
            for phase in ("required", "conditional", "maintenance"):
                self.assertIn(
                    ("invocation", f"skill:{skill}", f"phase:{skill}:{phase}"),
                    edge_pairs,
                )
        self.assertIn(
            (
                "order",
                "toolcall:canonical-owner",
                "toolcall:dependency-manifest-adapter",
            ),
            edge_pairs,
        )

    def test_every_canonical_packet_command_has_phase_and_ref(self) -> None:
        """Canonical command resolution is materialized once per phase/ordinal."""
        graph = build_graph(PROJECT_ROOT)
        records = {record["id"]: record for record in graph["identity_records"]}
        command_projections = graph["commands"]
        self.assertEqual(len(command_projections), 387)
        resolution = resolve_agent_canon_source_root(PROJECT_ROOT)
        for skill in (item["display_label"] for item in graph["skills"]):
            packet = packet_for_skill(resolution, skill)
            for phase, rows in (
                ("required", packet.resolved_required_commands),
                ("conditional", packet.resolved_conditional_commands),
                ("maintenance", packet.resolved_maintenance_commands),
            ):
                for index, row in enumerate(rows):
                    projection = next(
                        item
                        for item in command_projections
                        if item["display_label"] == row[0]
                        and records[item["ref"]["id"]]["canonical_payload"]["skill_id"]
                        == skill
                        and records[item["ref"]["id"]]["canonical_payload"][
                            "source_locator"
                        ].endswith(f".{phase}[{index}]")
                    )
                    self.assertEqual(
                        records[projection["ref"]["id"]]["kind"], "command"
                    )

    def test_invocation_order_is_derived_and_command_order_is_immutable(self) -> None:
        """Ordinals follow the existing order function and #461 report order."""
        graph = build_graph(PROJECT_ROOT)
        rules = load_skill_route_rules(PROJECT_ROOT)
        skill_ids = tuple(item["display_label"] for item in graph["skills"])
        expected_order = derive_skill_invocation_order(skill_ids, rules)
        observed_order = tuple(
            item["ref"]["id"].removeprefix("skill:")
            for item in sorted(
                graph["invocation_order"], key=lambda item: item["order"]
            )
        )
        self.assertEqual(observed_order, expected_order)
        resolution = resolve_agent_canon_source_root(PROJECT_ROOT)
        packet = packet_for_skill(resolution, "result-artifact-writeout")
        archive_commands = [
            row[0]
            for row in packet.resolved_conditional_commands
            if "runtime_log_archive_git.py" in row[0]
        ]
        self.assertEqual(len(archive_commands), 2)
        self.assertIn("archive-agent-report", archive_commands[0])
        self.assertEqual(archive_commands[1].split()[-1], "push")
        self.assertNotIn("sync", " ".join(archive_commands))
        self.assertNotIn("status", " ".join(archive_commands))

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
            "toolcalls",
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
        self.assertNotIn("source_root", serialized)

    def test_mermaid_is_one_actual_readback_complete_block_without_base64(self) -> None:
        """The rendered block carries graph/coverage refs and actual readback metadata."""
        graph = build_graph(PROJECT_ROOT)
        markdown = render_graph_mermaid(graph)
        self.assertEqual(markdown.count("```mermaid"), 1)
        self.assertIn("@dependency-start", markdown)
        self.assertIn(
            "upstream design ../../documents/design/skill-tool-invocation-graph.md",
            markdown,
        )
        self.assertIn(
            "downstream implementation ../../tools/agent_tools/check_skill_tool_invocation_graph.py",
            markdown,
        )
        self.assertNotIn("base64", markdown.lower())
        self.assertNotIn("coverage_marker", markdown)
        self.assertEqual(readback_mermaid(graph, markdown)["status"], "pass")
        self.assertEqual(
            graph["coverage"]["source_counts"], graph["coverage"]["rendered_counts"]
        )
        self.assertEqual(
            graph["coverage"]["source_counts"], graph["coverage"]["readback_counts"]
        )

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

    def test_checker_rejects_stale_json_mermaid_and_dependency_design_omission(
        self,
    ) -> None:
        """Edited machine or Mermaid artifacts and an omitted dependency skill fail closed."""
        check_artifacts(PROJECT_ROOT)
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
            markdown_path.write_text(original_markdown, encoding="utf-8")
            machine = json.loads(original_json)
            machine["skills"] = [
                item
                for item in machine["skills"]
                if item["ref"]["id"] != "skill:dependency-design"
            ]
            json_path.write_text(
                json.dumps(machine, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "dependency-design:omission"):
                check_artifacts(PROJECT_ROOT)
        finally:
            markdown_path.write_text(original_markdown, encoding="utf-8")
            json_path.write_text(original_json, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
