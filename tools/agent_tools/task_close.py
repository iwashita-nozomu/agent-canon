#!/usr/bin/env python3
# @dependency-start
# responsibility Provides task close agent workflow automation.
# upstream implementation ./agent_team.py resolves report root defaults
# upstream implementation ./report_artifact_checks.py validates schedule and work log artifacts
# upstream design ../../agents/templates/closeout_gate.md defines closeout status contract
# upstream design ../../agents/templates/agent_evaluation.md defines evaluation contract
# downstream implementation ../../tests/agent_tools/test_task_start_and_close.py tests closeout
# @dependency-end
"""Evaluate whether one run bundle is ready for a user-facing completion report."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path

from agent_team import resolve_report_root
from report_artifact_checks import check_schedule_artifact, check_work_log_artifact


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Check verification.txt and closeout_gate.md and fail unless the run is ready "
            "for a user-facing completion report."
        )
    )
    parser.add_argument("--run-id", help="Run id under reports/agents/.")
    parser.add_argument("--report-dir", help="Explicit run directory to inspect.")
    parser.add_argument(
        "--report-root",
        help=(
            "Optional directory that contains per-run report folders. Defaults to "
            "./reports/agents relative to the current workspace."
        ),
    )
    return parser


def parse_kv_lines(path: Path) -> dict[str, str]:
    """Parse a simple key=value file."""
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def parse_markdown_status(path: Path) -> dict[str, str]:
    """Parse '- key: value' status lines from one markdown artifact."""
    data: dict[str, str] = {}
    pattern = re.compile(r"^- ([a-zA-Z0-9_]+): (.+)$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            data[match.group(1)] = match.group(2).strip()
    return data


def parse_markdown_status_section(path: Path, heading: str) -> dict[str, str]:
    """Parse '- key: value' status lines under one level-2 markdown heading."""
    data: dict[str, str] = {}
    pattern = re.compile(r"^- ([a-zA-Z0-9_]+): (.+)$")
    in_section = False
    target = f"## {heading}"
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == target:
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        match = pattern.match(stripped)
        if match:
            key = match.group(1)
            if key in data:
                raise SystemExit(f"Duplicate status key in {heading}: {key}")
            data[key] = match.group(2).strip()
    return data


def join_blockers(blockers: list[str]) -> str:
    """Render blocker list for terminal output."""
    return ",".join(blockers) if blockers else ""


def resolve_run_artifact(report_dir: Path, value: str) -> Path | None:
    """Resolve one run-local artifact path, rejecting paths outside the run bundle."""
    if not value:
        return None
    raw_path = Path(value)
    candidate = raw_path.resolve() if raw_path.is_absolute() else (report_dir / raw_path).resolve()
    try:
        candidate.relative_to(report_dir)
    except ValueError:
        return None
    return candidate


def current_git_head(workspace: Path) -> str:
    """Return the current git commit for the workspace."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def current_diff_ref(workspace: Path) -> str:
    """Return a ref for the exact tracked diff state under review."""
    head = current_git_head(workspace)
    if not head:
        raise SystemExit(f"Unable to resolve git HEAD from workspace: {workspace}")
    unstaged = subprocess.run(
        ["git", "diff", "--binary"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    staged = subprocess.run(
        ["git", "diff", "--cached", "--binary"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    diff_bytes = unstaged.stdout + staged.stdout
    if not diff_bytes:
        return head
    diff_hash = hashlib.sha256(diff_bytes).hexdigest()
    return f"{head}-dirty-{diff_hash}"


def main() -> int:
    """Run the closeout check."""
    args = build_parser().parse_args()
    if bool(args.run_id) == bool(args.report_dir):
        raise SystemExit("Provide exactly one of --run-id or --report-dir.")

    if args.report_dir:
        report_dir = Path(args.report_dir).resolve()
    else:
        report_dir = (
            resolve_report_root(args.report_root, Path.cwd()) / str(args.run_id)
        ).resolve()
    workspace = Path.cwd().resolve()

    verification_path = report_dir / "verification.txt"
    closeout_path = report_dir / "closeout_gate.md"
    request_contract_path = report_dir / "user_request_contract.md"
    schedule_path = report_dir / "schedule.md"
    work_log_path = report_dir / "work_log.md"
    agent_evaluation_path = report_dir / "agent_evaluation.md"
    if not verification_path.is_file():
        raise SystemExit(f"verification.txt not found: {verification_path}")
    if not closeout_path.is_file():
        raise SystemExit(f"closeout_gate.md not found: {closeout_path}")
    if not request_contract_path.is_file():
        raise SystemExit(f"user_request_contract.md not found: {request_contract_path}")
    if not schedule_path.is_file():
        raise SystemExit(f"schedule.md not found: {schedule_path}")
    if not work_log_path.is_file():
        raise SystemExit(f"work_log.md not found: {work_log_path}")
    if not agent_evaluation_path.is_file():
        raise SystemExit(f"agent_evaluation.md not found: {agent_evaluation_path}")

    verification = parse_kv_lines(verification_path)
    closeout = parse_markdown_status_section(closeout_path, "Gate Status")
    mechanical_loop = parse_markdown_status_section(
        closeout_path, "Mechanical Completion Loop Evidence"
    )
    diff_check = parse_markdown_status_section(closeout_path, "Diff-Check Agent Evidence")
    diff_check_artifact_path = resolve_run_artifact(
        report_dir, diff_check.get("diff_check_artifact", "")
    )
    diff_check_artifact = (
        parse_markdown_status_section(diff_check_artifact_path, "Diff-Check Review")
        if diff_check_artifact_path and diff_check_artifact_path.is_file()
        else {}
    )
    active_diff_ref = current_diff_ref(workspace)
    agent_evaluation = parse_markdown_status(agent_evaluation_path)
    request_contract = parse_markdown_status(request_contract_path)
    schedule_blockers = check_schedule_artifact(schedule_path.read_text(encoding="utf-8"))
    work_log_blockers = check_work_log_artifact(work_log_path.read_text(encoding="utf-8"))

    checks = {
        "verification_status": verification.get("status") == "pass",
        "verification_unlock": verification.get("user_completion_report") == "unlocked",
        "closeout_verifier_status": closeout.get("verifier_status") == "pass",
        "closeout_auditor_status": closeout.get("auditor_status") == "resolved",
        "required_reviews_complete": closeout.get("required_reviews_complete") == "yes",
        "validation_complete": closeout.get("validation_complete") == "yes",
        "request_contract_complete": closeout.get("request_contract_complete") == "yes",
        "all_planned_chunks_complete": closeout.get("all_planned_chunks_complete") == "yes",
        "overall_delivery_complete": closeout.get("overall_delivery_complete") == "yes",
        "unfinished_tasks_absent": closeout.get("unfinished_tasks_absent") == "yes",
        "dependency_headers_complete": closeout.get("dependency_headers_complete") == "yes",
        "repo_wide_dependency_tools_complete": closeout.get("repo_wide_dependency_tools_complete")
        == "yes",
        "repo_wide_static_analysis_complete": closeout.get("repo_wide_static_analysis_complete")
        == "yes",
        "spec_product_coverage_complete": closeout.get("spec_product_coverage_complete")
        == "yes",
        "review_findings_integrated": closeout.get("review_findings_integrated") == "yes",
        "post_fix_full_review_complete": closeout.get("post_fix_full_review_complete") == "yes",
        "mechanical_completion_loop_complete": closeout.get(
            "mechanical_completion_loop_complete"
        )
        == "yes",
        "mechanical_loop_iterations": mechanical_loop.get("mechanical_loop_iterations", "")
        not in {"", "0", "none"},
        "mechanical_loop_open_items": mechanical_loop.get("mechanical_loop_open_items")
        == "none",
        "mechanical_loop_stop_reason": mechanical_loop.get("mechanical_loop_stop_reason", "")
        != "",
        "mechanical_loop_planned_work_status": mechanical_loop.get(
            "mechanical_loop_planned_work_status"
        )
        == "complete",
        "mechanical_loop_review_findings_status": mechanical_loop.get(
            "mechanical_loop_review_findings_status"
        )
        in {"none", "resolved"},
        "mechanical_loop_validation_status": mechanical_loop.get(
            "mechanical_loop_validation_status"
        )
        == "pass",
        "mechanical_loop_dependency_review_status": mechanical_loop.get(
            "mechanical_loop_dependency_review_status"
        )
        == "pass",
        "mechanical_loop_static_analysis_status": mechanical_loop.get(
            "mechanical_loop_static_analysis_status"
        )
        == "pass",
        "mechanical_loop_commit_push_status": mechanical_loop.get(
            "mechanical_loop_commit_push_status"
        )
        == "complete",
        "mechanical_loop_canon_sync_status": mechanical_loop.get(
            "mechanical_loop_canon_sync_status"
        )
        in {"complete", "not_applicable"},
        "mechanical_loop_follow_up_status": mechanical_loop.get(
            "mechanical_loop_follow_up_status"
        )
        in {"none", "resolved"},
        "diff_check_agent_complete": closeout.get("diff_check_agent_complete") == "yes",
        "diff_check_agent_role": diff_check.get("diff_check_agent_role", "")
        not in {"", "parent", "self", "codex"},
        "diff_check_agent_decision": diff_check.get("diff_check_agent_decision") == "approve",
        "diff_check_latest_diff_ref": diff_check.get("diff_check_latest_diff_ref")
        == active_diff_ref,
        "diff_check_artifact_path": diff_check_artifact_path is not None,
        "diff_check_artifact_exists": bool(
            diff_check_artifact_path and diff_check_artifact_path.is_file()
        ),
        "diff_check_artifact_role": diff_check_artifact.get("diff_check_agent_role")
        == diff_check.get("diff_check_agent_role"),
        "diff_check_artifact_decision": diff_check_artifact.get("diff_check_agent_decision")
        == "approve",
        "diff_check_artifact_latest_diff_ref": diff_check_artifact.get(
            "diff_check_latest_diff_ref"
        )
        == diff_check.get("diff_check_latest_diff_ref"),
        "diff_check_artifact_read_only": diff_check_artifact.get("diff_check_read_only")
        == "yes",
        "diff_check_artifact_independent": diff_check_artifact.get(
            "diff_check_independent_agent"
        )
        == "yes",
        "diff_check_artifact_findings_status": diff_check_artifact.get(
            "diff_check_findings_status"
        )
        in {"none", "resolved"},
        "canonical_tree_head_complete": closeout.get("canonical_tree_head_complete") == "yes",
        "agent_evaluation_complete": closeout.get("agent_evaluation_complete") == "yes",
        "agent_evaluation_status": agent_evaluation.get("evaluation_status") == "pass",
        "agent_feedback_resolved": agent_evaluation.get("feedback_actions_resolved") == "yes",
        "agent_learning_capture_complete": agent_evaluation.get("learning_capture_complete")
        == "yes",
        "request_contract_resolved": request_contract.get("all_clauses_resolved") == "yes",
        "no_forbidden_drift": request_contract.get("forbidden_drift_detected") == "no",
        "todo_artifact_complete": not schedule_blockers,
        "work_log_complete": not work_log_blockers,
        "commit_created": closeout.get("commit_created") == "yes",
        "push_completed": closeout.get("push_completed") == "yes",
        "closeout_unlock": closeout.get("user_completion_report") == "unlocked",
    }
    ready = all(checks.values())

    print(f"REPORT_DIR={report_dir}")
    print(f"VERIFICATION_STATUS={verification.get('status', '')}")
    print(f"VERIFICATION_UNLOCK={verification.get('user_completion_report', '')}")
    print(f"CLOSEOUT_VERIFIER_STATUS={closeout.get('verifier_status', '')}")
    print(f"CLOSEOUT_AUDITOR_STATUS={closeout.get('auditor_status', '')}")
    print(f"REQUIRED_REVIEWS_COMPLETE={closeout.get('required_reviews_complete', '')}")
    print(f"VALIDATION_COMPLETE={closeout.get('validation_complete', '')}")
    print(f"REQUEST_CONTRACT_COMPLETE={closeout.get('request_contract_complete', '')}")
    print(f"ALL_PLANNED_CHUNKS_COMPLETE={closeout.get('all_planned_chunks_complete', '')}")
    print(f"OVERALL_DELIVERY_COMPLETE={closeout.get('overall_delivery_complete', '')}")
    print(f"UNFINISHED_TASKS_ABSENT={closeout.get('unfinished_tasks_absent', '')}")
    print(f"DEPENDENCY_HEADERS_COMPLETE={closeout.get('dependency_headers_complete', '')}")
    print(
        "REPO_WIDE_DEPENDENCY_TOOLS_COMPLETE="
        f"{closeout.get('repo_wide_dependency_tools_complete', '')}"
    )
    print(
        "REPO_WIDE_STATIC_ANALYSIS_COMPLETE="
        f"{closeout.get('repo_wide_static_analysis_complete', '')}"
    )
    print(
        "SPEC_PRODUCT_COVERAGE_COMPLETE="
        f"{closeout.get('spec_product_coverage_complete', '')}"
    )
    print(f"REVIEW_FINDINGS_INTEGRATED={closeout.get('review_findings_integrated', '')}")
    print(
        "POST_FIX_FULL_REVIEW_COMPLETE="
        f"{closeout.get('post_fix_full_review_complete', '')}"
    )
    print(
        "MECHANICAL_COMPLETION_LOOP_COMPLETE="
        f"{closeout.get('mechanical_completion_loop_complete', '')}"
    )
    print(f"MECHANICAL_LOOP_ITERATIONS={mechanical_loop.get('mechanical_loop_iterations', '')}")
    print(f"MECHANICAL_LOOP_OPEN_ITEMS={mechanical_loop.get('mechanical_loop_open_items', '')}")
    print(
        "MECHANICAL_LOOP_VALIDATION_STATUS="
        f"{mechanical_loop.get('mechanical_loop_validation_status', '')}"
    )
    print(
        "MECHANICAL_LOOP_DEPENDENCY_REVIEW_STATUS="
        f"{mechanical_loop.get('mechanical_loop_dependency_review_status', '')}"
    )
    print(
        "MECHANICAL_LOOP_STATIC_ANALYSIS_STATUS="
        f"{mechanical_loop.get('mechanical_loop_static_analysis_status', '')}"
    )
    print(f"DIFF_CHECK_AGENT_COMPLETE={closeout.get('diff_check_agent_complete', '')}")
    print(f"DIFF_CHECK_AGENT_ROLE={diff_check.get('diff_check_agent_role', '')}")
    print(f"DIFF_CHECK_AGENT_DECISION={diff_check.get('diff_check_agent_decision', '')}")
    print(f"DIFF_CHECK_LATEST_DIFF_REF={diff_check.get('diff_check_latest_diff_ref', '')}")
    print(f"DIFF_CHECK_CURRENT_DIFF_REF={active_diff_ref}")
    print(f"DIFF_CHECK_ARTIFACT={diff_check.get('diff_check_artifact', '')}")
    print(
        "DIFF_CHECK_ARTIFACT_EXISTS="
        f"{'yes' if diff_check_artifact_path and diff_check_artifact_path.is_file() else 'no'}"
    )
    print(
        "CANONICAL_TREE_HEAD_COMPLETE="
        f"{closeout.get('canonical_tree_head_complete', '')}"
    )
    print(f"AGENT_EVALUATION_COMPLETE={closeout.get('agent_evaluation_complete', '')}")
    print(f"AGENT_EVALUATION_STATUS={agent_evaluation.get('evaluation_status', '')}")
    print(f"AGENT_FEEDBACK_RESOLVED={agent_evaluation.get('feedback_actions_resolved', '')}")
    print(
        "AGENT_LEARNING_CAPTURE_COMPLETE="
        f"{agent_evaluation.get('learning_capture_complete', '')}"
    )
    print(f"REQUEST_CONTRACT_RESOLVED={request_contract.get('all_clauses_resolved', '')}")
    print(f"FORBIDDEN_DRIFT_DETECTED={request_contract.get('forbidden_drift_detected', '')}")
    print(f"UNRESOLVED_CLAUSE_IDS={request_contract.get('unresolved_clause_ids', '')}")
    print(f"TODO_ARTIFACT_COMPLETE={'yes' if not schedule_blockers else 'no'}")
    print(f"TODO_ARTIFACT_BLOCKERS={join_blockers(schedule_blockers)}")
    print(f"WORK_LOG_COMPLETE={'yes' if not work_log_blockers else 'no'}")
    print(f"WORK_LOG_BLOCKERS={join_blockers(work_log_blockers)}")
    print(f"COMMIT_CREATED={closeout.get('commit_created', '')}")
    print(f"PUSH_COMPLETED={closeout.get('push_completed', '')}")
    print(f"USER_COMPLETION_REPORT={closeout.get('user_completion_report', '')}")
    print(f"CLOSEOUT_READY={'yes' if ready else 'no'}")

    if not ready:
        missing = ",".join(key for key, passed in checks.items() if not passed)
        print(f"CLOSEOUT_BLOCKERS={missing}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
