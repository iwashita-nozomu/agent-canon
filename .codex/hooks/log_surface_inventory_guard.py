#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Blocks hook/tool/skill log-surface drift not reflected in the generated inventory baseline.
# upstream implementation ../hooks.json invokes this hook for PostToolUse and Stop.
# upstream implementation ../../tools/agent_tools/log_surface_inventory.py inventories emitted log fields.
# upstream design ../../documents/runtime-log-archive.md defines durable hook result fields.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates hook wiring and quiet pass behavior.
# @dependency-end
"""Guard hook/tool/skill log-surface inventory drift."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

EDIT_TOOL_NAMES = {"apply_patch", "Bash", "bash", "python", "python3"}
EDIT_COMMAND_PATTERN = re.compile(
    r"(?is)(apply_patch|python3?\s+|ruff\s+--fix|python3?\s+-m\s+ruff\s+.*--fix|"
    r"git\s+mv|mv\s+|cp\s+|touch\s+|rm\s+|sed\s+-i|perl\s+-pi)"
)
PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
PAYLOAD_STATUS_EMPTY = "empty"
PAYLOAD_STATUS_VALID = "valid"
PAYLOAD_STATUS_INVALID_JSON = "invalid_json"
DISABLE_ENV = "AGENT_CANON_DISABLE_LOG_SURFACE_INVENTORY_GUARD"
BASELINE_ENV = "AGENT_CANON_LOG_SURFACE_INVENTORY_BASELINE"
TOOL_TIMEOUT_SECONDS = 60


def load_payload() -> dict[str, object]:
    """Read the Codex hook payload from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {PAYLOAD_STATUS_KEY: PAYLOAD_STATUS_EMPTY}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {PAYLOAD_STATUS_KEY: PAYLOAD_STATUS_INVALID_JSON}
    if isinstance(loaded, dict):
        loaded[PAYLOAD_STATUS_KEY] = PAYLOAD_STATUS_VALID
        return loaded
    return {PAYLOAD_STATUS_KEY: PAYLOAD_STATUS_INVALID_JSON}


def payload_status(payload: dict[str, object]) -> str:
    """Return how the hook payload was parsed."""
    value = payload.get(PAYLOAD_STATUS_KEY)
    return value if isinstance(value, str) else PAYLOAD_STATUS_VALID


def tool_command(payload: dict[str, object]) -> str:
    """Return a command-like string from one hook payload."""
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        command = tool_input.get("command") or tool_input.get("cmd")
        if isinstance(command, str):
            return command
    for key in ("command", "cmd"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def hook_event_name(payload: dict[str, object]) -> str:
    """Return the declared hook event name."""
    value = payload.get("hookEventName")
    if isinstance(value, str):
        return value
    return ""


def tool_name(payload: dict[str, object]) -> str:
    """Return the invoked tool name."""
    value = payload.get("tool_name")
    return value if isinstance(value, str) else ""


def should_check(payload: dict[str, object]) -> bool:
    """Return whether this invocation should run the full inventory guard."""
    if os.environ.get(DISABLE_ENV, "").strip() in {"1", "true", "yes"}:
        return False
    event = hook_event_name(payload)
    if event == "Stop":
        return True
    if event != "PostToolUse":
        return False
    return tool_name(payload) in EDIT_TOOL_NAMES or bool(
        EDIT_COMMAND_PATTERN.search(tool_command(payload))
    )


def repo_root() -> Path:
    """Resolve the active repository root."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


def agent_canon_root() -> Path:
    """Return the AgentCanon checkout that owns this hook."""
    return Path(__file__).resolve().parents[2]


def tool_path(root: Path) -> Path:
    """Return the inventory tool path for standalone or vendored execution."""
    candidates = (
        root / "tools" / "agent_tools" / "log_surface_inventory.py",
        root
        / "vendor"
        / "agent-canon"
        / "tools"
        / "agent_tools"
        / "log_surface_inventory.py",
        agent_canon_root() / "tools" / "agent_tools" / "log_surface_inventory.py",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-1]


def baseline_path(root: Path) -> Path:
    """Return the inventory baseline path for standalone or vendored execution."""
    override = os.environ.get(BASELINE_ENV, "").strip()
    if override:
        return Path(override)
    candidates = (
        root / "documents" / "log-surface-inventory.json",
        root / "vendor" / "agent-canon" / "documents" / "log-surface-inventory.json",
        agent_canon_root() / "documents" / "log-surface-inventory.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-1]


def inventory_root_for_baseline(baseline: Path) -> Path:
    """Return the source root whose surfaces are represented by the baseline."""
    return baseline.resolve().parents[1]


def block(reason: str) -> None:
    """Emit a Codex blocking hook payload."""
    json.dump(
        {
            "decision": "block",
            "reason": reason,
            "next_action": "regenerate_log_surface_inventory_then_retry",
            "remediation": [
                "Review the added or removed hook/tool/skill output fields.",
                "Run `python3 tools/agent_tools/log_surface_inventory.py --root . --output documents/log-surface-inventory.json` from AgentCanon.",
                "Re-run the blocked command after committing the regenerated inventory with the field change.",
            ],
        },
        sys.stdout,
    )


def main() -> int:
    """Run the log-surface guard."""
    payload = load_payload()
    if not should_check(payload):
        return 0

    root = repo_root()
    inventory_tool = tool_path(root)
    baseline = baseline_path(root)
    inventory_root = inventory_root_for_baseline(baseline)
    result = subprocess.run(
        [
            sys.executable,
            str(inventory_tool),
            "--root",
            str(inventory_root),
            "--check",
            "--baseline",
            str(baseline),
            "--quiet",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=TOOL_TIMEOUT_SECONDS,
    )
    if result.returncode == 0:
        return 0

    reason = (
        "Log surface inventory guard found hook/tool/skill output field drift. "
        "Regenerate documents/log-surface-inventory.json after reviewing the "
        "field change.\n"
        f"{result.stdout.strip() or result.stderr.strip()}"
    )
    block(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
