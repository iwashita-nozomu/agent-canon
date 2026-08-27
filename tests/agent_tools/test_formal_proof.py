"""Tests for formal proof scaffold generation."""

# @dependency-start
# contract test
# responsibility Tests natural-language to formal-proof scaffold planning.
# upstream implementation ../../tools/agent_tools/formal_proof.py builds proof scaffold artifacts.
# upstream design ../../agents/skills/formal-proof-workflow.md defines proof workflow requirements.
# upstream design ../../documents/tools/formal_proof.md documents the CLI contract.
# @dependency-end

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "formal_proof.py"
PRODUCER_TEST = PROJECT_ROOT / "tests" / "agent_tools" / "test_jit_canonical_ir.py"


def _load_proof_tool_handoff() -> tuple[
    dict[str, object], frozenset[str], frozenset[str]
]:
    """Load the producer fixture and its canonical field sets."""
    namespace = runpy.run_path(str(PRODUCER_TEST))
    return (
        cast(dict[str, object], namespace["PROOF_TOOL_HANDOFF_FIXTURE"]),
        cast(frozenset[str], namespace["PROOF_TOOL_HANDOFF_TOP_LEVEL_FIELDS"]),
        cast(frozenset[str], namespace["PROOF_TOOL_HANDOFF_ROLE_FIELDS"]),
    )


class FormalProofToolTest(unittest.TestCase):
    """Validate scaffold output and proof-status boundaries."""

    def test_ir_failure_fixture_does_not_authorize_math_or_jit_drift(self) -> None:
        """An IR failure routes tooling without authorizing unrelated math edits."""
        handoff, expected_top_level, expected_role = _load_proof_tool_handoff()
        mathematical_evidence = cast(dict[str, object], handoff["mathematical_evidence"])
        failure = cast(dict[str, object], handoff["failure"])
        math_writer = cast(dict[str, object], handoff["math_writer"])
        proof_tool_worker = cast(dict[str, object], handoff["proof_tool_worker"])
        self.assertEqual(set(handoff), expected_top_level)
        self.assertEqual(set(math_writer), expected_role)
        self.assertEqual(set(proof_tool_worker), expected_role)
        math_allowed = set(cast(list[str], math_writer["allowed_paths"]))
        math_forbidden = set(cast(list[str], math_writer["forbidden_paths"]))
        proof_allowed = set(cast(list[str], proof_tool_worker["allowed_paths"]))
        proof_forbidden = set(cast(list[str], proof_tool_worker["forbidden_paths"]))

        self.assertEqual(failure["kind"], "ir_extractor_or_lowering")
        self.assertEqual(mathematical_evidence["status"], "absent")
        self.assertEqual(handoff["return_status"], "route_infrastructure")
        self.assertEqual(math_writer["owner"], "algorithm-proof-exploration")
        self.assertEqual(
            math_writer["evidence"],
            {"status": "absent", "paths": []},
        )
        self.assertEqual(
            proof_tool_worker["owner"],
            "IR extractor and generated-proof mechanism owner",
        )
        self.assertEqual(
            proof_tool_worker["evidence"],
            {
                "status": "awaiting_native_receipt",
                "paths": [
                    "tools/agent_tools/jit_canonical_ir.py",
                    "generated Lean return projection",
                ],
            },
        )
        self.assertTrue({"tools/agent_tools/jit_canonical_ir.py", "lean/"} <= math_forbidden)
        self.assertTrue({"production algorithm and public API"} <= proof_forbidden)
        self.assertTrue(proof_allowed.isdisjoint(math_allowed))
        self.assertEqual(
            failure["producer_surface"],
            "tools/agent_tools/jit_canonical_ir.py",
        )

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
            runtime_dir = Path(tmp_dir) / "runtime"
            out_dir = runtime_dir / "tasks" / "formal-proof" / "spd"
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
                    "--runtime-root",
                    str(runtime_dir),
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
            self.assertIn(
                "package-retained proof trace",
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
            self.assertIn("import Aesop", stub)
            self.assertIn("<FORMAL_TARGET>", stub)
            self.assertIn("sorry", stub)
            self.assertIn("not proof evidence", stub)
            self.assertTrue((out_dir / "formal_proof_plan.md").is_file())
            self.assertTrue((out_dir / "existing_proof_queries.txt").is_file())
            trace_path = out_dir / "spd_quadratic_form_positive_proof_trace.py"
            self.assertTrue(trace_path.is_file())
            trace_globals = runpy.run_path(str(trace_path))
            trace = cast(dict[str, object], trace_globals["FORMAL_PROOF_TRACE"])
            self.assertEqual(
                trace["status"],
                "scaffold_only_unverified",
            )
            self.assertEqual(
                trace["theorem_stub_path"],
                str(out_dir / "spd_quadratic_form_positive.lean"),
            )
            self.assertEqual(
                trace["library_trace_module_path"],
                str(trace_path),
            )
            self.assertEqual(
                trace["origin_library_trace_module_path"],
                str(trace_path),
            )
            self.assertEqual(
                trace["library_trace_module_name"],
                "spd_quadratic_form_positive_proof_trace.py",
            )
            self.assertEqual(
                trace["runtime_theorem_stub_candidate_path"],
                str(out_dir / "spd_quadratic_form_positive.lean"),
            )
            self.assertIn("origin_*", str(trace["trace_path_semantics"]))

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

    def test_python_symbol_writes_ast_sourced_scaffold_without_importing(self) -> None:
        """Python AST source should parse symbols without executing module side effects."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sample = root / "sample.py"
            sentinel = root / "side_effect.txt"
            runtime_dir = root / "runtime"
            out_dir = runtime_dir / "tasks" / "formal-proof" / "python-ast"
            sample.write_text(
                "\n".join(
                    [
                        f"open({str(sentinel)!r}, 'w').write('imported')",
                        "",
                        "def lemma(x: int) -> int:",
                        '    """Claim: lemma returns x + 1 for integer x."""',
                        "    if x > 0:",
                        "        return x + 1",
                        "    return 1",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--python-symbol",
                    f"{sample}::lemma",
                    "--target",
                    "lean",
                    "--out-dir",
                    str(out_dir),
                    "--runtime-root",
                    str(runtime_dir),
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
            self.assertEqual(payload["source_kind"], "python_ast")
            self.assertEqual(payload["source_symbol"], "lemma")
            self.assertIn("def lemma(x: int) -> int", payload["source_summary"])
            self.assertIn("x + 1", "\n".join(payload["proof_obligations"]))
            self.assertIn("Branch nodes: 1", payload["claim_text"])
            self.assertFalse(sentinel.exists())
            self.assertTrue((out_dir / "lemma.lean").is_file())
            self.assertEqual(
                payload["library_trace_module_path"],
                str(out_dir / "lemma_proof_trace.py"),
            )
            self.assertEqual(payload["library_trace_module_name"], "lemma_proof_trace.py")
            self.assertEqual(
                payload["origin_library_trace_module_path"],
                str(out_dir / "lemma_proof_trace.py"),
            )

    def test_python_symbol_supports_nested_qualname_default_name(self) -> None:
        """Dotted class/function qualnames should resolve through AST bodies."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "sample.py"
            sample.write_text(
                "\n".join(
                    [
                        "class Container:",
                        "    def lemma(self, value: int) -> int:",
                        '        """Claim: nested lemma preserves value."""',
                        "        return value",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--python-symbol",
                    f"{sample}::Container.lemma",
                    "--format",
                    "json",
                    "--out-dir",
                    str(Path(tmp_dir) / "runtime" / "tasks" / "formal-proof" / "nested"),
                    "--runtime-root",
                    str(Path(tmp_dir) / "runtime"),
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["source_symbol"], "Container.lemma")
            self.assertTrue(payload["theorem_stub_path"].endswith("container_lemma.lean"))
            self.assertIn("nested lemma preserves value", payload["claim_text"])

    def test_python_symbol_errors_do_not_fall_back_to_claim_route(self) -> None:
        """Invalid Python symbol references should fail before scaffold output."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--python-symbol",
                "missing_separator",
                "--format",
                "json",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("path.py::qualname", result.stderr)
        self.assertNotIn("scaffold_only_unverified", result.stdout)

    def test_python_symbol_qualname_not_found_fails(self) -> None:
        """Missing AST symbols should be reported as source errors."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "sample.py"
            sample.write_text("def available() -> int:\n    return 1\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--python-symbol",
                    f"{sample}::missing",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Python AST symbol not found", result.stderr)

    def test_output_requires_explicit_external_runtime_root(self) -> None:
        """A write request fails closed instead of creating source-local output."""
        source_output = PROJECT_ROOT / "reports" / f"formal-proof-forbidden-{os.getpid()}"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--claim",
                "Claim: one equals one.",
                "--out-dir",
                str(source_output),
            ],
            cwd=PROJECT_ROOT,
            env={**dict(os.environ), "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("runtime_root_error", result.stderr)
        self.assertFalse(source_output.exists())

    def test_output_root_cannot_be_inside_source_checkout(self) -> None:
        """An explicit runtime root still cannot redirect output into source."""
        with tempfile.TemporaryDirectory() as runtime_tmp:
            source_output = PROJECT_ROOT / "reports" / f"formal-proof-forbidden-{os.getpid()}"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--claim",
                    "Claim: one equals one.",
                    "--runtime-root",
                    runtime_tmp,
                    "--out-dir",
                    str(source_output),
                ],
                cwd=PROJECT_ROOT,
                env={**dict(os.environ), "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("runtime_root_error", result.stderr)
        self.assertFalse(source_output.exists())


if __name__ == "__main__":
    unittest.main()
