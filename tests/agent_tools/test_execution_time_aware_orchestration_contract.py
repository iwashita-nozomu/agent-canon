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
# downstream implementation ../../.codex/personal/skills/agent-orchestration/SKILL.md runtime discovery shim
# @dependency-end

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = (
    PROJECT_ROOT
    / "tools"
    / "agent_tools"
    / "check_execution_time_aware_orchestration.py"
)
CONTRACT_PATH = (
    PROJECT_ROOT / "agents" / "skills" / "agent-orchestration.execution-contract.toml"
)
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
    ".codex/personal/skills/agent-orchestration/SKILL.md",
    "tools/agent_tools/check_execution_time_aware_orchestration.py",
)


class ExecutionTimeAwareOrchestrationContractTests(unittest.TestCase):
    """Keep the owner contract and its projections connected."""

    def read(self, relative_path: str) -> str:
        return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    def contract(self) -> dict[str, object]:
        return tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def fixture_root(self, temporary_directory: str) -> Path:
        root = Path(temporary_directory)
        for relative_path in CONTRACT_FIXTURE_PATHS:
            source = PROJECT_ROOT / relative_path
            destination = root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        return root

    def run_checker(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_rejected(self, root: Path, category: str) -> None:
        result = self.run_checker(root)
        self.assertNotEqual(
            result.returncode,
            0,
            result.stdout + result.stderr,
        )
        self.assertIn(
            f"EXECUTION_TIME_AWARE_ORCHESTRATION_FINDING={category}:",
            result.stdout,
        )

    def append(self, root: Path, relative_path: str, text: str) -> None:
        path = root / relative_path
        path.write_text(
            path.read_text(encoding="utf-8") + text,
            encoding="utf-8",
        )

    def consumer(self, consumer_id: str) -> dict[str, object]:
        consumers = self.contract().get("consumers")
        self.assertIsInstance(consumers, list)
        matches = [
            item
            for item in consumers
            if isinstance(item, dict) and item.get("id") == consumer_id
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_owner_keeps_the_complete_work_conservation_contract(self) -> None:
        text = " ".join(
            self.read("agents/skills/agent-orchestration.md").lower().split()
        )
        contract = self.contract()
        markers = contract.get("owner_markers")
        self.assertIsInstance(markers, list)
        self.assertIn(
            "execution-time-aware work-conservation contract",
            text,
        )
        for marker in markers:
            self.assertIsInstance(marker, str)
            self.assertIn(" ".join(marker.lower().split()), text, marker)

    def test_production_checker_accepts_the_complete_owner_closure(self) -> None:
        result = self.run_checker(PROJECT_ROOT)
        self.assertEqual(
            result.returncode,
            0,
            result.stdout + result.stderr,
        )
        self.assertIn(
            "EXECUTION_TIME_AWARE_ORCHESTRATION=pass",
            result.stdout,
        )

    def test_rejects_duplicate_local_scheduling_definition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.fixture_root(temporary_directory)
            self.append(
                root,
                "agents/skills/pr-processing.md",
                "\n## Execution-Time-Aware Work-Conservation Contract\n",
            )
            self.assert_rejected(
                root,
                "duplicate_local_scheduling_definition",
            )

    def test_rejects_duration_or_timeout_scope_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.fixture_root(temporary_directory)
            self.append(
                root,
                "templates/agents/schedule.md",
                "\n- Duration budget: cut scope after timeout.\n",
            )
            self.assert_rejected(
                root,
                "duration_or_timeout_scope_cutoff",
            )

    def test_rejects_keyword_based_routing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.fixture_root(temporary_directory)
            self.append(
                root,
                ".codex/personal/skills/agent-orchestration/SKILL.md",
                "\n- Prompt keywords route ready nodes.\n",
            )
            self.assert_rejected(root, "keyword_based_routing")

    def test_rejects_responsibility_scope_reduction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.fixture_root(temporary_directory)
            self.append(
                root,
                "agents/skills/pr-processing.md",
                "\n- Reduce requested responsibility to the first ready node.\n",
            )
            self.assert_rejected(
                root,
                "responsibility_scope_reduction",
            )

    def test_rejects_consumer_reference_without_executable_fields(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.fixture_root(temporary_directory)
            path = root / "agents/task_catalog.yaml"
            task_catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
            task_catalog["execution_time_policy"]["executable_fields"].remove(
                "context_reuse"
            )
            path.write_text(
                yaml.safe_dump(task_catalog, sort_keys=False),
                encoding="utf-8",
            )
            self.assert_rejected(
                root,
                "consumer_reference_without_executable_fields",
            )

    def test_rejects_consumer_reference_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.fixture_root(temporary_directory)
            path = root / "agents/task_catalog.yaml"
            task_catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
            task_catalog["execution_time_policy"]["owner_ref"] = (
                "agents/skills/other-owner.md#Contract"
            )
            path.write_text(
                yaml.safe_dump(task_catalog, sort_keys=False),
                encoding="utf-8",
            )
            self.assert_rejected(
                root,
                "consumer_reference_mismatch",
            )

    def test_pr_processing_consumes_and_specializes_the_owner(self) -> None:
        spec = self.consumer("pr-processing")
        path = spec["path"]
        self.assertIsInstance(path, str)
        text = " ".join(self.read(path).lower().split())
        self.assertIn(OWNER_REF.lower(), text)
        markers = spec.get("required_markers")
        self.assertIsInstance(markers, list)
        for marker in markers:
            self.assertIsInstance(marker, str)
            self.assertIn(" ".join(marker.lower().split()), text, marker)

    def test_runtime_catalog_and_schedule_project_the_owner(self) -> None:
        task_catalog = yaml.safe_load(self.read("agents/task_catalog.yaml"))
        self.assertEqual(
            task_catalog["execution_time_policy"]["owner_ref"],
            OWNER_REF,
        )
        self.assertIn(OWNER_REF, self.read("templates/agents/schedule.md"))

        runtime_spec = self.consumer("runtime-shim")
        runtime_path = runtime_spec["path"]
        self.assertIsInstance(runtime_path, str)
        runtime = " ".join(self.read(runtime_path).lower().split())
        runtime_markers = runtime_spec.get("required_markers")
        self.assertIsInstance(runtime_markers, list)
        for marker in runtime_markers:
            self.assertIsInstance(marker, str)
            self.assertIn(" ".join(marker.lower().split()), runtime, marker)

        schedule_spec = self.consumer("schedule")
        path = schedule_spec["path"]
        self.assertIsInstance(path, str)
        schedule = " ".join(self.read(path).lower().split())
        markers = schedule_spec.get("required_markers")
        self.assertIsInstance(markers, list)
        for marker in markers:
            self.assertIsInstance(marker, str)
            self.assertIn(
                " ".join(marker.lower().split()),
                schedule,
                marker,
            )


if __name__ == "__main__":
    unittest.main()
