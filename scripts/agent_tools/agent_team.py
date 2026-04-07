#!/usr/bin/env python3
"""Shared runtime helpers for the permanent agent team."""

from __future__ import annotations

import json
import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEAM_CONFIG_PATH = ROOT / "agents" / "agents_config.json"
DEFAULT_REPORT_ROOT = ROOT / "reports" / "agents"
TEMPLATE_ROOT = ROOT / "agents" / "templates"


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


def specialist_role_ids(config: TeamConfig) -> tuple[str, ...]:
    """Return specialist role ids."""
    return tuple(role.id for role in config.specialist_roles)


def resolve_role(config: TeamConfig, role_name: str) -> Role:
    """Resolve a role id to a role."""
    for role in config.always_on_roles + config.specialist_roles:
        if role_name == role.id:
            return role
    raise KeyError(f"unknown role: {role_name}")


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
    lines = [
        "run:",
        f"  id: {run_id}",
        f"  task: {task!r}",
        f"  owner: {owner!r}",
        f"  created_at_utc: {created_at_iso}",
        f"  report_dir: {str(report_dir)!r}",
        f"  workspace_root: {str(workspace_root)!r}",
        f"  team_config: {str(TEAM_CONFIG_PATH)!r}",
        f"  team_runtime: {str(ROOT / 'scripts' / 'agent_tools' / 'agent_team.py')!r}",
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
