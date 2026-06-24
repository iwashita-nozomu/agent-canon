#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Renders dependency manifest graph TSV artifacts into Markdown and DOT reports.
# upstream implementation ./check_dependency_graph.sh writes dependency graph TSV artifacts.
# upstream design ../../documents/dependency-manifest-design.md defines manifest graph semantics.
# downstream design ../../documents/tools/render_dependency_manifest_graph.md documents report generation.
# downstream implementation ../../tests/agent_tools/test_render_dependency_manifest_graph.py tests graph rendering.
# @dependency-end
"""Render dependency manifest graph reports from graph TSV artifacts."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

GRAPH_TSV_FIELD_COUNT = 4
GRAPH_IR_SCHEMA = "agent_canon.graph_ir.v1"
HIGH_DEGREE_NODE_LIMIT = 20
MAX_REPORTED_BROKEN_TARGETS = 50
MAX_REPORTED_CYCLES = 50
STATIC_NODE_W = 180
STATIC_NODE_H = 34
STATIC_NODE_COL_GAP = 14
STATIC_NODE_ROW_GAP = 10
STATIC_GROUP_COLUMNS = 3
STATIC_GROUP_GAP_X = 52
STATIC_GROUP_GAP_Y = 48
STATIC_GROUP_PAD_X = 22
STATIC_GROUP_PAD_TOP = 52
STATIC_GROUP_PAD_BOTTOM = 18
STATIC_ZOOM_LEVELS = (
    ("fit", 1.0, "Fit"),
    ("2x", 2.0, "2x"),
    ("4x", 4.0, "4x"),
    ("8x", 8.0, "8x"),
)
TERRITORY_COLORS = (
    "#d8ecf0",
    "#eadff1",
    "#e1ecd6",
    "#f1e4d1",
    "#dbe4f4",
    "#f3dedd",
    "#d8eee4",
    "#e7e1c7",
    "#dde8df",
    "#e2e0f2",
    "#f0e0c8",
    "#d7e6ee",
)


@dataclass(frozen=True)
class Edge:
    """One dependency graph edge."""

    direction: str
    kind: str
    source: str
    target: str


@dataclass(frozen=True)
class ContainmentEdge:
    """One inferred directory containment edge for the graph IR."""

    source: str
    target: str
    parent_path: str
    child_path: str
    child_kind: str


@dataclass(frozen=True)
class GraphReport:
    """Computed graph diagnostics."""

    nodes: tuple[str, ...]
    edges: tuple[Edge, ...]
    cycles: tuple[tuple[str, ...], ...]
    orphan_nodes: tuple[str, ...]
    broken_targets: tuple[str, ...]
    high_degree_nodes: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class GraphInput:
    """Dependency graph TSV input and source checker status."""

    path: Path
    source_returncode: int | None


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--graph-tsv", help="Existing dependency graph TSV to render.")
    parser.add_argument("--ir-out", help="Write repo-local graph IR JSON to this path.")
    parser.add_argument("--markdown-out", help="Write Markdown summary to this path.")
    parser.add_argument("--dot-out", help="Write Graphviz DOT to this path.")
    parser.add_argument("--html-out", help="Write a self-contained HTML graph viewer to this path.")
    parser.add_argument("--title", default="Code Space Dependency Graph", help="HTML report title.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--fail-on-broken", action="store_true", help="Exit non-zero when broken targets exist.")
    return parser


def generate_graph_tsv(root: Path) -> GraphInput:
    """Generate a temporary graph TSV by calling the canonical graph checker."""
    temp = tempfile.NamedTemporaryFile(prefix="dependency-graph-", suffix=".tsv", delete=False)
    temp_path = Path(temp.name)
    temp.close()
    result = subprocess.run(
        [
            "bash",
            "tools/agent_tools/check_dependency_graph.sh",
            "--root",
            str(root),
            "--graph-tsv",
            str(temp_path),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and (not temp_path.exists() or temp_path.stat().st_size == 0):
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr,
        )
    return GraphInput(path=temp_path, source_returncode=result.returncode)


def load_edges(path: Path) -> tuple[Edge, ...]:
    """Load graph TSV edges."""
    edges: list[Edge] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("direction\t"):
            continue
        fields = line.split("\t")
        if len(fields) != GRAPH_TSV_FIELD_COUNT:
            continue
        edges.append(Edge(*fields))
    return tuple(edges)


def repo_path_exists(root: Path, path: str) -> bool:
    """Return whether a dependency target exists or is an external-ish token."""
    if "://" in path or path.startswith("#"):
        return True
    return (root / path).exists()


def is_repo_path_token(path: str) -> bool:
    """Return whether a graph token is a repository path candidate."""
    return bool(path) and "://" not in path and not path.startswith("#")


def directory_id(path: str) -> str:
    """Return the IR node id for a repository directory path."""
    return f"dir:{path}"


def repo_path_parts(path: str) -> tuple[str, ...]:
    """Return normalized relative path parts used for directory inference."""
    stripped = path.strip("/")
    if not stripped or stripped in {".", ".."}:
        return ()
    return tuple(part for part in stripped.split("/") if part and part != ".")


def directory_display(path: str) -> dict[str, str]:
    """Return display labels for an inferred directory node."""
    if path == ".":
        return {"label": ".", "parent": "repository", "full": path}
    return path_display(path)


def directory_containment(
    paths: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[ContainmentEdge, ...]]:
    """Infer directory nodes and containment edges from repository paths."""
    directory_paths: set[str] = set()
    edge_set: set[ContainmentEdge] = set()
    for path in paths:
        if not is_repo_path_token(path):
            continue
        parts = repo_path_parts(path)
        if not parts:
            continue
        directory_paths.add(".")
        parent_dir = "."
        for index in range(1, len(parts)):
            child_dir = "/".join(parts[:index])
            directory_paths.add(child_dir)
            edge_set.add(
                ContainmentEdge(
                    source=directory_id(parent_dir),
                    target=directory_id(child_dir),
                    parent_path=parent_dir,
                    child_path=child_dir,
                    child_kind="directory",
                )
            )
            parent_dir = child_dir
        edge_set.add(
            ContainmentEdge(
                source=directory_id(parent_dir),
                target=path,
                parent_path=parent_dir,
                child_path=path,
                child_kind="repo_path",
            )
        )
    directory_order = tuple(sorted(directory_paths, key=lambda value: (value != ".", value)))
    edge_order = tuple(sorted(edge_set, key=lambda edge: (edge.source, edge.target, edge.child_kind)))
    return directory_order, edge_order


def detect_cycles(
    edges: tuple[Edge, ...],
    *,
    max_cycles: int = MAX_REPORTED_CYCLES,
) -> tuple[tuple[str, ...], ...]:
    """Detect simple cycles in source-target graph."""
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge.source].add(edge.target)
    cycles: set[tuple[str, ...]] = set()
    visiting: list[str] = []
    state: dict[str, str] = {}

    def visit(node: str) -> None:
        if len(cycles) >= max_cycles:
            return
        node_state = state.get(node)
        if node_state == "done":
            return
        if node in visiting:
            cycle = visiting[visiting.index(node):] + [node]
            canonical = min(
                tuple(cycle[index:-1] + cycle[:index] + [cycle[index]])
                for index in range(len(cycle) - 1)
            )
            cycles.add(canonical)
            return
        state[node] = "visiting"
        visiting.append(node)
        for target in sorted(adjacency.get(node, ())):
            visit(target)
            if len(cycles) >= max_cycles:
                break
        visiting.pop()
        state[node] = "done"

    for node in sorted(adjacency):
        visit(node)
        if len(cycles) >= max_cycles:
            break
    return tuple(sorted(cycles))


def build_report(root: Path, edges: tuple[Edge, ...]) -> GraphReport:
    """Build graph diagnostics."""
    node_set = {edge.source for edge in edges} | {edge.target for edge in edges}
    degree = Counter[str]()
    incoming = Counter[str]()
    outgoing = Counter[str]()
    for edge in edges:
        degree[edge.source] += 1
        degree[edge.target] += 1
        outgoing[edge.source] += 1
        incoming[edge.target] += 1
    orphan_nodes = tuple(sorted(node for node in node_set if incoming[node] == 0 and outgoing[node] == 0))
    broken = tuple(sorted(node for node in node_set if not repo_path_exists(root, node)))
    high_degree = tuple(
        sorted(degree.items(), key=lambda item: (-item[1], item[0]))[:HIGH_DEGREE_NODE_LIMIT]
    )
    return GraphReport(
        nodes=tuple(sorted(node_set)),
        edges=edges,
        cycles=detect_cycles(edges),
        orphan_nodes=orphan_nodes,
        broken_targets=broken,
        high_degree_nodes=high_degree,
    )


def render_markdown(report: GraphReport) -> str:
    """Render Markdown summary."""
    directory_nodes, containment_edges = directory_containment(report.nodes)
    lines = [
        "# Dependency Manifest Graph Report",
        "",
        f"- nodes: {len(report.nodes)}",
        f"- edges: {len(report.edges)}",
        f"- directory nodes: {len(directory_nodes)}",
        f"- containment edges: {len(containment_edges)}",
        f"- total IR nodes: {len(report.nodes) + len(directory_nodes)}",
        f"- total IR edges: {len(report.edges) + len(containment_edges)}",
        f"- cycles: {len(report.cycles)}",
        f"- broken targets: {len(report.broken_targets)}",
        "",
        "## High Degree Nodes",
        "",
        "| Path | Degree |",
        "| --- | ---: |",
    ]
    lines.extend(
        f"| `{path}` | {degree} |"
        for path, degree in report.high_degree_nodes[:HIGH_DEGREE_NODE_LIMIT]
    )
    lines.extend(["", "## Cycles", ""])
    if report.cycles:
        lines.extend(f"- {' -> '.join(cycle)}" for cycle in report.cycles[:HIGH_DEGREE_NODE_LIMIT])
    else:
        lines.append("- none")
    lines.extend(["", "## Broken Targets", ""])
    if report.broken_targets:
        lines.extend(f"- `{path}`" for path in report.broken_targets[:MAX_REPORTED_BROKEN_TARGETS])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def dot_id(value: str) -> str:
    """Escape a DOT string id."""
    return json.dumps(value)


def render_dot(report: GraphReport) -> str:
    """Render Graphviz DOT."""
    lines = ["digraph dependency_manifest {", "  rankdir=LR;"]
    for node in report.nodes:
        lines.append(f"  {dot_id(node)};")
    for edge in report.edges:
        label = edge.kind if edge.direction == "upstream" else f"{edge.direction}:{edge.kind}"
        lines.append(f"  {dot_id(edge.source)} -> {dot_id(edge.target)} [label={dot_id(label)}];")
    lines.append("}")
    return "\n".join(lines) + "\n"


def path_group(path: str) -> str:
    """Return the high-level code-space group for a node path."""
    if "://" in path:
        return "external"
    if path.startswith("#"):
        return "anchor"
    if path.startswith("vendor/agent-canon/"):
        return "vendor/agent-canon"
    if path.startswith("vendor/model-artifact-canon/"):
        return "vendor/model-artifact-canon"
    if "/" not in path:
        return "root"
    first = path.split("/", 1)[0]
    return first or "root"


def compact_middle(value: str, *, limit: int = 42) -> str:
    """Return a compact path-like label preserving both ends."""
    if len(value) <= limit:
        return value
    if limit <= 5:
        return value[:limit]
    head = max(8, (limit - 5) // 2)
    tail = max(8, limit - head - 5)
    return value[:head] + "..." + value[-tail:]


def path_display(path: str) -> dict[str, str]:
    """Return display labels while preserving full path separately."""
    group = path_group(path)
    if "://" in path:
        scheme, rest = path.split("://", 1)
        return {
            "label": compact_middle(f"{scheme}://{rest}", limit=28),
            "parent": "external",
            "full": path,
        }
    if path.startswith("#"):
        return {"label": compact_middle(path, limit=28), "parent": "anchor", "full": path}
    stripped = path.rstrip("/")
    parts = stripped.split("/") if stripped else [path]
    label = parts[-1] or path
    parent = "/".join(parts[:-1]) if len(parts) > 1 else group
    if parent.startswith(f"{group}/"):
        parent = f"{group}/{parent[len(group) + 1:]}"
    return {
        "label": compact_middle(label, limit=32),
        "parent": compact_middle(parent or group, limit=42),
        "full": path,
    }


def graph_fingerprint(edges: tuple[Edge, ...]) -> str:
    """Return a stable content fingerprint for dependency edges."""
    return hashlib.sha256(
        "\n".join(
            f"{edge.direction}\t{edge.kind}\t{edge.source}\t{edge.target}"
            for edge in edges
        ).encode("utf-8")
    ).hexdigest()


def dependency_node_record(
    node: str,
    *,
    incoming: Counter[str],
    outgoing: Counter[str],
    broken_targets: set[str],
) -> dict[str, object]:
    """Return an IR node record for one dependency graph artifact path."""
    display = path_display(node)
    group = path_group(node)
    degree = incoming[node] + outgoing[node]
    return {
        "id": node,
        "document_id": "dependency-manifest-graph",
        "layer": "artifact",
        "kind": "repo_path",
        "label": display["label"],
        "text": node,
        "source_start": 0,
        "source_end": 0,
        "confidence": 1.0,
        "group": group,
        "display": display,
        "source_locator": node,
        "incoming": incoming[node],
        "outgoing": outgoing[node],
        "degree": degree,
        "broken": node in broken_targets,
        "payload_json": {
            "path": node,
            "group": group,
            "display": display,
            "exists": node not in broken_targets,
            "metrics": {
                "incoming": incoming[node],
                "outgoing": outgoing[node],
                "degree": degree,
            },
        },
    }


def directory_node_record(
    directory_path: str,
    *,
    incoming: Counter[str],
    outgoing: Counter[str],
) -> dict[str, object]:
    """Return an IR node record for one inferred repository directory."""
    display = directory_display(directory_path)
    node_id = directory_id(directory_path)
    group = path_group(directory_path) if directory_path != "." else "root"
    degree = incoming[node_id] + outgoing[node_id]
    return {
        "id": node_id,
        "document_id": "dependency-manifest-graph",
        "layer": "artifact",
        "kind": "directory",
        "label": display["label"],
        "text": directory_path,
        "source_start": 0,
        "source_end": 0,
        "confidence": 1.0,
        "group": group,
        "display": display,
        "source_locator": directory_path,
        "incoming": incoming[node_id],
        "outgoing": outgoing[node_id],
        "degree": degree,
        "broken": False,
        "payload_json": {
            "path": directory_path,
            "group": group,
            "display": display,
            "exists": True,
            "metrics": {
                "incoming": incoming[node_id],
                "outgoing": outgoing[node_id],
                "degree": degree,
            },
        },
    }


def dependency_edge_records(edges: tuple[Edge, ...]) -> list[dict[str, object]]:
    """Return IR edge records for dependency graph TSV rows."""
    return [
        {
            "id": f"edge:{index:06d}",
            "document_id": "dependency-manifest-graph",
            "layer": "artifact",
            "kind": edge.kind,
            "relation": edge.direction,
            "source": edge.source,
            "target": edge.target,
            "label": edge.kind if edge.direction == "upstream" else f"{edge.direction}:{edge.kind}",
            "confidence": 1.0,
            "payload_json": asdict(edge) | {"row": index},
        }
        for index, edge in enumerate(edges)
    ]


def containment_edge_records(edges: tuple[ContainmentEdge, ...]) -> list[dict[str, object]]:
    """Return IR edge records for inferred directory containment."""
    return [
        {
            "id": f"contains:{index:06d}",
            "document_id": "dependency-manifest-graph",
            "layer": "artifact",
            "kind": "contains",
            "relation": "contains",
            "source": edge.source,
            "target": edge.target,
            "label": "contains",
            "confidence": 1.0,
            "payload_json": {
                "source": edge.source,
                "target": edge.target,
                "parentPath": edge.parent_path,
                "childPath": edge.child_path,
                "childKind": edge.child_kind,
            },
        }
        for index, edge in enumerate(edges)
    ]


def graph_ir(report: GraphReport, *, source_path: Path | None = None) -> dict[str, object]:
    """Return the repo-local graph intermediate representation."""
    incoming = Counter[str]()
    outgoing = Counter[str]()
    for edge in report.edges:
        outgoing[edge.source] += 1
        incoming[edge.target] += 1
    directory_paths, containment = directory_containment(report.nodes)
    containment_incoming = Counter[str]()
    containment_outgoing = Counter[str]()
    for edge in containment:
        containment_outgoing[edge.source] += 1
        containment_incoming[edge.target] += 1
    broken_targets = set(report.broken_targets)
    nodes = [
        dependency_node_record(node, incoming=incoming, outgoing=outgoing, broken_targets=broken_targets)
        for node in report.nodes
    ]
    nodes.extend(
        directory_node_record(path, incoming=containment_incoming, outgoing=containment_outgoing)
        for path in directory_paths
    )
    dependency_edges = dependency_edge_records(report.edges)
    containment_edges = containment_edge_records(containment)
    edges = dependency_edges + containment_edges
    return {
        "schema": GRAPH_IR_SCHEMA,
        "version": 1,
        "id": f"dependency-manifest:{graph_fingerprint(report.edges)[:16]}",
        "producer": "tools/agent_tools/render_dependency_manifest_graph.py",
        "source": {
            "kind": "dependency_manifest_graph_tsv",
            "path": str(source_path) if source_path else None,
            "authority": "tools/agent_tools/check_dependency_graph.sh --graph-tsv",
        },
        "summary": {
            "nodes": len(report.nodes),
            "edges": len(report.edges),
            "directoryNodes": len(directory_paths),
            "containmentEdges": len(containment),
            "totalNodes": len(nodes),
            "totalEdges": len(edges),
            "cycles": len(report.cycles),
            "brokenTargets": len(report.broken_targets),
        },
        "nodes": nodes,
        "edges": edges,
        "directions": sorted({edge.direction for edge in report.edges}),
        "kinds": sorted({edge.kind for edge in report.edges}),
        "highDegree": [
            {"id": path, "degree": degree}
            for path, degree in report.high_degree_nodes
        ],
        "cycles": [list(cycle) for cycle in report.cycles],
        "brokenTargets": list(report.broken_targets),
        "views": {
            "html_workbench": {
                "projection": "browser_graph_workbench",
                "primary_visual": "code_territory_map",
                "secondary_visual": "dense_group_static_graph",
            },
            "code_territory_map": {
                "projection": "group_voronoi",
                "group_field": "group",
                "edge_projection": "inter_group_dependency_edges",
            },
            "dense_group_static_graph": {
                "projection": "group_packed_nodes",
                "node_label": "display.label",
                "node_sub_label": "display.parent",
            },
        },
    }


def graph_payload(report: GraphReport) -> dict[str, object]:
    """Return the JSON-serializable graph payload used by the HTML viewer."""
    ir = graph_ir(report)
    dependency_nodes = [node for node in ir["nodes"] if node["kind"] == "repo_path"]
    directory_nodes = [node for node in ir["nodes"] if node["kind"] == "directory"]
    dependency_edges = [edge for edge in ir["edges"] if edge["relation"] != "contains"]
    containment_edges = [edge for edge in ir["edges"] if edge["relation"] == "contains"]
    nodes = [
        {
            "id": str(node["id"]),
            "group": str(node["group"]),
            "label": str(node["display"]["label"]),
            "parentLabel": str(node["display"]["parent"]),
            "incoming": int(node["incoming"]),
            "outgoing": int(node["outgoing"]),
            "degree": int(node["degree"]),
            "broken": bool(node["broken"]),
        }
        for node in dependency_nodes
    ]
    return {
        "summary": ir["summary"],
        "nodes": nodes,
        "edges": [edge["payload_json"] for edge in dependency_edges],
        "directoryTree": {
            "nodes": [
                {
                    "id": str(node["id"]),
                    "path": str(node["payload_json"]["path"]),
                    "group": str(node["group"]),
                    "label": str(node["display"]["label"]),
                    "parentLabel": str(node["display"]["parent"]),
                    "degree": int(node["degree"]),
                }
                for node in directory_nodes
            ],
            "edges": [edge["payload_json"] for edge in containment_edges],
        },
        "directions": ir["directions"],
        "kinds": ir["kinds"],
        "highDegree": ir["highDegree"],
        "cycles": ir["cycles"],
        "brokenTargets": ir["brokenTargets"],
        "views": ir["views"],
    }


def render_ir(report: GraphReport, *, source_path: Path) -> str:
    """Render the repo-local graph IR JSON."""
    return json.dumps(graph_ir(report, source_path=source_path), indent=2, sort_keys=True) + "\n"


def script_json(payload: dict[str, object]) -> str:
    """Return JSON that is safe inside a script-like HTML data block."""
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def short_html_label(value: str, *, limit: int = 46) -> str:
    """Return a bounded display label for static graph text."""
    return value if len(value) <= limit else f"{value[:limit - 3]}..."


def static_group_node_columns(count: int) -> int:
    """Return the number of node columns to use inside one group block."""
    if count >= 72:
        return 4
    if count >= 24:
        return 3
    return 2


def static_graph_layout(
    nodes: list[dict[str, object]],
) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int, int, int]], int, int]:
    """Pack graph nodes into dense group blocks."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for node in nodes:
        grouped[str(node["group"])].append(node)
    for group_nodes in grouped.values():
        group_nodes.sort(key=lambda item: str(item["id"]))

    max_group_width = (
        STATIC_GROUP_PAD_X * 2
        + 4 * STATIC_NODE_W
        + 3 * STATIC_NODE_COL_GAP
    )
    column_width = max_group_width + STATIC_GROUP_GAP_X
    column_heights = [0] * STATIC_GROUP_COLUMNS
    positions: dict[str, tuple[int, int]] = {}
    group_boxes: dict[str, tuple[int, int, int, int]] = {}

    group_order = sorted(grouped, key=lambda group: (-len(grouped[group]), group))
    for group in group_order:
        group_nodes = grouped[group]
        node_columns = static_group_node_columns(len(group_nodes))
        node_rows = (len(group_nodes) + node_columns - 1) // node_columns
        group_width = (
            STATIC_GROUP_PAD_X * 2
            + node_columns * STATIC_NODE_W
            + (node_columns - 1) * STATIC_NODE_COL_GAP
        )
        group_height = (
            STATIC_GROUP_PAD_TOP
            + node_rows * STATIC_NODE_H
            + max(0, node_rows - 1) * STATIC_NODE_ROW_GAP
            + STATIC_GROUP_PAD_BOTTOM
        )
        column = min(range(STATIC_GROUP_COLUMNS), key=lambda index: column_heights[index])
        group_x = 36 + column * column_width
        group_y = 42 + column_heights[column]
        column_heights[column] += group_height + STATIC_GROUP_GAP_Y
        group_boxes[group] = (group_x, group_y, group_width, group_height)

        for index, node in enumerate(group_nodes):
            node_column = index % node_columns
            node_row = index // node_columns
            node_x = group_x + STATIC_GROUP_PAD_X + node_column * (
                STATIC_NODE_W + STATIC_NODE_COL_GAP
            )
            node_y = group_y + STATIC_GROUP_PAD_TOP + node_row * (
                STATIC_NODE_H + STATIC_NODE_ROW_GAP
            )
            positions[str(node["id"])] = (node_x, node_y)

    width = 72 + STATIC_GROUP_COLUMNS * column_width - STATIC_GROUP_GAP_X
    height = max(620, max(column_heights, default=0) + 48)
    return positions, group_boxes, width, height


def static_graph_dimensions_from_nodes(nodes: list[dict[str, object]]) -> tuple[int, int]:
    """Return static SVG layout dimensions for rendered node payloads."""
    _positions, _group_boxes, width, height = static_graph_layout(nodes)
    return width, height


def halfplane_score(point: tuple[float, float], seed: tuple[float, float], other: tuple[float, float]) -> float:
    """Return signed distance proxy for seed-nearer half-plane clipping."""
    x, y = point
    sx, sy = seed
    ox, oy = other
    return 2 * x * (ox - sx) + 2 * y * (oy - sy) + sx * sx + sy * sy - ox * ox - oy * oy


def clip_polygon_to_seed(
    polygon: list[tuple[float, float]],
    seed: tuple[float, float],
    other: tuple[float, float],
) -> list[tuple[float, float]]:
    """Clip a polygon to the Voronoi half-plane for one seed."""
    if not polygon:
        return []
    clipped: list[tuple[float, float]] = []
    previous = polygon[-1]
    previous_score = halfplane_score(previous, seed, other)
    previous_inside = previous_score <= 1e-9
    for current in polygon:
        current_score = halfplane_score(current, seed, other)
        current_inside = current_score <= 1e-9
        if current_inside != previous_inside:
            denominator = previous_score - current_score
            ratio = 0.0 if denominator == 0 else previous_score / denominator
            clipped.append(
                (
                    previous[0] + ratio * (current[0] - previous[0]),
                    previous[1] + ratio * (current[1] - previous[1]),
                )
            )
        if current_inside:
            clipped.append(current)
        previous = current
        previous_score = current_score
        previous_inside = current_inside
    return clipped


def polygon_centroid(polygon: list[tuple[float, float]]) -> tuple[float, float]:
    """Return a stable label point for a polygon."""
    if not polygon:
        return (0.0, 0.0)
    return (
        sum(point[0] for point in polygon) / len(polygon),
        sum(point[1] for point in polygon) / len(polygon),
    )


def polygon_path(polygon: list[tuple[float, float]]) -> str:
    """Render an SVG path for a polygon."""
    if not polygon:
        return ""
    first, *rest = polygon
    commands = [f"M {first[0]:.1f} {first[1]:.1f}"]
    commands.extend(f"L {x:.1f} {y:.1f}" for x, y in rest)
    commands.append("Z")
    return " ".join(commands)


def stable_jitter(text: str, *, amplitude: float) -> tuple[float, float]:
    """Return deterministic small jitter for layout seeds."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    x = (int.from_bytes(digest[:4], "big") / 2**32 - 0.5) * amplitude
    y = (int.from_bytes(digest[4:8], "big") / 2**32 - 0.5) * amplitude
    return x, y


def territory_seed_points(
    groups: list[str],
    group_counts: Counter[str],
    *,
    width: int,
    height: int,
) -> dict[str, tuple[float, float]]:
    """Return deterministic Voronoi seed points, with larger groups near center."""
    columns = min(6, max(1, len(groups)))
    rows = (len(groups) + columns - 1) // columns
    spots: list[tuple[float, float]] = []
    for row in range(rows):
        for column in range(columns):
            spots.append(
                (
                    54 + (column + 0.5) * (width - 108) / columns,
                    44 + (row + 0.5) * (height - 88) / rows,
                )
            )
    center = (width / 2, height / 2)
    spots.sort(key=lambda point: (abs(point[0] - center[0]) + abs(point[1] - center[1]), point[1], point[0]))
    group_order = sorted(groups, key=lambda group: (-group_counts[group], group))
    seeds: dict[str, tuple[float, float]] = {}
    for group, spot in zip(group_order, spots):
        jitter_x, jitter_y = stable_jitter(group, amplitude=34)
        seeds[group] = (
            min(width - 24, max(24, spot[0] + jitter_x)),
            min(height - 24, max(24, spot[1] + jitter_y)),
        )
    return seeds


def territory_map_svg(report: GraphReport) -> str:
    """Render a Voronoi-style group territory map with inter-group edges."""
    payload = graph_payload(report)
    nodes = list(payload["nodes"])
    groups = sorted({str(node["group"]) for node in nodes})
    group_counts = Counter(str(node["group"]) for node in nodes)
    group_edges: Counter[tuple[str, str]] = Counter()
    edge_kinds: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    group_by_node = {str(node["id"]): str(node["group"]) for node in nodes}
    for edge in report.edges:
        source_group = group_by_node.get(edge.source, path_group(edge.source))
        target_group = group_by_node.get(edge.target, path_group(edge.target))
        group_edges[(source_group, target_group)] += 1
        edge_kinds[(source_group, target_group)][edge.kind] += 1

    width = 1180
    height = 420
    seeds = territory_seed_points(groups, group_counts, width=width, height=height)
    bounds = [(10.0, 10.0), (width - 10.0, 10.0), (width - 10.0, height - 10.0), (10.0, height - 10.0)]
    cells: dict[str, list[tuple[float, float]]] = {}
    label_points: dict[str, tuple[float, float]] = {}
    for group in groups:
        polygon = list(bounds)
        seed = seeds[group]
        for other_group in groups:
            if other_group == group:
                continue
            polygon = clip_polygon_to_seed(polygon, seed, seeds[other_group])
        cells[group] = polygon
        label_points[group] = polygon_centroid(polygon)

    parts = [
        (
            f'<svg class="territory-map" viewBox="0 0 {width} {height}" '
            'role="img" aria-label="Voronoi-style code territory map">'
        ),
        "<defs>",
        (
            '<marker id="territory-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
            '<path d="M 0 0 L 10 5 L 0 10 z"></path></marker>'
        ),
        "</defs>",
        '<g class="territory-cells">',
    ]
    for index, group in enumerate(sorted(groups, key=lambda item: (-group_counts[item], item))):
        color = TERRITORY_COLORS[index % len(TERRITORY_COLORS)]
        title = html.escape(f"{group}: {group_counts[group]} nodes")
        parts.append(
            f'<path class="territory-cell" fill="{color}" d="{polygon_path(cells[group])}">'
            f"<title>{title}</title></path>"
        )
    parts.append("</g>")
    parts.append('<g class="territory-edges">')
    max_edge_count = max(group_edges.values(), default=1)
    for (source_group, target_group), count in sorted(group_edges.items()):
        if source_group == target_group:
            continue
        source = label_points.get(source_group)
        target = label_points.get(target_group)
        if not source or not target:
            continue
        dominant_kind = edge_kinds[(source_group, target_group)].most_common(1)[0][0]
        title = html.escape(f"{source_group} -> {target_group}: {count} edges")
        width_scale = 1.2 + 4.2 * (count / max_edge_count) ** 0.5
        parts.append(
            f'<path class="territory-edge {html.escape(dominant_kind, quote=True)}" '
            f'stroke-width="{width_scale:.2f}" '
            f'd="M {source[0]:.1f} {source[1]:.1f} L {target[0]:.1f} {target[1]:.1f}">'
            f"<title>{title}</title></path>"
        )
    parts.append("</g>")
    parts.append('<g class="territory-labels">')
    for group in sorted(groups, key=lambda item: (-group_counts[item], item)):
        x, y = label_points[group]
        count = group_counts[group]
        title = html.escape(f"{group}: {count} nodes")
        label = html.escape(short_html_label(group, limit=24))
        parts.append(
            f'<text class="territory-label" x="{x:.1f}" y="{y:.1f}">'
            f"<title>{title}</title>"
            f'<tspan x="{x:.1f}" dy="-3">{label}</tspan>'
            f'<tspan class="sub" x="{x:.1f}" dy="14">{count} nodes</tspan>'
            "</text>"
        )
    parts.append("</g></svg>")
    return "\n".join(parts)


def group_overview_svg(report: GraphReport) -> str:
    """Render the current group-level overview projection."""
    return territory_map_svg(report)


def static_graph_svg(
    report: GraphReport,
    *,
    graph_id: str = "static-graph",
    css_class: str = "static-graph js-graph",
    view_box: tuple[float, float, float, float] | None = None,
    include_data_attrs: bool = True,
    content_id: str | None = "static-graph-content",
) -> str:
    """Render a static SVG overview with every node and edge embedded."""
    payload = graph_payload(report)
    nodes = list(payload["nodes"])
    positions, group_boxes, width, height = static_graph_layout(nodes)
    incoming = {str(node["id"]): int(node["incoming"]) for node in nodes}
    outgoing = {str(node["id"]): int(node["outgoing"]) for node in nodes}
    degree = {str(node["id"]): int(node["degree"]) for node in nodes}
    broken = {str(node["id"]): bool(node["broken"]) for node in nodes}
    if view_box is None:
        view_box = (0, 0, width, height)
    view_box_text = " ".join(f"{value:g}" for value in view_box)
    data_attrs = (
        f' data-base-width="{width}" data-base-height="{height}"'
        if include_data_attrs
        else ""
    )
    content_id_attr = f' id="{content_id}"' if content_id else ""
    parts = [
        (
            f'<svg id="{html.escape(graph_id, quote=True)}" '
            f'class="{html.escape(css_class, quote=True)}" viewBox="{view_box_text}"'
            f"{data_attrs} "
            'role="img" aria-label="Static dependency manifest graph">'
        ),
        "<defs>",
        (
            '<marker id="static-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
            '<path d="M 0 0 L 10 5 L 0 10 z"></path></marker>'
        ),
        "</defs>",
        f'<g{content_id_attr} class="static-graph-content">',
    ]

    parts.append('<g class="static-groups">')
    for group, (x, y, group_width, group_height) in group_boxes.items():
        parts.append(
            f'<g class="static-group-block" transform="translate({x} {y})">'
            f'<rect width="{group_width}" height="{group_height}"></rect>'
            f'<text class="static-group" x="12" y="24">{html.escape(group)}</text>'
            f'<text class="static-group-sub" x="12" y="40">'
            f'{sum(1 for node in nodes if str(node["group"]) == group)} nodes</text></g>'
        )
    parts.append("</g>")

    parts.append('<g class="static-edges">')
    for edge in report.edges:
        source = positions.get(edge.source)
        target = positions.get(edge.target)
        if not source or not target:
            continue
        start_x = source[0] + STATIC_NODE_W
        start_y = source[1] + STATIC_NODE_H / 2
        end_x = target[0]
        end_y = target[1] + STATIC_NODE_H / 2
        curve = max(54, abs(end_x - start_x) / 2)
        title = html.escape(f"{edge.direction}/{edge.kind}: {edge.source} -> {edge.target}")
        parts.append(
            f'<path class="static-edge {html.escape(edge.kind, quote=True)}" '
            f'd="M {start_x:.1f} {start_y:.1f} C {start_x + curve:.1f} {start_y:.1f}, '
            f'{end_x - curve:.1f} {end_y:.1f}, {end_x:.1f} {end_y:.1f}">'
            f"<title>{title}</title></path>"
        )
    parts.append("</g>")

    parts.append('<g class="static-nodes">')
    for node in nodes:
        node_id = str(node["id"])
        x, y = positions[node_id]
        node_class = "static-node broken" if broken[node_id] else "static-node"
        label = html.escape(str(node.get("label", short_html_label(node_id, limit=29))))
        parent_label = str(node.get("parentLabel", path_group(node_id)))
        subtitle = html.escape(f"{short_html_label(parent_label, limit=30)} / d {degree[node_id]}")
        title = html.escape(node_id)
        parts.append(
            f'<g class="{node_class}" transform="translate({x} {y})">'
            f'<rect width="{STATIC_NODE_W}" height="{STATIC_NODE_H}"></rect>'
            f'<text class="label" x="10" y="14">{label}</text>'
            f'<text class="sub" x="10" y="28">{subtitle}</text>'
            f"<title>{title}</title></g>"
        )
    parts.append("</g></g></svg>")
    return "\n".join(parts)


def edge_table_html(report: GraphReport) -> str:
    """Render the complete edge list as an HTML table."""
    rows = [
        "<table>",
        "<thead><tr><th>Direction</th><th>Kind</th><th>Source</th><th>Target</th></tr></thead>",
        "<tbody>",
    ]
    for edge in report.edges:
        rows.append(
            "<tr>"
            f"<td>{html.escape(edge.direction)}</td>"
            f"<td>{html.escape(edge.kind)}</td>"
            f"<td><code>{html.escape(edge.source)}</code></td>"
            f"<td><code>{html.escape(edge.target)}</code></td>"
            "</tr>"
        )
    rows.extend(["</tbody>", "</table>"])
    return "\n".join(rows)


def node_table_html(report: GraphReport) -> str:
    """Render the complete node list as an HTML table."""
    nodes = list(graph_payload(report)["nodes"])
    rows = [
        "<table>",
        "<thead><tr><th>Group</th><th>Name</th><th>Parent</th><th>Path</th><th>In</th><th>Out</th><th>Degree</th></tr></thead>",
        "<tbody>",
    ]
    for node in sorted(nodes, key=lambda item: (str(item["group"]), str(item["id"]))):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(node['group']))}</td>"
            f"<td><code>{html.escape(str(node['label']))}</code></td>"
            f"<td><code>{html.escape(str(node['parentLabel']))}</code></td>"
            f"<td><code>{html.escape(str(node['id']))}</code></td>"
            f"<td>{int(node['incoming'])}</td>"
            f"<td>{int(node['outgoing'])}</td>"
            f"<td>{int(node['degree'])}</td>"
            "</tr>"
        )
    rows.extend(["</tbody>", "</table>"])
    return "\n".join(rows)


def directory_table_html(report: GraphReport) -> str:
    """Render inferred directory containment edges as an HTML table."""
    directory_tree = graph_payload(report)["directoryTree"]
    edges = list(directory_tree["edges"])
    rows = [
        "<table>",
        "<thead><tr><th>Parent</th><th>Child</th><th>Child kind</th></tr></thead>",
        "<tbody>",
    ]
    for edge in sorted(edges, key=lambda item: (str(item["parentPath"]), str(item["childPath"]))):
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(str(edge['parentPath']))}</code></td>"
            f"<td><code>{html.escape(str(edge['childPath']))}</code></td>"
            f"<td>{html.escape(str(edge['childKind']))}</td>"
            "</tr>"
        )
    rows.extend(["</tbody>", "</table>"])
    return "\n".join(rows)


HTML_STYLE = """
  <style>
    :root {
      color-scheme: light;
      --ink: #17212b;
      --muted: #667789;
      --panel: #ffffff;
      --canvas: #f6f8fb;
      --line: #c9d4df;
      --accent: #1d7c83;
      --accent-soft: #d9eff0;
      --warn: #b75d38;
      --warn-soft: #f8e4d8;
      --design: #3268a8;
      --implementation: #467b3b;
      --environment: #7a5ca3;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: #eef3f6;
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      padding: 18px 20px 12px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 {
      margin: 0 0 8px;
      font-size: 24px;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .metrics {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .metric {
      min-width: 112px;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f9fbfd;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0;
    }
    .metric strong {
      display: block;
      margin-top: 2px;
      font-size: 18px;
    }
    .app-shell {
      display: grid;
      grid-template-columns: minmax(220px, 280px) minmax(420px, 1fr) minmax(240px, 320px);
      min-height: calc(100vh - 100px);
    }
    .controls, .inspector {
      background: var(--panel);
      border-right: 1px solid var(--line);
      padding: 14px;
      overflow: auto;
    }
    .inspector {
      border-right: 0;
      border-left: 1px solid var(--line);
    }
    .graph-pane {
      min-width: 0;
      display: grid;
      grid-template-rows: auto 1fr;
      background: var(--canvas);
    }
    .graph-toolbar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 14px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }
    .graph-canvas {
      min-height: 560px;
      overflow: auto;
      padding: 12px;
    }
    svg {
      display: block;
      min-width: 900px;
      min-height: 540px;
      background: white;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .graph-workbench {
      padding: 14px 20px 18px;
      border-bottom: 1px solid var(--line);
      background: #f8fbfd;
    }
    .graph-workbench h2 {
      margin: 0 0 6px;
      font-size: 18px;
      line-height: 1.25;
      letter-spacing: 0;
    }
    .graph-workbench p {
      margin: 0 0 12px;
      max-width: 920px;
    }
    .graph-stage-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
      align-items: stretch;
    }
    .overview-pane, .fullgraph-pane {
      min-width: 0;
    }
    .overview-pane h3, .fullgraph-pane h3 {
      margin: 0 0 8px;
      font-size: 14px;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .territory-map-wrap {
      height: min(42vh, 430px);
      min-height: 320px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
    }
    .territory-map {
      width: 100%;
      height: 100%;
      min-width: 0;
      min-height: 0;
      border: 0;
      border-radius: 0;
    }
    .territory-cell {
      stroke: #ffffff;
      stroke-width: 3;
    }
    .territory-edge {
      fill: none;
      stroke: #596b7c;
      opacity: 0.36;
      marker-end: url(#territory-arrow);
    }
    .territory-edge.design { stroke: var(--design); }
    .territory-edge.implementation { stroke: var(--implementation); }
    .territory-edge.environment { stroke: var(--environment); }
    .territory-label {
      text-anchor: middle;
      font-size: 12px;
      font-weight: 800;
      fill: var(--ink);
      paint-order: stroke;
      stroke: rgba(255, 255, 255, 0.82);
      stroke-width: 4px;
      stroke-linejoin: round;
    }
    .territory-label .sub {
      font-size: 10px;
      font-weight: 700;
      fill: var(--muted);
    }
    .overview-edge {
      fill: none;
      stroke: #8191a2;
      opacity: 0.34;
    }
    .overview-edge.design { stroke: var(--design); }
    .overview-edge.implementation { stroke: var(--implementation); }
    .overview-edge.environment { stroke: var(--environment); }
    .overview-node rect {
      fill: #ffffff;
      stroke: #7f91a3;
      rx: 8;
    }
    .overview-node .label {
      font-size: 12px;
      font-weight: 800;
      fill: var(--ink);
    }
    .overview-node .sub {
      font-size: 10px;
      fill: var(--muted);
    }
    .static-graph-wrap {
      height: min(72vh, 760px);
      min-height: 520px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
    }
    .static-toolbar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin: 0 0 12px;
    }
    .static-toolbar label {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-weight: 700;
    }
    .static-toolbar output {
      min-width: 44px;
      font-variant-numeric: tabular-nums;
    }
    .static-toolbar button,
    .static-zoom-link {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 5px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      color: var(--ink);
      font: inherit;
      cursor: pointer;
      text-decoration: none;
    }
    .static-toolbar button:hover,
    .static-zoom-link:hover {
      border-color: var(--accent);
    }
    .static-zoom-state {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
    }
    .static-graph {
      width: 100%;
      height: 100%;
      min-width: 0;
      min-height: 0;
      border: 0;
      border-radius: 0;
      cursor: grab;
      touch-action: none;
    }
    .static-graph.dragging {
      cursor: grabbing;
    }
    .static-graph-content {
      transition: transform 120ms ease;
    }
    .static-group-block rect {
      fill: #f9fbfd;
      stroke: #d5dee7;
      rx: 10;
    }
    .static-group {
      font-size: 15px;
      font-weight: 800;
      fill: var(--ink);
    }
    .static-group-sub {
      font-size: 11px;
      fill: var(--muted);
    }
    .static-edge {
      fill: none;
      stroke: #8191a2;
      stroke-width: 1.2;
      opacity: 0.32;
      marker-end: url(#static-arrow);
    }
    .static-edge.design { stroke: var(--design); }
    .static-edge.implementation { stroke: var(--implementation); }
    .static-edge.environment { stroke: var(--environment); }
    .static-edge path, marker path { fill: #8191a2; }
    .static-node rect {
      fill: #ffffff;
      stroke: #7f91a3;
      stroke-width: 1;
      rx: 6;
    }
    .static-node .label {
      font-size: 9.5px;
      font-weight: 700;
      fill: var(--ink);
    }
    .static-node .sub {
      font-size: 8px;
      fill: var(--muted);
    }
    .static-node.broken rect {
      fill: var(--warn-soft);
      stroke: var(--warn);
    }
    details.edge-table {
      margin-top: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
    }
    details.edge-table summary {
      cursor: pointer;
      padding: 10px 12px;
      font-weight: 700;
    }
    details.edge-table .table-wrap {
      max-height: 440px;
      overflow: auto;
      border-top: 1px solid var(--line);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
    }
    th, td {
      padding: 7px 9px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: #f4f7fa;
      font-size: 12px;
    }
    fieldset {
      margin: 0 0 14px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    legend {
      padding: 0 4px;
      font-weight: 700;
    }
    label {
      display: block;
      margin: 8px 0;
      color: var(--ink);
    }
    input[type="search"], input[type="text"], input[type="number"] {
      width: 100%;
      min-height: 34px;
      padding: 6px 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      font: inherit;
    }
    input[type="range"] { width: 160px; }
    .check-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 7px 0;
    }
    .check-row input { margin: 0; }
    .muted { color: var(--muted); }
    code {
      font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      overflow-wrap: anywhere;
    }
    .edge {
      fill: none;
      stroke: #8191a2;
      stroke-width: 1.6;
      opacity: 0.7;
      marker-end: url(#arrow);
    }
    .edge.design { stroke: var(--design); }
    .edge.implementation { stroke: var(--implementation); }
    .edge.environment { stroke: var(--environment); }
    .node rect {
      fill: #ffffff;
      stroke: #7f91a3;
      stroke-width: 1.2;
      rx: 8;
    }
    .node text { pointer-events: none; }
    .node .label {
      font-size: 12px;
      font-weight: 700;
      fill: var(--ink);
    }
    .node .sub {
      font-size: 10px;
      fill: var(--muted);
    }
    .node.broken rect {
      fill: var(--warn-soft);
      stroke: var(--warn);
    }
    .node.selected rect {
      fill: var(--accent-soft);
      stroke: var(--accent);
      stroke-width: 2;
    }
    .inspector-section {
      margin-bottom: 14px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--line);
    }
    .edge-list {
      margin: 8px 0 0;
      padding-left: 18px;
    }
    .edge-list li {
      margin-bottom: 6px;
      overflow-wrap: anywhere;
    }
    @media (max-width: 980px) {
      .graph-stage-grid { grid-template-columns: 1fr; }
      .app-shell { grid-template-columns: 1fr; }
      .controls, .inspector {
        border-left: 0;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      .graph-canvas { min-height: 460px; }
    }
  </style>
"""


HTML_SCRIPT = """
  <script>
    const DATA = JSON.parse(document.getElementById("graph-data").textContent);
    const NODE_W = 210;
    const NODE_H = 46;
    const COL_GAP = 250;
    const ROW_GAP = 72;
    const MAX_RENDER_NODES = 500;
    const MAX_RENDER_EDGES = 1000;
    const MAX_DATALIST_OPTIONS = 1200;
    const INSPECTOR_EDGE_LIMIT = 40;
    const state = {
      query: "",
      focus: "",
      depth: 1,
      scale: 1,
      directions: new Set(DATA.directions),
      kinds: new Set(DATA.kinds),
      selected: null,
    };

    const nodeRecords = DATA.nodes.map((node) => ({ ...node, search: node.id.toLowerCase() }));
    const edgeRecords = DATA.edges.map((edge, index) => ({
      ...edge,
      index,
      sourceSearch: edge.source.toLowerCase(),
      targetSearch: edge.target.toLowerCase(),
    }));
    const byId = new Map(nodeRecords.map((node) => [node.id, node]));
    const incidentById = new Map();
    let lastGraphSize = { width: 900, height: 540 };
    const svg = document.getElementById("graph");
    const inspector = document.getElementById("inspector-content");
    const resultCount = document.getElementById("result-count");

    function addListValue(map, key, value) {
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(value);
    }

    edgeRecords.forEach((edge) => {
      addListValue(incidentById, edge.source, edge);
      if (edge.target !== edge.source) addListValue(incidentById, edge.target, edge);
    });

    function el(name, attrs = {}) {
      const node = document.createElement(name);
      for (const [key, value] of Object.entries(attrs)) {
        if (key === "className") node.className = value;
        else node.setAttribute(key, value);
      }
      return node;
    }

    function svgEl(name, attrs = {}) {
      const node = document.createElementNS("http://www.w3.org/2000/svg", name);
      for (const [key, value] of Object.entries(attrs)) {
        node.setAttribute(key, value);
      }
      return node;
    }

    function shortLabel(value, limit = 34) {
      return value.length > limit ? `${value.slice(0, limit - 3)}...` : value;
    }

    function displayNode(node) {
      return {
        label: node.label || shortLabel(node.id),
        parent: node.parentLabel || node.group,
      };
    }

    function setText(node, value) {
      node.textContent = value;
      return node;
    }

    function setupStaticZoom() {
      const graph = document.getElementById("static-graph");
      const zoom = document.getElementById("static-zoom");
      const zoomValue = document.getElementById("static-zoom-value");
      if (!graph || !zoom) return;
      const baseWidth = Number.parseFloat(graph.dataset.baseWidth || "900");
      const baseHeight = Number.parseFloat(graph.dataset.baseHeight || "540");
      const view = {
        scale: Number.parseFloat(zoom.value || "1"),
        centerX: baseWidth / 2,
        centerY: baseHeight / 2,
      };
      let drag = null;

      function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
      }

      function currentViewBoxSize() {
        return {
          width: baseWidth / view.scale,
          height: baseHeight / view.scale,
        };
      }

      function applyStaticView() {
        const size = currentViewBoxSize();
        const halfW = size.width / 2;
        const halfH = size.height / 2;
        view.centerX = clamp(view.centerX, halfW, baseWidth - halfW);
        view.centerY = clamp(view.centerY, halfH, baseHeight - halfH);
        const x = view.centerX - halfW;
        const y = view.centerY - halfH;
        graph.setAttribute("viewBox", `${x} ${y} ${size.width} ${size.height}`);
        zoom.value = `${view.scale}`;
        if (zoomValue) zoomValue.value = `${view.scale.toFixed(1)}x`;
      }

      function applyStaticZoom(value) {
        view.scale = clamp(Number.parseFloat(value || "1"), 1, 8);
        applyStaticView();
      }

      zoom.addEventListener("input", (event) => {
        applyStaticZoom(event.target.value);
      });
      document.querySelectorAll("[data-static-zoom]").forEach((button) => {
        button.addEventListener("click", (event) => {
          event.preventDefault();
          zoom.value = button.dataset.staticZoom;
          applyStaticZoom(zoom.value);
        });
      });
      const reset = document.getElementById("static-reset");
      if (reset) {
        reset.addEventListener("click", () => {
          view.scale = 1;
          view.centerX = baseWidth / 2;
          view.centerY = baseHeight / 2;
          applyStaticView();
        });
      }
      graph.addEventListener("pointerdown", (event) => {
        graph.setPointerCapture(event.pointerId);
        graph.classList.add("dragging");
        drag = {
          x: event.clientX,
          y: event.clientY,
          centerX: view.centerX,
          centerY: view.centerY,
        };
      });
      graph.addEventListener("pointermove", (event) => {
        if (!drag) return;
        const size = currentViewBoxSize();
        const bounds = graph.getBoundingClientRect();
        const dx = (event.clientX - drag.x) * size.width / bounds.width;
        const dy = (event.clientY - drag.y) * size.height / bounds.height;
        view.centerX = drag.centerX - dx;
        view.centerY = drag.centerY - dy;
        applyStaticView();
      });
      graph.addEventListener("pointerup", (event) => {
        graph.releasePointerCapture(event.pointerId);
        graph.classList.remove("dragging");
        drag = null;
      });
      graph.addEventListener("wheel", (event) => {
        event.preventDefault();
        const next = view.scale * (event.deltaY < 0 ? 1.18 : 0.85);
        applyStaticZoom(next);
      }, { passive: false });
      applyStaticView();
    }

    function buildCheckboxes(containerId, values, activeSet, onChange) {
      const container = document.getElementById(containerId);
      container.textContent = "";
      values.forEach((value) => {
        const label = el("label", { className: "check-row" });
        const input = el("input", { type: "checkbox" });
        input.checked = activeSet.has(value);
        input.addEventListener("change", () => {
          if (input.checked) activeSet.add(value);
          else activeSet.delete(value);
          onChange();
        });
        label.append(input, setText(el("span"), value));
        container.append(label);
      });
    }

    function buildAdjacency(edges) {
      const adjacency = new Map();
      edges.forEach((edge) => {
        addListValue(adjacency, edge.source, edge.target);
        addListValue(adjacency, edge.target, edge.source);
      });
      return adjacency;
    }

    function graphNeighborhood(focus, depth, adjacency) {
      const seen = new Set([focus]);
      let frontier = new Set([focus]);
      for (let step = 0; step < depth; step += 1) {
        const next = new Set();
        frontier.forEach((node) => {
          (adjacency.get(node) || []).forEach((neighbor) => {
            if (!seen.has(neighbor)) next.add(neighbor);
          });
        });
        next.forEach((node) => seen.add(node));
        frontier = next;
      }
      return seen;
    }

    function trimVisibleModel(nodes, edges) {
      const fullNodeCount = nodes.length;
      const fullEdgeCount = edges.length;
      if (fullNodeCount <= MAX_RENDER_NODES && fullEdgeCount <= MAX_RENDER_EDGES) {
        return { nodes, edges, fullNodeCount, fullEdgeCount, truncated: false };
      }
      const priorityId = state.selected || state.focus || "";
      const rankedNodes = [...nodes].sort((left, right) => {
        const leftPriority = left.id === priorityId ? 0 : 1;
        const rightPriority = right.id === priorityId ? 0 : 1;
        return leftPriority - rightPriority
          || right.degree - left.degree
          || left.group.localeCompare(right.group)
          || left.id.localeCompare(right.id);
      });
      const kept = new Set(rankedNodes.slice(0, MAX_RENDER_NODES).map((node) => node.id));
      const trimmedNodes = nodes.filter((node) => kept.has(node.id));
      const trimmedEdges = edges
        .filter((edge) => kept.has(edge.source) && kept.has(edge.target))
        .slice(0, MAX_RENDER_EDGES);
      return {
        nodes: trimmedNodes,
        edges: trimmedEdges,
        fullNodeCount,
        fullEdgeCount,
        truncated: true,
      };
    }

    function visibleModel() {
      const query = state.query.toLowerCase();
      let edges = edgeRecords.filter(
        (edge) => state.directions.has(edge.direction) && state.kinds.has(edge.kind),
      );
      if (query) {
        edges = edges.filter(
          (edge) => edge.sourceSearch.includes(query) || edge.targetSearch.includes(query),
        );
      }
      let allowed = null;
      if (state.focus && byId.has(state.focus)) {
        allowed = graphNeighborhood(state.focus, state.depth, buildAdjacency(edges));
        edges = edges.filter((edge) => allowed.has(edge.source) && allowed.has(edge.target));
      }
      const nodeIds = new Set();
      edges.forEach((edge) => {
        nodeIds.add(edge.source);
        nodeIds.add(edge.target);
      });
      if (query) {
        nodeRecords
          .filter((node) => node.search.includes(query))
          .forEach((node) => nodeIds.add(node.id));
      }
      if (allowed) {
        allowed.forEach((node) => nodeIds.add(node));
      }
      if (!query && !allowed) {
        nodeRecords.forEach((node) => nodeIds.add(node.id));
      }
      const nodes = nodeRecords
        .filter((node) => nodeIds.has(node.id))
        .sort((left, right) => left.group.localeCompare(right.group) || left.id.localeCompare(right.id));
      return trimVisibleModel(nodes, edges);
    }

    function layout(nodes) {
      const groups = [...new Set(nodes.map((node) => node.group))].sort();
      const groupIndex = new Map(groups.map((group, index) => [group, index]));
      const rowIndex = new Map(groups.map((group) => [group, 0]));
      const points = new Map();
      nodes.forEach((node) => {
        const column = groupIndex.get(node.group) || 0;
        const row = rowIndex.get(node.group) || 0;
        rowIndex.set(node.group, row + 1);
        points.set(node.id, {
          x: 40 + column * COL_GAP,
          y: 54 + row * ROW_GAP,
        });
      });
      const maxRows = Math.max(1, ...rowIndex.values());
      return {
        points,
        width: Math.max(900, groups.length * COL_GAP + 80),
        height: Math.max(540, maxRows * ROW_GAP + 110),
      };
    }

    function renderInspector(nodeId) {
      inspector.textContent = "";
      const node = byId.get(nodeId);
      if (!node) {
        inspector.append(setText(el("p", { className: "muted" }), "Select a node"));
        return;
      }
      const summary = el("div", { className: "inspector-section" });
      const title = setText(el("h2"), "Node");
      const path = setText(el("code"), node.id);
      summary.append(title, path);
      const metrics = setText(
        el("p", { className: "muted" }),
        `${node.group} / in ${node.incoming} / out ${node.outgoing}${node.broken ? " / missing target" : ""}`,
      );
      summary.append(metrics);
      inspector.append(summary);

      const incident = incidentById.get(nodeId) || [];
      const section = el("div", { className: "inspector-section" });
      section.append(setText(el("h2"), "Incident Edges"));
      const list = el("ol", { className: "edge-list" });
      incident.slice(0, INSPECTOR_EDGE_LIMIT).forEach((edge) => {
        const item = el("li");
        setText(item, `${edge.direction}/${edge.kind}: ${edge.source} -> ${edge.target}`);
        list.append(item);
      });
      section.append(list);
      if (incident.length > INSPECTOR_EDGE_LIMIT) {
        section.append(setText(el("p", { className: "muted" }), `${incident.length - INSPECTOR_EDGE_LIMIT} more edges hidden`));
      }
      inspector.append(section);
    }

    function applyScale() {
      svg.style.width = `${lastGraphSize.width * state.scale}px`;
      svg.style.height = `${lastGraphSize.height * state.scale}px`;
    }

    function renderGraph() {
      const model = visibleModel();
      const graphLayout = layout(model.nodes);
      lastGraphSize = { width: graphLayout.width, height: graphLayout.height };
      svg.textContent = "";
      svg.setAttribute("viewBox", `0 0 ${graphLayout.width} ${graphLayout.height}`);
      applyScale();

      const defs = svgEl("defs");
      const marker = svgEl("marker", {
        id: "arrow",
        viewBox: "0 0 10 10",
        refX: "9",
        refY: "5",
        markerWidth: "5",
        markerHeight: "5",
        orient: "auto-start-reverse",
      });
      marker.append(svgEl("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#8191a2" }));
      defs.append(marker);
      svg.append(defs);

      const edgeLayer = svgEl("g");
      model.edges.forEach((edge) => {
        const source = graphLayout.points.get(edge.source);
        const target = graphLayout.points.get(edge.target);
        if (!source || !target) return;
        const startX = source.x + NODE_W;
        const startY = source.y + NODE_H / 2;
        const endX = target.x;
        const endY = target.y + NODE_H / 2;
        const curve = Math.max(48, Math.abs(endX - startX) / 2);
        const path = svgEl("path", {
          class: `edge ${edge.kind}`,
          d: `M ${startX} ${startY} C ${startX + curve} ${startY}, ${endX - curve} ${endY}, ${endX} ${endY}`,
        });
        path.append(setText(svgEl("title"), `${edge.direction}/${edge.kind}: ${edge.source} -> ${edge.target}`));
        edgeLayer.append(path);
      });
      svg.append(edgeLayer);

      const nodeLayer = svgEl("g");
      model.nodes.forEach((node) => {
        const point = graphLayout.points.get(node.id);
        if (!point) return;
        const display = displayNode(node);
        const group = svgEl("g", {
          class: `node${node.broken ? " broken" : ""}${state.selected === node.id ? " selected" : ""}`,
          transform: `translate(${point.x} ${point.y})`,
          tabindex: "0",
        });
        group.append(svgEl("rect", { width: NODE_W, height: NODE_H }));
        group.append(setText(svgEl("text", { x: "12", y: "19", class: "label" }), shortLabel(display.label)));
        group.append(setText(svgEl("text", { x: "12", y: "36", class: "sub" }), `${shortLabel(display.parent, 24)} / degree ${node.degree}`));
        group.append(setText(svgEl("title"), node.id));
        group.addEventListener("click", () => {
          state.selected = node.id;
          document.getElementById("focus").value = node.id;
          renderInspector(node.id);
        });
        nodeLayer.append(group);
      });
      svg.append(nodeLayer);

      const truncated = model.truncated
        ? ` (showing ${model.nodes.length}/${model.fullNodeCount} nodes, ${model.edges.length}/${model.fullEdgeCount} edges)`
        : "";
      resultCount.textContent = `${model.nodes.length} nodes / ${model.edges.length} edges visible${truncated}`;
      if (!state.selected || !model.nodes.some((node) => node.id === state.selected)) {
        renderInspector(model.nodes[0] ? model.nodes[0].id : "");
        state.selected = model.nodes[0] ? model.nodes[0].id : null;
      }
    }

    function setup() {
      setupStaticZoom();
      const focusList = document.getElementById("focus-list");
      nodeRecords.slice(0, MAX_DATALIST_OPTIONS).forEach((node) => {
        const option = el("option", { value: node.id });
        focusList.append(option);
      });
      buildCheckboxes("direction-filters", DATA.directions, state.directions, renderGraph);
      buildCheckboxes("kind-filters", DATA.kinds, state.kinds, renderGraph);
      document.getElementById("query").addEventListener("input", (event) => {
        state.query = event.target.value;
        renderGraph();
      });
      document.getElementById("focus").addEventListener("change", (event) => {
        state.focus = event.target.value;
        state.selected = state.focus || state.selected;
        renderGraph();
      });
      document.getElementById("depth").addEventListener("change", (event) => {
        state.depth = Math.max(0, Number.parseInt(event.target.value || "0", 10));
        renderGraph();
      });
      document.getElementById("zoom").addEventListener("input", (event) => {
        state.scale = Number.parseFloat(event.target.value || "1");
        applyScale();
      });
      renderGraph();
    }

    setup();
  </script>
"""


def render_html(
    report: GraphReport,
    *,
    title: str,
    source_path: Path,
) -> str:
    """Render a self-contained dependency graph HTML viewer."""
    payload = graph_payload(report)
    page_title = html.escape(title, quote=True)
    source = html.escape(str(source_path), quote=True)
    data = script_json(payload)
    territory_svg = territory_map_svg(report)
    static_svg = static_graph_svg(report)
    static_zoom_links = "\n".join(
        (
            f'      <button type="button" class="static-zoom-link" '
            f'data-static-zoom="{scale:g}">{html.escape(label)}</button>'
        )
        for _slug, scale, label in STATIC_ZOOM_LEVELS
    )
    node_table = node_table_html(report)
    edge_table = edge_table_html(report)
    directory_table = directory_table_html(report)
    summary = payload["summary"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{page_title}</title>
{HTML_STYLE}
</head>
<body>
  <header>
    <h1>{page_title}</h1>
    <div class="metrics">
      <div class="metric"><span>nodes</span><strong>{len(report.nodes)}</strong></div>
      <div class="metric"><span>edges</span><strong>{len(report.edges)}</strong></div>
      <div class="metric"><span>directories</span><strong>{int(summary["directoryNodes"])}</strong></div>
      <div class="metric"><span>contains</span><strong>{int(summary["containmentEdges"])}</strong></div>
      <div class="metric"><span>cycles</span><strong>{len(report.cycles)}</strong></div>
      <div class="metric"><span>broken targets</span><strong>{len(report.broken_targets)}</strong></div>
    </div>
  </header>
  <section class="graph-workbench" aria-label="Dependency graph workbench">
    <h2>Dependency Map</h2>
    <p class="muted">
      The territory map groups paths by repository area. The full graph map keeps
      every node and edge in a fixed viewport, with zoom changing the graph view
      rather than moving the page layout.
    </p>
    <div class="graph-stage-grid">
      <section class="overview-pane" aria-label="Code territory map">
        <h3>Code Territory Map</h3>
        <div class="territory-map-wrap">
{territory_svg}
        </div>
      </section>
      <section class="fullgraph-pane" aria-label="Full graph map">
        <h3>Full Graph Map</h3>
        <div class="static-toolbar" aria-label="Static graph zoom controls">
          <label for="static-zoom">
            Zoom
            <input id="static-zoom" type="range" min="1" max="8" step="0.25" value="1">
          </label>
          <output id="static-zoom-value" for="static-zoom">1.0x</output>
{static_zoom_links}
          <button id="static-reset" type="button">Center</button>
        </div>
        <div class="static-graph-wrap">
{static_svg}
        </div>
      </section>
    </div>
    <details class="edge-table">
      <summary>Complete node list ({len(report.nodes)})</summary>
      <div class="table-wrap">
{node_table}
      </div>
    </details>
    <details class="edge-table">
      <summary>Complete edge list ({len(report.edges)})</summary>
      <div class="table-wrap">
{edge_table}
      </div>
    </details>
    <details class="edge-table">
      <summary>Directory containment ({int(summary["directoryNodes"])} directories / {int(summary["containmentEdges"])} edges)</summary>
      <div class="table-wrap">
{directory_table}
      </div>
    </details>
  </section>
  <main class="app-shell">
    <aside class="controls" aria-label="Graph controls">
      <fieldset>
        <legend>Search</legend>
        <label for="query">Path query</label>
        <input id="query" type="search" autocomplete="off">
        <label for="focus">Focus path</label>
        <input id="focus" type="text" list="focus-list" autocomplete="off">
        <datalist id="focus-list"></datalist>
        <label for="depth">Depth</label>
        <input id="depth" type="number" min="0" max="8" value="1">
      </fieldset>
      <fieldset>
        <legend>Direction</legend>
        <div id="direction-filters"></div>
      </fieldset>
      <fieldset>
        <legend>Kind</legend>
        <div id="kind-filters"></div>
      </fieldset>
      <p class="muted">Source graph: <code>{source}</code></p>
    </aside>
    <section class="graph-pane" aria-label="Graph viewer">
      <div class="graph-toolbar">
        <output id="result-count"></output>
        <label for="zoom">Zoom <input id="zoom" type="range" min="0.6" max="1.6" step="0.1" value="1"></label>
      </div>
      <div class="graph-canvas">
        <svg id="graph" role="img" aria-label="Dependency manifest graph"></svg>
      </div>
    </section>
    <aside class="inspector" aria-label="Node inspector">
      <div id="inspector-content"></div>
    </aside>
  </main>
  <script id="graph-data" type="application/json">{data}</script>
{HTML_SCRIPT}
</body>
</html>
"""


def main() -> int:
    """Run the renderer."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    graph_input = (
        GraphInput(path=Path(args.graph_tsv).resolve(), source_returncode=None)
        if args.graph_tsv
        else generate_graph_tsv(root)
    )
    report = build_report(root, load_edges(graph_input.path))
    if args.ir_out:
        Path(args.ir_out).write_text(render_ir(report, source_path=graph_input.path), encoding="utf-8")
    if args.markdown_out:
        Path(args.markdown_out).write_text(render_markdown(report), encoding="utf-8")
    if args.dot_out:
        Path(args.dot_out).write_text(render_dot(report), encoding="utf-8")
    if args.html_out:
        Path(args.html_out).write_text(
            render_html(report, title=args.title, source_path=graph_input.path),
            encoding="utf-8",
        )
    if args.format == "json":
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    else:
        print(f"DEPENDENCY_MANIFEST_GRAPH=pass nodes={len(report.nodes)} edges={len(report.edges)} cycles={len(report.cycles)} broken={len(report.broken_targets)}")
        if graph_input.source_returncode not in (None, 0):
            print(f"DEPENDENCY_MANIFEST_GRAPH_SOURCE_CHECK=fail returncode={graph_input.source_returncode}")
        if args.ir_out:
            print(f"DEPENDENCY_MANIFEST_GRAPH_IR={args.ir_out}")
        if args.markdown_out:
            print(f"DEPENDENCY_MANIFEST_GRAPH_MARKDOWN={args.markdown_out}")
        if args.dot_out:
            print(f"DEPENDENCY_MANIFEST_GRAPH_DOT={args.dot_out}")
        if args.html_out:
            print(f"DEPENDENCY_MANIFEST_GRAPH_HTML={args.html_out}")
    return 1 if args.fail_on_broken and report.broken_targets else 0


if __name__ == "__main__":
    raise SystemExit(main())
