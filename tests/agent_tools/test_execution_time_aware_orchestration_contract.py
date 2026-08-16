"""Static checks for the execution-time-aware orchestration contract."""

# @dependency-start
# contract test
# responsibility Protects the canonical execution-time-aware orchestration contract and projections.
# upstream design ../../agents/skills/agent-orchestration.execution-contract.toml machine-readable owner contract
# upstream design ../../agents/skills/agent-orchestration.md canonical work-conservation owner
# upstream design ../../agents/skills/pr-processing.md PR queue specialization
# upstream design ../../agents/task_catalog.yaml task routing projection
# upstream design ../../templates/agents/schedule.md schedule projection
# upstream implementation ../../tools/agent_tools/check_execution_time_aware_orchestration.py production contract checker
# upstream implementation ../../tools/agent_tools/skill_tool_commands.py selected-skill command packet
# downstream implementation ../../.agents/skills/agent-orchestration/SKILL.md runtime discovery shim
# @dependency-end

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "check_execution_time_aware_orchestration.py"
OWNER_REF = (
    "agents/skills/agent-orchestration.md#"
    "Execution-Time-Aware Work-Conservation Contract"
)
CONTRACT_FIXTURE_PATHS = (
    "agents/skills/agent-orchestration.execution-contract.toml",
    "agents/skills/agent-orchestration.md",
    "agents/skills/pr-processing.md",
    "agents/skills/catalog.yaml",
    "agents/task_catalog.yaml",
    "templates/agents/schedule.md",
    ".agents/skills/agent-orchestration/SKILL.md",
    "tools/agent_tools/check_execution_time_aware_orchestration.py",
)


class ExecutionTimeAwareOrchestrationContractTests(unittest.TestCase):
    """Keep the owner contract and its projections connected."""

    def read(self, relative_path: str) -> str:
        """Read one repository surface for a static contract assertion."""
        return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    def fixture_root(self, temporary_directory: str) -> Path:
        """Copy only the owner closure needed by the production checker."""
        root = Path(temporary_directory)
        for relative_path in CONTRACT_FIXTURE_PATHS:
            source = PROJECT_ROOT / relative_path
            destination = root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        return root

    def run_checker(self, root: Path) -> subprocess.CompletedProcess[str]:
        """Run the production checker against one isolated fixture."""
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def run_decision(self, decision: dict[str, object]) -> subprocess.CompletedProcess[str]:
        """Classify one explicit execution-route decision fixture."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8") as handle:
            json.dump(decision, handle)
            handle.flush()
            return subprocess.run(
                [
                    sys.executable,
                    str(CHECKER),
                    "--root",
                    str(PROJECT_ROOT),
                    "--decision",
                    handle.name,
                    "--format",
                    "json",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

    def assert_rejected(self, root: Path, category: str) -> None:
        """Require a strict checker failure for one rejected mutation class."""
        result = self.run_checker(root)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            f"EXECUTION_TIME_AWARE_ORCHESTRATION_FINDING={category}:",
            result.stdout,
        )

    def append(self, root: Path, relative_path: str, text: str) -> None:
        """Append one controlled negative-fixture mutation."""
        path = root / relative_path
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")

    def test_production_checker_accepts_the_complete_owner_closure(self) -> None:
        """The production checker accepts the unmutated owner closure."""
        result = self.run_checker(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("EXECUTION_TIME_AWARE_ORCHESTRATION=pass", result.stdout)

    def test_rejects_duplicate_local_scheduling_definition(self) -> None:
        """A consumer cannot introduce a second scheduling owner."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.fixture_root(temporary_directory)
            self.append(
                root,
                "agents/skills/pr-processing.md",
                "\n## Execution-Time-Aware Work-Conservation Contract\n",
            )
            self.assert_rejected(root, "duplicate_local_scheduling_definition")

    def test_rejects_duration_or_timeout_scope_cutoff(self) -> None:
        """A schedule cannot use a budget or timeout to cut responsibility."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.fixture_root(temporary_directory)
            self.append(root, "templates/agents/schedule.md", "\n- Duration budget: cut scope after timeout.\n")
            self.assert_rejected(root, "duration_or_timeout_scope_cutoff")

    def test_rejects_keyword_based_routing(self) -> None:
        """A runtime shim cannot turn prompt keywords into scheduling policy."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.fixture_root(temporary_directory)
            self.append(root, ".agents/skills/agent-orchestration/SKILL.md", "\n- Prompt keywords route ready nodes.\n")
            self.assert_rejected(root, "keyword_based_routing")

    def test_rejects_responsibility_scope_reduction(self) -> None:
        """A queue specialization cannot reduce the requested responsibility."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.fixture_root(temporary_directory)
            self.append(root, "agents/skills/pr-processing.md", "\n- Reduce requested responsibility to the first ready node.\n")
            self.assert_rejected(root, "responsibility_scope_reduction")

    def test_rejects_consumer_reference_without_executable_fields(self) -> None:
        """A structured consumer reference must carry every executable field."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.fixture_root(temporary_directory)
            path = root / "agents/task_catalog.yaml"
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace("    - context_reuse\n", "", 1), encoding="utf-8")
            self.assert_rejected(root, "consumer_reference_without_executable_fields")

    def test_rejects_consumer_reference_mismatch(self) -> None:
        """A consumer cannot point at an alternate scheduling owner."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.fixture_root(temporary_directory)
            path = root / "agents/task_catalog.yaml"
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace(OWNER_REF, "agents/skills/other-owner.md#Contract", 1), encoding="utf-8")
            self.assert_rejected(root, "consumer_reference_mismatch")

    def test_single_node_without_edge_is_non_active(self) -> None:
        """A single bounded node does not materialize graph-only fields."""
        result = self.run_decision({"nodes": [{"id": "one"}], "edges": []})

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        route = json.loads(result.stdout)
        self.assertEqual(route["state"], "bounded_single_owner")
        self.assertFalse(route["graph_active"])
        self.assertEqual(route["graph_fields"], [])

    def test_multiple_independent_candidates_are_non_active(self) -> None:
        """Candidate count alone does not activate graph scheduling."""
        result = self.run_decision(
            {"nodes": [{"id": "one"}, {"id": "two"}], "edges": []}
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        route = json.loads(result.stdout)
        self.assertEqual(route["state"], "bounded_single_owner")
        self.assertEqual(route["candidate_count"], 2)
        self.assertFalse(route["graph_active"])

    def test_selected_edge_activates_graph(self) -> None:
        """A real selected edge activates only the selected graph route."""
        result = self.run_decision(
            {
                "nodes": [{"id": "one"}, {"id": "two"}],
                "edges": [{"type": "dependency", "source": "one", "target": "two"}],
                "graph_evidence": {
                    "dag": [{"source": "one", "target": "two"}],
                    "critical_path": ["one", "two"],
                    "ready_set": ["one"],
                    "queue_snapshot": ["one", "two"],
                    "makespan_objective": "minimize",
                    "node_ids": ["one", "two"],
                },
            }
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        route = json.loads(result.stdout)
        self.assertEqual(route["state"], "selected_edge_graph")
        self.assertTrue(route["graph_active"])
        self.assertEqual(route["active_edge_types"], ["dependency"])

    def test_invalid_or_missing_graph_evidence_is_rejected(self) -> None:
        """An active selected edge requires complete valid graph evidence."""
        base = {
            "nodes": [{"id": "one"}, {"id": "two"}],
            "edges": [{"type": "ordering", "source": "one", "target": "two"}],
        }
        for graph_evidence in (None, {"dag": [], "critical_path": []}):
            decision = dict(base)
            if graph_evidence is not None:
                decision["graph_evidence"] = graph_evidence
            result = self.run_decision(decision)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            route = json.loads(result.stdout)
            self.assertEqual(route["state"], "selected_edge_graph")
            self.assertTrue(route["graph_active"])
            self.assertTrue(route["findings"])
            self.assertEqual(route["findings"][0]["category"], "execution_graph")

if __name__ == "__main__":
    unittest.main()
