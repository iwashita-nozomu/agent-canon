#!/usr/bin/env python3
"""Check intermediate waterfall gate readiness for one agent run bundle."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from agent_team import DEFAULT_REPORT_ROOT


PLACEHOLDER_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
DECISION_PATTERN = re.compile(r"\b(approve|revise|escalate)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ArtifactCheck:
    """One artifact requirement for a waterfall gate."""

    path: str
    require_filled: bool = False
    require_approve: bool = False


GATE_CHECKS: dict[str, tuple[ArtifactCheck, ...]] = {
    "requirements": (
        ArtifactCheck("user_request_contract.md", require_filled=True),
        ArtifactCheck("management_review.md", require_filled=True, require_approve=True),
    ),
    "plan": (
        ArtifactCheck("schedule.md", require_filled=True),
        ArtifactCheck("schedule_review.md", require_filled=True, require_approve=True),
    ),
    "design": (
        ArtifactCheck("design_brief.md", require_filled=True),
        ArtifactCheck("design_review.md", require_filled=True, require_approve=True),
        ArtifactCheck("document_flow_review.md", require_filled=True, require_approve=True),
    ),
    "test": (
        ArtifactCheck("test_plan.md", require_filled=True),
    ),
    "implementation": (
        ArtifactCheck("change_review.md", require_filled=True, require_approve=True),
    ),
    "final": (
        ArtifactCheck("final_review.md", require_filled=True, require_approve=True),
    ),
}


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Fail unless the requested intermediate waterfall gate is ready.",
    )
    parser.add_argument("--run-id", help="Run id under reports/agents/.")
    parser.add_argument("--report-dir", help="Explicit run directory to inspect.")
    parser.add_argument(
        "--gate",
        required=True,
        choices=tuple(GATE_CHECKS),
        help="Waterfall gate to check.",
    )
    parser.add_argument(
        "--report-root",
        default=str(DEFAULT_REPORT_ROOT),
        help="Directory that contains per-run report folders.",
    )
    return parser


def resolve_report_dir(args: argparse.Namespace) -> Path:
    """Resolve and validate the report directory argument."""
    if bool(args.run_id) == bool(args.report_dir):
        raise SystemExit("Provide exactly one of --run-id or --report-dir.")
    if args.report_dir:
        return Path(args.report_dir).resolve()
    return (Path(args.report_root).resolve() / str(args.run_id)).resolve()


def is_placeholder_only_section(text: str) -> bool:
    """Return whether the artifact still looks like an untouched template."""
    stripped = PLACEHOLDER_PATTERN.sub("", text).strip()
    stripped = "\n".join(
        line
        for line in stripped.splitlines()
        if line.strip()
        and not line.strip().startswith("#")
        and not line.strip().startswith("- Run ID:")
        and not line.strip().startswith("- Task:")
        and not line.strip().startswith("- Owner:")
        and not line.strip().startswith("- Created At")
        and not line.strip().startswith("|")
    ).strip()
    return not stripped


def decision_is_approve(text: str) -> bool:
    """Return whether the artifact contains an approve decision."""
    decisions = [match.group(1).lower() for match in DECISION_PATTERN.finditer(text)]
    return bool(decisions) and decisions[-1] == "approve"


def table_body_rows(text: str, heading: str) -> list[str]:
    """Return non-header table rows under one markdown section."""
    rows: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == heading
            continue
        if not in_section or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(not cell or set(cell) <= {"-"} for cell in cells):
            continue
        if any(cell in {"Clause ID", "Source Bucket"} for cell in cells):
            continue
        rows.append(stripped)
    return rows


def check_user_request_contract(text: str) -> list[str]:
    """Return blockers for the requirements contract."""
    blockers: list[str] = []
    if not table_body_rows(text, "## Must-Do Clauses"):
        blockers.append("user_request_contract.md:must_do_clauses_empty")
    if not table_body_rows(text, "## Completion Evidence Clauses"):
        blockers.append("user_request_contract.md:completion_evidence_empty")
    return blockers


def check_artifact(report_dir: Path, check: ArtifactCheck) -> list[str]:
    """Return blockers for one artifact."""
    blockers: list[str] = []
    path = report_dir / check.path
    if not path.is_file():
        return [f"{check.path}:missing"]
    text = path.read_text(encoding="utf-8")
    if check.require_filled and ("<!--" in text or is_placeholder_only_section(text)):
        blockers.append(f"{check.path}:template_or_placeholder_remaining")
    if check.path == "user_request_contract.md":
        blockers.extend(check_user_request_contract(text))
    if check.require_approve and not decision_is_approve(text):
        blockers.append(f"{check.path}:decision_not_approve")
    return blockers


def main() -> int:
    """Run the gate check."""
    args = build_parser().parse_args()
    report_dir = resolve_report_dir(args)
    checks = GATE_CHECKS[str(args.gate)]
    blockers: list[str] = []
    for check in checks:
        blockers.extend(check_artifact(report_dir, check))

    ready = not blockers
    print(f"REPORT_DIR={report_dir}")
    print(f"WATERFALL_GATE={args.gate}")
    print(f"WATERFALL_GATE_READY={'yes' if ready else 'no'}")
    if blockers:
        print(f"WATERFALL_GATE_BLOCKERS={','.join(blockers)}")
        print(f"NEXT_ACTION=return_to_{args.gate}_owner_until_gate_approves")
        return 1
    print("NEXT_ACTION=proceed_to_next_waterfall_gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
