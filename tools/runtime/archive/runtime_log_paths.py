#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Resolves AgentCanon runtime hook and eval archive paths without mutating repositories.
# upstream design ../../documents/runtime/runtime-log-archive.md runtime log archive ownership and branch policy
# downstream implementation ../../.codex/hooks/hook_event_log.py writes hook JSONL through this resolver
# downstream implementation ./generate_agent_improvement_guide.py reads mounted hook log archives
# downstream implementation ./export_codex_runtime_summary.py writes bounded Codex runtime summaries
# downstream implementation ./eval_accumulation_check.py validates mounted hook log archives
# downstream implementation ./runtime_log_archive_git.py archives run-bundle agent reports
# downstream implementation ./evaluate_skill_workflow_prompts.py writes accumulated eval reports through this resolver
# downstream implementation ./evaluate_workflow_selection.py writes accumulated eval reports through this resolver
# downstream implementation ./evaluate_report_quality.py writes accumulated eval reports through this resolver
# downstream implementation ./evaluate_codex_agent_roles.py writes accumulated eval reports through this resolver
# downstream implementation ./runtime_log_archive_git.py copies agent reports into this archive
# @dependency-end
"""Resolve AgentCanon runtime log and eval archive paths."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

try:
    from tools.runtime.artifacts.runtime_artifacts import (
        RUNTIME_ROOT_ENV,
        RuntimeArtifactBoundary,
        RuntimePathEscape,
        runtime_artifact_boundary,
        runtime_spool_boundary,
    )
except ImportError:
    from tools.runtime.artifacts.runtime_artifacts import (  # type: ignore[no-redef]
        RUNTIME_ROOT_ENV,
        RuntimeArtifactBoundary,
        RuntimePathEscape,
        runtime_artifact_boundary,
        runtime_spool_boundary,
    )

try:
    from .log_repository_identity import (
        SourceRepositoryIdentityError,
        stable_source_id,
        stable_source_id_from_runtime_env,
    )
except ImportError:
    from tools.runtime.archive.log_repository_identity import (
        SourceRepositoryIdentityError,
        stable_source_id,
        stable_source_id_from_runtime_env,
    )

HOOK_ARCHIVE_DIR_ENV = "AGENT_CANON_HOOK_ARCHIVE_DIR"
HOOK_EVENT_SPOOL_DIR_ENV = "AGENT_CANON_HOOK_EVENT_SPOOL_DIR"
LOG_ENV_ENV = "AGENT_CANON_LOG_ENV"
LOG_ARCHIVE_PARENT = Path("archive") / "agent-canon-log"
LOG_ARCHIVE_REMOTE = "git@github.com:iwashita-nozomu/agent-canon-log.git"
PRIVATE_LOG_ROOT_ENV = "AGENT_CANON_LOG_ROOT"
CODEX_RUNTIME_CHAT_DIR_NAME = "chats"
CODEX_RUNTIME_INDEX_FILE = "index.jsonl"
NAMESPACE_HASH_LENGTH = 8
MAX_KEY_LENGTH = 80
GIT_COMMIT_KEY_LENGTH = 12
CODEX_TRACE_ENV_NAMES = ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_CONVERSATION_ID")
GIT_HEAD_TIMEOUT_SECONDS = 5
AGENT_CANON_ROOT_MARKERS = (
    (Path("tools") / "runtime" / "archive" / "runtime_log_paths.py", 2),
    (Path("eval") / "producers" / "evaluate_skill_workflow_prompts.py", 2),
    (Path("eval") / "definitions" / "README.md", 2),
    (Path("documents") / "runtime-log-archive.md", 1),
)


def safe_slug(value: str) -> str:
    """Return a filesystem-safe lowercase path segment."""
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("._-").casefold()
    return slug[:MAX_KEY_LENGTH].strip("._-") or "unknown"


def short_hash(value: str) -> str:
    """Return a stable short hash for non-identity local namespace details."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:NAMESPACE_HASH_LENGTH]


def repo_log_key(root: Path) -> str:
    """Return the source-repository key from the normalized Git remote identity."""
    try:
        return stable_source_id_from_runtime_env(root)
    except SourceRepositoryIdentityError:
        # Hook spooling remains local and non-blocking when a checkout is not a
        # Git clone; write routes fail with the typed identity error instead.
        return "unidentified-source"


def runtime_boundary(
    source_root: Path,
    runtime_root: Path | str | None = None,
    *,
    create: bool = False,
) -> RuntimeArtifactBoundary:
    """Return the explicit external runtime boundary for one source root."""
    return runtime_artifact_boundary(source_root, runtime_root, create=create)


def hook_event_spool_root(active_root: Path, runtime_root: Path | str | None = None) -> Path:
    """Return the O(1) repo-owned hook-event spool root."""
    override = os.environ.get(HOOK_EVENT_SPOOL_DIR_ENV, "").strip()
    if override:
        candidate = Path(override) / repo_log_key(active_root)
        # Explicit legacy override remains accepted only when it is inside the
        # declared external runtime root.
        boundary = runtime_spool_boundary(active_root, runtime_root)
        return boundary.resolve(candidate)
    boundary = runtime_spool_boundary(active_root, runtime_root)
    return boundary.resolve(Path("spool") / "hook-events" / repo_log_key(active_root))


def runtime_event_publication_outcome_spool_root(
    active_root: Path, runtime_root: Path | str | None = None
) -> Path:
    """Return the repo-local publication-outcome observation spool root."""
    boundary = runtime_spool_boundary(active_root, runtime_root)
    return boundary.resolve(Path("spool") / "publication-outcome")


def post_tooluse_spool_path(
    root: Path, hook_run_id: str, runtime_root: Path | str | None = None
) -> Path:
    """Return the O(1) default PostToolUse event path."""
    return hook_event_spool_root(root, runtime_root) / "post-tool-use" / "hook" / f"{hook_run_id}.json"


def _log_environment_key(root: Path) -> str:
    """Return the local environment key used by legacy mounted archives."""
    override = os.environ.get(LOG_ENV_ENV, "").strip()
    if override:
        return safe_slug(override)
    for env_name in ("DEVCONTAINER_PROJECT_NAME", "COMPOSE_PROJECT_NAME", "CODESPACE_NAME", "HOSTNAME"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return safe_slug(value)
    canonical = root.resolve()
    return safe_slug(canonical.name or "agent-canon")


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
    """Return the chat metadata key; it is never used for branch identity."""
    trace_key = codex_trace_key()
    if trace_key:
        return safe_slug(trace_key)
    return f"no-chat-{repo_log_key(source_root)}"


def log_branch_key(source_root: Path, canon_root: Path) -> str:
    """Return the stable source identity key used by agent-canon-log."""
    return stable_source_id(source_root)


def source_git_head(source_root: Path) -> str:
    """Return HEAD only when ``source_root`` is the repository root itself.

    ``git -C`` normally walks through parent directories.  Runtime exchange
    directories frequently live below a different checkout, so accepting that
    discovery would attribute the enclosing control repository's commit to a
    source that is not a Git checkout.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(source_root),
                "rev-parse",
                "--show-toplevel",
                "--verify",
                "HEAD",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_HEAD_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    lines = result.stdout.splitlines()
    if result.returncode != 0 or len(lines) != 2:
        return ""
    try:
        discovered_root = Path(lines[0]).resolve(strict=True)
        requested_root = source_root.resolve(strict=True)
    except OSError:
        return ""
    return lines[1].strip() if discovered_root == requested_root else ""


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


def mounted_log_archive_root(
    canon_root: Path, runtime_root: Path | str | None = None
) -> Path:
    """Return the external AgentCanon log archive root."""
    boundary = runtime_boundary(canon_root, runtime_root)
    return boundary.resolve(LOG_ARCHIVE_PARENT)


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
    """Return the explicit AgentCanon source root for one invocation.

    Parent repositories are intentionally source-free.  A caller running from
    a parent must pass the external development clone as ``root`` (or resolve
    it before calling this helper); no ``vendor/agent-canon`` discovery is
    permitted.
    """
    resolved = root.resolve()
    marker_root = marker_resolved_root(resolved)
    return marker_root if marker_root is not None else resolved


def _log_archive_root(canon_root: Path, runtime_root: Path | str | None = None) -> Path:
    """Return the active hook log archive root."""
    override = os.environ.get(HOOK_ARCHIVE_DIR_ENV, "").strip()
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_absolute():
            return runtime_boundary(canon_root, runtime_root).resolve(candidate)
        try:
            if candidate.is_symlink():
                raise RuntimePathEscape(f"explicit archive root is a symlink: {candidate}")
            resolved = candidate.resolve(strict=False)
            source = canon_root.expanduser().resolve()
            declared = os.environ.get(PRIVATE_LOG_ROOT_ENV, "").strip()
            if not declared or Path(declared).expanduser().resolve(strict=False) != resolved:
                raise RuntimePathEscape(
                    "absolute archive override must equal the declared private-log mount root"
                )
            current = Path(candidate.anchor or "/")
            for part in candidate.parts[1:]:
                current /= part
                if current.is_symlink():
                    raise RuntimePathEscape(f"explicit archive root has a symlink component: {current}")
        except OSError as exc:
            raise RuntimePathEscape(f"explicit archive root is unavailable: {candidate}") from exc
        if resolved == source or source in resolved.parents:
            raise RuntimePathEscape(f"explicit archive root is inside source: {resolved}")
        return resolved
    mount = mounted_log_archive_root(canon_root, runtime_root)
    if mount.is_dir():
        return mount
    if runtime_root is not None or os.environ.get(RUNTIME_ROOT_ENV, "").strip():
        # A fresh runtime generation is intentionally allowed to materialize
        # its archive lazily. The writer owns directory creation through the
        # RuntimeArtifactBoundary; readers simply observe an empty directory.
        return mount
    raise RuntimeError(
        "AgentCanon log archive root is required; set "
        f"{HOOK_ARCHIVE_DIR_ENV} or configure {RUNTIME_ROOT_ENV}"
    )


def hook_results_dir(
    active_root: Path, canon_root: Path, runtime_root: Path | str | None = None
) -> Path:
    """Return the hook JSONL result directory for one source repository."""
    return _log_archive_root(canon_root, runtime_root) / "hook-runs" / repo_log_key(active_root)


def codex_runtime_summary_dir(
    active_root: Path, canon_root: Path, runtime_root: Path | str | None = None
) -> Path:
    """Return the Codex runtime summary root directory for one source repository."""
    return _log_archive_root(canon_root, runtime_root) / "codex-runtime" / repo_log_key(active_root)


def codex_runtime_chat_dir(
    active_root: Path,
    canon_root: Path,
    conversation_id: str,
    runtime_root: Path | str | None = None,
) -> Path:
    """Return the per-chat Codex runtime summary directory for one conversation."""
    return (
        codex_runtime_summary_dir(active_root, canon_root, runtime_root)
        / CODEX_RUNTIME_CHAT_DIR_NAME
        / safe_slug(conversation_id)
    )


def codex_runtime_summary_path(
    active_root: Path,
    canon_root: Path,
    conversation_id: str,
    runtime_root: Path | str | None = None,
) -> Path:
    """Return the per-chat Codex runtime summary JSONL path."""
    return codex_runtime_chat_dir(active_root, canon_root, conversation_id, runtime_root) / codex_runtime_summary_file(canon_root)


def codex_runtime_index_path(
    active_root: Path, canon_root: Path, runtime_root: Path | str | None = None
) -> Path:
    """Return the cross-chat Codex runtime summary index path."""
    return codex_runtime_summary_dir(active_root, canon_root, runtime_root) / CODEX_RUNTIME_INDEX_FILE


def agent_report_archive_dir(
    active_root: Path, canon_root: Path, runtime_root: Path | str | None = None
) -> Path:
    """Return the archived reports/agents directory for one source repository."""
    return _log_archive_root(canon_root, runtime_root) / "agent-reports" / repo_log_key(active_root)


def eval_results_dir(
    canon_root: Path, family: str, runtime_root: Path | str | None = None
) -> Path:
    """Return the active accumulated eval result directory for one family."""
    return _log_archive_root(canon_root, runtime_root) / "eval-results" / safe_slug(family)


def eval_result_search_dirs(
    canon_root: Path, family: str, runtime_root: Path | str | None = None
) -> tuple[Path, ...]:
    """Return eval result directories to read for one family."""
    family_slug = safe_slug(family)
    archive_root = _log_archive_root(canon_root, runtime_root)
    candidates: list[Path] = [
        archive_root / "eval-results" / family_slug,
        archive_root / "eval-results" / "legacy-import" / family_slug,
    ]
    return tuple(dict.fromkeys(candidates))


def hook_result_search_dirs(
    requested_root: Path,
    canon_root: Path,
    runtime_root: Path | str | None = None,
) -> tuple[Path, ...]:
    """Return hook result directories to read for one repository context."""
    archive_root = _log_archive_root(canon_root, runtime_root)
    candidates: list[Path] = [
        archive_root / "hook-runs" / repo_log_key(requested_root),
        archive_root / "hook-runs" / "legacy-import",
        archive_root / "hook-runs",
    ]
    return tuple(dict.fromkeys(candidates))
