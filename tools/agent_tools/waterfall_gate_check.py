#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides waterfall gate check agent workflow automation.
# upstream design ../README.md shared automation index
# @dependency-end

"""Check intermediate waterfall gate readiness for one agent run bundle."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from agent_team import (
    load_materialized_active_design_packet,
    render_active_design_packet_violation,
    resolve_report_root,
    validate_materialized_active_design_packet,
)
from report_artifact_checks import (
    check_schedule_artifact,
    check_work_log_artifact,
    has_approve_decision,
    is_placeholder_only_section,
    section_has_content,
    table_body_rows,
)


@dataclass(frozen=True)
class ArtifactCheck:
    """One artifact requirement for a waterfall gate."""

    path: str
    require_filled: bool = False
    require_approve: bool = False
    required_sections: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateBlocker:
    """One gate blocker with its owning repair stage."""

    code: str
    owner_gate: str


GATE_CHECKS: dict[str, tuple[ArtifactCheck, ...]] = {
    "requirements": (
        ArtifactCheck(
            "user_request_contract.md",
            require_filled=True,
            required_sections=(
                "## Requirements Resolution Sweep",
                "## Resolved From Accumulated Context",
            ),
        ),
        ArtifactCheck(
            "management_review.md",
            require_filled=True,
            require_approve=True,
            required_sections=(
                "## Accumulated Context Resolution Review",
                "## Unknown Handling Review",
            ),
        ),
    ),
    "plan": (
        ArtifactCheck(
            "schedule.md",
            require_filled=True,
            required_sections=(
                "## Stage Plan",
                "## Clause Coverage",
                "## Planned Work Units",
            ),
        ),
        ArtifactCheck("schedule_review.md", require_filled=True, require_approve=True),
    ),
    "design": (
        # The design gate is resolved from run.active_design_packet below.
    ),
    "document_flow": (
        # The document-flow gate is resolved from run.active_design_packet below.
    ),
    "test": (ArtifactCheck("test_plan.md", require_filled=True),),
    "implementation": (
        ArtifactCheck(
            "change_review.md",
            require_filled=True,
            require_approve=True,
            required_sections=(
                "## Design-Base Implementation Review",
                "## Canonical Tree-Head Review",
            ),
        ),
    ),
    "final": (
        ArtifactCheck(
            "final_review.md",
            require_filled=True,
            require_approve=True,
            required_sections=(
                "## Design Trace Acceptance",
                "## Planned Work Completion Review",
                "## Spec-To-Product Coverage Review",
                "## Review Finding Incorporation Review",
                "## Post-Fix Full Review Rerun Review",
                "## Canonical Tree-Head Acceptance",
            ),
        ),
        ArtifactCheck(
            "work_log.md",
            require_filled=True,
            required_sections=("## Entries",),
        ),
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
        help=(
            "Optional directory that contains per-run report folders. Defaults to "
            "./reports/agents relative to the current workspace."
        ),
    )
    return parser


def resolve_report_dir(args: argparse.Namespace) -> Path:
    """Resolve and validate the report directory argument."""
    if bool(args.run_id) == bool(args.report_dir):
        raise SystemExit("Provide exactly one of --run-id or --report-dir.")
    if args.report_dir:
        return Path(args.report_dir).resolve()
    return (
        resolve_report_root(args.report_root, Path.cwd()) / str(args.run_id)
    ).resolve()


def decision_is_approve(text: str) -> bool:
    """Return whether the artifact contains an approve decision."""
    return has_approve_decision(text)


def check_user_request_contract(text: str) -> list[str]:
    """Return blockers for the requirements contract."""
    blockers: list[str] = []
    if not table_body_rows(text, "## Must-Do Clauses"):
        blockers.append("user_request_contract.md:must_do_clauses_empty")
    if not table_body_rows(text, "## Completion Evidence Clauses"):
        blockers.append("user_request_contract.md:completion_evidence_empty")
    for heading in (
        "## Must-Do Clauses",
        "## Must-Not-Do Clauses",
        "## Completion Evidence Clauses",
    ):
        for row in table_body_rows(text, heading):
            if "unknown_or_open_question" in row:
                slug = (
                    heading.removeprefix("## ")
                    .lower()
                    .replace("-", "_")
                    .replace(" ", "_")
                )
                blockers.append(
                    f"user_request_contract.md:active_unknown_clause:{slug}"
                )
    return blockers


def _shared_active_design_blockers(
    report_dir: Path,
    gate: Literal["design", "document_flow", "implementation"],
) -> list[GateBlocker]:
    """Load and validate only the manifest-selected active design packet."""
    materialized = load_materialized_active_design_packet(report_dir)
    violations = list(materialized.violations)
    if materialized.value is not None and materialized.context is not None:
        violations.extend(
            validate_materialized_active_design_packet(
                materialized.value,
                materialized.context,
                gate=gate,
            )
        )
    return [
        GateBlocker(
            code=render_active_design_packet_violation(violation),
            owner_gate="design",
        )
        for violation in sorted(violations, key=lambda value: value.order_key)
    ]


def check_artifact(report_dir: Path, check: ArtifactCheck) -> list[str]:
    """Return blockers for one artifact."""
    blockers: list[str] = []
    path = report_dir / check.path
    if not path.is_file():
        return [f"{check.path}:missing"]
    text = path.read_text(encoding="utf-8")
    if check.require_filled and is_placeholder_only_section(text):
        blockers.append(f"{check.path}:template_or_placeholder_remaining")
    for section in check.required_sections:
        if not section_has_content(text, section):
            slug = section.removeprefix("## ").lower().replace(" ", "_")
            blockers.append(f"{check.path}:section_empty_or_missing:{slug}")
    if check.path == "user_request_contract.md":
        blockers.extend(check_user_request_contract(text))
    elif check.path == "schedule.md":
        blockers.extend(check_schedule_artifact(text))
    elif check.path == "work_log.md":
        blockers.extend(check_work_log_artifact(text))
    if check.require_approve and not decision_is_approve(text):
        blockers.append(f"{check.path}:decision_not_approve")
    return blockers


def next_action_for_gate(gate: str, blockers: list[GateBlocker]) -> str:
    """Return the owning stage that should repair one failed gate check."""
    owner_gate = next(
        (blocker.owner_gate for blocker in blockers if blocker.owner_gate != gate),
        gate,
    )
    return f"return_to_{owner_gate}_owner_until_gate_approves"


def main() -> int:
    """Run the gate check."""
    args = build_parser().parse_args()
    report_dir = resolve_report_dir(args)
    gate = str(args.gate)
    blockers: list[GateBlocker] = []
    if gate in {"design", "document_flow", "implementation"}:
        blockers.extend(
            _shared_active_design_blockers(
                report_dir,
                cast(Literal["design", "document_flow", "implementation"], gate),
            )
        )
        if gate == "implementation":
            for check in GATE_CHECKS["implementation"]:
                blockers.extend(
                    GateBlocker(code=code, owner_gate="implementation")
                    for code in check_artifact(report_dir, check)
                )
    else:
        for check in GATE_CHECKS[gate]:
            blockers.extend(
                GateBlocker(code=code, owner_gate=gate)
                for code in check_artifact(report_dir, check)
            )

    ready = not blockers
    print(f"REPORT_DIR={report_dir}")
    print(f"WATERFALL_GATE={args.gate}")
    print(f"WATERFALL_GATE_READY={'yes' if ready else 'no'}")
    if blockers:
        print(
            f"WATERFALL_GATE_BLOCKERS={','.join(blocker.code for blocker in blockers)}"
        )
        print(f"NEXT_ACTION={next_action_for_gate(gate, blockers)}")
        return 1
    print("NEXT_ACTION=proceed_to_next_waterfall_gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
