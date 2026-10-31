# @dependency-start
# contract test
# responsibility Tests scoped StableHLO SSA dependency closure tracing.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/stablehlo_value_closure.rs traces scoped value dependencies.
# upstream design ../../documents/tools/stablehlo_value_closure.md defines the tool contract.
# @dependency-end

"""Tests for scoped StableHLO SSA dependency closure tracing."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import cast

AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


def _run_native_result(
    tmp_path: Path,
    ir: dict[str, object],
    *,
    value: str,
    function: str = "main",
    region_id: str = "",
) -> subprocess.CompletedProcess[str]:
    assert AGENT_CANON_CLI, "AGENT_CANON_CLI must select the current native executable"
    executable = Path(AGENT_CANON_CLI)
    assert (
        executable.is_absolute()
        and executable.is_file()
        and os.access(executable, os.X_OK)
    )
    ir_path = tmp_path / "operational-ir.json"
    ir_path.write_text(json.dumps(ir), encoding="utf-8")
    arguments = [
        str(executable),
        "stablehlo-value-closure",
        "--ir",
        str(ir_path),
        "--function",
        function,
        "--value",
        value,
        "--max-nodes",
        "32",
        "--format",
        "json",
    ]
    if region_id:
        arguments.extend(["--region-id", region_id])
    return subprocess.run(
        arguments, check=False, capture_output=True, text=True
    )


def _run_native(
    tmp_path: Path,
    ir: dict[str, object],
    *,
    value: str,
    function: str = "main",
    region_id: str = "",
) -> dict[str, object]:
    result = _run_native_result(
        tmp_path, ir, value=value, function=function, region_id=region_id
    )
    assert result.returncode == 0, result.stderr
    return cast(dict[str, object], json.loads(result.stdout))


def test_closure_keeps_callee_constants_scoped_to_callee(tmp_path: Path) -> None:
    """Trace callee constants without crossing same-name caller constants."""
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

    report = _run_native(tmp_path, ir, value="%out")
    op_ids = {row["op_id"] for row in cast(list[dict[str, object]], report["ops"])}
    assert "m1" in op_ids
    assert "c0" in op_ids
    assert "m0" not in op_ids


def test_while_operands_ignore_region_argument_aliases(tmp_path: Path) -> None:
    """Treat StableHLO while operands as incoming values, not region aliases."""
    op = "%r:2 = stablehlo.while(%iterArg = %x, %iterArg_0 = %y) : tensor<f32>, tensor<f32>"
    ir = {
        "schema": "agent-canon.thin-operational-ir.v2",
        "functions": [{"name": "main", "signature": "func.func public @main() {", "body_region_id": "r_main"}],
        "regions": [{"region_id": "r_main", "op_ids": ["while"]}],
        "ops": [{"op_id": "while", "kind": "Primitive", "opcode": "stablehlo.while", "function": "main", "region_id": "r_main", "line": 1, "text": op}],
    }
    report = _run_native(tmp_path, ir, value="%r#0")
    operation = cast(list[dict[str, object]], report["ops"])[0]
    assert operation["operand_names"] == ["%x", "%y"]


def test_closure_reports_constant_payloads_and_convert_ops(tmp_path: Path) -> None:
    """Report machine-readable constant payloads and scalar convert rows."""
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

    report = _run_native(tmp_path, ir, value="%out")

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


def test_numeric_result_name_fields_are_rejected_without_iterating_them(
    tmp_path: Path,
) -> None:
    """Match Python list(int) rejection, including values too large to expand."""
    for invalid_names in (2, 18_446_744_073_709_551_615):
        assert not isinstance(invalid_names, Iterable)

        ir = {
            "schema": "agent-canon.thin-operational-ir.v2",
            "functions": [
                {
                    "name": "main",
                    "signature": "func.func public @main() -> tensor<f32> {",
                    "body_region_id": "r_main",
                },
            ],
            "regions": [{"region_id": "r_main", "op_ids": ["constant"]}],
            "ops": [
                {
                    "op_id": "constant",
                    "kind": "Primitive",
                    "opcode": "stablehlo.constant",
                    "function": "main",
                    "region_id": "r_main",
                    "line": 1,
                    "result_names": invalid_names,
                    "text": "%out = stablehlo.constant dense<1.0> : tensor<f32>",
                }
            ],
        }

        result = _run_native_result(tmp_path, ir, value="%out")

        assert result.returncode != 0
        assert "result_names" in result.stderr
        assert "expected an iterable value" in result.stderr
