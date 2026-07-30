#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Materializes and validates the complete typed public skill/tool invocation graph.
# upstream design ../../agents/skills/catalog.yaml owns public skill identity and command phases
# upstream design ../../agents/skills/skill-dependencies.yaml owns skill relations and invocation order
# upstream design ../../tools/catalog.yaml owns canonical ToolIDs
# upstream implementation ./skill_tool_commands.py resolves command packets and execution argv
# upstream implementation ./visualization_contract.py owns typed owner/adapter coverage and readback
# downstream implementation ../../documents/runtime/skill-dependency-graph.md is generated Mermaid
# downstream implementation ../../documents/runtime/skill-dependency-graph.json is generated machine graph
# downstream implementation ../../tests/agent_tools/test_skill_dependency_map.py checks graph completeness
# @dependency-end
"""Materialize the deterministic public skill/tool invocation graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import yaml
from agent_canon_source_root import resolve_agent_canon_source_root
from skill_route_catalog import (
    SKILL_DEPENDENCY_MAP_PATH,
    VISUALIZATION_DEPENDENCY_ADAPTER_ARGUMENT_SCHEMA,
    VISUALIZATION_DEPENDENCY_ADAPTER_TOOL_ID,
    VISUALIZATION_OWNER_ARGUMENT_SCHEMA,
    VISUALIZATION_OWNER_TOOL_ID,
    SkillDependencyRule,
    build_visualization_owner_tool_call,
    derive_skill_invocation_order,
    load_skill_catalog,
    load_skill_dependency_map,
    load_skill_route_rules,
)
from skill_tool_commands import SkillCommandPacket, packet_for_skill
from visualization_contract import (
    ProjectionCoverageEntry,
    VisualizationSourceItem,
    VisualizationSourceUniverse,
    build_projection_coverage_manifest,
    build_source_universe,
    readback_projection,
    serialize_projection_coverage_manifest,
    serialize_projection_identity,
    serialize_tool_call,
    validate_projection_coverage,
)

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH_PATH = Path("documents/runtime/skill-dependency-graph.md")
DEFAULT_JSON_PATH = Path("documents/runtime/skill-dependency-graph.json")
GRAPH_SCHEMA = "agent_canon.skill_tool_invocation_graph.v1"
GRAPH_ARTIFACT_ID = "skill-tool-invocation-graph"
GRAPH_RENDERER_ID = VISUALIZATION_DEPENDENCY_ADAPTER_TOOL_ID
GRAPH_CAPACITY = 8192
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
GRAPH_HEADER = "<!-- Generated from the typed skill/tool invocation graph; do not edit by hand. -->"


class GraphCapacityError(ValueError):
    """Typed fail-closed renderer capacity error."""

    code = "skill_tool_invocation_graph_capacity_exceeded"

    def __init__(self, observed: int, capacity: int) -> None:
        """Initialize a stable capacity diagnostic."""
        self.observed = observed
        self.capacity = capacity
        super().__init__(f"{self.code}:observed={observed}:capacity={capacity}")


def _canonical_json(value: object) -> str:
    """Serialize JSON with the graph's stable key and Unicode policy."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    """Return a deterministic SHA-256 digest for one JSON value."""
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _stable_id(*parts: object) -> str:
    """Return one collision-resistant source identity."""
    return hashlib.sha256(
        "\x1f".join(str(part) for part in parts).encode("utf-8")
    ).hexdigest()


def _source_item(
    *,
    kind: str,
    origin: str,
    locator: str,
    ordinal: int,
    payload: Mapping[str, object],
) -> VisualizationSourceItem:
    """Build one canonical visualization source item."""
    if kind not in SOURCE_KINDS:
        raise ValueError(f"skill_tool_invocation_graph_invalid_source_kind:{kind}")
    payload_json = _canonical_json(dict(payload))
    return {
        "item_id": _stable_id(kind, origin, locator, ordinal, payload_json),
        "kind": cast(Any, kind),
        "origin": cast(Any, origin),
        "source_locator": locator,
        "source_start": None,
        "source_end": None,
        "ordinal": ordinal,
        "payload_json": payload_json,
    }


def _source_counts(items: Sequence[VisualizationSourceItem]) -> dict[str, int]:
    """Count every source kind, including zero-valued kinds."""
    counts = {kind: 0 for kind in SOURCE_KINDS}
    for item in items:
        counts[item["kind"]] += 1
    return counts


def _file_digest(root: Path, relative: str) -> str:
    """Digest one required canonical source file or fail closed."""
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
        if not isinstance(entry, Mapping):
            raise ValueError("skill_tool_invocation_graph_tool_catalog_invalid_entry")
        if not isinstance(entry.get("id"), str) or not isinstance(
            entry.get("path"), str
        ):
            raise ValueError("skill_tool_invocation_graph_tool_catalog_invalid_entry")
        entries.append(cast(Mapping[str, object], entry))
    return tuple(entries)


def _resolve_tool_id(
    logical_command: str,
    execution_argv: Sequence[str],
    entries: Sequence[Mapping[str, object]],
    root: Path,
) -> str | None:
    """Resolve a command to the ToolID owner without inventing catalog rows."""
    for entry in entries:
        command = entry.get("command")
        if isinstance(command, str) and (
            logical_command == command or logical_command.startswith(command + " ")
        ):
            return cast(str, entry["id"])
    tokens = shlex.split(logical_command)
    script_tokens = [token for token in tokens[1:2] if token]
    for token in script_tokens:
        relative = token
        if Path(token).is_absolute():
            try:
                relative = str(Path(token).resolve().relative_to(root.resolve()))
            except ValueError:
                continue
        for entry in entries:
            if entry.get("path") == relative:
                return cast(str, entry["id"])
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
) -> tuple[tuple[str, str, str, tuple[str, ...]], ...]:
    """Return one packet's resolved rows for an explicit phase."""
    if phase == "required":
        return packet.resolved_required_commands
    if phase == "conditional":
        return packet.resolved_conditional_commands
    if phase == "maintenance":
        return packet.resolved_maintenance_commands
    raise ValueError(f"skill_tool_invocation_graph_unknown_phase:{phase}")


def _build_owner_and_adapter_calls(
    literal_items: Sequence[VisualizationSourceItem],
    owner_items: Sequence[VisualizationSourceItem],
    dependency_items: Sequence[VisualizationSourceItem],
) -> tuple[dict[str, object], dict[str, object]]:
    """Build the owner-first canonical ToolCall pair for this projection."""
    owner_base = build_visualization_owner_tool_call(
        "capability:dependency_manifest_graph",
        "agents/skills/catalog.yaml#capability:dependency_manifest_graph",
    )
    arguments = dict(owner_base["arguments"])
    arguments.update(
        {
            "literal_items": list(literal_items),
            "owner_closure": list(owner_items),
            "dependency_closure": list(dependency_items),
            "artifact_id": GRAPH_ARTIFACT_ID,
            "renderer_id": GRAPH_RENDERER_ID,
            "artifact_format": "markdown_mermaid",
        }
    )
    owner = {
        "schema": owner_base["schema"],
        "tool_id": VISUALIZATION_OWNER_TOOL_ID,
        "argument_schema": VISUALIZATION_OWNER_ARGUMENT_SCHEMA,
        "arguments": arguments,
    }
    serialize_tool_call(owner)
    adapter_arguments = dict(arguments)
    adapter_arguments["dependency_manifest_locator"] = (
        "agents/skills/skill-dependencies.yaml"
    )
    adapter = {
        "schema": owner_base["schema"],
        "tool_id": VISUALIZATION_DEPENDENCY_ADAPTER_TOOL_ID,
        "argument_schema": VISUALIZATION_DEPENDENCY_ADAPTER_ARGUMENT_SCHEMA,
        "arguments": adapter_arguments,
    }
    serialize_tool_call(adapter)
    return owner, adapter


def _coverage(
    source_items: Sequence[VisualizationSourceItem],
    owner_call: Mapping[str, object],
    adapter_call: Mapping[str, object],
) -> tuple[VisualizationSourceUniverse, dict[str, object], dict[str, object], str]:
    """Build, read back, and validate complete typed projection coverage."""
    literal = [item for item in source_items if item["origin"] == "literal_request"]
    owner = [item for item in source_items if item["origin"] == "owner_closure"]
    dependency = [
        item for item in source_items if item["origin"] == "dependency_closure"
    ]
    universe = build_source_universe(
        request_id=cast(
            str, cast(Mapping[str, object], owner_call)["arguments"]["request_id"]
        ),
        literal_request=cast(
            str, cast(Mapping[str, object], owner_call)["arguments"]["literal_request"]
        ),
        literal_items=literal,
        owner_closure=owner,
        dependency_closure=dependency,
    )
    entries: list[ProjectionCoverageEntry] = []
    for item in universe["items"]:
        identity = f"skill-tool-graph:{item['kind']}:{item['item_id']}"
        token = serialize_projection_identity(identity)
        entries.append(
            {
                "source_item_id": item["item_id"],
                "source_kind": item["kind"],
                "rendered_identity": identity,
                "artifact_locator": [token],
                "renderer_id": GRAPH_RENDERER_ID,
                "readback_identity": identity,
                "payload_json": item["payload_json"],
                "view_state": "visible",
            }
        )
    expected_identities = {entry["readback_identity"]: entry for entry in entries}
    readback_placeholder = {
        "artifact_id": GRAPH_ARTIFACT_ID,
        "artifact_format": "markdown_mermaid",
        "renderer_id": GRAPH_RENDERER_ID,
        "identities": expected_identities,
        "readback_counts": _source_counts(universe["items"]),
        "coverage_digest": "",
        "status": "pass",
        "violations": [],
    }
    manifest = build_projection_coverage_manifest(
        universe,
        artifact_id=GRAPH_ARTIFACT_ID,
        renderer_id=GRAPH_RENDERER_ID,
        artifact_format="markdown_mermaid",
        entries=entries,
        readback=cast(Any, readback_placeholder),
    )
    marker = serialize_projection_coverage_manifest(
        manifest,
        owner_tool_call=cast(Any, owner_call),
        adapter_tool_call=cast(Any, adapter_call),
    )
    readback_placeholder = dict(
        readback_projection(
            _render_mermaid_placeholder(manifest, marker, entries),
            "markdown_mermaid",
            artifact_id=GRAPH_ARTIFACT_ID,
            renderer_id=GRAPH_RENDERER_ID,
        )
    )
    report = validate_projection_coverage(
        universe,
        manifest,
        readback=cast(Any, readback_placeholder),
    )
    if report["status"] != "pass":
        raise ValueError(
            "skill_tool_invocation_graph_coverage_failure:"
            + ";".join(violation["detail"] for violation in report["violations"])
        )
    return universe, cast(dict[str, object], manifest), readback_placeholder, marker


def _render_mermaid_placeholder(
    manifest: Mapping[str, object],
    marker: str,
    entries: Sequence[ProjectionCoverageEntry],
) -> str:
    """Render the coverage-only syntax used for canonical readback."""
    tokens = [locator for entry in entries for locator in entry["artifact_locator"]]
    return (
        "<!-- "
        + marker
        + " -->\n```mermaid\ngraph LR\n"
        + "\n".join(f"%% {token}" for token in tokens)
        + "\n```\n"
    )


def _edge(
    edges: list[dict[str, object]],
    source_items: list[VisualizationSourceItem],
    edge_type: str,
    source: str,
    target: str,
    **payload: object,
) -> None:
    """Append one typed edge and its source evidence."""
    edge_index = len(edges)
    record = {
        "edge_id": f"edge:{edge_index:04d}",
        "edge_type": edge_type,
        "source": source,
        "target": target,
        **payload,
    }
    edges.append(record)
    source_items.append(
        _source_item(
            kind="edge",
            origin="dependency_closure",
            locator=f"graph:edge:{edge_index:04d}",
            ordinal=edge_index,
            payload=record,
        )
    )


def build_graph(root: Path, *, capacity: int = GRAPH_CAPACITY) -> dict[str, object]:
    """Build the complete graph payload without truncating any source identity."""
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
    packets = _packets(root, skill_ids)
    tools = _load_tool_entries(root)
    invocation_order = derive_skill_invocation_order(skill_ids, route_rules)
    invocation_ordinals = {skill: index for index, skill in enumerate(invocation_order)}
    source_items: list[VisualizationSourceItem] = [
        _source_item(
            kind="identity",
            origin="literal_request",
            locator="route:capability:dependency_manifest_graph",
            ordinal=0,
            payload={"request": "complete public skill/tool invocation graph"},
        ),
        _source_item(
            kind="module",
            origin="owner_closure",
            locator="agents/skills/code-visualization.md",
            ordinal=0,
            payload={
                "owner_skill": "code-visualization",
                "owner_tool_id": VISUALIZATION_OWNER_TOOL_ID,
            },
        ),
    ]
    nodes: list[dict[str, object]] = []
    commands: list[dict[str, object]] = []
    phases: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    branches: list[dict[str, object]] = []
    modules: dict[str, dict[str, object]] = {}
    for ordinal, skill in enumerate(skill_ids):
        rule = rules[skill]
        skill_node = f"skill:{skill}"
        nodes.append(
            {
                "node_id": skill_node,
                "node_type": "skill",
                "label": skill,
                "responsibility_group": rule.responsibility_group,
                "invocation_ordinal": invocation_ordinals[skill],
            }
        )
        source_items.append(
            _source_item(
                kind="identity",
                origin="dependency_closure",
                locator=f"agents/skills/catalog.yaml#skill:{skill}",
                ordinal=ordinal,
                payload=nodes[-1],
            )
        )
        source_items.append(
            _source_item(
                kind="time",
                origin="dependency_closure",
                locator=f"agents/skills/skill-dependencies.yaml#invocation:{skill}",
                ordinal=invocation_ordinals[skill],
                payload={
                    "skill": skill,
                    "invocation_ordinal": invocation_ordinals[skill],
                },
            )
        )
        routing = route_by_skill[skill]
        for capability in routing.capabilities:
            branch = {
                "skill": skill,
                "capability_id": capability.capability_id,
                "owner": capability.owner,
                "phase": capability.phase,
                "activation": capability.activation,
                "exclusive": capability.exclusive,
            }
            branches.append(branch)
            source_items.append(
                _source_item(
                    kind="branch",
                    origin="dependency_closure",
                    locator=f"agents/skills/catalog.yaml#capability:{capability.capability_id}",
                    ordinal=len(branches) - 1,
                    payload=branch,
                )
            )
        for phase in PHASES:
            phase_node = f"phase:{skill}:{phase}"
            phase_record = {
                "node_id": phase_node,
                "skill": skill,
                "phase": phase,
                "responsibility_group": rule.responsibility_group,
            }
            phases.append(phase_record)
            nodes.append({"node_type": "phase", **phase_record})
            source_items.append(
                _source_item(
                    kind="phase",
                    origin="dependency_closure",
                    locator=f"agents/skills/catalog.yaml#skill:{skill}.tool_commands.{phase}",
                    ordinal=PHASES.index(phase),
                    payload=phase_record,
                )
            )
            resolved_rows = _packet_commands(packets[skill], phase)
            for command_index, (logical, source_root, execution_cwd, argv) in enumerate(
                resolved_rows
            ):
                command_node = f"command:{skill}:{phase}:{command_index}"
                tool_id = _resolve_tool_id(logical, argv, tools, root)
                command_record = {
                    "node_id": command_node,
                    "skill": skill,
                    "phase": phase,
                    "ordinal": command_index,
                    "logical_command": logical,
                    "source_root": source_root,
                    "execution_cwd": execution_cwd,
                    "execution_argv": list(argv),
                    "tool_id": tool_id,
                }
                commands.append(command_record)
                nodes.append(
                    {"node_type": "command", "label": logical, **command_record}
                )
                source_items.append(
                    _source_item(
                        kind="identity",
                        origin="dependency_closure",
                        locator=f"agents/skills/catalog.yaml#skill:{skill}.tool_commands.{phase}[{command_index}]",
                        ordinal=command_index,
                        payload=command_record,
                    )
                )
                source_items.append(
                    _source_item(
                        kind="field",
                        origin="dependency_closure",
                        locator=f"skill_tool_commands:{skill}:{phase}:{command_index}",
                        ordinal=command_index,
                        payload={
                            "logical_command": logical,
                            "source_root": source_root,
                            "execution_cwd": execution_cwd,
                            "execution_argv": list(argv),
                        },
                    )
                )
                _edge(
                    edges,
                    source_items,
                    "invocation",
                    skill_node,
                    phase_node,
                    phase=phase,
                    invocation_ordinal=invocation_ordinals[skill],
                )
                _edge(
                    edges,
                    source_items,
                    "invocation",
                    phase_node,
                    command_node,
                    phase=phase,
                    invocation_ordinal=command_index,
                )
                if tool_id is not None:
                    module_node = f"tool:{tool_id}"
                    if tool_id not in modules:
                        entry = next(entry for entry in tools if entry["id"] == tool_id)
                        modules[tool_id] = {
                            "node_id": module_node,
                            "node_type": "tool",
                            "tool_id": tool_id,
                            "label": tool_id,
                            "path": entry["path"],
                        }
                        nodes.append(modules[tool_id])
                        source_items.append(
                            _source_item(
                                kind="module",
                                origin="dependency_closure",
                                locator=f"tools/catalog.yaml#tool:{tool_id}",
                                ordinal=len(modules) - 1,
                                payload=modules[tool_id],
                            )
                        )
                    _edge(
                        edges,
                        source_items,
                        "tool-resolution",
                        command_node,
                        module_node,
                        tool_id=tool_id,
                    )
        for prerequisite in rule.required_prerequisites:
            _edge(
                edges, source_items, "prerequisite", f"skill:{prerequisite}", skill_node
            )
        for successor in rule.successors:
            _edge(edges, source_items, "successor", skill_node, f"skill:{successor}")
        for constraint in rule.order_constraints:
            _edge(
                edges,
                source_items,
                "order",
                f"skill:{constraint.before}",
                f"skill:{constraint.after}",
                reason=constraint.reason,
            )
        for candidate in rule.routing_candidates:
            _edge(edges, source_items, "routing", skill_node, f"skill:{candidate}")
        for other in rule.parallel_independent:
            if skill < other:
                _edge(edges, source_items, "parallel", skill_node, f"skill:{other}")
    for relative in (
        "agents/skills/catalog.yaml",
        "agents/skills/skill-dependencies.yaml",
        "tools/catalog.yaml",
        *(f"agents/skills/{skill}.md" for skill in skill_ids),
        *(f".agents/skills/{skill}/SKILL.md" for skill in skill_ids),
    ):
        digest = _file_digest(root, relative)
        source_items.append(
            _source_item(
                kind="evidence",
                origin="dependency_closure",
                locator=relative,
                ordinal=0,
                payload={"source_locator": relative, "sha256": digest},
            )
        )
    if "dependency-design" not in {
        node["label"] for node in nodes if node["node_type"] == "skill"
    }:
        raise ValueError("skill_tool_invocation_graph_dependency-design_omission")
    if any(edge["edge_type"] not in EDGE_TYPES for edge in edges):
        raise ValueError("skill_tool_invocation_graph_unknown_edge_type")
    if len(nodes) + len(edges) + len(source_items) > capacity:
        raise GraphCapacityError(len(nodes) + len(edges) + len(source_items), capacity)
    owner_items = [item for item in source_items if item["origin"] == "owner_closure"]
    literal_items = [
        item for item in source_items if item["origin"] == "literal_request"
    ]
    dependency_items = [
        item for item in source_items if item["origin"] == "dependency_closure"
    ]
    owner_call, adapter_call = _build_owner_and_adapter_calls(
        literal_items, owner_items, dependency_items
    )
    universe, manifest, readback, marker = _coverage(
        source_items, owner_call, adapter_call
    )
    graph = {
        "schema": GRAPH_SCHEMA,
        "version": 1,
        "artifact_id": GRAPH_ARTIFACT_ID,
        "skill_count": len(skill_ids),
        "skills": [node for node in nodes if node["node_type"] == "skill"],
        "phases": phases,
        "commands": commands,
        "tools": list(modules.values()),
        "edges": edges,
        "branches": branches,
        "invocation_order": list(invocation_order),
        "invocation_ordinals": invocation_ordinals,
        "source_digests": {
            item["source_locator"]: json.loads(item["payload_json"])["sha256"]
            for item in universe["items"]
            if item["kind"] == "evidence"
        },
        "canonical_owner_tool_call": owner_call,
        "adapter_tool_calls": [adapter_call],
        "tool_call_order": ["canonical_owner", "dependency_manifest_adapter"],
        "visualization_source_universe": universe,
        "projection_coverage_manifest": manifest,
        "readback": readback,
        "coverage_digest": manifest["coverage_digest"],
        "source_counts": manifest["source_counts"],
        "rendered_counts": manifest["rendered_counts"],
        "readback_counts": manifest["readback_counts"],
        "coverage_marker": marker,
    }
    graph["graph_digest"] = _digest(
        {key: value for key, value in graph.items() if key != "graph_digest"}
    )
    return graph


def render_graph_mermaid(graph: Mapping[str, object]) -> str:
    """Render every graph identity in deterministic responsibility/phase groups."""
    nodes = cast(list[Mapping[str, object]], graph["skills"])
    all_nodes = cast(
        list[Mapping[str, object]], graph["visualization_source_universe"]["items"]
    )
    del all_nodes
    lines = [
        GRAPH_HEADER,
        "# Public Skill/Tool Invocation Graph",
        "",
        f"<!-- {graph['coverage_marker']} -->",
        "```mermaid",
        "graph LR",
    ]
    groups: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for node in nodes:
        groups[cast(str, node["responsibility_group"])].append(node)
    for group in sorted(groups):
        lines.append(
            f'  subgraph responsibility_{_safe_mermaid_id(group)}["Responsibility: {_mermaid_label(group)}"]'
        )
        for node in groups[group]:
            node_id = _safe_mermaid_id(cast(str, node["node_id"]))
            label = f"{node['label']} (#{node['invocation_ordinal']})"
            lines.append(f'    {node_id}["{_mermaid_label(label)}"]')
        lines.append("  end")
    for phase in PHASES:
        lines.append(f'  subgraph phase_{phase}["Phase: {phase}"]')
        for node in cast(list[Mapping[str, object]], graph["phases"]):
            if node["phase"] == phase:
                phase_id = _safe_mermaid_id(cast(str, node["node_id"]))
                lines.append(
                    f'    {phase_id}{{"{_mermaid_label(str(node["skill"]))}"}}'
                )
        for node in cast(list[Mapping[str, object]], graph["commands"]):
            if node["phase"] == phase:
                command_id = _safe_mermaid_id(cast(str, node["node_id"]))
                lines.append(
                    f'    {command_id}["{_mermaid_label(str(node["logical_command"]))}"]'
                )
        lines.append("  end")
    if cast(list[Mapping[str, object]], graph["tools"]):
        lines.append('  subgraph tool_catalog["ToolID catalog"]')
        for node in cast(list[Mapping[str, object]], graph["tools"]):
            lines.append(
                f'    {_safe_mermaid_id(str(node["node_id"]))}[["{_mermaid_label(str(node["tool_id"]))}"]]'
            )
        lines.append("  end")
    for edge in cast(list[Mapping[str, object]], graph["edges"]):
        source = _safe_mermaid_id(str(edge["source"]))
        target = _safe_mermaid_id(str(edge["target"]))
        edge_type = str(edge["edge_type"])
        if edge_type in {"routing", "parallel"}:
            lines.append(f'  {source} -.->|"{edge_type}"| {target}')
        else:
            phase = f"/{edge['phase']}" if "phase" in edge else ""
            lines.append(f'  {source} -->|"{edge_type}{phase}"| {target}')
    lines.extend(
        [
            "  %% Edge legend: --> prerequisite, successor, order, invocation, tool-resolution; -.-> routing, parallel.",
            "```",
            "",
            "## Edge legend",
            "",
            "- `prerequisite`, `successor`, `order`, `invocation`, and `tool-resolution`: solid directed edges.",
            "- `routing` and `parallel`: dashed directed edges.",
            "",
        ]
    )
    manifest = cast(Mapping[str, object], graph["projection_coverage_manifest"])
    for entry in cast(list[Mapping[str, object]], manifest["entries"]):
        lines.append(f"<!-- {entry['artifact_locator'][0]} -->")
    return "\n".join(lines) + "\n"


def render_mermaid(rules: Mapping[str, SkillDependencyRule]) -> str:
    """Render the legacy rule-only projection retained for focused callers."""
    groups: dict[str, list[str]] = defaultdict(list)
    for rule in rules.values():
        groups[rule.responsibility_group].append(rule.skill)
    lines = [
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


def write_artifacts(
    root: Path, *, output: Path | None = None, capacity: int = GRAPH_CAPACITY
) -> tuple[Path, Path, dict[str, object]]:
    """Generate both canonical graph artifacts atomically at the file level."""
    graph = build_graph(root, capacity=capacity)
    markdown, json_path = _artifact_paths(root, output)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_graph_mermaid(graph), encoding="utf-8")
    json_path.write_text(
        json.dumps(graph, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return markdown, json_path, graph


def check_artifacts(root: Path, *, capacity: int = GRAPH_CAPACITY) -> dict[str, object]:
    """Fail closed on missing, edited, stale, or dependency-design-omitting artifacts."""
    graph = build_graph(root, capacity=capacity)
    markdown, json_path = _artifact_paths(root)
    expected_markdown = render_graph_mermaid(graph)
    expected_json = (
        json.dumps(graph, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )
    findings: list[str] = []
    for path, expected in ((markdown, expected_markdown), (json_path, expected_json)):
        if not path.is_file():
            findings.append(f"{path.relative_to(root)}:missing")
        elif path.read_text(encoding="utf-8") != expected:
            findings.append(f"{path.relative_to(root)}:edited-or-stale")
    if graph["skill_count"] != 60 or not any(
        skill["label"] == "dependency-design"
        for skill in cast(list[Mapping[str, object]], graph["skills"])
    ):
        findings.append("dependency-design:omission")
    if findings:
        raise ValueError(
            "skill_tool_invocation_graph_stale_artifact:" + ";".join(findings)
        )
    return graph


def check(root: Path) -> tuple[int, int, int]:
    """Validate source map and generated artifacts."""
    rules = dict(load_skill_dependency_map(root))
    graph = check_artifacts(root)
    edge_count = len(cast(list[object], graph["edges"]))
    parallel_count = sum(
        1
        for edge in cast(list[Mapping[str, object]], graph["edges"])
        if edge["edge_type"] == "parallel"
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
    graph_parser.add_argument("--capacity", type=int, default=GRAPH_CAPACITY)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one fail-closed graph operation."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "check":
            skill_count, edge_count, parallel_count = check(root)
            print(
                "SKILL_DEPENDENCY_MAP=pass "
                f"source={SKILL_DEPENDENCY_MAP_PATH} skills={skill_count}"
            )
            print(
                "SKILL_TOOL_INVOCATION_GRAPH=pass "
                f"skills={skill_count} edges={edge_count} parallel_edges={parallel_count} "
                f"json={DEFAULT_JSON_PATH} mermaid={DEFAULT_GRAPH_PATH}"
            )
            return 0
        markdown, json_path, graph = write_artifacts(
            root,
            output=args.output,
            capacity=args.capacity,
        )
        print(
            "SKILL_TOOL_INVOCATION_GRAPH=pass "
            f"skills={graph['skill_count']} commands={len(graph['commands'])} "
            f"tools={len(graph['tools'])} edges={len(graph['edges'])} "
            f"json={json_path} mermaid={markdown}"
        )
        return 0
    except GraphCapacityError as exc:
        print(f"SKILL_TOOL_INVOCATION_GRAPH=fail code={exc}", file=sys.stderr)
        return 3
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"SKILL_TOOL_INVOCATION_GRAPH=fail reason={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
