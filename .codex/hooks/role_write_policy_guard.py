#!/usr/bin/env python3
# @dependency-start
# responsibility Enforces active role write policy against current repository changes.
# upstream implementation ../../tools/agent_tools/task_authority.py locates request-local authority.
# upstream implementation ../../tools/agent_tools/agent_team.py validates role write scope.
# downstream implementation ./hook_dispatcher.py invokes this hook for PostToolUse and Stop.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates role write policy behavior.
# @dependency-end
"""Enforce AgentCanon role write policies for edit-like hook events."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
ROOT = HOOK_DIR.parents[1]
sys.path.insert(0, str(ROOT / "tools" / "agent_tools"))

from agent_team import load_team_config, validate_role_write_scope  # noqa: E402
from hook_event_log import HookLogContext, fingerprint_json, utc_now  # noqa: E402
from task_authority import load_task_authority  # noqa: E402

PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
LOG_PATH_ENV = "AGENT_CANON_ROLE_WRITE_POLICY_HOOK_LOG_PATH"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
ACTIVE_ROLE_ENVS = ("AGENT_CANON_ACTIVE_ROLE", "AGENT_CANON_ROLE")
EDIT_TOOL_NAMES = {"apply_patch", "python", "python3", "Bash", "bash"}
GIT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class RoleWriteFinding:
    """One role write policy finding."""

    code: str
    detail: str

    def render(self) -> str:
        """Render a stable finding line."""
        return f"ROLE_WRITE_POLICY_FINDING={self.code}:{self.detail}"


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
    """Return whether this hook should inspect role write scope."""
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
    """Return changed repo paths excluding run artifacts."""
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


def active_role(root: Path) -> tuple[str, str, Path | None]:
    """Resolve active role from env or task authority."""
    for env_name in ACTIVE_ROLE_ENVS:
        value = os.environ.get(env_name, "").strip()
        if value:
            authority = load_task_authority(root)
            return value, f"env:{env_name}", authority.path if authority else None
    authority = load_task_authority(root)
    if authority is not None and authority.active_role:
        return authority.active_role, "task_authority", authority.path
    return "", "missing", authority.path if authority else None


def block_payload(findings: tuple[RoleWriteFinding, ...]) -> dict[str, object]:
    """Return a blocking hook payload."""
    return {
        "decision": "block",
        "reason": "Role write policy guard found repo edits outside the active role authority.",
        "next_action": "set_active_role_and_reduce_write_scope_then_retry",
        "remediation": [
            "Set AGENT_CANON_ACTIVE_ROLE or task_authority.yaml active_role for the current stage.",
            "Keep reviewer/designer/research roles artifact-only.",
            "For implementer edits, add a WORKTREE_SCOPE.md editable directory or shrink the edit.",
        ],
        "findings": [finding.render() for finding in findings],
    }


def maybe_log(context: HookLogContext, entry: dict[str, object]) -> None:
    """Append hook log unless disabled."""
    if not os.environ.get(DISABLE_LOG_ENV, "").strip():
        context.append(entry)


def main() -> int:
    """Run the role write policy guard."""
    payload = load_payload()
    if not should_check(payload):
        return 0
    root = repo_root()
    paths = changed_files(root)
    role, role_source, authority_path = active_role(root)
    findings: list[RoleWriteFinding] = []
    violations: tuple[Path, ...] = ()
    if paths and not role:
        findings.append(RoleWriteFinding("missing-active-role", ",".join(paths[:5])))
    elif role:
        report_dir = authority_path.parent if authority_path is not None else root / "reports" / "agents" / "_unknown"
        try:
            _, violations = validate_role_write_scope(
                config=load_team_config(),
                role_name=role,
                report_dir=report_dir,
                workspace_root=root,
                files=tuple(Path(path) for path in paths),
            )
        except Exception as exc:  # noqa: BLE001 - hook reports schema/config failures as guard findings.
            findings.append(RoleWriteFinding("role-scope-check-error", f"{type(exc).__name__}:{exc}"))
        findings.extend(
            RoleWriteFinding("write-scope-violation", str(path))
            for path in violations
        )
    context = HookLogContext(
        active_root=root,
        hook_name="role_write_policy_guard",
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
            "active_role": role,
            "active_role_source": role_source,
            "authority_path": str(authority_path or ""),
            "changed_file_count": len(paths),
            "violations": [str(path) for path in violations],
            "finding_count": len(findings),
            "status": "fail" if findings else "pass",
        },
    )
    if findings:
        print(json.dumps(block_payload(tuple(findings)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
