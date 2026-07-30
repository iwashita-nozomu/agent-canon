#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Materializes and reads back the complete public Codex skill-shim adapter set.
# upstream design ../../documents/design/skill-runtime-shim-materialization.md owns the v1 schema, migration, and fixed-point contract
# upstream design ../../agents/skills/catalog.yaml owns public skill identity, discovery metadata, and command phases
# upstream implementation ./skill_route_catalog.py owns typed route and dependency projections
# upstream implementation ./skill_dependency_map.py owns graph/tool identity projections
# upstream implementation ./skill_tool_commands.py owns read-only command packets
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
import tempfile
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]

import yaml

from agent_canon_source_root import resolve_agent_canon_source_root
from check_skill_frontmatter import parse_frontmatter
from skill_dependency_map import build_graph
from skill_route_catalog import (
    SkillDependencyRule,
    SkillRoutingRule,
    load_skill_catalog,
    load_skill_dependency_map,
    load_skill_route_rules,
)
from skill_tool_commands import SkillCommandPacket, packet_for_skill

SCHEMA = "agent_canon.skill_runtime_shim"
VERSION = 1
FIXED_POINT_SCHEMA = "agent_canon.skill_runtime_shim.fixed_point"
MATERIALIZER_ID = "skill_shim_materializer.v1"
TEMPLATE_ID = "skill-runtime-shim-md-v1"
COMMAND_PACKET_TEMPLATE_ID = "skill-tool-command-packet-v2"
RUNTIME_ROOT = Path(".agents/skills")
CATALOG_PATH = Path("agents/skills/catalog.yaml")
DEPENDENCY_PATH = Path("agents/skills/skill-dependencies.yaml")
CONFIG_PATH = Path(".codex/config.toml")
GRAPH_PATH = Path("documents/runtime/skill-dependency-graph.json")
SKILL_COUNT = 60
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ABSOLUTE_LOCATOR_RE = re.compile(
    r"(?<![A-Za-z0-9._~/<>-])/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+"
)


class MaterializerError(RuntimeError):
    """One stable fail-closed materializer error."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        message = code if not detail else f"{code}:{detail}"
        super().__init__(message)


class PartialStopError(MaterializerError):
    """A per-file replace stopped after a partial runtime update."""

    def __init__(self, path: str, replaced: int) -> None:
        super().__init__("partial_stop", f"path={path}:replaced={replaced}")
        self.path = path
        self.replaced = replaced


@dataclass(frozen=True)
class HostEntry:
    """One read-only host skill configuration entry."""

    path: str
    enabled: bool
    index: int
    order: int
    digest: str


@dataclass(frozen=True)
class BuildContext:
    """All canonical inputs used by one materialization run."""

    root: Path
    skill_ids: tuple[str, ...]
    catalog_entries: Mapping[str, Mapping[str, object]]
    host_entries: Mapping[str, HostEntry]
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
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
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
    return hashlib.sha256(domain.encode("utf-8") + b"\0" + canonical_json_bytes(value)).hexdigest()


def file_digest(path: Path) -> str:
    """Hash source bytes exactly as stored."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise MaterializerError("invalid_mapping", field)
    return cast(Mapping[str, object], value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MaterializerError("invalid_string", field)
    return _normalize_string(value)


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise MaterializerError("invalid_boolean", field)
    return value


def _catalog_entries(root: Path) -> tuple[tuple[str, ...], dict[str, Mapping[str, object]]]:
    """Load the public catalog and require the complete 60-row discovery source."""
    data = load_skill_catalog(root)
    families = data.get("skill_families")
    if not isinstance(families, list):
        raise MaterializerError("catalog_invalid", "skill_families")
    ids: list[str] = []
    entries: dict[str, Mapping[str, object]] = {}
    for index, raw in enumerate(families):
        entry = _mapping(raw, f"skill_families[{index}]")
        skill = _string(entry.get("id"), f"skill_families[{index}].id")
        _normalize_string(skill, identifier=True)
        if skill in entries:
            raise MaterializerError("catalog_duplicate", skill)
        discovery = _mapping(entry.get("discovery"), f"{skill}.discovery")
        discovery_name = _string(discovery.get("name"), f"{skill}.discovery.name")
        discovery_description = _string(
            discovery.get("description"), f"{skill}.discovery.description"
        )
        if discovery_name != skill:
            raise MaterializerError("discovery_name_mismatch", skill)
        if not isinstance(discovery_description, str):
            raise MaterializerError("discovery_description_invalid", skill)
        ids.append(skill)
        entries[skill] = entry
    if len(ids) != SKILL_COUNT:
        raise MaterializerError("catalog_count_mismatch", str(len(ids)))
    return tuple(ids), entries


def _host_entries(root: Path, skill_ids: Sequence[str]) -> dict[str, HostEntry]:
    """Read host config order/path/enabled state without rewriting config."""
    try:
        raw = tomllib.loads((root / CONFIG_PATH).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise MaterializerError("host_config_unavailable", str(exc)) from exc
    skills = _mapping(raw.get("skills"), "skills")
    entries = skills.get("config")
    if not isinstance(entries, list):
        raise MaterializerError("host_config_invalid", "skills.config")
    observed: dict[str, HostEntry] = {}
    for index, raw_entry in enumerate(entries):
        entry = _mapping(raw_entry, f"skills.config[{index}]")
        path = _string(entry.get("path"), f"skills.config[{index}].path")
        enabled = _bool(entry.get("enabled"), f"skills.config[{index}].enabled")
        path_parts = Path(path).as_posix().split("/")
        if len(path_parts) < 3 or path_parts[-1] != "SKILL.md" or path_parts[-3] != "skills":
            raise MaterializerError("host_config_path_mismatch", path)
        skill = path_parts[-2]
        if skill in observed:
            raise MaterializerError("host_config_duplicate", skill)
        entry_digest = domain_digest(
            "agent-canon.host-config-entry.v1", {"path": path, "enabled": enabled}
        )
        observed[skill] = HostEntry(path, enabled, index, index, entry_digest)
    if tuple(observed) != tuple(skill_ids) and set(observed) != set(skill_ids):
        raise MaterializerError("host_config_skill_set_mismatch")
    if set(observed) != set(skill_ids) or len(observed) != SKILL_COUNT:
        raise MaterializerError("host_config_count_mismatch", str(len(observed)))
    return observed


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
            rows = []
            for logical, source_root, execution_cwd, argv in value:
                resolved_argv = []
                for token in argv:
                    token_path = Path(token)
                    if token_path.is_absolute():
                        try:
                            token = "@root/" + token_path.resolve().relative_to(root.resolve()).as_posix()
                        except ValueError:
                            token = "@absolute"
                    resolved_argv.append(token)
                rows.append([logical, "@root", "@root", resolved_argv])
            result[field] = rows
        elif isinstance(value, tuple):
            result[field] = list(value)
        else:
            result[field] = value
    return result


def _graph_refs(graph: Mapping[str, object], skill: str) -> tuple[dict[str, object], str]:
    """Return typed graph refs and their per-skill tool-surface digest."""
    skill_rows = cast(Sequence[Mapping[str, object]], graph["skills"])
    skill_row = next((row for row in skill_rows if row["display_label"] == skill), None)
    if skill_row is None:
        raise MaterializerError("graph_skill_missing", skill)
    skill_ref = cast(Mapping[str, str], skill_row["ref"])
    command_ids = {
        cast(str, item)
        for record in cast(Sequence[Mapping[str, object]], graph["identity_records"])
        if record["id"] == skill_ref["id"]
        for item in cast(Mapping[str, object], record["canonical_payload"])["command_ids"]
    }
    tool_refs: dict[str, Mapping[str, str]] = {}
    for edge in cast(Sequence[Mapping[str, object]], graph["edges"]):
        if edge["display_label"] != "tool-resolution":
            continue
        source = cast(Mapping[str, str], edge["source_ref"])
        if source["id"] not in command_ids:
            continue
        target = cast(Mapping[str, str], edge["target_ref"])
        tool_refs[target["id"]] = target
    toolcall_refs = [
        cast(Mapping[str, str], row["ref"])
        for row in cast(Sequence[Mapping[str, object]], graph["toolcalls"])
    ]
    argument_schema = {
        "id": "agent-canon.skill-tool-commands.args.v1",
        "digest": domain_digest(
            "agent-canon.skill-runtime-shim.owner.argument-schema.v1",
            {
                "$id": "agent-canon.skill-tool-commands.args.v1",
                "type": "object",
                "required": ["skill", "format"],
                "properties": {
                    "skill": {"type": "string", "minLength": 1},
                    "format": {"type": "string", "enum": ["json"]},
                },
                "additionalProperties": False,
            },
        ),
    }
    refs = {
        "skill_ref": dict(skill_ref),
        "tool_refs": [dict(tool_refs[key]) for key in sorted(tool_refs)],
        "toolcall_refs": [dict(ref) for ref in toolcall_refs],
        "argument_schema_refs": [argument_schema],
    }
    return refs, domain_digest(
        "agent-canon.skill-runtime-shim.owner.tool-surface.v1", refs
    )


def _source_snapshot_digest(root: Path, graph: Mapping[str, object], skill_ids: Sequence[str]) -> str:
    """Hash only immutable sources so runtime target replacement cannot perturb fixed point."""
    files = {
        "catalog": file_digest(root / CATALOG_PATH),
        "dependencies": file_digest(root / DEPENDENCY_PATH),
        "config": file_digest(root / CONFIG_PATH),
        "reader": file_digest(root / "agents/canonical/skills.md"),
        "graph": cast(str, graph["graph_digest"]),
    }
    files["canonical_docs"] = domain_digest(
        "agent-canon.skill-runtime-shim.canonical-docs.v1",
        {skill: file_digest(root / "agents/skills" / f"{skill}.md") for skill in skill_ids},
    )
    return domain_digest("agent-canon.skill-runtime-shim.source-snapshot.v1", files)


def build_context(root: Path) -> BuildContext:
    """Load and validate the complete canonical input universe."""
    root = root.resolve()
    skill_ids, entries = _catalog_entries(root)
    hosts = _host_entries(root, skill_ids)
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
    if len(packets) != SKILL_COUNT:
        raise MaterializerError("command_packet_count_mismatch", str(len(packets)))
    return BuildContext(
        root,
        skill_ids,
        entries,
        hosts,
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
    """Build one fixed-order v1 SkillRuntimeShimRecord."""
    entry = context.catalog_entries[skill]
    name, description = _catalog_discovery(entry)
    host = context.host_entries[skill]
    canonical_doc = _string(entry.get("canonical_doc"), f"{skill}.canonical_doc")
    shim_path = _string(entry.get("shim"), f"{skill}.shim")
    if shim_path != f".agents/skills/{skill}/SKILL.md":
        raise MaterializerError("shim_path_mismatch", skill)
    if canonical_doc != f"agents/skills/{skill}.md":
        raise MaterializerError("canonical_doc_mismatch", skill)
    canonical_path = context.root / canonical_doc
    if not canonical_path.is_file():
        raise MaterializerError("missing_canonical_doc", skill)
    graph_refs, tool_surface_digest = _graph_refs(context.graph, skill)
    packet = context.packets[skill]
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
            "host_config_path": host.path,
            "host_config_index": host.index,
            "host_config_order": host.order,
            "host_enabled": host.enabled,
            "host_config_entry_digest": host.digest,
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
    # The typed graph refs are intentionally consumed only while building the digest;
    # payloads never enter the generated Markdown adapter.
    if not graph_refs["argument_schema_refs"]:
        raise MaterializerError("argument_schema_missing", skill)
    record_digest = domain_digest(
        "agent-canon.skill-runtime-shim.record.v1", record
    )
    cast(dict[str, object], record["provenance"])["record_digest"] = record_digest
    return record


def _record_digest(record: Mapping[str, object]) -> str:
    return cast(str, cast(Mapping[str, object], record["provenance"])["record_digest"])


def render_shim(record: Mapping[str, object]) -> str:
    """Render the exact adapter-only Markdown template."""
    discovery = cast(Mapping[str, object], record["discovery"])
    owner = cast(Mapping[str, object], record["owner"])
    identity = cast(Mapping[str, object], record["identity"])
    provenance = cast(Mapping[str, object], record["provenance"])
    skill = cast(str, record["skill_id"])
    description = json.dumps(cast(str, discovery["description"]), ensure_ascii=False)
    canonical_doc = cast(str, owner["canonical_doc"])
    canonical_link = posixpath.relpath(canonical_doc, f".agents/skills/{skill}")
    lines = [
        "---",
        f"name: {discovery['name']}",
        f"description: {description}",
        "---",
        "<!-- generated: agent_canon.skill_runtime_shim.v1 -->",
        f"<!-- source: {owner['catalog_ref']} -->",
        f"<!-- canonical: {canonical_doc} sha256={provenance['canonical_doc_digest']} -->",
        f"<!-- route: {owner['route_ref']} digest={identity['route_identity_digest']} -->",
        f"<!-- dependencies: {owner['dependency_ref']} digest={identity['dependency_identity_digest']} -->",
        f"<!-- commands: {owner['command_ref']} digest={identity['command_packet_identity_digest']} -->",
        f"<!-- materializer: {provenance['materializer_id']} -->",
        "",
        "<!--",
        "@dependency-start",
        "contract reference",
        f"upstream implementation ../../../{canonical_doc}",
        "@dependency-end",
        "-->",
        "",
        f"# {skill}",
        "",
        "## Canonical Skill",
        "",
        f"Canonical workflow and policy: [{skill}]({canonical_link}).",
        "Read that owner before applying the skill. This file is only the Codex discovery",
        "adapter; it does not restate the canonical skill prose.",
        "",
        "## Tool Commands",
        "",
        "<!-- skill-tool-commands:start -->",
        f"Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill {skill} --format text`; "
        f"schema `skill_tool_commands.v2`, digest: `{identity['command_packet_identity_digest']}`.",
        "<!-- skill-tool-commands:end -->",
        "",
        "1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.",
        "",
    ]
    text = "\n".join(lines)
    if ABSOLUTE_LOCATOR_RE.search(text):
        raise MaterializerError("absolute_locator", skill)
    return text


def _runtime_path(context: BuildContext, skill: str) -> Path:
    return context.root / RUNTIME_ROOT / skill / "SKILL.md"


def classify_legacy(context: BuildContext, skill: str, expected: str) -> dict[str, object]:
    """Classify one existing target without routing from its prose."""
    path = _runtime_path(context, skill)
    if not path.is_file():
        return {"skill_id": skill, "classification": "missing", "resolution": "blocked"}
    current = path.read_bytes()
    if current.decode("utf-8") == expected:
        return {"skill_id": skill, "classification": "generated", "resolution": "migrated"}
    frontmatter, error = parse_frontmatter(path)
    if error or frontmatter is None:
        raise MaterializerError("unresolved_legacy_block", f"{skill}:{error or 'frontmatter'}")
    name, description = _catalog_discovery(context.catalog_entries[skill])
    if frontmatter.get("name") != name or frontmatter.get("description") != description:
        raise MaterializerError("frontmatter_drift", skill)
    body = current.decode("utf-8")
    canonical_doc = f"agents/skills/{skill}.md"
    canonical_ref_match = re.search(
        rf"(?:\.\./)*agents/skills/{re.escape(skill)}\.md", body
    )
    canonical_path = context.root / canonical_doc
    if canonical_ref_match is None and canonical_path.is_file():
        canonical_lines = canonical_path.read_text(encoding="utf-8").splitlines()
        heading = next(
            (index for index, line in enumerate(canonical_lines, start=1) if line.startswith("# ")),
            None,
        )
        if heading is not None:
            canonical_match_refs = [f"{canonical_doc}:L{heading}"]
        else:
            canonical_match_refs = []
    elif canonical_ref_match is not None:
        canonical_match_refs = [canonical_ref_match.group(0)]
    else:
        canonical_match_refs = []
    if not canonical_match_refs:
        raise MaterializerError("unresolved_legacy_block", skill)
    return {
        "skill_id": skill,
        "block_locator": f"{skill}:body",
        "legacy_body_digest": hashlib.sha256(current).hexdigest(),
        "normalized_block_digest": hashlib.sha256(body.replace("\r\n", "\n").encode()).hexdigest(),
        "canonical_owner_ref": f"{CATALOG_PATH.as_posix()}#skill:{skill}.canonical_doc",
        "canonical_match_refs": canonical_match_refs,
        "unmatched_block_digest": hashlib.sha256(current).hexdigest(),
        "classification": "legacy_canonical_prose",
        "resolution": "migrated",
        "reviewer_ref": "design:skill-runtime-shim-materialization.md#Adapter-Only--Canonical-Prose-Handling",
    }


def _projection_digest(skill: str, record: Mapping[str, object], content: bytes) -> str:
    return domain_digest(
        "agent-canon.skill-runtime-shim.projection.v1",
        {"skill_id": skill, "record_digest": _record_digest(record), "content_sha256": hashlib.sha256(content).hexdigest()},
    )


def build_rows(context: BuildContext) -> tuple[dict[str, object], dict[str, str], dict[str, str]]:
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


def readback_digest(
    context: BuildContext,
    records: Mapping[str, object],
    projections: Mapping[str, str],
) -> str:
    """Hash the 60-row actual target readback manifest."""
    rows = []
    for skill in sorted(context.skill_ids):
        path = _runtime_path(context, skill)
        if not path.is_file():
            raise MaterializerError("readback_missing", skill)
        content = path.read_bytes()
        expected = render_shim(cast(Mapping[str, object], records[skill])).encode("utf-8")
        if content != expected:
            raise MaterializerError("readback_mismatch", skill)
        rows.append(
            {
                "skill_id": skill,
                "content_sha256": hashlib.sha256(content).hexdigest(),
                "record_digest": _record_digest(cast(Mapping[str, object], records[skill])),
                "projection_digest": projections[skill],
            }
        )
    if len(rows) != SKILL_COUNT:
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
        if rendered[skill].count("skill_tool_commands.py show --skill") != 1:
            raise MaterializerError("command_packet_entry_count", skill)


def materialize(root: Path, *, all_skills: bool = False) -> dict[str, object]:
    """Materialize changed runtime targets using per-file temp+replace."""
    if not all_skills:
        raise MaterializerError("all_required")
    context = build_context(root)
    records, rendered, projections = build_rows(context)
    legacy = [classify_legacy(context, skill, rendered[skill]) for skill in context.skill_ids]
    _staged_readback(context, rendered)
    delta_paths: list[str] = []
    replaced = 0
    for skill in sorted(context.skill_ids):
        path = _runtime_path(context, skill)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = rendered[skill].encode("utf-8")
        before = path.read_bytes() if path.is_file() else None
        if before == data:
            continue
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=".SKILL.md.", suffix=".tmp", delete=False
            ) as handle:
                temporary = handle.name
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
            replaced += 1
            delta_paths.append(path.relative_to(context.root).as_posix())
        except OSError as exc:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
            raise PartialStopError(path.relative_to(context.root).as_posix(), replaced) from exc
    readback = readback_digest(context, cast(Mapping[str, object], records), projections)
    return {
        "schema": "agent_canon.skill_runtime_shim.materialize",
        "version": VERSION,
        "source_snapshot_digest": context.source_snapshot_digest,
        "record_digests": {skill: _record_digest(cast(Mapping[str, object], records[skill])) for skill in sorted(context.skill_ids)},
        "projection_digests": {skill: projections[skill] for skill in sorted(context.skill_ids)},
        "readback_digest": readback,
        "content_delta_count": len(delta_paths),
        "content_delta_paths": sorted(delta_paths),
        "legacy_resolution_count": len(legacy),
        "replaced_count": replaced,
        "status": "pass",
    }


def readback(root: Path, *, all_skills: bool = False) -> dict[str, object]:
    """Read back every generated target without writing any file."""
    if not all_skills:
        raise MaterializerError("all_required")
    context = build_context(root)
    records, rendered, projections = build_rows(context)
    _staged_readback(context, rendered)
    digest = readback_digest(context, cast(Mapping[str, object], records), projections)
    return {
        "schema": "agent_canon.skill_runtime_shim.readback",
        "version": VERSION,
        "source_snapshot_digest": context.source_snapshot_digest,
        "record_digests": {skill: _record_digest(cast(Mapping[str, object], records[skill])) for skill in sorted(context.skill_ids)},
        "projection_digests": {skill: projections[skill] for skill in sorted(context.skill_ids)},
        "readback_digest": digest,
        "readback_count": SKILL_COUNT,
        "status": "pass",
    }


def check(root: Path, *, all_skills: bool = False) -> dict[str, object]:
    """Check staged bytes and actual readback, reporting drift without writing."""
    if not all_skills:
        raise MaterializerError("all_required")
    context = build_context(root)
    records, rendered, projections = build_rows(context)
    _staged_readback(context, rendered)
    drift = []
    for skill in context.skill_ids:
        path = _runtime_path(context, skill)
        if not path.is_file() or path.read_bytes() != rendered[skill].encode("utf-8"):
            drift.append(path.relative_to(context.root).as_posix())
    payload: dict[str, object] = {
        "schema": "agent_canon.skill_runtime_shim.check",
        "version": VERSION,
        "source_snapshot_digest": context.source_snapshot_digest,
        "record_digests": {skill: _record_digest(cast(Mapping[str, object], records[skill])) for skill in sorted(context.skill_ids)},
        "projection_digests": {skill: projections[skill] for skill in sorted(context.skill_ids)},
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "materialize", "readback"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--all", action="store_true")
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
    args = build_parser().parse_args(argv)
    try:
        if args.command == "materialize":
            payload = materialize(args.root, all_skills=args.all)
        elif args.command == "readback":
            payload = readback(args.root, all_skills=args.all)
        else:
            payload = check(args.root, all_skills=args.all)
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
