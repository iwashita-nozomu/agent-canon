# @dependency-start
# contract test
# responsibility Tests C++ source-canonical IR extraction into the shared thin operational IR.
# upstream implementation ../../tools/agent_tools/cpp_source_canonical_ir.py extracts C++ source IR.
# upstream design ../../documents/tools/cpp_source_canonical_ir.md documents the wrapper schema.
# upstream implementation ../../tools/agent_tools/jit_canonical_ir.py defines the inner IR shape.
# @dependency-end
"""Tests for C++ source-canonical IR extraction."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "cpp_source_canonical_ir.py"


def run_tool(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the C++ source-canonical IR tool against one fixture root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_algorithm_fixture(root: Path) -> Path:
    """Write a compact C++ algorithm fixture."""
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

            struct Info {
              bool converged;
            };

            int kkt_residual(const Problem& problem, State state) {
              auto residual = problem.scale + state.value;
              return residual;
            }

            State apply_step(State state, int direction) {
              State next_state{state.value + direction};
              return next_state;
            }

            struct Stepper {
              State step(State state, const Problem& problem) const {
                auto direction = solve_direction(problem, state);
                return apply_step(state, direction);
              }

              int solve_direction(const Problem& problem, State state) const {
                return kkt_residual(problem, state);
              }
            };

            State solve_from_constructor(State state, const Problem& problem) {
              Stepper stepper{};
              return stepper.step(state, problem);
            }

            State solve(const Stepper& algorithm, State state, const Problem& problem) {
              auto next_state = algorithm.step(state, problem);
              Info info{true};
              return next_state;
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return source


def load_json_result(result: subprocess.CompletedProcess[str]):
    """Assert a successful tool result and parse JSON."""
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_cpp_source_canonical_ir_emits_source_wrapper_and_thin_ir(tmp_path: Path) -> None:
    """C++ source should join the shared thin operational IR without JIT fields."""
    source = write_algorithm_fixture(tmp_path)

    payload = load_json_result(
        run_tool(tmp_path, "--cpp-symbol", f"{source}::solve", "--format", "json")
    )

    assert payload["schema"] == "agent-canon.cpp-source-canonical-ir.v1"
    assert "stablehlo" not in payload
    assert "backend_trace" not in payload
    assert payload["source_root"]["schema"] == "agent-canon.cpp-source-root.v1"
    assert payload["source_root"]["relative_path"] == "include/algorithm.hpp"
    assert payload["public_interface"]["schema"] == "agent-canon.cpp-public-interface.v1"
    assert payload["public_interface"]["coverage"]["parameter_count"] == 3
    assert payload["public_interface"]["coverage"]["stablehlo_specific_fields"] == 0
    operational_ir = payload["operational_ir"]
    assert operational_ir["schema"] == "agent-canon.thin-operational-ir.v2"
    assert operational_ir["coverage"]["function_count"] >= 4
    assert operational_ir["coverage"]["call_count"] >= 3
    assert operational_ir["coverage"]["unassigned_op_count"] == 0
    assert all(op["region_id"] for op in operational_ir["ops"])


def test_cpp_source_canonical_ir_resolves_instance_method_from_parameter(
    tmp_path: Path,
) -> None:
    """A typed method parameter should resolve an instance method call."""
    source = write_algorithm_fixture(tmp_path)

    payload = load_json_result(
        run_tool(tmp_path, "--cpp-symbol", f"{source}::solve", "--format", "json")
    )

    call_ops = [
        op for op in payload["operational_ir"]["ops"] if op.get("opcode") == "cxx.call"
    ]
    assert any(
        op["edge_kind"] == "method_call"
        and op["receiver_name"] == "algorithm"
        and op["receiver_type"] == "Stepper"
        and op["target_symbol"] == "Stepper.step"
        and op["resolved"] is True
        for op in call_ops
    )
    edge_targets = {edge["to"] for edge in payload["operational_ir"]["expansion_edges"]}
    assert "function:Stepper.step" in edge_targets
    function_names = {function["name"] for function in payload["operational_ir"]["functions"]}
    assert {"solve", "Stepper.step", "Stepper.solve_direction", "kkt_residual"}.issubset(
        function_names
    )


def test_cpp_source_canonical_ir_resolves_instance_method_from_constructor(
    tmp_path: Path,
) -> None:
    """A local C++ object initializer should type later instance method calls."""
    source = write_algorithm_fixture(tmp_path)

    payload = load_json_result(
        run_tool(
            tmp_path,
            "--cpp-symbol",
            f"{source}::solve_from_constructor",
            "--format",
            "json",
        )
    )

    call_ops = [
        op for op in payload["operational_ir"]["ops"] if op.get("opcode") == "cxx.call"
    ]
    assert any(
        op["edge_kind"] == "method_call"
        and op["receiver_name"] == "stepper"
        and op["receiver_type"] == "Stepper"
        and op["target_symbol"] == "Stepper.step"
        and op["resolved"] is True
        for op in call_ops
    )


def test_cpp_source_canonical_ir_keeps_records_out_of_function_rows(
    tmp_path: Path,
) -> None:
    """Constructor records should not become operational function rows."""
    source = write_algorithm_fixture(tmp_path)

    payload = load_json_result(
        run_tool(tmp_path, "--cpp-symbol", f"{source}::solve", "--format", "json")
    )

    function_names = {function["name"] for function in payload["operational_ir"]["functions"]}
    assert "Stepper" not in function_names
    assert "State" not in function_names
    assert "Info" not in function_names
    edge_targets = {edge["to"] for edge in payload["operational_ir"]["expansion_edges"]}
    assert "function:Stepper" not in edge_targets
    assert "function:State" not in edge_targets
    assert "function:Info" not in edge_targets
    construct_ops = [
        op
        for op in payload["operational_ir"]["ops"]
        if op.get("edge_kind") == "constructs"
    ]
    assert construct_ops
    assert all(op["kind"] == "Primitive" for op in construct_ops)


def test_cpp_source_canonical_ir_collects_assignment_and_return_facts(
    tmp_path: Path,
) -> None:
    """The C++ wrapper should preserve shallow assignment and return equations."""
    source = write_algorithm_fixture(tmp_path)

    payload = load_json_result(
        run_tool(tmp_path, "--cpp-symbol", f"{source}::solve", "--format", "json")
    )

    facts = payload["source_facts"]["facts"]
    assert any(
        fact["fact_kind"] == "assignment_equation"
        and fact["source_symbol"] == "solve"
        and fact["target"] == "next_state"
        for fact in facts
    )
    assert any(
        fact["fact_kind"] == "return_equation"
        and fact["source_symbol"] == "solve"
        and fact["target"] == "return"
        for fact in facts
    )
    assert payload["source_facts"]["coverage"]["fact_count"] >= 5


def test_cpp_source_canonical_ir_resolves_same_namespace_direct_call(
    tmp_path: Path,
) -> None:
    """A direct leaf call inside a namespace should resolve to that namespace."""
    source = tmp_path / "include" / "namespaced.hpp"
    source.parent.mkdir(parents=True)
    source.write_text(
        textwrap.dedent(
            """
            namespace detail {
            int residual(int x) {
              return x;
            }

            int solve(int x) {
              auto value = residual(x);
              return value;
            }
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )

    payload = load_json_result(
        run_tool(tmp_path, "--cpp-symbol", f"{source}::detail::solve", "--format", "json")
    )

    function_names = {function["name"] for function in payload["operational_ir"]["functions"]}
    assert {"detail.solve", "detail.residual"}.issubset(function_names)
    edge_targets = {edge["to"] for edge in payload["operational_ir"]["expansion_edges"]}
    assert "function:detail.residual" in edge_targets


def test_cpp_source_canonical_ir_deduplicates_call_target_edges(tmp_path: Path) -> None:
    """Multiple calls to one callee should not duplicate expansion edges."""
    source = tmp_path / "include" / "repeated.hpp"
    source.parent.mkdir(parents=True)
    source.write_text(
        textwrap.dedent(
            """
            int residual(int x) {
              return x;
            }

            int solve(int x) {
              auto a = residual(x);
              auto b = residual(a);
              return b;
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )

    payload = load_json_result(
        run_tool(tmp_path, "--cpp-symbol", f"{source}::solve", "--format", "json")
    )

    residual_edges = [
        edge
        for edge in payload["operational_ir"]["expansion_edges"]
        if edge["kind"] == "call_target" and edge["to"] == "function:residual"
    ]
    assert len(residual_edges) == 1
    residual_calls = [
        op
        for op in payload["operational_ir"]["ops"]
        if op.get("opcode") == "cxx.call" and op.get("target_symbol") == "residual"
    ]
    assert len(residual_calls) == 2


def test_cpp_source_canonical_ir_enumerates_static_code_paths(tmp_path: Path) -> None:
    """Branch and loop alternatives should be explicit machine-readable paths."""
    source = tmp_path / "include" / "branching.hpp"
    source.parent.mkdir(parents=True)
    source.write_text(
        textwrap.dedent(
            """
            int solve(int x) {
              if (x > 0) {
                x = x + 1;
              } else {
                x = x - 1;
              }
              while (x < 10) {
                x = x + 1;
              }
              return x;
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )

    payload = load_json_result(
        run_tool(tmp_path, "--cpp-symbol", f"{source}::solve", "--format", "json")
    )

    code_paths = payload["operational_ir"]["code_paths"]
    coverage = payload["operational_ir"]["coverage"]
    assert coverage["if_count"] == 1
    assert coverage["while_count"] == 1
    assert coverage["code_path_count"] == 4
    assert coverage["code_path_decision_count"] == 8
    assert coverage["unmapped_code_path_functions"] == []
    summaries = {path["summary"] for path in code_paths}
    assert summaries == {
        "if@2:then -> while@7:skip",
        "if@2:then -> while@7:enter",
        "if@2:else -> while@7:skip",
        "if@2:else -> while@7:enter",
    }


def test_cpp_source_canonical_ir_markdown_and_deterministic_json(tmp_path: Path) -> None:
    """Markdown mode should render a compact report and JSON output should be stable."""
    source = write_algorithm_fixture(tmp_path)

    first = run_tool(tmp_path, "--cpp-symbol", f"{source}::solve", "--format", "json")
    second = run_tool(tmp_path, "--cpp-symbol", f"{source}::solve", "--format", "json")
    markdown = run_tool(tmp_path, "--cpp-symbol", f"{source}::solve", "--format", "markdown")

    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    assert markdown.returncode == 0, markdown.stderr
    assert "# C++ Source Canonical IR" in markdown.stdout
    assert "## Operational IR Coverage" in markdown.stdout


def test_cpp_source_canonical_ir_reports_invalid_symbol(tmp_path: Path) -> None:
    """Invalid symbol references should fail with a clear message."""
    source = write_algorithm_fixture(tmp_path)

    missing = run_tool(tmp_path, "--cpp-symbol", f"{source}::missing", "--format", "json")
    invalid = run_tool(tmp_path, "--cpp-symbol", "missing-symbol", "--format", "json")

    assert missing.returncode != 0
    assert "C++ source symbol not found" in missing.stderr
    assert invalid.returncode != 0
    assert "path.cpp::qualname" in invalid.stderr
