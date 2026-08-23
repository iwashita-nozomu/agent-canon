#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Lowers shared thin operational IR records into Lean evidence definitions.
# upstream design ../../documents/tools/operational_ir_to_lean.md documents the renderer contract.
# upstream design ../../documents/tools/cpp_source_canonical_ir.md defines the C++ source envelope.
# upstream implementation cpp_source_canonical_ir.py produces C++ source-canonical IR records.
# downstream implementation ../../tests/agent_tools/test_operational_ir_to_lean.py tests it.
# @dependency-end
"""Render shared thin operational IR records as Lean evidence definitions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import cast

THIN_OPERATIONAL_IR_SCHEMA = "agent-canon.thin-operational-ir.v2"
LEAN_KEYWORDS = frozenset(
    {
        "axiom",
        "by",
        "class",
        "def",
        "deriving",
        "else",
        "end",
        "example",
        "forall",
        "fun",
        "if",
        "import",
        "in",
        "inductive",
        "instance",
        "let",
        "match",
        "namespace",
        "open",
        "opaque",
        "rec",
        "structure",
        "theorem",
        "then",
        "universe",
        "where",
    }
)
STANDARD_OP_FIELDS = frozenset(
    {
        "op_id",
        "kind",
        "opcode",
        "line",
        "text",
        "text_sha256",
        "tensor_types",
        "dtypes",
        "function",
        "region_id",
        "region_path",
        "parent_op_id",
        "call_target",
    }
)
STANDARD_COVERAGE_FIELDS = frozenset(
    {
        "function_count",
        "region_count",
        "expansion_edge_count",
        "op_count",
        "assigned_region_count",
        "unassigned_op_count",
        "unassigned_op_ids",
        "unresolved_call_targets",
        "max_region_depth",
        "while_count",
        "case_count",
        "if_count",
        "call_count",
        "code_path_count",
        "code_path_decision_count",
        "max_code_path_decisions",
        "unmapped_code_path_functions",
    }
)
JSON_METADATA_ENCODER = json.JSONEncoder(
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)


@dataclass(frozen=True)
class RenderInput:
    """Normalized evidence packet consumed by the Lean renderer."""

    input_schema: str
    module_name: str
    provenance: tuple[tuple[str, str], ...]
    public_interface: tuple[tuple[str, str], ...]
    source_facts: tuple[Mapping[str, object], ...]
    operational_ir: Mapping[str, object]


def object_mapping(value: object, label: str) -> Mapping[str, object]:
    """Return a JSON object mapping or raise a schema error."""
    if not isinstance(value, Mapping):
        raise ValueError(f"missing {label} object")
    return cast(Mapping[str, object], value)


def optional_mapping(value: object) -> Mapping[str, object]:
    """Return a JSON object mapping or an empty mapping."""
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return {}


def mapping_list(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    """Return a list of JSON object rows or raise a schema error."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"missing {label} array")
    rows: list[Mapping[str, object]] = []
    items = cast(list[object], value)
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        rows.append(cast(Mapping[str, object], item))
    return tuple(rows)


def string_list(value: object, label: str) -> tuple[str, ...]:
    """Return a JSON string list or raise a schema error."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"missing {label} string array")
    rows: list[str] = []
    items = cast(list[object], value)
    for index, item in enumerate(items):
        if not isinstance(item, str):
            raise ValueError(f"{label}[{index}] must be a string")
        rows.append(item)
    return tuple(rows)


def string_field(row: Mapping[str, object], key: str, default: str = "") -> str:
    """Return a string field, stringifying primitive JSON values when needed."""
    value = row.get(key, default)
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, bool | int | float):
        return str(value)
    return JSON_METADATA_ENCODER.encode(value)


def int_field(row: Mapping[str, object], key: str, default: int = 0) -> int:
    """Return an integer field or raise a schema error for non-integral values."""
    value = row.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if value is None:
        return default
    raise ValueError(f"{key} must be an integer")


def required_int_field(row: Mapping[str, object], key: str) -> int:
    """Return a required integer field or raise a schema error."""
    if key not in row:
        raise ValueError(f"missing required coverage field: {key}")
    return int_field(row, key)


def required_string_list(row: Mapping[str, object], key: str) -> tuple[str, ...]:
    """Return a required string list field or raise a schema error."""
    if key not in row:
        raise ValueError(f"missing required coverage field: {key}")
    return string_list(row[key], f"coverage.{key}")


def lean_string(value: str) -> str:
    """Return a Lean string literal for one Python string."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def lean_string_list(values: Sequence[str]) -> str:
    """Render a Lean list of string literals."""
    if not values:
        return "[]"
    return "[" + ", ".join(lean_string(value) for value in values) + "]"


def lean_nat(value: int) -> str:
    """Render a non-negative Lean Nat literal."""
    if value < 0:
        raise ValueError(f"Nat field must be non-negative, got {value}")
    return str(value)


def validate_namespace(value: str) -> str:
    """Validate a dotted Lean namespace path."""
    if not value:
        raise ValueError("Lean namespace must not be empty")
    segments = value.split(".")
    for segment in segments:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_']*", segment):
            raise ValueError(f"invalid Lean namespace segment: {segment}")
        if segment in LEAN_KEYWORDS:
            raise ValueError(f"Lean namespace segment is reserved: {segment}")
    return value


def sanitize_lean_namespace(value: str) -> str:
    """Return a deterministic Lean namespace path from arbitrary metadata."""
    raw_segments = [segment for segment in re.split(r"[.:/\\\s-]+", value) if segment]
    if not raw_segments:
        raw_segments = ["GeneratedOperationalIr"]
    segments: list[str] = []
    for raw in raw_segments:
        segment = re.sub(r"[^A-Za-z0-9_']", "_", raw)
        if not segment or segment[0].isdigit():
            segment = f"Generated_{segment}"
        if segment in LEAN_KEYWORDS:
            segment = f"{segment}_generated"
        segments.append(segment)
    return ".".join(segments)


def default_module_name(record: Mapping[str, object]) -> str:
    """Choose a stable generated module namespace from record metadata."""
    source_root = optional_mapping(record.get("source_root"))
    root = optional_mapping(record.get("root"))
    candidate = (
        string_field(source_root, "qualname")
        or string_field(root, "qualname")
        or string_field(root, "python_symbol")
        or string_field(root, "cpp_symbol")
        or "GeneratedOperationalIr"
    )
    leaf = candidate.rsplit(".", 1)[-1].rsplit("::", 1)[-1]
    return sanitize_lean_namespace(f"{leaf}_operational_ir")


def key_value_lines(name: str, values: Sequence[tuple[str, str]]) -> list[str]:
    """Render a Lean definition containing key-value metadata."""
    if not values:
        return [f"def {name} : List KeyValue := []"]
    lines = [f"def {name} : List KeyValue := ["]
    for key, value in values:
        lines.append(f"  {{ key := {lean_string(key)}, value := {lean_string(value)} }},")
    lines.append("]")
    return lines


def selected_key_values(
    prefix: str,
    row: Mapping[str, object],
    keys: Sequence[str],
) -> tuple[tuple[str, str], ...]:
    """Return selected non-empty JSON fields as key-value rows."""
    values: list[tuple[str, str]] = []
    for key in keys:
        if key in row:
            values.append((f"{prefix}.{key}", string_field(row, key)))
    return tuple(values)


def collect_provenance(record: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    """Collect stable source provenance fields from an input envelope."""
    schema = string_field(record, "schema")
    values: list[tuple[str, str]] = [("schema", schema)]
    root = optional_mapping(record.get("root"))
    source_root = optional_mapping(record.get("source_root"))
    values.extend(
        selected_key_values(
            "root",
            root,
            (
                "schema",
                "source_kind",
                "cpp_symbol",
                "python_symbol",
                "source_path",
                "qualname",
                "repo_root",
            ),
        )
    )
    values.extend(
        selected_key_values(
            "source_root",
            source_root,
            (
                "schema",
                "status",
                "path",
                "relative_path",
                "qualname",
                "name",
                "source_sha256",
                "file_sha256",
                "source_span",
            ),
        )
    )
    return tuple(values)


def collect_public_interface(record: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    """Collect public-interface evidence fields from an input envelope."""
    public_interface = optional_mapping(record.get("public_interface"))
    if not public_interface:
        return ()
    values = list(
        selected_key_values(
            "public_interface",
            public_interface,
            ("schema", "status", "cpp_symbol", "python_symbol", "qualname", "name", "return_type"),
        )
    )
    if "parameters" in public_interface:
        values.append(
            (
                "public_interface.parameters_json",
                JSON_METADATA_ENCODER.encode(public_interface["parameters"]),
            )
        )
    if "return_roots" in public_interface:
        values.append(
            (
                "public_interface.return_roots_json",
                JSON_METADATA_ENCODER.encode(public_interface["return_roots"]),
            )
        )
    if "return_leaves" in public_interface:
        values.append(
            (
                "public_interface.return_leaves_json",
                JSON_METADATA_ENCODER.encode(public_interface["return_leaves"]),
            )
        )
    if "coverage" in public_interface:
        values.append(
            (
                "public_interface.coverage_json",
                JSON_METADATA_ENCODER.encode(public_interface["coverage"]),
            )
        )
    return tuple(values)


def normalize_render_input(record: Mapping[str, object]) -> RenderInput:
    """Normalize a source or direct thin-operational-IR record for rendering."""
    input_schema = string_field(record, "schema")
    if input_schema == THIN_OPERATIONAL_IR_SCHEMA:
        operational_ir = record
        source_facts: tuple[Mapping[str, object], ...] = ()
    else:
        operational_ir = object_mapping(record.get("operational_ir"), "operational_ir")
        source_facts_record = optional_mapping(record.get("source_facts"))
        source_facts = mapping_list(source_facts_record.get("facts", []), "source_facts.facts")
    operational_schema = string_field(operational_ir, "schema")
    if operational_schema != THIN_OPERATIONAL_IR_SCHEMA:
        raise ValueError(
            f"operational_ir schema must be {THIN_OPERATIONAL_IR_SCHEMA}, got {operational_schema}"
        )
    return RenderInput(
        input_schema=input_schema,
        module_name=default_module_name(record),
        provenance=collect_provenance(record),
        public_interface=collect_public_interface(record),
        source_facts=source_facts,
        operational_ir=operational_ir,
    )


def render_source_fact(row: Mapping[str, object]) -> str:
    """Render one source-fact row."""
    return (
        "{ "
        f"factId := {lean_string(string_field(row, 'fact_id'))}, "
        f"sourcePath := {lean_string(string_field(row, 'source_path'))}, "
        f"sourceSymbol := {lean_string(string_field(row, 'source_symbol'))}, "
        f"sourceSpan := {lean_string(string_field(row, 'source_span'))}, "
        f"factKind := {lean_string(string_field(row, 'fact_kind'))}, "
        f"target := {lean_string(string_field(row, 'target'))}, "
        f"expression := {lean_string(string_field(row, 'expression'))}, "
        f"statement := {lean_string(string_field(row, 'statement'))}, "
        f"textSha256 := {lean_string(string_field(row, 'text_sha256'))} "
        "}"
    )


def render_source_facts(rows: Sequence[Mapping[str, object]]) -> list[str]:
    """Render all source facts."""
    if not rows:
        return ["def sourceFacts : List SourceFact := []"]
    lines = ["def sourceFacts : List SourceFact := ["]
    for row in rows:
        lines.append(f"  {render_source_fact(row)},")
    lines.append("]")
    return lines


def op_metadata(row: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    """Return non-standard op fields as metadata."""
    metadata: list[tuple[str, str]] = []
    for key in sorted(row):
        if key not in STANDARD_OP_FIELDS:
            metadata.append(
                (
                    key,
                    JSON_METADATA_ENCODER.encode(row[key]),
                )
            )
    return tuple(metadata)


def render_metadata(values: Sequence[tuple[str, str]]) -> str:
    """Render inline key-value metadata."""
    if not values:
        return "[]"
    items = [
        f"{{ key := {lean_string(key)}, value := {lean_string(value)} }}"
        for key, value in values
    ]
    return "[" + ", ".join(items) + "]"


def render_function(row: Mapping[str, object]) -> str:
    """Render one operational function row."""
    return (
        "{ "
        f"functionId := {lean_string(string_field(row, 'function_id'))}, "
        f"name := {lean_string(string_field(row, 'name'))}, "
        f"signature := {lean_string(string_field(row, 'signature'))}, "
        f"lineStart := {lean_nat(int_field(row, 'line_start'))}, "
        f"lineEnd := {lean_nat(int_field(row, 'line_end'))}, "
        f"bodyRegionId := {lean_string(string_field(row, 'body_region_id'))} "
        "}"
    )


def render_region(row: Mapping[str, object]) -> str:
    """Render one operational region row."""
    op_ids = string_list(row.get("op_ids", []), "region.op_ids")
    return (
        "{ "
        f"regionId := {lean_string(string_field(row, 'region_id'))}, "
        f"kind := {lean_string(string_field(row, 'kind'))}, "
        f"parentFunction := {lean_string(string_field(row, 'parent_function'))}, "
        f"parentOpId := {lean_string(string_field(row, 'parent_op_id'))}, "
        f"depth := {lean_nat(int_field(row, 'depth'))}, "
        f"lineStart := {lean_nat(int_field(row, 'line_start'))}, "
        f"lineEnd := {lean_nat(int_field(row, 'line_end'))}, "
        f"opIds := {lean_string_list(op_ids)} "
        "}"
    )


def render_edge(row: Mapping[str, object]) -> str:
    """Render one expansion edge row."""
    return (
        "{ "
        f"edgeId := {lean_string(string_field(row, 'edge_id'))}, "
        f"kind := {lean_string(string_field(row, 'kind'))}, "
        f"fromNode := {lean_string(string_field(row, 'from'))}, "
        f"toNode := {lean_string(string_field(row, 'to'))} "
        "}"
    )


def render_op(row: Mapping[str, object]) -> str:
    """Render one operational op row."""
    tensor_types = string_list(row.get("tensor_types", []), "op.tensor_types")
    dtypes = string_list(row.get("dtypes", []), "op.dtypes")
    return (
        "{ "
        f"opId := {lean_string(string_field(row, 'op_id'))}, "
        f"kind := {lean_string(string_field(row, 'kind'))}, "
        f"opcode := {lean_string(string_field(row, 'opcode'))}, "
        f"line := {lean_nat(int_field(row, 'line'))}, "
        f"text := {lean_string(string_field(row, 'text'))}, "
        f"textSha256 := {lean_string(string_field(row, 'text_sha256'))}, "
        f"tensorTypes := {lean_string_list(tensor_types)}, "
        f"dtypes := {lean_string_list(dtypes)}, "
        f"functionName := {lean_string(string_field(row, 'function'))}, "
        f"regionId := {lean_string(string_field(row, 'region_id'))}, "
        f"parentOpId := {lean_string(string_field(row, 'parent_op_id'))}, "
        f"callTarget := {lean_string(string_field(row, 'call_target'))}, "
        f"metadata := {render_metadata(op_metadata(row))} "
        "}"
    )


def render_code_path_decision(row: Mapping[str, object]) -> str:
    """Render one code-path decision row."""
    return (
        "{ "
        f"opId := {lean_string(string_field(row, 'op_id'))}, "
        f"kind := {lean_string(string_field(row, 'kind'))}, "
        f"choice := {lean_string(string_field(row, 'choice'))}, "
        f"condition := {lean_string(string_field(row, 'condition'))}, "
        f"line := {lean_nat(int_field(row, 'line'))} "
        "}"
    )


def render_code_path_decisions(rows: Sequence[Mapping[str, object]]) -> str:
    """Render a Lean list of code-path decision rows."""
    if not rows:
        return "[]"
    return "[" + ", ".join(render_code_path_decision(row) for row in rows) + "]"


def render_code_path(row: Mapping[str, object]) -> str:
    """Render one code-path row."""
    op_ids = string_list(row.get("op_ids", []), "code_path.op_ids")
    decisions = mapping_list(row.get("decisions", []), "code_path.decisions")
    return (
        "{ "
        f"pathId := {lean_string(string_field(row, 'path_id'))}, "
        f"functionName := {lean_string(string_field(row, 'function'))}, "
        f"regionId := {lean_string(string_field(row, 'region_id'))}, "
        f"opIds := {lean_string_list(op_ids)}, "
        f"decisions := {render_code_path_decisions(decisions)}, "
        f"decisionCount := {lean_nat(int_field(row, 'decision_count'))}, "
        f"summary := {lean_string(string_field(row, 'summary'))} "
        "}"
    )


def render_rows(
    definition_name: str,
    lean_type: str,
    rows: Sequence[Mapping[str, object]],
    row_renderer: Callable[[Mapping[str, object]], str],
) -> list[str]:
    """Render a Lean list definition for table rows."""
    if not rows:
        return [f"def {definition_name} : List {lean_type} := []"]
    lines = [f"def {definition_name} : List {lean_type} := ["]
    for row in rows:
        lines.append(f"  {row_renderer(row)},")
    lines.append("]")
    return lines


def coverage_metadata(row: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    """Return non-standard coverage fields as metadata."""
    metadata: list[tuple[str, str]] = []
    for key in sorted(row):
        if key not in STANDARD_COVERAGE_FIELDS:
            metadata.append(
                (
                    key,
                    JSON_METADATA_ENCODER.encode(row[key]),
                )
            )
    return tuple(metadata)


def render_coverage(row: Mapping[str, object]) -> list[str]:
    """Render the operational coverage definition."""
    unassigned_ids = required_string_list(row, "unassigned_op_ids")
    unresolved_targets = required_string_list(row, "unresolved_call_targets")
    unmapped_code_path_functions = required_string_list(row, "unmapped_code_path_functions")
    return [
        "def operationalCoverage : OperationalCoverage := {",
        f"  functionCount := {lean_nat(required_int_field(row, 'function_count'))},",
        f"  regionCount := {lean_nat(required_int_field(row, 'region_count'))},",
        f"  expansionEdgeCount := {lean_nat(required_int_field(row, 'expansion_edge_count'))},",
        f"  opCount := {lean_nat(required_int_field(row, 'op_count'))},",
        f"  assignedRegionCount := {lean_nat(required_int_field(row, 'assigned_region_count'))},",
        f"  unassignedOpCount := {lean_nat(required_int_field(row, 'unassigned_op_count'))},",
        f"  unassignedOpIds := {lean_string_list(unassigned_ids)},",
        f"  unresolvedCallTargets := {lean_string_list(unresolved_targets)},",
        f"  maxRegionDepth := {lean_nat(required_int_field(row, 'max_region_depth'))},",
        f"  whileCount := {lean_nat(required_int_field(row, 'while_count'))},",
        f"  caseCount := {lean_nat(required_int_field(row, 'case_count'))},",
        f"  ifCount := {lean_nat(required_int_field(row, 'if_count'))},",
        f"  callCount := {lean_nat(required_int_field(row, 'call_count'))},",
        f"  codePathCount := {lean_nat(required_int_field(row, 'code_path_count'))},",
        "  codePathDecisionCount := "
        f"{lean_nat(required_int_field(row, 'code_path_decision_count'))},",
        "  maxCodePathDecisions := "
        f"{lean_nat(required_int_field(row, 'max_code_path_decisions'))},",
        f"  unmappedCodePathFunctions := {lean_string_list(unmapped_code_path_functions)},",
        f"  metadata := {render_metadata(coverage_metadata(row))}",
        "}",
        "",
        "def unresolvedCallTargets : List String := operationalCoverage.unresolvedCallTargets",
        "def unmappedCodePathFunctions : List String :=",
        "  operationalCoverage.unmappedCodePathFunctions",
        "def codePathCoverageComplete : Bool :=",
        "  operationalCoverage.unmappedCodePathFunctions.isEmpty &&",
        "  operationalCoverage.codePathCount >= operationalCoverage.functionCount",
        "def coverageComplete : Bool :=",
        "  operationalCoverage.unresolvedCallTargets.isEmpty &&",
        "  operationalCoverage.unassignedOpCount == 0 &&",
        "  codePathCoverageComplete",
    ]


def render_base_structures() -> list[str]:
    """Render common Lean structure definitions."""
    return [
        "structure KeyValue where",
        "  key : String",
        "  value : String",
        "deriving Repr, DecidableEq",
        "",
        "structure SourceFact where",
        "  factId : String",
        "  sourcePath : String",
        "  sourceSymbol : String",
        "  sourceSpan : String",
        "  factKind : String",
        "  target : String",
        "  expression : String",
        "  statement : String",
        "  textSha256 : String",
        "deriving Repr, DecidableEq",
        "",
        "structure OperationalFunction where",
        "  functionId : String",
        "  name : String",
        "  signature : String",
        "  lineStart : Nat",
        "  lineEnd : Nat",
        "  bodyRegionId : String",
        "deriving Repr, DecidableEq",
        "",
        "structure OperationalRegion where",
        "  regionId : String",
        "  kind : String",
        "  parentFunction : String",
        "  parentOpId : String",
        "  depth : Nat",
        "  lineStart : Nat",
        "  lineEnd : Nat",
        "  opIds : List String",
        "deriving Repr, DecidableEq",
        "",
        "structure ExpansionEdge where",
        "  edgeId : String",
        "  kind : String",
        "  fromNode : String",
        "  toNode : String",
        "deriving Repr, DecidableEq",
        "",
        "structure OperationalOp where",
        "  opId : String",
        "  kind : String",
        "  opcode : String",
        "  line : Nat",
        "  text : String",
        "  textSha256 : String",
        "  tensorTypes : List String",
        "  dtypes : List String",
        "  functionName : String",
        "  regionId : String",
        "  parentOpId : String",
        "  callTarget : String",
        "  metadata : List KeyValue",
        "deriving Repr, DecidableEq",
        "",
    ]


def render_code_path_structures() -> list[str]:
    """Render code-path Lean structure definitions."""
    return [
        "structure CodePathDecision where",
        "  opId : String",
        "  kind : String",
        "  choice : String",
        "  condition : String",
        "  line : Nat",
        "deriving Repr, DecidableEq",
        "",
        "structure CodePath where",
        "  pathId : String",
        "  functionName : String",
        "  regionId : String",
        "  opIds : List String",
        "  decisions : List CodePathDecision",
        "  decisionCount : Nat",
        "  summary : String",
        "deriving Repr, DecidableEq",
        "",
    ]


def render_coverage_structure() -> list[str]:
    """Render operational coverage Lean structure definitions."""
    return [
        "structure OperationalCoverage where",
        "  functionCount : Nat",
        "  regionCount : Nat",
        "  expansionEdgeCount : Nat",
        "  opCount : Nat",
        "  assignedRegionCount : Nat",
        "  unassignedOpCount : Nat",
        "  unassignedOpIds : List String",
        "  unresolvedCallTargets : List String",
        "  maxRegionDepth : Nat",
        "  whileCount : Nat",
        "  caseCount : Nat",
        "  ifCount : Nat",
        "  callCount : Nat",
        "  codePathCount : Nat",
        "  codePathDecisionCount : Nat",
        "  maxCodePathDecisions : Nat",
        "  unmappedCodePathFunctions : List String",
        "  metadata : List KeyValue",
        "deriving Repr, DecidableEq",
    ]


def render_structures() -> list[str]:
    """Render shared Lean structure definitions."""
    return [
        *render_base_structures(),
        *render_code_path_structures(),
        *render_coverage_structure(),
    ]


def render_lean(
    render_input: RenderInput,
    *,
    namespace: str,
    module_name: str,
) -> str:
    """Render one normalized input packet as a Lean evidence module."""
    operational_ir = render_input.operational_ir
    functions = mapping_list(operational_ir.get("functions", []), "operational_ir.functions")
    regions = mapping_list(operational_ir.get("regions", []), "operational_ir.regions")
    edges = mapping_list(
        operational_ir.get("expansion_edges", []),
        "operational_ir.expansion_edges",
    )
    code_paths = mapping_list(operational_ir.get("code_paths", []), "operational_ir.code_paths")
    ops = mapping_list(operational_ir.get("ops", []), "operational_ir.ops")
    coverage = object_mapping(operational_ir.get("coverage"), "operational_ir.coverage")
    allowed_kinds = string_list(operational_ir.get("allowed_kinds", []), "allowed_kinds")
    function_signatures = string_list(
        operational_ir.get("function_signatures", []),
        "function_signatures",
    )

    lines = [
        "/- Generated by tools/agent_tools/operational_ir_to_lean.py. -/",
        "/- Evidence data only: semantic proof obligations live in theorem packages. -/",
        f"namespace {namespace}",
        f"namespace {module_name}",
        "",
    ]
    lines.extend(render_structures())
    lines.extend(
        [
            "",
            f"def inputSchema : String := {lean_string(render_input.input_schema)}",
            f"def operationalIrSchema : String := {lean_string(THIN_OPERATIONAL_IR_SCHEMA)}",
            f"def allowedKinds : List String := {lean_string_list(allowed_kinds)}",
            f"def functionSignatures : List String := {lean_string_list(function_signatures)}",
            "",
        ]
    )
    lines.extend(key_value_lines("inputProvenance", render_input.provenance))
    lines.append("")
    lines.extend(key_value_lines("publicInterfaceFields", render_input.public_interface))
    lines.append("")
    lines.extend(render_source_facts(render_input.source_facts))
    lines.append("")
    lines.extend(
        render_rows(
            "operationalFunctions",
            "OperationalFunction",
            functions,
            render_function,
        )
    )
    lines.append("")
    lines.extend(render_rows("operationalRegions", "OperationalRegion", regions, render_region))
    lines.append("")
    lines.extend(render_rows("expansionEdges", "ExpansionEdge", edges, render_edge))
    lines.append("")
    lines.extend(render_rows("codePaths", "CodePath", code_paths, render_code_path))
    lines.append("")
    lines.extend(render_rows("operationalOps", "OperationalOp", ops, render_op))
    lines.append("")
    lines.extend(render_coverage(coverage))
    lines.extend(["", f"end {module_name}", f"end {namespace}", ""])
    return "\n".join(lines)


def enforce_complete_coverage(render_input: RenderInput) -> None:
    """Reject inputs with incomplete operational coverage."""
    coverage = object_mapping(
        render_input.operational_ir.get("coverage"),
        "operational_ir.coverage",
    )
    unresolved = required_string_list(coverage, "unresolved_call_targets")
    unassigned = required_int_field(coverage, "unassigned_op_count")
    unmapped_code_path_functions = required_string_list(
        coverage,
        "unmapped_code_path_functions",
    )
    code_path_count = required_int_field(coverage, "code_path_count")
    function_count = required_int_field(coverage, "function_count")
    if unresolved or unassigned or unmapped_code_path_functions or code_path_count < function_count:
        unresolved_text = ", ".join(unresolved) if unresolved else "<none>"
        unmapped_text = (
            ", ".join(unmapped_code_path_functions)
            if unmapped_code_path_functions
            else "<none>"
        )
        raise ValueError(
            "incomplete operational coverage: "
            f"unresolved_call_targets=[{unresolved_text}], "
            f"unassigned_op_count={unassigned}, "
            f"unmapped_code_path_functions=[{unmapped_text}], "
            f"code_path_count={code_path_count}, "
            f"function_count={function_count}"
        )


def load_record(path: Path) -> Mapping[str, object]:
    """Load one JSON record from disk."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"unable to read input JSON: {path}: {exc.strerror}") from exc
    try:
        payload = json.loads(raw)
    except JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg}") from exc
    return object_mapping(payload, "input")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ir",
        required=True,
        help="Input JSON: thin operational IR or an envelope containing operational_ir.",
    )
    parser.add_argument("--namespace", required=True, help="Lean namespace for generated evidence.")
    parser.add_argument(
        "--module-name",
        help="Nested Lean namespace for this generated module. Defaults from root metadata.",
    )
    parser.add_argument("--out", help="Optional output path. When omitted, print to stdout.")
    return parser.parse_args(list(argv))


def main(argv: Sequence[str]) -> int:
    """Run the operational IR to Lean renderer."""
    args = parse_args(argv)
    try:
        namespace = validate_namespace(str(args.namespace))
        record = load_record(Path(args.ir))
        render_input = normalize_render_input(record)
        module_name = validate_namespace(str(args.module_name or render_input.module_name))
        enforce_complete_coverage(render_input)
        rendered = render_lean(render_input, namespace=namespace, module_name=module_name)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
