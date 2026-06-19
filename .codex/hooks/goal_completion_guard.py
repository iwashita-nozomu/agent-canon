#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Prevents user-facing completion when goal.md still requires another iteration.
# upstream implementation ../hooks.json invokes this hook for Stop.
# upstream implementation ../../tools/agent_tools/goal_loop.py reports goal loop NEXT_ACTION.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates guard decisions.
# @dependency-end

"""Guard final responses against active goal-loop backlog state."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

COMPLETION_PATTERN = re.compile(
    r"(完了|対応しました|修正しました|実装しました|done|complete|completed|fixed|implemented)",
    re.IGNORECASE,
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


def repo_root() -> Path:
    """Resolve the active repository root for hook checks."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip())
    return Path.cwd()


def assistant_message(payload: dict[str, object]) -> str:
    """Extract the latest assistant message from a Stop payload."""
    message = payload.get("last_assistant_message")
    if isinstance(message, str):
        return message
    return ""


def goal_status(root: Path) -> str:
    """Return goal-loop status output when goal.md is present."""
    goal_file = root / "goal.md"
    goal_loop = root / "tools" / "agent_tools" / "goal_loop.py"
    if not goal_file.is_file() or not goal_loop.is_file():
        return ""
    result = subprocess.run(
        ["python3", str(goal_loop), "status", "--goal-file", str(goal_file)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def emit_block() -> None:
    """Ask Codex to continue instead of returning a premature completion report."""
    json.dump(
        {
            "decision": "block",
            "reason": (
                "goal.md still reports NEXT_ACTION=run_next_iteration. "
                "Continue the next backlog iteration or update goal evidence before final completion."
            ),
            "next_action": "run_next_goal_iteration_or_update_goal_evidence",
            "remediation": [
                "Run the next unchecked goal.md work unit.",
                "If the goal is actually complete, update goal evidence so NEXT_ACTION is no longer run_next_iteration.",
                "Do not send a user-facing completion report until the goal loop gate allows closeout.",
            ],
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def main() -> int:
    """Block completion-like final messages while the goal loop is still active."""
    payload = load_payload()
    if not COMPLETION_PATTERN.search(assistant_message(payload)):
        return 0
    status = goal_status(repo_root())
    if "NEXT_ACTION=run_next_iteration" in status:
        emit_block()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
