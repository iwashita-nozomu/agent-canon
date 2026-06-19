#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Runs helper-inventory hook checks using AgentCanon default and repo-local policy thresholds.
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
from datetime import UTC, datetime
from pathlib import Path

EDIT_TOOL_NAMES = {"apply_patch", "python", "python3"}
EDIT_COMMAND_PATTERN = re.compile(
    r"(?is)(apply_patch|ruff\s+--fix|python3?\s+-m\s+ruff\s+.*--fix|"
    r"git\s+mv|mv\s+|cp\s+|touch\s+|rm\s+|sed\s+-i|perl\s+-pi)"
)
POLICY_PATH_ENV = "AGENT_CANON_HELPER_INVENTORY_POLICY"
MODE_ENV = "AGENT_CANON_HELPER_INVENTORY_GUARD_MODE"
LOG_PATH_ENV = "AGENT_CANON_HELPER_INVENTORY_HOOK_LOG_PATH"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
READ_ONLY_COMMAND_PATTERN = re.compile(
    r"(?is)^\s*(git(?:\s+-C\s+\S+)?\s+(?:status|diff|show|log|branch|remote|"
    r"rev-parse|ls-files|submodule\s+status|fetch\b)|rg\b|sed\s+-n\b|cat\b|"
    r"ls\b|find\b|pwd\b|python3?\s+-m\s+ruff\s+(?:check|format)\b)"
)
PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
PAYLOAD_STATUS_EMPTY = "empty"
PAYLOAD_STATUS_VALID = "valid"
PAYLOAD_STATUS_INVALID_JSON = "invalid_json"
DEFAULT_POLICY_PATH = "helper_inventory_guard_policy.json"
DEFAULT_GUARD_MODE = "policy"
GUARD_MODES = {"policy", "block-new", "report", "off"}
MAX_REASON_RECORDS = 8
NON_BLOCKING_JUDGMENT_LIMIT = 1_000_000
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_DOMAIN_LIMITS = {
    "main": {
        "max_needs_user_judgment": 0,
        "max_tool_rule_gap": 0,
        "max_name_gap": 0,
    },
    "test": {
        "max_needs_user_judgment": NON_BLOCKING_JUDGMENT_LIMIT,
        "max_tool_rule_gap": 0,
        "max_name_gap": 0,
    },
    "experiment": {
        "max_needs_user_judgment": NON_BLOCKING_JUDGMENT_LIMIT,
        "max_tool_rule_gap": 0,
        "max_name_gap": 0,
    },
    "tooling": {
        "max_needs_user_judgment": NON_BLOCKING_JUDGMENT_LIMIT,
        "max_tool_rule_gap": 0,
        "max_name_gap": 0,
    },
    "*": {
        "max_needs_user_judgment": 0,
        "max_tool_rule_gap": 0,
        "max_name_gap": 0,
    },
}


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


def _hook_event_name(payload: dict[str, object]) -> str:
    value = payload.get("hookEventName")
    if isinstance(value, str):
        return value
    return ""


def _tool_name(payload: dict[str, object]) -> str:
    value = payload.get("tool_name")
    if isinstance(value, str):
        return value
    return ""


def _should_check(payload: dict[str, object]) -> bool:
    command = _tool_command(payload)
    if READ_ONLY_COMMAND_PATTERN.search(command):
        return False
    event = _hook_event_name(payload)
    if event == "Stop":
        return True
    if event != "PostToolUse":
        return False
    return _tool_name(payload) in EDIT_TOOL_NAMES or bool(EDIT_COMMAND_PATTERN.search(command))


def _policy_candidates(root: Path) -> list[tuple[Path, str]]:
    override = os.environ.get(POLICY_PATH_ENV, "").strip()
    if override:
        return [(Path(override), "override")]
    repo_policy = root / DEFAULT_POLICY_PATH
    return [(repo_policy, "repo-local")]


def _default_domain_limits() -> dict[str, dict[str, int]]:
    return {domain: dict(limits) for domain, limits in DEFAULT_DOMAIN_LIMITS.items()}


def _default_policy(path: Path, policy_status: str) -> dict[str, object]:
    return {
        "enabled": True,
        "mode": DEFAULT_GUARD_MODE,
        "baseline_ref": "HEAD",
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "domain_limits": _default_domain_limits(),
        "policy_path": str(path),
        "policy_status": policy_status,
    }


def _merge_domain_limits(raw_limits: object) -> dict[str, dict[str, int]]:
    merged = _default_domain_limits()
    if not isinstance(raw_limits, dict):
        return merged
    for domain, raw_domain_limits in raw_limits.items():
        if not isinstance(domain, str) or not isinstance(raw_domain_limits, dict):
            continue
        domain_limits = dict(merged.get(domain, {}))
        for key in ("max_needs_user_judgment", "max_tool_rule_gap", "max_name_gap"):
            value = raw_domain_limits.get(key)
            if isinstance(value, int):
                domain_limits[key] = value
        merged[domain] = domain_limits
    return merged


def _policy_with_defaults(
    loaded: dict[str, object],
    path: Path,
    policy_status: str,
) -> dict[str, object]:
    policy = _default_policy(path, policy_status)
    for key, value in loaded.items():
        if key != "domain_limits":
            policy[key] = value
    policy["domain_limits"] = _merge_domain_limits(loaded.get("domain_limits"))
    policy["policy_path"] = str(path)
    policy["policy_status"] = policy_status
    return policy


def _load_policy(root: Path) -> dict[str, object]:
    candidates = _policy_candidates(root)
    for path, scope in candidates:
        if not path.is_file():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"helper inventory policy is invalid: {path}: {type(exc).__name__}") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"helper inventory policy must be a JSON object: {path}")
        return _policy_with_defaults(loaded, path, scope)
    missing = ", ".join(str(path) for path, _scope in candidates)
    raise FileNotFoundError(f"helper inventory policy is required: {missing}")


def _guard_mode(policy: dict[str, object]) -> str:
    """Return helper guard behavior mode."""
    raw_mode = os.environ.get(MODE_ENV, "").strip() or str(policy.get("mode") or DEFAULT_GUARD_MODE)
    mode = raw_mode.strip().lower().replace("_", "-")
    return mode if mode in GUARD_MODES else DEFAULT_GUARD_MODE


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
        return command, 2, f"helper inventory command is required: {command[1]}"
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


def _is_name_gap(record: dict[str, object]) -> bool:
    """Return whether helper inventory selected a symbol for naming review."""
    return (
        record.get("searchable_name") is False
        or str(record.get("name_search_rule") or "").startswith("role-token-review:")
    )


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
    mode: str,
) -> tuple[list[dict[str, object]], dict[str, dict[str, int]]]:
    counts: dict[str, dict[str, int]] = {}
    for record in records:
        domain = str(record.get("domain") or "unknown")
        bucket = counts.setdefault(
            domain,
            {"needs_user_judgment": 0, "tool_rule_gap": 0, "name_gap": 0},
        )
        if bool(record.get("needs_user_judgment")):
            bucket["needs_user_judgment"] += 1
        if _is_tool_rule_gap(record):
            bucket["tool_rule_gap"] += 1
        if _is_name_gap(record):
            bucket["name_gap"] += 1

    if mode == "report":
        return [], counts
    if mode == "block-new":
        return [
            record
            for record in records
            if bool(record.get("needs_user_judgment"))
            or _is_tool_rule_gap(record)
            or _is_name_gap(record)
        ], counts

    violating_domains = {
        domain
        for domain, bucket in counts.items()
        if bucket["needs_user_judgment"]
        > _domain_limit(policy, domain, "max_needs_user_judgment")
        or bucket["tool_rule_gap"] > _domain_limit(policy, domain, "max_tool_rule_gap")
        or bucket["name_gap"] > _domain_limit(policy, domain, "max_name_gap")
    }
    return [record for record in records if str(record.get("domain") or "unknown") in violating_domains], counts


def _should_run_inventory(
    payload: dict[str, object],
    policy: dict[str, object],
    mode: str,
    changed_paths: list[str],
) -> bool:
    """Return whether the hook should invoke helper inventory."""
    if mode == "off" or not changed_paths or not _should_check(payload):
        return False
    if mode in {"block-new", "report"}:
        return True
    return bool(policy.get("enabled"))


def _default_log_path(root: Path) -> Path:
    override = os.environ.get(LOG_PATH_ENV, "").strip()
    return Path(override) if override else root / "reports" / "hooks" / "helper_inventory_guard.jsonl"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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
            f"{record.get('name_search_rule') or record.get('judgment_rule') or record.get('candidate_rule')}"
        )
    return "\n".join(lines)


def main() -> int:
    """Run the helper inventory hook and block when policy thresholds fail."""
    payload = _load_payload()
    root = repo_root()
    if _payload_status(payload) == PAYLOAD_STATUS_EMPTY:
        return 0
    if not _should_check(payload):
        return 0
    try:
        policy = _load_policy(root)
    except (FileNotFoundError, ValueError) as exc:
        _append_log(
            root,
            {
                "timestamp": _utc_now(),
                "event": _hook_event_name(payload),
                "tool_name": _tool_name(payload),
                "payload_status": _payload_status(payload),
                "checked": False,
                "policy_status": "error",
                "policy_error": str(exc),
                "status": "fail",
            },
        )
        json.dump(
            {
                "decision": "block",
                "reason": str(exc),
                "next_action": "repair_helper_inventory_policy_then_retry",
                "remediation": [
                    "Create helper_inventory_guard_policy.json at the active repository root or set AGENT_CANON_HELPER_INVENTORY_POLICY.",
                    "Re-run the helper inventory hook after the policy exists.",
                ],
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
        return 0
    mode = _guard_mode(policy)
    changed_paths = git_changed_python_paths(root)
    checked = _should_run_inventory(payload, policy, mode, changed_paths)
    command: list[str] = []
    returncode = 0
    output = ""
    records: list[dict[str, object]] = []
    violations: list[dict[str, object]] = []
    counts: dict[str, dict[str, int]] = {}
    if checked:
        command, returncode, output = run_inventory(root, policy)
        records = _records_from_output(output)
        violations, counts = _violating_records(records, policy, mode)
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
            "mode": mode,
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
        json.dump(
            {
                "decision": "block",
                "reason": output,
                "next_action": "fix_helper_inventory_command_then_retry",
                "remediation": [
                    "Run `python3 tools/agent_tools/helper_function_inventory.py --root . --changed --baseline-ref HEAD`.",
                    "Fix the inventory command failure before continuing helper-like edits.",
                ],
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
    elif violations:
        json.dump(
            {
                "decision": "block",
                "reason": _reason(command, violations, counts),
                "next_action": "reuse_or_justify_helper_like_additions",
                "remediation": [
                    "Reuse or extend existing helper surfaces when possible.",
                    "Add ownership and boundary evidence for remaining helper-like additions.",
                    "Re-run helper inventory before continuing.",
                ],
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
