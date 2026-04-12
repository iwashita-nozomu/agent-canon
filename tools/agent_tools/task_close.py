#!/usr/bin/env python3
"""Evaluate whether one run bundle is ready for a user-facing completion report."""

from __future__ import annotations

import argparse
import re
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


def join_blockers(blockers: list[str]) -> str:
    """Render blocker list for terminal output."""
    return ",".join(blockers) if blockers else ""


def main() -> int:
    """Run the closeout check."""
    args = build_parser().parse_args()
    if bool(args.run_id) == bool(args.report_dir):
        raise SystemExit("Provide exactly one of --run-id or --report-dir.")

    if args.report_dir:
        report_dir = Path(args.report_dir).resolve()
    else:
        report_dir = (resolve_report_root(args.report_root, Path.cwd()) / str(args.run_id)).resolve()

    verification_path = report_dir / "verification.txt"
    closeout_path = report_dir / "closeout_gate.md"
    request_contract_path = report_dir / "user_request_contract.md"
    schedule_path = report_dir / "schedule.md"
    work_log_path = report_dir / "work_log.md"
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

    verification = parse_kv_lines(verification_path)
    closeout = parse_markdown_status(closeout_path)
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
        "spec_product_coverage_complete": closeout.get("spec_product_coverage_complete")
        == "yes",
        "review_findings_integrated": closeout.get("review_findings_integrated") == "yes",
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
    print(
        "SPEC_PRODUCT_COVERAGE_COMPLETE="
        f"{closeout.get('spec_product_coverage_complete', '')}"
    )
    print(f"REVIEW_FINDINGS_INTEGRATED={closeout.get('review_findings_integrated', '')}")
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
