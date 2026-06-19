#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Resolves AgentCanon runtime hook and eval archive paths without mutating repositories.
# upstream design ../../documents/runtime-log-archive.md runtime log archive ownership and branch policy
# downstream implementation ../../.codex/hooks/hook_event_log.py writes hook JSONL through this resolver
# downstream implementation ./generate_agent_improvement_guide.py reads mounted hook log archives
# downstream implementation ./export_codex_runtime_summary.py writes bounded Codex runtime summaries
# downstream implementation ./eval_accumulation_check.py validates mounted hook log archives
# downstream implementation ./runtime_log_archive_git.py archives run-bundle agent reports
# downstream implementation ./evaluate_skill_workflow_prompts.py writes accumulated eval reports through this resolver
# downstream implementation ./evaluate_workflow_selection.py writes accumulated eval reports through this resolver
# downstream implementation ./evaluate_report_quality.py writes accumulated eval reports through this resolver
# downstream implementation ./evaluate_codex_agent_roles.py writes accumulated eval reports through this resolver
# downstream implementation ./local_llm_eval.py writes accumulated eval reports through this resolver
# downstream implementation ./runtime_log_archive_git.py copies agent reports into this archive
# @dependency-end
"""Resolve AgentCanon runtime log and eval archive paths."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

HOOK_ARCHIVE_DIR_ENV = "AGENT_CANON_HOOK_ARCHIVE_DIR"
LOG_ENV_ENV = "AGENT_CANON_LOG_ENV"
LOG_ARCHIVE_PARENT = Path(".agent-canon") / "log-archive"
LOG_ARCHIVE_REMOTE = "git@github.com:iwashita-nozomu/agent-canon-log.git"
CODEX_RUNTIME_CHAT_DIR_NAME = "chats"
CODEX_RUNTIME_INDEX_FILE = "index.jsonl"
NAMESPACE_HASH_LENGTH = 8
MAX_KEY_LENGTH = 80
GIT_COMMIT_KEY_LENGTH = 12
CODEX_TRACE_ENV_NAMES = ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_CONVERSATION_ID")
GIT_HEAD_TIMEOUT_SECONDS = 5
AGENT_CANON_ROOT_MARKERS = (
    (Path("tools") / "agent_tools" / "runtime_log_paths.py", 2),
    (Path("tools") / "agent_tools" / "evaluate_skill_workflow_prompts.py", 2),
    (Path("evidence") / "agent-evals" / "README.md", 2),
    (Path("documents") / "runtime-log-archive.md", 1),
)


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


def _log_environment_key(root: Path) -> str:
    """Return the local environment key used by legacy mounted archives."""
    override = os.environ.get(LOG_ENV_ENV, "").strip()
    if override:
        return safe_slug(override)
    for env_name in ("DEVCONTAINER_PROJECT_NAME", "COMPOSE_PROJECT_NAME", "CODESPACE_NAME", "HOSTNAME"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return f"{safe_slug(value)}-{short_hash(str(root.resolve()))}"
    canonical = root.resolve()
    return f"{safe_slug(canonical.name or 'agent-canon')}-{short_hash(str(canonical))}"


def log_environment_key(root: Path) -> str:
    """Return the public local environment key used in archive context output."""
    return _log_environment_key(root)


def codex_trace_key() -> str:
    """Return the current Codex chat/session trace key when the runtime exposes one."""
    for env_name in CODEX_TRACE_ENV_NAMES:
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return ""


def log_chat_key(source_root: Path) -> str:
    """Return the chat key segment used by runtime log archive branches."""
    trace_key = codex_trace_key()
    if trace_key:
        return safe_slug(trace_key)
    return f"no-chat-{repo_log_key(source_root)}"


def log_branch_key(source_root: Path, canon_root: Path) -> str:
    """Return the environment-plus-chat key used for runtime log archive branches."""
    return f"{log_environment_key(canon_root)}-{log_chat_key(source_root)}"


def source_git_head(source_root: Path) -> str:
    """Return the source repository HEAD SHA when it is available."""
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "--verify", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_HEAD_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def agent_canon_git_commit_key(canon_root: Path) -> str:
    """Return the AgentCanon Git commit key used in runtime log filenames."""
    head = source_git_head(canon_root)
    return safe_slug(head[:GIT_COMMIT_KEY_LENGTH]) if head else "no-git-head"


def hook_log_file_name(hook_name: str, canon_root: Path) -> str:
    """Return the commit-keyed hook JSONL filename."""
    return f"{safe_slug(hook_name)}-{agent_canon_git_commit_key(canon_root)}.jsonl"


def codex_runtime_summary_file(canon_root: Path) -> str:
    """Return the commit-keyed Codex runtime summary filename."""
    return f"summary-{agent_canon_git_commit_key(canon_root)}.jsonl"


def mounted_log_archive_root(canon_root: Path) -> Path:
    """Return the preferred AgentCanon-local log archive mount path."""
    return canon_root / LOG_ARCHIVE_PARENT


def is_agent_canon_root(root: Path) -> bool:
    """Return whether a path looks like an AgentCanon checkout."""
    return any((root / marker).is_file() for marker, _depth in AGENT_CANON_ROOT_MARKERS)


def marker_resolved_root(root: Path) -> Path | None:
    """Return the real AgentCanon root behind a direct or symlinked runtime view."""
    for marker, depth in AGENT_CANON_ROOT_MARKERS:
        marker_path = root / marker
        if marker_path.is_file():
            return marker_path.resolve().parents[depth]
    return None


def agent_canon_root(root: Path) -> Path:
    """Return AgentCanon source root for standalone or parent invocation."""
    resolved = root.resolve()
    vendored = resolved / "vendor" / "agent-canon"
    if is_agent_canon_root(vendored):
        return vendored
    marker_root = marker_resolved_root(resolved)
    return marker_root if marker_root is not None else resolved


def _log_archive_root(canon_root: Path) -> Path:
    """Return the active hook log archive root."""
    override = os.environ.get(HOOK_ARCHIVE_DIR_ENV, "").strip()
    if override:
        return Path(override)
    mount = mounted_log_archive_root(canon_root)
    if mount.is_dir():
        return mount
    raise RuntimeError(
        "AgentCanon log archive root is required; set "
        f"{HOOK_ARCHIVE_DIR_ENV} or mount {mounted_log_archive_root(canon_root)}"
    )


def hook_results_dir(active_root: Path, canon_root: Path) -> Path:
    """Return the hook JSONL result directory for one source repository."""
    return _log_archive_root(canon_root) / "hook-runs" / repo_log_key(active_root)


def codex_runtime_summary_dir(active_root: Path, canon_root: Path) -> Path:
    """Return the Codex runtime summary root directory for one source repository."""
    return _log_archive_root(canon_root) / "codex-runtime" / repo_log_key(active_root)


def codex_runtime_chat_dir(active_root: Path, canon_root: Path, conversation_id: str) -> Path:
    """Return the per-chat Codex runtime summary directory for one conversation."""
    return (
        codex_runtime_summary_dir(active_root, canon_root)
        / CODEX_RUNTIME_CHAT_DIR_NAME
        / safe_slug(conversation_id)
    )


def codex_runtime_summary_path(active_root: Path, canon_root: Path, conversation_id: str) -> Path:
    """Return the per-chat Codex runtime summary JSONL path."""
    return codex_runtime_chat_dir(active_root, canon_root, conversation_id) / codex_runtime_summary_file(canon_root)


def codex_runtime_index_path(active_root: Path, canon_root: Path) -> Path:
    """Return the cross-chat Codex runtime summary index path."""
    return codex_runtime_summary_dir(active_root, canon_root) / CODEX_RUNTIME_INDEX_FILE


def agent_report_archive_dir(active_root: Path, canon_root: Path) -> Path:
    """Return the archived reports/agents directory for one source repository."""
    return _log_archive_root(canon_root) / "agent-reports" / repo_log_key(active_root)


def eval_results_dir(canon_root: Path, family: str) -> Path:
    """Return the active accumulated eval result directory for one family."""
    return _log_archive_root(canon_root) / "eval-results" / safe_slug(family)


def eval_result_search_dirs(canon_root: Path, family: str) -> tuple[Path, ...]:
    """Return eval result directories to read for one family."""
    family_slug = safe_slug(family)
    archive_root = _log_archive_root(canon_root)
    candidates: list[Path] = [
        archive_root / "eval-results" / family_slug,
        archive_root / "eval-results" / "legacy-import" / family_slug,
    ]
    return tuple(dict.fromkeys(candidates))


def hook_result_search_dirs(requested_root: Path, canon_root: Path) -> tuple[Path, ...]:
    """Return hook result directories to read for one repository context."""
    archive_root = _log_archive_root(canon_root)
    candidates: list[Path] = [
        archive_root / "hook-runs" / repo_log_key(requested_root),
        archive_root / "hook-runs" / "legacy-import",
        canon_root / "agents" / "evals" / "results" / "hook-runs",
        archive_root / "hook-runs",
    ]
    return tuple(dict.fromkeys(candidates))
