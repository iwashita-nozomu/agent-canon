# @dependency-start
# upstream design ../../agents/workflows/agent-learning-workflow.md agent feedback workflow
# upstream implementation ../../tools/agent_tools/evaluate_agent_run.py evaluates run bundles
# downstream implementation ../../tools/agent_tools/task_close.py consumes agent evaluation status
# @dependency-end

"""Tests for agent run evaluation."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "evaluate_agent_run.py"


def write_ready_run(report_dir: Path) -> None:
    """Write a minimal passing run bundle."""
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "user_request_contract.md").write_text(
        "\n".join(
            [
                "# User Request Contract",
                "- all_clauses_resolved: yes",
                "- forbidden_drift_detected: no",
                "- unresolved_clause_ids:",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (report_dir / "schedule.md").write_text(
        "\n".join(
            [
                "# Schedule",
                "## Stage Plan",
                "| Stage | Owner Agent | Review Agent | Inputs | Exit Criteria | Status |",
                "| ----- | ----------- | ------------ | ------ | ------------- | ------ |",
                "| requirements | manager | reviewer | request | fixed | complete |",
                "## Clause Coverage",
                "| Clause ID | Covered By Stage | Review Gate | Status |",
                "| --------- | ---------------- | ----------- | ------ |",
                "| C1 | requirements | review | complete |",
                "## Planned Work Units",
                "| Unit ID | Clause IDs | Owner | Completion Evidence | Next Gate | Status |",
                "| ------- | ---------- | ----- | ------------------- | --------- | ------ |",
                "| W1 | C1 | codex | tests | closeout | complete |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (report_dir / "work_log.md").write_text(
        "\n".join(
            [
                "# Work Log",
                "## Purpose",
                "- Record meaningful execution.",
                "## Entries",
                "- kickoff: request_clause_ids=C1 next=implementation",
                "- validation: request_clause_ids=C1 next=closeout",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (report_dir / "change_review.md").write_text(
        "# Change Review\n\n## Chunk Findings\n\nNo blocking findings.\n",
        encoding="utf-8",
    )
    (report_dir / "final_review.md").write_text(
        "# Final Review\n\n## Decision\n\napprove\n",
        encoding="utf-8",
    )
    (report_dir / "verification.txt").write_text("status=pass\n", encoding="utf-8")
    (report_dir / "closeout_gate.md").write_text(
        "\n".join(
            [
                "# Closeout Gate",
                "- validation_complete: yes",
                "- dependency_headers_complete: yes",
                "- repo_wide_dependency_tools_complete: yes",
                "- canonical_tree_head_complete: yes",
                "- commit_created: yes",
                "- push_completed: yes",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (report_dir / "retrospective.md").write_text(
        "\n".join(
            [
                "# Retrospective",
                "## What Worked",
                "- Tooling caught the issue.",
                "## What Hurt",
                "- None.",
                "## Follow-ups",
                "- None.",
                "",
            ]
        ),
        encoding="utf-8",
    )


class EvaluateAgentRunTest(unittest.TestCase):
    """Verify the run evaluation helper."""

    def test_evaluate_ready_run_writes_pass_report(self) -> None:
        """A complete run should receive a passing agent evaluation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            write_ready_run(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--write",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("AGENT_EVALUATION_STATUS=pass", result.stdout)
            report = (report_dir / "agent_evaluation.md").read_text(encoding="utf-8")
            self.assertIn("- evaluation_status: pass", report)
            self.assertIn("- feedback_actions_resolved: yes", report)

    def test_evaluate_incomplete_run_fails_with_feedback(self) -> None:
        """Missing evidence should create fix-now feedback actions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "run"
            report_dir.mkdir(parents=True)
            (report_dir / "user_request_contract.md").write_text(
                "- all_clauses_resolved: no\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--write",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AGENT_EVALUATION_STATUS=revise", result.stdout)
            self.assertIn("AGENT_EVALUATION_FEEDBACK_ACTIONS_OPEN=", result.stdout)
            report = (report_dir / "agent_evaluation.md").read_text(encoding="utf-8")
            self.assertIn("| F1 | fix-now |", report)
