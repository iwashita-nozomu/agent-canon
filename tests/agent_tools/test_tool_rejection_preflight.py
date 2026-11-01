# @dependency-start
# contract test
# responsibility Tests tool rejection preflight gate prediction.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/tool_rejection_preflight.rs predicts hook/tool rejection gates
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md defines handoff packet fields
# @dependency-end
"""Tests for predicted tool rejection handoff gates."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "bin" / "agent-canon"
SELECTOR = "tool-rejection-preflight"
# Golden stdout was captured from the retired Python owner at 20a78515; the
# test permits only the explicit command and source-owner relocations below.
LEGACY_COMMAND = "python3 tools/validation/semantic/tools/tool_rejection_preflight.py"
NATIVE_COMMAND = "tools/bin/agent-canon tool-rejection-preflight"
LEGACY_WORKFLOW_SOURCE = "tools/validation/ci/checks/check_github_workflows.py"
NATIVE_WORKFLOW_SOURCE = "tools/runtime/dispatch/agent-canon/src/github_workflow_check.rs"
ORACLE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "tool_rejection_preflight"
COMBINED_PATHS = (
    "tools/agent_tools/new_shared_checker_oracle.py",
    "tools/agent_tools/../agent_tools/new_shared_checker_oracle.py",
    "tools/agent_tools/new_shared_checker_oracle.py",
    "src/model.cpp",
    ".codex/hooks.json",
    ".codex/hooks/hook_dispatcher.py",
    ".github/workflows/build.yml",
    "agents/COMMUNICATION_PROTOCOL.md",
    "experiments/registry.toml",
    "tools/runtime/dispatch/agent-canon/src/notebook_quality.rs",
    "vendor/skills/example/SKILL.md",
    "scratch-drift/example.txt",
    ".codex/personal/skills/subagent-bootstrap/SKILL.md",
    "notebooks/example.ipynb",
    'scratch/quote"file.py',
    "scratch/日本語.py",
    "scratch/emoji-😀.py",
    "../outside.rs",
)


class ToolRejectionPreflightTest(unittest.TestCase):
    """Validate gate prediction from planned paths."""

    def run_native(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(TOOL), SELECTOR, *arguments],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def python_golden(self, filename: str) -> str:
        baseline = (ORACLE_ROOT / filename).read_text(encoding="utf-8")
        self.assertIn(LEGACY_COMMAND, baseline)
        expected = baseline.replace(LEGACY_COMMAND, NATIVE_COMMAND)
        expected = expected.replace(
            "python3 " + LEGACY_WORKFLOW_SOURCE,
            "tools/bin/agent-canon check-github-workflows",
        )
        expected = expected.replace(LEGACY_WORKFLOW_SOURCE, NATIVE_WORKFLOW_SOURCE)
        self.assertNotIn(LEGACY_COMMAND, expected)
        return expected

    def test_repository_root_aliases_report_one_dot_path(self) -> None:
        """Empty and dot inputs identify the repository root as a single path."""
        result = self.run_native(
            "--root", str(PROJECT_ROOT), "--format", "json", "", ".", "./"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["predicted_gate_count"], 1)
        self.assertEqual(payload["predicted_gates"][0]["path"], ".")

    def test_backslash_paths_keep_the_platform_path_meaning(self) -> None:
        """POSIX backslashes remain filename characters in paths and routing."""
        result = self.run_native(
            "--root", str(PROJECT_ROOT), "--format", "json", "tools\\literal.py"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        gates = json.loads(result.stdout)["predicted_gates"]
        expected = "tools/literal.py" if os.name == "nt" else "tools\\literal.py"
        self.assertEqual({gate["path"] for gate in gates}, {expected})
        self.assertEqual(
            any(gate["gate"] == "tool_catalog" for gate in gates), os.name == "nt"
        )

    def test_help_describes_prediction_as_optional_diagnostic(self) -> None:
        """CLI guidance must not reintroduce a mandatory edit preflight."""
        result = subprocess.run(
            [str(TOOL), "tool-rejection-preflight", "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        help_text = " ".join(result.stdout.split())
        self.assertIn("Optionally predict candidate", help_text)
        self.assertIn("not edit authorization or required validation", help_text)

    def test_combined_gate_families_match_complete_python_text_and_json(self) -> None:
        """Complete historical output stays stable apart from the retired selector."""
        for output_format, preferred_format, fixture in (
            ("text", "json", "python_combined_text.txt"),
            ("json", "text", "python_combined_json.json"),
        ):
            with self.subTest(output_format=output_format):
                result = self.run_native(
                    "--root",
                    ".",
                    "--r",
                    ".",
                    "--format",
                    preferred_format,
                    "--f",
                    output_format,
                    *COMBINED_PATHS,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(result.stdout, self.python_golden(fixture))

    def test_changed_mode_matches_complete_python_text_and_json(self) -> None:
        """Changed-mode path selection matches Python splitlines and Git filters."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            for key, value in (
                ("user.name", "Preflight Oracle"),
                ("user.email", "preflight@example.invalid"),
                ("core.quotePath", "false"),
            ):
                subprocess.run(
                    ["git", "-C", str(root), "config", key, value],
                    check=True,
                    capture_output=True,
                    text=True,
                )

            (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
            (root / "changed.py").write_text("value = 1\n", encoding="utf-8")
            (root / "deleted.md").write_text("base\n", encoding="utf-8")
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "add",
                    ".gitignore",
                    "changed.py",
                    "deleted.md",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "commit", "-m", "baseline"],
                check=True,
                capture_output=True,
                text=True,
            )

            (root / "changed.py").write_text("value = 2\n", encoding="utf-8")
            (root / "deleted.md").unlink()
            (root / "untracked.txt").write_text("untracked\n", encoding="utf-8")
            (root / "ignored.txt").write_text("ignored\n", encoding="utf-8")
            (root / "unicode\u2028separator.py").write_text(
                "unicode separator\n",
                encoding="utf-8",
            )

            for output_format, fixture in (
                ("text", "python_changed_text.txt"),
                ("json", "python_changed_json.json"),
            ):
                with self.subTest(output_format=output_format):
                    result = self.run_native(
                        "--root",
                        str(root),
                        "--changed",
                        "--format",
                        output_format,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stderr, "")
                    self.assertEqual(result.stdout, self.python_golden(fixture))

    def test_python_tool_path_predicts_code_and_log_surface_gates(self) -> None:
        """Python tool edits should carry code, helper, dependency, and log gates."""
        result = subprocess.run(
            [
                str(TOOL),
                "tool-rejection-preflight",
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
        self.assertIn("gate:responsibility_scope", result.stdout)
        self.assertIn("gate:oop_readability_guard", result.stdout)
        self.assertIn("gate:solid_evidence_gate", result.stdout)
        self.assertIn("gate:style_checker_guard", result.stdout)
        self.assertIn("gate:dependency_review", result.stdout)
        self.assertNotIn("gate:log_surface_inventory_guard", result.stdout)
        self.assertIn("TOOL_REJECTION_PREDICTED_GATE=", result.stdout)

    def test_standalone_new_tool_source_routes_agentcanon_gates(self) -> None:
        """A new standalone tool source gets the canonical ownership gates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "tools" / "agent_tools").mkdir(parents=True)

            result = subprocess.run(
                [
                    str(TOOL),
                    "tool-rejection-preflight",
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

        self.assertIn("tools/agent_tools/new_shared_checker.py", paths)
        self.assertIn("agentcanon_new_tool_source_route", gates)
        self.assertIn("responsibility_scope", gates)
        self.assertIn("tool_catalog", gates)
        self.assertNotIn("log_surface_inventory_guard", gates)
        self.assertTrue(
            any(
                "git status --short --branch" in command
                for command in commands_by_gate["agentcanon_new_tool_source_route"]
            )
        )
        self.assertTrue(
            any(
                "tools/bin/agent-canon tool-catalog" in command
                for command in commands_by_gate["tool_catalog"]
            )
        )

    def test_vendor_library_path_predicts_library_guard(self) -> None:
        """Vendored dependency implementation edits should route to library guard."""
        result = subprocess.run(
            [
                str(TOOL),
                "tool-rejection-preflight",
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
                str(TOOL),
                "tool-rejection-preflight",
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
                str(TOOL),
                "tool-rejection-preflight",
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

    def test_markdown_path_predicts_style_checker_gate(self) -> None:
        """Markdown edits should carry automatic style checker coverage."""
        result = subprocess.run(
            [
                str(TOOL),
                "tool-rejection-preflight",
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
        self.assertEqual(
            sum(
                gate["gate"] == "responsibility_scope"
                for gate in payload["predicted_gates"]
            ),
            1,
        )

    def test_unknown_path_predicts_responsibility_assignment(self) -> None:
        """Unscoped planned paths should route through responsibility assignment."""
        result = subprocess.run(
            [
                str(TOOL),
                "tool-rejection-preflight",
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
        self.assertRegex(
            responsibility_gates[0]["handoff"],
            r"(assign this planned path to exactly one responsibility-scope\.toml scope|repair responsibility-scope\.toml)",
        )

    def test_skill_path_predicts_log_surface_gate(self) -> None:
        """Skill edits should require Codex log-surface validation."""
        result = subprocess.run(
            [
                str(TOOL),
                "tool-rejection-preflight",
                "--root",
                str(PROJECT_ROOT),
                "--format",
                "json",
                ".codex/personal/skills/subagent-bootstrap/SKILL.md",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        gates = {gate["gate"] for gate in payload["predicted_gates"]}
        self.assertNotIn("skill_mirror_sync", gates)
        self.assertNotIn("log_surface_inventory_guard", gates)

    def test_protocol_path_predicts_convention_gate(self) -> None:
        """Protocol docs should route to convention compliance checks."""
        result = subprocess.run(
            [
                str(TOOL),
                "tool-rejection-preflight",
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
                str(TOOL),
                "tool-rejection-preflight",
                "--root",
                str(PROJECT_ROOT),
                "--format",
                "json",
                "tools/experiments/execution/run_managed_experiment.py",
                "tools/validation/ci/checks/check_experiment_registry.py",
                "documents/experiments/experiment-registry.md",
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
                "tools/experiments/execution/run_managed_experiment.py",
                "tools/validation/ci/checks/check_experiment_registry.py",
                "documents/experiments/experiment-registry.md",
                "experiments/registry.toml",
            },
        )
        guarded_gate = next(
            gate
            for gate in payload["predicted_gates"]
            if gate["gate"] == "experiment_execution_surface_guard"
        )
        self.assertIn(
            "tools.validation.ci.checks.check_experiment_registry",
            guarded_gate["command"],
        )
        self.assertIn("test_run_managed_experiment.py", guarded_gate["command"])
        self.assertIn("$experiment-lifecycle", guarded_gate["handoff"])
        self.assertIn("$test-design", guarded_gate["handoff"])

    def test_changed_mode_uses_git_status_when_no_paths_are_given(self) -> None:
        """Changed mode should produce pass when a new repo has no changed files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            result = subprocess.run(
                [
                    str(TOOL),
                    "tool-rejection-preflight",
                    "--root",
                    str(root),
                    "--changed",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertIn("TOOL_REJECTION_PREFLIGHT=pass", result.stdout)
        self.assertIn("TOOL_REJECTION_PREDICTED_GATES=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
