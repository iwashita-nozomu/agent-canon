# @dependency-start
# contract test
# responsibility Tests the single full-expansion C++ template source to Lean evidence tool.
# upstream implementation ../../tools/agent_tools/cpp_template_to_lean.py expands C++ roots.
# upstream implementation ../../tools/agent_tools/cpp_source_canonical_ir.py extracts C++ IR.
# upstream implementation ../../tools/agent_tools/operational_ir_to_lean.py renders Lean.
# upstream design ../../documents/tools/cpp_template_to_lean.md documents the canonical route.
# @dependency-end
"""Tests for the C++ template to Lean full-expansion tool."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "cpp_template_to_lean.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the full C++ template to Lean tool."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_algorithm_fixture(root: Path) -> Path:
    """Write a compact C++ template-style algorithm fixture."""
    source = root / "include" / "algorithm.hpp"
    source.parent.mkdir(parents=True)
    source.write_text(
        textwrap.dedent(
            """
            struct Problem {
              int scale;
            };

            struct State {
              int value;
            };

            int kkt_residual(const Problem& problem, State state) {
              auto residual = problem.scale + state.value;
              return residual;
            }

            struct Stepper {
              State step(State state, const Problem& problem) const {
                auto direction = kkt_residual(problem, state);
                State next_state{state.value + direction};
                return next_state;
              }
            };

            State solve(const Stepper& algorithm, State state, const Problem& problem) {
              auto next_state = algorithm.step(state, problem);
              return next_state;
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return source


def write_unresolved_fixture(root: Path) -> Path:
    """Write a C++ root that cannot be fully expanded."""
    source = root / "include" / "unresolved.hpp"
    source.parent.mkdir(parents=True)
    source.write_text(
        textwrap.dedent(
            """
            int solve(int x) {
              auto y = external_call(x);
              return y;
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return source


def test_cpp_template_to_lean_single_step_emits_record_and_lean(tmp_path: Path) -> None:
    """One CLI call should emit both the expanded C++ record and Lean evidence."""
    source = write_algorithm_fixture(tmp_path)
    record = tmp_path / "solve.json"
    out = tmp_path / "SolveGenerated.lean"

    result = run_tool(
        "--root",
        str(tmp_path),
        "--cpp-symbol",
        f"{source}::solve",
        "--namespace",
        "Smoke",
        "--module-name",
        "SolveGenerated",
        "--record-out",
        str(record),
        "--out",
        str(out),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    payload = json.loads(record.read_text(encoding="utf-8"))
    assert payload["schema"] == "agent-canon.cpp-source-canonical-ir.v1"
    operational_ir = payload["operational_ir"]
    assert operational_ir["schema"] == "agent-canon.thin-operational-ir.v2"
    assert operational_ir["coverage"]["unassigned_op_count"] == 0
    assert operational_ir["coverage"]["unresolved_call_targets"] == []
    assert operational_ir["coverage"]["unmapped_code_path_functions"] == []
    assert operational_ir["code_paths"]
    text = out.read_text(encoding="utf-8")
    assert "namespace Smoke" in text
    assert "namespace SolveGenerated" in text
    assert "def publicInterfaceFields : List KeyValue" in text
    assert "def operationalCoverage : OperationalCoverage" in text
    assert "def codePaths : List CodePath" in text
    assert "def codePathCoverageComplete : Bool" in text
    assert "Stepper.step" in text
    assert "kkt_residual" in text


def test_cpp_template_to_lean_stdout_path_is_deterministic(tmp_path: Path) -> None:
    """When --out is omitted, generated Lean should be deterministic stdout."""
    source = write_algorithm_fixture(tmp_path)
    args = [
        "--root",
        str(tmp_path),
        "--cpp-symbol",
        f"{source}::solve",
        "--namespace",
        "Smoke",
    ]

    first = run_tool(*args)
    second = run_tool(*args)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stderr == ""
    assert first.stdout == second.stdout
    assert "namespace Smoke" in first.stdout
    assert "namespace solve_operational_ir" in first.stdout
    assert "return_equation" in first.stdout
    assert "def operationalCoverage : OperationalCoverage" in first.stdout
    assert "def codePaths : List CodePath" in first.stdout


def test_cpp_template_to_lean_rejects_invalid_namespace(tmp_path: Path) -> None:
    """Invalid Lean namespaces should fail before evidence output."""
    source = write_algorithm_fixture(tmp_path)

    result = run_tool(
        "--root",
        str(tmp_path),
        "--cpp-symbol",
        f"{source}::solve",
        "--namespace",
        "bad namespace",
    )

    assert result.returncode != 0
    assert "invalid Lean namespace segment:" in result.stderr
    assert result.stdout == ""


def test_cpp_template_to_lean_rejects_old_two_step_ir_flag(tmp_path: Path) -> None:
    """The canonical C++ route should not accept the old renderer --ir input."""
    source = write_algorithm_fixture(tmp_path)

    result = run_tool(
        "--root",
        str(tmp_path),
        "--cpp-symbol",
        f"{source}::solve",
        "--namespace",
        "Smoke",
        "--ir",
        str(tmp_path / "solve.json"),
    )

    assert result.returncode != 0
    assert "unrecognized arguments: --ir" in result.stderr
    assert result.stdout == ""


def test_cpp_template_to_lean_blocks_incomplete_operational_coverage(
    tmp_path: Path,
) -> None:
    """Unresolved reachable calls should write the repair record but no Lean."""
    source = write_unresolved_fixture(tmp_path)
    record = tmp_path / "unresolved.json"
    out = tmp_path / "Unresolved.lean"

    result = run_tool(
        "--root",
        str(tmp_path),
        "--cpp-symbol",
        f"{source}::solve",
        "--namespace",
        "Smoke",
        "--record-out",
        str(record),
        "--out",
        str(out),
    )

    assert result.returncode != 0
    assert "incomplete operational coverage:" in result.stderr
    assert "external_call" in result.stderr
    assert result.stdout == ""
    assert record.exists()
    assert not out.exists()
