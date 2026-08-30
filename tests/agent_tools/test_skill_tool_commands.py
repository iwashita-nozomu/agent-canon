"""Focused tests for structured Skill command resolution."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.agent.skills.skill_tool_commands import (  # noqa: E402
    CommandPlan,
    execute_command,
    execute_plan,
    native_make_target_introspection,
    packet_for_skill,
    project_public_command_for_layout,
    resolve_command,
)
from tools.runtime.source.agent_canon_source_root import (  # noqa: E402
    resolve_agent_canon_source_root,
)


class StructuredSkillCommandTest(unittest.TestCase):
    """Verify typed argv, native items, and failure boundaries."""

    def fixture(self, root: Path, item: dict[str, object], arguments: dict[str, object] | None = None) -> None:
        (root / "agents/skills").mkdir(parents=True)
        (root / "tools").mkdir()
        (root / "agents/skills/catalog.yaml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "skill_families": [
                        {
                            "id": "demo",
                            "tool_commands": {
                                "required": [item],
                                "conditional": [],
                                "maintenance": [],
                            },
                        }
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        dispatch = {
            "argv": [sys.executable, "-c", "import sys; print(repr(sys.argv[1:]))"],
        }
        if arguments is not None:
            dispatch["arguments"] = arguments
        (root / "tools/catalog.yaml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "entries": [{"id": "demo-tool", "dispatch": dispatch}],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def test_scalar_and_list_bindings_are_argv_elements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(
                root,
                {
                    "tool_id": "demo-tool",
                    "operation_id": "default",
                    "bindings": {
                        "name": {"from": "name"},
                        "paths": {"from": "paths"},
                    },
                },
                {
                    "name": {"type": "string", "flag": "--name", "required": True},
                    "paths": {"type": "path-list", "flag": "--path", "repeat": True, "required": True},
                },
            )
            plan = resolve_command(root, "demo", "required:0", {"name": "alpha", "paths": ["a.md", "b.md"]})
            self.assertEqual(plan.execution_argv[-6:], ("--name", "alpha", "--path", "a.md", "--path", "b.md"))

    def test_shell_metacharacters_remain_one_literal_argv_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(
                root,
                {"tool_id": "demo-tool", "bindings": {"value": {"from": "value"}}},
                {"value": {"type": "string", "required": True}},
            )
            value = "$(touch SHOULD_NOT_EXIST); a|b > c && 'quoted'"
            plan = resolve_command(root, "demo", "required:0", {"value": value})
            self.assertEqual(plan.execution_argv[-1], value)
            self.assertFalse((root / "SHOULD_NOT_EXIST").exists())

    def test_invalid_binding_is_rejected_before_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(
                root,
                {"tool_id": "demo-tool", "bindings": {"paths": {"from": "paths"}}},
                {"paths": {"type": "path-list", "flag": "--path", "required": True}},
            )
            runner = Mock()
            result = execute_command(root, "demo", "required:0", {"paths": "not-a-list"})
            self.assertEqual(result.status, "invalid-input")
            runner.assert_not_called()

    def test_failure_taxonomy_distinguishes_spawn_exit_and_readback(self) -> None:
        plan = CommandPlan("demo", "/tmp", "/tmp", (), ("demo",))
        spawn = execute_plan(plan, runner=Mock(side_effect=OSError("spawn")))
        self.assertEqual(spawn.status, "spawn-failed")
        failed = execute_plan(plan, runner=Mock(return_value=subprocess.CompletedProcess([], 3, b"", b"bad")))
        self.assertEqual(failed.status, "command-failed")
        unreadable = execute_plan(plan, runner=Mock(return_value=subprocess.CompletedProcess([], 0, b"\xff", b"")))
        self.assertEqual(unreadable.status, "readback-failed")

    def test_tool_unavailable_is_reported_without_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, {"executable": "/missing/agent-canon-executable", "argv": ["--probe"]})
            result = execute_command(root, "demo", "required:0")
            self.assertEqual(result.status, "tool-unavailable")

    def test_native_make_introspection_does_not_run_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            touched = root / "recipe-ran"
            (root / "Makefile").write_text(f"check:\n\t@echo no > {touched}\n", encoding="utf-8")
            result = native_make_target_introspection(root, "check")
            self.assertEqual(result.status, "completed")
            self.assertFalse(touched.exists())
            self.assertEqual(native_make_target_introspection(root, "missing").status, "command-failed")

    def test_public_projection_accepts_only_structured_plan(self) -> None:
        plan = CommandPlan("demo", "/repo", "/repo", (), ("python3", "script.py"))
        projection = project_public_command_for_layout(plan, layout="standalone")
        self.assertEqual(projection.public_argv, plan.execution_argv)

    def test_generated_packet_preserves_five_tuple_and_json_envelope(self) -> None:
        resolution = resolve_agent_canon_source_root(ROOT)
        packet = packet_for_skill(resolution, "agent-orchestration")
        self.assertEqual(len(packet.resolved_required_commands[0]), 5)
        payload = json.loads(json.dumps(packet, default=lambda value: value.__dict__))
        self.assertIn("resolved_required_commands", payload)

    def test_catalog_suffixes_are_dispatch_relative_and_witness_resolves_once(self) -> None:
        """Catalog suffixes never duplicate their tool dispatch argv prefix."""
        catalog = yaml.safe_load((ROOT / "agents/skills/catalog.yaml").read_text(encoding="utf-8"))
        tools = {
            item["id"]: item
            for item in yaml.safe_load((ROOT / "tools/catalog.yaml").read_text(encoding="utf-8"))["entries"]
        }
        catalog_rows = 0
        for skill in catalog["skill_families"]:
            for phase in ("required", "conditional", "maintenance"):
                for item in skill["tool_commands"].get(phase, []) or []:
                    if "tool_id" not in item:
                        continue
                    catalog_rows += 1
                    prefix = tools[item["tool_id"]]["dispatch"]["argv"]
                    suffix = item.get("argv_suffix", [])
                    self.assertNotEqual(suffix[: len(prefix)], prefix)
        self.assertEqual(catalog_rows, 279)

        plan = resolve_command(ROOT, "agent-orchestration", "required:0")
        prefix = tools["check-execution-time-aware-orchestration"]["dispatch"]["argv"]
        suffix = next(
            item
            for item in catalog["skill_families"][0]["tool_commands"]["required"]
            if item.get("tool_id") == "check-execution-time-aware-orchestration"
        ).get("argv_suffix", [])
        expected = list(prefix) + list(suffix)
        expected[1] = str((ROOT / expected[1]).resolve())
        self.assertEqual(list(plan.execution_argv), expected)


if __name__ == "__main__":
    unittest.main()
