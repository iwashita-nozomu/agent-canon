# @dependency-start
# contract tool
# responsibility AgentTeam workspace scope owner module.
# upstream design ../../../documents/design/agent-team-module-boundaries.md RC-01..RC-08 approved module boundary.
# upstream implementation ../../agent/orchestration/team_config.py provides role and artifact policy inputs.
# @dependency-end
"""Own AgentTeam workspace scope, path, and snapshot operations."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from tools.runtime.artifacts.runtime_artifacts import (
    RUNTIME_ROOT_ENV,
    RuntimeRootRequired,
    SourceLocalArtifact,
    RuntimeSymlinkEscape,
    runtime_artifact_boundary,
)

from tools.runtime.source.agent_canon_source_root import (
    RepositoryRoots,
    RootResolution,
    resolve_agent_canon_source_root,
)

RUN_ID_TASK_SLUG_MAX_CHARS = 40

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
        raise RuntimeError(
            f"runtime_artifact_path_invalid:{root_key}:{declared}"
        ) from exc
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


def slugify(value: str) -> str:
    """Return an ASCII slug that is safe for file paths."""
    ascii_only = value.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return slug or "task"


def make_run_id(task: str, created_at: datetime) -> str:
    """Build a stable default run id."""
    timestamp = created_at.strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{slugify(task)[:RUN_ID_TASK_SLUG_MAX_CHARS]}"
