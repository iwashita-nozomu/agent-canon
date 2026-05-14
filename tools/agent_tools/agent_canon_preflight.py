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
LATEST_CHECKLIST = Path("documents/agent-canon-parent-repo-latest-checklist.md")
SURFACE_MANIFEST = Path("tools/agent_tools/surface_manifest.py")
SURFACE_SPEC_COMMANDS = ("link-specs", "copy-specs", "removed-legacy-paths")


@dataclass(frozen=True)
class AgentCanonPreflightResult:
    """Machine-readable preflight outcome."""

    status: str
    reason: str
    next_step: str
    checklist_path: str
    checklist_status: str


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
    checklist_path, checklist_status = latest_checklist_status(project_root)
    if skip:
        return AgentCanonPreflightResult(
            status="skipped_by_flag",
            reason="agent-canon preflight skipped by command-line flag",
            next_step="run make agent-canon-ensure-latest manually before editing shared surfaces",
            checklist_path=checklist_path,
            checklist_status=checklist_status,
        )

    if is_agent_canon_source_repo(project_root):
        return AgentCanonPreflightResult(
            status="skipped_source_canon",
            reason="workspace is the shared agent-canon source repository",
            next_step="ensure derived template snapshots after committing canon changes",
            checklist_path=checklist_path,
            checklist_status=checklist_status,
        )

    if not is_git_worktree(project_root):
        return AgentCanonPreflightResult(
            status="skipped_non_git_workspace",
            reason="workspace root is not a git worktree; preflight is not applicable",
            next_step="run from a git worktree before editing shared AgentCanon surfaces",
            checklist_path=checklist_path,
            checklist_status=checklist_status,
        )

    status_result = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    update_surface_status = agent_canon_update_surface_status(project_root)
    if update_surface_status.strip():
        print("AGENT_CANON_PREFLIGHT_UPDATE_SURFACE_DIRTY=yes")
    if update_surface_status.strip():
        print(update_surface_status)
    if status_result.stdout.strip():
        print("AGENT_CANON_PREFLIGHT_PARENT_DIRTY_OUTSIDE_UPDATE_SURFACE=yes")

    ensure_result = subprocess.run(
        ["make", "agent-canon-ensure-latest"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if ensure_result.returncode != 0:
        detail = (ensure_result.stderr or ensure_result.stdout).strip()
        return AgentCanonPreflightResult(
            status="blocked_shared_canon_workflow",
            reason=detail or "make agent-canon-ensure-latest failed",
            next_step=(
                "commit_or_push_proposal_then_open_agent-canon_PR_then_after_merge_"
                "run_make_agent-canon-ensure-latest"
            ),
            checklist_path=checklist_path,
            checklist_status=checklist_status,
        )

    return AgentCanonPreflightResult(
        status="pass",
        reason="agent-canon snapshot is current",
        next_step="none",
        checklist_path=checklist_path,
        checklist_status=checklist_status,
    )


def latest_checklist_status(project_root: Path) -> tuple[str, str]:
    """Return the expected latest-state checklist path and availability."""
    candidates = (
        project_root / "vendor" / "agent-canon" / LATEST_CHECKLIST,
        project_root / LATEST_CHECKLIST,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.relative_to(project_root).as_posix(), "present"
    return candidates[0].relative_to(project_root).as_posix(), "missing"


def agent_canon_update_surface_status(project_root: Path) -> str:
    """Return dirty status for paths that AgentCanon refresh can mutate."""
    if not is_git_worktree(project_root):
        return ""
    paths = ["vendor/agent-canon", ".gitmodules"]
    paths.extend(surface_manifest_paths(project_root))
    parent_status = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", *paths],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    submodule_root = project_root / "vendor" / "agent-canon"
    submodule_status = ""
    if (submodule_root / ".git").exists() and is_git_worktree(submodule_root):
        submodule_status = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=submodule_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    return "\n".join(part.strip() for part in (parent_status, submodule_status) if part.strip())


def surface_manifest_paths(project_root: Path) -> list[str]:
    """Return root paths that link-root may overwrite or remove."""
    script_path = project_root / "vendor" / "agent-canon" / SURFACE_MANIFEST
    if not script_path.is_file():
        script_path = project_root / SURFACE_MANIFEST
    if not script_path.is_file():
        return list(SHARED_CANON_DIRTY_PATH_PREFIXES)
    paths: list[str] = []
    for command in SURFACE_SPEC_COMMANDS:
        result = subprocess.run(
            [
                "python3",
                str(script_path),
                "--root",
                str(project_root),
                command,
            ],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return list(SHARED_CANON_DIRTY_PATH_PREFIXES)
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            paths.append(line.split(":", maxsplit=1)[0])
    return paths


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
