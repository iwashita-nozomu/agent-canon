// @dependency-start
// contract implementation
// responsibility Renders the shared thin operational IR and source facts as Lean evidence data.
// upstream implementation jit_ir_to_lean.rs owns the related JIT-to-Lean route
// upstream design ../../../../../documents/tools/operational_ir_to_lean.md defines the renderer contract
// downstream implementation cpp_template_to_lean.rs composes this renderer with the native C++ source reader
// downstream implementation main.rs exposes operational-ir-to-lean
// downstream test ../../../../../tests/agent_tools/test_operational_ir_to_lean.py validates the renderer contract
// @dependency-end

//! Generic thin-operational-IR to Lean evidence rendering.

use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use serde_json::{Map, Value};
use std::fs;
use std::path::{Path, PathBuf};

pub const SELECTOR: &str = "operational-ir-to-lean";
const IR_SCHEMA: &str = "agent-canon.thin-operational-ir.v2";
const USAGE: &str = "usage: agent-canon operational-ir-to-lean --ir IR --namespace NAMESPACE [--module-name MODULE_NAME] [--out OUT]";
const LEAN_KEYWORDS: &[&str] = &[
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
];
const STANDARD_OP_FIELDS: &[&str] = &[
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
];
const STANDARD_COVERAGE_FIELDS: &[&str] = &[
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
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum OptionName {
    Ir,
    Namespace,
    ModuleName,
    Out,
    Help,
}

const OPTIONS: &[(&str, OptionName)] = &[
    ("--ir", OptionName::Ir),
    ("--namespace", OptionName::Namespace),
    ("--module-name", OptionName::ModuleName),
    ("--out", OptionName::Out),
    ("--help", OptionName::Help),
];

#[derive(Default)]
struct Args {
    ir: Option<PathBuf>,
    namespace: Option<String>,
    module_name: Option<String>,
    out: Option<PathBuf>,
}

enum ParseResult {
    Help,
    Run(Args),
}

#[derive(Debug)]
struct RenderInput {
    input_schema: String,
    module_name: String,
    provenance: Vec<(String, String)>,
    public_interface: Vec<(String, String)>,
    source_facts: Vec<Value>,
    operational_ir: Value,
}

fn parse_args(argv: &[String]) -> Result<ParseResult, String> {
    let mut args = Args::default();
    let mut index = 0;
    while index < argv.len() {
        let token = &argv[index];
        if token == "-h" {
            return Ok(ParseResult::Help);
        }
        let (name, inline) = token
            .split_once('=')
            .map_or((token.as_str(), None), |(name, value)| (name, Some(value)));
        let option = resolve_long_option_prefix(name, OPTIONS).map_err(|error| match error {
            LongOptionError::Unrecognized => format!("unrecognized arguments: {name}"),
            LongOptionError::Ambiguous(candidates) => format!(
                "ambiguous option: {name} could match {}",
                candidates.join(", ")
            ),
        })?;
        if option == OptionName::Help {
            if inline.is_some() {
                return Err(format!(
                    "argument --help: ignored explicit argument '{token}'"
                ));
            }
            return Ok(ParseResult::Help);
        }
        let value = if let Some(value) = inline {
            value.to_owned()
        } else {
            index += 1;
            argv.get(index)
                .filter(|value| !value.starts_with('-'))
                .cloned()
                .ok_or_else(|| format!("argument {name}: expected one argument"))?
        };
        match option {
            OptionName::Ir => args.ir = Some(value.into()),
            OptionName::Namespace => args.namespace = Some(value),
            OptionName::ModuleName => args.module_name = Some(value),
            OptionName::Out => args.out = Some(value.into()),
            OptionName::Help => unreachable!(),
        }
        index += 1;
    }
    if args.ir.is_none() {
        return Err("the following arguments are required: --ir".into());
    }
    if args.namespace.is_none() {
        return Err("the following arguments are required: --namespace".into());
    }
    Ok(ParseResult::Run(args))
}

fn object<'a>(value: Option<&'a Value>, label: &str) -> Result<&'a Map<String, Value>, String> {
    value
        .and_then(Value::as_object)
        .ok_or_else(|| format!("missing {label} object"))
}

fn optional_object(value: Option<&Value>) -> &Map<String, Value> {
    value
        .and_then(Value::as_object)
        .unwrap_or_else(|| empty_object())
}

fn empty_object() -> &'static Map<String, Value> {
    static EMPTY: std::sync::OnceLock<Map<String, Value>> = std::sync::OnceLock::new();
    EMPTY.get_or_init(Map::new)
}

fn string_field(row: &Map<String, Value>, key: &str, default: &str) -> String {
    match row.get(key) {
        None | Some(Value::Null) => default.to_owned(),
        Some(Value::String(value)) => value.clone(),
        Some(value) => serde_json::to_string(value).unwrap_or_else(|_| default.to_owned()),
    }
}

fn json_compact(value: &Value) -> String {
    serde_json::to_string(value).unwrap_or_default()
}

fn list_of_objects(value: Option<&Value>, label: &str) -> Result<Vec<Map<String, Value>>, String> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    if value.is_null() {
        return Ok(Vec::new());
    }
    let rows = value
        .as_array()
        .ok_or_else(|| format!("missing {label} array"))?;
    rows.iter()
        .enumerate()
        .map(|(index, value)| {
            value
                .as_object()
                .cloned()
                .ok_or_else(|| format!("{label}[{index}] must be an object"))
        })
        .collect()
}

fn list_of_strings(value: Option<&Value>, label: &str) -> Result<Vec<String>, String> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    if value.is_null() {
        return Ok(Vec::new());
    }
    let rows = value
        .as_array()
        .ok_or_else(|| format!("missing {label} string array"))?;
    rows.iter()
        .enumerate()
        .map(|(index, value)| {
            value
                .as_str()
                .map(str::to_owned)
                .ok_or_else(|| format!("{label}[{index}] must be a string"))
        })
        .collect()
}

fn integer_field(row: &Map<String, Value>, key: &str, default: i64) -> Result<i64, String> {
    match row.get(key) {
        None | Some(Value::Null) => Ok(default),
        Some(Value::Bool(_)) => Err(format!("{key} must be an integer")),
        Some(Value::Number(value)) => value
            .as_i64()
            .or_else(|| value.as_u64().and_then(|value| i64::try_from(value).ok()))
            .or_else(|| {
                value
                    .as_f64()
                    .filter(|value| value.fract() == 0.0)
                    .and_then(|value| i64::try_from(value as i128).ok())
            })
            .ok_or_else(|| format!("{key} must be an integer")),
        _ => Err(format!("{key} must be an integer")),
    }
}

fn required_integer(row: &Map<String, Value>, key: &str) -> Result<i64, String> {
    if !row.contains_key(key) {
        return Err(format!("missing required coverage field: {key}"));
    }
    integer_field(row, key, 0)
}

fn required_strings(row: &Map<String, Value>, key: &str) -> Result<Vec<String>, String> {
    if !row.contains_key(key) {
        return Err(format!("missing required coverage field: {key}"));
    }
    list_of_strings(row.get(key), key)
}

fn normalize_input(record: &Map<String, Value>) -> Result<RenderInput, String> {
    let input_schema = string_field(record, "schema", "");
    let (operational, source_facts) = if input_schema == IR_SCHEMA {
        (record, Vec::new())
    } else {
        let operational = object(record.get("operational_ir"), "operational_ir")?;
        let facts_record = optional_object(record.get("source_facts"));
        let facts = list_of_objects(facts_record.get("facts"), "source_facts.facts")?
            .into_iter()
            .map(Value::Object)
            .collect();
        (operational, facts)
    };
    let schema = string_field(operational, "schema", "");
    if schema != IR_SCHEMA {
        return Err(format!(
            "operational_ir schema must be {IR_SCHEMA}, got {schema}"
        ));
    }
    let source_root = optional_object(record.get("source_root"));
    let root = optional_object(record.get("root"));
    let candidate = ["qualname"]
        .iter()
        .find_map(|key| {
            source_root
                .get(*key)
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
        })
        .or_else(|| root.get("qualname").and_then(Value::as_str))
        .or_else(|| root.get("python_symbol").and_then(Value::as_str))
        .or_else(|| root.get("cpp_symbol").and_then(Value::as_str))
        .unwrap_or("GeneratedOperationalIr");
    let leaf = candidate
        .rsplit('.')
        .next()
        .unwrap_or(candidate)
        .rsplit("::")
        .next()
        .unwrap_or(candidate);
    let module_name = sanitize_namespace(&format!("{leaf}_operational_ir"));
    let mut provenance = vec![("schema".to_owned(), input_schema.clone())];
    for (prefix, source, fields) in [
        (
            "root",
            root,
            &[
                "schema",
                "source_kind",
                "cpp_symbol",
                "python_symbol",
                "source_path",
                "qualname",
                "repo_root",
            ][..],
        ),
        (
            "source_root",
            source_root,
            &[
                "schema",
                "status",
                "path",
                "relative_path",
                "qualname",
                "name",
                "source_sha256",
                "file_sha256",
                "source_span",
            ][..],
        ),
    ] {
        for field in fields {
            if source.contains_key(*field) {
                provenance.push((format!("{prefix}.{field}"), string_field(source, field, "")));
            }
        }
    }
    let mut public_interface = Vec::new();
    let interface = optional_object(record.get("public_interface"));
    for field in [
        "schema",
        "status",
        "cpp_symbol",
        "python_symbol",
        "qualname",
        "name",
        "return_type",
    ] {
        if interface.contains_key(field) {
            public_interface.push((
                format!("public_interface.{field}"),
                string_field(interface, field, ""),
            ));
        }
    }
    for field in ["parameters", "return_roots", "return_leaves", "coverage"] {
        if let Some(value) = interface.get(field) {
            public_interface.push((
                format!("public_interface.{field}_json"),
                json_compact(value),
            ));
        }
    }
    Ok(RenderInput {
        input_schema,
        module_name,
        provenance,
        public_interface,
        source_facts,
        operational_ir: Value::Object(operational.clone()),
    })
}

fn lean_string(value: &str) -> String {
    let escaped = value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
        .replace('\t', "\\t");
    format!("\"{escaped}\"")
}

fn lean_strings(values: &[String]) -> String {
    if values.is_empty() {
        "[]".into()
    } else {
        format!(
            "[{}]",
            values
                .iter()
                .map(|value| lean_string(value))
                .collect::<Vec<_>>()
                .join(", ")
        )
    }
}

pub fn validate_namespace(namespace: &str) -> Result<(), String> {
    if namespace.is_empty() {
        return Err("Lean namespace must not be empty".into());
    }
    for part in namespace.split('.') {
        let mut chars = part.chars();
        let valid_start = chars
            .next()
            .is_some_and(|character| character.is_ascii_alphabetic() || character == '_');
        if !valid_start
            || !chars.all(|character| {
                character.is_ascii_alphanumeric() || character == '_' || character == '\''
            })
        {
            return Err(format!("invalid Lean namespace segment: {part}"));
        }
        if LEAN_KEYWORDS.contains(&part) {
            return Err(format!("Lean namespace segment is reserved: {part}"));
        }
    }
    Ok(())
}

fn sanitize_namespace(value: &str) -> String {
    let raw = value
        .split(|character: char| {
            matches!(character, '.' | ':' | '/' | '\\' | '-') || character.is_whitespace()
        })
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>();
    let raw = if raw.is_empty() {
        vec!["GeneratedOperationalIr"]
    } else {
        raw
    };
    raw.into_iter()
        .map(|part| {
            let mut result = part
                .chars()
                .map(|character| {
                    if character.is_ascii_alphanumeric() || character == '_' || character == '\'' {
                        character
                    } else {
                        '_'
                    }
                })
                .collect::<String>();
            if result.is_empty()
                || result
                    .chars()
                    .next()
                    .is_some_and(|character| character.is_ascii_digit())
            {
                result = format!("Generated_{result}");
            }
            if LEAN_KEYWORDS.contains(&result.as_str()) {
                result.push_str("_generated");
            }
            result
        })
        .collect::<Vec<_>>()
        .join(".")
}

fn metadata_lines(name: &str, rows: &[(String, String)]) -> Vec<String> {
    if rows.is_empty() {
        return vec![format!("def {name} : List KeyValue := []")];
    }
    let mut lines = vec![format!("def {name} : List KeyValue := [")];
    for (key, value) in rows {
        lines.push(format!(
            "  {{ key := {}, value := {} }},",
            lean_string(key),
            lean_string(value)
        ));
    }
    lines.push("]".into());
    lines
}

fn render_structures() -> Vec<String> {
    [
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
    .iter()
    .map(|line| (*line).to_owned())
    .collect()
}

fn mappings(value: Option<&Value>, label: &str) -> Result<Vec<Map<String, Value>>, String> {
    list_of_objects(value, label)
}

fn row_string(row: &Map<String, Value>, key: &str) -> String {
    string_field(row, key, "")
}
fn row_nat(row: &Map<String, Value>, key: &str) -> Result<String, String> {
    let value = integer_field(row, key, 0)?;
    if value < 0 {
        return Err(format!("Nat field must be non-negative, got {value}"));
    }
    Ok(value.to_string())
}
fn required_nat(row: &Map<String, Value>, key: &str) -> Result<String, String> {
    if !row.contains_key(key) {
        return Err(format!("missing required coverage field: {key}"));
    }
    row_nat(row, key)
}
fn row_string_list(row: &Map<String, Value>, key: &str, label: &str) -> Result<String, String> {
    Ok(lean_strings(&list_of_strings(row.get(key), label)?))
}

fn render_source_fact(row: &Map<String, Value>) -> String {
    format!("{{ factId := {}, sourcePath := {}, sourceSymbol := {}, sourceSpan := {}, factKind := {}, target := {}, expression := {}, statement := {}, textSha256 := {} }}",lean_string(&row_string(row,"fact_id")),lean_string(&row_string(row,"source_path")),lean_string(&row_string(row,"source_symbol")),lean_string(&row_string(row,"source_span")),lean_string(&row_string(row,"fact_kind")),lean_string(&row_string(row,"target")),lean_string(&row_string(row,"expression")),lean_string(&row_string(row,"statement")),lean_string(&row_string(row,"text_sha256")))
}

fn render_function(row: &Map<String, Value>) -> Result<String, String> {
    Ok(format!("{{ functionId := {}, name := {}, signature := {}, lineStart := {}, lineEnd := {}, bodyRegionId := {} }}",lean_string(&row_string(row,"function_id")),lean_string(&row_string(row,"name")),lean_string(&row_string(row,"signature")),row_nat(row,"line_start")?,row_nat(row,"line_end")?,lean_string(&row_string(row,"body_region_id"))))
}
fn render_region(row: &Map<String, Value>) -> Result<String, String> {
    Ok(format!("{{ regionId := {}, kind := {}, parentFunction := {}, parentOpId := {}, depth := {}, lineStart := {}, lineEnd := {}, opIds := {} }}",lean_string(&row_string(row,"region_id")),lean_string(&row_string(row,"kind")),lean_string(&row_string(row,"parent_function")),lean_string(&row_string(row,"parent_op_id")),row_nat(row,"depth")?,row_nat(row,"line_start")?,row_nat(row,"line_end")?,row_string_list(row,"op_ids","region.op_ids")?))
}
fn render_edge(row: &Map<String, Value>) -> String {
    format!(
        "{{ edgeId := {}, kind := {}, fromNode := {}, toNode := {} }}",
        lean_string(&row_string(row, "edge_id")),
        lean_string(&row_string(row, "kind")),
        lean_string(&row_string(row, "from")),
        lean_string(&row_string(row, "to"))
    )
}

fn metadata_for_row(row: &Map<String, Value>, standard: &[&str]) -> Vec<(String, String)> {
    row.iter()
        .filter(|(key, _)| !standard.contains(&key.as_str()))
        .map(|(key, value)| (key.clone(), json_compact(value)))
        .collect()
}
fn render_metadata(rows: &[(String, String)]) -> String {
    if rows.is_empty() {
        "[]".into()
    } else {
        format!(
            "[{}]",
            rows.iter()
                .map(|(key, value)| format!(
                    "{{ key := {}, value := {} }}",
                    lean_string(key),
                    lean_string(value)
                ))
                .collect::<Vec<_>>()
                .join(", ")
        )
    }
}

fn render_op(row: &Map<String, Value>) -> Result<String, String> {
    let metadata = metadata_for_row(row, STANDARD_OP_FIELDS);
    Ok(format!("{{ opId := {}, kind := {}, opcode := {}, line := {}, text := {}, textSha256 := {}, tensorTypes := {}, dtypes := {}, functionName := {}, regionId := {}, parentOpId := {}, callTarget := {}, metadata := {} }}",lean_string(&row_string(row,"op_id")),lean_string(&row_string(row,"kind")),lean_string(&row_string(row,"opcode")),row_nat(row,"line")?,lean_string(&row_string(row,"text")),lean_string(&row_string(row,"text_sha256")),row_string_list(row,"tensor_types","op.tensor_types")?,row_string_list(row,"dtypes","op.dtypes")?,lean_string(&row_string(row,"function")),lean_string(&row_string(row,"region_id")),lean_string(&row_string(row,"parent_op_id")),lean_string(&row_string(row,"call_target")),render_metadata(&metadata)))
}

fn render_code_path(row: &Map<String, Value>) -> Result<String, String> {
    let decisions = mappings(row.get("decisions"), "code_path.decisions")?
        .iter()
        .map(|row| {
            Ok(format!(
                "{{ opId := {}, kind := {}, choice := {}, condition := {}, line := {} }}",
                lean_string(&row_string(row, "op_id")),
                lean_string(&row_string(row, "kind")),
                lean_string(&row_string(row, "choice")),
                lean_string(&row_string(row, "condition")),
                row_nat(row, "line")?
            ))
        })
        .collect::<Result<Vec<_>, String>>()?;
    let decisions = if decisions.is_empty() {
        "[]".into()
    } else {
        format!("[{}]", decisions.join(", "))
    };
    Ok(format!("{{ pathId := {}, functionName := {}, regionId := {}, opIds := {}, decisions := {}, decisionCount := {}, summary := {} }}",lean_string(&row_string(row,"path_id")),lean_string(&row_string(row,"function")),lean_string(&row_string(row,"region_id")),row_string_list(row,"op_ids","code_path.op_ids")?,decisions,row_nat(row,"decision_count")?,lean_string(&row_string(row,"summary"))))
}

fn render_rows(
    name: &str,
    ty: &str,
    rows: &[Map<String, Value>],
    render: impl Fn(&Map<String, Value>) -> Result<String, String>,
) -> Result<Vec<String>, String> {
    if rows.is_empty() {
        return Ok(vec![format!("def {name} : List {ty} := []")]);
    }
    let mut lines = vec![format!("def {name} : List {ty} := [")];
    for row in rows {
        lines.push(format!("  {},", render(row)?));
    }
    lines.push("]".into());
    Ok(lines)
}

fn enforce_complete_coverage(input: &RenderInput) -> Result<(), String> {
    let coverage = object(
        input.operational_ir.get("coverage"),
        "operational_ir.coverage",
    )?;
    let unresolved = required_strings(coverage, "unresolved_call_targets")?;
    let unassigned = required_integer(coverage, "unassigned_op_count")?;
    let unmapped = required_strings(coverage, "unmapped_code_path_functions")?;
    let code_paths = required_integer(coverage, "code_path_count")?;
    let functions = required_integer(coverage, "function_count")?;
    if !unresolved.is_empty() || unassigned != 0 || !unmapped.is_empty() || code_paths < functions {
        let unresolved = if unresolved.is_empty() {
            "<none>".into()
        } else {
            unresolved.join(", ")
        };
        let unmapped = if unmapped.is_empty() {
            "<none>".into()
        } else {
            unmapped.join(", ")
        };
        return Err(format!("incomplete operational coverage: unresolved_call_targets=[{unresolved}], unassigned_op_count={unassigned}, unmapped_code_path_functions=[{unmapped}], code_path_count={code_paths}, function_count={functions}"));
    }
    Ok(())
}

fn render_coverage(input: &RenderInput) -> Result<Vec<String>, String> {
    let coverage = object(
        input.operational_ir.get("coverage"),
        "operational_ir.coverage",
    )?;
    let values = [
        ("function_count", "functionCount"),
        ("region_count", "regionCount"),
        ("expansion_edge_count", "expansionEdgeCount"),
        ("op_count", "opCount"),
        ("assigned_region_count", "assignedRegionCount"),
        ("unassigned_op_count", "unassignedOpCount"),
        ("max_region_depth", "maxRegionDepth"),
        ("while_count", "whileCount"),
        ("case_count", "caseCount"),
        ("if_count", "ifCount"),
        ("call_count", "callCount"),
        ("code_path_count", "codePathCount"),
        ("code_path_decision_count", "codePathDecisionCount"),
        ("max_code_path_decisions", "maxCodePathDecisions"),
    ];
    let mut lines = vec!["def operationalCoverage : OperationalCoverage := {".to_owned()];
    for (json_name, lean_name) in values {
        lines.push(format!(
            "  {lean_name} := {},",
            required_nat(coverage, json_name)?
        ));
    }
    lines.push(format!(
        "  unassignedOpIds := {},",
        lean_strings(&required_strings(coverage, "unassigned_op_ids")?)
    ));
    lines.push(format!(
        "  unresolvedCallTargets := {},",
        lean_strings(&required_strings(coverage, "unresolved_call_targets")?)
    ));
    lines.push(format!(
        "  unmappedCodePathFunctions := {},",
        lean_strings(&required_strings(coverage, "unmapped_code_path_functions")?)
    ));
    let metadata = metadata_for_row(coverage, STANDARD_COVERAGE_FIELDS);
    lines.push(format!("  metadata := {}", render_metadata(&metadata)));
    lines.extend(["}".into(),"".into(),"def unresolvedCallTargets : List String := operationalCoverage.unresolvedCallTargets".into(),"def unmappedCodePathFunctions : List String := operationalCoverage.unmappedCodePathFunctions".into(),"def codePathCoverageComplete : Bool :=".into(),"  operationalCoverage.unmappedCodePathFunctions.isEmpty &&".into(),"  operationalCoverage.codePathCount >= operationalCoverage.functionCount".into(),"def coverageComplete : Bool :=".into(),"  operationalCoverage.unresolvedCallTargets.isEmpty &&".into(),"  operationalCoverage.unassignedOpCount == 0 &&".into(),"  codePathCoverageComplete".into()]);
    Ok(lines)
}

fn render_lean(input: &RenderInput, namespace: &str, module: &str) -> Result<String, String> {
    let ir = object(Some(&input.operational_ir), "operational_ir")?;
    let functions = mappings(ir.get("functions"), "operational_ir.functions")?;
    let regions = mappings(ir.get("regions"), "operational_ir.regions")?;
    let edges = mappings(ir.get("expansion_edges"), "operational_ir.expansion_edges")?;
    let code_paths = mappings(ir.get("code_paths"), "operational_ir.code_paths")?;
    let ops = mappings(ir.get("ops"), "operational_ir.ops")?;
    let allowed = list_of_strings(ir.get("allowed_kinds"), "allowed_kinds")?;
    let signatures = list_of_strings(ir.get("function_signatures"), "function_signatures")?;
    let mut lines = vec![
        "/- Generated by agent-canon operational-ir-to-lean. -/".into(),
        "/- Evidence data only: semantic proof obligations live in theorem packages. -/".into(),
        format!("namespace {namespace}"),
        format!("namespace {module}"),
        String::new(),
    ];
    lines.extend(render_structures());
    lines.extend([
        String::new(),
        format!(
            "def inputSchema : String := {}",
            lean_string(&input.input_schema)
        ),
        format!(
            "def operationalIrSchema : String := {}",
            lean_string(IR_SCHEMA)
        ),
        format!(
            "def allowedKinds : List String := {}",
            lean_strings(&allowed)
        ),
        format!(
            "def functionSignatures : List String := {}",
            lean_strings(&signatures)
        ),
        String::new(),
    ]);
    lines.extend(metadata_lines("inputProvenance", &input.provenance));
    lines.push(String::new());
    lines.extend(metadata_lines(
        "publicInterfaceFields",
        &input.public_interface,
    ));
    lines.push(String::new());
    let facts = input
        .source_facts
        .iter()
        .map(|fact| {
            fact.as_object()
                .cloned()
                .ok_or_else(|| "source fact must be an object".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    if facts.is_empty() {
        lines.push("def sourceFacts : List SourceFact := []".into());
    } else {
        lines.push("def sourceFacts : List SourceFact := [".into());
        for fact in &facts {
            lines.push(format!("  {},", render_source_fact(fact)));
        }
        lines.push("]".into());
    }
    lines.push(String::new());
    lines.extend(render_rows(
        "operationalFunctions",
        "OperationalFunction",
        &functions,
        render_function,
    )?);
    lines.push(String::new());
    lines.extend(render_rows(
        "operationalRegions",
        "OperationalRegion",
        &regions,
        render_region,
    )?);
    lines.push(String::new());
    lines.extend(render_rows(
        "expansionEdges",
        "ExpansionEdge",
        &edges,
        |row| Ok(render_edge(row)),
    )?);
    lines.push(String::new());
    lines.extend(render_rows(
        "codePaths",
        "CodePath",
        &code_paths,
        render_code_path,
    )?);
    lines.push(String::new());
    lines.extend(render_rows(
        "operationalOps",
        "OperationalOp",
        &ops,
        render_op,
    )?);
    lines.push(String::new());
    lines.extend(render_coverage(input)?);
    lines.extend([
        String::new(),
        format!("end {module}"),
        format!("end {namespace}"),
        String::new(),
    ]);
    Ok(lines.join("\n"))
}

pub fn render_envelope(
    record: &Value,
    namespace: &str,
    module_name: Option<&str>,
) -> Result<String, String> {
    let record = record
        .as_object()
        .ok_or_else(|| "input JSON must be an object".to_owned())?;
    let input = normalize_input(record)?;
    enforce_complete_coverage(&input)?;
    validate_namespace(namespace)?;
    let module = module_name.unwrap_or(&input.module_name);
    validate_namespace(module)?;
    render_lean(&input, namespace, module)
}

fn load_record(path: &Path) -> Result<Map<String, Value>, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("unable to read input JSON: {}: {error}", path.display()))?;
    let value: Value = serde_json::from_str(&text)
        .map_err(|error| format!("invalid JSON {}: {error}", path.display()))?;
    value
        .as_object()
        .cloned()
        .ok_or_else(|| "input JSON must be an object".into())
}

pub fn run(argv: &[String]) -> i32 {
    let args = match parse_args(argv) {
        Ok(ParseResult::Help) => {
            println!("{USAGE}");
            return 0;
        }
        Ok(ParseResult::Run(args)) => args,
        Err(error) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let result = (|| -> Result<(), String> {
        let record = load_record(args.ir.as_deref().expect("required argument"))?;
        let input = normalize_input(&record)?;
        enforce_complete_coverage(&input)?;
        let namespace = args.namespace.as_deref().expect("required argument");
        validate_namespace(namespace)?;
        let module = args.module_name.as_deref().unwrap_or(&input.module_name);
        validate_namespace(module)?;
        let rendered = render_lean(&input, namespace, module)?;
        if let Some(path) = args.out.as_deref() {
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent)
                    .map_err(|error| format!("cannot create {}: {error}", parent.display()))?;
            }
            fs::write(path, rendered.as_bytes())
                .map_err(|error| format!("cannot write {}: {error}", path.display()))?;
        } else {
            print!("{rendered}");
        }
        Ok(())
    })();
    match result {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            1
        }
    }
}
