"""Tests for proof trace code/claim alignment checks."""

# @dependency-start
# contract test
# responsibility Tests proof trace code path and proposition alignment checker.
# upstream implementation ../../tools/agent_tools/check_proof_trace_alignment.py checks anchors.
# upstream design ../../agents/skills/formal-proof-workflow.md defines trace policy.
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
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "check_proof_trace_alignment.py"


class CheckProofTraceAlignmentTest(unittest.TestCase):
    """Validate proof trace alignment findings."""

    def run_checker(self, root: Path, trace: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker for one fixture trace."""
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
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
            self.assertIn("missing-required-source-token:return value - 1", result.stdout)

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


if __name__ == "__main__":
    unittest.main()
