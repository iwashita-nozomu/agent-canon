#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Normalizes subagent invocation and attribution evidence without side effects.
# upstream design ../../documents/design/agentcanon-hook-simplification-wave3.md owns subagent-selection parity.
# upstream implementation ./workflow_context.py supplies inherited workflow context.
# downstream implementation ./behavior_event_assembly.py consumes SubagentSelection.
# downstream implementation ./workflow_monitor.py projects the assembled event.
# @dependency-end
"""Pure subagent selection and attribution owner."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


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


_ACTIONS = frozenset({"spawn", "send_input", "wait", "close", "resume"})


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
    if action not in _ACTIONS:
        if tool_name in {"Task", "spawn_agent"}:
            action = "spawn"
        elif tool_name in {"send_input", "wait_agent", "close_agent", "resume_agent"}:
            action = tool_name.removesuffix("_agent")
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
