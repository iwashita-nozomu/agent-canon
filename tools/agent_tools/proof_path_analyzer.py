#!/usr/bin/env python3
# @dependency-start
# responsibility Analyzes proof-status adoption and proof-path holes over lemma graphs.
# upstream implementation algorithm_lemma_graph.py emits lemma dependency graph JSON.
# upstream design ../../agents/skills/formal-proof-workflow.md defines proof path workflow.
# downstream design ../../documents/tools/proof_path_analyzer.md documents CLI usage.
# downstream implementation ../../tests/agent_tools/test_proof_path_analyzer.py tests it.
# @dependency-end
"""Analyze a proof-status overlay over one or more lemma dependency graphs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

TERMINAL_FRONTIER_STATUSES = frozenset(
    {
        "verified",
        "refuted",
        "unprovable_under_assumptions",
        "unverified_with_next_witness",
        "assumption",
        "algorithm_change_required",
    }
)
OPEN_WITNESS_STATUSES = frozenset(
    {
        "unverified_with_next_witness",
        "assumption",
        "algorithm_change_required",
    }
)
CODE_FACT_DERIVABILITY_CLASSES = frozenset(
    {
        "ir_or_lemma_graph",
        "code_only_ir_algorithm_gap",
        "code_only_code_style_opacity",
        "external_backend_assumption",
        "mathematical_assumption",
        "not_derivable_from_code",
        "proof_status_only",
    }
)
IR_BACKED_CODE_FACT_CLASSES = frozenset({"ir_or_lemma_graph"})
IMPLEMENTATION_TOKEN_RE = re.compile(
    r"(?:[A-Za-z0-9_./-]+\.py::[A-Za-z_][A-Za-z0-9_.]*)|"
    r"(?:[A-Za-z0-9_./-]+\.(?:json|md|lean|py))|"
    r"(?:[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_.]*)|"
    r"(?:(?<![A-Za-z0-9])_[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)"
)
B_LABEL_RE = re.compile(r"\b(B\d+)\b")


@dataclass(frozen=True)
class GraphConnectivity:
    """Recomputed graph connectivity for one lemma graph input."""

    graph_path: str
    target_ids: tuple[str, ...]
    missing_node_ids: tuple[str, ...]
    disconnected_target_ids: tuple[str, ...]
    missing_lemma_ids: tuple[str, ...]
    valid: bool


@dataclass(frozen=True)
class ProofPathFinding:
    """One proof path integrity finding."""

    finding_id: str
    severity: str
    kind: str
    message: str
    subject: str


@dataclass(frozen=True)
class CodeDerivedFact:
    """One code-derived or explicitly non-code proof fact."""

    fact_id: str
    statement: str
    derivability: str
    source_kind: str
    source_id: str
    gap_owner: str
    proof_effect: str


@dataclass(frozen=True)
class ProofPathHole:
    """One connected proof hole or refuted weak route."""

    hole_id: str
    status: str
    implementation_surface: str
    next_witness: str
    missing_assumption: str
    code_derived_facts: tuple[CodeDerivedFact, ...]


@dataclass(frozen=True)
class FrontierMinimality:
    """Minimality check for one returned open frontier row."""

    hole_id: str
    representative_node_ids: tuple[str, ...]
    on_target_chain: bool
    has_smaller_open_target_descendant: bool
    minimal: bool
    evidence: str


@dataclass(frozen=True)
class ProofPathReport:
    """Machine-readable proof path analysis."""

    status: str
    graph_connectivity: tuple[GraphConnectivity, ...]
    graph_source_ir_fingerprints: tuple[str, ...]
    expected_source_ir_fingerprints: tuple[str, ...]
    fingerprint_valid: bool
    proof_complete: bool
    verified_fragment_count: int
    unadopted_verified_fragment_count: int
    open_witness_count: int
    operational_assumption_count: int
    external_assumption_count: int
    unprovable_count: int
    open_witnesses: tuple[ProofPathHole, ...]
    operational_assumptions: tuple[ProofPathHole, ...]
    external_assumptions: tuple[ProofPathHole, ...]
    unprovable_under_assumptions: tuple[ProofPathHole, ...]
    frontier_minimal: bool
    frontier_minimality: tuple[FrontierMinimality, ...]
    code_fact_count: int
    code_fact_derivability_counts: dict[str, int]
    open_witnesses_without_code_facts: tuple[str, ...]
    stale_implementation_tokens: tuple[str, ...]
    duplicate_frontier_labels: tuple[str, ...]
    bare_unverified_frontier_count: int
    findings: tuple[ProofPathFinding, ...]
    validation: dict[str, Any]


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lemma-graph",
        action="append",
        required=True,
        help="Lemma graph JSON file. May be passed multiple times.",
    )
    parser.add_argument("--proof-status", required=True, help="Proof status JSON file.")
    parser.add_argument(
        "--algorithm-ir",
        action="append",
        default=None,
        help="Algorithm Expansion IR JSON file used to validate code-derived fact source ids.",
    )
    parser.add_argument(
        "--proof-frontier",
        action="append",
        default=None,
        help="Reader-facing frontier/adoption text to scan. May be repeated.",
    )
    parser.add_argument(
        "--adoption-text",
        action="append",
        default=None,
        help="Additional text file used to confirm checked-fragment adoption.",
    )
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    parser.add_argument("--out", help="Optional output path. Omit to print stdout.")
    return parser


def load_json(path: str) -> dict[str, Any]:
    """Load a JSON object."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def as_tuple(value: object) -> tuple[Any, ...]:
    """Return JSON-ish sequences as tuples."""
    if isinstance(value, list | tuple):
        return tuple(value)
    return ()


def as_str_tuple(value: object) -> tuple[str, ...]:
    """Return JSON-ish sequences as string tuples."""
    return tuple(str(item) for item in as_tuple(value))


def graph_connectivity(path: str, graph: dict[str, Any]) -> GraphConnectivity:
    """Recompute graph endpoint and target-chain connectivity."""
    node_ids = {
        str(node.get("lemma_id"))
        for node in as_tuple(graph.get("lemma_nodes"))
        if isinstance(node, dict)
    }
    missing_edge_ids: set[str] = set()
    adjacency: dict[str, list[str]] = {}
    for edge in as_tuple(graph.get("lemma_edges")):
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source_lemma_id", ""))
        target = str(edge.get("target_lemma_id", ""))
        if source not in node_ids:
            missing_edge_ids.add(source)
            continue
        if target not in node_ids:
            missing_edge_ids.add(target)
            continue
        adjacency.setdefault(source, []).append(target)

    target_ids: list[str] = []
    disconnected_targets: set[str] = set()
    missing_lemmas: set[str] = set()
    for chain in as_tuple(graph.get("target_chains")):
        if not isinstance(chain, dict):
            continue
        target_id = str(chain.get("target_id", ""))
        target_ids.append(target_id)
        expected = set(as_str_tuple(chain.get("lemma_ids")))
        reachable: set[str] = set()
        stack = list(adjacency.get(target_id, ()))
        while stack:
            node_id = stack.pop()
            if node_id in reachable:
                continue
            reachable.add(node_id)
            stack.extend(adjacency.get(node_id, ()))
        missing = expected - reachable
        if missing:
            disconnected_targets.add(target_id)
            missing_lemmas.update(missing)

    return GraphConnectivity(
        graph_path=path,
        target_ids=tuple(sorted(target_ids)),
        missing_node_ids=tuple(sorted(missing_edge_ids)),
        disconnected_target_ids=tuple(sorted(disconnected_targets)),
        missing_lemma_ids=tuple(sorted(missing_lemmas)),
        valid=not missing_edge_ids and not disconnected_targets,
    )


def graph_text_corpus(graphs: tuple[dict[str, Any], ...]) -> str:
    """Return a searchable text corpus from lemma graph nodes."""
    parts: list[str] = []
    for graph in graphs:
        for node in as_tuple(graph.get("lemma_nodes")):
            if not isinstance(node, dict):
                continue
            parts.extend(
                [
                    str(node.get("lemma_id", "")),
                    str(node.get("label", "")),
                    str(node.get("statement", "")),
                    str(node.get("remaining_gap", "")),
                    " ".join(as_str_tuple(node.get("source_symbols"))),
                    " ".join(as_str_tuple(node.get("source_paths"))),
                    " ".join(as_str_tuple(node.get("source_code_facts"))),
                ]
            )
    return "\n".join(parts)


def graph_node_ids(graphs: tuple[dict[str, Any], ...]) -> set[str]:
    """Return all lemma node ids from all graphs."""
    return {
        str(node.get("lemma_id", ""))
        for graph in graphs
        for node in as_tuple(graph.get("lemma_nodes"))
        if isinstance(node, dict)
    }


def graph_adjacency(graphs: tuple[dict[str, Any], ...]) -> dict[str, set[str]]:
    """Return dependency adjacency across all graph edges."""
    adjacency: dict[str, set[str]] = {}
    for graph in graphs:
        for edge in as_tuple(graph.get("lemma_edges")):
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("source_lemma_id", ""))
            target = str(edge.get("target_lemma_id", ""))
            if source and target:
                adjacency.setdefault(source, set()).add(target)
    return adjacency


def graph_target_chain_ids(graphs: tuple[dict[str, Any], ...]) -> set[str]:
    """Return node ids selected by target chains."""
    selected: set[str] = set()
    for graph in graphs:
        for chain in as_tuple(graph.get("target_chains")):
            if not isinstance(chain, dict):
                continue
            target_id = str(chain.get("target_id", ""))
            if target_id:
                selected.add(target_id)
            selected.update(as_str_tuple(chain.get("lemma_ids")))
            selected.update(as_str_tuple(chain.get("reachable_lemma_ids")))
    return selected


def graph_source_ir_fingerprints(graphs: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    """Return source Algorithm Expansion IR fingerprints recorded by graphs."""
    return tuple(
        sorted(
            {
                str(graph.get("source_ir_fingerprint", ""))
                for graph in graphs
                if graph.get("source_ir_fingerprint")
            }
        )
    )


def expected_source_ir_fingerprints(proof_status: dict[str, Any]) -> tuple[str, ...]:
    """Return proof-status fingerprints that generated lemma overlays must match."""
    if isinstance(proof_status.get("source_ir_fingerprint"), str):
        return (str(proof_status["source_ir_fingerprint"]),)
    values = proof_status.get("source_ir_fingerprints")
    if isinstance(values, list | tuple):
        return tuple(sorted(str(value) for value in values if value))
    return ()


def descendant_node_ids(adjacency: dict[str, set[str]], roots: tuple[str, ...]) -> set[str]:
    """Return all graph descendants reachable from roots."""
    descendants: set[str] = set()
    stack = list(roots)
    while stack:
        node_id = stack.pop()
        for child in adjacency.get(node_id, ()):
            if child in descendants:
                continue
            descendants.add(child)
            stack.append(child)
    return descendants


def ir_text_corpus(irs: tuple[dict[str, Any], ...]) -> str:
    """Return searchable text from Algorithm Expansion IR files."""
    parts: list[str] = []
    for ir in irs:
        parts.extend(
            [
                str(ir.get("root_path", "")),
                str(ir.get("root_symbol", "")),
                str(ir.get("target_theorem", "")),
            ]
        )
        for node in as_tuple(ir.get("nodes")):
            if not isinstance(node, dict):
                continue
            parts.extend(str(value) for value in node.values())
        for edge in as_tuple(ir.get("edges")):
            if not isinstance(edge, dict):
                continue
            parts.extend(str(value) for value in edge.values())
        for obligation in as_tuple(ir.get("obligations")):
            if not isinstance(obligation, dict):
                continue
            parts.extend(str(value) for value in obligation.values())
        for check in as_tuple(ir.get("static_checks")):
            if not isinstance(check, dict):
                continue
            parts.extend(str(value) for value in check.values())
        for assumption in as_tuple(ir.get("backend_assumptions")):
            if not isinstance(assumption, dict):
                continue
            parts.extend(str(value) for value in assumption.values())
        for fact in as_tuple(ir.get("code_facts")):
            if not isinstance(fact, dict):
                continue
            parts.extend(str(value) for value in fact.values())
    return "\n".join(parts)


def adoption_text(paths: tuple[str, ...]) -> str:
    """Read text files used to check checked-fragment adoption."""
    chunks: list[str] = []
    for path in paths:
        chunks.append(Path(path).read_text(encoding="utf-8"))
    return "\n".join(chunks)


def entries(payload: dict[str, Any], key: str) -> tuple[dict[str, Any], ...]:
    """Return proof-status entry dictionaries."""
    return tuple(item for item in as_tuple(payload.get(key)) if isinstance(item, dict))


def code_derived_facts(item: dict[str, Any]) -> tuple[CodeDerivedFact, ...]:
    """Return normalized code-derived facts from a proof-status row."""
    facts: list[CodeDerivedFact] = []
    for raw_fact in as_tuple(item.get("code_derived_facts")):
        if not isinstance(raw_fact, dict):
            continue
        facts.append(
            CodeDerivedFact(
                fact_id=str(raw_fact.get("fact_id", "")),
                statement=str(raw_fact.get("statement", "")),
                derivability=str(raw_fact.get("derivability", "")),
                source_kind=str(raw_fact.get("source_kind", "")),
                source_id=str(raw_fact.get("source_id", "")),
                gap_owner=str(raw_fact.get("gap_owner", "")),
                proof_effect=str(raw_fact.get("proof_effect", "")),
            )
        )
    return tuple(facts)


def b_label_name(text: str) -> tuple[str | None, str]:
    """Extract the first B-label and normalized name from one frontier string."""
    match = B_LABEL_RE.search(text)
    if match is None:
        return None, text.strip()
    label = match.group(1)
    name = text[match.end() :].strip(" :-")
    return label, name


def duplicate_label_names(pairs: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    """Return B-labels attached to multiple names within one source."""
    label_to_names: dict[str, set[str]] = {}
    for label, name in pairs:
        if name:
            label_to_names.setdefault(label, set()).add(name)
    return tuple(sorted(label for label, names in label_to_names.items() if len(names) > 1))


def duplicate_b_labels(proof_status: dict[str, Any], text_paths: tuple[str, ...]) -> tuple[str, ...]:
    """Return B-labels that collide within a single frontier source."""
    duplicates: set[str] = set()
    status_pairs: list[tuple[str, str]] = []
    for item in entries(proof_status, "open_frontier"):
        label, name = b_label_name(str(item.get("frontier", "")))
        if label is not None:
            status_pairs.append((label, name))
    duplicates.update(duplicate_label_names(tuple(status_pairs)))

    for path in text_paths:
        source_pairs: list[tuple[str, str]] = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [cell.strip(" `") for cell in line.strip().strip("|").split("|")]
            if not cells:
                continue
            label, name = b_label_name(cells[0])
            if label is not None and name and name not in {"Frontier", "---"}:
                source_pairs.append((label, name))
        duplicates.update(duplicate_label_names(tuple(source_pairs)))

    return tuple(sorted(duplicates))


def bare_unverified_frontiers(proof_status: dict[str, Any], text_paths: tuple[str, ...]) -> tuple[str, ...]:
    """Return frontier rows that use bare unverified as a terminal outcome."""
    bad: list[str] = []
    for item in entries(proof_status, "open_frontier"):
        if str(item.get("status", "")) == "unverified":
            bad.append(str(item.get("frontier", "<unnamed frontier>")))

    for path in text_paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if "unverified_with_next_witness" in line:
                continue
            if re.search(r"\bunverified\b", line):
                bad.append(f"{path}: {line.strip()}")
    return tuple(bad)


def implementation_tokens(text: str) -> tuple[str, ...]:
    """Extract implementation-looking tokens from proof-status surfaces."""
    tokens = []
    for token in IMPLEMENTATION_TOKEN_RE.findall(text):
        cleaned = token.strip("`.,;:()[]")
        if cleaned:
            tokens.append(cleaned)
    return tuple(tokens)


def token_is_valid(token: str, corpus: str) -> bool:
    """Return whether one implementation token is supported by graph text or the filesystem."""
    if token in corpus:
        return True
    if "::" in token:
        path, symbol = token.split("::", 1)
        return path in corpus and symbol in corpus
    if token.startswith("_"):
        return token in corpus
    if token.endswith((".json", ".md", ".lean", ".py")):
        return token in corpus or Path(token).exists()
    return token in corpus


def stale_implementation_tokens(proof_status: dict[str, Any], corpus: str) -> tuple[str, ...]:
    """Return implementation tokens not present in graph text or the filesystem."""
    stale: set[str] = set()
    for bucket in (
        "checked_fragments",
        "unprovable_under_assumptions",
        "open_frontier",
        "operational_assumptions",
        "external_assumptions",
    ):
        for item in entries(proof_status, bucket):
            surface = str(item.get("implementation_surface", ""))
            for token in implementation_tokens(surface):
                if not token_is_valid(token, corpus):
                    stale.add(token)
    return tuple(sorted(stale))


def code_fact_derivability_counts(facts: tuple[CodeDerivedFact, ...]) -> dict[str, int]:
    """Count code-derived facts by derivability class."""
    counts: dict[str, int] = {}
    for fact in facts:
        counts[fact.derivability] = counts.get(fact.derivability, 0) + 1
    return counts


def representative_node_ids(
    hole: ProofPathHole,
    *,
    node_ids: set[str],
    target_chain_ids: set[str],
) -> tuple[str, ...]:
    """Return graph node ids that represent one open frontier hole."""
    ids = {
        fact.source_id
        for fact in hole.code_derived_facts
        if fact.source_id in node_ids and fact.source_id in target_chain_ids
    }
    return tuple(sorted(ids))


def frontier_minimality_rows(
    open_witnesses: tuple[ProofPathHole, ...],
    *,
    node_ids: set[str],
    adjacency: dict[str, set[str]],
    target_chain_ids: set[str],
) -> tuple[FrontierMinimality, ...]:
    """Check whether returned open witnesses are minimal graph-frontier rows."""
    representatives = {
        hole.hole_id: representative_node_ids(
            hole,
            node_ids=node_ids,
            target_chain_ids=target_chain_ids,
        )
        for hole in open_witnesses
    }
    rows: list[FrontierMinimality] = []
    for hole in open_witnesses:
        reps = representatives[hole.hole_id]
        descendants = descendant_node_ids(adjacency, reps)
        smaller_holes = tuple(
            other.hole_id
            for other in open_witnesses
            if other.hole_id != hole.hole_id
            and bool(set(representatives[other.hole_id]) & descendants)
        )
        on_target_chain = bool(reps)
        has_smaller = bool(smaller_holes)
        minimal = on_target_chain and not has_smaller
        if not on_target_chain:
            evidence = "no representative source_id from this open row appears on a target chain"
        elif has_smaller:
            evidence = "smaller open target-chain descendants: " + ", ".join(smaller_holes)
        else:
            evidence = "representative source_ids are on a target chain and hide no smaller open target-chain descendant"
        rows.append(
            FrontierMinimality(
                hole_id=hole.hole_id,
                representative_node_ids=reps,
                on_target_chain=on_target_chain,
                has_smaller_open_target_descendant=has_smaller,
                minimal=minimal,
                evidence=evidence,
            )
        )
    return tuple(rows)


def validate_code_derived_fact(fact: CodeDerivedFact, corpus: str) -> tuple[str, ...]:
    """Return validation finding messages for one code-derived fact."""
    problems: list[str] = []
    if fact.derivability not in CODE_FACT_DERIVABILITY_CLASSES:
        problems.append(f"unsupported derivability class `{fact.derivability}`")
    if not fact.statement:
        problems.append("missing statement")
    if not fact.fact_id:
        problems.append("missing fact_id")
    if fact.derivability in IR_BACKED_CODE_FACT_CLASSES:
        if not fact.source_id:
            problems.append("IR-backed fact is missing source_id")
        elif fact.source_id not in corpus:
            problems.append(f"IR-backed source_id `{fact.source_id}` was not found in graph/IR text")
    return tuple(problems)


def build_report(
    *,
    graph_paths: tuple[str, ...],
    algorithm_ir_paths: tuple[str, ...],
    proof_status_path: str,
    proof_frontier_paths: tuple[str, ...],
    adoption_paths: tuple[str, ...],
) -> ProofPathReport:
    """Build proof path analysis report."""
    graphs = tuple(load_json(path) for path in graph_paths)
    algorithm_irs = tuple(load_json(path) for path in algorithm_ir_paths)
    proof_status = load_json(proof_status_path)
    connectivity = tuple(
        graph_connectivity(path, graph) for path, graph in zip(graph_paths, graphs, strict=True)
    )
    adoption_corpus = adoption_text(proof_frontier_paths + adoption_paths)
    graph_corpus = graph_text_corpus(graphs)
    proof_source_corpus = "\n".join([graph_corpus, ir_text_corpus(algorithm_irs)])
    node_ids = graph_node_ids(graphs)
    adjacency = graph_adjacency(graphs)
    target_chain_ids = graph_target_chain_ids(graphs)
    graph_fingerprints = graph_source_ir_fingerprints(graphs)
    expected_fingerprints = expected_source_ir_fingerprints(proof_status)
    fingerprint_valid = not expected_fingerprints or set(expected_fingerprints).issubset(
        set(graph_fingerprints)
    )

    checked = entries(proof_status, "checked_fragments")
    unadopted = tuple(
        str(item.get("theorem", ""))
        for item in checked
        if str(item.get("status", "")) == "verified"
        and str(item.get("theorem", "")) not in adoption_corpus
    )
    open_frontier = entries(proof_status, "open_frontier")
    operational_assumption_rows = entries(proof_status, "operational_assumptions")
    external_assumption_rows = entries(proof_status, "external_assumptions")
    unprovable = entries(proof_status, "unprovable_under_assumptions")
    frontier_unprovable = tuple(
        item
        for item in open_frontier
        if str(item.get("status", "")) == "unprovable_under_assumptions"
    )
    open_witnesses = tuple(
        ProofPathHole(
            hole_id=str(item.get("frontier", "")),
            status=str(item.get("status", "")),
            implementation_surface=str(item.get("implementation_surface", "")),
            next_witness=str(item.get("next_witness", "")),
            missing_assumption="",
            code_derived_facts=code_derived_facts(item),
        )
        for item in open_frontier
        if str(item.get("status", "")) in OPEN_WITNESS_STATUSES
    )
    unprovable_witnesses = tuple(
        ProofPathHole(
            hole_id=str(item.get("theorem") or item.get("frontier", "")),
            status=str(item.get("status", "")),
            implementation_surface=str(item.get("implementation_surface", "")),
            next_witness="",
            missing_assumption=str(item.get("missing_assumption") or item.get("next_witness", "")),
            code_derived_facts=code_derived_facts(item),
        )
        for item in unprovable + frontier_unprovable
    )
    operational_assumptions = tuple(
        ProofPathHole(
            hole_id=str(item.get("frontier", "")),
            status=str(item.get("status", "")),
            implementation_surface=str(item.get("implementation_surface", "")),
            next_witness=str(item.get("next_witness", "")),
            missing_assumption="",
            code_derived_facts=code_derived_facts(item),
        )
        for item in operational_assumption_rows
    )
    external_assumptions = tuple(
        ProofPathHole(
            hole_id=str(item.get("frontier", "")),
            status=str(item.get("status", "")),
            implementation_surface=str(item.get("implementation_surface", "")),
            next_witness=str(item.get("next_witness", "")),
            missing_assumption="",
            code_derived_facts=code_derived_facts(item),
        )
        for item in external_assumption_rows
    )
    bare = bare_unverified_frontiers(proof_status, proof_frontier_paths)
    stale = stale_implementation_tokens(proof_status, graph_corpus)
    duplicate_labels = duplicate_b_labels(proof_status, proof_frontier_paths)
    all_code_facts = tuple(
        fact
        for hole in open_witnesses
        + unprovable_witnesses
        + operational_assumptions
        + external_assumptions
        for fact in hole.code_derived_facts
    )
    open_without_code_facts = tuple(
        hole.hole_id for hole in open_witnesses if not hole.code_derived_facts
    )
    frontier_minimality = frontier_minimality_rows(
        open_witnesses,
        node_ids=node_ids,
        adjacency=adjacency,
        target_chain_ids=target_chain_ids,
    )
    frontier_minimal = all(row.minimal for row in frontier_minimality)

    findings: list[ProofPathFinding] = []
    for item in connectivity:
        for node_id in item.missing_node_ids:
            findings.append(
                ProofPathFinding(
                    finding_id=f"missing-node-{len(findings) + 1}",
                    severity="error",
                    kind="missing_node",
                    message="Lemma graph edge references a missing node.",
                    subject=node_id,
                )
            )
        for target_id in item.disconnected_target_ids:
            findings.append(
                ProofPathFinding(
                    finding_id=f"disconnected-target-{len(findings) + 1}",
                    severity="error",
                    kind="disconnected_target",
                    message="Target chain cannot reach every selected lemma.",
                    subject=target_id,
                )
            )
    for theorem in unadopted:
        findings.append(
            ProofPathFinding(
                finding_id=f"unadopted-fragment-{len(findings) + 1}",
                severity="error",
                kind="unadopted_verified_fragment",
                message="Verified checker fragment is absent from adoption text.",
                subject=theorem,
            )
        )
    for subject in bare:
        findings.append(
            ProofPathFinding(
                finding_id=f"bare-unverified-{len(findings) + 1}",
                severity="error",
                kind="bare_unverified_frontier",
                message="Frontier row uses bare unverified without a named next witness.",
                subject=subject,
            )
        )
    for token in stale:
        findings.append(
            ProofPathFinding(
                finding_id=f"stale-token-{len(findings) + 1}",
                severity="error",
                kind="stale_implementation_token",
                message="Proof status references an implementation token not supported by graphs.",
                subject=token,
            )
        )
    for label in duplicate_labels:
        findings.append(
            ProofPathFinding(
                finding_id=f"duplicate-label-{len(findings) + 1}",
                severity="error",
                kind="duplicate_frontier_label",
                message="One frontier label names more than one proof obligation.",
                subject=label,
            )
        )
    if not fingerprint_valid:
        findings.append(
            ProofPathFinding(
                finding_id=f"stale-algorithm-fingerprint-{len(findings) + 1}",
                severity="error",
                kind="stale_algorithm_lemma_group",
                message=(
                    "proof_status source_ir_fingerprints are absent from the "
                    "supplied lemma graphs; regenerate Algorithm Expansion IR, "
                    "lemma graphs, and proof-status overlay before adopting "
                    "these lemmas"
                ),
                subject=", ".join(expected_fingerprints),
            )
        )
    for row in frontier_minimality:
        if not row.minimal:
            findings.append(
                ProofPathFinding(
                    finding_id=f"frontier-minimality-{len(findings) + 1}",
                    severity="error",
                    kind="nonminimal_frontier_blocker",
                    message=row.evidence,
                    subject=row.hole_id,
                )
            )
    for fact in all_code_facts:
        for problem in validate_code_derived_fact(fact, proof_source_corpus):
            findings.append(
                ProofPathFinding(
                    finding_id=f"code-fact-{len(findings) + 1}",
                    severity="error",
                    kind="invalid_code_derived_fact",
                    message=problem,
                    subject=fact.fact_id,
                )
            )

    graph_valid = all(item.valid for item in connectivity)
    integrity_valid = not findings
    open_witness_count = len(open_witnesses)
    unprovable_count = len(unprovable_witnesses)
    proof_complete = (
        graph_valid
        and integrity_valid
        and open_witness_count == 0
        and unprovable_count == 0
        and all(str(item.get("status", "")) == "verified" for item in checked)
    )
    valid = graph_valid and integrity_valid
    return ProofPathReport(
        status="proof_path_valid" if valid else "proof_path_invalid",
        graph_connectivity=connectivity,
        graph_source_ir_fingerprints=graph_fingerprints,
        expected_source_ir_fingerprints=expected_fingerprints,
        fingerprint_valid=fingerprint_valid,
        proof_complete=proof_complete,
        verified_fragment_count=sum(1 for item in checked if item.get("status") == "verified"),
        unadopted_verified_fragment_count=len(unadopted),
        open_witness_count=open_witness_count,
        operational_assumption_count=len(operational_assumptions),
        external_assumption_count=len(external_assumptions),
        unprovable_count=unprovable_count,
        open_witnesses=open_witnesses,
        operational_assumptions=operational_assumptions,
        external_assumptions=external_assumptions,
        unprovable_under_assumptions=unprovable_witnesses,
        frontier_minimal=frontier_minimal,
        frontier_minimality=frontier_minimality,
        code_fact_count=len(all_code_facts),
        code_fact_derivability_counts=code_fact_derivability_counts(all_code_facts),
        open_witnesses_without_code_facts=open_without_code_facts,
        stale_implementation_tokens=stale,
        duplicate_frontier_labels=duplicate_labels,
        bare_unverified_frontier_count=len(bare),
        findings=tuple(findings),
        validation={
            "valid": valid,
            "graph_connected": graph_valid,
            "integrity_valid": integrity_valid,
            "connected": graph_valid,
            "proof_complete": proof_complete,
            "frontier_minimal": frontier_minimal,
            "algorithm_fingerprint_valid": fingerprint_valid,
        },
    )


def render_text(report: ProofPathReport) -> str:
    """Render stable text output."""
    lines = [
        f"PROOF_PATH={report.status}",
        f"PROOF_PATH_VALID={str(report.validation['valid']).lower()}",
        f"PROOF_PATH_CONNECTED={str(report.validation['connected']).lower()}",
        f"PROOF_PATH_COMPLETE={str(report.proof_complete).lower()}",
        f"PROOF_PATH_ALGORITHM_FINGERPRINT_VALID={str(report.fingerprint_valid).lower()}",
        f"PROOF_PATH_FRONTIER_MINIMAL={str(report.frontier_minimal).lower()}",
        f"PROOF_PATH_OPEN_WITNESSES={report.open_witness_count}",
        f"PROOF_PATH_OPERATIONAL_ASSUMPTIONS={report.operational_assumption_count}",
        f"PROOF_PATH_EXTERNAL_ASSUMPTIONS={report.external_assumption_count}",
        f"PROOF_PATH_CODE_FACTS={report.code_fact_count}",
        f"PROOF_PATH_FINDINGS={len(report.findings)}",
    ]
    for finding in report.findings:
        lines.append(
            "PROOF_PATH_FINDING="
            f"{finding.severity}:{finding.kind}:{finding.subject}:{finding.message}"
        )
    return "\n".join(lines) + "\n"


def markdown_cell(value: object) -> str:
    """Escape a Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: ProofPathReport) -> str:
    """Render Markdown output."""
    lines = [
        "# Proof Path Analysis",
        "",
        f"- status: `{report.status}`",
        f"- graph connected: `{report.validation['connected']}`",
        f"- proof complete: `{report.proof_complete}`",
        f"- algorithm fingerprint valid: `{report.fingerprint_valid}`",
        f"- frontier minimal: `{report.frontier_minimal}`",
        f"- verified fragments: `{report.verified_fragment_count}`",
        f"- open witnesses: `{report.open_witness_count}`",
        f"- operational assumptions: `{report.operational_assumption_count}`",
        f"- external assumptions: `{report.external_assumption_count}`",
        f"- unprovable-under-assumption rows: `{report.unprovable_count}`",
        f"- code-derived facts: `{report.code_fact_count}`",
        "",
        "## Algorithm Fingerprints",
        "",
        "| Kind | Fingerprints |",
        "| --- | --- |",
        f"| graph source IR | `{', '.join(report.graph_source_ir_fingerprints) or 'none'}` |",
        f"| proof status expected | `{', '.join(report.expected_source_ir_fingerprints) or 'none'}` |",
        f"| valid | `{report.fingerprint_valid}` |",
        "",
        "## Graph Connectivity",
        "",
        "| Graph | Targets | Missing Nodes | Disconnected Targets | Valid |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report.graph_connectivity:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(item.graph_path),
                    markdown_cell(", ".join(item.target_ids)),
                    markdown_cell(", ".join(item.missing_node_ids)),
                    markdown_cell(", ".join(item.disconnected_target_ids)),
                    markdown_cell(item.valid),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Findings",
            "",
            "| Severity | Kind | Subject | Message |",
            "| --- | --- | --- | --- |",
        ]
    )
    if report.findings:
        for finding in report.findings:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(finding.severity),
                        markdown_cell(finding.kind),
                        markdown_cell(finding.subject),
                        markdown_cell(finding.message),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| info | none | proof path overlay | no integrity findings |")
    lines.extend(
        [
            "",
            "## Open Witnesses",
            "",
            "Open witnesses are connected proof holes, not structural graph failures.",
            "",
            "| Hole | Status | Implementation Surface | Next Witness |",
            "| --- | --- | --- | --- |",
        ]
    )
    if report.open_witnesses:
        for hole in report.open_witnesses:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(hole.hole_id),
                        markdown_cell(hole.status),
                        markdown_cell(hole.implementation_surface),
                        markdown_cell(hole.next_witness),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| info | none | proof path overlay | no open witnesses |")
    lines.extend(
        [
            "",
            "## Frontier Minimality",
            "",
            "Each returned open witness must be the first nonterminal target-chain row, not a higher-level blocker hiding a smaller open witness.",
            "",
            "| Hole | Minimal | Target-Chain Representatives | Evidence |",
            "| --- | --- | --- | --- |",
        ]
    )
    if report.frontier_minimality:
        for row in report.frontier_minimality:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(row.hole_id),
                        markdown_cell(row.minimal),
                        markdown_cell(", ".join(row.representative_node_ids)),
                        markdown_cell(row.evidence),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| info | true | proof path overlay | no open witnesses |")
    lines.extend(
        [
            "",
            "## Operational Assumptions",
            "",
            "Operational assumptions fix the implemented algorithm trace; convergence remains a derived lemma on that trace.",
            "",
            "| Assumption | Status | Implementation Surface | Role |",
            "| --- | --- | --- | --- |",
        ]
    )
    if report.operational_assumptions:
        for hole in report.operational_assumptions:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(hole.hole_id),
                        markdown_cell(hole.status),
                        markdown_cell(hole.implementation_surface),
                        markdown_cell(hole.next_witness),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| info | none | proof path overlay | no operational assumptions |")
    lines.extend(
        [
            "",
            "## External Assumptions",
            "",
            "External assumptions are trusted proof boundaries, not open PDIPM algorithm witnesses.",
            "",
            "| Assumption | Status | Implementation Surface | Boundary |",
            "| --- | --- | --- | --- |",
        ]
    )
    if report.external_assumptions:
        for hole in report.external_assumptions:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(hole.hole_id),
                        markdown_cell(hole.status),
                        markdown_cell(hole.implementation_surface),
                        markdown_cell(hole.next_witness),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| info | none | proof path overlay | no external assumptions |")
    lines.extend(
        [
            "",
            "## Code-Derived Facts",
            "",
            "| Hole | Fact | Derivability | Source | Gap Owner | Proof Effect |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    fact_rows = [
        (hole.hole_id, fact)
        for hole in report.open_witnesses + report.unprovable_under_assumptions
        for fact in hole.code_derived_facts
    ]
    if fact_rows:
        for hole_id, fact in fact_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(hole_id),
                        markdown_cell(fact.statement),
                        markdown_cell(fact.derivability),
                        markdown_cell(f"{fact.source_kind}:{fact.source_id}"),
                        markdown_cell(fact.gap_owner),
                        markdown_cell(fact.proof_effect),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| info | none | proof path overlay | none | none | no code-derived facts recorded |")
    lines.extend(
        [
            "",
            "## Refuted Weak Routes",
            "",
            "| Theorem | Implementation Surface | Missing Assumption |",
            "| --- | --- | --- |",
        ]
    )
    if report.unprovable_under_assumptions:
        for hole in report.unprovable_under_assumptions:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(hole.hole_id),
                        markdown_cell(hole.implementation_surface),
                        markdown_cell(hole.missing_assumption),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| info | proof path overlay | no refuted weak routes |")
    return "\n".join(lines) + "\n"


def write_or_print(content: str, path: str | None) -> None:
    """Write content to path or stdout."""
    if path:
        Path(path).write_text(content, encoding="utf-8")
    else:
        sys.stdout.write(content)


def main(argv: list[str] | None = None) -> int:
    """Run proof path analyzer."""
    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_report(
        graph_paths=tuple(args.lemma_graph),
        algorithm_ir_paths=tuple(args.algorithm_ir or ()),
        proof_status_path=args.proof_status,
        proof_frontier_paths=tuple(args.proof_frontier or ()),
        adoption_paths=tuple(args.adoption_text or ()),
    )
    if args.format == "json":
        output = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    elif args.format == "markdown":
        output = render_markdown(report)
    else:
        output = render_text(report)
    write_or_print(output, args.out)
    return 0 if report.validation["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
