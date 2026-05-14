#!/usr/bin/env python3
# @dependency-start
# responsibility Runs helper-inventory hook checks using repo-owned policy thresholds.
# upstream implementation ../hooks.json invokes this hook for PostToolUse and Stop.
# upstream implementation ../../tools/agent_tools/helper_function_inventory.py provides changed/baseline helper findings.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates guard output.
# @dependency-end

"""Block new helper-inventory findings according to repo-local policy."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EDIT_TOOL_NAMES = {"apply_patch", "Bash", "bash", "python", "python3"}
EDIT_COMMAND_PATTERN = re.compile(
    r"(?is)(apply_patch|python3?\s+|ruff\s+--fix|python3?\s+-m\s+ruff\s+.*--fix|"
    r"git\s+mv|mv\s+|cp\s+|touch\s+|rm\s+|sed\s+-i|perl\s+-pi)"
)
POLICY_PATH_ENV = "AGENT_CANON_HELPER_INVENTORY_POLICY"
LOG_PATH_ENV = "AGENT_CANON_HELPER_INVENTORY_HOOK_LOG_PATH"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
PAYLOAD_STATUS_EMPTY = "empty"
PAYLOAD_STATUS_VALID = "valid"
PAYLOAD_STATUS_INVALID_JSON = "invalid_json"
TOOL_EVENT_FALLBACK = "PostToolUse"
DEFAULT_POLICY_PATH = "helper_inventory_guard_policy.json"
MAX_REASON_RECORDS = 8


def _load_payload() -> dict[str, object]:
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


def _payload_status(payload: dict[str, object]) -> str:
    value = payload.get(PAYLOAD_STATUS_KEY)
    return value if isinstance(value, str) else PAYLOAD_STATUS_VALID


def repo_root() -> Path:
    """Return the active Git repository root for helper inventory checks."""
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


def _tool_command(payload: dict[str, object]) -> str:
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


def _has_tool_signal(payload: dict[str, object]) -> bool:
    return isinstance(payload.get("tool_name"), str) or bool(_tool_command(payload))


def _uses_event_fallback(payload: dict[str, object]) -> bool:
    if isinstance(payload.get("hookEventName"), str):
        return False
    status = _payload_status(payload)
    return status == PAYLOAD_STATUS_VALID and _has_tool_signal(payload)


def _hook_event_name(payload: dict[str, object]) -> str:
    value = payload.get("hookEventName")
    if isinstance(value, str):
        return value
    if _uses_event_fallback(payload):
        return TOOL_EVENT_FALLBACK
    return ""


def _tool_name(payload: dict[str, object]) -> str:
    value = payload.get("tool_name")
    if isinstance(value, str):
        return value
    return ""


def _should_check(payload: dict[str, object]) -> bool:
    if _uses_event_fallback(payload) and not _has_tool_signal(payload):
        return True
    event = _hook_event_name(payload)
    if event == "Stop":
        return True
    if event != "PostToolUse":
        return False
    return _tool_name(payload) in EDIT_TOOL_NAMES or bool(
        EDIT_COMMAND_PATTERN.search(_tool_command(payload))
    )


def _policy_path(root: Path) -> Path:
    override = os.environ.get(POLICY_PATH_ENV, "").strip()
    return Path(override) if override else root / DEFAULT_POLICY_PATH


def _load_policy(root: Path) -> dict[str, object]:
    path = _policy_path(root)
    if not path.is_file():
        return {"enabled": False, "policy_path": str(path), "policy_status": "missing"}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "enabled": True,
            "policy_path": str(path),
            "policy_status": f"invalid:{type(exc).__name__}",
        }
    if not isinstance(loaded, dict):
        return {"enabled": True, "policy_path": str(path), "policy_status": "invalid"}
    loaded["policy_path"] = str(path)
    loaded["policy_status"] = "loaded"
    return loaded


def git_changed_python_paths(root: Path) -> list[str]:
    """Return changed Python paths that should be inspected by the hook."""
    names: set[str] = set()
    for args in (
        ["diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "--"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            names.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(name for name in names if name.endswith(".py"))


def _inventory_command(root: Path, policy: dict[str, object]) -> list[str]:
    tool = root / "tools" / "agent_tools" / "helper_function_inventory.py"
    baseline = str(policy.get("baseline_ref") or "HEAD")
    return [
        "python3",
        str(tool),
        "--root",
        str(root),
        "--changed",
        "--baseline-ref",
        baseline,
        "--format",
        "json",
    ]


def run_inventory(root: Path, policy: dict[str, object]) -> tuple[list[str], int, str]:
    """Run the helper inventory command and return command, status, and output."""
    command = _inventory_command(root, policy)
    if not Path(command[1]).is_file():
        return command, 0, json.dumps({"records": [], "tool_status": "missing"})
    result = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=int(policy.get("timeout_seconds") or 30),
    )
    return command, result.returncode, (result.stdout + result.stderr).strip()


def _records_from_output(output: str) -> list[dict[str, object]]:
    try:
        payload = json.loads(output or "{}")
    except json.JSONDecodeError:
        return []
    records = payload.get("records") if isinstance(payload, dict) else None
    return [record for record in records if isinstance(record, dict)] if isinstance(records, list) else []


def _is_tool_rule_gap(record: dict[str, object]) -> bool:
    haystack = " ".join(
        str(record.get(key, ""))
        for key in ("verdict", "judgment_rule", "candidate_rule", "role")
    )
    gap_tokens = ("tool_rule_gap", "role_gap", "general_role_gap", "domain_rule_gap")
    return any(token in haystack for token in gap_tokens)


def _domain_limit(policy: dict[str, object], domain: str, key: str) -> int:
    raw_limits = policy.get("domain_limits")
    if not isinstance(raw_limits, dict):
        return 0
    domain_limits = raw_limits.get(domain) or raw_limits.get("*") or {}
    if not isinstance(domain_limits, dict):
        return 0
    value = domain_limits.get(key)
    if isinstance(value, int):
        return value
    return 0


def _violating_records(
    records: list[dict[str, object]],
    policy: dict[str, object],
) -> tuple[list[dict[str, object]], dict[str, dict[str, int]]]:
    counts: dict[str, dict[str, int]] = {}
    for record in records:
        domain = str(record.get("domain") or "unknown")
        bucket = counts.setdefault(domain, {"needs_user_judgment": 0, "tool_rule_gap": 0})
        if bool(record.get("needs_user_judgment")):
            bucket["needs_user_judgment"] += 1
        if _is_tool_rule_gap(record):
            bucket["tool_rule_gap"] += 1

    violating_domains = {
        domain
        for domain, bucket in counts.items()
        if bucket["needs_user_judgment"]
        > _domain_limit(policy, domain, "max_needs_user_judgment")
        or bucket["tool_rule_gap"] > _domain_limit(policy, domain, "max_tool_rule_gap")
    }
    return [record for record in records if str(record.get("domain") or "unknown") in violating_domains], counts


def _default_log_path(root: Path) -> Path:
    override = os.environ.get(LOG_PATH_ENV, "").strip()
    return Path(override) if override else root / "reports" / "hooks" / "helper_inventory_guard.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _append_log(root: Path, entry: dict[str, object]) -> None:
    if os.environ.get(DISABLE_LOG_ENV, "").strip() == "1":
        return
    try:
        path = _default_log_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            json.dump(entry, stream, sort_keys=True)
            stream.write("\n")
    except OSError:
        return


def _reason(command: list[str], records: list[dict[str, object]], counts: dict[str, dict[str, int]]) -> str:
    lines = [
        "Helper inventory hook found new changed-file findings.",
        f"$ {' '.join(command)}",
        f"domain_counts={json.dumps(counts, sort_keys=True)}",
    ]
    for record in records[:MAX_REASON_RECORDS]:
        lines.append(
            "HELPER_INVENTORY_FINDING="
            f"{record.get('path')}:{record.get('line')}:"
            f"{record.get('domain')}:{record.get('qualname')}:"
            f"{record.get('judgment_rule') or record.get('candidate_rule')}"
        )
    return "\n".join(lines)


def main() -> int:
    """Run the helper inventory hook and block when policy thresholds fail."""
    payload = _load_payload()
    root = repo_root()
    if _payload_status(payload) == PAYLOAD_STATUS_EMPTY:
        return 0
    policy = _load_policy(root)
    changed_paths = git_changed_python_paths(root)
    checked = _should_check(payload) and bool(policy.get("enabled")) and bool(changed_paths)
    command: list[str] = []
    returncode = 0
    output = ""
    records: list[dict[str, object]] = []
    violations: list[dict[str, object]] = []
    counts: dict[str, dict[str, int]] = {}
    if checked:
        command, returncode, output = run_inventory(root, policy)
        records = _records_from_output(output)
        violations, counts = _violating_records(records, policy)
    _append_log(
        root,
        {
            "timestamp": _utc_now(),
            "event": _hook_event_name(payload),
            "tool_name": _tool_name(payload),
            "payload_status": _payload_status(payload),
            "checked": checked,
            "policy_status": policy.get("policy_status"),
            "policy_path": policy.get("policy_path"),
            "changed_python_count": len(changed_paths),
            "inventory_returncode": returncode,
            "records": len(records),
            "violations": len(violations),
            "status": "fail" if returncode != 0 or violations else "pass",
            "command": command,
            "domain_counts": counts,
        },
    )
    if returncode != 0:
        json.dump({"decision": "block", "reason": output}, sys.stdout)
        sys.stdout.write("\n")
    elif violations:
        json.dump({"decision": "block", "reason": _reason(command, violations, counts)}, sys.stdout)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
