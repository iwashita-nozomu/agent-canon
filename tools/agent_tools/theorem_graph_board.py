#!/usr/bin/env python3
"""Summarize theorem-graph route rows as a whole-theorem frontier board.

@dependency-start
contract tool
responsibility Builds board-level route summaries for formal-proof theorem graphs.
upstream design ../../.agents/skills/formal-proof-workflow/SKILL.md requires problem-level board passes.
upstream design ../../.agents/skills/algorithm-proof-exploration/SKILL.md requires route-row batch selection.
upstream implementation theorem_graph_circularity_check.py validates circularity and forbidden reachability.
@dependency-end
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

JsonObject = dict[str, object]

ROUTE_EXAMPLE_LIMIT = 5
ROUTE_NODE_DISPLAY_LIMIT = 20

TERMINAL_STATUS_TERMS = (
    "verified",
    "checked",
    "refuted",
    "unprovable_under_assumptions",
    "boundary",
    "profile_only",
    "projection_only",
)

OPEN_STATUS_TERMS = (
    "open",
    "frontier",
    "unverified",
    "unconnected",
    "next_witness",
)

ROUTE_LABELS = {
    "sufficient": (
        "sufficient",
        "direct_stop_bridge",
        "value_numeric_stop_route",
        "finite_stop",
    ),
    "reverse": (
        "reverse",
        "necessity",
        "equivalence",
    ),
    "circularity": (
        "circularity",
        "projection",
    ),
    "implementation_extractor": (
        "implementation",
        "extractor",
        "stablehlo",
        "generated_source",
        "trace",
        "lookup",
    ),
    "backend": (
        "backend",
        "fp32",
        "llvm",
        "decode",
    ),
    "problem_config_expressivity": (
        "problem",
        "config",
        "member",
        "expressivity",
        "first_order",
        "generated_tolerance",
        "budget",
    ),
    "algorithm_change": (
        "algorithm",
        "recurrence",
        "line_search",
        "initializer",
    ),
}


def rows(value: object) -> list[dict[str, object]]:
    """Return JSON object rows."""
    if not isinstance(value, list):
        return []
    return [cast(dict[str, object], item) for item in value if isinstance(item, dict)]


def node_text(node: Mapping[str, object]) -> str:
    """Return lower-case searchable node text."""
    fields = [
        str(node.get("id", "")),
        str(node.get("kind", "")),
        str(node.get("status", "")),
        str(node.get("origin", "")),
        str(node.get("theorem", "")),
        str(node.get("definition", "")),
    ]
    return " ".join(fields).lower()


def classify_route(node: Mapping[str, object]) -> str:
    """Classify one node into a route row."""
    text = node_text(node)
    scores: dict[str, int] = {}
    for route, terms in ROUTE_LABELS.items():
        scores[route] = sum(1 for term in terms if term in text)
    route, score = max(scores.items(), key=lambda item: (item[1], item[0]))
    if score <= 0:
        return "other"
    return route


def node_status(node: Mapping[str, object]) -> str:
    """Classify terminal/open status for board use."""
    kind = str(node.get("kind", "")).lower()
    status = str(node.get("status", "")).lower()
    text = f"{kind} {status}"
    if any(term in text for term in TERMINAL_STATUS_TERMS):
        return "terminal"
    if any(term in text for term in OPEN_STATUS_TERMS):
        if "profile_only" in text or "not_required" in text:
            return "terminal"
        return "open"
    if kind in {"code_fact", "formal_library", "verified_code_fact"}:
        return "terminal"
    if any(
        term in kind
        for term in (
            "condition",
            "certificate",
            "class",
            "conclusion",
            "lemma",
            "fact",
            "boundary",
        )
    ):
        return "terminal"
    return "unknown"


def active_edges(graph: Mapping[str, object]) -> dict[str, list[str]]:
    """Build active proof-edge adjacency using the circularity checker policy."""
    inactive_terms = (
        "not_required",
        "diagnostic",
        "projection_only",
        "rejected",
        "obsolete",
        "profile_only",
    )
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in rows(graph.get("edges")):
        source = edge.get("source")
        target = edge.get("target")
        if source is None or target is None:
            continue
        kind = str(edge.get("kind", ""))
        status = str(edge.get("status", ""))
        if kind.startswith("diagnostic_"):
            continue
        if any(term in kind or term in status for term in inactive_terms):
            continue
        outgoing[str(source)].append(str(target))
    return outgoing


def reachable(start: str, outgoing: Mapping[str, list[str]]) -> set[str]:
    """Return active reachable node ids from start."""
    seen: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(outgoing.get(current, ()))
    return seen


@dataclass
class RouteAccumulator:
    """Mutable per-route state before JSON rendering."""

    route: str
    total: int = 0
    statuses: Counter[str] = field(default_factory=Counter)
    open_nodes: list[str] = field(default_factory=list)
    unknown_nodes: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)


def board(graph: Mapping[str, object]) -> JsonObject:
    """Build the board summary."""
    nodes = {str(row["id"]): row for row in rows(graph.get("nodes")) if "id" in row}
    outgoing = active_edges(graph)
    root = str(graph.get("root", ""))
    reachable_ids = reachable(root, outgoing) if root in nodes else set(nodes)
    if not reachable_ids:
        reachable_ids = set(nodes)

    route_rows: dict[str, RouteAccumulator] = {}
    for node_id in sorted(reachable_ids):
        node = nodes.get(node_id)
        if node is None:
            continue
        route = classify_route(node)
        row = route_rows.setdefault(route, RouteAccumulator(route=route))
        status = node_status(node)
        row.total += 1
        row.statuses[status] += 1
        if status == "open":
            row.open_nodes.append(node_id)
        elif status == "unknown":
            row.unknown_nodes.append(node_id)
        if len(row.examples) < ROUTE_EXAMPLE_LIMIT:
            row.examples.append(node_id)

    rows_out = []
    for route, row in sorted(route_rows.items()):
        statuses = dict(row.statuses)
        open_count = int(statuses.get("open", 0))
        unknown_count = int(statuses.get("unknown", 0))
        terminal_count = int(statuses.get("terminal", 0))
        if open_count:
            verdict = "actionable_open"
        elif unknown_count:
            verdict = "needs_classification"
        else:
            verdict = "closed"
        rows_out.append(
            {
                "route": route,
                "verdict": verdict,
                "total": row.total,
                "terminal": terminal_count,
                "open": open_count,
                "unknown": unknown_count,
                "open_nodes": row.open_nodes[:ROUTE_NODE_DISPLAY_LIMIT],
                "unknown_nodes": row.unknown_nodes[:ROUTE_NODE_DISPLAY_LIMIT],
                "examples": row.examples,
            }
        )

    return {
        "graph_id": graph.get("graph_id"),
        "root": root,
        "reachable_nodes": len(reachable_ids),
        "routes": rows_out,
        "open_route_count": sum(1 for row in rows_out if row["verdict"] == "actionable_open"),
        "unknown_route_count": sum(1 for row in rows_out if row["verdict"] == "needs_classification"),
    }


def render_markdown(summary: Mapping[str, object]) -> str:
    """Render board summary as Markdown."""
    lines = [
        "<!--",
        "@dependency-start",
        "responsibility Records theorem-graph route-board summary for a configured proof graph.",
        "upstream implementation theorem_graph_board.py generates this report from a theorem graph JSON.",
        "downstream proof goal-level checkers consume route open and unknown counts.",
        "@dependency-end",
        "-->",
        "",
        "# Theorem Graph Board",
        "",
        f"- graph_id: `{summary.get('graph_id')}`",
        f"- root: `{summary.get('root')}`",
        f"- reachable_nodes: `{summary.get('reachable_nodes')}`",
        f"- open_route_count: `{summary.get('open_route_count')}`",
        f"- unknown_route_count: `{summary.get('unknown_route_count')}`",
        "",
        "| Route | Verdict | Total | Terminal | Open | Unknown | Open Nodes | Unknown Nodes |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in cast(list[Mapping[str, object]], summary.get("routes", [])):
        open_nodes = ", ".join(f"`{item}`" for item in cast(list[str], row.get("open_nodes", []))) or "None"
        unknown_nodes = ", ".join(f"`{item}`" for item in cast(list[str], row.get("unknown_nodes", []))) or "None"
        lines.append(
            "| {route} | `{verdict}` | {total} | {terminal} | {open} | {unknown} | {open_nodes} | {unknown_nodes} |".format(
                route=row.get("route"),
                verdict=row.get("verdict"),
                total=row.get("total"),
                terminal=row.get("terminal"),
                open=row.get("open"),
                unknown=row.get("unknown"),
                open_nodes=open_nodes,
                unknown_nodes=unknown_nodes,
            )
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    """Create parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True)
    parser.add_argument("--out")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--fail-on-open", action="store_true")
    parser.add_argument("--fail-on-unknown", action="store_true")
    return parser


def main() -> int:
    """Run CLI."""
    args = build_parser().parse_args()
    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    if not isinstance(graph, dict):
        raise ValueError("graph must be a JSON object")
    summary = board(cast(dict[str, object], graph))
    if args.format == "json":
        output = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    else:
        output = render_markdown(summary)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    if args.fail_on_open and summary["open_route_count"]:
        return 1
    if args.fail_on_unknown and summary["unknown_route_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
