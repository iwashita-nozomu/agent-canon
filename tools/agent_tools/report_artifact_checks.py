#!/usr/bin/env python3
# @dependency-start
# responsibility Provides report artifact checks agent workflow automation.
# upstream design ../README.md shared automation index
# @dependency-end

"""Shared checks for run-bundle artifact completeness."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PLACEHOLDER_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
APPROVE_DECISION_PATTERN = re.compile(
    r"^(?:[-*]\s*)?(?:decision\s*:\s*)?approve\s*$",
    re.IGNORECASE,
)
REQUIRED_ACTUAL_WAVE_FIELDS = (
    "wave_event",
    "wave_id",
    "event_kind",
    "spawn_authority",
    "trigger",
    "budget_before",
    "budget_after",
    "runtime_max_threads",
    "runtime_max_depth",
    "spawned_roles",
    "skipped_roles",
    "allowed_paths",
    "do_not_read",
    "write_scope",
    "validation_route",
    "review_gate",
    "handoff_artifacts",
    "status",
)
MID_TASK_CLASSIFICATION_ACTIONS = {
    "same_active_task_delta": "send_input",
    "scope_or_contract_change": "fresh_followup_wave",
    "new_task": "fresh_run",
}
MID_TASK_CLASSIFICATION_SCOPE_STATUS = {
    "same_active_task_delta": "unchanged",
    "scope_or_contract_change": "changed",
    "new_task": "new_task",
}
MID_TASK_REQUIRED_WAVE_FIELDS = (
    "input_classification",
    "updated_packet",
    "redispatch_action",
    "target_agents",
    "scope_status",
    "lifecycle_policy_ref",
)
WAVE_COMPARISON_FIELDS = (
    ("Spawn Authority", "spawn_authority"),
    ("Trigger", "trigger"),
    ("Budget Before", "budget_before"),
    ("Budget After", "budget_after"),
    ("Runtime Max Threads", "runtime_max_threads"),
    ("Runtime Max Depth", "runtime_max_depth"),
    ("Allowed Paths", "allowed_paths"),
    ("Do Not Read", "do_not_read"),
    ("Write Scope", "write_scope"),
    ("Validation Route", "validation_route"),
    ("Review Gate", "review_gate"),
    ("Handoff Artifacts", "handoff_artifacts"),
    ("Status", "status"),
)


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


def section_has_content(text: str, heading: str) -> bool:
    """Return whether a markdown section exists and has non-placeholder content."""
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
    if not in_section:
        return False
    body_text = PLACEHOLDER_PATTERN.sub("", "\n".join(body))
    body_text = "\n".join(line for line in body_text.splitlines() if line.strip()).strip()
    return bool(body_text)


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
        if any(
            cell in {"Clause ID", "Source Bucket", "Stage", "Unit ID", "Wave ID", "Time"}
            for cell in cells
        ):
            continue
        rows.append(stripped)
    return rows


def markdown_table_dict_rows(text: str, heading: str) -> list[dict[str, str]]:
    """Return markdown table rows as dictionaries under one level-2 heading."""
    rows: list[dict[str, str]] = []
    headers: list[str] | None = None
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == heading
            headers = None
            continue
        if not in_section or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(not cell or set(cell) <= {"-"} for cell in cells):
            continue
        if headers is None:
            headers = cells
            continue
        padded = cells + [""] * max(0, len(headers) - len(cells))
        rows.append({header: padded[index] for index, header in enumerate(headers)})
    return rows


def bullet_rows(text: str, heading: str) -> list[str]:
    """Return bullet rows under one markdown section."""
    rows: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == heading
            continue
        if not in_section:
            continue
        if stripped.startswith("- "):
            rows.append(stripped)
    return rows


def token_fields(line: str) -> dict[str, str]:
    """Parse whitespace-separated key=value fields from one evidence line."""
    data: dict[str, str] = {}
    for token in line.strip().strip("-").strip("`").split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        data[key.strip()] = value.strip("`'\"")
    return data


def _git_report_paths(workspace: Path, args: tuple[str, ...]) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", *args, "-z", "--", "reports"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        return []
    return [
        raw_path.decode("utf-8", errors="surrogateescape")
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    ]


def report_artifact_placement_blockers(workspace: Path, report_dir: Path) -> list[str]:
    """Return generated report artifacts outside the active run bundle.

    Tracked durable reports are allowed. Untracked or ignored generated report files
    are allowed only under the current run directory because runtime archive tooling
    collects one active run bundle at closeout.
    """
    if not report_dir.resolve().is_relative_to(workspace.resolve()):
        return []
    report_paths = {
        path: "untracked"
        for path in _git_report_paths(
            workspace,
            ("--others", "--exclude-standard"),
        )
    }
    for path in _git_report_paths(
        workspace,
        ("--others", "--ignored", "--exclude-standard"),
    ):
        report_paths.setdefault(path, "ignored")

    blockers: list[str] = []
    report_root_metadata = {
        (report_dir.parent / ".active_run").resolve(),
        (report_dir.parent / ".active_run.sha256").resolve(),
    }
    for path, state in sorted(report_paths.items()):
        candidate = workspace / path
        if candidate.resolve() in report_root_metadata:
            continue
        if candidate.resolve().is_relative_to(report_dir.resolve()):
            continue
        blockers.append(f"report_artifact_{state}_outside_current_run:{path}")
    return blockers


def actual_wave_event_fields(workflow_monitoring_text: str) -> list[dict[str, str]]:
    """Return structured Actual Wave Events rows from workflow_monitoring.md."""
    rows: list[dict[str, str]] = []
    in_section = False
    for line in workflow_monitoring_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == "## Actual Wave Events"
            continue
        if not in_section or "wave_event=" not in stripped:
            continue
        rows.append(token_fields(stripped))
    return rows


def _split_csv_field(value: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in value.split(",")
        if item.strip() and item.strip().lower() != "none"
    )


def _actual_waves_by_id(
    actual_rows: list[dict[str, str]],
) -> tuple[dict[str, dict[str, str]], list[str]]:
    actual_by_id: dict[str, dict[str, str]] = {}
    blockers: list[str] = []
    for row in actual_rows:
        wave_id = row.get("wave_id", "").strip()
        if not wave_id:
            blockers.append("workflow_monitoring.md:actual_wave_missing:wave_id")
            continue
        if wave_id in actual_by_id:
            blockers.append(f"workflow_monitoring.md:actual_wave_duplicate:{wave_id}")
            continue
        actual_by_id[wave_id] = row
    return actual_by_id, blockers


def _actual_wave_field_blockers(wave_id: str, actual: dict[str, str]) -> list[str]:
    blockers = [
        f"workflow_monitoring.md:actual_wave_field_missing:{wave_id}:{field}"
        for field in REQUIRED_ACTUAL_WAVE_FIELDS
        if actual.get(field, "").strip() in {"", "missing"}
    ]
    if actual.get("event_kind") == "mid_task_user_input":
        blockers.extend(_mid_task_user_input_blockers(wave_id, actual))
    return blockers


def _mid_task_user_input_blockers(
    wave_id: str,
    actual: dict[str, str],
) -> list[str]:
    """Return blockers for mid-task user input wave checkpoints."""
    blockers = [
        f"workflow_monitoring.md:mid_task_user_input_field_missing:{wave_id}:{field}"
        for field in MID_TASK_REQUIRED_WAVE_FIELDS
        if actual.get(field, "").strip() in {"", "missing"}
    ]
    if actual.get("updated_packet", "").strip() == "none":
        blockers.append(
            f"workflow_monitoring.md:mid_task_user_input_field_missing:{wave_id}:updated_packet"
        )
    classification = actual.get("input_classification", "").strip()
    if not classification:
        return blockers
    if classification not in MID_TASK_CLASSIFICATION_ACTIONS:
        blockers.append(
            "workflow_monitoring.md:mid_task_user_input_invalid_classification:"
            f"{wave_id}:{classification}"
        )
        return blockers
    expected_action = MID_TASK_CLASSIFICATION_ACTIONS[classification]
    if actual.get("redispatch_action", "").strip() != expected_action:
        blockers.append(
            "workflow_monitoring.md:mid_task_user_input_invalid_redispatch_action:"
            f"{wave_id}:expected={expected_action}"
        )
    expected_scope = MID_TASK_CLASSIFICATION_SCOPE_STATUS[classification]
    if actual.get("scope_status", "").strip() != expected_scope:
        blockers.append(
            "workflow_monitoring.md:mid_task_user_input_invalid_scope_status:"
            f"{wave_id}:expected={expected_scope}"
        )
    target_agents = actual.get("target_agents", "").strip()
    if classification != "new_task" and target_agents in {"", "missing", "none"}:
        blockers.append(
            f"workflow_monitoring.md:mid_task_user_input_field_missing:{wave_id}:target_agents"
        )
    return blockers


def _actual_wave_mismatch_blockers(
    wave_id: str,
    planned: dict[str, str],
    actual: dict[str, str],
) -> list[str]:
    blockers: list[str] = []
    for schedule_field, event_field in WAVE_COMPARISON_FIELDS:
        planned_value = planned.get(schedule_field, "").strip()
        if planned_value and planned_value != actual.get(event_field, "").strip():
            blockers.append(
                "workflow_monitoring.md:actual_wave_mismatch:"
                f"{wave_id}:{event_field}"
            )
    if _split_csv_field(planned.get("Spawned Roles", "")) != _split_csv_field(
        actual.get("spawned_roles", "")
    ):
        blockers.append(f"workflow_monitoring.md:actual_wave_mismatch:{wave_id}:spawned_roles")
    return blockers


def wave_reconciliation_blockers(
    schedule_text: str,
    workflow_monitoring_text: str,
    lifecycle_status: dict[str, str],
) -> list[str]:
    """Return blockers when planned subagent waves do not match observed events."""
    planned_rows = markdown_table_dict_rows(schedule_text, "## Agent Wave Ledger")
    planned_by_id = {
        row.get("Wave ID", "").strip(): row
        for row in planned_rows
        if row.get("Wave ID", "").strip()
    }
    blockers: list[str] = []

    if lifecycle_status.get("agent_wave_ledger_status") == "not_applicable":
        actual_rows = actual_wave_event_fields(workflow_monitoring_text)
        if planned_by_id or actual_rows:
            blockers.append("subagent_lifecycle:not_applicable_but_wave_evidence_present")
        return blockers

    actual_by_id, actual_id_blockers = _actual_waves_by_id(
        actual_wave_event_fields(workflow_monitoring_text)
    )
    blockers.extend(actual_id_blockers)

    for wave_id, planned in planned_by_id.items():
        actual = actual_by_id.get(wave_id)
        if actual is None:
            blockers.append(f"workflow_monitoring.md:actual_wave_missing:{wave_id}")
            continue
        blockers.extend(_actual_wave_field_blockers(wave_id, actual))
        blockers.extend(_actual_wave_mismatch_blockers(wave_id, planned, actual))
    for wave_id in sorted(set(actual_by_id) - set(planned_by_id)):
        blockers.append(f"workflow_monitoring.md:actual_wave_without_plan:{wave_id}")
    return blockers


def check_schedule_artifact(text: str) -> list[str]:
    """Return blockers for schedule.md."""
    blockers: list[str] = []
    required_tables = (
        ("## Stage Plan", "stage_plan_empty"),
        ("## Clause Coverage", "clause_coverage_empty"),
        ("## Planned Work Units", "planned_work_units_empty"),
        ("## Agent Wave Ledger", "agent_wave_ledger_empty"),
    )
    for heading, slug in required_tables:
        if not table_body_rows(text, heading):
            blockers.append(f"schedule.md:{slug}")
    return blockers


def check_work_log_artifact(text: str) -> list[str]:
    """Return blockers for work_log.md."""
    blockers: list[str] = []
    if not section_has_content(text, "## Entries"):
        blockers.append("work_log.md:section_empty_or_missing:entries")
        return blockers
    if not bullet_rows(text, "## Entries"):
        blockers.append("work_log.md:entries_empty")
    return blockers


def final_review_decision_lines(text: str) -> list[str]:
    """Return normalized non-placeholder lines from a final-review Decision section."""
    lines: list[str] = []
    in_decision = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_decision:
                break
            in_decision = stripped == "## Decision"
            continue
        if in_decision:
            normalized = PLACEHOLDER_PATTERN.sub("", line).strip()
            if normalized:
                lines.append(normalized)
    return lines


def has_approve_decision(text: str) -> bool:
    """Return whether a final-review Decision section contains an exact approve decision."""
    return any(APPROVE_DECISION_PATTERN.fullmatch(line) for line in final_review_decision_lines(text))


def check_final_review_artifact(text: str) -> list[str]:
    """Return blockers for final_review.md."""
    blockers: list[str] = []
    if is_placeholder_only_section(text):
        blockers.append("final_review.md:placeholder_only")
    if not section_has_content(text, "## Decision"):
        blockers.append("final_review.md:section_empty_or_missing:decision")
        return blockers
    if not has_approve_decision(text):
        blockers.append("final_review.md:decision_not_approve")
    return blockers
