#!/usr/bin/env python3
# @dependency-start
# responsibility Emits a reproducible KKT solver-chain equation section from Algorithm IR facts.
# upstream implementation algorithm_expansion_ir.py emits Algorithm Expansion IR JSON.
# upstream implementation algorithm_lemma_graph.py consumes the same IR facts for proof graphs.
# downstream design ../../documents/tools/kkt_equation_section.md documents generated equation adoption guardrails.
# downstream implementation ../../tests/agent_tools/test_kkt_equation_section.py tests the generator.
# @dependency-end
"""Emit a KKT solver-chain equation section from Algorithm Expansion IR facts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodeFact:
    """One IR code fact used as generator evidence."""

    fact_id: str
    source_path: str
    source_symbol: str
    source_span: str
    target: str
    expression: str


@dataclass(frozen=True)
class EvidenceRequirement:
    """One source fact required before emitting the equation template."""

    evidence_id: str
    description: str
    source_symbol: str
    target: str
    expression_pattern: str


@dataclass(frozen=True)
class EvidenceMatch:
    """One matched requirement and the backing code fact."""

    evidence_id: str
    description: str
    fact: CodeFact


@dataclass(frozen=True)
class SectionReport:
    """Machine-readable equation-section generation result."""

    status: str
    inputs: tuple[str, ...]
    evidence: tuple[EvidenceMatch, ...]
    missing_evidence: tuple[str, ...]
    markdown: str


REQUIREMENTS: tuple[EvidenceRequirement, ...] = (
    EvidenceRequirement(
        "P1",
        "PDIPM complementarity RHS after inequality elimination.",
        "_pdipm_reduced_kkt_complementarity_rhs",
        "return",
        r"r_c_used\s*-\s*safe_lam_ineq\s*\*\s*residuals\.r_ineq",
    ),
    EvidenceRequirement(
        "P2",
        "PDIPM reduced primal RHS.",
        "_pdipm_reduced_kkt_rhs_top",
        "return",
        r"-residuals\.r_x.*linearization\.j_ineq_t.*complementarity_rhs",
    ),
    EvidenceRequirement(
        "P3",
        "PDIPM reduced equality RHS.",
        "_pdipm_solve_direction",
        "rhs_bot",
        r"-residuals\.r_eq",
    ),
    EvidenceRequirement(
        "P4",
        "PDIPM sends the reduced problem to kkt.Problem.",
        "_pdipm_solve_direction",
        "kkt_answer",
        r"kkt\.Problem\(Hv=linearization\.h_eff.*rhs_x=rhs_top.*rhs_lam=rhs_bot",
    ),
    EvidenceRequirement(
        "P5",
        "PDIPM extracts the primal reduced-KKT increment.",
        "_pdipm_solve_direction",
        "dx",
        r"getattr\(kkt_answer,\s*['\"]x['\"]\)",
    ),
    EvidenceRequirement(
        "P6",
        "PDIPM extracts the equality multiplier increment.",
        "_pdipm_solve_direction",
        "dlam_eq",
        r"getattr\(kkt_answer,\s*['\"]lam['\"]\)",
    ),
    EvidenceRequirement(
        "P7",
        "PDIPM reconstructs eliminated slack increments.",
        "_pdipm_solve_direction",
        "ds",
        r"-\(residuals\.r_ineq\s*\+\s*linearization\.j_ineq\s*@\s*dx\)",
    ),
    EvidenceRequirement(
        "P8",
        "PDIPM reconstructs eliminated inequality multiplier increments.",
        "_pdipm_solve_direction",
        "dlam",
        r"diag_s_inv.*r_c_used.*diag_lam.*ds",
    ),
    EvidenceRequirement(
        "K1",
        "KKT regularizes the primal block.",
        "_kkt_preconditioned_system",
        "regularized_h",
        r"problem\.Hv\s*@\s*v\s*\+\s*primal_regularization\s*\*\s*v",
    ),
    EvidenceRequirement(
        "K2",
        "KKT builds the Schur preconditioner target base.",
        "_kkt_preconditioned_system",
        "schur_base",
        r"problem\.Bv\s*\*\s*h_inv_approx\s*\*\s*problem\.BTv",
    ),
    EvidenceRequirement(
        "K3",
        "KKT regularizes the Schur target.",
        "_kkt_preconditioned_system",
        "schur_mv",
        r"schur_base\s*@\s*v\s*\+\s*dual_regularization\s*\*\s*v",
    ),
    EvidenceRequirement(
        "K4",
        "KKT builds the block-diagonal preconditioner.",
        "_run_kkt_solve",
        "preconditioner",
        r"make_block_diagonal\(system\.h_inv_approx,\s*system\.s_inv_approx",
    ),
    EvidenceRequirement(
        "K5",
        "KKT exposes the inverse-square-root preconditioner.",
        "_kkt_preconditioner_sqrt_pair",
        "preconditioner_minv_sqrt",
        r"power_operator\(preconditioner,\s*preconditioner_power=0\.5\)",
    ),
    EvidenceRequirement(
        "K6",
        "KKT exposes the square-root preconditioner.",
        "_kkt_preconditioner_sqrt_pair",
        "preconditioner_msqrt",
        r"power_operator\(preconditioner,\s*preconditioner_power=-0\.5\)",
    ),
    EvidenceRequirement(
        "K7",
        "KKT calls MINRES on the regularized operator and RHS.",
        "_run_kkt_solve",
        "solver_answer",
        r"runtime\.request\.solver_algorithm\(minres\.Problem\(Mv=kkt_operator,\s*rhs=rhs\)",
    ),
    EvidenceRequirement(
        "R1",
        "KKT reports the regularized residual.",
        "_kkt_solve_info",
        "regularized_residual",
        r"kkt_operator\s*@\s*v\s*-\s*rhs",
    ),
    EvidenceRequirement(
        "R2",
        "KKT reports the unregularized primal residual.",
        "_kkt_solve_info",
        "unregularized_top",
        r"problem\.Hv\s*@\s*x\s*\+\s*problem\.BTv\s*@\s*lam\s*-\s*rhs_x",
    ),
    EvidenceRequirement(
        "R3",
        "KKT reports the unregularized equality residual.",
        "_kkt_solve_info",
        "unregularized_bot",
        r"problem\.Bv\s*@\s*x\s*-\s*rhs_lam",
    ),
    EvidenceRequirement(
        "M1",
        "MINRES transforms the RHS by the inverse square root.",
        "_minres_setup_values",
        "solve_b",
        r"derived_minv_sqrt\s*@\s*physical_b",
    ),
    EvidenceRequirement(
        "M2",
        "MINRES transforms the initial iterate by the square root.",
        "_minres_setup_values",
        "solve_x0",
        r"derived_msqrt\s*@\s*physical_x0",
    ),
    EvidenceRequirement(
        "M3",
        "MINRES solves the symmetrically transformed system.",
        "_minres_setup_values",
        "solve_mv",
        r"derived_minv_sqrt.*problem\.Mv.*derived_minv_sqrt",
    ),
    EvidenceRequirement(
        "M4",
        "MINRES reports the physical true residual.",
        "log_minres_iteration",
        "r_true",
        r"context\.physical_proj\s*@\s*\(context\.physical_b\s*-\s*context\.physical_Mv\s*@\s*x_physical\)",
    ),
)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ir-json",
        action="append",
        required=True,
        help="Algorithm Expansion IR JSON file. May be passed multiple times.",
    )
    parser.add_argument(
        "--title",
        default="Generated KKT Solver-Chain Equations",
        help="Section title to render as an H2 heading.",
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--out", help="Optional output path. Omit to print stdout.")
    return parser


def as_tuple(value: object) -> tuple[object, ...]:
    """Return list-like JSON values as tuples."""
    if isinstance(value, list | tuple):
        return tuple(value)
    return ()


def load_code_facts(paths: tuple[str, ...]) -> tuple[CodeFact, ...]:
    """Load all code facts from one or more Algorithm Expansion IR files."""
    facts: list[CodeFact] = []
    for raw_path in paths:
        payload = json.loads(Path(raw_path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{raw_path} must contain a JSON object")
        for raw_fact in as_tuple(payload.get("code_facts")):
            if not isinstance(raw_fact, dict):
                continue
            facts.append(
                CodeFact(
                    fact_id=str(raw_fact.get("fact_id", "")),
                    source_path=str(raw_fact.get("source_path", "")),
                    source_symbol=str(raw_fact.get("source_symbol", "")),
                    source_span=str(raw_fact.get("source_span", "")),
                    target=str(raw_fact.get("target", "")),
                    expression=str(raw_fact.get("expression", "")),
                )
            )
    return tuple(facts)


def match_requirement(
    requirement: EvidenceRequirement,
    facts: tuple[CodeFact, ...],
) -> EvidenceMatch | None:
    """Find the first code fact satisfying one requirement."""
    pattern = re.compile(requirement.expression_pattern)
    for fact in facts:
        if fact.source_symbol != requirement.source_symbol:
            continue
        if fact.target != requirement.target:
            continue
        if pattern.search(fact.expression):
            return EvidenceMatch(
                evidence_id=requirement.evidence_id,
                description=requirement.description,
                fact=fact,
            )
    return None


def build_evidence(facts: tuple[CodeFact, ...]) -> tuple[tuple[EvidenceMatch, ...], tuple[str, ...]]:
    """Return matched and missing requirement evidence."""
    matches: list[EvidenceMatch] = []
    missing: list[str] = []
    for requirement in REQUIREMENTS:
        match = match_requirement(requirement, facts)
        if match is None:
            missing.append(f"{requirement.evidence_id}: {requirement.description}")
        else:
            matches.append(match)
    return tuple(matches), tuple(missing)


def matches_by_id(evidence: tuple[EvidenceMatch, ...]) -> dict[str, EvidenceMatch]:
    """Return evidence matches keyed by requirement id."""
    return {match.evidence_id: match for match in evidence}


def render_fact_equations(
    lookup: dict[str, EvidenceMatch],
    evidence_ids: tuple[str, ...],
) -> list[str]:
    """Render exact equations copied from matched IR code facts."""
    lines = ["```text"]
    for evidence_id in evidence_ids:
        match = lookup[evidence_id]
        fact = match.fact
        lhs = f"{fact.source_symbol}.{fact.target}" if fact.target == "return" else fact.target
        lines.append(f"{lhs} := {fact.expression}")
    lines.append("```")
    return lines


def render_markdown(
    *,
    title: str,
    inputs: tuple[str, ...],
    evidence: tuple[EvidenceMatch, ...],
) -> str:
    """Render the reproducible equation section."""
    lookup = matches_by_id(evidence)
    lines: list[str] = [
        f"## {title}",
        "",
        "This section is generated from Algorithm Expansion IR code facts. It",
        "describes the implemented solver path only; proof obligations are kept in",
        "a separate subsection and are not runtime branches.",
        "Every displayed implementation equation below is substituted directly",
        "from a matched IR `code_facts[*].expression` entry.",
        "",
        "Generated from:",
        "",
    ]
    lines.extend(f"- `{path}`" for path in inputs)
    lines.extend(
        [
            "",
            "### Implemented KKT Solve Path",
            "",
            "PDIPM eliminates the inequality slack and inequality multiplier",
            "increments before calling `kkt.py`. The implemented reduced-KKT RHS,",
            "KKT call, and back-substitution equations are:",
            "",
        ]
    )
    lines.extend(render_fact_equations(lookup, ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8")))
    lines.extend(
        [
            "",
            "`kkt.py` regularizes the saddle operator, builds the preconditioner,",
            "and calls MINRES using these IR-derived equations:",
            "",
        ]
    )
    lines.extend(render_fact_equations(lookup, ("K1", "K2", "K3", "K4", "K5", "K6", "K7")))
    lines.extend(
        [
            "",
            "MINRES constructs the transformed solve variables from these code facts:",
            "",
        ]
    )
    lines.extend(render_fact_equations(lookup, ("M1", "M2", "M3")))
    lines.extend(
        [
            "",
            "The returned residual certificates are the following IR-derived",
            "diagnostic equations:",
            "",
        ]
    )
    lines.extend(render_fact_equations(lookup, ("R1", "R2", "R3", "M4")))
    lines.extend(
        [
            "",
            "The KKT info fields report norms and relative norms for the",
            "regularized and unregularized residual facts above; the nested MINRES",
            "info reports `final_true_rel_r` from the generated `r_true` fact.",
            "",
            "### Proof Obligations Separated From Runtime Flow",
            "",
            "The runtime path above only constructs and solves the reduced/regularized",
            "systems. The convergence proof still has separate mathematical",
            "obligations:",
            "",
            "- reduced-KKT algebra: the reduced system plus back-substitution matches",
            "  the full Newton linearization up to the chosen floor model;",
            "- regularization bridge: the generated regularized KKT solve fact",
            "  contributes only the permitted residual-model effect relative to",
            "  the unregularized reduced-KKT model for the current outer residual;",
            "- preconditioned MINRES quality: the transformed MINRES residual implies the",
            "  required residual-model-effect bound in physical KKT variables;",
            "- certificate soundness: the generated regularized, unregularized, and",
            "  MINRES true-residual facts are in the same residual units consumed",
            "  by the PDIPM residual-model-effect certificate.",
            "",
            "### Source Fact Evidence",
            "",
        ]
    )
    for match in evidence:
        fact = match.fact
        lines.extend(
            [
                f"- `{match.evidence_id}` {match.description}",
                f"  - source: `{fact.source_path}::{fact.source_symbol}:{fact.source_span}`",
                f"  - target: `{fact.target}`",
                f"  - expression: `{fact.expression}`",
            ]
        )
    return "\n".join(lines) + "\n"


def build_report(args: argparse.Namespace) -> SectionReport:
    """Build the section report from CLI args."""
    inputs = tuple(str(path) for path in args.ir_json)
    facts = load_code_facts(inputs)
    evidence, missing = build_evidence(facts)
    markdown = "" if missing else render_markdown(title=str(args.title), inputs=inputs, evidence=evidence)
    return SectionReport(
        status="missing_required_code_facts" if missing else "kkt_equation_section_built",
        inputs=inputs,
        evidence=evidence,
        missing_evidence=missing,
        markdown=markdown,
    )


def write_output(text: str, out: str | None) -> None:
    """Write CLI output to stdout or a file."""
    if out:
        Path(out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    report = build_report(args)
    if args.format == "json":
        write_output(json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n", args.out)
    else:
        if report.missing_evidence:
            for item in report.missing_evidence:
                print(f"missing required KKT equation evidence: {item}", file=sys.stderr)
            return 2
        write_output(report.markdown, args.out)
    return 0 if not report.missing_evidence else 2


if __name__ == "__main__":
    raise SystemExit(main())
