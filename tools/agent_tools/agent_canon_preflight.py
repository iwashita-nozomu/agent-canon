#!/usr/bin/env python3
# @dependency-start
# responsibility Provides agent canon preflight agent workflow automation.
# upstream design ../README.md shared automation index
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md defines task-entry freshness routing
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines PR-first shared-canon propagation
# upstream design ../../agents/workflows/derived-agent-canon-diff-workflow.md defines derived proposal routing
# downstream implementation ../../tests/agent_tools/test_task_start_and_close.py tests preflight
# downstream implementation ../../tests/agent_tools/test_smoke_test_research_perspective_pack.py tests bootstrap smoke workspaces
# @dependency-end

"""Preflight helpers for agent-canon freshness at task entrypoints."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

GIT_STATUS_PATH_COLUMN = 3
RENAMED_PATH_SPLIT_MAX = 1
SHARED_CANON_DIRTY_PATH_PREFIXES = (
    ".agents/",
    ".claude/",
    ".codex/",
    ".github/AGENTS.md",
    ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
    ".github/agents/",
    ".github/copilot-instructions.md",
    ".github/instructions/",
    ".github/workflows/agent-coordination.yml",
    "AGENTS.md",
    "CLAUDE.md",
    "ROOT_AGENTS.md",
    "agents/",
    "documents/SHARED_RUNTIME_SURFACES.md",
    "mcp/",
    "tools/sync_agent_canon.sh",
    "vendor/agent-canon",
)


@dataclass(frozen=True)
class AgentCanonPreflightResult:
    """Machine-readable preflight outcome."""

    status: str
    reason: str
    next_step: str


def project_root_from_script(script_path: Path) -> Path:
    """Return the repository root that owns the current script."""
    result = subprocess.run(
        ["git", "-C", str(script_path.resolve().parent), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip())


def run_agent_canon_preflight(
    project_root: Path,
    *,
    skip: bool = False,
) -> AgentCanonPreflightResult:
    """Ensure the local agent-canon snapshot is current when safe to do so."""
    if skip:
        return AgentCanonPreflightResult(
            status="skipped_by_flag",
            reason="agent-canon preflight skipped by command-line flag",
            next_step="run make agent-canon-ensure-latest manually before editing shared surfaces",
        )

    if is_agent_canon_source_repo(project_root):
        return AgentCanonPreflightResult(
            status="skipped_source_canon",
            reason="workspace is the shared agent-canon source repository",
            next_step="ensure derived template snapshots after committing canon changes",
        )

    if not is_git_worktree(project_root):
        return AgentCanonPreflightResult(
            status="skipped_non_git_workspace",
            reason="workspace root is not a git worktree; preflight is not applicable",
            next_step="run from a git worktree before editing shared AgentCanon surfaces",
        )

    status_result = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    if status_result.stdout.strip():
        if dirty_status_mentions_shared_canon(status_result.stdout):
            return AgentCanonPreflightResult(
                status="blocked_shared_canon_workflow",
                reason=(
                    "shared AgentCanon surface is dirty; route it through a proposal "
                    "or AgentCanon PR before refreshing the template pin"
                ),
                next_step=(
                    "commit_or_push_proposal_then_open_agent-canon_PR_then_after_merge_"
                    "run_make_agent-canon-ensure-latest"
                ),
            )
        return AgentCanonPreflightResult(
            status="blocked_dirty_worktree",
            reason=(
                "worktree is dirty; automatic agent-canon ensure-latest is skipped "
                "until commit or stash"
            ),
            next_step="commit_or_stash_then_run_make_agent-canon-ensure-latest",
        )

    ensure_result = subprocess.run(
        ["make", "agent-canon-ensure-latest"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if ensure_result.returncode != 0:
        detail = (ensure_result.stderr or ensure_result.stdout).strip()
        if detail:
            raise RuntimeError(detail)
        raise RuntimeError("make agent-canon-ensure-latest failed")

    return AgentCanonPreflightResult(
        status="pass",
        reason="agent-canon snapshot is current",
        next_step="none",
    )


def is_git_worktree(project_root: Path) -> bool:
    """Return true when project_root can run repository-local git checks."""
    result = subprocess.run(
        ["git", "-C", str(project_root), "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def dirty_status_mentions_shared_canon(status_text: str) -> bool:
    """Return true when git status includes shared AgentCanon surfaces."""
    for line in status_text.splitlines():
        if len(line) < GIT_STATUS_PATH_COLUMN:
            continue
        path_text = line[GIT_STATUS_PATH_COLUMN:].strip()
        if " -> " in path_text:
            path_text = path_text.rsplit(" -> ", maxsplit=RENAMED_PATH_SPLIT_MAX)[-1]
        for prefix in SHARED_CANON_DIRTY_PATH_PREFIXES:
            if path_text == prefix.rstrip("/") or path_text.startswith(prefix):
                return True
    return False


def is_agent_canon_source_repo(project_root: Path) -> bool:
    """Return true when the workspace is AgentCanon itself, not a derived repo."""
    return (
        (project_root / "agents" / "canonical" / "CODEX_WORKFLOW.md").is_file()
        and (project_root / "tools" / "agent_tools" / "agent_canon_preflight.py").is_file()
        and not (project_root / "vendor" / "agent-canon").exists()
    )
