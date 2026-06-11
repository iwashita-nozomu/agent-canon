"""Tests for IR equation fact to lemma graph correspondence checker."""

# @dependency-start
# responsibility Tests Algorithm Expansion IR / LemmaGraph correspondence checks.
# upstream implementation ../../tools/agent_tools/ir_graph_correspondence.py checks IR equation coverage.
# upstream implementation ../../tools/agent_tools/algorithm_lemma_graph.py emits code-fact lemma nodes.
# upstream design ../../documents/tools/ir_graph_correspondence.md documents CLI usage.
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "ir_graph_correspondence.py"


FACT_ID = "fact__python_app_pdipm__py___step_update__assignment_equation__line_10__x_next"
FACT_LEMMA_ID = "lemma__fact_python_app_pdipm_py_step_update_assignment_equation_line_10_x_next"


def sample_ir() -> dict[str, object]:
    """Return a compact IR payload with one step-update assignment fact."""
    return {
        "status": "algorithm_ir_built",
        "root_path": "python/app/pdipm.py",
        "root_symbol": "_solve",
        "target_theorem": "local_convergence",
        "code_facts": [
            {
                "fact_id": FACT_ID,
                "fact_kind": "assignment_equation",
                "source_path": "python/app/pdipm.py",
                "source_symbol": "_step_update",
                "source_node_id": "node__step_update",
                "target": "x_next",
                "expression": "x + alpha * dx",
                "statement": "`_step_update` assignment_equation `x_next` as `x + alpha * dx`.",
                "equation_tags": ["step_update"],
                "target_profiles": ["local_convergence", "step_update"],
            },
            {
                "fact_id": "fact__python_app_pdipm__py___step_update__class_default__line_4__alpha",
                "fact_kind": "class_default",
                "source_path": "python/app/pdipm.py",
                "source_symbol": "_step_update",
                "source_node_id": "node__step_update",
                "target": "alpha",
                "expression": "1.0",
                "statement": "`_step_update` class_default `alpha` as `1.0`.",
                "equation_tags": ["step_update"],
                "target_profiles": ["local_convergence"],
            },
        ],
    }


def sample_graph(include_fact_node: bool = True) -> dict[str, object]:
    """Return a compact lemma graph with a code-fact consumption edge."""
    nodes: list[dict[str, object]] = [
        {
            "lemma_id": "target__local_convergence__local_convergence",
            "lemma_kind": "target_theorem",
            "proof_status": "unverified",
            "source_code_facts": [],
        },
        {
            "lemma_id": "lemma__node_step_update",
            "lemma_kind": "local_obligation",
            "proof_status": "unverified",
            "source_code_facts": [FACT_ID],
        },
    ]
    if include_fact_node:
        nodes.append(
            {
                "lemma_id": FACT_LEMMA_ID,
                "lemma_kind": "code_fact",
                "proof_status": "code_derived",
                "source_code_facts": [FACT_ID],
            }
        )
    return {
        "status": "lemma_graph_valid",
        "lemma_nodes": nodes,
        "lemma_edges": [
            {
                "edge_id": "edge-1",
                "source_lemma_id": "target__local_convergence__local_convergence",
                "target_lemma_id": "lemma__node_step_update",
                "edge_kind": "target_requires",
                "status": "valid",
            },
            {
                "edge_id": "edge-2",
                "source_lemma_id": "lemma__node_step_update",
                "target_lemma_id": FACT_LEMMA_ID,
                "edge_kind": "lemma_consumes_code_fact",
                "status": "valid",
            },
        ],
        "target_chains": [
            {
                "target_id": "target__local_convergence__local_convergence",
                "profile": "local_convergence",
                "theorem": "local_convergence",
                "lemma_ids": ["lemma__node_step_update", FACT_LEMMA_ID],
                "reachable_lemma_ids": ["lemma__node_step_update", FACT_LEMMA_ID],
                "missing_lemma_ids": [],
                "connected": True,
            }
        ],
    }


def sample_status() -> dict[str, object]:
    """Return a proof-status payload that adopts the assignment fact."""
    return {
        "checked_fragments": [
            {
                "theorem": "Proof.step_update_equation",
                "status": "verified",
                "code_derived_facts": [
                    {
                        "derivability": "ir_or_lemma_graph",
                        "fact_id": FACT_ID,
                        "source_id": FACT_LEMMA_ID,
                        "source_kind": "lemma_node",
                        "statement": "The step update assignment is consumed.",
                    }
                ],
            }
        ]
    }


class IRGraphCorrespondenceTest(unittest.TestCase):
    """Validate assignment fact correspondence checks."""

    def run_tool(
        self,
        *,
        graph: dict[str, object] | None = None,
        status: dict[str, object] | None = None,
        require_adoption: bool = False,
        fact_ids: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        """Run the checker against temporary files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ir_path = root / "ir.json"
            graph_path = root / "graph.json"
            status_path = root / "status.json"
            ir_path.write_text(json.dumps(sample_ir()), encoding="utf-8")
            graph_path.write_text(json.dumps(graph or sample_graph()), encoding="utf-8")
            if status is not None:
                status_path.write_text(json.dumps(status), encoding="utf-8")
            command = [
                sys.executable,
                str(SCRIPT),
                "--algorithm-ir",
                str(ir_path),
                "--lemma-graph",
                str(graph_path),
                "--target-profile",
                "local_convergence",
                "--equation-tag",
                "step_update",
                "--format",
                "json",
            ]
            if status is not None:
                command.extend(["--proof-status", str(status_path)])
            if require_adoption:
                command.append("--require-proof-status-adoption")
            for fact_id in fact_ids:
                command.extend(["--fact-id", fact_id])
            return subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

    def test_assignment_fact_is_graph_covered_and_adopted(self) -> None:
        """A selected assignment fact should resolve through graph and proof status."""
        result = self.run_tool(status=sample_status(), require_adoption=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["validation"]["valid"])
        self.assertEqual(payload["fact_count"], 1)
        self.assertEqual(payload["graph_node_covered_count"], 1)
        self.assertEqual(payload["consumption_edge_covered_count"], 1)
        self.assertEqual(payload["target_chain_covered_count"], 1)
        self.assertEqual(payload["proof_status_adopted_count"], 1)
        self.assertEqual(payload["facts"][0]["status"], "adopted")
        self.assertEqual(payload["findings"], [])

    def test_missing_fact_node_invalidates_correspondence(self) -> None:
        """A missing code-fact lemma node should fail the checker."""
        result = self.run_tool(graph=sample_graph(include_fact_node=False))

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["validation"]["valid"])
        self.assertEqual(payload["findings"][0]["kind"], "missing_code_fact_lemma_node")

    def test_adoption_is_optional_when_not_required(self) -> None:
        """Graph coverage can be checked before proof-status adoption is complete."""
        result = self.run_tool(status=None, require_adoption=False)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["validation"]["valid"])
        self.assertEqual(payload["proof_status_adopted_count"], 0)
        self.assertEqual(payload["facts"][0]["status"], "graph_covered")

    def test_exact_fact_id_slice_selects_one_equation(self) -> None:
        """A theorem-critical formula can be checked as an exact fact slice."""
        result = self.run_tool(
            status=sample_status(),
            require_adoption=True,
            fact_ids=(FACT_ID,),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["fact_count"], 1)
        self.assertEqual(payload["selected_fact_ids"], [FACT_ID])


if __name__ == "__main__":
    unittest.main()
