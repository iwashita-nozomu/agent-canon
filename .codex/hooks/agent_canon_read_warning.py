#!/usr/bin/env python3
# @dependency-start
# responsibility Warns when Codex commands read or inspect AgentCanon shared-source paths.
# upstream implementation ../hooks.json invokes this hook for PreToolUse Bash calls.
# upstream design ../../documents/SHARED_RUNTIME_SURFACES.md defines shared AgentCanon surfaces.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates warning output.
# @dependency-end

"""Warn when a shell command appears to inspect AgentCanon shared source files."""

from __future__ import annotations

import json
import re
import sys

AGENT_CANON_PATH_PATTERN = re.compile(
    r"(^|[\s'\"=:])(\./)?(vendor/agent-canon|agents|\.agents|\.codex|\.claude|documents|memory|mcp|tools)(/|[\s'\";]|$)"
)
READ_COMMAND_PATTERN = re.compile(
    r"(?is)(^|[;&|]\s*)(cat|sed|grep|rg|head|tail|less|more|wc|stat|ls|find|awk|python3?\s+-c)\b"
)

MESSAGE = (
    "AgentCanon shared-source path detected. Treat the file as shared canon, not "
    "template-local truth. For shared-canon changes, edit vendor/agent-canon as "
    "the source of truth and propagate through the AgentCanon PR/submodule pin flow; "
    "do not make Docker/devcontainer build logic depend on vendor/agent-canon content."
)


def load_payload() -> dict[str, object]:
    """Read the Codex hook payload from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def command_from(payload: dict[str, object]) -> str:
    """Extract a Bash command from a PreToolUse payload."""
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        command = tool_input.get("command")
        if isinstance(command, str):
            return command
    command = payload.get("command")
    if isinstance(command, str):
        return command
    return ""


def emit_warning() -> None:
    """Emit a UI-visible warning without blocking the command."""
    json.dump({"systemMessage": MESSAGE}, sys.stdout)
    sys.stdout.write("\n")


def main() -> int:
    """Warn when a read-like command mentions an AgentCanon shared path."""
    command = command_from(load_payload())
    if AGENT_CANON_PATH_PATTERN.search(command) and READ_COMMAND_PATTERN.search(command):
        emit_warning()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
