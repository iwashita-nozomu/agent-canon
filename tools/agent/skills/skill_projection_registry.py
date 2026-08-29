#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Resolves ignored generated skill views to catalog-owned source documents.
# upstream design ../../../documents/design/skill-runtime-shim-materialization.md owns the materializer path contract
# upstream implementation ../../../agents/skills/catalog.yaml owns public skill identity and owner paths
# downstream implementation ../../runtime/manifest/surface_manifest.py publishes the Rust graph snapshot
# downstream implementation ../../analysis/dependencies/source_dependency_graph.py resolves source-only graph targets
# @dependency-end
"""Read the materializer-owned mapping for generated skill projections."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - clean host before the tool image exists.
    try:
        from tools.runtime.container import stdlib_yaml as yaml
    except ImportError:
        import tools.runtime.container.stdlib_yaml as yaml  # type: ignore[no-redef]

SKILL_CATALOG = Path("agents/skills/catalog.yaml")
GENERATED_SKILL_PREFIX = ".codex/personal/skills/"
GENERATED_SKILL_SUFFIX = "/SKILL.md"
GENERATED_SKILL_REF_RE = re.compile(
    r"\.codex/personal/skills/[^\s`)>]+/SKILL\.md"
)


@dataclass(frozen=True)
class GeneratedProjection:
    """One ignored generated view mapped to its tracked materializer owner."""

    path: str
    source: str
    projection_producer: str
    projection_kind: str


class GeneratedProjectionRegistryError(ValueError):
    """A generated view has no unique canonical owner."""

    def __init__(self, code: str, path: str, owners: tuple[str, ...]) -> None:
        """Bind a stable code, target path, and competing owners."""
        self.code = code
        self.path = path
        self.owners = owners
        super().__init__(f"{code}:{path}:{','.join(owners)}")


def generated_skill_projections(root: Path) -> tuple[GeneratedProjection, ...]:
    """Read catalog and internal-routine generated paths without requiring views."""
    catalog_path = root.resolve() / SKILL_CATALOG
    projections: list[GeneratedProjection] = []
    owners: dict[str, str] = {}
    if catalog_path.is_file():
        try:
            raw: object = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise ValueError(f"skill catalog unavailable: {error}") from error
        if not isinstance(raw, Mapping) or not isinstance(raw.get("skill_families"), list):
            raise ValueError("skill catalog must contain a skill_families list")
        for index, item in enumerate(cast(list[object], raw["skill_families"])):
            if not isinstance(item, Mapping):
                raise ValueError(f"skill catalog entry {index} must be a mapping")
            skill = item.get("id")
            canonical = item.get("canonical_doc")
            shim = item.get("shim")
            if not all(
                isinstance(value, str) and value
                for value in (skill, canonical, shim)
            ):
                raise ValueError(f"skill catalog entry {index} has incomplete identity")
            expected_canonical = f"agents/skills/{skill}.md"
            expected_shim = f"{GENERATED_SKILL_PREFIX}{skill}{GENERATED_SKILL_SUFFIX}"
            if canonical != expected_canonical or shim != expected_shim:
                raise ValueError(
                    f"skill catalog entry {skill} has non-canonical materializer paths"
                )
            if shim in owners:
                raise ValueError(f"duplicate generated skill projection: {shim}")
            owners[shim] = canonical
            projections.append(
                GeneratedProjection(
                    path=shim,
                    source=canonical,
                    projection_producer="agent-canon-bootstrap",
                    projection_kind="skill_shim",
                )
            )
    # Internal routines are intentionally outside the public skill catalog,
    # but private runtime adapters are still generated views of their source.
    internal_root = root.resolve() / "agents" / "internal-routines"
    if internal_root.is_dir():
        for source_path in sorted(internal_root.rglob("*.md")):
            source = source_path.relative_to(root.resolve()).as_posix()
            try:
                text = source_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as error:
                raise ValueError(
                    f"internal routine unavailable: {source}: {error}"
                ) from error
            for shim in sorted(set(GENERATED_SKILL_REF_RE.findall(text))):
                if not shim.split(GENERATED_SKILL_PREFIX, 1)[1].startswith("_"):
                    continue
                previous_owner = owners.get(shim)
                if previous_owner is not None:
                    if previous_owner != source:
                        raise GeneratedProjectionRegistryError(
                            "generated_projection_ambiguous",
                            shim,
                            (previous_owner, source),
                        )
                    continue
                owners[shim] = source
                projections.append(
                    GeneratedProjection(
                        path=shim,
                        source=source,
                        projection_producer="agent-canon-bootstrap",
                        projection_kind="internal_skill_shim",
                    )
                )
    return tuple(sorted(projections, key=lambda projection: projection.path))


def generated_skill_projection_target(root: Path, relative: str) -> str | None:
    """Resolve one generated skill path through the catalog materializer registry."""
    for projection in generated_skill_projections(root):
        if projection.path == relative:
            return projection.source
    return None
