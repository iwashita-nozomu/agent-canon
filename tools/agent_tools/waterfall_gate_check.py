#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides waterfall gate check agent workflow automation.
# upstream design ../README.md shared automation index
# @dependency-end

"""Check intermediate waterfall gate readiness for one agent run bundle."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from agent_team import resolve_report_root
from report_artifact_checks import (
    check_schedule_artifact,
    check_work_log_artifact,
    is_placeholder_only_section,
    section_has_content,
    table_body_rows,
)

DECISION_PATTERN = re.compile(r"\b(approve|revise|escalate)\b", re.IGNORECASE)
ABSTRACT_DESIGN_FRAME_REQUIRED_TERMS: dict[str, tuple[str, ...]] = {
    "responsibility_model": ("responsibility model", "responsibility_model"),
    "concept_or_layer_model": (
        "concept graph",
        "concept or layer model",
        "layer model",
        "concept/layer",
        "concept_or_layer_model",
    ),
    "non_goals": ("non-goals", "non_goals", "non goals"),
    "future_extension_layers": (
        "future extension layers",
        "future_extension_layers",
    ),
    "evaluation_axes": ("evaluation axes", "evaluation_axes"),
    "canonical_surface_relationships": (
        "canonical-surface relationships",
        "canonical surface relationships",
        "relationship to existing canonical surfaces",
        "canonical_surface_relationships",
    ),
}


@dataclass(frozen=True)
class ArtifactCheck:
    """One artifact requirement for a waterfall gate."""

    path: str
    require_filled: bool = False
    require_approve: bool = False
    required_sections: tuple[str, ...] = ()


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
        ArtifactCheck(
            "design_brief.md",
            require_filled=True,
            required_sections=(
                "## Upstream Requirement Packet",
                "## Abstract Design Frame",
                "## Implementation Source Packet",
                "## Canonical Tree-Head Plan",
                "## Design-To-Implementation Trace",
            ),
        ),
        ArtifactCheck(
            "design_review.md",
            require_filled=True,
            require_approve=True,
            required_sections=(
                "## Design Artifact Under Review",
                "## Upstream Requirement Packet Review",
                "## Abstract Design Frame Review",
                "## Implementation Source Packet Review",
                "## Canonical Tree-Head Review",
                "## Design-To-Implementation Trace Review",
            ),
        ),
    ),
    "document_flow": (
        ArtifactCheck("document_flow_review.md", require_filled=True, require_approve=True),
    ),
    "test": (
        ArtifactCheck("test_plan.md", require_filled=True),
    ),
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
    return (resolve_report_root(args.report_root, Path.cwd()) / str(args.run_id)).resolve()


def decision_is_approve(text: str) -> bool:
    """Return whether the artifact contains an approve decision."""
    decisions = [match.group(1).lower() for match in DECISION_PATTERN.finditer(text)]
    return bool(decisions) and decisions[-1] == "approve"


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
                slug = heading.removeprefix("## ").lower().replace("-", "_").replace(" ", "_")
                blockers.append(f"user_request_contract.md:active_unknown_clause:{slug}")
    return blockers


def section_body(text: str, heading: str) -> str:
    """Return the body text for one second-level Markdown section."""
    lines = text.splitlines()
    in_section = False
    body: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_section:
                break
            in_section = stripped == heading
            continue
        if in_section:
            body.append(line)
    return "\n".join(body)


def check_abstract_design_frame(text: str) -> list[str]:
    """Return blockers when the abstract design frame is under-specified."""
    body = section_body(text, "## Abstract Design Frame")
    blockers: list[str] = []
    for term_id, accepted_terms in ABSTRACT_DESIGN_FRAME_REQUIRED_TERMS.items():
        if not abstract_term_has_content(body, accepted_terms):
            blockers.append(f"design_brief.md:abstract_design_frame_missing:{term_id}")
    return blockers


def section_label_values(body: str) -> dict[str, str]:
    """Return simple Markdown list label values from a section body."""
    values: dict[str, str] = {}
    for line in body.splitlines():
        stripped = line.strip().lstrip("-* ").strip()
        if ":" not in stripped:
            continue
        label, value = stripped.split(":", 1)
        normalized_label = label.strip().lower()
        if normalized_label:
            values[normalized_label] = value.strip()
    return values


def populated_label_value(values: dict[str, str], label: str) -> bool:
    """Return whether one review label has concrete non-placeholder content."""
    value = values.get(label, "").strip().strip("`")
    return value.lower() not in {"", "-", "todo", "tbd", "none", "n/a"}


def design_artifact_path_matches(value: str, design_brief_path: Path) -> bool:
    """Return whether a review target path names the current design brief."""
    normalized = value.strip().strip("`'\"")
    if not normalized:
        return False
    candidate = Path(normalized)
    if candidate.is_absolute():
        return candidate.resolve() == design_brief_path.resolve()
    if (design_brief_path.parent / candidate).resolve() == design_brief_path.resolve():
        return True
    return normalized in {"design_brief.md", "./design_brief.md"} or (
        not candidate.is_absolute()
        and candidate.name == "design_brief.md"
        and candidate.parent in {Path("."), Path("")}
    )


def check_design_review_artifact(report_dir: Path, text: str) -> list[str]:
    """Return blockers for design review's reviewed-artifact identity."""
    body = section_body(text, "## Design Artifact Under Review")
    values = section_label_values(body)
    blockers: list[str] = []
    design_brief_path = report_dir / "design_brief.md"
    required_labels = (
        "design artifact path",
        "design revision or section set",
        "source packet reviewed",
        "reviewer separation",
    )
    for label in required_labels:
        if not populated_label_value(values, label):
            slug = label.replace(" ", "_")
            blockers.append(f"design_review.md:design_artifact_under_review_missing:{slug}")
    path_value = values.get("design artifact path", "")
    if populated_label_value(values, "design artifact path") and not design_artifact_path_matches(
        path_value,
        design_brief_path,
    ):
        blockers.append("design_review.md:design_artifact_path_not_current")
    return blockers


def abstract_term_has_content(body: str, accepted_terms: tuple[str, ...]) -> bool:
    """Return whether one abstract-frame dimension is named with concrete content."""
    placeholder_values = {"", "-", "todo", "tbd", "none", "n/a"}
    for line in body.splitlines():
        normalized = line.strip().lstrip("-* ").lower()
        matched_term = next(
            (term for term in accepted_terms if normalized.startswith(term)),
            "",
        )
        if not matched_term:
            continue
        remainder = normalized.removeprefix(matched_term).strip()
        if not (remainder.startswith(":") or remainder.startswith("-")):
            continue
        value = remainder[1:].strip()
        if value not in placeholder_values:
            return True
    return False


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
    elif check.path == "design_brief.md":
        blockers.extend(check_abstract_design_frame(text))
    elif check.path == "design_review.md":
        blockers.extend(check_design_review_artifact(report_dir, text))
    elif check.path == "schedule.md":
        blockers.extend(check_schedule_artifact(text))
    elif check.path == "work_log.md":
        blockers.extend(check_work_log_artifact(text))
    if check.require_approve and not decision_is_approve(text):
        blockers.append(f"{check.path}:decision_not_approve")
    return blockers


def next_action_for_gate(gate: str, blockers: list[str]) -> str:
    """Return the owning stage that should repair one failed gate check."""
    if gate == "implementation" and any(
        blocker.startswith(("design_brief.md:", "design_review.md:"))
        for blocker in blockers
    ):
        return "return_to_design_owner_until_gate_approves"
    return f"return_to_{gate}_owner_until_gate_approves"


def main() -> int:
    """Run the gate check."""
    args = build_parser().parse_args()
    report_dir = resolve_report_dir(args)
    checks = GATE_CHECKS[str(args.gate)]
    blockers: list[str] = []
    for check in checks:
        blockers.extend(check_artifact(report_dir, check))
    if args.gate == "implementation" and (report_dir / "design_brief.md").is_file():
        for design_check in GATE_CHECKS["design"]:
            blockers.extend(check_artifact(report_dir, design_check))

    ready = not blockers
    print(f"REPORT_DIR={report_dir}")
    print(f"WATERFALL_GATE={args.gate}")
    print(f"WATERFALL_GATE_READY={'yes' if ready else 'no'}")
    if blockers:
        print(f"WATERFALL_GATE_BLOCKERS={','.join(blockers)}")
        print(f"NEXT_ACTION={next_action_for_gate(str(args.gate), blockers)}")
        return 1
    print("NEXT_ACTION=proceed_to_next_waterfall_gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
