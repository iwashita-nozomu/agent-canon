#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Materializes and reads back the complete public Codex skill-shim adapter set.
# upstream design ../../documents/design/skill-runtime-shim-materialization.md owns the v3 schema, migration, and fixed-point contract
# upstream design ../../agents/skills/catalog.yaml owns public skill identity, discovery metadata, and command phases
# upstream implementation ./skill_route_catalog.py owns typed route and dependency projections
# upstream implementation ./skill_dependency_map.py owns graph/tool identity projections
# upstream implementation ./skill_tool_commands.py owns read-only command packets
# upstream implementation ./tool_calls.py owns skill ToolCall token materialization
# downstream implementation ../../tests/agent_tools/test_skill_shim_materializer.py validates migration, readback, and fixed point
# @dependency-end
"""Materialize the canonical thin runtime shims for all public skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import stat
import tempfile
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, cast

try:
    import yaml
except ModuleNotFoundError:  # clean host before the shared tool image exists
    try:
        from . import stdlib_yaml as yaml
    except ImportError:
        import stdlib_yaml as yaml  # type: ignore[no-redef]
from agent_canon_source_root import resolve_agent_canon_source_root

if __package__:
    from .tool_calls import materialize_skill_tool_call_token
else:
    from tool_calls import materialize_skill_tool_call_token
from skill_dependency_map import build_graph
from skill_route_catalog import (
    SkillDependencyRule,
    SkillRoutingRule,
    load_skill_catalog,
    load_skill_dependency_map,
    load_skill_route_rules,
)
from skill_tool_commands import SkillCommandPacket, packet_for_skill

try:
    from .parent_root_side_effects import (
        ParentRootAttestationRequest,
        ParentRootReject,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
    )
except ImportError:
    from parent_root_side_effects import (  # type: ignore[no-redef]
        ParentRootAttestationRequest,
        ParentRootReject,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
    )

SCHEMA = "agent_canon.skill_runtime_shim"
VERSION = 3
FIXED_POINT_SCHEMA = "agent_canon.skill_runtime_shim.fixed_point"
MATERIALIZER_ID = "skill_shim_materializer.v3"
TEMPLATE_ID = "skill-runtime-shim-md-v3"
COMMAND_PACKET_TEMPLATE_ID = "skill-tool-command-packet-v3"
MATERIALIZATION_RECORD_SCHEMA = "agent_canon.skill_runtime_shim.materialization_record"
MATERIALIZATION_RECORD_VERSION = 3
RUNTIME_ROOT = Path(".codex/personal/skills")
CATALOG_PATH = Path("agents/skills/catalog.yaml")
DEPENDENCY_PATH = Path("agents/skills/skill-dependencies.yaml")
GRAPH_PATH = Path("documents/runtime/skill-dependency-graph.json")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ABSOLUTE_LOCATOR_RE = re.compile(
    r"(?<![A-Za-z0-9._~/<>-])/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+"
)


def _parent_boundary(
    root: Path, purpose: str, *, image_build: bool = False
) -> tuple[Any, Any]:
    """Return an authenticated capability for every materializer write."""
    if image_build:
        if os.environ.get("AGENT_CANON_IMAGE_BUILD") != "1":
            raise ParentRootSideEffectError(
                ParentRootReject.HANDOFF_INVALID,
                "image-build mode requires the Docker build capability",
            )
        return _ImageBuildBoundary(root), _ImageBuildAttestation(root.resolve(strict=True))
    configured = os.environ.get("AGENT_CANON_PARENT_ROOT", "").strip()
    if not configured:
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID,
            f"{purpose}: explicit parent root is required",
        )
    parent = Path(configured).resolve(strict=True)
    attestation = attest_parent_root(
        ParentRootAttestationRequest(cwd=parent, explicit_root=parent, purpose=purpose)
    )
    return ParentRootSideEffectBoundary(), attestation


class MaterializerError(RuntimeError):
    """One stable fail-closed materializer error."""

    def __init__(self, code: str, detail: str = "") -> None:
        """Bind a stable machine error code and optional detail."""
        self.code = code
        self.detail = detail
        message = code if not detail else f"{code}:{detail}"
        super().__init__(message)


@dataclass(frozen=True)
class _ImageBuildPath:
    """One generated target receipt for the explicit image-build mode."""

    physical_path: Path
    target_dev: int | None
    target_ino: int | None


@dataclass(frozen=True)
class _ImageBuildAttestation:
    """Trusted image-layer root supplied by the Dockerfile build step."""

    root: Path


class _ImageBuildBoundary:
    """Provide the materializer write protocol for an ephemeral image layer."""

    def __init__(self, root: Path) -> None:
        """Bind one absolute, regular image build root."""
        if root.is_symlink():
            raise MaterializerError("image_build_root_invalid", str(root))
        resolved = root.resolve(strict=True)
        if not resolved.is_dir():
            raise MaterializerError("image_build_root_invalid", str(root))
        self.root = resolved

    def _target(self, candidate: Path) -> Path:
        """Resolve one target beneath the image root without following links."""
        lexical = candidate if candidate.is_absolute() else self.root / candidate
        if any(part == ".." for part in lexical.parts):
            raise MaterializerError("image_build_path_escape", str(candidate))
        try:
            lexical.relative_to(self.root)
        except ValueError as exc:
            raise MaterializerError("image_build_path_escape", str(candidate)) from exc
        current = self.root
        for part in lexical.relative_to(self.root).parts:
            current /= part
            if current.is_symlink():
                raise MaterializerError("image_build_symlink", str(current))
        target = lexical.resolve(strict=False)
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise MaterializerError("image_build_path_escape", str(candidate)) from exc
        return target

    def resolve_parent_owned_path(
        self,
        _attestation: _ImageBuildAttestation,
        candidate: Path,
        _purpose: str,
        *,
        create: bool = False,
    ) -> _ImageBuildPath:
        """Resolve a generated file and create its parent when requested."""
        target = self._target(candidate)
        if create or not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not target.is_file():
            raise MaterializerError("image_build_target_invalid", str(target))
        target_stat = target.stat() if target.exists() else None
        return _ImageBuildPath(
            target,
            target_stat.st_dev if target_stat is not None else None,
            target_stat.st_ino if target_stat is not None else None,
        )

    @staticmethod
    def read_parent_owned_file(receipt: _ImageBuildPath) -> bytes:
        """Read one generated image-layer target."""
        return receipt.physical_path.read_bytes()

    def atomic_publish(
        self,
        receipt: _ImageBuildPath,
        data: bytes,
        *,
        mode: int = 0o644,
    ) -> _ImageBuildPath:
        """Publish one generated file atomically into the image layer."""
        target = self._target(receipt.physical_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise MaterializerError("image_build_target_invalid", str(target))
        current = target.stat() if target.exists() else None
        if receipt.target_dev is not None and (
            current is None
            or current.st_dev != receipt.target_dev
            or current.st_ino != receipt.target_ino
        ):
            raise MaterializerError("image_build_target_changed", str(target))
        temporary_fd, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        try:
            with os.fdopen(temporary_fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary_name, stat.S_IMODE(mode))
            os.replace(temporary_name, target)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
        published = target.stat()
        return _ImageBuildPath(target, published.st_dev, published.st_ino)


class PartialStopError(MaterializerError):
    """A per-file replace stopped after a partial runtime update."""

    def __init__(self, path: str, replaced: int) -> None:
        """Bind the target that stopped and completed replace count."""
        super().__init__("partial_stop", f"path={path}:replaced={replaced}")
        self.path = path
        self.replaced = replaced


class LegacyMigrationError(MaterializerError):
    """A fail-closed legacy migration with every unmatched block receipt."""

    def __init__(self, receipt: Sequence[Mapping[str, object]]) -> None:
        """Preserve every legacy classification for fail-closed reporting."""
        super().__init__("unresolved_legacy_blocks")
        self.receipt = [dict(row) for row in receipt]


class SkillToolCallMaterializer(Protocol):
    """Typed callable boundary for the agent-team ToolCall owner."""

    def __call__(self, skill: str, *, phase: str = "required") -> dict[str, object]:
        """Materialize one skill/phase ToolCall identity."""
        ...


@dataclass(frozen=True)
class BuildContext:
    """All canonical inputs used by one materialization run."""

    root: Path
    output_root: Path
    skill_ids: tuple[str, ...]
    catalog_entries: Mapping[str, Mapping[str, object]]
    routes: Mapping[str, SkillRoutingRule]
    dependencies: Mapping[str, SkillDependencyRule]
    packets: Mapping[str, SkillCommandPacket]
    graph: Mapping[str, object]
    source_snapshot_digest: str


def _normalize_string(value: str, *, identifier: bool = False) -> str:
    """Normalize one scalar according to the canonical serialization contract."""
    normalized = unicodedata.normalize("NFKC" if identifier else "NFC", value)
    if identifier:
        normalized = normalized.lower()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized):
            raise MaterializerError("invalid_identifier", normalized)
    return normalized.replace("\r\n", "\n").replace("\r", "\n")


def _canonical_value(value: object) -> object:
    """Normalize a JSON-compatible value without changing semantic array order."""
    if isinstance(value, str):
        return _normalize_string(value)
    if isinstance(value, bool) or isinstance(value, int):
        return value
    if value is None:
        raise MaterializerError("null_not_allowed")
    if isinstance(value, Mapping):
        mapping = _mapping(dict(cast(dict[str, object], value)), "canonical_value")
        return {str(key): _canonical_value(item) for key, item in mapping.items()}
    if isinstance(value, (list, tuple)):
        sequence = cast(list[object] | tuple[object, ...], value)
        return [_canonical_value(item) for item in sequence]
    raise MaterializerError("unsupported_canonical_value", type(value).__name__)


def canonical_json_bytes(value: object) -> bytes:
    """Serialize compact UTF-8 JSON while preserving the declared field order."""
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def domain_digest(domain: str, value: object) -> str:
    """Hash one canonical value in a named digest domain."""
    return hashlib.sha256(
        domain.encode("utf-8") + b"\0" + canonical_json_bytes(value)
    ).hexdigest()


def file_digest(path: Path) -> str:
    """Hash source bytes exactly as stored."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise MaterializerError("invalid_mapping", field)
    return dict(cast(dict[str, object], value))


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MaterializerError("invalid_string", field)
    return _normalize_string(value)


def _catalog_entries(
    root: Path,
) -> tuple[tuple[str, ...], dict[str, Mapping[str, object]]]:
    """Load the complete public catalog and its discovery source."""
    data = load_skill_catalog(root)
    families = data.get("skill_families")
    if not isinstance(families, list):
        raise MaterializerError("catalog_invalid", "skill_families")
    ids: list[str] = []
    entries: dict[str, Mapping[str, object]] = {}
    for index, raw in enumerate(cast(list[object], families)):
        entry = _mapping(raw, f"skill_families[{index}]")
        skill = _string(entry.get("id"), f"skill_families[{index}].id")
        _normalize_string(skill, identifier=True)
        if skill in entries:
            raise MaterializerError("catalog_duplicate", skill)
        discovery = _mapping(entry.get("discovery"), f"{skill}.discovery")
        discovery_name = _string(discovery.get("name"), f"{skill}.discovery.name")
        _string(discovery.get("description"), f"{skill}.discovery.description")
        if discovery_name != skill:
            raise MaterializerError("discovery_name_mismatch", skill)
        ids.append(skill)
        entries[skill] = entry
    return tuple(ids), entries


def _route_payload(rule: SkillRoutingRule) -> dict[str, object]:
    """Project route identity without making a second route decision."""
    return {
        "skill": rule.skill,
        "reason": rule.reason,
        "stage_policy": rule.stage_policy,
        "triggers": [list(group) for group in rule.triggers],
        "capabilities": [asdict(capability) for capability in rule.capabilities],
        "related_skills": list(rule.related_skills),
        "visualization_owner_skill": rule.visualization_owner_skill or "none",
        "visualization_role": rule.visualization_role,
        "tool_id": rule.tool_id,
        "argument_schema": rule.argument_schema,
        "responsibility_group": rule.responsibility_group,
    }


def _dependency_payload(rule: SkillDependencyRule) -> dict[str, object]:
    """Project dependency identity in source order."""
    return {
        "skill": rule.skill,
        "responsibility_group": rule.responsibility_group,
        "required_prerequisites": list(rule.required_prerequisites),
        "routing_candidates": list(rule.routing_candidates),
        "successors": list(rule.successors),
        "order_constraints": [asdict(item) for item in rule.order_constraints],
        "parallel_independent": list(rule.parallel_independent),
    }


def _packet_payload(packet: SkillCommandPacket, root: Path) -> dict[str, object]:
    """Canonicalize a full command packet while removing machine-specific roots."""
    result: dict[str, object] = {}
    for field in SkillCommandPacket.__dataclass_fields__:
        value = getattr(packet, field)
        if field.startswith("resolved_"):
            rows: list[list[object]] = []
            resolved_commands = cast(
                tuple[
                    tuple[str, str, str, tuple[tuple[str, str], ...], tuple[str, ...]],
                    ...,
                ],
                value,
            )
            for (
                logical,
                _source_root,
                _execution_cwd,
                root_bindings,
                argv,
            ) in resolved_commands:
                resolved_argv: list[str] = []
                for token in argv:
                    token_path = Path(token)
                    normalized_token = token
                    if token_path.is_absolute():
                        try:
                            normalized_token = (
                                "@root/"
                                + token_path.resolve()
                                .relative_to(root.resolve())
                                .as_posix()
                            )
                        except ValueError:
                            normalized_token = "@absolute"
                    resolved_argv.append(normalized_token)
                normalized_bindings: list[list[str]] = []
                for binding_key, binding in root_bindings:
                    binding_path = Path(binding)
                    if binding_path.is_absolute():
                        try:
                            binding = (
                                "@root/"
                                + binding_path.resolve()
                                .relative_to(root.resolve())
                                .as_posix()
                            )
                        except ValueError:
                            binding = "@absolute"
                    normalized_bindings.append([binding_key, binding])
                rows.append(
                    [logical, "@root", "@root", normalized_bindings, resolved_argv]
                )
            result[field] = rows
        elif isinstance(value, tuple):
            result[field] = list(cast(tuple[object, ...], value))
        else:
            result[field] = value
    return result


def _tool_call_refs(packet: SkillCommandPacket) -> tuple[list[dict[str, object]], str]:
    """Read skill/phase ToolCall identities from their sole owner."""
    phases = (
        ("required", packet.required_commands),
        ("discovered", packet.discovered_commands),
        ("conditional", packet.conditional_commands),
        ("maintenance", packet.maintenance_commands),
    )
    refs: list[dict[str, object]] = []
    for phase, commands in phases:
        if not commands:
            continue
        materialize_token = cast(
            SkillToolCallMaterializer, materialize_skill_tool_call_token
        )
        token = materialize_token(packet.skill, phase=phase)
        identity = cast(Mapping[str, object], token["identity"])
        refs.append({"command_count": len(commands), **dict(identity)})
    if not refs:
        raise MaterializerError("tool_call_phase_missing", packet.skill)
    payload = {"skill": packet.skill, "phase_refs": refs}
    return refs, domain_digest(
        "agent-canon.skill-runtime-shim.owner.tool-surface.v2", payload
    )


def _source_snapshot_digest(
    root: Path, graph: Mapping[str, object], skill_ids: Sequence[str]
) -> str:
    """Hash only immutable sources so runtime target replacement cannot perturb fixed point."""
    files = {
        "catalog": file_digest(root / CATALOG_PATH),
        "dependencies": file_digest(root / DEPENDENCY_PATH),
        "graph": cast(str, graph["graph_digest"]),
    }
    files["canonical_docs"] = domain_digest(
        "agent-canon.skill-runtime-shim.canonical-docs.v1",
        {
            skill: file_digest(root / "agents/skills" / f"{skill}.md")
            for skill in skill_ids
        },
    )
    return domain_digest("agent-canon.skill-runtime-shim.source-snapshot.v1", files)


def build_context(root: Path, *, output_root: Path | None = None) -> BuildContext:
    """Load and validate the complete canonical input universe."""
    root = root.resolve()
    output = (output_root or root).resolve()
    skill_ids, entries = _catalog_entries(root)
    try:
        routes = {rule.skill: rule for rule in load_skill_route_rules(root)}
        dependencies = dict(load_skill_dependency_map(root, skill_ids))
        graph = cast(Mapping[str, object], build_graph(root))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise MaterializerError("owner_source_invalid", str(exc)) from exc
    if set(routes) != set(skill_ids) or set(dependencies) != set(skill_ids):
        raise MaterializerError("owner_skill_set_mismatch")
    try:
        resolution = resolve_agent_canon_source_root(root)
        packets = {skill: packet_for_skill(resolution, skill) for skill in skill_ids}
    except (OSError, ValueError) as exc:
        raise MaterializerError("command_packet_invalid", str(exc)) from exc
    if len(packets) != len(skill_ids):
        raise MaterializerError("command_packet_count_mismatch", str(len(packets)))
    return BuildContext(
        root,
        output,
        skill_ids,
        entries,
        routes,
        dependencies,
        packets,
        graph,
        _source_snapshot_digest(root, graph, skill_ids),
    )


def _catalog_discovery(entry: Mapping[str, object]) -> tuple[str, str]:
    discovery = _mapping(entry["discovery"], "discovery")
    return _string(discovery["name"], "discovery.name"), _string(
        discovery["description"], "discovery.description"
    )


def build_record(context: BuildContext, skill: str) -> dict[str, object]:
    """Build one fixed-order v3 SkillRuntimeShimRecord."""
    entry = context.catalog_entries[skill]
    name, description = _catalog_discovery(entry)
    canonical_doc = _string(entry.get("canonical_doc"), f"{skill}.canonical_doc")
    shim_path = _string(entry.get("shim"), f"{skill}.shim")
    if shim_path != f".codex/personal/skills/{skill}/SKILL.md":
        raise MaterializerError("shim_path_mismatch", skill)
    if canonical_doc != f"agents/skills/{skill}.md":
        raise MaterializerError("canonical_doc_mismatch", skill)
    canonical_path = context.root / canonical_doc
    if not canonical_path.is_file():
        raise MaterializerError("missing_canonical_doc", skill)
    packet = context.packets[skill]
    tool_call_refs, tool_surface_digest = _tool_call_refs(packet)
    packet_digest = domain_digest(
        "skill_tool_commands.v2", _packet_payload(packet, context.root)
    )
    route = context.routes[skill]
    dependency = context.dependencies[skill]
    catalog_identity = domain_digest(
        "agent-canon.skill-runtime-shim.owner.catalog.v1",
        {
            "id": skill,
            "purpose": _string(entry.get("purpose"), f"{skill}.purpose"),
            "canonical_doc": canonical_doc,
            "shim": shim_path,
            "discovery": {"name": name, "description": description},
        },
    )
    dependency_identity = domain_digest(
        "agent-canon.skill-runtime-shim.owner.dependency.v1",
        _dependency_payload(dependency),
    )
    route_identity = domain_digest(
        "agent-canon.skill-runtime-shim.owner.route.v1", _route_payload(route)
    )
    source_digests = {
        "catalog_source_digest": file_digest(context.root / CATALOG_PATH),
        "dependency_source_digest": file_digest(context.root / DEPENDENCY_PATH),
        "canonical_doc_digest": file_digest(canonical_path),
    }
    record: dict[str, object] = {
        "schema": {"id": SCHEMA, "version": VERSION},
        "skill_id": skill,
        "discovery": {
            "name": name,
            "description": description,
            "shim_path": shim_path,
            "method": "managed-global-agents-skills-discovery",
        },
        "owner": {
            "canonical_doc": canonical_doc,
            "canonical_ref": f"{CATALOG_PATH.as_posix()}#skill:{skill}.canonical_doc",
            "catalog_ref": f"{CATALOG_PATH.as_posix()}#skill:{skill}",
            "dependency_ref": f"{DEPENDENCY_PATH.as_posix()}#invocation:{skill}",
            "route_ref": f"{CATALOG_PATH.as_posix()}#skill:{skill}.routing",
            "command_ref": f"{CATALOG_PATH.as_posix()}#skill:{skill}.tool_commands",
            "tool_surface_ref": "tools/agent_tools/agent_team.py#materialize_skill_tool_call_token",
            "graph_ref": f"{GRAPH_PATH.as_posix()}#skill:{skill}",
        },
        "identity": {
            "catalog_identity_digest": catalog_identity,
            "dependency_identity_digest": dependency_identity,
            "route_identity_digest": route_identity,
            "command_packet_identity_digest": packet_digest,
            "tool_surface_identity_digest": tool_surface_digest,
            "tool_call_refs": tool_call_refs,
        },
        "render": {
            "mode": "adapter_only",
            "template_id": TEMPLATE_ID,
            "command_packet_template_id": COMMAND_PACKET_TEMPLATE_ID,
        },
        "provenance": {
            "catalog_source_digest": source_digests["catalog_source_digest"],
            "dependency_source_digest": source_digests["dependency_source_digest"],
            "canonical_doc_digest": source_digests["canonical_doc_digest"],
            "materializer_id": MATERIALIZER_ID,
        },
    }
    if not tool_call_refs:
        raise MaterializerError("argument_schema_missing", skill)
    record_digest = domain_digest("agent-canon.skill-runtime-shim.record.v3", record)
    cast(dict[str, object], record["provenance"])["record_digest"] = record_digest
    return record


def _record_digest(record: Mapping[str, object]) -> str:
    return cast(str, cast(Mapping[str, object], record["provenance"])["record_digest"])


def _materialization_record_comment(record: Mapping[str, object]) -> str:
    """Render the sole structured metadata comment from the rebuilt record."""
    payload = {
        "schema": MATERIALIZATION_RECORD_SCHEMA,
        "version": MATERIALIZATION_RECORD_VERSION,
        "record_digest": _record_digest(record),
    }
    return (
        "<!-- materialization-record: "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + " -->"
    )


def _dependency_manifest_lines(record: Mapping[str, object]) -> list[str]:
    """Render the discovery adapter dependency manifest."""
    skill = cast(str, record["skill_id"])
    owner = cast(Mapping[str, object], record["owner"])
    canonical_doc = cast(str, owner["canonical_doc"])
    runtime_dir = f"{RUNTIME_ROOT.as_posix()}/{skill}"
    canonical_link = posixpath.relpath(canonical_doc, runtime_dir)
    body = [
        "contract skill",
        f"responsibility Exposes {skill} for runtime discovery.",
        f"upstream design {canonical_link} owner",
    ]
    return ["<!--", "@dependency-start", *body, "@dependency-end", "-->"]


def _render_shim_template(
    record: Mapping[str, object],
    *,
    metadata_lines: Sequence[str],
) -> str:
    """Render one complete generated schema without optional sections."""
    discovery = cast(Mapping[str, object], record["discovery"])
    owner = cast(Mapping[str, object], record["owner"])
    skill = cast(str, record["skill_id"])
    description = json.dumps(cast(str, discovery["description"]), ensure_ascii=False)
    canonical_doc = cast(str, owner["canonical_doc"])
    canonical_link = posixpath.relpath(canonical_doc, f"{RUNTIME_ROOT.as_posix()}/{skill}")
    lines = [
        "---",
        f"name: {discovery['name']}",
        f"description: {description}",
        "---",
        *metadata_lines,
        "",
        *_dependency_manifest_lines(record),
        "",
        f"# {skill}",
        "",
        "## Canonical Skill",
        "",
        f"Canonical workflow and policy: [{skill}]({canonical_link}).",
        "",
        "## Tool Commands",
        "",
        "<!-- skill-tool-commands:start -->",
        f"`python3 tools/agent_tools/skill_tool_commands.py show --skill {skill} --format text`",
        "<!-- skill-tool-commands:end -->",
        "",
        "1. Read the canonical owner before applying this skill.",
        "",
    ]
    text = "\n".join(lines)
    if ABSOLUTE_LOCATOR_RE.search(text):
        raise MaterializerError("absolute_locator", skill)
    return text


def render_shim(record: Mapping[str, object]) -> str:
    """Render the final adapter with one versioned record-digest comment."""
    return _render_shim_template(
        record,
        metadata_lines=[_materialization_record_comment(record)],
    )


def _runtime_path(context: BuildContext, skill: str) -> Path:
    return context.output_root / RUNTIME_ROOT / skill / "SKILL.md"


def _legacy_generated_schema_matches(candidate: str, expected: str) -> bool:
    """Match a complete old template while treating old digests as history."""
    pieces = re.split(r"([0-9a-f]{64})", expected)
    pattern = "".join(
        r"[0-9a-f]{64}" if SHA256_RE.fullmatch(piece) else re.escape(piece)
        for piece in pieces
    )
    if re.fullmatch(pattern, candidate) is not None:
        return True

    # Catalog discovery metadata is part of the generated frontmatter, while
    # the adapter body remains the same canonical projection. Accept a
    # metadata-only migration so a catalog description change can be rebuilt by
    # this generator without treating the thin shim as hand-authored prose.
    frontmatter = re.compile(r"\A---\n(.*?)\n---\n", flags=re.DOTALL)
    candidate_match = frontmatter.match(candidate)
    expected_match = frontmatter.match(expected)
    if candidate_match is None or expected_match is None:
        return False
    try:
        candidate_metadata = yaml.safe_load(candidate_match.group(1))
        expected_metadata = yaml.safe_load(expected_match.group(1))
    except yaml.YAMLError:
        return False
    if not isinstance(candidate_metadata, Mapping) or not isinstance(expected_metadata, Mapping):
        return False
    if candidate_metadata.get("name") != expected_metadata.get("name"):
        return False

    def stable_body(value: str) -> str:
        value_match = frontmatter.match(value)
        if value_match is None:
            return ""
        body = value[value_match.end() :]
        normalized = re.sub(
            r'("record_digest":")[0-9a-f]{64}',
            r'\1<record-digest>',
            body,
        )
        return re.sub(r'("version":)\d+', r"\1<version>", normalized)

    return stable_body(candidate) == stable_body(expected)


def classify_legacy(
    context: BuildContext, skill: str, expected: str
) -> dict[str, object]:
    """Classify one existing target using only exact generated sections."""
    path = _runtime_path(context, skill)
    if not path.is_file():
        return {
            "skill_id": skill,
            "classification": "missing",
            "resolution": "migrated",
            "unmatched_blocks": [],
        }
    current = path.read_bytes()
    try:
        body = current.decode("utf-8")
    except UnicodeDecodeError:
        return {
            "skill_id": skill,
            "classification": "invalid_utf8",
            "resolution": "blocked",
            "unmatched_blocks": [
                {
                    "locator": path.relative_to(context.output_root).as_posix(),
                    "digest": hashlib.sha256(current).hexdigest(),
                }
            ],
        }
    if body == expected:
        return {
            "skill_id": skill,
            "classification": "generated",
            "resolution": "migrated",
            "unmatched_blocks": [],
        }
    if _legacy_generated_schema_matches(body, expected):
        return {
            "skill_id": skill,
            "classification": "generated_prior_schema",
            "resolution": "migrated",
            "unmatched_blocks": [],
        }
    legacy_sections = _markdown_sections(_markdown_body(body))
    unmatched_blocks: list[dict[str, str]] = []
    for locator, section in legacy_sections.items():
        unmatched_blocks.append(
            {
                "locator": f"{path.relative_to(context.output_root).as_posix()}#{locator}",
                "digest": hashlib.sha256(section.encode("utf-8")).hexdigest(),
            }
        )
    if not unmatched_blocks:
        unmatched_blocks.append(
            {
                "locator": path.relative_to(context.output_root).as_posix(),
                "digest": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            }
        )
    return {
        "skill_id": skill,
        "classification": "legacy_schema_mismatch",
        "resolution": "blocked",
        "accepted_sections": [],
        "unmatched_blocks": unmatched_blocks,
        "reviewer_ref": "design:skill-runtime-shim-materialization.md#Adapter-Only--Canonical-Prose-Handling",
    }


def _markdown_sections(text: str) -> dict[str, str]:
    """Return exact level-two sections with source line locators as keys."""
    lines = text.replace("\r\n", "\n").splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.startswith("## ")]
    sections: dict[str, str] = {}
    for offset, start in enumerate(starts):
        end = starts[offset + 1] if offset + 1 < len(starts) else len(lines)
        locator = f"L{start + 1}-L{end}"
        sections[locator] = "".join(lines[start:end])
    preamble_end = starts[0] if starts else len(lines)
    preamble = "".join(lines[:preamble_end]).strip()
    if preamble:
        sections["preamble"] = preamble + "\n"
    return sections


def _markdown_body(text: str) -> str:
    """Remove only the required top-level frontmatter before section matching."""
    match = re.match(r"\A---\n.*?\n---\n", text, flags=re.DOTALL)
    if match is None:
        return text
    return text[match.end() :]


def _projection_digest(skill: str, record: Mapping[str, object], content: bytes) -> str:
    return domain_digest(
        "agent-canon.skill-runtime-shim.projection.v1",
        {
            "skill_id": skill,
            "record_digest": _record_digest(record),
            "content_sha256": hashlib.sha256(content).hexdigest(),
        },
    )


def build_rows(
    context: BuildContext,
) -> tuple[dict[str, object], dict[str, str], dict[str, str]]:
    """Build all records and staged projections in catalog order."""
    records: dict[str, object] = {}
    rendered: dict[str, str] = {}
    projections: dict[str, str] = {}
    for skill in context.skill_ids:
        record = build_record(context, skill)
        content = render_shim(record)
        records[skill] = record
        rendered[skill] = content
        projections[skill] = _projection_digest(skill, record, content.encode("utf-8"))
    return records, rendered, projections


def _validate_materialization_record_comment(
    text: str, record: Mapping[str, object], skill: str
) -> None:
    """Require one exact comment bound to the rebuilt owner record."""
    expected = _materialization_record_comment(record)
    if text.count("<!-- materialization-record:") != 1 or text.count(expected) != 1:
        raise MaterializerError("materialization_record_mismatch", skill)


def readback_digest(
    context: BuildContext,
    records: Mapping[str, object],
    projections: Mapping[str, str],
) -> str:
    """Hash the catalog-sized actual target readback manifest."""
    rows: list[dict[str, str]] = []
    for skill in sorted(context.skill_ids):
        path = _runtime_path(context, skill)
        if not path.is_file():
            raise MaterializerError("readback_missing", skill)
        content = path.read_bytes()
        record = cast(Mapping[str, object], records[skill])
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MaterializerError("readback_invalid_utf8", skill) from exc
        _validate_materialization_record_comment(text, record, skill)
        expected = render_shim(record).encode("utf-8")
        if content != expected:
            raise MaterializerError("readback_mismatch", skill)
        rows.append(
            {
                "skill_id": skill,
                "content_sha256": hashlib.sha256(content).hexdigest(),
                "record_digest": _record_digest(record),
                "projection_digest": projections[skill],
            }
        )
    if len(rows) != len(context.skill_ids):
        raise MaterializerError("readback_count_mismatch", str(len(rows)))
    return domain_digest("agent-canon.skill-runtime-shim.readback.v1", rows)


def _staged_readback(context: BuildContext, rendered: Mapping[str, str]) -> None:
    for skill in context.skill_ids:
        data = rendered[skill].encode("utf-8")
        if data.decode("utf-8") != rendered[skill]:
            raise MaterializerError("staged_readback_decode", skill)
        if ABSOLUTE_LOCATOR_RE.search(rendered[skill]):
            raise MaterializerError("absolute_locator", skill)
        frontmatter = yaml.safe_load(rendered[skill].split("---", 2)[1])
        name = _mapping(frontmatter, f"{skill}.frontmatter").get("name")
        if name != skill:
            raise MaterializerError("staged_frontmatter_mismatch", skill)
        if rendered[skill].count("<!-- materialization-record:") != 1:
            raise MaterializerError("materialization_record_count", skill)
        if rendered[skill].count("skill_tool_commands.py show --skill") != 1:
            raise MaterializerError("command_packet_entry_count", skill)


def materialize(
    root: Path,
    *,
    all_skills: bool = False,
    image_build: bool = False,
    output_root: Path | None = None,
) -> dict[str, object]:
    """Materialize changed runtime targets using per-file temp+replace."""
    if not all_skills:
        raise MaterializerError("all_required")
    context = build_context(root, output_root=output_root)
    records, rendered, projections = build_rows(context)
    legacy = [
        classify_legacy(context, skill, rendered[skill]) for skill in context.skill_ids
    ]
    if any(cast(Sequence[object], row["unmatched_blocks"]) for row in legacy):
        raise LegacyMigrationError(legacy)
    _staged_readback(context, rendered)
    boundary, attestation = _parent_boundary(
        context.output_root, "skill-shim-materializer", image_build=image_build
    )
    delta_paths: list[str] = []
    replaced = 0
    for skill in sorted(context.skill_ids):
        path = _runtime_path(context, skill)
        data = rendered[skill].encode("utf-8")
        target = boundary.resolve_parent_owned_path(
            attestation, path, "skill-shim-materializer", create=False
        )
        before = (
            boundary.read_parent_owned_file(target)
            if target.target_dev is not None
            else None
        )
        current_mode = (
            target.physical_path.stat().st_mode & 0o777
            if target.target_dev is not None
            else None
        )
        if before == data and current_mode == 0o644:
            continue
        try:
            # Reuse the already authenticated target receipt.  Calling the
            # convenience writer here would resolve the same path a second
            # time for every file, repeating component/identity checks and
            # creating an avoidable per-file attestation window.
            boundary.atomic_publish(target, data, mode=0o644)
            replaced += 1
            delta_paths.append(path.relative_to(context.output_root).as_posix())
        except OSError as exc:
            raise PartialStopError(
                path.relative_to(context.output_root).as_posix(), replaced
            ) from exc
    readback = readback_digest(
        context, cast(Mapping[str, object], records), projections
    )
    return {
        "schema": "agent_canon.skill_runtime_shim.materialize",
        "version": VERSION,
        "source_snapshot_digest": context.source_snapshot_digest,
        "record_digests": {
            skill: _record_digest(cast(Mapping[str, object], records[skill]))
            for skill in sorted(context.skill_ids)
        },
        "projection_digests": {
            skill: projections[skill] for skill in sorted(context.skill_ids)
        },
        "readback_digest": readback,
        "content_delta_count": len(delta_paths),
        "content_delta_paths": sorted(delta_paths),
        "legacy_resolution_count": len(legacy),
        "legacy_migration_receipt": legacy,
        "replaced_count": replaced,
        "status": "pass",
    }


def readback(
    root: Path, *, all_skills: bool = False, output_root: Path | None = None
) -> dict[str, object]:
    """Read back every generated target without writing any file."""
    if not all_skills:
        raise MaterializerError("all_required")
    context = build_context(root, output_root=output_root)
    records, rendered, projections = build_rows(context)
    _staged_readback(context, rendered)
    digest = readback_digest(context, cast(Mapping[str, object], records), projections)
    return {
        "schema": "agent_canon.skill_runtime_shim.readback",
        "version": VERSION,
        "source_snapshot_digest": context.source_snapshot_digest,
        "record_digests": {
            skill: _record_digest(cast(Mapping[str, object], records[skill]))
            for skill in sorted(context.skill_ids)
        },
        "projection_digests": {
            skill: projections[skill] for skill in sorted(context.skill_ids)
        },
        "readback_digest": digest,
        "readback_count": len(context.skill_ids),
        "status": "pass",
    }


def check(
    root: Path, *, all_skills: bool = False, output_root: Path | None = None
) -> dict[str, object]:
    """Check staged bytes and actual readback, reporting drift without writing."""
    if not all_skills:
        raise MaterializerError("all_required")
    context = build_context(root, output_root=output_root)
    records, rendered, projections = build_rows(context)
    _staged_readback(context, rendered)
    drift: list[str] = []
    for skill in context.skill_ids:
        path = _runtime_path(context, skill)
        if not path.is_file() or path.read_bytes() != rendered[skill].encode("utf-8"):
            drift.append(path.relative_to(context.output_root).as_posix())
    payload: dict[str, object] = {
        "schema": "agent_canon.skill_runtime_shim.check",
        "version": VERSION,
        "source_snapshot_digest": context.source_snapshot_digest,
        "record_digests": {
            skill: _record_digest(cast(Mapping[str, object], records[skill]))
            for skill in sorted(context.skill_ids)
        },
        "projection_digests": {
            skill: projections[skill] for skill in sorted(context.skill_ids)
        },
        "content_delta_count": len(drift),
        "content_delta_paths": sorted(drift),
        "status": "pass" if not drift else "fail",
    }
    return payload


def fixed_point_acceptance(root: Path) -> dict[str, object]:
    """Run the materializer twice and return the exact fixed-point acceptance record."""
    first = materialize(root, all_skills=True)
    second = materialize(root, all_skills=True)
    equal_records = first["record_digests"] == second["record_digests"]
    equal_projections = first["projection_digests"] == second["projection_digests"]
    equal_readback = first["readback_digest"] == second["readback_digest"]
    status = (
        "pass"
        if equal_records
        and equal_projections
        and equal_readback
        and second["content_delta_count"] == 0
        and second["content_delta_paths"] == []
        else "fail"
    )
    return {
        "schema": FIXED_POINT_SCHEMA,
        "version": VERSION,
        "source_snapshot_digest": first["source_snapshot_digest"],
        "first_run": {
            "record_digests": first["record_digests"],
            "projection_digests": first["projection_digests"],
            "readback_digest": first["readback_digest"],
            "content_delta_count": first["content_delta_count"],
            "content_delta_paths": first["content_delta_paths"],
        },
        "second_run": {
            "record_digests": second["record_digests"],
            "projection_digests": second["projection_digests"],
            "readback_digest": second["readback_digest"],
            "content_delta_count": second["content_delta_count"],
            "content_delta_paths": second["content_delta_paths"],
        },
        "equal_record_digests": equal_records,
        "equal_projection_digests": equal_projections,
        "equal_readback_digest": equal_readback,
        "status": status,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the materializer command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "materialize", "readback"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--image-build",
        action="store_true",
        help="Materialize into an ephemeral Docker image layer.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="Write the generated view below this staging root instead of the source root.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _print_payload(payload: Mapping[str, object], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"SKILL_SHIM_MATERIALIZER_SCHEMA={payload['schema']}")
    print(f"SKILL_SHIM_MATERIALIZER_STATUS={payload['status']}")
    for key in ("source_snapshot_digest", "content_delta_count", "readback_digest"):
        if key in payload:
            print(f"SKILL_SHIM_MATERIALIZER_{key.upper()}={payload[key]}")
    if payload.get("content_delta_paths"):
        for path in cast(Sequence[str], payload["content_delta_paths"]):
            print(f"SKILL_SHIM_MATERIALIZER_DELTA={path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected materializer operation."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "materialize":
            payload = materialize(
                args.root,
                all_skills=args.all,
                image_build=args.image_build,
                output_root=args.output_root,
            )
        elif args.image_build:
            raise MaterializerError("image_build_materialize_only")
        elif args.command == "readback":
            payload = readback(
                args.root, all_skills=args.all, output_root=args.output_root
            )
        else:
            payload = check(
                args.root, all_skills=args.all, output_root=args.output_root
            )
    except LegacyMigrationError as exc:
        print(
            "SKILL_SHIM_MATERIALIZER_LEGACY_RECEIPT="
            + json.dumps(exc.receipt, ensure_ascii=False, sort_keys=True)
        )
        print(f"SKILL_SHIM_MATERIALIZER_FAILURE={exc.code}:{exc.detail}")
        return 2
    except PartialStopError as exc:
        print(f"SKILL_SHIM_MATERIALIZER_FAILURE={exc.code}:{exc.detail}")
        return 2
    except MaterializerError as exc:
        print(f"SKILL_SHIM_MATERIALIZER_FAILURE={exc.code}:{exc.detail}")
        return 2
    _print_payload(payload, args.format)
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
