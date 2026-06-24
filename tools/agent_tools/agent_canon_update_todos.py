#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Tracks AgentCanon update TODOs that parent-repo agents must apply.
# upstream design ../../documents/agent-canon-parent-repo-latest-checklist.md parent repo latest-state workflow
# upstream design ../../documents/agent-canon-update-tasks.toml shared update TODO manifest
# downstream implementation ../../tools/agent_tools/agent_canon_preflight.py routes task-start agents through pending TODOs
# downstream implementation ../../tests/agent_tools/test_agent_canon_update_todos.py tests update TODO state transitions
# @dependency-end
"""Manage parent-repository TODOs introduced by AgentCanon updates."""

from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

DEFAULT_MANIFEST = Path("documents/agent-canon-update-tasks.toml")
DEFAULT_STATE_PATH = Path(".agent-canon/update-state.toml")
DEFAULT_GENERATED_PATH = Path(".agent-canon/update-todos.generated.md")
DEFAULT_PENDING_JSON_PATH = Path(".agent-canon/update-todos.pending.json")
DEFAULT_PREFIX = Path("vendor/agent-canon")
STATE_TABLE = "agent_canon_update"


@dataclass(frozen=True)
class Git:
    """Small repository-local git runner."""

    root: Path

    def output(self, *args: str, check: bool = True) -> str:
        """Run git and return stripped stdout."""
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=False,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(detail or f"git {' '.join(args)} failed")
        return result.stdout.strip()

    def commit_exists(self, commit: str) -> bool:
        """Return whether commit exists in this clone."""
        result = subprocess.run(
            ["git", "-C", str(self.root), "cat-file", "-e", f"{commit}^{{commit}}"],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def is_same(self, left: str, right: str) -> bool:
        """Return whether two revisions resolve to the same commit."""
        left_sha = self.output("rev-parse", left, check=False)
        right_sha = self.output("rev-parse", right, check=False)
        return bool(left_sha and right_sha and left_sha == right_sha)

    def is_ancestor_or_equal(self, ancestor: str, descendant: str) -> bool:
        """Return whether ancestor is contained in descendant history."""
        if self.is_same(ancestor, descendant):
            return True
        result = subprocess.run(
            ["git", "-C", str(self.root), "merge-base", "--is-ancestor", ancestor, descendant],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode in {0, 1}:
            return result.returncode == 0
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or "git history check failed")


@dataclass(frozen=True)
class UpdateTask:
    """One parent-repo TODO carried by the AgentCanon manifest."""

    task_id: str
    title: str
    introduced_after: str
    severity: str
    applies_to: tuple[str, ...]
    summary: str
    actions: tuple[str, ...]
    acceptance: tuple[str, ...]
    paths: tuple[str, ...]

    @classmethod
    def from_mapping(cls, item: Mapping[str, object]) -> UpdateTask:
        """Create a task from one TOML table."""
        return cls(
            task_id=required_string(item, "id"),
            title=required_string(item, "title"),
            introduced_after=required_string(item, "introduced_after"),
            severity=required_string(item, "severity"),
            applies_to=string_tuple(item, "applies_to"),
            summary=required_string(item, "summary"),
            actions=string_tuple(item, "actions"),
            acceptance=string_tuple(item, "acceptance"),
            paths=string_tuple(item, "paths"),
        )

    def applies_to_parent_repo(self) -> bool:
        """Return whether this task is meant for AgentCanon parent repositories."""
        return "all" in self.applies_to or "parent_repo" in self.applies_to

    def payload(self) -> dict[str, object]:
        """Return a machine-readable task object for parent agents."""
        return {
            "id": self.task_id,
            "title": self.title,
            "introduced_after": self.introduced_after,
            "severity": self.severity,
            "applies_to": list(self.applies_to),
            "summary": self.summary,
            "actions": list(self.actions),
            "acceptance": list(self.acceptance),
            "paths": list(self.paths),
        }


@dataclass(frozen=True)
class UpdateState:
    """Per-parent repository AgentCanon update TODO state."""

    tasks_applied_through: str
    completed_tasks: frozenset[str]
    deferred_tasks: frozenset[str]
    raw_completed: Mapping[str, Mapping[str, str]]
    raw_deferred: Mapping[str, Mapping[str, str]]

    def is_resolved(self, task_id: str) -> bool:
        """Return whether a task has been completed or explicitly deferred."""
        return task_id in self.completed_tasks or task_id in self.deferred_tasks


@dataclass(frozen=True)
class Plan:
    """Computed parent-repo AgentCanon update TODO status."""

    status: str
    next_action: str
    reason: str
    target_commit: str
    state_commit: str
    pending_tasks: tuple[UpdateTask, ...]
    resolved_tasks: tuple[UpdateTask, ...]
    manifest_path: Path
    state_path: Path
    generated_path: Path
    pending_json_path: Path

    def output_lines(self) -> list[str]:
        """Return machine-readable status lines."""
        first = self.pending_tasks[0] if self.pending_tasks else None
        return [
            f"AGENT_CANON_UPDATE_TODO_STATUS={self.status}",
            f"AGENT_CANON_UPDATE_TODO_REASON={self.reason}",
            f"AGENT_CANON_UPDATE_TODO_NEXT={self.next_action}",
            f"AGENT_CANON_UPDATE_TODO_TARGET_COMMIT={self.target_commit}",
            f"AGENT_CANON_UPDATE_TODO_STATE_COMMIT={self.state_commit}",
            f"AGENT_CANON_UPDATE_TODO_PENDING_COUNT={len(self.pending_tasks)}",
            f"AGENT_CANON_UPDATE_TODO_RESOLVED_UNACKED_COUNT={len(self.resolved_tasks)}",
            f"AGENT_CANON_UPDATE_TODO_TASKS={','.join(task.task_id for task in self.pending_tasks)}",
            f"AGENT_CANON_UPDATE_TODO_RESOLVED_TASKS={','.join(task.task_id for task in self.resolved_tasks)}",
            f"AGENT_CANON_UPDATE_TODO_MANIFEST={self.manifest_path.as_posix()}",
            f"AGENT_CANON_UPDATE_TODO_STATE={self.state_path.as_posix()}",
            f"AGENT_CANON_UPDATE_TODO_GENERATED={self.generated_path.as_posix()}",
            f"AGENT_CANON_UPDATE_TODO_PENDING_JSON={self.pending_json_path.as_posix()}",
            f"AGENT_CANON_UPDATE_TODO_FIRST_TASK={first.task_id if first else ''}",
            f"AGENT_CANON_UPDATE_TODO_FIRST_SEVERITY={first.severity if first else ''}",
            f"AGENT_CANON_UPDATE_TODO_FIRST_ACTION={first.actions[0] if first and first.actions else ''}",
            f"AGENT_CANON_UPDATE_TODO_FIRST_PATHS={','.join(first.paths) if first else ''}",
        ]


@dataclass(frozen=True)
class AcknowledgeDecision:
    """Result of deciding whether update TODO state can be acknowledged."""

    plan: Plan
    state: UpdateState | None

    def can_acknowledge(self) -> bool:
        """Return whether every range task has been resolved."""
        return self.state is not None and not self.plan.pending_tasks


@dataclass(frozen=True)
class Paths:
    """Resolved parent repository and AgentCanon paths."""

    root: Path
    canon_root: Path
    manifest_path: Path
    state_path: Path
    generated_path: Path
    pending_json_path: Path
    prefix: Path

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> Paths:
        """Resolve paths from CLI arguments."""
        root = Path(args.root).resolve()
        prefix = Path(args.agent_canon_path)
        canon_root = (root / prefix).resolve()
        manifest = Path(args.manifest) if args.manifest else DEFAULT_MANIFEST
        if not canon_root.exists():
            canon_root = root
        return cls(
            root=root,
            canon_root=canon_root,
            manifest_path=resolve_manifest(root, canon_root, manifest),
            state_path=root / Path(args.state_path),
            generated_path=root / Path(args.generated_path),
            pending_json_path=root / Path(args.pending_json_path),
            prefix=prefix,
        )

    def relative(self, path: Path) -> Path:
        """Return a stable root-relative path when possible."""
        try:
            return path.relative_to(self.root)
        except ValueError:
            return path


def required_string(mapping: Mapping[str, object], key: str) -> str:
    """Return one required string value."""
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"manifest task missing string field: {key}")
    return value.strip()


def string_tuple(mapping: Mapping[str, object], key: str) -> tuple[str, ...]:
    """Return one string sequence value."""
    value = mapping.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise RuntimeError(f"manifest task missing list field: {key}")
    sequence = cast(Sequence[object], value)
    return tuple(item for item in sequence if isinstance(item, str) and item.strip())


def resolve_manifest(root: Path, canon_root: Path, manifest: Path) -> Path:
    """Resolve the update task manifest through parent or AgentCanon root."""
    if manifest.is_absolute():
        return manifest
    canon_candidate = canon_root / manifest
    root_candidate = root / manifest
    if canon_candidate.exists():
        return canon_candidate
    return root_candidate


def load_manifest(path: Path) -> tuple[UpdateTask, ...]:
    """Load shared update tasks."""
    if not path.is_file():
        raise RuntimeError(f"manifest missing: {path}")
    data = cast(Mapping[str, object], tomllib.loads(path.read_text(encoding="utf-8")))
    raw_tasks_value = data.get("task", [])
    if not isinstance(raw_tasks_value, list):
        raise RuntimeError("manifest field [[task]] must be a list")
    raw_tasks = cast(list[object], raw_tasks_value)
    task_mappings = [string_key_mapping(item) for item in raw_tasks]
    tasks = [UpdateTask.from_mapping(item) for item in task_mappings if item is not None]
    return tuple(task for task in tasks if task.applies_to_parent_repo())


def load_state(path: Path) -> UpdateState | None:
    """Load parent repo update state when present."""
    if not path.is_file():
        return None
    data = cast(Mapping[str, object], tomllib.loads(path.read_text(encoding="utf-8")))
    table_value = data.get(STATE_TABLE)
    if not isinstance(table_value, Mapping):
        raise RuntimeError(f"{path} missing [{STATE_TABLE}]")
    table = cast(Mapping[str, object], table_value)
    commit = table.get("tasks_applied_through")
    if not isinstance(commit, str) or not commit.strip():
        raise RuntimeError(f"{path} missing {STATE_TABLE}.tasks_applied_through")
    completed = nested_string_mapping(data.get("completed_tasks"))
    deferred = nested_string_mapping(data.get("deferred_tasks"))
    return UpdateState(
        tasks_applied_through=commit.strip(),
        completed_tasks=frozenset(completed),
        deferred_tasks=frozenset(deferred),
        raw_completed=completed,
        raw_deferred=deferred,
    )


def nested_string_mapping(value: object) -> Mapping[str, Mapping[str, str]]:
    """Return a nested string mapping from TOML table values."""
    if not isinstance(value, Mapping):
        return {}
    outer = cast(Mapping[object, object], value)
    result: dict[str, dict[str, str]] = {}
    for key, inner in outer.items():
        if not isinstance(key, str) or not isinstance(inner, Mapping):
            continue
        inner_mapping = cast(Mapping[object, object], inner)
        result[key] = {
            inner_key: inner_value
            for inner_key, inner_value in inner_mapping.items()
            if isinstance(inner_key, str) and isinstance(inner_value, str)
        }
    return result


def string_key_mapping(value: object) -> Mapping[str, object] | None:
    """Return value as a string-keyed mapping when possible."""
    if not isinstance(value, Mapping):
        return None
    mapping = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        return None
    return cast(Mapping[str, object], mapping)


def parent_target_commit(paths: Paths, explicit_target: str) -> str:
    """Return the AgentCanon commit the parent repo currently targets."""
    if explicit_target:
        return explicit_target
    parent_git = Git(paths.root)
    submodule_ref = f"HEAD:{paths.prefix.as_posix()}"
    submodule_commit = parent_git.output("rev-parse", submodule_ref, check=False)
    if submodule_commit:
        return submodule_commit
    return Git(paths.canon_root).output("rev-parse", "HEAD")


def task_in_update_range(task: UpdateTask, state: UpdateState, target: str, git: Git) -> bool:
    """Return whether one task falls between parent state and target pin."""
    boundary = task.introduced_after
    if not git.commit_exists(boundary) or not git.commit_exists(target):
        raise RuntimeError(f"git history unavailable for {task.task_id}")
    if git.is_same(boundary, target):
        return False
    return git.is_ancestor_or_equal(state.tasks_applied_through, boundary) and (
        git.is_ancestor_or_equal(boundary, target)
    )


def build_plan(paths: Paths, target_commit: str) -> Plan:
    """Build the current TODO routing plan."""
    relative_manifest = paths.relative(paths.manifest_path)
    relative_state = paths.relative(paths.state_path)
    relative_generated = paths.relative(paths.generated_path)
    relative_pending_json = paths.relative(paths.pending_json_path)
    try:
        tasks = load_manifest(paths.manifest_path)
    except RuntimeError as exc:
        return Plan(
            status="manifest_missing",
            next_action="repair_agent_canon_checkout",
            reason=str(exc),
            target_commit=target_commit,
            state_commit="unknown",
            pending_tasks=(),
            resolved_tasks=(),
            manifest_path=relative_manifest,
            state_path=relative_state,
            generated_path=relative_generated,
            pending_json_path=relative_pending_json,
        )

    state = load_state(paths.state_path)
    if state is None:
        return Plan(
            status="state_missing",
            next_action="initialize_agent_canon_update_state",
            reason="parent repo has no .agent-canon/update-state.toml",
            target_commit=target_commit,
            state_commit="missing",
            pending_tasks=(),
            resolved_tasks=(),
            manifest_path=relative_manifest,
            state_path=relative_state,
            generated_path=relative_generated,
            pending_json_path=relative_pending_json,
        )

    try:
        pending, resolved = classify_tasks(tasks, state, target_commit, Git(paths.canon_root))
    except RuntimeError as exc:
        return Plan(
            status="history_unavailable",
            next_action="fetch_agent_canon_history_then_apply_update_todos",
            reason=str(exc),
            target_commit=target_commit,
            state_commit=state.tasks_applied_through,
            pending_tasks=(),
            resolved_tasks=(),
            manifest_path=relative_manifest,
            state_path=relative_state,
            generated_path=relative_generated,
            pending_json_path=relative_pending_json,
        )
    return resolved_plan(
        pending=pending,
        resolved=resolved,
        target_commit=target_commit,
        state=state,
        paths=paths,
    )


def classify_tasks(
    tasks: tuple[UpdateTask, ...],
    state: UpdateState,
    target_commit: str,
    git: Git,
) -> tuple[tuple[UpdateTask, ...], tuple[UpdateTask, ...]]:
    """Split range tasks into open and resolved-but-unacknowledged buckets."""
    pending: list[UpdateTask] = []
    resolved: list[UpdateTask] = []
    for task in tasks:
        if not task_in_update_range(task, state, target_commit, git):
            continue
        if state.is_resolved(task.task_id):
            resolved.append(task)
        else:
            pending.append(task)
    return tuple(pending), tuple(resolved)


def resolved_plan(
    *,
    pending: tuple[UpdateTask, ...],
    resolved: tuple[UpdateTask, ...],
    target_commit: str,
    state: UpdateState,
    paths: Paths,
) -> Plan:
    """Create a Plan from task buckets."""
    if pending:
        status = "pending"
        next_action = "apply_agent_canon_update_todos"
        reason = "parent repo must apply AgentCanon update TODOs before new work"
    elif resolved:
        status = "ready_to_ack"
        next_action = "acknowledge_agent_canon_update_todos"
        reason = "all range TODOs are resolved; advance tasks_applied_through"
    else:
        status = "pass"
        next_action = "continue_parent_workflow"
        reason = "no AgentCanon update TODOs are pending for this parent repo"
    return Plan(
        status=status,
        next_action=next_action,
        reason=reason,
        target_commit=target_commit,
        state_commit=state.tasks_applied_through,
        pending_tasks=pending,
        resolved_tasks=resolved,
        manifest_path=paths.relative(paths.manifest_path),
        state_path=paths.relative(paths.state_path),
        generated_path=paths.relative(paths.generated_path),
        pending_json_path=paths.relative(paths.pending_json_path),
    )


def write_plan_outputs(plan: Plan, root: Path) -> None:
    """Write generated parent-repo TODO views."""
    markdown_path = root / plan.generated_path
    json_path = root / plan.pending_json_path
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_plan_markdown(plan), encoding="utf-8")
    json_path.write_text(render_pending_json(plan), encoding="utf-8")


def render_plan_markdown(plan: Plan) -> str:
    """Render a generated TODO report."""
    lines = [
        "# AgentCanon Update TODOs",
        "",
        f"- status: {plan.status}",
        f"- next_action: {plan.next_action}",
        f"- target_commit: `{plan.target_commit}`",
        f"- tasks_applied_through: `{plan.state_commit}`",
        "",
    ]
    if not plan.pending_tasks:
        lines.append("No open AgentCanon update TODOs.")
    for task in plan.pending_tasks:
        lines.extend(render_task_markdown(task))
    if plan.resolved_tasks:
        lines.extend(["", "## Resolved But Unacknowledged", ""])
        lines.extend(f"- `{task.task_id}`: {task.title}" for task in plan.resolved_tasks)
    return "\n".join(lines).rstrip() + "\n"


def render_task_markdown(task: UpdateTask) -> list[str]:
    """Render one task section."""
    lines = [
        "",
        f"## {task.task_id}: {task.title}",
        "",
        f"- severity: {task.severity}",
        f"- introduced_after: `{task.introduced_after}`",
        f"- summary: {task.summary}",
        "",
        "Actions:",
    ]
    lines.extend(f"- [ ] {action}" for action in task.actions)
    lines.extend(["", "Acceptance:"])
    lines.extend(f"- [ ] {item}" for item in task.acceptance)
    if task.paths:
        lines.extend(["", "Expected paths:"])
        lines.extend(f"- `{path}`" for path in task.paths)
    return lines


def render_pending_json(plan: Plan) -> str:
    """Render pending tasks as compact JSON."""
    payload = {
        "status": plan.status,
        "next_action": plan.next_action,
        "target_commit": plan.target_commit,
        "state_commit": plan.state_commit,
        "state_path": plan.state_path.as_posix(),
        "generated_path": plan.generated_path.as_posix(),
        "pending_json_path": plan.pending_json_path.as_posix(),
        "pending_tasks": [task.task_id for task in plan.pending_tasks],
        "pending_task_details": [task.payload() for task in plan.pending_tasks],
        "resolved_unacknowledged_tasks": [task.task_id for task in plan.resolved_tasks],
        "resolved_unacknowledged_task_details": [
            task.payload() for task in plan.resolved_tasks
        ],
        "operator_protocol": {
            "pending_next_action": "apply_or_defer_pending_tasks_before_unrelated_work",
            "complete_command": (
                "python3 tools/agent_tools/agent_canon_update_todos.py complete "
                "<task-id> --note '<evidence>'"
            ),
            "not_applicable_command": (
                "python3 tools/agent_tools/agent_canon_update_todos.py not-applicable "
                "<task-id> --reason '<evidence>' --owner '<owner>'"
            ),
            "defer_command": (
                "python3 tools/agent_tools/agent_canon_update_todos.py defer "
                "<task-id> --reason '<blocker>' --owner '<owner>'"
            ),
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def write_initial_state(paths: Paths, target_commit: str, *, force: bool) -> str:
    """Create the parent repository state file and scoped ignore file."""
    paths.state_path.parent.mkdir(parents=True, exist_ok=True)
    ignore_path = paths.state_path.parent / ".gitignore"
    if not ignore_path.exists() or force:
        ignore_path.write_text("*\n!.gitignore\n!update-state.toml\n", encoding="utf-8")
    if paths.state_path.exists() and not force:
        return "exists"
    state = UpdateState(
        tasks_applied_through=target_commit,
        completed_tasks=frozenset(),
        deferred_tasks=frozenset(),
        raw_completed={},
        raw_deferred={},
    )
    paths.state_path.write_text(render_state(state), encoding="utf-8")
    return "created"


def render_state(state: UpdateState) -> str:
    """Render parent repo update state as TOML."""
    lines = [
        "# @dependency-start",
        "# contract data",
        "# responsibility Tracks this parent repo's applied AgentCanon update TODO boundary.",
        "# upstream design ../vendor/agent-canon/documents/agent-canon-parent-repo-latest-checklist.md parent update workflow",
        "# upstream design ../vendor/agent-canon/documents/agent-canon-update-tasks.toml shared update TODO manifest",
        "# downstream implementation ../tools/agent_tools/agent_canon_update_todos.py advances this state",
        "# @dependency-end",
        "",
        f"[{STATE_TABLE}]",
        f"tasks_applied_through = {json.dumps(state.tasks_applied_through)}",
    ]
    lines.extend(render_task_tables("completed_tasks", state.raw_completed))
    lines.extend(render_task_tables("deferred_tasks", state.raw_deferred))
    return "\n".join(lines).rstrip() + "\n"


def render_task_tables(prefix: str, table: Mapping[str, Mapping[str, str]]) -> list[str]:
    """Render nested task status tables."""
    lines: list[str] = []
    for task_id, values in sorted(table.items()):
        lines.extend(["", f"[{prefix}.{json.dumps(task_id)}]"])
        for key, value in sorted(values.items()):
            lines.append(f"{key} = {json.dumps(value)}")
    return lines


def timestamp() -> str:
    """Return a stable UTC timestamp string."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def update_task_state(
    paths: Paths,
    task_id: str,
    *,
    status: str,
    note: str,
    owner: str,
    target_commit: str,
) -> None:
    """Mark one task complete or deferred."""
    state = load_state(paths.state_path)
    if state is None:
        raise RuntimeError("run init before marking AgentCanon update TODOs")
    completed = dict(state.raw_completed)
    deferred = dict(state.raw_deferred)
    entry = {"status": status, "note": note, "owner": owner, "updated_at": timestamp()}
    if status == "done":
        completed[task_id] = entry
        deferred.pop(task_id, None)
    else:
        deferred[task_id] = entry
        completed.pop(task_id, None)
    new_state = UpdateState(
        tasks_applied_through=state.tasks_applied_through,
        completed_tasks=frozenset(completed),
        deferred_tasks=frozenset(deferred),
        raw_completed=completed,
        raw_deferred=deferred,
    )
    paths.state_path.write_text(render_state(new_state), encoding="utf-8")
    print(f"AGENT_CANON_UPDATE_TODO_MARKED={task_id}")
    print(f"AGENT_CANON_UPDATE_TODO_MARKED_STATUS={status}")
    print(f"AGENT_CANON_UPDATE_TODO_TARGET_COMMIT={target_commit}")


def acknowledge_decision(paths: Paths, target_commit: str) -> AcknowledgeDecision:
    """Return whether update TODO state can advance."""
    state = load_state(paths.state_path)
    if state is None:
        return AcknowledgeDecision(
            plan=Plan(
                status="state_missing",
                next_action="initialize_agent_canon_update_state",
                reason="parent repo has no .agent-canon/update-state.toml",
                target_commit=target_commit,
                state_commit="missing",
                pending_tasks=(),
                resolved_tasks=(),
                manifest_path=paths.relative(paths.manifest_path),
                state_path=paths.relative(paths.state_path),
                generated_path=paths.relative(paths.generated_path),
                pending_json_path=paths.relative(paths.pending_json_path),
            ),
            state=None,
        )
    plan = build_plan(paths, target_commit)
    return AcknowledgeDecision(plan=plan, state=state)


def write_acknowledged_state(paths: Paths, state: UpdateState, target_commit: str) -> None:
    """Advance tasks_applied_through in the parent state file."""
    new_state = UpdateState(
        tasks_applied_through=target_commit,
        completed_tasks=state.completed_tasks,
        deferred_tasks=state.deferred_tasks,
        raw_completed=state.raw_completed,
        raw_deferred=state.raw_deferred,
    )
    paths.state_path.write_text(render_state(new_state), encoding="utf-8")


def print_plan(plan: Plan) -> None:
    """Print one machine-readable plan."""
    for line in plan.output_lines():
        print(line)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Parent repository root.")
    parser.add_argument("--agent-canon-path", default=DEFAULT_PREFIX.as_posix())
    parser.add_argument("--manifest", help="Manifest path relative to AgentCanon root.")
    parser.add_argument("--state-path", default=DEFAULT_STATE_PATH.as_posix())
    parser.add_argument("--generated-path", default=DEFAULT_GENERATED_PATH.as_posix())
    parser.add_argument("--pending-json-path", default=DEFAULT_PENDING_JSON_PATH.as_posix())
    parser.add_argument("--target-commit", help="Override target AgentCanon commit.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="Print current update TODO routing.")
    plan.add_argument("--write", action="store_true", help="Write generated TODO views.")
    subparsers.add_parser("status", help="Alias for plan without writes.")
    init = subparsers.add_parser("init", help="Initialize parent repo update state.")
    init.add_argument("--force", action="store_true", help="Overwrite existing state.")
    complete = subparsers.add_parser("complete", help="Mark one TODO complete.")
    complete.add_argument("task_id")
    complete.add_argument("--note", required=True)
    complete.add_argument("--owner", default="agent")
    defer = subparsers.add_parser("defer", help="Mark one TODO deferred.")
    defer.add_argument("task_id")
    defer.add_argument("--reason", required=True)
    defer.add_argument("--owner", required=True)
    not_applicable = subparsers.add_parser(
        "not-applicable",
        help="Mark one TODO not applicable to this parent repo.",
    )
    not_applicable.add_argument("task_id")
    not_applicable.add_argument("--reason", required=True)
    not_applicable.add_argument("--owner", required=True)
    subparsers.add_parser("acknowledge", help="Advance tasks_applied_through.")
    return parser


def run_plan(paths: Paths, target_commit: str, *, write: bool) -> int:
    """Run plan/status command."""
    plan = build_plan(paths, target_commit)
    if write:
        write_plan_outputs(plan, paths.root)
    print_plan(plan)
    return 0


def main() -> int:
    """Run the update TODO command."""
    args = build_parser().parse_args()
    paths = Paths.from_args(args)
    try:
        target_commit = parent_target_commit(paths, args.target_commit or "")
        if args.command == "init":
            result = write_initial_state(paths, target_commit, force=args.force)
            print(f"AGENT_CANON_UPDATE_TODO_INIT={result}")
            print(f"AGENT_CANON_UPDATE_TODO_STATE={paths.relative(paths.state_path).as_posix()}")
            print(f"AGENT_CANON_UPDATE_TODO_TARGET_COMMIT={target_commit}")
            return 0
        if args.command in {"plan", "status"}:
            return run_plan(paths, target_commit, write=getattr(args, "write", False))
        if args.command == "complete":
            update_task_state(
                paths,
                args.task_id,
                status="done",
                note=args.note,
                owner=args.owner,
                target_commit=target_commit,
            )
            return 0
        if args.command == "defer":
            update_task_state(
                paths,
                args.task_id,
                status="deferred",
                note=args.reason,
                owner=args.owner,
                target_commit=target_commit,
            )
            return 0
        if args.command == "not-applicable":
            update_task_state(
                paths,
                args.task_id,
                status="not_applicable",
                note=args.reason,
                owner=args.owner,
                target_commit=target_commit,
            )
            return 0
        if args.command == "acknowledge":
            decision = acknowledge_decision(paths, target_commit)
            print_plan(decision.plan)
            if not decision.can_acknowledge() or decision.state is None:
                return 1
            write_acknowledged_state(paths, decision.state, target_commit)
            print("AGENT_CANON_UPDATE_TODO_ACKNOWLEDGED=yes")
            return 0
    except RuntimeError as exc:
        print("AGENT_CANON_UPDATE_TODO_STATUS=error")
        print(f"AGENT_CANON_UPDATE_TODO_REASON={exc}")
        print("AGENT_CANON_UPDATE_TODO_NEXT=repair_update_todo_state")
        return 1
    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
