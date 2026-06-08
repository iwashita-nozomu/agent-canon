"""Tests for Algorithm IR Mermaid flowchart rendering."""

# @dependency-start
# responsibility Tests Algorithm Expansion IR to Mermaid proof flowchart rendering.
# upstream implementation ../../tools/agent_tools/algorithm_flowchart.py renders flowcharts.
# upstream implementation ../../tools/agent_tools/algorithm_expansion_ir.py emits source IR.
# upstream implementation ../../tools/agent_tools/algorithm_lemma_graph.py emits lemma graphs.
# upstream design ../../agents/skills/algorithm-flowchart.md documents workflow.
# downstream design ../../documents/tools/algorithm_flowchart.md documents CLI usage.
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "algorithm_flowchart.py"


def sample_ir_payload() -> dict[str, object]:
    """Return a compact Algorithm Expansion IR payload."""
    return {
        "status": "algorithm_ir_built",
        "root_path": "python/app/pdipm.py",
        "root_symbol": "_solve",
        "target_theorem": "PDIPM local convergence",
        "nodes": [
            {
                "node_id": "python_app_pdipm_py___solve",
                "source_path": "python/app/pdipm.py",
                "source_symbol": "_solve",
                "math_role": "linear_or_nonlinear_solve",
                "runtime_object": "direction_or_solve",
                "residual_unit": "outer_ipm_residual_unit",
                "precision_model": "none",
            },
            {
                "node_id": "python_app_minres_py___solve",
                "source_path": "python/app/minres.py",
                "source_symbol": "_solve",
                "math_role": "linear_or_nonlinear_solve",
                "runtime_object": "direction_or_solve",
                "residual_unit": "minres_true_residual_unit",
                "precision_model": "dtype_or_backend_floor",
            },
        ],
        "edges": [
            {
                "edge_id": "edge-1",
                "source_node_id": "python_app_pdipm_py___solve",
                "target_node_id": "python_app_minres_py___solve",
                "edge_kind": "calls",
                "call_text": "solve_kkt_with_minres",
                "status": "retained",
            }
        ],
        "code_facts": [
            {
                "fact_id": "fact__python_app_minres_py___finish__r_true",
                "source_path": "python/app/minres.py",
                "source_symbol": "_finish",
                "source_node_id": "python_app_minres_py___solve",
                "fact_kind": "assignment_equation",
                "target": "r_true",
                "expression": "physical_proj @ (physical_b - physical_Mv @ x_physical)",
            }
        ],
    }


def sample_lemma_graph() -> dict[str, object]:
    """Return a compact LemmaGraph payload."""
    return {
        "status": "lemma_graph_built",
        "lemma_nodes": [
            {
                "lemma_id": "lemma__python_app_pdipm_py_solve",
                "proof_status": "unverified",
                "source_nodes": ["python_app_pdipm_py___solve"],
                "source_code_facts": [],
            },
            {
                "lemma_id": "lemma__python_app_minres_py_solve",
                "proof_status": "assumption",
                "source_nodes": ["python_app_minres_py___solve"],
                "source_code_facts": [
                    "fact__python_app_minres_py___finish__r_true"
                ],
            },
        ],
    }


def sample_proof_status() -> dict[str, object]:
    """Return a compact proof status overlay."""
    return {
        "checked_fragments": [
            {
                "theorem": "PDIPMConvergence.minres_true_residual",
                "status": "verified",
            }
        ],
        "open_frontier": [
            {
                "hole_id": "B8 MINRES finite precision",
                "status": "unverified_with_next_witness",
                "code_derived_facts": [
                    {
                        "fact_id": "B8-F1",
                        "source_id": "lemma__python_app_minres_py_solve",
                    }
                ],
            }
        ],
    }


class AlgorithmFlowchartTest(unittest.TestCase):
    """Validate Mermaid flowchart generation."""

    def run_tool(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        """Run the flowchart tool."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=PROJECT_ROOT,
            check=False,
            input=stdin,
            capture_output=True,
            text=True,
        )

    def test_markdown_flowchart_overlays_proof_status_and_code_facts(self) -> None:
        """The chart should include algorithm, fact, and proof status blocks."""
        with tempfile.TemporaryDirectory() as raw_dir:
            tmp = Path(raw_dir)
            ir_path = tmp / "ir.json"
            graph_path = tmp / "graph.json"
            proof_path = tmp / "proof_status.json"
            ir_path.write_text(json.dumps(sample_ir_payload()), encoding="utf-8")
            graph_path.write_text(json.dumps(sample_lemma_graph()), encoding="utf-8")
            proof_path.write_text(json.dumps(sample_proof_status()), encoding="utf-8")

            result = self.run_tool(
                "--ir-json",
                str(ir_path),
                "--lemma-graph",
                str(graph_path),
                "--proof-status",
                str(proof_path),
                "--include-code-facts",
                "--direction",
                "LR",
                "--format",
                "markdown",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("```mermaid", result.stdout)
        self.assertIn("flowchart LR", result.stdout)
        self.assertIn("solve_kkt_with_minres", result.stdout)
        self.assertIn("assignment_equation: r_true", result.stdout)
        self.assertIn("proof: unverified_with_next_witness", result.stdout)
        self.assertIn("classDef open", result.stdout)

    def test_json_summary_reports_status_counts(self) -> None:
        """JSON output should expose machine-readable status counts."""
        result = self.run_tool(
            "--ir-json",
            "-",
            "--format",
            "json",
            stdin=json.dumps(sample_ir_payload()),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "algorithm_flowchart_built")
        self.assertEqual(payload["node_count"], 2)
        self.assertEqual(payload["status_counts"]["unverified"], 2)
        self.assertIn("flowchart TD", payload["mermaid"])


if __name__ == "__main__":
    unittest.main()
