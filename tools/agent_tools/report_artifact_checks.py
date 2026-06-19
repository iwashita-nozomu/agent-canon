#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides report artifact checks agent workflow automation.
# upstream design ../README.md shared automation index
# upstream implementation ./mid_task_user_input_policy.py defines mid-task user input evidence policy
# @dependency-end

"""Shared checks for run-bundle artifact completeness."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from mid_task_user_input_policy import (
    MID_TASK_CLASSIFICATION_ACTIONS,
    MID_TASK_CLASSIFICATION_SCOPE_STATUS,
    MID_TASK_EVIDENCE_FIELDS,
    MID_TASK_REQUIRED_WAVE_FIELDS,
    MID_TASK_REUSE_MARKERS,
    MID_TASK_SPAWN_AUTHORITY,
    MID_TASK_SPAWNED_ROLES_REQUIRED_CLASSIFICATIONS,
    MID_TASK_TARGET_REQUIRED_CLASSIFICATIONS,
    has_reuse_marker,
    is_empty_policy_value,
)

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
    "role_instances",
    "skipped_roles",
    "allowed_paths",
    "do_not_read",
    "write_scope",
    "validation_route",
    "review_gate",
    "handoff_artifacts",
    "status",
)
WAVE_COMPARISON_FIELDS = (
    ("Spawn Authority", "spawn_authority"),
    ("Trigger", "trigger"),
    ("Budget Before", "budget_before"),
    ("Budget After", "budget_after"),
    ("Runtime Max Threads", "runtime_max_threads"),
    ("Runtime Max Depth", "runtime_max_depth"),
    ("Role Instances", "role_instances"),
    ("Allowed Paths", "allowed_paths"),
    ("Do Not Read", "do_not_read"),
    ("Write Scope", "write_scope"),
    ("Validation Route", "validation_route"),
    ("Review Gate", "review_gate"),
    ("Handoff Artifacts", "handoff_artifacts"),
    ("Status", "status"),
)
MECHANICALLY_REGENERATED_REPORT_ROOTS = (
    PurePosixPath("reports/agent-eval-runs"),
    PurePosixPath("reports/agent-improvement-guide"),
    PurePosixPath("reports/agent-runtime-dashboard"),
    PurePosixPath("reports/dependency-review"),
    PurePosixPath("reports/hooks"),
    PurePosixPath("reports/.cache"),
)
MECHANICALLY_REGENERATED_REPORT_FILE_PATTERNS = (
    re.compile(r"^reports/[^/]+\.(?:json|patch|txt)$"),
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


def _normalized_git_path(path: str) -> str:
    """Return a POSIX-style Git path for classification."""
    return path.replace("\\", "/").strip("/")


def _is_relative_to(path: PurePosixPath, root: PurePosixPath) -> bool:
    """Return whether a POSIX path is equal to or nested under root."""
    return path == root or path.is_relative_to(root)


def is_mechanically_regenerated_report_path(path: str) -> bool:
    """Return whether one report path is a known mechanically regenerated output."""
    normalized = _normalized_git_path(path)
    candidate = PurePosixPath(normalized)
    if any(
        _is_relative_to(candidate, root)
        for root in MECHANICALLY_REGENERATED_REPORT_ROOTS
    ):
        return True
    return any(
        pattern.match(normalized)
        for pattern in MECHANICALLY_REGENERATED_REPORT_FILE_PATTERNS
    )


def generated_report_artifact_blockers(workspace: Path) -> list[str]:
    """Return regenerated report outputs that should not remain in the tree."""
    report_paths = {
        path: "tracked"
        for path in _git_report_paths(workspace, ())
        if is_mechanically_regenerated_report_path(path)
    }
    for path in _git_report_paths(
        workspace,
        ("--others", "--exclude-standard"),
    ):
        if is_mechanically_regenerated_report_path(path):
            report_paths.setdefault(path, "untracked")
    for path in _git_report_paths(
        workspace,
        ("--others", "--ignored", "--exclude-standard"),
    ):
        if is_mechanically_regenerated_report_path(path):
            report_paths.setdefault(path, "ignored")
    return [
        f"generated_report_artifact_{state}_left_in_tree:{path}"
        for path, state in sorted(report_paths.items())
    ]


def join_artifact_blockers(blockers: Sequence[str]) -> str:
    """Render blockers for compact shell output."""
    return "|".join(blockers) if blockers else "none"


def report_artifact_placement_blockers(workspace: Path, report_dir: Path) -> list[str]:
    """Return generated report artifacts outside the active run bundle.

    Tracked durable reports are allowed. Tracked generated report roots and tracked
    agent run bundles outside the current run are blockers. Untracked generated
    report files are allowed only under the current run directory because runtime
    archive tooling collects one active run bundle at closeout. Ignored non-
    generated report paths are local cache and do not block closeout.
    """
    if not report_dir.resolve().is_relative_to(workspace.resolve()):
        return []
    report_paths = {}
    for path in _git_report_paths(workspace, ()):
        normalized = _normalized_git_path(path)
        if normalized.startswith("reports/agents/") or is_mechanically_regenerated_report_path(path):
            report_paths[path] = "tracked"
    for path in _git_report_paths(
        workspace,
        ("--others", "--exclude-standard"),
    ):
        report_paths.setdefault(path, "untracked")
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
        if state == "ignored" and not is_mechanically_regenerated_report_path(path):
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
        if not in_section or not stripped.startswith("- wave_event="):
            continue
        rows.append(token_fields(stripped))
    return rows


def _split_csv_field(value: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in value.split(",")
        if item.strip() and item.strip().lower() != "none"
    )


def _candidate_evidence_paths(
    value: str,
    report_dir: Path | None,
    workspace: Path | None,
    evidence_field: str,
) -> tuple[Path, ...]:
    """Return policy-allowed filesystem paths for one evidence token."""
    if is_empty_policy_value(value):
        return ()
    path = Path(value)
    raw_candidates: list[Path] = []
    if path.is_absolute():
        raw_candidates.append(path)
    else:
        if workspace is not None:
            raw_candidates.append(workspace / path)
        if report_dir is not None:
            raw_candidates.append(report_dir / path)
            raw_candidates.append(report_dir.parent / path)
            if len(path.parts) == 1:
                raw_candidates.append(report_dir.parent / path.name)
    if report_dir is None:
        return ()
    current_run_root = report_dir.resolve()
    report_root = report_dir.parent.resolve()
    candidates: list[Path] = []
    for candidate in raw_candidates:
        resolved = candidate.resolve()
        if evidence_field == "fresh_wave_evidence":
            if resolved.is_relative_to(current_run_root):
                candidates.append(candidate)
        elif (
            evidence_field == "fresh_run_bundle"
            and resolved.parent == report_root
            and resolved != current_run_root
        ):
            candidates.append(candidate)
    return tuple(dict.fromkeys(candidates))


def _raw_evidence_paths(
    value: str,
    report_dir: Path | None,
    workspace: Path | None,
) -> tuple[Path, ...]:
    """Return unfiltered path interpretations for diagnostics."""
    if is_empty_policy_value(value):
        return ()
    path = Path(value)
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        if workspace is not None:
            candidates.append(workspace / path)
        if report_dir is not None:
            candidates.append(report_dir / path)
            candidates.append(report_dir.parent / path)
    if report_dir is not None:
        if len(path.parts) == 1:
            candidates.append(report_dir.parent / path.name)
    return tuple(dict.fromkeys(candidates))


def _evidence_path_exists(
    value: str,
    report_dir: Path | None,
    workspace: Path | None,
    *,
    require_dir: bool = False,
    evidence_field: str,
) -> bool:
    """Return whether one evidence token points at an existing artifact."""
    candidates = _candidate_evidence_paths(value, report_dir, workspace, evidence_field)
    if not candidates:
        return False
    if require_dir:
        return any(candidate.is_dir() for candidate in candidates)
    return any(candidate.exists() for candidate in candidates)


def _evidence_path_outside_scope(
    value: str,
    report_dir: Path | None,
    workspace: Path | None,
    evidence_field: str,
) -> bool:
    """Return whether evidence exists but outside the allowed run-artifact scope."""
    raw_existing = any(
        candidate.exists()
        for candidate in _raw_evidence_paths(value, report_dir, workspace)
    )
    if not raw_existing:
        return False
    return not _candidate_evidence_paths(value, report_dir, workspace, evidence_field)


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


def _actual_wave_field_blockers(
    wave_id: str,
    actual: dict[str, str],
    report_dir: Path | None = None,
    workspace: Path | None = None,
) -> list[str]:
    blockers = [
        f"workflow_monitoring.md:actual_wave_field_missing:{wave_id}:{field}"
        for field in REQUIRED_ACTUAL_WAVE_FIELDS
        if actual.get(field, "").strip() in {"", "missing"}
    ]
    if actual.get("event_kind") == "mid_task_user_input":
        blockers.extend(
            _mid_task_user_input_blockers(wave_id, actual, report_dir, workspace)
        )
    return blockers


def _mid_task_user_input_blockers(
    wave_id: str,
    actual: dict[str, str],
    report_dir: Path | None = None,
    workspace: Path | None = None,
) -> list[str]:
    """Return blockers for mid-task user input wave checkpoints."""
    blockers = [
        f"workflow_monitoring.md:mid_task_user_input_field_missing:{wave_id}:{field}"
        for field in MID_TASK_REQUIRED_WAVE_FIELDS
        if actual.get(field, "").strip().lower() in {"", "missing"}
    ]
    if is_empty_policy_value(actual.get("updated_packet", "")):
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
    expected_spawn_authority = MID_TASK_SPAWN_AUTHORITY[classification]
    if actual.get("spawn_authority", "").strip() != expected_spawn_authority:
        blockers.append(
            "workflow_monitoring.md:mid_task_user_input_invalid_spawn_authority:"
            f"{wave_id}:expected={expected_spawn_authority}"
        )
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
    if classification in MID_TASK_TARGET_REQUIRED_CLASSIFICATIONS and is_empty_policy_value(
        target_agents
    ):
        blockers.append(
            f"workflow_monitoring.md:mid_task_user_input_field_missing:{wave_id}:target_agents"
        )
    spawned_roles = actual.get("spawned_roles", "").strip()
    if classification in MID_TASK_SPAWNED_ROLES_REQUIRED_CLASSIFICATIONS:
        if is_empty_policy_value(spawned_roles):
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_field_missing:"
                f"{wave_id}:spawned_roles"
            )
    if classification in MID_TASK_EVIDENCE_FIELDS:
        skipped_roles = actual.get("skipped_roles", "")
        if has_reuse_marker(skipped_roles):
            markers = ",".join(MID_TASK_REUSE_MARKERS)
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_reused_agent_forbidden:"
                f"{wave_id}:{markers}"
            )
    evidence_field = MID_TASK_EVIDENCE_FIELDS.get(classification)
    if evidence_field:
        evidence_value = actual.get(evidence_field, "").strip()
        if is_empty_policy_value(evidence_value):
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_field_missing:"
                f"{wave_id}:{evidence_field}"
            )
        elif _evidence_path_outside_scope(
            evidence_value,
            report_dir,
            workspace,
            evidence_field,
        ):
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_evidence_outside_scope:"
                f"{wave_id}:{evidence_field}:{evidence_value}"
            )
        elif not _evidence_path_exists(
            evidence_value,
            report_dir,
            workspace,
            require_dir=evidence_field == "fresh_run_bundle",
            evidence_field=evidence_field,
        ):
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_evidence_missing:"
                f"{wave_id}:{evidence_field}:{evidence_value}"
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
    if _split_csv_field(planned.get("Role Instances", "")) != _split_csv_field(
        actual.get("role_instances", "")
    ):
        blockers.append(f"workflow_monitoring.md:actual_wave_mismatch:{wave_id}:role_instances")
    return blockers


def wave_reconciliation_blockers(
    schedule_text: str,
    workflow_monitoring_text: str,
    lifecycle_status: dict[str, str],
    report_dir: Path | None = None,
    workspace: Path | None = None,
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
        blockers.extend(
            _actual_wave_field_blockers(wave_id, actual, report_dir, workspace)
        )
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
