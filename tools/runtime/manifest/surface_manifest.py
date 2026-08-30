#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Parses and validates AgentCanon-owned standalone runtime surface classification.
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md bootstrap runtime surface policy
# upstream design ../../documents/runtime/shared-runtime-surfaces.toml machine-readable runtime inventory
# upstream implementation ./skill_projection_registry.py resolves generated skill-view owner paths
# downstream implementation ../../tools/runtime/dispatch/agent-canon/src/dependency_manifest.rs consumes normalized source classification
# downstream implementation ./check_convention_compliance.py validates runtime catalog wiring
# @dependency-end
"""Parse AgentCanon standalone runtime-surface classification metadata.

This module deliberately has no parent-repository synchronization authority.  It
only validates the source-owned inventory and emits the JSON snapshot consumed by
the standalone graph builder.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]

try:
    from tools.agent.skills.skill_projection_registry import (
        GeneratedProjection,
        generated_skill_projections,
    )
except ImportError:  # pragma: no cover - direct script execution
    from tools.agent.skills.skill_projection_registry import (  # type: ignore[no-redef]
        GeneratedProjection,
        generated_skill_projections,
    )

DEFAULT_MANIFEST = Path("documents/runtime/shared-runtime-surfaces.toml")
DEFAULT_DOC = Path("documents/runtime/SHARED_RUNTIME_SURFACES.md")
NORMALIZED_SNAPSHOT_SCHEMA = "agent-canon.surface-manifest.v2"
MANIFEST_COMMANDS = frozenset({"normalized-snapshot", "check-doc", "projection-forbidden-roots"})
ALLOWED_MODES = frozenset({"runtime", "tool", "eval"})
ALLOWED_PROJECTION_PRODUCERS = frozenset({"agent-canon", "agent-canon-bootstrap", "agent-canon-log"})
ALLOWED_PROJECTION_KINDS = frozenset({"runtime_surface", "tool_surface", "eval_surface"})
DOC_MARKERS = (
    "bootstrap runtime",
    "standalone",
    "agent-canon-log",
    "no parent-repository synchronization",
)


@dataclass(frozen=True)
class SurfaceSelection:
    """Typed runtime inventory selection metadata."""

    integration_mode: str
    default_consumer: bool
    selection: str


@dataclass(frozen=True)
class SurfaceEntry:
    """One AgentCanon-owned standalone runtime surface."""

    path: str
    mode: str
    projection_producer: str
    projection_kind: str
    source: str
    local_override_allowed: bool
    optional: bool

    def source_or_default(self) -> str:
        """Return the source path used by the standalone snapshot."""
        return self.source or self.path


@dataclass(frozen=True)
class SurfaceManifest:
    """Validated runtime inventory content."""

    prefix: str
    surface_selection: SurfaceSelection
    entries: tuple[SurfaceEntry, ...]
    generated_projections: tuple[GeneratedProjection, ...] = ()
    projection_forbidden_roots: tuple[str, ...] = ()

    @property
    def integration_mode(self) -> str:
        return self.surface_selection.integration_mode

    @property
    def default_consumer(self) -> bool:
        return self.surface_selection.default_consumer

    @property
    def selection(self) -> str:
        return self.surface_selection.selection

    def by_mode(self, mode: str) -> tuple[SurfaceEntry, ...]:
        return tuple(entry for entry in self.entries if entry.mode == mode)


def _string(mapping: Mapping[str, object], key: str, *, required: bool = False, default: str = "") -> str:
    value = mapping.get(key, default)
    if required and key not in mapping:
        raise ValueError(f"{key} is required")
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _bool(mapping: Mapping[str, object], key: str, default: bool) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _relative(value: str, field: str) -> str:
    path = Path(value)
    if not value or path.is_absolute() or "\\" in value or ".." in path.parts or path.as_posix() != value:
        raise ValueError(f"{field} must be a normalized repository-relative POSIX path")
    return value


def _list(mapping: Mapping[str, object], key: str) -> tuple[str, ...]:
    raw = mapping.get(key, [])
    if not isinstance(raw, list):
        raise ValueError(f"{key} must be a list")
    values: list[str] = []
    for item in cast(list[object], raw):
        if not isinstance(item, str) or not item:
            raise ValueError(f"{key} entries must be non-empty strings")
        values.append(_relative(item, f"{key} entry"))
    return tuple(values)


def _tables(data: Mapping[str, object], key: str) -> tuple[Mapping[str, object], ...]:
    raw = data.get(key, [])
    if not isinstance(raw, list):
        raise ValueError(f"{key} must be a list")
    tables: list[Mapping[str, object]] = []
    for item in cast(list[object], raw):
        if not isinstance(item, dict):
            raise ValueError(f"{key} entries must be tables")
        tables.append(cast(Mapping[str, object], item))
    return tuple(tables)


def _entry(mapping: Mapping[str, object]) -> SurfaceEntry:
    path = _relative(_string(mapping, "path", required=True), "surface path")
    mode = _string(mapping, "mode", required=True)
    if mode not in ALLOWED_MODES:
        raise ValueError(f"{path}: unsupported runtime surface mode {mode}")
    producer = _string(mapping, "projection_producer", required=True)
    if producer not in ALLOWED_PROJECTION_PRODUCERS:
        raise ValueError(f"{path}: unsupported runtime surface producer {producer}")
    kind = _string(mapping, "projection_kind", required=True)
    if kind not in ALLOWED_PROJECTION_KINDS:
        raise ValueError(f"{path}: unsupported runtime surface kind {kind}")
    source = _string(mapping, "source")
    if source:
        source = _relative(source, f"{path}: source")
    return SurfaceEntry(path, mode, producer, kind, source, _bool(mapping, "local_override_allowed", False), _bool(mapping, "optional", False))


def _selection(data: Mapping[str, object]) -> SurfaceSelection:
    mode = _string(data, "integration_mode", required=True)
    if mode != "agent-canon-runtime":
        raise ValueError(f"invalid integration_mode: {mode}")
    default = _bool(data, "default_consumer", False)
    selection = _string(data, "selection", required=True)
    if selection != "explicit-opt-in":
        raise ValueError(f"invalid selection: {selection}")
    return SurfaceSelection(mode, default, selection)


def manifest_path(root: Path, prefix: str, raw_manifest: str) -> Path:
    """Resolve a source-owned manifest path."""
    relative = Path(raw_manifest)
    prefixed = root / prefix / relative
    return prefixed if prefixed.is_file() else root / relative


def load_manifest(root: Path, prefix: str, raw_manifest: str) -> SurfaceManifest:
    """Load and validate standalone runtime classification metadata."""
    path = manifest_path(root, prefix, raw_manifest)
    data = cast(Mapping[str, object], tomllib.loads(path.read_text(encoding="utf-8")))
    if data.get("version") != 1:
        raise ValueError("version = 1 is required")
    entries = tuple(_entry(table) for table in _tables(data, "surface"))
    paths = [entry.path for entry in entries]
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate surface paths")
    generated_projections = generated_skill_projections(root)
    forbidden = _list(data, "projection_forbidden_roots")
    return SurfaceManifest(
        _string(data, "prefix", default=prefix),
        _selection(data),
        entries,
        generated_projections,
        forbidden,
    )


def normalized_snapshot(manifest: SurfaceManifest) -> Mapping[str, object]:
    """Return the graph-builder snapshot without synchronization operations."""
    return {
        "schema": NORMALIZED_SNAPSHOT_SCHEMA,
        "prefix": manifest.prefix,
        "entries": [
            {
                "path": entry.path,
                "mode": entry.mode,
                "source": entry.source_or_default(),
                "projection_producer": entry.projection_producer,
                "projection_kind": entry.projection_kind,
                "local_override_allowed": entry.local_override_allowed,
                "optional": entry.optional,
            }
            for entry in manifest.entries
        ],
        "generated_projections": [
            {
                "path": projection.path,
                "source": projection.source,
                "projection_producer": projection.projection_producer,
                "projection_kind": projection.projection_kind,
            }
            for projection in manifest.generated_projections
        ],
    }


def check_doc(root: Path, prefix: str, manifest: SurfaceManifest) -> list[str]:
    """Check the auxiliary runtime document and non-empty inventory."""
    candidates = (root / prefix / DEFAULT_DOC, root / DEFAULT_DOC)
    path = next((item for item in candidates if item.is_file()), candidates[-1])
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    findings = [f"SURFACE_MANIFEST_FINDING={marker}:missing-doc-marker" for marker in DOC_MARKERS if marker not in text]
    if not manifest.entries:
        findings.append("SURFACE_MANIFEST_FINDING=runtime-inventory:empty-manifest")
    return findings


def build_parser() -> argparse.ArgumentParser:
    """Create the standalone inventory CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--prefix", default=".")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("command", choices=sorted(MANIFEST_COMMANDS))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one source inventory command."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        manifest = load_manifest(root, args.prefix, args.manifest)
    except (OSError, ValueError) as error:
        print(f"SURFACE_MANIFEST_ERROR={error}", file=__import__("sys").stderr)
        return 1
    if args.command == "normalized-snapshot":
        print(json.dumps(normalized_snapshot(manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    elif args.command == "projection-forbidden-roots":
        print("\n".join(manifest.projection_forbidden_roots))
    else:
        findings = check_doc(root, args.prefix, manifest)
        for finding in findings:
            print(finding)
        return 1 if findings else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
