#!/usr/bin/env python3
"""Shared runtime helpers for the permanent agent team."""

from __future__ import annotations

import json
import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TEAM_CONFIG_PATH = ROOT / "agents" / "agents_config.json"
MEMORY_LOADOUT_PATH = ROOT / "memory" / "subagent_loadouts.yaml"
DEFAULT_REPORT_ROOT = Path("reports") / "agents"
TEMPLATE_ROOT = ROOT / "agents" / "templates"
PYTHON_SUFFIXES = {".py", ".pyi"}
CPP_SUFFIXES = {
    ".c",
    ".cc",
    ".cp",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".ixx",
    ".tpp",
    ".ipp",
}
CPP_PATH_MARKERS = (
    "CMakeLists.txt",
    "cmake/",
    "src/",
    "include/",
    "lib/",
)


def resolve_report_root(
    report_root: str | None,
    workspace_root: Path | None = None,
) -> Path:
    """Resolve the report root relative to the active workspace by default."""
    base_root = workspace_root.resolve() if workspace_root is not None else Path.cwd().resolve()
    if report_root is None:
        return (base_root / DEFAULT_REPORT_ROOT).resolve()
    candidate = Path(report_root)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_root / candidate).resolve()


@dataclass(frozen=True)
class WritePolicy:
    """Describe how one role may write to the filesystem."""

    mode: str
    allowed_artifacts: tuple[str, ...]
    requires_worktree_scope: bool = False
    notes: str = ""


@dataclass(frozen=True)
class Role:
    """Describe one permanent team role."""

    id: str
    owns: tuple[str, ...]
    required_outputs: tuple[str, ...]
    activation: str
    write_policy: WritePolicy
    codex_agents: tuple[str, ...]


@dataclass(frozen=True)
class RoleWriteScope:
    """Resolved write scope for one role in one workspace."""

    role_id: str
    mode: str
    allowed_files: tuple[Path, ...]
    allowed_directories: tuple[Path, ...]
    requires_worktree_scope: bool
    worktree_scope_file: Path | None
    unresolved_reason: str | None
    notes: str


@dataclass(frozen=True)
class RoleMemoryLoadout:
    """Resolved fixed memory read and write surfaces for one role."""

    role_id: str
    read_files: tuple[Path, ...]
    method_files: tuple[Path, ...]
    candidate_file: Path | None
    allow_method_write: bool
    allow_global_write: bool
    notes: str


@dataclass(frozen=True)
class TeamConfig:
    """Materialized team configuration."""

    raw: dict[str, object]
    team: dict[str, object]
    always_on_roles: tuple[Role, ...]
    specialist_roles: tuple[Role, ...]
    handoffs: tuple[dict[str, object], ...]
    context_policies: tuple[dict[str, object], ...]
    activation_rules: tuple[dict[str, object], ...]
    quality_gates: tuple[str, ...]
    artifacts: dict[str, str]


@dataclass(frozen=True)
class TaskCatalog:
    """Materialized task catalog."""

    raw: dict[str, object]
    workflow_families: tuple[dict[str, object], ...]
    tasks: tuple[dict[str, object], ...]
    review_packs: tuple[dict[str, object], ...]


def load_team_config(path: Path = TEAM_CONFIG_PATH) -> TeamConfig:
    """Load the canonical team config."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    team = dict(raw["team"])
    always_on_roles = tuple(_parse_role(role, "always") for role in raw["always_on_roles"])
    specialist_roles = tuple(_parse_role(role, "optional") for role in raw["specialist_roles"])
    handoffs = tuple(dict(item) for item in raw["handoffs"])
    context_policies = tuple(dict(item) for item in raw["context_policies"])
    activation_rules = tuple(dict(item) for item in raw["activation_rules"])
    quality_gates = tuple(str(item) for item in raw["quality_gates"])
    artifacts = {str(key): str(value) for key, value in dict(raw["artifacts"]).items()}
    return TeamConfig(
        raw=raw,
        team=team,
        always_on_roles=always_on_roles,
        specialist_roles=specialist_roles,
        handoffs=handoffs,
        context_policies=context_policies,
        activation_rules=activation_rules,
        quality_gates=quality_gates,
        artifacts=artifacts,
    )


def load_task_catalog(config: TeamConfig) -> TaskCatalog:
    """Load the task catalog referenced by the team config."""
    catalog_path = ROOT / str(config.team["task_catalog"])
    raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"task catalog must parse as a mapping: {catalog_path}")
    return TaskCatalog(
        raw=raw,
        workflow_families=_as_mapping_tuple(raw.get("workflow_families"), "workflow_families"),
        tasks=_as_mapping_tuple(raw.get("tasks"), "tasks"),
        review_packs=_as_mapping_tuple(raw.get("review_packs"), "review_packs"),
    )


def load_memory_loadouts(path: Path = MEMORY_LOADOUT_PATH) -> dict[str, object]:
    """Load the machine-readable role-to-memory routing config."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"memory loadout config must parse as a mapping: {path}")
    return data


def specialist_role_ids(config: TeamConfig) -> tuple[str, ...]:
    """Return specialist role ids."""
    return tuple(role.id for role in config.specialist_roles)


def resolve_role(config: TeamConfig, role_name: str) -> Role:
    """Resolve a role id to a role."""
    for role in config.always_on_roles + config.specialist_roles:
        if role_name == role.id:
            return role
    raise KeyError(f"unknown role: {role_name}")


def resolve_role_memory_loadout(
    role_name: str,
    loadouts: dict[str, object] | None = None,
) -> RoleMemoryLoadout:
    """Resolve one role's fixed memory loadout."""
    raw = loadouts if loadouts is not None else load_memory_loadouts()
    global_read_files = _as_string_tuple(raw.get("global_read_files"), "global_read_files")
    method_files_raw = raw.get("method_files")
    candidate_files_raw = raw.get("candidate_files")
    role_loadouts_raw = raw.get("role_loadouts")
    if not isinstance(method_files_raw, dict):
        raise RuntimeError("memory loadout method_files must be a mapping")
    if not isinstance(candidate_files_raw, dict):
        raise RuntimeError("memory loadout candidate_files must be a mapping")
    if not isinstance(role_loadouts_raw, dict):
        raise RuntimeError("memory loadout role_loadouts must be a mapping")
    if role_name not in role_loadouts_raw:
        raise KeyError(f"memory loadout missing role: {role_name}")
    entry = role_loadouts_raw[role_name]
    if not isinstance(entry, dict):
        raise RuntimeError(f"memory loadout entry must be a mapping for role {role_name}")

    method_keys = _as_string_tuple(entry.get("method_reads"), f"role_loadouts[{role_name}].method_reads")
    resolved_global_files = tuple((ROOT / relative).resolve() for relative in global_read_files)
    resolved_method_files = []
    for key in method_keys:
        relative = method_files_raw.get(key)
        if not isinstance(relative, str):
            raise RuntimeError(f"memory loadout method key missing or invalid: {key}")
        resolved_method_files.append((ROOT / relative).resolve())

    candidate_file: Path | None = None
    candidate_key = entry.get("candidate_file")
    if candidate_key is not None:
        if not isinstance(candidate_key, str):
            raise RuntimeError(f"memory loadout candidate key must be a string for role {role_name}")
        relative = candidate_files_raw.get(candidate_key)
        if not isinstance(relative, str):
            raise RuntimeError(f"memory loadout candidate key missing or invalid: {candidate_key}")
        candidate_file = (ROOT / relative).resolve()

    read_files = list(resolved_global_files)
    read_files.extend(resolved_method_files)
    if candidate_file is not None:
        read_files.append(candidate_file)

    return RoleMemoryLoadout(
        role_id=role_name,
        read_files=tuple(read_files),
        method_files=tuple(resolved_method_files),
        candidate_file=candidate_file,
        allow_method_write=bool(entry.get("allow_method_write", False)),
        allow_global_write=bool(entry.get("allow_global_write", False)),
        notes=str(entry.get("notes", "")),
    )


def task_ids(catalog: TaskCatalog) -> tuple[str, ...]:
    """Return known task ids from the catalog."""
    return tuple(str(task["id"]) for task in catalog.tasks)


def discover_changed_paths(workspace_root: Path) -> tuple[str, ...]:
    """Return changed paths from git status when available."""
    result = subprocess.run(
        ["git", "-C", str(workspace_root), "status", "--short"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ()

    changed: list[str] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.rstrip()
        if len(line) < 4:
            continue
        path_part = line[3:]
        if " -> " in path_part:
            _, path_part = path_part.split(" -> ", 1)
        normalized = path_part.strip()
        if normalized and normalized not in changed:
            changed.append(normalized)
    return tuple(changed)


def auto_language_specialists(
    workspace_root: Path,
    changed_paths: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Infer language-specific reviewers from changed paths."""
    candidate_paths = changed_paths or discover_changed_paths(workspace_root)
    selected: list[str] = []
    for raw_path in candidate_paths:
        normalized = raw_path.replace("\\", "/").lstrip("./")
        suffix = Path(normalized).suffix.lower()
        if (
            "python_reviewer" not in selected
            and (
                normalized.startswith("python/")
                or normalized.startswith("tests/")
                or suffix in PYTHON_SUFFIXES
            )
        ):
            selected.append("python_reviewer")
        if (
            "cpp_reviewer" not in selected
            and (
                suffix in CPP_SUFFIXES
                or any(
                    normalized == marker or normalized.startswith(marker)
                    for marker in CPP_PATH_MARKERS
                )
            )
        ):
            selected.append("cpp_reviewer")
    return tuple(selected)


def resolve_task_spec(catalog: TaskCatalog, task_id: str) -> dict[str, object]:
    """Resolve one task id from the catalog."""
    for task in catalog.tasks:
        if task.get("id") == task_id:
            return task
    raise KeyError(f"unknown task id: {task_id}")


def resolve_workflow_family(catalog: TaskCatalog, family_id: str) -> dict[str, object]:
    """Resolve one workflow family from the catalog."""
    for family in catalog.workflow_families:
        if family.get("id") == family_id:
            return family
    raise KeyError(f"unknown workflow family: {family_id}")


def default_specialists_for_task(
    config: TeamConfig,
    catalog: TaskCatalog,
    task_id: str,
    include_default_review_packs: bool = True,
) -> tuple[str, ...]:
    """Return task-default specialist ids including default review packs."""
    task = resolve_task_spec(catalog, task_id)
    family = resolve_workflow_family(catalog, str(task["family"]))
    family_roles = family.get("roles", {})
    if not isinstance(family_roles, dict):
        raise RuntimeError(f"workflow family roles must be a mapping for {family['id']}")
    family_specialists = _as_string_tuple(
        family_roles.get("specialists"),
        f"workflow_families[{family['id']}].roles.specialists",
    )
    selected: list[str] = []

    for role_id in _as_string_tuple(task.get("specialists"), f"tasks[{task_id}].specialists"):
        if role_id not in family_specialists:
            raise RuntimeError(
                f"task {task_id} specialist {role_id} is not declared in family {family['id']}"
            )
        resolve_role(config, role_id)
        if role_id not in selected:
            selected.append(role_id)

    if include_default_review_packs:
        for pack in catalog.review_packs:
            default_tasks = _as_string_tuple(
                pack.get("default_for_tasks"),
                f"review_packs[{pack['id']}].default_for_tasks",
            )
            if task_id not in default_tasks:
                continue
            for role_id in _as_string_tuple(
                pack.get("specialists"),
                f"review_packs[{pack['id']}].specialists",
            ):
                resolve_role(config, role_id)
                if role_id not in selected:
                    selected.append(role_id)

    return tuple(selected)


def select_roles(
    config: TeamConfig,
    enabled_specialists: list[str],
    full_team: bool,
) -> tuple[Role, ...]:
    """Return the active roles for one run."""
    if full_team:
        return config.always_on_roles + config.specialist_roles
    enabled_roles = tuple(resolve_role(config, name) for name in enabled_specialists)
    enabled_set = {role.id for role in enabled_roles}
    enabled_activations = {
        role.activation for role in enabled_roles if role in config.specialist_roles
    }
    selected_specialists = tuple(
        role
        for role in config.specialist_roles
        if role.id in enabled_set or role.activation in enabled_activations
    )
    return config.always_on_roles + selected_specialists


def iter_artifacts(config: TeamConfig, roles: tuple[Role, ...]) -> tuple[str, ...]:
    """Return unique artifact filenames in deterministic order."""
    ordered_artifacts: list[str] = []
    for role in roles:
        for output in role.required_outputs:
            if output not in ordered_artifacts:
                ordered_artifacts.append(output)
    ordered_artifacts.extend(
        [
            config.artifacts["team_manifest"],
            config.artifacts["verification"],
        ]
    )
    unique_artifacts: list[str] = []
    for artifact in ordered_artifacts:
        if artifact not in unique_artifacts:
            unique_artifacts.append(artifact)
    return tuple(unique_artifacts)


def render_template(template_name: str, replacements: dict[str, str]) -> str:
    """Load and fill a text template from agents/templates."""
    content = (TEMPLATE_ROOT / template_name).read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    return content


def has_template(artifact_name: str) -> bool:
    """Return whether a template exists for one artifact filename."""
    return (TEMPLATE_ROOT / artifact_name).is_file()


def required_output_templates_missing(
    config: TeamConfig,
    roles: tuple[Role, ...],
    allowed_missing: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return required output templates that are missing from agents/templates."""
    missing: list[str] = []
    for role in roles:
        for output in role.required_outputs:
            if output in allowed_missing:
                continue
            if output not in missing and not has_template(output):
                missing.append(output)
    return tuple(missing)


def create_run_bundle(
    config: TeamConfig,
    report_dir: Path,
    run_id: str,
    task: str,
    owner: str,
    created_at_iso: str,
    roles: tuple[Role, ...],
    workspace_root: Path,
) -> tuple[str, ...]:
    """Create the standard files for a run."""
    replacements = {
        "RUN_ID": run_id,
        "TASK": task,
        "OWNER": owner,
        "CREATED_AT": created_at_iso,
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    created_files = list(iter_artifacts(config, roles))
    for artifact in created_files:
        if has_template(artifact):
            (report_dir / artifact).write_text(
                render_template(artifact, replacements),
                encoding="utf-8",
            )
    (report_dir / config.artifacts["team_manifest"]).write_text(
        build_manifest(
            config=config,
            run_id=run_id,
            task=task,
            owner=owner,
            created_at_iso=created_at_iso,
            report_dir=report_dir,
            roles=roles,
            workspace_root=workspace_root,
        ),
        encoding="utf-8",
    )
    (report_dir / config.artifacts["verification"]).write_text(
        "\n".join(
            [
                f"run_id={run_id}",
                f"task={task}",
                f"owner={owner}",
                f"created_at_utc={created_at_iso}",
                "status=pending",
                "user_completion_report=locked",
                "closeout_gate_status=pending",
                "",
            ]
        ),
        encoding="utf-8",
    )
    unique_created_files: list[str] = []
    for artifact in created_files:
        if artifact not in unique_created_files:
            unique_created_files.append(artifact)
    return tuple(unique_created_files)


def build_manifest(
    config: TeamConfig,
    run_id: str,
    task: str,
    owner: str,
    created_at_iso: str,
    report_dir: Path,
    roles: tuple[Role, ...],
    workspace_root: Path,
) -> str:
    """Build the team manifest yaml."""
    memory_loadouts = load_memory_loadouts()
    lines = [
        "run:",
        f"  id: {run_id}",
        f"  task: {task!r}",
        f"  owner: {owner!r}",
        f"  created_at_utc: {created_at_iso}",
        f"  report_dir: {str(report_dir)!r}",
        f"  workspace_root: {str(workspace_root)!r}",
        f"  team_config: {str(TEAM_CONFIG_PATH)!r}",
        f"  team_runtime: {str(ROOT / 'tools' / 'agent_tools' / 'agent_team.py')!r}",
        f"  memory_loadout_config: {str(MEMORY_LOADOUT_PATH)!r}",
        f"  task_catalog: {str(ROOT / str(config.team['task_catalog']))!r}",
        "roles:",
    ]
    communication_protocol = config.team.get("communication_protocol")
    if communication_protocol is not None:
        lines.insert(
            9,
            f"  communication_protocol: {str(ROOT / str(communication_protocol))!r}",
        )
    for role in roles:
        lines.append(f"  - id: {role.id}")
        lines.append(f"    activation: {role.activation}")
        lines.append("    status: pending")
        if role.codex_agents:
            lines.append("    codex_agents:")
            for codex_agent in role.codex_agents:
                lines.append(f"      - {codex_agent}")
        lines.append("    owns:")
        for responsibility in role.owns:
            lines.append(f"      - {responsibility}")
        lines.append("    required_outputs:")
        for output in role.required_outputs:
            lines.append(f"      - {output}")
        scope = resolve_role_write_scope(
            config=config,
            role=role,
            report_dir=report_dir,
            workspace_root=workspace_root,
        )
        lines.append("    write_policy:")
        lines.append(f"      mode: {scope.mode}")
        lines.append(f"      requires_worktree_scope: {str(scope.requires_worktree_scope).lower()}")
        if scope.notes:
            lines.append(f"      notes: {scope.notes!r}")
        if scope.worktree_scope_file is not None:
            lines.append(f"      worktree_scope_file: {str(scope.worktree_scope_file)!r}")
        if scope.unresolved_reason is not None:
            lines.append(f"      unresolved_reason: {scope.unresolved_reason!r}")
        lines.append("      allowed_files:")
        for path in scope.allowed_files:
            lines.append(f"        - {str(path)!r}")
        lines.append("      allowed_directories:")
        for path in scope.allowed_directories:
            lines.append(f"        - {str(path)!r}")
        memory_loadout = resolve_role_memory_loadout(role.id, memory_loadouts)
        lines.append("    memory_loadout:")
        lines.append(f"      allow_method_write: {str(memory_loadout.allow_method_write).lower()}")
        lines.append(f"      allow_global_write: {str(memory_loadout.allow_global_write).lower()}")
        if memory_loadout.notes:
            lines.append(f"      notes: {memory_loadout.notes!r}")
        if memory_loadout.candidate_file is not None:
            lines.append(f"      candidate_file: {str(memory_loadout.candidate_file)!r}")
        lines.append("      method_files:")
        for path in memory_loadout.method_files:
            lines.append(f"        - {str(path)!r}")
        lines.append("      read_files:")
        for path in memory_loadout.read_files:
            lines.append(f"        - {str(path)!r}")
    lines.append("context_policies:")
    for policy in config.context_policies:
        lines.append("  - roles:")
        for role_name in tuple(policy["roles"]):
            lines.append(f"      - {role_name}")
        lines.append(f"    mode: {policy['mode']}")
        lines.append("    share_only:")
        for artifact in tuple(policy["share_only"]):
            lines.append(f"      - {artifact}")
        lines.append("    do_not_share:")
        for artifact in tuple(policy["do_not_share"]):
            lines.append(f"      - {artifact}")
    lines.append("quality_gates:")
    for gate in config.quality_gates:
        lines.append(f"  - {gate}")
    lines.append("artifacts:")
    for artifact in iter_artifacts(config, roles):
        lines.append(f"  - {artifact}")
    return "\n".join(lines) + "\n"


def resolve_role_write_scope(
    config: TeamConfig,
    role: Role,
    report_dir: Path,
    workspace_root: Path,
) -> RoleWriteScope:
    """Resolve concrete write paths for one role."""
    allowed_files = tuple(
        sorted(
            {
                (report_dir / config.artifacts[artifact_key]).resolve()
                for artifact_key in role.write_policy.allowed_artifacts
            },
            key=str,
        )
    )
    allowed_directories: tuple[Path, ...] = ()
    scope_file = find_worktree_scope_file(workspace_root)
    unresolved_reason: str | None = None
    if role.write_policy.mode == "worktree_scope_plus_artifacts":
        editable_directories = tuple(
            _resolve_scope_directories(
                scope_file,
                workspace_root,
                "## Editable Directories",
            )
        )
        allowed_directories = tuple(sorted(editable_directories, key=str))
        if role.write_policy.requires_worktree_scope and scope_file is None:
            unresolved_reason = "WORKTREE_SCOPE.md is required but was not found in the workspace root."
        elif role.write_policy.requires_worktree_scope and not allowed_directories:
            unresolved_reason = "WORKTREE_SCOPE.md was found, but no editable directories could be parsed."
    elif role.write_policy.mode == "runtime_outputs_plus_artifacts":
        runtime_output_directories = tuple(
            _resolve_scope_directories(
                scope_file,
                workspace_root,
                "## Runtime Output Directories",
            )
        )
        allowed_directories = tuple(sorted(runtime_output_directories, key=str))
        if role.write_policy.requires_worktree_scope and scope_file is None:
            unresolved_reason = "WORKTREE_SCOPE.md is required but was not found in the workspace root."
        elif role.write_policy.requires_worktree_scope and not allowed_directories:
            unresolved_reason = (
                "WORKTREE_SCOPE.md was found, but no runtime output directories could be parsed."
            )
    return RoleWriteScope(
        role_id=role.id,
        mode=role.write_policy.mode,
        allowed_files=allowed_files,
        allowed_directories=allowed_directories,
        requires_worktree_scope=role.write_policy.requires_worktree_scope,
        worktree_scope_file=scope_file,
        unresolved_reason=unresolved_reason,
        notes=role.write_policy.notes,
    )


def collect_changed_files(
    workspace_root: Path,
    ignored_roots: tuple[Path, ...] = (),
) -> tuple[Path, ...]:
    """Collect modified, staged, deleted, renamed, and untracked files."""
    changed: set[Path] = set()
    changed.update(
        _git_paths(
            workspace_root,
            ["diff", "--name-only", "--diff-filter=ACDMRTUXB"],
        )
    )
    changed.update(
        _git_paths(
            workspace_root,
            ["diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB"],
        )
    )
    changed.update(_git_paths(workspace_root, ["ls-files", "--others", "--exclude-standard"]))
    ignored = tuple(root.resolve() for root in ignored_roots)
    filtered_paths = [
        path.resolve()
        for path in changed
        if not any(path.resolve() == root or root in path.resolve().parents for root in ignored)
    ]
    return tuple(sorted(filtered_paths, key=str))


def validate_role_write_scope(
    config: TeamConfig,
    role_name: str,
    report_dir: Path,
    workspace_root: Path,
    files: tuple[Path, ...] | None = None,
    report_dir_snapshot: dict[str, str] | None = None,
    workspace_snapshot: dict[str, str] | None = None,
    ignored_paths: tuple[Path, ...] = (),
) -> tuple[RoleWriteScope, tuple[Path, ...]]:
    """Validate changed files against the role's allowed write scope."""
    role = resolve_role(config, role_name)
    resolved_report_dir = report_dir.resolve()
    resolved_workspace_root = workspace_root.resolve()
    scope = resolve_role_write_scope(config, role, resolved_report_dir, resolved_workspace_root)
    resolved_ignored_paths = tuple(path.resolve() for path in ignored_paths)
    if workspace_snapshot is None:
        changed_files = set(
            collect_changed_files(
                resolved_workspace_root,
                ignored_roots=(resolved_report_dir,),
            )
        )
        changed_files = {
            path
            for path in changed_files
            if not any(
                _matches_ignored_path(path.resolve(), ignored_path)
                for ignored_path in resolved_ignored_paths
            )
        }
    else:
        changed_files = set(
            collect_workspace_change_delta(
                resolved_workspace_root,
                workspace_snapshot,
                ignored_roots=(resolved_report_dir,),
                ignored_paths=resolved_ignored_paths,
            )
        )
    if report_dir_snapshot is not None:
        changed_files.update(collect_directory_changes(resolved_report_dir, report_dir_snapshot))
    changed_files.update(path.resolve() for path in (files or ()))
    violations = tuple(sorted(
        (path for path in changed_files if not _path_allowed(path.resolve(), scope)),
        key=str,
    ))
    return scope, violations


def slugify(value: str) -> str:
    """Return an ASCII slug that is safe for file paths."""
    ascii_only = value.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return slug or "task"


def make_run_id(task: str, created_at) -> str:
    """Build a stable default run id."""
    timestamp = created_at.strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{slugify(task)[:40]}"


def _parse_role(raw_role: dict[str, object], default_activation: str) -> Role:
    """Parse a role from json."""
    raw_write_policy = dict(raw_role["write_policy"])
    write_policy = WritePolicy(
        mode=str(raw_write_policy["mode"]),
        allowed_artifacts=tuple(str(item) for item in raw_write_policy["allowed_artifacts"]),
        requires_worktree_scope=bool(raw_write_policy.get("requires_worktree_scope", False)),
        notes=str(raw_write_policy.get("notes", "")),
    )
    return Role(
        id=str(raw_role["id"]),
        owns=tuple(str(item) for item in raw_role["owns"]),
        required_outputs=tuple(str(item) for item in raw_role["required_outputs"]),
        activation=str(raw_role.get("activation", default_activation)),
        write_policy=write_policy,
        codex_agents=tuple(str(item) for item in raw_role.get("codex_agents", ())),
    )


def find_worktree_scope_file(workspace_root: Path) -> Path | None:
    """Return the worktree scope file if present."""
    candidate = workspace_root.resolve() / "WORKTREE_SCOPE.md"
    if candidate.is_file():
        return candidate
    return None


def _resolve_scope_directories(
    scope_file: Path | None,
    workspace_root: Path,
    section_heading: str,
) -> list[Path]:
    """Parse directories from one named WORKTREE_SCOPE.md section."""
    if scope_file is None:
        return []
    content = scope_file.read_text(encoding="utf-8")
    in_section = False
    directories: list[Path] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == section_heading
            continue
        if not in_section or not stripped.startswith("- "):
            continue
        path_text = _extract_markdown_code_or_bullet_value(stripped[2:])
        if not path_text:
            continue
        path_text = path_text.rstrip("/").strip()
        directories.append((workspace_root / path_text).resolve())
    return directories


def _extract_markdown_code_or_bullet_value(text: str) -> str:
    """Extract the primary path token from a markdown bullet."""
    code_match = re.search(r"`([^`]+)`", text)
    if code_match is not None:
        return code_match.group(1)
    plain_text = text.split(" -- ", 1)[0]
    plain_text = text.split(" - ", 1)[0] if plain_text == text else plain_text
    plain_text = text.split(" (", 1)[0] if plain_text == text else plain_text
    return plain_text.strip()


def _git_paths(workspace_root: Path, args: list[str]) -> set[Path]:
    """Run git and convert stdout paths into absolute Paths."""
    result = subprocess.run(
        ["git", "-C", str(workspace_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    paths: set[Path] = set()
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped:
            paths.add((workspace_root / stripped).resolve())
    return paths


def capture_directory_snapshot(root: Path) -> dict[str, str]:
    """Return a content-hash snapshot for every file below one directory."""
    resolved_root = root.resolve()
    if not resolved_root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path in sorted(resolved_root.rglob("*")):
        if path.is_file():
            snapshot[str(path.resolve())] = _file_sha256(path)
    return snapshot


def load_directory_snapshot(path: Path) -> dict[str, str]:
    """Load a directory snapshot from json."""
    return {
        str(snapshot_path): str(digest)
        for snapshot_path, digest in json.loads(path.read_text(encoding="utf-8")).items()
    }


def write_directory_snapshot(root: Path, output_path: Path) -> None:
    """Write the current directory snapshot to json."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(capture_directory_snapshot(root), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def capture_workspace_change_snapshot(
    workspace_root: Path,
    ignored_roots: tuple[Path, ...] = (),
    ignored_paths: tuple[Path, ...] = (),
) -> dict[str, str]:
    """Return a snapshot for the workspace's current git-visible changes."""
    changed_paths = collect_changed_files(workspace_root, ignored_roots=ignored_roots)
    resolved_ignored_paths = tuple(path.resolve() for path in ignored_paths)
    snapshot: dict[str, str] = {}
    for path in changed_paths:
        resolved_path = path.resolve()
        if any(
            _matches_ignored_path(resolved_path, ignored_path)
            for ignored_path in resolved_ignored_paths
        ):
            continue
        snapshot[str(resolved_path)] = _path_snapshot_digest(resolved_path)
    return snapshot


def write_workspace_change_snapshot(
    workspace_root: Path,
    output_path: Path,
    ignored_roots: tuple[Path, ...] = (),
    ignored_paths: tuple[Path, ...] = (),
) -> None:
    """Write the current git-visible workspace change snapshot to json."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            capture_workspace_change_snapshot(
                workspace_root,
                ignored_roots=ignored_roots,
                ignored_paths=ignored_paths,
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def collect_directory_changes(root: Path, before_snapshot: dict[str, str]) -> tuple[Path, ...]:
    """Return files that changed within one directory since the captured snapshot."""
    after_snapshot = capture_directory_snapshot(root)
    changed_paths = {
        Path(raw_path).resolve()
        for raw_path in set(before_snapshot) | set(after_snapshot)
        if before_snapshot.get(raw_path) != after_snapshot.get(raw_path)
    }
    return tuple(sorted(changed_paths, key=str))


def collect_workspace_change_delta(
    workspace_root: Path,
    before_snapshot: dict[str, str],
    ignored_roots: tuple[Path, ...] = (),
    ignored_paths: tuple[Path, ...] = (),
) -> tuple[Path, ...]:
    """Return git-visible workspace paths that changed since the captured snapshot."""
    after_snapshot = capture_workspace_change_snapshot(
        workspace_root,
        ignored_roots=ignored_roots,
        ignored_paths=ignored_paths,
    )
    changed_paths = {
        Path(raw_path).resolve()
        for raw_path in set(before_snapshot) | set(after_snapshot)
        if before_snapshot.get(raw_path) != after_snapshot.get(raw_path)
    }
    return tuple(sorted(changed_paths, key=str))


def _path_allowed(path: Path, scope: RoleWriteScope) -> bool:
    """Return whether one path falls within the resolved write scope."""
    if path in scope.allowed_files:
        return True
    for directory in scope.allowed_directories:
        if path == directory or directory in path.parents:
            return True
    return False


def _matches_ignored_path(path: Path, ignored_path: Path) -> bool:
    """Return whether a path should be ignored during write-scope collection."""
    if path == ignored_path:
        return True
    return ignored_path.is_dir() and ignored_path in path.parents


def _file_sha256(path: Path) -> str:
    """Return the sha256 digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_snapshot_digest(path: Path) -> str:
    """Return a digest for one path, including deletions."""
    if path.is_file():
        return _file_sha256(path)
    return "__missing__"


def _as_mapping_tuple(value: object, field_name: str) -> tuple[dict[str, object], ...]:
    """Validate a list of mappings and return it as a tuple."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be a list")
    normalized: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise RuntimeError(f"{field_name} entries must be mappings")
        normalized.append(dict(item))
    return tuple(normalized)


def _as_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    """Validate a list of strings and return it as a tuple."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be a list")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise RuntimeError(f"{field_name} entries must be strings")
        normalized.append(item)
    return tuple(normalized)
