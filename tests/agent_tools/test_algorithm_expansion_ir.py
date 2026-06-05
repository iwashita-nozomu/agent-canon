"""Tests for Algorithm Expansion IR extraction."""

# @dependency-start
# responsibility Tests AST-only Algorithm Expansion IR tooling.
# upstream implementation ../../tools/agent_tools/algorithm_expansion_ir.py builds Algorithm IR.
# upstream design ../../agents/skills/formal-proof-workflow.md defines Algorithm IR workflow.
# downstream design ../../documents/tools/algorithm_expansion_ir.md documents CLI usage.
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "algorithm_expansion_ir.py"


class AlgorithmExpansionIRTest(unittest.TestCase):
    """Validate algorithm IR extraction and instance interaction edges."""

    def run_tool(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the tool against one fixture root."""
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(root),
                *args,
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_fixture(self, root: Path) -> tuple[Path, Path]:
        """Write a small algorithm module with import side effects."""
        source = root / "pkg" / "algorithm.py"
        external_solver = root / "pkg" / "external_solver.py"
        sentinel = root / "imported.txt"
        source.parent.mkdir(parents=True)
        external_solver.write_text(
            textwrap.dedent(
                """
                def imported_step(value: int) -> int:
                    return value + 2

                class ImportedAlgorithm:
                    def __call__(self, value: int) -> int:
                        return imported_step(value)
                """
            ).lstrip(),
            encoding="utf-8",
        )
        source.write_text(
            textwrap.dedent(
                f"""
                from dataclasses import dataclass
                from .external_solver import imported_step
                import pkg.external_solver as ext

                open({str(sentinel)!r}, "w").write("imported")
                raise RuntimeError("should_not_execute")

                @dataclass
                class State:
                    value: int

                class Info:
                    def __init__(self, converged: bool) -> None:
                        self.converged = converged

                class Stepper:
                    def step(self, state: State, problem: object) -> State:
                        direction = self._solve_direction(problem, state)
                        return _apply_step(state, direction)

                    def _solve_direction(self, problem: object, state: State) -> int:
                        return _kkt_residual(problem, state)

                def _kkt_residual(problem: object, state: State) -> int:
                    return state.value + 1

                def _apply_step(state: State, direction: int) -> State:
                    return State(state.value + direction)

                def initialize(config: object) -> tuple[Stepper, State]:
                    state = State(config.value)
                    algorithm = Stepper()
                    return algorithm, state

                def solve(algorithm: Stepper, state: State, problem: object) -> tuple[State, Info]:
                    next_state = algorithm.step(state, problem)
                    info = Info(converged=True)
                    return next_state, info

                def solve_from_constructor(state: State, problem: object) -> State:
                    stepper = Stepper()
                    return stepper.step(state, problem)

                def callback_runner(callback: object, state: State, problem: object) -> State:
                    return callback(state, problem)

                def solve_with_callback(state: State, problem: object) -> State:
                    stepper = Stepper()
                    return callback_runner(stepper.step, state, problem)

                class Wrapper:
                    algorithm: ext.ImportedAlgorithm

                    def __init__(self, algorithm: ext.ImportedAlgorithm) -> None:
                        self.algorithm = algorithm

                    def run(self, value: int) -> int:
                        return self.algorithm(value)

                import math as jnp

                def solve_with_import_alias(value: int) -> int:
                    return jnp.ceil(value)

                def solve_with_relative_import(value: int) -> int:
                    return imported_step(value)
                """
            ).lstrip(),
            encoding="utf-8",
        )
        return source, sentinel

    def test_json_ir_resolves_instance_method_and_does_not_import(self) -> None:
        """Annotated instances should resolve method calls without executing module code."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source, sentinel = self.write_fixture(root)

            result = self.run_tool(
                root,
                "--python-symbol",
                f"{source}::solve",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "algorithm_ir_built")
            self.assertIn("backend_profile_library", payload)
            self.assertFalse(sentinel.exists())
            self.assertIn("obligations", payload)
            self.assertIn("static_checks", payload)
            self.assertIn("backend_assumptions", payload)
            self.assertIn("code_facts", payload)
            self.assertIn("goal_directed_slice", payload)
            symbols = {node["source_symbol"] for node in payload["nodes"]}
            self.assertIn("solve", symbols)
            self.assertIn("Stepper.step", symbols)
            self.assertIn("Stepper._solve_direction", symbols)
            self.assertIn("_kkt_residual", symbols)
            self.assertIn("Info", symbols)
            edges = payload["edges"]
            step_edge = next(
                edge
                for edge in edges
                if edge["edge_kind"] == "instance_method_call"
                and edge["target_symbol"] == "Stepper.step"
                and edge["receiver_name"] == "algorithm"
            )
            self.assertEqual(step_edge["status"], "statically_checked")
            self.assertTrue(
                any(
                    edge["edge_kind"] == "instance_method_call"
                    and edge["target_symbol"] == "Stepper.step"
                    and edge["receiver_name"] == "algorithm"
                    and edge["receiver_type"] == "Stepper"
                    for edge in edges
                )
            )
            self.assertTrue(
                any(
                    edge["edge_kind"] == "instance_constructs"
                    and edge["target_symbol"] == "Info"
                    for edge in edges
                )
            )
            self.assertTrue(
                any(
                    check["edge_id"] == step_edge["edge_id"]
                    and check["check_kind"] == "instance_method_resolution"
                    and check["status"] == "statically_checked"
                    and check["proof_effect"]
                    == "drop_instance_dispatch_edge_before_obligation_selection"
                    for check in payload["static_checks"]
                )
            )
            obligations = "\n".join(payload["selected_local_obligations"])
            self.assertIn("Stepper._solve_direction", obligations)
            self.assertIn("linear_or_nonlinear_solve", obligations)
            step_obligation = next(
                obligation
                for obligation in payload["obligations"]
                if obligation["obligation_id"] == "obl__Stepper__step"
            )
            self.assertNotIn(step_edge["edge_id"], step_obligation["consumes_edges"])
            node_keys = set(payload["nodes"][0])
            self.assertGreaterEqual(
                node_keys,
                {
                    "node_id",
                    "source_path",
                    "source_symbol",
                    "source_span",
                    "node_kind",
                    "lineno",
                    "end_lineno",
                    "math_role",
                    "runtime_object",
                    "residual_unit",
                    "precision_model",
                    "iteration_scope",
                    "equation_tags",
                    "proof_relevance",
                    "selected_obligation_id",
                    "assumption_id",
                    "status",
                },
            )
            edge_keys = set(payload["edges"][0])
            self.assertGreaterEqual(
                edge_keys,
                {
                    "edge_id",
                    "source_node_id",
                    "target_node_id",
                    "edge_kind",
                    "source_symbol",
                    "target_symbol",
                    "call_text",
                    "line",
                    "assigned_to",
                    "receiver_name",
                    "receiver_type",
                    "child_config_field",
                    "child_initialize",
                    "proof_scope",
                    "selection_rule",
                    "role",
                    "quantity_flow",
                    "unit_conversion",
                    "resolved",
                    "status",
                },
            )
            static_check_keys = set(payload["static_checks"][0])
            self.assertGreaterEqual(
                static_check_keys,
                {
                    "check_id",
                    "edge_id",
                    "check_kind",
                    "source_symbol",
                    "target_symbol",
                    "evidence",
                    "status",
                    "proof_effect",
                },
            )
            self.assertTrue(
                any(
                    fact["fact_kind"] == "assignment_equation"
                    and fact["source_symbol"] == "solve"
                    and fact["target"] == "next_state"
                    for fact in payload["code_facts"]
                )
            )

    def test_constructor_assignment_enables_later_method_resolution(self) -> None:
        """Constructor assignment should type later instance method calls."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source, _ = self.write_fixture(root)

            result = self.run_tool(
                root,
                "--python-symbol",
                f"{source}::solve_from_constructor",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(
                any(
                    edge["edge_kind"] == "instance_method_call"
                    and edge["target_symbol"] == "Stepper.step"
                    and edge["receiver_name"] == "stepper"
                    and edge["receiver_type"] == "Stepper"
                    and edge["resolved"] is True
                    for edge in payload["edges"]
                )
            )
            self.assertTrue(
                any(
                    check["check_kind"] == "instance_method_resolution"
                    and check["target_symbol"] == "Stepper.step"
                    and check["status"] == "statically_checked"
                    for check in payload["static_checks"]
                )
            )
            self.assertIn(
                "Stepper.step",
                {node["source_symbol"] for node in payload["nodes"]},
            )

    def test_import_alias_attribute_call_is_not_instance_interaction(self) -> None:
        """Module alias attribute calls should not be reported as instance gaps."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source, _ = self.write_fixture(root)

            result = self.run_tool(
                root,
                "--python-symbol",
                f"{source}::solve_with_import_alias",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(
                any(
                    edge["target_symbol"] == "math.ceil"
                    and edge["edge_kind"] == "calls"
                    for edge in payload["edges"]
                )
            )
            self.assertFalse(
                any(
                    check["target_symbol"] == "jnp.ceil"
                    for check in payload["static_checks"]
                )
            )

    def test_relative_import_is_resolved_without_importing_module(self) -> None:
        """Relative imports should resolve to another AST module."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source, _ = self.write_fixture(root)

            result = self.run_tool(
                root,
                "--python-symbol",
                f"{source}::solve_with_relative_import",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(
                any(
                    node["source_path"] == "pkg/external_solver.py"
                    and node["source_symbol"] == "imported_step"
                    for node in payload["nodes"]
                )
            )
            self.assertTrue(
                any(
                    edge["target_symbol"] == "imported_step"
                    and edge["resolved"] is True
                    for edge in payload["edges"]
                )
            )

    def test_import_root_resolves_source_outside_repo_root(self) -> None:
        """Explicit import roots should allow AST expansion from another source tree."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "app"
            dependency_root = Path(tmp_dir) / "dependency"
            source = root / "pkg" / "algorithm.py"
            dependency_module = dependency_root / "external_pkg" / "solver.py"
            source.parent.mkdir(parents=True)
            dependency_module.parent.mkdir(parents=True)
            dependency_module.write_text(
                "def external_solve(value: int) -> int:\n    return value + 3\n",
                encoding="utf-8",
            )
            source.write_text(
                textwrap.dedent(
                    """
                    from external_pkg.solver import external_solve

                    def solve(value: int) -> int:
                        return external_solve(value)
                    """
                ).lstrip(),
                encoding="utf-8",
            )

            result = self.run_tool(
                root,
                "--import-root",
                str(dependency_root),
                "--python-symbol",
                f"{source}::solve",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(
                any(
                    node["source_path"] == str(dependency_module)
                    and node["source_symbol"] == "external_solve"
                    for node in payload["nodes"]
                )
            )
            self.assertTrue(
                any(
                    edge["target_symbol"] == "external_solve"
                    and edge["resolved"] is True
                    for edge in payload["edges"]
                )
            )

    def test_callable_argument_resolves_bound_method_reference(self) -> None:
        """Callable method references passed as values should expand the callee."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source, _ = self.write_fixture(root)

            result = self.run_tool(
                root,
                "--python-symbol",
                f"{source}::solve_with_callback",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            edge = next(
                edge
                for edge in payload["edges"]
                if edge["edge_kind"] == "callable_argument"
                and edge["target_symbol"] == "Stepper.step"
            )
            self.assertEqual(edge["status"], "statically_checked")
            self.assertTrue(
                any(
                    check["edge_id"] == edge["edge_id"]
                    and check["check_kind"] == "callable_argument_resolution"
                    for check in payload["static_checks"]
                )
            )

    def test_self_callable_field_resolves_imported_algorithm_call(self) -> None:
        """Class field annotations should resolve imported callable algorithm fields."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source, _ = self.write_fixture(root)

            result = self.run_tool(
                root,
                "--python-symbol",
                f"{source}::Wrapper.run",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(
                any(
                    node["source_path"] == "pkg/external_solver.py"
                    and node["source_symbol"] == "ImportedAlgorithm.__call__"
                    for node in payload["nodes"]
                )
            )
            self.assertTrue(
                any(
                    edge["target_symbol"] == "ImportedAlgorithm.__call__"
                    and edge["resolved"] is True
                    and edge["receiver_name"] == "self.algorithm"
                    for edge in payload["edges"]
                )
            )

    def test_markdown_output_contains_nodes_edges_and_obligations(self) -> None:
        """Markdown output should expose stable sections for proof notes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source, _ = self.write_fixture(root)

            result = self.run_tool(
                root,
                "--python-symbol",
                f"{source}::solve",
                "--format",
                "markdown",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("# Algorithm Expansion IR", result.stdout)
            self.assertIn("## Nodes", result.stdout)
            self.assertIn("## Edges", result.stdout)
            self.assertIn("## Code Facts", result.stdout)
            self.assertIn("## Static Checks", result.stdout)
            self.assertIn("## Backend Assumptions", result.stdout)
            self.assertIn("## Obligations", result.stdout)
            self.assertIn("## Selected Local Obligations", result.stdout)
            self.assertIn("`Stepper.step`", result.stdout)

    def test_fp32_target_adds_proof_only_backend_assumption_overlay(self) -> None:
        """Backend arithmetic witnesses belong to IR overlays, not runtime config."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source, _ = self.write_fixture(root)

            result = self.run_tool(
                root,
                "--python-symbol",
                f"{source}::solve",
                "--target-theorem",
                "fp32 floor-limited convergence on IREE",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            assumptions = payload["backend_assumptions"]
            self.assertEqual(len(assumptions), 1)
            assumption = assumptions[0]
            self.assertEqual(
                assumption["assumption_id"],
                "asm__backend_profile__target",
            )
            self.assertEqual(assumption["owning_surface"], "algorithm_expansion_ir")
            self.assertEqual(assumption["scope"], "proof_only_overlay")
            self.assertIn("backend_profile", assumption["profile_variable"])
            self.assertIn("profile_library_path", assumption)
            self.assertIn("profile_ids", assumption)
            self.assertIn("profile_details", assumption)
            self.assertIn("denormal_mode", assumption["required_witnesses"])
            self.assertIn(
                "read from the backend profile library by the IR builder",
                assumption["statement"],
            )

    def test_equation_tags_and_defaults_are_code_facts(self) -> None:
        """Expression/default facts should expose proof-topic equation tags."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "pkg" / "pdipm_like.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                textwrap.dedent(
                    """
                    _MINRES_DTYPE_RTOL_FACTOR = 64.0

                    class SolveConfig:
                        maxiter: int = 200
                        rtol: str = "1e-12"
                        reorthogonalization: str = "full"

                    def _pdipm_reduced_kkt_rhs_top(residuals, linearization):
                        rhs_top = residuals.r_dual - linearization.j_ineq
                        return rhs_top

                    def _pdipm_fraction_to_boundary_step_lengths(s, lam_ineq, ds, dlam):
                        alpha_pri = s + ds
                        alpha_dual = lam_ineq + dlam
                        return alpha_pri, alpha_dual

                    def _pdipm_apply_primal_dual_step(carry, direction, alpha_pri, alpha_dual):
                        x_next = carry.x + alpha_pri * direction.dx
                        return x_next

                    def _step_update(carry, direction):
                        alpha_pri, alpha_dual = _pdipm_fraction_to_boundary_step_lengths(
                            carry.s,
                            carry.lam_ineq,
                            direction.ds,
                            direction.dlam,
                        )
                        return _pdipm_apply_primal_dual_step(
                            carry,
                            direction,
                            alpha_pri,
                            alpha_dual,
                        )

                    def _minres_effective_stopping(config):
                        runtime_rtol = config.rtol
                        return runtime_rtol
                    """
                ).lstrip(),
                encoding="utf-8",
            )

            result = self.run_tool(
                root,
                "--python-symbol",
                f"{source}::_step_update",
                "--target-theorem",
                "PDIPM local floor-limited convergence with MINRES defaults",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            node_tags = {
                tag
                for node in payload["nodes"]
                for tag in node.get("equation_tags", [])
            }
            self.assertIn("step_update", node_tags)
            self.assertIn("floor_preserving_step", node_tags)
            facts = payload["code_facts"]
            self.assertTrue(
                any(
                    fact["target"] == "_MINRES_DTYPE_RTOL_FACTOR"
                    and "minres_defaults" in fact["equation_tags"]
                    for fact in facts
                )
            )
            self.assertTrue(
                any(
                    fact["source_symbol"] == "SolveConfig"
                    and fact["target"] == "maxiter"
                    and fact["expression"] == "200"
                    for fact in facts
                )
            )
            self.assertTrue(
                any(
                    fact["source_symbol"] == "_step_update"
                    and fact["fact_kind"] == "assignment_equation"
                    and "step_update" in fact["target_profiles"]
                    for fact in facts
                )
            )

    def test_backend_profile_library_is_read_by_ir_builder(self) -> None:
        """Backend profile libraries are proof inputs to the IR builder."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source, _ = self.write_fixture(root)
            profile_library = root / "lean" / "lib" / "backend_profiles.json"
            profile_library.parent.mkdir(parents=True)
            profile_library.write_text(
                json.dumps(
                    {
                        "schema": "agent-canon.backend-profiles.v1",
                        "profiles": {
                            "iree_fp32_strict": {
                                "required_witnesses": [
                                    "dtype",
                                    "denormal_mode",
                                    "lowered_ir_or_backend_flag_evidence",
                                ]
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_tool(
                root,
                "--python-symbol",
                f"{source}::solve",
                "--target-theorem",
                "fp32 floor-limited convergence on IREE",
                "--backend-profile-library",
                "lean/lib/backend_profiles.json",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            assumption = payload["backend_assumptions"][0]
            self.assertEqual(payload["backend_profile_library"], "lean/lib/backend_profiles.json")
            self.assertEqual(assumption["profile_ids"], ["iree_fp32_strict"])
            self.assertEqual(
                assumption["required_witnesses"],
                [
                    "denormal_mode",
                    "dtype",
                    "lowered_ir_or_backend_flag_evidence",
                ],
            )

    def test_bookkeeping_nodes_are_excluded_from_selected_obligations(self) -> None:
        """IR should not turn config/initialize bookkeeping into local proof work."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source, _ = self.write_fixture(root)

            result = self.run_tool(
                root,
                "--python-symbol",
                f"{source}::initialize",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            node_by_symbol = {node["source_symbol"]: node for node in payload["nodes"]}
            self.assertEqual(node_by_symbol["initialize"]["proof_relevance"], "excluded")
            self.assertEqual(node_by_symbol["State"]["proof_relevance"], "excluded")
            obligations = "\n".join(payload["selected_local_obligations"])
            self.assertNotIn("initialize", obligations)
            self.assertNotIn("State", obligations)

    def test_invalid_root_symbol_fails_clearly(self) -> None:
        """Missing symbols should fail instead of producing a partial IR."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source, _ = self.write_fixture(root)

            result = self.run_tool(
                root,
                "--python-symbol",
                f"{source}::missing",
                "--format",
                "json",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Python AST symbol not found: missing", result.stderr)


if __name__ == "__main__":
    unittest.main()
