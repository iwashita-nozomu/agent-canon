"""Tests for intermediate waterfall gate checks."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "bootstrap_agent_run.py"
GATE_CHECK_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "waterfall_gate_check.py"


class WaterfallGateCheckTest(unittest.TestCase):
    """Verify that intermediate waterfall gates fail closed."""

    def test_requirements_gate_rejects_active_unknown_clause(self) -> None:
        """Requirements should defer unknowns instead of leaving them active."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "unknown-requirement"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "user_request_contract.md").write_text(
                "\n".join(
                    [
                        "# User Request Contract",
                        "",
                        "## Requirements Resolution Sweep",
                        "Checked notes, documents, and local code precedent.",
                        "## Resolved From Accumulated Context",
                        (
                            "| Clause ID | Resolved From | Evidence Path | Resolution | "
                            "Remaining Risk |"
                        ),
                        (
                            "| --------- | ------------- | ------------- | ---------- | "
                            "-------------- |"
                        ),
                        (
                            "| T1-C0 | repo_or_code_precedent | documents/ | "
                            "Existing workflow applies. | none |"
                        ),
                        "## Must-Do Clauses",
                        (
                            "| Clause ID | Source Bucket | User Wording Or Evidence | "
                            "Operational Interpretation | Owner Stage | Evidence Path | Status |"
                        ),
                        (
                            "| --------- | ------------- | ------------------------- | "
                            "-------------------------- | ----------- | ------------- | ------ |"
                        ),
                        (
                            "| T1-C1 | unknown_or_open_question | unclear | decide later | "
                            "requirements | user_request_contract.md | active |"
                        ),
                        "## Must-Not-Do Clauses",
                        (
                            "| Clause ID | Source Bucket | Forbidden Drift | Why It Is Forbidden | "
                            "Guard Stage | Evidence Path | Status |"
                        ),
                        (
                            "| --------- | ------------- | --------------- | ------------------- | "
                            "----------- | ------------- | ------ |"
                        ),
                        "## Completion Evidence Clauses",
                        (
                            "| Clause ID | Source Bucket | Required Evidence | "
                            "Where It Must Appear | Owner Stage | Status |"
                        ),
                        (
                            "| --------- | ------------- | ----------------- | "
                            "-------------------- | ----------- | ------ |"
                        ),
                        (
                            "| T1-E1 | current_request | requirements review | "
                            "management_review.md | requirements | active |"
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "management_review.md").write_text(
                "\n".join(
                    [
                        "# Management Review",
                        "",
                        "## Scope Review",
                        "Scope is concrete.",
                        "## Accumulated Context Resolution Review",
                        "Resolution sweep is recorded.",
                        "## Unknown Handling Review",
                        "No unknowns should remain active.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "requirements",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            expected_blocker = "user_request_contract.md:active_unknown_clause:must_do_clauses"
            self.assertIn(expected_blocker, result.stdout)

    def test_design_gate_rejects_fresh_template_bundle(self) -> None:
        """A fresh bundle should not pass design gate without filled reviews."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            report_dir = report_root / "fresh-bundle"
            subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "waterfall gate smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    "fresh-bundle",
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "design",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("WATERFALL_GATE_READY=no", result.stdout)
            self.assertIn("design_review.md:decision_not_approve", result.stdout)

    def test_plan_gate_rejects_empty_todo_surface(self) -> None:
        """Plan gate should fail when schedule.md does not contain concrete TODO rows."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "empty-plan"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "schedule.md").write_text(
                "\n".join(
                    [
                        "# Schedule",
                        "",
                        "## Stage Plan",
                        "| Stage | Owner Agent | Review Agent | Inputs | Exit Criteria | Status |",
                        "| ----- | ----------- | ------------ | ------ | ------------- | ------ |",
                        "| requirements | manager | manager_reviewer | contract | fixed | done |",
                        "## Clause Coverage",
                        "| Clause ID | Covered By Stage | Review Gate | Status |",
                        "| --------- | ---------------- | ----------- | ------ |",
                        "| T1-C1 | requirements | requirements | done |",
                        "## Planned Work Units",
                        "| Unit ID | Clause IDs | Owner | Completion Evidence | Next Gate | Status |",
                        "| ------- | ---------- | ----- | ------------------- | --------- | ------ |",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "schedule_review.md").write_text(
                "\n".join(
                    [
                        "# Schedule Review",
                        "",
                        "## Findings",
                        "No blockers.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "plan",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("schedule.md:planned_work_units_empty", result.stdout)

    def test_design_gate_accepts_filled_approved_artifacts(self) -> None:
        """A filled design bundle should pass when both design reviews approve."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "filled"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "design_brief.md").write_text(
                "\n".join(
                    [
                        "# Detailed Design Brief",
                        "",
                        "## Goals",
                        "Implement the approved small change.",
                        "## Existing Code And Docs To Reuse",
                        "Mirror `tools/agent_tools/task_close.py`.",
                        "## Upstream Requirement Packet",
                        (
                            "Read `user_request_contract.md`, `schedule.md`, `intent_brief.md`, "
                            "and `agents/workflows/implementation-waterfall-workflow.md`."
                        ),
                        "## Implementation Source Packet",
                        (
                            "Read `user_request_contract.md`, `design_review.md`, "
                            "`document_flow_review.md`, `test_plan.md`, and "
                            "`tools/agent_tools/task_close.py`."
                        ),
                        "## Canonical Tree-Head Plan",
                        (
                            "Keep `tools/agent_tools/waterfall_gate_check.py` as the only "
                            "canonical implementation path and do not leave backup or copy files."
                        ),
                        "## File-By-File Design",
                        "Update `tools/agent_tools/waterfall_gate_check.py` only.",
                        "## Design-To-Implementation Trace",
                        (
                            "Slice A maps T1-C1 to "
                            "`tools/agent_tools/waterfall_gate_check.py` and test plan item T1."
                        ),
                        "## Identifier And Naming Plan",
                        "Use `waterfall_gate_check.py` after the existing task tool names.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "design_review.md").write_text(
                "\n".join(
                    [
                        "# Detailed Design Review",
                        "",
                        "## Findings",
                        "No blockers.",
                        "## Upstream Requirement Packet Review",
                        "The design cites the governing requirement and workflow documents.",
                        "## Implementation Source Packet Review",
                        "The packet names every required read-before-edit artifact.",
                        "## Canonical Tree-Head Review",
                        "The design leaves only canonical tracked paths in the tree.",
                        "## Design-To-Implementation Trace Review",
                        "Each planned edit maps to the request clause and test plan.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "document_flow_review.md").write_text(
                "\n".join(
                    [
                        "# Document Flow Review",
                        "",
                        "## Findings",
                        "No blockers.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "design",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("WATERFALL_GATE_READY=yes", result.stdout)
            self.assertIn("NEXT_ACTION=proceed_to_next_waterfall_gate", result.stdout)

    def test_final_gate_rejects_empty_work_log(self) -> None:
        """Final gate should fail when work_log.md has no concrete entries."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "final-empty-work-log"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "final_review.md").write_text(
                "\n".join(
                    [
                        "# Final Review",
                        "",
                        "## Ship Blockers",
                        "| Finding | Severity | Status |",
                        "| ------- | -------- | ------ |",
                        "| none | info | resolved |",
                        "## Design Trace Acceptance",
                        "Trace is complete.",
                        "## Planned Work Completion Review",
                        "All planned work units are complete.",
                        "## Spec-To-Product Coverage Review",
                        "Every clause has a product surface.",
                        "## Review Finding Incorporation Review",
                        "All fix-now findings were integrated.",
                        "## Post-Fix Full Review Rerun Review",
                        "No post-review fixes occurred after the last full review pass.",
                        "## Canonical Tree-Head Acceptance",
                        "Only canonical tracked paths remain in the tree head.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "work_log.md").write_text(
                "\n".join(
                    [
                        "# Work Log",
                        "",
                        "## Purpose",
                        "- Required run log.",
                        "",
                        "## Entries",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "final",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("work_log.md:section_empty_or_missing:entries", result.stdout)

    def test_final_gate_rejects_too_thin_work_log(self) -> None:
        """Final gate should fail when the log is present but too thin to be useful."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "final-thin-work-log"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "final_review.md").write_text(
                "\n".join(
                    [
                        "# Final Review",
                        "",
                        "## Ship Blockers",
                        "| Finding | Severity | Status |",
                        "| ------- | -------- | ------ |",
                        "| none | info | resolved |",
                        "## Design Trace Acceptance",
                        "Trace is complete.",
                        "## Planned Work Completion Review",
                        "All planned work units are complete.",
                        "## Spec-To-Product Coverage Review",
                        "Every clause has a product surface.",
                        "## Review Finding Incorporation Review",
                        "All fix-now findings were integrated.",
                        "## Post-Fix Full Review Rerun Review",
                        "No post-review fixes occurred after the last full review pass.",
                        "## Canonical Tree-Head Acceptance",
                        "Only canonical tracked paths remain in the tree head.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "work_log.md").write_text(
                "\n".join(
                    [
                        "# Work Log",
                        "",
                        "## Purpose",
                        "- Required run log.",
                        "",
                        "## Entries",
                        (
                            "- `2026-04-12 14:10 JST | review | final pass recorded | "
                            "status: done | request_clause_ids: T1-C1 | next: closeout`"
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "final",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("work_log.md:entries_too_few", result.stdout)

    def test_final_gate_rejects_missing_post_fix_full_review_section(self) -> None:
        """Final gate should fail when the post-fix full review evidence is missing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "final-missing-post-fix-review"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "final_review.md").write_text(
                "\n".join(
                    [
                        "# Final Review",
                        "",
                        "## Ship Blockers",
                        "| Finding | Severity | Status |",
                        "| ------- | -------- | ------ |",
                        "| none | info | resolved |",
                        "## Design Trace Acceptance",
                        "Trace is complete.",
                        "## Planned Work Completion Review",
                        "All planned work units are complete.",
                        "## Spec-To-Product Coverage Review",
                        "Every clause has a product surface.",
                        "## Review Finding Incorporation Review",
                        "All fix-now findings were integrated.",
                        "## Canonical Tree-Head Acceptance",
                        "Only canonical tracked paths remain in the tree head.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "work_log.md").write_text(
                "\n".join(
                    [
                        "# Work Log",
                        "",
                        "## Purpose",
                        "- Required run log.",
                        "",
                        "## Entries",
                        (
                            "- `2026-04-12 13:50 JST | kickoff | fixed the closeout clause set | "
                            "status: done | request_clause_ids: T1-C1 | next: rerun final review`"
                        ),
                        (
                            "- `2026-04-12 14:00 JST | edit | refreshed the final review artifact | "
                            "status: done | request_clause_ids: T1-C1 | next: check closeout sections`"
                        ),
                        (
                            "- `2026-04-12 14:10 JST | review | final pass recorded | "
                            "status: done | request_clause_ids: T1-C1 | next: closeout`"
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "final",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "final_review.md:section_empty_or_missing:post-fix_full_review_rerun_review",
                result.stdout,
            )

    def test_final_gate_rejects_missing_canonical_tree_head_section(self) -> None:
        """Final gate should fail when canonical tree-head acceptance is missing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "final-missing-canonical-tree-head"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "final_review.md").write_text(
                "\n".join(
                    [
                        "# Final Review",
                        "",
                        "## Ship Blockers",
                        "| Finding | Severity | Status |",
                        "| ------- | -------- | ------ |",
                        "| none | info | resolved |",
                        "## Design Trace Acceptance",
                        "Trace is complete.",
                        "## Planned Work Completion Review",
                        "All planned work units are complete.",
                        "## Spec-To-Product Coverage Review",
                        "Every clause has a product surface.",
                        "## Review Finding Incorporation Review",
                        "All fix-now findings were integrated.",
                        "## Post-Fix Full Review Rerun Review",
                        "No post-review fixes occurred after the last full review pass.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "work_log.md").write_text(
                "\n".join(
                    [
                        "# Work Log",
                        "",
                        "## Purpose",
                        "- Required run log.",
                        "",
                        "## Entries",
                        (
                            "- `2026-04-16 11:20 JST | kickoff | fixed the canonical tree acceptance scope | "
                            "status: done | request_clause_ids: T1-C1 | next: rerun final review`"
                        ),
                        (
                            "- `2026-04-16 11:35 JST | edit | updated final review content | "
                            "status: done | request_clause_ids: T1-C1 | next: capture final review decision`"
                        ),
                        (
                            "- `2026-04-16 11:50 JST | review | final pass recorded | "
                            "status: done | request_clause_ids: T1-C1 | next: closeout`"
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "final",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "final_review.md:section_empty_or_missing:canonical_tree-head_acceptance",
                result.stdout,
            )

    def test_design_gate_rejects_missing_source_packet(self) -> None:
        """A design review should not pass when the design lacks source packet trace."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-source-packet"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "design_brief.md").write_text(
                "\n".join(
                    [
                        "# Detailed Design Brief",
                        "",
                        "## Goals",
                        "Implement the approved small change.",
                        "## Existing Code And Docs To Reuse",
                        "Mirror `tools/agent_tools/task_close.py`.",
                        "## Identifier And Naming Plan",
                        "Use local precedent.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "design_review.md").write_text(
                "\n".join(
                    [
                        "# Detailed Design Review",
                        "",
                        "## Findings",
                        "No blockers.",
                        "## Upstream Requirement Packet Review",
                        "The design cites the governing requirement and workflow documents.",
                        "## Implementation Source Packet Review",
                        "The packet names every required read-before-edit artifact.",
                        "## Design-To-Implementation Trace Review",
                        "Each planned edit maps to the request clause and test plan.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "document_flow_review.md").write_text(
                "\n".join(
                    [
                        "# Document Flow Review",
                        "",
                        "## Findings",
                        "No blockers.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "design",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            expected_blocker = (
                "design_brief.md:section_empty_or_missing:implementation_source_packet"
            )
            self.assertIn(expected_blocker, result.stdout)

    def test_design_gate_rejects_missing_upstream_requirement_packet(self) -> None:
        """Design gate should fail when the design omits upstream document references."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-upstream-packet"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "design_brief.md").write_text(
                "\n".join(
                    [
                        "# Detailed Design Brief",
                        "",
                        "## Goals",
                        "Implement the approved small change.",
                        "## Existing Code And Docs To Reuse",
                        "Mirror `tools/agent_tools/task_close.py`.",
                        "## Implementation Source Packet",
                        "Read `user_request_contract.md` and `design_review.md`.",
                        "## Design-To-Implementation Trace",
                        "Slice A maps T1-C1 to `tools/agent_tools/task_close.py`.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "design_review.md").write_text(
                "\n".join(
                    [
                        "# Detailed Design Review",
                        "",
                        "## Findings",
                        "No blockers.",
                        "## Upstream Requirement Packet Review",
                        "The design should cite the governing requirement docs.",
                        "## Implementation Source Packet Review",
                        "The packet names every required read-before-edit artifact.",
                        "## Design-To-Implementation Trace Review",
                        "Each planned edit maps to the request clause and test plan.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "document_flow_review.md").write_text(
                "\n".join(
                    [
                        "# Document Flow Review",
                        "",
                        "## Findings",
                        "No blockers.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "design",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design_brief.md:section_empty_or_missing:upstream_requirement_packet",
                result.stdout,
            )


if __name__ == "__main__":
    unittest.main()
