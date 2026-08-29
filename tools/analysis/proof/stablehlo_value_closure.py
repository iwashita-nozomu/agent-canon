#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Traces scoped StableHLO value dependencies from JIT-canonical operational IR.
# upstream implementation jit_canonical_ir.py emits operational_ir functions, regions, and ops.
# upstream implementation ../../rust/agent-canon/src/jit_ir_to_lean.rs emits the matching Lean operational op fields.
# downstream implementation theorem_graph_circularity_check.py consumes closure frontiers when theorem graph leaves are audited.
# @dependency-end

"""Trace a scoped StableHLO SSA value closure from JIT-canonical IR.

This tool intentionally keeps MLIR SSA names scoped by function and region.
Names such as ``%cst`` are local to a function body; treating them as global
causes false proof edges when a private callee reuses the same textual name.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import cast

JsonObject = dict[str, object]

DEFAULT_MAX_NODES = 1000
PERCENT_NAME_RE = re.compile(r"%[A-Za-z0-9_#.]+(?::[0-9]+)?")
CONSTANT_RE = re.compile(
    r"(?P<result>%[A-Za-z0-9_#.]+)\s*=\s*stablehlo\.constant\s+"
    r"dense<(?P<literal>[^>]+)>\s*:\s*tensor<(?P<tensor_type>[^>]+)>"
)
CONVERT_RE = re.compile(
    r"(?P<result>%[A-Za-z0-9_#.]+)\s*=\s*stablehlo\.convert\s+"
    r"(?P<operand>%[A-Za-z0-9_#.]+)\s*:\s*"
    r"\(tensor<(?P<from_tensor_type>[^>]+)>\)\s*->\s*"
    r"tensor<(?P<to_tensor_type>[^>]+)>"
)


@dataclass(frozen=True)
class ScopedValue:
    function: str
    region_id: str
    name: str

    def key(self) -> str:
        return f"{self.function}:{self.region_id}:{self.name}"


def percent_names(text: str) -> list[str]:
    return [name.split(":", 1)[0] for name in PERCENT_NAME_RE.findall(text)]


def return_operands(text: str) -> list[str]:
    text = text.strip()
    if text.startswith("stablehlo.return "):
        rest = text.removeprefix("stablehlo.return ")
    elif text.startswith("return "):
        rest = text.removeprefix("return ")
    else:
        return []
    return [part.strip() for part in rest.split(" : ", 1)[0].split(",") if part.strip()]


def result_names(text: str) -> list[str]:
    if " = " not in text:
        return []
    lhs, _rhs = text.split(" = ", 1)
    names = []
    for raw_name in PERCENT_NAME_RE.findall(lhs):
        if ":" in raw_name:
            base, count_text = raw_name.split(":", 1)
            try:
                count = int(count_text)
            except ValueError:
                names.append(base)
            else:
                names.extend(f"{base}#{index}" for index in range(count))
                names.append(base)
        else:
            names.append(raw_name)
    return names


def operand_names(text: str, results: list[str]) -> list[str]:
    stripped = text.strip()
    if stripped.startswith("stablehlo.return ") or stripped.startswith("return "):
        names = return_operands(stripped)
    elif " = " in text:
        _lhs, rhs = text.split(" = ", 1)
        names = while_initial_operands(rhs) or percent_names(rhs)
    else:
        names = percent_names(text)
    result_set = set(results)
    return [name for name in names if name not in result_set]


def while_initial_operands(rhs: str) -> list[str]:
    """Return StableHLO while initial values, not region argument aliases."""
    if not rhs.strip().startswith("stablehlo.while("):
        return []
    body = rhs.split("stablehlo.while(", 1)[1].split(") :", 1)[0]
    operands = []
    for part in body.split(","):
        if " = " not in part:
            continue
        _alias, value = part.split(" = ", 1)
        value_names = percent_names(value)
        if value_names:
            operands.append(value_names[0])
    return operands


def function_argument_names(signature: str) -> list[str]:
    if "(" not in signature or ")" not in signature:
        return []
    args = signature.split("(", 1)[1].split(")", 1)[0]
    return percent_names(args)


def load_operational_ir(path: Path) -> JsonObject:
    value = cast(JsonObject, json.loads(path.read_text()))
    if "operational_ir" in value:
        value = cast(JsonObject, value["operational_ir"])
    if value.get("schema") != "agent-canon.thin-operational-ir.v2":
        raise SystemExit(f"{path}: unsupported or missing operational_ir schema")
    return value


def normalize_op(raw: JsonObject) -> JsonObject:
    text = str(raw.get("text", ""))
    results = list(raw.get("result_names") or raw.get("resultNames") or result_names(text))
    operands = list(raw.get("operand_names") or raw.get("operandNames") or operand_names(text, results))
    return {
        **raw,
        "op_id": raw.get("op_id") or raw.get("opId") or "",
        "kind": raw.get("kind") or "",
        "opcode": raw.get("opcode") or "",
        "function": raw.get("function") or raw.get("functionName") or "",
        "region_id": raw.get("region_id") or raw.get("regionId") or "",
        "parent_op_id": raw.get("parent_op_id") or raw.get("parentOpId") or "",
        "call_target": raw.get("call_target") or raw.get("callTarget") or "",
        "line": int(raw.get("line") or 0),
        "text": text,
        "result_names": results,
        "operand_names": operands,
    }


def scalar_dtype(tensor_type: str) -> str:
    """Return the scalar dtype suffix from a StableHLO tensor type fragment."""
    text = tensor_type.strip()
    if "x" in text:
        return text.rsplit("x", 1)[1]
    return text


def constant_payload_row(op: JsonObject) -> JsonObject | None:
    """Return a machine-readable dense constant payload row for one op."""
    if op.get("opcode") != "stablehlo.constant":
        return None
    match = CONSTANT_RE.search(str(op.get("text", "")))
    if not match:
        return None
    result = match.group("result")
    tensor_type = match.group("tensor_type")
    return {
        "op_id": op["op_id"],
        "function": op["function"],
        "region_id": op["region_id"],
        "line": op["line"],
        "result_name": result,
        "dense_literal": match.group("literal"),
        "tensor_type": tensor_type,
        "dtype": scalar_dtype(tensor_type),
        "text": op["text"],
    }


def convert_op_row(op: JsonObject) -> JsonObject | None:
    """Return a machine-readable StableHLO scalar convert row for one op."""
    if op.get("opcode") != "stablehlo.convert":
        return None
    match = CONVERT_RE.search(str(op.get("text", "")))
    if not match:
        return None
    from_tensor_type = match.group("from_tensor_type")
    to_tensor_type = match.group("to_tensor_type")
    return {
        "op_id": op["op_id"],
        "function": op["function"],
        "region_id": op["region_id"],
        "line": op["line"],
        "result_name": match.group("result"),
        "operand_name": match.group("operand"),
        "from_tensor_type": from_tensor_type,
        "to_tensor_type": to_tensor_type,
        "from_dtype": scalar_dtype(from_tensor_type),
        "to_dtype": scalar_dtype(to_tensor_type),
        "text": op["text"],
    }


def region_index(ir: JsonObject) -> dict[str, JsonObject]:
    return {str(region.get("region_id")): region for region in ir.get("regions", [])}


def function_index(ir: JsonObject) -> dict[str, JsonObject]:
    return {str(fn.get("name")): fn for fn in ir.get("functions", [])}


def op_index(ir: JsonObject) -> tuple[dict[str, JsonObject], dict[tuple[str, str, str], list[JsonObject]]]:
    by_id: dict[str, JsonObject] = {}
    by_value: dict[tuple[str, str, str], list[JsonObject]] = {}
    for raw in ir.get("ops", []):
        op = normalize_op(raw)
        by_id[op["op_id"]] = op
        for name in op["result_names"]:
            by_value.setdefault((op["function"], op["region_id"], name), []).append(op)
    return by_id, by_value


def function_body_region(functions: dict[str, JsonObject], function: str) -> str:
    fn = functions.get(function)
    if not fn:
        return ""
    return str(fn.get("body_region_id") or fn.get("bodyRegionId") or "")


def function_args(functions: dict[str, JsonObject], function: str) -> list[str]:
    fn = functions.get(function)
    if not fn:
        return []
    if "argument_names" in fn:
        return list(fn["argument_names"])
    if "argumentNames" in fn:
        return list(fn["argumentNames"])
    return function_argument_names(str(fn.get("signature", "")))


def region_ancestors(regions: dict[str, JsonObject], region_id: str) -> list[str]:
    path = []
    current = region_id
    seen = set()
    while current and current not in seen:
        seen.add(current)
        path.append(current)
        parent_op_id = str(regions.get(current, {}).get("parent_op_id") or "")
        if not parent_op_id:
            break
        parent_region = ""
        for candidate_id, candidate in regions.items():
            op_ids = candidate.get("op_ids") or []
            if parent_op_id in op_ids:
                parent_region = candidate_id
                break
        current = parent_region
    return path


def resolve_definition(
    by_value: dict[tuple[str, str, str], list[JsonObject]],
    regions: dict[str, JsonObject],
    value: ScopedValue,
    before_line: int | None = None,
) -> JsonObject | None:
    for region_id in region_ancestors(regions, value.region_id):
        candidates = by_value.get((value.function, region_id, value.name), [])
        if before_line is not None:
            candidates = [op for op in candidates if op["line"] <= before_line]
        if candidates:
            return sorted(candidates, key=lambda op: op["line"])[-1]
    return None


def callee_return_ops(ops: dict[str, JsonObject], functions: dict[str, JsonObject], target: str) -> list[JsonObject]:
    body_region = function_body_region(functions, target)
    return sorted(
        [
            op
            for op in ops.values()
            if op["function"] == target and op["region_id"] == body_region and op["kind"] == "Return"
        ],
        key=lambda op: op["line"],
    )


def trace_closure(ir: JsonObject, root: ScopedValue, max_nodes: int) -> JsonObject:
    functions = function_index(ir)
    regions = region_index(ir)
    ops, by_value = op_index(ir)
    queue: deque[tuple[ScopedValue, dict[str, ScopedValue], str | None]] = deque([(root, {}, None)])
    seen_values: set[str] = set()
    op_rows: dict[str, JsonObject] = {}
    leaves: dict[str, JsonObject] = {}
    edges: list[dict[str, str]] = []

    while queue and len(seen_values) < max_nodes:
        value, arg_map, via = queue.popleft()
        key = value.key()
        if key in seen_values:
            continue
        seen_values.add(key)

        if value.name in arg_map:
            mapped = arg_map[value.name]
            leaves[key] = {
                "kind": "callee_argument_mapping",
                "value": value.name,
                "mapped_to": mapped.key(),
                "function": value.function,
                "region_id": value.region_id,
            }
            queue.append((mapped, {}, key))
            continue

        if value.name in function_args(functions, value.function):
            leaves[key] = {
                "kind": "public_or_function_argument",
                "value": value.name,
                "function": value.function,
                "region_id": value.region_id,
            }
            continue

        op = resolve_definition(by_value, regions, value)
        if op is None and value.name.startswith("%") and "#" in value.name:
            base = value.name.split("#", 1)[0]
            op = resolve_definition(by_value, regions, ScopedValue(value.function, value.region_id, base))
        if op is None:
            leaves[key] = {
                "kind": "unresolved_value",
                "value": value.name,
                "function": value.function,
                "region_id": value.region_id,
            }
            continue

        op_rows[op["op_id"]] = {
            "op_id": op["op_id"],
            "kind": op["kind"],
            "opcode": op["opcode"],
            "function": op["function"],
            "region_id": op["region_id"],
            "line": op["line"],
            "result_names": op["result_names"],
            "operand_names": op["operand_names"],
            "call_target": op["call_target"],
            "text": op["text"],
        }
        if via:
            edges.append({"source": via, "target": key, "kind": "depends_on"})

        for operand in op["operand_names"]:
            if operand.startswith("%iterArg"):
                leaves[f"{op['function']}:{op['region_id']}:{operand}"] = {
                    "kind": "loop_region_argument",
                    "value": operand,
                    "function": op["function"],
                    "region_id": op["region_id"],
                    "producer_op_id": op["parent_op_id"],
                }
                continue
            queue.append((ScopedValue(op["function"], op["region_id"], operand), arg_map, key))

        if op["kind"] == "Call" and op["call_target"]:
            callee = op["call_target"]
            callee_args = function_args(functions, callee)
            callee_map = {
                arg: ScopedValue(op["function"], op["region_id"], operand)
                for arg, operand in zip(callee_args, op["operand_names"], strict=False)
            }
            for ret in callee_return_ops(ops, functions, callee):
                op_rows[ret["op_id"]] = {
                    "op_id": ret["op_id"],
                    "kind": ret["kind"],
                    "opcode": ret["opcode"],
                    "function": ret["function"],
                    "region_id": ret["region_id"],
                    "line": ret["line"],
                    "result_names": ret["result_names"],
                    "operand_names": ret["operand_names"],
                    "call_target": ret["call_target"],
                    "text": ret["text"],
                }
                for operand in ret["operand_names"]:
                    queue.append(
                        (
                            ScopedValue(callee, function_body_region(functions, callee), operand),
                            callee_map,
                            key,
                        )
                    )

    op_list = sorted(op_rows.values(), key=lambda row: (row["function"], row["line"], row["op_id"]))
    constant_payloads = [
        row for op in op_list if (row := constant_payload_row(op)) is not None
    ]
    convert_ops = [
        row for op in op_list if (row := convert_op_row(op)) is not None
    ]
    return {
        "schema": "agent-canon.stablehlo-value-closure.v1",
        "root": {"function": root.function, "region_id": root.region_id, "name": root.name},
        "value_count": len(seen_values),
        "op_count": len(op_rows),
        "leaf_count": len(leaves),
        "constant_payload_count": len(constant_payloads),
        "convert_op_count": len(convert_ops),
        "truncated": bool(queue),
        "ops": op_list,
        "constant_payloads": constant_payloads,
        "convert_ops": convert_ops,
        "leaves": sorted(leaves.values(), key=lambda row: (row["function"], row["region_id"], row["value"])),
        "edges": edges,
    }


def render_text(report: JsonObject) -> str:
    lines = [
        f"STABLEHLO_VALUE_CLOSURE_ROOT={report['root']['function']}:{report['root']['region_id']}:{report['root']['name']}",
        f"STABLEHLO_VALUE_CLOSURE_VALUES={report['value_count']}",
        f"STABLEHLO_VALUE_CLOSURE_OPS={report['op_count']}",
        f"STABLEHLO_VALUE_CLOSURE_LEAVES={report['leaf_count']}",
        f"STABLEHLO_VALUE_CLOSURE_CONSTANT_PAYLOADS={report['constant_payload_count']}",
        f"STABLEHLO_VALUE_CLOSURE_CONVERT_OPS={report['convert_op_count']}",
        f"STABLEHLO_VALUE_CLOSURE_TRUNCATED={str(report['truncated']).lower()}",
    ]
    for op in report["ops"]:
        lines.append(
            "OP\t{op_id}\t{function}\t{region_id}\t{kind}\t{opcode}\tresults={results}\toperands={operands}\tcall={call}".format(
                op_id=op["op_id"],
                function=op["function"],
                region_id=op["region_id"],
                kind=op["kind"],
                opcode=op["opcode"],
                results=",".join(op["result_names"]),
                operands=",".join(op["operand_names"]),
                call=op["call_target"],
            )
        )
    for payload in report.get("constant_payloads", []):
        lines.append(
            "CONSTANT\t{op_id}\t{function}\t{region_id}\t{result}\tdense={literal}\ttype={tensor_type}\tdtype={dtype}".format(
                op_id=payload["op_id"],
                function=payload["function"],
                region_id=payload["region_id"],
                result=payload["result_name"],
                literal=payload["dense_literal"],
                tensor_type=payload["tensor_type"],
                dtype=payload["dtype"],
            )
        )
    for convert in report.get("convert_ops", []):
        lines.append(
            "CONVERT\t{op_id}\t{function}\t{region_id}\t{result}\toperand={operand}\tfrom={from_type}\tto={to_type}".format(
                op_id=convert["op_id"],
                function=convert["function"],
                region_id=convert["region_id"],
                result=convert["result_name"],
                operand=convert["operand_name"],
                from_type=convert["from_tensor_type"],
                to_type=convert["to_tensor_type"],
            )
        )
    for leaf in report["leaves"]:
        lines.append(
            "LEAF\t{kind}\t{function}\t{region_id}\t{value}".format(
                kind=leaf["kind"],
                function=leaf.get("function", ""),
                region_id=leaf.get("region_id", ""),
                value=leaf.get("value", ""),
            )
        )
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ir", required=True, type=Path, help="JIT-canonical IR JSON or operational_ir JSON")
    parser.add_argument("--function", required=True, help="Root function name, for example main")
    parser.add_argument("--region-id", default="", help="Root region id; defaults to the function body region")
    parser.add_argument("--value", required=True, help="SSA value name, for example %%276")
    parser.add_argument("--max-nodes", type=int, default=DEFAULT_MAX_NODES)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    ir = load_operational_ir(args.ir)
    functions = function_index(ir)
    region_id = args.region_id or function_body_region(functions, args.function)
    report = trace_closure(ir, ScopedValue(args.function, region_id, args.value), args.max_nodes)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        sys.stdout.write(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
