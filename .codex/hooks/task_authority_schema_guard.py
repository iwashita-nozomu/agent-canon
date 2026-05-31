#!/usr/bin/env python3
# @dependency-start
# responsibility Validates request-local task authority before repo-changing hook events proceed.
# upstream implementation ../../tools/agent_tools/task_authority.py defines the shared schema.
# upstream implementation ./hook_event_log.py assigns Canon-owned hook log paths and IDs.
# downstream implementation ./hook_dispatcher.py invokes this hook for PostToolUse and Stop.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates schema guard behavior.
# @dependency-end
"""Validate task_authority.yaml for edit-like hook events."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
ROOT = HOOK_DIR.parents[1]
sys.path.insert(0, str(ROOT / "tools" / "agent_tools"))

from hook_event_log import HookLogContext, fingerprint_json, utc_now  # noqa: E402
from task_authority import (  # noqa: E402
    AUTHORITY_ENV,
    AuthorityFinding,
    load_task_authority,
    validate_authority_payload,
)

PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
LOG_PATH_ENV = "AGENT_CANON_TASK_AUTHORITY_HOOK_LOG_PATH"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
EDIT_TOOL_NAMES = {"apply_patch", "python", "python3", "Bash", "bash"}
GIT_TIMEOUT_SECONDS = 10


def load_payload() -> dict[str, object]:
    """Read one hook payload."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {PAYLOAD_STATUS_KEY: "empty"}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {PAYLOAD_STATUS_KEY: "invalid_json"}
    if isinstance(loaded, dict):
        loaded[PAYLOAD_STATUS_KEY] = "valid"
        return loaded
    return {PAYLOAD_STATUS_KEY: "invalid_json"}


def hook_event_name(payload: dict[str, object]) -> str:
    """Return hook event name."""
    value = payload.get("hookEventName")
    return value if isinstance(value, str) else ""


def tool_name(payload: dict[str, object]) -> str:
    """Return tool name."""
    value = payload.get("tool_name")
    return value if isinstance(value, str) else ""


def should_check(payload: dict[str, object]) -> bool:
    """Return whether this hook should inspect authority."""
    event = hook_event_name(payload)
    if event == "Stop":
        return True
    return event == "PostToolUse" and tool_name(payload) in EDIT_TOOL_NAMES


def repo_root() -> Path:
    """Return active repository root."""
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


def changed_files(root: Path) -> tuple[str, ...]:
    """Return changed paths visible to task-authority enforcement."""
    names: set[str] = set()
    for args in (
        ("diff", "--name-only", "--diff-filter=ACMRTD", "HEAD", "--"),
        ("diff", "--cached", "--name-only", "--diff-filter=ACMRTD", "--"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        if result.returncode == 0:
            names.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return tuple(sorted(path for path in names if not path.startswith("reports/agents/")))


def block_payload(findings: tuple[AuthorityFinding, ...]) -> dict[str, object]:
    """Return a blocking hook payload."""
    return {
        "decision": "block",
        "reason": "Task authority schema is missing or invalid for a repo-changing event.",
        "next_action": "create_or_fix_task_authority_yaml_then_retry",
        "remediation": [
            "Use the active run bundle task_authority.yaml as the request-local authority.",
            f"Set {AUTHORITY_ENV} when running a focused hook test outside a run bundle.",
            "Record allowed paths and risky authorities before repo edits.",
        ],
        "findings": [finding.render() for finding in findings],
    }


def maybe_log(context: HookLogContext, entry: dict[str, object]) -> None:
    """Append hook log unless disabled."""
    if not os.environ.get(DISABLE_LOG_ENV, "").strip():
        context.append(entry)


def main() -> int:
    """Run the task-authority schema guard."""
    payload = load_payload()
    if not should_check(payload):
        return 0
    root = repo_root()
    authority = load_task_authority(root)
    paths = changed_files(root)
    findings: list[AuthorityFinding] = []
    if authority is None:
        if paths:
            findings.append(AuthorityFinding("missing-authority", ",".join(paths[:5])))
    else:
        findings.extend(validate_authority_payload(authority.payload))
    context = HookLogContext(
        active_root=root,
        hook_name="task_authority_schema_guard",
        override_path=os.environ.get(LOG_PATH_ENV, ""),
    )
    timestamp = utc_now()
    maybe_log(
        context,
        {
            "hook_run_id": context.run_id(timestamp, fingerprint_json(payload)),
            "timestamp": timestamp,
            "event": hook_event_name(payload),
            "tool_name": tool_name(payload),
            "authority_path": str(authority.path) if authority else "",
            "changed_file_count": len(paths),
            "findings": [asdict(finding) for finding in findings],
            "status": "fail" if findings else "pass",
        },
    )
    if findings:
        print(json.dumps(block_payload(tuple(findings)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
