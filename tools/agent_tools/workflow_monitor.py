#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Appends workflow monitoring evidence to run bundles.
# upstream design ../../agents/templates/workflow_monitoring.md defines monitor sections
# upstream implementation ./mid_task_user_input_policy.py defines mid-task user input evidence policy
# downstream implementation ../../tests/agent_tools/test_workflow_monitor.py tests it
# @dependency-end
"""Append machine-readable workflow monitoring evidence to one run bundle."""

from __future__ import annotations

import argparse
import fcntl
import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TextIO, cast

from agent_team import resolve_report_root, schedule_wave_row
from mid_task_user_input_policy import (
    MID_TASK_CLASSIFICATION_ACTIONS,
    MID_TASK_CLASSIFICATION_SCOPE_STATUS,
    MID_TASK_EVIDENCE_FIELDS,
    MID_TASK_REQUIRED_KEYS,
    MID_TASK_REUSE_MARKERS,
    MID_TASK_SPAWN_AUTHORITY,
    MID_TASK_SPAWNED_ROLES_REQUIRED_CLASSIFICATIONS,
    MID_TASK_TARGET_REQUIRED_CLASSIFICATIONS,
    has_reuse_marker,
    is_empty_policy_value,
)

DECISION_KEYS = (
    "skill_improvement_decision",
    "config_improvement_decision",
    "workflow_improvement_decision",
    "memory_learning_decision",
)
DECISION_VALUES = {"applied", "recorded", "not_applicable", "pending"}
TOOL_WARNING_REQUIRED_KEYS = (
    "warning_id",
    "source_tool",
    "severity",
    "status",
    "message",
    "repair_command",
)
TOOL_WARNING_STATUS_VALUES = {
    "open",
    "resolved",
    "accepted_with_reason",
    "deferred_with_issue",
    "not_applicable",
}
TOOL_WARNING_LEDGER_STATUS_VALUES = {"pending", "open", "resolved", "none"}
SUBAGENT_WAVE_REQUIRED_KEYS = (
    "wave_id",
    "parent_or_delegate",
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
SUBAGENT_WAVE_EVENT_KINDS = {
    "spawned",
    "delegated_child_spawn",
    "skipped",
    "authority_blocker",
}
SUBAGENT_WAVE_EMPTY_OK_STATUSES = {
    "blocked",
    "blocked_authority_required",
    "skipped",
    "not_applicable",
}
SUBAGENT_WAVE_DELEGATED_EVENTS = {"delegated_child_spawn"}
VALIDATION_FAILURE_TRIAGE_TRIGGER = "validation_failure_requires_parallel_triage"
VALIDATION_FAILURE_READ_ONLY_WRITE_SCOPES = {
    "none",
    "read-only",
    "read_only",
    "read_only_triage",
    "read_only_until_cause_identified",
}
VALIDATION_FAILURE_REPAIR_REQUIRED_KEYS = (
    "failing_contract",
    "observation_level",
    "cause_classification",
    "intent_preservation",
    "evidence",
)
RUNTIME_PROFILE_INVENTORY_PATH = (
    Path(__file__).resolve().parents[2]
    / "documents"
    / "runtime-profiles-and-check-matrix.json"
)


def validation_failure_taxonomy_values(field: str) -> frozenset[str]:
    """Load one validation-failure slug set from the runtime profile inventory."""
    raw_data = json.loads(RUNTIME_PROFILE_INVENTORY_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw_data, dict):
        raise ValueError("runtime profile inventory must be a JSON object")
    data = cast(dict[str, object], raw_data)
    raw_response = data.get("validation_failure_response")
    if not isinstance(raw_response, dict):
        raise ValueError("runtime profile inventory missing validation_failure_response")
    response = cast(dict[str, object], raw_response)
    raw_values = response.get(field)
    if not isinstance(raw_values, list) or not raw_values:
        raise ValueError(
            f"runtime profile inventory missing validation_failure_response.{field}"
        )
    values = cast(list[object], raw_values)
    slugs: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"validation_failure_response.{field} must contain strings"
            )
        slugs.append(value)
    return frozenset(slugs)


VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES = validation_failure_taxonomy_values(
    "intent_preservation"
)
VALIDATION_FAILURE_CAUSE_CLASSIFICATION_VALUES = validation_failure_taxonomy_values(
    "cause_classes"
)
STANDARD_CLOSEOUT_BEHAVIOR_EVENTS = (
    "skill_invocation=$agent-orchestration status=observed",
    "subagent_lifecycle=closed subagents_closed=yes fresh_subagents_required=true",
    (
        "tool_call=run_repo_dependency_review.sh repo_dependency_review=pass "
        "scope=repo-wide"
    ),
    "tool_call=make ci static_analysis=pass scope=repo-wide",
    "tool_call=pyright code_checker=pass checker=pyright scope=repo-wide",
    "tool_call=ruff code_checker=pass checker=ruff scope=repo-wide",
    (
        "tool_call=oop-readability-check code_checker=pass "
        "checker=oop-readability scope=changed-paths"
    ),
    "tool_call=check_convention_compliance.py CONVENTION_COMPLIANCE=pass",
    "static_analysis_feedback=recorded target=review-backlog-scan",
    (
        "hook_tool_feedback=reviewed parent_protocol_update=not_required "
        "subagent_protocol_update=not_required "
        "protocol_feedback_reason=standard-closeout-no-new-protocol-change"
    ),
    (
        "pre_edit_rejection_prediction=reviewed "
        "predicted_tool_rejection_gates=recorded"
    ),
    "execution_path_comparison_not_required reason=single-active-route",
    "token_efficiency_not_required reason=no-comparable-session",
    "prompt_eval_required action=run_evaluate_skill_workflow_prompts_with_accumulate",
    "runtime_feedback_not_observed",
    "review_decision=approve review_findings_integrated=yes",
    "diff_check_agent_decision=approve diff_check_agent_complete=yes",
)
STANDARD_CLOSEOUT_SIGNALS = (
    "repo_dependency_review=pass scope=repo-wide",
    "web_research_not_required reason=not-needed-for-closeout-token-recording",
    "review_status=approve",
    "validation_status=pass",
    "drift_risk=checked",
)


def empty_decisions() -> dict[str, str]:
    """Return an empty decision mapping."""
    return {}


@dataclass(frozen=True)
class MonitoringEntries:
    """Structured inputs for one workflow monitoring append."""

    signals: tuple[str, ...] = ()
    behavior_events: tuple[str, ...] = ()
    runtime_feedback: tuple[str, ...] = ()
    tool_warnings: tuple[str, ...] = ()
    tool_warning_status: str = ""
    mid_task_user_inputs: tuple[str, ...] = ()
    subagent_waves: tuple[str, ...] = ()
    interventions: tuple[str, ...] = ()
    decisions: Mapping[str, str] = field(default_factory=empty_decisions)
    timestamp: str = ""


EMPTY_MONITORING_ENTRIES = MonitoringEntries()
MONITORING_LEGACY_KEYS = {
    "signals",
    "behavior_events",
    "runtime_feedback",
    "tool_warnings",
    "tool_warning_status",
    "mid_task_user_inputs",
    "subagent_waves",
    "interventions",
    "decisions",
    "timestamp",
}


@contextmanager
def locked_monitoring_artifact(path: Path) -> Iterator[TextIO]:
    """Hold an exclusive lock while updating the monitoring artifact."""
    path.touch(exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            yield handle
        finally:
            handle.flush()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def locked_existing_artifact(path: Path) -> Iterator[TextIO]:
    """Hold an exclusive lock while updating an existing artifact."""
    if not path.is_file():
        raise ValueError(f"missing required artifact: {path}")
    with path.open("r+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            yield handle
        finally:
            handle.flush()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Append signals, interventions, and improvement decisions."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--report-dir", help="Explicit run bundle directory.")
    target.add_argument("--run-id", help="Run id under reports/agents/.")
    parser.add_argument(
        "--report-root",
        help="Optional report root. Defaults to <workspace-root>/reports/agents.",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used with --run-id and relative report roots.",
    )
    add_monitoring_entry_arguments(parser)
    add_tool_warning_arguments(parser)
    add_mid_task_user_input_argument(parser)
    add_subagent_wave_argument(parser)
    add_closeout_decision_arguments(parser)
    return parser


def add_monitoring_entry_arguments(parser: argparse.ArgumentParser) -> None:
    """Add common monitoring entry arguments."""
    parser.add_argument(
        "--signal",
        action="append",
        default=[],
        help="Signal to append.",
    )
    parser.add_argument(
        "--intervention",
        action="append",
        default=[],
        help="Intervention to append.",
    )
    parser.add_argument(
        "--behavior-event",
        action="append",
        default=[],
        help=(
            "Agent behavior event to append, such as skill invocation, subagent routing, "
            "tool call, review decision, prompt eval result, or feedback action."
        ),
    )
    parser.add_argument(
        "--runtime-feedback",
        action="append",
        default=[],
        help=(
            "User- or reviewer-observed runtime feedback as key=value tokens, for "
            "example 'source=user target=.agents/skills/foo/SKILL.md action=prompt_repair'."
        ),
    )


def add_tool_warning_arguments(parser: argparse.ArgumentParser) -> None:
    """Add tool warning ledger arguments."""
    parser.add_argument(
        "--tool-warning",
        action="append",
        default=[],
        help=(
            "Observed non-blocking tool, hook, checker, or wrapper warning as "
            "key=value tokens. Required keys: warning_id, source_tool, severity, "
            "status, message, repair_command. Status values: open, resolved, "
            "accepted_with_reason, deferred_with_issue, not_applicable."
        ),
    )
    parser.add_argument(
        "--tool-warning-status",
        choices=sorted(TOOL_WARNING_LEDGER_STATUS_VALUES),
        default="",
        help=(
            "Set the aggregate Tool Warnings ledger status. Use none when no "
            "tool warnings were observed, open while any warning is unresolved, "
            "and resolved only after all warning_ids are closed."
        ),
    )


def add_mid_task_user_input_argument(parser: argparse.ArgumentParser) -> None:
    """Add the mid-task user input checkpoint argument."""
    parser.add_argument(
        "--mid-task-user-input",
        action="append",
        default=[],
        help=(
            "Checkpoint a user instruction added during an active multi-agent run. "
            "Provide key=value tokens including wave_id, input_classification "
            "(same_active_task_delta, scope_or_contract_change, new_task), "
            "updated_packet, target_agents, scope_status, budget_before, "
            "budget_after, runtime_max_threads, runtime_max_depth, allowed_paths, "
            "do_not_read, write_scope, validation_route, review_gate, and "
            "handoff_artifacts. scope_or_contract_change also requires "
            "spawned_roles, role_instances, and fresh_wave_evidence; new_task also requires "
            "fresh_run_bundle. The command appends matching schedule.md Agent "
            "Wave Ledger and workflow_monitoring.md Actual Wave Events rows."
        ),
    )


def add_subagent_wave_argument(parser: argparse.ArgumentParser) -> None:
    """Add the structured subagent wave recorder argument."""
    parser.add_argument(
        "--subagent-wave",
        action="append",
        default=[],
        help=(
            "Record an actual parent or delegated subagent wave as key=value tokens. "
            "Required keys: wave_id, parent_or_delegate, spawn_authority, trigger, "
            "budget_before, budget_after, runtime_max_threads, runtime_max_depth, "
            "spawned_roles, role_instances, skipped_roles, allowed_paths, do_not_read, "
            "write_scope, validation_route, review_gate, handoff_artifacts, and status. "
            "Optional event_kind defaults to spawned; delegated child waves must include "
            "remaining_spawn_budget."
        ),
    )


def add_closeout_decision_arguments(parser: argparse.ArgumentParser) -> None:
    """Add closeout preset and improvement decision arguments."""
    parser.add_argument(
        "--closeout-token-preset",
        action="store_true",
        help=(
            "Append the standard closeout behavior tokens consumed by "
            "evaluate_agent_run.py. Use only after the corresponding evidence "
            "has already been verified in the run bundle."
        ),
    )
    parser.add_argument(
        "--decision",
        action="append",
        default=[],
        help=(
            "Improvement decision as key=value. Keys are "
            "skill_improvement_decision, config_improvement_decision, "
            "workflow_improvement_decision, memory_learning_decision."
        ),
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help="Optional timestamp prefix. Defaults to current local time.",
    )


def default_monitoring_text(report_dir: Path) -> str:
    """Return a minimal monitoring artifact when one is missing."""
    return "\n".join(
        [
            "# Workflow Monitoring",
            "<!--",
            "@dependency-start",
            "responsibility Records workflow monitoring for this run bundle.",
            "upstream design ../../../agents/templates/"
            "workflow_monitoring.md template",
            "@dependency-end",
            "-->",
            "",
            f"- Run ID: {report_dir.name}",
            "",
            "## Signals",
            "",
            "## Behavior Events",
            "",
            "## Actual Wave Events",
            "",
            "## Tool Warnings",
            "",
            "- tool_warnings_status: pending",
            "",
            "## Interventions",
            "",
            "## Improvement Decisions",
            "",
            "- skill_improvement_decision: pending",
            "- config_improvement_decision: pending",
            "- workflow_improvement_decision: pending",
            "- memory_learning_decision: pending",
            "",
        ]
    )


def resolve_report_dir(args: argparse.Namespace) -> Path:
    """Resolve the target run bundle directory."""
    workspace_root = Path(str(args.workspace_root)).resolve()
    if args.report_dir:
        return Path(str(args.report_dir)).resolve()
    return (
        resolve_report_root(args.report_root, workspace_root) / str(args.run_id)
    ).resolve()


def timestamp_prefix(timestamp: str) -> str:
    """Return a stable timestamp prefix for an appended line."""
    value = timestamp.strip() or datetime.now().strftime("%Y-%m-%d %H:%M JST")
    return f"`{value}` "


def normalize_entry(entry: str, timestamp: str) -> str:
    """Render one markdown list item."""
    stripped = entry.strip()
    if not stripped:
        raise ValueError("workflow monitoring entries must not be empty")
    return f"- {timestamp_prefix(timestamp)}{stripped}"


def normalize_runtime_feedback(entry: str) -> str:
    """Render one runtime feedback event with stable machine-readable tokens."""
    stripped = entry.strip()
    if not stripped:
        raise ValueError("runtime feedback entries must not be empty")
    if "target=" not in stripped or "action=" not in stripped:
        raise ValueError("runtime feedback must include target=... and action=...")
    return f"runtime_feedback=observed {stripped}"


def parse_token_fields(entry: str) -> dict[str, str]:
    """Parse whitespace-separated key=value tokens."""
    data: dict[str, str] = {}
    for token in entry.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def normalize_subagent_wave(entry: str) -> dict[str, str]:
    """Normalize one actual parent or delegated subagent wave."""
    stripped = entry.strip()
    if not stripped:
        raise ValueError("subagent wave entries must not be empty")
    fields = parse_token_fields(stripped)
    missing = [
        key
        for key in SUBAGENT_WAVE_REQUIRED_KEYS
        if fields.get(key, "").strip().lower() in {"", "missing"}
    ]
    if missing:
        raise ValueError("subagent wave must include required keys: " + ",".join(missing))
    normalized = dict(fields)
    normalized.setdefault("event_kind", "spawned")
    normalized.setdefault("delegated_policy_ref", "team_manifest.yaml#run.delegated_spawn_policy")
    event_kind = normalized["event_kind"]
    if event_kind not in SUBAGENT_WAVE_EVENT_KINDS:
        raise ValueError(
            "subagent wave event_kind must be one of: "
            + ",".join(sorted(SUBAGENT_WAVE_EVENT_KINDS))
        )
    runtime_max_depth = normalized["runtime_max_depth"]
    if not runtime_max_depth.isdigit() or int(runtime_max_depth) < 1:
        raise ValueError("subagent wave runtime_max_depth must be an integer >= 1")
    status = normalized["status"]
    if status not in SUBAGENT_WAVE_EMPTY_OK_STATUSES:
        for key in ("spawned_roles", "role_instances"):
            if is_empty_policy_value(normalized[key]):
                raise ValueError(f"subagent wave {key} must identify actual roles")
    is_delegated = normalized["parent_or_delegate"] != "parent" or (
        event_kind in SUBAGENT_WAVE_DELEGATED_EVENTS
    )
    if is_delegated and is_empty_policy_value(
        normalized.get("remaining_spawn_budget", "")
    ):
        raise ValueError(
            "delegated subagent wave must include remaining_spawn_budget"
        )
    validate_validation_failure_wave(normalized)
    return normalized


def validate_validation_failure_wave(row: Mapping[str, str]) -> None:
    """Validate validation-failure triage versus repair wave evidence."""
    if row.get("trigger") != VALIDATION_FAILURE_TRIAGE_TRIGGER:
        return
    write_scope = row.get("write_scope", "")
    missing = [
        key
        for key in VALIDATION_FAILURE_REPAIR_REQUIRED_KEYS
        if is_empty_policy_value(row.get(key, ""))
    ]
    if missing and write_scope not in VALIDATION_FAILURE_READ_ONLY_WRITE_SCOPES:
        raise ValueError(
            "validation failure repair wave must remain read-only before cause "
            "identification or include required keys: " + ",".join(missing)
        )
    intent_preservation = row.get("intent_preservation", "")
    if intent_preservation and (
        intent_preservation not in VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES
    ):
        raise ValueError(
            "validation failure intent_preservation must be one of: "
            + ",".join(sorted(VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES))
        )
    cause_classification = row.get("cause_classification", "")
    if cause_classification and (
        cause_classification not in VALIDATION_FAILURE_CAUSE_CLASSIFICATION_VALUES
    ):
        raise ValueError(
            "validation failure cause_classification must be one of: "
            + ",".join(sorted(VALIDATION_FAILURE_CAUSE_CLASSIFICATION_VALUES))
        )


def validation_failure_fields(row: Mapping[str, str]) -> list[tuple[str, str]]:
    """Return optional validation-failure evidence fields for output rows."""
    if row.get("trigger") != VALIDATION_FAILURE_TRIAGE_TRIGGER:
        return []
    return [
        (key, row[key])
        for key in VALIDATION_FAILURE_REPAIR_REQUIRED_KEYS
        if not is_empty_policy_value(row.get(key, ""))
    ]


def subagent_wave_actual_event(row: dict[str, str]) -> str:
    """Return an Actual Wave Events token row for a subagent wave."""
    fields = [
        ("wave_event", "recorded"),
        ("wave_id", row["wave_id"]),
        ("event_kind", row["event_kind"]),
        ("spawn_authority", row["spawn_authority"]),
        ("trigger", row["trigger"]),
        ("budget_before", row["budget_before"]),
        ("budget_after", row["budget_after"]),
        ("runtime_max_threads", row["runtime_max_threads"]),
        ("runtime_max_depth", row["runtime_max_depth"]),
        ("spawned_roles", row["spawned_roles"]),
        ("role_instances", row["role_instances"]),
        ("skipped_roles", row["skipped_roles"]),
        ("allowed_paths", row["allowed_paths"]),
        ("do_not_read", row["do_not_read"]),
        ("write_scope", row["write_scope"]),
        ("validation_route", row["validation_route"]),
        ("review_gate", row["review_gate"]),
        ("handoff_artifacts", row["handoff_artifacts"]),
        ("status", row["status"]),
        ("delegated_policy_ref", row["delegated_policy_ref"]),
    ]
    if "remaining_spawn_budget" in row:
        fields.append(("remaining_spawn_budget", row["remaining_spawn_budget"]))
    fields.extend(validation_failure_fields(row))
    return " ".join(f"{key}={value}" for key, value in fields)


def subagent_wave_behavior_event(row: dict[str, str]) -> str:
    """Return a Behavior Events token row for a subagent wave."""
    fields = [
        ("subagent_wave", "recorded"),
        ("wave_id", row["wave_id"]),
        ("event_kind", row["event_kind"]),
        ("spawned_roles", row["spawned_roles"]),
        ("role_instances", row["role_instances"]),
        ("skipped_roles", row["skipped_roles"]),
        ("budget_before", row["budget_before"]),
        ("budget_after", row["budget_after"]),
        ("status", row["status"]),
    ]
    if "remaining_spawn_budget" in row:
        fields.append(("remaining_spawn_budget", row["remaining_spawn_budget"]))
    fields.extend(validation_failure_fields(row))
    return " ".join(f"{key}={value}" for key, value in fields)


def parse_mid_task_fields(entry: str) -> dict[str, str]:
    """Parse one mid-task user instruction checkpoint."""
    if not entry.strip():
        raise ValueError("mid-task user input entries must not be empty")
    fields = parse_token_fields(entry.strip())
    missing = [
        key
        for key in MID_TASK_REQUIRED_KEYS
        if fields.get(key, "").strip().lower() in {"", "missing"}
    ]
    if missing:
        raise ValueError(
            "mid-task user input must include required keys: " + ",".join(missing)
        )
    return fields


def mid_task_classification(fields: Mapping[str, str]) -> str:
    """Return and validate one mid-task input classification."""
    classification = fields["input_classification"]
    if classification not in MID_TASK_CLASSIFICATION_ACTIONS:
        raise ValueError(
            "mid-task input_classification must be one of: "
            + ",".join(sorted(MID_TASK_CLASSIFICATION_ACTIONS))
        )
    if is_empty_policy_value(fields["updated_packet"]):
        raise ValueError("mid-task user input updated_packet must not be none")
    return classification


def validate_mid_task_route_fields(
    fields: Mapping[str, str],
    classification: str,
) -> tuple[str, str]:
    """Validate route fields that are derived from the classification."""
    expected_action = MID_TASK_CLASSIFICATION_ACTIONS[classification]
    action = fields.get("redispatch_action", expected_action)
    if action != expected_action:
        raise ValueError(
            f"mid-task redispatch_action for {classification} must be {expected_action}"
        )
    expected_scope_status = MID_TASK_CLASSIFICATION_SCOPE_STATUS[classification]
    if fields["scope_status"] != expected_scope_status:
        raise ValueError(
            f"mid-task scope_status for {classification} must be {expected_scope_status}"
        )
    expected_spawn_authority = MID_TASK_SPAWN_AUTHORITY[classification]
    spawn_authority = fields.get("spawn_authority", expected_spawn_authority)
    if spawn_authority != expected_spawn_authority:
        raise ValueError(
            f"mid-task spawn_authority for {classification} must be "
            f"{expected_spawn_authority}"
        )
    return expected_action, expected_spawn_authority


def validate_mid_task_target_and_evidence(
    fields: Mapping[str, str],
    classification: str,
) -> None:
    """Validate classification-specific target and evidence fields."""
    if classification in MID_TASK_TARGET_REQUIRED_CLASSIFICATIONS and is_empty_policy_value(
        fields.get("target_agents", "")
    ):
        raise ValueError(
            f"mid-task target_agents for {classification} must identify an agent or role"
        )
    evidence_field = MID_TASK_EVIDENCE_FIELDS.get(classification)
    if evidence_field and is_empty_policy_value(fields.get(evidence_field, "")):
        raise ValueError(
            f"mid-task {evidence_field} for {classification} must identify evidence"
        )
    if classification in MID_TASK_SPAWNED_ROLES_REQUIRED_CLASSIFICATIONS and (
        "spawned_roles" not in fields
        or is_empty_policy_value(fields.get("spawned_roles", ""))
    ):
        raise ValueError(
            f"mid-task spawned_roles for {classification} must identify fresh roles"
        )
    if classification in MID_TASK_SPAWNED_ROLES_REQUIRED_CLASSIFICATIONS and (
        "role_instances" not in fields
        or is_empty_policy_value(fields.get("role_instances", ""))
    ):
        raise ValueError(
            f"mid-task role_instances for {classification} must identify role_type+instance_id"
        )
    if classification in MID_TASK_EVIDENCE_FIELDS:
        skipped_roles = fields.get("skipped_roles", "")
        if has_reuse_marker(skipped_roles):
            markers = ",".join(MID_TASK_REUSE_MARKERS)
            raise ValueError(
                f"mid-task {classification} must not include reused-agent marker: "
                f"{markers}"
            )


def mid_task_defaults(
    fields: Mapping[str, str],
    classification: str,
    expected_action: str,
    expected_spawn_authority: str,
) -> dict[str, str]:
    """Return normalized mid-task fields with defaulted ledger values."""
    normalized = dict(fields)
    normalized.setdefault("parent_or_delegate", "parent")
    normalized.setdefault("trigger", "mid_task_user_input")
    normalized.setdefault("spawn_authority", expected_spawn_authority)
    normalized.setdefault("redispatch_action", expected_action)
    normalized.setdefault(
        "lifecycle_policy_ref",
        "team_manifest.yaml#run.subagent_lifecycle_policy",
    )
    normalized.setdefault(
        "delegated_policy_ref",
        "team_manifest.yaml#run.subagent_lifecycle_policy",
    )
    normalized.setdefault("status", "checkpointed")
    if "spawned_roles" not in normalized:
        normalized["spawned_roles"] = "none"
    if "role_instances" not in normalized:
        normalized["role_instances"] = "none"
    if "skipped_roles" not in normalized:
        normalized["skipped_roles"] = (
            f"{normalized['target_agents']}:reused_run_local_send_input"
            if classification == "same_active_task_delta"
            else "none"
        )
    return normalized


def normalize_mid_task_user_input(entry: str) -> dict[str, str]:
    """Normalize one mid-task user instruction checkpoint."""
    fields = parse_mid_task_fields(entry)
    classification = mid_task_classification(fields)
    expected_action, expected_spawn_authority = validate_mid_task_route_fields(
        fields,
        classification,
    )
    validate_mid_task_target_and_evidence(fields, classification)
    return mid_task_defaults(
        fields,
        classification,
        expected_action,
        expected_spawn_authority,
    )


def mid_task_actual_wave_event(row: dict[str, str]) -> str:
    """Return an Actual Wave Events token row for a mid-task checkpoint."""
    fields = [
        ("wave_event", "recorded"),
        ("wave_id", row["wave_id"]),
        ("event_kind", "mid_task_user_input"),
        ("spawn_authority", row["spawn_authority"]),
        ("trigger", row["trigger"]),
        ("budget_before", row["budget_before"]),
        ("budget_after", row["budget_after"]),
        ("runtime_max_threads", row["runtime_max_threads"]),
        ("runtime_max_depth", row["runtime_max_depth"]),
        ("spawned_roles", row["spawned_roles"]),
        ("role_instances", row["role_instances"]),
        ("skipped_roles", row["skipped_roles"]),
        ("allowed_paths", row["allowed_paths"]),
        ("do_not_read", row["do_not_read"]),
        ("write_scope", row["write_scope"]),
        ("validation_route", row["validation_route"]),
        ("review_gate", row["review_gate"]),
        ("handoff_artifacts", row["handoff_artifacts"]),
        ("status", row["status"]),
        ("input_classification", row["input_classification"]),
        ("updated_packet", row["updated_packet"]),
        ("redispatch_action", row["redispatch_action"]),
        ("target_agents", row["target_agents"]),
        ("scope_status", row["scope_status"]),
        ("lifecycle_policy_ref", row["lifecycle_policy_ref"]),
    ]
    evidence_field = MID_TASK_EVIDENCE_FIELDS.get(row["input_classification"])
    if evidence_field:
        fields.append((evidence_field, row[evidence_field]))
    return " ".join(f"{key}={value}" for key, value in fields)


def mid_task_behavior_event(row: dict[str, str]) -> str:
    """Return a Behavior Events token row for a mid-task user checkpoint."""
    fields = [
        ("mid_task_user_input", "checkpointed"),
        ("wave_id", row["wave_id"]),
        ("input_classification", row["input_classification"]),
        ("updated_packet", row["updated_packet"]),
        ("redispatch_action", row["redispatch_action"]),
        ("target_agents", row["target_agents"]),
        ("scope_status", row["scope_status"]),
        ("lifecycle_policy_ref", row["lifecycle_policy_ref"]),
    ]
    evidence_field = MID_TASK_EVIDENCE_FIELDS.get(row["input_classification"])
    if evidence_field:
        fields.append((evidence_field, row[evidence_field]))
    return " ".join(f"{key}={value}" for key, value in fields)


def append_mid_task_schedule_rows(
    report_dir: Path,
    rows: tuple[dict[str, str], ...],
) -> None:
    """Append mid-task user input rows to schedule.md."""
    if not rows:
        return
    schedule_path = report_dir / "schedule.md"
    with locked_existing_artifact(schedule_path) as handle:
        lines = handle.read().splitlines()
        insert_entries(
            lines,
            "## Agent Wave Ledger",
            [schedule_wave_row(row) for row in rows],
        )
        handle.seek(0)
        handle.truncate()
        handle.write("\n".join(lines).rstrip() + "\n")


def markdown_wave_id(line: str) -> str:
    """Return the wave id from one Agent Wave Ledger row, or an empty string."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return ""
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if not cells:
        return ""
    wave_id = cells[0]
    if wave_id == "Wave ID" or set(wave_id) <= {"-", " "}:
        return ""
    return wave_id


def upsert_subagent_wave_schedule_rows(
    report_dir: Path,
    rows: tuple[dict[str, str], ...],
) -> None:
    """Insert or replace actual subagent wave rows in schedule.md."""
    if not rows:
        return
    schedule_path = report_dir / "schedule.md"
    desired = {row["wave_id"]: schedule_wave_row(row) for row in rows}
    replaced: set[str] = set()
    with locked_existing_artifact(schedule_path) as handle:
        lines = handle.read().splitlines()
        ensure_section(lines, "## Agent Wave Ledger")
        start, end = section_bounds(lines, "## Agent Wave Ledger")
        index = start + 1
        while index < end:
            wave_id = markdown_wave_id(lines[index])
            if wave_id not in desired:
                index += 1
                continue
            if wave_id in replaced:
                del lines[index]
                end -= 1
                continue
            lines[index] = desired[wave_id]
            replaced.add(wave_id)
            index += 1
        missing_rows = [
            desired[wave_id]
            for wave_id in desired
            if wave_id not in replaced
        ]
        if missing_rows:
            insert_entries(lines, "## Agent Wave Ledger", missing_rows)
        handle.seek(0)
        handle.truncate()
        handle.write("\n".join(lines).rstrip() + "\n")


def normalize_tool_warning(entry: str) -> str:
    """Render one tool warning ledger item with required routing fields."""
    stripped = entry.strip()
    if not stripped:
        raise ValueError("tool warning entries must not be empty")
    fields = parse_token_fields(stripped)
    missing = [key for key in TOOL_WARNING_REQUIRED_KEYS if key not in fields]
    if missing:
        raise ValueError(
            "tool warning must include required keys: " + ",".join(missing)
        )
    status = fields["status"]
    if status not in TOOL_WARNING_STATUS_VALUES:
        raise ValueError(
            "tool warning status must be one of: "
            + ",".join(sorted(TOOL_WARNING_STATUS_VALUES))
        )
    return f"tool_warning=recorded {stripped}"


def set_section_status(
    lines: list[str],
    heading: str,
    key: str,
    value: str,
) -> None:
    """Set or insert one '- key: value' line under a section."""
    if not value:
        return
    ensure_section(lines, heading)
    start, end = section_bounds(lines, heading)
    prefix = f"- {key}:"
    for index in range(start + 1, end):
        if lines[index].strip().startswith(prefix):
            lines[index] = f"- {key}: {value}"
            return
    insert_at = start + 1
    while insert_at < end and lines[insert_at].strip() == "":
        insert_at += 1
    lines.insert(insert_at, f"- {key}: {value}")


def infer_tool_warning_status(lines: list[str]) -> str:
    """Infer aggregate ledger status from the latest row for each warning_id."""
    start = section_start(lines, "## Tool Warnings")
    if start == -1:
        return ""
    section = "\n".join(markdown_section_lines(lines, "## Tool Warnings"))
    latest: dict[str, str] = {}
    for line in section.splitlines():
        if "tool_warning=recorded" not in line:
            continue
        fields = parse_token_fields(line)
        warning_id = fields.get("warning_id", "")
        status = fields.get("status", "")
        if warning_id and status:
            latest[warning_id] = status
    if not latest:
        return ""
    if any(status == "open" for status in latest.values()):
        return "open"
    return "resolved"


def markdown_section_lines(lines: list[str], heading: str) -> list[str]:
    """Return raw lines for one existing level-2 markdown section."""
    start = section_start(lines, heading)
    if start == -1:
        return []
    _, end = section_bounds(lines, heading)
    return lines[start:end]


def section_start(lines: list[str], heading: str) -> int:
    """Return the heading index for one level-2 section, or -1 when absent."""
    for index, line in enumerate(lines):
        if line.strip() == heading:
            return index
    return -1


def ensure_section(lines: list[str], heading: str) -> None:
    """Append a level-2 section when the artifact does not contain it yet."""
    if section_start(lines, heading) == -1:
        lines.extend(["", heading, ""])


def section_bounds(lines: list[str], heading: str) -> tuple[int, int]:
    """Return insertion bounds for one existing level-2 section."""
    start = section_start(lines, heading)
    if start == -1:
        raise ValueError(f"missing workflow monitoring section: {heading}")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return start, end


def insert_entries(lines: list[str], heading: str, entries: list[str]) -> None:
    """Append entries to one markdown section if they are not already present."""
    if not entries:
        return
    ensure_section(lines, heading)
    _, end = section_bounds(lines, heading)
    insert_at = end
    if insert_at > 0 and lines[insert_at - 1].strip():
        lines.insert(insert_at, "")
        insert_at += 1
    existing = set(lines)
    for entry in entries:
        if entry in existing:
            continue
        lines.insert(insert_at, entry)
        existing.add(entry)
        insert_at += 1


def wave_event_id(line: str) -> str:
    """Return the wave id from one workflow monitoring event row."""
    if "wave_event=recorded" not in line:
        return ""
    return parse_token_fields(line).get("wave_id", "")


def upsert_wave_event_entries(
    lines: list[str],
    heading: str,
    entries: list[str],
) -> None:
    """Insert or replace workflow monitoring wave-event rows by wave id."""
    if not entries:
        return
    ensure_section(lines, heading)
    desired = {wave_event_id(entry): entry for entry in entries}
    desired.pop("", None)
    replaced: set[str] = set()
    start, end = section_bounds(lines, heading)
    index = start + 1
    while index < end:
        wave_id = wave_event_id(lines[index])
        if wave_id not in desired:
            index += 1
            continue
        if wave_id in replaced:
            del lines[index]
            end -= 1
            continue
        lines[index] = desired[wave_id]
        replaced.add(wave_id)
        index += 1
    insert_entries(
        lines,
        heading,
        [entry for wave_id, entry in desired.items() if wave_id not in replaced],
    )


def parse_decision(raw: str) -> tuple[str, str]:
    """Parse and validate one decision key=value pair."""
    if "=" not in raw:
        raise ValueError(f"invalid decision, expected key=value: {raw}")
    key, value = (part.strip() for part in raw.split("=", 1))
    if key not in DECISION_KEYS:
        raise ValueError(f"unknown decision key: {key}")
    if value not in DECISION_VALUES:
        raise ValueError(f"invalid decision value for {key}: {value}")
    return key, value


def apply_decisions(lines: list[str], decisions: dict[str, str]) -> None:
    """Set improvement decision values in the monitoring artifact."""
    if not decisions:
        return
    ensure_section(lines, "## Improvement Decisions")
    start, end = section_bounds(lines, "## Improvement Decisions")
    present: set[str] = set()
    for index in range(start + 1, end):
        stripped = lines[index].strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key = stripped.removeprefix("- ").split(":", 1)[0].strip()
        if key in decisions:
            lines[index] = f"- {key}: {decisions[key]}"
            present.add(key)
    insert_at = end
    for key, value in decisions.items():
        if key in present:
            continue
        lines.insert(insert_at, f"- {key}: {value}")
        insert_at += 1


def string_entries(value: object) -> tuple[str, ...]:
    """Return one legacy entry field as a tuple of strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        items = cast("list[object] | tuple[object, ...]", value)
        return tuple(str(item) for item in items)
    raise TypeError(f"expected string entries, got {type(value).__name__}")


def decision_entries(value: object) -> Mapping[str, str]:
    """Return one legacy decision field as a string mapping."""
    if value is None:
        return {}
    if isinstance(value, Mapping):
        items = cast("Mapping[object, object]", value)
        return {str(key): str(item) for key, item in items.items()}
    raise TypeError(f"expected decision mapping, got {type(value).__name__}")


def entries_from_legacy(kwargs: dict[str, object]) -> MonitoringEntries:
    """Build structured monitoring entries from the pre-dataclass keyword API."""
    unknown = set(kwargs) - MONITORING_LEGACY_KEYS
    if unknown:
        raise TypeError(f"unknown monitoring entry keys: {','.join(sorted(unknown))}")
    return MonitoringEntries(
        signals=string_entries(kwargs.get("signals")),
        behavior_events=string_entries(kwargs.get("behavior_events")),
        runtime_feedback=string_entries(kwargs.get("runtime_feedback")),
        tool_warnings=string_entries(kwargs.get("tool_warnings")),
        tool_warning_status=str(kwargs.get("tool_warning_status", "")),
        mid_task_user_inputs=string_entries(kwargs.get("mid_task_user_inputs")),
        subagent_waves=string_entries(kwargs.get("subagent_waves")),
        interventions=string_entries(kwargs.get("interventions")),
        decisions=decision_entries(kwargs.get("decisions")),
        timestamp=str(kwargs.get("timestamp", "")),
    )


def normalized_wave_rows(
    entries: MonitoringEntries,
) -> tuple[tuple[dict[str, str], ...], tuple[dict[str, str], ...]]:
    """Return normalized mid-task and subagent wave rows."""
    return (
        tuple(
            normalize_mid_task_user_input(item)
            for item in entries.mid_task_user_inputs
        ),
        tuple(
            normalize_subagent_wave(item)
            for item in entries.subagent_waves
        ),
    )


def append_wave_schedule_rows(
    report_dir: Path,
    mid_task_rows: tuple[dict[str, str], ...],
    subagent_wave_rows: tuple[dict[str, str], ...],
) -> None:
    """Update schedule.md with every monitor-owned wave row."""
    append_mid_task_schedule_rows(report_dir, mid_task_rows)
    upsert_subagent_wave_schedule_rows(report_dir, subagent_wave_rows)


def append_monitoring_sections(
    lines: list[str],
    entries: MonitoringEntries,
    mid_task_rows: tuple[dict[str, str], ...],
    subagent_wave_rows: tuple[dict[str, str], ...],
) -> None:
    """Apply normalized monitoring rows to workflow_monitoring.md sections."""
    signal_entries = [
        normalize_entry(item, entries.timestamp)
        for item in entries.signals
    ]
    behavior_entries = [
        normalize_entry(item, entries.timestamp)
        for item in entries.behavior_events
    ]
    behavior_entries.extend(
        normalize_entry(normalize_runtime_feedback(item), entries.timestamp)
        for item in entries.runtime_feedback
    )
    behavior_entries.extend(
        normalize_entry(mid_task_behavior_event(row), entries.timestamp)
        for row in mid_task_rows
    )
    behavior_entries.extend(
        normalize_entry(subagent_wave_behavior_event(row), entries.timestamp)
        for row in subagent_wave_rows
    )
    actual_wave_entries = [
        normalize_entry(mid_task_actual_wave_event(row), entries.timestamp)
        for row in mid_task_rows
    ]
    subagent_wave_entries = [
        normalize_entry(subagent_wave_actual_event(row), entries.timestamp)
        for row in subagent_wave_rows
    ]
    tool_warning_entries = [
        normalize_entry(normalize_tool_warning(item), entries.timestamp)
        for item in entries.tool_warnings
    ]
    intervention_entries = [
        normalize_entry(item, entries.timestamp)
        for item in entries.interventions
    ]
    insert_entries(lines, "## Signals", signal_entries)
    insert_entries(lines, "## Behavior Events", behavior_entries)
    insert_entries(lines, "## Actual Wave Events", actual_wave_entries)
    upsert_wave_event_entries(lines, "## Actual Wave Events", subagent_wave_entries)
    insert_entries(lines, "## Tool Warnings", tool_warning_entries)
    inferred_tool_warning_status = (
        entries.tool_warning_status or infer_tool_warning_status(lines)
    )
    set_section_status(
        lines,
        "## Tool Warnings",
        "tool_warnings_status",
        inferred_tool_warning_status,
    )
    insert_entries(lines, "## Interventions", intervention_entries)
    apply_decisions(lines, dict(entries.decisions))


def append_monitoring(
    report_dir: Path,
    entries: MonitoringEntries = EMPTY_MONITORING_ENTRIES,
    **legacy_entries: object,
) -> Path:
    """Append monitoring evidence and return the artifact path."""
    active_entries = entries_from_legacy(legacy_entries) if legacy_entries else entries
    report_dir.mkdir(parents=True, exist_ok=True)
    mid_task_rows, subagent_wave_rows = normalized_wave_rows(active_entries)
    append_wave_schedule_rows(report_dir, mid_task_rows, subagent_wave_rows)
    path = report_dir / "workflow_monitoring.md"
    with locked_monitoring_artifact(path) as handle:
        text = handle.read()
        if not text.strip():
            text = default_monitoring_text(report_dir)
        lines = text.splitlines()
        append_monitoring_sections(
            lines,
            active_entries,
            mid_task_rows,
            subagent_wave_rows,
        )
        handle.seek(0)
        handle.truncate()
        handle.write("\n".join(lines).rstrip() + "\n")
    return path


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    decisions = dict(parse_decision(item) for item in args.decision)
    signals = list(args.signal)
    behavior_events = list(args.behavior_event)
    if args.closeout_token_preset:
        signals.extend(STANDARD_CLOSEOUT_SIGNALS)
        behavior_events.extend(STANDARD_CLOSEOUT_BEHAVIOR_EVENTS)
    path = append_monitoring(
        resolve_report_dir(args),
        MonitoringEntries(
            signals=tuple(signals),
            behavior_events=tuple(behavior_events),
            runtime_feedback=tuple(args.runtime_feedback),
            tool_warnings=tuple(args.tool_warning),
            tool_warning_status=str(args.tool_warning_status),
            mid_task_user_inputs=tuple(args.mid_task_user_input),
            subagent_waves=tuple(args.subagent_wave),
            interventions=tuple(args.intervention),
            decisions=decisions,
            timestamp=str(args.timestamp),
        ),
    )
    print(f"WORKFLOW_MONITORING={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
