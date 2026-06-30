#!/usr/bin/env python3
# @dependency-start
# contract tool
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
from collections.abc import Sequence
from pathlib import Path

from agent_team import resolve_report_root
from report_artifact_checks import (
    check_final_review_artifact,
    check_schedule_artifact,
    check_work_log_artifact,
    report_artifact_placement_blockers,
    token_fields,
    wave_reconciliation_blockers,
)

STATIC_ANALYSIS_COMPLETE_STATUSES = {"yes", "profile_selected"}
MAKE_CI_READY_STATUSES = {"pass", "targeted", "not_applicable"}
MECHANICAL_STATIC_ANALYSIS_READY_STATUSES = {"pass", "targeted", "not_applicable"}
DOCUMENT_STRUCTURE_MISSING_VALUES = {"", "missing", "none", "not_applicable"}
DOCUMENT_SPLIT_DECISION_PREFIXES = (
    "keep:",
    "split:",
    "merge:",
    "inline:",
    "rename:",
)
DOCUMENT_SPLIT_DECISION_FORMAT_ONLY_PREFIX = "not_applicable:format-only:"


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


def markdown_section_text(path: Path, heading: str) -> str:
    """Return one level-2 Markdown section."""
    lines = path.read_text(encoding="utf-8").splitlines()
    target = f"## {heading}"
    in_section = False
    selected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == target:
            in_section = True
            selected.append(line)
            continue
        if in_section and stripped.startswith("## "):
            break
        if in_section:
            selected.append(line)
    return "\n".join(selected)


def workflow_tool_warning_problems(workflow_monitoring_path: Path) -> tuple[str, ...]:
    """Return unresolved workflow-monitoring tool warning problems."""
    if not workflow_monitoring_path.is_file():
        return ("workflow_monitoring.md missing",)
    status = parse_markdown_status(workflow_monitoring_path).get(
        "tool_warnings_status", ""
    ).strip().lower()
    problems: list[str] = []
    if status not in {"none", "resolved"}:
        problems.append("tool_warnings_status must be none or resolved")
    latest_by_id: dict[str, dict[str, str]] = {}
    for line in markdown_section_text(
        workflow_monitoring_path, "Tool Warnings"
    ).splitlines():
        if "tool_warning=recorded" not in line:
            continue
        fields = token_fields(line)
        warning_id = fields.get("warning_id", "")
        if not warning_id:
            problems.append("tool_warning entry missing warning_id")
            continue
        latest_by_id[warning_id] = fields
    for warning_id, fields in sorted(latest_by_id.items()):
        warning_status = fields.get("status", "").lower()
        severity = fields.get("severity", "").lower()
        if warning_status in {"", "open", "pending", "observed", "unresolved"}:
            problems.append(f"tool warning remains open: {warning_id}")
        if severity in {"fix-now", "s0", "s1", "blocker"} and warning_status != "resolved":
            problems.append(f"fix-now tool warning must be resolved: {warning_id}")
    return tuple(problems)


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
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    diff_bytes = unstaged.stdout + staged.stdout
    if untracked.returncode == 0 and untracked.stdout:
        for raw_path in sorted(path for path in untracked.stdout.split(b"\0") if path):
            if raw_path.startswith(b"reports/agents/"):
                continue
            path = workspace / raw_path.decode("utf-8", errors="surrogateescape")
            diff_bytes += b"\0UNTRACKED\0" + raw_path + b"\0"
            if path.is_file():
                diff_bytes += path.read_bytes()
    if not diff_bytes:
        return head
    diff_hash = hashlib.sha256(diff_bytes).hexdigest()
    return f"{head}-dirty-{diff_hash}"


def changed_markdown_paths(workspace: Path) -> tuple[str, ...]:
    """Return source-tree Markdown paths changed in the current checkout."""
    commands = (
        ("git", "diff", "--name-only"),
        ("git", "diff", "--cached", "--name-only"),
        ("git", "ls-files", "--others", "--exclude-standard"),
    )
    paths: set[str] = set()
    for command in commands:
        result = subprocess.run(
            list(command),
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            path = line.strip()
            if not path.endswith(".md"):
                continue
            if path.startswith(("reports/", ".agent-canon/log-archive/")):
                continue
            paths.add(path)
    return tuple(sorted(paths))


def parse_document_structure_paths(value: str) -> set[str]:
    """Parse a closeout document-structure path list."""
    if value in {"", "missing", "none"}:
        return set()
    return {
        Path(item.strip()).as_posix()
        for item in re.split(r"[,\s]+", value)
        if item.strip() and item.strip() not in {"missing", "none"}
    }


def document_split_decision_ready(status: str, decision: str) -> bool:
    """Return whether document split evidence matches the structure route."""
    normalized_decision = decision.strip()
    if normalized_decision in DOCUMENT_STRUCTURE_MISSING_VALUES:
        return False
    if status == "skipped":
        return normalized_decision.startswith(DOCUMENT_SPLIT_DECISION_FORMAT_ONLY_PREFIX)
    if status == "complete":
        return normalized_decision.startswith(DOCUMENT_SPLIT_DECISION_PREFIXES)
    return False


def document_structure_evidence_ready(
    changed_markdown: Sequence[str], evidence: dict[str, str]
) -> tuple[bool, bool, bool]:
    """Return path-record, split-decision, and route readiness."""
    if not changed_markdown:
        return True, True, True
    recorded_paths = parse_document_structure_paths(
        evidence.get("document_structure_paths", "")
    )
    normalized_changed = {Path(path).as_posix() for path in changed_markdown}
    paths_recorded = normalized_changed.issubset(recorded_paths)
    status = evidence.get("document_structure_status", "")
    structure_contract = evidence.get("structure_contract", "")
    split_decision_ready = document_split_decision_ready(
        status, evidence.get("document_split_decision", "")
    )
    complete_route = (
        status == "complete"
        and evidence.get("structure_planning") == "complete"
        and evidence.get("prose_graph") == "complete"
        and structure_contract
        not in {"", "missing", "none", "not_applicable"}
        and "skipped" not in structure_contract
    )
    skipped_route = (
        status == "skipped"
        and evidence.get("md_style_check") == "pass"
        and "skipped" in evidence.get("structure_contract", "")
        and evidence.get("format_only_reason", "") not in {"", "missing", "none"}
    )
    return paths_recorded, split_decision_ready, split_decision_ready and (
        complete_route or skipped_route
    )


def active_run_name(report_dir: Path) -> str | None:
    """Return the active run marker for a report root, or None when absent."""
    active_run_path = report_dir.parent / ".active_run"
    if not active_run_path.is_file():
        return None
    return active_run_path.read_text(encoding="utf-8").strip()


def active_run_matches(active_run: str | None, report_dir: Path) -> bool:
    """Return whether one active-run marker points to this report directory."""
    return active_run in {report_dir.name, str(report_dir.resolve())}


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
    active_run = active_run_name(report_dir)

    verification_path = report_dir / "verification.txt"
    closeout_path = report_dir / "closeout_gate.md"
    request_contract_path = report_dir / "user_request_contract.md"
    schedule_path = report_dir / "schedule.md"
    work_log_path = report_dir / "work_log.md"
    workflow_monitoring_path = report_dir / "workflow_monitoring.md"
    final_review_path = report_dir / "final_review.md"
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
    tool_warning_evidence = parse_markdown_status_section(
        closeout_path, "Tool Warning Evidence"
    )
    document_structure = parse_markdown_status_section(
        closeout_path, "Document Structure Evidence"
    )
    subagent_lifecycle = parse_markdown_status_section(
        closeout_path, "Subagent Lifecycle Evidence"
    )
    agent_canon_latest = parse_markdown_status_section(
        closeout_path, "AgentCanon Latest And CI Gate Evidence"
    )
    runtime_log_archive = parse_markdown_status_section(
        closeout_path, "Runtime Log Archive Evidence"
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
    changed_markdown = changed_markdown_paths(workspace)
    (
        document_structure_paths_ready,
        document_split_decision_route_ready,
        document_structure_route_ready,
    ) = (
        document_structure_evidence_ready(changed_markdown, document_structure)
    )
    agent_evaluation = parse_markdown_status(agent_evaluation_path)
    workflow_tool_warning_blockers = workflow_tool_warning_problems(
        workflow_monitoring_path
    )
    request_contract = parse_markdown_status(request_contract_path)
    schedule_text = schedule_path.read_text(encoding="utf-8")
    workflow_monitoring_text = (
        workflow_monitoring_path.read_text(encoding="utf-8")
        if workflow_monitoring_path.is_file()
        else ""
    )
    schedule_blockers = check_schedule_artifact(schedule_text)
    work_log_blockers = check_work_log_artifact(work_log_path.read_text(encoding="utf-8"))
    final_review_blockers = (
        check_final_review_artifact(final_review_path.read_text(encoding="utf-8"))
        if final_review_path.is_file()
        else ["final_review.md:missing"]
    )
    report_artifact_blockers = report_artifact_placement_blockers(workspace, report_dir)
    wave_reconciliation = wave_reconciliation_blockers(
        schedule_text,
        workflow_monitoring_text,
        subagent_lifecycle,
        report_dir,
        workspace,
    )

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
        "repo_wide_static_analysis_complete": closeout.get(
            "repo_wide_static_analysis_complete"
        )
        in STATIC_ANALYSIS_COMPLETE_STATUSES,
        "agent_canon_latest_complete": closeout.get("agent_canon_latest_complete") == "yes",
        "agent_canon_latest_command": agent_canon_latest.get(
            "agent_canon_latest_command", ""
        )
        not in {"", "missing", "none"},
        "agent_canon_latest_status": agent_canon_latest.get("agent_canon_latest_status", "")
        == "pass",
        "agent_canon_submodule_status": agent_canon_latest.get(
            "agent_canon_submodule_status", ""
        )
        not in {"", "missing", "none"},
        "agent_canon_source_head": agent_canon_latest.get("agent_canon_source_head", "")
        not in {"", "missing", "none"},
        "agent_canon_parent_pin": agent_canon_latest.get("agent_canon_parent_pin", "")
        not in {"", "missing", "none"},
        "make_ci_status": closeout.get("make_ci_status") in MAKE_CI_READY_STATUSES,
        "spec_product_coverage_complete": closeout.get("spec_product_coverage_complete")
        == "yes",
        "review_findings_integrated": closeout.get("review_findings_integrated") == "yes",
        "post_fix_full_review_complete": closeout.get("post_fix_full_review_complete") == "yes",
        "tool_warnings_resolved": closeout.get("tool_warnings_resolved") == "yes",
        "tool_warning_monitoring_status": tool_warning_evidence.get(
            "tool_warning_monitoring_status", ""
        )
        in {"none", "resolved"},
        "tool_warning_open_items": tool_warning_evidence.get("tool_warning_open_items")
        == "none",
        "tool_warning_resolution_evidence": tool_warning_evidence.get(
            "tool_warning_resolution_evidence", ""
        )
        not in {"", "missing", "none"},
        "workflow_tool_warnings_closed": not workflow_tool_warning_blockers,
        "document_structure_paths_recorded": document_structure_paths_ready,
        "document_split_decision_evidence": document_split_decision_route_ready,
        "document_structure_evidence": document_structure_route_ready,
        "mechanical_completion_loop_complete": closeout.get(
            "mechanical_completion_loop_complete"
        )
        == "yes",
        "subagents_closed": closeout.get("subagents_closed") == "yes",
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
        in MECHANICAL_STATIC_ANALYSIS_READY_STATUSES,
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
        "fresh_subagents_required": subagent_lifecycle.get("fresh_subagents_required")
        == "yes",
        "reuse_for_new_task": subagent_lifecycle.get("reuse_for_new_task")
        == "forbidden",
        "previous_task_subagent_reuse": subagent_lifecycle.get(
            "previous_task_subagent_reuse"
        )
        == "none",
        "agent_wave_ledger_status": subagent_lifecycle.get("agent_wave_ledger_status")
        in {"complete", "not_applicable"},
        "planned_vs_actual_wave_status": subagent_lifecycle.get(
            "planned_vs_actual_wave_status"
        )
        in {"reconciled", "not_applicable"},
        "subagent_wave_reconciliation_clean": not wave_reconciliation,
        "dynamic_spawn_policy_status": subagent_lifecycle.get("dynamic_spawn_policy_status")
        in {"applied", "not_applicable"},
        "subagent_closeout_status": subagent_lifecycle.get("subagent_closeout_status")
        == "closed",
        "open_subagent_instances": subagent_lifecycle.get("open_subagent_instances")
        == "none",
        "close_agent_evidence": subagent_lifecycle.get("close_agent_evidence", "")
        not in {"", "none", "missing"},
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
        "runtime_log_archive_synced": closeout.get("runtime_log_archive_synced") == "yes",
        "runtime_log_archive_sync_command": runtime_log_archive.get(
            "runtime_log_archive_sync_command", ""
        )
        not in {"", "missing", "none"},
        "runtime_log_archive_sync_status": runtime_log_archive.get(
            "runtime_log_archive_sync_status", ""
        )
        == "pass",
        "runtime_log_archive_check_clean_status": runtime_log_archive.get(
            "runtime_log_archive_check_clean_status", ""
        )
        == "pass",
        "runtime_log_archive_dirty": runtime_log_archive.get(
            "runtime_log_archive_dirty", ""
        )
        == "no",
        "runtime_log_archive_foreign_dirty": runtime_log_archive.get(
            "runtime_log_archive_foreign_dirty", ""
        )
        == "no",
        "runtime_log_archive_branch_match": runtime_log_archive.get(
            "runtime_log_archive_branch_match", ""
        )
        == "yes",
        "runtime_log_archive_commit_or_noop": runtime_log_archive.get(
            "runtime_log_archive_commit", ""
        )
        not in {"", "missing", "none"},
        "runtime_log_archive_push_or_noop": runtime_log_archive.get(
            "runtime_log_archive_push", ""
        )
        not in {"", "missing", "none"},
        "agent_evaluation_status": agent_evaluation.get("evaluation_status") == "pass",
        "agent_feedback_resolved": agent_evaluation.get("feedback_actions_resolved") == "yes",
        "agent_learning_capture_complete": agent_evaluation.get("learning_capture_complete")
        == "yes",
        "request_contract_resolved": request_contract.get("all_clauses_resolved") == "yes",
        "no_forbidden_drift": request_contract.get("forbidden_drift_detected") == "no",
        "todo_artifact_complete": not schedule_blockers,
        "work_log_complete": not work_log_blockers,
        "final_review_artifact_complete": not final_review_blockers,
        "report_active_run_match": active_run_matches(active_run, report_dir),
        "report_artifact_placement_clean": not report_artifact_blockers,
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
        "AGENT_CANON_LATEST_COMPLETE="
        f"{closeout.get('agent_canon_latest_complete', '')}"
    )
    print(
        "AGENT_CANON_LATEST_COMMAND="
        f"{agent_canon_latest.get('agent_canon_latest_command', '')}"
    )
    print(
        "AGENT_CANON_LATEST_STATUS="
        f"{agent_canon_latest.get('agent_canon_latest_status', '')}"
    )
    print(
        "AGENT_CANON_SUBMODULE_STATUS="
        f"{agent_canon_latest.get('agent_canon_submodule_status', '')}"
    )
    print(
        "AGENT_CANON_SOURCE_HEAD="
        f"{agent_canon_latest.get('agent_canon_source_head', '')}"
    )
    print(
        "AGENT_CANON_PARENT_PIN="
        f"{agent_canon_latest.get('agent_canon_parent_pin', '')}"
    )
    print(f"MAKE_CI_STATUS={closeout.get('make_ci_status', '')}")
    print(
        "SPEC_PRODUCT_COVERAGE_COMPLETE="
        f"{closeout.get('spec_product_coverage_complete', '')}"
    )
    print(f"REVIEW_FINDINGS_INTEGRATED={closeout.get('review_findings_integrated', '')}")
    print(
        "POST_FIX_FULL_REVIEW_COMPLETE="
        f"{closeout.get('post_fix_full_review_complete', '')}"
    )
    print(f"TOOL_WARNINGS_RESOLVED={closeout.get('tool_warnings_resolved', '')}")
    print(
        "TOOL_WARNING_MONITORING_STATUS="
        f"{tool_warning_evidence.get('tool_warning_monitoring_status', '')}"
    )
    print(
        "TOOL_WARNING_OPEN_ITEMS="
        f"{tool_warning_evidence.get('tool_warning_open_items', '')}"
    )
    print(
        "TOOL_WARNING_RESOLUTION_EVIDENCE="
        f"{tool_warning_evidence.get('tool_warning_resolution_evidence', '')}"
    )
    print(
        "WORKFLOW_TOOL_WARNING_BLOCKERS="
        f"{join_blockers(list(workflow_tool_warning_blockers))}"
    )
    print(
        "DOCUMENT_STRUCTURE_REQUIRED="
        f"{'yes' if changed_markdown else 'no'}"
    )
    print(
        "DOCUMENT_STRUCTURE_CHANGED_MARKDOWN="
        f"{','.join(changed_markdown) if changed_markdown else 'none'}"
    )
    print(
        "DOCUMENT_STRUCTURE_STATUS="
        f"{document_structure.get('document_structure_status', '')}"
    )
    print(
        "DOCUMENT_STRUCTURE_PATHS="
        f"{document_structure.get('document_structure_paths', '')}"
    )
    print(
        "DOCUMENT_SPLIT_DECISION="
        f"{document_structure.get('document_split_decision', '')}"
    )
    print(
        "DOCUMENT_SPLIT_DECISION_EVIDENCE="
        f"{'yes' if document_split_decision_route_ready else 'no'}"
    )
    print(
        "DOCUMENT_STRUCTURE_EVIDENCE="
        f"{'yes' if document_structure_route_ready else 'no'}"
    )
    print(
        "MECHANICAL_COMPLETION_LOOP_COMPLETE="
        f"{closeout.get('mechanical_completion_loop_complete', '')}"
    )
    print(f"SUBAGENTS_CLOSED={closeout.get('subagents_closed', '')}")
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
    print(
        "SUBAGENT_FRESH_REQUIRED="
        f"{subagent_lifecycle.get('fresh_subagents_required', '')}"
    )
    print(
        "SUBAGENT_REUSE_FOR_NEW_TASK="
        f"{subagent_lifecycle.get('reuse_for_new_task', '')}"
    )
    print(
        "SUBAGENT_PREVIOUS_TASK_REUSE="
        f"{subagent_lifecycle.get('previous_task_subagent_reuse', '')}"
    )
    print(
        "SUBAGENT_CLOSEOUT_STATUS="
        f"{subagent_lifecycle.get('subagent_closeout_status', '')}"
    )
    print(
        "SUBAGENT_WAVE_RECONCILIATION_BLOCKERS="
        f"{join_blockers(wave_reconciliation)}"
    )
    print(
        "SUBAGENT_OPEN_INSTANCES="
        f"{subagent_lifecycle.get('open_subagent_instances', '')}"
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
    print(f"RUNTIME_LOG_ARCHIVE_SYNCED={closeout.get('runtime_log_archive_synced', '')}")
    print(
        "RUNTIME_LOG_ARCHIVE_SYNC_COMMAND="
        f"{runtime_log_archive.get('runtime_log_archive_sync_command', '')}"
    )
    print(
        "RUNTIME_LOG_ARCHIVE_SYNC_STATUS="
        f"{runtime_log_archive.get('runtime_log_archive_sync_status', '')}"
    )
    print(
        "RUNTIME_LOG_ARCHIVE_CHECK_CLEAN_STATUS="
        f"{runtime_log_archive.get('runtime_log_archive_check_clean_status', '')}"
    )
    print(
        "RUNTIME_LOG_ARCHIVE_DIRTY="
        f"{runtime_log_archive.get('runtime_log_archive_dirty', '')}"
    )
    print(
        "RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY="
        f"{runtime_log_archive.get('runtime_log_archive_foreign_dirty', '')}"
    )
    print(
        "RUNTIME_LOG_ARCHIVE_BRANCH_MATCH="
        f"{runtime_log_archive.get('runtime_log_archive_branch_match', '')}"
    )
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
    print(f"FINAL_REVIEW_ARTIFACT_COMPLETE={'yes' if not final_review_blockers else 'no'}")
    print(f"FINAL_REVIEW_ARTIFACT_BLOCKERS={join_blockers(final_review_blockers)}")
    print(f"REPORT_ACTIVE_RUN={active_run or ''}")
    print(f"REPORT_ACTIVE_RUN_MATCH={'yes' if active_run_matches(active_run, report_dir) else 'no'}")
    print(
        "REPORT_ARTIFACT_PLACEMENT_CLEAN="
        f"{'yes' if not report_artifact_blockers else 'no'}"
    )
    print(f"REPORT_ARTIFACT_PLACEMENT_BLOCKERS={join_blockers(report_artifact_blockers)}")
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
