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

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "skill_dependency_map.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
import skill_route_catalog as catalog_module  # noqa: E402
from skill_dependency_map import render_mermaid  # noqa: E402


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
        self.assertEqual(len(rules), 59)
        self.assertTrue(all(rule.responsibility_group for rule in rules.values()))

    def test_check_cli_validates_canonical_map(self) -> None:
        """The focused checker reports the source and complete public count."""
        result = self.run_tool("check", "--root", str(PROJECT_ROOT))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SKILL_DEPENDENCY_MAP=pass", result.stdout)
        self.assertIn("source=agents/skills/skill-dependencies.yaml", result.stdout)
        self.assertIn("skills=59", result.stdout)

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
            self.assertIn("SKILL_DEPENDENCY_GRAPH=pass", result.stdout)
            graph = output.read_text(encoding="utf-8")
            self.assertEqual(graph.count("```mermaid"), 1)
            public_ids = catalog_module._skill_ids_from_catalog(
                catalog_module.load_skill_catalog(PROJECT_ROOT)
            )
            self.assertEqual(sum(f'"{skill}"' in graph for skill in public_ids), 59)


if __name__ == "__main__":
    unittest.main()
