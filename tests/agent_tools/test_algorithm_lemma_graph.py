"""Tests for Algorithm IR to lemma dependency graph conversion."""

# @dependency-start
# responsibility Tests lemma dependency graph construction from Algorithm Expansion IR.
# upstream implementation ../../tools/agent_tools/algorithm_lemma_graph.py builds lemma graphs.
# upstream implementation ../../tools/agent_tools/algorithm_expansion_ir.py emits source IR.
# upstream design ../../agents/skills/formal-proof-workflow.md defines proof graph workflow.
# upstream design ../../documents/tools/algorithm_lemma_graph.md documents CLI usage.
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "algorithm_lemma_graph.py"


def sample_ir_payload() -> dict[str, object]:
    """Return a compact Algorithm Expansion IR payload."""
    return {
        "status": "algorithm_ir_built",
        "root_path": "python/app/pdipm.py",
        "root_symbol": "_solve",
        "target_theorem": "PDIPM local floor-limited convergence",
        "nodes": [
            {
                "node_id": "python_app_pdipm_py___solve",
                "source_path": "python/app/pdipm.py",
                "source_symbol": "_solve",
                "math_role": "linear_or_nonlinear_solve",
                "runtime_object": "direction_or_solve",
                "residual_unit": "outer_ipm_residual_unit",
                "precision_model": "none",
                "equation_tags": ["step_update"],
            },
            {
                "node_id": "python_app_kkt_py___solve",
                "source_path": "python/app/kkt.py",
                "source_symbol": "_solve",
                "math_role": "linear_or_nonlinear_solve",
                "runtime_object": "direction_or_solve",
                "residual_unit": "kkt_residual_unit",
                "precision_model": "none",
                "equation_tags": ["reduced_kkt"],
            },
            {
                "node_id": "python_app_pdipm_py___certificate",
                "source_path": "python/app/pdipm.py",
                "source_symbol": "_certificate",
                "math_role": "certificate",
                "runtime_object": "certificate",
                "residual_unit": "certificate_unit",
                "precision_model": "none",
                "equation_tags": [],
            },
            {
                "node_id": "python_app_pdipm_py___fp32_floor",
                "source_path": "python/app/pdipm.py",
                "source_symbol": "_fp32_floor",
                "math_role": "implementation_bookkeeping",
                "runtime_object": "unknown",
                "residual_unit": "outer_ipm_residual_unit",
                "precision_model": "dtype_or_backend_floor",
                "equation_tags": ["floor_preserving_step"],
            },
        ],
        "edges": [
            {
                "edge_id": "edge-1",
                "source_node_id": "python_app_pdipm_py___solve",
                "target_node_id": "python_app_kkt_py___solve",
                "source_symbol": "_solve",
                "target_symbol": "_solve",
                "status": "retained",
            },
            {
                "edge_id": "edge-2",
                "source_node_id": "python_app_pdipm_py___solve",
                "target_node_id": "python_app_pdipm_py___certificate",
                "source_symbol": "_solve",
                "target_symbol": "_certificate",
                "status": "statically_checked",
            },
        ],
        "obligations": [
            {
                "obligation_id": "obl___solve",
                "statement": "prove pdipm solve",
                "grain": "local_obligation",
                "consumes_nodes": ["python_app_pdipm_py___solve"],
                "consumes_edges": ["edge-1"],
                "remaining_gap": "formal theorem required",
            },
            {
                "obligation_id": "obl___solve",
                "statement": "prove kkt solve",
                "grain": "local_obligation",
                "consumes_nodes": ["python_app_kkt_py___solve"],
                "consumes_edges": [],
                "remaining_gap": "formal theorem required",
            },
            {
                "obligation_id": "obl___certificate",
                "statement": "prove certificate",
                "grain": "known_lemma",
                "consumes_nodes": ["python_app_pdipm_py___certificate"],
                "consumes_edges": [],
                "remaining_gap": "checked lemma required",
            },
            {
                "obligation_id": "obl___fp32_floor",
                "statement": "assume fp32 floor",
                "grain": "assumption",
                "consumes_nodes": ["python_app_pdipm_py___fp32_floor"],
                "consumes_edges": [],
                "remaining_gap": "backend assumption required",
            },
        ],
        "backend_assumptions": [
            {
                "assumption_id": "asm__backend_profile__target",
                "statement": (
                    "Backend floating-point semantics are proof IR overlay "
                    "variables and evidence obligations."
                ),
                "profile_variable": "backend_profile",
                "profile_library_path": "lean/lib/backend_profiles.json",
                "profile_ids": ["iree_fp32_strict"],
                "profile_details": {
                    "iree_fp32_strict": {
                        "description": "IREE FP32 profile",
                        "required_witnesses": [
                            "dtype",
                            "denormal_mode",
                            "lowered_ir_or_backend_flag_evidence",
                        ],
                    }
                },
                "owning_surface": "algorithm_expansion_ir",
                "scope": "proof_only_overlay",
                "applies_to_nodes": ["python_app_pdipm_py___fp32_floor"],
                "required_witnesses": ["dtype", "denormal_mode"],
                "checker_route": "record_as_backend_assumption",
                "status": "unverified",
            }
        ],
        "code_facts": [
            {
                "fact_id": "fact__python_app_pdipm_py___solve__assignment_equation__line_10__x_next",
                "source_path": "python/app/pdipm.py",
                "source_symbol": "_solve",
                "source_node_id": "python_app_pdipm_py___solve",
                "source_span": "10:None",
                "fact_kind": "assignment_equation",
                "target": "x_next",
                "expression": "x + alpha * dx",
                "statement": "`_solve` assignment_equation `x_next` as `x + alpha * dx`.",
                "equation_tags": ["step_update"],
                "target_profiles": ["all", "local_convergence", "step_update"],
            },
            {
                "fact_id": "fact__python_app_minres_py__solveconfig__class_default__line_5__maxiter",
                "source_path": "python/app/minres.py",
                "source_symbol": "SolveConfig",
                "source_node_id": "python_app_minres_py__SolveConfig",
                "source_span": "5:None",
                "fact_kind": "class_default",
                "target": "maxiter",
                "expression": "200",
                "statement": "`SolveConfig` class_default `maxiter` as `200`.",
                "equation_tags": ["minres_defaults"],
                "target_profiles": ["all", "solver_chain", "minres_defaults"],
            },
        ],
    }


class AlgorithmLemmaGraphTest(unittest.TestCase):
    """Validate lemma graph generation and graph connectivity."""

    def run_tool(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        """Run the lemma graph tool."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=PROJECT_ROOT,
            check=False,
            input=stdin,
            capture_output=True,
            text=True,
        )

    def test_json_graph_connects_target_profiles_and_dedupes_duplicate_obligation_ids(
        self,
    ) -> None:
        """The graph should use IR node ids, not duplicated obligation ids."""
        result = self.run_tool(
            "--format",
            "json",
            stdin=json.dumps(sample_ir_payload()),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "lemma_graph_built")
        self.assertTrue(payload["validation"]["valid"])
        lemma_ids = {node["lemma_id"] for node in payload["lemma_nodes"]}
        self.assertIn("lemma__python_app_pdipm_py_solve", lemma_ids)
        self.assertIn("lemma__python_app_kkt_py_solve", lemma_ids)
        self.assertIn("lemma__asm_backend_profile_target", lemma_ids)
        self.assertIn("lemma__backend_profile__iree_fp32_strict", lemma_ids)
        self.assertIn(
            "lemma__fact_python_app_pdipm_py_solve_assignment_equation_line_10_x_next",
            lemma_ids,
        )
        self.assertIn(
            "lemma__fact_python_app_minres_py_solveconfig_class_default_line_5_maxiter",
            lemma_ids,
        )
        self.assertNotEqual(
            "lemma__python_app_pdipm_py_solve",
            "lemma__python_app_kkt_py_solve",
        )
        self.assertTrue(
            any(
                edge["source_lemma_id"] == "lemma__python_app_pdipm_py_solve"
                and edge["target_lemma_id"] == "lemma__python_app_kkt_py_solve"
                and edge["edge_kind"] == "implementation_lemma_dependency"
                for edge in payload["lemma_edges"]
            )
        )
        self.assertTrue(
            any(
                edge["source_lemma_id"] == "lemma__python_app_pdipm_py_fp32_floor"
                and edge["target_lemma_id"] == "lemma__asm_backend_profile_target"
                and edge["edge_kind"] == "backend_profile_dependency"
                for edge in payload["lemma_edges"]
            )
        )
        self.assertTrue(
            any(
                edge["source_lemma_id"] == "lemma__asm_backend_profile_target"
                and edge["target_lemma_id"] == "lemma__backend_profile__iree_fp32_strict"
                and edge["edge_kind"] == "backend_profile_record"
                for edge in payload["lemma_edges"]
            )
        )
        self.assertTrue(
            any(
                edge["source_lemma_id"] == "lemma__python_app_pdipm_py_solve"
                and edge["target_lemma_id"]
                == "lemma__fact_python_app_pdipm_py_solve_assignment_equation_line_10_x_next"
                and edge["edge_kind"] == "lemma_consumes_code_fact"
                for edge in payload["lemma_edges"]
            )
        )

    def test_target_profile_selects_relevant_lemma_chain(self) -> None:
        """A profile-specific target should select only matching lemma nodes."""
        result = self.run_tool(
            "--target-profile",
            "certificate_soundness",
            "--format",
            "json",
            stdin=json.dumps(sample_ir_payload()),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["target_profiles"], ["certificate_soundness"])
        chains = payload["target_chains"]
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0]["profile"], "certificate_soundness")
        self.assertEqual(
            chains[0]["lemma_ids"],
            ["lemma__python_app_pdipm_py_certificate"],
        )
        self.assertTrue(chains[0]["connected"])

    def test_equation_target_profiles_select_code_fact_nodes(self) -> None:
        """Equation-specific profiles should select matching code-derived facts."""
        for profile, expected in (
            (
                "step_update",
                "lemma__fact_python_app_pdipm_py_solve_assignment_equation_line_10_x_next",
            ),
            (
                "minres_defaults",
                "lemma__fact_python_app_minres_py_solveconfig_class_default_line_5_maxiter",
            ),
            ("floor_preserving_step", "lemma__python_app_pdipm_py_fp32_floor"),
            ("reduced_kkt", "lemma__python_app_kkt_py_solve"),
        ):
            with self.subTest(profile=profile):
                result = self.run_tool(
                    "--target-profile",
                    profile,
                    "--format",
                    "json",
                    stdin=json.dumps(sample_ir_payload()),
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["target_profiles"], [profile])
                self.assertTrue(payload["target_chains"][0]["connected"])
                self.assertIn(expected, payload["target_chains"][0]["lemma_ids"])

    def test_markdown_and_dot_outputs_are_available(self) -> None:
        """Reader and graphviz formats should render stable graph sections."""
        ir_json = json.dumps(sample_ir_payload())
        markdown = self.run_tool("--format", "markdown", stdin=ir_json)
        dot = self.run_tool("--format", "dot", stdin=ir_json)

        self.assertEqual(markdown.returncode, 0, markdown.stderr)
        self.assertIn("# Lemma Dependency Graph", markdown.stdout)
        self.assertIn("## Target Chains", markdown.stdout)
        self.assertEqual(dot.returncode, 0, dot.stderr)
        self.assertIn("digraph lemma_dependency_graph", dot.stdout)
        self.assertIn("target_requires", dot.stdout)

    def test_cyclic_graph_returns_nonzero(self) -> None:
        """Cyclic lemma dependencies should fail validation."""
        payload = sample_ir_payload()
        payload["edges"] = [  # type: ignore[index]
            *payload["edges"],  # type: ignore[index]
            {
                "edge_id": "cycle-edge",
                "source_node_id": "python_app_kkt_py___solve",
                "target_node_id": "python_app_pdipm_py___solve",
                "status": "retained",
            },
        ]
        result = self.run_tool("--format", "json", stdin=json.dumps(payload))

        self.assertEqual(result.returncode, 1, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertFalse(parsed["validation"]["valid"])
        self.assertFalse(parsed["validation"]["acyclic"])


if __name__ == "__main__":
    unittest.main()
