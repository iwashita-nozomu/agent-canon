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
            '--candidate "${AGENT_CANON_HOOK_ARCHIVE_DIR:-'
            '${AGENT_CANON_SOURCE_ROOT}/.agent-canon/log-archive}"'
        )
        archive_boundary_marker = "--purpose run-all-checks-hook-archive"
        explicit_eval_marker = "--purpose run-all-checks-explicit-eval-log"
        temporary_eval_marker = "--purpose run-all-checks-eval-log"
        cleanup_marker = "--purpose run-all-checks-cleanup"
        producer_marker = (
            'run_accumulated_agent_evals.py" "${accumulated_eval_args[@]}"'
        )
        checker_marker = 'eval_accumulation_check.py" 2>&1; then'
        command_env_marker = (
            'AGENT_CANON_HOOK_ARCHIVE_DIR="${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}"'
        )

        self.assertIn(archive_marker, text)
        self.assertIn(archive_boundary_marker, text)
        self.assertIn(explicit_eval_marker, text)
        self.assertIn(temporary_eval_marker, text)
        self.assertIn(cleanup_marker, text)
        self.assertIn(command_env_marker, text)
        self.assertIn(
            '--run-id run-all-checks --log-dir "${AGENT_CANON_CI_EVAL_LOG_DIR_VALUE}"',
            text,
        )
        self.assertLess(text.index(archive_marker), text.index(producer_marker))
        self.assertLess(text.index(archive_boundary_marker), text.index(producer_marker))
        self.assertLess(text.index(producer_marker), text.index(checker_marker))
        self.assertNotIn("export AGENT_CANON_HOOK_ARCHIVE_DIR", text)

    def test_eval_accumulation_runs_only_in_standalone_source(self) -> None:
        """run_all_checks runs accumulated eval checks only in standalone AgentCanon source."""
        text = SCRIPT.read_text(encoding="utf-8")

        standalone_condition = 'if [[ "${AGENT_CANON_REPOSITORY_MODE}" == "standalone_source" ]]; then'
        mode_definition = (
            'if [[ -d "${WORKSPACE_ROOT}/vendor/agent-canon" && -f "${WORKSPACE_ROOT}/.gitmodules" ]]; then'
        )
        parent_template_mode = (
            'AGENT_CANON_REPOSITORY_MODE="template_or_derived"'
        )
        standalone_marker = (
            'accumulated_eval_args=(--run-id run-all-checks --log-dir "${AGENT_CANON_CI_EVAL_LOG_DIR_VALUE}")'
        )
        standalone_eval_run = (
            'run_accumulated_agent_evals.py" "${accumulated_eval_args[@]}" 2>&1; then'
        )
        skip_eval_mark = "ACCUMULATED_AGENT_EVAL=skip reason=agentcanon_source_owned_gate"
        skip_check_mark = "EVAL_ACCUMULATION=skip reason=agentcanon_source_owned_gate"

        self.assertIn(standalone_condition, text)
        self.assertIn(mode_definition, text)
        self.assertIn(parent_template_mode, text)
        self.assertIn(standalone_marker, text)
        self.assertIn(standalone_eval_run, text)
        self.assertIn(skip_eval_mark, text)
        self.assertIn(skip_check_mark, text)

        standalone_condition_index = text.index(standalone_condition)
        skip_eval_index = text.index(skip_eval_mark)
        skip_check_index = text.index(skip_check_mark)
        producer_index = text.index(standalone_eval_run)
        checker_index = text.index('eval_accumulation_check.py" 2>&1; then')

        self.assertLess(standalone_condition_index, producer_index)
        self.assertLess(standalone_condition_index, checker_index)
        self.assertLess(standalone_condition_index, skip_eval_index)
        self.assertLess(standalone_condition_index, skip_check_index)
        self.assertLess(producer_index, checker_index)
        self.assertLess(producer_index, skip_eval_index)
        self.assertLess(skip_eval_index, skip_check_index)

    def test_mode_collision_with_root_cargo_and_vendor_submodule_skips_accumulated_eval(self) -> None:
        """Root Cargo.toml plus vendored submodule markers classify as template_or_derived."""
        text = SCRIPT.read_text(encoding="utf-8")

        standalone_mode_marker = 'AGENT_CANON_REPOSITORY_MODE="standalone_source"'
        template_mode_marker = 'AGENT_CANON_REPOSITORY_MODE="template_or_derived"'
        skip_eval_mark = "ACCUMULATED_AGENT_EVAL=skip reason=agentcanon_source_owned_gate"
        skip_check_mark = "EVAL_ACCUMULATION=skip reason=agentcanon_source_owned_gate"

        self.assertGreater(text.count(standalone_mode_marker), 0)
        self.assertEqual(text.count(template_mode_marker), 1)
        self.assertEqual(text.count(skip_eval_mark), 1)
        self.assertEqual(text.count(skip_check_mark), 1)
        self.assertIn(
            'if [[ -d "${WORKSPACE_ROOT}/vendor/agent-canon" && -f "${WORKSPACE_ROOT}/.gitmodules" ]]; then',
            text,
        )
        self.assertIn("AGENT_CANON_SOURCE_ROOT=\"${WORKSPACE_ROOT}/vendor/agent-canon\"", text)

    def test_experiment_registry_gate_can_be_skipped(self) -> None:
        """The optional experiment gate has explicit parser and guard wiring."""
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("SKIP_EXPERIMENTS=0", text)
        self.assertIn("--skip-experiments)", text)
        self.assertIn("SKIP_EXPERIMENTS=1", text)
        self.assertIn('if [ "$SKIP_EXPERIMENTS" -eq 1 ]; then', text)
        skip_marker = "EXPERIMENT_REGISTRY=skip reason=skip_experiments_option"
        self.assertIn(skip_marker, text)
        self.assertIn(
            "experiment registry validation skipped by --skip-experiments",
            text,
        )
        self.assertLess(
            text.index('if [ "$SKIP_EXPERIMENTS" -eq 1 ]; then'),
            text.index("check_experiment_registry.py"),
        )

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

    def test_all_checks_invokes_agent_canon_via_parent_boundary_script(self) -> None:
        """The boundary adapter should be used for agent-canon execution."""
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            'python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" exec-parent-bound',
            text,
        )
        self.assertIn('--source-root "${AGENT_CANON_SOURCE_ROOT}"', text)
        self.assertIn("--purpose run-all-checks-script", text)
        self.assertIn("verify-child", text)

    def test_all_checks_installs_setup_cleanup_before_allocations(self) -> None:
        """A rejected late override must not leave earlier setup directories."""
        text = SCRIPT.read_text(encoding="utf-8")

        trap_marker = "trap cleanup_run_all_checks_temp EXIT"
        hook_allocation = (
            'python3 "${AGENT_CANON_BOUNDARY_SCRIPT}" ensure-dir \\\n'
            '    --root "${WORKSPACE_ROOT}" \\\n'
            '    --candidate "${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}"'
        )
        self.assertIn(trap_marker, text)
        self.assertIn(hook_allocation, text)
        self.assertLess(text.index(trap_marker), text.index(hook_allocation))
        self.assertIn("--purpose run-all-checks-setup-rollback", text)

    def test_all_checks_removes_home_tools_defaults_for_cli_target(self) -> None:
        """CLI fallback should no longer infer target paths from HOME/.tools."""
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('AGENT_CANON_CLI_TARGET_DIR="${AGENT_CANON_CLI_TARGET_DIR:-${WORKSPACE_ROOT}/.agent-canon/cache/cargo-target}"', text)
        self.assertNotIn('${HOME}/.tools/agent-canon/cargo-target', text)

    def test_pr_gate_has_no_legacy_profile(self) -> None:
        """The PR gate must keep one explicit full maintenance/source route."""
        pr_text = PR_SCRIPT.read_text(encoding="utf-8")

        legacy_flag = "--integration" + "-only"
        legacy_profile = "integration" + "_only"
        self.assertNotIn(legacy_flag, pr_text)
        self.assertNotIn(legacy_profile, pr_text)

    def test_pr_gate_receipt_uses_source_owned_binary_status(self) -> None:
        """The producer and consumer accept only source or skipped receipts."""
        ci_text = SCRIPT.read_text(encoding="utf-8")
        pr_text = PR_SCRIPT.read_text(encoding="utf-8")
        selector_text = PR_SELECTOR.read_text(encoding="utf-8")

        self.assertIn('PR_GATE_DEPENDENCY_SOURCE_STATUS="not_applicable"', ci_text)
        self.assertIn('status=source)', ci_text)
        self.assertIn('status=skipped)', ci_text)
        self.assertIn('pr_gate_receipt.py" validate', ci_text)
        self.assertIn("PR_GATE_DEPENDENCY_SOURCE_STATUS=skipped", pr_text)
        self.assertIn("parent_graph_completeness_not_selected", selector_text)
        self.assertIn("write_pr_gate_receipt \\", pr_text)
        self.assertIn('"${PR_GATE_DEPENDENCY_SOURCE_REASON}"', pr_text)
        self.assertIn('"${PR_GATE_DEPENDENCY_SOURCE_EVIDENCE}"', pr_text)
        self.assertIn("--selector-reason", pr_text)
        self.assertIn("--selector-evidence", pr_text)
        self.assertIn("validated_source_receipt_consumed", ci_text)
        self.assertNotIn("strict_dependency_status", ci_text)
        self.assertNotIn("PR_GATE_DEPENDENCY_GRAPH_STATUS", ci_text)

    def test_pr_gate_keeps_structure_and_projection_checks_without_pin_integrity(self) -> None:
        """Pin freshness is not a parent gate, while structure/projection checks remain."""
        pr_text = PR_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("agentcanon_pr_branch_integrity", pr_text)
        self.assertNotIn("agentcanon_pr_submodule_remote_reachable", pr_text)
        self.assertNotIn("agentcanon_pr_branch_pending", pr_text)
        self.assertNotIn("run_pr_integrity_check", pr_text)
        self.assertNotIn("submodule-gitlink-worktree-mismatch", pr_text)
        self.assertNotIn(
            "submodule-pinned-commit-unreachable-from-configured-remote", pr_text
        )
        self.assertIn("agentcanon_pr_submodule_snapshot", pr_text)
        self.assertIn("AGENT_CANON_SUBMODULE_EVIDENCE=pass", pr_text)
        self.assertIn("run_shared_surface_check", pr_text)
        self.assertIn("AGENT_CANON_PR_DEPENDENCY_SOURCE_GATE=not_required", pr_text)
        self.assertIn("agentcanon_pr_branch_dirty", pr_text)
        self.assertIn("AGENT_CANON_PR_LATEST_DIRTY_AGENTCANON_WORKTREE=yes", pr_text)
        self.assertNotIn("deferred_branch_pr", pr_text)

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

        self.assertIn('bash "${CANON_CI_ROOT}/run_python_quality_checks.sh"', ci_text)
        self.assertIn("tools/ci/run_python_quality_checks.sh", pre_review_text)
        self.assertIn(
            "python_quality_runner=tools/ci/run_python_quality_checks.sh",
            pre_review_text,
        )
        self.assertIn("exec-parent-bound", pre_review_text)
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
