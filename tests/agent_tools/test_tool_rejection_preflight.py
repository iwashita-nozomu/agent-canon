# @dependency-start
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
        self.assertIn("gate:module_boundary_guard", result.stdout)
        self.assertIn("gate:helper_first_guard", result.stdout)
        self.assertIn("gate:oop_readability_guard", result.stdout)
        self.assertIn("gate:helper_inventory_guard", result.stdout)
        self.assertIn("gate:style_checker_guard", result.stdout)
        self.assertIn("gate:dependency_review", result.stdout)
        self.assertIn("gate:log_surface_inventory_guard", result.stdout)
        self.assertIn("TOOL_REJECTION_PREDICTED_GATE=", result.stdout)

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

    def test_skill_path_predicts_mirror_and_log_surface_gates(self) -> None:
        """Skill edits should require mirror and log-surface validation."""
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
        self.assertIn("skill_mirror_sync", gates)
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
