#!/usr/bin/env python3
# @dependency-start
# responsibility Blocks high-risk Codex Bash commands before tool execution.
# upstream implementation ../hooks.json invokes this hook for PreToolUse Bash calls.
# upstream design ../../documents/codex-configuration-reference.md documents Codex hook events.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates guard decisions.
# @dependency-end

"""Guard Codex Bash tool calls against destructive host-level operations."""

from __future__ import annotations

import json
import re
import sys

COMMAND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?is)(^|[;&|]\s*)(sudo\s+)?rm\s+-[^\n;&|]*[rf][^\n;&|]*[rf]"
            r"[^\n;&|]*(\s+|=)(/|/\*|~|\$HOME)(\s|$|[;&|])"
        ),
        "Refusing recursive forced removal of a root or home path.",
    ),
    (
        re.compile(r"(?is)(^|[;&|]\s*)git\s+reset\s+--hard(\s|$|[;&|])"),
        "Refusing git reset --hard; use an explicit, reviewed recovery path.",
    ),
    (
        re.compile(r"(?is)(^|[;&|]\s*)git\s+clean\s+-[^\n;&|]*[xdf][^\n;&|]*(\s|$|[;&|])"),
        "Refusing broad git clean with destructive flags.",
    ),
    (
        re.compile(r"(?is)(^|[;&|]\s*)(mkfs|fdisk|parted)\b"),
        "Refusing disk partitioning or filesystem formatting command.",
    ),
    (
        re.compile(r"(?is)(^|[;&|]\s*)dd\s+.*\bof=/dev/(sd|nvme|mmcblk)"),
        "Refusing raw disk write to a block device.",
    ),
    (
        re.compile(r":\s*\(\)\s*\{\s*:\|:\s*&\s*\}\s*;:"),
        "Refusing shell fork bomb pattern.",
    ),
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


def emit_deny(reason: str) -> None:
    """Emit the current Codex PreToolUse denial shape."""
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def main() -> int:
    """Evaluate the hook payload and deny high-risk commands."""
    payload = load_payload()
    command = command_from(payload)
    for pattern, reason in COMMAND_PATTERNS:
        if pattern.search(command):
            emit_deny(reason)
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
