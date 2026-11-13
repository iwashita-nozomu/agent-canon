"""Tests for proof trace code/claim alignment checks."""

# @dependency-start
# contract test
# responsibility Tests proof trace code path and proposition alignment checker.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/check_proof_trace_alignment.rs checks anchors.
# upstream design ../../agents/skills/formal-proof-workflow.md defines trace policy.
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NATIVE_CLI = Path(
    os.environ.get("AGENT_CANON_CLI", PROJECT_ROOT / "tools/bin/agent-canon")
)


class CheckProofTraceAlignmentTest(unittest.TestCase):
    """Validate proof trace alignment findings."""

    def run_checker(
        self, root: Path, trace: Path, *args: str
    ) -> subprocess.CompletedProcess[str]:
        """Run the checker for one fixture trace."""
        return subprocess.run(
            [
                str(NATIVE_CLI),
                "check-proof-trace-alignment",
                "--root",
                str(root),
                "--trace-module",
                str(trace),
                *args,
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_aligned_trace_passes(self) -> None:
        """A retained theorem and matching source anchor should pass."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "src" / "solver.py"
            trace = root / "trace.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                textwrap.dedent(
                    """
                    def solve(value: int) -> int:
                        if value > 0:
                            return value + 1
                        return 1
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            trace.write_text(
                textwrap.dedent(
                    """
                    FORMAL_PROOF_TRACE = {
                        "checked_proof_fragments": [
                            {"name": "solver_positive_step", "status": "checked"},
                        ],
                        "solver_positive_step_contract": {
                            "checked_fragment": "solver_positive_step",
                            "claim": "solve returns the positive-step expression.",
                            "source_path": "src/solver.py",
                            "source_symbol": "solve",
                            "implementation_anchor": {
                                "required_source_tokens": ["return value + 1"],
                                "forbidden_source_tokens": ["return value - 1"],
                                "required_ast_patterns": ["value + 1"],
                                "min_return_count": 2,
                                "min_branch_count": 1,
                                "max_branch_count": 1,
                            },
                        },
                    }
                    """
                ).lstrip(),
                encoding="utf-8",
            )

            result = self.run_checker(root, trace, "--format", "json")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["checked_contract_count"], 1)
            self.assertEqual(payload["checked_anchor_count"], 2)
            self.assertEqual(payload["findings"], [])

    def test_stale_source_token_fails(self) -> None:
        """A stale required token should be reported."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "src" / "solver.py"
            trace = root / "trace.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "def solve(value: int) -> int:\n    return value + 1\n",
                encoding="utf-8",
            )
            trace.write_text(
                textwrap.dedent(
                    """
                    FORMAL_PROOF_TRACE = {
                        "checked_proof_fragments": [
                            {"name": "solver_positive_step", "status": "checked"},
                        ],
                        "solver_positive_step_contract": {
                            "checked_fragment": "solver_positive_step",
                            "claim": "solve returns the positive-step expression.",
                            "implementation_anchor": {
                                "source_path": "src/solver.py",
                                "qualname": "solve",
                                "required_source_tokens": ["return value - 1"],
                            },
                        },
                    }
                    """
                ).lstrip(),
                encoding="utf-8",
            )

            result = self.run_checker(root, trace)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("PROOF_TRACE_ALIGNMENT=fail", result.stdout)
            self.assertIn(
                "missing-required-source-token:return value - 1", result.stdout
            )

    def test_missing_checked_fragment_fails(self) -> None:
        """A contract must refer to a retained checked fragment."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "src" / "solver.py"
            trace = root / "trace.py"
            source.parent.mkdir(parents=True)
            source.write_text("def solve() -> int:\n    return 1\n", encoding="utf-8")
            trace.write_text(
                textwrap.dedent(
                    """
                    FORMAL_PROOF_TRACE = {
                        "checked_proof_fragments": [],
                        "solver_contract": {
                            "checked_fragment": "missing_theorem",
                            "claim": "solve returns one.",
                            "source_path": "src/solver.py",
                            "source_symbol": "solve",
                        },
                    }
                    """
                ).lstrip(),
                encoding="utf-8",
            )

            result = self.run_checker(root, trace)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "checked-fragment-not-retained:missing_theorem",
                result.stdout,
            )

    def test_trace_keeps_mapping_inputs_and_ignores_unrelated_objects(self) -> None:
        """Non-JSON metadata remains valid input to the existing trace contract."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "solver.py"
            source.write_text(
                "def solve(value):\n    return value + 1\n", encoding="utf-8"
            )
            trace = root / "trace.py"
            trace.write_text(
                "from collections import UserDict\n"
                "FORMAL_PROOF_TRACE = UserDict({\n"
                " 'unused': object(),\n"
                " 'step': UserDict({'source_path':'solver.py', 'source_symbol':'solve',\n"
                " 'claim':'A step increments the value.', 'callback':lambda: None,\n"
                " 'implementation_anchor':{'required_ast_patterns':['value + 1']}})})\n",
                encoding="utf-8",
            )
            result = self.run_checker(root, trace, "--format", "json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["findings"], [])

    def test_ast_pattern_and_shape_limits_keep_independent_failures(self) -> None:
        """Each failed source property produces its original finding category."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "solver.py"
            source.write_text(
                "def solve(value):\n    if value:\n        return 1\n    return 0\n",
                encoding="utf-8",
            )
            trace = root / "trace.py"
            trace.write_text(
                "FORMAL_PROOF_TRACE = {'step': {'source_path':'solver.py',\n"
                " 'source_symbol':'solve', 'claim':'The function has a conditional.',\n"
                " 'implementation_anchor': {'required_ast_patterns':['abs(value)'],\n"
                " 'min_return_count':3, 'max_branch_count':0}}}\n",
                encoding="utf-8",
            )
            result = self.run_checker(root, trace, "--format", "json")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(
                {item["kind"] for item in json.loads(result.stdout)["findings"]},
                {
                    "missing-required-ast-pattern",
                    "return-count-below-minimum",
                    "branch-count-above-maximum",
                },
            )

    def test_large_python_integer_limit_is_preserved(self) -> None:
        """The external Python integer contract keeps arbitrary precision."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "solver.py").write_text(
                "def solve():\n    return 1\n", encoding="utf-8"
            )
            trace = root / "trace.py"
            trace.write_text(
                "FORMAL_PROOF_TRACE = {'step': {'source_path':'solver.py',\n"
                " 'source_symbol':'solve', 'claim':'Returns one.',\n"
                " 'implementation_anchor': {'min_return_count':2**300}}}\n",
                encoding="utf-8",
            )
            result = self.run_checker(root, trace, "--format", "json")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                f"1<{2**300}",
                [item["detail"] for item in json.loads(result.stdout)["findings"]],
            )


if __name__ == "__main__":
    unittest.main()
