#!/usr/bin/env python3
# @dependency-start
# upstream design ../../agents/workflows/agent-learning-workflow.md defines feedback capture workflow
# upstream design ../../agents/templates/agent_evaluation.md defines evaluation artifact shape
# upstream implementation ./report_artifact_checks.py validates schedule and work log completeness
# downstream implementation ../../tests/agent_tools/test_evaluate_agent_run.py verifies scoring behavior
# @dependency-end
"""Evaluate one run bundle and write actionable agent feedback."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from agent_team import resolve_report_root
from report_artifact_checks import (
    check_schedule_artifact,
    check_work_log_artifact,
    section_has_content,
)


DEFAULT_MIN_SCORE = 85
REQUIRED_ARTIFACTS = (
    "user_request_contract.md",
    "schedule.md",
    "work_log.md",
    "change_review.md",
    "final_review.md",
    "verification.txt",
    "closeout_gate.md",
    "retrospective.md",
)


@dataclass(frozen=True)
class CriterionResult:
    """One rubric criterion result."""

    name: str
    score: int
    max_score: int
    status: str
    feedback: str


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Grade a run bundle and produce agent feedback actions."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-id", help="Run id under reports/agents/.")
    group.add_argument("--report-dir", help="Explicit run directory to inspect.")
    parser.add_argument(
        "--report-root",
        help="Optional report root. Defaults to ./reports/agents under the workspace.",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used with --run-id and relative report roots.",
    )
    parser.add_argument(
        "--output",
        default="agent_evaluation.md",
        help="Evaluation artifact path relative to report dir, or an absolute path.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the evaluation artifact. Without this, only print status lines.",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=DEFAULT_MIN_SCORE,
        help=f"Minimum passing score. Defaults to {DEFAULT_MIN_SCORE}.",
    )
    return parser


def parse_kv_lines(path: Path) -> dict[str, str]:
    """Parse a simple key=value file."""
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def parse_markdown_status(path: Path) -> dict[str, str]:
    """Parse '- key: value' status lines from a markdown artifact."""
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    pattern = re.compile(r"^- ([a-zA-Z0-9_]+): (.+)$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            data[match.group(1)] = match.group(2).strip()
    return data


def markdown_decision(path: Path) -> str:
    """Return the first non-empty line under a Decision section."""
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    in_decision = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_decision = stripped == "## Decision"
            continue
        if in_decision and stripped and not stripped.startswith("<!--"):
            return stripped.lower()
    return ""


def artifact_text(report_dir: Path, name: str) -> str:
    """Return artifact text or an empty string."""
    path = report_dir / name
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def criterion(
    name: str,
    max_score: int,
    passed: bool,
    feedback: str,
    partial_score: int | None = None,
) -> CriterionResult:
    """Build one criterion result."""
    if passed:
        return CriterionResult(name, max_score, max_score, "pass", "No action required.")
    score = partial_score if partial_score is not None else 0
    return CriterionResult(name, score, max_score, "revise", feedback)


def evaluate(report_dir: Path) -> tuple[list[CriterionResult], list[str]]:
    """Evaluate one report directory."""
    missing = [name for name in REQUIRED_ARTIFACTS if not (report_dir / name).is_file()]
    request_contract = parse_markdown_status(report_dir / "user_request_contract.md")
    verification = parse_kv_lines(report_dir / "verification.txt")
    closeout = parse_markdown_status(report_dir / "closeout_gate.md")
    schedule_text = artifact_text(report_dir, "schedule.md")
    work_log_text = artifact_text(report_dir, "work_log.md")
    retrospective_text = artifact_text(report_dir, "retrospective.md")
    final_decision = markdown_decision(report_dir / "final_review.md")
    change_review_text = artifact_text(report_dir, "change_review.md").lower()

    schedule_blockers = check_schedule_artifact(schedule_text)
    work_log_blockers = check_work_log_artifact(work_log_text)

    criteria = [
        criterion(
            "artifact_completeness",
            10,
            not missing,
            f"Create missing run artifacts: {', '.join(missing)}.",
        ),
        criterion(
            "request_traceability",
            15,
            request_contract.get("all_clauses_resolved") == "yes"
            and request_contract.get("forbidden_drift_detected") == "no"
            and not request_contract.get("unresolved_clause_ids", "").strip(),
            "Resolve all request clauses, clear unresolved ids, and confirm forbidden drift is absent.",
        ),
        criterion(
            "planned_work_and_chronology",
            15,
            not schedule_blockers and not work_log_blockers,
            "Fill schedule stage/coverage/work-unit tables and add meaningful work-log entries.",
        ),
        criterion(
            "review_feedback_loop",
            15,
            "approve" in final_decision
            and "required_change" not in change_review_text
            and "revise" not in change_review_text,
            "Resolve or escalate review feedback and record an approving final review decision.",
        ),
        criterion(
            "validation_and_closeout_evidence",
            20,
            verification.get("status") == "pass"
            and closeout.get("validation_complete") == "yes"
            and closeout.get("commit_created") == "yes"
            and closeout.get("push_completed") == "yes",
            "Record passing verification, validation_complete=yes, commit evidence, and push evidence.",
        ),
        criterion(
            "dependency_and_canonical_evidence",
            10,
            closeout.get("dependency_headers_complete") == "yes"
            and closeout.get("canonical_tree_head_complete") == "yes",
            "Record dependency manifest evidence and canonical tree-head evidence in closeout_gate.md.",
        ),
        criterion(
            "learning_and_feedback_capture",
            15,
            section_has_content(retrospective_text, "## What Worked")
            and section_has_content(retrospective_text, "## What Hurt")
            and section_has_content(retrospective_text, "## Follow-ups"),
            "Fill retrospective sections with concrete feedback, including 'None' when no follow-up remains.",
        ),
    ]
    blockers = [item.feedback for item in criteria if item.status != "pass"]
    return criteria, blockers


def render_markdown(
    report_dir: Path,
    criteria: list[CriterionResult],
    blockers: list[str],
    min_score: int,
) -> str:
    """Render the evaluation artifact."""
    score = sum(item.score for item in criteria)
    max_score = sum(item.max_score for item in criteria)
    status = "pass" if score >= min_score and not blockers else "revise"
    feedback_resolved = "yes" if status == "pass" else "no"
    learning_complete = (
        "yes"
        if any(item.name == "learning_and_feedback_capture" and item.status == "pass" for item in criteria)
        else "no"
    )
    lines = [
        "# Agent Evaluation",
        "",
        "<!--",
        "@dependency-start",
        "upstream design ../../../../vendor/agent-canon/agents/workflows/agent-learning-workflow.md agent feedback workflow",
        "upstream implementation ../../../../vendor/agent-canon/tools/agent_tools/evaluate_agent_run.py generates this artifact",
        "@dependency-end",
        "-->",
        "",
        f"- evaluation_status: {status}",
        f"- score: {score}",
        f"- max_score: {max_score}",
        f"- threshold: {min_score}",
        f"- feedback_actions_resolved: {feedback_resolved}",
        f"- learning_capture_complete: {learning_complete}",
        "",
        "## Scope",
        "",
        f"- report_dir: {report_dir}",
        "",
        "## Rubric",
        "",
        "| Criterion | Score | Max | Status | Feedback |",
        "| --------- | ----- | --- | ------ | -------- |",
    ]
    for item in criteria:
        lines.append(
            f"| {item.name} | {item.score} | {item.max_score} | {item.status} | {item.feedback} |"
        )
    lines.extend(
        [
            "",
            "## Feedback Actions",
            "",
            "| Action ID | Severity | Action | Status |",
            "| --------- | -------- | ------ | ------ |",
        ]
    )
    if blockers:
        for index, blocker in enumerate(blockers, start=1):
            lines.append(f"| F{index} | fix-now | {blocker} | open |")
    else:
        lines.append("| F0 | none | No open feedback actions. | resolved |")
    lines.extend(
        [
            "",
            "## Learning Capture",
            "",
            "If this evaluation exposed a durable agent-side lesson, record it with "
            "`tools/agent_tools/log_agent_learning.py` and cite the evidence. Do not copy raw chat.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    """Run the agent evaluation."""
    args = build_parser().parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    if args.report_dir:
        report_dir = Path(args.report_dir).resolve()
    else:
        report_dir = resolve_report_root(args.report_root, workspace_root) / str(args.run_id)
        report_dir = report_dir.resolve()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = report_dir / output_path

    criteria, blockers = evaluate(report_dir)
    score = sum(item.score for item in criteria)
    max_score = sum(item.max_score for item in criteria)
    status = "pass" if score >= args.min_score and not blockers else "revise"
    report = render_markdown(report_dir, criteria, blockers, args.min_score)
    if args.write:
        output_path.write_text(report, encoding="utf-8")

    print(f"AGENT_EVALUATION_REPORT={output_path}")
    print(f"AGENT_EVALUATION_STATUS={status}")
    print(f"AGENT_EVALUATION_SCORE={score}")
    print(f"AGENT_EVALUATION_MAX_SCORE={max_score}")
    print(f"AGENT_EVALUATION_THRESHOLD={args.min_score}")
    print(f"AGENT_EVALUATION_FEEDBACK_ACTIONS_OPEN={len(blockers)}")
    if blockers:
        print("AGENT_EVALUATION_BLOCKERS=" + "|".join(blockers))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
