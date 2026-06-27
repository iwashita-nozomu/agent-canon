#!/usr/bin/env python3
"""Check theorem dependency graphs for circularity and proof-leaf origins.

@dependency-start
contract tool
responsibility Checks proposition-graph circularity for formal-proof theorem routes.
upstream design ../../agents/skills/formal-proof-workflow.md requires graph-based circularity checks.
upstream design ../../agents/skills/algorithm-proof-exploration.md separates projection evidence from convergence evidence.
@dependency-end
"""

from __future__ import annotations

import argparse
import json
import os
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


@dataclass(frozen=True)
class LeafOriginFinding:
    """One terminal proof-leaf origin finding."""

    check_id: str
    leaf: str
    leaf_kind: str
    leaf_status: str
    leaf_origin: str
    path: tuple[str, ...]
    severity: str
    explanation: str


@dataclass(frozen=True)
class ReachabilityFinding:
    """One forbidden reachable proof node finding."""

    check_id: str
    start: str
    reached: str
    reached_kind: str
    reached_status: str
    reached_origin: str
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
        help="Exit nonzero when a circularity or leaf-origin finding is detected.",
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
        if not is_active_proof_edge(edge):
            continue
        outgoing[str(edge["source"])].append(edge)
    return nodes, outgoing


def is_active_proof_edge(edge: Mapping[str, object]) -> bool:
    """Return whether an edge belongs to the active proof graph.

    Theorem graphs may retain diagnostic, projection-only, or explicitly
    not-required alternative routes so reviewers can audit rejected paths. Those
    routes are useful evidence, but they must not participate in circularity or
    leaf-origin checks for the active target theorem.
    """
    kind = str(edge.get("kind", ""))
    status = str(edge.get("status", ""))
    if kind.startswith("diagnostic_"):
        return False
    inactive_terms = (
        "not_required",
        "diagnostic",
        "projection_only",
        "rejected",
    )
    return not any(term in status for term in inactive_terms)


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

    def edge_kinds(cycle: tuple[str, ...]) -> tuple[str, ...]:
        kinds: list[str] = []
        for source, target in zip(cycle[:-1], cycle[1:], strict=True):
            for edge in outgoing.get(source, []):
                if str(edge.get("target", "")) == target:
                    kinds.append(str(edge.get("kind", "")))
                    break
        return tuple(kinds)

    def is_equivalence_normalization_cycle(cycle: tuple[str, ...]) -> bool:
        kinds = edge_kinds(cycle)
        return bool(kinds) and all(kind == "equivalent_to" for kind in kinds)

    def dfs(node: str) -> None:
        if node in visiting:
            cycle = visiting[visiting.index(node) :] + [node]
            normalized = canonical(cycle)
            if not is_equivalence_normalization_cycle(normalized):
                cycles.add(normalized)
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


def node_passes_leaf_origin_check(
    node: Mapping[str, object],
    *,
    allowed_node_kinds: set[str],
    allowed_origins: set[str],
    allowed_origin_terms: set[str],
    allowed_statuses: set[str],
    allowed_status_prefixes: set[str],
    forbidden_status_terms: set[str],
) -> bool:
    """Return whether a terminal proof leaf has an allowed origin/status."""
    kind = str(node.get("kind", ""))
    status = str(node.get("status", ""))
    origin = str(node.get("origin", ""))
    if any(term and term in status for term in forbidden_status_terms):
        return False
    if kind in allowed_node_kinds:
        return True
    if origin in allowed_origins:
        return True
    if any(term and term in origin for term in allowed_origin_terms):
        return True
    if status in allowed_statuses:
        return True
    return any(prefix and status.startswith(prefix) for prefix in allowed_status_prefixes)


def leaf_paths(
    *,
    start: str,
    outgoing: Mapping[str, list[dict[str, object]]],
    allowed_edge_kinds: set[str],
) -> list[tuple[str, tuple[str, ...]]]:
    """Return terminal leaves reachable from start through allowed edges."""
    leaves: list[tuple[str, tuple[str, ...]]] = []
    queue: deque[tuple[str, tuple[str, ...]]] = deque()
    queue.append((start, (start,)))
    seen_edges: set[tuple[str, str, str]] = set()
    while queue:
        node_id, path = queue.popleft()
        next_edges = [
            edge
            for edge in outgoing.get(node_id, [])
            if str(edge.get("kind", "")) in allowed_edge_kinds
        ]
        if not next_edges:
            leaves.append((node_id, path))
            continue
        for edge in next_edges:
            target = str(edge["target"])
            edge_key = (node_id, str(edge.get("kind", "")), target)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            if target in path:
                leaves.append((target, path + (target,)))
                continue
            queue.append((target, path + (target,)))
    return leaves


def node_is_forbidden_reachable(
    node: Mapping[str, object],
    *,
    forbidden_node_kinds: set[str],
    forbidden_status_terms: set[str],
    allowed_node_kinds: set[str],
    allowed_statuses: set[str],
    allowed_status_prefixes: set[str],
) -> bool:
    """Return whether a reachable node violates a configured route check."""
    kind = str(node.get("kind", ""))
    status = str(node.get("status", ""))
    if kind in allowed_node_kinds:
        return False
    if status in allowed_statuses:
        return False
    if any(prefix and status.startswith(prefix) for prefix in allowed_status_prefixes):
        return False
    if kind in forbidden_node_kinds:
        return True
    return any(term and term in status for term in forbidden_status_terms)


def forbidden_reachable_nodes(
    *,
    start: str,
    nodes: Mapping[str, Mapping[str, object]],
    outgoing: Mapping[str, list[dict[str, object]]],
    allowed_edge_kinds: set[str],
    forbidden_node_kinds: set[str],
    forbidden_status_terms: set[str],
    allowed_node_kinds: set[str],
    allowed_statuses: set[str],
    allowed_status_prefixes: set[str],
) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    """Return all forbidden nodes reachable from start through allowed edges."""
    findings: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    queue: deque[tuple[str, tuple[str, ...], tuple[str, ...]]] = deque()
    queue.append((start, (start,), ()))
    seen_edges: set[tuple[str, str, str]] = set()
    while queue:
        node_id, path, edge_kinds = queue.popleft()
        if node_id != start and node_is_forbidden_reachable(
            nodes.get(node_id, {}),
            forbidden_node_kinds=forbidden_node_kinds,
            forbidden_status_terms=forbidden_status_terms,
            allowed_node_kinds=allowed_node_kinds,
            allowed_statuses=allowed_statuses,
            allowed_status_prefixes=allowed_status_prefixes,
        ):
            findings.append((node_id, path, edge_kinds))
        for edge in outgoing.get(node_id, []):
            edge_kind = str(edge.get("kind", ""))
            if edge_kind not in allowed_edge_kinds:
                continue
            target = str(edge["target"])
            edge_key = (node_id, edge_kind, target)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            if target in path:
                continue
            queue.append((target, path + (target,), edge_kinds + (edge_kind,)))
    return findings


def check_forbidden_reachability(
    graph: Mapping[str, object],
) -> tuple[list[ReachabilityFinding], list[str]]:
    """Run configured forbidden reachability checks."""
    nodes, outgoing = graph_indexes(graph)
    findings: list[ReachabilityFinding] = []
    passed_checks: list[str] = []
    for check in rows(graph.get("forbidden_reachability_checks")):
        check_id = str(check.get("id", "unnamed_forbidden_reachability_check"))
        start = str(check.get("start", ""))
        if not start:
            continue
        allowed_edge_kinds = string_set(check.get("via_edge_kinds"))
        if not allowed_edge_kinds:
            continue
        forbidden_node_kinds = string_set(check.get("forbidden_node_kinds"))
        forbidden_status_terms = string_set(check.get("forbidden_status_terms"))
        allowed_node_kinds = string_set(check.get("allowed_node_kinds"))
        allowed_statuses = string_set(check.get("allowed_statuses"))
        allowed_status_prefixes = string_set(check.get("allowed_status_prefixes"))
        check_findings: list[ReachabilityFinding] = []
        for reached, path, edge_kinds in forbidden_reachable_nodes(
            start=start,
            nodes=nodes,
            outgoing=outgoing,
            allowed_edge_kinds=allowed_edge_kinds,
            forbidden_node_kinds=forbidden_node_kinds,
            forbidden_status_terms=forbidden_status_terms,
            allowed_node_kinds=allowed_node_kinds,
            allowed_statuses=allowed_statuses,
            allowed_status_prefixes=allowed_status_prefixes,
        ):
            node = nodes.get(reached, {})
            check_findings.append(
                ReachabilityFinding(
                    check_id=check_id,
                    start=start,
                    reached=reached,
                    reached_kind=str(node.get("kind", "")),
                    reached_status=str(node.get("status", "")),
                    reached_origin=str(node.get("origin", "")),
                    path=path,
                    edge_kinds=edge_kinds,
                    severity=str(check.get("severity", "forbidden_reachability")),
                    explanation=str(check.get("explanation", "")),
                )
            )
        if check_findings:
            findings.extend(check_findings)
        else:
            passed_checks.append(check_id)
    return findings, passed_checks


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


def check_leaf_origins(
    graph: Mapping[str, object],
) -> tuple[list[LeafOriginFinding], list[str]]:
    """Run configured terminal proof-leaf origin checks."""
    nodes, outgoing = graph_indexes(graph)
    findings: list[LeafOriginFinding] = []
    passed_checks: list[str] = []
    for check in rows(graph.get("leaf_origin_checks")):
        check_id = str(check.get("id", "unnamed_leaf_origin_check"))
        start = str(check.get("start", ""))
        if not start:
            continue
        allowed_edge_kinds = string_set(check.get("via_edge_kinds"))
        if not allowed_edge_kinds:
            continue
        allowed_node_kinds = string_set(check.get("allowed_node_kinds"))
        allowed_origins = string_set(check.get("allowed_origins"))
        allowed_origin_terms = string_set(check.get("allowed_origin_terms"))
        allowed_statuses = string_set(check.get("allowed_statuses"))
        allowed_status_prefixes = string_set(check.get("allowed_status_prefixes"))
        forbidden_status_terms = string_set(check.get("forbidden_status_terms"))
        check_findings: list[LeafOriginFinding] = []
        for leaf, path in leaf_paths(
            start=start,
            outgoing=outgoing,
            allowed_edge_kinds=allowed_edge_kinds,
        ):
            node = nodes.get(leaf, {})
            if node_passes_leaf_origin_check(
                node,
                allowed_node_kinds=allowed_node_kinds,
                allowed_origins=allowed_origins,
                allowed_origin_terms=allowed_origin_terms,
                allowed_statuses=allowed_statuses,
                allowed_status_prefixes=allowed_status_prefixes,
                forbidden_status_terms=forbidden_status_terms,
            ):
                continue
            check_findings.append(
                LeafOriginFinding(
                    check_id=check_id,
                    leaf=leaf,
                    leaf_kind=str(node.get("kind", "")),
                    leaf_status=str(node.get("status", "")),
                    leaf_origin=str(node.get("origin", "")),
                    path=path,
                    severity=str(check.get("severity", "leaf_origin_check")),
                    explanation=str(check.get("explanation", "")),
                )
            )
        if check_findings:
            findings.extend(check_findings)
        else:
            passed_checks.append(check_id)
    return findings, passed_checks


def render_text(
    findings: list[CircularityFinding],
    passed_checks: list[str],
    cycles: list[tuple[str, ...]],
    leaf_findings: list[LeafOriginFinding],
    leaf_passed_checks: list[str],
    reachability_findings: list[ReachabilityFinding],
    reachability_passed_checks: list[str],
) -> str:
    """Render text output."""
    status = "found" if findings or leaf_findings or reachability_findings else "pass"
    reachability_finding_check_ids = {
        finding.check_id for finding in reachability_findings
    }
    reachability_check_count = (
        len(reachability_finding_check_ids) + len(reachability_passed_checks)
    )
    lines = [
        f"THEOREM_GRAPH_CIRCULARITY={status}",
        f"THEOREM_GRAPH_CIRCULARITY_CHECKS={len(findings) + len(passed_checks)}",
        f"THEOREM_GRAPH_CIRCULARITY_FINDINGS={len(findings)}",
        f"THEOREM_GRAPH_CIRCULARITY_PASSED={len(passed_checks)}",
        f"THEOREM_GRAPH_DIRECTED_CYCLES={len(cycles)}",
        f"THEOREM_GRAPH_LEAF_ORIGIN_CHECKS={len(leaf_findings) + len(leaf_passed_checks)}",
        f"THEOREM_GRAPH_LEAF_ORIGIN_FINDINGS={len(leaf_findings)}",
        f"THEOREM_GRAPH_LEAF_ORIGIN_PASSED={len(leaf_passed_checks)}",
        "THEOREM_GRAPH_FORBIDDEN_REACHABILITY_CHECKS="
        f"{reachability_check_count}",
        f"THEOREM_GRAPH_FORBIDDEN_REACHABILITY_FINDINGS={len(reachability_findings)}",
        f"THEOREM_GRAPH_FORBIDDEN_REACHABILITY_PASSED={len(reachability_passed_checks)}",
    ]
    for finding in findings:
        lines.append(
            "THEOREM_GRAPH_CIRCULARITY_FINDING="
            f"{finding.check_id}:start={finding.start}:reached={finding.reached}:"
            f"path={'->'.join(finding.path)}"
        )
    for check_id in passed_checks:
        lines.append(f"THEOREM_GRAPH_CIRCULARITY_PASS={check_id}")
    for finding in leaf_findings:
        lines.append(
            "THEOREM_GRAPH_LEAF_ORIGIN_FINDING="
            f"{finding.check_id}:leaf={finding.leaf}:status={finding.leaf_status}:"
            f"origin={finding.leaf_origin}:path={'->'.join(finding.path)}"
        )
    for check_id in leaf_passed_checks:
        lines.append(f"THEOREM_GRAPH_LEAF_ORIGIN_PASS={check_id}")
    for finding in reachability_findings:
        lines.append(
            "THEOREM_GRAPH_FORBIDDEN_REACHABILITY_FINDING="
            f"{finding.check_id}:reached={finding.reached}:"
            f"status={finding.reached_status}:origin={finding.reached_origin}:"
            f"path={'->'.join(finding.path)}"
        )
    for check_id in reachability_passed_checks:
        lines.append(f"THEOREM_GRAPH_FORBIDDEN_REACHABILITY_PASS={check_id}")
    return "\n".join(lines) + "\n"


def dependency_path_from_output(output_path: str | None) -> str:
    """Return this tool path relative to the rendered output file."""
    if output_path is None:
        return Path(__file__).resolve().as_posix()
    return Path(
        os.path.relpath(
            Path(__file__).resolve(),
            Path(output_path).resolve().parent,
        )
    ).as_posix()


def render_markdown(
    findings: list[CircularityFinding],
    passed_checks: list[str],
    cycles: list[tuple[str, ...]],
    leaf_findings: list[LeafOriginFinding],
    leaf_passed_checks: list[str],
    reachability_findings: list[ReachabilityFinding],
    reachability_passed_checks: list[str],
    *,
    dependency_path: str,
) -> str:
    """Render Markdown output."""
    reachability_finding_check_ids = {
        finding.check_id for finding in reachability_findings
    }
    reachability_check_count = (
        len(reachability_finding_check_ids) + len(reachability_passed_checks)
    )
    lines = [
        "<!--",
        "@dependency-start",
        "responsibility Records theorem-graph circularity, leaf-origin, and forbidden-reachability checks.",
        f"upstream implementation {dependency_path} generates this report from a theorem graph JSON.",
        "downstream design check_finite_stop_goal.py consumes circularity and reachability counts.",
        "@dependency-end",
        "-->",
        "",
        "# Theorem Graph Circularity Check",
        "",
        f"- checks: `{len(findings) + len(passed_checks)}`",
        f"- findings: `{len(findings)}`",
        f"- passed: `{len(passed_checks)}`",
        f"- directed cycles: `{len(cycles)}`",
        f"- leaf-origin checks: `{len(leaf_findings) + len(leaf_passed_checks)}`",
        f"- leaf-origin findings: `{len(leaf_findings)}`",
        f"- forbidden-reachability checks: `{reachability_check_count}`",
        f"- forbidden-reachability findings: `{len(reachability_findings)}`",
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
    if leaf_findings:
        lines.extend(
            [
                "",
                "## Leaf-Origin Findings",
                "",
                "| Check | Severity | Leaf | Kind | Status | Origin | Path | Explanation |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for finding in leaf_findings:
            lines.append(
                f"| `{finding.check_id}` | `{finding.severity}` | `{finding.leaf}` | "
                f"`{finding.leaf_kind}` | `{finding.leaf_status}` | "
                f"`{finding.leaf_origin}` | `{' -> '.join(finding.path)}` | "
                f"{finding.explanation or 'None'} |"
            )
    if leaf_passed_checks:
        lines.extend(["", "## Leaf-Origin Passed Checks", ""])
        lines.extend(f"- `{check_id}`" for check_id in leaf_passed_checks)
    if reachability_findings:
        lines.extend(
            [
                "",
                "## Forbidden Reachability Findings",
                "",
                "| Check | Severity | Reached | Kind | Status | Origin | Path | Edge Kinds | Explanation |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for finding in reachability_findings:
            lines.append(
                f"| `{finding.check_id}` | `{finding.severity}` | "
                f"`{finding.reached}` | `{finding.reached_kind}` | "
                f"`{finding.reached_status}` | `{finding.reached_origin}` | "
                f"`{' -> '.join(finding.path)}` | "
                f"`{' -> '.join(finding.edge_kinds)}` | "
                f"{finding.explanation or 'None'} |"
            )
    if reachability_passed_checks:
        lines.extend(["", "## Forbidden Reachability Passed Checks", ""])
        lines.extend(f"- `{check_id}`" for check_id in reachability_passed_checks)
    return "\n".join(lines) + "\n"


def render_json(
    findings: list[CircularityFinding],
    passed_checks: list[str],
    cycles: list[tuple[str, ...]],
    leaf_findings: list[LeafOriginFinding],
    leaf_passed_checks: list[str],
    reachability_findings: list[ReachabilityFinding],
    reachability_passed_checks: list[str],
) -> str:
    """Render JSON output."""
    reachability_finding_check_ids = {
        finding.check_id for finding in reachability_findings
    }
    reachability_check_count = (
        len(reachability_finding_check_ids) + len(reachability_passed_checks)
    )
    return json.dumps(
        {
            "status": "found"
            if findings or leaf_findings or reachability_findings
            else "pass",
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
            "leaf_origin_check_count": len(leaf_findings) + len(leaf_passed_checks),
            "leaf_origin_passed_checks": leaf_passed_checks,
            "leaf_origin_findings": [
                {
                    "check_id": finding.check_id,
                    "leaf": finding.leaf,
                    "leaf_kind": finding.leaf_kind,
                    "leaf_status": finding.leaf_status,
                    "leaf_origin": finding.leaf_origin,
                    "path": list(finding.path),
                    "severity": finding.severity,
                    "explanation": finding.explanation,
                }
                for finding in leaf_findings
            ],
            "forbidden_reachability_check_count": reachability_check_count,
            "forbidden_reachability_passed_checks": reachability_passed_checks,
            "forbidden_reachability_findings": [
                {
                    "check_id": finding.check_id,
                    "start": finding.start,
                    "reached": finding.reached,
                    "reached_kind": finding.reached_kind,
                    "reached_status": finding.reached_status,
                    "reached_origin": finding.reached_origin,
                    "path": list(finding.path),
                    "edge_kinds": list(finding.edge_kinds),
                    "severity": finding.severity,
                    "explanation": finding.explanation,
                }
                for finding in reachability_findings
            ],
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run CLI."""
    args = build_parser().parse_args(argv)
    graph = load_graph(Path(args.graph))
    findings, passed_checks, cycles = check_circularity(graph)
    leaf_findings, leaf_passed_checks = check_leaf_origins(graph)
    reachability_findings, reachability_passed_checks = check_forbidden_reachability(
        graph
    )
    if args.format == "json":
        rendered = render_json(
            findings,
            passed_checks,
            cycles,
            leaf_findings,
            leaf_passed_checks,
            reachability_findings,
            reachability_passed_checks,
        )
    elif args.format == "markdown":
        rendered = render_markdown(
            findings,
            passed_checks,
            cycles,
            leaf_findings,
            leaf_passed_checks,
            reachability_findings,
            reachability_passed_checks,
            dependency_path=dependency_path_from_output(args.out),
        )
    else:
        rendered = render_text(
            findings,
            passed_checks,
            cycles,
            leaf_findings,
            leaf_passed_checks,
            reachability_findings,
            reachability_passed_checks,
        )
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    has_findings = findings or leaf_findings or reachability_findings
    return 1 if args.fail_on_finding and has_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
