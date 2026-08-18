#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Parses and validates AgentCanon shared runtime projection metadata.
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md shared surface ownership policy
# upstream design ../../documents/runtime/shared-runtime-surfaces.toml machine-readable surface manifest
# downstream implementation ../sync_agent_canon.sh consumes sync specs from this manifest
# downstream implementation ./check_convention_compliance.py validates manifest wiring
# @dependency-end
"""Parse AgentCanon runtime surface projection manifests."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import cast

DEFAULT_MANIFEST = Path("documents/runtime/shared-runtime-surfaces.toml")
DEFAULT_DOC = Path("documents/runtime/SHARED_RUNTIME_SURFACES.md")
NORMALIZED_SNAPSHOT_SCHEMA = "agent-canon.surface-manifest.v1"
ALLOWED_INTEGRATION_MODES = frozenset({"live-agent-canon", "static-seed"})
ALLOWED_SELECTIONS = frozenset({"explicit-opt-in", "default"})
LEGACY_MANIFEST_VERSION = 1
SYNC_SPEC_COMMANDS = frozenset(
    {
        "link-specs",
        "copy-specs",
        "update-transition-specs",
        "regular-specs",
        "removed-legacy-paths",
        "root-absent-paths",
    }
)
MANIFEST_COMMANDS = SYNC_SPEC_COMMANDS | frozenset({"normalized-snapshot", "check-doc"})
ALLOWED_MODES = frozenset(
    {
        "symlink",
        "copy",
        "regular",
        "repo_state",
        "standalone_only",
        "removed_legacy",
    }
)
DELETION_MODES = frozenset({"removed_legacy", "standalone_only"})
ROOT_ABSENCE_TASK = "root-absence"
UPDATE_TRANSITION_TASK = "update-transition"
ALLOWED_PROJECTION_PRODUCERS = frozenset(
    {
        "agent-canon",
        "template",
        "template-or-derived-repo",
        "project",
        "github-path-constraint",
        "agent-canon-standalone",
        "agent-canon-update",
        "legacy",
    }
)
ALLOWED_PROJECTION_KINDS = frozenset(
    {
        "runtime_surface",
        "shared_policy",
        "shared_template",
        "active_contract",
        "durable_state",
        "project_config",
        "project_content",
        "test_mirror",
        "github_copy",
        "generated_evidence",
        "projection_view",
        "standalone_only",
        "transaction_state",
        "removed_legacy",
    }
)
DOC_ALWAYS_REQUIRED_MARKERS = (
    "documents/runtime/shared-runtime-surfaces.toml",
    "AGENTS.md",
    ".codex/config.toml",
    ".codex/agents",
    "tools/agent-canon",
    "Root `tools/` is a parent-owned regular container",
    "tools/agent-canon -> ../vendor/agent-canon/tools",
    "vendor/agent-canon/tools/",
    "Project-local automation must stay in project-owned paths",
)


@dataclass(frozen=True)
class SurfaceSelection:
    """Typed integration selection metadata for one surface manifest."""

    integration_mode: str
    default_consumer: bool
    selection: str

    @property
    def is_live_agent_canon(self) -> bool:
        """Return whether this selection is the explicitly selected live mode."""
        return (
            self.integration_mode == "live-agent-canon"
            and self.default_consumer is False
            and self.selection == "explicit-opt-in"
        )

    def require_live_agent_canon(self, operation: str) -> None:
        """Reject sync operations for a non-live or default consumer manifest."""
        if not self.is_live_agent_canon:
            raise ValueError(
                f"{operation} requires live-agent-canon,false,explicit-opt-in selection"
            )


@dataclass(frozen=True)
class SurfaceEntry:
    """One root runtime surface contract."""

    path: str
    mode: str
    projection_producer: str
    projection_kind: str
    source: str
    local_override_allowed: bool
    optional: bool

    def source_or_default(self) -> str:
        """Return the source path relative to AgentCanon prefix."""
        return self.source or self.path


@dataclass(frozen=True)
class SurfaceManifest:
    """Validated manifest content."""

    prefix: str
    surface_selection: SurfaceSelection
    entries: tuple[SurfaceEntry, ...]
    update_transitions: tuple[UpdateTransition, ...]
    deletion_targets: tuple[DeletionTarget, ...]

    @property
    def integration_mode(self) -> str:
        """Return the validated integration mode."""
        return self.surface_selection.integration_mode

    @property
    def default_consumer(self) -> bool:
        """Return the validated default-consumer flag."""
        return self.surface_selection.default_consumer

    @property
    def selection(self) -> str:
        """Return the validated selection mode."""
        return self.surface_selection.selection

    def require_live_agent_canon(self, operation: str) -> None:
        """Require the explicit live integration for a sync operation."""
        self.surface_selection.require_live_agent_canon(operation)

    def by_mode(self, mode: str) -> tuple[SurfaceEntry, ...]:
        """Return manifest entries for one mode."""
        return tuple(entry for entry in self.entries if entry.mode == mode)


@dataclass(frozen=True)
class LegacyIdentity:
    """One history-bound identity eligible for a one-time transition."""

    kind: str
    git_blob: str
    content_sha256: str
    git_mode: str
    symlink_target: str


@dataclass(frozen=True)
class UpdateTransitionCandidate:
    """One parent path considered during an update transition."""

    path: str
    identities: tuple[LegacyIdentity, ...]


@dataclass(frozen=True)
class UpdateTransition:
    """A migration activated only by a known previous AgentCanon pin."""

    transition_id: str
    from_agent_canon_pins: tuple[str, ...]
    candidates: tuple[UpdateTransitionCandidate, ...]


@dataclass(frozen=True)
class DeletionTarget:
    """One task-owned deletion target admitted below a canonical root."""

    task: str
    owner: str
    path: str
    canonical_path: Path


def admit_deletion_targets(
    root: Path,
    entries: Sequence[SurfaceEntry],
    transitions: Sequence[UpdateTransition],
) -> tuple[
    tuple[SurfaceEntry, ...],
    tuple[UpdateTransition, ...],
    tuple[DeletionTarget, ...],
]:
    """Generate, normalize, and admit every manifest deletion target."""
    try:
        canonical_root = root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"deletion root cannot be resolved: {root}") from exc
    if not canonical_root.is_dir():
        raise ValueError(
            f"deletion root is not a directory: {canonical_root}"
        )

    def admit(raw_path: str, *, task: str, owner: str) -> DeletionTarget:
        if not task or not owner:
            raise ValueError(
                "deletion target requires an explicit task owner"
            )
        pure_path = PurePosixPath(raw_path)
        normalized = pure_path.as_posix()
        invalid = (
            not raw_path
            or raw_path != raw_path.strip()
            or pure_path.is_absolute()
            or not pure_path.parts
            or ".." in pure_path.parts
            or normalized != raw_path
            or any(
                character in raw_path
                for character in ("\0", "\n", "\r", "\t")
            )
        )
        if invalid:
            raise ValueError(
                f"{owner}: deletion target {raw_path!r} must be a "
                "normalized non-root repository-relative POSIX path"
            )
        candidate_path = canonical_root / normalized
        try:
            canonical_parent = (
                candidate_path.parent.resolve(strict=False)
            )
        except (OSError, RuntimeError) as exc:
            raise ValueError(
                f"{owner}: deletion target {raw_path!r} cannot be resolved"
            ) from exc
        canonical_path = canonical_parent / candidate_path.name
        if canonical_path == canonical_root:
            raise ValueError(
                f"{owner}: deletion target {raw_path!r} resolves to the "
                "canonical repository root"
            )
        try:
            canonical_path.relative_to(canonical_root)
        except ValueError as exc:
            raise ValueError(
                f"{owner}: deletion target {raw_path!r} resolves outside "
                "the canonical repository root"
            ) from exc
        return DeletionTarget(
            task=task,
            owner=owner,
            path=normalized,
            canonical_path=canonical_path,
        )

    normalized_entries: list[SurfaceEntry] = []
    normalized_transitions: list[UpdateTransition] = []
    admitted: list[DeletionTarget] = []
    for entry in entries:
        if entry.mode in DELETION_MODES:
            target = admit(
                entry.path,
                task=ROOT_ABSENCE_TASK,
                owner=(
                    f"surface:{entry.mode}:{entry.projection_producer}:"
                    f"{entry.projection_kind}"
                ),
            )
            entry = replace(entry, path=target.path)
            admitted.append(target)
        normalized_entries.append(entry)
    for transition in transitions:
        candidates: list[UpdateTransitionCandidate] = []
        for candidate in transition.candidates:
            target = admit(
                candidate.path,
                task=UPDATE_TRANSITION_TASK,
                owner=f"update-transition:{transition.transition_id}",
            )
            candidates.append(replace(candidate, path=target.path))
            admitted.append(target)
        normalized_transitions.append(
            replace(transition, candidates=tuple(candidates))
        )
    return (
        tuple(normalized_entries),
        tuple(normalized_transitions),
        tuple(admitted),
    )


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--prefix",
        default="vendor/agent-canon",
        help="AgentCanon prefix path relative to root.",
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Manifest path relative to AgentCanon prefix or root.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in sorted(MANIFEST_COMMANDS):
        subcommands.add_parser(command)
    return parser


def string_value(mapping: Mapping[str, object], key: str, default: str = "") -> str:
    """Return a required or default string field."""
    value = mapping.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def bool_value(mapping: Mapping[str, object], key: str, default: bool) -> bool:
    """Return a boolean field."""
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def required_string_value(mapping: Mapping[str, object], key: str) -> str:
    """Return a mandatory string field."""
    if key not in mapping:
        raise ValueError(f"{key} is required")
    return string_value(mapping, key)


def path_list(mapping: Mapping[str, object]) -> tuple[str, ...]:
    """Return a validated path list from one group."""
    raw_paths = mapping.get("paths")
    if not isinstance(raw_paths, list):
        raise ValueError("group paths must be a list")
    paths: list[str] = []
    for item in cast(list[object], raw_paths):
        if not isinstance(item, str) or not item.strip():
            raise ValueError("group paths entries must be non-empty strings")
        paths.append(item)
    return tuple(paths)


def validate_entry(entry: SurfaceEntry) -> SurfaceEntry:
    """Validate one manifest entry."""
    if entry.mode not in ALLOWED_MODES:
        raise ValueError(f"{entry.path}: invalid mode {entry.mode}")
    if entry.projection_producer not in ALLOWED_PROJECTION_PRODUCERS:
        raise ValueError(
            f"{entry.path}: invalid projection_producer {entry.projection_producer}"
        )
    if entry.projection_kind not in ALLOWED_PROJECTION_KINDS:
        raise ValueError(
            f"{entry.path}: invalid projection_kind {entry.projection_kind}"
        )
    if entry.mode in {"symlink", "copy"} and not entry.source_or_default():
        raise ValueError(f"{entry.path}: {entry.mode} requires a source")
    return entry


def validate_manifest_metadata(
    integration_mode: str, default_consumer: bool, selection: str
) -> SurfaceSelection:
    """Validate the top-level integration selection contract."""
    if integration_mode not in ALLOWED_INTEGRATION_MODES:
        raise ValueError(f"invalid integration_mode {integration_mode}")
    if selection not in ALLOWED_SELECTIONS:
        raise ValueError(f"invalid selection {selection}")
    if integration_mode == "live-agent-canon":
        if default_consumer:
            raise ValueError(
                "live-agent-canon integration must not be the default consumer"
            )
        if selection != "explicit-opt-in":
            raise ValueError(
                "live-agent-canon integration requires explicit-opt-in selection"
            )
    elif not default_consumer or selection != "default":
        raise ValueError(
            "static-seed integration must be the default consumer with default selection"
        )
    return SurfaceSelection(integration_mode, default_consumer, selection)


def selection_from_mapping(data: Mapping[str, object]) -> SurfaceSelection:
    """Load complete metadata or map an unannotated v1 manifest to its legacy mode."""
    metadata_keys = frozenset({"integration_mode", "default_consumer", "selection"})
    present = metadata_keys.intersection(data)
    if not present:
        if "version" not in data:
            raise ValueError(
                "version = 1 is required for an unannotated legacy manifest"
            )
        version = data["version"]
        if type(version) is not int:
            raise ValueError("version must be an integer")
        if version != LEGACY_MANIFEST_VERSION:
            raise ValueError(
                "integration metadata is required for non-v1 surface manifests"
            )
        return SurfaceSelection("live-agent-canon", False, "explicit-opt-in")
    if present != metadata_keys:
        missing = ",".join(sorted(metadata_keys - present))
        raise ValueError(f"integration metadata must be complete; missing {missing}")
    return validate_manifest_metadata(
        required_string_value(data, "integration_mode"),
        bool_value(data, "default_consumer", False),
        required_string_value(data, "selection"),
    )


def default_local_override(projection_producer: str) -> bool:
    """Return the default override policy for one projection producer."""
    return projection_producer in {"template", "template-or-derived-repo", "project"}


def entry_from_mapping(mapping: Mapping[str, object]) -> SurfaceEntry:
    """Create one manifest entry from one TOML table."""
    projection_producer = string_value(mapping, "projection_producer")
    return validate_entry(
        SurfaceEntry(
            path=string_value(mapping, "path"),
            mode=string_value(mapping, "mode"),
            projection_producer=projection_producer,
            projection_kind=string_value(mapping, "projection_kind"),
            source=string_value(mapping, "source"),
            local_override_allowed=bool_value(
                mapping,
                "local_override_allowed",
                default_local_override(projection_producer),
            ),
            optional=bool_value(mapping, "optional", False),
        )
    )


def entries_from_group(mapping: Mapping[str, object]) -> tuple[SurfaceEntry, ...]:
    """Expand one grouped manifest table."""
    projection_producer = string_value(mapping, "projection_producer")
    mode = string_value(mapping, "mode")
    projection_kind = string_value(mapping, "projection_kind")
    source_prefix = string_value(mapping, "source_prefix")
    entries: list[SurfaceEntry] = []
    for path in path_list(mapping):
        source = f"{source_prefix}{path}" if source_prefix else path
        entries.append(
            validate_entry(
                SurfaceEntry(
                    path=path,
                    mode=mode,
                    projection_producer=projection_producer,
                    projection_kind=projection_kind,
                    source=source,
                    local_override_allowed=bool_value(
                        mapping,
                        "local_override_allowed",
                        default_local_override(projection_producer),
                    ),
                    optional=bool_value(mapping, "optional", False),
                )
            )
        )
    return tuple(entries)


def string_list(mapping: Mapping[str, object], key: str) -> tuple[str, ...]:
    """Return one validated non-empty string list."""
    raw_values = mapping.get(key)
    if not isinstance(raw_values, list) or not raw_values:
        raise ValueError(f"{key} must be a non-empty list")
    values: list[str] = []
    for item in cast(list[object], raw_values):
        if not isinstance(item, str) or not item:
            raise ValueError(f"{key} entries must be non-empty strings")
        values.append(item)
    return tuple(values)


def legacy_identity_from_mapping(mapping: Mapping[str, object]) -> LegacyIdentity:
    """Create and validate one history-derived legacy identity."""
    identity = LegacyIdentity(
        kind=string_value(mapping, "kind"),
        git_blob=string_value(mapping, "git_blob"),
        content_sha256=string_value(mapping, "content_sha256"),
        git_mode=string_value(mapping, "git_mode"),
        symlink_target=string_value(mapping, "symlink_target"),
    )
    if identity.kind not in {"regular", "symlink"}:
        raise ValueError(f"legacy identity has invalid kind {identity.kind}")
    if not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", identity.git_blob):
        raise ValueError("legacy identity git_blob must be a lowercase object id")
    if not re.fullmatch(r"[0-9a-f]{64}", identity.content_sha256):
        raise ValueError("legacy identity content_sha256 must be lowercase SHA-256")
    if identity.kind == "regular":
        if identity.git_mode not in {"100644", "100755"}:
            raise ValueError("regular legacy identity requires Git mode 100644 or 100755")
        if identity.symlink_target:
            raise ValueError("regular legacy identity must not define symlink_target")
    elif identity.git_mode != "120000" or not identity.symlink_target:
        raise ValueError("symlink legacy identity requires mode 120000 and symlink_target")
    return identity


def update_transition_from_mapping(mapping: Mapping[str, object]) -> UpdateTransition:
    """Create and validate one one-time update transition."""
    transition_id = string_value(mapping, "id")
    if not transition_id or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", transition_id):
        raise ValueError("update_transition id must use lowercase kebab-case")
    previous_pins = string_list(mapping, "from_agent_canon_pins")
    if any(
        not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", value)
        for value in previous_pins
    ):
        raise ValueError(f"{transition_id}: invalid from_agent_canon_pins")
    candidates: list[UpdateTransitionCandidate] = []
    for candidate in manifest_tables(mapping, "candidate"):
        path = string_value(candidate, "path")
        identities = tuple(
            legacy_identity_from_mapping(identity)
            for identity in manifest_tables(candidate, "identity")
        )
        if not identities:
            raise ValueError(f"{transition_id}:{path}: identities must not be empty")
        candidates.append(UpdateTransitionCandidate(path=path, identities=identities))
    if not candidates:
        raise ValueError(f"{transition_id}: candidates must not be empty")
    candidate_paths = [candidate.path for candidate in candidates]
    if len(candidate_paths) != len(set(candidate_paths)):
        raise ValueError(f"{transition_id}: duplicate candidate paths")
    return UpdateTransition(
        transition_id=transition_id,
        from_agent_canon_pins=previous_pins,
        candidates=tuple(candidates),
    )


def manifest_path(root: Path, prefix: str, raw_manifest: str) -> Path:
    """Resolve the manifest path."""
    relative = Path(raw_manifest)
    prefixed = root / prefix / relative
    if prefixed.is_file():
        return prefixed
    return root / relative


def manifest_tables(data: Mapping[str, object], key: str) -> tuple[Mapping[str, object], ...]:
    """Return a validated sequence of manifest tables."""
    raw_tables = data.get(key, [])
    if not isinstance(raw_tables, list):
        raise ValueError(f"{key} must be a list")
    tables: list[Mapping[str, object]] = []
    for item in cast(list[object], raw_tables):
        if not isinstance(item, dict):
            raise ValueError(f"{key} entries must be tables")
        tables.append(cast(Mapping[str, object], item))
    return tuple(tables)


def load_manifest(root: Path, prefix: str, raw_manifest: str) -> SurfaceManifest:
    """Load and validate the surface manifest."""
    path = manifest_path(root, prefix, raw_manifest)
    data = cast(Mapping[str, object], tomllib.loads(path.read_text(encoding="utf-8")))
    manifest_prefix = string_value(data, "prefix", prefix)
    surface_selection = selection_from_mapping(data)
    entries: list[SurfaceEntry] = []
    for group in manifest_tables(data, "group"):
        entries.extend(entries_from_group(group))
    for surface in manifest_tables(data, "surface"):
        entries.append(entry_from_mapping(surface))
    paths = [entry.path for entry in entries]
    duplicates = sorted({path for path in paths if paths.count(path) > 1})
    if duplicates:
        raise ValueError(f"duplicate surface paths: {','.join(duplicates)}")
    update_transitions = tuple(
        update_transition_from_mapping(table)
        for table in manifest_tables(data, "update_transition")
    )
    transition_ids = [transition.transition_id for transition in update_transitions]
    if len(transition_ids) != len(set(transition_ids)):
        raise ValueError("duplicate update_transition ids")
    normalized_entries, normalized_transitions, deletion_targets = (
        admit_deletion_targets(root, entries, update_transitions)
    )
    return SurfaceManifest(
        prefix=manifest_prefix,
        surface_selection=surface_selection,
        entries=normalized_entries,
        update_transitions=normalized_transitions,
        deletion_targets=deletion_targets,
    )


def target_for_entry(root: Path, prefix: str, entry: SurfaceEntry) -> str:
    """Return a symlink target relative to the root path parent."""
    source_path = root / prefix / entry.source_or_default()
    parent = (root / entry.path).parent
    return os.path.relpath(source_path, parent)


def source_for_entry(prefix: str, entry: SurfaceEntry) -> str:
    """Return a root-relative source path for copy or regular seed use."""
    return (Path(prefix) / entry.source_or_default()).as_posix()


def render_specs(entries: Iterable[SurfaceEntry], root: Path, prefix: str) -> str:
    """Render colon-delimited sync specs."""
    lines = [
        f"{entry.path}:{target_for_entry(root, prefix, entry)}"
        for entry in entries
        if entry.mode == "symlink"
    ]
    return "\n".join(lines)


def render_copy_specs(entries: Iterable[SurfaceEntry], prefix: str) -> str:
    """Render copy specs."""
    lines = [
        f"{entry.path}:{source_for_entry(prefix, entry)}"
        for entry in entries
        if entry.mode == "copy"
    ]
    return "\n".join(lines)


def render_update_transition_specs(transitions: Iterable[UpdateTransition]) -> str:
    """Render history-bound transition identities for the shell updater."""
    lines: list[str] = []
    for transition in transitions:
        previous_pins = ",".join(transition.from_agent_canon_pins)
        for candidate in transition.candidates:
            for identity in candidate.identities:
                lines.append(
                    "\t".join(
                        (
                            transition.transition_id,
                            previous_pins,
                            candidate.path,
                            identity.kind,
                            identity.git_blob,
                            identity.content_sha256,
                            identity.git_mode,
                            identity.symlink_target,
                        )
                    )
                )
    return "\n".join(lines)


def render_regular_specs(entries: Iterable[SurfaceEntry], prefix: str) -> str:
    """Render regular file materialization specs."""
    lines = [
        f"{entry.path}:{source_for_entry(prefix, entry) if entry.source else ''}"
        for entry in entries
        if entry.mode == "regular" and not entry.optional
    ]
    return "\n".join(lines)


def render_removed_legacy(entries: Iterable[SurfaceEntry]) -> str:
    """Render removed legacy paths."""
    lines = [entry.path for entry in entries if entry.mode == "removed_legacy"]
    return "\n".join(lines)


def render_root_absent_paths(targets: Iterable[DeletionTarget]) -> str:
    """Render admitted paths that must be absent from a parent repo root."""
    lines = [
        target.path
        for target in targets
        if target.task == ROOT_ABSENCE_TASK
    ]
    return "\n".join(lines)


def git_index_paths(root: Path) -> frozenset[str] | None:
    """Return index paths, or None when repository state cannot be inspected."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return frozenset(path for path in completed.stdout.split("\0") if path)


def path_has_index_entry(path: str, index_paths: frozenset[str]) -> bool:
    """Return whether the index contains a path or one of its descendants."""
    normalized = path.rstrip("/")
    prefix = f"{normalized}/"
    return normalized in index_paths or any(
        index_path.startswith(prefix) for index_path in index_paths
    )


def render_actionable_root_absent_paths(
    targets: Iterable[DeletionTarget], root: Path
) -> str:
    """Render admitted R ∩ (E ∪ I), excluding fixed points.

    R contains only task-owned strict descendants admitted by
    ``admit_deletion_targets``. E is worktree existence and I is Git index
    representation. A target absent from both is already at the fixed point.
    """
    candidates = [
        target.path
        for target in targets
        if target.task == ROOT_ABSENCE_TASK
    ]
    index_paths = git_index_paths(root)
    if index_paths is None:
        return "\n".join(candidates)
    actionable = [
        path
        for path in candidates
        if os.path.lexists(root / path)
        or path_has_index_entry(path, index_paths)
    ]
    return "\n".join(actionable)


def normalized_snapshot(manifest: SurfaceManifest) -> Mapping[str, object]:
    """Return the strict DTO consumed by non-Python graph producers.

    The TOML manifest remains the source of truth.  Projection modes use the
    existing ``source_or_default`` path semantics, while non-projection modes
    preserve an omitted source as an empty string so consumers can distinguish
    a binding from a state/exclusion entry.
    """
    return {
        "schema": NORMALIZED_SNAPSHOT_SCHEMA,
        "prefix": manifest.prefix,
        "entries": [
            {
                "path": entry.path,
                "mode": entry.mode,
                "source": (
                    entry.source_or_default()
                    if entry.mode in {"symlink", "copy"}
                    else entry.source
                ),
                "projection_producer": entry.projection_producer,
                "projection_kind": entry.projection_kind,
                "local_override_allowed": entry.local_override_allowed,
                "optional": entry.optional,
            }
            for entry in manifest.entries
        ],
    }


def check_doc(root: Path, prefix: str, manifest: SurfaceManifest) -> list[str]:
    """Return doc consistency findings."""
    findings: list[str] = []
    doc_paths = (root / prefix / DEFAULT_DOC, root / DEFAULT_DOC)
    doc_path = next((path for path in doc_paths if path.is_file()), doc_paths[-1])
    doc_text = doc_path.read_text(encoding="utf-8") if doc_path.is_file() else ""
    for marker in DOC_ALWAYS_REQUIRED_MARKERS:
        if marker not in doc_text:
            findings.append(f"SURFACE_MANIFEST_FINDING={marker}:missing-doc-marker")
    sync_path = root / prefix / "tools" / "sync_agent_canon.sh"
    if not sync_path.is_file():
        sync_path = root / "tools" / "sync_agent_canon.sh"
    sync_text = sync_path.read_text(encoding="utf-8") if sync_path.is_file() else ""
    if "surface_manifest.py" not in sync_text:
        findings.append("SURFACE_MANIFEST_FINDING=tools/sync_agent_canon.sh:missing-manifest-call")
    if not manifest.entries:
        findings.append("SURFACE_MANIFEST_FINDING=documents/runtime/shared-runtime-surfaces.toml:empty-manifest")
    return findings


def render_command_outputs(manifest: SurfaceManifest, root: Path) -> Mapping[str, str]:
    """Return output text for manifest rendering commands."""
    return {
        "link-specs": render_specs(manifest.entries, root, manifest.prefix),
        "copy-specs": render_copy_specs(manifest.entries, manifest.prefix),
        "update-transition-specs": render_update_transition_specs(
            manifest.update_transitions
        ),
        "regular-specs": render_regular_specs(manifest.entries, manifest.prefix),
        "removed-legacy-paths": render_removed_legacy(manifest.entries),
        "root-absent-paths": render_root_absent_paths(
            manifest.deletion_targets
        ),
        "normalized-snapshot": json.dumps(
            normalized_snapshot(manifest),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def write_command_output(output: str) -> None:
    """Write a newline protocol without inventing an empty record."""
    if not output:
        return
    sys.stdout.write(output)
    sys.stdout.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the manifest command."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        manifest = load_manifest(root, args.prefix, args.manifest)
        if args.command in SYNC_SPEC_COMMANDS:
            manifest.require_live_agent_canon(args.command)
    except ValueError as exc:
        print(f"SURFACE_MANIFEST_ERROR={exc}", file=sys.stderr)
        return 1
    if args.command == "root-absent-paths":
        write_command_output(
            render_actionable_root_absent_paths(
                manifest.deletion_targets, root
            )
        )
        return 0
    outputs = render_command_outputs(manifest, root)
    if args.command in outputs:
        write_command_output(outputs[args.command])
        return 0
    if args.command == "check-doc":
        findings = check_doc(root, manifest.prefix, manifest)
        for finding in findings:
            print(finding)
        return 1 if findings else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
