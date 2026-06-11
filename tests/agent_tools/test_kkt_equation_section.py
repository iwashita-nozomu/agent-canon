"""Tests for generated KKT solver-chain equation sections."""

# @dependency-start
# responsibility Tests KKT solver-chain equation section generation from Algorithm IR facts.
# upstream implementation ../../tools/agent_tools/kkt_equation_section.py emits equation sections.
# upstream implementation ../../tools/agent_tools/algorithm_expansion_ir.py emits source facts.
# upstream design ../../agents/skills/algorithm-proof-exploration.md defines IR-backed proof notes.
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "kkt_equation_section.py"


def code_fact(
    source_symbol: str,
    target: str,
    expression: str,
    *,
    fact_id: str | None = None,
    source_path: str = "python/jax_util/optimizers/pdipm.py",
) -> dict[str, str]:
    """Build one compact IR code fact."""
    return {
        "fact_id": fact_id or f"fact__{source_symbol}__{target}",
        "source_path": source_path,
        "source_symbol": source_symbol,
        "source_span": "1:None",
        "target": target,
        "expression": expression,
    }


def sample_ir_payload() -> dict[str, object]:
    """Return the minimal facts required by the equation generator."""
    return {
        "status": "algorithm_ir_built",
        "code_facts": [
            code_fact(
                "_pdipm_reduced_kkt_complementarity_rhs",
                "return",
                "r_c_used - safe_lam_ineq * residuals.r_ineq",
            ),
            code_fact(
                "_pdipm_reduced_kkt_rhs_top",
                "return",
                (
                    "-residuals.r_x + linearization.j_ineq_t * "
                    "linearization.ineq_block_scale @ "
                    "(linearization.ineq_block_rhs_scale @ complementarity_rhs)"
                ),
            ),
            code_fact("_pdipm_solve_direction", "rhs_bot", "-residuals.r_eq"),
            code_fact(
                "_pdipm_solve_direction",
                "kkt_answer",
                (
                    "runtime.kkt_algorithm(kkt.Problem(Hv=linearization.h_eff, "
                    "Bv=linearization.j_eq, BTv=linearization.j_eq_t, "
                    "rhs_x=rhs_top, rhs_lam=rhs_bot), kkt_state_in, solve_config)"
                ),
            ),
            code_fact(
                "_pdipm_solve_direction",
                "dx",
                "getattr(kkt_answer, 'x')",
            ),
            code_fact(
                "_pdipm_solve_direction",
                "dlam_eq",
                "getattr(kkt_answer, 'lam')",
            ),
            code_fact(
                "_pdipm_solve_direction",
                "ds",
                "-(residuals.r_ineq + linearization.j_ineq @ dx)",
            ),
            code_fact(
                "_pdipm_solve_direction",
                "dlam",
                "-(diag_s_inv @ (r_c_used + diag_lam @ ds))",
            ),
            code_fact(
                "_kkt_regularized_h",
                "regularized_h",
                "LinOp(lambda v: problem.Hv @ v + primal_regularization * v)",
                source_path="python/jax_util/solvers/kkt.py",
            ),
            code_fact(
                "_kkt_update_preconditioners",
                "schur_base",
                "problem.Bv * h_inv_approx * problem.BTv",
                source_path="python/jax_util/solvers/kkt.py",
            ),
            code_fact(
                "_kkt_update_preconditioners",
                "schur_mv",
                "LinOp(lambda v: schur_base @ v + dual_regularization * v)",
                source_path="python/jax_util/solvers/kkt.py",
            ),
            code_fact(
                "_kkt_run_minres",
                "preconditioner",
                (
                    "rank_r_preconditioner.make_block_diagonal("
                    "h_inv_approx, s_inv_approx)"
                ),
                source_path="python/jax_util/solvers/kkt.py",
            ),
            code_fact(
                "_kkt_preconditioner_sqrt_pair",
                "preconditioner_minv_sqrt",
                "rank_r_preconditioner.power_operator(preconditioner, preconditioner_power=0.5)",
                source_path="python/jax_util/solvers/kkt.py",
            ),
            code_fact(
                "_kkt_preconditioner_sqrt_pair",
                "preconditioner_msqrt",
                "rank_r_preconditioner.power_operator(preconditioner, preconditioner_power=-0.5)",
                source_path="python/jax_util/solvers/kkt.py",
            ),
            code_fact(
                "_kkt_run_minres",
                "solver_answer",
                (
                    "solver_algorithm(minres.Problem(Mv=kkt_operator, "
                    "rhs=rhs), minres_state, solve_config.solver_solve)"
                ),
                source_path="python/jax_util/solvers/kkt.py",
            ),
            code_fact(
                "_kkt_solve_info",
                "regularized_residual",
                "kkt_operator @ v - rhs",
                source_path="python/jax_util/solvers/kkt.py",
            ),
            code_fact(
                "_kkt_solve_info",
                "unregularized_top",
                "problem.Hv @ x + problem.BTv @ lam - rhs_x",
                source_path="python/jax_util/solvers/kkt.py",
            ),
            code_fact(
                "_kkt_solve_info",
                "unregularized_bot",
                "problem.Bv @ x - rhs_lam",
                source_path="python/jax_util/solvers/kkt.py",
            ),
            code_fact(
                "_minres_transformed_system",
                "solve_b",
                "minv_sqrt @ physical_b",
                source_path="python/jax_util/solvers/minres.py",
            ),
            code_fact(
                "_minres_transformed_system",
                "solve_x0",
                "msqrt @ physical_x0",
                source_path="python/jax_util/solvers/minres.py",
            ),
            code_fact(
                "_minres_transformed_system",
                "solve_mv",
                (
                    "LinOp(lambda y: minv_sqrt @ "
                    "(physical_proj @ (problem.Mv @ (physical_proj @ (minv_sqrt @ y)))))"
                ),
                source_path="python/jax_util/solvers/minres.py",
            ),
            code_fact(
                "log_minres_iteration",
                "r_true",
                "context.physical_proj @ (context.physical_b - context.physical_Mv @ x_physical)",
                source_path="python/jax_util/solvers/minres.py",
            ),
        ],
    }


class KktEquationSectionTest(unittest.TestCase):
    """Validate generated equation sections."""

    def run_tool(self, payload: dict[str, object], *args: str) -> subprocess.CompletedProcess[str]:
        """Run the equation-section tool with one temporary IR input."""
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            ir_path = root / "ir.json"
            ir_path.write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--ir-json", str(ir_path), *args],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

    def test_markdown_section_contains_solver_chain_equations(self) -> None:
        """A complete fact set should render runtime equations and proof obligations."""
        result = self.run_tool(sample_ir_payload())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Generated KKT Solver-Chain Equations", result.stdout)
        self.assertIn("Every displayed implementation equation", result.stdout)
        self.assertIn("_pdipm_reduced_kkt_rhs_top.return := -residuals.r_x", result.stdout)
        self.assertIn("dx := getattr(kkt_answer, 'x')", result.stdout)
        self.assertIn("dlam_eq := getattr(kkt_answer, 'lam')", result.stdout)
        self.assertIn("ds := -(residuals.r_ineq + linearization.j_ineq @ dx)", result.stdout)
        self.assertIn("regularized_h := LinOp(lambda v: problem.Hv @ v", result.stdout)
        self.assertIn("solve_mv := LinOp(lambda y: minv_sqrt @", result.stdout)
        self.assertIn("unregularized_top := problem.Hv @ x", result.stdout)
        self.assertIn("Proof Obligations Separated From Runtime Flow", result.stdout)
        self.assertNotIn("Proof boundary", result.stdout)
        self.assertNotIn("[ H_eff   J_eq^T ]", result.stdout)
        self.assertNotIn("A_reg = [ H + rho I", result.stdout)

    def test_json_reports_missing_required_code_facts(self) -> None:
        """The generator should fail closed when a required source fact is missing."""
        payload = sample_ir_payload()
        payload["code_facts"] = payload["code_facts"][:-1]  # type: ignore[index]

        result = self.run_tool(payload, "--format", "json")

        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "missing_required_code_facts")
        self.assertEqual(len(report["missing_evidence"]), 1)
        self.assertIn("MINRES reports the physical true residual", report["missing_evidence"][0])


if __name__ == "__main__":
    unittest.main()
