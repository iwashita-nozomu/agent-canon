#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides agent canon preflight agent workflow automation.
# upstream design ../README.md shared automation index
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md defines task-entry freshness routing
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines PR-first shared-canon propagation
# upstream design ../../agents/workflows/derived-agent-canon-diff-workflow.md defines derived AgentCanon branch routing
# upstream design ../../documents/agent-canon-parent-repo-latest-checklist.md defines parent update TODO routing
# upstream implementation agent_canon_update_todos.py reports AgentCanon update TODO state
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
    ".codex/",
    ".github/AGENTS.md",
    ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
    ".github/workflows/agent-coordination.yml",
    "AGENTS.md",
    "ROOT_AGENTS.md",
    "agents/",
    "documents/SHARED_RUNTIME_SURFACES.md",
    "mcp/",
    "tools/sync_agent_canon.sh",
    "vendor/agent-canon",
)
LATEST_CHECKLIST = Path("documents/agent-canon-parent-repo-latest-checklist.md")
UPDATE_TODO_TOOL = Path("tools/agent_tools/agent_canon_update_todos.py")
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
    update_todo_status: str = "not_checked"
    update_todo_reason: str = "not checked"
    update_todo_next: str = "not_checked"
    update_todo_pending_count: str = "0"
    update_todo_resolved_count: str = "0"
    update_todo_tasks: str = ""
    update_todo_resolved_tasks: str = ""
    update_todo_state: str = ".agent-canon/update-state.toml"
    update_todo_manifest: str = "vendor/agent-canon/documents/agent-canon-update-tasks.toml"
    update_todo_generated: str = ".agent-canon/update-todos.generated.md"
    update_todo_pending_json: str = ".agent-canon/update-todos.pending.json"
    update_todo_first_task: str = ""
    update_todo_first_severity: str = ""
    update_todo_first_action: str = ""
    update_todo_first_paths: str = ""


@dataclass(frozen=True)
class UpdateTodoStatusReader:
    """Reads AgentCanon update TODO status from the parent root view."""

    project_root: Path

    def read(self) -> dict[str, str]:
        """Return update TODO routing fields without blocking task start."""
        tool_path = resolve_update_todo_tool(self.project_root)
        if tool_path is None:
            fields = {
                "AGENT_CANON_UPDATE_TODO_STATUS": "tool_missing",
                "AGENT_CANON_UPDATE_TODO_REASON": "agent_canon_update_todos.py not found",
                "AGENT_CANON_UPDATE_TODO_NEXT": "repair_agent_canon_checkout",
            }
            print_update_todo_fields(fields)
            return fields
        result = subprocess.run(
            ["python3", str(tool_path), "--root", str(self.project_root), "status"],
            cwd=self.project_root,
            check=False,
            capture_output=True,
            text=True,
        )
        fields = update_todo_fields_from_result(result)
        print_update_todo_fields(fields)
        return fields


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
        return base_preflight_result(
            status="skipped_by_flag",
            reason="agent-canon preflight skipped by command-line flag",
            next_step="run make agent-canon-ensure-latest manually before editing shared surfaces",
            checklist_path=checklist_path,
            checklist_status=checklist_status,
        )

    if is_agent_canon_source_repo(project_root):
        return base_preflight_result(
            status="skipped_source_canon",
            reason="workspace is the shared agent-canon source repository",
            next_step="ensure derived template snapshots after committing canon changes",
            checklist_path=checklist_path,
            checklist_status=checklist_status,
        )

    if not is_git_worktree(project_root):
        return base_preflight_result(
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
        return base_preflight_result(
            status="blocked_shared_canon_workflow",
            reason=detail or "make agent-canon-ensure-latest failed",
            next_step=(
                "commit_agentcanon_branch_then_merge-main-into-current-preserve-dirty_then_open_agent-canon_PR_"
                "then_after_merge_run_make_agent-canon-ensure-latest"
            ),
            checklist_path=checklist_path,
            checklist_status=checklist_status,
        )

    todo_result = UpdateTodoStatusReader(project_root).read()
    return successful_preflight_result(checklist_path, checklist_status, todo_result)


def base_preflight_result(
    *,
    status: str,
    reason: str,
    next_step: str,
    checklist_path: str,
    checklist_status: str,
) -> AgentCanonPreflightResult:
    """Create a preflight result without update TODO fields."""
    return AgentCanonPreflightResult(
        status=status,
        reason=reason,
        next_step=next_step,
        checklist_path=checklist_path,
        checklist_status=checklist_status,
    )


def successful_preflight_result(
    checklist_path: str,
    checklist_status: str,
    todo_result: dict[str, str],
) -> AgentCanonPreflightResult:
    """Create a passing preflight result with update TODO routing fields."""
    return AgentCanonPreflightResult(
        status="pass",
        reason="agent-canon snapshot is current",
        next_step=todo_result.get("AGENT_CANON_UPDATE_TODO_NEXT", "none"),
        checklist_path=checklist_path,
        checklist_status=checklist_status,
        update_todo_status=todo_result.get("AGENT_CANON_UPDATE_TODO_STATUS", "not_checked"),
        update_todo_reason=todo_result.get("AGENT_CANON_UPDATE_TODO_REASON", "not checked"),
        update_todo_next=todo_result.get("AGENT_CANON_UPDATE_TODO_NEXT", "not_checked"),
        update_todo_pending_count=todo_result.get("AGENT_CANON_UPDATE_TODO_PENDING_COUNT", "0"),
        update_todo_resolved_count=todo_result.get(
            "AGENT_CANON_UPDATE_TODO_RESOLVED_UNACKED_COUNT",
            "0",
        ),
        update_todo_tasks=todo_result.get("AGENT_CANON_UPDATE_TODO_TASKS", ""),
        update_todo_resolved_tasks=todo_result.get(
            "AGENT_CANON_UPDATE_TODO_RESOLVED_TASKS",
            "",
        ),
        update_todo_state=todo_result.get(
            "AGENT_CANON_UPDATE_TODO_STATE",
            ".agent-canon/update-state.toml",
        ),
        update_todo_manifest=todo_result.get(
            "AGENT_CANON_UPDATE_TODO_MANIFEST",
            "vendor/agent-canon/documents/agent-canon-update-tasks.toml",
        ),
        update_todo_generated=todo_result.get(
            "AGENT_CANON_UPDATE_TODO_GENERATED",
            ".agent-canon/update-todos.generated.md",
        ),
        update_todo_pending_json=todo_result.get(
            "AGENT_CANON_UPDATE_TODO_PENDING_JSON",
            ".agent-canon/update-todos.pending.json",
        ),
        update_todo_first_task=todo_result.get("AGENT_CANON_UPDATE_TODO_FIRST_TASK", ""),
        update_todo_first_severity=todo_result.get(
            "AGENT_CANON_UPDATE_TODO_FIRST_SEVERITY",
            "",
        ),
        update_todo_first_action=todo_result.get("AGENT_CANON_UPDATE_TODO_FIRST_ACTION", ""),
        update_todo_first_paths=todo_result.get("AGENT_CANON_UPDATE_TODO_FIRST_PATHS", ""),
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


def update_todo_fields_from_result(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    """Convert the update TODO tool result into preflight fields."""
    fields = parse_machine_fields(result.stdout)
    if result.returncode != 0:
        fields.setdefault("AGENT_CANON_UPDATE_TODO_STATUS", "error")
        fields.setdefault(
            "AGENT_CANON_UPDATE_TODO_REASON",
            (result.stderr or result.stdout).strip() or "update TODO status failed",
        )
        fields.setdefault("AGENT_CANON_UPDATE_TODO_NEXT", "repair_update_todo_state")
    return fields


def resolve_update_todo_tool(project_root: Path) -> Path | None:
    """Return the update TODO tool path from root view or vendor source."""
    candidates = (
        project_root / UPDATE_TODO_TOOL,
        project_root / "vendor" / "agent-canon" / UPDATE_TODO_TOOL,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def parse_machine_fields(text: str) -> dict[str, str]:
    """Parse KEY=value status lines."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        if key.startswith("AGENT_CANON_UPDATE_TODO_"):
            fields[key] = value
    return fields


def print_update_todo_fields(fields: dict[str, str]) -> None:
    """Emit update TODO status fields for task-start logs."""
    for key in sorted(fields):
        print(f"{key}={fields[key]}")


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
