#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Defines mid-task user input policy tokens for workflow monitoring and closeout checks.
# upstream design ../../agents/canonical/CODEX_SUBAGENTS.md defines mid-task subagent reuse and fresh-run policy
# downstream implementation ./workflow_monitor.py emits mid-task checkpoint and evidence rows
# downstream implementation ./report_artifact_checks.py validates mid-task checkpoint and evidence rows
# @dependency-end
"""Shared policy for mid-task user input routing evidence."""

from __future__ import annotations

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
MID_TASK_SPAWN_AUTHORITY = {
    "same_active_task_delta": "parent_checkpoint_then_send_input",
    "scope_or_contract_change": "parent_checkpoint_then_spawn_fresh_wave",
    "new_task": "fresh_run_required",
}
MID_TASK_REQUIRED_KEYS = (
    "wave_id",
    "input_classification",
    "updated_packet",
    "target_agents",
    "scope_status",
    "budget_before",
    "budget_after",
    "runtime_max_threads",
    "runtime_max_depth",
    "allowed_paths",
    "do_not_read",
    "write_scope",
    "validation_route",
    "review_gate",
    "handoff_artifacts",
)
MID_TASK_REQUIRED_WAVE_FIELDS = (
    "input_classification",
    "updated_packet",
    "redispatch_action",
    "target_agents",
    "scope_status",
    "lifecycle_policy_ref",
)
MID_TASK_EVIDENCE_FIELDS = {
    "scope_or_contract_change": "fresh_wave_evidence",
    "new_task": "fresh_run_bundle",
}
MID_TASK_TARGET_REQUIRED_CLASSIFICATIONS = {
    "same_active_task_delta",
    "scope_or_contract_change",
}
MID_TASK_SPAWNED_ROLES_REQUIRED_CLASSIFICATIONS = {
    "scope_or_contract_change",
}
MID_TASK_EMPTY_VALUES = {"", "missing", "none"}
MID_TASK_REUSE_MARKERS = ("reused_run_local_send_input",)


def is_empty_policy_value(value: str) -> bool:
    """Return whether a machine-token value is empty for policy purposes."""
    return value.strip().lower() in MID_TASK_EMPTY_VALUES


def has_reuse_marker(value: str) -> bool:
    """Return whether a token value claims reuse of a run-local agent."""
    return any(marker in value for marker in MID_TASK_REUSE_MARKERS)
