"""Tests for proof path overlay analysis."""

# @dependency-start
# responsibility Tests proof_path_analyzer proof-status overlay checks.
# upstream implementation ../../tools/agent_tools/proof_path_analyzer.py analyzes proof paths.
# upstream implementation ../../tools/agent_tools/algorithm_lemma_graph.py emits lemma graphs.
# upstream design ../../agents/skills/formal-proof-workflow.md defines proof graph workflow.
# downstream design ../../documents/tools/proof_path_analyzer.md documents CLI usage.
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "proof_path_analyzer.py"


def sample_graph() -> dict[str, object]:
    """Return a compact lemma graph payload."""
    return {
        "status": "lemma_graph_built",
        "source_ir_fingerprint": "sample-ir-fingerprint",
        "root": "python/app.py::_solve",
        "theorem": "local_convergence",
        "target_profiles": ["local_convergence"],
        "lemma_nodes": [
            {
                "lemma_id": "target__local_convergence__local_convergence",
                "label": "target",
                "statement": "target theorem",
                "lemma_kind": "target_theorem",
                "proof_status": "unverified",
                "source_symbols": ["_solve"],
                "source_paths": ["python/app.py"],
                "remaining_gap": "prove target",
            },
            {
                "lemma_id": "lemma__step",
                "label": "_step",
                "statement": "prove step",
                "lemma_kind": "local_obligation",
                "proof_status": "unverified",
                "source_symbols": ["_step"],
                "source_paths": ["python/app.py"],
                "remaining_gap": "formal theorem required",
            },
            {
                "lemma_id": "lemma__backend",
                "label": "backend_profile",
                "statement": "assume backend",
                "lemma_kind": "assumption",
                "proof_status": "assumption",
                "source_symbols": ["backend_profile"],
                "source_paths": ["lean/lib/backend_profiles.json"],
                "remaining_gap": "backend witness",
            },
        ],
        "lemma_edges": [
            {
                "edge_id": "edge-1",
                "source_lemma_id": "target__local_convergence__local_convergence",
                "target_lemma_id": "lemma__step",
                "edge_kind": "target_requires",
                "status": "valid",
            },
            {
                "edge_id": "edge-2",
                "source_lemma_id": "lemma__step",
                "target_lemma_id": "lemma__backend",
                "edge_kind": "backend_profile_dependency",
                "status": "valid",
            },
        ],
        "target_chains": [
            {
                "target_id": "target__local_convergence__local_convergence",
                "profile": "local_convergence",
                "theorem": "local_convergence",
                "lemma_ids": ["lemma__step", "lemma__backend"],
                "reachable_lemma_ids": ["lemma__step", "lemma__backend"],
                "missing_lemma_ids": [],
                "connected": True,
            }
        ],
    }


def sample_status() -> dict[str, object]:
    """Return a compact proof status payload."""
    return {
        "checked_fragments": [
            {
                "theorem": "Proof.step_handoff",
                "status": "verified",
                "checker": "Lean 4",
                "command": "lean Step.lean",
                "file": "Step.lean",
                "remaining_obligation": "instantiate local step",
                "implementation_surface": "python/app.py::_step",
            }
        ],
        "unprovable_under_assumptions": [],
        "open_frontier": [
            {
                "frontier": "B1 step bridge",
                "code_derived_facts": [
                    {
                        "derivability": "ir_or_lemma_graph",
                        "fact_id": "B1-F1",
                        "gap_owner": "none",
                        "proof_effect": "step obligation is selected by the graph",
                        "source_id": "lemma__step",
                        "source_kind": "lemma_node",
                        "statement": "The step lemma is selected in the lemma graph.",
                    }
                ],
                "implementation_surface": "python/app.py::_step",
                "next_witness": "local bridge witness",
                "status": "unverified_with_next_witness",
            }
        ],
        "schema": "test-proof-status",
        "source_ir_fingerprints": ["sample-ir-fingerprint"],
    }


class ProofPathAnalyzerTest(unittest.TestCase):
    """Validate proof path analyzer integrity checks."""

    def run_tool(
        self,
        graph: dict[str, object],
        status: dict[str, object],
        adoption_text: str = "Proof.step_handoff\n",
        frontier_text: str = "| B1 step bridge | unverified_with_next_witness |\n",
    ) -> subprocess.CompletedProcess[str]:
        """Run proof path analyzer with temporary inputs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph_path = root / "graph.json"
            status_path = root / "status.json"
            adoption_path = root / "adoption.md"
            frontier_path = root / "frontier.md"
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            status_path.write_text(json.dumps(status), encoding="utf-8")
            adoption_path.write_text(adoption_text, encoding="utf-8")
            frontier_path.write_text(frontier_text, encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--lemma-graph",
                    str(graph_path),
                    "--proof-status",
                    str(status_path),
                    "--proof-frontier",
                    str(frontier_path),
                    "--adoption-text",
                    str(adoption_path),
                    "--format",
                    "json",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

    def test_connected_path_is_valid_but_not_complete_with_open_witness(self) -> None:
        """Current proof holes should stay connected without pretending completeness."""
        result = self.run_tool(sample_graph(), sample_status())

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["validation"]["valid"])
        self.assertTrue(payload["validation"]["connected"])
        self.assertTrue(payload["validation"]["algorithm_fingerprint_valid"])
        self.assertTrue(payload["fingerprint_valid"])
        self.assertFalse(payload["proof_complete"])
        self.assertTrue(payload["frontier_minimal"])
        self.assertEqual(payload["open_witness_count"], 1)
        self.assertEqual(payload["operational_assumption_count"], 0)
        self.assertEqual(payload["external_assumption_count"], 0)
        self.assertEqual(payload["code_fact_count"], 1)
        self.assertEqual(payload["code_fact_derivability_counts"], {"ir_or_lemma_graph": 1})
        self.assertEqual(payload["open_witnesses_without_code_facts"], [])
        self.assertEqual(payload["open_witnesses"][0]["hole_id"], "B1 step bridge")
        self.assertEqual(payload["open_witnesses"][0]["next_witness"], "local bridge witness")
        self.assertEqual(payload["frontier_minimality"][0]["hole_id"], "B1 step bridge")
        self.assertTrue(payload["frontier_minimality"][0]["minimal"])
        self.assertEqual(payload["findings"], [])

    def test_terminal_frontier_unprovable_is_not_an_open_witness(self) -> None:
        """Explored frontier rows may end as assumption-insufficient outcomes."""
        status = sample_status()
        status["open_frontier"][0]["status"] = "unprovable_under_assumptions"  # type: ignore[index]
        status["open_frontier"][0]["next_witness"] = "missing local bridge witness"  # type: ignore[index]

        result = self.run_tool(
            sample_graph(),
            status,
            frontier_text="| B1 step bridge | unprovable_under_assumptions |\n",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["validation"]["valid"])
        self.assertFalse(payload["proof_complete"])
        self.assertEqual(payload["open_witness_count"], 0)
        self.assertEqual(payload["unprovable_count"], 1)
        self.assertEqual(payload["code_fact_count"], 1)
        self.assertEqual(
            payload["unprovable_under_assumptions"][0]["hole_id"],
            "B1 step bridge",
        )
        self.assertEqual(
            payload["unprovable_under_assumptions"][0]["missing_assumption"],
            "missing local bridge witness",
        )

    def test_missing_node_fails_validation(self) -> None:
        """Edges referencing removed nodes should be reported."""
        graph = sample_graph()
        graph["lemma_nodes"] = [  # type: ignore[index]
            node
            for node in graph["lemma_nodes"]  # type: ignore[index]
            if node["lemma_id"] != "lemma__step"
        ]

        result = self.run_tool(graph, sample_status())

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertIn("lemma__step", payload["graph_connectivity"][0]["missing_node_ids"])
        self.assertFalse(payload["validation"]["valid"])

    def test_missing_target_edge_fails_connectivity(self) -> None:
        """Removing a target edge should disconnect the target chain."""
        graph = sample_graph()
        graph["lemma_edges"] = [  # type: ignore[index]
            edge
            for edge in graph["lemma_edges"]  # type: ignore[index]
            if edge["edge_id"] != "edge-1"
        ]

        result = self.run_tool(graph, sample_status())

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertIn(
            "target__local_convergence__local_convergence",
            payload["graph_connectivity"][0]["disconnected_target_ids"],
        )
        self.assertIn("lemma__step", payload["graph_connectivity"][0]["missing_lemma_ids"])

    def test_bare_unverified_frontier_fails(self) -> None:
        """Frontier rows must name their next witness."""
        status = sample_status()
        status["open_frontier"][0]["status"] = "unverified"  # type: ignore[index]

        result = self.run_tool(status=status, graph=sample_graph())

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["bare_unverified_frontier_count"], 1)

    def test_unadopted_verified_fragment_fails(self) -> None:
        """A checked fragment must appear in adoption text."""
        result = self.run_tool(sample_graph(), sample_status(), adoption_text="")

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["unadopted_verified_fragment_count"], 1)
        self.assertEqual(
            payload["findings"][0]["kind"],
            "unadopted_verified_fragment",
        )

    def test_stale_implementation_token_fails(self) -> None:
        """Implementation surfaces must match graph tokens or real files."""
        status = sample_status()
        status["checked_fragments"][0]["implementation_surface"] = (  # type: ignore[index]
            "python/app.py::_bogus_token"
        )

        result = self.run_tool(sample_graph(), status)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertIn("python/app.py::_bogus_token", payload["stale_implementation_tokens"])

    def test_external_assumption_is_reported_without_opening_witness(self) -> None:
        """Trusted external boundaries should stay visible without blocking the proof frontier."""
        status = sample_status()
        status["external_assumptions"] = [
            {
                "code_derived_facts": [
                    {
                        "derivability": "external_backend_assumption",
                        "fact_id": "B5-F1",
                        "gap_owner": "lean_lib_backend_source_packet",
                        "proof_effect": "backend packet is adopted as an external assumption",
                        "source_id": "lean/lib/backend_fp32_evidence.json",
                        "source_kind": "backend_evidence_source_packet",
                        "statement": "The backend FP32 evidence packet is retained in lean/lib.",
                    }
                ],
                "frontier": "B5 backend axiom",
                "implementation_surface": "lean/lib/backend_profiles.json",
                "next_witness": "external IREE-FP32 backend axiom",
                "status": "external_assumption",
            }
        ]

        result = self.run_tool(sample_graph(), status)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["open_witness_count"], 1)
        self.assertEqual(payload["external_assumption_count"], 1)
        self.assertEqual(payload["code_fact_count"], 2)
        self.assertEqual(
            payload["code_fact_derivability_counts"],
            {"external_backend_assumption": 1, "ir_or_lemma_graph": 1},
        )
        self.assertEqual(payload["external_assumptions"][0]["hole_id"], "B5 backend axiom")
        self.assertEqual(
            payload["external_assumptions"][0]["next_witness"],
            "external IREE-FP32 backend axiom",
        )

    def test_stale_algorithm_fingerprint_fails(self) -> None:
        """Proof-status overlays must match the algorithm IR fingerprint."""
        status = sample_status()
        status["source_ir_fingerprints"] = ["old-ir-fingerprint"]

        result = self.run_tool(sample_graph(), status)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["fingerprint_valid"])
        self.assertIn(
            "stale_algorithm_lemma_group",
            {finding["kind"] for finding in payload["findings"]},
        )

    def test_operational_assumption_is_reported_without_opening_witness(self) -> None:
        """Implemented algorithm trace assumptions should not masquerade as convergence claims."""
        status = sample_status()
        status["operational_assumptions"] = [
            {
                "frontier": "A0 implemented trace",
                "implementation_surface": "python/app.py::_solve",
                "next_witness": "trace follows extracted Step_impl; convergence is derived separately",
                "status": "operational_assumption",
            }
        ]

        result = self.run_tool(sample_graph(), status)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["open_witness_count"], 1)
        self.assertEqual(payload["operational_assumption_count"], 1)
        self.assertEqual(payload["operational_assumptions"][0]["hole_id"], "A0 implemented trace")
        self.assertEqual(
            payload["operational_assumptions"][0]["next_witness"],
            "trace follows extracted Step_impl; convergence is derived separately",
        )

    def test_backend_generated_name_does_not_create_suffix_token(self) -> None:
        """Underscore suffixes inside prose names should not become implementation tokens."""
        status = sample_status()
        status["open_frontier"][0]["implementation_surface"] = (  # type: ignore[index]
            "lean/lib/backend_profiles.json and generated backend_assumptions"
        )

        result = self.run_tool(sample_graph(), status)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertNotIn("_assumptions", payload["stale_implementation_tokens"])

    def test_duplicate_frontier_label_fails(self) -> None:
        """A B-label should identify only one frontier obligation."""
        frontier_text = (
            "| B1 step bridge | unverified_with_next_witness |\n"
            "| B1 different bridge | unverified_with_next_witness |\n"
        )

        result = self.run_tool(sample_graph(), sample_status(), frontier_text=frontier_text)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["duplicate_frontier_labels"], ["B1"])

    def test_cross_source_frontier_label_shortening_is_valid(self) -> None:
        """Different files may shorten a B-label name without creating a collision."""
        frontier_text = "| B1 step | unverified_with_next_witness |\n"

        result = self.run_tool(sample_graph(), sample_status(), frontier_text=frontier_text)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["duplicate_frontier_labels"], [])

    def test_adoption_text_frontier_references_do_not_define_labels(self) -> None:
        """Adoption notes may discuss a label without redefining frontier identity."""
        adoption_text = (
            "Proof.step_handoff\n"
            "| B1 different explanatory wording | implementation note |\n"
        )

        result = self.run_tool(sample_graph(), sample_status(), adoption_text=adoption_text)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["duplicate_frontier_labels"], [])

    def test_ir_backed_code_fact_source_must_exist(self) -> None:
        """IR-backed code facts must point at graph or IR text evidence."""
        status = sample_status()
        status["open_frontier"][0]["code_derived_facts"][0]["source_id"] = "missing_lemma"  # type: ignore[index]

        result = self.run_tool(sample_graph(), status)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertIn(
            "invalid_code_derived_fact",
            {finding["kind"] for finding in payload["findings"]},
        )

    def test_nonminimal_frontier_blocker_fails(self) -> None:
        """A returned blocker must not hide a smaller open target-chain node."""
        status = sample_status()
        status["open_frontier"].append(  # type: ignore[union-attr]
            {
                "frontier": "B2 backend bridge",
                "code_derived_facts": [
                    {
                        "derivability": "ir_or_lemma_graph",
                        "fact_id": "B2-F1",
                        "gap_owner": "none",
                        "proof_effect": "backend obligation is below the step bridge",
                        "source_id": "lemma__backend",
                        "source_kind": "lemma_node",
                        "statement": "The backend lemma is selected in the lemma graph.",
                    }
                ],
                "implementation_surface": "lean/lib/backend_profiles.json",
                "next_witness": "backend witness",
                "status": "unverified_with_next_witness",
            }
        )

        result = self.run_tool(sample_graph(), status)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["frontier_minimal"])
        self.assertFalse(payload["frontier_minimality"][0]["minimal"])
        self.assertEqual(payload["findings"][0]["kind"], "nonminimal_frontier_blocker")


if __name__ == "__main__":
    unittest.main()
