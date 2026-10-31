// @dependency-start
// contract tool
// responsibility Traces scoped StableHLO SSA value dependencies from JIT-canonical operational IR.
// upstream implementation ../../../../../tools/analysis/proof/jit_canonical_ir.py emits operational_ir functions, regions, and ops.
// upstream implementation jit_ir_to_lean.rs consumes the matching Lean operational op fields.
// downstream implementation theorem_graph_circularity_check.rs consumes closure frontiers when theorem graph leaves are audited.
// downstream test ../../../../../tests/agent_tools/test_stablehlo_value_closure.py preserves the scoped closure oracles.
// @dependency-end

//! Scoped StableHLO SSA closure over JIT-canonical operational IR.
//!
//! The analysis deliberately keeps SSA names scoped by function and region.

use regex::Regex;
use serde::Serialize;
use serde_json::{Map, Value};
use std::collections::{HashMap, HashSet, VecDeque};
use std::fs;
use std::path::Path;
use std::sync::LazyLock;

pub const SELECTOR: &str = "stablehlo-value-closure";
pub const DEFAULT_MAX_NODES: i64 = 1000;
const IR_SCHEMA: &str = "agent-canon.thin-operational-ir.v2";
const REPORT_SCHEMA: &str = "agent-canon.stablehlo-value-closure.v1";

static PERCENT_NAME_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"%[A-Za-z0-9_#.]+(?::[0-9]+)?").expect("static SSA value pattern")
});
static CONSTANT_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"(?P<result>%[A-Za-z0-9_#.]+)\s*=\s*stablehlo\.constant\s+dense<(?P<literal>[^>]+)>\s*:\s*tensor<(?P<tensor_type>[^>]+)>",
    )
    .expect("static StableHLO constant pattern")
});
static CONVERT_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"(?P<result>%[A-Za-z0-9_#.]+)\s*=\s*stablehlo\.convert\s+(?P<operand>%[A-Za-z0-9_#.]+)\s*:\s*\(tensor<(?P<from_tensor_type>[^>]+)>\)\s*->\s*tensor<(?P<to_tensor_type>[^>]+)>",
    )
    .expect("static StableHLO convert pattern")
});

#[derive(Clone, Debug, Eq, Hash, PartialEq, Serialize)]
pub struct ScopedValue {
    pub function: String,
    pub region_id: String,
    pub name: String,
}

impl ScopedValue {
    pub fn new(
        function: impl Into<String>,
        region_id: impl Into<String>,
        name: impl Into<String>,
    ) -> Self {
        Self {
            function: function.into(),
            region_id: region_id.into(),
            name: name.into(),
        }
    }

    pub fn key(&self) -> String {
        format!("{}:{}:{}", self.function, self.region_id, self.name)
    }
}

#[derive(Clone, Debug, Default)]
pub struct OperationalIr {
    functions: Vec<FunctionRecord>,
    regions: Vec<RegionRecord>,
    ops: Vec<Operation>,
}

#[derive(Clone, Debug)]
struct FunctionRecord {
    name: String,
    body_region_id: String,
    argument_names: Vec<String>,
}

#[derive(Clone, Debug)]
struct RegionRecord {
    region_id: String,
    parent_op_id: String,
    op_ids: PythonMembership,
}

#[derive(Clone, Debug)]
enum PythonMembership {
    Empty,
    Sequence(Vec<Value>),
    String(String),
    ObjectKeys(HashSet<String>),
}

impl PythonMembership {
    fn from_or_default(value: Option<&Value>, field: &str) -> Result<Self, String> {
        let Some(value) = value.filter(|value| value_truthy(value)) else {
            return Ok(Self::Empty);
        };
        match value {
            Value::Array(items) => Ok(Self::Sequence(items.clone())),
            Value::String(text) => Ok(Self::String(text.clone())),
            Value::Object(object) => Ok(Self::ObjectKeys(object.keys().cloned().collect())),
            Value::Number(_) => Err(format!("{field}: expected an iterable value, got number")),
            Value::Bool(_) => Err(format!("{field}: expected an iterable value, got boolean")),
            Value::Null => Ok(Self::Empty),
        }
    }

    fn contains(&self, item: &str) -> bool {
        match self {
            Self::Empty => false,
            Self::Sequence(items) => items
                .iter()
                .any(|value| value == &Value::String(item.into())),
            Self::String(text) => text.contains(item),
            Self::ObjectKeys(keys) => keys.contains(item),
        }
    }
}

#[derive(Clone, Debug)]
struct Operation {
    op_id: String,
    kind: String,
    opcode: String,
    function: String,
    region_id: String,
    parent_op_id: String,
    call_target: String,
    line: i64,
    text: String,
    result_names: Vec<String>,
    operand_names: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct OperationRow {
    pub op_id: String,
    pub kind: String,
    pub opcode: String,
    pub function: String,
    pub region_id: String,
    pub line: i64,
    pub result_names: Vec<String>,
    pub operand_names: Vec<String>,
    pub call_target: String,
    pub text: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct ConstantPayloadRow {
    pub op_id: String,
    pub function: String,
    pub region_id: String,
    pub line: i64,
    pub result_name: String,
    pub dense_literal: String,
    pub tensor_type: String,
    pub dtype: String,
    pub text: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct ConvertOpRow {
    pub op_id: String,
    pub function: String,
    pub region_id: String,
    pub line: i64,
    pub result_name: String,
    pub operand_name: String,
    pub from_tensor_type: String,
    pub to_tensor_type: String,
    pub from_dtype: String,
    pub to_dtype: String,
    pub text: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct ClosureLeaf {
    pub kind: String,
    pub value: String,
    pub function: String,
    pub region_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mapped_to: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub producer_op_id: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ClosureEdge {
    pub source: String,
    pub target: String,
    pub kind: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct ClosureReport {
    pub schema: &'static str,
    pub root: ScopedValue,
    pub value_count: usize,
    pub op_count: usize,
    pub leaf_count: usize,
    pub constant_payload_count: usize,
    pub convert_op_count: usize,
    pub truncated: bool,
    pub ops: Vec<OperationRow>,
    pub constant_payloads: Vec<ConstantPayloadRow>,
    pub convert_ops: Vec<ConvertOpRow>,
    pub leaves: Vec<ClosureLeaf>,
    pub edges: Vec<ClosureEdge>,
}

pub fn parse_operational_ir(value: &Value) -> Result<OperationalIr, String> {
    let payload = value
        .get("operational_ir")
        .filter(|nested| !nested.is_null())
        .unwrap_or(value);
    let object = payload
        .as_object()
        .ok_or_else(|| "operational_ir must be a JSON object".to_string())?;
    if object.get("schema").and_then(Value::as_str) != Some(IR_SCHEMA) {
        return Err("unsupported or missing operational_ir schema".into());
    }
    let functions = object
        .get("functions")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_object)
        .map(|function| {
            let argument_names = if let Some(names) = function.get("argument_names") {
                field_string_list(Some(names), "argument_names")?
            } else if let Some(names) = function.get("argumentNames") {
                field_string_list(Some(names), "argumentNames")?
            } else {
                function_argument_names(&field_string(function, &["signature"]))
            };
            Ok(FunctionRecord {
                name: field_string(function, &["name"]),
                body_region_id: first_nonempty(function, &["body_region_id", "bodyRegionId"]),
                argument_names,
            })
        })
        .collect::<Result<Vec<_>, String>>()?;
    let regions = object
        .get("regions")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_object)
        .map(|region| {
            Ok(RegionRecord {
                region_id: field_string(region, &["region_id", "regionId"]),
                parent_op_id: field_string(region, &["parent_op_id", "parentOpId"]),
                op_ids: PythonMembership::from_or_default(
                    region.get("op_ids").or_else(|| region.get("opIds")),
                    "op_ids",
                )?,
            })
        })
        .collect::<Result<Vec<_>, String>>()?;
    let ops = object
        .get("ops")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_object)
        .map(parse_operation)
        .collect::<Result<Vec<_>, String>>()?;
    Ok(OperationalIr {
        functions,
        regions,
        ops,
    })
}

fn parse_operation(raw: &Map<String, Value>) -> Result<Operation, String> {
    let text = field_string(raw, &["text"]);
    let result_names = field_string_list_alias(raw, "result_names", "resultNames")?
        .filter(|items| !items.is_empty())
        .unwrap_or_else(|| result_names(&text));
    let operand_names = field_string_list_alias(raw, "operand_names", "operandNames")?
        .filter(|items| !items.is_empty())
        .unwrap_or_else(|| operand_names(&text, &result_names));
    Ok(Operation {
        op_id: first_nonempty(raw, &["op_id", "opId"]),
        kind: first_nonempty(raw, &["kind"]),
        opcode: first_nonempty(raw, &["opcode"]),
        function: first_nonempty(raw, &["function", "functionName"]),
        region_id: first_nonempty(raw, &["region_id", "regionId"]),
        parent_op_id: first_nonempty(raw, &["parent_op_id", "parentOpId"]),
        call_target: first_nonempty(raw, &["call_target", "callTarget"]),
        line: raw.get("line").map_or(0, value_i64),
        text,
        result_names,
        operand_names,
    })
}

fn field_string(object: &Map<String, Value>, names: &[&str]) -> String {
    names
        .iter()
        .find_map(|name| object.get(*name).filter(|value| !value.is_null()))
        .map(value_string)
        .unwrap_or_default()
}

fn first_nonempty(object: &Map<String, Value>, names: &[&str]) -> String {
    names
        .iter()
        .find_map(|name| {
            object
                .get(*name)
                .filter(|value| value_truthy(value))
                .map(value_string)
        })
        .unwrap_or_default()
}

fn value_string(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::Number(number) => number.to_string(),
        Value::Array(_) => format!("{value}"),
        Value::Object(_) => format!("{value}"),
    }
}

fn value_i64(value: &Value) -> i64 {
    value
        .as_i64()
        .or_else(|| value.as_bool().map(i64::from))
        .or_else(|| value.as_str().and_then(|text| text.parse().ok()))
        .unwrap_or(0)
}

fn value_truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(value) => *value,
        Value::Number(number) => number.as_f64().is_some_and(|value| value != 0.0),
        Value::String(value) => !value.is_empty(),
        Value::Array(value) => !value.is_empty(),
        Value::Object(value) => !value.is_empty(),
    }
}

fn field_string_list_alias(
    object: &Map<String, Value>,
    first: &str,
    second: &str,
) -> Result<Option<Vec<String>>, String> {
    let selected = object
        .get(first)
        .filter(|value| value_truthy(value))
        .map(|value| (first, value))
        .or_else(|| {
            object
                .get(second)
                .filter(|value| value_truthy(value))
                .map(|value| (second, value))
        });
    selected
        .map(|(field, value)| field_string_list(Some(value), field))
        .transpose()
}

fn field_string_list(value: Option<&Value>, field: &str) -> Result<Vec<String>, String> {
    match value {
        Some(Value::Array(items)) => items
            .iter()
            .map(|item| {
                item.as_str()
                    .map(ToOwned::to_owned)
                    .ok_or_else(|| format!("{field}: expected string items in iterable value"))
            })
            .collect(),
        Some(Value::String(text)) => Ok(text.chars().map(|ch| ch.to_string()).collect()),
        Some(Value::Object(object)) => Ok(object.keys().cloned().collect()),
        Some(Value::Number(_)) => Err(format!("{field}: expected an iterable value, got number")),
        Some(Value::Bool(_)) => Err(format!("{field}: expected an iterable value, got boolean")),
        Some(Value::Null) => Err(format!("{field}: expected an iterable value, got null")),
        None => Ok(vec![]),
    }
}

fn percent_names(text: &str) -> Vec<String> {
    PERCENT_NAME_RE
        .find_iter(text)
        .map(|found| {
            found
                .as_str()
                .split(':')
                .next()
                .unwrap_or(found.as_str())
                .to_string()
        })
        .collect()
}

fn return_operands(text: &str) -> Vec<String> {
    let stripped = text.trim();
    let rest = stripped
        .strip_prefix("stablehlo.return ")
        .or_else(|| stripped.strip_prefix("return "));
    rest.map(|rest| {
        rest.split_once(" : ")
            .map(|(operands, _)| operands)
            .unwrap_or(rest)
            .split(',')
            .map(str::trim)
            .filter(|part| !part.is_empty())
            .map(ToOwned::to_owned)
            .collect()
    })
    .unwrap_or_default()
}

fn result_names(text: &str) -> Vec<String> {
    let Some((lhs, _)) = text.split_once(" = ") else {
        return vec![];
    };
    let mut names = vec![];
    for found in PERCENT_NAME_RE.find_iter(lhs) {
        let raw = found.as_str();
        if let Some((base, count_text)) = raw.split_once(':') {
            if let Ok(count) = count_text.parse::<usize>() {
                names.extend((0..count).map(|index| format!("{base}#{index}")));
                names.push(base.to_string());
            } else {
                names.push(base.to_string());
            }
        } else {
            names.push(raw.to_string());
        }
    }
    names
}

fn operand_names(text: &str, results: &[String]) -> Vec<String> {
    let stripped = text.trim();
    let names = if stripped.starts_with("stablehlo.return ") || stripped.starts_with("return ") {
        return_operands(stripped)
    } else if let Some((_, rhs)) = text.split_once(" = ") {
        let while_names = while_initial_operands(rhs);
        if while_names.is_empty() {
            percent_names(rhs)
        } else {
            while_names
        }
    } else {
        percent_names(text)
    };
    names
        .into_iter()
        .filter(|name| !results.contains(name))
        .collect()
}

fn while_initial_operands(rhs: &str) -> Vec<String> {
    let Some(body) = rhs
        .trim_start()
        .strip_prefix("stablehlo.while(")
        .and_then(|body| body.split_once(") :").map(|(body, _)| body))
    else {
        return vec![];
    };
    body.split(',')
        .filter_map(|part| part.split_once(" = ").map(|(_, value)| value))
        .filter_map(|value| percent_names(value).into_iter().next())
        .collect()
}

fn function_argument_names(signature: &str) -> Vec<String> {
    let Some(after_open) = signature.split_once('(').map(|(_, rest)| rest) else {
        return vec![];
    };
    let Some(arguments) = after_open.split_once(')').map(|(args, _)| args) else {
        return vec![];
    };
    percent_names(arguments)
}

fn scalar_dtype(tensor_type: &str) -> String {
    let text = tensor_type.trim();
    text.rsplit_once('x')
        .map(|(_, suffix)| suffix)
        .unwrap_or(text)
        .to_string()
}

fn function_map(ir: &OperationalIr) -> HashMap<&str, &FunctionRecord> {
    ir.functions
        .iter()
        .map(|function| (function.name.as_str(), function))
        .collect()
}

fn region_map(ir: &OperationalIr) -> HashMap<&str, &RegionRecord> {
    ir.regions
        .iter()
        .map(|region| (region.region_id.as_str(), region))
        .collect()
}

fn function_body_region<'a>(
    functions: &HashMap<&'a str, &'a FunctionRecord>,
    function: &str,
) -> String {
    functions
        .get(function)
        .map(|record| record.body_region_id.clone())
        .unwrap_or_default()
}

fn function_args<'a>(
    functions: &HashMap<&'a str, &'a FunctionRecord>,
    function: &str,
) -> Vec<String> {
    functions
        .get(function)
        .map(|record| record.argument_names.clone())
        .unwrap_or_default()
}

fn region_ancestors<'a>(
    regions: &HashMap<&'a str, &'a RegionRecord>,
    region_id: &str,
) -> Vec<String> {
    let mut path = vec![];
    let mut current = region_id.to_string();
    let mut seen = HashSet::new();
    while !current.is_empty() && seen.insert(current.clone()) {
        path.push(current.clone());
        let parent_op_id = regions
            .get(current.as_str())
            .map(|region| region.parent_op_id.as_str())
            .unwrap_or_default();
        if parent_op_id.is_empty() {
            break;
        }
        current = regions
            .values()
            .find(|region| region.op_ids.contains(parent_op_id))
            .map(|region| region.region_id.clone())
            .unwrap_or_default();
    }
    path
}

fn resolve_definition<'a, 'r>(
    by_value: &HashMap<(String, String, String), Vec<&'a Operation>>,
    regions: &HashMap<&'r str, &'r RegionRecord>,
    value: &ScopedValue,
) -> Option<&'a Operation> {
    for region_id in region_ancestors(regions, &value.region_id) {
        if let Some(candidates) =
            by_value.get(&(value.function.clone(), region_id, value.name.clone()))
        {
            return candidates.iter().max_by_key(|op| op.line).copied();
        }
    }
    None
}

fn operation_row(operation: &Operation) -> OperationRow {
    OperationRow {
        op_id: operation.op_id.clone(),
        kind: operation.kind.clone(),
        opcode: operation.opcode.clone(),
        function: operation.function.clone(),
        region_id: operation.region_id.clone(),
        line: operation.line,
        result_names: operation.result_names.clone(),
        operand_names: operation.operand_names.clone(),
        call_target: operation.call_target.clone(),
        text: operation.text.clone(),
    }
}

fn constant_payload_row(operation: &Operation) -> Option<ConstantPayloadRow> {
    if operation.opcode != "stablehlo.constant" {
        return None;
    }
    let captures = CONSTANT_RE.captures(&operation.text)?;
    let tensor_type = captures.name("tensor_type")?.as_str().to_string();
    Some(ConstantPayloadRow {
        op_id: operation.op_id.clone(),
        function: operation.function.clone(),
        region_id: operation.region_id.clone(),
        line: operation.line,
        result_name: captures.name("result")?.as_str().to_string(),
        dense_literal: captures.name("literal")?.as_str().to_string(),
        dtype: scalar_dtype(&tensor_type),
        tensor_type,
        text: operation.text.clone(),
    })
}

fn convert_op_row(operation: &Operation) -> Option<ConvertOpRow> {
    if operation.opcode != "stablehlo.convert" {
        return None;
    }
    let captures = CONVERT_RE.captures(&operation.text)?;
    let from_tensor_type = captures.name("from_tensor_type")?.as_str().to_string();
    let to_tensor_type = captures.name("to_tensor_type")?.as_str().to_string();
    Some(ConvertOpRow {
        op_id: operation.op_id.clone(),
        function: operation.function.clone(),
        region_id: operation.region_id.clone(),
        line: operation.line,
        result_name: captures.name("result")?.as_str().to_string(),
        operand_name: captures.name("operand")?.as_str().to_string(),
        from_dtype: scalar_dtype(&from_tensor_type),
        to_dtype: scalar_dtype(&to_tensor_type),
        from_tensor_type,
        to_tensor_type,
        text: operation.text.clone(),
    })
}

pub fn trace_value_closure(ir: &OperationalIr, root: ScopedValue, max_nodes: i64) -> ClosureReport {
    let functions = function_map(ir);
    let regions = region_map(ir);
    let mut op_by_id: HashMap<&str, &Operation> = HashMap::new();
    let mut by_value: HashMap<(String, String, String), Vec<&Operation>> = HashMap::new();
    for operation in &ir.ops {
        op_by_id.insert(operation.op_id.as_str(), operation);
        for name in &operation.result_names {
            by_value
                .entry((
                    operation.function.clone(),
                    operation.region_id.clone(),
                    name.clone(),
                ))
                .or_default()
                .push(operation);
        }
    }
    let mut queue = VecDeque::from([(
        root.clone(),
        HashMap::<String, ScopedValue>::new(),
        None::<String>,
    )]);
    let mut seen_values = HashSet::new();
    let mut op_rows: HashMap<String, OperationRow> = HashMap::new();
    let mut leaves: HashMap<String, ClosureLeaf> = HashMap::new();
    let mut edges = vec![];

    while !queue.is_empty() && (seen_values.len() as i64) < max_nodes {
        let (value, arg_map, via) = queue.pop_front().expect("queue checked nonempty");
        let key = value.key();
        if !seen_values.insert(key.clone()) {
            continue;
        }
        if let Some(mapped) = arg_map.get(&value.name) {
            leaves.insert(
                key.clone(),
                ClosureLeaf {
                    kind: "callee_argument_mapping".into(),
                    value: value.name.clone(),
                    function: value.function.clone(),
                    region_id: value.region_id.clone(),
                    mapped_to: Some(mapped.key()),
                    producer_op_id: None,
                },
            );
            queue.push_back((mapped.clone(), HashMap::new(), Some(key)));
            continue;
        }
        if function_args(&functions, &value.function).contains(&value.name) {
            leaves.insert(
                key,
                ClosureLeaf {
                    kind: "public_or_function_argument".into(),
                    value: value.name,
                    function: value.function,
                    region_id: value.region_id,
                    mapped_to: None,
                    producer_op_id: None,
                },
            );
            continue;
        }
        let mut definition = resolve_definition(&by_value, &regions, &value);
        if definition.is_none() && value.name.starts_with('%') && value.name.contains('#') {
            let base = value.name.split('#').next().unwrap_or(&value.name);
            definition = resolve_definition(
                &by_value,
                &regions,
                &ScopedValue::new(&value.function, &value.region_id, base),
            );
        }
        let Some(operation) = definition else {
            leaves.insert(
                key,
                ClosureLeaf {
                    kind: "unresolved_value".into(),
                    value: value.name,
                    function: value.function,
                    region_id: value.region_id,
                    mapped_to: None,
                    producer_op_id: None,
                },
            );
            continue;
        };
        op_rows.insert(operation.op_id.clone(), operation_row(operation));
        if let Some(source) = via {
            edges.push(ClosureEdge {
                source,
                target: key.clone(),
                kind: "depends_on".into(),
            });
        }
        for operand in &operation.operand_names {
            if operand.starts_with("%iterArg") {
                let leaf_key =
                    format!("{}:{}:{}", operation.function, operation.region_id, operand);
                leaves.insert(
                    leaf_key,
                    ClosureLeaf {
                        kind: "loop_region_argument".into(),
                        value: operand.clone(),
                        function: operation.function.clone(),
                        region_id: operation.region_id.clone(),
                        mapped_to: None,
                        producer_op_id: Some(operation.parent_op_id.clone()),
                    },
                );
                continue;
            }
            queue.push_back((
                ScopedValue::new(&operation.function, &operation.region_id, operand),
                arg_map.clone(),
                Some(key.clone()),
            ));
        }
        if operation.kind == "Call" && !operation.call_target.is_empty() {
            let callee = operation.call_target.as_str();
            let callee_arguments = function_args(&functions, callee);
            let callee_map: HashMap<String, ScopedValue> = callee_arguments
                .into_iter()
                .zip(operation.operand_names.iter())
                .map(|(argument, operand)| {
                    (
                        argument,
                        ScopedValue::new(&operation.function, &operation.region_id, operand),
                    )
                })
                .collect();
            let body_region = function_body_region(&functions, callee);
            let mut returns: Vec<&Operation> = ir
                .ops
                .iter()
                .filter(|candidate| {
                    candidate.function == callee
                        && candidate.region_id == body_region
                        && candidate.kind == "Return"
                })
                .collect();
            returns.sort_by_key(|operation| operation.line);
            for ret in returns {
                op_rows.insert(ret.op_id.clone(), operation_row(ret));
                for operand in &ret.operand_names {
                    queue.push_back((
                        ScopedValue::new(callee, &body_region, operand),
                        callee_map.clone(),
                        Some(key.clone()),
                    ));
                }
            }
        }
    }
    let mut operations: Vec<OperationRow> = op_rows.into_values().collect();
    operations.sort_by(|left, right| {
        (&left.function, left.line, &left.op_id).cmp(&(&right.function, right.line, &right.op_id))
    });
    let constant_payloads: Vec<_> = operations
        .iter()
        .filter_map(|row| {
            op_by_id
                .get(row.op_id.as_str())
                .and_then(|operation| constant_payload_row(operation))
        })
        .collect();
    let convert_ops: Vec<_> = operations
        .iter()
        .filter_map(|row| {
            op_by_id
                .get(row.op_id.as_str())
                .and_then(|operation| convert_op_row(operation))
        })
        .collect();
    let mut leaf_rows: Vec<_> = leaves.into_values().collect();
    leaf_rows.sort_by(|left, right| {
        (&left.function, &left.region_id, &left.value).cmp(&(
            &right.function,
            &right.region_id,
            &right.value,
        ))
    });
    ClosureReport {
        schema: REPORT_SCHEMA,
        root,
        value_count: seen_values.len(),
        op_count: operations.len(),
        leaf_count: leaf_rows.len(),
        constant_payload_count: constant_payloads.len(),
        convert_op_count: convert_ops.len(),
        truncated: !queue.is_empty(),
        ops: operations,
        constant_payloads,
        convert_ops,
        leaves: leaf_rows,
        edges,
    }
}

pub fn render_text(report: &ClosureReport) -> String {
    let mut lines = vec![
        format!(
            "STABLEHLO_VALUE_CLOSURE_ROOT={}:{}:{}",
            report.root.function, report.root.region_id, report.root.name
        ),
        format!("STABLEHLO_VALUE_CLOSURE_VALUES={}", report.value_count),
        format!("STABLEHLO_VALUE_CLOSURE_OPS={}", report.op_count),
        format!("STABLEHLO_VALUE_CLOSURE_LEAVES={}", report.leaf_count),
        format!(
            "STABLEHLO_VALUE_CLOSURE_CONSTANT_PAYLOADS={}",
            report.constant_payload_count
        ),
        format!(
            "STABLEHLO_VALUE_CLOSURE_CONVERT_OPS={}",
            report.convert_op_count
        ),
        format!("STABLEHLO_VALUE_CLOSURE_TRUNCATED={}", report.truncated),
    ];
    for op in &report.ops {
        lines.push(format!(
            "OP\t{}\t{}\t{}\t{}\t{}\tresults={}\toperands={}\tcall={}",
            op.op_id,
            op.function,
            op.region_id,
            op.kind,
            op.opcode,
            op.result_names.join(","),
            op.operand_names.join(","),
            op.call_target
        ));
    }
    for payload in &report.constant_payloads {
        lines.push(format!(
            "CONSTANT\t{}\t{}\t{}\t{}\tdense={}\ttype={}\tdtype={}",
            payload.op_id,
            payload.function,
            payload.region_id,
            payload.result_name,
            payload.dense_literal,
            payload.tensor_type,
            payload.dtype
        ));
    }
    for convert in &report.convert_ops {
        lines.push(format!(
            "CONVERT\t{}\t{}\t{}\t{}\toperand={}\tfrom={}\tto={}",
            convert.op_id,
            convert.function,
            convert.region_id,
            convert.result_name,
            convert.operand_name,
            convert.from_tensor_type,
            convert.to_tensor_type
        ));
    }
    for leaf in &report.leaves {
        lines.push(format!(
            "LEAF\t{}\t{}\t{}\t{}",
            leaf.kind, leaf.function, leaf.region_id, leaf.value
        ));
    }
    lines.join("\n") + "\n"
}

#[derive(Default)]
struct CliArgs {
    ir: Option<String>,
    function: Option<String>,
    region_id: String,
    value: Option<String>,
    max_nodes: i64,
    format: String,
}

fn parse_args(args: &[String]) -> Result<Option<CliArgs>, String> {
    let mut parsed = CliArgs {
        max_nodes: DEFAULT_MAX_NODES,
        format: "text".into(),
        ..CliArgs::default()
    };
    let mut index = 0;
    while index < args.len() {
        let option = args[index].as_str();
        if option == "--help" || option == "-h" {
            println!("Usage: agent-canon {SELECTOR} --ir PATH --function NAME --value SSA [--region-id ID] [--max-nodes N] [--format text|json]");
            return Ok(None);
        }
        if option == "--format" {
            index += 1;
            parsed.format = args.get(index).ok_or("--format requires a value")?.clone();
        } else if option == "--max-nodes" {
            index += 1;
            parsed.max_nodes = args
                .get(index)
                .ok_or("--max-nodes requires an integer")?
                .parse()
                .map_err(|_| "--max-nodes must be an integer")?;
        } else {
            index += 1;
            let value = args
                .get(index)
                .ok_or_else(|| format!("{option} requires a value"))?
                .clone();
            match option {
                "--ir" => parsed.ir = Some(value),
                "--function" => parsed.function = Some(value),
                "--region-id" => parsed.region_id = value,
                "--value" => parsed.value = Some(value),
                _ => return Err(format!("unknown option: {option}")),
            }
        }
        index += 1;
    }
    if parsed.format != "text" && parsed.format != "json" {
        return Err("--format must be text or json".into());
    }
    if parsed.ir.is_none() || parsed.function.is_none() || parsed.value.is_none() {
        return Err("--ir, --function, and --value are required".into());
    }
    Ok(Some(parsed))
}

pub fn run(args: &[String]) -> i32 {
    match run_inner(args) {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: {error}");
            2
        }
    }
}

fn run_inner(args: &[String]) -> Result<(), String> {
    let Some(args) = parse_args(args)? else {
        return Ok(());
    };
    let path = args.ir.expect("required arg checked");
    let bytes = fs::read(&path).map_err(|error| format!("{path}: {error}"))?;
    let value: Value =
        serde_json::from_slice(&bytes).map_err(|error| format!("{path}: {error}"))?;
    let ir = parse_operational_ir(&value).map_err(|error| format!("{path}: {error}"))?;
    let functions = function_map(&ir);
    let function = args.function.expect("required arg checked");
    let region_id = if args.region_id.is_empty() {
        function_body_region(&functions, &function)
    } else {
        args.region_id
    };
    let report = trace_value_closure(
        &ir,
        ScopedValue::new(
            function,
            region_id,
            args.value.expect("required arg checked"),
        ),
        args.max_nodes,
    );
    if args.format == "json" {
        let json = serde_json::to_value(&report).map_err(|error| error.to_string())?;
        println!(
            "{}",
            serde_json::to_string_pretty(&json).map_err(|error| error.to_string())?
        );
    } else {
        print!("{}", render_text(&report));
    }
    Ok(())
}

pub fn load_operational_ir(path: &Path) -> Result<OperationalIr, String> {
    let bytes = fs::read(path).map_err(|error| format!("{}: {error}", path.display()))?;
    let value: Value =
        serde_json::from_slice(&bytes).map_err(|error| format!("{}: {error}", path.display()))?;
    parse_operational_ir(&value).map_err(|error| format!("{}: {error}", path.display()))
}
