#!/usr/bin/env python3
# @dependency-start
# responsibility Builds a lemma dependency graph from Algorithm Expansion IR JSON.
# upstream implementation algorithm_expansion_ir.py emits Algorithm Expansion IR JSON.
# upstream design ../../agents/skills/formal-proof-workflow.md defines proof graph workflow.
# downstream design ../../documents/tools/algorithm_lemma_graph.md documents CLI usage.
# downstream implementation ../../tests/agent_tools/test_algorithm_lemma_graph.py tests it.
# @dependency-end
"""Build a lemma dependency graph from Algorithm Expansion IR JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

STATIC_EDGE_STATUSES = frozenset(
    {
        "statically_checked",
        "static_checker_required",
        "static_resolution_gap",
    }
)
KNOWN_TARGET_PROFILES = (
    "all",
    "certificate_soundness",
    "local_convergence",
    "fp32_floor",
    "solver_chain",
    "reduced_kkt",
    "step_update",
    "floor_preserving_step",
    "minres_defaults",
    "pdipm_initialization_path",
)


@dataclass(frozen=True)
class LemmaNode:
    """One lemma, theorem target, or static structural claim."""

    lemma_id: str
    label: str
    statement: str
    lemma_kind: str
    proof_status: str
    source_obligation_id: str | None
    source_nodes: tuple[str, ...]
    source_edges: tuple[str, ...]
    source_symbols: tuple[str, ...]
    source_paths: tuple[str, ...]
    source_code_facts: tuple[str, ...]
    math_role: str
    residual_unit: str
    precision_model: str
    target_profiles: tuple[str, ...]
    remaining_gap: str


@dataclass(frozen=True)
class LemmaEdge:
    """One directed dependency edge between lemma graph nodes."""

    edge_id: str
    source_lemma_id: str
    target_lemma_id: str
    edge_kind: str
    reason: str
    source_ir_edge_id: str | None
    status: str


@dataclass(frozen=True)
class TargetChain:
    """Reachability result for one theorem target/profile."""

    target_id: str
    profile: str
    theorem: str
    lemma_ids: tuple[str, ...]
    reachable_lemma_ids: tuple[str, ...]
    missing_lemma_ids: tuple[str, ...]
    connected: bool


@dataclass(frozen=True)
class LemmaGraphValidation:
    """Mechanical validation summary for a lemma graph."""

    node_count: int
    edge_count: int
    target_count: int
    missing_edge_target_ids: tuple[str, ...]
    cycle_edge_ids: tuple[str, ...]
    disconnected_target_ids: tuple[str, ...]
    connected: bool
    acyclic: bool
    valid: bool


@dataclass(frozen=True)
class LemmaGraphReport:
    """Machine-readable lemma graph report."""

    status: str
    source_ir_status: str
    source_ir_fingerprint: str
    root: str
    theorem: str
    target_profiles: tuple[str, ...]
    lemma_nodes: tuple[LemmaNode, ...]
    lemma_edges: tuple[LemmaEdge, ...]
    target_chains: tuple[TargetChain, ...]
    validation: LemmaGraphValidation


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ir-json",
        help="Algorithm Expansion IR JSON file. Omit or pass '-' to read stdin.",
    )
    parser.add_argument(
        "--target-profile",
        action="append",
        choices=KNOWN_TARGET_PROFILES,
        help="Target profile to materialize. Defaults to all known profiles.",
    )
    parser.add_argument("--format", choices=("text", "json", "markdown", "dot"), default="text")
    parser.add_argument("--out", help="Optional output path. Omit to print stdout.")
    return parser


def algorithm_fingerprint(ir_payload: dict[str, object]) -> str:
    """Return a stable fingerprint for algorithm-derived lemma groups.

    The fingerprint deliberately follows the Algorithm Expansion IR, not a
    hand-edited proof overlay. If the algorithm expansion changes, generated
    lemma groups derived from the old IR must be regenerated or treated as
    stale.
    """
    fingerprint_payload = {
        "root_path": ir_payload.get("root_path", ""),
        "root_symbol": ir_payload.get("root_symbol", ""),
        "target_theorem": ir_payload.get("target_theorem", ""),
        "nodes": ir_payload.get("nodes", []),
        "edges": ir_payload.get("edges", []),
        "code_facts": ir_payload.get("code_facts", []),
        "static_checks": ir_payload.get("static_checks", []),
        "backend_assumptions": ir_payload.get("backend_assumptions", []),
        "obligations": ir_payload.get("obligations", []),
        "goal_directed_slice": ir_payload.get("goal_directed_slice", []),
        "selected_local_obligations": ir_payload.get("selected_local_obligations", []),
    }
    encoded = json.dumps(
        fingerprint_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def slug(value: str) -> str:
    """Return a stable identifier fragment."""
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_").lower()
    return normalized or "unnamed"


def read_ir_payload(path: str | None) -> dict[str, object]:
    """Read Algorithm Expansion IR JSON from a file or stdin."""
    if path is None or path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("IR JSON must be a JSON object")
    return payload


def tuple_of_strings(value: object) -> tuple[str, ...]:
    """Return a tuple of string values from JSON-ish data."""
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value)


def proof_status_for_grain(grain: str) -> str:
    """Map IR obligation grain to proof graph status."""
    if grain == "assumption":
        return "assumption"
    if grain == "excluded":
        return "excluded"
    return "unverified"


def node_profiles(node: dict[str, object], obligation: dict[str, object]) -> tuple[str, ...]:
    """Infer theorem target profiles for one lemma node."""
    profiles: set[str] = {"all"}
    math_role = str(node.get("math_role", ""))
    source_path = str(node.get("source_path", ""))
    source_symbol = str(node.get("source_symbol", ""))
    precision_model = str(node.get("precision_model", "none"))
    grain = str(obligation.get("grain", ""))
    equation_tags = set(tuple_of_strings(node.get("equation_tags")))

    if math_role in {"certificate", "diagnostic"} or source_symbol.endswith("Info"):
        profiles.add("certificate_soundness")
    if math_role in {"mathematical_state_transition", "linear_or_nonlinear_solve"}:
        profiles.add("local_convergence")
    if precision_model != "none" or grain == "assumption" or "fp32" in source_symbol.lower():
        profiles.add("fp32_floor")
    solver_tokens = ("solvers/", "kkt", "minres", "lobpcg", "preconditioner", "rank_r")
    if any(token in source_path or token in source_symbol.lower() for token in solver_tokens):
        profiles.add("solver_chain")
    if "reduced_kkt" in equation_tags:
        profiles.add("reduced_kkt")
        profiles.add("local_convergence")
        profiles.add("solver_chain")
    if "step_update" in equation_tags:
        profiles.add("step_update")
        profiles.add("local_convergence")
    if "floor_preserving_step" in equation_tags:
        profiles.add("floor_preserving_step")
        profiles.add("fp32_floor")
        profiles.add("local_convergence")
    if "minres_defaults" in equation_tags:
        profiles.add("minres_defaults")
        profiles.add("solver_chain")
    if "pdipm_initialization_path" in equation_tags:
        profiles.add("pdipm_initialization_path")
        profiles.add("local_convergence")
    return tuple(profile for profile in KNOWN_TARGET_PROFILES if profile in profiles)


def lemma_id_for_node_id(node_id: str) -> str:
    """Return the graph lemma id for one IR node id."""
    return f"lemma__{slug(node_id)}"


def target_id_for(profile: str, theorem: str) -> str:
    """Return graph node id for one theorem/profile target."""
    return f"target__{profile}__{slug(theorem)}"


def make_target_node(profile: str, theorem: str) -> LemmaNode:
    """Create one theorem/profile target node."""
    return LemmaNode(
        lemma_id=target_id_for(profile, theorem),
        label=f"{profile}: {theorem}",
        statement=f"Target theorem `{theorem}` under profile `{profile}`.",
        lemma_kind="target_theorem",
        proof_status="unverified",
        source_obligation_id=None,
        source_nodes=(),
        source_edges=(),
        source_symbols=(),
        source_paths=(),
        source_code_facts=(),
        math_role="target_theorem",
        residual_unit="none",
        precision_model="none",
        target_profiles=(profile,),
        remaining_gap="prove target theorem from connected lemma graph",
    )


def build_obligation_nodes(ir_payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Build raw lemma-node dictionaries from IR obligations."""
    ir_nodes = {
        str(node.get("node_id")): node
        for node in ir_payload.get("nodes", [])
        if isinstance(node, dict)
    }
    code_facts_by_node: dict[str, list[str]] = {}
    for fact in ir_payload.get("code_facts", []):
        if not isinstance(fact, dict):
            continue
        source_node_id = str(fact.get("source_node_id") or "")
        if source_node_id:
            code_facts_by_node.setdefault(source_node_id, []).append(str(fact.get("fact_id", "")))
    raw_nodes: list[dict[str, object]] = []
    for obligation in ir_payload.get("obligations", []):
        if not isinstance(obligation, dict):
            continue
        consumed_nodes = tuple_of_strings(obligation.get("consumes_nodes"))
        if not consumed_nodes:
            continue
        primary_node_id = consumed_nodes[0]
        ir_node = ir_nodes.get(primary_node_id, {})
        lemma_id = lemma_id_for_node_id(primary_node_id)
        profiles = node_profiles(ir_node, obligation)
        raw_nodes.append(
            {
                "lemma": LemmaNode(
                    lemma_id=lemma_id,
                    label=str(ir_node.get("source_symbol", primary_node_id)),
                    statement=str(obligation.get("statement", "")),
                    lemma_kind=str(obligation.get("grain", "local_obligation")),
                    proof_status=proof_status_for_grain(str(obligation.get("grain", ""))),
                    source_obligation_id=str(obligation.get("obligation_id", "")) or None,
                    source_nodes=consumed_nodes,
                    source_edges=tuple_of_strings(obligation.get("consumes_edges")),
                    source_symbols=(str(ir_node.get("source_symbol", primary_node_id)),),
                    source_paths=(str(ir_node.get("source_path", "")),),
                    source_code_facts=tuple(sorted(code_facts_by_node.get(primary_node_id, ()))),
                    math_role=str(ir_node.get("math_role", "unknown")),
                    residual_unit=str(ir_node.get("residual_unit", "none")),
                    precision_model=str(ir_node.get("precision_model", "none")),
                    target_profiles=profiles,
                    remaining_gap=str(obligation.get("remaining_gap", "")),
                ),
                "primary_node_id": primary_node_id,
            }
        )
    return tuple(raw_nodes)


def build_backend_assumption_nodes(ir_payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Build raw lemma-node dictionaries from IR backend assumption overlays."""
    raw_nodes: list[dict[str, object]] = []
    for assumption in ir_payload.get("backend_assumptions", []):
        if not isinstance(assumption, dict):
            continue
        assumption_id = str(assumption.get("assumption_id", "backend_profile"))
        applies_to_nodes = tuple_of_strings(assumption.get("applies_to_nodes"))
        raw_nodes.append(
            {
                "lemma": LemmaNode(
                    lemma_id=f"lemma__{slug(assumption_id)}",
                    label=str(assumption.get("profile_variable", assumption_id)),
                    statement=str(assumption.get("statement", "")),
                    lemma_kind="assumption",
                    proof_status="assumption",
                    source_obligation_id=assumption_id,
                    source_nodes=applies_to_nodes,
                    source_edges=(),
                    source_symbols=(str(assumption.get("profile_variable", "")),),
                    source_paths=(str(assumption.get("owning_surface", "")),),
                    source_code_facts=(),
                    math_role="backend_arithmetic_assumption",
                    residual_unit="backend_error_floor_unit",
                    precision_model="backend_profile",
                    target_profiles=("all", "fp32_floor"),
                    remaining_gap=str(assumption.get("checker_route", "")),
                ),
                "primary_node_id": f"backend-assumption:{assumption_id}",
                "applies_to_nodes": applies_to_nodes,
            }
        )
    return tuple(raw_nodes)


def build_backend_profile_nodes(ir_payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Build lemma nodes for concrete backend profile records from lean/."""
    raw_nodes: list[dict[str, object]] = []
    for assumption in ir_payload.get("backend_assumptions", []):
        if not isinstance(assumption, dict):
            continue
        assumption_id = str(assumption.get("assumption_id", "backend_profile"))
        profile_library_path = str(assumption.get("profile_library_path", ""))
        profile_details = assumption.get("profile_details")
        if not isinstance(profile_details, dict):
            profile_details = {}
        profile_ids = tuple_of_strings(assumption.get("profile_ids"))
        for profile_id in profile_ids:
            raw_profile = profile_details.get(profile_id, {})
            profile = raw_profile if isinstance(raw_profile, dict) else {}
            witnesses = tuple_of_strings(profile.get("required_witnesses"))
            description = str(profile.get("description", "backend profile"))
            statement = (
                f"Backend profile `{profile_id}` from `{profile_library_path}`: "
                f"{description}"
            )
            if witnesses:
                statement = f"{statement} Required witnesses: {', '.join(witnesses)}."
            raw_nodes.append(
                {
                    "lemma": LemmaNode(
                        lemma_id=f"lemma__backend_profile__{slug(profile_id)}",
                        label=f"backend profile: {profile_id}",
                        statement=statement,
                        lemma_kind="backend_profile",
                        proof_status="external_evidence_required",
                        source_obligation_id=f"{assumption_id}:{profile_id}",
                        source_nodes=(),
                        source_edges=(),
                        source_symbols=(profile_id,),
                        source_paths=(profile_library_path,),
                        source_code_facts=(),
                        math_role="backend_arithmetic_profile",
                        residual_unit="backend_error_floor_unit",
                        precision_model="backend_profile",
                        target_profiles=("all", "fp32_floor"),
                        remaining_gap=(
                            "bind lowered IR, compiler flags, and runtime backend "
                            "semantics before using this arithmetic profile"
                        ),
                    ),
                    "assumption_id": assumption_id,
                    "profile_id": profile_id,
                }
            )
    return tuple(raw_nodes)


def build_code_fact_nodes(ir_payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Build lemma graph nodes for code-derived expression/default facts."""
    raw_nodes: list[dict[str, object]] = []
    for fact in ir_payload.get("code_facts", []):
        if not isinstance(fact, dict):
            continue
        fact_id = str(fact.get("fact_id", "code_fact"))
        profiles = tuple_of_strings(fact.get("target_profiles")) or ("all",)
        raw_nodes.append(
            {
                "lemma": LemmaNode(
                    lemma_id=f"lemma__{slug(fact_id)}",
                    label=str(fact.get("target", fact_id)),
                    statement=str(fact.get("statement", "")),
                    lemma_kind="code_fact",
                    proof_status="code_derived",
                    source_obligation_id=None,
                    source_nodes=(
                        (str(fact.get("source_node_id")),)
                        if fact.get("source_node_id")
                        else ()
                    ),
                    source_edges=(),
                    source_symbols=(str(fact.get("source_symbol", "")),),
                    source_paths=(str(fact.get("source_path", "")),),
                    source_code_facts=(fact_id,),
                    math_role="implementation_equation_fact",
                    residual_unit="none",
                    precision_model="none",
                    target_profiles=profiles,
                    remaining_gap="code-derived fact; mathematical use still requires theorem selection",
                ),
                "fact_id": fact_id,
                "source_node_id": str(fact.get("source_node_id") or ""),
            }
        )
    return tuple(raw_nodes)


def dedupe_edges(edges: list[LemmaEdge]) -> tuple[LemmaEdge, ...]:
    """Dedupe graph edges while preserving deterministic ids."""
    seen: set[tuple[str, str, str, str | None]] = set()
    deduped: list[LemmaEdge] = []
    for edge in edges:
        key = (
            edge.source_lemma_id,
            edge.target_lemma_id,
            edge.edge_kind,
            edge.source_ir_edge_id,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            LemmaEdge(
                edge_id=f"lemma-edge-{len(deduped) + 1}",
                source_lemma_id=edge.source_lemma_id,
                target_lemma_id=edge.target_lemma_id,
                edge_kind=edge.edge_kind,
                reason=edge.reason,
                source_ir_edge_id=edge.source_ir_edge_id,
                status=edge.status,
            )
        )
    return tuple(deduped)


def build_dependency_edges(
    ir_payload: dict[str, object],
    lemma_by_ir_node: dict[str, str],
) -> tuple[LemmaEdge, ...]:
    """Build lemma dependency edges from IR implementation edges."""
    edges: list[LemmaEdge] = []
    for ir_edge in ir_payload.get("edges", []):
        if not isinstance(ir_edge, dict):
            continue
        source_lemma_id = lemma_by_ir_node.get(str(ir_edge.get("source_node_id", "")))
        target_lemma_id = lemma_by_ir_node.get(str(ir_edge.get("target_node_id", "")))
        if source_lemma_id is None or target_lemma_id is None:
            continue
        if source_lemma_id == target_lemma_id:
            continue
        status = str(ir_edge.get("status", ""))
        edge_kind = (
            "static_dispatch_selects_callee"
            if status in STATIC_EDGE_STATUSES
            else "implementation_lemma_dependency"
        )
        edges.append(
            LemmaEdge(
                edge_id="pending",
                source_lemma_id=source_lemma_id,
                target_lemma_id=target_lemma_id,
                edge_kind=edge_kind,
                reason=(
                    f"IR edge {ir_edge.get('edge_id')} "
                    f"{ir_edge.get('source_symbol')} -> {ir_edge.get('target_symbol')}"
                ),
                source_ir_edge_id=str(ir_edge.get("edge_id", "")) or None,
                status="valid",
            )
        )
    return dedupe_edges(edges)


def build_backend_assumption_edges(
    backend_nodes: tuple[dict[str, object], ...],
    lemma_by_ir_node: dict[str, str],
) -> tuple[LemmaEdge, ...]:
    """Connect precision lemmas to the backend assumptions they consume."""
    edges: list[LemmaEdge] = []
    for raw in backend_nodes:
        assumption_lemma = raw["lemma"].lemma_id
        for node_id in raw.get("applies_to_nodes", ()):
            source_lemma = lemma_by_ir_node.get(str(node_id))
            if source_lemma is None:
                continue
            edges.append(
                LemmaEdge(
                    edge_id="pending",
                    source_lemma_id=source_lemma,
                    target_lemma_id=assumption_lemma,
                    edge_kind="backend_profile_dependency",
                    reason=(
                        "precision/floor lemma consumes proof-only backend "
                        f"assumption `{assumption_lemma}`"
                    ),
                    source_ir_edge_id=None,
                    status="valid",
                )
            )
    return dedupe_edges(edges)


def build_backend_profile_edges(
    backend_nodes: tuple[dict[str, object], ...],
    profile_nodes: tuple[dict[str, object], ...],
) -> tuple[LemmaEdge, ...]:
    """Connect backend assumptions to concrete profile records."""
    assumption_by_id = {
        str(raw["lemma"].source_obligation_id): raw["lemma"].lemma_id for raw in backend_nodes
    }
    edges: list[LemmaEdge] = []
    for raw in profile_nodes:
        source_obligation_id = str(raw["lemma"].source_obligation_id or "")
        assumption_id = source_obligation_id.split(":", 1)[0]
        assumption_lemma = assumption_by_id.get(assumption_id)
        if assumption_lemma is None:
            continue
        edges.append(
            LemmaEdge(
                edge_id="pending",
                source_lemma_id=assumption_lemma,
                target_lemma_id=raw["lemma"].lemma_id,
                edge_kind="backend_profile_record",
                reason="backend assumption is instantiated by a lean/lib backend profile record",
                source_ir_edge_id=None,
                status="valid",
            )
        )
    return dedupe_edges(edges)


def build_code_fact_edges(
    code_fact_nodes: tuple[dict[str, object], ...],
    lemma_by_ir_node: dict[str, str],
) -> tuple[LemmaEdge, ...]:
    """Connect implementation lemmas to code-derived expression facts."""
    edges: list[LemmaEdge] = []
    for raw in code_fact_nodes:
        source_node_id = str(raw.get("source_node_id") or "")
        source_lemma = lemma_by_ir_node.get(source_node_id)
        if source_lemma is None:
            continue
        edges.append(
            LemmaEdge(
                edge_id="pending",
                source_lemma_id=source_lemma,
                target_lemma_id=raw["lemma"].lemma_id,
                edge_kind="lemma_consumes_code_fact",
                reason="implementation obligation consumes an AST-derived equation/default fact",
                source_ir_edge_id=None,
                status="valid",
            )
        )
    return dedupe_edges(edges)


def lemma_ids_for_profile(lemma_nodes: tuple[LemmaNode, ...], profile: str) -> tuple[str, ...]:
    """Return lemma ids selected by a target profile."""
    if profile == "all":
        return tuple(
            node.lemma_id
            for node in lemma_nodes
            if node.lemma_kind != "target_theorem" and node.proof_status != "excluded"
        )
    return tuple(
        node.lemma_id
        for node in lemma_nodes
        if profile in node.target_profiles
        and node.lemma_kind != "target_theorem"
        and node.proof_status != "excluded"
    )


def build_target_edges(
    theorem: str,
    profiles: tuple[str, ...],
    lemma_nodes: tuple[LemmaNode, ...],
) -> tuple[LemmaEdge, ...]:
    """Build explicit theorem/profile-to-lemma requirement edges."""
    edges: list[LemmaEdge] = []
    for profile in profiles:
        target_id = target_id_for(profile, theorem)
        for lemma_id in lemma_ids_for_profile(lemma_nodes, profile):
            edges.append(
                LemmaEdge(
                    edge_id="pending",
                    source_lemma_id=target_id,
                    target_lemma_id=lemma_id,
                    edge_kind="target_requires",
                    reason=f"profile `{profile}` selects lemma `{lemma_id}`",
                    source_ir_edge_id=None,
                    status="valid",
                )
            )
    return dedupe_edges(edges)


def reachable_from(start_id: str, edges: tuple[LemmaEdge, ...]) -> tuple[str, ...]:
    """Return graph nodes reachable from one start node."""
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge.source_lemma_id, []).append(edge.target_lemma_id)
    seen: set[str] = set()
    stack = list(adjacency.get(start_id, ()))
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        stack.extend(adjacency.get(node_id, ()))
    return tuple(sorted(seen))


def cycle_edge_ids(nodes: tuple[LemmaNode, ...], edges: tuple[LemmaEdge, ...]) -> tuple[str, ...]:
    """Return edge ids that participate in a directed cycle."""
    adjacency: dict[str, list[tuple[str, str]]] = {}
    for edge in edges:
        adjacency.setdefault(edge.source_lemma_id, []).append((edge.target_lemma_id, edge.edge_id))
    visiting: set[str] = set()
    visited: set[str] = set()
    cycle_edges: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            return
        if node_id in visited:
            return
        visiting.add(node_id)
        for child_id, edge_id in adjacency.get(node_id, ()):
            if child_id in visiting:
                cycle_edges.add(edge_id)
                continue
            visit(child_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node in nodes:
        visit(node.lemma_id)
    return tuple(sorted(cycle_edges))


def build_target_chains(
    theorem: str,
    profiles: tuple[str, ...],
    lemma_nodes: tuple[LemmaNode, ...],
    edges: tuple[LemmaEdge, ...],
) -> tuple[TargetChain, ...]:
    """Build reachability chains for all selected target profiles."""
    chains: list[TargetChain] = []
    for profile in profiles:
        target_id = target_id_for(profile, theorem)
        expected = lemma_ids_for_profile(lemma_nodes, profile)
        reachable = reachable_from(target_id, edges)
        missing = tuple(sorted(set(expected) - set(reachable)))
        chains.append(
            TargetChain(
                target_id=target_id,
                profile=profile,
                theorem=theorem,
                lemma_ids=tuple(sorted(expected)),
                reachable_lemma_ids=reachable,
                missing_lemma_ids=missing,
                connected=not missing,
            )
        )
    return tuple(chains)


def validate_graph(
    lemma_nodes: tuple[LemmaNode, ...],
    lemma_edges: tuple[LemmaEdge, ...],
    target_chains: tuple[TargetChain, ...],
) -> LemmaGraphValidation:
    """Validate graph references, cycles, and target-chain connectivity."""
    node_ids = {node.lemma_id for node in lemma_nodes}
    missing_ids = tuple(
        sorted(
            {
                target
                for edge in lemma_edges
                for target in (edge.source_lemma_id, edge.target_lemma_id)
                if target not in node_ids
            }
        )
    )
    cycle_ids = cycle_edge_ids(lemma_nodes, lemma_edges)
    disconnected = tuple(chain.target_id for chain in target_chains if not chain.connected)
    return LemmaGraphValidation(
        node_count=len(lemma_nodes),
        edge_count=len(lemma_edges),
        target_count=len(target_chains),
        missing_edge_target_ids=missing_ids,
        cycle_edge_ids=cycle_ids,
        disconnected_target_ids=disconnected,
        connected=not disconnected,
        acyclic=not cycle_ids,
        valid=not missing_ids and not cycle_ids and not disconnected,
    )


def build_lemma_graph(ir_payload: dict[str, object], profiles: tuple[str, ...]) -> LemmaGraphReport:
    """Build the lemma dependency graph."""
    theorem = str(ir_payload.get("target_theorem", "target theorem"))
    root = f"{ir_payload.get('root_path', '')}::{ir_payload.get('root_symbol', '')}"
    source_ir_fingerprint = str(
        ir_payload.get("algorithm_fingerprint") or algorithm_fingerprint(ir_payload)
    )
    target_profiles = profiles or KNOWN_TARGET_PROFILES
    raw_obligation_nodes = build_obligation_nodes(ir_payload)
    raw_backend_nodes = build_backend_assumption_nodes(ir_payload)
    raw_backend_profile_nodes = build_backend_profile_nodes(ir_payload)
    raw_code_fact_nodes = build_code_fact_nodes(ir_payload)
    obligation_nodes = tuple(raw["lemma"] for raw in raw_obligation_nodes)
    lemma_by_ir_node = {
        str(raw["primary_node_id"]): raw["lemma"].lemma_id for raw in raw_obligation_nodes
    }
    backend_nodes = tuple(raw["lemma"] for raw in raw_backend_nodes)
    backend_profile_nodes = tuple(raw["lemma"] for raw in raw_backend_profile_nodes)
    code_fact_nodes = tuple(raw["lemma"] for raw in raw_code_fact_nodes)
    target_nodes = tuple(make_target_node(profile, theorem) for profile in target_profiles)
    dependency_edges = build_dependency_edges(ir_payload, lemma_by_ir_node)
    backend_edges = build_backend_assumption_edges(raw_backend_nodes, lemma_by_ir_node)
    backend_profile_edges = build_backend_profile_edges(
        raw_backend_nodes,
        raw_backend_profile_nodes,
    )
    code_fact_edges = build_code_fact_edges(raw_code_fact_nodes, lemma_by_ir_node)
    proof_nodes = (*obligation_nodes, *backend_nodes, *backend_profile_nodes, *code_fact_nodes)
    target_edges = build_target_edges(theorem, target_profiles, proof_nodes)
    lemma_edges = dedupe_edges(
        [
            *target_edges,
            *dependency_edges,
            *backend_edges,
            *backend_profile_edges,
            *code_fact_edges,
        ]
    )
    lemma_nodes = tuple(sorted((*target_nodes, *proof_nodes), key=lambda item: item.lemma_id))
    target_chains = build_target_chains(theorem, target_profiles, proof_nodes, lemma_edges)
    validation = validate_graph(lemma_nodes, lemma_edges, target_chains)
    return LemmaGraphReport(
        status="lemma_graph_built" if validation.valid else "lemma_graph_invalid",
        source_ir_status=str(ir_payload.get("status", "unknown")),
        source_ir_fingerprint=source_ir_fingerprint,
        root=root,
        theorem=theorem,
        target_profiles=target_profiles,
        lemma_nodes=lemma_nodes,
        lemma_edges=lemma_edges,
        target_chains=target_chains,
        validation=validation,
    )


def render_text(report: LemmaGraphReport) -> str:
    """Render stable text output."""
    lines = [
        f"LEMMA_GRAPH={report.status}",
        f"LEMMA_GRAPH_ROOT={report.root}",
        f"LEMMA_GRAPH_THEOREM={report.theorem}",
        f"LEMMA_GRAPH_SOURCE_IR_FINGERPRINT={report.source_ir_fingerprint}",
        f"LEMMA_GRAPH_NODES={len(report.lemma_nodes)}",
        f"LEMMA_GRAPH_EDGES={len(report.lemma_edges)}",
        f"LEMMA_GRAPH_TARGETS={len(report.target_chains)}",
        f"LEMMA_GRAPH_VALID={str(report.validation.valid).lower()}",
    ]
    for node in report.lemma_nodes:
        lines.append(
            "LEMMA_GRAPH_NODE="
            f"{node.lemma_id}:{node.lemma_kind}:{node.proof_status}:"
            f"{','.join(node.target_profiles)}"
        )
    for edge in report.lemma_edges:
        lines.append(
            "LEMMA_GRAPH_EDGE="
            f"{edge.edge_id}:{edge.source_lemma_id}->{edge.target_lemma_id}:"
            f"{edge.edge_kind}:{edge.status}"
        )
    for chain in report.target_chains:
        lines.append(
            "LEMMA_GRAPH_TARGET_CHAIN="
            f"{chain.target_id}:{chain.profile}:connected={str(chain.connected).lower()}:"
            f"lemmas={len(chain.lemma_ids)}"
        )
    return "\n".join(lines) + "\n"


def markdown_cell(value: object) -> str:
    """Escape a Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: LemmaGraphReport) -> str:
    """Render Markdown output."""
    lines = [
        "# Lemma Dependency Graph",
        "",
        f"- root: `{report.root}`",
        f"- theorem: `{report.theorem}`",
        f"- source IR fingerprint: `{report.source_ir_fingerprint}`",
        f"- status: `{report.status}`",
        f"- nodes: `{len(report.lemma_nodes)}`",
        f"- edges: `{len(report.lemma_edges)}`",
        f"- valid: `{report.validation.valid}`",
        "",
        "## Target Chains",
        "",
        "| Target | Profile | Lemmas | Reachable | Connected |",
        "| --- | --- | --- | --- | --- |",
    ]
    for chain in report.target_chains:
        lines.append(
            "| "
            + " | ".join(
                markdown_cell(value)
                for value in (
                    chain.target_id,
                    chain.profile,
                    len(chain.lemma_ids),
                    len(chain.reachable_lemma_ids),
                    chain.connected,
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Lemma Nodes",
            "",
            "| Lemma | Kind | Status | Profiles | Source Symbols | Code Facts | Remaining Gap |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for node in report.lemma_nodes:
        lines.append(
            "| "
            + " | ".join(
                markdown_cell(value)
                for value in (
                    node.lemma_id,
                    node.lemma_kind,
                    node.proof_status,
                    ", ".join(node.target_profiles),
                    ", ".join(node.source_symbols) or "none",
                    ", ".join(node.source_code_facts) or "none",
                    node.remaining_gap,
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Lemma Edges",
            "",
            "| Edge | Source | Target | Kind | Reason |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for edge in report.lemma_edges:
        lines.append(
            "| "
            + " | ".join(
                markdown_cell(value)
                for value in (
                    edge.edge_id,
                    edge.source_lemma_id,
                    edge.target_lemma_id,
                    edge.edge_kind,
                    edge.reason,
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def dot_id(value: str) -> str:
    """Return a DOT-safe quoted id."""
    return json.dumps(value)


def render_dot(report: LemmaGraphReport) -> str:
    """Render a Graphviz DOT graph."""
    lines = ["digraph lemma_dependency_graph {"]
    for node in report.lemma_nodes:
        lines.append(
            f"  {dot_id(node.lemma_id)} "
            f"[label={json.dumps(node.label)}, shape="
            f"{'box' if node.lemma_kind == 'target_theorem' else 'ellipse'}];"
        )
    for edge in report.lemma_edges:
        lines.append(
            f"  {dot_id(edge.source_lemma_id)} -> {dot_id(edge.target_lemma_id)} "
            f"[label={json.dumps(edge.edge_kind)}];"
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_json(report: LemmaGraphReport) -> str:
    """Render JSON output."""
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_report(report: LemmaGraphReport, output_format: str) -> str:
    """Render the selected output format."""
    if output_format == "json":
        return render_json(report)
    if output_format == "markdown":
        return render_markdown(report)
    if output_format == "dot":
        return render_dot(report)
    return render_text(report)


def main() -> int:
    """CLI entrypoint."""
    args = build_parser().parse_args()
    ir_payload = read_ir_payload(args.ir_json)
    profiles = tuple(args.target_profile or ())
    report = build_lemma_graph(ir_payload, profiles)
    rendered = render_report(report, str(args.format))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report.validation.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
