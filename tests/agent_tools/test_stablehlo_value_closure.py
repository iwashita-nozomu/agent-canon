# @dependency-start
# contract test
# responsibility Tests scoped StableHLO SSA dependency closure tracing.
# upstream implementation ../../tools/agent_tools/stablehlo_value_closure.py traces scoped value dependencies.
# upstream design ../../documents/tools/stablehlo_value_closure.md defines the tool contract.
# @dependency-end

"""Tests for scoped StableHLO SSA dependency closure tracing."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Protocol, cast


class _ClosureModule(Protocol):
    def load_operational_ir(self, path: Path) -> dict[str, object]: ...

    def trace_closure(
        self,
        ir: dict[str, object],
        root: object,
        max_nodes: int,
    ) -> dict[str, object]: ...

    ScopedValue: type


def _load_module() -> _ClosureModule:
    tool_path = Path(__file__).resolve().parents[2] / "tools/agent_tools/stablehlo_value_closure.py"
    spec = importlib.util.spec_from_file_location("_agent_canon_test_stablehlo_value_closure", tool_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast(_ClosureModule, module)


def test_closure_keeps_callee_constants_scoped_to_callee() -> None:
    """Trace callee constants without crossing same-name caller constants."""
    tool = _load_module()
    ir = {
        "schema": "agent-canon.thin-operational-ir.v2",
        "functions": [
            {
                "name": "main",
                "signature": "func.func public @main(%arg0: tensor<f32>) -> tensor<f32> {",
                "body_region_id": "r_main",
            },
            {
                "name": "callee",
                "signature": "func.func private @callee(%arg0: tensor<f32>) -> tensor<f32> {",
                "body_region_id": "r_callee",
            },
        ],
        "regions": [
            {"region_id": "r_main", "op_ids": ["m0", "m1", "m2"]},
            {"region_id": "r_callee", "op_ids": ["c0", "c1"]},
        ],
        "ops": [
            {
                "op_id": "m0",
                "kind": "Primitive",
                "opcode": "stablehlo.constant",
                "function": "main",
                "region_id": "r_main",
                "line": 1,
                "text": "%cst = stablehlo.constant dense<0.0> : tensor<f32>",
            },
            {
                "op_id": "m1",
                "kind": "Call",
                "opcode": "call",
                "function": "main",
                "region_id": "r_main",
                "line": 2,
                "call_target": "callee",
                "text": "%out = call @callee(%arg0) : (tensor<f32>) -> tensor<f32>",
            },
            {
                "op_id": "c0",
                "kind": "Primitive",
                "opcode": "stablehlo.constant",
                "function": "callee",
                "region_id": "r_callee",
                "line": 3,
                "text": "%cst = stablehlo.constant dense<1.0> : tensor<f32>",
            },
            {
                "op_id": "c1",
                "kind": "Return",
                "opcode": "return",
                "function": "callee",
                "region_id": "r_callee",
                "line": 4,
                "text": "return %cst : tensor<f32>",
            },
        ],
    }

    report = tool.trace_closure(ir, tool.ScopedValue("main", "r_main", "%out"), 32)
    op_ids = {row["op_id"] for row in cast(list[dict[str, object]], report["ops"])}
    assert "m1" in op_ids
    assert "c0" in op_ids
    assert "m0" not in op_ids


def test_while_operands_ignore_region_argument_aliases() -> None:
    """Treat StableHLO while operands as incoming values, not region aliases."""
    tool = _load_module()
    op = "%r:2 = stablehlo.while(%iterArg = %x, %iterArg_0 = %y) : tensor<f32>, tensor<f32>"
    assert tool.operand_names(op, ["%r#0", "%r#1", "%r"]) == ["%x", "%y"]


def test_closure_reports_constant_payloads_and_convert_ops() -> None:
    """Report machine-readable constant payloads and scalar convert rows."""
    tool = _load_module()
    ir = {
        "schema": "agent-canon.thin-operational-ir.v2",
        "functions": [
            {
                "name": "main",
                "signature": "func.func public @main() -> tensor<f32> {",
                "body_region_id": "r_main",
            },
        ],
        "regions": [
            {"region_id": "r_main", "op_ids": ["c0", "v0"]},
        ],
        "ops": [
            {
                "op_id": "c0",
                "kind": "Primitive",
                "opcode": "stablehlo.constant",
                "function": "main",
                "region_id": "r_main",
                "line": 1,
                "text": "%cst = stablehlo.constant dense<1.000000e+00> : tensor<f64>",
            },
            {
                "op_id": "v0",
                "kind": "Primitive",
                "opcode": "stablehlo.convert",
                "function": "main",
                "region_id": "r_main",
                "line": 2,
                "text": "%out = stablehlo.convert %cst : (tensor<f64>) -> tensor<f32>",
            },
        ],
    }

    report = tool.trace_closure(ir, tool.ScopedValue("main", "r_main", "%out"), 32)

    constants = cast(list[dict[str, object]], report["constant_payloads"])
    converts = cast(list[dict[str, object]], report["convert_ops"])
    assert constants == [
        {
            "op_id": "c0",
            "function": "main",
            "region_id": "r_main",
            "line": 1,
            "result_name": "%cst",
            "dense_literal": "1.000000e+00",
            "tensor_type": "f64",
            "dtype": "f64",
            "text": "%cst = stablehlo.constant dense<1.000000e+00> : tensor<f64>",
        }
    ]
    assert converts == [
        {
            "op_id": "v0",
            "function": "main",
            "region_id": "r_main",
            "line": 2,
            "result_name": "%out",
            "operand_name": "%cst",
            "from_tensor_type": "f64",
            "to_tensor_type": "f32",
            "from_dtype": "f64",
            "to_dtype": "f32",
            "text": "%out = stablehlo.convert %cst : (tensor<f64>) -> tensor<f32>",
        }
    ]
