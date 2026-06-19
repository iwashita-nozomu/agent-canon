#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Blocks changed notebooks that behave like fine-grained tests instead of readable demos.
# upstream implementation ../hooks.json invokes this hook for PostToolUse and Stop.
# upstream implementation ./hook_event_log.py assigns Canon-owned hook log paths and IDs.
# upstream implementation ../../tools/validation/notebook_quality.py validates notebook quality.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates notebook hook behavior.
# @dependency-end
"""Block changed notebooks with test-like or unreadable notebook content."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from hook_event_log import HookLogContext, fingerprint_json, utc_now

PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
PAYLOAD_STATUS_VALID = "valid"
PAYLOAD_STATUS_EMPTY = "empty"
PAYLOAD_STATUS_INVALID_JSON = "invalid_json"
LOG_PATH_ENV = "AGENT_CANON_NOTEBOOK_QUALITY_HOOK_LOG_PATH"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
EDIT_TOOL_NAMES = {"apply_patch", "python", "python3", "Bash", "bash"}
EDIT_COMMAND_PATTERN = re.compile(
    r"(?is)(apply_patch|\.ipynb\b|jupyter\s+nbconvert|python3?\s+|"
    r"papermill|sed\s+-i|perl\s+-pi|mv\s+|cp\s+|rm\s+)"
)
CHECKER_COMMAND_RE = re.compile(
    r"(?is)(notebook_quality(?:_guard)?\.py|tools/validation/notebook_quality\.py)"
)
GIT_TIMEOUT_SECONDS = 10
CHECK_TIMEOUT_SECONDS = 60
MAX_REASON_LINES = 8


def load_payload() -> dict[str, object]:
    """Read one Codex hook payload from stdin."""
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
    """Return how the hook payload was read."""
    value = payload.get(PAYLOAD_STATUS_KEY)
    return value if isinstance(value, str) else PAYLOAD_STATUS_VALID


def repo_root() -> Path:
    """Return the active Git repository root."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


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
    """Return the tool name from one hook payload."""
    value = payload.get("tool_name")
    return value if isinstance(value, str) else ""


def should_check(payload: dict[str, object]) -> bool:
    """Return whether this hook invocation should inspect changed notebooks."""
    if payload_status(payload) == PAYLOAD_STATUS_EMPTY:
        return False
    command = tool_command(payload)
    if CHECKER_COMMAND_RE.search(command):
        return False
    event = hook_event_name(payload)
    if event == "Stop":
        return True
    if event != "PostToolUse":
        return False
    return tool_name(payload) in EDIT_TOOL_NAMES or bool(
        EDIT_COMMAND_PATTERN.search(command)
    )


def git_lines(root: Path, args: list[str]) -> list[str]:
    """Return non-empty git output lines."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_notebooks(root: Path) -> list[str]:
    """Return changed notebook paths relative to one root."""
    names: set[str] = set()
    for args in (
        ["diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "--"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        names.update(git_lines(root, args))
    return sorted(
        name
        for name in names
        if name.endswith(".ipynb") and (root / name).is_file()
    )


def checker_command(root: Path) -> list[str]:
    """Return the notebook quality checker command."""
    return [
        "python3",
        str(root / "tools" / "validation" / "notebook_quality.py"),
        "--root",
        str(root),
        "--changed",
    ]


def blocked_reason(result: subprocess.CompletedProcess[str]) -> str:
    """Return a concise Codex block reason."""
    lines = [
        line
        for line in result.stdout.splitlines()
        if line.startswith("NOTEBOOK_QUALITY_FINDING=")
    ][:MAX_REASON_LINES]
    if not lines and result.stderr.strip():
        lines = result.stderr.splitlines()[:MAX_REASON_LINES]
    detail = "\n".join(lines)
    return (
        "Notebook quality hook blocked changed notebooks. "
        "Move fine-grained checks to tests/ and keep notebooks as readable, "
        f"runnable demos.\n{detail}"
    ).strip()


def append_log(
    root: Path,
    payload: dict[str, object],
    result: subprocess.CompletedProcess[str],
    notebooks: list[str],
) -> None:
    """Append one notebook hook result log entry."""
    if os.environ.get(DISABLE_LOG_ENV, "").strip():
        return
    timestamp = utc_now()
    payload_fingerprint = fingerprint_json(payload)
    context = HookLogContext(
        active_root=root,
        hook_name="notebook_quality_guard",
        override_path=os.environ.get(LOG_PATH_ENV, "").strip(),
    )
    status = "fail" if result.returncode else "pass"
    context.append(
        {
            "timestamp": timestamp,
            "hook_run_id": context.run_id(timestamp, payload_fingerprint),
            "payload_fingerprint": payload_fingerprint,
            "payload_status": payload_status(payload),
            "event": hook_event_name(payload),
            "event_declared": isinstance(payload.get("hookEventName"), str),
            "tool_name": tool_name(payload),
            "root": str(root),
            "status": status,
            "checked": True,
            "notebooks": notebooks,
            "finding_count": sum(
                1
                for line in result.stdout.splitlines()
                if line.startswith("NOTEBOOK_QUALITY_FINDING=")
            ),
            "command": checker_command(root),
            "returncode": result.returncode,
            "output_snippet": "\n".join(result.stdout.splitlines()[:MAX_REASON_LINES]),
            "hook_log_namespace": context.runtime_namespace(),
            "failure_fingerprint": ""
            if result.returncode == 0
            else fingerprint_json(
                {
                    "notebooks": notebooks,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            ),
        }
    )


def main() -> int:
    """Run the notebook quality hook."""
    payload = load_payload()
    if not should_check(payload):
        return 0
    root = repo_root()
    notebooks = changed_notebooks(root)
    if not notebooks:
        return 0
    tool = root / "tools" / "validation" / "notebook_quality.py"
    if not tool.is_file():
        result = subprocess.CompletedProcess(
            args=checker_command(root),
            returncode=1,
            stdout="",
            stderr=f"missing notebook quality tool: {tool}",
        )
    else:
        result = subprocess.run(
            checker_command(root),
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_SECONDS,
        )
    append_log(root, payload, result, notebooks)
    if result.returncode:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": blocked_reason(result),
                    "next_action": "fix_notebook_quality_findings_then_retry",
                    "remediation": [
                        "Move fine-grained assertions and heavy checks from notebooks into tests/.",
                        "Keep changed notebooks readable and runnable as demos.",
                        "Run `python3 tools/validation/notebook_quality.py --root . --changed` after fixes.",
                    ],
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
