#!/usr/bin/env python3
# @dependency-start
# responsibility Renders Algorithm Expansion IR, lemma graphs, and proof status as Mermaid block charts.
# upstream implementation algorithm_expansion_ir.py builds Algorithm Expansion IR.
# upstream implementation algorithm_lemma_graph.py builds lemma dependency graphs.
# upstream implementation proof_path_analyzer.py checks proof-status overlays.
# upstream design ../../agents/skills/algorithm-flowchart.md defines visual proof-path workflow.
# downstream design ../../documents/tools/algorithm_flowchart.md documents CLI usage.
# downstream implementation ../../tests/agent_tools/test_algorithm_flowchart.py tests CLI behavior.
# @dependency-end
"""Render Algorithm Expansion IR as a proof-status Mermaid flowchart."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

STATUS_PRIORITY = {
    "unprovable_under_assumptions": 90,
    "refuted": 85,
    "open": 80,
    "unverified_with_next_witness": 75,
    "external_assumption": 70,
    "operational_assumption": 65,
    "blocked": 60,
    "not_run": 55,
    "unverified": 50,
    "assumption": 40,
    "verified": 10,
    "excluded": 0,
}

STATUS_CLASS = {
    "runtime": "runtime",
    "verified": "verified",
    "assumption": "assumption",
    "external_assumption": "external",
    "operational_assumption": "operational",
    "unverified": "unverified",
    "unverified_with_next_witness": "open",
    "open": "open",
    "blocked": "open",
    "not_run": "open",
    "unprovable_under_assumptions": "negative",
    "refuted": "negative",
    "excluded": "excluded",
}

STATIC_EDGE_STATUSES = {
    "statically_checked",
    "static_checker_required",
    "static_resolution_gap",
}

RUNTIME_VIEW_EDGE_ROLES = {
    "runtime_dependency",
    "instance_interaction",
    "variant_dispatch",
    "callback_dispatch",
    "state_transition",
}

FLOWCHART_VIEWS = ("proof", "runtime", "core")


@dataclass(frozen=True)
class FlowNode:
    """One flowchart block."""

    flow_id: str
    source_id: str
    label: str
    source_path: str
    source_symbol: str
    block_kind: str
    math_role: str
    proof_status: str
    proof_sources: tuple[str, ...]


@dataclass(frozen=True)
class FlowEdge:
    """One flowchart dependency edge."""

    source_flow_id: str
    target_flow_id: str
    label: str
    edge_kind: str
    status: str


@dataclass(frozen=True)
class FlowchartReport:
    """Machine-readable flowchart report."""

    status: str
    view: str
    root: str
    theorem: str
    source_ir_status: str
    node_count: int
    edge_count: int
    status_counts: dict[str, int]
    nodes: tuple[FlowNode, ...]
    edges: tuple[FlowEdge, ...]
    mermaid: str


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--ir-json",
        help="Algorithm Expansion IR JSON file. Pass '-' to read stdin.",
    )
    input_group.add_argument(
        "--python-symbol",
        help="Build Algorithm Expansion IR from path.py::qualname before rendering.",
    )
    parser.add_argument("--root", default=".", help="Repository root for --python-symbol.")
    parser.add_argument(
        "--import-root",
        action="append",
        default=[],
        help="Additional AST-only import resolution root. May be passed multiple times.",
    )
    parser.add_argument(
        "--target-theorem",
        default="final_target_theorem",
        help="Target theorem label used when --python-symbol builds IR.",
    )
    parser.add_argument(
        "--backend-profile-library",
        default="lean/lib/backend_profiles.json",
        help="Proof-only backend profile library used when --python-symbol builds IR.",
    )
    parser.add_argument(
        "--lemma-graph",
        action="append",
        default=[],
        help="Optional lemma graph JSON emitted by algorithm_lemma_graph.py.",
    )
    parser.add_argument(
        "--proof-status",
        help="Optional proof_status.json overlay used to color proof state.",
    )
    parser.add_argument(
        "--include-code-facts",
        action="store_true",
        help="Render IR code facts as subordinate blocks.",
    )
    parser.add_argument(
        "--view",
        choices=FLOWCHART_VIEWS,
        default="proof",
        help=(
            "Render mode. `proof` overlays LemmaGraph/proof_status; `runtime` "
            "renders implementation edges only and omits proof-status labels; "
            "`core` renders proof-relevant mathematical/solver/certificate/"
            "diagnostic blocks and tagged equation facts only."
        ),
    )
    parser.add_argument(
        "--include-bookkeeping",
        action="store_true",
        help=(
            "In runtime view, keep implementation_bookkeeping nodes that are "
            "excluded from theorem-directed proof slices."
        ),
    )
    parser.add_argument(
        "--direction",
        choices=("TD", "LR"),
        default="TD",
        help="Mermaid flowchart direction.",
    )
    parser.add_argument("--title", default="Algorithm Proof Flowchart")
    parser.add_argument("--format", choices=("mermaid", "markdown", "json"), default="markdown")
    parser.add_argument("--out", help="Optional output path. Omit to print stdout.")
    return parser


def read_json_file(path: str) -> dict[str, object]:
    """Read a JSON object from path or stdin."""
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object from {path}")
    return payload


def build_ir_payload_from_symbol(args: argparse.Namespace) -> dict[str, object]:
    """Build Algorithm Expansion IR without importing the target module."""
    from algorithm_expansion_ir import (  # type: ignore[import-not-found]
        build_algorithm_ir,
        load_backend_profile_library,
        load_module_index,
        parse_python_symbol_reference,
        relative_path,
    )

    root = Path(str(args.root))
    path, qualname = parse_python_symbol_reference(str(args.python_symbol))
    if not path.is_absolute():
        path = root / path
    import_roots = tuple(
        candidate if candidate.is_absolute() else root / candidate
        for candidate in (Path(raw_path) for raw_path in args.import_root)
    )
    profile_library_path = Path(str(args.backend_profile_library))
    if not profile_library_path.is_absolute():
        profile_library_path = root / profile_library_path
    profile_library = load_backend_profile_library(profile_library_path)
    index = load_module_index(path, root, import_roots)
    report = build_algorithm_ir(
        qualname,
        index,
        str(args.target_theorem),
        root,
        import_roots,
        backend_profile_library_path=relative_path(profile_library_path, root),
        backend_profile_library=profile_library,
    )
    return asdict(report)


def slug(value: str) -> str:
    """Return a stable Mermaid-safe identifier fragment."""
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_").lower()
    return normalized or "unnamed"


def escape_label(value: str) -> str:
    """Escape a value for Mermaid quoted labels."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', r"\"")
        .replace("\n", "<br/>")
        .replace("|", "&#124;")
    )


def status_rank(status: str) -> int:
    """Return priority for status aggregation."""
    return STATUS_PRIORITY.get(status, STATUS_PRIORITY["unverified"])


def strongest_status(statuses: Iterable[str], default: str = "unverified") -> str:
    """Return the most important proof status in a set."""
    unique = list(statuses)
    if not unique:
        return default
    return max(unique, key=status_rank)


def status_class(status: str) -> str:
    """Return Mermaid class name for status."""
    return STATUS_CLASS.get(status, "unverified")


def short_symbol(symbol: str) -> str:
    """Return a compact symbol label."""
    if not symbol:
        return "unknown"
    return symbol.split(".")[-1]


def lemma_graph_statuses(
    graphs: Iterable[dict[str, object]],
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, dict[str, object]]]:
    """Map IR nodes and facts to lemma graph proof statuses."""
    node_statuses: dict[str, set[str]] = defaultdict(set)
    fact_statuses: dict[str, set[str]] = defaultdict(set)
    lemma_by_id: dict[str, dict[str, object]] = {}
    for graph in graphs:
        for lemma in graph.get("lemma_nodes", []):
            if not isinstance(lemma, dict):
                continue
            lemma_id = str(lemma.get("lemma_id", ""))
            if lemma_id:
                lemma_by_id[lemma_id] = lemma
            status = str(lemma.get("proof_status", "unverified"))
            for source_node in lemma.get("source_nodes", []) or []:
                node_statuses[str(source_node)].add(status)
            for source_fact in lemma.get("source_code_facts", []) or []:
                fact_statuses[str(source_fact)].add(status)
    return node_statuses, fact_statuses, lemma_by_id


def proof_status_overlay(
    proof_status: dict[str, object] | None,
    lemma_by_id: dict[str, dict[str, object]],
    fact_source_node: dict[str, str],
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, int]]:
    """Map proof_status overlay rows to IR nodes and facts."""
    node_statuses: dict[str, set[str]] = defaultdict(set)
    fact_statuses: dict[str, set[str]] = defaultdict(set)
    summary = {
        "checked_fragments": 0,
        "open_frontier": 0,
        "external_assumptions": 0,
        "operational_assumptions": 0,
        "unprovable_under_assumptions": 0,
    }
    if proof_status is None:
        return node_statuses, fact_statuses, summary

    checked = proof_status.get("checked_fragments", [])
    if isinstance(checked, list):
        summary["checked_fragments"] = len(checked)

    row_specs = (
        ("open_frontier", "open"),
        ("external_assumptions", "external_assumption"),
        ("operational_assumptions", "operational_assumption"),
        ("unprovable_under_assumptions", "unprovable_under_assumptions"),
    )
    for row_key, default_status in row_specs:
        rows = proof_status.get(row_key, [])
        if not isinstance(rows, list):
            continue
        summary[row_key] = len(rows)
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_status = str(row.get("status") or default_status)
            if row_status in {"verified"}:
                row_status = default_status
            for fact in row.get("code_derived_facts", []) or []:
                if not isinstance(fact, dict):
                    continue
                source_id = str(fact.get("source_id", ""))
                fact_id = str(fact.get("fact_id", ""))
                if fact_id:
                    fact_statuses[fact_id].add(row_status)
                if source_id in fact_source_node:
                    fact_statuses[source_id].add(row_status)
                    node_statuses[fact_source_node[source_id]].add(row_status)
                lemma = lemma_by_id.get(source_id)
                if lemma is not None:
                    for source_node in lemma.get("source_nodes", []) or []:
                        node_statuses[str(source_node)].add(row_status)
                    for source_fact in lemma.get("source_code_facts", []) or []:
                        fact_statuses[str(source_fact)].add(row_status)
                        source_node = fact_source_node.get(str(source_fact))
                        if source_node:
                            node_statuses[source_node].add(row_status)
    return node_statuses, fact_statuses, summary


def combine_status_maps(*maps: dict[str, set[str]]) -> dict[str, set[str]]:
    """Combine status maps."""
    combined: dict[str, set[str]] = defaultdict(set)
    for mapping in maps:
        for key, statuses in mapping.items():
            combined[key].update(statuses)
    return combined


def flow_label_for_node(node: dict[str, object], proof_status: str, *, view: str) -> str:
    """Build a compact block label for an IR node."""
    symbol = short_symbol(str(node.get("source_symbol", "")))
    role = str(node.get("math_role", "unknown"))
    precision = str(node.get("precision_model", "none"))
    unit = str(node.get("residual_unit", "unknown"))
    pieces = [symbol, role]
    if precision and precision != "none":
        pieces.append(f"precision: {precision}")
    if unit and unit != "unknown":
        pieces.append(f"unit: {unit}")
    if view == "proof":
        pieces.append(f"proof: {proof_status}")
    return "\n".join(pieces)


def flow_label_for_fact(fact: dict[str, object], proof_status: str, *, view: str) -> str:
    """Build a compact block label for a code fact."""
    target = str(fact.get("target", "fact"))
    expression = str(fact.get("expression", "")).strip()
    if len(expression) > 90:
        expression = expression[:87] + "..."
    kind = str(fact.get("fact_kind", "code_fact"))
    return "\n".join(
        item
        for item in (
            f"{kind}: {target}",
            expression,
            f"proof: {proof_status}" if view == "proof" else "",
        )
        if item
    )


def should_render_edge(edge: dict[str, object], *, view: str) -> bool:
    """Return whether an IR edge belongs in the selected flowchart view."""
    if view == "proof":
        return True
    return str(edge.get("role", "runtime_dependency")) in RUNTIME_VIEW_EDGE_ROLES


def should_render_node(
    node: dict[str, object],
    *,
    view: str,
    include_bookkeeping: bool,
) -> bool:
    """Return whether an IR node belongs in the selected flowchart view."""
    if view == "proof" or include_bookkeeping:
        return True
    if view == "core":
        math_role = str(node.get("math_role", ""))
        equation_tags = node.get("equation_tags", ())
        return (
            (isinstance(equation_tags, list | tuple) and bool(equation_tags))
            or math_role
            in {
                "mathematical_state_transition",
                "linear_or_nonlinear_solve",
                "certificate",
                "diagnostic",
            }
        )
    return str(node.get("proof_relevance", "required")) != "excluded"


def should_render_fact(fact: dict[str, object], *, view: str) -> bool:
    """Return whether one IR code fact belongs in the selected flowchart view."""
    if view != "core":
        return True
    equation_tags = fact.get("equation_tags", ())
    return isinstance(equation_tags, list | tuple) and bool(equation_tags)


def build_flowchart_report(
    ir_payload: dict[str, object],
    lemma_graphs: tuple[dict[str, object], ...],
    proof_status_payload: dict[str, object] | None,
    *,
    include_code_facts: bool,
    include_bookkeeping: bool,
    direction: str,
    view: str,
) -> FlowchartReport:
    """Build the flowchart report."""
    if view not in FLOWCHART_VIEWS:
        raise ValueError(f"unknown flowchart view: {view}")
    graph_node_statuses, graph_fact_statuses, lemma_by_id = lemma_graph_statuses(lemma_graphs)
    fact_source_node = {
        str(fact.get("fact_id", "")): str(fact.get("source_node_id", ""))
        for fact in ir_payload.get("code_facts", [])
        if isinstance(fact, dict) and fact.get("fact_id") and fact.get("source_node_id")
    }
    overlay_node_statuses, overlay_fact_statuses, _overlay_summary = proof_status_overlay(
        proof_status_payload,
        lemma_by_id,
        fact_source_node,
    )
    if view in {"runtime", "core"}:
        node_statuses: dict[str, set[str]] = defaultdict(set)
        fact_statuses: dict[str, set[str]] = defaultdict(set)
    else:
        node_statuses = combine_status_maps(graph_node_statuses, overlay_node_statuses)
        fact_statuses = combine_status_maps(graph_fact_statuses, overlay_fact_statuses)

    flow_nodes: list[FlowNode] = []
    flow_edges: list[FlowEdge] = []
    source_to_flow: dict[str, str] = {}
    for index, node in enumerate(ir_payload.get("nodes", []) or []):
        if not isinstance(node, dict):
            continue
        if not should_render_node(
            node,
            view=view,
            include_bookkeeping=include_bookkeeping,
        ):
            continue
        source_id = str(node.get("node_id", f"node_{index}"))
        proof_status = (
            "runtime"
            if view in {"runtime", "core"}
            else strongest_status(node_statuses.get(source_id, set()))
        )
        flow_id = f"n{index}"
        source_to_flow[source_id] = flow_id
        flow_nodes.append(
            FlowNode(
                flow_id=flow_id,
                source_id=source_id,
                label=flow_label_for_node(node, proof_status, view=view),
                source_path=str(node.get("source_path", "")),
                source_symbol=str(node.get("source_symbol", "")),
                block_kind="algorithm_node",
                math_role=str(node.get("math_role", "")),
                proof_status=proof_status,
                proof_sources=tuple(sorted(node_statuses.get(source_id, set()))),
            )
        )

    if include_code_facts:
        for index, fact in enumerate(ir_payload.get("code_facts", []) or []):
            if not isinstance(fact, dict):
                continue
            if not should_render_fact(fact, view=view):
                continue
            fact_id = str(fact.get("fact_id", f"fact_{index}"))
            source_node_id = str(fact.get("source_node_id", ""))
            if source_node_id not in source_to_flow:
                continue
            proof_status = (
                "runtime"
                if view in {"runtime", "core"}
                else strongest_status(fact_statuses.get(fact_id, set()))
            )
            flow_id = f"f{index}"
            source_to_flow[fact_id] = flow_id
            flow_nodes.append(
                FlowNode(
                    flow_id=flow_id,
                    source_id=fact_id,
                    label=flow_label_for_fact(fact, proof_status, view=view),
                    source_path=str(fact.get("source_path", "")),
                    source_symbol=str(fact.get("source_symbol", "")),
                    block_kind="code_fact",
                    math_role="code_fact",
                    proof_status=proof_status,
                    proof_sources=tuple(sorted(fact_statuses.get(fact_id, set()))),
                )
            )
            flow_edges.append(
                FlowEdge(
                    source_flow_id=source_to_flow[source_node_id],
                    target_flow_id=flow_id,
                    label="code fact",
                    edge_kind="code_fact",
                    status=proof_status,
                )
            )

    for edge in ir_payload.get("edges", []) or []:
        if not isinstance(edge, dict):
            continue
        if not should_render_edge(edge, view=view):
            continue
        source = source_to_flow.get(str(edge.get("source_node_id", "")))
        target = source_to_flow.get(str(edge.get("target_node_id", "")))
        if source is None or target is None:
            continue
        status = str(edge.get("status", "retained"))
        edge_kind = str(edge.get("edge_kind", "calls"))
        call_text = str(edge.get("call_text") or edge.get("target_symbol") or edge_kind)
        if len(call_text) > 48:
            call_text = call_text[:45] + "..."
        flow_edges.append(
            FlowEdge(
                source_flow_id=source,
                target_flow_id=target,
                label=call_text,
                edge_kind=edge_kind,
                status=status,
            )
        )

    status_counts: dict[str, int] = defaultdict(int)
    for node in flow_nodes:
        status_counts[node.proof_status] += 1
    mermaid = render_mermaid(flow_nodes, flow_edges, direction=direction)
    return FlowchartReport(
        status="algorithm_flowchart_built",
        view=view,
        root=f"{ir_payload.get('root_path', '')}::{ir_payload.get('root_symbol', '')}",
        theorem=str(ir_payload.get("target_theorem", "")),
        source_ir_status=str(ir_payload.get("status", "")),
        node_count=len(flow_nodes),
        edge_count=len(flow_edges),
        status_counts=dict(sorted(status_counts.items())),
        nodes=tuple(flow_nodes),
        edges=tuple(flow_edges),
        mermaid=mermaid,
    )


def render_mermaid(nodes: tuple[FlowNode, ...] | list[FlowNode], edges: tuple[FlowEdge, ...] | list[FlowEdge], *, direction: str) -> str:
    """Render a Mermaid flowchart."""
    lines = [f"flowchart {direction}"]
    grouped: dict[str, list[FlowNode]] = defaultdict(list)
    for node in nodes:
        grouped[node.source_path or "unknown"].append(node)
    for group_index, (source_path, group_nodes) in enumerate(sorted(grouped.items())):
        cluster_id = f"cluster_{group_index}_{slug(source_path)}"
        lines.append(f'  subgraph {cluster_id}["{escape_label(source_path)}"]')
        for node in group_nodes:
            shape_open, shape_close = ("[", "]")
            if node.block_kind == "code_fact":
                shape_open, shape_close = ("{{", "}}")
            lines.append(
                f'    {node.flow_id}{shape_open}"{escape_label(node.label)}"{shape_close}'
            )
        lines.append("  end")
    for edge in edges:
        arrow = "-.->" if edge.status in STATIC_EDGE_STATUSES else "-->"
        lines.append(
            f'  {edge.source_flow_id} {arrow}|"{escape_label(edge.label)}"| {edge.target_flow_id}'
        )
    lines.extend(
        [
            "  classDef verified fill:#dcfce7,stroke:#166534,color:#052e16;",
            "  classDef runtime fill:#e0f2fe,stroke:#0369a1,color:#082f49;",
            "  classDef assumption fill:#fef9c3,stroke:#a16207,color:#422006;",
            "  classDef external fill:#ede9fe,stroke:#6d28d9,color:#2e1065;",
            "  classDef operational fill:#dbeafe,stroke:#1d4ed8,color:#172554;",
            "  classDef open fill:#ffedd5,stroke:#c2410c,color:#431407;",
            "  classDef negative fill:#fee2e2,stroke:#b91c1c,color:#450a0a;",
            "  classDef unverified fill:#f3f4f6,stroke:#6b7280,color:#111827;",
            "  classDef excluded fill:#e5e7eb,stroke:#9ca3af,color:#374151;",
        ]
    )
    for node in nodes:
        lines.append(f"  class {node.flow_id} {status_class(node.proof_status)};")
    return "\n".join(lines) + "\n"


def render_markdown(report: FlowchartReport, title: str) -> str:
    """Render a Markdown report with Mermaid diagram."""
    status_heading = "Proof Status Counts" if report.view == "proof" else "Runtime Status Counts"
    status_label = "Proof status" if report.view == "proof" else "View status"
    lines = [
        f"# {title}",
        "",
        f"- View: `{report.view}`",
        f"- Root: `{report.root}`",
        f"- Target theorem: `{report.theorem}`",
        f"- Source IR status: `{report.source_ir_status}`",
        f"- Blocks: `{report.node_count}`",
        f"- Edges: `{report.edge_count}`",
        "",
        f"## {status_heading}",
        "",
        f"| {status_label} | Blocks |",
        "| --- | ---: |",
    ]
    for status, count in report.status_counts.items():
        lines.append(f"| `{status}` | {count} |")
    lines.extend(
        [
            "",
            "## Flowchart",
            "",
            "```mermaid",
            report.mermaid.rstrip(),
            "```",
            "",
            "## Blocks",
            "",
            f"| Block | Source | Role | {status_label} |",
            "| --- | --- | --- | --- |",
        ]
    )
    for node in report.nodes:
        source = f"{node.source_path}::{node.source_symbol}"
        lines.append(
            f"| `{node.source_id}` | `{source}` | `{node.math_role}` | `{node.proof_status}` |"
        )
    return "\n".join(lines) + "\n"


def render_json(report: FlowchartReport) -> str:
    """Render JSON report."""
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    """CLI entrypoint."""
    args = build_parser().parse_args()
    ir_payload = (
        build_ir_payload_from_symbol(args)
        if args.python_symbol
        else read_json_file(str(args.ir_json))
    )
    lemma_graphs = tuple(read_json_file(path) for path in args.lemma_graph)
    proof_status_payload = (
        read_json_file(str(args.proof_status)) if args.proof_status else None
    )
    report = build_flowchart_report(
        ir_payload,
        lemma_graphs,
        proof_status_payload,
        include_code_facts=bool(args.include_code_facts),
        include_bookkeeping=bool(args.include_bookkeeping),
        direction=str(args.direction),
        view=str(args.view),
    )
    if args.format == "mermaid":
        rendered = report.mermaid
    elif args.format == "json":
        rendered = render_json(report)
    else:
        rendered = render_markdown(report, str(args.title))
    if args.out:
        out = Path(str(args.out))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
