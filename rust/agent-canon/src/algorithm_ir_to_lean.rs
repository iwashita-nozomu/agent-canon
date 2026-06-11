// @dependency-start
// responsibility Lowers generic Algorithm Expansion IR Python-AST JSON into Lean route artifacts.
// upstream implementation ../../../tools/agent_tools/algorithm_expansion_ir.py emits expression_ast/control_facts.
// upstream design ../../../documents/design/algorithm-ir-to-lean.md defines the Python/Rust lowering boundary.
// upstream design ../../../documents/tools/algorithm_ir_to_lean.md documents operator usage.
// downstream implementation main.rs exposes algorithm-ir-to-lean.
// @dependency-end

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
struct Args {
    algorithm_ir: PathBuf,
    namespace: String,
    module_name: Option<String>,
    out: PathBuf,
}

#[derive(Debug, Clone)]
struct CodeFact {
    fact_id: String,
    source_symbol: String,
    source_span: String,
    fact_kind: String,
    target: String,
    expression: String,
    expression_ast: Value,
}

#[derive(Debug, Clone)]
struct ControlFact {
    fact_id: String,
    source_symbol: String,
    source_span: String,
    control_kind: String,
    condition: Option<String>,
    condition_ast: Option<Value>,
    target: Option<String>,
    target_ast: Option<Value>,
    iterator: Option<String>,
    iterator_ast: Option<Value>,
    body_targets: Vec<String>,
    orelse_targets: Vec<String>,
    statement: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum ProjectionSegment {
    Attr(String),
    Index(Box<Term>),
    Slice {
        lower: Option<Box<Term>>,
        upper: Option<Box<Term>>,
        step: Option<Box<Term>>,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ProjectionPath {
    root: String,
    segments: Vec<ProjectionSegment>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum Term {
    Name(String),
    Const(String),
    None,
    Projection(ProjectionPath),
    Attr(Box<Term>, String),
    Call {
        func: Box<Term>,
        args: Vec<Term>,
        keywords: Vec<(String, Term)>,
    },
    Bin {
        op: String,
        left: Box<Term>,
        right: Box<Term>,
    },
    Unary {
        op: String,
        value: Box<Term>,
    },
    IfThenElse {
        test: Box<Term>,
        body: Box<Term>,
        orelse: Box<Term>,
    },
    Tuple(Vec<Term>),
    List(Vec<Term>),
    Set(Vec<Term>),
    Dict(Vec<(Option<Term>, Term)>),
    Subscript {
        value: Box<Term>,
        index: Box<Term>,
    },
    Slice {
        lower: Option<Box<Term>>,
        upper: Option<Box<Term>>,
        step: Option<Box<Term>>,
    },
    Compare {
        left: Box<Term>,
        ops: Vec<String>,
        comparators: Vec<Term>,
    },
    Bool {
        op: String,
        values: Vec<Term>,
    },
    Lambda {
        args: Vec<String>,
        body: Box<Term>,
    },
}

pub fn run(args: &[String]) -> i32 {
    match parse_args(args).and_then(run_checked) {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("algorithm-ir-to-lean: {error}");
            2
        }
    }
}

fn parse_args(args: &[String]) -> Result<Args, String> {
    let mut algorithm_ir = None;
    let mut namespace = "GeneratedAlgorithmPath".to_string();
    let mut module_name = None;
    let mut out = None;
    let mut index = 0;

    while index < args.len() {
        match args[index].as_str() {
            "--algorithm-ir" => {
                index += 1;
                algorithm_ir = args.get(index).map(PathBuf::from);
            }
            "--namespace" => {
                index += 1;
                namespace = args
                    .get(index)
                    .ok_or("--namespace requires a value")?
                    .to_string();
            }
            "--module-name" => {
                index += 1;
                module_name = Some(
                    args.get(index)
                        .ok_or("--module-name requires a value")?
                        .to_string(),
                );
            }
            "--out" => {
                index += 1;
                out = args.get(index).map(PathBuf::from);
            }
            "--help" | "-h" => return Err(usage()),
            other => return Err(format!("unknown argument {other:?}\n{}", usage())),
        }
        index += 1;
    }

    Ok(Args {
        algorithm_ir: algorithm_ir.ok_or("--algorithm-ir is required")?,
        namespace,
        module_name,
        out: out.ok_or("--out is required")?,
    })
}

fn usage() -> String {
    "usage: agent-canon algorithm-ir-to-lean --algorithm-ir <path> --namespace <Lean.Namespace> [--module-name name] --out <path>".to_string()
}

fn run_checked(args: Args) -> Result<(), String> {
    let data = fs::read_to_string(&args.algorithm_ir)
        .map_err(|error| format!("failed to read {}: {error}", args.algorithm_ir.display()))?;
    let ir_hash = hex_sha256(data.as_bytes());
    let payload: Value = serde_json::from_str(&data)
        .map_err(|error| format!("failed to parse {}: {error}", args.algorithm_ir.display()))?;
    let facts = code_facts(&payload)?;
    let controls = control_facts(&payload)?;
    let output = render_lean(
        &facts,
        &controls,
        &args.algorithm_ir,
        &ir_hash,
        &args.namespace,
        args.module_name.as_deref(),
    )?;
    if let Some(parent) = args.out.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("failed to create {}: {error}", parent.display()))?;
    }
    fs::write(&args.out, output)
        .map_err(|error| format!("failed to write {}: {error}", args.out.display()))?;
    Ok(())
}

fn hex_sha256(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn string_field(value: &Value, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string()
}

fn optional_string_field(value: &Value, key: &str) -> Option<String> {
    value.get(key).and_then(Value::as_str).map(str::to_string)
}

fn optional_ast_field(value: &Value, key: &str) -> Option<Value> {
    value.get(key).filter(|raw| !raw.is_null()).cloned()
}

fn string_list_field(value: &Value, key: &str) -> Vec<String> {
    value
        .get(key)
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

fn code_facts(payload: &Value) -> Result<Vec<CodeFact>, String> {
    let Some(raw_facts) = payload.get("code_facts").and_then(Value::as_array) else {
        return Err("Algorithm IR field code_facts must be a list".to_string());
    };
    let mut facts = Vec::new();
    for raw in raw_facts {
        let fact_kind = string_field(raw, "fact_kind");
        if !matches!(
            fact_kind.as_str(),
            "assignment_equation" | "return_equation"
        ) {
            continue;
        }
        let expression_ast = raw
            .get("expression_ast")
            .ok_or_else(|| {
                format!(
                    "code fact {} is missing expression_ast; regenerate Algorithm IR with the Python AST extractor",
                    string_field(raw, "fact_id")
                )
            })?
            .clone();
        facts.push(CodeFact {
            fact_id: string_field(raw, "fact_id"),
            source_symbol: string_field(raw, "source_symbol"),
            source_span: string_field(raw, "source_span"),
            fact_kind,
            target: string_field(raw, "target"),
            expression: string_field(raw, "expression"),
            expression_ast,
        });
    }
    Ok(facts)
}

fn control_facts(payload: &Value) -> Result<Vec<ControlFact>, String> {
    let Some(raw_facts) = payload.get("control_facts").and_then(Value::as_array) else {
        return Ok(Vec::new());
    };
    let mut facts = Vec::new();
    for raw in raw_facts {
        facts.push(ControlFact {
            fact_id: string_field(raw, "fact_id"),
            source_symbol: string_field(raw, "source_symbol"),
            source_span: string_field(raw, "source_span"),
            control_kind: string_field(raw, "control_kind"),
            condition: optional_string_field(raw, "condition"),
            condition_ast: optional_ast_field(raw, "condition_ast"),
            target: optional_string_field(raw, "target"),
            target_ast: optional_ast_field(raw, "target_ast"),
            iterator: optional_string_field(raw, "iterator"),
            iterator_ast: optional_ast_field(raw, "iterator_ast"),
            body_targets: string_list_field(raw, "body_targets"),
            orelse_targets: string_list_field(raw, "orelse_targets"),
            statement: string_field(raw, "statement"),
        });
    }
    Ok(facts)
}

fn ast_node(value: &Value) -> Result<&str, String> {
    value
        .get("node")
        .and_then(Value::as_str)
        .ok_or_else(|| format!("AST object is missing node field: {value}"))
}

fn ast_field<'a>(value: &'a Value, field: &str) -> Result<&'a Value, String> {
    value.get(field).ok_or_else(|| {
        format!(
            "AST {} is missing field {field}",
            ast_node(value).unwrap_or("?")
        )
    })
}

fn ast_string(value: &Value, field: &str) -> Result<String, String> {
    ast_field(value, field)?
        .as_str()
        .map(str::to_string)
        .ok_or_else(|| {
            format!(
                "AST {} field {field} is not a string",
                ast_node(value).unwrap_or("?")
            )
        })
}

fn ast_list<'a>(value: &'a Value, field: &str) -> Result<Vec<&'a Value>, String> {
    ast_field(value, field)?
        .as_array()
        .map(|items| items.iter().collect())
        .ok_or_else(|| {
            format!(
                "AST {} field {field} is not a list",
                ast_node(value).unwrap_or("?")
            )
        })
}

fn optional_term(value: &Value, field: &str) -> Result<Option<Box<Term>>, String> {
    let raw = ast_field(value, field)?;
    if raw.is_null() {
        Ok(None)
    } else {
        Ok(Some(Box::new(term_from_ast(raw)?)))
    }
}

fn projection_path_from_ast(value: &Value) -> Result<Option<ProjectionPath>, String> {
    match ast_node(value)? {
        "Name" => Ok(Some(ProjectionPath {
            root: ast_string(value, "id")?,
            segments: Vec::new(),
        })),
        "Attribute" => {
            let Some(mut base) = projection_path_from_ast(ast_field(value, "value")?)? else {
                return Ok(None);
            };
            base.segments
                .push(ProjectionSegment::Attr(ast_string(value, "attr")?));
            Ok(Some(base))
        }
        "Subscript" => {
            let Some(mut base) = projection_path_from_ast(ast_field(value, "value")?)? else {
                return Ok(None);
            };
            let slice = ast_field(value, "slice")?;
            let segment = if ast_node(slice)? == "Slice" {
                ProjectionSegment::Slice {
                    lower: optional_term(slice, "lower")?,
                    upper: optional_term(slice, "upper")?,
                    step: optional_term(slice, "step")?,
                }
            } else {
                ProjectionSegment::Index(Box::new(term_from_ast(slice)?))
            };
            base.segments.push(segment);
            Ok(Some(base))
        }
        _ => Ok(None),
    }
}

fn term_from_ast(value: &Value) -> Result<Term, String> {
    if let Some(path) = projection_path_from_ast(value)? {
        if !path.segments.is_empty() {
            return Ok(Term::Projection(path));
        }
    }
    match ast_node(value)? {
        "Name" => Ok(Term::Name(ast_string(value, "id")?)),
        "Constant" => {
            let raw = ast_field(value, "value")?;
            if raw.is_null() {
                Ok(Term::None)
            } else if let Some(text) = raw.as_str() {
                Ok(Term::Const(format!("{text:?}")))
            } else {
                Ok(Term::Const(raw.to_string()))
            }
        }
        "Attribute" => Ok(Term::Attr(
            Box::new(term_from_ast(ast_field(value, "value")?)?),
            ast_string(value, "attr")?,
        )),
        "Call" => {
            let func = Box::new(term_from_ast(ast_field(value, "func")?)?);
            let args = ast_list(value, "args")?
                .into_iter()
                .map(term_from_ast)
                .collect::<Result<Vec<_>, _>>()?;
            let mut keywords = Vec::new();
            for keyword in ast_list(value, "keywords")? {
                let key = keyword
                    .get("arg")
                    .and_then(Value::as_str)
                    .unwrap_or("**")
                    .to_string();
                keywords.push((key, term_from_ast(ast_field(keyword, "value")?)?));
            }
            Ok(Term::Call {
                func,
                args,
                keywords,
            })
        }
        "BinOp" => Ok(Term::Bin {
            op: ast_node(ast_field(value, "op")?)?.to_string(),
            left: Box::new(term_from_ast(ast_field(value, "left")?)?),
            right: Box::new(term_from_ast(ast_field(value, "right")?)?),
        }),
        "UnaryOp" => Ok(Term::Unary {
            op: ast_node(ast_field(value, "op")?)?.to_string(),
            value: Box::new(term_from_ast(ast_field(value, "operand")?)?),
        }),
        "IfExp" => Ok(Term::IfThenElse {
            test: Box::new(term_from_ast(ast_field(value, "test")?)?),
            body: Box::new(term_from_ast(ast_field(value, "body")?)?),
            orelse: Box::new(term_from_ast(ast_field(value, "orelse")?)?),
        }),
        "Tuple" => Ok(Term::Tuple(
            ast_list(value, "elts")?
                .into_iter()
                .map(term_from_ast)
                .collect::<Result<Vec<_>, _>>()?,
        )),
        "List" => Ok(Term::List(
            ast_list(value, "elts")?
                .into_iter()
                .map(term_from_ast)
                .collect::<Result<Vec<_>, _>>()?,
        )),
        "Set" => Ok(Term::Set(
            ast_list(value, "elts")?
                .into_iter()
                .map(term_from_ast)
                .collect::<Result<Vec<_>, _>>()?,
        )),
        "Dict" => {
            let keys = ast_list(value, "keys")?;
            let values = ast_list(value, "values")?;
            if keys.len() != values.len() {
                return Err("Dict AST has different keys and values lengths".to_string());
            }
            let mut pairs = Vec::new();
            for (key, value) in keys.into_iter().zip(values) {
                let rendered_key = if key.is_null() {
                    None
                } else {
                    Some(term_from_ast(key)?)
                };
                pairs.push((rendered_key, term_from_ast(value)?));
            }
            Ok(Term::Dict(pairs))
        }
        "Subscript" => Ok(Term::Subscript {
            value: Box::new(term_from_ast(ast_field(value, "value")?)?),
            index: Box::new(term_from_ast(ast_field(value, "slice")?)?),
        }),
        "Slice" => Ok(Term::Slice {
            lower: optional_term(value, "lower")?,
            upper: optional_term(value, "upper")?,
            step: optional_term(value, "step")?,
        }),
        "Compare" => Ok(Term::Compare {
            left: Box::new(term_from_ast(ast_field(value, "left")?)?),
            ops: ast_list(value, "ops")?
                .into_iter()
                .map(ast_node)
                .map(|result| result.map(str::to_string))
                .collect::<Result<Vec<_>, _>>()?,
            comparators: ast_list(value, "comparators")?
                .into_iter()
                .map(term_from_ast)
                .collect::<Result<Vec<_>, _>>()?,
        }),
        "BoolOp" => Ok(Term::Bool {
            op: ast_node(ast_field(value, "op")?)?.to_string(),
            values: ast_list(value, "values")?
                .into_iter()
                .map(term_from_ast)
                .collect::<Result<Vec<_>, _>>()?,
        }),
        "Lambda" => {
            let args_value = ast_field(value, "args")?;
            let args = ast_list(args_value, "args")?
                .into_iter()
                .map(|arg| ast_string(arg, "arg"))
                .collect::<Result<Vec<_>, _>>()?;
            Ok(Term::Lambda {
                args,
                body: Box::new(term_from_ast(ast_field(value, "body")?)?),
            })
        }
        other => Err(format!("unsupported Python AST expression node {other}")),
    }
}

fn lean_string(value: &str) -> String {
    serde_json::to_string(value).expect("string literal serializes")
}

fn lean_option_string(value: Option<&str>) -> String {
    value
        .map(|text| format!("some {}", lean_string(text)))
        .unwrap_or_else(|| "none".to_string())
}

fn lean_string_list(values: &[String]) -> String {
    values
        .iter()
        .map(|value| lean_string(value))
        .collect::<Vec<_>>()
        .join(", ")
}

fn lean_name(value: &str) -> String {
    lean_ident("fn", value)
}

fn lean_fact_name(fact: &CodeFact) -> String {
    lean_ident("fact", &fact.fact_id)
}

fn lean_ident(prefix: &str, value: &str) -> String {
    let mut name = String::new();
    let mut last_was_sep = false;
    for ch in value.chars() {
        if ch.is_ascii_alphanumeric() || ch == '_' || ch == '\'' {
            name.push(ch);
            last_was_sep = false;
        } else if !last_was_sep {
            name.push('_');
            last_was_sep = true;
        }
    }
    let name = name.trim_matches('_');
    let mut name = if name.is_empty() {
        "anonymous".to_string()
    } else {
        name.to_string()
    };
    while name.contains("__") {
        name = name.replace("__", "_");
    }
    if name.chars().next().is_some_and(|ch| ch.is_ascii_digit()) {
        name = format!("n_{name}");
    }
    format!("{prefix}_{name}")
}

fn namespace_parts(namespace: &str) -> Result<Vec<String>, String> {
    let parts: Vec<String> = namespace
        .split('.')
        .filter(|part| !part.is_empty())
        .map(str::to_string)
        .collect();
    if parts.is_empty() {
        return Err("namespace must contain at least one identifier".to_string());
    }
    for part in &parts {
        let mut chars = part.chars();
        let Some(first) = chars.next() else {
            return Err("namespace contains an empty component".to_string());
        };
        if !(first.is_ascii_alphabetic() || first == '_') {
            return Err(format!("invalid Lean namespace component: {part:?}"));
        }
        if !chars.all(|ch| ch.is_ascii_alphanumeric() || ch == '_' || ch == '\'') {
            return Err(format!("invalid Lean namespace component: {part:?}"));
        }
    }
    Ok(parts)
}

fn render_lean(
    facts: &[CodeFact],
    controls: &[ControlFact],
    ir_path: &Path,
    ir_hash: &str,
    namespace: &str,
    module_name: Option<&str>,
) -> Result<String, String> {
    let grouped = group_by_symbol(facts);
    let parts = namespace_parts(namespace)?;
    let mut lines = Vec::new();
    lines.extend(render_header(ir_path, ir_hash, module_name));
    lines.extend(render_prelude(&parts));
    for (symbol, symbol_facts) in &grouped {
        lines.extend(render_symbol_equations(symbol, symbol_facts)?);
    }
    lines.extend(render_control_facts(controls)?);
    lines.extend(render_catalog(grouped.keys()));
    lines.extend(render_substitution_route_catalog(grouped.keys()));
    close_namespaces(&mut lines, &parts);
    Ok(lines.join("\n"))
}

fn render_header(ir_path: &Path, ir_hash: &str, module_name: Option<&str>) -> Vec<String> {
    let label = module_name
        .map(str::to_string)
        .or_else(|| {
            ir_path
                .file_stem()
                .map(|value| value.to_string_lossy().to_string())
        })
        .unwrap_or_else(|| "algorithm_ir".to_string());
    let ir_name = ir_path
        .file_name()
        .map(|value| value.to_string_lossy().to_string())
        .unwrap_or_else(|| ir_path.display().to_string());
    vec![
        "/-".to_string(),
        "@dependency-start".to_string(),
        format!("responsibility Generated Lean implementation equation artifacts for {label}."),
        format!("upstream implementation ../{ir_name} Algorithm Expansion IR JSON consumed by this generated file."),
        "upstream implementation ../../../vendor/agent-canon/rust/agent-canon/src/algorithm_ir_to_lean.rs generated this file.".to_string(),
        "@dependency-end".to_string(),
        "-/".to_string(),
        String::new(),
        "/-".to_string(),
        "This file is generated. Do not hand-edit theorem content here.".to_string(),
        format!("source_ir_sha256={ir_hash}"),
        "-/".to_string(),
        String::new(),
    ]
}

fn render_prelude(parts: &[String]) -> Vec<String> {
    let mut lines = Vec::new();
    for part in parts {
        lines.push(format!("namespace {part}"));
    }
    lines.extend(
        [
            "",
            "noncomputable section",
            "",
            "mutual",
            "inductive Expr where",
            "  | name : String -> Expr",
            "  | const : String -> Expr",
            "  | none : Expr",
            "  | projection : String -> List ProjectionSegment -> Expr",
            "  | attr : Expr -> String -> Expr",
            "  | call : Expr -> List Expr -> List (String × Expr) -> Expr",
            "  | bin : String -> Expr -> Expr -> Expr",
            "  | unary : String -> Expr -> Expr",
            "  | ifThenElse : Expr -> Expr -> Expr -> Expr",
            "  | tuple : List Expr -> Expr",
            "  | list : List Expr -> Expr",
            "  | set : List Expr -> Expr",
            "  | dict : List (Option Expr × Expr) -> Expr",
            "  | subscript : Expr -> Expr -> Expr",
            "  | slice : Option Expr -> Option Expr -> Option Expr -> Expr",
            "  | compare : Expr -> List String -> List Expr -> Expr",
            "  | bool : String -> List Expr -> Expr",
            "  | lambda : List String -> Expr -> Expr",
            "deriving Repr",
            "",
            "inductive ProjectionSegment where",
            "  | attr : String -> ProjectionSegment",
            "  | index : Expr -> ProjectionSegment",
            "  | slice : Option Expr -> Option Expr -> Option Expr -> ProjectionSegment",
            "deriving Repr",
            "end",
            "",
            "structure CodeEquation where",
            "  factId : String",
            "  sourceSymbol : String",
            "  sourceSpan : String",
            "  factKind : String",
            "  target : String",
            "  expression : String",
            "  expr : Expr",
            "deriving Repr",
            "",
            "structure ControlFact where",
            "  factId : String",
            "  sourceSymbol : String",
            "  sourceSpan : String",
            "  controlKind : String",
            "  condition : Option String",
            "  conditionExpr : Option Expr",
            "  target : Option String",
            "  targetExpr : Option Expr",
            "  iterator : Option String",
            "  iteratorExpr : Option Expr",
            "  bodyTargets : List String",
            "  orelseTargets : List String",
            "  statement : String",
            "deriving Repr",
            "",
        ]
        .into_iter()
        .map(str::to_string),
    );
    lines
}

fn line_key(fact: &CodeFact) -> (u64, String) {
    let line = fact
        .source_span
        .split(':')
        .next()
        .and_then(|part| part.parse::<u64>().ok())
        .unwrap_or(0);
    (line, fact.fact_id.clone())
}

fn group_by_symbol(facts: &[CodeFact]) -> BTreeMap<String, Vec<CodeFact>> {
    let mut grouped: BTreeMap<String, Vec<CodeFact>> = BTreeMap::new();
    for fact in facts {
        if !fact.source_symbol.is_empty() {
            grouped
                .entry(fact.source_symbol.clone())
                .or_default()
                .push(fact.clone());
        }
    }
    for symbol_facts in grouped.values_mut() {
        symbol_facts.sort_by_key(line_key);
    }
    grouped
}

fn render_symbol_equations(symbol: &str, facts: &[CodeFact]) -> Result<Vec<String>, String> {
    let name = lean_name(symbol);
    let mut lines = Vec::new();
    for fact in facts {
        lines.extend(render_named_equation(fact)?);
    }
    let fact_names = facts
        .iter()
        .map(lean_fact_name)
        .collect::<Vec<_>>()
        .join(", ");
    lines.extend([
        format!("/-- Generated IR equations for implementation symbol `{symbol}`. -/"),
        format!("def {name}_equations : List CodeEquation :="),
        format!("  [{fact_names}]"),
        String::new(),
    ]);
    Ok(lines)
}

fn render_named_equation(fact: &CodeFact) -> Result<Vec<String>, String> {
    let name = lean_fact_name(fact);
    let mut lines = vec![
        format!(
            "/-- Generated code fact `{}` from implementation symbol `{}`. -/",
            fact.fact_id, fact.source_symbol
        ),
        format!("def {name} : CodeEquation :="),
    ];
    lines.extend(render_equation_body(fact)?);
    lines.push(String::new());
    Ok(lines)
}

fn render_equation_body(fact: &CodeFact) -> Result<Vec<String>, String> {
    let term = term_from_ast(&fact.expression_ast)
        .map_err(|error| format!("{} {}: {error}", fact.source_symbol, fact.target))?;
    Ok(vec![
        "{".to_string(),
        format!("  factId := {}", lean_string(&fact.fact_id)),
        format!("  sourceSymbol := {}", lean_string(&fact.source_symbol)),
        format!("  sourceSpan := {}", lean_string(&fact.source_span)),
        format!("  factKind := {}", lean_string(&fact.fact_kind)),
        format!("  target := {}", lean_string(&fact.target)),
        format!("  expression := {}", lean_string(&fact.expression)),
        format!("  expr := {}", render_term_expr(&term)),
        "}".to_string(),
    ])
}

fn render_control_facts(facts: &[ControlFact]) -> Result<Vec<String>, String> {
    let mut lines = vec![
        "/-- AST-derived branch and loop facts. -/".to_string(),
        "def generatedControlFacts : List ControlFact :=".to_string(),
        "  [".to_string(),
    ];
    for (index, fact) in facts.iter().enumerate() {
        let mut rendered = render_control_fact(fact)?;
        if index != facts.len() - 1 {
            if let Some(last) = rendered.last_mut() {
                last.push(',');
            }
        }
        lines.extend(rendered);
    }
    lines.push("  ]".to_string());
    lines.push(String::new());
    Ok(lines)
}

fn render_control_fact(fact: &ControlFact) -> Result<Vec<String>, String> {
    Ok(vec![
        "  {".to_string(),
        format!("    factId := {}", lean_string(&fact.fact_id)),
        format!("    sourceSymbol := {}", lean_string(&fact.source_symbol)),
        format!("    sourceSpan := {}", lean_string(&fact.source_span)),
        format!("    controlKind := {}", lean_string(&fact.control_kind)),
        format!(
            "    condition := {}",
            lean_option_string(fact.condition.as_deref())
        ),
        format!(
            "    conditionExpr := {}",
            render_optional_ast(fact.condition_ast.as_ref())?
        ),
        format!(
            "    target := {}",
            lean_option_string(fact.target.as_deref())
        ),
        format!(
            "    targetExpr := {}",
            render_optional_ast(fact.target_ast.as_ref())?
        ),
        format!(
            "    iterator := {}",
            lean_option_string(fact.iterator.as_deref())
        ),
        format!(
            "    iteratorExpr := {}",
            render_optional_ast(fact.iterator_ast.as_ref())?
        ),
        format!(
            "    bodyTargets := [{}]",
            lean_string_list(&fact.body_targets)
        ),
        format!(
            "    orelseTargets := [{}]",
            lean_string_list(&fact.orelse_targets)
        ),
        format!("    statement := {}", lean_string(&fact.statement)),
        "  }".to_string(),
    ])
}

fn render_optional_ast(value: Option<&Value>) -> Result<String, String> {
    match value {
        Some(ast) => Ok(format!("some ({})", render_term_expr(&term_from_ast(ast)?))),
        None => Ok("none".to_string()),
    }
}

fn render_catalog<'a>(symbols: impl Iterator<Item = &'a String>) -> Vec<String> {
    let names = symbols
        .map(|symbol| lean_string(symbol))
        .collect::<Vec<_>>()
        .join(", ");
    vec![
        "def generatedSourceSymbols : List String :=".to_string(),
        format!("  [{names}]"),
        String::new(),
    ]
}

fn render_substitution_route_catalog<'a>(symbols: impl Iterator<Item = &'a String>) -> Vec<String> {
    let symbols: Vec<&String> = symbols.collect();
    let mut lines = vec![
        "/--".to_string(),
        "Generated implementation substitution routes.".to_string(),
        String::new(),
        "Each route is the ordered assignment/return equation list for one".to_string(),
        "source symbol. Proof modules consume these routes before introducing".to_string(),
        "theorem-specific mathematical bridges.".to_string(),
        "-/".to_string(),
        "abbrev SubstitutionRoute := List CodeEquation".to_string(),
        String::new(),
        "def substitutionRouteTargets (route : SubstitutionRoute) : List String :=".to_string(),
        "  route.map CodeEquation.target".to_string(),
        String::new(),
        "def substitutionRouteExpressions (route : SubstitutionRoute) : List String :=".to_string(),
        "  route.map CodeEquation.expression".to_string(),
        String::new(),
    ];
    for symbol in &symbols {
        let name = lean_name(symbol);
        lines.extend([
            format!("/-- Ordered assignment/return route for implementation symbol `{symbol}`. -/"),
            format!("def {name}_substitutionRoute : SubstitutionRoute :="),
            format!("  {name}_equations"),
            String::new(),
        ]);
    }
    let route_pairs = symbols
        .iter()
        .map(|symbol| {
            format!(
                "({}, {}_substitutionRoute)",
                lean_string(symbol),
                lean_name(symbol)
            )
        })
        .collect::<Vec<_>>()
        .join(", ");
    lines.extend([
        "def generatedSubstitutionRoutes : List (String × SubstitutionRoute) :=".to_string(),
        format!("  [{route_pairs}]"),
        String::new(),
    ]);
    lines
}

fn render_term_expr(term: &Term) -> String {
    match term {
        Term::Name(value) => format!("Expr.name {}", lean_string(value)),
        Term::Const(value) => format!("Expr.const {}", lean_string(value)),
        Term::None => "Expr.none".to_string(),
        Term::Projection(path) => render_projection(path),
        Term::Attr(value, attr) => {
            format!(
                "Expr.attr ({}) {}",
                render_term_expr(value),
                lean_string(attr)
            )
        }
        Term::Call {
            func,
            args,
            keywords,
        } => {
            let args = args
                .iter()
                .map(render_term_expr)
                .collect::<Vec<_>>()
                .join(", ");
            let keywords = keywords
                .iter()
                .map(|(key, value)| format!("({}, {})", lean_string(key), render_term_expr(value)))
                .collect::<Vec<_>>()
                .join(", ");
            format!(
                "Expr.call ({}) ([{}]) ([{}])",
                render_term_expr(func),
                args,
                keywords
            )
        }
        Term::Bin { op, left, right } => format!(
            "Expr.bin {} ({}) ({})",
            lean_string(op),
            render_term_expr(left),
            render_term_expr(right)
        ),
        Term::Unary { op, value } => {
            format!(
                "Expr.unary {} ({})",
                lean_string(op),
                render_term_expr(value)
            )
        }
        Term::IfThenElse { test, body, orelse } => format!(
            "Expr.ifThenElse ({}) ({}) ({})",
            render_term_expr(test),
            render_term_expr(body),
            render_term_expr(orelse)
        ),
        Term::Tuple(items) => {
            let items = items
                .iter()
                .map(render_term_expr)
                .collect::<Vec<_>>()
                .join(", ");
            format!("Expr.tuple [{items}]")
        }
        Term::List(items) => {
            let items = items
                .iter()
                .map(render_term_expr)
                .collect::<Vec<_>>()
                .join(", ");
            format!("Expr.list [{items}]")
        }
        Term::Set(items) => {
            let items = items
                .iter()
                .map(render_term_expr)
                .collect::<Vec<_>>()
                .join(", ");
            format!("Expr.set [{items}]")
        }
        Term::Dict(items) => {
            let items = items
                .iter()
                .map(|(key, value)| {
                    let key = key
                        .as_ref()
                        .map(|item| format!("some ({})", render_term_expr(item)))
                        .unwrap_or_else(|| "none".to_string());
                    format!("({}, {})", key, render_term_expr(value))
                })
                .collect::<Vec<_>>()
                .join(", ");
            format!("Expr.dict [{items}]")
        }
        Term::Subscript { value, index } => {
            format!(
                "Expr.subscript ({}) ({})",
                render_term_expr(value),
                render_term_expr(index)
            )
        }
        Term::Slice { lower, upper, step } => format!(
            "Expr.slice ({}) ({}) ({})",
            render_optional_expr(lower.as_deref()),
            render_optional_expr(upper.as_deref()),
            render_optional_expr(step.as_deref())
        ),
        Term::Compare {
            left,
            ops,
            comparators,
        } => {
            let ops = ops
                .iter()
                .map(|op| lean_string(op))
                .collect::<Vec<_>>()
                .join(", ");
            let comparators = comparators
                .iter()
                .map(render_term_expr)
                .collect::<Vec<_>>()
                .join(", ");
            format!(
                "Expr.compare ({}) [{}] [{}]",
                render_term_expr(left),
                ops,
                comparators
            )
        }
        Term::Bool { op, values } => {
            let values = values
                .iter()
                .map(render_term_expr)
                .collect::<Vec<_>>()
                .join(", ");
            format!("Expr.bool {} [{values}]", lean_string(op))
        }
        Term::Lambda { args, body } => {
            let args = args
                .iter()
                .map(|arg| lean_string(arg))
                .collect::<Vec<_>>()
                .join(", ");
            format!("Expr.lambda [{args}] ({})", render_term_expr(body))
        }
    }
}

fn render_projection(path: &ProjectionPath) -> String {
    let segments = path
        .segments
        .iter()
        .map(render_projection_segment)
        .collect::<Vec<_>>()
        .join(", ");
    format!("Expr.projection {} [{segments}]", lean_string(&path.root))
}

fn render_projection_segment(segment: &ProjectionSegment) -> String {
    match segment {
        ProjectionSegment::Attr(value) => {
            format!("ProjectionSegment.attr {}", lean_string(value))
        }
        ProjectionSegment::Index(value) => {
            format!("ProjectionSegment.index ({})", render_term_expr(value))
        }
        ProjectionSegment::Slice { lower, upper, step } => format!(
            "ProjectionSegment.slice ({}) ({}) ({})",
            render_optional_expr(lower.as_deref()),
            render_optional_expr(upper.as_deref()),
            render_optional_expr(step.as_deref())
        ),
    }
}

fn render_optional_expr(term: Option<&Term>) -> String {
    match term {
        Some(value) => format!("some ({})", render_term_expr(value)),
        None => "none".to_string(),
    }
}

fn close_namespaces(lines: &mut Vec<String>, parts: &[String]) {
    lines.push("end".to_string());
    for part in parts.iter().rev() {
        lines.push(format!("end {part}"));
    }
    lines.push(String::new());
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn name(value: &str) -> Value {
        json!({"node": "Name", "id": value, "ctx": {"node": "Load"}})
    }

    fn attr(base: Value, name: &str) -> Value {
        json!({"node": "Attribute", "value": base, "attr": name, "ctx": {"node": "Load"}})
    }

    fn call(func: Value, args: Vec<Value>) -> Value {
        json!({"node": "Call", "func": func, "args": args, "keywords": []})
    }

    #[test]
    fn lowers_attribute_chains_to_projection_paths() {
        let ast = attr(attr(name("carry"), "answer"), "status");
        let term = term_from_ast(&ast).unwrap();
        assert_eq!(
            term,
            Term::Projection(ProjectionPath {
                root: "carry".to_string(),
                segments: vec![
                    ProjectionSegment::Attr("answer".to_string()),
                    ProjectionSegment::Attr("status".to_string())
                ],
            })
        );
        assert_eq!(
            render_term_expr(&term),
            "Expr.projection \"carry\" [ProjectionSegment.attr \"answer\", ProjectionSegment.attr \"status\"]"
        );
    }

    #[test]
    fn lowers_calls_without_python_string_parsing() {
        let ast = call(
            name("solve_direction"),
            vec![attr(name("problem"), "objective"), name("state")],
        );
        let rendered = render_term_expr(&term_from_ast(&ast).unwrap());
        assert!(rendered.contains("Expr.call (Expr.name \"solve_direction\")"));
        assert!(
            rendered.contains("Expr.projection \"problem\" [ProjectionSegment.attr \"objective\"]")
        );
    }

    #[test]
    fn rejects_code_facts_without_expression_ast() {
        let payload = json!({
            "code_facts": [{
                "fact_id": "fact_missing",
                "source_symbol": "solve",
                "source_span": "1:1",
                "fact_kind": "assignment_equation",
                "target": "x",
                "expression": "legacy_string_only()"
            }]
        });
        let error = code_facts(&payload).unwrap_err();
        assert!(error.contains("missing expression_ast"));
    }

    #[test]
    fn renders_generic_control_facts() {
        let fact = ControlFact {
            fact_id: "ctrl_1".to_string(),
            source_symbol: "solve".to_string(),
            source_span: "10:4".to_string(),
            control_kind: "if".to_string(),
            condition: Some("res <= tol".to_string()),
            condition_ast: Some(json!({
                "node": "Compare",
                "left": {"node": "Name", "id": "res", "ctx": {"node": "Load"}},
                "ops": [{"node": "LtE"}],
                "comparators": [{"node": "Name", "id": "tol", "ctx": {"node": "Load"}}]
            })),
            target: None,
            target_ast: None,
            iterator: None,
            iterator_ast: None,
            body_targets: vec!["return".to_string()],
            orelse_targets: vec!["state".to_string()],
            statement: "if res <= tol".to_string(),
        };
        let rendered = render_control_facts(&[fact]).unwrap().join("\n");
        assert!(rendered.contains("def generatedControlFacts : List ControlFact :="));
        assert!(rendered.contains("controlKind := \"if\""));
        assert!(rendered.contains("conditionExpr := some (Expr.compare"));
    }

    #[test]
    fn end_to_end_writes_generic_lean_module() {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("agent-canon-ir-to-lean-{suffix}"));
        fs::create_dir_all(&root).unwrap();
        let ir_path = root.join("sample_ir.json");
        let out_path = root.join("Generated.lean");
        fs::write(
            &ir_path,
            serde_json::to_string(&json!({
                "code_facts": [{
                    "fact_id": "fact_solve_1",
                    "source_symbol": "solve",
                    "source_span": "10:4",
                    "fact_kind": "assignment_equation",
                    "target": "direction",
                    "expression": "solve_direction(problem, state)",
                    "expression_ast": {
                        "node": "Call",
                        "func": {"node": "Name", "id": "solve_direction", "ctx": {"node": "Load"}},
                        "args": [
                            {"node": "Name", "id": "problem", "ctx": {"node": "Load"}},
                            {"node": "Name", "id": "state", "ctx": {"node": "Load"}}
                        ],
                        "keywords": []
                    }
                }],
                "control_facts": []
            }))
            .unwrap(),
        )
        .unwrap();
        let args = Args {
            algorithm_ir: ir_path,
            namespace: "Sample.Generated".to_string(),
            module_name: None,
            out: out_path.clone(),
        };
        run_checked(args).unwrap();
        let generated = fs::read_to_string(out_path).unwrap();
        assert!(generated.contains("namespace Sample"));
        assert!(generated.contains("inductive Expr where"));
        assert!(generated.contains("inductive ProjectionSegment where"));
        assert!(generated.contains("def fact_fact_solve_1 : CodeEquation :="));
        assert!(generated.contains("def fn_solve_equations : List CodeEquation :="));
        assert!(generated.contains("  [fact_fact_solve_1]"));
        assert!(generated.contains("expr := Expr.call (Expr.name \"solve_direction\")"));
        assert!(!generated.contains("Expr.raw"));
        assert!(!generated.contains("axiom eval"));
        fs::remove_dir_all(root).unwrap();
    }
}
