#!/usr/bin/env python3
# @dependency-start
# upstream design ../README.md shared automation index
# @dependency-end

"""Preflight helpers for agent-canon freshness at task entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


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
            reason="worktree is dirty; automatic agent-canon ensure-latest is skipped until commit or stash",
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
