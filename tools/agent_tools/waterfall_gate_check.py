#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides waterfall gate check agent workflow automation.
# upstream design ../README.md shared automation index
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md active design packet schema contract
# upstream implementation ./agent_team.py owns active design packet schema constants and path resolution
# @dependency-end

"""Check intermediate waterfall gate readiness for one agent run bundle."""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypeGuard, cast

import yaml
from agent_team import (
    ACTIVE_DESIGN_PACKET_ARTIFACT_FIELDS,
    ACTIVE_DESIGN_PACKET_FIELDS,
    ACTIVE_DESIGN_PACKET_SCHEMA,
    ReportBundleArtifactPathError,
    resolve_report_bundle_artifact_path,
    resolve_report_root,
)
from report_artifact_checks import (
    check_schedule_artifact,
    check_work_log_artifact,
    is_placeholder_only_section,
    section_has_content,
    table_body_rows,
)

DECISION_PATTERN = re.compile(r"\b(approve|revise|escalate)\b", re.IGNORECASE)
REVIEW_TARGET_SHA_PATTERN = re.compile(
    r"\breview_target_sha256\s*=\s*`?([0-9a-f]{64})`?",
    re.IGNORECASE,
)
DESIGN_ARTIFACT_PATH_PATTERN = re.compile(
    r"^\s*-\s*Design artifact path:\s*`?([^`\r\n]+?)`?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
ABSTRACT_DESIGN_FRAME_REQUIRED_TERMS: dict[str, tuple[str, ...]] = {
    "responsibility_model": ("responsibility model", "responsibility_model"),
    "concept_or_layer_model": (
        "concept graph",
        "concept or layer model",
        "concept/layer model",
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


@dataclass(frozen=True)
class ActiveDesignPacket:
    """Resolved active design packet declared by one run manifest."""

    schema: str
    design_artifact_declared_path: str
    design_artifact: Path
    design_review_artifact: Path
    document_flow_review_artifact: Path
    document_flow_required: bool


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


def check_abstract_design_frame(
    text: str,
    artifact_name: str = "design_brief.md",
) -> list[str]:
    """Return blockers when the abstract design frame is under-specified."""
    body = section_body(text, "## Abstract Design Frame")
    blockers: list[str] = []
    for term_id, accepted_terms in ABSTRACT_DESIGN_FRAME_REQUIRED_TERMS.items():
        if not abstract_term_has_content(body, accepted_terms):
            blockers.append(f"{artifact_name}:abstract_design_frame_missing:{term_id}")
    return blockers


def abstract_term_has_content(body: str, accepted_terms: tuple[str, ...]) -> bool:
    """Return whether one abstract-frame dimension is named with concrete content."""
    placeholder_values = {"", "-", "todo", "tbd", "none", "n/a"}
    lines = body.splitlines()
    for index, line in enumerate(lines):
        normalized = line.strip().lstrip("-* ").lower()
        heading_normalized = normalized.lstrip("#").strip()
        if any(
            heading_normalized == term.lower()
            for term in accepted_terms
        ):
            for following in lines[index + 1 :]:
                following_stripped = following.strip()
                if not following_stripped:
                    continue
                if following_stripped.startswith("#"):
                    break
                if following_stripped.lower() not in placeholder_values:
                    return True
            continue
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


def resolve_active_design_packet_path(
    report_dir: Path,
    field: str,
    value: str,
) -> tuple[Path | None, GateBlocker | None]:
    """Resolve one declared packet path without searching for alternatives."""
    try:
        candidate = resolve_report_bundle_artifact_path(
            report_dir,
            value,
            require_existing_regular_file=True,
        )
    except ReportBundleArtifactPathError as exc:
        blocker_kind = (
            "active_design_packet_path_outside_bundle"
            if exc.reason == "outside_bundle"
            else "active_design_packet_field_invalid"
        )
        return None, active_design_blocker(
            f"team_manifest.yaml:{blocker_kind}:{field}"
        )
    return candidate, None


def is_string_value(value: object) -> bool:
    """Return whether one parsed mapping key is a string."""
    return isinstance(value, str)


def is_string_object_mapping(value: object) -> TypeGuard[dict[str, object]]:
    """Return whether a parsed YAML value is a string-keyed mapping."""
    if not isinstance(value, dict):
        return False
    untyped_mapping = cast(dict[object, object], value)
    return all(map(is_string_value, untyped_mapping))


def active_design_blocker(code: str) -> GateBlocker:
    """Create a blocker owned by the detailed-design gate."""
    return GateBlocker(code=code, owner_gate="design")


def load_active_design_packet(
    report_dir: Path,
) -> tuple[ActiveDesignPacket | None, list[GateBlocker]]:
    """Load and validate only the active packet declared by team_manifest.yaml."""
    manifest_path = report_dir / "team_manifest.yaml"
    if not manifest_path.is_file():
        return None, [active_design_blocker("team_manifest.yaml:missing")]
    try:
        parsed_manifest: object = yaml.safe_load(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError):
        return None, [
            active_design_blocker(
                "team_manifest.yaml:active_design_packet_field_invalid:manifest"
            )
        ]
    if not is_string_object_mapping(parsed_manifest):
        return None, [
            active_design_blocker("team_manifest.yaml:active_design_packet_missing")
        ]
    run_value = parsed_manifest.get("run")
    if not is_string_object_mapping(run_value):
        return None, [
            active_design_blocker("team_manifest.yaml:active_design_packet_missing")
        ]
    packet_value = run_value.get("active_design_packet")
    if not is_string_object_mapping(packet_value):
        return None, [
            active_design_blocker("team_manifest.yaml:active_design_packet_missing")
        ]
    packet = packet_value
    unknown_fields = sorted(set(packet).difference(ACTIVE_DESIGN_PACKET_FIELDS))
    if unknown_fields:
        return None, [
            active_design_blocker(
                "team_manifest.yaml:active_design_packet_field_unknown:"
                + ",".join(unknown_fields)
            )
        ]
    blockers: list[GateBlocker] = []
    for field in ACTIVE_DESIGN_PACKET_FIELDS:
        if field not in packet:
            blockers.append(
                active_design_blocker(
                    f"team_manifest.yaml:active_design_packet_field_missing:{field}"
                )
            )
    if blockers:
        return None, blockers
    schema_value = packet["schema"]
    if not isinstance(schema_value, str):
        return None, [
            active_design_blocker(
                "team_manifest.yaml:active_design_packet_field_invalid:schema"
            )
        ]
    schema = schema_value
    if schema != ACTIVE_DESIGN_PACKET_SCHEMA:
        return None, [
            active_design_blocker(
                f"team_manifest.yaml:active_design_packet_schema_unknown:{schema}"
            )
        ]
    document_flow_required_value = packet["document_flow_required"]
    if not isinstance(document_flow_required_value, bool):
        return None, [
            active_design_blocker(
                "team_manifest.yaml:active_design_packet_field_invalid:document_flow_required"
            )
        ]
    document_flow_required = document_flow_required_value
    resolved: dict[str, Path] = {}
    declared: dict[str, str] = {}
    for field in ACTIVE_DESIGN_PACKET_ARTIFACT_FIELDS:
        field_value = packet[field]
        if not isinstance(field_value, str):
            blockers.append(
                active_design_blocker(
                    f"team_manifest.yaml:active_design_packet_field_invalid:{field}"
                )
            )
            continue
        declared[field] = field_value
        path, blocker = resolve_active_design_packet_path(
            report_dir,
            field,
            field_value,
        )
        if blocker is not None:
            blockers.append(blocker)
        elif path is not None:
            resolved[field] = path
    if blockers:
        return None, blockers
    return (
        ActiveDesignPacket(
            schema=schema,
            design_artifact_declared_path=declared["design_artifact"],
            design_artifact=resolved["design_artifact"],
            design_review_artifact=resolved["design_review_artifact"],
            document_flow_review_artifact=resolved["document_flow_review_artifact"],
            document_flow_required=document_flow_required,
        ),
        [],
    )


def review_target_sha256(text: str) -> str | None:
    """Return the last explicitly recorded review target SHA."""
    matches = REVIEW_TARGET_SHA_PATTERN.findall(text)
    return matches[-1].lower() if matches else None


def review_design_artifact_path(text: str) -> str | None:
    """Return the last explicit Design artifact path review field."""
    matches = DESIGN_ARTIFACT_PATH_PATTERN.findall(text)
    if not matches:
        return None
    return matches[-1].strip().strip("'\"")


def check_review_identity(
    path: Path,
    text: str,
    expected_design_artifact_path: str,
    expected_sha256: str,
) -> list[GateBlocker]:
    """Check one packet review's identity and final decision."""
    relative_path = path.name
    blockers: list[GateBlocker] = []
    reviewed_artifact_path = review_design_artifact_path(text)
    if reviewed_artifact_path is None:
        blockers.append(
            active_design_blocker(f"{relative_path}:design_artifact_path_missing")
        )
    elif reviewed_artifact_path != expected_design_artifact_path:
        blockers.append(
            active_design_blocker(f"{relative_path}:design_artifact_path_mismatch")
        )
    target_sha = review_target_sha256(text)
    if target_sha is None:
        blockers.append(
            active_design_blocker(f"{relative_path}:review_target_sha256_missing")
        )
    elif target_sha != expected_sha256:
        blockers.append(
            active_design_blocker(f"{relative_path}:review_target_sha256_mismatch")
        )
    if not decision_is_approve(text):
        blockers.append(
            active_design_blocker(f"{relative_path}:decision_not_approve")
        )
    return blockers


def check_active_document_flow_review(
    packet: ActiveDesignPacket,
) -> list[GateBlocker]:
    """Check the selected flow review when the packet activates that stage."""
    if not packet.document_flow_required:
        return []
    expected_sha256 = hashlib.sha256(packet.design_artifact.read_bytes()).hexdigest()
    review_path = packet.document_flow_review_artifact
    return check_review_identity(
        review_path,
        review_path.read_text(encoding="utf-8"),
        packet.design_artifact_declared_path,
        expected_sha256,
    )


def check_active_design_packet(
    report_dir: Path,
    packet: ActiveDesignPacket,
) -> list[GateBlocker]:
    """Check the exact declared design and review artifacts."""
    design_path = packet.design_artifact
    design_relative_path = design_path.relative_to(report_dir.resolve()).as_posix()
    blockers = [
        active_design_blocker(code)
        for code in check_artifact(
            report_dir,
            ArtifactCheck(
                design_relative_path,
                require_filled=True,
                required_sections=(
                    "## Abstract Design Frame",
                    "## Implementation Source Packet",
                    "## Design-To-Implementation Trace",
                ),
            ),
        )
    ]
    if not blockers:
        blockers.extend(
            active_design_blocker(code)
            for code in check_abstract_design_frame(
                design_path.read_text(encoding="utf-8"),
                design_relative_path,
            )
        )
    expected_sha256 = hashlib.sha256(design_path.read_bytes()).hexdigest()
    review_path = packet.design_review_artifact
    blockers.extend(
        check_review_identity(
            review_path,
            review_path.read_text(encoding="utf-8"),
            packet.design_artifact_declared_path,
            expected_sha256,
        )
    )
    return [*blockers, *check_active_document_flow_review(packet)]


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
        packet, packet_blockers = load_active_design_packet(report_dir)
        blockers.extend(packet_blockers)
        if packet is not None:
            if gate == "document_flow":
                blockers.extend(check_active_document_flow_review(packet))
            else:
                blockers.extend(check_active_design_packet(report_dir, packet))
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
        print(f"WATERFALL_GATE_BLOCKERS={','.join(blocker.code for blocker in blockers)}")
        print(f"NEXT_ACTION={next_action_for_gate(gate, blockers)}")
        return 1
    print("NEXT_ACTION=proceed_to_next_waterfall_gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
