#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
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
from task_authority import (  # noqa: E402
    ACTIVE_RUN_BASELINE_POINTER,
    ACTIVE_RUN_POINTER,
    TaskAuthority,
    authority_baseline_path,
    entry_matches_path,
    load_task_authority,
    path_authority_entries,
    path_changed_from_baseline,
)

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


def git_changed_files(root: Path) -> tuple[str, ...]:
    """Return all changed paths visible to hook enforcement."""
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
    return tuple(sorted(names))


def changed_files(root: Path) -> tuple[str, ...]:
    """Return changed repo paths excluding run artifacts."""
    return tuple(
        path for path in git_changed_files(root) if not path.startswith("reports/agents/")
    )


def relative_path(root: Path, path: Path) -> str:
    """Return a repo-relative path string when possible."""
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def active_role(root: Path) -> tuple[str, str, TaskAuthority | None]:
    """Resolve active role from env or task authority."""
    for env_name in ACTIVE_ROLE_ENVS:
        value = os.environ.get(env_name, "").strip()
        if value:
            authority = load_task_authority(root)
            return value, f"env:{env_name}", authority
    authority = load_task_authority(root)
    if authority is not None and authority.active_role:
        return authority.active_role, "task_authority", authority
    return "", "missing", authority


def task_authority_path_findings(
    authority: TaskAuthority,
    paths: tuple[str, ...],
) -> tuple[RoleWriteFinding, ...]:
    """Return request-local path-authority findings for changed repo paths."""
    if not paths:
        return ()
    findings: list[RoleWriteFinding] = []
    allowed_entries = path_authority_entries(authority.payload.get("allowed_paths", []))
    forbidden_entries = path_authority_entries(authority.payload.get("forbidden_paths", []))
    for path in paths:
        if any(entry_matches_path(entry, path) for entry in forbidden_entries):
            findings.append(RoleWriteFinding("task-authority-forbidden-path", path))
            continue
        if not any(entry_matches_path(entry, path) for entry in allowed_entries):
            findings.append(RoleWriteFinding("task-authority-path-violation", path))
    return tuple(findings)


def dirty_active_pointer_findings(
    root: Path,
    repo_paths: tuple[str, ...],
    all_paths: tuple[str, ...],
) -> tuple[RoleWriteFinding, ...]:
    """Return findings when an edit changes active-run pointer and repo files together."""
    if not repo_paths:
        return ()
    findings: list[RoleWriteFinding] = []
    dirty = set(all_paths)
    active_pointer = ACTIVE_RUN_POINTER.as_posix()
    baseline_changed = path_changed_from_baseline(
        root / ACTIVE_RUN_POINTER,
        root / ACTIVE_RUN_BASELINE_POINTER,
    )
    if active_pointer in dirty or baseline_changed:
        findings.append(RoleWriteFinding("active-run-pointer-mutated-with-repo-edit", active_pointer))
    return tuple(findings)


def dirty_authority_path_findings(
    root: Path,
    authority: TaskAuthority,
    repo_paths: tuple[str, ...],
    all_paths: tuple[str, ...],
) -> tuple[RoleWriteFinding, ...]:
    """Return findings when an edit changes authority file and repo files together."""
    if not repo_paths:
        return ()
    findings: list[RoleWriteFinding] = []
    dirty = set(all_paths)
    authority_rel = relative_path(root, authority.path)
    baseline_changed = path_changed_from_baseline(
        authority.path,
        authority_baseline_path(authority.path),
    )
    if authority_rel in dirty or baseline_changed:
        findings.append(RoleWriteFinding("authority-mutated-with-repo-edit", authority_rel))
    return tuple(findings)


def block_payload(findings: tuple[RoleWriteFinding, ...]) -> dict[str, object]:
    """Return a blocking hook payload."""
    return {
        "decision": "block",
        "reason": "Role write policy guard found repo edits outside the active role authority.",
        "next_action": "set_active_role_and_reduce_write_scope_then_retry",
        "remediation": [
            "Set AGENT_CANON_ACTIVE_ROLE or task_authority.yaml active_role for the current stage.",
            "Keep reviewer/designer/research roles artifact-only.",
            "For implementer edits, update task_authority.yaml allowed_paths, team_manifest.yaml write scope, or shrink the edit.",
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
    all_paths = git_changed_files(root)
    paths = changed_files(root)
    role, role_source, authority = active_role(root)
    authority_path = authority.path if authority is not None else None
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
        if authority is not None:
            findings.extend(task_authority_path_findings(authority, paths))
            findings.extend(dirty_authority_path_findings(root, authority, paths, all_paths))
    findings.extend(dirty_active_pointer_findings(root, paths, all_paths))
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
