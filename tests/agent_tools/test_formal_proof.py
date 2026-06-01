"""Tests for formal proof scaffold generation."""

# @dependency-start
# responsibility Tests natural-language to formal-proof scaffold planning.
# upstream implementation ../../tools/agent_tools/formal_proof.py builds proof scaffold artifacts.
# upstream design ../../agents/skills/formal-proof-workflow.md defines proof workflow requirements.
# downstream design ../../documents/tools/formal_proof.md documents the CLI contract.
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "formal_proof.py"


class FormalProofToolTest(unittest.TestCase):
    """Validate scaffold output and proof-status boundaries."""

    def test_writes_lean_scaffold_and_search_queries(self) -> None:
        """Lean scaffold should be clearly unverified and query existing proofs."""
        claim = "\n".join(
            [
                "Assumptions: A is a symmetric positive definite matrix.",
                "Claim: x^T A x is positive for every nonzero vector x.",
                "Proof sketch: Use the definition of positive definiteness.",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            claim_path = Path(tmp_dir) / "claim.md"
            out_dir = Path(tmp_dir) / "proof"
            claim_path.write_text(claim, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--claim-file",
                    str(claim_path),
                    "--target",
                    "lean",
                    "--domain",
                    "linear algebra",
                    "--name",
                    "spd_quadratic_form_positive",
                    "--out-dir",
                    str(out_dir),
                    "--format",
                    "json",
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "scaffold_only_unverified")
            self.assertEqual(payload["target"], "lean")
            self.assertIn(
                "Search existing formal libraries",
                "\n".join(payload["proof_obligations"]),
            )
            self.assertTrue(
                any("LeanSearch" in query for query in payload["existing_proof_queries"])
            )
            self.assertTrue(
                any("formalization" in query for query in payload["literature_queries"])
            )
            self.assertEqual(
                payload["theorem_stub_path"],
                str(out_dir / "spd_quadratic_form_positive.lean"),
            )

            stub = (out_dir / "spd_quadratic_form_positive.lean").read_text(encoding="utf-8")
            self.assertIn("<FORMAL_TARGET>", stub)
            self.assertIn("sorry", stub)
            self.assertIn("not proof evidence", stub)
            self.assertTrue((out_dir / "formal_proof_plan.md").is_file())
            self.assertTrue((out_dir / "existing_proof_queries.txt").is_file())

    def test_text_output_for_smt_includes_solver_commands(self) -> None:
        """SMT target should expose SMT solver verification commands."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--claim",
                "Claim: every integer greater than two is prime.",
                "--target",
                "smt",
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("FORMAL_PROOF_STATUS=scaffold_only_unverified", result.stdout)
        self.assertIn("FORMAL_PROOF_VERIFY=z3 -smt2", result.stdout)
        self.assertIn("counterexample assumptions", result.stdout)


if __name__ == "__main__":
    unittest.main()
