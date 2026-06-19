# @dependency-start
# contract test
# responsibility Tests shared thin operational IR to Lean evidence rendering.
# upstream implementation ../../tools/agent_tools/operational_ir_to_lean.py renders Lean evidence.
# upstream implementation ../../tools/agent_tools/cpp_source_canonical_ir.py produces C++ source IR.
# upstream design ../../documents/tools/operational_ir_to_lean.md documents the renderer contract.
# @dependency-end
"""Tests for operational IR to Lean evidence rendering."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "operational_ir_to_lean.py"
CPP_IR_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "cpp_source_canonical_ir.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the operational IR to Lean renderer."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def run_cpp_ir(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the C++ source-canonical IR producer."""
    return subprocess.run(
        [sys.executable, str(CPP_IR_SCRIPT), "--root", str(root), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_json(path: Path, payload: object) -> None:
    """Write a deterministic JSON fixture."""
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def thin_ir_code_paths() -> list[dict[str, object]]:
    """Return fully covered code-path fixture rows."""
    return [
        {
            "path_id": "path:solve:00000",
            "function": "solve",
            "region_id": "region_00000",
            "op_ids": ["op_00000"],
            "decisions": [],
            "decision_count": 0,
            "summary": "straight_line",
        }
    ]


def thin_ir_coverage() -> dict[str, object]:
    """Return fully covered thin-operational-IR counters."""
    return {
        "function_count": 1,
        "region_count": 1,
        "expansion_edge_count": 1,
        "op_count": 1,
        "assigned_region_count": 1,
        "unassigned_op_count": 0,
        "unassigned_op_ids": [],
        "unresolved_call_targets": [],
        "max_region_depth": 0,
        "while_count": 0,
        "case_count": 0,
        "if_count": 0,
        "call_count": 0,
        "code_path_count": 1,
        "code_path_decision_count": 0,
        "max_code_path_decisions": 0,
        "unmapped_code_path_functions": [],
    }


def thin_ir_payload() -> dict[str, object]:
    """Return a fully covered thin-operational-IR fixture."""
    return {
        "schema": "agent-canon.thin-operational-ir.v2",
        "allowed_kinds": ["Function", "Let", "Call", "Return"],
        "function_signatures": ["int solve(int x)"],
        "functions": [
            {
                "function_id": "function:solve",
                "name": "solve",
                "signature": "int solve(int x)",
                "line_start": 1,
                "line_end": 4,
                "body_region_id": "region_00001",
            }
        ],
        "regions": [
            {
                "region_id": "region_00000",
                "kind": "module",
                "parent_function": "",
                "parent_op_id": "",
                "depth": 0,
                "line_start": 1,
                "line_end": 4,
                "op_ids": ["op_00000"],
            }
        ],
        "expansion_edges": [
            {
                "edge_id": "edge_00000",
                "kind": "program_root",
                "from": "program",
                "to": "function:solve",
            }
        ],
        "code_paths": thin_ir_code_paths(),
        "ops": [
            {
                "op_id": "op_00000",
                "kind": "Return",
                "opcode": "cxx.return",
                "line": 3,
                "text": "x",
                "text_sha256": "abc123",
                "tensor_types": [],
                "dtypes": [],
                "function": "solve",
                "region_id": "region_00000",
                "region_path": ["region_00000"],
                "parent_op_id": "",
                "call_target": "",
                "target_symbol": "",
            }
        ],
        "coverage": thin_ir_coverage(),
    }


def thin_ir_payload_with_unresolved(unresolved_targets: list[str]) -> dict[str, object]:
    """Return a thin-operational-IR fixture with unresolved calls."""
    payload = thin_ir_payload()
    ops = payload["ops"]
    coverage = payload["coverage"]
    assert isinstance(ops, list)
    assert isinstance(coverage, dict)
    op = cast(dict[str, object], ops[0])
    assert isinstance(op, dict)
    op["target_symbol"] = unresolved_targets[0]
    coverage["unresolved_call_targets"] = unresolved_targets
    return payload


def thin_ir_payload_with_unassigned_op() -> dict[str, object]:
    """Return a thin-operational-IR fixture with unassigned op coverage."""
    payload = thin_ir_payload()
    coverage = payload["coverage"]
    assert isinstance(coverage, dict)
    coverage["unassigned_op_count"] = 1
    coverage["unassigned_op_ids"] = ["op_missing_region"]
    return payload


def thin_ir_payload_with_unmapped_code_path() -> dict[str, object]:
    """Return a thin-operational-IR fixture with missing code-path coverage."""
    payload = thin_ir_payload()
    payload["code_paths"] = []
    coverage = payload["coverage"]
    assert isinstance(coverage, dict)
    coverage["code_path_count"] = 0
    coverage["unmapped_code_path_functions"] = ["solve"]
    return payload


def cpp_envelope_payload() -> dict[str, object]:
    """Return a C++ source-canonical envelope fixture."""
    return {
        "schema": "agent-canon.cpp-source-canonical-ir.v1",
        "root": {
            "schema": "agent-canon.cpp-source-root-ref.v1",
            "cpp_symbol": "include/algorithm.hpp::solve",
            "repo_root": "/repo",
            "source_kind": "cxx_source",
            "source_path": "include/algorithm.hpp",
            "qualname": "solve",
        },
        "source_root": {
            "schema": "agent-canon.cpp-source-root.v1",
            "status": "ok",
            "path": "/repo/include/algorithm.hpp",
            "relative_path": "include/algorithm.hpp",
            "qualname": "solve",
            "name": "solve",
            "source_sha256": "sourcehash",
            "file_sha256": "filehash",
            "source_span": "1:4",
        },
        "public_interface": {
            "schema": "agent-canon.cpp-public-interface.v1",
            "status": "ok",
            "qualname": "solve",
            "name": "solve",
            "parameters": [{"index": 0, "name": "x", "declaration": "int x", "type": "int"}],
            "return_type": "int",
            "coverage": {"parameter_count": 1, "has_return_type": True},
        },
        "source_facts": {
            "schema": "agent-canon.cpp-source-facts.v1",
            "facts": [
                {
                    "fact_id": "fact:solve:return",
                    "source_path": "include/algorithm.hpp",
                    "source_symbol": "solve",
                    "source_span": "3:None",
                    "fact_kind": "return_equation",
                    "target": "return",
                    "expression": 'x"y\\z\n',
                    "statement": "solve returns x",
                    "text_sha256": "facthash",
                }
            ],
            "coverage": {"fact_count": 1},
        },
        "operational_ir": thin_ir_payload(),
    }


def cpp_envelope_payload_with_unresolved(unresolved_targets: list[str]) -> dict[str, object]:
    """Return a C++ source-canonical envelope fixture with unresolved calls."""
    payload = cpp_envelope_payload()
    payload["operational_ir"] = thin_ir_payload_with_unresolved(unresolved_targets)
    return payload


def write_algorithm_fixture(root: Path) -> Path:
    """Write a C++ algorithm fixture."""
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


def test_operational_ir_to_lean_rejects_invalid_json(tmp_path: Path) -> None:
    """Malformed JSON should fail before any Lean output is produced."""
    ir = tmp_path / "bad.json"
    ir.write_text("{bad json", encoding="utf-8")

    result = run_tool("--ir", str(ir), "--namespace", "Smoke")

    assert result.returncode != 0
    assert "invalid JSON" in result.stderr
    assert result.stdout == ""


def test_operational_ir_to_lean_rejects_missing_operational_ir(tmp_path: Path) -> None:
    """Unrelated JSON should not be rendered as evidence."""
    ir = tmp_path / "wrong.json"
    write_json(ir, {"schema": "agent-canon.unrelated.v1"})

    result = run_tool("--ir", str(ir), "--namespace", "Smoke")

    assert result.returncode != 0
    assert "missing operational_ir object" in result.stderr


def test_operational_ir_to_lean_reports_missing_input_file(tmp_path: Path) -> None:
    """Missing input files should fail with a clean CLI message."""
    missing = tmp_path / "missing.json"

    result = run_tool("--ir", str(missing), "--namespace", "Smoke")

    assert result.returncode != 0
    assert "unable to read input JSON" in result.stderr
    assert str(missing) in result.stderr


def test_operational_ir_to_lean_escapes_lean_strings(tmp_path: Path) -> None:
    """Generated Lean string literals should survive quotes, slashes, and newlines."""
    ir = tmp_path / "cpp.json"
    write_json(ir, cpp_envelope_payload())

    result = run_tool("--ir", str(ir), "--namespace", "Smoke", "--module-name", "Generated")

    assert result.returncode == 0, result.stderr
    assert 'expression := "x\\"y\\\\z\\n"' in result.stdout
    assert "def sourceFacts : List SourceFact" in result.stdout


def test_operational_ir_to_lean_is_deterministic(tmp_path: Path) -> None:
    """Repeated rendering of the same input should be byte-stable."""
    ir = tmp_path / "thin.json"
    write_json(ir, thin_ir_payload())

    first = run_tool("--ir", str(ir), "--namespace", "Smoke")
    second = run_tool("--ir", str(ir), "--namespace", "Smoke")

    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    assert "def operationalCoverage : OperationalCoverage" in first.stdout
    assert "def codePaths : List CodePath" in first.stdout
    assert "def codePathCoverageComplete : Bool" in first.stdout


def test_operational_ir_to_lean_out_file_and_default_module(tmp_path: Path) -> None:
    """The CLI should write to --out and derive a stable module name."""
    ir = tmp_path / "cpp.json"
    out = tmp_path / "Generated.lean"
    write_json(ir, cpp_envelope_payload())

    result = run_tool("--ir", str(ir), "--namespace", "Smoke", "--out", str(out))

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    text = out.read_text(encoding="utf-8")
    assert "namespace Smoke" in text
    assert "namespace solve_operational_ir" in text
    assert '("public_interface.parameters_json"' not in text
    assert "def publicInterfaceFields : List KeyValue" in text


def test_operational_ir_to_lean_coverage_gate(tmp_path: Path) -> None:
    """Unresolved calls should fail before Lean output is produced."""
    ir = tmp_path / "unresolved.json"
    write_json(ir, cpp_envelope_payload_with_unresolved(["external_call"]))

    result = run_tool("--ir", str(ir), "--namespace", "Smoke")

    assert result.returncode != 0
    assert "incomplete operational coverage" in result.stderr
    assert "external_call" in result.stderr
    assert result.stdout == ""


def test_operational_ir_to_lean_coverage_gate_rejects_unassigned_ops(
    tmp_path: Path,
) -> None:
    """Unassigned operation rows should fail before Lean output is produced."""
    ir = tmp_path / "unassigned.json"
    write_json(ir, thin_ir_payload_with_unassigned_op())

    result = run_tool("--ir", str(ir), "--namespace", "Smoke")

    assert result.returncode != 0
    assert "incomplete operational coverage" in result.stderr
    assert "unassigned_op_count=1" in result.stderr


def test_operational_ir_to_lean_coverage_gate_rejects_unmapped_code_paths(
    tmp_path: Path,
) -> None:
    """Missing code-path rows should fail before Lean output is produced."""
    ir = tmp_path / "unmapped_code_paths.json"
    write_json(ir, thin_ir_payload_with_unmapped_code_path())

    result = run_tool("--ir", str(ir), "--namespace", "Smoke")

    assert result.returncode != 0
    assert "incomplete operational coverage" in result.stderr
    assert "unmapped_code_path_functions=[solve]" in result.stderr


def test_operational_ir_to_lean_rejects_missing_coverage_completeness_fields(
    tmp_path: Path,
) -> None:
    """Missing coverage completeness fields should not render as complete coverage."""
    payload = thin_ir_payload()
    coverage = payload["coverage"]
    assert isinstance(coverage, dict)
    del coverage["unresolved_call_targets"]
    ir = tmp_path / "missing_coverage.json"
    write_json(ir, payload)

    default = run_tool("--ir", str(ir), "--namespace", "Smoke")

    assert default.returncode != 0
    assert "missing required coverage field: unresolved_call_targets" in default.stderr


def test_operational_ir_to_lean_cpp_source_pipeline(tmp_path: Path) -> None:
    """Existing C++ source IR should feed the generic Lean renderer."""
    source = write_algorithm_fixture(tmp_path)
    ir = tmp_path / "solve.json"
    out = tmp_path / "SolveGenerated.lean"
    produced = run_cpp_ir(
        tmp_path,
        "--cpp-symbol",
        f"{source}::solve",
        "--format",
        "json",
        "--out",
        str(ir),
    )
    assert produced.returncode == 0, produced.stderr

    result = run_tool(
        "--ir",
        str(ir),
        "--namespace",
        "Smoke",
        "--module-name",
        "SolveGenerated",
        "--out",
        str(out),
    )

    assert result.returncode == 0, result.stderr
    text = out.read_text(encoding="utf-8")
    assert "namespace SolveGenerated" in text
    assert 'name := "solve"' in text
    assert "Stepper.step" in text
    assert "kkt_residual" in text
    assert "return_equation" in text
    assert "operationalCoverage" in text
