// @dependency-start
// contract implementation
// responsibility Lowers consumer-selected JAX roots into StableHLO and assembles JIT-canonical operational IR evidence.
// upstream implementation stablehlo_value_closure.rs owns the shared typed operational IR reader
// upstream implementation python-provider/src/jit_runtime.rs owns safe calls into consumer Python/JAX functions
// upstream design ../../../../../documents/tools/jit_canonical_ir.md owns the extraction and backend evidence contract
// downstream implementation jit_ir_to_lean.rs consumes the generated JIT-canonical record
// downstream implementation main.rs exposes jit-canonical-ir
// @dependency-end

//! Native JIT-canonical IR extraction and backend evidence collection.

use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use regex::Regex;
use rustpython_ast::{Expr, Ranged, Stmt};
use rustpython_parser::{ast, Parse};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

pub const SELECTOR: &str = "jit-canonical-ir";
const PROVIDER_ENV: &str = "AGENT_CANON_PYTHON_PROVIDER";
const JAX_PLATFORM_ENV: &str = "AGENT_CANON_JIT_JAX_PLATFORM";
const BACKEND_TARGET_ENV: &str = "AGENT_CANON_JIT_BACKEND_TARGET";
const INPUT_DEVICE_ENV: &str = "AGENT_CANON_JIT_INPUT_DEVICE";
const CUDA_VISIBLE_ENV: &str = "AGENT_CANON_JIT_CUDA_VISIBLE_DEVICES";
const IREE_CUDA_TARGET_ENV: &str = "AGENT_CANON_JIT_IREE_CUDA_TARGET";
const GPU_BLOCKED: &str = "gpu_route_blocked=canonical_managed_experiment_runner_required:tools/experiments/execution/run_managed_experiment.py";
const USAGE: &str = "usage: agent-canon jit-canonical-ir --python-symbol PATH::QUALNAME --input-factory PATH::QUALNAME --out PATH [--xla-flags FLAGS] [--xla-dump-dir PATH] [--backend-trace-dir PATH] [--no-source-root] [--no-backend-trace] [--stablehlo-out PATH] [--backend-trace-out PATH]";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum OptionName {
    PythonSymbol,
    InputFactory,
    XlaFlags,
    XlaDumpDir,
    BackendTraceDir,
    NoSourceRoot,
    NoBackendTrace,
    Out,
    StablehloOut,
    BackendTraceOut,
    Help,
}

const OPTIONS: &[(&str, OptionName)] = &[
    ("--python-symbol", OptionName::PythonSymbol),
    ("--input-factory", OptionName::InputFactory),
    ("--xla-flags", OptionName::XlaFlags),
    ("--xla-dump-dir", OptionName::XlaDumpDir),
    ("--backend-trace-dir", OptionName::BackendTraceDir),
    ("--no-source-root", OptionName::NoSourceRoot),
    ("--no-backend-trace", OptionName::NoBackendTrace),
    ("--out", OptionName::Out),
    ("--stablehlo-out", OptionName::StablehloOut),
    ("--backend-trace-out", OptionName::BackendTraceOut),
    ("--help", OptionName::Help),
];

#[derive(Default)]
struct Args {
    python_symbol: Option<String>,
    input_factory: Option<String>,
    xla_flags: Option<String>,
    xla_dump_dir: Option<PathBuf>,
    backend_trace_dir: Option<PathBuf>,
    no_source_root: bool,
    no_backend_trace: bool,
    out: Option<PathBuf>,
    stablehlo_out: Option<PathBuf>,
    backend_trace_out: Option<PathBuf>,
}

enum ParseResult {
    Help,
    Run(Box<Args>),
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
            LongOptionError::Ambiguous(options) => {
                format!(
                    "ambiguous option: {name} could match {}",
                    options.join(", ")
                )
            }
        })?;
        if option == OptionName::Help {
            if inline.is_some() {
                return Err(format!(
                    "argument --help: ignored explicit argument '{token}'"
                ));
            }
            return Ok(ParseResult::Help);
        }
        if matches!(
            option,
            OptionName::NoSourceRoot | OptionName::NoBackendTrace
        ) {
            if inline.is_some() {
                return Err(format!(
                    "argument {name}: ignored explicit argument '{token}'"
                ));
            }
            match option {
                OptionName::NoSourceRoot => args.no_source_root = true,
                OptionName::NoBackendTrace => args.no_backend_trace = true,
                _ => unreachable!(),
            }
            index += 1;
            continue;
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
            OptionName::PythonSymbol => args.python_symbol = Some(value),
            OptionName::InputFactory => args.input_factory = Some(value),
            OptionName::XlaFlags => args.xla_flags = Some(value),
            OptionName::XlaDumpDir => args.xla_dump_dir = Some(value.into()),
            OptionName::BackendTraceDir => args.backend_trace_dir = Some(value.into()),
            OptionName::Out => args.out = Some(value.into()),
            OptionName::StablehloOut => args.stablehlo_out = Some(value.into()),
            OptionName::BackendTraceOut => args.backend_trace_out = Some(value.into()),
            OptionName::NoSourceRoot | OptionName::NoBackendTrace | OptionName::Help => {
                unreachable!()
            }
        }
        index += 1;
    }
    if args.python_symbol.is_none() {
        return Err("the following arguments are required: --python-symbol".into());
    }
    if args.input_factory.is_none() {
        return Err("the following arguments are required: --input-factory".into());
    }
    if args.out.is_none() {
        return Err("the following arguments are required: --out".into());
    }
    Ok(ParseResult::Run(Box::new(args)))
}

#[derive(Debug)]
struct RuntimeConfig {
    jax_platform: String,
    backend_target: Option<String>,
    input_device: Option<String>,
    cuda_visible_devices: Option<String>,
    iree_cuda_target: Option<String>,
}

fn optional_env(name: &str, keep_empty: bool) -> Option<String> {
    env::var(name)
        .ok()
        .map(|value| value.trim().to_owned())
        .filter(|value| keep_empty || !value.is_empty())
}

fn runtime_config(include_backend_trace: bool) -> Result<RuntimeConfig, String> {
    let jax_platform = optional_env(JAX_PLATFORM_ENV, false)
        .ok_or_else(|| format!("backend_env_missing={JAX_PLATFORM_ENV}"))?;
    let backend_target = optional_env(BACKEND_TARGET_ENV, false);
    if include_backend_trace && backend_target.is_none() {
        return Err(format!("backend_env_missing={BACKEND_TARGET_ENV}"));
    }
    Ok(RuntimeConfig {
        jax_platform,
        backend_target,
        input_device: optional_env(INPUT_DEVICE_ENV, false),
        cuda_visible_devices: optional_env(CUDA_VISIBLE_ENV, true),
        iree_cuda_target: optional_env(IREE_CUDA_TARGET_ENV, false),
    })
}

fn configure_jax(args: &Args, config: &RuntimeConfig) -> Result<(), String> {
    let _requested_cuda_visibility = config.cuda_visible_devices.as_deref();
    if ["gpu", "cuda"].contains(&config.jax_platform.as_str()) {
        return Err(GPU_BLOCKED.into());
    }
    if config.jax_platform != "cpu" {
        env::set_var("JAX_PLATFORM_NAME", &config.jax_platform);
        env::set_var(
            "XLA_PYTHON_CLIENT_PREALLOCATE",
            env::var("XLA_PYTHON_CLIENT_PREALLOCATE").unwrap_or_else(|_| "false".into()),
        );
    } else {
        env::set_var("JAX_PLATFORMS", "cpu");
        if env::var_os("CUDA_VISIBLE_DEVICES").is_none() {
            env::set_var("CUDA_VISIBLE_DEVICES", "");
        }
        env::set_var("JAX_PLATFORM_NAME", "cpu");
        if env::var_os("XLA_PYTHON_CLIENT_PREALLOCATE").is_none() {
            env::set_var("XLA_PYTHON_CLIENT_PREALLOCATE", "false");
        }
    }
    if let Some(dump_dir) = args.xla_dump_dir.as_ref() {
        if dump_dir.exists() {
            fs::remove_dir_all(dump_dir).map_err(|error| {
                format!(
                    "cannot replace XLA dump directory {}: {error}",
                    dump_dir.display()
                )
            })?;
        }
        fs::create_dir_all(dump_dir).map_err(|error| {
            format!(
                "cannot create XLA dump directory {}: {error}",
                dump_dir.display()
            )
        })?;
    }
    let mut requested = args
        .xla_flags
        .as_deref()
        .unwrap_or_default()
        .split_whitespace()
        .map(str::to_owned)
        .collect::<Vec<_>>();
    if let Some(dump_dir) = args.xla_dump_dir.as_ref() {
        requested.push(format!("--xla_dump_to={}", dump_dir.display()));
        requested.push("--xla_dump_hlo_as_text".into());
    }
    if !requested.is_empty() {
        let mut merged = env::var("XLA_FLAGS")
            .unwrap_or_default()
            .split_whitespace()
            .map(str::to_owned)
            .collect::<Vec<_>>();
        for flag in requested {
            let key = flag.split_once('=').map_or(flag.as_str(), |(key, _)| key);
            if !merged.iter().any(|existing| {
                existing
                    .split_once('=')
                    .map_or(existing.as_str(), |(key, _)| key)
                    == key
            }) {
                merged.push(flag);
            }
        }
        env::set_var("XLA_FLAGS", merged.join(" "));
    }
    Ok(())
}

fn sha256(text: &str) -> String {
    format!("{:x}", Sha256::digest(text.as_bytes()))
}

fn provider_result(args: &Args, config: &RuntimeConfig, cwd: &Path) -> Result<Value, String> {
    let provider =
        env::var_os(PROVIDER_ENV).unwrap_or_else(|| "agent-canon-python-provider".into());
    let mut command = Command::new(&provider);
    command
        .arg("jit-lower")
        .arg(args.python_symbol.as_deref().unwrap_or_default())
        .arg(args.input_factory.as_deref().unwrap_or_default())
        .arg(config.input_device.as_deref().unwrap_or_default())
        .arg((args.xla_dump_dir.is_some() && !args.no_backend_trace).to_string())
        .current_dir(cwd);
    if config.jax_platform != "cpu" {
        command.env("JAX_PLATFORM_NAME", &config.jax_platform);
    }
    let output = command
        .output()
        .map_err(|error| format!("Python/JAX provider unavailable: {error}"))?;
    let value: Value = serde_json::from_slice(&output.stdout).map_err(|error| {
        format!(
            "Python/JAX provider returned invalid JSON (exit {}): {error}",
            output.status.code().unwrap_or(1)
        )
    })?;
    if !output.status.success() || value.get("status").and_then(Value::as_str) == Some("fail") {
        return Err(value
            .get("error")
            .and_then(Value::as_str)
            .map(str::to_owned)
            .unwrap_or_else(|| String::from_utf8_lossy(&output.stderr).trim().to_owned()));
    }
    Ok(value)
}

fn classify_opcode(opcode: &str) -> &'static str {
    match opcode {
        "func.func" => "Function",
        "return" => "Return",
        "func.call" | "call" => "Call",
        "stablehlo.while" | "mhlo.while" | "scf.while" => "While",
        "stablehlo.if" | "mhlo.if" | "scf.if" => "If",
        "stablehlo.case" | "mhlo.case" => "Case",
        "stablehlo.tuple" | "mhlo.tuple" => "Tuple",
        "stablehlo.get_tuple_element" | "mhlo.get_tuple_element" => "Projection",
        _ => "Primitive",
    }
}

#[derive(Clone, Debug)]
struct Region {
    region_id: String,
    kind: String,
    parent_function: String,
    parent_op_id: String,
    depth: usize,
    line_start: usize,
    line_end: Option<usize>,
    op_ids: Vec<String>,
    close_reason: String,
}

#[allow(clippy::too_many_arguments)]
fn open_region(
    regions: &mut Vec<Region>,
    edges: &mut Vec<Value>,
    stack: &mut Vec<String>,
    kind: &str,
    parent_function: &str,
    parent_op_id: &str,
    line_start: usize,
    edge_kind: &str,
    edge_from: &str,
) -> String {
    let region_id = format!("region_{:05}", regions.len());
    regions.push(Region {
        region_id: region_id.clone(),
        kind: kind.to_owned(),
        parent_function: parent_function.to_owned(),
        parent_op_id: parent_op_id.to_owned(),
        depth: stack.len(),
        line_start,
        line_end: None,
        op_ids: Vec::new(),
        close_reason: String::new(),
    });
    stack.push(region_id.clone());
    edges.push(json!({"edge_id": format!("edge_{:05}", edges.len()), "kind": edge_kind, "from": edge_from, "to": region_id}));
    region_id
}

fn extract_operational_ir(stablehlo: &str) -> Value {
    let op_regex =
        Regex::new(r"\b(?:stablehlo|mhlo|chlo|func|scf|arith)\.[A-Za-z0-9_]+|\breturn\b|\bcall\b")
            .expect("valid opcode regex");
    let tensor_regex = Regex::new(r"tensor<([^>]+)>").expect("valid tensor regex");
    let dtype_regex = Regex::new(r"\b(?:bf16|f16|f32|f64|i1|i8|i16|i32|i64|ui8|ui16|ui32|ui64)\b")
        .expect("valid dtype regex");
    let function_regex =
        Regex::new(r"\bfunc\.func(?:\s+public|\s+private)?\s+@(?P<name>[-A-Za-z0-9_.$]+)")
            .expect("valid function regex");
    let call_regex = Regex::new(r"@(?P<name>[-A-Za-z0-9_.$]+)").expect("valid call regex");
    let mut ops = Vec::<Value>::new();
    let mut functions = Vec::<Value>::new();
    let mut regions = Vec::<Region>::new();
    let mut edges = Vec::<Value>::new();
    let mut region_stack = Vec::<String>::new();
    let mut function_stack = Vec::<String>::new();
    let mut while_stack = Vec::<String>::new();
    let mut case_stack = Vec::<(String, usize)>::new();
    let mut function_signatures = Vec::<String>::new();
    open_region(
        &mut regions,
        &mut edges,
        &mut region_stack,
        "module",
        "",
        "",
        1,
        "program_root",
        "program",
    );
    let close_region = |line: usize,
                        regions: &mut Vec<Region>,
                        stack: &mut Vec<String>,
                        functions: &mut Vec<Value>,
                        function_stack: &mut Vec<String>,
                        while_stack: &mut Vec<String>,
                        case_stack: &mut Vec<(String, usize)>| {
        if stack.len() <= 1 {
            if let Some(root) = stack
                .first()
                .and_then(|id| regions.iter_mut().find(|region| region.region_id == *id))
            {
                root.line_end = Some(line);
            }
            return;
        }
        if let Some(region_id) = stack.pop() {
            if let Some(region) = regions
                .iter_mut()
                .find(|region| region.region_id == region_id)
            {
                region.line_end = Some(line);
                match region.kind.as_str() {
                    "function_body" => {
                        if let Some(name) = function_stack.pop() {
                            if let Some(function) = functions.iter_mut().find(|function| {
                                function.get("name").and_then(Value::as_str) == Some(name.as_str())
                            }) {
                                function["line_end"] = json!(line);
                            }
                        }
                    }
                    "while_do" => {
                        while_stack.pop();
                    }
                    "case_branch"
                        if region.close_reason == "case_end"
                            && case_stack
                                .last()
                                .is_some_and(|(op_id, _)| *op_id == region.parent_op_id) =>
                    {
                        case_stack.pop();
                    }
                    _ => {}
                }
            }
        }
    };
    for (line_index, raw_line) in stablehlo.lines().enumerate() {
        let line_no = line_index + 1;
        let stripped = raw_line.trim();
        if stripped.is_empty() {
            continue;
        }
        if stripped.starts_with("})") {
            if let Some(id) = region_stack.last() {
                if let Some(region) = regions.iter_mut().find(|region| region.region_id == *id) {
                    region.close_reason = "case_end".into();
                }
            }
            close_region(
                line_no,
                &mut regions,
                &mut region_stack,
                &mut functions,
                &mut function_stack,
                &mut while_stack,
                &mut case_stack,
            );
            continue;
        }
        if stripped.starts_with("},") {
            close_region(
                line_no,
                &mut regions,
                &mut region_stack,
                &mut functions,
                &mut function_stack,
                &mut while_stack,
                &mut case_stack,
            );
            if stripped.contains('{') {
                if let Some((op_id, next_branch)) = case_stack.last_mut() {
                    let index = *next_branch;
                    *next_branch += 1;
                    open_region(
                        &mut regions,
                        &mut edges,
                        &mut region_stack,
                        "case_branch",
                        function_stack.last().map_or("", String::as_str),
                        op_id,
                        line_no,
                        &format!("case_branch_{index}"),
                        op_id,
                    );
                }
            }
            continue;
        }
        if stripped.starts_with("} do") {
            close_region(
                line_no,
                &mut regions,
                &mut region_stack,
                &mut functions,
                &mut function_stack,
                &mut while_stack,
                &mut case_stack,
            );
            if let Some(parent_op_id) = while_stack.last().cloned() {
                open_region(
                    &mut regions,
                    &mut edges,
                    &mut region_stack,
                    "while_do",
                    function_stack.last().map_or("", String::as_str),
                    &parent_op_id,
                    line_no,
                    "while_do",
                    &parent_op_id,
                );
            }
            continue;
        }
        if stripped.starts_with('}') {
            close_region(
                line_no,
                &mut regions,
                &mut region_stack,
                &mut functions,
                &mut function_stack,
                &mut while_stack,
                &mut case_stack,
            );
            continue;
        }
        if stripped == "cond {" {
            if let Some(parent_op_id) = while_stack.last().cloned() {
                open_region(
                    &mut regions,
                    &mut edges,
                    &mut region_stack,
                    "while_cond",
                    function_stack.last().map_or("", String::as_str),
                    &parent_op_id,
                    line_no,
                    "while_cond",
                    &parent_op_id,
                );
            }
            continue;
        }
        let Some(opcode_match) = op_regex.find(stripped) else {
            continue;
        };
        let opcode = opcode_match.as_str();
        let kind = classify_opcode(opcode);
        let Some(current_region) = region_stack.last().cloned() else {
            continue;
        };
        let mut current_function = function_stack.last().cloned().unwrap_or_default();
        let mut call_target = String::new();
        if kind == "Call" {
            call_target = call_regex
                .captures(stripped)
                .and_then(|caps| caps.name("name"))
                .map_or(String::new(), |value| value.as_str().to_owned());
        }
        if kind == "Function" {
            function_signatures.push(stripped.to_owned());
            current_function = function_regex
                .captures(stripped)
                .and_then(|caps| caps.name("name"))
                .map_or_else(
                    || format!("anonymous_{:05}", functions.len()),
                    |value| value.as_str().to_owned(),
                );
            functions.push(json!({"function_id":format!("function:{current_function}"),"name":current_function,"signature":stripped,"line_start":line_no,"line_end":Value::Null,"body_region_id":""}));
        }
        let mut dtypes = dtype_regex
            .find_iter(stripped)
            .map(|value| value.as_str().to_owned())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>();
        dtypes.sort();
        let op_id = format!("op_{:05}", ops.len());
        let region_path = region_stack.clone();
        let parent_op_id = regions
            .iter()
            .find(|region| region.region_id == current_region)
            .map_or("", |region| region.parent_op_id.as_str())
            .to_owned();
        let tensor_types = tensor_regex
            .captures_iter(stripped)
            .filter_map(|caps| caps.get(1).map(|value| value.as_str().to_owned()))
            .collect::<Vec<_>>();
        ops.push(json!({
            "op_id":op_id,"kind":kind,"opcode":opcode,"line":line_no,"text":stripped,"text_sha256":sha256(stripped),
            "tensor_types":tensor_types,"dtypes":dtypes,"function":current_function,"region_id":current_region,"region_path":region_path,"parent_op_id":parent_op_id,"call_target":call_target
        }));
        if let Some(region) = regions
            .iter_mut()
            .find(|region| region.region_id == current_region)
        {
            region.op_ids.push(op_id.clone());
        }
        if !call_target.is_empty() {
            edges.push(json!({"edge_id":format!("edge_{:05}",edges.len()),"kind":"call_target","from":op_id,"to":format!("function:{call_target}")}));
        }
        match kind {
            "Function" => {
                let body_id = open_region(
                    &mut regions,
                    &mut edges,
                    &mut region_stack,
                    "function_body",
                    &current_function,
                    &op_id,
                    line_no,
                    "function_body",
                    &format!("function:{current_function}"),
                );
                if let Some(function) = functions.iter_mut().find(|function| {
                    function.get("name").and_then(Value::as_str) == Some(current_function.as_str())
                }) {
                    function["body_region_id"] = json!(body_id);
                }
                function_stack.push(current_function);
            }
            "While" => while_stack.push(op_id),
            "Case" => {
                case_stack.push((op_id.clone(), 1));
                open_region(
                    &mut regions,
                    &mut edges,
                    &mut region_stack,
                    "case_branch",
                    function_stack.last().map_or("", String::as_str),
                    &op_id,
                    line_no,
                    "case_branch_0",
                    &op_id,
                );
            }
            _ => {}
        }
    }
    let line_count = stablehlo.lines().count();
    while region_stack.len() > 1 {
        close_region(
            line_count,
            &mut regions,
            &mut region_stack,
            &mut functions,
            &mut function_stack,
            &mut while_stack,
            &mut case_stack,
        );
    }
    if let Some(root) = regions.first_mut() {
        root.line_end = Some(line_count);
    }
    for region in &mut regions {
        if region.line_end.is_none() {
            region.line_end = Some(line_count);
        }
    }
    for function in &mut functions {
        if function["line_end"].is_null() {
            function["line_end"] = json!(line_count);
        }
    }
    let assigned_region_ids = ops
        .iter()
        .filter_map(|op| op.get("region_id").and_then(Value::as_str))
        .collect::<BTreeSet<_>>();
    let known_region_ids = regions
        .iter()
        .map(|region| region.region_id.as_str())
        .collect::<BTreeSet<_>>();
    let unassigned_ops = ops
        .iter()
        .filter(|op| {
            op.get("region_id")
                .and_then(Value::as_str)
                .is_some_and(|id| !known_region_ids.contains(id))
        })
        .filter_map(|op| op.get("op_id").cloned())
        .collect::<Vec<_>>();
    let function_ids = functions
        .iter()
        .filter_map(|function| function.get("function_id").and_then(Value::as_str))
        .collect::<BTreeSet<_>>();
    let unresolved = ops
        .iter()
        .filter_map(|op| op.get("call_target").and_then(Value::as_str))
        .filter(|target| {
            !target.is_empty() && !function_ids.contains(format!("function:{target}").as_str())
        })
        .map(str::to_owned)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let max_depth = regions
        .iter()
        .map(|region| region.depth)
        .max()
        .unwrap_or_default();
    let count_kind = |kind: &str| {
        ops.iter()
            .filter(|op| op.get("kind").and_then(Value::as_str) == Some(kind))
            .count()
    };
    let region_json = regions.iter().map(|region| json!({"region_id":region.region_id,"kind":region.kind,"parent_function":region.parent_function,"parent_op_id":region.parent_op_id,"depth":region.depth,"line_start":region.line_start,"line_end":region.line_end.unwrap_or_default(),"op_ids":region.op_ids})).collect::<Vec<_>>();
    json!({
        "schema":"agent-canon.thin-operational-ir.v2",
        "allowed_kinds":["Function","Let","Call","If","While","Case","Tuple","Projection","Primitive","Return"],
        "function_signatures":function_signatures,
        "functions":functions,
        "regions":region_json,
        "expansion_edges":edges,
        "ops":ops,
        "coverage":{
            "function_count":functions.len(),"region_count":regions.len(),"expansion_edge_count":edges.len(),"op_count":ops.len(),
            "assigned_region_count":assigned_region_ids.len(),"unassigned_op_count":unassigned_ops.len(),"unassigned_op_ids":unassigned_ops,
            "unresolved_call_targets":unresolved,"max_region_depth":max_depth,"while_count":count_kind("While"),"case_count":count_kind("Case"),
            "if_count":count_kind("If"),"call_count":count_kind("Call")
        }
    })
}

fn sha256_text(text: &str) -> String {
    sha256(text)
}

#[derive(Clone, Debug)]
struct SourceSignature {
    path: PathBuf,
    qualname: String,
    name: String,
    parameters: Vec<Value>,
    return_annotation: String,
    body_statement_count: usize,
    source_sha256: String,
    main_pattern: Option<Value>,
}

fn function_in_suite<'a>(suite: &'a [Stmt], parts: &[&str]) -> Option<&'a Stmt> {
    let part = *parts.first()?;
    for statement in suite {
        let body = match statement {
            Stmt::FunctionDef(node) if node.name.as_str() == part => {
                if parts.len() == 1 {
                    return Some(statement);
                }
                continue;
            }
            Stmt::AsyncFunctionDef(node) if node.name.as_str() == part => {
                if parts.len() == 1 {
                    return Some(statement);
                }
                continue;
            }
            Stmt::ClassDef(node) if node.name.as_str() == part => &node.body,
            _ => continue,
        };
        if parts.len() > 1 {
            if let Some(found) = function_in_suite(body, &parts[1..]) {
                return Some(found);
            }
        }
    }
    None
}

fn source_segment(source: &str, node: &impl Ranged) -> String {
    let range = node.range();
    let start = range.start().to_usize();
    let end = range.end().to_usize();
    source.get(start..end).unwrap_or_default().trim().to_owned()
}

fn expression_source(source: &str, expression: Option<&Expr>) -> String {
    expression.map_or_else(String::new, |expr| source_segment(source, expr))
}

fn call_name(expression: &Expr) -> String {
    match expression {
        Expr::Name(node) => node.id.to_string(),
        Expr::Attribute(node) => {
            let parent = call_name(&node.value);
            if parent.is_empty() {
                node.attr.to_string()
            } else {
                format!("{parent}.{}", node.attr)
            }
        }
        Expr::Call(node) => call_name(&node.func),
        _ => String::new(),
    }
}

fn target_names(target: &Expr) -> Vec<String> {
    match target {
        Expr::Name(node) => vec![node.id.to_string()],
        Expr::Tuple(node) => node.elts.iter().flat_map(target_names).collect(),
        Expr::List(node) => node.elts.iter().flat_map(target_names).collect(),
        _ => Vec::new(),
    }
}

fn literal_or_source(source: &str, expression: &Expr) -> Value {
    if let Expr::Constant(node) = expression {
        match &node.value {
            ast::Constant::Str(value) => return json!(value),
            ast::Constant::Bool(value) => return json!(value),
            ast::Constant::Int(value) => {
                if let Ok(number) = value.to_string().parse::<i64>() {
                    return json!(number);
                }
            }
            _ => {}
        }
    }
    json!(source_segment(source, expression))
}

fn call_keywords(source: &str, call: &ast::ExprCall) -> Value {
    let mut keywords = Map::new();
    for keyword in &call.keywords {
        if let Some(name) = keyword.arg.as_ref() {
            keywords.insert(name.to_string(), literal_or_source(source, &keyword.value));
        }
    }
    Value::Object(keywords)
}

fn main_pattern(source: &str, body: &[Stmt]) -> Option<Value> {
    let mut initialize = None;
    let mut algorithm_call = None;
    let mut returned = None;
    for statement in body {
        if let Stmt::Assign(assign) = statement {
            if assign.targets.len() == 1 {
                let assigned = target_names(&assign.targets[0]);
                if let Expr::Call(call) = assign.value.as_ref() {
                    let callee = call_name(&call.func);
                    if callee.ends_with(".initialize") {
                        initialize = Some(json!({
                            "assigned":assigned,
                            "callee":callee,
                            "args":call.args.iter().map(|arg| source_segment(source,arg)).collect::<Vec<_>>()
                        }));
                    }
                    if let Expr::Name(name) = call.func.as_ref() {
                        let mut solve_config = None;
                        for arg in &call.args {
                            match arg {
                                Expr::Name(value) if value.id.as_str() == "solve_config" => {
                                    solve_config = Some(
                                        json!({"source":"parameter","name":value.id.to_string()}),
                                    );
                                }
                                Expr::Call(config)
                                    if call_name(&config.func).ends_with(".SolveConfig") =>
                                {
                                    let mut descriptor = json!({"constructor":call_name(&config.func),"keywords":call_keywords(source,config)});
                                    if let Some(stopping) = config.keywords.iter().find(|keyword| {
                                        keyword
                                            .arg
                                            .as_ref()
                                            .is_some_and(|name| name.as_str() == "stopping")
                                    }) {
                                        if let Expr::Call(stopping_call) = &stopping.value {
                                            descriptor["stopping_constructor"] =
                                                json!(call_name(&stopping_call.func));
                                            descriptor["stopping_keywords"] =
                                                call_keywords(source, stopping_call);
                                        }
                                    }
                                    solve_config = Some(descriptor);
                                }
                                _ => {}
                            }
                        }
                        if let Some(solve_config) = solve_config {
                            algorithm_call = Some(json!({
                                "assigned":assigned,
                                "callee":name.id.to_string(),
                                "args":call.args.iter().map(|arg| source_segment(source,arg)).collect::<Vec<_>>(),
                                "solve_config":solve_config
                            }));
                        }
                    }
                }
            }
        }
        if let Stmt::Return(ret) = statement {
            returned = Some(
                ret.value
                    .as_ref()
                    .map_or_else(Vec::new, |value| target_names(value.as_ref())),
            );
        }
    }
    Some(json!({
        "pattern":"initialize_then_algorithm_call_return_tuple",
        "initialize":initialize?,"algorithm_call":algorithm_call?,"return":returned?
    }))
}

fn parse_source_signature(symbol: &str) -> Result<Option<SourceSignature>, String> {
    let (path_text, qualname) = symbol
        .split_once("::")
        .ok_or_else(|| format!("symbol must be path.py::qualname, got {symbol:?}"))?;
    let path = Path::new(path_text)
        .canonicalize()
        .map_err(|error| format!("symbol path does not exist: {error}"))?;
    let source = fs::read_to_string(&path)
        .map_err(|error| format!("cannot read Python source {}: {error}", path.display()))?;
    let suite = ast::Suite::parse(&source, &path.to_string_lossy())
        .map_err(|error| format!("Python AST parse failed for {}: {error}", path.display()))?;
    let parts = qualname.split('.').collect::<Vec<_>>();
    let Some(statement) = function_in_suite(&suite, &parts) else {
        return Ok(None);
    };
    let (name, args, returns, body): (&str, &ast::Arguments, Option<&Expr>, &[Stmt]) =
        match statement {
            Stmt::FunctionDef(node) => (
                node.name.as_str(),
                &node.args,
                node.returns.as_deref(),
                &node.body,
            ),
            Stmt::AsyncFunctionDef(node) => (
                node.name.as_str(),
                &node.args,
                node.returns.as_deref(),
                &node.body,
            ),
            _ => return Ok(None),
        };
    let parameters = args
        .args
        .iter()
        .enumerate()
        .map(|(index, argument)| {
            json!({
                "index":index,
                "name":argument.def.arg.to_string(),
                "annotation":expression_source(&source, argument.def.annotation.as_deref())
            })
        })
        .collect::<Vec<_>>();
    let return_annotation = expression_source(&source, returns);
    let text = source_segment(&source, statement);
    Ok(Some(SourceSignature {
        path,
        qualname: qualname.to_owned(),
        name: name.to_owned(),
        parameters,
        return_annotation,
        body_statement_count: body.len(),
        source_sha256: sha256(&text),
        main_pattern: main_pattern(&source, body),
    }))
}

fn source_root(signature: &SourceSignature, symbol: &str) -> Value {
    json!({
        "schema":"agent-canon.source-root.v1","python_symbol":symbol,"path":signature.path,
        "qualname":signature.qualname,"name":signature.name,"parameters":signature.parameters.iter().filter_map(|row|row.get("name").cloned()).collect::<Vec<_>>(),
        "return_annotation":signature.return_annotation,"source_sha256":signature.source_sha256,
        "body_statement_count":signature.body_statement_count,"main_pattern":signature.main_pattern
    })
}

fn return_roots(annotation: &str, output_leaf_roots: &[String]) -> Vec<Value> {
    let annotation = annotation.trim();
    let inner = annotation
        .strip_prefix("tuple[")
        .and_then(|value| value.strip_suffix(']'))
        .or_else(|| {
            annotation
                .strip_prefix("Tuple[")
                .and_then(|value| value.strip_suffix(']'))
        });
    let parts = inner.map(split_top_level_csv).unwrap_or_else(|| {
        if annotation.is_empty() {
            Vec::new()
        } else {
            vec![annotation.to_owned()]
        }
    });
    let labels = if parts.is_empty() {
        output_leaf_roots.to_vec()
    } else {
        parts
            .iter()
            .enumerate()
            .map(|(index, part)| {
                let name = part
                    .rsplit('.')
                    .next()
                    .unwrap_or(part)
                    .split('[')
                    .next()
                    .unwrap_or(part)
                    .trim();
                if name.is_empty() {
                    format!("return_{index}")
                } else {
                    let mut chars = name.chars();
                    chars.next().map_or_else(
                        || format!("return_{index}"),
                        |first| first.to_lowercase().to_string() + chars.as_str(),
                    )
                }
            })
            .collect()
    };
    labels.iter().enumerate().map(|(index, label)| json!({"index":index,"label":label,"annotation":parts.get(index).cloned().unwrap_or_default(),"path":format!("result[{index}]")})).collect()
}

fn split_top_level_csv(text: &str) -> Vec<String> {
    let mut items = Vec::new();
    let mut depth = 0usize;
    let mut start = 0usize;
    for (index, character) in text.char_indices() {
        match character {
            '[' | '(' | '{' => depth += 1,
            ']' | ')' | '}' => depth = depth.saturating_sub(1),
            ',' if depth == 0 => {
                let part = text[start..index].trim();
                if !part.is_empty() {
                    items.push(part.to_owned());
                }
                start = index + character.len_utf8();
            }
            _ => {}
        }
    }
    let tail = text[start..].trim();
    if !tail.is_empty() {
        items.push(tail.to_owned());
    }
    items
}

fn source_signature_value(signature: &SourceSignature, symbol: &str) -> Value {
    json!({"schema":"agent-canon.public-source-signature.v1","status":"ok","python_symbol":symbol,"path":signature.path,"qualname":signature.qualname,"name":signature.name,"parameters":signature.parameters,"return_annotation":signature.return_annotation})
}

fn stablehlo_entry_signature(signature: &str) -> Value {
    let argument_regex = Regex::new(r"%arg(?P<index>\d+):\s*(?P<type>tensor<[^>]+>)")
        .expect("valid StableHLO argument regex");
    let return_regex = Regex::new(
        r#"(?P<type>tensor<[^>]+>)\s*\{\s*jax\.result_info\s*=\s*"(?P<info>[^"]+)"\s*\}"#,
    )
    .expect("valid StableHLO return regex");
    let index_regex =
        Regex::new(r"\[(?P<index>\d+)\]").expect("valid StableHLO result index regex");
    let arguments=argument_regex.captures_iter(signature).map(|captures| json!({"index":captures.name("index").and_then(|v|v.as_str().parse::<usize>().ok()).unwrap_or_default(),"name":format!("arg{}",captures.name("index").map_or("0",|v|v.as_str())),"stablehlo_type":captures.name("type").map_or("",|v|v.as_str())})).collect::<Vec<_>>();
    let return_leaves=return_regex.captures_iter(signature).enumerate().map(|(leaf_index,captures)| {let info=captures.name("info").map_or("",|v|v.as_str());let indexes=index_regex.captures_iter(info).filter_map(|m|m.name("index")?.as_str().parse::<usize>().ok()).collect::<Vec<_>>();json!({"leaf_index":leaf_index,"result_info":info,"stablehlo_type":captures.name("type").map_or("",|v|v.as_str()),"result_indexes":indexes})}).collect::<Vec<_>>();
    json!({"signature":signature,"arguments":arguments,"return_leaves":return_leaves})
}

fn build_public_interface(
    args: &Args,
    runtime: &Value,
    operational_ir: &Value,
    source: Option<&SourceSignature>,
) -> Result<Value, String> {
    let symbol = args.python_symbol.as_deref().unwrap_or_default();
    let source_signature=source.map(|source|source_signature_value(source,symbol)).unwrap_or_else(|| {let (path,qualname)=symbol.split_once("::").unwrap_or(("",""));json!({"schema":"agent-canon.public-source-signature.v1","status":"function_not_found","python_symbol":symbol,"path":Path::new(path).canonicalize().unwrap_or_else(|_|PathBuf::from(path)),"qualname":qualname,"name":qualname.rsplit('.').next().unwrap_or(qualname),"parameters":[],"return_annotation":""})});
    let parameters = source_signature
        .get("parameters")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut argument_leaves = runtime
        .get("argument_leaves")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    for leaf in &mut argument_leaves {
        let index = leaf
            .get("root_index")
            .and_then(Value::as_u64)
            .unwrap_or_default() as usize;
        if let Some(name) = parameters
            .get(index)
            .and_then(|parameter| parameter.get("name"))
            .and_then(Value::as_str)
        {
            leaf["root_name"] = json!(name);
            let local = leaf
                .get("local_path")
                .and_then(Value::as_str)
                .unwrap_or_default();
            leaf["path"] = json!(format!("{name}{local}"));
        }
    }
    let mut problem_assumptions = runtime
        .get("problem_assumptions")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    for assumption in &mut problem_assumptions {
        let index = assumption
            .get("root_index")
            .and_then(Value::as_u64)
            .unwrap_or_default() as usize;
        if let Some(name) = parameters
            .get(index)
            .and_then(|parameter| parameter.get("name"))
            .and_then(Value::as_str)
        {
            assumption["root_name"] = json!(name);
            let local = assumption
                .get("local_path")
                .and_then(Value::as_str)
                .unwrap_or_default();
            assumption["path"] = json!(format!("{name}{local}"));
        }
    }
    let raw_return_leaves = runtime
        .get("return_leaves")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let root_names = raw_return_leaves
        .iter()
        .map(|leaf| {
            leaf.get("root_name")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_owned()
        })
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let roots = return_roots(
        source_signature
            .get("return_annotation")
            .and_then(Value::as_str)
            .unwrap_or_default(),
        &root_names,
    );
    let mut return_leaves = raw_return_leaves;
    for leaf in &mut return_leaves {
        let index = leaf
            .get("root_index")
            .and_then(Value::as_u64)
            .unwrap_or_default() as usize;
        if let Some(label) = roots
            .get(index)
            .and_then(|root| root.get("label"))
            .and_then(Value::as_str)
        {
            leaf["root_name"] = json!(label);
            let local = leaf
                .get("local_path")
                .and_then(Value::as_str)
                .unwrap_or_default();
            leaf["path"] = json!(format!("{label}{local}"));
        }
    }
    let function_name = source.map_or_else(
        || symbol.rsplit("::").next().unwrap_or(symbol).to_owned(),
        |source| source.name.clone(),
    );
    let signatures = operational_ir
        .get("function_signatures")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let candidates = signatures
        .iter()
        .filter_map(Value::as_str)
        .filter(|line| {
            line.contains(&format!("public @{function_name}"))
                || line.contains(&format!("@{function_name}("))
        })
        .collect::<Vec<_>>();
    let entry_signature = candidates
        .first()
        .copied()
        .or_else(|| signatures.first().and_then(Value::as_str))
        .unwrap_or_default();
    let entry = stablehlo_entry_signature(entry_signature);
    let argument_leaf_count = argument_leaves.len();
    let return_leaf_count = return_leaves.len();
    let return_root_count = roots.len();
    let stablehlo_argument_count = entry["arguments"].as_array().map_or(0, Vec::len);
    let stablehlo_return_count = entry["return_leaves"].as_array().map_or(0, Vec::len);
    let problem_assumption_count = problem_assumptions.len();
    let has_answer_state_info = roots
        .iter()
        .filter_map(|root| root.get("label").and_then(Value::as_str))
        .collect::<Vec<_>>()
        == ["answer", "state", "info"];
    Ok(json!({
        "schema":"agent-canon.public-interface.v1","python_symbol":symbol,"source_signature":source_signature,
        "argument_roots":parameters,"argument_leaves":argument_leaves,"return_annotation":source_signature.get("return_annotation").and_then(Value::as_str).unwrap_or_default(),
        "return_roots":roots,"return_leaves":return_leaves,"problem_assumptions":problem_assumptions,"stablehlo_entry":entry,
        "coverage":{"argument_root_count":parameters.len(),"argument_leaf_count":argument_leaf_count,"return_root_count":return_root_count,"return_leaf_count":return_leaf_count,"stablehlo_argument_count":stablehlo_argument_count,"stablehlo_return_leaf_count":stablehlo_return_count,"problem_assumption_count":problem_assumption_count,"has_answer_state_info_return":has_answer_state_info}
    }))
}

pub fn run(argv: &[String]) -> i32 {
    let args = match parse_args(argv) {
        Ok(ParseResult::Help) => {
            println!("{USAGE}\n\nBackend/runtime selection is read from environment variables: {JAX_PLATFORM_ENV}, {BACKEND_TARGET_ENV}, {INPUT_DEVICE_ENV}, {CUDA_VISIBLE_ENV}, {IREE_CUDA_TARGET_ENV}.");
            return 0;
        }
        Ok(ParseResult::Run(args)) => args,
        Err(error) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    match run_checked(&args) {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            1
        }
    }
}

fn run_checked(args: &Args) -> Result<(), String> {
    let config = runtime_config(!args.no_backend_trace)?;
    configure_jax(args, &config)?;
    let root = env::current_dir().map_err(|error| error.to_string())?;
    let runtime = provider_result(args, &config, &root)?;
    let stablehlo = runtime
        .get("stablehlo")
        .and_then(Value::as_str)
        .ok_or_else(|| "Python/JAX provider omitted StableHLO text".to_owned())?;
    let operational_ir = extract_operational_ir(stablehlo);
    crate::stablehlo_value_closure::parse_operational_ir(&json!({"operational_ir":operational_ir}))
        .map_err(|error| {
            format!("generated operational IR violates its shared reader contract: {error}")
        })?;
    let source_signature =
        parse_source_signature(args.python_symbol.as_deref().unwrap_or_default())?;
    let source_signature =
        source_signature.ok_or_else(|| "source function not found".to_owned())?;
    let root_record = json!({
        "python_symbol":args.python_symbol,"input_factory_symbol":args.input_factory,"repo_root":root,"jit_kind":"filter_jit"
    });
    let stablehlo_record = json!({"dialect":runtime.get("dialect").cloned().unwrap_or_else(|| json!("stablehlo")),"sha256":sha256_text(stablehlo),"text":stablehlo,"line_count":stablehlo.lines().count()});
    let source_root = if args.no_source_root {
        let (path, qualname) = args
            .python_symbol
            .as_deref()
            .unwrap_or_default()
            .split_once("::")
            .unwrap_or(("", ""));
        json!({"schema":"agent-canon.source-root.v1","status":"hlo_only","python_symbol":args.python_symbol,"path":Path::new(path).canonicalize().unwrap_or_else(|_| PathBuf::from(path)),"qualname":qualname,"name":qualname.rsplit('.').next().unwrap_or(qualname),"parameters":[],"return_annotation":"","source_sha256":"","body_statement_count":0,"main_pattern":Value::Null})
    } else {
        source_root(
            &source_signature,
            args.python_symbol.as_deref().unwrap_or_default(),
        )
    };
    let backend = if args.no_backend_trace {
        None
    } else {
        Some(backend_trace(args, &config, &runtime, stablehlo)?)
    };
    let mut record = Map::new();
    record.insert("schema".into(), json!("agent-canon.jit-canonical-ir.v1"));
    record.insert("root".into(), root_record);
    record.insert("stablehlo".into(), stablehlo_record);
    record.insert(
        "public_interface".into(),
        build_public_interface(args, &runtime, &operational_ir, Some(&source_signature))?,
    );
    record.insert("operational_ir".into(), operational_ir);
    record.insert("source_root".into(), source_root);
    if let Some(backend) = backend {
        record.insert(
            "backend_environment".into(),
            backend
                .get("environment")
                .cloned()
                .unwrap_or_else(|| json!({})),
        );
        record.insert(
            "backend_trace".into(),
            backend.get("trace").cloned().unwrap_or_else(|| json!({})),
        );
    }
    let record = Value::Object(record);
    write_json_file(args.out.as_deref().expect("required parser field"), &record)?;
    if let Some(path) = args.stablehlo_out.as_deref() {
        write_text_file(path, stablehlo)?;
    }
    if let Some(path) = args.backend_trace_out.as_deref() {
        if let Some(backend) = record.get("backend_trace") {
            write_json_file(path, backend)?;
        }
    }
    Ok(())
}

fn write_text_file(path: &Path, text: &str) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create {}: {error}", parent.display()))?;
    }
    fs::write(path, text).map_err(|error| format!("cannot write {}: {error}", path.display()))
}

fn write_json_file(path: &Path, value: &Value) -> Result<(), String> {
    let text = serde_json::to_string_pretty(value).map_err(|error| error.to_string())? + "\n";
    write_text_file(path, &text)
}

const BACKEND_ARTIFACT_GROUPS: &[&str] = &[
    "executable_sources",
    "llvm_ir",
    "llvm_bitcode",
    "object_files",
    "assembly",
    "other",
];
const IREE_PHASES: &[&str] = &[
    "input",
    "abi",
    "preprocessing",
    "global-optimization",
    "dispatch-creation",
    "flow",
    "stream",
    "executable-sources",
    "executable-configurations",
    "executable-targets",
    "hal",
    "vm",
];
const LLVM_FAST_MATH_FLAGS: &[&str] = &[
    "nnan", "ninf", "nsz", "arcp", "contract", "afn", "reassoc", "fast",
];
const LLVM_FLOAT_OPCODES: &[&str] = &["fadd", "fsub", "fmul", "fdiv", "frem", "fcmp"];

fn find_executable(name: &str) -> Option<PathBuf> {
    env::split_paths(&env::var_os("PATH")?)
        .map(|directory| directory.join(name))
        .find(|path| path.is_file())
}

fn find_llvm_dis() -> Option<PathBuf> {
    [
        "llvm-dis",
        "llvm-dis-23",
        "llvm-dis-22",
        "llvm-dis-21",
        "llvm-dis-20",
        "llvm-dis-19",
        "llvm-dis-18",
        "llvm-dis-17",
        "llvm-dis-16",
        "llvm-dis-15",
        "llvm-dis-14",
    ]
    .iter()
    .find_map(|name| find_executable(name))
}

fn command_output(command: &mut Command) -> Result<(i32, String, String), String> {
    let output = command.output().map_err(|error| {
        format!(
            "cannot execute {}: {error}",
            command.get_program().to_string_lossy()
        )
    })?;
    Ok((
        output.status.code().unwrap_or(1),
        String::from_utf8_lossy(&output.stdout)
            .replace("\r\n", "\n")
            .replace('\r', "\n"),
        String::from_utf8_lossy(&output.stderr)
            .replace("\r\n", "\n")
            .replace('\r', "\n"),
    ))
}

fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

struct TemporaryDirectory(PathBuf);
impl Drop for TemporaryDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn copy_bytes(
    source: &Path,
    output_dir: &Path,
    relative_prefix: &str,
    kind: &str,
) -> Result<Value, String> {
    let bytes = fs::read(source)
        .map_err(|error| format!("cannot read backend artifact {}: {error}", source.display()))?;
    let destination = output_dir
        .join(relative_prefix)
        .join(source.file_name().unwrap_or_default());
    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create {}: {error}", parent.display()))?;
    }
    fs::write(&destination, &bytes)
        .map_err(|error| format!("cannot write {}: {error}", destination.display()))?;
    Ok(
        json!({"path":destination,"sha256":sha256_bytes(&bytes),"kind":kind,"size_bytes":bytes.len()}),
    )
}

fn parse_llvm_functions(text: &str) -> Vec<Value> {
    let define = Regex::new(r"^define\s+(?P<attrs>.*?)\s*@(?P<name>[^(\s]+)\((?P<params>[^)]*)\)")
        .expect("valid LLVM function regex");
    let label = Regex::new(r"^([-A-Za-z0-9_.$]+):(?:\s*;.*)?$").expect("valid LLVM label regex");
    let result = Regex::new(r"^(%[-A-Za-z0-9_.$]+)\s*=\s*(.*)$").expect("valid LLVM result regex");
    let opcode = Regex::new(r"\b(?P<opcode>fadd|fsub|fmul|fdiv|frem|fcmp|select|call|br|phi|load|store|getelementptr|ret)\b(?P<tail>[^;]*)").expect("valid LLVM opcode regex");
    let mut functions = Vec::<Map<String, Value>>::new();
    let mut current: Option<usize> = None;
    let mut current_block = "entry".to_owned();
    for (index, line) in text.lines().enumerate() {
        let line_no = index + 1;
        let stripped = line.trim();
        if let Some(captures) = define.captures(line) {
            let name = captures.name("name").map_or("", |value| value.as_str());
            functions.push(Map::from_iter([
                ("name".into(), json!(name)),
                ("signature".into(), json!(stripped)),
                (
                    "return_and_attrs".into(),
                    json!(captures
                        .name("attrs")
                        .map_or("", |value| value.as_str())
                        .trim()),
                ),
                (
                    "params".into(),
                    json!(captures
                        .name("params")
                        .map_or("", |value| value.as_str())
                        .trim()),
                ),
                ("op_counts".into(), json!({})),
                ("fast_math_flags".into(), json!({})),
                (
                    "basic_blocks".into(),
                    json!([{"label":"entry","line":line_no,"instruction_ids":[]}]),
                ),
                ("instructions".into(), json!([])),
            ]));
            current = Some(functions.len() - 1);
            current_block = "entry".into();
            continue;
        }
        let Some(function_index) = current else {
            continue;
        };
        if stripped.starts_with('}') {
            current = None;
            continue;
        }
        if let Some(captures) = label.captures(stripped) {
            current_block = captures
                .get(1)
                .map_or("", |value| value.as_str())
                .to_owned();
            if let Some(blocks) = functions[function_index]
                .get_mut("basic_blocks")
                .and_then(Value::as_array_mut)
            {
                blocks.push(json!({"label":current_block,"line":line_no,"instruction_ids":[]}));
            }
            continue;
        }
        let (result_name, body) =
            result
                .captures(stripped)
                .map_or((String::new(), stripped.to_owned()), |captures| {
                    (
                        captures
                            .get(1)
                            .map_or("", |value| value.as_str())
                            .to_owned(),
                        captures
                            .get(2)
                            .map_or("", |value| value.as_str())
                            .to_owned(),
                    )
                });
        let Some(captures) = opcode.captures(&body) else {
            continue;
        };
        let opcode_name = captures.name("opcode").map_or("", |value| value.as_str());
        let tail = captures
            .name("tail")
            .map_or("", |value| value.as_str())
            .trim();
        let counts = functions[function_index]
            .get_mut("op_counts")
            .and_then(Value::as_object_mut)
            .expect("op counts map");
        let count = counts
            .get(opcode_name)
            .and_then(Value::as_u64)
            .unwrap_or_default()
            + 1;
        counts.insert(opcode_name.into(), json!(count));
        let mut flags = Vec::new();
        for flag in LLVM_FAST_MATH_FLAGS {
            if Regex::new(&format!(r"\b{}\b", regex::escape(flag)))
                .expect("valid fast math regex")
                .is_match(tail)
            {
                let counts = functions[function_index]
                    .get_mut("fast_math_flags")
                    .and_then(Value::as_object_mut)
                    .expect("fast math map");
                let count = counts
                    .get(*flag)
                    .and_then(Value::as_u64)
                    .unwrap_or_default()
                    + 1;
                counts.insert((*flag).into(), json!(count));
                flags.push(*flag);
            }
        }
        let function_name = functions[function_index]
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        let instructions = functions[function_index]
            .get_mut("instructions")
            .and_then(Value::as_array_mut)
            .expect("instructions array");
        let instruction_id = format!("{function_name}:inst_{:05}", instructions.len());
        instructions.push(json!({"instruction_id":instruction_id,"function":function_name,"basic_block":current_block,"line":line_no,"result_name":result_name,"opcode":opcode_name,"operand_text":tail,"text":stripped,"text_sha256":sha256(stripped),"fast_math_flags":flags,"is_float_op":LLVM_FLOAT_OPCODES.contains(&opcode_name)}));
        if let Some(block) = functions[function_index]
            .get_mut("basic_blocks")
            .and_then(Value::as_array_mut)
            .and_then(|blocks| blocks.last_mut())
            .and_then(Value::as_object_mut)
            .and_then(|block| block.get_mut("instruction_ids"))
            .and_then(Value::as_array_mut)
        {
            block.push(json!(instruction_id));
        }
    }
    functions
        .into_iter()
        .map(|mut function| {
            for field in ["op_counts", "fast_math_flags"] {
                if let Some(object) = function.get_mut(field).and_then(Value::as_object_mut) {
                    let sorted = object
                        .iter()
                        .map(|(key, value)| (key.clone(), value.clone()))
                        .collect::<BTreeMap<_, _>>();
                    *object = Map::from_iter(sorted);
                }
            }
            let instructions = function
                .get("instructions")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            let float_count = instructions
                .iter()
                .filter(|row| row.get("is_float_op").and_then(Value::as_bool) == Some(true))
                .count();
            function.insert("instruction_count".into(), json!(instructions.len()));
            function.insert("float_instruction_count".into(), json!(float_count));
            Value::Object(function)
        })
        .collect()
}

fn backend_environment(
    config: &RuntimeConfig,
    runtime: &Value,
    dialect: &str,
    compiler_errors: &[String],
) -> Value {
    let mut executables = Map::new();
    for (name, path) in [
        ("iree-compile", find_executable("iree-compile")),
        ("iree-run-module", find_executable("iree-run-module")),
        ("llvm-dis", find_llvm_dis()),
    ] {
        executables.insert(name.into(), path.map_or(Value::Null, |path| json!(path)));
    }
    let env_names = [
        JAX_PLATFORM_ENV,
        BACKEND_TARGET_ENV,
        INPUT_DEVICE_ENV,
        CUDA_VISIBLE_ENV,
        IREE_CUDA_TARGET_ENV,
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "JAX_PLATFORMS",
        "JAX_PLATFORM_NAME",
    ];
    let runtime_selection_env = env_names
        .iter()
        .filter_map(|name| {
            env::var(name)
                .ok()
                .map(|value| ((*name).to_owned(), json!(value)))
        })
        .collect::<Map<_, _>>();
    let packages = runtime.get("packages").cloned().unwrap_or_else(
        || json!({"jax":runtime.get("jax_version").cloned().unwrap_or(Value::Null)}),
    );
    let python = runtime
        .get("python_version")
        .cloned()
        .unwrap_or(Value::Null);
    let platform = runtime
        .get("platform")
        .cloned()
        .unwrap_or_else(|| json!(env::consts::OS));
    let _configured_cuda_devices = config.cuda_visible_devices.as_deref();
    json!({"schema":"agent-canon.backend-environment.v1","dialect":dialect,"python":python,"platform":platform,"packages":packages,"jax_default_backend":runtime.get("jax_default_backend").cloned().unwrap_or(Value::Null),"jax_devices":runtime.get("jax_devices").cloned().unwrap_or_else(||json!([])),"runtime_selection_env":runtime_selection_env,"executables":executables,"compiler_ir_errors":compiler_errors,"float_semantics_policy":"Backend FP semantics are generated from backend trace coverage, not accepted as an external axiom."})
}

fn backend_trace(
    args: &Args,
    config: &RuntimeConfig,
    runtime: &Value,
    stablehlo: &str,
) -> Result<Value, String> {
    let compiler = find_executable("iree-compile");
    let run_module = find_executable("iree-run-module");
    let llvm_dis = find_llvm_dis();
    let executables =
        json!({"iree-compile":compiler,"iree-run-module":run_module,"llvm-dis":llvm_dis});
    let mut trace = json!({"schema":"agent-canon.typed-backend-trace.v1","target_backend":config.backend_target,"target_options":{"iree_cuda_target":config.iree_cuda_target},"executables":executables,"compiler_ir_errors":runtime.get("compiler_ir_errors").cloned().unwrap_or_else(||json!([])),"compile_command":[],"coverage":"not_generated","phase_traces":[],"compile_attempts":[],"xla_compile":runtime.get("xla_compile").cloned().unwrap_or_else(||json!({})),"executable_sources":[],"llvm_ir":[],"llvm_bitcode":[],"object_files":[],"assembly":[]});
    let environment = backend_environment(
        config,
        runtime,
        runtime
            .get("dialect")
            .and_then(Value::as_str)
            .unwrap_or("stablehlo"),
        runtime
            .get("compiler_ir_errors")
            .and_then(Value::as_array)
            .map(|rows| {
                rows.iter()
                    .filter_map(Value::as_str)
                    .map(str::to_owned)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default()
            .as_slice(),
    );
    if compiler.is_none() {
        trace["coverage"] = json!("compiler_unavailable");
        return Ok(json!({"environment":environment,"trace":trace}));
    }
    let Some(output_dir) = args.backend_trace_dir.as_ref() else {
        trace["coverage"] = json!("output_dir_not_requested");
        return Ok(json!({"environment":environment,"trace":trace}));
    };
    if output_dir.exists() {
        fs::remove_dir_all(output_dir).map_err(|error| {
            format!(
                "cannot replace backend trace directory {}: {error}",
                output_dir.display()
            )
        })?;
    }
    fs::create_dir_all(output_dir).map_err(|error| {
        format!(
            "cannot create backend trace directory {}: {error}",
            output_dir.display()
        )
    })?;
    let temp_root = env::temp_dir().join(format!(
        "agent-canon-iree-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    ));
    fs::create_dir_all(&temp_root).map_err(|error| {
        format!(
            "cannot create temporary IREE directory {}: {error}",
            temp_root.display()
        )
    })?;
    let _temp_cleanup = TemporaryDirectory(temp_root.clone());
    let input = temp_root.join("input_stablehlo.mlir");
    fs::write(&input, stablehlo)
        .map_err(|error| format!("cannot write {}: {error}", input.display()))?;
    let compiler = compiler.expect("checked compiler");
    let target = config.backend_target.as_deref().unwrap_or_default();
    let mut phase_records = Vec::new();
    let mut last_phase = "none".to_owned();
    for phase in IREE_PHASES {
        let phase_output = temp_root.join(format!("{phase}.mlir"));
        let mut command = Command::new(&compiler);
        command
            .arg(&input)
            .args(iree_target_args(
                target,
                "stablehlo",
                config.iree_cuda_target.as_deref(),
            ))
            .arg(format!("--compile-to={phase}"))
            .args(["--output-format=vm-asm", "-o"])
            .arg(&phase_output);
        let (returncode, stdout, stderr) = command_output(&mut command)?;
        let argv = command_argv(
            &compiler,
            &input,
            target,
            "stablehlo",
            config.iree_cuda_target.as_deref(),
            Some(phase),
            &phase_output,
        );
        let mut row = json!({"phase":phase,"compile_command":argv,"returncode":returncode,"stdout":stdout,"stderr":stderr});
        if returncode == 0 && phase_output.exists() {
            let copied = copy_backend_text(&phase_output, output_dir, "backend_phases")?;
            row["artifact"] = copied;
            last_phase = (*phase).to_owned();
        }
        phase_records.push(row);
        if returncode != 0 {
            break;
        }
    }
    trace["phase_traces"] = json!(phase_records);
    trace["last_successful_phase"] = json!(last_phase);
    let mut artifacts = empty_backend_artifacts();
    let mut attempts = Vec::new();
    for (name, dump, out, executable_targets) in [
        (
            "full_dump_embedded",
            temp_root.join("full_dump_embedded"),
            temp_root.join("full_embedded.vmfb"),
            false,
        ),
        (
            "compile_to_executable_targets",
            temp_root.join("executable_targets_dump"),
            temp_root.join("executable_targets.mlir"),
            true,
        ),
    ] {
        fs::create_dir_all(&dump)
            .map_err(|error| format!("cannot create {}: {error}", dump.display()))?;
        let mut command = Command::new(&compiler);
        command.arg(&input).args(iree_target_args(
            target,
            "stablehlo",
            config.iree_cuda_target.as_deref(),
        ));
        if executable_targets {
            command.args(["--compile-to=executable-targets", "--output-format=vm-asm"]);
        }
        command
            .arg(format!(
                "--iree-hal-dump-executable-files-to={}",
                dump.display()
            ))
            .args(["-o"])
            .arg(&out);
        let (returncode, stdout, stderr) = command_output(&mut command)?;
        let mut argv = vec![compiler.display().to_string(), input.display().to_string()];
        argv.extend(iree_target_args(
            target,
            "stablehlo",
            config.iree_cuda_target.as_deref(),
        ));
        if executable_targets {
            argv.extend([
                "--compile-to=executable-targets".into(),
                "--output-format=vm-asm".into(),
            ]);
        }
        argv.push(format!(
            "--iree-hal-dump-executable-files-to={}",
            dump.display()
        ));
        argv.extend(["-o".into(), out.display().to_string()]);
        let collected =
            collect_dump_artifacts(&dump, output_dir, &format!("compile_attempts/{name}"))?;
        merge_artifacts(&mut artifacts, &collected);
        let mut counts = Map::new();
        for key in BACKEND_ARTIFACT_GROUPS {
            counts.insert(
                (*key).into(),
                json!(collected
                    .get(*key)
                    .and_then(Value::as_array)
                    .map_or(0, Vec::len)),
            );
        }
        let mut attempt = json!({"name":name,"compile_command":argv,"returncode":returncode,"stdout":stdout,"stderr":stderr,"artifact_counts":counts});
        if returncode != 0 {
            attempt["diagnostic_summary"] = summarize_mlir_failure(
                attempt
                    .get("stderr")
                    .and_then(Value::as_str)
                    .unwrap_or_default(),
            );
        }
        if out.exists() {
            let output_record = copy_backend_binary(
                &out,
                output_dir,
                &format!("compile_attempts/{name}"),
                "vmfb",
            )?;
            attempt["output"] = output_record;
        }
        attempts.push(attempt);
        if artifacts
            .get("llvm_ir")
            .and_then(Value::as_array)
            .is_some_and(|rows| !rows.is_empty())
        {
            break;
        }
    }
    if let Some(dump) = args.xla_dump_dir.as_deref() {
        let xla = collect_xla_dump(dump, output_dir)?;
        merge_artifacts(&mut artifacts, &xla);
        let mut xla_compile = runtime
            .get("xla_compile")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        xla_compile.insert("dump_source".into(), json!("xla_dump_dir"));
        xla_compile.insert("artifact_counts".into(), artifact_counts(&xla));
        trace["xla_compile"] = Value::Object(xla_compile);
    }
    trace["compile_attempts"] = json!(attempts);
    if let Some(attempt) = trace["compile_attempts"]
        .as_array()
        .and_then(|rows| rows.first())
        .cloned()
    {
        trace["compile_command"] = attempt
            .get("compile_command")
            .cloned()
            .unwrap_or_else(|| json!([]));
        trace["returncode"] = attempt.get("returncode").cloned().unwrap_or(Value::Null);
        trace["stdout"] = attempt.get("stdout").cloned().unwrap_or_else(|| json!(""));
        trace["stderr"] = attempt.get("stderr").cloned().unwrap_or_else(|| json!(""));
        if let Some(output) = attempt.get("output") {
            trace["vmfb"] = output.clone();
        }
    }
    for key in BACKEND_ARTIFACT_GROUPS {
        trace[*key] = artifacts.get(*key).cloned().unwrap_or_else(|| json!([]));
    }
    let llvm = trace["llvm_ir"]
        .as_array()
        .is_some_and(|rows| !rows.is_empty());
    let success = trace["compile_attempts"].as_array().is_some_and(|rows| {
        rows.iter()
            .any(|row| row.get("returncode").and_then(Value::as_i64) == Some(0))
    });
    trace["coverage"] = json!(if llvm {
        "generated_with_llvm".to_owned()
    } else if success {
        "generated_without_llvm_text".to_owned()
    } else {
        format!("phase_trace_until_{last_phase}_llvm_compile_failed")
    });
    Ok(json!({"environment":environment,"trace":trace}))
}

fn iree_target_args(target: &str, input_type: &str, cuda_target: Option<&str>) -> Vec<String> {
    let mut args = vec![
        format!("--iree-input-type={input_type}"),
        format!("--iree-hal-target-backends={target}"),
        "--mlir-disable-threading".into(),
    ];
    if let Some(target) = cuda_target {
        args.push(format!("--iree-cuda-target={target}"));
    }
    args
}

fn command_argv(
    compiler: &Path,
    input: &Path,
    target: &str,
    input_type: &str,
    cuda_target: Option<&str>,
    phase: Option<&str>,
    output: &Path,
) -> Vec<String> {
    let mut argv = vec![compiler.display().to_string(), input.display().to_string()];
    argv.extend(iree_target_args(target, input_type, cuda_target));
    if let Some(phase) = phase {
        argv.push(format!("--compile-to={phase}"));
        argv.extend(["--output-format=vm-asm".into()]);
    }
    argv.extend(["-o".into(), output.display().to_string()]);
    argv
}

fn empty_backend_artifacts() -> Map<String, Value> {
    Map::from_iter(
        BACKEND_ARTIFACT_GROUPS
            .iter()
            .map(|key| ((*key).to_owned(), json!([]))),
    )
}

fn copy_backend_text(source: &Path, output: &Path, prefix: &str) -> Result<Value, String> {
    let bytes =
        fs::read(source).map_err(|error| format!("cannot read {}: {error}", source.display()))?;
    let text = String::from_utf8_lossy(&bytes).into_owned();
    let dest = output
        .join(prefix)
        .join(source.file_name().unwrap_or_default());
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create {}: {error}", parent.display()))?;
    }
    fs::write(&dest, &text).map_err(|error| format!("cannot write {}: {error}", dest.display()))?;
    if source.extension().and_then(|value| value.to_str()) == Some("ll") {
        let functions = parse_llvm_functions(&text);
        let mut op_counts = BTreeMap::<String, usize>::new();
        let mut fast_math_flags = BTreeMap::<String, usize>::new();
        let mut instruction_count = 0usize;
        let mut float_instruction_count = 0usize;
        let mut basic_block_count = 0usize;
        for function in &functions {
            for (name, count) in function
                .get("op_counts")
                .and_then(Value::as_object)
                .into_iter()
                .flatten()
            {
                *op_counts.entry(name.clone()).or_default() +=
                    count.as_u64().unwrap_or_default() as usize;
            }
            for (name, count) in function
                .get("fast_math_flags")
                .and_then(Value::as_object)
                .into_iter()
                .flatten()
            {
                *fast_math_flags.entry(name.clone()).or_default() +=
                    count.as_u64().unwrap_or_default() as usize;
            }
            instruction_count += function
                .get("instruction_count")
                .and_then(Value::as_u64)
                .unwrap_or_default() as usize;
            float_instruction_count += function
                .get("float_instruction_count")
                .and_then(Value::as_u64)
                .unwrap_or_default() as usize;
            basic_block_count += function
                .get("basic_blocks")
                .and_then(Value::as_array)
                .map_or(0, Vec::len);
        }
        return Ok(
            json!({"path":dest,"sha256":sha256(&text),"kind":"llvm_ir","functions":functions,"op_counts":op_counts,"fast_math_flags":fast_math_flags,"basic_block_count":basic_block_count,"instruction_count":instruction_count,"float_instruction_count":float_instruction_count}),
        );
    }
    Ok(
        json!({"path":dest,"sha256":sha256(&text),"kind":"mlir_text","op_counts":mlir_op_counts(&text)}),
    )
}

fn copy_backend_binary(
    source: &Path,
    output: &Path,
    prefix: &str,
    kind: &str,
) -> Result<Value, String> {
    let bytes =
        fs::read(source).map_err(|error| format!("cannot read {}: {error}", source.display()))?;
    let dest = output
        .join(prefix)
        .join(source.file_name().unwrap_or_default());
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create {}: {error}", parent.display()))?;
    }
    fs::write(&dest, &bytes)
        .map_err(|error| format!("cannot write {}: {error}", dest.display()))?;
    if kind == "vmfb" {
        Ok(json!({"path":dest,"sha256":sha256_bytes(&bytes),"size_bytes":bytes.len()}))
    } else {
        Ok(json!({"path":dest,"sha256":sha256_bytes(&bytes),"kind":kind,"size_bytes":bytes.len()}))
    }
}

fn mlir_op_counts(text: &str) -> Value {
    let regex =
        Regex::new(r"\b(?:stablehlo|mhlo|chlo|func|scf|arith)\.[A-Za-z0-9_]+|\breturn\b|\bcall\b")
            .expect("valid MLIR opcode regex");
    let mut counts = BTreeMap::<String, usize>::new();
    for op in regex.find_iter(text) {
        *counts.entry(op.as_str().to_owned()).or_default() += 1;
    }
    json!(counts)
}

fn summarize_mlir_failure(stderr: &str) -> Value {
    let first_error = stderr
        .lines()
        .find(|line| line.contains(" error: ") || line.starts_with("error: "))
        .map(str::trim);
    let pass_regex = Regex::new(r"Pipeline failed while executing `(?P<pass_name>[^`]+)`")
        .expect("valid IREE failure pass regex");
    let failed_pass = pass_regex
        .captures(stderr)
        .and_then(|captures| captures.name("pass_name"))
        .map(|value| value.as_str());
    json!({"first_error":first_error,"failed_pass":failed_pass})
}

fn walk_files(root: &Path) -> Result<Vec<PathBuf>, String> {
    let mut pending = vec![root.to_path_buf()];
    let mut files = Vec::new();
    while let Some(directory) = pending.pop() {
        if !directory.exists() {
            continue;
        }
        let mut entries = fs::read_dir(&directory)
            .map_err(|error| format!("cannot read {}: {error}", directory.display()))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string())?;
        entries.sort_by_key(|entry| entry.path());
        for entry in entries {
            let path = entry.path();
            if path.is_dir() {
                pending.push(path);
            } else if path.is_file() {
                files.push(path);
            }
        }
    }
    files.sort();
    Ok(files)
}

fn collect_dump_artifacts(
    dump: &Path,
    output: &Path,
    prefix: &str,
) -> Result<Map<String, Value>, String> {
    let mut artifacts = empty_backend_artifacts();
    for path in walk_files(dump)? {
        let suffix = path
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();
        let group = match suffix.as_str() {
            "ll" => "llvm_ir",
            "bc" => "llvm_bitcode",
            "mlir" => "executable_sources",
            "s" | "ptx" => "assembly",
            "o" => "object_files",
            _ => "other",
        };
        let kind = match suffix.as_str() {
            "bc" => "llvm_bitcode",
            "o" => "object_file",
            "s" => "assembly",
            "ptx" => "ptx",
            "mlir" => "mlir_text",
            _ => "backend_artifact",
        };
        let relative_parent = path
            .parent()
            .and_then(|parent| parent.strip_prefix(dump).ok())
            .map(|parent| parent.to_string_lossy().replace('\\', "/"))
            .unwrap_or_default();
        let relative_prefix = if relative_parent.is_empty() || relative_parent == "." {
            prefix.to_owned()
        } else {
            format!("{prefix}/{relative_parent}")
        };
        let mut record = if ["mlir", "ll", "s", "ptx"].contains(&suffix.as_str()) {
            copy_backend_text(&path, output, &relative_prefix)?
        } else {
            copy_bytes(&path, output, &relative_prefix, kind)?
        };
        if suffix == "s" || suffix == "ptx" {
            record["kind"] = json!(kind);
        }
        if let Some(rows) = artifacts.get_mut(group).and_then(Value::as_array_mut) {
            rows.push(record);
        }
        if suffix == "bc" {
            if let Some(disassembled) = disassemble_llvm_bitcode(&path, output, &relative_prefix)? {
                if let Some(rows) = artifacts.get_mut("llvm_ir").and_then(Value::as_array_mut) {
                    rows.push(disassembled);
                }
            }
        }
    }
    Ok(artifacts)
}

fn artifact_counts(artifacts: &Map<String, Value>) -> Value {
    let mut counts = Map::new();
    for key in BACKEND_ARTIFACT_GROUPS {
        counts.insert(
            (*key).into(),
            json!(artifacts
                .get(*key)
                .and_then(Value::as_array)
                .map_or(0, Vec::len)),
        );
    }
    Value::Object(counts)
}

fn merge_artifacts(target: &mut Map<String, Value>, source: &Map<String, Value>) {
    for key in BACKEND_ARTIFACT_GROUPS {
        let mut rows = target
            .get(*key)
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        let mut seen = rows
            .iter()
            .filter_map(|row| row.get("sha256").and_then(Value::as_str))
            .map(str::to_owned)
            .collect::<BTreeSet<_>>();
        for row in source
            .get(*key)
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            if let Some(hash) = row.get("sha256").and_then(Value::as_str) {
                if !seen.insert(hash.to_owned()) {
                    continue;
                }
            }
            rows.push(row.clone());
        }
        target.insert((*key).into(), json!(rows));
    }
}

fn collect_xla_dump(dump: &Path, output: &Path) -> Result<Map<String, Value>, String> {
    let mut artifacts = empty_backend_artifacts();
    for path in walk_files(dump)? {
        let name = path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or_default();
        if name.starts_with("LLVMDialectModule.pass-") {
            continue;
        }
        let suffix = path
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();
        if suffix == "ll" && !name.contains(".ir-") {
            continue;
        }
        if !["ll", "bc", "ptx", "s"].contains(&suffix.as_str()) {
            continue;
        }
        let group = if suffix == "ll" {
            "llvm_ir"
        } else if suffix == "bc" {
            "llvm_bitcode"
        } else {
            "assembly"
        };
        let relative_parent = path
            .parent()
            .and_then(|parent| parent.strip_prefix(dump).ok())
            .map(|parent| parent.to_string_lossy().replace('\\', "/"))
            .unwrap_or_default();
        let relative_prefix = if relative_parent.is_empty() || relative_parent == "." {
            "xla_dump".to_owned()
        } else {
            format!("xla_dump/{relative_parent}")
        };
        let mut record = if suffix == "bc" {
            copy_bytes(&path, output, &relative_prefix, "llvm_bitcode")?
        } else {
            copy_backend_text(&path, output, &relative_prefix)?
        };
        if suffix == "s" || suffix == "ptx" {
            record["kind"] = json!(if suffix == "s" { "assembly" } else { "ptx" });
        }
        if let Some(rows) = artifacts.get_mut(group).and_then(Value::as_array_mut) {
            rows.push(record);
        }
        if suffix == "bc" {
            if let Some(disassembled) = disassemble_llvm_bitcode(&path, output, &relative_prefix)? {
                if let Some(rows) = artifacts.get_mut("llvm_ir").and_then(Value::as_array_mut) {
                    rows.push(disassembled);
                }
            }
        }
    }
    Ok(artifacts)
}

fn disassemble_llvm_bitcode(
    source: &Path,
    output: &Path,
    prefix: &str,
) -> Result<Option<Value>, String> {
    let Some(llvm_dis) = find_llvm_dis() else {
        return Ok(None);
    };
    let temporary = env::temp_dir().join(format!(
        "agent-canon-llvm-dis-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    ));
    fs::create_dir_all(&temporary).map_err(|error| {
        format!(
            "cannot create temporary LLVM directory {}: {error}",
            temporary.display()
        )
    })?;
    let _temp_cleanup = TemporaryDirectory(temporary.clone());
    let text_path = temporary.join(format!(
        "{}.ll",
        source.file_stem().unwrap_or_default().to_string_lossy()
    ));
    let mut command = Command::new(llvm_dis);
    command.arg(source).arg("-o").arg(&text_path);
    let (status, _, _) = command_output(&mut command)?;
    if status == 0 && text_path.exists() {
        let mut record = copy_backend_text(&text_path, output, prefix)?;
        record["source_bitcode"] = json!(source);
        Ok(Some(record))
    } else {
        Ok(None)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stablehlo_extraction_preserves_operations_regions_and_coverage() {
        let text = "func.func public @main(%arg0: tensor<2xf32>) -> tensor<2xf32> {\n  %0 = stablehlo.add %arg0, %arg0 : tensor<2xf32>\n  return %0 : tensor<2xf32>\n}\n";
        let record = extract_operational_ir(text);
        assert_eq!(record["schema"], "agent-canon.thin-operational-ir.v2");
        assert_eq!(record["functions"][0]["name"], "main");
        assert_eq!(record["ops"][0]["kind"], "Function");
        assert_eq!(record["ops"][1]["tensor_types"][0], "2xf32");
        assert_eq!(record["ops"][2]["kind"], "Return");
        assert_eq!(record["coverage"]["unassigned_op_count"], 0);
        crate::stablehlo_value_closure::parse_operational_ir(&json!({"operational_ir":record}))
            .unwrap();
    }

    #[test]
    fn source_signature_extracts_parameter_return_and_main_pattern_without_importing() {
        let directory = tempfile::tempdir().unwrap();
        let source = directory.path().join("root.py");
        fs::write(
            &source,
            "def main(problem, solve_config):\n    initialized = problem.initialize()\n    result = solve(problem, solve_config)\n    return answer, state, info\n",
        )
        .unwrap();
        let signature = parse_source_signature(&format!("{}::main", source.display()))
            .unwrap()
            .unwrap();
        assert_eq!(signature.name, "main");
        assert_eq!(signature.parameters[0]["name"], "problem");
        assert_eq!(signature.parameters[1]["name"], "solve_config");
        assert_eq!(signature.body_statement_count, 3);
        assert_eq!(
            signature.main_pattern.as_ref().unwrap()["pattern"],
            "initialize_then_algorithm_call_return_tuple"
        );
        assert_eq!(
            signature.main_pattern.unwrap()["return"],
            json!(["answer", "state", "info"])
        );
    }

    #[test]
    fn llvm_fixture_preserves_function_blocks_opcodes_and_fast_math_flags() {
        let text = "define float @main_dispatch(float %x) {\nentry:\n  %1 = fadd contract float %x, 1.0\n  ret float %1\n}\n";
        let functions = parse_llvm_functions(text);
        assert_eq!(functions.len(), 1);
        assert_eq!(functions[0]["name"], "main_dispatch");
        assert_eq!(functions[0]["op_counts"]["fadd"], 1);
        assert_eq!(functions[0]["fast_math_flags"]["contract"], 1);
        assert_eq!(
            functions[0]["basic_blocks"][1]["instruction_ids"][0],
            "main_dispatch:inst_00000"
        );
        assert_eq!(functions[0]["float_instruction_count"], 1);
    }
}
