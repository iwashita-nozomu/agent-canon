"""Static checks for the execution-time-aware orchestration contract."""

# @dependency-start
# contract test
# responsibility Protects the canonical execution-time-aware orchestration contract and projections.
# upstream design ../../agents/skills/agent-orchestration.execution-contract.toml machine-readable owner contract
# upstream design ../../agents/skills/agent-orchestration.md canonical work-conservation owner
# upstream design ../../agents/skills/pr-processing.md PR queue specialization
# upstream design ../../agents/task_catalog.yaml task routing projection
# upstream design ../../agents/templates/schedule.md schedule projection
# upstream implementation ../../tools/agent_tools/check_execution_time_aware_orchestration.py production contract checker
# upstream implementation ../../tools/agent_tools/skill_tool_commands.py selected-skill command packet
# downstream implementation ../../.agents/skills/agent-orchestration/SKILL.md runtime discovery shim
# @dependency-end

from __future__ import annotations

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
    "agents/templates/schedule.md",
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

    def test_owner_keeps_the_complete_work_conservation_contract(self) -> None:
        """The canonical owner must retain every execution-time decision."""
        text = " ".join(
            self.read("agents/skills/agent-orchestration.md").lower().split()
        )

        for marker in (
            "execution-time-aware work-conservation contract",
            "dependency dag",
            "critical path",
            "ready set",
            "minimize makespan",
            "responsibility completeness",
            "correctness",
            "every ready node",
            "non-conflicting",
            "batch remote reads",
            "warm worker and reviewer contexts",
            "complete remaining closure",
            "before opening the owning review",
            "affected by the repaired node",
            "wait only when the useful ready set is empty",
            "elapsed-time scope gate",
            "prompt-keyword routing",
            "fixed duration",
        ):
            self.assertIn(marker, text, marker)

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
            self.append(root, "agents/templates/schedule.md", "\n- Duration budget: cut scope after timeout.\n")
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

    def test_pr_processing_consumes_and_specializes_the_owner(self) -> None:
        """PR processing keeps queue-specific rules under the owner contract."""
        text = " ".join(self.read("agents/skills/pr-processing.md").lower().split())

        self.assertIn(OWNER_REF.lower(), text)
        for marker in (
            "batched queue snapshot",
            "independent candidates",
            "one closure review for each exact candidate",
            "only the affected candidate evidence",
            "same warm worker and reviewer context",
            "merge candidates in dependency order",
            "never use elapsed time",
        ):
            self.assertIn(marker, text, marker)

    def test_runtime_catalog_and_schedule_project_the_owner(self) -> None:
        """Projections point to the owner without becoming policy copies."""
        self.assertIn(OWNER_REF, self.read("agents/task_catalog.yaml"))
        self.assertIn(OWNER_REF, self.read("agents/templates/schedule.md"))
        self.assertIn(OWNER_REF, self.read(".agents/skills/agent-orchestration/SKILL.md"))

        schedule = " ".join(self.read("agents/templates/schedule.md").lower().split())
        for marker in (
            "execution-time-aware plan",
            "dependency dag / closure",
            "critical path",
            "ready set",
            "useful ready set",
            "dispatch batch",
            "affected evidence invalidation",
        ):
            self.assertIn(marker, schedule, marker)


if __name__ == "__main__":
    unittest.main()
