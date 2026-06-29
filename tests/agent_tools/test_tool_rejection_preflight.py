# @dependency-start
# contract test
# responsibility Tests tool rejection preflight gate prediction.
# upstream implementation ../../tools/agent_tools/tool_rejection_preflight.py predicts hook/tool rejection gates
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md defines handoff packet fields
# @dependency-end
"""Tests for predicted tool rejection handoff gates."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "tool_rejection_preflight.py"


class ToolRejectionPreflightTest(unittest.TestCase):
    """Validate gate prediction from planned paths."""

    def test_python_tool_path_predicts_code_and_log_surface_gates(self) -> None:
        """Python tool edits should carry code, helper, dependency, and log gates."""
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--root",
                str(PROJECT_ROOT),
                "tools/agent_tools/example.py",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("TOOL_REJECTION_PREFLIGHT=warn", result.stdout)
        self.assertIn("gate:cause_investigation_guard", result.stdout)
        self.assertIn("gate:import_responsibility", result.stdout)
        self.assertIn("gate:responsibility_scope", result.stdout)
        self.assertIn("scope:shared-tooling", result.stdout)
        self.assertIn("owner:agent-canon", result.stdout)
        self.assertIn("gate:module_boundary_guard", result.stdout)
        self.assertIn("gate:helper_first_guard", result.stdout)
        self.assertIn("gate:oop_readability_guard", result.stdout)
        self.assertIn("gate:solid_evidence_gate", result.stdout)
        self.assertIn("gate:helper_inventory_guard", result.stdout)
        self.assertIn("gate:style_checker_guard", result.stdout)
        self.assertIn("gate:dependency_review", result.stdout)
        self.assertIn("gate:log_surface_inventory_guard", result.stdout)
        self.assertIn("TOOL_REJECTION_PREDICTED_GATE=", result.stdout)

    def test_parent_tools_symlink_routes_new_agentcanon_tool_source_gates(self) -> None:
        """Parent tools/ views should route new shared tool sources to AgentCanon."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source_tools = root / "vendor" / "agent-canon" / "tools"
            (source_tools / "agent_tools").mkdir(parents=True)
            (root / "tools").symlink_to(
                Path("vendor") / "agent-canon" / "tools",
                target_is_directory=True,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--format",
                    "json",
                    "tools/agent_tools/new_shared_checker.py",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        payload = json.loads(result.stdout)
        gates = {gate["gate"] for gate in payload["predicted_gates"]}
        commands_by_gate: dict[str, list[str]] = {}
        for gate in payload["predicted_gates"]:
            commands_by_gate.setdefault(gate["gate"], []).append(gate["command"])
        paths = {gate["path"] for gate in payload["predicted_gates"]}

        self.assertIn(
            "vendor/agent-canon/tools/agent_tools/new_shared_checker.py", paths
        )
        self.assertIn("agentcanon_new_tool_source_route", gates)
        self.assertIn("responsibility_scope", gates)
        self.assertIn("tool_catalog", gates)
        self.assertIn("log_surface_inventory_guard", gates)
        self.assertTrue(
            any(
                "git -C vendor/agent-canon status" in command
                for command in commands_by_gate["agentcanon_new_tool_source_route"]
            )
        )
        self.assertTrue(
            any(
                "cd vendor/agent-canon" in command
                for command in commands_by_gate["log_surface_inventory_guard"]
            )
        )
        self.assertTrue(
            any(
                "cd vendor/agent-canon" in command
                for command in commands_by_gate["tool_catalog"]
            )
        )

    def test_vendor_library_path_predicts_library_guard(self) -> None:
        """Vendored dependency implementation edits should route to library guard."""
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--root",
                str(PROJECT_ROOT),
                "--format",
                "json",
                "vendor/skills/example/SKILL.md",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        gates = {gate["gate"] for gate in payload["predicted_gates"]}
        self.assertIn("library_implementation_guard", gates)
        self.assertNotIn("tool_catalog", gates)

    def test_github_workflow_path_predicts_workflow_check(self) -> None:
        """Workflow edits under GitHub paths should route to the workflow checker."""
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--root",
                str(PROJECT_ROOT),
                "--format",
                "json",
                ".github/workflows/build.yml",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        gates = {gate["gate"] for gate in payload["predicted_gates"]}
        self.assertEqual(payload["status"], "warn")
        self.assertIn("github_workflow_check", gates)
        self.assertIn("dependency_review", gates)

    def test_hook_config_path_predicts_hook_runtime_alignment(self) -> None:
        """Hook wiring edits should carry hook runtime and log-surface gates."""
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--root",
                str(PROJECT_ROOT),
                "--format",
                "json",
                ".codex/hooks.json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        gates = {gate["gate"] for gate in payload["predicted_gates"]}
        self.assertIn("codex_hook_runtime_alignment", gates)
        self.assertIn("dependency_review", gates)
        dependency_gates = [
            gate
            for gate in payload["predicted_gates"]
            if gate["gate"] == "dependency_review"
        ]
        self.assertEqual(len(dependency_gates), 1)
        self.assertIn("top-level hooks only", dependency_gates[0]["handoff"])
        self.assertNotIn("dependency header", dependency_gates[0]["handoff"])

    def test_agentcanon_hook_config_source_path_preserves_schema_route(self) -> None:
        """Parent symlink resolution should keep hook runtime and schema routing."""
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--root",
                str(PROJECT_ROOT),
                "--format",
                "json",
                "vendor/agent-canon/.codex/hooks.json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        gates = {gate["gate"] for gate in payload["predicted_gates"]}
        dependency_gates = [
            gate
            for gate in payload["predicted_gates"]
            if gate["gate"] == "dependency_review"
        ]
        self.assertIn("codex_hook_runtime_alignment", gates)
        self.assertEqual(len(dependency_gates), 1)
        self.assertIn("top-level hooks only", dependency_gates[0]["handoff"])
        self.assertNotIn("dependency header", dependency_gates[0]["handoff"])

    def test_markdown_path_predicts_style_checker_gate(self) -> None:
        """Markdown edits should carry automatic style checker coverage."""
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--root",
                str(PROJECT_ROOT),
                "--format",
                "json",
                "documents/example.md",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        gates = {gate["gate"] for gate in payload["predicted_gates"]}
        self.assertIn("style_checker_guard", gates)
        self.assertIn("dependency_review", gates)
        self.assertIn("responsibility_scope", gates)
        self.assertTrue(
            any(
                gate["handoff"].startswith("scope:shared-policy-documents ")
                for gate in payload["predicted_gates"]
                if gate["gate"] == "responsibility_scope"
            )
        )

    def test_unknown_path_predicts_responsibility_assignment(self) -> None:
        """Unscoped planned paths should route through responsibility assignment."""
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--root",
                str(PROJECT_ROOT),
                "--format",
                "json",
                "scratch-drift/example.txt",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        responsibility_gates = [
            gate
            for gate in payload["predicted_gates"]
            if gate["gate"] == "responsibility_scope"
        ]
        self.assertEqual(len(responsibility_gates), 1)
        self.assertIn(
            "assign this planned path to exactly one responsibility-scope.toml scope",
            responsibility_gates[0]["handoff"],
        )

    def test_skill_path_predicts_log_surface_gate(self) -> None:
        """Skill edits should require Codex log-surface validation."""
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--root",
                str(PROJECT_ROOT),
                "--format",
                "json",
                ".agents/skills/subagent-bootstrap/SKILL.md",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        gates = {gate["gate"] for gate in payload["predicted_gates"]}
        self.assertNotIn("skill_mirror_sync", gates)
        self.assertIn("log_surface_inventory_guard", gates)

    def test_protocol_path_predicts_convention_gate(self) -> None:
        """Protocol docs should route to convention compliance checks."""
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--root",
                str(PROJECT_ROOT),
                "--format",
                "json",
                "agents/COMMUNICATION_PROTOCOL.md",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        gates = {gate["gate"] for gate in payload["predicted_gates"]}
        self.assertIn("agent_protocol_convention", gates)
        self.assertIn("dependency_review", gates)

    def test_experiment_execution_surface_predicts_lifecycle_guard(self) -> None:
        """Managed experiment execution surfaces should route to lifecycle gates."""
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--root",
                str(PROJECT_ROOT),
                "--format",
                "json",
                "tools/experiments/run_managed_experiment.py",
                "tools/ci/check_experiment_registry.py",
                "documents/experiment-registry.md",
                "experiments/registry.toml",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        guarded_paths = {
            gate["path"]
            for gate in payload["predicted_gates"]
            if gate["gate"] == "experiment_execution_surface_guard"
        }
        self.assertEqual(
            guarded_paths,
            {
                "tools/experiments/run_managed_experiment.py",
                "tools/ci/check_experiment_registry.py",
                "documents/experiment-registry.md",
                "experiments/registry.toml",
            },
        )
        guarded_gate = next(
            gate
            for gate in payload["predicted_gates"]
            if gate["gate"] == "experiment_execution_surface_guard"
        )
        self.assertIn("check_experiment_registry.py", guarded_gate["command"])
        self.assertIn("test_run_managed_experiment.py", guarded_gate["command"])
        self.assertIn("$experiment-lifecycle", guarded_gate["handoff"])
        self.assertIn("$test-design", guarded_gate["handoff"])

    def test_parent_agentcanon_experiment_tool_path_keeps_lifecycle_guard(self) -> None:
        """Parent submodule paths should keep managed experiment execution routing."""
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--root",
                str(PROJECT_ROOT),
                "--format",
                "json",
                "vendor/agent-canon/tools/experiments/run_managed_experiment.py",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        gates = {gate["gate"] for gate in payload["predicted_gates"]}
        self.assertIn("experiment_execution_surface_guard", gates)
        self.assertNotIn("agentcanon_new_tool_source_route", gates)

    def test_changed_mode_uses_git_status_when_no_paths_are_given(self) -> None:
        """Changed mode should produce pass when a new repo has no changed files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            result = subprocess.run(
                [sys.executable, str(TOOL), "--root", str(root), "--changed"],
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertIn("TOOL_REJECTION_PREFLIGHT=pass", result.stdout)
        self.assertIn("TOOL_REJECTION_PREDICTED_GATES=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
