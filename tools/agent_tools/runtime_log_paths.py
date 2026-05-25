#!/usr/bin/env python3
# @dependency-start
# responsibility Resolves AgentCanon runtime hook log archive paths without mutating repositories.
# upstream design ../../documents/runtime-log-archive.md runtime log archive ownership and branch policy
# downstream implementation ../../.codex/hooks/hook_event_log.py writes hook JSONL through this resolver
# downstream implementation ./generate_agent_improvement_guide.py reads mounted hook log archives
# downstream implementation ./eval_accumulation_check.py validates mounted hook log archives
# @dependency-end
"""Resolve AgentCanon runtime log archive paths."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

HOOK_ARCHIVE_DIR_ENV = "AGENT_CANON_HOOK_ARCHIVE_DIR"
LOG_ARCHIVE_MOUNT = Path(".agent-canon") / "log-archive"
LOG_ARCHIVE_REMOTE = "git@github.com:iwashita-nozomu/agent-canon-log.git"
NAMESPACE_HASH_LENGTH = 8
MAX_KEY_LENGTH = 80


def safe_slug(value: str) -> str:
    """Return a filesystem-safe lowercase path segment."""
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("._-").casefold()
    return slug[:MAX_KEY_LENGTH].strip("._-") or "unknown"


def short_hash(value: str) -> str:
    """Return a stable short hash for path-derived keys."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:NAMESPACE_HASH_LENGTH]


def repo_log_key(root: Path) -> str:
    """Return the source-repository key used inside the shared hook archive."""
    canonical = root.resolve()
    name = safe_slug(canonical.name or "repo")
    return f"{name}-{short_hash(str(canonical))}"


def mounted_log_archive_root(canon_root: Path) -> Path:
    """Return the preferred AgentCanon-local log archive mount path."""
    return canon_root / LOG_ARCHIVE_MOUNT


def state_log_archive_root() -> Path:
    """Return the non-repository fallback log archive root."""
    xdg_state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg_state_home:
        return Path(xdg_state_home) / "agent-canon" / "log-archive"
    home = os.environ.get("HOME", "").strip()
    if home:
        return Path(home) / ".local" / "state" / "agent-canon" / "log-archive"
    return Path(tempfile.gettempdir()) / "agent-canon" / "log-archive"


def log_archive_root(canon_root: Path) -> Path:
    """Return the active hook log archive root."""
    override = os.environ.get(HOOK_ARCHIVE_DIR_ENV, "").strip()
    if override:
        return Path(override)
    mount = mounted_log_archive_root(canon_root)
    if mount.is_dir():
        return mount
    return state_log_archive_root()


def hook_results_dir(active_root: Path, canon_root: Path) -> Path:
    """Return the hook JSONL result directory for one source repository."""
    return log_archive_root(canon_root) / "hook-runs" / repo_log_key(active_root)


def legacy_hook_results_dir(canon_root: Path) -> Path:
    """Return the historical in-tree hook result directory."""
    return canon_root / "agents" / "evals" / "results" / "hook-runs"


def hook_result_search_dirs(requested_root: Path, canon_root: Path) -> tuple[Path, ...]:
    """Return hook result directories to read for one repository context."""
    candidates: list[Path] = [
        hook_results_dir(requested_root, canon_root),
        legacy_hook_results_dir(canon_root),
    ]
    if requested_root.resolve() == canon_root.resolve():
        candidates.append(log_archive_root(canon_root) / "hook-runs" / "legacy-import")
    return tuple(dict.fromkeys(candidates))
