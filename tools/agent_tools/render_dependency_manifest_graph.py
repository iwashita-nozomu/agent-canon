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
import html
import json
import subprocess
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

GRAPH_TSV_FIELD_COUNT = 4
HIGH_DEGREE_NODE_LIMIT = 20
MAX_REPORTED_BROKEN_TARGETS = 50
MAX_REPORTED_CYCLES = 50


@dataclass(frozen=True)
class Edge:
    """One dependency graph edge."""

    direction: str
    kind: str
    source: str
    target: str


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
    lines = [
        "# Dependency Manifest Graph Report",
        "",
        f"- nodes: {len(report.nodes)}",
        f"- edges: {len(report.edges)}",
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
    first = path.split("/", 1)[0]
    return first or "root"


def graph_payload(report: GraphReport) -> dict[str, object]:
    """Return the JSON-serializable graph payload used by the HTML viewer."""
    incoming = Counter[str]()
    outgoing = Counter[str]()
    for edge in report.edges:
        outgoing[edge.source] += 1
        incoming[edge.target] += 1
    broken_targets = set(report.broken_targets)
    nodes = [
        {
            "id": node,
            "group": path_group(node),
            "incoming": incoming[node],
            "outgoing": outgoing[node],
            "degree": incoming[node] + outgoing[node],
            "broken": node in broken_targets,
        }
        for node in report.nodes
    ]
    return {
        "summary": {
            "nodes": len(report.nodes),
            "edges": len(report.edges),
            "cycles": len(report.cycles),
            "brokenTargets": len(report.broken_targets),
        },
        "nodes": nodes,
        "edges": [asdict(edge) for edge in report.edges],
        "directions": sorted({edge.direction for edge in report.edges}),
        "kinds": sorted({edge.kind for edge in report.edges}),
        "highDegree": [
            {"id": path, "degree": degree}
            for path, degree in report.high_degree_nodes
        ],
        "cycles": [list(cycle) for cycle in report.cycles],
        "brokenTargets": list(report.broken_targets),
    }


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

    function setText(node, value) {
      node.textContent = value;
      return node;
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
        const group = svgEl("g", {
          class: `node${node.broken ? " broken" : ""}${state.selected === node.id ? " selected" : ""}`,
          transform: `translate(${point.x} ${point.y})`,
          tabindex: "0",
        });
        group.append(svgEl("rect", { width: NODE_W, height: NODE_H }));
        group.append(setText(svgEl("text", { x: "12", y: "19", class: "label" }), shortLabel(node.id)));
        group.append(setText(svgEl("text", { x: "12", y: "36", class: "sub" }), `${node.group} / degree ${node.degree}`));
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


def render_html(report: GraphReport, *, title: str, source_path: Path) -> str:
    """Render a self-contained dependency graph HTML viewer."""
    payload = graph_payload(report)
    page_title = html.escape(title, quote=True)
    source = html.escape(str(source_path), quote=True)
    data = script_json(payload)
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
      <div class="metric"><span>cycles</span><strong>{len(report.cycles)}</strong></div>
      <div class="metric"><span>broken targets</span><strong>{len(report.broken_targets)}</strong></div>
    </div>
  </header>
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
        if args.markdown_out:
            print(f"DEPENDENCY_MANIFEST_GRAPH_MARKDOWN={args.markdown_out}")
        if args.dot_out:
            print(f"DEPENDENCY_MANIFEST_GRAPH_DOT={args.dot_out}")
        if args.html_out:
            print(f"DEPENDENCY_MANIFEST_GRAPH_HTML={args.html_out}")
    return 1 if args.fail_on_broken and report.broken_targets else 0


if __name__ == "__main__":
    raise SystemExit(main())
