#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Normalizes tool-selection evidence without writing telemetry.
# upstream design ../../../documents/design/agentcanon-hook-simplification-wave3.md owns tool-selection parity.
# downstream implementation ../../runtime/archive/behavior_event_assembly.py consumes ToolSelection.
# downstream implementation ../../../tests/agent_tools/test_tool_selection.py validates domains and ordering.
# @dependency-end
"""Pure tool-selection owner."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSelection:
    tool_name: str = ""
    command_verb: str = ""
    selected_tools: tuple[str, ...] = ()
    tool_input_fingerprint: str = ""
    tool_input_keys: tuple[str, ...] = ()
    tool_input_key_count: int = 0
    selection_kind: str = ""

    def should_log(self) -> bool:
        return bool(self.tool_name or self.selected_tools)


def _tool_input(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    value = payload.get("tool_input")
    return value if isinstance(value, dict) else {}


def _command_verb(value: object) -> str:
    if not isinstance(value, str):
        return ""
    match = re.search(r"(?:^|\s)(?:sudo\s+)?([A-Za-z0-9_.-]+)", value.strip())
    return match.group(1) if match else ""


def select_tools(payload: object) -> ToolSelection:
    """Return stable tool evidence using only the supplied payload."""
    if not isinstance(payload, dict):
        return ToolSelection()
    tool_name = payload.get("tool_name") if isinstance(payload.get("tool_name"), str) else ""
    tool_input = _tool_input(payload)
    command = ""
    for key in ("command", "cmd"):
        if isinstance(tool_input.get(key), str):
            command = tool_input[key]
            break
    if not command:
        for key in ("command", "cmd"):
            if isinstance(payload.get(key), str):
                command = payload[key]
                break
    selected = payload.get("selected_tools")
    if not isinstance(selected, (list, tuple)):
        selected = ()
    selected_tools = tuple(str(item) for item in selected if isinstance(item, str) and item)
    if tool_name and not selected_tools:
        selected_tools = (tool_name,)
    encoded = json.dumps(tool_input, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    fingerprint = hashlib.sha256(encoded).hexdigest()[:12] if tool_input else ""
    keys = tuple(sorted(str(key) for key in tool_input))
    return ToolSelection(
        tool_name=tool_name,
        command_verb=_command_verb(command),
        selected_tools=selected_tools,
        tool_input_fingerprint=fingerprint,
        tool_input_keys=keys,
        tool_input_key_count=len(keys),
        selection_kind="executed_tool" if tool_name else "",
    )


def select_tool(payload: object) -> ToolSelection:
    """Singular spelling retained as the canonical API alias."""
    return select_tools(payload)
