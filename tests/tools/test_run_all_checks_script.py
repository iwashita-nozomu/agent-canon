"""Tests for the integrated CI shell entrypoint."""

# @dependency-start
# contract test
# responsibility Tests integrated CI shell wiring that is too expensive to execute wholesale.
# upstream implementation ../../tools/ci/run_all_checks.sh runs repository and AgentCanon CI gates
# upstream implementation ../../tools/agent_tools/run_accumulated_agent_evals.py writes accumulated eval reports
# upstream implementation ../../tools/agent_tools/eval_accumulation_check.py validates accumulated eval reports
# upstream implementation ../../tools/agent_tools/runtime_log_paths.py resolves mounted log archive paths
# @dependency-end

from __future__ import annotations

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "run_all_checks.sh"
PR_SCRIPT = PROJECT_ROOT / "tools" / "ci" / "check_agent_canon_pr.sh"
PR_SELECTOR = PROJECT_ROOT / "tools" / "ci" / "agent_canon_pr_graph_selector.py"
PRE_REVIEW_SCRIPT = PROJECT_ROOT / "tools" / "ci" / "pre_review.sh"
PYTHON_QUALITY_SCRIPT = PROJECT_ROOT / "tools" / "ci" / "run_python_quality_checks.sh"


class RunAllChecksScriptTest(unittest.TestCase):
    """Validate static CI entrypoint contracts."""

    def test_eval_accumulation_has_archive_before_producers(self) -> None:
        """Accumulated eval producers need a writable AgentCanon log archive."""
        text = SCRIPT.read_text(encoding="utf-8")

        archive_marker = (
            'AGENT_CANON_CI_HOOK_ARCHIVE_DIR="${AGENT_CANON_HOOK_ARCHIVE_DIR:-'
            '${AGENT_CANON_SOURCE_ROOT}/.agent-canon/log-archive}"'
        )
        mkdir_marker = 'mkdir -p "${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}"'
        eval_default_marker = (
            'AGENT_CANON_CI_EVAL_LOG_DIR_VALUE="${AGENT_CANON_CI_EVAL_LOG_DIR}"'
        )
        state_default_marker = 'AGENT_CANON_CI_EVAL_LOG_DIR_VALUE="${WORKSPACE_ROOT}/.state/agent-eval-runs/run-all-checks"'
        producer_marker = 'tools/agent_tools/run_accumulated_agent_evals.py "${accumulated_eval_args[@]}"'
        checker_marker = "tools/agent_tools/eval_accumulation_check.py"
        command_env_marker = (
            'AGENT_CANON_HOOK_ARCHIVE_DIR="${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}"'
        )

        self.assertIn(archive_marker, text)
        self.assertIn(mkdir_marker, text)
        self.assertIn(eval_default_marker, text)
        self.assertIn(state_default_marker, text)
        self.assertIn(command_env_marker, text)
        self.assertIn(
            '--run-id run-all-checks --log-dir "${AGENT_CANON_CI_EVAL_LOG_DIR_VALUE}"',
            text,
        )
        self.assertLess(text.index(archive_marker), text.index(producer_marker))
        self.assertLess(text.index(mkdir_marker), text.index(producer_marker))
        self.assertLess(text.index(producer_marker), text.index(checker_marker))
        self.assertNotIn("export AGENT_CANON_HOOK_ARCHIVE_DIR", text)

    def test_pr_gate_only_keeps_shared_surface_ownership(self) -> None:
        """The PR gate emits ownership evidence without running run_all_checks."""
        ci_text = SCRIPT.read_text(encoding="utf-8")
        pr_text = PR_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("--skip-docs", ci_text)
        self.assertIn("--skip-github-workflows", ci_text)
        self.assertIn("DOCS_CHECKS=skip reason=already_checked_by_parent_gate", ci_text)
        self.assertIn(
            "GITHUB_WORKFLOW_CHECKS=skip reason=already_checked_by_parent_gate",
            ci_text,
        )
        self.assertIn("AGENT_CANON_PR_PROJECT_QUALITY=delegated", pr_text)
        self.assertIn('local owner="parent_ci"', pr_text)
        self.assertIn('owner="agentcanon_project_ci"', pr_text)
        self.assertNotIn('bash "${CANON_TOOLS_ROOT}/ci/run_all_checks.sh"', pr_text)
        self.assertNotIn("PR_QUICK_CI_ARGS=", pr_text)

    def test_pr_gate_has_no_legacy_profile(self) -> None:
        """The PR gate must keep one explicit full maintenance/source route."""
        pr_text = PR_SCRIPT.read_text(encoding="utf-8")

        legacy_flag = "--integration" + "-only"
        legacy_profile = "integration" + "_only"
        self.assertNotIn(legacy_flag, pr_text)
        self.assertNotIn(legacy_profile, pr_text)

    def test_pr_gate_receipt_accepts_prepared_or_skipped_dependency_graph(self) -> None:
        """Parent PRs may skip graph completeness when its profile does not require it."""
        ci_text = SCRIPT.read_text(encoding="utf-8")
        pr_text = PR_SCRIPT.read_text(encoding="utf-8")
        selector_text = PR_SELECTOR.read_text(encoding="utf-8")

        self.assertIn('PR_GATE_DEPENDENCY_GRAPH_STATUS="not_applicable"', ci_text)
        self.assertIn('strict_dependency_status}" != "prepared"', ci_text)
        self.assertIn('strict_dependency_status}" != "skipped"', ci_text)
        self.assertIn(
            'PR_GATE_DEPENDENCY_GRAPH_STATUS="${strict_dependency_status}"',
            ci_text,
        )
        self.assertIn("PR_GATE_DEPENDENCY_GRAPH_STATUS=skipped", pr_text)
        self.assertIn("parent_graph_completeness_not_selected", selector_text)
        self.assertIn("write_pr_gate_receipt \\", pr_text)
        self.assertIn('"${PR_GATE_DEPENDENCY_GRAPH_REASON}"', pr_text)
        self.assertIn('"${PR_GATE_DEPENDENCY_GRAPH_EVIDENCE}"', pr_text)
        self.assertIn("selector_reason=%s", pr_text)
        self.assertIn("selector_evidence=%s", pr_text)
        self.assertIn(
            "skipped graph selector reason/evidence missing",
            ci_text,
        )
        self.assertIn(
            "parent PR graph completeness not required",
            ci_text,
        )

    def test_pr_gate_keeps_gitlink_and_projection_integrity_checks(self) -> None:
        """Graph completeness is optional, but publication/projection integrity remains required."""
        pr_text = PR_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("agentcanon_pr_branch_integrity", pr_text)
        self.assertIn("submodule-gitlink-worktree-mismatch", pr_text)
        self.assertIn(
            "submodule-pinned-commit-unreachable-from-configured-remote", pr_text
        )
        self.assertIn("run_shared_surface_check", pr_text)
        self.assertIn("AGENT_CANON_PR_DEPENDENCY_GRAPH_GATE=not_required", pr_text)
        self.assertNotIn("blocked_dirty_agentcanon_branch", pr_text)

    def test_pr_gate_delegates_profile_surface_and_diff_selection(self) -> None:
        """The shell gate delegates selection to the canonical fail-closed helper."""
        pr_text = PR_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("agent_canon_pr_graph_selector.py", pr_text)
        self.assertNotIn("agentcanon-shared-surface", pr_text)
        self.assertNotIn("full-confidence-candidate", pr_text)
        self.assertNotIn("agentcanon_pr_graph_migration_surface_touched", pr_text)
        self.assertNotIn("git diff --name-only", pr_text)
        self.assertNotIn("git diff --unified=0", pr_text)

    def test_python_quality_checks_are_shared(self) -> None:
        """Run-all and pre-review should use the same Python quality runner."""
        ci_text = SCRIPT.read_text(encoding="utf-8")
        pre_review_text = PRE_REVIEW_SCRIPT.read_text(encoding="utf-8")
        quality_text = PYTHON_QUALITY_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("tools/ci/run_python_quality_checks.sh", ci_text)
        self.assertIn("tools/ci/run_python_quality_checks.sh", pre_review_text)
        self.assertIn(
            "python_quality_runner=tools/ci/run_python_quality_checks.sh",
            pre_review_text,
        )
        self.assertIn("python_quality_args+=(--quick)", ci_text)
        self.assertIn("PYTHON_QUALITY_CHECKS=pass", quality_text)
        self.assertIn('PYTHON_SOURCE_PATHS+=("$candidate_path")', quality_text)
        self.assertIn('PYTHON_TEST_PATHS+=("$candidate_path")', quality_text)
        self.assertIn("find tests", quality_text)
        self.assertIn("-type f", quality_text)
        self.assertNotIn("-prune", quality_text)
        self.assertIn("if [ ${#PYTHON_TEST_PATHS[@]} -eq 0 ]; then", quality_text)
        self.assertIn("PYTEST=skip reason=no_parent_owned_tests", quality_text)
        self.assertNotIn("python3 -m pyright", pre_review_text)
        self.assertNotIn("python3 -m pytest", pre_review_text)
        self.assertNotIn("python3 -m ruff", pre_review_text)


if __name__ == "__main__":
    unittest.main()
