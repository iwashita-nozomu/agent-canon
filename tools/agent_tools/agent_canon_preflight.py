#!/usr/bin/env python3
# @dependency-start
# responsibility Provides agent canon preflight agent workflow automation.
# upstream design ../README.md shared automation index
# downstream implementation ../../tests/agent_tools/test_task_start_and_close.py tests preflight
# downstream implementation ../../tests/agent_tools/test_smoke_test_research_perspective_pack.py tests bootstrap smoke workspaces
# @dependency-end

"""Preflight helpers for agent-canon freshness at task entrypoints."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


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
        ["git", "status", "--short"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    if status_result.stdout.strip():
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


def is_agent_canon_source_repo(project_root: Path) -> bool:
    """Return true when the workspace is AgentCanon itself, not a derived repo."""
    return (
        (project_root / "agents" / "canonical" / "CODEX_WORKFLOW.md").is_file()
        and (project_root / "tools" / "agent_tools" / "agent_canon_preflight.py").is_file()
        and not (project_root / "vendor" / "agent-canon").exists()
    )
