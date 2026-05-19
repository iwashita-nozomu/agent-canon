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

from tools.agent_tools.check_convention_compliance import (
    AGENT_CANON_PUSH_REMOTE_MARKERS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "check_convention_compliance.py"

MINIMAL_REPO_FILES: dict[str, str] = {
    "documents/conventions/README.md": "conventions\n",
    "documents/conventions/common/01_principles.md": "check_hardcoded_numbers.py\n",
    "documents/conventions/common/02_naming.md": "check_log_helper_names.py\n",
    "documents/conventions/common/03_comments.md": "comments\n",
    "documents/conventions/common/04_operators.md": "operators\n",
    "documents/conventions/common/05_docs.md": "docs\n",
    "documents/conventions/python/01_scope.md": "scope\n",
    "documents/conventions/python/04_type_annotations.md": "check_static_any.py\n",
    "documents/conventions/python/06_comments.md": "comments\n",
    "documents/conventions/python/07_type_checker.md": "check_static_any.py\n",
    "documents/conventions/python/09_file_roles.md": "roles\n",
    "documents/conventions/python/11_naming.md": "naming\n",
    "documents/conventions/python/15_jax_rules.md": "jax\n",
    "documents/conventions/python/20_benchmark_policy.md": "benchmark\n",
    "documents/conventions/python/30_experiment_directory_structure.md": "experiments\n",
    "documents/coding-conventions-python.md": "python import_responsibility.py\n",
    "documents/coding-conventions-cpp.md": "cpp\n",
    "documents/coding-conventions-project.md": "project container_config.py\n",
    "documents/coding-conventions-house-style.md": "house\n",
    "documents/coding-conventions-testing.md": "testing\n",
    "documents/coding-conventions-reviews.md": "reviews\n",
    "documents/coding-conventions-experiments.md": "experiments\n",
    "documents/coding-conventions-logging.md": "check_log_helper_names.py\n",
    "documents/algorithm-implementation-boundary.md": "algorithm\n",
    "documents/object-oriented-design.md": "readability.py\n",
    "documents/REVIEW_PROCESS.md": "review\n",
    "documents/SHARED_RUNTIME_SURFACES.md": (
        "surface_manifest.py documents/shared-runtime-surfaces.toml owner class\n"
        ".codex/hooks.json .codex/hooks .devcontainer/ documents/README.md "
        "documents/template-bootstrap.md "
        "documents/github-first-module-and-devcontainer-policy.md "
        "memory/USER_PREFERENCES.md "
        "tests/agent_tools/ Root `tools/` is a symlink view "
        "vendor/agent-canon/tools/ "
        "Project-local automation must stay in project-owned paths\n"
    ),
    "documents/shared-runtime-surfaces.toml": (
        'mode = "standalone_only"\n'
        'owner = "agent-canon-standalone"\n'
        'path = "goal.md"\n'
        '"documents/README.md"\n'
        '"documents/template-bootstrap.md"\n'
        '".devcontainer"\n'
        '"documents/github-first-module-and-devcontainer-policy.md"\n'
        '".codex/hooks.json"\n'
        '"tests/agent_tools/test_check_convention_compliance.py"\n'
    ),
    "documents/agent-canon-parent-repo-latest-checklist.md": "checklist\n",
    "documents/responsibility-scope-management.md": "import_responsibility.py responsibility_scope.py\n",
    "documents/tools/README.md": "tool_catalog.py tool_drift.py notebook_quality.py import_responsibility.py\n",
    "tools/README.md": (
        "tool_catalog.py tool_drift.py notebook_quality.py import_responsibility.py "
        "check_runtime_profile_inventory.py\n"
    ),
    "agents/canonical/CODEX_WORKFLOW.md": (
        "Close-Out Prohibitions\n"
        "user-facing completion\n"
        "repo_wide_static_analysis_complete\n"
        "repo_wide_dependency_tools_complete\n"
        "run_repo_dependency_review.sh\n"
    ),
    "agents/workflows/example-workflow.md": (
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
    ),
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
    "agents/evals/agent_behavior_eval.toml": "behavior evaluate_agent_run.py\n",
    "agents/templates/closeout_gate.md": "evaluate_agent_run.py run_repo_dependency_review.sh\n",
    "agents/workflows/hypothesis-validation-workflow.md": (
        "scan_code_dependencies.sh\n"
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
    ),
    "agents/workflows/comprehensive-refactoring-workflow.md": (
        "readability.py check_convention_compliance.py\n"
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
    ),
    "agents/workflows/adaptive-improvement-workflow.md": (
        "evaluate_skill_workflow_prompts.py check_convention_compliance.py\n"
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
    ),
    "agents/workflows/agent-canon-pr-workflow.md": (
        "check_github_workflows.py\n"
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
        + "".join(f"{marker}\n" for marker in AGENT_CANON_PUSH_REMOTE_MARKERS)
    ),
    "tools/ci/run_all_checks.sh": (
        "check_hardcoded_numbers.py check_static_any.py "
        "check_log_helper_names.py import_responsibility.py check_convention_compliance.py "
        "tool_catalog.py tool_drift.py notebook_quality.py "
        "check_github_workflows.py container_config.py check_runtime_profile_inventory.py\n"
    ),
    "tools/ci/run_docs_checks.sh": "check_runtime_profile_inventory.py\n",
    "tools/sync_agent_canon.sh": "surface_manifest.py build_regular_specs regular_path\n",
    "agents/skills/environment-maintenance.md": "container_config.py\n",
}

MINIMAL_AGENT_TOOLS = (
    "run_repo_dependency_review.sh",
    "scan_code_dependencies.sh",
    "check_hardcoded_numbers.py",
    "check_static_any.py",
    "check_log_helper_names.py",
    "import_responsibility.py",
    "evaluate_skill_workflow_prompts.py",
    "evaluate_agent_run.py",
    "check_convention_compliance.py",
    "tool_catalog.py",
    "tool_drift.py",
    "surface_manifest.py",
    "check_runtime_profile_inventory.py",
)

MINIMAL_PYTHON_TOOLS = (
    "tools/oop/python/readability.py",
    "tools/oop/cpp/readability.py",
    "tools/validation/notebook_quality.py",
)


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

    def test_workflow_hook_requires_positive_command(self) -> None:
        """A stale mention without a run command is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = root / "agents" / "workflows" / "example-workflow.md"
            workflow.write_text(
                "# Example\nMention check_convention_compliance.py in prose only.\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-positive-convention-compliance-command",
                result.stdout,
            )

    def test_workflow_hook_rejects_suppression(self) -> None:
        """A workflow must not be able to pass by saying not to run the gate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = root / "agents" / "workflows" / "example-workflow.md"
            workflow.write_text(
                "# Example\n"
                "Before closeout, run "
                "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
                "Do not run check_convention_compliance.py for quick tasks.\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "forbidden-convention-compliance-suppression",
                result.stdout,
            )

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

    def test_agentcanon_pr_workflow_requires_remote_verification_guard(self) -> None:
        """The AgentCanon PR workflow must keep every remote verification marker."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            for marker in AGENT_CANON_PUSH_REMOTE_MARKERS:
                with self.subTest(marker=marker):
                    workflow = root / "agents" / "workflows" / "agent-canon-pr-workflow.md"
                    workflow.write_text(
                        MINIMAL_REPO_FILES["agents/workflows/agent-canon-pr-workflow.md"].replace(
                            f"{marker}\n",
                            "",
                        ),
                        encoding="utf-8",
                    )

                    result = self.run_checker(root)

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("agentcanon_push_remote_guard", result.stdout)
                    self.assertIn(f"missing-marker:{marker}", result.stdout)

    def test_missing_surface_manifest_marker_fails(self) -> None:
        """Shared surface docs must stay manifest-backed and complete."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            (root / "documents" / "SHARED_RUNTIME_SURFACES.md").write_text(
                "surface_manifest.py documents/shared-runtime-surfaces.toml\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("surface_manifest:documents/SHARED_RUNTIME_SURFACES.md", result.stdout)
            self.assertIn("missing-marker:.codex/hooks.json", result.stdout)

    def test_parent_repo_can_keep_shared_docs_only_in_vendor_canon(self) -> None:
        """A parent repo may keep AgentCanon docs out of root documents."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            for source in sorted((root / "documents").rglob("*")):
                if not source.is_file():
                    continue
                target = root / "vendor" / "agent-canon" / source.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CONVENTION_COMPLIANCE=pass", result.stdout)

    def test_normative_convention_without_verification_route_fails(self) -> None:
        """A convention source with normative assertions needs a verification route."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            (root / "documents" / "coding-conventions-python.md").write_text(
                "# Python\n\n- 公開関数には型注釈が必須です。\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("normative-lines-without-verification-route", result.stdout)

    def test_prohibition_without_prohibition_section_fails(self) -> None:
        """A convention source with prohibitions needs a prohibition section."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            (root / "documents" / "coding-conventions-python.md").write_text(
                "# Python\n\n- 型なし公開関数を禁止します。\n\n"
                "## 検証\n\n- `python3 -m pyright`\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("prohibition-lines-without-prohibition-section", result.stdout)

    def copy_minimal_repo(self, root: Path) -> None:
        """Create the minimum tree needed by the checker."""
        for path, text in MINIMAL_REPO_FILES.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        for tool in MINIMAL_AGENT_TOOLS:
            target = root / "tools" / "agent_tools" / tool
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        for tool_path in MINIMAL_PYTHON_TOOLS:
            target = root / tool_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        github_checker = root / "tools" / "ci" / "check_github_workflows.py"
        github_checker.parent.mkdir(parents=True, exist_ok=True)
        github_checker.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        container_checker = root / "tools" / "ci" / "container_config.py"
        container_checker.write_text("#!/usr/bin/env python3\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
