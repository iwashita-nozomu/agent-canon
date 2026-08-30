#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Classifies task entry as standalone AgentCanon source or a source-free parent without synchronizing repositories.
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md defines standalone source PR and source-free parent routing
# upstream design ../../documents/runtime/bootstrap-runtime.md defines the external runtime boundary
# downstream implementation ./bootstrap_agent_run.py reports the classification at task entry
# downstream implementation ../../tests/agent_tools/test_bootstrap_and_close.py tests task-entry classification
# @dependency-end

"""Read-only task-entry classification for the standalone AgentCanon model."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

LATEST_CHECKLIST = Path(
    "documents/agent-canon/agent-canon-parent-repo-latest-checklist.md"
)


@dataclass(frozen=True)
class AgentCanonPreflightResult:
    """Bounded task-entry result with no update or projection side effects."""

    status: str
    reason: str
    next_step: str
    checklist_path: str
    checklist_status: str


def run_agent_canon_preflight(
    project_root: Path,
    *,
    skip: bool = False,
) -> AgentCanonPreflightResult:
    """Classify one checkout without fetching, syncing, or inspecting a vendor."""
    checklist_path, checklist_status = latest_checklist_status(project_root)
    if skip:
        return _result(
            "skipped_by_flag",
            "task-entry classification skipped by command-line flag",
            "inspect_the_selected_checkout_before_mutation",
            checklist_path,
            checklist_status,
        )
    if is_agent_canon_source_repo(project_root):
        return _result(
            "source_checkout_selected",
            "workspace is a standalone AgentCanon source checkout",
            "use_the_current_topic_branch_and_agentcanon_PR_workflow",
            checklist_path,
            checklist_status,
        )
    if not is_git_worktree(project_root):
        return _result(
            "skipped_non_git_workspace",
            "workspace root is not a Git worktree",
            "select_an_authorized_project_or_agentcanon_checkout",
            checklist_path,
            checklist_status,
        )
    return _result(
        "skipped_source_free_parent",
        "source-free parent has no embedded AgentCanon update surface",
        "use_parent_owned_instructions_or_select_an_external_agentcanon_clone",
        checklist_path,
        checklist_status,
    )


def _result(
    status: str,
    reason: str,
    next_step: str,
    checklist_path: str,
    checklist_status: str,
) -> AgentCanonPreflightResult:
    return AgentCanonPreflightResult(
        status=status,
        reason=reason,
        next_step=next_step,
        checklist_path=checklist_path,
        checklist_status=checklist_status,
    )


def latest_checklist_status(project_root: Path) -> tuple[str, str]:
    """Return the parent-local checklist path without searching another repo."""
    candidate = project_root / LATEST_CHECKLIST
    return LATEST_CHECKLIST.as_posix(), "present" if candidate.is_file() else "missing"


def is_git_worktree(project_root: Path) -> bool:
    """Return whether Git recognizes the exact selected checkout."""
    result = subprocess.run(
        ["git", "-C", str(project_root), "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def is_agent_canon_source_repo(project_root: Path) -> bool:
    """Recognize only the standalone source layout owned by AgentCanon."""
    return (
        (project_root / "bootstrap.sh").is_file()
        and (project_root / "bootstrap" / "host" / "manifest.toml").is_file()
        and (project_root / "tools" / "runtime" / "dispatch" / "agent-canon" / "Cargo.toml").is_file()
    )
