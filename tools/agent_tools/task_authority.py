#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Loads and validates request-local task authority for hooks and subagent handoffs.
# upstream design ../../agents/agents_config.json defines role write policies.
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md requires request clauses before repo edits.
# downstream implementation ../../.codex/hooks/task_authority_schema_guard.py blocks malformed authority.
# downstream implementation ../../.codex/hooks/role_write_policy_guard.py enforces role write scope.
# downstream implementation ../../.codex/hooks/helper_first_guard.py consumes helper change authority.
# downstream implementation ../../.codex/hooks/first_party_library_guard.py consumes first-party library authority.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates hook integration.
# downstream implementation ../../tests/agent_tools/test_task_start_and_close.py validates bundle generation.
# @dependency-end
"""Request-local task authority helpers shared by AgentCanon hooks."""

from __future__ import annotations

import fnmatch
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias, cast

import yaml

AUTHORITY_FILE_NAME = "task_authority.yaml"
AUTHORITY_ENV = "AGENT_CANON_TASK_AUTHORITY"
ACTIVE_RUN_POINTER = Path("reports") / "agents" / ".active_run"
ACTIVE_RUN_BASELINE_POINTER = Path("reports") / "agents" / ".active_run.sha256"
AUTHORITY_BASELINE_SUFFIX = ".sha256"
VALID_ACTIONS = {"add", "modify", "delete", "move", "rename", "write", "read"}
VALID_RISKY_AUTHORITY_KEYS = {
    "helper_change",
    "first_party_library_change",
    "public_api_change",
    "workflow_change",
    "shared_canon_change",
}
AuthorityPayload: TypeAlias = dict[str, object]
AuthorityEntry: TypeAlias = dict[str, object]


@dataclass(frozen=True)
class AuthorityFinding:
    """One validation finding from task authority."""

    code: str
    detail: str

    def render(self) -> str:
        """Render a stable finding line."""
        return f"TASK_AUTHORITY_FINDING={self.code}:{self.detail}"


@dataclass(frozen=True)
class TaskAuthority:
    """Loaded task authority payload plus its source path."""

    path: Path
    payload: AuthorityPayload

    @property
    def active_role(self) -> str:
        """Return the active role recorded in the authority payload."""
        role = self.payload.get("active_role")
        return role if isinstance(role, str) else ""

    @property
    def allow_first_party_library_change(self) -> bool:
        """Return whether the task globally allows first-party library changes."""
        return self.payload.get("allow_first_party_library_change") is True

    def risky_entries(self, key: str) -> tuple[AuthorityEntry, ...]:
        """Return risky authority entries for one key, including legacy aliases."""
        entries: list[object] = []
        risky = object_mapping(self.payload.get("risky_authorities"))
        value = risky.get(key)
        if isinstance(value, list):
            entries.extend(cast(list[object], value))
        alias_value = self.payload.get(f"{key}_authority")
        if isinstance(alias_value, list):
            entries.extend(cast(list[object], alias_value))
        if key == "first_party_library_change":
            legacy = self.payload.get("library_change_authority")
            if isinstance(legacy, list):
                entries.extend(cast(list[object], legacy))
        return tuple(cast(AuthorityEntry, item) for item in entries if isinstance(item, dict))


def load_yaml_mapping(path: Path) -> AuthorityPayload:
    """Load one YAML mapping."""
    raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return cast(AuthorityPayload, raw)


def object_mapping(value: object) -> dict[object, object]:
    """Return a typed object mapping when YAML produced one."""
    return cast(dict[object, object], value) if isinstance(value, dict) else {}


def object_list(value: object) -> list[object]:
    """Return a typed object list when YAML produced one."""
    return cast(list[object], value) if isinstance(value, list) else []


def file_sha256(path: Path) -> str:
    """Return the SHA-256 hash of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def authority_baseline_path(authority_path: Path) -> Path:
    """Return the immutable baseline sidecar path for one authority file."""
    return authority_path.with_name(authority_path.name + AUTHORITY_BASELINE_SUFFIX)


def write_hash_baseline(path: Path, baseline_path: Path) -> None:
    """Write a hash baseline sidecar for a runtime authority file."""
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(file_sha256(path) + "\n", encoding="utf-8")


def path_changed_from_baseline(path: Path, baseline_path: Path) -> bool:
    """Return whether a runtime authority file differs from its baseline sidecar."""
    if not path.is_file() or not baseline_path.is_file():
        return False
    expected = baseline_path.read_text(encoding="utf-8").strip()
    return bool(expected) and file_sha256(path) != expected


def write_task_authority_baselines(report_dir: Path, report_root: Path) -> None:
    """Write baselines for active-run pointer and task authority after bootstrap."""
    active_pointer = report_root / ACTIVE_RUN_POINTER.name
    if active_pointer.is_file():
        active_baseline = active_pointer.with_name(ACTIVE_RUN_BASELINE_POINTER.name)
        write_hash_baseline(active_pointer, active_baseline)
    authority_path = report_dir / AUTHORITY_FILE_NAME
    if authority_path.is_file():
        write_hash_baseline(authority_path, authority_baseline_path(authority_path))


def find_authority_path(root: Path) -> Path | None:
    """Find the explicitly request-local authority file for the current run."""
    override = os.environ.get(AUTHORITY_ENV, "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else (root / path)
    pointer = root / ACTIVE_RUN_POINTER
    if pointer.is_file():
        active = pointer.read_text(encoding="utf-8").strip()
        if active:
            run_dir = Path(active)
            if not run_dir.is_absolute():
                run_dir = root / run_dir
            candidate = run_dir / AUTHORITY_FILE_NAME
            if candidate.is_file():
                return candidate
    return None


def load_task_authority(root: Path) -> TaskAuthority | None:
    """Load task authority when it exists."""
    path = find_authority_path(root)
    if path is None or not path.is_file():
        return None
    return TaskAuthority(path=path.resolve(), payload=load_yaml_mapping(path))


def validate_role_policies(raw_roles: object) -> tuple[AuthorityFinding, ...]:
    """Validate task-authority role policy rows."""
    if not isinstance(raw_roles, dict):
        return (AuthorityFinding("invalid-roles", "roles-must-be-mapping"),)
    findings: list[AuthorityFinding] = []
    for role, policy in cast(dict[object, object], raw_roles).items():
        if not isinstance(role, str) or not isinstance(policy, dict):
            findings.append(AuthorityFinding("invalid-role-entry", str(role)))
            continue
        policy_mapping = cast(dict[object, object], policy)
        if "can_modify_repo" in policy_mapping and not isinstance(policy_mapping["can_modify_repo"], bool):
            findings.append(AuthorityFinding("invalid-role-policy", f"{role}.can_modify_repo"))
    return tuple(findings)


def validate_risky_authorities(raw_risky: object) -> tuple[AuthorityFinding, ...]:
    """Validate risky-authority policy rows."""
    if not isinstance(raw_risky, dict):
        return (AuthorityFinding("invalid-risky-authorities", "must-be-mapping"),)
    findings: list[AuthorityFinding] = []
    for key, value in cast(dict[object, object], raw_risky).items():
        if key not in VALID_RISKY_AUTHORITY_KEYS:
            findings.append(AuthorityFinding("unknown-risky-authority", str(key)))
        if not isinstance(value, list):
            findings.append(AuthorityFinding("invalid-risky-authority-list", str(key)))
    return tuple(findings)


def validate_allowed_path_actions(raw_allowed_paths: object) -> tuple[AuthorityFinding, ...]:
    """Validate allowed-path action names."""
    findings: list[AuthorityFinding] = []
    for entry in path_authority_entries(raw_allowed_paths):
        actions = entry.get("actions", [])
        action_values = cast(list[object], actions) if isinstance(actions, list) else []
        if not isinstance(actions, list) or not all(action in VALID_ACTIONS for action in action_values):
            findings.append(AuthorityFinding("invalid-actions", str(entry.get("path", ""))))
    return tuple(findings)


def validate_authority_payload(payload: AuthorityPayload) -> tuple[AuthorityFinding, ...]:
    """Validate the shared task authority schema."""
    findings: list[AuthorityFinding] = []
    if payload.get("version") != 1:
        findings.append(AuthorityFinding("invalid-version", "version-must-be-1"))
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        findings.append(AuthorityFinding("missing-run-id", "run_id"))
    for key in ("request_clauses", "allowed_paths", "forbidden_paths"):
        value = payload.get(key, [])
        if not isinstance(value, list):
            findings.append(AuthorityFinding("invalid-list", key))
    findings.extend(validate_role_policies(payload.get("roles", {})))
    findings.extend(validate_risky_authorities(payload.get("risky_authorities", {})))
    findings.extend(validate_allowed_path_actions(payload.get("allowed_paths", [])))
    return tuple(findings)


def path_authority_entries(raw_entries: object) -> tuple[AuthorityEntry, ...]:
    """Normalize path authority rows from strings or mappings."""
    if not isinstance(raw_entries, list):
        return ()
    entries: list[AuthorityEntry] = []
    for item in cast(list[object], raw_entries):
        if isinstance(item, str):
            entries.append({"path": item, "actions": ["modify"]})
        elif isinstance(item, dict):
            entries.append(cast(AuthorityEntry, item))
    return tuple(entries)


def pattern_covers(pattern: str, path: str) -> bool:
    """Return whether one authority pattern covers one repository path."""
    normalized_pattern = pattern.strip().lstrip("./")
    normalized_path = path.strip().lstrip("./")
    if normalized_pattern == normalized_path:
        return True
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern.removesuffix("/**").rstrip("/")
        return normalized_path == prefix or normalized_path.startswith(prefix + "/")
    return fnmatch.fnmatch(normalized_path, normalized_pattern)


def entry_matches_path(entry: AuthorityEntry, path: str) -> bool:
    """Return whether an authority entry applies to one path."""
    raw_patterns = entry.get("paths")
    patterns: list[str] = []
    if isinstance(raw_patterns, list):
        patterns.extend(str(pattern) for pattern in cast(list[object], raw_patterns))
    raw_path = entry.get("path")
    if isinstance(raw_path, str):
        patterns.append(raw_path)
    return any(pattern_covers(pattern, path) for pattern in patterns)


def helper_authority_matches(
    authority: TaskAuthority | None,
    *,
    path: str,
    qualname: str,
) -> tuple[bool, str]:
    """Return whether helper authority matches a helper record."""
    if authority is None:
        return False, "authority:missing"
    for entry in authority.risky_entries("helper_change"):
        if not entry_matches_path(entry, path):
            continue
        raw_qualnames = entry.get("qualnames")
        qualnames = [str(item) for item in cast(list[object], raw_qualnames)] if isinstance(raw_qualnames, list) else []
        raw_qualname = entry.get("qualname")
        if isinstance(raw_qualname, str):
            qualnames.append(raw_qualname)
        if qualnames and qualname not in qualnames:
            continue
        required = ("owning_module", "caller_paths", "existing_helper_gap", "tests")
        missing = [key for key in required if key not in entry or entry.get(key) in ("", [], None)]
        if missing:
            return False, f"authority:{entry.get('id', '<unknown>')}:missing:{','.join(missing)}"
        return True, f"authority:{entry.get('id', '<unknown>')}:matched"
    return False, "authority:no-matching-helper-entry"


def first_party_library_authorized(
    authority: TaskAuthority | None,
    path: str,
) -> tuple[bool, str]:
    """Return whether first-party library/API change is authorized for a path."""
    if authority is None:
        return False, "authority:missing"
    if authority.allow_first_party_library_change:
        return True, "authority:global-first-party-library-change"
    for entry in authority.risky_entries("first_party_library_change"):
        if not entry_matches_path(entry, path):
            continue
        required = ("reason", "affected_callers", "tests")
        missing = [key for key in required if key not in entry or entry.get(key) in ("", [], None)]
        if missing:
            return False, f"authority:{entry.get('id', '<unknown>')}:missing:{','.join(missing)}"
        return True, f"authority:{entry.get('id', '<unknown>')}:matched"
    return False, "authority:no-matching-library-entry"


def build_default_task_authority(
    *,
    run_id: str,
    task: str,
    roles: dict[str, bool],
) -> str:
    """Render a conservative default task authority document."""
    payload: AuthorityPayload = {
        "version": 1,
        "run_id": run_id,
        "task": task,
        "active_role": "",
        "request_clauses": [],
        "allowed_paths": [],
        "forbidden_paths": [
            {"path": "vendor/**", "reason": "external-or-submodule-surface"},
        ],
        "allow_first_party_library_change": False,
        "risky_authorities": {
            "helper_change": [],
            "first_party_library_change": [],
            "public_api_change": [],
            "workflow_change": [],
            "shared_canon_change": [],
        },
        "roles": {
            role_id: {"can_modify_repo": can_modify_repo}
            for role_id, can_modify_repo in roles.items()
        },
    }
    return yaml.safe_dump(payload, sort_keys=False)
