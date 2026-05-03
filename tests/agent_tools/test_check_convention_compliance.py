"""Tests for convention compliance wiring verifier."""

# @dependency-start
# responsibility Tests convention compliance verifier behavior.
# upstream implementation ../../tools/agent_tools/check_convention_compliance.py verifier  # noqa: E501
# upstream design ../../documents/conventions/README.md convention index
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "check_convention_compliance.py"


class CheckConventionComplianceTest(unittest.TestCase):
    """Verify convention compliance checker behavior."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a root."""
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_current_repository_passes(self) -> None:
        """The canonical repository satisfies the convention wiring gate."""
        result = self.run_checker(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CONVENTION_COMPLIANCE=pass", result.stdout)
        self.assertIn("CONVENTION_COMPLIANCE_FINDINGS=0", result.stdout)

    def test_missing_workflow_hook_fails(self) -> None:
        """A workflow prompt without the verifier marker is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = root / "agents" / "workflows" / "example-workflow.md"
            workflow.write_text("# Example\nNo verifier here.\n", encoding="utf-8")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "workflow_hook:agents/workflows/example-workflow.md",
                result.stdout,
            )
            self.assertIn("missing-convention-compliance-gate", result.stdout)

    def test_json_output_is_machine_readable(self) -> None:
        """JSON output exposes status and finding records."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            (root / "agents" / "evals" / "skill_workflow_prompt_eval.toml").write_text(
                "version = 1\n",
                encoding="utf-8",
            )

            result = self.run_checker(root, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "fail")
            self.assertTrue(payload["findings"])

    def copy_minimal_repo(self, root: Path) -> None:
        """Create the minimum tree needed by the checker."""
        files = {
            "documents/conventions/README.md": "conventions\n",
            "documents/conventions/common/01_principles.md": (
                "check_hardcoded_numbers.py\n"
            ),
            "documents/conventions/common/02_naming.md": "naming\n",
            "documents/conventions/common/03_comments.md": "comments\n",
            "documents/conventions/common/04_operators.md": "operators\n",
            "documents/conventions/common/05_docs.md": "docs\n",
            "documents/conventions/python/01_scope.md": "scope\n",
            "documents/conventions/python/04_type_annotations.md": "types\n",
            "documents/conventions/python/06_comments.md": "comments\n",
            "documents/conventions/python/07_type_checker.md": "type checker\n",
            "documents/conventions/python/09_file_roles.md": "roles\n",
            "documents/conventions/python/11_naming.md": "naming\n",
            "documents/conventions/python/15_jax_rules.md": "jax\n",
            "documents/conventions/python/20_benchmark_policy.md": "benchmark\n",
            "documents/conventions/python/30_experiment_directory_structure.md": (
                "experiments\n"
            ),
            "documents/coding-conventions-python.md": "python\n",
            "documents/coding-conventions-cpp.md": "cpp\n",
            "documents/coding-conventions-project.md": "project\n",
            "documents/coding-conventions-house-style.md": "house\n",
            "documents/coding-conventions-testing.md": "testing\n",
            "documents/coding-conventions-reviews.md": "reviews\n",
            "documents/coding-conventions-experiments.md": "experiments\n",
            "documents/coding-conventions-logging.md": "logging\n",
            "documents/algorithm-implementation-boundary.md": "algorithm\n",
            "documents/object-oriented-design.md": "analyze_oop_readability.py\n",
            "documents/REVIEW_PROCESS.md": "review\n",
            "agents/canonical/CODEX_WORKFLOW.md": (
                "Close-Out Prohibitions\n"
                "user-facing completion\n"
                "repo_wide_static_analysis_complete\n"
                "repo_wide_dependency_tools_complete\n"
                "run_repo_dependency_review.sh\n"
            ),
            "agents/workflows/example-workflow.md": "check_convention_compliance.py\n",
            ".agents/skills/agent-orchestration/SKILL.md": (
                "$agent-orchestration $codex-task-workflow $subagent-bootstrap "
                "task-shape skill check_convention_compliance.py\n"
            ),
            "agents/skills/agent-orchestration.md": (
                "$agent-orchestration $codex-task-workflow $subagent-bootstrap "
                "task-shape skill check_convention_compliance.py\n"
            ),
            "agents/TASK_WORKFLOWS.md": (
                "$agent-orchestration $codex-task-workflow $subagent-bootstrap "
                "task-shape skill check_convention_compliance.py\n"
            ),
            "agents/evals/skill_workflow_prompt_eval.toml": (
                "check_convention_compliance.py CONVENTION-WORKFLOW CONVENTION-SKILL\n"
                "evaluate_skill_workflow_prompts.py\n"
            ),
            "agents/evals/agent_behavior_eval.toml": "behavior\n",
            "agents/templates/closeout_gate.md": (
                "evaluate_agent_run.py run_repo_dependency_review.sh\n"
            ),
            "agents/workflows/hypothesis-validation-workflow.md": (
                "scan_code_dependencies.sh\n"
            ),
            "agents/workflows/comprehensive-refactoring-workflow.md": (
                "analyze_oop_readability.py check_convention_compliance.py\n"
            ),
            "agents/workflows/adaptive-improvement-workflow.md": (
                "evaluate_skill_workflow_prompts.py check_convention_compliance.py\n"
            ),
            "tools/ci/run_all_checks.sh": (
                "check_hardcoded_numbers.py check_convention_compliance.py\n"
            ),
        }
        tools = [
            "run_repo_dependency_review.sh",
            "scan_code_dependencies.sh",
            "check_hardcoded_numbers.py",
            "analyze_oop_readability.py",
            "evaluate_skill_workflow_prompts.py",
            "evaluate_agent_run.py",
            "check_convention_compliance.py",
        ]
        for path, text in files.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        for tool in tools:
            target = root / "tools" / "agent_tools" / tool
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("#!/usr/bin/env bash\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
