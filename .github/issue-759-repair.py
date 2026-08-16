from __future__ import annotations

from pathlib import Path
import re


TEST_PATH = Path("tests/agent_tools/test_execution_time_aware_orchestration_contract.py")


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"unexpected {label}: expected one exact block")
    return text.replace(old, new, 1)


def replace_function(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, flags=re.DOTALL)
    if count != 1:
        raise SystemExit(f"unexpected {label}: expected one function block")
    return updated


def main() -> None:
    text = TEST_PATH.read_text(encoding="utf-8")
    text = replace_exact(
        text,
        "import tempfile\nimport unittest",
        "import tempfile\nimport tomllib\nimport unittest",
        "orchestration test import block",
    )

    old_helper = '''    def read(self, relative_path: str) -> str:
        """Read one repository surface for a static contract assertion."""
        return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

'''
    new_helper = old_helper + '''    def contract(self) -> dict[str, object]:
        """Read the machine-readable owner instead of duplicating its markers."""
        return tomllib.loads(
            self.read("agents/skills/agent-orchestration.execution-contract.toml")
        )

'''
    text = replace_exact(
        text,
        old_helper,
        new_helper,
        "orchestration test helper block",
    )

    text = replace_function(
        text,
        r"    def test_owner_keeps_the_complete_work_conservation_contract\(self\) -> None:\n.*?(?=    def test_production_checker_accepts_the_complete_owner_closure)",
        '''    def test_owner_keeps_the_complete_work_conservation_contract(self) -> None:
        """The canonical owner must retain every declared execution-time decision."""
        text = " ".join(
            self.read("agents/skills/agent-orchestration.md").lower().split()
        )
        markers = self.contract()["owner_markers"]
        self.assertIsInstance(markers, list)
        for marker in markers:
            self.assertIsInstance(marker, str)
            self.assertIn(" ".join(marker.lower().split()), text, marker)

''',
        "owner contract test",
    )

    text = replace_function(
        text,
        r"    def test_pr_processing_consumes_and_specializes_the_owner\(self\) -> None:\n.*?(?=    def test_runtime_catalog_and_schedule_project_the_owner)",
        '''    def test_pr_processing_consumes_and_specializes_the_owner(self) -> None:
        """PR processing keeps queue-specific rules under the owner contract."""
        text = " ".join(self.read("agents/skills/pr-processing.md").lower().split())
        consumers = self.contract()["consumers"]
        self.assertIsInstance(consumers, list)
        consumer = next(
            item
            for item in consumers
            if isinstance(item, dict) and item.get("id") == "pr-processing"
        )
        markers = consumer["required_markers"]
        self.assertIsInstance(markers, list)

        self.assertIn(OWNER_REF.lower(), text)
        for marker in markers:
            self.assertIsInstance(marker, str)
            self.assertIn(" ".join(marker.lower().split()), text, marker)
        self.assertIn("never use elapsed time", text)

''',
        "PR consumer test",
    )

    text = replace_function(
        text,
        r"    def test_runtime_catalog_and_schedule_project_the_owner\(self\) -> None:\n.*?(?=\nif __name__ == \"__main__\":)",
        '''    def test_runtime_catalog_and_schedule_project_the_owner(self) -> None:
        """Projections point to the owner without becoming policy copies."""
        consumers = self.contract()["consumers"]
        self.assertIsInstance(consumers, list)
        indexed = {
            item["id"]: item
            for item in consumers
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }

        self.assertIn(OWNER_REF, self.read("agents/task_catalog.yaml"))
        self.assertIn(OWNER_REF, self.read("templates/agents/schedule.md"))

        runtime = " ".join(
            self.read(".agents/skills/agent-orchestration/SKILL.md").lower().split()
        )
        runtime_markers = indexed["runtime-shim"]["required_markers"]
        self.assertIsInstance(runtime_markers, list)
        for marker in runtime_markers:
            self.assertIsInstance(marker, str)
            self.assertIn(" ".join(marker.lower().split()), runtime, marker)

        schedule = " ".join(self.read("templates/agents/schedule.md").lower().split())
        schedule_markers = indexed["schedule"]["required_markers"]
        self.assertIsInstance(schedule_markers, list)
        for marker in schedule_markers:
            self.assertIsInstance(marker, str)
            self.assertIn(" ".join(marker.lower().split()), schedule, marker)

''',
        "runtime projection test",
    )

    TEST_PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
