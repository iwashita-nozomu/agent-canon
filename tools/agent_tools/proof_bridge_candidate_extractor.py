#!/usr/bin/env python3
"""Extract candidate mathematical bridge propositions from Algorithm IR facts.

@dependency-start
responsibility Lists proof bridge candidates mechanically from Algorithm Expansion IR code facts.
upstream implementation algorithm_expansion_ir.py emits Algorithm Expansion IR JSON.
upstream design ../../agents/skills/formal-proof-workflow.md requires bridge-candidate exploration.
downstream design ../../documents/tools/proof_bridge_candidate_extractor.md documents CLI usage.
@dependency-end
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast


@dataclass(frozen=True)
class BridgeCandidate:
    """One possible mathematical proposition suggested by implementation facts."""

    candidate_id: str
    title: str
    proposition_shape: str
    source_symbols: tuple[str, ...]
    source_fact_ids: tuple[str, ...]
    evidence_expressions: tuple[str, ...]
    theorem_role: str
    initial_status: str
    selection_note: str


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ir-json", action="append", required=True)
    parser.add_argument("--target-theorem", default="")
    parser.add_argument("--format", choices=("json", "markdown", "text"), default="text")
    parser.add_argument("--out")
    return parser


def load_json(path: str) -> dict[str, object]:
    """Load a JSON object."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return cast(dict[str, object], payload)


def dict_list(value: object) -> list[dict[str, object]]:
    """Return JSON object rows from a JSON list."""
    if not isinstance(value, list):
        return []
    return [cast(dict[str, object], item) for item in cast(list[object], value) if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    """Return string values from a JSON list."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast(list[object], value)]


def slug(value: str) -> str:
    """Return a stable identifier fragment."""
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_").lower()
    return normalized or "candidate"


def code_facts(payloads: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return all code facts from loaded IR payloads."""
    facts: list[dict[str, object]] = []
    for payload in payloads:
        facts.extend(dict_list(payload.get("code_facts")))
    return facts


def fact_text(fact: dict[str, object]) -> str:
    """Return searchable text for a fact."""
    values = [
        fact.get("source_symbol", ""),
        fact.get("target", ""),
        fact.get("expression", ""),
        " ".join(tag for tag in string_list(fact.get("equation_tags")) if tag),
    ]
    return " ".join(str(value) for value in values).lower()


def fact_id(fact: dict[str, object]) -> str:
    """Return a fact identifier."""
    return str(fact.get("fact_id") or fact.get("statement") or "fact")


def fact_expr(fact: dict[str, object]) -> str:
    """Return a compact fact expression."""
    expression = str(fact.get("expression") or "")
    target = str(fact.get("target") or "")
    if target and expression:
        return f"{target} := {expression}"
    return expression or str(fact.get("statement") or "")


def select_facts(
    facts: list[dict[str, object]],
    *needles: str,
) -> tuple[dict[str, object], ...]:
    """Return facts whose searchable text contains all needles."""
    lowered = tuple(needle.lower() for needle in needles)
    return tuple(fact for fact in facts if all(needle in fact_text(fact) for needle in lowered))


def candidate_from_facts(
    *,
    candidate_id: str,
    title: str,
    proposition_shape: str,
    facts: tuple[dict[str, object], ...],
    theorem_role: str,
    selection_note: str,
) -> BridgeCandidate | None:
    """Build a candidate when evidence facts are present."""
    if not facts:
        return None
    return BridgeCandidate(
        candidate_id=candidate_id,
        title=title,
        proposition_shape=proposition_shape,
        source_symbols=tuple(
            sorted({str(fact.get("source_symbol") or "") for fact in facts if fact.get("source_symbol")})
        ),
        source_fact_ids=tuple(fact_id(fact) for fact in facts),
        evidence_expressions=tuple(fact_expr(fact) for fact in facts),
        theorem_role=theorem_role,
        initial_status="candidate_from_ir",
        selection_note=selection_note,
    )


def extract_candidates(facts: list[dict[str, object]]) -> tuple[BridgeCandidate, ...]:
    """Extract bridge candidates from code facts."""
    specs: list[BridgeCandidate | None] = [
        candidate_from_facts(
            candidate_id="bridge__reduced_kkt_rhs",
            title="Reduced KKT right-hand side is defined by implementation equations",
            proposition_shape=(
                "The reduced system RHS used by the nested solver is the pair "
                "constructed from the current residuals and eliminated inequality block."
            ),
            facts=(
                *select_facts(facts, "_pdipm_reduced_kkt_rhs_top"),
                *select_facts(facts, "_pdipm_solve_direction", "rhs_bot"),
            ),
            theorem_role="equation_bridge",
            selection_note="Use before proving any KKT-direction statement.",
        ),
        candidate_from_facts(
            candidate_id="bridge__reduced_kkt_answer_projection",
            title="Nested solver answer supplies dx and equality multiplier increment",
            proposition_shape=(
                "The primal and equality-dual components of the outer direction "
                "are projected from the reduced KKT answer."
            ),
            facts=(
                *select_facts(facts, "_pdipm_solve_direction", "dx"),
                *select_facts(facts, "_pdipm_solve_direction", "dlam"),
            ),
            theorem_role="direction_projection",
            selection_note="Use to remove unconstrained answer components.",
        ),
        candidate_from_facts(
            candidate_id="bridge__back_substitution",
            title="Inequality slack and multiplier increments are restored by back-substitution",
            proposition_shape=(
                "Given the reduced answer, ds and dlam_ineq are the implementation "
                "back-substitution formulas."
            ),
            facts=(
                *select_facts(facts, "_pdipm_solve_direction", "ds"),
                *select_facts(facts, "_pdipm_solve_direction", "dlam"),
                *select_facts(facts, "restoreSlackIncrement"),
                *select_facts(facts, "restoreIneqMultiplier"),
            ),
            theorem_role="restoration_bridge",
            selection_note="Use to connect reduced-system results to full direction results.",
        ),
        candidate_from_facts(
            candidate_id="bridge__step_update_residual_recompute",
            title="Step update recomputes residuals at the generated next state",
            proposition_shape=(
                "The next residual bundle is computed from the primal-dual fields "
                "after applying the generated step."
            ),
            facts=(
                *select_facts(facts, "_pdipm_step_update"),
                *select_facts(facts, "_compute_residuals"),
            ),
            theorem_role="state_transition_bridge",
            selection_note="Use before scalar residual nonincrease.",
        ),
        candidate_from_facts(
            candidate_id="bridge__scalar_ipm_residual",
            title="Stopping metric is the scalar max aggregation of residual blocks",
            proposition_shape=(
                "The convergence residual is the scalar maximum of stationarity, "
                "equality, inequality, and complementarity relative residuals."
            ),
            facts=select_facts(facts, "_pdipm_convergence", "ipm_res"),
            theorem_role="metric_bridge",
            selection_note="Use to avoid componentwise-decrease overstrengthening.",
        ),
        candidate_from_facts(
            candidate_id="bridge__fraction_to_boundary",
            title="Step length is generated by fraction-to-boundary formulas",
            proposition_shape=(
                "The primal and dual step lengths are clipped fraction-to-boundary "
                "values computed from slack and multiplier margins."
            ),
            facts=select_facts(facts, "_pdipm_fraction_to_boundary_step_lengths"),
            theorem_role="step_length_bridge",
            selection_note="Use for positivity or step-size route candidates.",
        ),
        candidate_from_facts(
            candidate_id="bridge__inner_solver_residual_certificate",
            title="Nested iterative solver returns a residual certificate",
            proposition_shape=(
                "The nested solver output includes a true or final residual measure "
                "that can be translated into an outer direction-quality bound."
            ),
            facts=(
                *select_facts(facts, "final_true_rel_r"),
                *select_facts(facts, "final_true_norm_r"),
                *select_facts(facts, "relative_residual"),
                *select_facts(facts, "converged"),
            ),
            theorem_role="inexact_solve_bridge",
            selection_note="Use for inexact direction and quotient/projection route candidates.",
        ),
    ]
    seen: set[str] = set()
    candidates: list[BridgeCandidate] = []
    for candidate in specs:
        if candidate is None or candidate.candidate_id in seen:
            continue
        seen.add(candidate.candidate_id)
        candidates.append(candidate)
    return tuple(candidates)


def render_markdown(candidates: tuple[BridgeCandidate, ...], target_theorem: str) -> str:
    """Render candidates as Markdown."""
    lines = [
        "# Proof Bridge Candidates",
        "",
        f"- target theorem: `{target_theorem or 'unspecified'}`",
        f"- candidates: `{len(candidates)}`",
        "",
        "| Candidate | Role | Status | Proposition Shape | Evidence Facts | Selection Note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in candidates:
        lines.append(
            "| "
            + " | ".join(
                value.replace("|", "\\|").replace("\n", " ")
                for value in (
                    item.candidate_id,
                    item.theorem_role,
                    item.initial_status,
                    item.proposition_shape,
                    str(len(item.source_fact_ids)),
                    item.selection_note,
                )
            )
            + " |"
        )
    lines.append("")
    lines.append("## Evidence")
    for item in candidates:
        lines.extend(["", f"### {item.candidate_id}", ""])
        for expression in item.evidence_expressions[:20]:
            lines.append(f"- `{expression}`")
        if len(item.evidence_expressions) > 20:
            lines.append(f"- ... {len(item.evidence_expressions) - 20} more")
    return "\n".join(lines) + "\n"


def render_text(candidates: tuple[BridgeCandidate, ...]) -> str:
    """Render stable text output."""
    lines = [f"PROOF_BRIDGE_CANDIDATES={len(candidates)}"]
    for item in candidates:
        lines.append(
            "PROOF_BRIDGE_CANDIDATE="
            f"{item.candidate_id}:{item.theorem_role}:{item.initial_status}:"
            f"facts={len(item.source_fact_ids)}"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run CLI."""
    args = build_parser().parse_args(argv)
    payloads = [load_json(path) for path in args.ir_json]
    candidates = extract_candidates(code_facts(payloads))
    if args.format == "json":
        rendered = json.dumps(
            {
                "status": "proof_bridge_candidates_built",
                "target_theorem": args.target_theorem,
                "candidate_count": len(candidates),
                "candidates": [asdict(candidate) for candidate in candidates],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    elif args.format == "markdown":
        rendered = render_markdown(candidates, args.target_theorem)
    else:
        rendered = render_text(candidates)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
