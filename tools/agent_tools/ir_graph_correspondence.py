#!/usr/bin/env python3
# @dependency-start
# responsibility Checks correspondence between Algorithm Expansion IR equation facts and lemma graph/proof-status adoption.
# upstream implementation algorithm_expansion_ir.py emits Algorithm Expansion IR code facts.
# upstream implementation algorithm_lemma_graph.py emits code-fact lemma nodes and graph edges.
# upstream implementation proof_path_analyzer.py checks proof-status overlays after graph correspondence is established.
# upstream design ../../agents/skills/formal-proof-workflow.md defines IR-to-proof workflow.
# downstream design ../../documents/tools/ir_graph_correspondence.md documents CLI usage.
# downstream implementation ../../tests/agent_tools/test_ir_graph_correspondence.py tests checker behavior.
# @dependency-end
"""Check Algorithm Expansion IR equation facts against lemma graphs and proof status."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_FACT_KINDS = ("assignment_equation", "return_equation")
PROOF_STATUS_BUCKETS = (
    "checked_fragments",
    "open_frontier",
    "unprovable_under_assumptions",
    "operational_assumptions",
    "external_assumptions",
)


@dataclass(frozen=True)
class CorrespondenceFinding:
    """One IR/graph/proof-status correspondence finding."""

    severity: str
    kind: str
    fact_id: str
    message: str


@dataclass(frozen=True)
class FactCoverage:
    """Coverage for one IR code fact."""

    fact_id: str
    fact_kind: str
    source_path: str
    source_symbol: str
    target: str
    expression: str
    equation_tags: tuple[str, ...]
    target_profiles: tuple[str, ...]
    lemma_id: str
    graph_node_exists: bool
    consumed_by_lemma_ids: tuple[str, ...]
    on_target_chain: bool
    adopted_by: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class IterationUnit:
    """Grouped equation facts for one implementation iteration unit."""

    unit_id: str
    source_path: str
    source_symbol: str
    equation_tags: tuple[str, ...]
    fact_count: int
    graph_covered_count: int
    target_chain_count: int
    adopted_count: int


@dataclass(frozen=True)
class CorrespondenceReport:
    """Machine-readable IR/lemma graph correspondence report."""

    status: str
    fact_count: int
    graph_node_covered_count: int
    consumption_edge_covered_count: int
    target_chain_covered_count: int
    proof_status_adopted_count: int
    selected_profiles: tuple[str, ...]
    selected_fact_kinds: tuple[str, ...]
    selected_equation_tags: tuple[str, ...]
    selected_fact_ids: tuple[str, ...]
    iteration_units: tuple[IterationUnit, ...]
    facts: tuple[FactCoverage, ...]
    findings: tuple[CorrespondenceFinding, ...]
    validation: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--algorithm-ir",
        action="append",
        required=True,
        help="Algorithm Expansion IR JSON file. May be passed multiple times.",
    )
    parser.add_argument(
        "--lemma-graph",
        action="append",
        required=True,
        help="Lemma graph JSON file. May be passed multiple times.",
    )
    parser.add_argument(
        "--proof-status",
        help="Optional proof_status.json used to classify which equation facts are adopted.",
    )
    parser.add_argument(
        "--target-profile",
        action="append",
        default=None,
        help="Only inspect facts selected for this theorem profile. May be repeated.",
    )
    parser.add_argument(
        "--fact-kind",
        action="append",
        default=None,
        help=(
            "IR code fact kind to inspect. Defaults to assignment_equation and "
            "return_equation. May be repeated."
        ),
    )
    parser.add_argument(
        "--equation-tag",
        action="append",
        default=None,
        help="Only inspect facts with this equation tag. May be repeated.",
    )
    parser.add_argument(
        "--fact-id",
        action="append",
        default=None,
        help="Only inspect this exact IR code fact id. May be repeated.",
    )
    parser.add_argument(
        "--source-symbol",
        action="append",
        default=None,
        help="Only inspect facts from this source symbol. May be repeated.",
    )
    parser.add_argument(
        "--require-proof-status-adoption",
        action="store_true",
        help="Fail when selected IR facts are not referenced by proof_status code_derived_facts.",
    )
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    parser.add_argument("--out", help="Optional output path. Omit to print stdout.")
    return parser


def load_json(path: str) -> dict[str, object]:
    """Load a JSON object from path."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def as_tuple(value: object) -> tuple[object, ...]:
    """Return tuple-like JSON values as tuples."""
    if isinstance(value, list | tuple):
        return tuple(value)
    return ()


def str_tuple(value: object) -> tuple[str, ...]:
    """Return tuple-like JSON values as string tuples."""
    return tuple(str(item) for item in as_tuple(value))


def slug(value: str) -> str:
    """Return the lemma-graph slug used for fact ids."""
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_").lower()
    return normalized or "unnamed"


def lemma_id_for_fact(fact_id: str) -> str:
    """Return the expected code-fact lemma id."""
    return f"lemma__{slug(fact_id)}"


def selected_by_profile(fact: dict[str, object], profiles: tuple[str, ...]) -> bool:
    """Return whether a fact belongs to any selected theorem profile."""
    if not profiles:
        return True
    fact_profiles = set(str_tuple(fact.get("target_profiles")))
    return bool(fact_profiles.intersection(profiles))


def selected_by_tags(fact: dict[str, object], tags: tuple[str, ...]) -> bool:
    """Return whether a fact has any requested equation tag."""
    if not tags:
        return True
    fact_tags = set(str_tuple(fact.get("equation_tags")))
    return bool(fact_tags.intersection(tags))


def selected_by_symbol(fact: dict[str, object], symbols: tuple[str, ...]) -> bool:
    """Return whether a fact comes from any requested source symbol."""
    if not symbols:
        return True
    return str(fact.get("source_symbol", "")) in set(symbols)


def selected_ir_facts(
    irs: tuple[dict[str, object], ...],
    *,
    fact_kinds: tuple[str, ...],
    profiles: tuple[str, ...],
    tags: tuple[str, ...],
    symbols: tuple[str, ...],
    fact_ids: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    """Return IR code facts selected for correspondence checking."""
    selected: list[dict[str, object]] = []
    seen: set[str] = set()
    fact_kind_set = set(fact_kinds)
    fact_id_set = set(fact_ids)
    for ir in irs:
        for fact in as_tuple(ir.get("code_facts")):
            if not isinstance(fact, dict):
                continue
            fact_id = str(fact.get("fact_id", ""))
            if not fact_id or fact_id in seen:
                continue
            if fact_id_set and fact_id not in fact_id_set:
                continue
            if str(fact.get("fact_kind", "")) not in fact_kind_set:
                continue
            if not selected_by_profile(fact, profiles):
                continue
            if not selected_by_tags(fact, tags):
                continue
            if not selected_by_symbol(fact, symbols):
                continue
            selected.append(fact)
            seen.add(fact_id)
    return tuple(selected)


def graph_node_ids(graphs: tuple[dict[str, object], ...]) -> set[str]:
    """Return all lemma graph node ids."""
    return {
        str(node.get("lemma_id", ""))
        for graph in graphs
        for node in as_tuple(graph.get("lemma_nodes"))
        if isinstance(node, dict)
    }


def graph_consumers_by_fact(graphs: tuple[dict[str, object], ...]) -> dict[str, set[str]]:
    """Return graph lemma ids that consume each code fact lemma id."""
    consumers: dict[str, set[str]] = {}
    for graph in graphs:
        for edge in as_tuple(graph.get("lemma_edges")):
            if not isinstance(edge, dict):
                continue
            if str(edge.get("edge_kind", "")) != "lemma_consumes_code_fact":
                continue
            target = str(edge.get("target_lemma_id", ""))
            source = str(edge.get("source_lemma_id", ""))
            if target and source:
                consumers.setdefault(target, set()).add(source)
    return consumers


def graph_target_chain_ids(graphs: tuple[dict[str, object], ...], profiles: tuple[str, ...]) -> set[str]:
    """Return all lemma ids on selected target chains."""
    selected: set[str] = set()
    profile_set = set(profiles)
    for graph in graphs:
        for chain in as_tuple(graph.get("target_chains")):
            if not isinstance(chain, dict):
                continue
            if profile_set and str(chain.get("profile", "")) not in profile_set:
                continue
            selected.add(str(chain.get("target_id", "")))
            selected.update(str_tuple(chain.get("lemma_ids")))
            selected.update(str_tuple(chain.get("reachable_lemma_ids")))
    return selected


def proof_status_adoptions(proof_status: dict[str, object] | None) -> dict[str, set[str]]:
    """Return proof-status rows that adopt each raw fact id or lemma id."""
    if proof_status is None:
        return {}
    adopted: dict[str, set[str]] = {}
    for bucket in PROOF_STATUS_BUCKETS:
        for item in as_tuple(proof_status.get(bucket)):
            if not isinstance(item, dict):
                continue
            row_id = str(item.get("theorem") or item.get("frontier") or bucket)
            for raw_fact in as_tuple(item.get("code_derived_facts")):
                if not isinstance(raw_fact, dict):
                    continue
                keys = {
                    str(raw_fact.get("fact_id", "")),
                    str(raw_fact.get("source_id", "")),
                }
                for key in keys:
                    if key:
                        adopted.setdefault(key, set()).add(row_id)
    return adopted


def coverage_status(
    *,
    graph_node_exists: bool,
    consumed: bool,
    on_target_chain: bool,
    adopted: bool,
    require_adoption: bool,
) -> str:
    """Return one stable fact coverage status."""
    if not graph_node_exists:
        return "missing_graph_node"
    if not consumed:
        return "missing_consumption_edge"
    if not on_target_chain:
        return "not_on_target_chain"
    if require_adoption and not adopted:
        return "missing_proof_status_adoption"
    if adopted:
        return "adopted"
    return "graph_covered"


def build_fact_coverage(
    facts: tuple[dict[str, object], ...],
    *,
    node_ids: set[str],
    consumers_by_fact: dict[str, set[str]],
    target_chain_ids: set[str],
    adoptions: dict[str, set[str]],
    require_adoption: bool,
) -> tuple[FactCoverage, ...]:
    """Build coverage rows for selected facts."""
    rows: list[FactCoverage] = []
    for fact in facts:
        fact_id = str(fact.get("fact_id", ""))
        lemma_id = lemma_id_for_fact(fact_id)
        adopted_by = set(adoptions.get(fact_id, set()))
        adopted_by.update(adoptions.get(lemma_id, set()))
        graph_node_exists = lemma_id in node_ids
        consumed_by = tuple(sorted(consumers_by_fact.get(lemma_id, set())))
        on_target_chain = lemma_id in target_chain_ids
        status = coverage_status(
            graph_node_exists=graph_node_exists,
            consumed=bool(consumed_by),
            on_target_chain=on_target_chain,
            adopted=bool(adopted_by),
            require_adoption=require_adoption,
        )
        rows.append(
            FactCoverage(
                fact_id=fact_id,
                fact_kind=str(fact.get("fact_kind", "")),
                source_path=str(fact.get("source_path", "")),
                source_symbol=str(fact.get("source_symbol", "")),
                target=str(fact.get("target", "")),
                expression=str(fact.get("expression", "")),
                equation_tags=str_tuple(fact.get("equation_tags")),
                target_profiles=str_tuple(fact.get("target_profiles")),
                lemma_id=lemma_id,
                graph_node_exists=graph_node_exists,
                consumed_by_lemma_ids=consumed_by,
                on_target_chain=on_target_chain,
                adopted_by=tuple(sorted(adopted_by)),
                status=status,
            )
        )
    return tuple(rows)


def build_iteration_units(rows: tuple[FactCoverage, ...]) -> tuple[IterationUnit, ...]:
    """Group selected facts by source symbol and equation tags."""
    grouped: dict[tuple[str, str, tuple[str, ...]], list[FactCoverage]] = {}
    for row in rows:
        key = (row.source_path, row.source_symbol, row.equation_tags)
        grouped.setdefault(key, []).append(row)
    units: list[IterationUnit] = []
    for (source_path, source_symbol, tags), facts in sorted(grouped.items()):
        unit_id = f"{source_path}::{source_symbol}:{','.join(tags) or 'untagged'}"
        units.append(
            IterationUnit(
                unit_id=unit_id,
                source_path=source_path,
                source_symbol=source_symbol,
                equation_tags=tags,
                fact_count=len(facts),
                graph_covered_count=sum(1 for fact in facts if fact.graph_node_exists),
                target_chain_count=sum(1 for fact in facts if fact.on_target_chain),
                adopted_count=sum(1 for fact in facts if fact.adopted_by),
            )
        )
    return tuple(units)


def build_findings(
    rows: tuple[FactCoverage, ...],
    *,
    require_adoption: bool,
) -> tuple[CorrespondenceFinding, ...]:
    """Return correspondence findings for coverage rows."""
    findings: list[CorrespondenceFinding] = []
    for row in rows:
        if not row.graph_node_exists:
            findings.append(
                CorrespondenceFinding(
                    severity="error",
                    kind="missing_code_fact_lemma_node",
                    fact_id=row.fact_id,
                    message=f"Expected lemma node `{row.lemma_id}` was not found.",
                )
            )
        elif not row.consumed_by_lemma_ids:
            findings.append(
                CorrespondenceFinding(
                    severity="error",
                    kind="missing_code_fact_consumption_edge",
                    fact_id=row.fact_id,
                    message=f"No `lemma_consumes_code_fact` edge targets `{row.lemma_id}`.",
                )
            )
        elif not row.on_target_chain:
            findings.append(
                CorrespondenceFinding(
                    severity="warning",
                    kind="code_fact_not_on_selected_target_chain",
                    fact_id=row.fact_id,
                    message="The code fact is in the graph but not on the selected target chain.",
                )
            )
        if require_adoption and not row.adopted_by:
            findings.append(
                CorrespondenceFinding(
                    severity="error",
                    kind="missing_proof_status_adoption",
                    fact_id=row.fact_id,
                    message="Selected code fact is not referenced by proof_status code_derived_facts.",
                )
            )
    return tuple(findings)


def build_report(
    *,
    algorithm_ir_paths: tuple[str, ...],
    lemma_graph_paths: tuple[str, ...],
    proof_status_path: str | None,
    fact_kinds: tuple[str, ...],
    profiles: tuple[str, ...],
    tags: tuple[str, ...],
    symbols: tuple[str, ...],
    fact_ids: tuple[str, ...],
    require_adoption: bool,
) -> CorrespondenceReport:
    """Build the IR/lemma graph correspondence report."""
    irs = tuple(load_json(path) for path in algorithm_ir_paths)
    graphs = tuple(load_json(path) for path in lemma_graph_paths)
    proof_status = load_json(proof_status_path) if proof_status_path else None
    facts = selected_ir_facts(
        irs,
        fact_kinds=fact_kinds,
        profiles=profiles,
        tags=tags,
        symbols=symbols,
        fact_ids=fact_ids,
    )
    rows = build_fact_coverage(
        facts,
        node_ids=graph_node_ids(graphs),
        consumers_by_fact=graph_consumers_by_fact(graphs),
        target_chain_ids=graph_target_chain_ids(graphs, profiles),
        adoptions=proof_status_adoptions(proof_status),
        require_adoption=require_adoption,
    )
    findings = build_findings(rows, require_adoption=require_adoption)
    error_count = sum(1 for finding in findings if finding.severity == "error")
    warning_count = sum(1 for finding in findings if finding.severity == "warning")
    valid = error_count == 0
    return CorrespondenceReport(
        status="ir_graph_correspondence_valid" if valid else "ir_graph_correspondence_invalid",
        fact_count=len(rows),
        graph_node_covered_count=sum(1 for row in rows if row.graph_node_exists),
        consumption_edge_covered_count=sum(1 for row in rows if row.consumed_by_lemma_ids),
        target_chain_covered_count=sum(1 for row in rows if row.on_target_chain),
        proof_status_adopted_count=sum(1 for row in rows if row.adopted_by),
        selected_profiles=profiles,
        selected_fact_kinds=fact_kinds,
        selected_equation_tags=tags,
        selected_fact_ids=fact_ids,
        iteration_units=build_iteration_units(rows),
        facts=rows,
        findings=findings,
        validation={
            "valid": valid,
            "error_count": error_count,
            "warning_count": warning_count,
            "graph_node_coverage_complete": all(row.graph_node_exists for row in rows),
            "consumption_edge_coverage_complete": all(row.consumed_by_lemma_ids for row in rows),
            "target_chain_coverage_complete": all(row.on_target_chain for row in rows),
            "proof_status_adoption_required": require_adoption,
            "proof_status_adoption_complete": (not require_adoption)
            or all(row.adopted_by for row in rows),
        },
    )


def render_text(report: CorrespondenceReport) -> str:
    """Render stable text output."""
    lines = [
        f"IR_GRAPH_CORRESPONDENCE={report.status}",
        f"IR_GRAPH_CORRESPONDENCE_VALID={str(report.validation['valid']).lower()}",
        f"IR_GRAPH_FACTS={report.fact_count}",
        f"IR_GRAPH_GRAPH_NODE_COVERED={report.graph_node_covered_count}",
        f"IR_GRAPH_CONSUMPTION_EDGE_COVERED={report.consumption_edge_covered_count}",
        f"IR_GRAPH_TARGET_CHAIN_COVERED={report.target_chain_covered_count}",
        f"IR_GRAPH_PROOF_STATUS_ADOPTED={report.proof_status_adopted_count}",
        f"IR_GRAPH_FINDINGS={len(report.findings)}",
    ]
    for finding in report.findings:
        lines.append(
            "IR_GRAPH_FINDING="
            f"{finding.severity}:{finding.kind}:{finding.fact_id}:{finding.message}"
        )
    return "\n".join(lines) + "\n"


def markdown_cell(value: object) -> str:
    """Escape one Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: CorrespondenceReport) -> str:
    """Render Markdown output."""
    lines = [
        "# IR Graph Correspondence",
        "",
        f"- status: `{report.status}`",
        f"- valid: `{report.validation['valid']}`",
        f"- selected profiles: `{', '.join(report.selected_profiles) or 'all'}`",
        f"- selected fact kinds: `{', '.join(report.selected_fact_kinds)}`",
        f"- selected equation tags: `{', '.join(report.selected_equation_tags) or 'all'}`",
        f"- selected fact ids: `{', '.join(report.selected_fact_ids) or 'all'}`",
        f"- facts: `{report.fact_count}`",
        f"- graph node covered: `{report.graph_node_covered_count}`",
        f"- consumption edge covered: `{report.consumption_edge_covered_count}`",
        f"- target chain covered: `{report.target_chain_covered_count}`",
        f"- proof status adopted: `{report.proof_status_adopted_count}`",
        "",
        "## Findings",
        "",
        "| Severity | Kind | Fact | Message |",
        "| --- | --- | --- | --- |",
    ]
    if report.findings:
        for finding in report.findings:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(finding.severity),
                        markdown_cell(finding.kind),
                        markdown_cell(finding.fact_id),
                        markdown_cell(finding.message),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| info | none | correspondence | no findings |")
    lines.extend(
        [
            "",
            "## Iteration Units",
            "",
            "| Unit | Facts | Graph Covered | Target Chain | Adopted |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for unit in report.iteration_units:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(unit.unit_id),
                    str(unit.fact_count),
                    str(unit.graph_covered_count),
                    str(unit.target_chain_count),
                    str(unit.adopted_count),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Facts",
            "",
            "| Fact | Source | Target | Tags | Graph | Target Chain | Adopted By | Status |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for fact in report.facts:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(fact.fact_id),
                    markdown_cell(f"{fact.source_path}::{fact.source_symbol}"),
                    markdown_cell(fact.target),
                    markdown_cell(", ".join(fact.equation_tags)),
                    markdown_cell(fact.graph_node_exists),
                    markdown_cell(fact.on_target_chain),
                    markdown_cell(", ".join(fact.adopted_by)),
                    markdown_cell(fact.status),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_output(text: str, path: str | None) -> None:
    """Write output to path or stdout."""
    if path:
        Path(path).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = build_parser().parse_args(argv)
    report = build_report(
        algorithm_ir_paths=tuple(args.algorithm_ir),
        lemma_graph_paths=tuple(args.lemma_graph),
        proof_status_path=args.proof_status,
        fact_kinds=tuple(args.fact_kind or DEFAULT_FACT_KINDS),
        profiles=tuple(args.target_profile or ()),
        tags=tuple(args.equation_tag or ()),
        symbols=tuple(args.source_symbol or ()),
        fact_ids=tuple(args.fact_id or ()),
        require_adoption=bool(args.require_proof_status_adoption),
    )
    if args.format == "json":
        text = json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    elif args.format == "markdown":
        text = render_markdown(report)
    else:
        text = render_text(report)
    write_output(text, args.out)
    return 0 if report.validation["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
