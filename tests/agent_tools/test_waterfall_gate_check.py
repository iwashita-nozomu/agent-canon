# @dependency-start
# contract test
# responsibility Tests test waterfall gate check behavior.
# upstream design ../../tools/README.md validated automation surface
# @dependency-end

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


def write_markdown(path: Path, lines: list[str]) -> None:
    """Write a compact Markdown fixture."""
    path.write_text("\n".join([*lines, ""]), encoding="utf-8")


def run_gate(report_dir: Path, gate: str) -> subprocess.CompletedProcess[str]:
    """Run one waterfall gate check."""
    return subprocess.run(
        [
            sys.executable,
            str(GATE_CHECK_SCRIPT),
            "--report-dir",
            str(report_dir),
            "--gate",
            gate,
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_document_flow_review(report_dir: Path) -> None:
    """Write an approving document flow review fixture."""
    write_markdown(
        report_dir / "document_flow_review.md",
        [
            "# Document Flow Review",
            "",
            "## Findings",
            "No blockers.",
            "## Decision",
            "approve",
        ],
    )


def approved_design_review_lines(
    *,
    include_abstract: bool = True,
    design_artifact_path: str = "design_brief.md",
    include_artifact_section: bool = True,
    include_revision: bool = True,
    include_source_packet: bool = True,
    include_reviewer_separation: bool = True,
) -> list[str]:
    """Return a design review fixture that satisfies the design gate."""
    lines = [
        "# Detailed Design Review",
        "",
        "## Findings",
        "No blockers.",
    ]
    if include_artifact_section:
        lines.extend(
            [
                "## Design Artifact Under Review",
                f"- Design artifact path: {design_artifact_path}",
            ]
        )
        if include_revision:
            lines.append(
                "- Design revision or section set: current sections through "
                "Design-To-Implementation Trace"
            )
        if include_source_packet:
            lines.append("- Source packet reviewed: design_brief.md Implementation Source Packet")
        if include_reviewer_separation:
            lines.append(
                "- Reviewer separation: design_reviewer is separate from designer"
            )
    lines.extend(
        [
            "## Upstream Requirement Packet Review",
            "The design cites the governing requirement and workflow documents.",
        ]
    )
    if include_abstract:
        lines.extend(
            [
                "## Abstract Design Frame Review",
                "The design starts from responsibility before file scope.",
            ]
        )
    lines.extend(
        [
            "## Implementation Source Packet Review",
            "The packet names every required read-before-edit artifact.",
            "## Canonical Tree-Head Review",
            "The design leaves only canonical tracked paths in the tree.",
            "## Design-To-Implementation Trace Review",
            "Each planned edit maps to the request clause and test plan.",
            "## Decision",
            "approve",
        ]
    )
    return lines


def design_brief_lines(
    *,
    include_abstract: bool = True,
    include_upstream: bool = True,
    include_implementation: bool = True,
    include_canonical: bool = True,
    include_trace: bool = True,
) -> list[str]:
    """Return a detailed design fixture with optional required sections."""
    lines = [
        "# Detailed Design Brief",
        "",
        "## Goals",
        "Implement the approved bounded change.",
        "## Existing Code And Docs To Reuse",
        "Mirror `tools/agent_tools/task_close.py`.",
    ]
    if include_abstract:
        lines.extend(
            [
                "## Abstract Design Frame",
                (
                    "Responsibility model: gate checks enforce design readiness "
                    "before implementation path selection."
                ),
                "Concept or layer model: requirements flow into design, review, implementation, and validation layers.",
                "Non-goals: the design does not let workers invent file scope from nearby helpers.",
                "Future extension layers: generated prompts and closeout gates can add stricter checks.",
                "Evaluation axes: readiness is judged by traceability, reviewability, and validation coverage.",
                "Canonical-surface relationships: the workflow, templates, tools, and tests stay aligned.",
            ]
        )
    if include_upstream:
        lines.extend(
            [
                "## Upstream Requirement Packet",
                (
                    "Read `user_request_contract.md`, `schedule.md`, `intent_brief.md`, "
                    "and `agents/workflows/implementation-waterfall-workflow.md`."
                ),
            ]
        )
    if include_implementation:
        lines.extend(
            [
                "## Implementation Source Packet",
                (
                    "Read `user_request_contract.md`, `design_review.md`, "
                    "`document_flow_review.md`, `test_plan.md`, and "
                    "`tools/agent_tools/task_close.py`."
                ),
            ]
        )
    if include_canonical:
        lines.extend(
            [
                "## Canonical Tree-Head Plan",
                (
                    "Keep `tools/agent_tools/waterfall_gate_check.py` as the only "
                    "canonical implementation path and do not leave backup files."
                ),
            ]
        )
    lines.extend(["## File-By-File Design", "Update the gate checker only."])
    if include_trace:
        lines.extend(
            [
                "## Design-To-Implementation Trace",
                "Slice A maps T1-C1 to the gate checker and test plan item T1.",
            ]
        )
    lines.extend(
        [
            "## Identifier And Naming Plan",
            "Use `waterfall_gate_check.py` after the existing task tool names.",
        ]
    )
    return lines


def write_approved_design_bundle(
    report_dir: Path,
    design_lines: list[str],
) -> None:
    """Write design artifacts with an approving review and document-flow review."""
    write_design_bundle_with_review(
        report_dir,
        design_lines,
        approved_design_review_lines(),
    )


def write_design_bundle_with_review(
    report_dir: Path,
    design_lines: list[str],
    design_review_lines: list[str],
) -> None:
    """Write design artifacts with caller-selected design-review lines."""
    write_markdown(report_dir / "design_brief.md", design_lines)
    write_markdown(report_dir / "design_review.md", design_review_lines)
    write_document_flow_review(report_dir)


def write_unknown_requirement_bundle(report_dir: Path) -> None:
    """Write a requirement bundle with an invalid active unknown clause."""
    write_markdown(
        report_dir / "user_request_contract.md",
        [
            "# User Request Contract",
            "",
            "## Requirements Resolution Sweep",
            "Checked notes, documents, and local code precedent.",
            "## Resolved From Accumulated Context",
            "| Clause ID | Resolved From | Evidence Path | Resolution | Remaining Risk |",
            "| --------- | ------------- | ------------- | ---------- | -------------- |",
            "| T1-C0 | repo_or_code_precedent | documents/ | Existing workflow applies. | none |",
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
            "| Clause ID | Source Bucket | Forbidden Drift | Why It Is Forbidden | Guard Stage | Evidence Path | Status |",
            "| --------- | ------------- | --------------- | ------------------- | ----------- | ------------- | ------ |",
            "## Completion Evidence Clauses",
            "| Clause ID | Source Bucket | Required Evidence | Where It Must Appear | Owner Stage | Status |",
            "| --------- | ------------- | ----------------- | -------------------- | ----------- | ------ |",
            "| T1-E1 | current_request | requirements review | management_review.md | requirements | active |",
        ],
    )
    write_markdown(
        report_dir / "management_review.md",
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
        ],
    )


class WaterfallGateCheckTest(unittest.TestCase):
    """Verify that intermediate waterfall gates fail closed."""

    def test_requirements_gate_rejects_active_unknown_clause(self) -> None:
        """Requirements should defer unknowns instead of leaving them active."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "unknown-requirement"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_unknown_requirement_bundle(report_dir)
            result = run_gate(report_dir, "requirements")

            self.assertNotEqual(result.returncode, 0)
            expected_blocker = "user_request_contract.md:active_unknown_clause:must_do_clauses"
            self.assertIn(expected_blocker, result.stdout)

    def test_requirements_gate_allows_dependency_header_comment(self) -> None:
        """Dependency headers should not make a filled artifact look like a template."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "dependency-header"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(
                report_dir / "user_request_contract.md",
                [
                    "# User Request Contract",
                    "<!--",
                    "@dependency-start",
                    "responsibility Documents run requirements.",
                    "@dependency-end",
                    "-->",
                    "",
                    "## Requirements Resolution Sweep",
                    "Checked repo docs, source packet, and local tests.",
                    "## Resolved From Accumulated Context",
                    "| Clause ID | Resolved From | Evidence Path | Resolution | Remaining Risk |",
                    "| --------- | ------------- | ------------- | ---------- | -------------- |",
                    "| T1-C0 | repo_or_code_precedent | documents/ | Existing workflow applies. | none |",
                    "## Must-Do Clauses",
                    (
                        "| Clause ID | Source Bucket | User Wording Or Evidence | "
                        "Operational Interpretation | Owner Stage | Evidence Path | Status |"
                    ),
                    (
                        "| --------- | ------------- | ------------------------- | "
                        "-------------------------- | ----------- | ------------- | ------ |"
                    ),
                    "| T1-C1 | current_request | fix gate | enforce requirements | requirements | user_request_contract.md | active |",
                    "## Must-Not-Do Clauses",
                    "| Clause ID | Source Bucket | Forbidden Drift | Why It Is Forbidden | Guard Stage | Evidence Path | Status |",
                    "| --------- | ------------- | --------------- | ------------------- | ----------- | ------------- | ------ |",
                    "| T1-N1 | repo_or_code_precedent | skip gate | unsafe | requirements | management_review.md | active |",
                    "## Completion Evidence Clauses",
                    "| Clause ID | Source Bucket | Required Evidence | Where It Must Appear | Owner Stage | Status |",
                    "| --------- | ------------- | ----------------- | -------------------- | ----------- | ------ |",
                    "| T1-E1 | current_request | requirements review | management_review.md | requirements | active |",
                ],
            )
            write_markdown(
                report_dir / "management_review.md",
                [
                    "# Management Review",
                    "",
                    "## Scope Review",
                    "Scope is concrete.",
                    "## Accumulated Context Resolution Review",
                    "Resolution sweep is recorded.",
                    "## Unknown Handling Review",
                    "No unknowns remain active.",
                    "## Decision",
                    "approve",
                ],
            )

            result = run_gate(report_dir, "requirements")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("WATERFALL_GATE_READY=yes", result.stdout)
            self.assertNotIn("template_or_placeholder_remaining", result.stdout)

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

            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("WATERFALL_GATE_READY=no", result.stdout)
            self.assertIn("design_review.md:decision_not_approve", result.stdout)

    def test_document_flow_gate_is_separate_from_design_gate(self) -> None:
        """Design approval should not unconditionally require document flow."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "design-only"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(report_dir / "design_brief.md", design_brief_lines())
            write_markdown(
                report_dir / "design_review.md",
                approved_design_review_lines(),
            )

            design_result = run_gate(report_dir, "design")
            document_flow_result = run_gate(report_dir, "document_flow")

            self.assertEqual(
                design_result.returncode,
                0,
                design_result.stdout + design_result.stderr,
            )
            self.assertIn("WATERFALL_GATE_READY=yes", design_result.stdout)
            self.assertNotEqual(document_flow_result.returncode, 0)
            self.assertIn("document_flow_review.md:missing", document_flow_result.stdout)

    def test_test_gate_rejects_dependency_header_only_plan(self) -> None:
        """Dependency headers alone should not satisfy the test-plan gate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "dependency-header-only-test"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(
                report_dir / "test_plan.md",
                [
                    "# Test Plan",
                    "<!--",
                    "@dependency-start",
                    "responsibility Documents test plan.",
                    "@dependency-end",
                    "-->",
                    "",
                    "## Static Path Survey",
                    "<!-- Record static paths. -->",
                    "## Nasty Cases",
                    "| Target | Case | Why It Is Nasty | Expected Outcome | Status |",
                    "| ------ | ---- | --------------- | ---------------- | ------ |",
                    "## Regression Cases To Keep",
                    "<!-- Record regressions. -->",
                    "## Implementation Notes",
                    "<!-- Record implementation notes. -->",
                ],
            )

            result = run_gate(report_dir, "test")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("test_plan.md:template_or_placeholder_remaining", result.stdout)

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
                        (
                            "| Unit ID | Clause IDs | Owner | Completion Evidence | "
                            "Next Gate | Status |"
                        ),
                        (
                            "| ------- | ---------- | ----- | ------------------- | "
                            "--------- | ------ |"
                        ),
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
            write_approved_design_bundle(report_dir, design_brief_lines())
            result = run_gate(report_dir, "design")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("WATERFALL_GATE_READY=yes", result.stdout)
            self.assertIn("NEXT_ACTION=proceed_to_next_waterfall_gate", result.stdout)

    def test_design_gate_rejects_missing_abstract_design_frame(self) -> None:
        """Design gate should fail when design selects files without abstraction."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-abstract-frame"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_approved_design_bundle(
                report_dir,
                design_brief_lines(include_abstract=False),
            )
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            expected_blocker = (
                "design_brief.md:section_empty_or_missing:abstract_design_frame"
            )
            self.assertIn(expected_blocker, result.stdout)

    def test_design_gate_rejects_missing_abstract_design_frame_review(self) -> None:
        """Design gate should fail when design review omits abstract-frame review."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-abstract-review"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_design_bundle_with_review(
                report_dir,
                design_brief_lines(),
                approved_design_review_lines(include_abstract=False),
            )
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            expected_blocker = (
                "design_review.md:section_empty_or_missing:abstract_design_frame_review"
            )
            self.assertIn(expected_blocker, result.stdout)

    def test_design_gate_rejects_missing_reviewed_artifact_section(self) -> None:
        """Design review must name the current design artifact it approved."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-artifact-section"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_design_bundle_with_review(
                report_dir,
                design_brief_lines(),
                approved_design_review_lines(include_artifact_section=False),
            )
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design_review.md:section_empty_or_missing:design_artifact_under_review",
                result.stdout,
            )
            self.assertIn(
                "design_review.md:design_artifact_under_review_missing:design_artifact_path",
                result.stdout,
            )

    def test_design_gate_rejects_stale_reviewed_artifact_path(self) -> None:
        """Design review approval cannot target a stale design artifact path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "stale-artifact-path"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_design_bundle_with_review(
                report_dir,
                design_brief_lines(),
                approved_design_review_lines(
                    design_artifact_path="reports/agents/old/design_brief.md"
                ),
            )
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design_review.md:design_artifact_path_not_current",
                result.stdout,
            )

    def test_design_gate_rejects_missing_review_source_packet(self) -> None:
        """Design review must record source packet and separation evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-review-evidence"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_design_bundle_with_review(
                report_dir,
                design_brief_lines(),
                approved_design_review_lines(
                    include_source_packet=False,
                    include_reviewer_separation=False,
                ),
            )
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design_review.md:design_artifact_under_review_missing:source_packet_reviewed",
                result.stdout,
            )
            self.assertIn(
                "design_review.md:design_artifact_under_review_missing:reviewer_separation",
                result.stdout,
            )

    def test_implementation_gate_requires_current_design_approval(self) -> None:
        """Implementation cannot proceed from an unapproved existing design."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "implementation-design-review"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(report_dir / "design_brief.md", design_brief_lines())
            write_markdown(
                report_dir / "change_review.md",
                [
                    "# Change Review",
                    "",
                    "## Design-Base Implementation Review",
                    "Implementation cites the design.",
                    "## Canonical Tree-Head Review",
                    "Tree head is canonical.",
                    "## Decision",
                    "approve",
                ],
            )

            missing_review = run_gate(report_dir, "implementation")
            write_markdown(
                report_dir / "design_review.md",
                approved_design_review_lines(
                    design_artifact_path="reports/agents/old/design_brief.md"
                ),
            )
            stale_review = run_gate(report_dir, "implementation")
            write_markdown(
                report_dir / "design_review.md",
                approved_design_review_lines(),
            )
            approved_review = run_gate(report_dir, "implementation")

            self.assertNotEqual(missing_review.returncode, 0)
            self.assertIn("design_review.md:missing", missing_review.stdout)
            self.assertIn(
                "NEXT_ACTION=return_to_design_owner_until_gate_approves",
                missing_review.stdout,
            )
            self.assertNotEqual(stale_review.returncode, 0)
            self.assertIn(
                "design_review.md:design_artifact_path_not_current",
                stale_review.stdout,
            )
            self.assertIn(
                "NEXT_ACTION=return_to_design_owner_until_gate_approves",
                stale_review.stdout,
            )
            self.assertEqual(
                approved_review.returncode,
                0,
                approved_review.stdout + approved_review.stderr,
            )

    def test_design_gate_rejects_under_specified_abstract_design_frame(self) -> None:
        """Design gate should require the six abstract design frame dimensions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "thin-abstract-frame"
            report_dir.mkdir(parents=True, exist_ok=True)
            thin_design = design_brief_lines()
            thin_design = [
                line
                for line in thin_design
                if not line.startswith(
                    (
                        "Concept or layer model:",
                        "Non-goals:",
                        "Future extension layers:",
                        "Evaluation axes:",
                        "Canonical-surface relationships:",
                    )
                )
            ]
            write_approved_design_bundle(report_dir, thin_design)
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design_brief.md:abstract_design_frame_missing:concept_or_layer_model",
                result.stdout,
            )
            self.assertIn(
                "design_brief.md:abstract_design_frame_missing:canonical_surface_relationships",
                result.stdout,
            )

    def test_design_gate_rejects_term_inventory_abstract_design_frame(self) -> None:
        """Design gate should reject a one-line inventory of ADF terms."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "inventory-abstract-frame"
            report_dir.mkdir(parents=True, exist_ok=True)
            inventory_design = design_brief_lines()
            start = inventory_design.index("## Abstract Design Frame")
            end = inventory_design.index("## Upstream Requirement Packet")
            inventory_design = (
                inventory_design[: start + 1]
                + [
                    (
                        "Responsibility model, concept graph, non-goals, future extension layers, "
                        "evaluation axes, and relationship to existing canonical surfaces."
                    )
                ]
                + inventory_design[end:]
            )
            write_approved_design_bundle(report_dir, inventory_design)
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design_brief.md:abstract_design_frame_missing:responsibility_model",
                result.stdout,
            )
            self.assertIn(
                "design_brief.md:abstract_design_frame_missing:evaluation_axes",
                result.stdout,
            )

    def test_design_gate_rejects_placeholder_abstract_design_frame_values(self) -> None:
        """Design gate should reject ADF labels that still have placeholder values."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "placeholder-abstract-frame"
            report_dir.mkdir(parents=True, exist_ok=True)
            placeholder_design = design_brief_lines()
            placeholder_design = [
                "Responsibility model: todo" if line.startswith("Responsibility model:") else line
                for line in placeholder_design
            ]
            write_approved_design_bundle(report_dir, placeholder_design)
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design_brief.md:abstract_design_frame_missing:responsibility_model",
                result.stdout,
            )

    def test_implementation_checkpoint_contract_requires_abstract_trace(self) -> None:
        """Checkpoint review surfaces should reject file-local-only justification."""
        template_text = (PROJECT_ROOT / "agents" / "templates" / "change_review.md").read_text(
            encoding="utf-8"
        )
        workflow_text = (
            PROJECT_ROOT / "agents" / "workflows" / "implementation-waterfall-workflow.md"
        ).read_text(encoding="utf-8")

        for text in (template_text, workflow_text):
            self.assertIn("Abstract Design Frame", text)
            self.assertIn("Implementation Source Packet", text)
            self.assertIn("nearest file", text)
            self.assertIn("helper", text)
            self.assertIn("current finding", text)

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
                            "- `2026-04-12 14:10 JST | review | final pass recorded | "
                            "request_clause_ids: T1-C1 | next: closeout`"
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
                            "- `2026-04-16 11:50 JST | review | final pass recorded | "
                            "request_clause_ids: T1-C1 | next: closeout`"
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
            write_approved_design_bundle(
                report_dir,
                design_brief_lines(include_implementation=False),
            )
            result = run_gate(report_dir, "design")

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
            write_approved_design_bundle(
                report_dir,
                design_brief_lines(include_upstream=False),
            )
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design_brief.md:section_empty_or_missing:upstream_requirement_packet",
                result.stdout,
            )


if __name__ == "__main__":
    unittest.main()
