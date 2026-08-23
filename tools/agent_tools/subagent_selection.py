#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Normalizes subagent invocation and attribution evidence without side effects.
# upstream design ../../documents/design/agentcanon-hook-simplification-wave3.md owns subagent-selection parity.
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md owns capability and receipt semantics.
# upstream implementation ./workflow_context.py supplies inherited workflow context.
# downstream implementation ./behavior_event_assembly.py consumes SubagentSelection.
# downstream implementation ./workflow_monitor.py projects the assembled event.
# @dependency-end
"""Pure subagent selection and attribution owner."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


COLLABORATION_OPERATIONS = (
    "send_message",
    "followup_task",
    "list_agents",
    "interrupt_agent",
)
COORDINATION_CAPABILITY_STATUSES = frozenset(
    {"available", "unavailable", "unverified"}
)
COORDINATION_MODES = frozenset(
    {"direct_peer", "parent_relay", "durable_artifact"}
)


@dataclass(frozen=True)
class SubagentSelection:
    invoked: bool = False
    action: str = ""
    tool_name: str = ""
    agent_type: str = ""
    target: str = ""
    targets: tuple[str, ...] = ()
    model: str = ""
    reasoning_effort: str = ""
    fork_context: bool = False
    prompt_fingerprint: str = ""
    prompt_char_count: int = 0
    item_count: int = 0
    capability_status: str = "unverified"
    effective_operations: tuple[str, ...] = ()
    evidence_ref: str = ""
    coordination_mode: str = "durable_artifact"
    receipt_status: str = ""

    def should_log(self) -> bool:
        return self.invoked


_ACTIONS = frozenset(
    {"spawn", "send_input", "wait", "close", "resume", *COLLABORATION_OPERATIONS}
)


def _normalise_operation(tool_name: str, action: str) -> str:
    """Map runtime tool aliases to an observed operation without claiming access."""
    if action in _ACTIONS:
        return action
    lowered = tool_name.casefold()
    for operation in (*COLLABORATION_OPERATIONS, "spawn", "send_input", "wait", "close", "resume"):
        if lowered in {
            operation,
            f"tools.{operation}",
            f"tools.collaboration.{operation}",
            f"functions.{operation}",
            f"functions.collaboration.{operation}",
        }:
            return operation
    if tool_name in {"Task", "spawn_agent"}:
        return "spawn"
    if tool_name in {"send_input", "wait_agent", "close_agent", "resume_agent"}:
        return tool_name.removesuffix("_agent")
    return action


def _coordination_fields(
    payload: dict[str, object], operation: str
) -> tuple[str, tuple[str, ...], str, str, str]:
    """Read explicit capability evidence; never infer it from a matcher/tool name."""
    raw_status = payload.get("coordination_capability_status", payload.get("capability_status"))
    status = raw_status if isinstance(raw_status, str) and raw_status in COORDINATION_CAPABILITY_STATUSES else "unverified"
    raw_operations = payload.get(
        "coordination_effective_operations", payload.get("effective_operations", ())
    )
    operations = tuple(
        item
        for item in raw_operations
        if isinstance(item, str) and item in COLLABORATION_OPERATIONS
    ) if isinstance(raw_operations, (list, tuple)) else ()
    raw_evidence = payload.get("coordination_evidence_ref", payload.get("evidence_ref", ""))
    evidence = raw_evidence if isinstance(raw_evidence, str) else ""
    requested_mode = payload.get("coordination_mode", payload.get("communication_mode", ""))
    mode = requested_mode if isinstance(requested_mode, str) else ""
    if status == "available":
        mode = "direct_peer" if operation in operations and evidence else "durable_artifact"
    elif mode not in {"parent_relay", "durable_artifact"}:
        mode = "durable_artifact"
    raw_receipt_status = payload.get("coordination_receipt_status", "")
    receipt_status = (
        raw_receipt_status
        if isinstance(raw_receipt_status, str) and raw_receipt_status
        else "observed"
        if operation in COLLABORATION_OPERATIONS
        else ""
    )
    return status, operations, evidence, mode, receipt_status


def _string(payload: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def select_subagents(payload: object, workflow_context: object = None) -> SubagentSelection:
    if not isinstance(payload, dict):
        return SubagentSelection()
    tool_name = _string(payload, "tool_name", "subagent_tool_name")
    action = _string(payload, "subagent_event_kind", "action", "event")
    action = _normalise_operation(tool_name, action)
    raw_targets = payload.get("subagent_targets", payload.get("targets", ()))
    targets = tuple(item for item in raw_targets if isinstance(item, str) and item) if isinstance(raw_targets, (list, tuple)) else ()
    target = _string(payload, "subagent_target", "target")
    prompt = _string(payload, "subagent_prompt", "prompt")
    capability_status, effective_operations, evidence_ref, coordination_mode, receipt_status = _coordination_fields(payload, action)
    return SubagentSelection(
        invoked=bool(action or targets or target or payload.get("subagent_invoked")),
        action=action,
        tool_name=tool_name,
        agent_type=_string(payload, "subagent_agent_type", "agent_type"),
        target=target,
        targets=targets,
        model=_string(payload, "subagent_model", "model"),
        reasoning_effort=_string(payload, "subagent_reasoning_effort", "reasoning_effort"),
        fork_context=bool(payload.get("subagent_fork_context", payload.get("fork_context", False))),
        prompt_fingerprint=hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16] if prompt else "",
        prompt_char_count=len(prompt),
        item_count=len(targets),
        capability_status=capability_status,
        effective_operations=effective_operations,
        evidence_ref=evidence_ref,
        coordination_mode=coordination_mode,
        receipt_status=receipt_status,
    )
