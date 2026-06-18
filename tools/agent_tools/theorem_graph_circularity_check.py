#!/usr/bin/env python3
"""Check theorem dependency graphs for proof-route circularity.

@dependency-start
responsibility Checks proposition-graph circularity for formal-proof theorem routes.
upstream design ../../agents/skills/formal-proof-workflow.md requires graph-based circularity checks.
upstream design ../../agents/skills/algorithm-proof-exploration.md separates projection evidence from convergence evidence.
@dependency-end
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast


@dataclass(frozen=True)
class CircularityFinding:
    """One graph-based circularity finding."""

    check_id: str
    start: str
    reached: str
    reached_kind: str
    path: tuple[str, ...]
    edge_kinds: tuple[str, ...]
    severity: str
    explanation: str


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, help="Theorem graph JSON file.")
    parser.add_argument("--out", help="Optional output file.")
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--fail-on-finding",
        action="store_true",
        help="Exit nonzero when a circularity finding is detected.",
    )
    return parser


def load_graph(path: Path) -> dict[str, object]:
    """Load theorem graph JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("graph must be a JSON object")
    return cast(dict[str, object], payload)


def rows(value: object) -> list[dict[str, object]]:
    """Return object rows from a JSON list."""
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [cast(dict[str, object], item) for item in items if isinstance(item, dict)]


def string_set(value: object) -> set[str]:
    """Return a set of strings from a JSON list."""
    if not isinstance(value, list):
        return set()
    return {str(item) for item in cast(list[object], value)}


def graph_indexes(
    graph: Mapping[str, object],
) -> tuple[dict[str, dict[str, object]], dict[str, list[dict[str, object]]]]:
    """Return node and outgoing-edge indexes."""
    nodes = {str(node["id"]): node for node in rows(graph.get("nodes")) if "id" in node}
    outgoing: dict[str, list[dict[str, object]]] = defaultdict(list)
    for edge in rows(graph.get("edges")):
        if "source" not in edge or "target" not in edge:
            continue
        outgoing[str(edge["source"])].append(edge)
    return nodes, outgoing


def reachable_path(
    *,
    start: str,
    nodes: Mapping[str, Mapping[str, object]],
    outgoing: Mapping[str, list[dict[str, object]]],
    allowed_edge_kinds: set[str],
    forbidden_node_kinds: set[str],
) -> tuple[str, tuple[str, ...], tuple[str, ...]] | None:
    """Find the first forbidden node reachable from start through allowed edges."""
    queue: deque[tuple[str, tuple[str, ...], tuple[str, ...]]] = deque()
    queue.append((start, (start,), ()))
    seen = {start}
    while queue:
        node_id, path, edge_kinds = queue.popleft()
        if node_id != start:
            kind = str(nodes.get(node_id, {}).get("kind", ""))
            if kind in forbidden_node_kinds:
                return node_id, path, edge_kinds
        for edge in outgoing.get(node_id, []):
            edge_kind = str(edge.get("kind", ""))
            if edge_kind not in allowed_edge_kinds:
                continue
            target = str(edge["target"])
            if target in seen:
                continue
            seen.add(target)
            queue.append((target, path + (target,), edge_kinds + (edge_kind,)))
    return None


def detect_directed_cycles(
    nodes: Mapping[str, Mapping[str, object]],
    outgoing: Mapping[str, list[dict[str, object]]],
) -> list[tuple[str, ...]]:
    """Detect simple directed cycles for diagnostic evidence."""
    cycles: set[tuple[str, ...]] = set()
    visiting: list[str] = []
    visited: set[str] = set()

    def canonical(cycle: list[str]) -> tuple[str, ...]:
        body = cycle[:-1]
        rotations = [body[index:] + body[:index] for index in range(len(body))]
        best = min(rotations)
        return tuple(best + [best[0]])

    def dfs(node: str) -> None:
        if node in visiting:
            cycle = visiting[visiting.index(node) :] + [node]
            cycles.add(canonical(cycle))
            return
        if node in visited:
            return
        visiting.append(node)
        for edge in outgoing.get(node, []):
            dfs(str(edge["target"]))
        visiting.pop()
        visited.add(node)

    for node_id in nodes:
        dfs(node_id)
    return sorted(cycles)


def check_circularity(
    graph: Mapping[str, object],
) -> tuple[list[CircularityFinding], list[str], list[tuple[str, ...]]]:
    """Run configured circularity checks."""
    nodes, outgoing = graph_indexes(graph)
    findings: list[CircularityFinding] = []
    passed_checks: list[str] = []
    for check in rows(graph.get("circularity_checks")):
        check_id = str(check.get("id", "unnamed_check"))
        start = str(check.get("start", ""))
        if not start:
            continue
        allowed_edge_kinds = string_set(check.get("via_edge_kinds"))
        forbidden_node_kinds = string_set(check.get("forbidden_reachable_kinds"))
        if not allowed_edge_kinds or not forbidden_node_kinds:
            continue
        found = reachable_path(
            start=start,
            nodes=nodes,
            outgoing=outgoing,
            allowed_edge_kinds=allowed_edge_kinds,
            forbidden_node_kinds=forbidden_node_kinds,
        )
        if found is None:
            passed_checks.append(check_id)
            continue
        reached, path, edge_kinds = found
        findings.append(
            CircularityFinding(
                check_id=check_id,
                start=start,
                reached=reached,
                reached_kind=str(nodes.get(reached, {}).get("kind", "")),
                path=path,
                edge_kinds=edge_kinds,
                severity=str(check.get("severity", "circularity_check")),
                explanation=str(check.get("explanation", "")),
            )
        )
    return findings, passed_checks, detect_directed_cycles(nodes, outgoing)


def render_text(
    findings: list[CircularityFinding],
    passed_checks: list[str],
    cycles: list[tuple[str, ...]],
) -> str:
    """Render text output."""
    status = "found" if findings else "pass"
    lines = [
        f"THEOREM_GRAPH_CIRCULARITY={status}",
        f"THEOREM_GRAPH_CIRCULARITY_CHECKS={len(findings) + len(passed_checks)}",
        f"THEOREM_GRAPH_CIRCULARITY_FINDINGS={len(findings)}",
        f"THEOREM_GRAPH_CIRCULARITY_PASSED={len(passed_checks)}",
        f"THEOREM_GRAPH_DIRECTED_CYCLES={len(cycles)}",
    ]
    for finding in findings:
        lines.append(
            "THEOREM_GRAPH_CIRCULARITY_FINDING="
            f"{finding.check_id}:start={finding.start}:reached={finding.reached}:"
            f"path={'->'.join(finding.path)}"
        )
    for check_id in passed_checks:
        lines.append(f"THEOREM_GRAPH_CIRCULARITY_PASS={check_id}")
    return "\n".join(lines) + "\n"


def render_markdown(
    findings: list[CircularityFinding],
    passed_checks: list[str],
    cycles: list[tuple[str, ...]],
) -> str:
    """Render Markdown output."""
    lines = [
        "# Theorem Graph Circularity Check",
        "",
        f"- checks: `{len(findings) + len(passed_checks)}`",
        f"- findings: `{len(findings)}`",
        f"- passed: `{len(passed_checks)}`",
        f"- directed cycles: `{len(cycles)}`",
        "",
        "| Check | Severity | Start | Reached | Path | Edge Kinds | Explanation |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for finding in findings:
        lines.append(
            f"| `{finding.check_id}` | `{finding.severity}` | `{finding.start}` | "
            f"`{finding.reached}` (`{finding.reached_kind}`) | "
            f"`{' -> '.join(finding.path)}` | `{' -> '.join(finding.edge_kinds)}` | "
            f"{finding.explanation or 'None'} |"
        )
    if passed_checks:
        lines.extend(["", "## Passed Checks", ""])
        lines.extend(f"- `{check_id}`" for check_id in passed_checks)
    if cycles:
        lines.extend(["", "## Directed Cycles", ""])
        lines.extend(f"- `{' -> '.join(cycle)}`" for cycle in cycles)
    return "\n".join(lines) + "\n"


def render_json(
    findings: list[CircularityFinding],
    passed_checks: list[str],
    cycles: list[tuple[str, ...]],
) -> str:
    """Render JSON output."""
    return json.dumps(
        {
            "status": "found" if findings else "pass",
            "check_count": len(findings) + len(passed_checks),
            "passed_checks": passed_checks,
            "findings": [
                {
                    "check_id": finding.check_id,
                    "start": finding.start,
                    "reached": finding.reached,
                    "reached_kind": finding.reached_kind,
                    "path": list(finding.path),
                    "edge_kinds": list(finding.edge_kinds),
                    "severity": finding.severity,
                    "explanation": finding.explanation,
                }
                for finding in findings
            ],
            "directed_cycles": [list(cycle) for cycle in cycles],
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run CLI."""
    args = build_parser().parse_args(argv)
    findings, passed_checks, cycles = check_circularity(load_graph(Path(args.graph)))
    if args.format == "json":
        rendered = render_json(findings, passed_checks, cycles)
    elif args.format == "markdown":
        rendered = render_markdown(findings, passed_checks, cycles)
    else:
        rendered = render_text(findings, passed_checks, cycles)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 1 if args.fail_on_finding and findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
