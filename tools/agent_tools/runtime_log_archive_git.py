#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Manages the ignored Git clone used for AgentCanon runtime log and report archives.
# upstream design ../../documents/runtime-log-archive.md runtime log archive ownership and branch policy
# upstream implementation ./runtime_log_paths.py resolves archive paths and source repo keys
# downstream design ../../documents/runtime-log-archive.md documents this tool as the normal Git workflow
# downstream implementation ../../tests/agent_tools/test_runtime_log_archive_git.py validates clone, branch, status, and push behavior
# @dependency-end
"""Manage the external AgentCanon runtime log archive Git repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtime_log_paths import (  # noqa: E402
    LOG_ARCHIVE_REMOTE,
    agent_report_archive_dir,
    codex_trace_key,
    log_branch_key,
    log_environment_key,
    mounted_log_archive_root,
    repo_log_key,
    source_git_head,
)

DEFAULT_COMMIT_NAME = "AgentCanon Log Archive"
DEFAULT_COMMIT_EMAIL = "agent-canon-log@example.invalid"
AGENT_REPORT_ARCHIVE_SCHEMA = "agent-report-snapshot.v1"
DEFAULT_AGENT_REPORT_ROOT = Path("reports") / "agents"
DEFAULT_AGENT_REPORT_DESTINATION = Path("agent-reports")
AGENT_REPORT_EXCLUDED_DIRS = frozenset(
    {".cache", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
)
AGENT_REPORT_EXCLUDED_FILES = frozenset({".active_run", ".mcp_inventory_cache.json"})
DEFAULT_AGENT_REPORT_MAX_FILE_BYTES = 10 * 1024 * 1024
GIT_PORCELAIN_STATUS_PATH_START = 3
GIT_PORCELAIN_STATUS_MIN_LINE_LENGTH = GIT_PORCELAIN_STATUS_PATH_START + 1
REPORT_SNAPSHOT_DIGEST_CHARS = 16
REPO_KEYED_ARCHIVE_FAMILIES = frozenset({"agent-reports", "codex-runtime", "hook-runs"})
MANAGED_GLOBAL_ARCHIVE_FAMILIES = frozenset({"eval-results", "legacy-import"})
BRANCH_SWITCH_COMMIT_MESSAGE = "Preserve managed runtime logs before branch switch"
GIT_INDEX_LOCK_MESSAGE = "index.lock"
GIT_INDEX_LOCK_RETRIES = 5
GIT_INDEX_LOCK_RETRY_SECONDS = 1.0


@dataclass(frozen=True)
class ArchiveContext:
    """Resolved archive operation context."""

    source_root: Path
    canon_root: Path
    archive_root: Path
    repo_key: str
    env_key: str
    branch_key: str
    branch: str
    remote: str


@dataclass(frozen=True)
class ArchiveStatusSummary:
    """Structured dirty-state summary for the archive clone."""

    current_branch: str
    dirty: bool
    branch_matches: bool
    dirty_keys: tuple[str, ...]
    current_key_dirty: bool
    foreign_dirty_keys: tuple[str, ...]
    tree_keys: tuple[str, ...]
    foreign_tree_keys: tuple[str, ...]
    global_dirty: bool


class ArchiveGitError(RuntimeError):
    """Raised when the archive Git operation cannot proceed safely."""


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Repository whose runtime logs are being written. Defaults to the superproject when AgentCanon is vendored.",
    )
    parser.add_argument(
        "--canon-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="AgentCanon root that owns .agent-canon/log-archive.",
    )
    parser.add_argument(
        "--remote",
        default=LOG_ARCHIVE_REMOTE,
        help="Log archive Git remote. Defaults to the shared agent-canon-log SSH URL.",
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        help="Override the archive clone path. Defaults to <canon-root>/.agent-canon/log-archive.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("repo-key", help="Print the source repository key and log branch.")

    ensure = subparsers.add_parser(
        "ensure",
        help="Clone/fetch the archive and switch to logs/<environment-key>-<chat-key>.",
    )
    ensure.add_argument("--no-fetch", action="store_true", help="Do not fetch origin before selecting the branch.")

    status = subparsers.add_parser("status", help="Print archive clone, branch, and dirty state.")
    status.add_argument("--porcelain", action="store_true", help="Include git status --porcelain output.")

    check_clean = subparsers.add_parser(
        "check-clean",
        help="Fail unless the archive clone is on the expected branch and has no uncommitted log artifacts.",
    )
    check_clean.add_argument(
        "--porcelain",
        action="store_true",
        help="Include git status --porcelain output on failure.",
    )

    agent_reports = subparsers.add_parser(
        "archive-agent-reports",
        help="Copy reports/agents run bundles into the current runtime archive branch.",
    )
    agent_reports.add_argument(
        "--report-root",
        type=Path,
        help="Agent report root. Defaults to <source-root>/reports/agents.",
    )
    agent_reports.add_argument(
        "--destination-prefix",
        default=DEFAULT_AGENT_REPORT_DESTINATION.as_posix(),
        help="Archive-relative destination prefix for copied agent reports.",
    )
    agent_reports.add_argument(
        "--max-file-bytes",
        type=int,
        default=DEFAULT_AGENT_REPORT_MAX_FILE_BYTES,
        help="Skip individual report files larger than this many bytes.",
    )

    legacy = subparsers.add_parser(
        "import-legacy",
        help="Copy old AgentCanon in-tree hook JSONL into legacy-import/hook-runs.",
    )
    legacy.add_argument(
        "--legacy-root",
        type=Path,
        help="Legacy hook JSONL root. Defaults to <canon-root>/agents/evals/results/hook-runs.",
    )
    legacy.add_argument(
        "--destination-prefix",
        default="legacy-import/hook-runs",
        help="Archive-relative destination prefix for legacy JSONL.",
    )
    legacy.add_argument(
        "--delete-source",
        action="store_true",
        help="Delete imported source JSONL after copying. Tracked files are removed with git rm.",
    )

    eval_results = subparsers.add_parser(
        "import-eval-results",
        help="Copy old AgentCanon in-tree eval Markdown reports into legacy-import/eval-results.",
    )
    eval_results.add_argument(
        "--legacy-root",
        type=Path,
        help="Legacy eval results root. Defaults to <canon-root>/agents/evals/results.",
    )
    eval_results.add_argument(
        "--destination-prefix",
        default="legacy-import/eval-results",
        help="Archive-relative destination prefix for legacy eval reports.",
    )
    eval_results.add_argument(
        "--delete-source",
        action="store_true",
        help=(
            "Delete imported source eval result files after copying. AgentCanon source "
            "keeps runtime-log policy in documents/runtime-log-archive.md, not under agents/evals/results."
        ),
    )

    agent_report = subparsers.add_parser(
        "archive-agent-report",
        help="Snapshot a reports/agents/<run-id> bundle into the external log archive.",
    )
    agent_report.add_argument(
        "--report-dir",
        type=Path,
        required=True,
        help="Run bundle directory to archive, normally reports/agents/<run-id>.",
    )

    push = subparsers.add_parser("push", help="Commit and push append-only logs for this source repository.")
    push.add_argument("--message", help="Commit message. Defaults to 'Append <repo-key> runtime logs'.")
    push.add_argument("--no-pull", action="store_true", help="Do not pull --rebase before pushing.")

    sync = subparsers.add_parser(
        "sync",
        help="Ensure the archive, copy current agent reports, commit, and push log artifacts.",
    )
    sync.add_argument("--message", help="Commit message. Defaults to 'Append <repo-key> runtime logs'.")
    sync.add_argument("--no-pull", action="store_true", help="Do not pull --rebase before pushing.")
    sync.add_argument("--no-push", action="store_true", help="Copy artifacts into the archive without pushing.")
    sync.add_argument("--no-agent-reports", action="store_true", help="Do not copy reports/agents artifacts.")
    sync.add_argument(
        "--report-root",
        type=Path,
        help="Agent report root. Defaults to <source-root>/reports/agents.",
    )
    sync.add_argument(
        "--max-file-bytes",
        type=int,
        default=DEFAULT_AGENT_REPORT_MAX_FILE_BYTES,
        help="Skip individual report files larger than this many bytes.",
    )
    return parser


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run one command and return the completed process."""
    result = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        command = " ".join(args)
        detail = result.stderr.strip() or result.stdout.strip()
        raise ArchiveGitError(f"{command} failed: {detail}")
    return result


def git(
    archive_root: Path,
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run git inside the archive clone."""
    command = ["git", "-C", str(archive_root), *args]
    for attempt in range(GIT_INDEX_LOCK_RETRIES + 1):
        result = run(command, check=False)
        if result.returncode == 0 or not git_index_locked(result) or attempt == GIT_INDEX_LOCK_RETRIES:
            if check and result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip()
                raise ArchiveGitError(f"{' '.join(command)} failed: {detail}")
            return result
        time.sleep(GIT_INDEX_LOCK_RETRY_SECONDS)
    raise ArchiveGitError(f"{' '.join(command)} failed after index lock retries")


def git_index_locked(result: subprocess.CompletedProcess[str]) -> bool:
    """Return whether a git failure is caused by a transient index lock."""
    detail = f"{result.stderr}\n{result.stdout}"
    return GIT_INDEX_LOCK_MESSAGE in detail


def git_root(path: Path) -> Path | None:
    """Return the Git toplevel for one path, if available."""
    result = run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return None


def superproject_root(path: Path) -> Path | None:
    """Return the superproject root when AgentCanon is checked out as a submodule."""
    result = run(
        ["git", "-C", str(path), "rev-parse", "--show-superproject-working-tree"],
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return None


def default_source_root(canon_root: Path) -> Path:
    """Return the default source repo for branch naming."""
    cwd_git_root = git_root(Path.cwd())
    canon_git_root = git_root(canon_root)
    if cwd_git_root is not None and canon_git_root is not None and cwd_git_root == canon_git_root:
        return cwd_git_root
    return superproject_root(canon_root) or cwd_git_root or Path.cwd().resolve()


def build_context(args: argparse.Namespace) -> ArchiveContext:
    """Resolve source/canon/archive paths and branch names."""
    canon_root = args.canon_root.resolve()
    source_root = (args.source_root.resolve() if args.source_root else default_source_root(canon_root))
    archive_root = (
        args.archive_root.resolve()
        if args.archive_root
        else mounted_log_archive_root(canon_root).resolve()
    )
    key = repo_log_key(source_root)
    env_key = log_environment_key(canon_root)
    branch_key = log_branch_key(source_root, canon_root)
    return ArchiveContext(
        source_root=source_root,
        canon_root=canon_root,
        archive_root=archive_root,
        repo_key=key,
        env_key=env_key,
        branch_key=branch_key,
        branch=f"logs/{branch_key}",
        remote=args.remote,
    )


def remote_branch_exists(context: ArchiveContext, branch: str) -> bool:
    """Return whether origin/<branch> exists locally after fetch."""
    result = git(context.archive_root, ["rev-parse", "--verify", f"origin/{branch}"], check=False)
    return result.returncode == 0


def local_branch_exists(context: ArchiveContext, branch: str) -> bool:
    """Return whether one local branch exists."""
    result = git(context.archive_root, ["rev-parse", "--verify", branch], check=False)
    return result.returncode == 0


def current_branch(context: ArchiveContext) -> str:
    """Return the current branch name for the archive clone."""
    result = git(context.archive_root, ["branch", "--show-current"])
    return result.stdout.strip()


def porcelain_status(context: ArchiveContext) -> str:
    """Return porcelain status output for the archive clone."""
    return git(
        context.archive_root,
        ["status", "--porcelain", "--untracked-files=all"],
        check=False,
    ).stdout


def porcelain_paths(context: ArchiveContext) -> tuple[str, ...]:
    """Return dirty archive-relative paths from porcelain status."""
    paths = []
    for line in porcelain_status(context).splitlines():
        path = porcelain_path(line)
        if path:
            paths.append(path)
    return tuple(paths)


def porcelain_path(line: str) -> str:
    """Extract a path from one non-z porcelain status line."""
    if len(line) < GIT_PORCELAIN_STATUS_MIN_LINE_LENGTH:
        return ""
    path = line[GIT_PORCELAIN_STATUS_PATH_START:]
    if " -> " in path:
        path = path.rsplit(" -> ", 1)[-1]
    return path.strip()


def managed_runtime_archive_path(path: str) -> bool:
    """Return whether a dirty archive path is a managed runtime artifact."""
    parts = Path(path).parts
    if not parts:
        return False
    if parts[0] in REPO_KEYED_ARCHIVE_FAMILIES and len(parts) >= 2:
        return True
    return parts[0] in MANAGED_GLOBAL_ARCHIVE_FAMILIES


def dirty_key_for_path(path: str) -> tuple[str, bool]:
    """Return (repo_key, global_dirty) for one archive-relative dirty path."""
    parts = Path(path).parts
    if len(parts) >= 2 and parts[0] in REPO_KEYED_ARCHIVE_FAMILIES:
        if parts[1] != "legacy-import":
            return parts[1], False
    if parts and parts[0] in {
        ".gitattributes",
        "README.md",
        "eval-results",
        "legacy-import",
        "reports",
        "tools",
    }:
        return "", True
    return "", False


def archive_tree_keys(context: ArchiveContext) -> tuple[str, ...]:
    """Return repo-key directory names already present in keyed archive families."""
    keys: set[str] = set()
    for family in sorted(REPO_KEYED_ARCHIVE_FAMILIES):
        family_root = context.archive_root / family
        try:
            children = tuple(family_root.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and child.name != "legacy-import":
                keys.add(child.name)
    return tuple(sorted(keys))


def associated_repo_keys(context: ArchiveContext) -> tuple[str, ...]:
    """Return repo keys allowed to coexist on the same chat archive branch."""
    keys = {context.repo_key, repo_log_key(context.canon_root)}
    parent = superproject_root(context.canon_root)
    if parent is not None:
        keys.add(repo_log_key(parent))
    return tuple(sorted(keys))


def archive_status_summary(context: ArchiveContext) -> ArchiveStatusSummary:
    """Return structured archive dirty-state information."""
    current = current_branch(context)
    status = porcelain_status(context)
    tree_keys = archive_tree_keys(context)
    associated_keys = set(associated_repo_keys(context))
    dirty_keys: set[str] = set()
    global_dirty = False
    for line in status.splitlines():
        key, is_global = dirty_key_for_path(porcelain_path(line))
        if key:
            dirty_keys.add(key)
        if is_global:
            global_dirty = True
    foreign_keys = tuple(sorted(key for key in dirty_keys if key not in associated_keys))
    foreign_tree_keys = tuple(sorted(key for key in tree_keys if key not in associated_keys))
    return ArchiveStatusSummary(
        current_branch=current,
        dirty=bool(status.strip()),
        branch_matches=current == context.branch,
        dirty_keys=tuple(sorted(dirty_keys)),
        current_key_dirty=context.repo_key in dirty_keys,
        foreign_dirty_keys=foreign_keys,
        tree_keys=tree_keys,
        foreign_tree_keys=foreign_tree_keys,
        global_dirty=global_dirty,
    )


def print_status_summary(context: ArchiveContext, summary: ArchiveStatusSummary) -> None:
    """Print stable structured archive status lines."""
    print(f"RUNTIME_LOG_ARCHIVE_CURRENT_BRANCH={summary.current_branch}")
    print(f"RUNTIME_LOG_ARCHIVE_EXPECTED_BRANCH={context.branch}")
    print(f"RUNTIME_LOG_ARCHIVE_BRANCH_MATCH={'yes' if summary.branch_matches else 'no'}")
    print(f"RUNTIME_LOG_ARCHIVE_DIRTY={'yes' if summary.dirty else 'no'}")
    print(f"RUNTIME_LOG_ARCHIVE_DIRTY_KEYS={','.join(summary.dirty_keys)}")
    print(f"RUNTIME_LOG_ARCHIVE_CURRENT_KEY_DIRTY={'yes' if summary.current_key_dirty else 'no'}")
    print(f"RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY_KEYS={','.join(summary.foreign_dirty_keys)}")
    print(f"RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY={'yes' if summary.foreign_dirty_keys else 'no'}")
    print(f"RUNTIME_LOG_ARCHIVE_TREE_KEYS={','.join(summary.tree_keys)}")
    print(f"RUNTIME_LOG_ARCHIVE_FOREIGN_TREE_KEYS={','.join(summary.foreign_tree_keys)}")
    print(f"RUNTIME_LOG_ARCHIVE_FOREIGN_TREE={'yes' if summary.foreign_tree_keys else 'no'}")
    print(f"RUNTIME_LOG_ARCHIVE_GLOBAL_DIRTY={'yes' if summary.global_dirty else 'no'}")


def archive_next_action(context: ArchiveContext, summary: ArchiveStatusSummary) -> str:
    """Return the next operation for a non-clean archive state."""
    if not summary.branch_matches:
        return f"run runtime_log_archive_git.py ensure for archive branch {context.branch}"
    if summary.foreign_dirty_keys:
        return (
            "commit or migrate foreign repo-key log paths before closeout: "
            + ",".join(summary.foreign_dirty_keys)
        )
    if summary.global_dirty:
        return "commit or revert archive-level dirty paths before closeout"
    if summary.dirty:
        return "run runtime_log_archive_git.py sync, then check-clean"
    return "none"


def safe_archive_relative_path(value: str) -> Path:
    """Return an archive-relative path or fail for unsafe input."""
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ArchiveGitError(f"archive path must be relative and cannot contain '..': {value}")
    return path


def safe_run_id(value: str) -> str:
    """Return a filesystem-safe run id for the archive tree."""
    if not value or value in {".", ".."}:
        raise ArchiveGitError(f"invalid run id: {value!r}")
    if "/" in value or "\\" in value:
        raise ArchiveGitError(f"run id must be one path segment: {value!r}")
    return value


def ensure_commit_identity(context: ArchiveContext) -> None:
    """Ensure the archive clone has a local identity for automated commits."""
    name = git(context.archive_root, ["config", "--get", "user.name"], check=False)
    email = git(context.archive_root, ["config", "--get", "user.email"], check=False)
    if name.returncode != 0 or not name.stdout.strip():
        git(context.archive_root, ["config", "user.name", DEFAULT_COMMIT_NAME])
    if email.returncode != 0 or not email.stdout.strip():
        git(context.archive_root, ["config", "user.email", DEFAULT_COMMIT_EMAIL])


def preserve_managed_dirty_paths(context: ArchiveContext, current: str) -> None:
    """Commit managed runtime artifacts before switching archive branches."""
    paths = porcelain_paths(context)
    unmanaged = [path for path in paths if not managed_runtime_archive_path(path)]
    if unmanaged:
        raise ArchiveGitError(
            "archive has non-runtime local changes on "
            f"{current}: {', '.join(unmanaged)}"
        )
    if not paths:
        return
    ensure_commit_identity(context)
    git(context.archive_root, ["add", "--", *paths])
    staged = git(context.archive_root, ["diff", "--cached", "--quiet"], check=False)
    if staged.returncode != 0:
        git(
            context.archive_root,
            ["commit", "-m", f"{BRANCH_SWITCH_COMMIT_MESSAGE}: {current}"],
        )


def source_is_tracked(canon_root: Path, path: Path) -> bool:
    """Return whether one source path is tracked by the canon Git repo."""
    try:
        relative = path.resolve().relative_to(canon_root.resolve())
    except ValueError:
        return False
    result = run(
        ["git", "-C", str(canon_root), "ls-files", "--error-unmatch", "--", relative.as_posix()],
        check=False,
    )
    return result.returncode == 0


def delete_source_file(context: ArchiveContext, source: Path) -> None:
    """Delete one imported source file, using git rm when possible."""
    try:
        relative = source.resolve().relative_to(context.canon_root.resolve())
    except ValueError:
        source.unlink()
        return
    if source_is_tracked(context.canon_root, source):
        run(["git", "-C", str(context.canon_root), "rm", "--", relative.as_posix()])
        return
    source.unlink()


def is_archive_clone(path: Path) -> bool:
    """Return whether path is an existing Git worktree."""
    return (path / ".git").exists()


def ensure_origin(context: ArchiveContext) -> None:
    """Ensure origin points at the configured remote."""
    result = git(context.archive_root, ["remote", "get-url", "origin"], check=False)
    if result.returncode != 0:
        git(context.archive_root, ["remote", "add", "origin", context.remote])
        return
    if result.stdout.strip() != context.remote:
        git(context.archive_root, ["remote", "set-url", "origin", context.remote])


def switch_to_archive_branch(context: ArchiveContext, branch: str) -> None:
    """Switch the archive clone to one local or remote branch."""
    if local_branch_exists(context, branch):
        git(context.archive_root, ["switch", branch])
        return
    if remote_branch_exists(context, branch):
        git(context.archive_root, ["switch", "--track", "-c", branch, f"origin/{branch}"])
        return
    if remote_branch_exists(context, "main"):
        git(context.archive_root, ["switch", "-c", branch, "origin/main"])
        return
    git(context.archive_root, ["switch", "-c", branch])


def ensure_archive(context: ArchiveContext, *, fetch: bool = True) -> None:
    """Ensure the ignored clone exists and is on the runtime log branch."""
    if not context.archive_root.exists():
        context.archive_root.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", context.remote, str(context.archive_root)])
    if not is_archive_clone(context.archive_root):
        raise ArchiveGitError(f"archive path is not a Git clone: {context.archive_root}")

    ensure_origin(context)
    if fetch:
        git(context.archive_root, ["fetch", "origin"], check=False)

    branch = context.branch
    current = current_branch(context)
    if current == branch:
        return
    summary = archive_status_summary(context)
    if summary.dirty:
        preserve_managed_dirty_paths(context, current)
        summary = archive_status_summary(context)
        if summary.dirty:
            raise ArchiveGitError(
                f"archive has local changes on {current}; run sync or push for that branch before switching to {branch}"
            )
    switch_to_archive_branch(context, branch)


def print_context(context: ArchiveContext) -> None:
    """Print stable context lines."""
    run_local_agent_reports = context.source_root / DEFAULT_AGENT_REPORT_ROOT
    archive_agent_reports = (
        context.archive_root / DEFAULT_AGENT_REPORT_DESTINATION / context.repo_key
    )
    print(f"RUNTIME_LOG_ARCHIVE_SOURCE_ROOT={context.source_root}")
    print(f"RUNTIME_LOG_ARCHIVE_CANON_ROOT={context.canon_root}")
    print(f"RUNTIME_LOG_ARCHIVE_ROOT={context.archive_root}")
    print(f"RUNTIME_LOG_ARCHIVE_ENV_KEY={context.env_key}")
    print(f"RUNTIME_LOG_ARCHIVE_REMOTE={context.remote}")
    print(f"RUNTIME_LOG_ARCHIVE_REPO_KEY={context.repo_key}")
    print(f"RUNTIME_LOG_ARCHIVE_BRANCH_KEY={context.branch_key}")
    print(f"RUNTIME_LOG_ARCHIVE_BRANCH={context.branch}")
    print(f"RUNTIME_LOG_ARCHIVE_REPORTS_RUN_LOCAL={run_local_agent_reports}")
    print(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_BRANCH={context.branch}")
    print(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_DIR={archive_agent_reports}")
    print(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_REL=agent-reports/{context.repo_key}")


def command_repo_key(context: ArchiveContext) -> int:
    """Print repo-key context."""
    print_context(context)
    return 0


def command_ensure(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Ensure archive clone and branch."""
    ensure_archive(context, fetch=not args.no_fetch)
    print_context(context)
    print(f"RUNTIME_LOG_ARCHIVE_CURRENT_BRANCH={current_branch(context)}")
    print("RUNTIME_LOG_ARCHIVE_ENSURE=pass")
    return 0


def command_status(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Print archive status."""
    print_context(context)
    if not context.archive_root.exists():
        print("RUNTIME_LOG_ARCHIVE_STATUS=missing")
        return 0
    if not is_archive_clone(context.archive_root):
        print("RUNTIME_LOG_ARCHIVE_STATUS=invalid")
        return 1
    status = porcelain_status(context)
    summary = archive_status_summary(context)
    print_status_summary(context, summary)
    print(f"RUNTIME_LOG_ARCHIVE_NEXT_ACTION={archive_next_action(context, summary)}")
    if args.porcelain:
        for line in status.splitlines():
            print(f"RUNTIME_LOG_ARCHIVE_PORCELAIN={line}")
    print("RUNTIME_LOG_ARCHIVE_STATUS=pass")
    return 0


def command_check_clean(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Fail unless the archive clone is on the expected branch and clean."""
    print_context(context)
    if not context.archive_root.exists():
        print("RUNTIME_LOG_ARCHIVE_CLEAN=no")
        print("RUNTIME_LOG_ARCHIVE_STATUS=missing")
        return 1
    if not is_archive_clone(context.archive_root):
        print("RUNTIME_LOG_ARCHIVE_CLEAN=no")
        print("RUNTIME_LOG_ARCHIVE_STATUS=invalid")
        return 1
    status = porcelain_status(context)
    summary = archive_status_summary(context)
    print_status_summary(context, summary)
    clean = summary.branch_matches and not summary.dirty and not summary.foreign_tree_keys
    print(f"RUNTIME_LOG_ARCHIVE_NEXT_ACTION={archive_next_action(context, summary)}")
    if args.porcelain:
        for line in status.splitlines():
            print(f"RUNTIME_LOG_ARCHIVE_PORCELAIN={line}")
    print(f"RUNTIME_LOG_ARCHIVE_CLEAN={'yes' if clean else 'no'}")
    print("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=pass" if clean else "RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=fail")
    return 0 if clean else 1


def command_import_legacy(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Import old in-tree hook JSONL into the archive clone."""
    ensure_archive(context)
    legacy_root = (
        args.legacy_root.resolve()
        if args.legacy_root
        else context.canon_root / "agents" / "evals" / "results" / "hook-runs"
    )
    destination_prefix = safe_archive_relative_path(args.destination_prefix)
    if context.archive_root.resolve() == legacy_root or context.archive_root.resolve() in legacy_root.parents:
        raise ArchiveGitError("legacy root cannot be inside the archive clone")
    if not legacy_root.exists():
        print_context(context)
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_LEGACY_ROOT={legacy_root}")
        print("RUNTIME_LOG_ARCHIVE_IMPORT_FILES=0")
        print("RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE=no")
        print("RUNTIME_LOG_ARCHIVE_IMPORT=pass")
        return 0

    imported = 0
    existing = 0
    for source in sorted(legacy_root.rglob("*.jsonl")):
        if not source.is_file():
            continue
        relative = source.relative_to(legacy_root)
        target = context.archive_root / destination_prefix / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != source.read_bytes():
                raise ArchiveGitError(f"archive destination already exists with different content: {target}")
            existing += 1
        else:
            shutil.copy2(source, target)
            imported += 1
        if args.delete_source:
            delete_source_file(context, source)

    if (context.archive_root / destination_prefix).exists():
        git(context.archive_root, ["add", "--", destination_prefix.as_posix()])

    print_context(context)
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_LEGACY_ROOT={legacy_root}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_DESTINATION={destination_prefix.as_posix()}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_FILES={imported + existing}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_NEW_FILES={imported}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EXISTING_FILES={existing}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE={'yes' if args.delete_source else 'no'}")
    print("RUNTIME_LOG_ARCHIVE_IMPORT=pass")
    return 0


def should_import_eval_result(relative: Path) -> bool:
    """Return whether one legacy eval result file should move to eval-results."""
    if relative.parts and relative.parts[0] == "hook-runs":
        return False
    return True


def should_delete_eval_source(relative: Path) -> bool:
    """Return whether one imported eval source file can leave the source tree."""
    return True


def command_import_eval_results(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Import old in-tree eval Markdown reports into the archive clone."""
    ensure_archive(context)
    legacy_root = (
        args.legacy_root.resolve()
        if args.legacy_root
        else context.canon_root / "agents" / "evals" / "results"
    )
    destination_prefix = safe_archive_relative_path(args.destination_prefix)
    if context.archive_root.resolve() == legacy_root or context.archive_root.resolve() in legacy_root.parents:
        raise ArchiveGitError("legacy root cannot be inside the archive clone")
    if not legacy_root.exists():
        print_context(context)
        print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_ROOT={legacy_root}")
        print("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_FILES=0")
        print("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_DELETED_SOURCE=no")
        print("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS=pass")
        return 0

    imported = 0
    existing = 0
    deleted = 0
    for source in sorted(path for path in legacy_root.rglob("*") if path.is_file()):
        relative = source.relative_to(legacy_root)
        if not should_import_eval_result(relative):
            continue
        target = context.archive_root / destination_prefix / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != source.read_bytes():
                raise ArchiveGitError(f"archive destination already exists with different content: {target}")
            existing += 1
        else:
            shutil.copy2(source, target)
            imported += 1
        if args.delete_source and should_delete_eval_source(relative):
            delete_source_file(context, source)
            deleted += 1

    if args.delete_source:
        for notice in (legacy_root / "hook-runs" / "README.md",):
            if notice.exists():
                delete_source_file(context, notice)
                deleted += 1

    if (context.archive_root / destination_prefix).exists():
        git(context.archive_root, ["add", "--", destination_prefix.as_posix()])

    print_context(context)
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_ROOT={legacy_root}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_DESTINATION={destination_prefix.as_posix()}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_FILES={imported + existing}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_NEW_FILES={imported}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_EXISTING_FILES={existing}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_DELETIONS={deleted}")
    print(f"RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_DELETED_SOURCE={'yes' if args.delete_source else 'no'}")
    print("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS=pass")
    return 0


def iter_report_files(report_dir: Path) -> list[Path]:
    """Return deterministic report bundle files to snapshot."""
    files: list[Path] = []
    for path in sorted(report_dir.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        files.append(path)
    return files


def report_snapshot_digest(report_dir: Path, files: list[Path]) -> str:
    """Return a stable digest for one report snapshot."""
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(report_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()[:REPORT_SNAPSHOT_DIGEST_CHARS]


def write_jsonl_once(path: Path, payload: dict[str, object], key: str) -> bool:
    """Append a JSON object unless a line with the same key already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = cast(object, json.loads(line))
            except json.JSONDecodeError:
                continue
            if isinstance(existing, dict):
                existing_payload = cast(dict[str, object], existing)
                if existing_payload.get("archive_id") == key:
                    return False
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return True


def command_archive_agent_report(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Snapshot one run bundle into the archive clone."""
    ensure_archive(context)
    report_dir = args.report_dir.resolve()
    if not report_dir.is_dir():
        raise ArchiveGitError(f"report directory does not exist: {report_dir}")
    try:
        report_dir.relative_to(context.source_root.resolve())
    except ValueError as exc:
        raise ArchiveGitError(
            f"report directory must be under source root {context.source_root}: {report_dir}"
        ) from exc

    run_id = safe_run_id(report_dir.name)
    files = iter_report_files(report_dir)
    if not files:
        raise ArchiveGitError(f"report directory has no files to archive: {report_dir}")
    snapshot_id = report_snapshot_digest(report_dir, files)
    archive_id = f"{run_id}-{snapshot_id}"
    destination = agent_report_archive_dir(context.source_root, context.canon_root) / run_id / snapshot_id
    destination.mkdir(parents=True, exist_ok=True)

    file_entries: list[dict[str, object]] = []
    copied = 0
    existing = 0
    for source in files:
        relative = source.relative_to(report_dir)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        source_bytes = source.read_bytes()
        if target.exists():
            if target.read_bytes() != source_bytes:
                raise ArchiveGitError(f"archive destination has conflicting content: {target}")
            existing += 1
        else:
            shutil.copy2(source, target)
            copied += 1
        file_entries.append(
            {
                "path": relative.as_posix(),
                "bytes": len(source_bytes),
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
            }
        )

    manifest = {
        "schema": AGENT_REPORT_ARCHIVE_SCHEMA,
        "archive_id": archive_id,
        "archived_at": datetime.now(UTC).isoformat(),
        "codex_trace_key": codex_trace_key(),
        "agent_canon_git_head": source_git_head(context.canon_root),
        "source_git_head": source_git_head(context.source_root),
        "source_root": str(context.source_root),
        "canon_root": str(context.canon_root),
        "repo_key": context.repo_key,
        "branch": context.branch,
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "report_dir": str(report_dir),
        "destination": str(destination.relative_to(context.archive_root)),
        "file_count": len(file_entries),
        "files": file_entries,
    }
    manifest_path = destination / "archive_manifest.json"
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if manifest_path.exists():
        try:
            existing_manifest = cast(object, json.loads(manifest_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise ArchiveGitError(f"archive manifest is not valid JSON: {manifest_path}") from exc
        existing_manifest_payload = (
            cast(dict[str, object], existing_manifest) if isinstance(existing_manifest, dict) else {}
        )
        if existing_manifest_payload.get("archive_id") != archive_id:
            raise ArchiveGitError(f"archive manifest conflict: {manifest_path}")
    else:
        manifest_path.write_text(manifest_text, encoding="utf-8")

    index_path = agent_report_archive_dir(context.source_root, context.canon_root) / "index.jsonl"
    index_appended = write_jsonl_once(
        index_path,
        {
            "schema": AGENT_REPORT_ARCHIVE_SCHEMA,
            "archive_id": archive_id,
            "archived_at": manifest["archived_at"],
            "repo_key": context.repo_key,
            "run_id": run_id,
            "snapshot_id": snapshot_id,
            "destination": manifest["destination"],
            "file_count": len(file_entries),
        },
        archive_id,
    )
    git(context.archive_root, ["add", "--", Path("agent-reports").as_posix()])

    print_context(context)
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_RUN_ID={run_id}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SNAPSHOT={snapshot_id}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_DESTINATION={manifest['destination']}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_FILES={len(file_entries)}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_NEW_FILES={copied}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_EXISTING_FILES={existing}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_INDEX_APPENDED={'yes' if index_appended else 'no'}")
    print("RUNTIME_LOG_ARCHIVE_AGENT_REPORT=pass")
    return 0


@dataclass(frozen=True)
class AgentReportArchiveSummary:
    """Counts from copying run-local agent reports into the archive."""

    report_root: Path
    destination: Path
    files: int
    copied: int
    updated: int
    existing: int
    skipped: int


def report_root_for_context(context: ArchiveContext, report_root: Path | None) -> Path:
    """Return the source report root for agent run artifacts."""
    return (report_root.resolve() if report_root else context.source_root / DEFAULT_AGENT_REPORT_ROOT)


def should_skip_agent_report(relative: Path, source: Path, max_file_bytes: int) -> bool:
    """Return whether one report artifact should stay out of the log archive."""
    if any(part in AGENT_REPORT_EXCLUDED_DIRS for part in relative.parts):
        return True
    if relative.name in AGENT_REPORT_EXCLUDED_FILES:
        return True
    try:
        return source.stat().st_size > max(0, max_file_bytes)
    except OSError:
        return True


def copy_agent_reports(
    context: ArchiveContext,
    *,
    report_root: Path | None,
    destination_prefix: Path,
    max_file_bytes: int,
) -> AgentReportArchiveSummary:
    """Copy run-local reports/agents artifacts to the archive branch."""
    ensure_archive(context)
    root = report_root_for_context(context, report_root)
    default_destination = agent_report_archive_dir(context.source_root, context.canon_root)
    destination = (
        default_destination
        if destination_prefix == DEFAULT_AGENT_REPORT_DESTINATION
        else context.archive_root / destination_prefix / context.repo_key
    )
    if context.archive_root.resolve() == root or context.archive_root.resolve() in root.parents:
        raise ArchiveGitError("agent report root cannot be inside the archive clone")
    if not root.exists():
        return AgentReportArchiveSummary(root, destination, 0, 0, 0, 0, 0)

    files = copied = updated = existing = skipped = 0
    for source in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = source.relative_to(root)
        if should_skip_agent_report(relative, source, max_file_bytes):
            skipped += 1
            continue
        files += 1
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() == source.read_bytes():
                existing += 1
                continue
            shutil.copy2(source, target)
            updated += 1
            continue
        shutil.copy2(source, target)
        copied += 1

    if destination.exists():
        git(context.archive_root, ["add", "--", destination_prefix.as_posix()])
    return AgentReportArchiveSummary(root, destination, files, copied, updated, existing, skipped)


def print_agent_report_archive_summary(summary: AgentReportArchiveSummary) -> None:
    """Print stable status lines for agent report archiving."""
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_ROOT={summary.report_root}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_DESTINATION={summary.destination}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_FILES={summary.files}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_COPIED={summary.copied}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_UPDATED={summary.updated}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_EXISTING={summary.existing}")
    print(f"RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SKIPPED={summary.skipped}")


def command_archive_agent_reports(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Archive current reports/agents artifacts."""
    destination_prefix = safe_archive_relative_path(args.destination_prefix)
    summary = copy_agent_reports(
        context,
        report_root=args.report_root,
        destination_prefix=destination_prefix,
        max_file_bytes=args.max_file_bytes,
    )
    print_context(context)
    print_agent_report_archive_summary(summary)
    print("RUNTIME_LOG_ARCHIVE_AGENT_REPORTS=pass")
    return 0


def stage_archive_paths(context: ArchiveContext) -> None:
    """Stage all AgentCanon-managed log archive families that exist."""
    log_paths = [
        Path("hook-runs") / context.repo_key,
        Path("codex-runtime") / context.repo_key,
        DEFAULT_AGENT_REPORT_DESTINATION / context.repo_key,
        Path("eval-results"),
        Path("legacy-import"),
    ]
    for logs_path in log_paths:
        if (context.archive_root / logs_path).exists():
            git(context.archive_root, ["add", "--", logs_path.as_posix()])


def command_push(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Commit and push source repo runtime logs."""
    ensure_archive(context)
    message = args.message or f"Append {context.repo_key} runtime logs"

    stage_archive_paths(context)
    staged = git(context.archive_root, ["diff", "--cached", "--quiet"], check=False)
    committed = "no"
    if staged.returncode != 0:
        ensure_commit_identity(context)
        git(context.archive_root, ["commit", "-m", message])
        committed = "yes"
    if not args.no_pull and remote_branch_exists(context, context.branch):
        git(context.archive_root, ["pull", "--rebase", "--autostash", "origin", context.branch])
    git(context.archive_root, ["push", "-u", "origin", context.branch])

    print_context(context)
    print(f"RUNTIME_LOG_ARCHIVE_COMMITTED={committed}")
    print("RUNTIME_LOG_ARCHIVE_PUSH=pass")
    return 0


def command_sync(context: ArchiveContext, args: argparse.Namespace) -> int:
    """Run the normal unattended archive sync flow."""
    ensure_archive(context)
    print_context(context)
    if not args.no_agent_reports:
        summary = copy_agent_reports(
            context,
            report_root=args.report_root,
            destination_prefix=DEFAULT_AGENT_REPORT_DESTINATION,
            max_file_bytes=args.max_file_bytes,
        )
        print_agent_report_archive_summary(summary)
    if args.no_push:
        stage_archive_paths(context)
        print("RUNTIME_LOG_ARCHIVE_SYNC_PUSH=skipped")
        print("RUNTIME_LOG_ARCHIVE_SYNC=pass")
        return 0
    push_args = argparse.Namespace(message=args.message, no_pull=args.no_pull)
    result = command_push(context, push_args)
    print("RUNTIME_LOG_ARCHIVE_SYNC=pass")
    return result


def main(argv: list[str] | None = None) -> int:
    """Run the runtime log archive Git helper."""
    parser = build_parser()
    args = parser.parse_args(argv)
    context = build_context(args)
    try:
        if args.command == "repo-key":
            return command_repo_key(context)
        if args.command == "ensure":
            return command_ensure(context, args)
        if args.command == "status":
            return command_status(context, args)
        if args.command == "check-clean":
            return command_check_clean(context, args)
        if args.command == "import-legacy":
            return command_import_legacy(context, args)
        if args.command == "import-eval-results":
            return command_import_eval_results(context, args)
        if args.command == "archive-agent-report":
            return command_archive_agent_report(context, args)
        if args.command == "archive-agent-reports":
            return command_archive_agent_reports(context, args)
        if args.command == "push":
            return command_push(context, args)
        if args.command == "sync":
            return command_sync(context, args)
    except ArchiveGitError as exc:
        print(f"RUNTIME_LOG_ARCHIVE_ERROR={exc}")
        print("RUNTIME_LOG_ARCHIVE=fail")
        return 1
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
