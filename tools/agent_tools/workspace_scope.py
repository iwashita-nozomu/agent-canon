# @dependency-start
# contract tool
# responsibility AgentTeam workspace scope owner module.
# upstream design ../../documents/design/agent-team-module-boundaries.md RC-01..RC-08 approved module boundary.
# upstream implementation ./team_config.py provides role and artifact policy inputs.
# downstream implementation ./agent_team.py facade consumes path APIs.
# downstream implementation ./bootstrap_agent_run.py consumes path APIs.
# downstream implementation ./task_close.py consumes path APIs.
# @dependency-end
"""Own AgentTeam workspace scope, path, and snapshot operations."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    from .runtime_artifacts import (
        RUNTIME_ROOT_ENV,
        RuntimeRootRequired,
        SourceLocalArtifact,
        RuntimeSymlinkEscape,
        runtime_artifact_boundary,
    )
except ImportError:  # direct script/module execution
    from runtime_artifacts import (  # type: ignore[no-redef]
        RUNTIME_ROOT_ENV,
        RuntimeRootRequired,
        SourceLocalArtifact,
        RuntimeSymlinkEscape,
        runtime_artifact_boundary,
    )

try:
    from .parent_root_side_effects import (
        ParentRootAttestationRequest,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
        ensure_parent_owned_directory,
        resolve_parent_owned_path,
    )
except ImportError:  # direct script/module execution
    from parent_root_side_effects import (  # type: ignore[no-redef]
        ParentRootAttestationRequest,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
        ensure_parent_owned_directory,
        resolve_parent_owned_path,
    )
from typing import TYPE_CHECKING

if __package__:
    from .agent_canon_source_root import (
        RepositoryRoots,
        RootResolution,
        resolve_agent_canon_source_root,
    )
    from .team_config import Role, TeamConfig, resolve_role
else:
    from agent_canon_source_root import (  # type: ignore[no-redef]
        RepositoryRoots,
        RootResolution,
        resolve_agent_canon_source_root,
    )
    from team_config import Role, TeamConfig, resolve_role

if TYPE_CHECKING:
    if __package__:
        from .packets import ActiveDesignPacketConfig
    else:
        from packets import ActiveDesignPacketConfig

GIT_STATUS_SHORT_MIN_LINE_LENGTH = 4

GIT_STATUS_SHORT_PATH_START = 3

RUN_ID_TASK_SLUG_MAX_CHARS = 40

SHA256_READ_CHUNK_BYTES = 65_536

DEFAULT_REPORT_ROOT = Path("reports") / "agents"


def _agent_canon_source_root() -> Path:
    """Return this module's AgentCanon source root for artifact containment."""
    return Path(__file__).resolve().parents[2]


def resolve_runtime_artifact_path(
    path: Path | str,
    *,
    runtime_root: Path | str | None = None,
    source_root: Path | None = None,
) -> Path:
    """Resolve one explicit external runtime artifact path.

    The runtime root is selected only by the caller or
    ``AGENT_CANON_RUNTIME_ROOT``.  A caller that supplied an explicit absolute
    artifact path before the runtime-root migration remains supported, but a
    relative path (including a path derived from the current directory) fails
    closed.  This keeps the old explicit ``--report-dir`` interface additive
    without restoring a source-relative default.
    """
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise RuntimeRootRequired(
            "explicit external runtime root required for relative artifact path: "
            f"{candidate}; pass --runtime-root or set {RUNTIME_ROOT_ENV}"
        )
    source = (source_root or _agent_canon_source_root()).resolve()
    configured = runtime_root
    if configured is None:
        configured = os.environ.get(RUNTIME_ROOT_ENV, "").strip() or None
    if configured is not None:
        boundary = runtime_artifact_boundary(source, configured)
        return boundary.resolve(candidate)
    probe = candidate
    while probe != probe.parent:
        if probe.is_symlink():
            raise RuntimeSymlinkEscape(
                f"runtime artifact contains a symlink component: {probe}"
            )
        probe = probe.parent
    resolved = candidate.resolve(strict=False)
    if resolved == source or source in resolved.parents:
        raise SourceLocalArtifact(
            f"runtime artifact must not resolve into AgentCanon source: {resolved}"
        )
    return resolved


def _resolve_rooted_path(root: Path, relative_path: str, root_key: str) -> Path:
    """Resolve a logical relative path below one typed runtime root."""
    declared = str(relative_path)
    candidate = Path(declared)
    if (
        not declared
        or "\x00" in declared
        or "\\" in declared
        or "//" in declared
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise RuntimeError(f"runtime_artifact_path_invalid:{root_key}:{declared}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise RuntimeError(f"runtime_artifact_path_invalid:{root_key}:{declared}") from exc
    return resolved


def resolve_workspace_document_path(
    workspace_root: Path,
    relative_path: str,
    *,
    root_key: str | None = None,
    agentcanon_source_root: Path | None = None,
    report_root: Path | None = None,
) -> Path:
    """Resolve a document only below the explicitly selected logical root."""
    if root_key is None:
        raise RuntimeError("runtime_roots_invalid:root_key_missing")
    roots = {
        "workspace": workspace_root,
        "agentcanon": agentcanon_source_root,
        "artifact": report_root,
    }
    selected = roots.get(root_key)
    if selected is None:
        raise RuntimeError(
            f"runtime_roots_invalid:missing_{root_key}_root:{relative_path}"
        )
    return _resolve_rooted_path(selected, relative_path, root_key)


def resolve_repository_roots(
    workspace_root: Path,
    report_root: str | Path | None = None,
    *,
    source_root: Path | None = None,
    canon_root: Path | None = None,
    runtime_root: str | Path | None = None,
) -> RepositoryRoots:
    """Assemble source/state/report roots before constructing a run spec."""
    workspace = workspace_root.resolve()
    resolution: RootResolution
    same_standalone_identity = (
        source_root is not None
        and canon_root is not None
        and workspace == source_root.resolve()
        and workspace == canon_root.resolve()
    )
    if (source_root is None and canon_root is None) or same_standalone_identity:
        resolution = resolve_agent_canon_source_root(workspace)
    else:
        resolution = resolve_agent_canon_source_root(
            workspace,
            source_root=source_root,
            canon_root=canon_root,
        )
    selected_report = resolve_report_root(
        None if report_root is None else str(report_root),
        workspace,
        runtime_root=runtime_root,
        source_root=resolution.source_root,
    )
    public = resolution.public_tool_root
    return RepositoryRoots(
        workspace_root=workspace,
        agentcanon_source_root=resolution.source_root,
        report_root=selected_report,
        layout=resolution.layout,
        public_tool_root=public,
    )


def resolve_report_root(
    report_root: str | None,
    workspace_root: Path | None = None,
    *,
    runtime_root: Path | str | None = None,
    source_root: Path | None = None,
) -> Path:
    """Resolve reports below one explicit external runtime root.

    The old ``<workspace>/reports/agents`` default is intentionally gone.  A
    runtime root must be supplied directly or through
    ``AGENT_CANON_RUNTIME_ROOT``.  An absolute ``--report-root`` remains an
    additive compatibility path and is accepted only when it is outside the
    AgentCanon source tree.
    """
    del workspace_root  # retained for the additive positional API
    source = (source_root or _agent_canon_source_root()).resolve()
    configured = runtime_root
    if configured is None:
        configured = os.environ.get(RUNTIME_ROOT_ENV, "").strip() or None
    if configured is not None:
        boundary = runtime_artifact_boundary(source, configured)
        declared = DEFAULT_REPORT_ROOT if report_root is None else Path(report_root)
        return boundary.resolve(declared)
    if report_root is not None and Path(report_root).is_absolute():
        return resolve_runtime_artifact_path(report_root, source_root=source)
    raise RuntimeRootRequired(
        "explicit external runtime root required for report artifacts; pass "
        "--runtime-root or set "
        f"{RUNTIME_ROOT_ENV}"
    )


class ReportBundleArtifactPathError(RuntimeError):
    """Report one rejected run-artifact path and its containment reason."""

    def __init__(self, declared_path: str, reason: str) -> None:
        """Bind one rejected path to its containment failure reason."""
        self.declared_path = declared_path
        self.reason = reason
        super().__init__(
            f"report_bundle_artifact_path_invalid:{reason}:{declared_path}"
        )


def resolve_report_bundle_artifact_path(
    report_dir: Path,
    declared_path: str,
    *,
    require_existing_regular_file: bool = False,
) -> Path:
    """Resolve a lexical bundle path without following symlink components."""
    relative_path = Path(declared_path)
    if not declared_path or relative_path.is_absolute():
        raise ReportBundleArtifactPathError(declared_path, "not_relative")
    parts = tuple(part for part in relative_path.parts if part not in {"", "."})
    if not parts:
        raise ReportBundleArtifactPathError(declared_path, "not_relative")
    for component in parts:
        if component == "..":
            raise ReportBundleArtifactPathError(declared_path, "outside_bundle")
    report_root = resolve_runtime_artifact_path(report_dir)
    lexical_path = report_root
    for index, component in enumerate(parts):
        lexical_path = lexical_path / component
        if lexical_path.is_symlink():
            raise ReportBundleArtifactPathError(declared_path, "symlink_component")
        if not lexical_path.exists():
            continue
        is_final_component = index == len(parts) - 1
        if is_final_component and not lexical_path.is_file():
            raise ReportBundleArtifactPathError(declared_path, "nonregular_target")
        if not is_final_component and not lexical_path.is_dir():
            raise ReportBundleArtifactPathError(declared_path, "non_directory_parent")
    candidate = lexical_path.resolve()
    try:
        candidate.relative_to(report_root)
    except ValueError as exc:
        raise ReportBundleArtifactPathError(declared_path, "outside_bundle") from exc
    if require_existing_regular_file and not candidate.is_file():
        raise ReportBundleArtifactPathError(declared_path, "missing_regular_file")
    return candidate


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


def schedule_wave_row(row: dict[str, str]) -> str:
    """Return a schedule.md Agent Wave Ledger row."""
    cells = (
        row["wave_id"],
        row["parent_or_delegate"],
        row["spawn_authority"],
        row["trigger"],
        row["budget_before"],
        row["budget_after"],
        row["runtime_max_threads"],
        row["runtime_max_depth"],
        row["spawned_roles"],
        row["role_instances"],
        row["skipped_roles"],
        row["allowed_paths"],
        row["do_not_read"],
        row["write_scope"],
        row["validation_route"],
        row["review_gate"],
        row["handoff_artifacts"],
        row["delegated_policy_ref"],
        row["status"],
    )
    return "| " + " | ".join(cells) + " |"


def resolve_role_write_scope(
    config: TeamConfig,
    role: Role,
    report_dir: Path,
    workspace_root: Path,
    active_design_packet: ActiveDesignPacketConfig | None = None,
) -> RoleWriteScope:
    """Resolve concrete write paths for one role."""
    allowed_files = role_allowed_artifact_files(
        config,
        role,
        report_dir,
        active_design_packet,
    )
    allowed_directories = role_allowed_directories(role, workspace_root)
    unresolved_reason = role_write_scope_unresolved_reason(role, allowed_directories)
    return RoleWriteScope(
        role_id=role.id,
        mode=role.write_policy.mode,
        allowed_files=allowed_files,
        allowed_directories=allowed_directories,
        requires_worktree_scope=role.write_policy.requires_worktree_scope,
        worktree_scope_file=None,
        unresolved_reason=unresolved_reason,
        notes=role.write_policy.notes,
    )


def role_allowed_artifact_files(
    config: TeamConfig,
    role: Role,
    report_dir: Path,
    active_design_packet: ActiveDesignPacketConfig | None = None,
) -> tuple[Path, ...]:
    """Resolve generated artifact files one role may write."""
    if __package__:
        from .packets import resolve_active_design_packet_config, selected_artifact_name
    else:
        from packets import resolve_active_design_packet_config, selected_artifact_name
    packet = active_design_packet or resolve_active_design_packet_config(config)
    return tuple(
        sorted(
            {
                resolve_report_bundle_artifact_path(
                    report_dir,
                    selected_artifact_name(config, artifact_key, packet),
                )
                for artifact_key in role.write_policy.allowed_artifacts
            },
            key=str,
        )
    )


def role_allowed_directories(
    role: Role,
    workspace_root: Path,
) -> tuple[Path, ...]:
    """Resolve configured current-checkout directories one role may write."""
    if role.write_policy.allowed_directories:
        return tuple(
            sorted(
                (
                    (workspace_root / directory).resolve()
                    for directory in role.write_policy.allowed_directories
                ),
                key=str,
            )
        )
    return ()


def role_write_scope_unresolved_reason(
    role: Role,
    allowed_directories: tuple[Path, ...],
) -> str | None:
    """Return why a configured current-checkout write policy is unresolved."""
    if not role.write_policy.requires_worktree_scope:
        return None
    if allowed_directories:
        return None
    return (
        "Legacy WORKTREE_SCOPE write scope is disabled; configure explicit "
        "write_policy.allowed_directories in agents/agents_config.json."
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
    changed.update(
        _git_paths(workspace_root, ["ls-files", "--others", "--exclude-standard"])
    )
    ignored = tuple(root.resolve() for root in ignored_roots)
    filtered_paths = [
        path.resolve()
        for path in changed
        if not any(
            path.resolve() == root or root in path.resolve().parents for root in ignored
        )
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
    scope = resolve_role_write_scope(
        config, role, resolved_report_dir, resolved_workspace_root
    )
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
        changed_files.update(
            collect_directory_changes(resolved_report_dir, report_dir_snapshot)
        )
    changed_files.update(path.resolve() for path in (files or ()))
    violations = tuple(
        sorted(
            (
                path
                for path in changed_files
                if not _path_allowed(path.resolve(), scope)
            ),
            key=str,
        )
    )
    return scope, violations


def slugify(value: str) -> str:
    """Return an ASCII slug that is safe for file paths."""
    ascii_only = value.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return slug or "task"


def make_run_id(task: str, created_at: datetime) -> str:
    """Build a stable default run id."""
    timestamp = created_at.strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{slugify(task)[:RUN_ID_TASK_SLUG_MAX_CHARS]}"


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
        for snapshot_path, digest in json.loads(
            path.read_text(encoding="utf-8")
        ).items()
    }


def write_directory_snapshot(root: Path, output_path: Path) -> None:
    """Write the current directory snapshot to json."""
    try:
        attestation = attest_parent_root(
            ParentRootAttestationRequest(cwd=root.resolve(), explicit_root=None, purpose="directory-snapshot")
        )
        ensure_parent_owned_directory(attestation, output_path.parent, "directory-snapshot-parent")
        receipt = resolve_parent_owned_path(attestation, output_path, "directory-snapshot")
        ParentRootSideEffectBoundary().atomic_publish(
            receipt, (json.dumps(capture_directory_snapshot(root), indent=2, sort_keys=True) + "\n").encode("utf-8")
        )
    except ParentRootSideEffectError as exc:
        raise ReportBundleArtifactPathError(str(output_path), exc.reject.value) from exc


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
    try:
        attestation = attest_parent_root(
            ParentRootAttestationRequest(cwd=workspace_root.resolve(), explicit_root=None, purpose="workspace-snapshot")
        )
        ensure_parent_owned_directory(attestation, output_path.parent, "workspace-snapshot-parent")
        receipt = resolve_parent_owned_path(attestation, output_path, "workspace-snapshot")
        ParentRootSideEffectBoundary().atomic_publish(
            receipt,
            (json.dumps(
                capture_workspace_change_snapshot(
                    workspace_root,
                    ignored_roots=ignored_roots,
                    ignored_paths=ignored_paths,
                ), indent=2, sort_keys=True
            ) + "\n").encode("utf-8"),
        )
    except ParentRootSideEffectError as exc:
        raise ReportBundleArtifactPathError(str(output_path), exc.reject.value) from exc


def collect_directory_changes(
    root: Path, before_snapshot: dict[str, str]
) -> tuple[Path, ...]:
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
        for chunk in iter(lambda: handle.read(SHA256_READ_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_snapshot_digest(path: Path) -> str:
    """Return a digest for one path, including deletions."""
    if path.is_file():
        return _file_sha256(path)
    return "__missing__"
