#!/usr/bin/env python3
# @dependency-start
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
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

AUTHORITY_FILE_NAME = "task_authority.yaml"
AUTHORITY_ENV = "AGENT_CANON_TASK_AUTHORITY"
ACTIVE_RUN_POINTER = Path("reports") / "agents" / ".active_run"
VALID_ACTIONS = {"add", "modify", "delete", "move", "rename", "write", "read"}
VALID_RISKY_AUTHORITY_KEYS = {
    "helper_change",
    "first_party_library_change",
    "public_api_change",
    "workflow_change",
    "shared_canon_change",
}


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
    payload: dict[str, Any]

    @property
    def active_role(self) -> str:
        """Return the active role recorded in the authority payload."""
        role = self.payload.get("active_role")
        return role if isinstance(role, str) else ""

    @property
    def allow_first_party_library_change(self) -> bool:
        """Return whether the task globally allows first-party library changes."""
        return self.payload.get("allow_first_party_library_change") is True

    def risky_entries(self, key: str) -> tuple[dict[str, Any], ...]:
        """Return risky authority entries for one key, including legacy aliases."""
        entries: list[object] = []
        risky = self.payload.get("risky_authorities")
        if isinstance(risky, dict):
            value = risky.get(key)
            if isinstance(value, list):
                entries.extend(value)
        alias_value = self.payload.get(f"{key}_authority")
        if isinstance(alias_value, list):
            entries.extend(alias_value)
        if key == "first_party_library_change":
            legacy = self.payload.get("library_change_authority")
            if isinstance(legacy, list):
                entries.extend(legacy)
        return tuple(cast(dict[str, Any], item) for item in entries if isinstance(item, dict))


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    """Load one YAML mapping."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return cast(dict[str, Any], raw)


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


def validate_authority_payload(payload: dict[str, Any]) -> tuple[AuthorityFinding, ...]:
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
    roles = payload.get("roles", {})
    if not isinstance(roles, dict):
        findings.append(AuthorityFinding("invalid-roles", "roles-must-be-mapping"))
    else:
        for role, policy in roles.items():
            if not isinstance(role, str) or not isinstance(policy, dict):
                findings.append(AuthorityFinding("invalid-role-entry", str(role)))
                continue
            if "can_modify_repo" in policy and not isinstance(policy["can_modify_repo"], bool):
                findings.append(AuthorityFinding("invalid-role-policy", f"{role}.can_modify_repo"))
    risky = payload.get("risky_authorities", {})
    if not isinstance(risky, dict):
        findings.append(AuthorityFinding("invalid-risky-authorities", "must-be-mapping"))
    else:
        for key, value in risky.items():
            if key not in VALID_RISKY_AUTHORITY_KEYS:
                findings.append(AuthorityFinding("unknown-risky-authority", str(key)))
            if not isinstance(value, list):
                findings.append(AuthorityFinding("invalid-risky-authority-list", str(key)))
    for entry in path_authority_entries(payload.get("allowed_paths", [])):
        actions = entry.get("actions", [])
        if not isinstance(actions, list) or not all(action in VALID_ACTIONS for action in actions):
            findings.append(AuthorityFinding("invalid-actions", str(entry.get("path", ""))))
    return tuple(findings)


def path_authority_entries(raw_entries: object) -> tuple[dict[str, Any], ...]:
    """Normalize path authority rows from strings or mappings."""
    if not isinstance(raw_entries, list):
        return ()
    entries: list[dict[str, Any]] = []
    for item in raw_entries:
        if isinstance(item, str):
            entries.append({"path": item, "actions": ["modify"]})
        elif isinstance(item, dict):
            entries.append(cast(dict[str, Any], item))
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


def entry_matches_path(entry: dict[str, Any], path: str) -> bool:
    """Return whether an authority entry applies to one path."""
    raw_patterns = entry.get("paths")
    patterns: list[str] = []
    if isinstance(raw_patterns, list):
        patterns.extend(str(pattern) for pattern in raw_patterns)
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
        qualnames = [str(item) for item in raw_qualnames] if isinstance(raw_qualnames, list) else []
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
    payload: dict[str, Any] = {
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
