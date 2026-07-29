#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Provides the standalone compatibility wrapper for destructive Git safety.
# upstream implementation ./hook_safety.py owns pure branch intent and redacted payload logic.
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md owns shared-checkout and branch reuse policy.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates destructive Git decisions.
# @dependency-end
"""Standalone wrapper for the pure shared-checkout Git safety leaf."""

from __future__ import annotations

import json
import sys

from hook_safety import (  # noqa: E402
    SHELL_TOOL_NAMES,
    branch_block_payload,
    first_block,
    payload_tool_command,
    payload_tool_name,
)


def load_payload() -> dict[str, object]:
    """Read one standalone payload without making the leaf depend on I/O."""
    try:
        loaded = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def main() -> int:
    payload = load_payload()
    if payload_tool_name(payload) not in SHELL_TOOL_NAMES:
        return 0
    command = payload_tool_command(payload)
    intent = first_block(command)
    if intent is not None:
        json.dump(branch_block_payload(command, intent), sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
