"""Focused tests for the canonical public-skill dependency dictionary."""

# @dependency-start
# contract test
# responsibility Tests typed public-skill dependency validation and generated Mermaid coverage.
# upstream implementation ../../tools/agent_tools/skill_dependency_map.py validates and projects the map
# upstream implementation ../../tools/agent_tools/skill_route_catalog.py owns map parsing and route-order derivation
# upstream design ../../agents/skills/catalog.yaml enumerates public skill identities
# upstream design ../../agents/skills/skill-dependencies.yaml owns dependency relations
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "skill_dependency_map.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
import skill_route_catalog as catalog_module  # noqa: E402
from skill_dependency_map import (  # noqa: E402
    GraphCapacityError,
    build_graph,
    render_mermaid,
)


class SkillDependencyMapTest(unittest.TestCase):
    """Check map identity, graph invariants, and fail-closed diagnostics."""

    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the dependency-map CLI from the repository root."""
        return subprocess.run(
            [sys.executable, str(TOOL), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_map(self, root: Path, payload: dict[str, object]) -> None:
        """Write one isolated dependency-map fixture."""
        path = root / catalog_module.SKILL_DEPENDENCY_MAP_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    def base_payload(self) -> dict[str, object]:
        """Load a mutable copy of the canonical map."""
        path = PROJECT_ROOT / catalog_module.SKILL_DEPENDENCY_MAP_PATH
        return deepcopy(yaml.safe_load(path.read_text(encoding="utf-8")))

    def dependency_records(self, payload: dict[str, object]) -> dict[str, dict[str, object]]:
        """Return typed-enough mutable records for focused mutation fixtures."""
        return payload["skill_dependencies"]  # type: ignore[return-value]

    def test_map_covers_every_public_catalog_skill(self) -> None:
        """The canonical dictionary has exactly the public catalog key set."""
        catalog = catalog_module.load_skill_catalog(PROJECT_ROOT)
        public_ids = catalog_module._skill_ids_from_catalog(catalog)
        rules = catalog_module.load_skill_dependency_map(PROJECT_ROOT, public_ids)

        self.assertEqual(tuple(rules), public_ids)
        self.assertEqual(len(rules), 60)
        self.assertTrue(all(rule.responsibility_group for rule in rules.values()))

    def test_check_cli_validates_canonical_map(self) -> None:
        """The focused checker reports the source and complete public count."""
        result = self.run_tool("check", "--root", str(PROJECT_ROOT))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SKILL_DEPENDENCY_MAP=pass", result.stdout)
        self.assertIn("source=agents/skills/skill-dependencies.yaml", result.stdout)
        self.assertIn("skills=60", result.stdout)

    def test_cycle_is_rejected(self) -> None:
        """Mutually successor-linked skills fail the static DAG check."""
        payload = self.base_payload()
        records = self.dependency_records(payload)
        records["repo-onboarding"]["successors"] = ["task-routing"]
        records["task-routing"]["successors"] = ["repo-onboarding"]
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_map(root, payload)
            with self.assertRaisesRegex(ValueError, "skill-dependency-map-cycle"):
                catalog_module.load_skill_dependency_map(root, tuple(records))

    def test_missing_reference_is_rejected(self) -> None:
        """A relation to a non-public skill fails closed before graph output."""
        payload = self.base_payload()
        records = self.dependency_records(payload)
        records["agent-orchestration"]["successors"] = ["missing-skill"]
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_map(root, payload)
            with self.assertRaisesRegex(
                ValueError, "skill-dependency-map-unknown-reference"
            ):
                catalog_module.load_skill_dependency_map(root, tuple(records))

    def test_order_contradiction_is_rejected(self) -> None:
        """An explicit reverse order against an existing prerequisite fails."""
        payload = self.base_payload()
        records = self.dependency_records(payload)
        records["repo-onboarding"]["required_prerequisites"] = ["task-routing"]
        records["repo-onboarding"]["order_constraints"] = [
            {"before": "repo-onboarding", "after": "task-routing", "reason": "fixture"}
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_map(root, payload)
            with self.assertRaisesRegex(
                ValueError, "skill-dependency-map-order-contradiction"
            ):
                catalog_module.load_skill_dependency_map(root, tuple(records))

    def test_research_workflow_order_matches_literature_constraint(self) -> None:
        """Research workflow order now enforces literature-survey before execution."""
        rules = dict(catalog_module.load_skill_dependency_map(PROJECT_ROOT))
        research = rules["research-workflow"]
        self.assertIn("literature-survey", research.routing_candidates)
        self.assertIn(
            ("literature-survey", "research-workflow"),
            {(constraint.before, constraint.after) for constraint in research.order_constraints},
        )

    def test_parallel_relation_cannot_overlap_ordered_work(self) -> None:
        """Parallel-independent declarations cannot contradict the DAG."""
        payload = self.base_payload()
        records = self.dependency_records(payload)
        records["repo-onboarding"]["required_prerequisites"] = ["task-routing"]
        records["repo-onboarding"]["parallel_independent"] = ["task-routing"]
        records["task-routing"]["parallel_independent"].append("repo-onboarding")
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_map(root, payload)
            with self.assertRaisesRegex(
                ValueError, "skill-dependency-map-parallel-contradiction"
            ):
                catalog_module.load_skill_dependency_map(root, tuple(records))

    def test_graph_contains_all_public_skills_and_order_metadata(self) -> None:
        """The projection keeps every public node, groups, and typed edges."""
        rules = dict(catalog_module.load_skill_dependency_map(PROJECT_ROOT))
        graph = render_mermaid(rules)

        self.assertIn("graph LR", graph)
        self.assertIn("subgraph group_orchestration", graph)
        self.assertIn('"agent-orchestration"', graph)
        self.assertIn("prerequisite", graph)
        self.assertIn("order", graph)
        for skill in rules:
            self.assertIn(f'"{skill}"', graph)

    def test_graph_cli_writes_generated_artifact(self) -> None:
        """The graph route writes one generated Markdown artifact."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "graph.md"
            result = self.run_tool(
                "graph",
                "--root",
                str(PROJECT_ROOT),
                "--output",
                str(output),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SKILL_TOOL_INVOCATION_GRAPH=pass", result.stdout)
            graph = output.read_text(encoding="utf-8")
            self.assertEqual(graph.count("```mermaid"), 1)
            public_ids = catalog_module._skill_ids_from_catalog(
                catalog_module.load_skill_catalog(PROJECT_ROOT)
            )
            self.assertEqual(sum(f'"{skill}"' in graph for skill in public_ids), 60)

    def test_graph_has_complete_json_mermaid_and_typed_coverage(self) -> None:
        """The generated schema keeps all skills, phases, commands, edges, and counts."""
        payload = build_graph(PROJECT_ROOT)
        self.assertEqual(
            payload["schema"], "agent_canon.skill_tool_invocation_graph.v1"
        )
        self.assertEqual(payload["skill_count"], 60)
        self.assertIn(
            "dependency-design",
            {skill["label"] for skill in payload["skills"]},
        )
        self.assertEqual(
            set(payload["source_counts"]),
            {
                "identity",
                "edge",
                "field",
                "phase",
                "branch",
                "module",
                "evidence",
                "time",
            },
        )
        self.assertEqual(payload["source_counts"], payload["rendered_counts"])
        self.assertEqual(payload["source_counts"], payload["readback_counts"])
        self.assertEqual(
            {edge["edge_type"] for edge in payload["edges"]},
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
        markdown = (
            PROJECT_ROOT / "documents/runtime/skill-dependency-graph.md"
        ).read_text(encoding="utf-8")
        machine = json.loads(
            (PROJECT_ROOT / "documents/runtime/skill-dependency-graph.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(markdown.count("```mermaid"), 1)
        self.assertEqual(machine["coverage_digest"], payload["coverage_digest"])

    def test_every_packet_command_is_materialized_with_phase(self) -> None:
        """Each canonical packet resolution has one graph command node and phase."""
        payload = build_graph(PROJECT_ROOT)
        graph_commands = {
            (command["skill"], command["phase"], command["logical_command"])
            for command in payload["commands"]
        }
        sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
        from agent_canon_source_root import (
            resolve_agent_canon_source_root,  # noqa: E402
        )
        from skill_tool_commands import packet_for_skill  # noqa: E402

        resolution = resolve_agent_canon_source_root(PROJECT_ROOT)
        for skill in catalog_module._skill_ids_from_catalog(
            catalog_module.load_skill_catalog(PROJECT_ROOT)
        ):
            packet = packet_for_skill(resolution, skill)
            for phase, rows in (
                ("required", packet.resolved_required_commands),
                ("conditional", packet.resolved_conditional_commands),
                ("maintenance", packet.resolved_maintenance_commands),
            ):
                for row in rows:
                    self.assertIn((skill, phase, row[0]), graph_commands)

    def test_artifact_checker_rejects_edited_mermaid(self) -> None:
        """The checker rejects an edited generated Mermaid artifact."""
        path = PROJECT_ROOT / "documents/runtime/skill-dependency-graph.md"
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(original + "\n%% edited\n", encoding="utf-8")
            result = self.run_tool("check", "--root", str(PROJECT_ROOT))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("stale_artifact", result.stderr)
        finally:
            path.write_text(original, encoding="utf-8")

    def test_artifact_checker_rejects_edited_json(self) -> None:
        """The checker rejects an edited generated JSON artifact."""
        path = PROJECT_ROOT / "documents/runtime/skill-dependency-graph.json"
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(original + "\n", encoding="utf-8")
            result = self.run_tool("check", "--root", str(PROJECT_ROOT))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("skill-dependency-graph.json:edited-or-stale", result.stderr)
        finally:
            path.write_text(original, encoding="utf-8")

    def test_capacity_failure_is_typed_and_does_not_prune(self) -> None:
        """Insufficient renderer capacity fails with a typed error."""
        with self.assertRaisesRegex(
            GraphCapacityError,
            "skill_tool_invocation_graph_capacity_exceeded",
        ):
            build_graph(PROJECT_ROOT, capacity=1)

    def test_graph_digest_is_deterministic(self) -> None:
        """Repeated materialization has stable graph and coverage digests."""
        first = build_graph(PROJECT_ROOT)
        second = build_graph(PROJECT_ROOT)
        self.assertEqual(first["graph_digest"], second["graph_digest"])
        self.assertEqual(first["coverage_digest"], second["coverage_digest"])


if __name__ == "__main__":
    unittest.main()
