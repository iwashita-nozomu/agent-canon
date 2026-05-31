#!/usr/bin/env python3
# @dependency-start
# responsibility Renders dependency manifest graph TSV artifacts into Markdown and DOT reports.
# upstream implementation ./check_dependency_graph.sh writes dependency graph TSV artifacts.
# upstream design ../../documents/dependency-manifest-design.md defines manifest graph semantics.
# downstream design ../../documents/tools/render_dependency_manifest_graph.md documents report generation.
# downstream implementation ../../tests/agent_tools/test_render_dependency_manifest_graph.py tests graph rendering.
# @dependency-end
"""Render dependency manifest graph reports from graph TSV artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


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
        if len(fields) != 4:
            continue
        edges.append(Edge(*fields))
    return tuple(edges)


def repo_path_exists(root: Path, path: str) -> bool:
    """Return whether a dependency target exists or is an external-ish token."""
    if "://" in path or path.startswith("#"):
        return True
    return (root / path).exists()


def detect_cycles(edges: tuple[Edge, ...], *, max_cycles: int = 50) -> tuple[tuple[str, ...], ...]:
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
    high_degree = tuple(sorted(degree.items(), key=lambda item: (-item[1], item[0]))[:20])
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
    lines.extend(f"| `{path}` | {degree} |" for path, degree in report.high_degree_nodes[:20])
    lines.extend(["", "## Cycles", ""])
    if report.cycles:
        lines.extend(f"- {' -> '.join(cycle)}" for cycle in report.cycles[:20])
    else:
        lines.append("- none")
    lines.extend(["", "## Broken Targets", ""])
    if report.broken_targets:
        lines.extend(f"- `{path}`" for path in report.broken_targets[:50])
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
    return 1 if args.fail_on_broken and report.broken_targets else 0


if __name__ == "__main__":
    raise SystemExit(main())
