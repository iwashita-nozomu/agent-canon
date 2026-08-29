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
COORDINATION_RECEIPT_SCHEMA = "agent-canon.coordination-receipt.v1"


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


def build_coordination_receipt(
    payload: object,
    selection: SubagentSelection | None,
    *,
    hook_event_name: str,
) -> dict[str, object] | None:
    """Build one honest base-event receipt from the real PostToolUse result."""
    if (
        hook_event_name != "PostToolUse"
        or selection is None
        or selection.action not in COLLABORATION_OPERATIONS
    ):
        return None
    exact_post_tool_payload = (
        isinstance(payload, dict)
        and set(payload) == {"hookEventName", "tool_name", "tool_input", "tool_response"}
        and payload.get("hookEventName") == "PostToolUse"
        and isinstance(payload.get("tool_name"), str)
        and isinstance(payload.get("tool_input"), dict)
    )
    response = payload.get("tool_response") if exact_post_tool_payload else None
    valid_response = (
        isinstance(response, dict)
        and set(response) == {"exit_code", "stderr", "stdout"}
        and type(response.get("exit_code")) is int
        and isinstance(response.get("stderr"), str)
        and isinstance(response.get("stdout"), str)
    )
    result_status = (
        "succeeded"
        if valid_response and response["exit_code"] == 0
        else "failed"
        if valid_response
        else "invalid_tool_result"
    )
    return {
        "schema": COORDINATION_RECEIPT_SCHEMA,
        "operation": selection.action,
        "capability_status": "unverified",
        "effective_operations": [],
        "evidence_ref": "",
        "transport": "durable_artifact",
        "direct_peer": False,
        "status": result_status,
    }


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
    )
