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
        eval_default_marker = 'AGENT_CANON_CI_EVAL_LOG_DIR_VALUE="${AGENT_CANON_CI_EVAL_LOG_DIR}"'
        state_default_marker = (
            'AGENT_CANON_CI_EVAL_LOG_DIR_VALUE="${WORKSPACE_ROOT}/.state/agent-eval-runs/run-all-checks"'
        )
        producer_marker = 'tools/agent_tools/run_accumulated_agent_evals.py "${accumulated_eval_args[@]}"'
        checker_marker = "tools/agent_tools/eval_accumulation_check.py"
        command_env_marker = 'AGENT_CANON_HOOK_ARCHIVE_DIR="${AGENT_CANON_CI_HOOK_ARCHIVE_DIR}"'

        self.assertIn(archive_marker, text)
        self.assertIn(mkdir_marker, text)
        self.assertIn(eval_default_marker, text)
        self.assertIn(state_default_marker, text)
        self.assertIn(command_env_marker, text)
        self.assertIn('--run-id run-all-checks --log-dir "${AGENT_CANON_CI_EVAL_LOG_DIR_VALUE}"', text)
        self.assertLess(text.index(archive_marker), text.index(producer_marker))
        self.assertLess(text.index(mkdir_marker), text.index(producer_marker))
        self.assertLess(text.index(producer_marker), text.index(checker_marker))
        self.assertNotIn("export AGENT_CANON_HOOK_ARCHIVE_DIR", text)

    def test_pr_gate_reuses_quick_ci_without_repeating_parent_gates(self) -> None:
        """The PR gate should not rerun AgentCanon checks it already executed directly."""
        ci_text = SCRIPT.read_text(encoding="utf-8")
        pr_text = PR_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("--skip-docs", ci_text)
        self.assertIn("--skip-github-workflows", ci_text)
        self.assertIn("DOCS_CHECKS=skip reason=already_checked_by_parent_gate", ci_text)
        self.assertIn(
            "GITHUB_WORKFLOW_CHECKS=skip reason=already_checked_by_parent_gate",
            ci_text,
        )
        self.assertIn(
            "PR_QUICK_CI_ARGS=(--quick --skip-docs --skip-github-workflows)",
            pr_text,
        )

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
        self.assertIn('python_quality_args+=(--quick)', ci_text)
        self.assertIn("PYTHON_QUALITY_CHECKS=pass", quality_text)
        self.assertNotIn("python3 -m pyright", pre_review_text)
        self.assertNotIn("python3 -m pytest", pre_review_text)
        self.assertNotIn("python3 -m ruff", pre_review_text)


if __name__ == "__main__":
    unittest.main()
