#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Parses and validates AgentCanon shared runtime surface ownership.
# upstream design ../../documents/SHARED_RUNTIME_SURFACES.md shared surface ownership policy
# upstream design ../../documents/shared-runtime-surfaces.toml machine-readable surface manifest
# downstream implementation ../sync_agent_canon.sh consumes sync specs from this manifest
# downstream implementation ./check_convention_compliance.py validates manifest wiring
# @dependency-end
"""Parse AgentCanon runtime surface ownership manifests."""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

DEFAULT_MANIFEST = Path("documents/shared-runtime-surfaces.toml")
DEFAULT_DOC = Path("documents/SHARED_RUNTIME_SURFACES.md")
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
ALLOWED_OWNERS = frozenset(
    {
        "agent-canon",
        "template",
        "template-or-derived-repo",
        "project",
        "github-path-constraint",
        "agent-canon-standalone",
        "legacy",
    }
)
ALLOWED_CLASSES = frozenset(
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
        "standalone_only",
        "removed_legacy",
    }
)
DOC_ALWAYS_REQUIRED_MARKERS = (
    "documents/shared-runtime-surfaces.toml",
    ".codex/hooks.json",
    ".codex/hooks",
    ".devcontainer/",
    "documents/README.md",
    "documents/template-bootstrap.md",
    "documents/github-first-module-and-devcontainer-policy.md",
    "memory/USER_PREFERENCES.md",
    "tests/agent_tools/",
    "Root `tools/` is a symlink view",
    "vendor/agent-canon/tools/",
    "Project-local automation must stay in project-owned paths",
)
DOC_MARKERS_BY_MANIFEST_PATH = {
    ".codex/project-config.toml": (".codex/project-config.toml",),
    ".codex/project-skills": (".codex/project-skills",),
}


@dataclass(frozen=True)
class SurfaceEntry:
    """One root runtime surface contract."""

    path: str
    mode: str
    owner: str
    surface_class: str
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
    entries: tuple[SurfaceEntry, ...]

    def by_mode(self, mode: str) -> tuple[SurfaceEntry, ...]:
        """Return manifest entries for one mode."""
        return tuple(entry for entry in self.entries if entry.mode == mode)


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
    for command in (
        "link-specs",
        "copy-specs",
        "regular-specs",
        "removed-legacy-paths",
        "root-absent-paths",
        "check-doc",
    ):
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
    if entry.owner not in ALLOWED_OWNERS:
        raise ValueError(f"{entry.path}: invalid owner {entry.owner}")
    if entry.surface_class not in ALLOWED_CLASSES:
        raise ValueError(f"{entry.path}: invalid class {entry.surface_class}")
    if entry.mode in {"symlink", "copy"} and not entry.source_or_default():
        raise ValueError(f"{entry.path}: {entry.mode} requires a source")
    return entry


def default_local_override(owner: str) -> bool:
    """Return the default local override policy for one owner."""
    return owner in {"template", "template-or-derived-repo", "project"}


def entry_from_mapping(mapping: Mapping[str, object]) -> SurfaceEntry:
    """Create one manifest entry from one TOML table."""
    owner = string_value(mapping, "owner")
    return validate_entry(
        SurfaceEntry(
            path=string_value(mapping, "path"),
            mode=string_value(mapping, "mode"),
            owner=owner,
            surface_class=string_value(mapping, "class"),
            source=string_value(mapping, "source"),
            local_override_allowed=bool_value(
                mapping,
                "local_override_allowed",
                default_local_override(owner),
            ),
            optional=bool_value(mapping, "optional", False),
        )
    )


def entries_from_group(mapping: Mapping[str, object]) -> tuple[SurfaceEntry, ...]:
    """Expand one grouped manifest table."""
    owner = string_value(mapping, "owner")
    mode = string_value(mapping, "mode")
    surface_class = string_value(mapping, "class")
    source_prefix = string_value(mapping, "source_prefix")
    entries: list[SurfaceEntry] = []
    for path in path_list(mapping):
        source = f"{source_prefix}{path}" if source_prefix else path
        entries.append(
            validate_entry(
                SurfaceEntry(
                    path=path,
                    mode=mode,
                    owner=owner,
                    surface_class=surface_class,
                    source=source,
                    local_override_allowed=bool_value(
                        mapping,
                        "local_override_allowed",
                        default_local_override(owner),
                    ),
                    optional=bool_value(mapping, "optional", False),
                )
            )
        )
    return tuple(entries)


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
    entries: list[SurfaceEntry] = []
    for group in manifest_tables(data, "group"):
        entries.extend(entries_from_group(group))
    for surface in manifest_tables(data, "surface"):
        entries.append(entry_from_mapping(surface))
    paths = [entry.path for entry in entries]
    duplicates = sorted({path for path in paths if paths.count(path) > 1})
    if duplicates:
        raise ValueError(f"duplicate surface paths: {','.join(duplicates)}")
    return SurfaceManifest(prefix=manifest_prefix, entries=tuple(entries))


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


def render_root_absent_paths(entries: Iterable[SurfaceEntry]) -> str:
    """Render paths that must not be materialized in a parent repo root."""
    lines = [
        entry.path
        for entry in entries
        if entry.mode in {"removed_legacy", "standalone_only"}
    ]
    return "\n".join(lines)


def check_doc(root: Path, prefix: str, manifest: SurfaceManifest) -> list[str]:
    """Return doc consistency findings."""
    findings: list[str] = []
    doc_paths = (root / prefix / DEFAULT_DOC, root / DEFAULT_DOC)
    doc_path = next((path for path in doc_paths if path.is_file()), doc_paths[-1])
    doc_text = doc_path.read_text(encoding="utf-8") if doc_path.is_file() else ""
    for marker in required_doc_markers(manifest):
        if marker not in doc_text:
            findings.append(f"SURFACE_MANIFEST_FINDING={marker}:missing-doc-marker")
    sync_path = root / prefix / "tools" / "sync_agent_canon.sh"
    if not sync_path.is_file():
        sync_path = root / "tools" / "sync_agent_canon.sh"
    sync_text = sync_path.read_text(encoding="utf-8") if sync_path.is_file() else ""
    if "surface_manifest.py" not in sync_text:
        findings.append("SURFACE_MANIFEST_FINDING=tools/sync_agent_canon.sh:missing-manifest-call")
    if not manifest.entries:
        findings.append("SURFACE_MANIFEST_FINDING=documents/shared-runtime-surfaces.toml:empty-manifest")
    return findings


def required_doc_markers(manifest: SurfaceManifest) -> tuple[str, ...]:
    """Return doc markers required by always-on policy and active manifest entries."""
    markers: list[str] = list(DOC_ALWAYS_REQUIRED_MARKERS)
    manifest_paths = {entry.path for entry in manifest.entries}
    for path, path_markers in DOC_MARKERS_BY_MANIFEST_PATH.items():
        if path in manifest_paths:
            markers.extend(path_markers)
    return tuple(markers)


def render_command_outputs(manifest: SurfaceManifest, root: Path) -> Mapping[str, str]:
    """Return output text for manifest rendering commands."""
    return {
        "link-specs": render_specs(manifest.entries, root, manifest.prefix),
        "copy-specs": render_copy_specs(manifest.entries, manifest.prefix),
        "regular-specs": render_regular_specs(manifest.entries, manifest.prefix),
        "removed-legacy-paths": render_removed_legacy(manifest.entries),
        "root-absent-paths": render_root_absent_paths(manifest.entries),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the manifest command."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        manifest = load_manifest(root, args.prefix, args.manifest)
    except ValueError as exc:
        print(f"SURFACE_MANIFEST_ERROR={exc}", file=sys.stderr)
        return 1
    outputs = render_command_outputs(manifest, root)
    if args.command in outputs:
        print(outputs[args.command])
        return 0
    if args.command == "check-doc":
        findings = check_doc(root, manifest.prefix, manifest)
        for finding in findings:
            print(finding)
        return 1 if findings else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
