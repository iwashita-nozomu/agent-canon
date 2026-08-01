#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Materializes and validates the complete typed public skill/tool invocation graph.
# upstream design ../../agents/skills/catalog.yaml owns public skill identity and command phases
# upstream design ../../agents/skills/skill-dependencies.yaml owns skill relations and invocation order
# upstream design ../../tools/catalog.yaml owns canonical ToolIDs
# upstream design ../../documents/design/skill-tool-invocation-graph.md owns the v2 schema and digest rules
# upstream implementation ./skill_tool_commands.py resolves command packets and execution argv
# upstream implementation ./skill_route_catalog.py owns typed visualization owner/adapter routing
# downstream implementation ../../documents/runtime/skill-dependency-graph.md is generated Mermaid
# downstream implementation ../../documents/runtime/skill-dependency-graph.json is generated machine graph
# downstream implementation ./check_skill_tool_invocation_graph.py is the public checker entrypoint
# downstream implementation ../../tests/agent_tools/test_skill_dependency_map.py checks graph completeness
# @dependency-end
"""Materialize and validate the deterministic public skill/tool graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import yaml
from agent_canon_source_root import resolve_agent_canon_source_root
from skill_route_catalog import (
    SKILL_DEPENDENCY_MAP_PATH,
    VISUALIZATION_ADAPTER_TOOL_IDS,
    VISUALIZATION_DEPENDENCY_ADAPTER_ARGUMENT_SCHEMA,
    VISUALIZATION_DEPENDENCY_ADAPTER_TOOL_ID,
    VISUALIZATION_OWNER_ARGUMENT_SCHEMA,
    VISUALIZATION_OWNER_TOOL_ID,
    SkillDependencyRule,
    build_visualization_adapter_tool_call,
    build_visualization_owner_tool_call,
    derive_skill_invocation_order,
    load_skill_catalog,
    load_skill_dependency_map,
    load_skill_route_rules,
)
from skill_tool_commands import SkillCommandPacket, packet_for_skill
from visualization_contract import (
    TOOL_ARGUMENT_SCHEMAS,
    VisualizationSourceItem,
    build_source_universe,
    serialize_tool_call,
)

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH_PATH = Path("documents/runtime/skill-dependency-graph.md")
DEFAULT_JSON_PATH = Path("documents/runtime/skill-dependency-graph.json")
GRAPH_SCHEMA = "agent_canon.skill_tool_invocation_graph.v2"
CHECK_SCHEMA = "agent_canon.skill_tool_invocation_check.v1"
GRAPH_ARTIFACT_ID = "skill-tool-invocation-graph"
GRAPH_RENDERER_ID = VISUALIZATION_DEPENDENCY_ADAPTER_TOOL_ID
PHASES = ("required", "conditional", "maintenance")
EDGE_TYPES = (
    "prerequisite",
    "successor",
    "order",
    "routing",
    "parallel",
    "invocation",
    "tool-resolution",
)
DESIGN_LOCATOR = "documents/design/skill-tool-invocation-graph.md"
DESIGN_CLAUSE_IDS = tuple(f"SG-{index:03d}" for index in range(1, 16))
DIC_CLAUSE_IDS = tuple(f"DIC-{index:03d}" for index in range(1, 10))
IMPLEMENTATION_TRACE_PATHS = (
    "agents/skills/catalog.yaml",
    "documents/design/skill-tool-invocation-graph.md",
    "documents/runtime/skill-dependency-graph.json",
    "documents/runtime/skill-dependency-graph.md",
    "tests/agent_tools/test_route.py",
    "tests/agent_tools/test_skill_dependency_map.py",
    "tools/agent_tools/check_skill_tool_invocation_graph.py",
    "tools/agent_tools/capability_route.py",
    "tools/agent_tools/route.py",
    "tools/agent_tools/skill_dependency_map.py",
    "tools/agent_tools/skill_route_catalog.py",
)
SOURCE_KINDS = (
    "identity",
    "edge",
    "field",
    "phase",
    "branch",
    "module",
    "evidence",
    "time",
)
IDENTITY_KINDS = (
    "skill",
    "phase",
    "command",
    "tool",
    "capability",
    "toolcall",
    "edge",
    "source",
    "manifest",
    "coverage",
    "readback",
)
GRAPH_HEADER = "<!-- Generated from the typed skill/tool invocation graph; do not edit by hand. -->"
GRAPH_DEPENDENCY_HEADER = """<!--
@dependency-start
contract reference
responsibility Publishes the generated public skill/tool invocation graph as the canonical Mermaid reader surface.
upstream design ../../documents/design/skill-tool-invocation-graph.md owns the graph universe, serialization, and readback contract
upstream implementation ../../tools/agent_tools/skill_dependency_map.py materializes the typed graph and renders the Mermaid projection
downstream implementation ../../tools/agent_tools/check_skill_tool_invocation_graph.py validates source/artifact equality and actual Mermaid syntax readback
downstream implementation ../../tests/agent_tools/test_skill_dependency_map.py covers completeness, determinism, and stale-artifact failures
@dependency-end
-->"""
MERMAID_HEADER_RE = re.compile(
    r"^<!-- graph_digest=([0-9a-f]{64}) coverage_digest=([0-9a-f]{64}) -->$"
)
MERMAID_KV_RE = re.compile(r"([a-z_]+)=([^ ]+)")
MERMAID_NODE_RE = re.compile(
    r'^\s+(n_[A-Za-z0-9_]+)(?:\[\["(.*)"\]\]|\["(.*)"\]|\{"(.*)"\})$'
)
MERMAID_EDGE_RE = re.compile(
    r'^\s+(n_[A-Za-z0-9_]+)\s+(-\.->|-->)\|"(.*)"\|\s+(n_[A-Za-z0-9_]+)$'
)
MERMAID_REF_LABEL_RE = re.compile(r"^(.*) \(ref=([0-9a-f]{64})\)$")
MERMAID_ORDERED_LABEL_RE = re.compile(r"^(.*) \(order=([0-9]+); ref=([0-9a-f]{64})\)$")

_IDENTIFIER_FIELDS = frozenset(
    {
        "adapter_id",
        "alias",
        "alias_of",
        "argument_schema_id",
        "capability_id",
        "edge_id",
        "id",
        "kind",
        "owner_id",
        "phase_id",
        "schema",
        "skill_id",
        "source_id",
        "target_id",
        "tool_id",
    }
)


class GraphIdentityError(ValueError):
    """Base class for typed identity/preimage failures."""

    def __init__(self, code: str, detail: str) -> None:
        """Initialize a machine-readable identity failure."""
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}")


class GraphIdentityCollisionError(GraphIdentityError):
    """Same kind/id was presented with a different canonical preimage."""

    def __init__(self, detail: str) -> None:
        """Initialize an identity collision."""
        super().__init__("identity_collision", detail)


class GraphDigestCollisionError(GraphIdentityError):
    """One digest was assigned to different canonical preimages."""

    def __init__(self, detail: str) -> None:
        """Initialize a digest collision."""
        super().__init__("digest_collision", detail)


class GraphDigestMismatchError(GraphIdentityError):
    """A reference or identity record has an invalid digest."""

    def __init__(self, detail: str) -> None:
        """Initialize a digest mismatch."""
        super().__init__("digest_mismatch", detail)


def _normalize_identifier(value: str) -> str:
    """Apply the approved NFKC/casefold identifier normalization."""
    if not isinstance(value, str):
        raise TypeError("identifier must be a string")
    return unicodedata.normalize("NFKC", value).casefold()


def _canonicalize(value: object, field: str | None = None) -> object:
    """Normalize display text and identifiers recursively before sorting maps."""
    if isinstance(value, str):
        if field in _IDENTIFIER_FIELDS:
            return _normalize_identifier(value)
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        return {
            unicodedata.normalize("NFC", str(key)): _canonicalize(item, str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_canonicalize(item, field) for item in value]
    if isinstance(value, tuple):
        return [_canonicalize(item, field) for item in value]
    return value


def _canonical_bytes(value: object) -> bytes:
    """Serialize compact UTF-8 bytes with recursively sorted mapping keys."""
    return json.dumps(
        _canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_json(value: object) -> str:
    """Serialize one compact canonical JSON value."""
    return _canonical_bytes(value).decode("utf-8")


def _digest(value: object) -> str:
    """Return a deterministic SHA-256 digest for one JSON value."""
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _identity_preimage(identity_id: str, kind: str, payload: object) -> bytes:
    """Build the SG-004 identity preimage exactly."""
    return b"\x00".join(
        (
            b"agent-canon",
            b"skill-tool-invocation-graph.v2",
            _normalize_identifier(identity_id).encode("utf-8"),
            _normalize_identifier(kind).encode("utf-8"),
            _canonical_bytes(payload),
        )
    )


def _identity_digest(identity_id: str, kind: str, payload: object) -> str:
    """Hash an identity preimage, excluding the digest field itself."""
    return hashlib.sha256(_identity_preimage(identity_id, kind, payload)).hexdigest()


def _ref(record: Mapping[str, object]) -> dict[str, str]:
    """Return only the stable reference part of an identity record."""
    return {"id": cast(str, record["id"]), "digest": cast(str, record["digest"])}


class _IdentityStore:
    """Store each canonical payload once and issue digest-checked references."""

    def __init__(self) -> None:
        """Initialize the identity and preimage indexes."""
        self.records: list[dict[str, object]] = []
        self._by_key: dict[tuple[str, str], dict[str, object]] = {}
        self._by_digest: dict[str, bytes] = {}
        self._by_payload: dict[bytes, tuple[str, str]] = {}

    def add(
        self, kind: str, identity_id: str, payload: Mapping[str, object]
    ) -> dict[str, str]:
        """Add or reuse one identity, rejecting collisions and payload duplication."""
        if kind not in IDENTITY_KINDS:
            raise ValueError(f"invalid_identity_kind:{kind}")
        canonical_kind = _normalize_identifier(kind)
        canonical_id = _normalize_identifier(identity_id)
        normalized = cast(Mapping[str, object], _canonicalize(dict(payload)))
        preimage = _identity_preimage(canonical_id, canonical_kind, normalized)
        digest = hashlib.sha256(preimage).hexdigest()
        key = (canonical_kind, canonical_id)
        existing = self._by_key.get(key)
        if existing is not None:
            if (
                cast(str, existing["digest"]) != digest
                or existing["canonical_payload"] != normalized
            ):
                raise GraphIdentityCollisionError(f"{kind}:{identity_id}")
            return _ref(existing)
        old_preimage = self._by_digest.get(digest)
        if old_preimage is not None and old_preimage != preimage:
            raise GraphDigestCollisionError(digest)
        payload_key = _canonical_bytes(normalized)
        old_identity = self._by_payload.get(payload_key)
        if old_identity is not None:
            old_kind, old_id = old_identity
            raise GraphIdentityCollisionError(
                f"payload_duplicate:{old_kind}:{old_id}:{canonical_kind}:{canonical_id}"
            )
        record: dict[str, object] = {
            "id": canonical_id,
            "digest": digest,
            "kind": canonical_kind,
            "canonical_payload": dict(normalized),
        }
        self.records.append(record)
        self._by_key[key] = record
        self._by_digest[digest] = preimage
        self._by_payload[payload_key] = (canonical_kind, canonical_id)
        return _ref(record)

    def require(self, reference: Mapping[str, object]) -> dict[str, object]:
        """Resolve and verify one Ref."""
        identity_id = reference.get("id")
        digest = reference.get("digest")
        if not isinstance(identity_id, str) or not isinstance(digest, str):
            raise GraphDigestMismatchError("malformed_ref")
        canonical_id = _normalize_identifier(identity_id)
        matches = [record for record in self.records if record["id"] == canonical_id]
        if len(matches) != 1:
            raise GraphDigestMismatchError(f"missing_ref:{identity_id}")
        record = matches[0]
        if record["digest"] != digest:
            raise GraphDigestMismatchError(f"ref:{identity_id}")
        expected = _identity_digest(
            canonical_id,
            cast(str, record["kind"]),
            cast(Mapping[str, object], record["canonical_payload"]),
        )
        if expected != digest:
            raise GraphDigestMismatchError(f"record:{identity_id}")
        return record


def _file_digest(root: Path, relative: str) -> str:
    """Digest one canonical source file, retaining only its logical locator."""
    path = root / relative
    if not path.is_file():
        raise ValueError(f"skill_tool_invocation_graph_missing_source:{relative}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_mermaid_id(value: str) -> str:
    """Convert a graph identity to a Mermaid-safe identifier."""
    return "n_" + "".join(char if char.isalnum() else "_" for char in value)


def _mermaid_label(value: str) -> str:
    """Escape the bounded label alphabet used by the generated graph."""
    return (
        value.replace('"', "'").replace("\n", " ").replace("[", "(").replace("]", ")")
    )


def _label(value: str) -> str:
    """Compatibility alias for the legacy rule-only renderer."""
    return _mermaid_label(value)


def _load_tool_entries(root: Path) -> tuple[Mapping[str, object], ...]:
    """Load ToolID-owned catalog entries in their canonical order."""
    path = root / "tools/catalog.yaml"
    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(
            "skill_tool_invocation_graph_tool_catalog_unavailable"
        ) from exc
    if not isinstance(raw, Mapping) or not isinstance(raw.get("entries"), list):
        raise ValueError("skill_tool_invocation_graph_tool_catalog_invalid")
    entries: list[Mapping[str, object]] = []
    for entry in raw["entries"]:
        if (
            not isinstance(entry, Mapping)
            or not isinstance(entry.get("id"), str)
            or not isinstance(entry.get("path"), str)
        ):
            raise ValueError("skill_tool_invocation_graph_tool_catalog_invalid_entry")
        entries.append(cast(Mapping[str, object], entry))
    return tuple(entries)


def _resolve_tool_id(
    logical_command: str,
    execution_env: Sequence[tuple[str, str]],
    execution_argv: Sequence[str],
    entries: Sequence[Mapping[str, object]],
) -> str | None:
    """Resolve a logical command to a catalog ToolID without inventing rows."""
    for entry in entries:
        command = entry.get("command")
        if isinstance(command, str) and (
            logical_command == command or logical_command.startswith(command + " ")
        ):
            return cast(str, entry["id"])
    tokens = shlex.split(logical_command)
    for token in tokens[1:2]:
        for entry in entries:
            if entry.get("path") == token:
                return cast(str, entry["id"])
    env = dict(execution_env)
    if (
        len(execution_argv) >= 4
        and execution_argv[0] in ("python", "python3")
        and execution_argv[1] == "-m"
        and execution_argv[2] == "agent_tools.agent_canon_source_root"
        and execution_argv[3] == "exec"
        and env.get("PYTHONPATH") is not None
    ):
        # Canonicalize AgentCanon sync invocations expressed through the source-root
        # owner wrapper back to the underlying sync-agent-canon ToolID.
        sync_script = Path(execution_argv[4]) if len(execution_argv) > 4 else None
        if (
            sync_script is not None
            and sync_script.as_posix().removeprefix("./") == "tools/sync_agent_canon.sh"
        ):
            return "sync-agent-canon"
    if execution_argv:
        executable = execution_argv[0]
        for entry in entries:
            command = entry.get("command")
            if isinstance(command, str) and command.split(maxsplit=1)[0] == executable:
                return cast(str, entry["id"])
    return None


def _packets(root: Path, skill_ids: Sequence[str]) -> dict[str, SkillCommandPacket]:
    """Resolve every public skill through the canonical command packet owner."""
    resolution = resolve_agent_canon_source_root(root)
    return {skill: packet_for_skill(resolution, skill) for skill in skill_ids}


def _packet_commands(
    packet: SkillCommandPacket, phase: str
) -> tuple[
    tuple[str, str, str, tuple[tuple[str, str], ...], tuple[str, ...]], ...
]:
    """Return one packet's resolved rows for an explicit phase."""
    if phase == "required":
        return packet.resolved_required_commands
    if phase == "conditional":
        return packet.resolved_conditional_commands
    if phase == "maintenance":
        return packet.resolved_maintenance_commands
    raise ValueError(f"skill_tool_invocation_graph_unknown_phase:{phase}")


def _route_snapshot(rules: Sequence[object]) -> list[dict[str, object]]:
    """Create a logical, ToolCall-free route packet snapshot."""
    result: list[dict[str, object]] = []
    for rule in rules:
        typed = cast(Any, rule)
        result.append(
            {
                "skill": typed.skill,
                "stage_policy": typed.stage_policy,
                "responsibility_group": typed.responsibility_group,
                "related_skills": list(typed.related_skills),
                "capabilities": [
                    {
                        "id": route.capability_id,
                        "owner": route.owner,
                        "phase": route.phase,
                        "activation": route.activation,
                        "exclusive": route.exclusive,
                    }
                    for route in typed.capabilities
                ],
                "visualization_role": typed.visualization_role,
                "tool_id": typed.tool_id,
                "argument_schema": typed.argument_schema,
                "required_prerequisites": list(typed.required_prerequisites),
                "successors": list(typed.successors),
            }
        )
    return result


def _build_owner_and_adapter_calls(
    capability_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Invoke the typed visualization owner before its dependency adapter."""
    owner = build_visualization_owner_tool_call(
        f"capability:{capability_id}",
        f"agents/skills/catalog.yaml#capability:{capability_id}",
    )
    serialize_tool_call(owner)
    adapter = build_visualization_adapter_tool_call(owner)
    serialize_tool_call(adapter)
    return cast(dict[str, object], owner), cast(dict[str, object], adapter)


def _legacy_source_item(
    kind: str, origin: str, locator: str, ordinal: int, payload: Mapping[str, object]
) -> VisualizationSourceItem:
    """Build the source item accepted by the public owner ToolCall contract."""
    return {
        "item_id": _digest(
            {
                "kind": kind,
                "origin": origin,
                "locator": locator,
                "ordinal": ordinal,
                "payload": payload,
            }
        ),
        "kind": cast(Any, kind),
        "origin": cast(Any, origin),
        "source_locator": locator,
        "source_start": None,
        "source_end": None,
        "ordinal": ordinal,
        # visualization_contract owns this compatibility envelope's sorted-key
        # serializer; the v2 graph never persists this full source payload.
        "payload_json": json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
    }


def _source_record(
    identities: _IdentityStore,
    source_inventory: list[dict[str, object]],
    source_kind: str,
    locator: str,
    ordinal: int,
    subject: Mapping[str, str] | None,
    **extra: object,
) -> dict[str, str]:
    """Materialize one source locator/digest record as a Ref-only inventory item."""
    if source_kind not in SOURCE_KINDS:
        raise ValueError(f"invalid_source_kind:{source_kind}")
    payload: dict[str, object] = {
        "source_kind": source_kind,
        "source_locator": locator,
        "ordinal": ordinal,
        "subject_ref": dict(subject) if subject is not None else None,
        **extra,
    }
    source_id = f"source:{source_kind}:{ordinal:05d}:{_digest(payload)[:16]}"
    source_ref = identities.add("source", source_id, payload)
    source_inventory.append(
        {
            "ref": source_ref,
            "kind": source_kind,
            "source_locator": locator,
            "ordinal": ordinal,
        }
    )
    return source_ref


def _source_counts(source_inventory: Sequence[Mapping[str, object]]) -> dict[str, int]:
    """Count all eight typed source categories, including zero values."""
    counts = {kind: 0 for kind in SOURCE_KINDS}
    for item in source_inventory:
        counts[cast(str, item["kind"])] += 1
    return counts


def _projection_entry(
    reference: Mapping[str, str], label: str, order: int | None = None
) -> dict[str, object]:
    """Build a projection envelope containing a Ref and no canonical payload."""
    result: dict[str, object] = {"ref": dict(reference), "display_label": label}
    if order is not None:
        result["order"] = order
    return result


def _validate_projection_refs(
    graph: Mapping[str, object], identities: _IdentityStore
) -> None:
    """Validate every Ref-only projection against the IdentityRecord store."""
    for field in ("skills", "phases", "commands", "tools", "capabilities", "toolcalls"):
        for item in cast(Sequence[Mapping[str, object]], graph[field]):
            identities.require(cast(Mapping[str, object], item["ref"]))
            if (
                "canonical_payload" in item
                or "logical_argv" in item
                or "execution_argv" in item
            ):
                raise ValueError(f"payload_leak:{field}")
    for edge in cast(Sequence[Mapping[str, object]], graph["edges"]):
        identities.require(cast(Mapping[str, object], edge["edge_ref"]))
        identities.require(cast(Mapping[str, object], edge["source_ref"]))
        identities.require(cast(Mapping[str, object], edge["target_ref"]))


def _add_edge(
    identities: _IdentityStore,
    edges: list[dict[str, object]],
    source_inventory: list[dict[str, object]],
    edge_type: str,
    source: Mapping[str, str],
    target: Mapping[str, str],
    order: int,
    attributes: Mapping[str, object] | None = None,
) -> None:
    """Materialize one edge identity, projection, and source evidence row."""
    if edge_type not in EDGE_TYPES:
        raise ValueError(f"unknown_edge_type:{edge_type}")
    edge_id = f"edge:{len(edges):05d}"
    payload = {
        "id": edge_id,
        "kind": edge_type,
        "source_id": source["id"],
        "target_id": target["id"],
        "order": order,
        "attributes": dict(attributes or {}),
    }
    edge_ref = identities.add("edge", edge_id, payload)
    edges.append(
        {
            "edge_ref": edge_ref,
            "source_ref": dict(source),
            "target_ref": dict(target),
            "display_label": edge_type,
        }
    )
    _source_record(
        identities,
        source_inventory,
        "edge",
        f"graph:edge:{len(edges) - 1:05d}",
        len(edges) - 1,
        edge_ref,
        edge_type=edge_type,
        source_ref=dict(source),
        target_ref=dict(target),
        order=order,
    )


def _projection_digest(graph: Mapping[str, object]) -> dict[str, str]:
    """Digest each projection independently of downstream artifact bytes."""
    return {
        "nodes": _digest(
            {
                key: graph[key]
                for key in (
                    "skills",
                    "phases",
                    "commands",
                    "tools",
                    "capabilities",
                    "toolcalls",
                )
            }
        ),
        "edges": _digest(graph["edges"]),
        "invocation_order": _digest(graph["invocation_order"]),
    }


def _source_snapshot(
    root: Path,
    rules: Sequence[object],
    packets: Mapping[str, SkillCommandPacket],
    toolcall_packet: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build the six logical source locator/digest entries required by SG-003."""
    skill_ids = tuple(packets)
    command_packet = [
        {
            "skill": skill,
            "phase": phase,
            "commands": [
                {"logical_command": row[0], "logical_argv": list(shlex.split(row[0]))}
                for row in _packet_commands(packets[skill], phase)
            ],
        }
        for skill in skill_ids
        for phase in PHASES
    ]
    route_packet = _route_snapshot(rules)
    locators = {
        "catalog_sha256": "agents/skills/catalog.yaml",
        "dependencies_sha256": "agents/skills/skill-dependencies.yaml",
        "reader_index_sha256": "agents/canonical/skills.md",
        "route_packet_sha256": "agents/skills/catalog.yaml#routing",
        "command_packet_sha256": "tools/agent_tools/skill_tool_commands.py#canonical-resolution",
        "toolcall_packet_sha256": "agents/skills/catalog.yaml#typed-visualization-toolcalls",
    }
    return {
        "catalog_sha256": _file_digest(root, locators["catalog_sha256"]),
        "dependencies_sha256": _file_digest(root, locators["dependencies_sha256"]),
        "reader_index_sha256": _file_digest(root, locators["reader_index_sha256"]),
        "route_packet_sha256": _digest(route_packet),
        "command_packet_sha256": _digest(command_packet),
        "toolcall_packet_sha256": _digest(toolcall_packet),
        "source_locators": locators,
    }


def _validate_reader_parity(root: Path) -> None:
    """Check skills.md as a link-only reader index, never as a 60-row canon."""
    text = (root / "agents/canonical/skills.md").read_text(encoding="utf-8")
    required_links = (
        "../skills/README.md",
        "../skills/catalog.yaml",
        "../internal-routines/README.md",
    )
    missing = [link for link in required_links if link not in text]
    if missing:
        raise ValueError("skills_md_link_parity:" + ",".join(missing))


def _validate_design_correspondence(root: Path) -> dict[str, object]:
    """Require forward and reverse trace coverage before materialization."""
    design_path = root / DESIGN_LOCATOR
    if not design_path.is_file():
        raise ValueError("design_correspondence_missing:design_locator")
    design_text = design_path.read_text(encoding="utf-8")
    required_tokens = (*DESIGN_CLAUSE_IDS, *DIC_CLAUSE_IDS, *IMPLEMENTATION_TRACE_PATHS)
    missing = [token for token in required_tokens if token not in design_text]
    adapter_pairs = tuple(
        (tool_id, TOOL_ARGUMENT_SCHEMAS[tool_id])
        for tool_id in VISUALIZATION_ADAPTER_TOOL_IDS
    )
    missing_pairs = [
        f"{tool_id}|{argument_schema}"
        for tool_id, argument_schema in adapter_pairs
        if tool_id not in design_text or argument_schema not in design_text
    ]
    if missing or missing_pairs:
        detail = ",".join((*missing, *missing_pairs))
        raise ValueError(f"design_correspondence_missing:{detail}")
    return {
        "design_locator": DESIGN_LOCATOR,
        "design_sha256": _file_digest(root, DESIGN_LOCATOR),
        "clause_ids": list(DESIGN_CLAUSE_IDS),
        "dic_clause_ids": list(DIC_CLAUSE_IDS),
        "implementation_target_paths": list(IMPLEMENTATION_TRACE_PATHS),
        "adapter_pairs": [
            {"tool_id": tool_id, "argument_schema": argument_schema}
            for tool_id, argument_schema in adapter_pairs
        ],
    }


def build_graph(root: Path) -> dict[str, object]:
    """Build the complete v2 graph without truncating any source identity."""
    _validate_reader_parity(root)
    design_correspondence = _validate_design_correspondence(root)
    catalog = load_skill_catalog(root)
    skill_ids = tuple(
        cast(str, cast(Mapping[str, object], entry)["id"])
        for entry in cast(list[object], catalog["skill_families"])
    )
    if len(skill_ids) != 60:
        raise ValueError(f"skill_tool_invocation_graph_skill_count:{len(skill_ids)}")
    rules = dict(load_skill_dependency_map(root, skill_ids))
    route_rules = load_skill_route_rules(root)
    route_by_skill = {rule.skill: rule for rule in route_rules}
    if set(skill_ids) != set(rules) or set(skill_ids) != set(route_by_skill):
        raise ValueError("skill_tool_invocation_graph_skill_identity_mismatch")
    packets = _packets(root, skill_ids)
    tools = _load_tool_entries(root)
    invocation_order = derive_skill_invocation_order(skill_ids, route_rules)
    invocation_ordinals = {skill: index for index, skill in enumerate(invocation_order)}
    identities = _IdentityStore()
    source_inventory: list[dict[str, object]] = []
    skill_refs: dict[str, dict[str, str]] = {}
    phase_refs: dict[tuple[str, str], dict[str, str]] = {}
    command_refs: dict[tuple[str, str, int], dict[str, str]] = {}
    capability_refs: dict[str, dict[str, str]] = {}
    tool_refs: dict[str, dict[str, str]] = {}
    tool_ids_by_command: dict[tuple[str, str, int], str | None] = {}
    phase_commands: dict[
        tuple[str, str], list[tuple[int, str, str, tuple[tuple[str, str], ...], tuple[str, ...]]]
    ] = (
        defaultdict(list)
    )

    for skill in skill_ids:
        rule = rules[skill]
        phase_ids = [f"phase:{skill}:{phase}" for phase in PHASES]
        capability_ids = [
            f"capability:{skill}:{route.capability_id}"
            for route in route_by_skill[skill].capabilities
        ]
        command_ids: list[str] = []
        for phase in PHASES:
            for index, (logical, _source_root, _execution_cwd, _execution_env, argv) in enumerate(
                _packet_commands(packets[skill], phase)
            ):
                command_id = f"command:{skill}:{phase}:{index:04d}"
                command_ids.append(command_id)
                phase_commands[(skill, phase)].append(
                    (index, logical, _execution_cwd, _execution_env, argv)
                )
        skill_refs[skill] = identities.add(
            "skill",
            f"skill:{skill}",
            {
                "id": skill,
                "catalog_locator": f"agents/skills/catalog.yaml#skill:{skill}",
                "canonical_doc": f"agents/skills/{skill}.md",
                "shim": f".agents/skills/{skill}/SKILL.md",
                "command_ids": command_ids,
                "capability_ids": capability_ids,
                "phase_ids": phase_ids,
            },
        )
        _source_record(
            identities,
            source_inventory,
            "identity",
            f"agents/skills/catalog.yaml#skill:{skill}",
            skill_ids.index(skill),
            skill_refs[skill],
            responsibility_group=rule.responsibility_group,
        )
        _source_record(
            identities,
            source_inventory,
            "time",
            f"agents/skills/skill-dependencies.yaml#invocation:{skill}",
            invocation_ordinals[skill],
            skill_refs[skill],
            invocation_ordinal=invocation_ordinals[skill],
        )
        for cap in route_by_skill[skill].capabilities:
            capability_id = f"capability:{skill}:{cap.capability_id}"
            capability_refs[capability_id] = identities.add(
                "capability",
                capability_id,
                {
                    "id": cap.capability_id,
                    "owner_id": skill,
                    "type": cap.activation,
                    "phase_id": f"phase:{skill}:conditional",
                    "adapter_id": VISUALIZATION_DEPENDENCY_ADAPTER_TOOL_ID
                    if cap.capability_id == "dependency_manifest_graph"
                    else None,
                },
            )
            _source_record(
                identities,
                source_inventory,
                "branch",
                f"agents/skills/catalog.yaml#capability:{cap.capability_id}",
                len(capability_refs) - 1,
                capability_refs[capability_id],
                owner=cap.owner,
                phase=cap.phase,
            )

    for skill in skill_ids:
        for phase_index, phase in enumerate(PHASES):
            phase_id = f"phase:{skill}:{phase}"
            phase_refs[(skill, phase)] = identities.add(
                "phase",
                phase_id,
                {"id": phase_id, "owner_id": skill, "order": phase_index},
            )
            _source_record(
                identities,
                source_inventory,
                "phase",
                f"agents/skills/catalog.yaml#skill:{skill}.tool_commands.{phase}",
                phase_index,
                phase_refs[(skill, phase)],
            )
            for index, logical, _cwd, _env, argv in phase_commands[(skill, phase)]:
                command_id = f"command:{skill}:{phase}:{index:04d}"
                tool_id = _resolve_tool_id(logical, _env, argv, tools)
                tool_ids_by_command[(skill, phase, index)] = tool_id
                command_refs[(skill, phase, index)] = identities.add(
                    "command",
                    command_id,
                    {
                        "id": command_id,
                        "skill_id": skill,
                        "logical_argv": list(shlex.split(logical)),
                        "source_locator": f"agents/skills/catalog.yaml#skill:{skill}.tool_commands.{phase}[{index}]",
                        "execution_cwd": ".",
                        "argv_digest": _digest(list(shlex.split(logical))),
                    },
                )
                _source_record(
                    identities,
                    source_inventory,
                    "identity",
                    f"agents/skills/catalog.yaml#skill:{skill}.tool_commands.{phase}[{index}]",
                    index,
                    command_refs[(skill, phase, index)],
                    phase=phase,
                )
                _source_record(
                    identities,
                    source_inventory,
                    "field",
                    f"tools/agent_tools/skill_tool_commands.py#{skill}:{phase}:{index}",
                    index,
                    command_refs[(skill, phase, index)],
                    logical_argv=list(shlex.split(logical)),
                )
                if tool_id is not None and tool_id not in tool_refs:
                    entry = next(entry for entry in tools if entry["id"] == tool_id)
                    tool_refs[tool_id] = identities.add(
                        "tool",
                        f"tool:{tool_id}",
                        {
                            "id": tool_id,
                            "owner_id": "tools/catalog.yaml",
                            "argument_schema_id": entry.get("argument_schema_id"),
                            "logical_locator": cast(str, entry["path"]),
                        },
                    )
                    _source_record(
                        identities,
                        source_inventory,
                        "module",
                        f"tools/catalog.yaml#tool:{tool_id}",
                        len(tool_refs) - 1,
                        tool_refs[tool_id],
                    )

    capability_id = "dependency_manifest_graph"
    if not any(
        route.capability_id == capability_id
        for rule in route_rules
        for route in rule.capabilities
    ):
        raise ValueError(
            "typed_visualization_capability_missing:dependency_manifest_graph"
        )
    owner_call, adapter_call = _build_owner_and_adapter_calls(capability_id)
    toolcall_summaries = (
        {
            "id": "toolcall:canonical-owner",
            "tool_id": VISUALIZATION_OWNER_TOOL_ID,
            "argument_schema_id": VISUALIZATION_OWNER_ARGUMENT_SCHEMA,
            "order": 0,
            "locator_refs": [
                "agents/skills/catalog.yaml#capability:dependency_manifest_graph"
            ],
        },
        {
            "id": "toolcall:dependency-manifest-adapter",
            "tool_id": VISUALIZATION_DEPENDENCY_ADAPTER_TOOL_ID,
            "argument_schema_id": VISUALIZATION_DEPENDENCY_ADAPTER_ARGUMENT_SCHEMA,
            "order": 1,
            "locator_refs": ["tools/agent_tools/render_dependency_manifest_graph.py"],
        },
    )
    toolcall_refs: dict[str, dict[str, str]] = {}
    for summary in toolcall_summaries:
        toolcall_refs[cast(str, summary["id"])] = identities.add(
            "toolcall",
            cast(str, summary["id"]),
            {
                "id": summary["id"],
                "tool_id": summary["tool_id"],
                "input_refs": [],
                "output_refs": [],
                "locator_refs": summary["locator_refs"],
                "order": summary["order"],
            },
        )
    _source_record(
        identities,
        source_inventory,
        "module",
        "agents/skills/code-visualization.md",
        0,
        toolcall_refs["toolcall:canonical-owner"],
        owner_tool_id=VISUALIZATION_OWNER_TOOL_ID,
    )

    # Exercise the public source-universe contract after the owner ToolCall and before the adapter.
    literal_items = [
        _legacy_source_item(
            "identity",
            "literal_request",
            "route:capability:dependency_manifest_graph",
            0,
            {"request": "complete public skill/tool invocation graph"},
        )
    ]
    owner_items = [
        _legacy_source_item(
            "module",
            "owner_closure",
            "agents/skills/code-visualization.md",
            0,
            {"owner_skill": "code-visualization"},
        )
    ]
    dependency_items = [
        _legacy_source_item(
            cast(str, item["kind"]),
            "dependency_closure",
            cast(str, item["source_locator"]),
            cast(int, item["ordinal"]),
            {"ref": item["ref"]},
        )
        for item in source_inventory
    ]
    source_universe = build_source_universe(
        request_id=cast(
            str, cast(Mapping[str, object], owner_call["arguments"])["request_id"]
        ),
        literal_request=cast(
            str, cast(Mapping[str, object], owner_call["arguments"])["literal_request"]
        ),
        literal_items=literal_items,
        owner_closure=owner_items,
        dependency_closure=dependency_items,
    )
    if len(source_universe["items"]) != len(literal_items) + len(owner_items) + len(
        dependency_items
    ):
        raise ValueError("source_universe_omission")

    source_snapshot = _source_snapshot(root, route_rules, packets, toolcall_summaries)
    for key, locator in cast(
        Mapping[str, str], source_snapshot["source_locators"]
    ).items():
        _source_record(
            identities,
            source_inventory,
            "evidence",
            locator,
            len(source_inventory),
            None,
            source_name=key,
            sha256=source_snapshot[key],
        )

    edges: list[dict[str, object]] = []
    edge_order = 0
    _add_edge(
        identities,
        edges,
        source_inventory,
        "order",
        toolcall_refs["toolcall:canonical-owner"],
        toolcall_refs["toolcall:dependency-manifest-adapter"],
        edge_order,
        {"reason": "owner-before-adapter"},
    )
    edge_order += 1
    for skill in skill_ids:
        for phase in PHASES:
            _add_edge(
                identities,
                edges,
                source_inventory,
                "invocation",
                skill_refs[skill],
                phase_refs[(skill, phase)],
                edge_order,
                {"phase": phase, "invocation_ordinal": invocation_ordinals[skill]},
            )
            edge_order += 1
            for index, _logical, _cwd, _env, _argv in phase_commands[(skill, phase)]:
                _add_edge(
                    identities,
                    edges,
                    source_inventory,
                    "invocation",
                    phase_refs[(skill, phase)],
                    command_refs[(skill, phase, index)],
                    edge_order,
                    {"phase": phase, "command_ordinal": index},
                )
                edge_order += 1
    for skill in skill_ids:
        rule = rules[skill]
        for prerequisite in rule.required_prerequisites:
            _add_edge(
                identities,
                edges,
                source_inventory,
                "prerequisite",
                skill_refs[prerequisite],
                skill_refs[skill],
                edge_order,
            )
            edge_order += 1
        for successor in rule.successors:
            _add_edge(
                identities,
                edges,
                source_inventory,
                "successor",
                skill_refs[skill],
                skill_refs[successor],
                edge_order,
            )
            edge_order += 1
        for constraint in rule.order_constraints:
            _add_edge(
                identities,
                edges,
                source_inventory,
                "order",
                skill_refs[constraint.before],
                skill_refs[constraint.after],
                edge_order,
                {"reason": constraint.reason},
            )
            edge_order += 1
        for candidate in rule.routing_candidates:
            _add_edge(
                identities,
                edges,
                source_inventory,
                "routing",
                skill_refs[skill],
                skill_refs[candidate],
                edge_order,
            )
            edge_order += 1
        for other in rule.parallel_independent:
            if skill < other:
                _add_edge(
                    identities,
                    edges,
                    source_inventory,
                    "parallel",
                    skill_refs[skill],
                    skill_refs[other],
                    edge_order,
                )
                edge_order += 1
    for key, tool_id in tool_ids_by_command.items():
        if tool_id is not None:
            _add_edge(
                identities,
                edges,
                source_inventory,
                "tool-resolution",
                command_refs[key],
                tool_refs[tool_id],
                edge_order,
                {"tool_id": tool_id},
            )
            edge_order += 1

    if "dependency-design" not in skill_ids:
        raise ValueError("skill_tool_invocation_graph_dependency-design_omission")
    if any(edge["display_label"] not in EDGE_TYPES for edge in edges):
        raise ValueError("skill_tool_invocation_graph_unknown_edge_type")

    skills_projection = [
        {
            **_projection_entry(skill_refs[skill], skill, invocation_ordinals[skill]),
            "kind": "skill",
        }
        for skill in skill_ids
    ]
    phases_projection = [
        _projection_entry(phase_refs[(skill, phase)], f"{skill}/{phase}", phase_index)
        for skill in skill_ids
        for phase_index, phase in enumerate(PHASES)
    ]
    commands_projection = [
        _projection_entry(command_refs[(skill, phase, index)], logical, index)
        for skill in skill_ids
        for phase in PHASES
        for index, logical, _cwd, _env, _argv in phase_commands[(skill, phase)]
    ]
    tools_projection = [
        _projection_entry(ref, tool_id) for tool_id, ref in tool_refs.items()
    ]
    capabilities_projection = [
        _projection_entry(ref, capability_id)
        for capability_id, ref in capability_refs.items()
    ]
    toolcalls_projection = [
        _projection_entry(
            toolcall_refs[cast(str, summary["id"])],
            cast(str, summary["tool_id"]),
            cast(int, summary["order"]),
        )
        for summary in toolcall_summaries
    ]
    invocation_projection = [
        {"ref": dict(skill_refs[skill]), "order": invocation_ordinals[skill]}
        for skill in invocation_order
    ]
    graph: dict[str, object] = {
        "schema": GRAPH_SCHEMA,
        "version": 2,
        "artifact_id": GRAPH_ARTIFACT_ID,
        "skill_count": len(skill_ids),
        "skills": skills_projection,
        "phases": phases_projection,
        "commands": commands_projection,
        "tools": tools_projection,
        "capabilities": capabilities_projection,
        "toolcalls": toolcalls_projection,
        "edges": edges,
        "invocation_order": invocation_projection,
        "source_snapshot": source_snapshot,
        "source_inventory": source_inventory,
        "source_counts": _source_counts(source_inventory),
        "design_correspondence": design_correspondence,
        "responsibility_groups": {
            skill: rules[skill].responsibility_group for skill in skill_ids
        },
        "tool_call_order": [
            "toolcall:canonical-owner",
            "toolcall:dependency-manifest-adapter",
        ],
        "owner_tool_call_ref": dict(toolcall_refs["toolcall:canonical-owner"]),
        "adapter_tool_call_ref": dict(
            toolcall_refs["toolcall:dependency-manifest-adapter"]
        ),
        "projection_digests": {},
    }
    graph["projection_digests"] = _projection_digest(graph)
    identity_refs = [_ref(record) for record in identities.records]
    edge_refs = [cast(dict[str, str], edge["edge_ref"]) for edge in edges]
    source_digest = _digest(source_snapshot)
    coverage_payload = {
        "id": "coverage:skill-tool-invocation-graph",
        "source_digest": source_digest,
        "source_refs": identity_refs,
        "projection_digests": graph["projection_digests"],
        "counts": graph["source_counts"],
    }
    coverage_ref = identities.add(
        "coverage", cast(str, coverage_payload["id"]), coverage_payload
    )
    manifest_payload = {
        "id": "manifest:skill-tool-invocation-graph",
        "source_digest": source_digest,
        "identity_refs": identity_refs,
        "edge_refs": edge_refs,
        "coverage_refs": [coverage_ref],
        "counts": {
            "skills": len(skills_projection),
            "phases": len(phases_projection),
            "commands": len(commands_projection),
            "tools": len(tools_projection),
            "edges": len(edges),
        },
    }
    manifest_ref = identities.add(
        "manifest", cast(str, manifest_payload["id"]), manifest_payload
    )
    readback_payload = {
        "id": "readback:skill-tool-invocation-graph",
        "source_digest": source_digest,
        "projection_digests": graph["projection_digests"],
        "coverage_ref": coverage_ref,
        "manifest_ref": manifest_ref,
        "counts": graph["source_counts"],
    }
    readback_ref = identities.add(
        "readback", cast(str, readback_payload["id"]), readback_payload
    )
    graph["identity_records"] = identities.records
    graph["manifest"] = {
        "ref": manifest_ref,
        "source_digest": source_digest,
        "identity_refs": identity_refs,
        "edge_refs": edge_refs,
        "coverage_refs": [coverage_ref],
        "counts": manifest_payload["counts"],
    }
    graph["coverage"] = {
        "ref": coverage_ref,
        "source_digest": source_digest,
        "projection_digests": graph["projection_digests"],
        "source_counts": graph["source_counts"],
        "rendered_counts": graph["source_counts"],
        "readback_counts": graph["source_counts"],
    }
    graph["coverage_digest"] = coverage_ref["digest"]
    graph["manifest_digest"] = manifest_ref["digest"]
    graph["source_digests"] = {
        key: source_snapshot[key]
        for key in (
            "catalog_sha256",
            "dependencies_sha256",
            "reader_index_sha256",
            "route_packet_sha256",
            "command_packet_sha256",
            "toolcall_packet_sha256",
        )
    }
    graph["readback_ref"] = readback_ref
    graph["graph_digest"] = _digest(
        {
            key: value
            for key, value in graph.items()
            if key not in {"graph_digest", "json_digest", "mermaid_digest", "readback"}
        }
    )
    mermaid = render_graph_mermaid(graph)
    graph["mermaid_digest"] = hashlib.sha256(mermaid.encode("utf-8")).hexdigest()
    graph["readback"] = {
        "ref": readback_ref,
        "source_digest": source_digest,
        "graph_digest": graph["graph_digest"],
        "mermaid_digest": graph["mermaid_digest"],
        "json_digest": "",
        "projection_digests": graph["projection_digests"],
        "counts": graph["source_counts"],
    }
    graph["json_digest"] = _digest(
        {
            key: value
            for key, value in graph.items()
            if key not in {"json_digest", "readback", "mermaid_digest"}
        }
    )
    graph["readback"] = dict(cast(Mapping[str, object], graph["readback"]))
    cast(dict[str, object], graph["readback"])["json_digest"] = graph["json_digest"]
    _validate_projection_refs(graph, identities)
    return graph


def _projection_nodes(
    graph: Mapping[str, object],
) -> list[tuple[str, Mapping[str, object], int]]:
    """Return all rendered node projections with deterministic group order."""
    result: list[tuple[str, Mapping[str, object], int]] = []
    for kind, field in (
        ("skill", "skills"),
        ("phase", "phases"),
        ("command", "commands"),
        ("tool", "tools"),
        ("capability", "capabilities"),
        ("toolcall", "toolcalls"),
    ):
        for index, item in enumerate(
            cast(Sequence[Mapping[str, object]], graph[field])
        ):
            result.append((kind, item, index))
    return result


def _rendered_node_label(item: Mapping[str, object]) -> str:
    """Render a node's display, order, and digest into actual Mermaid syntax."""
    reference = cast(Mapping[str, object], item["ref"])
    display = _mermaid_label(cast(str, item["display_label"]))
    digest = cast(str, reference["digest"])
    if "order" in item:
        return f"{display} (order={item['order']}; ref={digest})"
    return f"{display} (ref={digest})"


def _rendered_edge_label(
    edge: Mapping[str, object], payload: Mapping[str, object]
) -> str:
    """Render an edge's type, order, and digest into actual Mermaid syntax."""
    edge_ref = cast(Mapping[str, object], edge["edge_ref"])
    return (
        f"{edge['display_label']} (order={payload['order']}; ref={edge_ref['digest']})"
    )


def render_graph_mermaid(graph: Mapping[str, object]) -> str:
    """Render one complete graph with compact Ref metadata and no manifest marker."""
    lines = [
        GRAPH_DEPENDENCY_HEADER,
        GRAPH_HEADER,
        "# Public Skill/Tool Invocation Graph",
        "",
        f"<!-- graph_digest={graph['graph_digest']} coverage_digest={cast(Mapping[str, object], graph['coverage'])['ref']['digest']} -->",
        "```mermaid",
        "graph LR",
    ]
    skills = cast(Sequence[Mapping[str, object]], graph["skills"])
    groups: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    identity_by_id = {
        cast(str, record["id"]): record
        for record in cast(Sequence[Mapping[str, object]], graph["identity_records"])
    }
    for item in skills:
        skill_id = cast(str, cast(Mapping[str, object], item["ref"])["id"])
        skill_name = skill_id.removeprefix("skill:")
        responsibility_groups = cast(Mapping[str, str], graph["responsibility_groups"])
        groups[responsibility_groups[skill_name]].append(item)
    for group in sorted(groups):
        lines.append(
            f'  subgraph responsibility_{_safe_mermaid_id(group)}["Responsibility: {_mermaid_label(group)}"]'
        )
        for item in groups[group]:
            reference = cast(Mapping[str, object], item["ref"])
            identity_id = cast(str, reference["id"])
            lines.append(
                f"    %% node kind=skill id={identity_id} digest={reference['digest']} order={item['order']}"
            )
            lines.append(
                f'    {_safe_mermaid_id(identity_id)}["{_rendered_node_label(item)}"]'
            )
        lines.append("  end")
    for phase in PHASES:
        lines.append(f'  subgraph phase_{phase}["Phase: {phase}"]')
        for item in cast(Sequence[Mapping[str, object]], graph["phases"]):
            reference = cast(Mapping[str, object], item["ref"])
            if cast(str, reference["id"]).endswith(f":{phase}"):
                identity_id = cast(str, reference["id"])
                lines.append(
                    f"    %% node kind=phase id={identity_id} digest={reference['digest']} order={item['order']}"
                )
                lines.append(
                    f'    {_safe_mermaid_id(identity_id)}{{"{_rendered_node_label(item)}"}}'
                )
        for item in cast(Sequence[Mapping[str, object]], graph["commands"]):
            identity_id = cast(str, cast(Mapping[str, object], item["ref"])["id"])
            payload = cast(
                Mapping[str, object], identity_by_id[identity_id]["canonical_payload"]
            )
            if (
                cast(str, payload["source_locator"])
                .split(".tool_commands.", 1)[1]
                .split("[", 1)[0]
                == phase
            ):
                reference = cast(Mapping[str, object], item["ref"])
                lines.append(
                    f"    %% node kind=command id={identity_id} digest={reference['digest']} order={item['order']}"
                )
                lines.append(
                    f'    {_safe_mermaid_id(identity_id)}["{_rendered_node_label(item)}"]'
                )
        lines.append("  end")
    for kind, field, title, shape in (
        ("tool", "tools", "ToolID catalog", "[["),
        ("capability", "capabilities", "Typed capabilities", "[["),
        ("toolcall", "toolcalls", "ToolCall order", "[["),
    ):
        entries = cast(Sequence[Mapping[str, object]], graph[field])
        if not entries:
            continue
        lines.append(f'  subgraph {kind}_catalog["{title}"]')
        for item in entries:
            reference = cast(Mapping[str, object], item["ref"])
            identity_id = cast(str, reference["id"])
            order = item.get("order", 0)
            lines.append(
                f"    %% node kind={kind} id={identity_id} digest={reference['digest']} order={order}"
            )
            lines.append(
                f'    {_safe_mermaid_id(identity_id)}{shape}"{_rendered_node_label(item)}"]]'
            )
        lines.append("  end")
    for index, source in enumerate(
        cast(Sequence[Mapping[str, object]], graph["source_inventory"])
    ):
        reference = cast(Mapping[str, object], source["ref"])
        locator = cast(str, source["source_locator"]).replace(" ", "%20")
        lines.append(
            f"  %% source kind={source['kind']} id={reference['id']} digest={reference['digest']} locator={locator} ordinal={source['ordinal']}"
        )
    for edge in cast(Sequence[Mapping[str, object]], graph["edges"]):
        edge_ref = cast(Mapping[str, object], edge["edge_ref"])
        source_ref = cast(Mapping[str, object], edge["source_ref"])
        target_ref = cast(Mapping[str, object], edge["target_ref"])
        edge_record = identity_by_id[cast(str, edge_ref["id"])]
        payload = cast(Mapping[str, object], edge_record["canonical_payload"])
        source_id = cast(str, source_ref["id"])
        target_id = cast(str, target_ref["id"])
        line_type = (
            "-.->" if edge["display_label"] in {"routing", "parallel"} else "-->"
        )
        lines.append(
            f"  %% edge id={edge_ref['id']} digest={edge_ref['digest']} type={edge['display_label']} source={source_id} source_digest={source_ref['digest']} target={target_id} target_digest={target_ref['digest']} order={payload['order']}"
        )
        lines.append(
            f'  {_safe_mermaid_id(source_id)} {line_type}|"{_rendered_edge_label(edge, payload)}"| {_safe_mermaid_id(target_id)}'
        )
    lines.extend(
        [
            "  %% Edge legend: solid = prerequisite, successor, order, invocation, tool-resolution; dashed = routing, parallel.",
            "```",
            "",
            "## Edge legend",
            "",
            "- `prerequisite`, `successor`, `order`, `invocation`, and `tool-resolution`: solid directed edges.",
            "- `routing` and `parallel`: dashed directed edges.",
            "",
            f"Coverage digest: `{cast(Mapping[str, object], graph['coverage'])['ref']['digest']}`.",
            f"Graph digest: `{graph['graph_digest']}`.",
            "",
        ]
    )
    return "\n".join(lines)


def _parse_mermaid_metadata(
    text: str,
) -> tuple[
    dict[str, str], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]
]:
    """Parse generated node, edge, and source metadata from the actual Mermaid block."""
    lines = text.splitlines()
    headers = [line for line in lines if MERMAID_HEADER_RE.match(line)]
    if len(headers) != 1 or "```mermaid" not in text or text.count("```mermaid") != 1:
        raise ValueError("mermaid_readback_block_or_header")
    header_match = MERMAID_HEADER_RE.match(headers[0])
    assert header_match is not None
    header = {
        "graph_digest": header_match.group(1),
        "coverage_digest": header_match.group(2),
    }
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    sources: list[dict[str, str]] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("%% node "):
            nodes.append(dict(MERMAID_KV_RE.findall(stripped.removeprefix("%% node "))))
        elif stripped.startswith("%% edge "):
            edges.append(dict(MERMAID_KV_RE.findall(stripped.removeprefix("%% edge "))))
        elif stripped.startswith("%% source "):
            sources.append(
                dict(MERMAID_KV_RE.findall(stripped.removeprefix("%% source ")))
            )
    return header, nodes, edges, sources


def _parse_mermaid_syntax(
    text: str,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Parse actual Mermaid node/edge statements, never their comments."""
    lines = text.splitlines()
    try:
        start = lines.index("```mermaid") + 1
        end = lines.index("```", start)
    except ValueError as exc:
        raise ValueError("mermaid_readback_block_or_header") from exc
    actual_nodes: dict[str, str] = {}
    actual_edges: list[dict[str, str]] = []
    for line in lines[start:end]:
        if line.lstrip().startswith("%%"):
            continue
        node_match = MERMAID_NODE_RE.match(line)
        edge_match = MERMAID_EDGE_RE.match(line)
        if node_match is not None:
            label = next(
                group for group in node_match.groups()[1:] if group is not None
            )
            node_id = node_match.group(1)
            if node_id in actual_nodes:
                raise ValueError(f"mermaid_readback_duplicate_node:{node_id}")
            actual_nodes[node_id] = label
        elif edge_match is not None:
            actual_edges.append(
                {
                    "source": edge_match.group(1),
                    "arrow": edge_match.group(2),
                    "label": edge_match.group(3),
                    "target": edge_match.group(4),
                }
            )
    return actual_nodes, actual_edges


def _parse_actual_node_label(label: str) -> tuple[str, int | None, str]:
    """Recover actual display, order, and digest from a Mermaid node label."""
    ordered = MERMAID_ORDERED_LABEL_RE.fullmatch(label)
    if ordered is not None:
        return ordered.group(1), int(ordered.group(2)), ordered.group(3)
    plain = MERMAID_REF_LABEL_RE.fullmatch(label)
    if plain is not None:
        return plain.group(1), None, plain.group(2)
    raise ValueError("mermaid_readback_node_label_missing_ref")


def _parse_actual_edge_label(label: str) -> tuple[str, int, str]:
    """Recover actual edge type, order, and digest from a Mermaid edge label."""
    match = re.fullmatch(r"(.*) \(order=([0-9]+); ref=([0-9a-f]{64})\)", label)
    if match is None:
        raise ValueError("mermaid_readback_edge_label_missing_ref")
    return match.group(1), int(match.group(2)), match.group(3)


def readback_mermaid(graph: Mapping[str, object], text: str) -> dict[str, object]:
    """Compare actual Mermaid node/edge/source refs, order, and digests."""
    header, nodes, edges, sources = _parse_mermaid_metadata(text)
    actual_nodes, actual_edges = _parse_mermaid_syntax(text)
    coverage_ref = cast(
        Mapping[str, object], cast(Mapping[str, object], graph["coverage"])["ref"]
    )
    if header != {
        "graph_digest": graph["graph_digest"],
        "coverage_digest": coverage_ref["digest"],
    }:
        raise ValueError("mermaid_readback_digest_mismatch")
    expected_actual_nodes: dict[str, tuple[str, int | None, str]] = {}
    for kind, item, _index in _projection_nodes(graph):
        reference = cast(Mapping[str, object], item["ref"])
        expected_actual_nodes[_safe_mermaid_id(cast(str, reference["id"]))] = (
            _mermaid_label(cast(str, item["display_label"])),
            cast(int, item["order"]) if "order" in item else None,
            cast(str, reference["digest"]),
        )
    observed_actual_nodes = {
        node_id: _parse_actual_node_label(label)
        for node_id, label in actual_nodes.items()
    }
    if observed_actual_nodes != expected_actual_nodes:
        raise ValueError("mermaid_readback_actual_node_order_or_digest_mismatch")
    identity_by_id = {
        cast(str, record["id"]): record
        for record in cast(Sequence[Mapping[str, object]], graph["identity_records"])
    }
    expected_actual_edges: set[tuple[str, str, str, str, str, int]] = set()
    for item in cast(Sequence[Mapping[str, object]], graph["edges"]):
        edge_ref = cast(Mapping[str, object], item["edge_ref"])
        source_ref = cast(Mapping[str, object], item["source_ref"])
        target_ref = cast(Mapping[str, object], item["target_ref"])
        payload = cast(
            Mapping[str, object],
            identity_by_id[cast(str, edge_ref["id"])]["canonical_payload"],
        )
        expected_actual_edges.add(
            (
                _safe_mermaid_id(cast(str, source_ref["id"])),
                "-.->" if item["display_label"] in {"routing", "parallel"} else "-->",
                _safe_mermaid_id(cast(str, target_ref["id"])),
                cast(str, item["display_label"]),
                cast(str, edge_ref["digest"]),
                cast(int, payload["order"]),
            )
        )
    observed_actual_edges: set[tuple[str, str, str, str, str, int]] = set()
    for item in actual_edges:
        edge_type, order, digest = _parse_actual_edge_label(item["label"])
        observed_actual_edges.add(
            (
                item["source"],
                item["arrow"],
                item["target"],
                edge_type,
                digest,
                order,
            )
        )
    if observed_actual_edges != expected_actual_edges or len(actual_edges) != len(
        expected_actual_edges
    ):
        raise ValueError("mermaid_readback_actual_edge_order_or_digest_mismatch")
    expected_nodes = {
        (
            kind,
            cast(str, cast(Mapping[str, object], item["ref"])["id"]),
            cast(str, cast(Mapping[str, object], item["ref"])["digest"]),
        )
        for kind, item, _order in _projection_nodes(graph)
    }
    observed_nodes = {
        (item.get("kind", ""), item.get("id", ""), item.get("digest", ""))
        for item in nodes
    }
    if observed_nodes != expected_nodes:
        raise ValueError("mermaid_readback_node_ref_mismatch")
    expected_edges = set()
    for item in cast(Sequence[Mapping[str, object]], graph["edges"]):
        edge_ref = cast(Mapping[str, object], item["edge_ref"])
        source_ref = cast(Mapping[str, object], item["source_ref"])
        target_ref = cast(Mapping[str, object], item["target_ref"])
        payload = cast(
            Mapping[str, object],
            identity_by_id[cast(str, edge_ref["id"])]["canonical_payload"],
        )
        expected_edges.add(
            (
                edge_ref["id"],
                edge_ref["digest"],
                item["display_label"],
                source_ref["id"],
                source_ref["digest"],
                target_ref["id"],
                target_ref["digest"],
                str(payload["order"]),
            )
        )
    observed_edges = tuple(
        (
            item.get("id", ""),
            item.get("digest", ""),
            item.get("type", ""),
            item.get("source", ""),
            item.get("source_digest", ""),
            item.get("target", ""),
            item.get("target_digest", ""),
            item.get("order", ""),
        )
        for item in edges
    )
    if set(observed_edges) != expected_edges or len(observed_edges) != len(
        expected_edges
    ):
        raise ValueError("mermaid_readback_edge_order_or_digest_mismatch")
    expected_sources = {
        (
            item["kind"],
            cast(str, cast(Mapping[str, object], item["ref"])["id"]),
            cast(str, cast(Mapping[str, object], item["ref"])["digest"]),
            item["source_locator"],
            str(item["ordinal"]),
        )
        for item in cast(Sequence[Mapping[str, object]], graph["source_inventory"])
    }
    observed_sources = {
        (
            item.get("kind", ""),
            item.get("id", ""),
            item.get("digest", ""),
            item.get("locator", ""),
            item.get("ordinal", ""),
        )
        for item in sources
    }
    if observed_sources != expected_sources:
        raise ValueError("mermaid_readback_source_coverage_mismatch")
    return {
        "status": "pass",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "source_counts": _source_counts(
            cast(Sequence[Mapping[str, object]], graph["source_inventory"])
        ),
    }


def render_mermaid(rules: Mapping[str, SkillDependencyRule]) -> str:
    """Render the legacy rule-only projection retained for focused callers."""
    groups: dict[str, list[str]] = defaultdict(list)
    for rule in rules.values():
        groups[rule.responsibility_group].append(rule.skill)
    lines = [
        GRAPH_DEPENDENCY_HEADER,
        GRAPH_HEADER,
        "# Public Skill Dependency Graph",
        "",
        "```mermaid",
        "graph LR",
    ]
    for group, skills in groups.items():
        legacy_group_id = group.replace("-", "_")
        lines.append(f'  subgraph group_{legacy_group_id}["{_label(group)}"]')
        for skill in skills:
            lines.append(
                f'    {_safe_mermaid_id(f"skill:{skill}")}["{_mermaid_label(skill)}"]'
            )
        lines.append("  end")
    for rule in rules.values():
        for prerequisite in rule.required_prerequisites:
            lines.append(
                f'  {_safe_mermaid_id(f"skill:{prerequisite}")} -->|"prerequisite"| {_safe_mermaid_id(f"skill:{rule.skill}")}'
            )
        for successor in rule.successors:
            lines.append(
                f'  {_safe_mermaid_id(f"skill:{rule.skill}")} -->|"successor"| {_safe_mermaid_id(f"skill:{successor}")}'
            )
        for constraint in rule.order_constraints:
            lines.append(
                f'  {_safe_mermaid_id(f"skill:{constraint.before}")} -->|"order"| {_safe_mermaid_id(f"skill:{constraint.after}")}'
            )
        for candidate in rule.routing_candidates:
            lines.append(
                f'  {_safe_mermaid_id(f"skill:{rule.skill}")} -.->|"routing"| {_safe_mermaid_id(f"skill:{candidate}")}'
            )
    lines.extend(["  %% Edge legend", "```", ""])
    return "\n".join(lines)


def _artifact_paths(root: Path, output: Path | None = None) -> tuple[Path, Path]:
    """Return the generated Markdown/JSON pair."""
    markdown = output if output is not None else root / DEFAULT_GRAPH_PATH
    json_path = (
        markdown.with_suffix(".json")
        if output is not None
        else root / DEFAULT_JSON_PATH
    )
    return markdown, json_path


def _json_text(graph: Mapping[str, object]) -> str:
    """Serialize the machine artifact with the same compact canonical policy."""
    return _canonical_json(graph)


def _json_digest_from_graph(graph: Mapping[str, object]) -> str:
    """Compute JSON digest without downstream artifact/readback digests."""
    return _digest(
        {
            key: value
            for key, value in graph.items()
            if key not in {"json_digest", "readback", "mermaid_digest"}
        }
    )


def write_artifacts(
    root: Path, *, output: Path | None = None
) -> tuple[Path, Path, dict[str, object]]:
    """Generate both canonical graph artifacts."""
    graph = build_graph(root)
    markdown, json_path = _artifact_paths(root, output)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_graph_mermaid(graph), encoding="utf-8")
    json_path.write_text(_json_text(graph), encoding="utf-8")
    return markdown, json_path, graph


def _validate_loaded_graph(machine: Mapping[str, object]) -> None:
    """Reject edited machine graphs before comparing their artifact bytes."""
    if machine.get("schema") != GRAPH_SCHEMA or machine.get("version") != 2:
        raise ValueError("skill_tool_invocation_graph_schema_mismatch")
    skills = cast(Sequence[Mapping[str, object]], machine.get("skills", []))
    if machine.get("skill_count") != 60 or "dependency-design" not in {
        cast(
            str,
            cast(
                Mapping[str, object], cast(Mapping[str, object], skill["ref"])["id"]
            ).removeprefix("skill:"),
        )
        for skill in skills
    }:
        raise ValueError("dependency-design:omission")
    if machine.get("json_digest") != _json_digest_from_graph(machine):
        raise ValueError("json_digest:mismatch")


def check_artifacts(root: Path) -> dict[str, object]:
    """Fail closed on missing, edited, stale, or dependency-design-omitting artifacts."""
    expected = build_graph(root)
    markdown, json_path = _artifact_paths(root)
    findings: list[str] = []
    if not markdown.is_file():
        findings.append(f"{markdown.relative_to(root)}:missing")
    if not json_path.is_file():
        findings.append(f"{json_path.relative_to(root)}:missing")
    if findings:
        raise ValueError(
            "skill_tool_invocation_graph_stale_artifact:" + ";".join(findings)
        )
    actual_markdown = markdown.read_text(encoding="utf-8")
    actual_json_text = json_path.read_text(encoding="utf-8")
    try:
        actual_machine = cast(Mapping[str, object], json.loads(actual_json_text))
        _validate_loaded_graph(actual_machine)
        readback_mermaid(expected, actual_markdown)
    except (ValueError, json.JSONDecodeError) as exc:
        findings.append(f"readback:{exc}")
    if actual_markdown != render_graph_mermaid(expected):
        findings.append(f"{markdown.relative_to(root)}:edited-or-stale")
    if actual_json_text != _json_text(expected):
        findings.append(f"{json_path.relative_to(root)}:edited-or-stale")
    if findings:
        raise ValueError(
            "skill_tool_invocation_graph_stale_artifact:" + ";".join(findings)
        )
    return expected


def check(root: Path) -> tuple[int, int, int]:
    """Validate source map and generated artifacts."""
    rules = dict(load_skill_dependency_map(root))
    graph = check_artifacts(root)
    edge_count = len(cast(Sequence[object], graph["edges"]))
    parallel_count = sum(
        1
        for edge in cast(Sequence[Mapping[str, object]], graph["edges"])
        if edge["display_label"] == "parallel"
    )
    return len(rules), edge_count, parallel_count


def build_parser() -> argparse.ArgumentParser:
    """Build the graph materializer/checker CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser(
        "check", help="validate source and generated graph artifacts"
    )
    check_parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    graph_parser = subparsers.add_parser(
        "graph", help="generate Mermaid and JSON graph artifacts"
    )
    graph_parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    graph_parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one fail-closed graph operation."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "check":
            skill_count, edge_count, parallel_count = check(root)
            print(
                f"SKILL_DEPENDENCY_MAP=pass source={SKILL_DEPENDENCY_MAP_PATH} skills={skill_count}"
            )
            print(
                f"SKILL_TOOL_INVOCATION_GRAPH=pass schema={GRAPH_SCHEMA} skills={skill_count} edges={edge_count} parallel_edges={parallel_count} json={DEFAULT_JSON_PATH} mermaid={DEFAULT_GRAPH_PATH}"
            )
            return 0
        markdown, json_path, graph = write_artifacts(root, output=args.output)
        print(
            f"SKILL_TOOL_INVOCATION_GRAPH=pass schema={GRAPH_SCHEMA} skills={graph['skill_count']} commands={len(graph['commands'])} tools={len(graph['tools'])} edges={len(graph['edges'])} json={json_path} mermaid={markdown}"
        )
        return 0
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"SKILL_TOOL_INVOCATION_GRAPH=fail reason={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
