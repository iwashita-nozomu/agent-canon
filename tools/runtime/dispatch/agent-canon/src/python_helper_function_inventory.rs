// @dependency-start
// contract implementation
// responsibility Inventories Python helper symbols using native Python AST facts and role/action tokens.
// upstream design ../../../../../documents/conventions/coding-conventions-python.md helper and role naming policy
// upstream implementation python_ast.rs shares native Python source and AST helpers
// downstream implementation ../../../../../tests/agent_tools/test_helper_function_inventory.py preserves helper inventory behavior
// @dependency-end

use crate::python_ast::{
    ast_dump_normalized_module_body, line_at_offset, node_line, normalize_python_newlines,
};
use rustpython_ast::{Ranged, Visitor};
use rustpython_parser::{ast, Parse};
use serde::Serialize;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

const DEFAULT_EXCLUDED_PARTS: &[&str] = &[
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "reports",
    "vendor",
];
const PUBLIC_LOCAL_HELPER_ROLES: &[&str] = &[
    "adapter_bridge",
    "collector_inventory",
    "converter_normalizer",
    "cli_parser",
    "command_runner",
    "factory_builder",
    "formatter_reporter",
    "parser_loader",
    "predicate",
    "static_analyzer",
    "validator_checker",
    "writer_mutator",
];
const CLASS_LOCAL_HELPER_ROLES: &[&str] = &[
    "adapter_bridge",
    "collector_inventory",
    "command_runner",
    "converter_normalizer",
    "data_container",
    "factory_builder",
    "formatter_reporter",
    "parser_loader",
    "state_holder",
    "static_analyzer",
    "validator_checker",
    "writer_mutator",
];
const LOCAL_SPECIALIZATIONS: &[&str] = &["single_caller_helper", "file_local_helper_cluster"];
const LOW_SIGNAL_HELPER_ROLES: &[&str] = &[
    "general_helper",
    "numeric_kernel",
    "protocol_interface",
    "test_support",
    "workflow_tooling",
];
const MUTATING_METHODS: &[&str] = &[
    "add",
    "append",
    "clear",
    "discard",
    "extend",
    "insert",
    "pop",
    "remove",
    "setdefault",
    "sort",
    "update",
    "write",
    "writelines",
];
const ROLE_SCORE_WEAK: usize = 1;
const ROLE_SCORE_STANDARD: usize = 2;
const ROLE_SCORE_STRONG: usize = 3;
const ROLE_SCORE_DOMINANT: usize = 4;
const ROLE_SCORE_BOUNDARY: usize = 5;
const BASE_HELPER_CONFIDENCE: f64 = 0.35;
const PRIVATE_NAME_CONFIDENCE_BONUS: f64 = 0.25;
const NESTED_SCOPE_CONFIDENCE_BONUS: f64 = 0.2;
const ROLE_SCORE_CONFIDENCE_CAP: f64 = 0.2;
const ROLE_SCORE_CONFIDENCE_DIVISOR: f64 = 20.0;
const DEFAULT_HALF_CONFIDENCE: f64 = 0.5;
const CALL_CONFIDENCE_BONUS: f64 = 0.05;
const FEATURE_CONFIDENCE_BONUS: f64 = 0.05;
const MAX_HELPER_CONFIDENCE: f64 = 0.99;
const JUDGMENT_CONFIDENCE: f64 = 0.4;
const SECONDARY_ROLE_SLICE_STOP: usize = 4;
const DOC_SUMMARY_LIMIT: usize = 140;
const LOCAL_CALLER_CLUSTER_LIMIT: usize = 3;
const EVIDENCE_RENDER_LIMIT: usize = 6;
const MARKDOWN_EVIDENCE_LIMIT: usize = 4;
const REDUNDANT_WITH_EVIDENCE_LIMIT: usize = 3;

fn role_name_tokens(role: &str) -> &'static [&'static str] {
    match role {
        "adapter_bridge" => &[
            "adapt", "adapter", "bridge", "connect", "forward", "proxy", "route", "shim", "wrap",
            "wrapper",
        ],
        "cli_parser" => &["arg", "args", "cli", "option", "parse", "parser"],
        "collector_inventory" => &[
            "collect",
            "enumerate",
            "extract",
            "find",
            "gather",
            "inventory",
            "list",
            "scan",
            "summary",
            "summarize",
        ],
        "command_runner" => &[
            "call", "command", "exec", "execute", "invoke", "launch", "run", "spawn",
        ],
        "converter_normalizer" => &[
            "adapt",
            "coerce",
            "convert",
            "map",
            "materialize",
            "normalize",
            "render",
            "resolve",
            "transform",
            "translate",
        ],
        "data_container" => &[
            "config", "context", "data", "info", "metadata", "metrics", "model", "options",
            "packet", "params", "record", "result", "state",
        ],
        "workflow_tooling" => &["agent", "route", "task", "tool", "workflow"],
        "writer_mutator" => &[
            "append", "emit", "persist", "record", "save", "store", "update", "write",
        ],
        "exception_type" => &["error", "exception", "failure"],
        "factory_builder" => &["build", "construct", "create", "factory", "make", "new"],
        "formatter_reporter" => &[
            "describe",
            "emit",
            "format",
            "render",
            "report",
            "summary",
            "summarize",
            "write",
        ],
        "general_helper" => &["helper", "support"],
        "numeric_kernel" => &[
            "compute", "kernel", "linear", "metric", "numeric", "residual", "score", "solve",
        ],
        "parser_loader" => &[
            "discover",
            "load",
            "materialize",
            "parse",
            "read",
            "resolve",
        ],
        "predicate" => &[
            "allow", "allows", "can", "check", "contains", "exists", "has", "is", "match",
            "matches", "needs", "ready", "should", "valid",
        ],
        "protocol_interface" => &["interface", "port", "protocol"],
        "state_holder" => &["cache", "holder", "registry", "session", "state", "store"],
        "static_analyzer" => &[
            "analyze", "ast", "classify", "detect", "infer", "inspect", "parse", "scan",
        ],
        "test_support" => &["fixture", "reference", "sample", "support", "test"],
        "validator_checker" => &[
            "assert", "check", "ensure", "guard", "lint", "validate", "verify",
        ],
        _ => &[],
    }
}

#[derive(Clone, Debug, Serialize)]
struct BodyFacts {
    calls: Vec<String>,
    call_locations: Vec<(String, usize)>,
    features: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
struct FunctionRecord {
    path: String,
    line: usize,
    end_line: usize,
    kind: String,
    domain: String,
    name: String,
    qualname: String,
    scope: String,
    visibility: String,
    role: String,
    secondary_roles: Vec<String>,
    name_tokens: Vec<String>,
    role_name_tokens: Vec<String>,
    matched_role_name_tokens: Vec<String>,
    searchable_name: bool,
    name_search_rule: String,
    confidence: f64,
    helper_candidate: bool,
    candidate_rule: String,
    needs_user_judgment: bool,
    judgment_rule: String,
    redundant_helper: bool,
    redundancy_rule: String,
    redundant_with: Vec<String>,
    implementation_signature: String,
    incoming_count: usize,
    incoming_callers: Vec<String>,
    incoming_call_sites: Vec<String>,
    outgoing_internal: Vec<String>,
    outgoing_call_sites: Vec<String>,
    specialized_helper: bool,
    specialization: String,
    side_effects: Vec<String>,
    features: Vec<String>,
    calls: Vec<String>,
    args: Vec<String>,
    bases: Vec<String>,
    method_count: usize,
    public_method_count: usize,
    decorators: Vec<String>,
    returns_annotation: String,
    doc_summary: String,
    evidence: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
struct Inventory {
    root: String,
    changed_only: bool,
    baseline_ref: String,
    baseline_symbols_seen: usize,
    baseline_filtered: usize,
    files_scanned: usize,
    symbols_seen: usize,
    functions_seen: usize,
    classes_seen: usize,
    symbols_reported: usize,
    helpers_reported: usize,
    judgment_required_reported: usize,
    name_gaps_reported: usize,
    role_counts: BTreeMap<String, usize>,
    verdict_counts: BTreeMap<String, usize>,
    records: Vec<FunctionRecord>,
}

#[derive(Clone, Debug, PartialEq)]
enum OutputFormat {
    Text,
    Json,
    Markdown,
}

#[derive(Clone, Debug)]
struct Options {
    paths: Vec<String>,
    root: PathBuf,
    format: OutputFormat,
    all_functions: bool,
    only_auto_helpers: bool,
    only_user_judgment: bool,
    only_name_gaps: bool,
    changed_only: bool,
    baseline_ref: String,
    include_vendor: bool,
    include_hidden: bool,
    include_pyi: bool,
    min_confidence: f64,
}

impl Default for Options {
    fn default() -> Self {
        Self {
            paths: Vec::new(),
            root: PathBuf::from("."),
            format: OutputFormat::Text,
            all_functions: false,
            only_auto_helpers: false,
            only_user_judgment: false,
            only_name_gaps: false,
            changed_only: false,
            baseline_ref: String::new(),
            include_vendor: false,
            include_hidden: false,
            include_pyi: false,
            min_confidence: 0.0,
        }
    }
}

fn usage() -> &'static str {
    "usage: agent-canon helper-function-inventory [paths ...] [--root ROOT] [--format {text,json,markdown}] [--all-functions] [--only-auto-helpers] [--only-user-judgment] [--only-name-gaps] [--changed] [--baseline-ref REF] [--include-vendor] [--include-hidden] [--include-pyi] [--min-confidence VALUE]"
}

fn option_value(
    args: &[String],
    index: &mut usize,
    inline: Option<&str>,
    option: &str,
) -> Result<String, String> {
    if let Some(value) = inline {
        if value.is_empty() {
            return Err(format!("argument {option}: expected one argument"));
        }
        return Ok(value.to_string());
    }
    let next = args
        .get(*index + 1)
        .ok_or_else(|| format!("argument {option}: expected one argument"))?;
    if next.starts_with('-') {
        return Err(format!("argument {option}: expected one argument"));
    }
    *index += 1;
    Ok(next.clone())
}

impl Options {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut options = Self::default();
        let mut index = 0;
        let mut positional_only = false;
        while index < args.len() {
            let token = &args[index];
            if positional_only {
                options.paths.push(token.clone());
                index += 1;
                continue;
            }
            if token == "--" {
                positional_only = true;
                index += 1;
                continue;
            }
            if matches!(token.as_str(), "-h" | "--help") {
                return Err(String::from("__help__"));
            }
            let (key, inline) = token
                .split_once('=')
                .map(|(key, value)| (key, Some(value.to_string())))
                .unwrap_or((token.as_str(), None));
            match key {
                "--root" => {
                    options.root =
                        PathBuf::from(option_value(args, &mut index, inline.as_deref(), key)?)
                }
                "--format" => {
                    options.format = match option_value(args, &mut index, inline.as_deref(), key)?
                        .as_str()
                    {
                        "text" => OutputFormat::Text,
                        "json" => OutputFormat::Json,
                        "markdown" => OutputFormat::Markdown,
                        value => return Err(format!(
                            "invalid choice: {value:?} (choose from 'text', 'json', 'markdown')"
                        )),
                    }
                }
                "--all-functions" if inline.is_none() => options.all_functions = true,
                "--only-auto-helpers" if inline.is_none() => options.only_auto_helpers = true,
                "--only-user-judgment" if inline.is_none() => options.only_user_judgment = true,
                "--only-name-gaps" if inline.is_none() => options.only_name_gaps = true,
                "--changed" if inline.is_none() => options.changed_only = true,
                "--include-vendor" if inline.is_none() => options.include_vendor = true,
                "--include-hidden" if inline.is_none() => options.include_hidden = true,
                "--include-pyi" if inline.is_none() => options.include_pyi = true,
                "--baseline-ref" => {
                    options.baseline_ref = option_value(args, &mut index, inline.as_deref(), key)?
                }
                "--min-confidence" => {
                    let value = option_value(args, &mut index, inline.as_deref(), key)?;
                    options.min_confidence = value.parse::<f64>().map_err(|_| {
                        format!("argument --min-confidence: invalid float value: {value:?}")
                    })?;
                }
                value if value.starts_with('-') => {
                    return Err(format!("unrecognized arguments: {token}"))
                }
                _ => options.paths.push(token.clone()),
            }
            index += 1;
        }
        if options.only_auto_helpers && options.only_user_judgment {
            return Err(
                "argument --only-user-judgment: not allowed with argument --only-auto-helpers"
                    .into(),
            );
        }
        Ok(options)
    }
}

pub fn run(args: &[String]) -> i32 {
    let options = match Options::parse(args) {
        Ok(options) => options,
        Err(message) if message == "__help__" => {
            println!("{}", usage());
            return 0;
        }
        Err(message) => {
            eprintln!("{}", usage());
            eprintln!("agent-canon helper-function-inventory: error: {message}");
            return 2;
        }
    };
    let root = absolute_path(&options.root);
    let inventory = build_inventory(&root, &options);
    match options.format {
        OutputFormat::Json => {
            let mut value = serde_json::to_value(&inventory).unwrap_or(Value::Null);
            let head = git_sha(&root);
            if let Value::Object(ref mut object) = value {
                let _ = object.insert("head".into(), Value::String(head));
            }
            let rendered = serde_json::to_string_pretty(&value).unwrap_or_else(|_| "{}".into());
            println!("{}", escape_non_ascii_json(&rendered));
        }
        OutputFormat::Markdown => print!("{}", render_markdown(&inventory)),
        OutputFormat::Text => print!("{}", render_text(&inventory)),
    }
    0
}

fn absolute_path(path: &Path) -> PathBuf {
    if let Ok(canonical) = path.canonicalize() {
        return canonical;
    }
    if path.is_absolute() {
        return path.to_path_buf();
    }
    std::env::current_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(path)
}

fn escape_non_ascii_json(value: &str) -> String {
    let mut result = String::with_capacity(value.len());
    let mut in_string = false;
    let mut escaped = false;
    for character in value.chars() {
        if in_string && (character as u32) > 0x7f {
            let scalar = character as u32;
            if scalar <= 0xffff {
                result.push_str(&format!("\\u{scalar:04x}"));
            } else {
                let adjusted = scalar - 0x10000;
                let high = 0xd800 + (adjusted >> 10);
                let low = 0xdc00 + (adjusted & 0x3ff);
                result.push_str(&format!("\\u{high:04x}\\u{low:04x}"));
            }
            continue;
        }
        result.push(character);
        if in_string {
            if escaped {
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == '"' {
                in_string = false;
            }
        } else if character == '"' {
            in_string = true;
        }
    }
    result
}

#[derive(Default)]
struct FileWalkState {
    files: Vec<PathBuf>,
    seen_dirs: BTreeSet<PathBuf>,
    seen_files: BTreeSet<PathBuf>,
}

fn logical_excluded(relative: &Path, include_vendor: bool, include_hidden: bool) -> bool {
    let parts = relative
        .components()
        .map(|part| part.as_os_str().to_string_lossy());
    let parts: Vec<String> = parts.map(|part| part.into_owned()).collect();
    if parts.iter().any(|part| {
        DEFAULT_EXCLUDED_PARTS.contains(&part.as_str()) && !(include_vendor && part == "vendor")
    }) {
        return true;
    }
    if !include_hidden && parts.iter().any(|part| part.starts_with('.')) {
        return true;
    }
    parts.len() >= 2 && parts[0] == "python" && parts[1] == "typings"
}

fn source_suffix_allowed(path: &Path, include_pyi: bool) -> bool {
    match path.extension().and_then(|extension| extension.to_str()) {
        Some("py") => true,
        Some("pyi") => include_pyi,
        _ => false,
    }
}

fn stable_relative(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .map(|relative| relative.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| path.to_string_lossy().replace('\\', "/"))
}

fn root_relative_or_self(root: &Path, path: &Path) -> PathBuf {
    path.strip_prefix(root).unwrap_or(path).to_path_buf()
}

fn append_source_once(state: &mut FileWalkState, path: PathBuf, include_pyi: bool) {
    if !source_suffix_allowed(&path, include_pyi) {
        return;
    }
    let resolved = path.canonicalize().unwrap_or_else(|_| path.clone());
    if state.seen_files.insert(resolved) {
        state.files.push(path);
    }
}

fn iter_python_files(
    root: &Path,
    raw_paths: &[String],
    include_vendor: bool,
    include_hidden: bool,
    include_pyi: bool,
) -> Vec<PathBuf> {
    let targets = if raw_paths.is_empty() {
        vec![root.to_path_buf()]
    } else {
        raw_paths.iter().map(|path| root.join(path)).collect()
    };
    let mut state = FileWalkState::default();
    for target in targets {
        if target.is_file() {
            append_source_once(&mut state, target, include_pyi);
            continue;
        }
        walk_source_dir(
            root,
            &target,
            include_vendor,
            include_hidden,
            include_pyi,
            &mut state,
        );
    }
    state.files.sort_by_key(|path| stable_relative(root, path));
    state.files
}

fn walk_source_dir(
    root: &Path,
    current: &Path,
    include_vendor: bool,
    include_hidden: bool,
    include_pyi: bool,
    state: &mut FileWalkState,
) {
    let real_current = current
        .canonicalize()
        .unwrap_or_else(|_| current.to_path_buf());
    if !state.seen_dirs.insert(real_current) {
        return;
    }
    if logical_excluded(
        &root_relative_or_self(root, current),
        include_vendor,
        include_hidden,
    ) {
        return;
    }
    let Ok(entries) = fs::read_dir(current) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            if !logical_excluded(
                &root_relative_or_self(root, &path),
                include_vendor,
                include_hidden,
            ) {
                walk_source_dir(
                    root,
                    &path,
                    include_vendor,
                    include_hidden,
                    include_pyi,
                    state,
                );
            }
        } else {
            append_source_once(state, path, include_pyi);
        }
    }
}

fn requested_relative_paths(root: &Path, options: &Options) -> BTreeSet<String> {
    if options.paths.is_empty() {
        return BTreeSet::new();
    }
    iter_python_files(
        root,
        &options.paths,
        options.include_vendor,
        options.include_hidden,
        options.include_pyi,
    )
    .iter()
    .map(|path| stable_relative(root, path))
    .collect()
}

fn git_output(root: &Path, arguments: &[&str]) -> Option<Output> {
    Command::new("git")
        .arg("-C")
        .arg(root)
        .args(arguments)
        .output()
        .ok()
}

fn git_lines(root: &Path, arguments: &[&str]) -> Vec<String> {
    let Some(output) = git_output(root, arguments) else {
        return Vec::new();
    };
    if !output.status.success() {
        return Vec::new();
    }
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect()
}

fn changed_python_files(root: &Path, options: &Options) -> Vec<PathBuf> {
    let mut names = BTreeSet::new();
    for arguments in [
        vec!["diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"],
        vec![
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMR",
            "--",
        ],
        vec!["ls-files", "--others", "--exclude-standard"],
    ] {
        names.extend(git_lines(root, &arguments));
    }
    names
        .into_iter()
        .filter_map(|name| {
            let relative = Path::new(&name);
            let path = root.join(relative);
            if !source_suffix_allowed(relative, options.include_pyi)
                || logical_excluded(relative, options.include_vendor, options.include_hidden)
                || !path.is_file()
            {
                None
            } else {
                Some(path)
            }
        })
        .collect()
}

fn filtered_changed_python_files(root: &Path, options: &Options) -> Vec<PathBuf> {
    let changed = changed_python_files(root, options);
    let requested = requested_relative_paths(root, options);
    if requested.is_empty() {
        return changed;
    }
    changed
        .into_iter()
        .filter(|path| requested.contains(&stable_relative(root, path)))
        .collect()
}

fn git_ref_text(root: &Path, reference: &str, relative_path: &str) -> Option<String> {
    let spec = format!("{reference}:{relative_path}");
    let output = git_output(root, &["show", &spec])?;
    if !output.status.success() {
        return None;
    }
    String::from_utf8(output.stdout).ok()
}

fn git_renamed_paths(root: &Path, reference: &str) -> BTreeMap<String, String> {
    if reference.is_empty() {
        return BTreeMap::new();
    }
    let Some(output) = git_output(
        root,
        &["diff", "--name-status", "--find-renames", reference, "--"],
    ) else {
        return BTreeMap::new();
    };
    if !output.status.success() {
        return BTreeMap::new();
    }
    let text = String::from_utf8_lossy(&output.stdout);
    let mut renamed = BTreeMap::new();
    for line in text.lines() {
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.len() >= 3 && parts[0].starts_with('R') {
            let _ = renamed.insert(parts[2].to_string(), parts[1].to_string());
        }
    }
    renamed
}

fn path_domain(path: &str) -> String {
    let parts: Vec<String> = Path::new(path)
        .components()
        .map(|part| part.as_os_str().to_string_lossy().into_owned())
        .collect();
    if parts
        .iter()
        .any(|part| part == "tests" || part == "test" || part.starts_with("test_"))
    {
        "test".into()
    } else if parts.iter().any(|part| {
        part == "benchmarks"
            || part == "experiments"
            || part == "notebooks"
            || part.starts_with("bench")
            || part.starts_with("experiment")
    }) {
        "experiment".into()
    } else if parts
        .iter()
        .any(|part| ["agent_tools", "scripts", "tools"].contains(&part.as_str()))
    {
        "tooling".into()
    } else {
        "main".into()
    }
}

fn dotted_name(expression: &ast::Expr) -> String {
    match expression {
        ast::Expr::Name(node) => node.id.to_string(),
        ast::Expr::Attribute(node) => {
            let base = dotted_name(&node.value);
            if base.is_empty() {
                node.attr.to_string()
            } else {
                format!("{base}.{}", node.attr)
            }
        }
        ast::Expr::Call(node) => dotted_name(&node.func),
        ast::Expr::Subscript(node) => dotted_name(&node.value),
        _ => String::new(),
    }
}

fn function_parameters(arguments: &ast::Arguments) -> Vec<String> {
    let mut names = arguments
        .posonlyargs
        .iter()
        .chain(&arguments.args)
        .chain(&arguments.kwonlyargs)
        .map(|argument| argument.def.arg.to_string())
        .collect::<Vec<_>>();
    if let Some(argument) = &arguments.vararg {
        names.push(argument.arg.to_string());
    }
    if let Some(argument) = &arguments.kwarg {
        names.push(argument.arg.to_string());
    }
    names
}

fn function_args(arguments: &ast::Arguments) -> Vec<String> {
    arguments
        .args
        .iter()
        .map(|argument| argument.def.arg.to_string())
        .collect()
}

fn argument_passes_parameter(expression: &ast::Expr, parameters: &BTreeSet<String>) -> bool {
    match expression {
        ast::Expr::Name(node) => parameters.contains(node.id.as_str()),
        ast::Expr::Starred(node) => {
            matches!(&*node.value, ast::Expr::Name(value) if parameters.contains(value.id.as_str()))
        }
        _ => false,
    }
}

fn call_passes_parameters(call: &ast::ExprCall, parameters: &BTreeSet<String>) -> bool {
    if call.args.is_empty() && call.keywords.is_empty() {
        return false;
    }
    call.args
        .iter()
        .all(|argument| argument_passes_parameter(argument, parameters))
        && call.keywords.iter().all(|keyword| {
            matches!(&keyword.value, ast::Expr::Name(value) if parameters.contains(value.id.as_str()))
        })
}

#[derive(Default)]
struct AstProbe {
    saw_call: bool,
    saw_return: bool,
    saw_string: bool,
}

impl Visitor for AstProbe {
    fn visit_stmt_return(&mut self, node: ast::StmtReturn) {
        self.saw_return = true;
        self.generic_visit_stmt_return(node);
    }

    fn visit_expr_call(&mut self, node: ast::ExprCall) {
        self.saw_call = true;
        self.generic_visit_expr_call(node);
    }

    fn visit_expr_constant(&mut self, node: ast::ExprConstant) {
        if matches!(&node.value, ast::Constant::Str(_)) {
            self.saw_string = true;
        }
        self.generic_visit_expr_constant(node);
    }
}

fn expression_has_call(expression: &ast::Expr) -> bool {
    let mut probe = AstProbe::default();
    probe.visit_expr(expression.clone());
    probe.saw_call
}

fn expression_has_string(expression: &ast::Expr) -> bool {
    let mut probe = AstProbe::default();
    probe.visit_expr(expression.clone());
    probe.saw_string
}

fn statement_contains_return(statement: &ast::Stmt) -> bool {
    let mut probe = AstProbe::default();
    probe.visit_stmt(statement.clone());
    probe.saw_return
}

fn body_without_docstring(body: &[ast::Stmt]) -> &[ast::Stmt] {
    match body.first() {
        Some(ast::Stmt::Expr(statement)) if expression_has_string(&statement.value) => &body[1..],
        _ => body,
    }
}

fn docstring(body: &[ast::Stmt]) -> Option<String> {
    match body.first() {
        Some(ast::Stmt::Expr(statement)) => match &*statement.value {
            ast::Expr::Constant(value) => match &value.value {
                ast::Constant::Str(text) => Some(text.clone()),
                _ => None,
            },
            _ => None,
        },
        _ => None,
    }
}

fn doc_summary(docstring: Option<&str>) -> String {
    let Some(docstring) = docstring else {
        return String::new();
    };
    let compact = docstring.split_whitespace().collect::<Vec<_>>().join(" ");
    for separator in [". ", "。"] {
        if let Some(index) = compact.find(separator) {
            let end = index + separator.trim().len();
            return compact[..end].trim().to_string();
        }
    }
    compact.chars().take(DOC_SUMMARY_LIMIT).collect()
}

fn is_returned_parameter(value: &ast::Expr, parameters: &BTreeSet<String>) -> bool {
    matches!(value, ast::Expr::Name(node) if parameters.contains(node.id.as_str()))
}

#[derive(Clone, Copy)]
enum BodyRootKind {
    Function,
    Class,
}

struct FunctionBodyCollector<'a> {
    source: &'a str,
    root_start: usize,
    root_kind: BodyRootKind,
    parameters: BTreeSet<String>,
    calls: BTreeMap<String, usize>,
    call_locations: Vec<(String, usize)>,
    features: BTreeSet<String>,
}

impl FunctionBodyCollector<'_> {
    fn record_call(&mut self, name: String, line: usize) {
        if name.is_empty() {
            return;
        }
        *self.calls.entry(name.clone()).or_default() += 1;
        self.call_locations.push((name.clone(), line));
        let leaf = name.rsplit('.').next().unwrap_or(&name);
        record_call_features(&mut self.features, &name, leaf);
    }

    fn add(&mut self, feature: &str) {
        self.features.insert(feature.to_string());
    }

    fn facts(mut self, single_statement: bool) -> BodyFacts {
        if single_statement {
            self.features.insert("single_statement_body".into());
        }
        let mut calls = Vec::new();
        for (name, count) in self.calls {
            for _ in 0..count {
                calls.push(name.clone());
            }
        }
        self.call_locations.sort();
        BodyFacts {
            calls,
            call_locations: self.call_locations,
            features: self.features.into_iter().collect(),
        }
    }
}

impl Visitor for FunctionBodyCollector<'_> {
    fn visit_stmt_function_def(&mut self, node: ast::StmtFunctionDef) {
        if node.start().to_usize() == self.root_start
            && matches!(self.root_kind, BodyRootKind::Function)
        {
            self.generic_visit_stmt_function_def(node);
        } else {
            self.add("nested_function_definition");
        }
    }

    fn visit_stmt_async_function_def(&mut self, node: ast::StmtAsyncFunctionDef) {
        if node.start().to_usize() == self.root_start
            && matches!(self.root_kind, BodyRootKind::Function)
        {
            self.generic_visit_stmt_async_function_def(node);
        } else {
            self.add("nested_function_definition");
        }
    }

    fn visit_stmt_class_def(&mut self, node: ast::StmtClassDef) {
        if node.start().to_usize() == self.root_start
            && matches!(self.root_kind, BodyRootKind::Class)
        {
            self.generic_visit_stmt_class_def(node);
        }
    }

    fn visit_expr_call(&mut self, node: ast::ExprCall) {
        self.record_call(dotted_name(&node.func), node_line(self.source, &node));
        self.generic_visit_expr_call(node);
    }

    fn visit_expr_attribute(&mut self, node: ast::ExprAttribute) {
        if dotted_name(&ast::Expr::Attribute(node.clone())) == "sys.platform" {
            self.add("environment");
        }
        self.generic_visit_expr_attribute(node);
    }

    fn visit_expr_bin_op(&mut self, node: ast::ExprBinOp) {
        if matches!(&node.op, ast::Operator::Div) {
            self.add("path_operation");
        }
        if matches!(
            &node.op,
            ast::Operator::Add
                | ast::Operator::MatMult
                | ast::Operator::Mult
                | ast::Operator::Pow
                | ast::Operator::Sub
        ) {
            self.add("operator_expression");
        }
        self.generic_visit_expr_bin_op(node);
    }

    fn visit_expr_joined_str(&mut self, node: ast::ExprJoinedStr) {
        self.add("text_transform");
        self.generic_visit_expr_joined_str(node);
    }

    fn visit_expr_lambda(&mut self, node: ast::ExprLambda) {
        self.add("nested_function_definition");
        self.generic_visit_expr_lambda(node);
    }

    fn visit_stmt_return(&mut self, node: ast::StmtReturn) {
        if let Some(value) = node.value.as_deref() {
            if expression_has_call(value) {
                self.add("call_return");
            }
            if let ast::Expr::Call(call) = value {
                self.add("direct_call_return");
                if call_passes_parameters(call, &self.parameters) {
                    self.add("pass_through_call_return");
                }
            }
            if is_returned_parameter(value, &self.parameters) {
                self.add("identity_return");
            }
            match value {
                ast::Expr::IfExp(_) => self.add("conditional_return"),
                ast::Expr::Dict(_) | ast::Expr::DictComp(_) => self.add("mapping_return"),
                ast::Expr::List(_)
                | ast::Expr::ListComp(_)
                | ast::Expr::Set(_)
                | ast::Expr::SetComp(_)
                | ast::Expr::Tuple(_) => self.add("collection_return"),
                ast::Expr::BoolOp(_) | ast::Expr::Compare(_) | ast::Expr::UnaryOp(_) => {
                    self.add("predicate_return")
                }
                _ => {}
            }
        }
        self.generic_visit_stmt_return(node);
    }

    fn visit_stmt_expr(&mut self, node: ast::StmtExpr) {
        if let ast::Expr::Call(call) = &*node.value {
            self.add("call_statement");
            if call_passes_parameters(call, &self.parameters) {
                self.add("pass_through_call_statement");
            }
        }
        self.generic_visit_stmt_expr(node);
    }

    fn visit_stmt_if(&mut self, node: ast::StmtIf) {
        if node
            .body
            .iter()
            .chain(&node.orelse)
            .any(statement_contains_return)
        {
            self.add("conditional_return");
        }
        self.generic_visit_stmt_if(node);
    }

    fn visit_stmt_with(&mut self, node: ast::StmtWith) {
        self.add("resource_lifecycle");
        self.generic_visit_stmt_with(node);
    }

    fn visit_stmt_async_with(&mut self, node: ast::StmtAsyncWith) {
        self.add("resource_lifecycle");
        self.generic_visit_stmt_async_with(node);
    }

    fn visit_stmt_for(&mut self, node: ast::StmtFor) {
        self.add("iteration");
        self.generic_visit_stmt_for(node);
    }

    fn visit_stmt_async_for(&mut self, node: ast::StmtAsyncFor) {
        self.add("iteration");
        self.generic_visit_stmt_async_for(node);
    }

    fn visit_comprehension(&mut self, node: ast::Comprehension) {
        self.add("iteration");
        self.generic_visit_comprehension(node);
    }

    fn visit_expr_yield(&mut self, node: ast::ExprYield) {
        self.add("generator");
        self.generic_visit_expr_yield(node);
    }

    fn visit_expr_yield_from(&mut self, node: ast::ExprYieldFrom) {
        self.add("generator");
        self.generic_visit_expr_yield_from(node);
    }

    fn visit_stmt_raise(&mut self, node: ast::StmtRaise) {
        self.add("raises");
        self.generic_visit_stmt_raise(node);
    }

    fn visit_stmt_import(&mut self, node: ast::StmtImport) {
        self.add("local_import");
        self.generic_visit_stmt_import(node);
    }

    fn visit_stmt_import_from(&mut self, node: ast::StmtImportFrom) {
        self.add("local_import");
        self.generic_visit_stmt_import_from(node);
    }

    fn visit_stmt_global(&mut self, node: ast::StmtGlobal) {
        self.add("state_mutation");
        self.generic_visit_stmt_global(node);
    }

    fn visit_stmt_assign(&mut self, node: ast::StmtAssign) {
        if node
            .targets
            .iter()
            .any(|target| matches!(target, ast::Expr::Attribute(_) | ast::Expr::Subscript(_)))
        {
            self.add("state_mutation");
        }
        self.generic_visit_stmt_assign(node);
    }

    fn visit_stmt_ann_assign(&mut self, node: ast::StmtAnnAssign) {
        if matches!(
            &*node.target,
            ast::Expr::Attribute(_) | ast::Expr::Subscript(_)
        ) {
            self.add("state_mutation");
        }
        self.generic_visit_stmt_ann_assign(node);
    }
}

fn body_facts(
    source: &str,
    root: &ast::Stmt,
    parameters: &[String],
    single_statement: bool,
) -> BodyFacts {
    let root_start = root.start().to_usize();
    let root_kind = match root {
        ast::Stmt::FunctionDef(_) | ast::Stmt::AsyncFunctionDef(_) => BodyRootKind::Function,
        _ => BodyRootKind::Class,
    };
    let mut collector = FunctionBodyCollector {
        source,
        root_start,
        root_kind,
        parameters: parameters.iter().cloned().collect(),
        calls: BTreeMap::new(),
        call_locations: Vec::new(),
        features: BTreeSet::new(),
    };
    collector.visit_stmt(root.clone());
    collector.facts(single_statement)
}

fn function_body_facts(source: &str, node: &ast::StmtFunctionDef) -> BodyFacts {
    let body = body_without_docstring(&node.body);
    body_facts(
        source,
        &ast::Stmt::FunctionDef(node.clone()),
        &function_parameters(&node.args),
        body.len() == 1,
    )
}

fn async_function_body_facts(source: &str, node: &ast::StmtAsyncFunctionDef) -> BodyFacts {
    let body = body_without_docstring(&node.body);
    body_facts(
        source,
        &ast::Stmt::AsyncFunctionDef(node.clone()),
        &function_parameters(&node.args),
        body.len() == 1,
    )
}

fn class_body_facts(source: &str, node: &ast::StmtClassDef) -> BodyFacts {
    let mut all_calls = BTreeMap::<String, usize>::new();
    let mut locations = Vec::new();
    let mut features = BTreeSet::new();
    let class = body_facts(source, &ast::Stmt::ClassDef(node.clone()), &[], false);
    for call in class.calls {
        *all_calls.entry(call).or_default() += 1;
    }
    locations.extend(class.call_locations);
    features.extend(class.features);
    for statement in &node.body {
        match statement {
            ast::Stmt::FunctionDef(method) => {
                let facts = function_body_facts(source, method);
                for call in facts.calls {
                    *all_calls.entry(call).or_default() += 1;
                }
                locations.extend(facts.call_locations);
                features.extend(facts.features);
            }
            ast::Stmt::AsyncFunctionDef(method) => {
                let facts = async_function_body_facts(source, method);
                for call in facts.calls {
                    *all_calls.entry(call).or_default() += 1;
                }
                locations.extend(facts.call_locations);
                features.extend(facts.features);
            }
            _ => {}
        }
    }
    locations.sort();
    let mut calls = Vec::new();
    for (call, count) in all_calls {
        for _ in 0..count {
            calls.push(call.clone());
        }
    }
    BodyFacts {
        calls,
        call_locations: locations,
        features: features.into_iter().collect(),
    }
}

fn record_call_features(features: &mut BTreeSet<String>, name: &str, leaf: &str) {
    if MUTATING_METHODS.contains(&leaf) {
        features.insert("mutation_call".into());
    }
    if ["close", "cleanup", "release", "shutdown"].contains(&leaf) {
        features.insert("resource_lifecycle".into());
    }
    if name.starts_with("subprocess.") || ["Popen", "run"].contains(&leaf) {
        features.insert("subprocess".into());
    }
    if ["print", "sys.stdout.write", "sys.stderr.write"].contains(&name) {
        features.insert("stdio".into());
    }
    if name.starts_with("logging.") || ["debug", "info", "warning", "error"].contains(&leaf) {
        features.insert("logging".into());
    }
    if ["write", "write_text", "write_bytes", "dump", "dumps"].contains(&leaf) {
        features.insert("write".into());
    }
    if [
        "mkdir", "unlink", "rename", "replace", "copy", "copy2", "rmtree",
    ]
    .contains(&leaf)
    {
        features.insert("filesystem_mutation".into());
    }
    if name == "progress_callback" {
        features.insert("callback_emission".into());
    }
    if ["read", "read_text", "read_bytes", "load", "loads"].contains(&leaf) {
        features.insert("read".into());
    }
    if ["json.", "tomllib.", "tomli.", "yaml."]
        .iter()
        .any(|prefix| name.starts_with(prefix))
    {
        features.insert("serialization".into());
    }
    if name.starts_with("base64.") {
        features.insert("encoding_transform".into());
    }
    if name.starts_with("re.") {
        features.insert("text_transform".into());
    }
    if name == "Path"
        || ["pathlib.", "os.path."]
            .iter()
            .any(|prefix| name.starts_with(prefix))
    {
        features.insert("path_operation".into());
    }
    if [
        "absolute",
        "expanduser",
        "joinpath",
        "relative_to",
        "resolve",
        "with_name",
        "with_suffix",
    ]
    .contains(&leaf)
    {
        features.insert("path_operation".into());
    }
    if [
        "format",
        "join",
        "lower",
        "removeprefix",
        "removesuffix",
        "replace",
        "rstrip",
        "split",
        "strip",
        "upper",
    ]
    .contains(&leaf)
    {
        features.insert("text_transform".into());
    }
    if name.starts_with("hashlib.")
        || name.starts_with("hmac.")
        || ["digest", "hexdigest"].contains(&leaf)
    {
        features.insert("digest_transform".into());
    }
    if ["decrypt", "encrypt"].contains(&leaf) {
        features.insert("security_transform".into());
    }
    if name.starts_with("os.environ")
        || ["os.getenv", "getenv"].contains(&name)
        || name.starts_with("platform.")
    {
        features.insert("environment".into());
    }
    if ["ctypes.", "cffi."]
        .iter()
        .any(|prefix| name.starts_with(prefix))
        || ["byref", "cast", "c_void_p"].contains(&leaf)
    {
        features.insert("pointer_interop".into());
    }
    if ["getattr", "hasattr", "isinstance", "issubclass", "type"].contains(&leaf) {
        features.insert("type_introspection".into());
    }
    if name.starts_with("ast.") || name.starts_with("libcst.") {
        features.insert("static_analysis".into());
    }
    if ["jax.", "jnp.", "np.", "numpy.", "math.", "lax."]
        .iter()
        .any(|prefix| name.starts_with(prefix))
    {
        features.insert("numeric".into());
    }
    if [
        "array",
        "asarray",
        "ascontiguousarray",
        "flatten",
        "ravel",
        "reshape",
        "tolist",
        "tree_flatten",
        "tree_leaves",
        "tree_map",
        "tree_unflatten",
    ]
    .contains(&leaf)
    {
        features.insert("data_shape_transform".into());
    }
    if name.starts_with("argparse.") || leaf == "ArgumentParser" {
        features.insert("cli_parser".into());
    }
    if name.starts_with("requests.") || name.starts_with("urllib.") {
        features.insert("network".into());
    }
}

type RoleScores = Vec<(String, usize)>;

fn add_role_score(
    scores: &mut RoleScores,
    evidence: &mut Vec<String>,
    role: &str,
    points: usize,
    reason: &str,
) {
    if let Some((_, score)) = scores.iter_mut().find(|(name, _)| name == role) {
        *score += points;
    } else {
        scores.push((role.to_string(), points));
    }
    evidence.push(format!("{role}:{reason}"));
}

fn ordered_roles(scores: &RoleScores) -> Vec<String> {
    let mut items = scores.iter().enumerate().collect::<Vec<_>>();
    items.sort_by(
        |(left_index, (_, left_score)), (right_index, (_, right_score))| {
            right_score
                .cmp(left_score)
                .then_with(|| left_index.cmp(right_index))
        },
    );
    items
        .into_iter()
        .map(|(_, (role, _))| role.clone())
        .collect()
}

fn max_role_score(scores: &RoleScores) -> usize {
    scores.iter().map(|(_, score)| *score).max().unwrap_or(0)
}

fn path_parts(path: &str) -> Vec<String> {
    Path::new(path)
        .components()
        .map(|part| part.as_os_str().to_string_lossy().into_owned())
        .collect()
}

fn add_path_role_scores(scores: &mut RoleScores, evidence: &mut Vec<String>, parts: &[String]) {
    if parts
        .iter()
        .any(|part| part == "tools" || part == "agent_tools")
    {
        add_role_score(
            scores,
            evidence,
            "workflow_tooling",
            ROLE_SCORE_WEAK,
            "tool-path",
        );
    }
    if parts.iter().any(|part| part == "tests") {
        add_role_score(
            scores,
            evidence,
            "test_support",
            ROLE_SCORE_WEAK,
            "test-path",
        );
    }
}

fn add_common_body_role_scores(
    scores: &mut RoleScores,
    evidence: &mut Vec<String>,
    calls: &BTreeSet<String>,
    features: &BTreeSet<String>,
) {
    add_effect_role_scores(scores, evidence, features);
    add_transform_role_scores(scores, evidence, features);
    add_structure_role_scores(scores, evidence, calls, features);
}

fn add_effect_role_scores(
    scores: &mut RoleScores,
    evidence: &mut Vec<String>,
    features: &BTreeSet<String>,
) {
    if features.contains("subprocess") {
        add_role_score(
            scores,
            evidence,
            "command_runner",
            ROLE_SCORE_STRONG,
            "subprocess-call",
        );
    }
    if features.contains("network") {
        add_role_score(
            scores,
            evidence,
            "command_runner",
            ROLE_SCORE_WEAK,
            "network-call",
        );
    }
    if features.contains("cli_parser") {
        add_role_score(
            scores,
            evidence,
            "cli_parser",
            ROLE_SCORE_DOMINANT,
            "argparse-call",
        );
    }
    if features.contains("write") || features.contains("filesystem_mutation") {
        add_role_score(
            scores,
            evidence,
            "writer_mutator",
            ROLE_SCORE_STANDARD,
            "write-or-filesystem-call",
        );
    }
    if features.contains("resource_lifecycle") {
        add_role_score(
            scores,
            evidence,
            "writer_mutator",
            ROLE_SCORE_STRONG,
            "resource-lifecycle",
        );
    }
    if features.contains("callback_emission") {
        add_role_score(
            scores,
            evidence,
            "formatter_reporter",
            ROLE_SCORE_STRONG,
            "callback-emission",
        );
    }
    if features.contains("call_statement") {
        add_role_score(
            scores,
            evidence,
            "adapter_bridge",
            ROLE_SCORE_STANDARD,
            "call-statement",
        );
    }
    if features.contains("logging") || features.contains("stdio") {
        add_role_score(
            scores,
            evidence,
            "formatter_reporter",
            ROLE_SCORE_WEAK,
            "human-output",
        );
    }
}

fn add_transform_role_scores(
    scores: &mut RoleScores,
    evidence: &mut Vec<String>,
    features: &BTreeSet<String>,
) {
    if features.contains("serialization") && features.contains("read") {
        add_role_score(
            scores,
            evidence,
            "parser_loader",
            ROLE_SCORE_STANDARD,
            "serialization-read",
        );
    } else if features.contains("serialization") {
        add_role_score(
            scores,
            evidence,
            "formatter_reporter",
            ROLE_SCORE_STANDARD,
            "serialization-transform",
        );
    }
    if features.contains("path_operation") {
        add_role_score(
            scores,
            evidence,
            "converter_normalizer",
            ROLE_SCORE_STRONG,
            "path-operation",
        );
    }
    if features.contains("text_transform") || features.contains("encoding_transform") {
        add_role_score(
            scores,
            evidence,
            "converter_normalizer",
            ROLE_SCORE_STANDARD,
            "text-or-encoding-transform",
        );
    }
    if features.contains("type_introspection") {
        add_role_score(
            scores,
            evidence,
            "converter_normalizer",
            ROLE_SCORE_STANDARD,
            "type-introspection",
        );
    }
    if features.contains("conditional_return") || features.contains("environment") {
        add_role_score(
            scores,
            evidence,
            "converter_normalizer",
            ROLE_SCORE_STANDARD,
            "conditional-or-environment-normalization",
        );
    }
    if features.contains("identity_return") {
        add_role_score(
            scores,
            evidence,
            "converter_normalizer",
            ROLE_SCORE_STANDARD,
            "identity-return",
        );
    }
    if features.contains("digest_transform") || features.contains("security_transform") {
        add_role_score(
            scores,
            evidence,
            "converter_normalizer",
            ROLE_SCORE_STRONG,
            "digest-or-security-transform",
        );
    }
    if features.contains("pointer_interop") || features.contains("data_shape_transform") {
        add_role_score(
            scores,
            evidence,
            "converter_normalizer",
            ROLE_SCORE_DOMINANT,
            "interop-or-shape-transform",
        );
    }
    if features.contains("read") {
        add_role_score(
            scores,
            evidence,
            "parser_loader",
            ROLE_SCORE_STANDARD,
            "read-call",
        );
    }
}

fn add_structure_role_scores(
    scores: &mut RoleScores,
    evidence: &mut Vec<String>,
    calls: &BTreeSet<String>,
    features: &BTreeSet<String>,
) {
    if features.contains("static_analysis") || calls.iter().any(|call| call.starts_with("ast.")) {
        add_role_score(
            scores,
            evidence,
            "static_analyzer",
            ROLE_SCORE_BOUNDARY,
            "ast-call",
        );
    }
    if features.contains("numeric") {
        add_role_score(
            scores,
            evidence,
            "numeric_kernel",
            ROLE_SCORE_STRONG,
            "numeric-call",
        );
    }
    if features.contains("operator_expression") {
        add_role_score(
            scores,
            evidence,
            "numeric_kernel",
            ROLE_SCORE_STANDARD,
            "operator-expression",
        );
    }
    if features.contains("mapping_return") {
        add_role_score(
            scores,
            evidence,
            "formatter_reporter",
            ROLE_SCORE_STANDARD,
            "mapping-return",
        );
    }
    if features.contains("collection_return")
        || features.contains("generator")
        || features.contains("iteration")
    {
        add_role_score(
            scores,
            evidence,
            "collector_inventory",
            ROLE_SCORE_STANDARD,
            "collection-or-iteration",
        );
    }
    if features.contains("nested_function_definition") {
        add_role_score(
            scores,
            evidence,
            "factory_builder",
            ROLE_SCORE_DOMINANT,
            "nested-callable-definition",
        );
    }
    if features.contains("raises") {
        add_role_score(
            scores,
            evidence,
            "validator_checker",
            ROLE_SCORE_STANDARD,
            "raises",
        );
    }
}

fn add_function_body_role_scores(
    scores: &mut RoleScores,
    evidence: &mut Vec<String>,
    features: &BTreeSet<String>,
) {
    if features.contains("state_mutation") || features.contains("mutation_call") {
        add_role_score(
            scores,
            evidence,
            "writer_mutator",
            ROLE_SCORE_WEAK,
            "mutation-call",
        );
    }
    if features.contains("call_return")
        && !["read", "write", "numeric", "static_analysis"]
            .iter()
            .any(|feature| features.contains(*feature))
    {
        add_role_score(
            scores,
            evidence,
            "factory_builder",
            ROLE_SCORE_WEAK,
            "call-return",
        );
    }
}

fn collection_annotation(annotation: &str) -> bool {
    let lowered = annotation.to_lowercase();
    ["tuple", "list", "set", "frozenset"]
        .iter()
        .any(|prefix| lowered.starts_with(prefix))
        || lowered.contains("sequence")
}

fn role_scores(
    path: &str,
    returns_annotation: &str,
    facts: &BodyFacts,
    is_function: bool,
) -> (RoleScores, Vec<String>) {
    let mut scores = Vec::new();
    let mut evidence = Vec::new();
    add_path_role_scores(&mut scores, &mut evidence, &path_parts(path));
    let calls = facts.calls.iter().cloned().collect::<BTreeSet<_>>();
    let features = facts.features.iter().cloned().collect::<BTreeSet<_>>();
    if is_function && (returns_annotation == "bool" || features.contains("predicate_return")) {
        add_role_score(
            &mut scores,
            &mut evidence,
            "predicate",
            ROLE_SCORE_STRONG,
            "predicate-shape",
        );
    }
    if is_function && collection_annotation(returns_annotation) {
        add_role_score(
            &mut scores,
            &mut evidence,
            "collector_inventory",
            ROLE_SCORE_STANDARD,
            "collection-annotation",
        );
    }
    add_common_body_role_scores(&mut scores, &mut evidence, &calls, &features);
    if is_function {
        add_function_body_role_scores(&mut scores, &mut evidence, &features);
    }
    if scores.is_empty() {
        add_role_score(
            &mut scores,
            &mut evidence,
            "general_helper",
            ROLE_SCORE_WEAK,
            "unclassified",
        );
    }
    (scores, evidence)
}

fn class_role_scores(
    path: &str,
    bases: &[String],
    decorators: &[String],
    annotated_fields: usize,
    facts: &BodyFacts,
) -> (RoleScores, Vec<String>) {
    let mut scores = Vec::new();
    let mut evidence = Vec::new();
    add_path_role_scores(&mut scores, &mut evidence, &path_parts(path));
    if bases
        .iter()
        .any(|base| base == "Protocol" || base.ends_with(".Protocol"))
    {
        add_role_score(
            &mut scores,
            &mut evidence,
            "protocol_interface",
            ROLE_SCORE_DOMINANT,
            "protocol-base",
        );
    }
    if bases.iter().any(|base| {
        base.ends_with("Exception")
            || base.ends_with("Error")
            || ["BaseException", "Exception"].contains(&base.as_str())
    }) {
        add_role_score(
            &mut scores,
            &mut evidence,
            "exception_type",
            ROLE_SCORE_BOUNDARY,
            "exception-base",
        );
    }
    if bases.iter().any(|base| {
        [
            "Answer",
            "Config",
            "Info",
            "Problem",
            "SolveConfig",
            "State",
        ]
        .iter()
        .any(|suffix| base.ends_with(suffix))
    }) {
        add_role_score(
            &mut scores,
            &mut evidence,
            "data_container",
            ROLE_SCORE_DOMINANT,
            "algorithm-data-container-base",
        );
    }
    if decorators
        .iter()
        .any(|decorator| decorator.ends_with("dataclass") || decorator.ends_with("define"))
    {
        add_role_score(
            &mut scores,
            &mut evidence,
            "data_container",
            ROLE_SCORE_DOMINANT,
            "data-class-decorator",
        );
    }
    if annotated_fields > 0 {
        add_role_score(
            &mut scores,
            &mut evidence,
            "data_container",
            ROLE_SCORE_STANDARD,
            "annotated-fields",
        );
    }
    let calls = facts.calls.iter().cloned().collect::<BTreeSet<_>>();
    let features = facts.features.iter().cloned().collect::<BTreeSet<_>>();
    add_common_body_role_scores(&mut scores, &mut evidence, &calls, &features);
    if features.contains("state_mutation") || features.contains("mutation_call") {
        add_role_score(
            &mut scores,
            &mut evidence,
            "state_holder",
            ROLE_SCORE_WEAK,
            "state-mutation",
        );
    }
    if scores.is_empty() {
        add_role_score(
            &mut scores,
            &mut evidence,
            "general_helper",
            ROLE_SCORE_WEAK,
            "unclassified",
        );
    }
    (scores, evidence)
}

fn is_candidate_symbol(kind: &str, name: &str, scope: &str, role: &str) -> bool {
    if name.starts_with("__") && name.ends_with("__") {
        return false;
    }
    if scope == "nested" {
        return true;
    }
    if name.starts_with('_') {
        return true;
    }
    if kind == "function" && PUBLIC_LOCAL_HELPER_ROLES.contains(&role) {
        return true;
    }
    kind == "class" && CLASS_LOCAL_HELPER_ROLES.contains(&role)
}

fn confidence(
    name: &str,
    scope: &str,
    scores: &RoleScores,
    facts: &BodyFacts,
    candidate: bool,
) -> f64 {
    if !candidate {
        return 0.0;
    }
    let mut score = BASE_HELPER_CONFIDENCE;
    if name.starts_with('_') {
        score += PRIVATE_NAME_CONFIDENCE_BONUS;
    }
    if scope == "nested" {
        score += NESTED_SCOPE_CONFIDENCE_BONUS;
    }
    if !scores.is_empty() {
        score += (max_role_score(scores) as f64 / ROLE_SCORE_CONFIDENCE_DIVISOR)
            .min(ROLE_SCORE_CONFIDENCE_CAP);
    }
    if !facts.calls.is_empty() {
        score += CALL_CONFIDENCE_BONUS;
    }
    if !facts.features.is_empty() {
        score += FEATURE_CONFIDENCE_BONUS;
    }
    (score.min(MAX_HELPER_CONFIDENCE) * 100.0).round() / 100.0
}

fn identifier_tokens(name: &str) -> Vec<String> {
    let stripped = name.trim_matches('_');
    let mut tokens = Vec::new();
    let mut part = Vec::new();
    let flush = |part: &mut Vec<char>, tokens: &mut Vec<String>| {
        if part.is_empty() {
            return;
        }
        let mut index = 0;
        while index < part.len() {
            let current = part[index];
            if current.is_ascii_uppercase() {
                let mut end = index + 1;
                while end < part.len() && part[end].is_ascii_uppercase() {
                    end += 1;
                }
                if end == part.len() {
                    tokens.push(
                        part[index..end]
                            .iter()
                            .copied()
                            .collect::<String>()
                            .to_ascii_lowercase(),
                    );
                    index = end;
                } else if part[end].is_ascii_lowercase() {
                    if end - index > 1 {
                        tokens.push(
                            part[index..end - 1]
                                .iter()
                                .copied()
                                .collect::<String>()
                                .to_ascii_lowercase(),
                        );
                        index = end - 1;
                    } else {
                        let start = index;
                        index = end + 1;
                        while index < part.len() && part[index].is_ascii_lowercase() {
                            index += 1;
                        }
                        tokens.push(
                            part[start..index]
                                .iter()
                                .copied()
                                .collect::<String>()
                                .to_ascii_lowercase(),
                        );
                    }
                } else {
                    index += 1;
                }
            } else if current.is_ascii_lowercase() || current.is_ascii_digit() {
                let start = index;
                let digits = current.is_ascii_digit();
                index += 1;
                while index < part.len()
                    && if digits {
                        part[index].is_ascii_digit()
                    } else {
                        part[index].is_ascii_lowercase()
                    }
                {
                    index += 1;
                }
                tokens.push(
                    part[start..index]
                        .iter()
                        .copied()
                        .collect::<String>()
                        .to_ascii_lowercase(),
                );
            } else {
                index += 1;
            }
        }
        part.clear();
    };
    for character in stripped.chars() {
        if character == '_' || !character.is_ascii_alphanumeric() {
            flush(&mut part, &mut tokens);
        } else {
            part.push(character);
        }
    }
    flush(&mut part, &mut tokens);
    tokens
}

fn role_tokens(role: &str) -> Vec<String> {
    let fixed = role_name_tokens(role);
    if !fixed.is_empty() {
        return fixed
            .iter()
            .map(|token| token.to_string())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
    }
    identifier_tokens(role)
        .into_iter()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn name_search_metadata(
    name: &str,
    role: &str,
) -> (Vec<String>, Vec<String>, Vec<String>, bool, String) {
    let name_parts = identifier_tokens(name);
    let role_parts = role_tokens(role);
    let name_set = name_parts.iter().cloned().collect::<BTreeSet<_>>();
    let matches = role_parts
        .iter()
        .filter(|token| name_set.contains(*token))
        .cloned()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    if !matches.is_empty() {
        let joined = matches.join(",");
        (
            name_parts,
            role_parts,
            matches,
            true,
            format!("role-token-match:{joined}"),
        )
    } else {
        (
            name_parts,
            role_parts,
            Vec::new(),
            false,
            format!("role-token-review:{role}"),
        )
    }
}

fn side_effect(feature: &str) -> bool {
    [
        "environment",
        "filesystem_mutation",
        "local_import",
        "logging",
        "mutation_call",
        "network",
        "state_mutation",
        "stdio",
        "subprocess",
        "write",
    ]
    .contains(&feature)
}

fn function_qualname_and_scope(parent_stack: &[String], name: &str) -> (String, String) {
    let mut parts = parent_stack.to_vec();
    parts.push(name.to_string());
    let qualname = parts.join(".");
    if let Some(parent) = parent_stack.last() {
        if parent.chars().next().is_some_and(char::is_uppercase) {
            (qualname, "method".into())
        } else {
            (qualname, "nested".into())
        }
    } else {
        (qualname, "module".into())
    }
}

fn is_interface_boundary(record: &FunctionRecord) -> bool {
    record.kind == "class" && record.role == "protocol_interface"
}

fn nested_candidate_rule(record: &FunctionRecord) -> String {
    let function_helper = record.kind == "function"
        && PUBLIC_LOCAL_HELPER_ROLES.contains(&record.role.as_str())
        && !LOW_SIGNAL_HELPER_ROLES.contains(&record.role.as_str());
    let class_helper = record.kind == "class" && CLASS_LOCAL_HELPER_ROLES.contains(&record.role.as_str());
    if function_helper || class_helper {
        format!("{}:nested-{}", record.domain, record.role)
    } else {
        String::new()
    }
}

fn local_symbol(record: &FunctionRecord) -> bool {
    LOCAL_SPECIALIZATIONS.contains(&record.specialization.as_str()) && record.incoming_count > 0
}

fn test_candidate_rule(record: &FunctionRecord, local: bool) -> String {
    let has_fixture = record
        .decorators
        .iter()
        .any(|decorator| decorator.rsplit('.').next() == Some("fixture"));
    if record.kind == "function" && record.name.starts_with("test_") {
        return String::new();
    }
    if record.visibility == "private" && local {
        return format!("test:private-local-{}", record.role);
    }
    if record.kind == "function" {
        if has_fixture {
            return "test:fixture-function".into();
        }
        if local && PUBLIC_LOCAL_HELPER_ROLES.contains(&record.role.as_str()) {
            return format!("test:local-{}", record.role);
        }
        return String::new();
    }
    if local {
        "test:local-test-class".into()
    } else {
        String::new()
    }
}

fn experiment_candidate_rule(record: &FunctionRecord, local: bool) -> String {
    if record.visibility == "private"
        && local
        && !LOW_SIGNAL_HELPER_ROLES.contains(&record.role.as_str())
    {
        return format!("experiment:private-local-{}", record.role);
    }
    if !local {
        return String::new();
    }
    if record.kind == "function" && PUBLIC_LOCAL_HELPER_ROLES.contains(&record.role.as_str()) {
        return format!("experiment:local-{}", record.role);
    }
    if record.kind == "class" && CLASS_LOCAL_HELPER_ROLES.contains(&record.role.as_str()) {
        return format!("experiment:local-{}", record.role);
    }
    String::new()
}

fn tooling_candidate_rule(record: &FunctionRecord, local: bool) -> String {
    if record.visibility == "private"
        && local
        && !LOW_SIGNAL_HELPER_ROLES.contains(&record.role.as_str())
    {
        return format!("tooling:private-local-{}", record.role);
    }
    if !local {
        return String::new();
    }
    if record.kind == "function" && PUBLIC_LOCAL_HELPER_ROLES.contains(&record.role.as_str()) {
        return format!("tooling:local-{}", record.role);
    }
    if record.kind == "class" && CLASS_LOCAL_HELPER_ROLES.contains(&record.role.as_str()) {
        return format!("tooling:local-{}", record.role);
    }
    String::new()
}

fn main_candidate_rule(record: &FunctionRecord, local: bool) -> String {
    if record.visibility == "private"
        && local
        && !LOW_SIGNAL_HELPER_ROLES.contains(&record.role.as_str())
    {
        format!("main:private-local-{}", record.role)
    } else {
        String::new()
    }
}

fn candidate_rule(record: &FunctionRecord) -> String {
    if record.name.starts_with("__") && record.name.ends_with("__") || is_interface_boundary(record)
    {
        return String::new();
    }
    if record.scope == "nested" {
        return nested_candidate_rule(record);
    }
    let local = local_symbol(record);
    match record.domain.as_str() {
        "test" => test_candidate_rule(record, local),
        "experiment" => experiment_candidate_rule(record, local),
        "tooling" => tooling_candidate_rule(record, local),
        _ => main_candidate_rule(record, local),
    }
}

fn shared_private_numeric_contract(record: &FunctionRecord) -> bool {
    record.kind == "function"
        && record.incoming_count > LOCAL_CALLER_CLUSTER_LIMIT
        && (record.role == "numeric_kernel"
            || record
                .secondary_roles
                .iter()
                .any(|role| role == "numeric_kernel"))
        && !record.redundant_helper
}

fn design_judgment_rule(record: &FunctionRecord) -> String {
    if record.name.starts_with("__") && record.name.ends_with("__") || is_interface_boundary(record)
    {
        return String::new();
    }
    let local = local_symbol(record);
    match record.domain.as_str() {
        "main" => {
            if local && record.visibility == "public" {
                if record.kind == "function"
                    && PUBLIC_LOCAL_HELPER_ROLES.contains(&record.role.as_str())
                {
                    return format!("main:public-local-{}", record.role);
                }
                if record.kind == "class"
                    && CLASS_LOCAL_HELPER_ROLES.contains(&record.role.as_str())
                {
                    return format!("main:public-local-{}", record.role);
                }
            }
            if local && LOW_SIGNAL_HELPER_ROLES.contains(&record.role.as_str()) {
                return format!("main:low-signal-local-{}", record.role);
            }
            if record.visibility == "private"
                && record.incoming_count > 0
                && !shared_private_numeric_contract(record)
            {
                return format!("main:shared-private-{}", record.role);
            }
            String::new()
        }
        "experiment" | "test" | "tooling" => {
            if record.domain == "test"
                && record.kind == "function"
                && record.name.starts_with("test_")
            {
                return String::new();
            }
            if local && ["general_helper", "numeric_kernel"].contains(&record.role.as_str()) {
                format!("{}:low-signal-local-{}", record.domain, record.role)
            } else {
                String::new()
            }
        }
        _ => String::new(),
    }
}

fn verdict(record: &FunctionRecord) -> &'static str {
    if record.redundant_helper {
        "redundant_helper"
    } else if record.helper_candidate {
        "auto_helper"
    } else if record.needs_user_judgment {
        "needs_user_judgment"
    } else {
        "not_helper"
    }
}

fn should_report_name_gap(record: &FunctionRecord) -> bool {
    !record.searchable_name
        && (record.helper_candidate || record.needs_user_judgment || record.redundant_helper)
}

fn function_implementation_signature(body: &[ast::Stmt], arguments: &ast::Arguments) -> String {
    let normalized_body = body_without_docstring(body);
    if normalized_body.is_empty() {
        return String::new();
    }
    ast_dump_normalized_module_body(normalized_body, &function_parameters(arguments))
}

struct DefinitionCollector<'a> {
    relative_path: String,
    source: &'a str,
    stack: Vec<String>,
    records: Vec<FunctionRecord>,
}

impl DefinitionCollector<'_> {
    fn record_function(&mut self, name: &str, node: &ast::StmtFunctionDef, is_async: bool) {
        let (qualname, scope) = function_qualname_and_scope(&self.stack, name);
        let facts = function_body_facts(self.source, node);
        let returns_annotation = node
            .returns
            .as_deref()
            .map(ToString::to_string)
            .unwrap_or_default();
        let (scores, mut evidence) =
            role_scores(&self.relative_path, &returns_annotation, &facts, true);
        let roles = ordered_roles(&scores);
        let role = roles
            .first()
            .cloned()
            .unwrap_or_else(|| "general_helper".into());
        let (
            name_tokens,
            expected_name_tokens,
            matched_name_tokens,
            searchable_name,
            name_search_rule,
        ) = name_search_metadata(name, &role);
        let candidate = is_candidate_symbol("function", name, &scope, &role);
        let decorators = node
            .decorator_list
            .iter()
            .map(dotted_name)
            .filter(|name| !name.is_empty())
            .collect::<Vec<_>>();
        if is_async {
            evidence.push("async:function".into());
        }
        let signature = function_implementation_signature(&node.body, &node.args);
        let call_sites = facts
            .call_locations
            .iter()
            .map(|(call, line)| format!("{call}@{line}"))
            .collect();
        let features = facts.features.clone();
        let calls = facts
            .calls
            .iter()
            .cloned()
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        let line = node_line(self.source, node);
        let end = node.end().to_usize();
        let end_line = line_at_offset(self.source, end.saturating_sub(1));
        let record_confidence = confidence(name, &scope, &scores, &facts, candidate);
        self.records.push(FunctionRecord {
            path: self.relative_path.clone(),
            line,
            end_line,
            kind: "function".into(),
            domain: path_domain(&self.relative_path),
            name: name.to_string(),
            qualname,
            scope,
            visibility: if name.starts_with('_') {
                "private"
            } else {
                "public"
            }
            .into(),
            role,
            secondary_roles: roles
                .into_iter()
                .skip(1)
                .take(SECONDARY_ROLE_SLICE_STOP - 1)
                .collect(),
            name_tokens,
            role_name_tokens: expected_name_tokens,
            matched_role_name_tokens: matched_name_tokens,
            searchable_name,
            name_search_rule,
            confidence: record_confidence,
            helper_candidate: candidate,
            candidate_rule: String::new(),
            needs_user_judgment: false,
            judgment_rule: String::new(),
            redundant_helper: false,
            redundancy_rule: String::new(),
            redundant_with: Vec::new(),
            implementation_signature: signature,
            incoming_count: 0,
            incoming_callers: Vec::new(),
            incoming_call_sites: Vec::new(),
            outgoing_internal: Vec::new(),
            outgoing_call_sites: call_sites,
            specialized_helper: false,
            specialization: "not_evaluated".into(),
            side_effects: features
                .iter()
                .filter(|feature| side_effect(feature))
                .cloned()
                .collect(),
            features,
            calls,
            args: function_args(&node.args),
            bases: Vec::new(),
            method_count: 0,
            public_method_count: 0,
            decorators,
            returns_annotation,
            doc_summary: doc_summary(docstring(&node.body).as_deref()),
            evidence,
        });
    }

    fn record_class(&mut self, node: &ast::StmtClassDef) {
        let mut qual_parts = self.stack.clone();
        qual_parts.push(node.name.to_string());
        let qualname = qual_parts.join(".");
        let scope = if self.stack.is_empty() {
            "module"
        } else {
            "nested"
        }
        .to_string();
        let facts = class_body_facts(self.source, node);
        let bases = node
            .bases
            .iter()
            .map(dotted_name)
            .filter(|name| !name.is_empty())
            .collect::<Vec<_>>();
        let decorators = node
            .decorator_list
            .iter()
            .map(dotted_name)
            .filter(|name| !name.is_empty())
            .collect::<Vec<_>>();
        let method_names = node
            .body
            .iter()
            .filter_map(|statement| match statement {
                ast::Stmt::FunctionDef(method) => Some(method.name.to_string()),
                ast::Stmt::AsyncFunctionDef(method) => Some(method.name.to_string()),
                _ => None,
            })
            .collect::<Vec<_>>();
        let annotated_field_count = node
            .body
            .iter()
            .filter(|statement| matches!(statement, ast::Stmt::AnnAssign(_) | ast::Stmt::Assign(_)))
            .count();
        let (scores, evidence) = class_role_scores(
            &self.relative_path,
            &bases,
            &decorators,
            annotated_field_count,
            &facts,
        );
        let roles = ordered_roles(&scores);
        let role = roles
            .first()
            .cloned()
            .unwrap_or_else(|| "general_helper".into());
        let name = node.name.to_string();
        let (
            name_tokens,
            expected_name_tokens,
            matched_name_tokens,
            searchable_name,
            name_search_rule,
        ) = name_search_metadata(&name, &role);
        let candidate = is_candidate_symbol("class", &name, &scope, &role);
        let call_sites = facts
            .call_locations
            .iter()
            .map(|(call, line)| format!("{call}@{line}"))
            .collect();
        let features = facts.features.clone();
        let calls = facts
            .calls
            .iter()
            .cloned()
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        let line = node_line(self.source, node);
        let end_line = line_at_offset(self.source, node.end().to_usize().saturating_sub(1));
        let record_confidence = confidence(&name, &scope, &scores, &facts, candidate);
        self.records.push(FunctionRecord {
            path: self.relative_path.clone(),
            line,
            end_line,
            kind: "class".into(),
            domain: path_domain(&self.relative_path),
            name: name.clone(),
            qualname,
            scope,
            visibility: if name.starts_with('_') {
                "private"
            } else {
                "public"
            }
            .into(),
            role,
            secondary_roles: roles
                .into_iter()
                .skip(1)
                .take(SECONDARY_ROLE_SLICE_STOP - 1)
                .collect(),
            name_tokens,
            role_name_tokens: expected_name_tokens,
            matched_role_name_tokens: matched_name_tokens,
            searchable_name,
            name_search_rule,
            confidence: record_confidence,
            helper_candidate: candidate,
            candidate_rule: String::new(),
            needs_user_judgment: false,
            judgment_rule: String::new(),
            redundant_helper: false,
            redundancy_rule: String::new(),
            redundant_with: Vec::new(),
            implementation_signature: String::new(),
            incoming_count: 0,
            incoming_callers: Vec::new(),
            incoming_call_sites: Vec::new(),
            outgoing_internal: Vec::new(),
            outgoing_call_sites: call_sites,
            specialized_helper: false,
            specialization: "not_evaluated".into(),
            side_effects: features
                .iter()
                .filter(|feature| side_effect(feature))
                .cloned()
                .collect(),
            features,
            calls,
            args: Vec::new(),
            bases,
            method_count: method_names.len(),
            public_method_count: method_names
                .iter()
                .filter(|name| !name.starts_with('_'))
                .count(),
            decorators,
            returns_annotation: String::new(),
            doc_summary: doc_summary(docstring(&node.body).as_deref()),
            evidence,
        });
    }
}

impl Visitor for DefinitionCollector<'_> {
    fn visit_stmt_class_def(&mut self, node: ast::StmtClassDef) {
        self.record_class(&node);
        self.stack.push(node.name.to_string());
        self.generic_visit_stmt_class_def(node);
        self.stack.pop();
    }

    fn visit_stmt_function_def(&mut self, node: ast::StmtFunctionDef) {
        let name = node.name.to_string();
        self.record_function(&name, &node, false);
        self.stack.push(name);
        self.generic_visit_stmt_function_def(node);
        self.stack.pop();
    }

    fn visit_stmt_async_function_def(&mut self, node: ast::StmtAsyncFunctionDef) {
        let name = node.name.to_string();
        // Reuse the same field contract while retaining async evidence.
        let (qualname, scope) = function_qualname_and_scope(&self.stack, &name);
        let facts = async_function_body_facts(self.source, &node);
        let returns_annotation = node
            .returns
            .as_deref()
            .map(ToString::to_string)
            .unwrap_or_default();
        let (scores, mut evidence) =
            role_scores(&self.relative_path, &returns_annotation, &facts, true);
        let roles = ordered_roles(&scores);
        let role = roles
            .first()
            .cloned()
            .unwrap_or_else(|| "general_helper".into());
        let (
            name_tokens,
            expected_name_tokens,
            matched_name_tokens,
            searchable_name,
            name_search_rule,
        ) = name_search_metadata(&name, &role);
        let candidate = is_candidate_symbol("function", &name, &scope, &role);
        let decorators = node
            .decorator_list
            .iter()
            .map(dotted_name)
            .filter(|name| !name.is_empty())
            .collect::<Vec<_>>();
        evidence.push("async:function".into());
        let features = facts.features.clone();
        let calls = facts
            .calls
            .iter()
            .cloned()
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        let call_sites = facts
            .call_locations
            .iter()
            .map(|(call, line)| format!("{call}@{line}"))
            .collect();
        let line = node_line(self.source, &node);
        let end_line = line_at_offset(self.source, node.end().to_usize().saturating_sub(1));
        let record_confidence = confidence(&name, &scope, &scores, &facts, candidate);
        self.records.push(FunctionRecord {
            path: self.relative_path.clone(),
            line,
            end_line,
            kind: "function".into(),
            domain: path_domain(&self.relative_path),
            name: name.clone(),
            qualname,
            scope,
            visibility: if name.starts_with('_') {
                "private"
            } else {
                "public"
            }
            .into(),
            role,
            secondary_roles: roles
                .into_iter()
                .skip(1)
                .take(SECONDARY_ROLE_SLICE_STOP - 1)
                .collect(),
            name_tokens,
            role_name_tokens: expected_name_tokens,
            matched_role_name_tokens: matched_name_tokens,
            searchable_name,
            name_search_rule,
            confidence: record_confidence,
            helper_candidate: candidate,
            candidate_rule: String::new(),
            needs_user_judgment: false,
            judgment_rule: String::new(),
            redundant_helper: false,
            redundancy_rule: String::new(),
            redundant_with: Vec::new(),
            implementation_signature: function_implementation_signature(&node.body, &node.args),
            incoming_count: 0,
            incoming_callers: Vec::new(),
            incoming_call_sites: Vec::new(),
            outgoing_internal: Vec::new(),
            outgoing_call_sites: call_sites,
            specialized_helper: false,
            specialization: "not_evaluated".into(),
            side_effects: features
                .iter()
                .filter(|feature| side_effect(feature))
                .cloned()
                .collect(),
            features,
            calls,
            args: function_args(&node.args),
            bases: Vec::new(),
            method_count: 0,
            public_method_count: 0,
            decorators,
            returns_annotation,
            doc_summary: doc_summary(docstring(&node.body).as_deref()),
            evidence,
        });
        self.stack.push(name);
        self.generic_visit_stmt_async_function_def(node);
        self.stack.pop();
    }
}

fn analyze_source(root: &Path, path: &Path, source: &str) -> Vec<FunctionRecord> {
    let source = normalize_python_newlines(source);
    let source_path = path.to_string_lossy();
    let Ok(suite) = ast::Suite::parse(&source, source_path.as_ref()) else {
        return Vec::new();
    };
    let mut collector = DefinitionCollector {
        relative_path: stable_relative(root, path),
        source: &source,
        stack: Vec::new(),
        records: Vec::new(),
    };
    for statement in suite {
        collector.visit_stmt(statement);
    }
    collector.records
}

fn analyze_file(root: &Path, path: &Path) -> Vec<FunctionRecord> {
    match fs::read_to_string(path) {
        Ok(source) => analyze_source(root, path, &source),
        Err(_) => Vec::new(),
    }
}

struct CallGraphMaps {
    by_name: HashMap<String, Vec<usize>>,
    by_qualname: HashMap<String, usize>,
}

#[derive(Default)]
struct CallGraphEdges {
    incoming_sites: HashMap<usize, BTreeSet<String>>,
    incoming_callers: HashMap<usize, BTreeSet<String>>,
    outgoing: HashMap<usize, BTreeSet<String>>,
}

fn call_graph_maps(records: &[FunctionRecord]) -> CallGraphMaps {
    let mut by_name: HashMap<String, Vec<usize>> = HashMap::new();
    let mut by_qualname = HashMap::new();
    for (index, record) in records.iter().enumerate() {
        by_name.entry(record.name.clone()).or_default().push(index);
        let _ = by_qualname.insert(record.qualname.clone(), index);
    }
    CallGraphMaps {
        by_name,
        by_qualname,
    }
}

fn enclosing_class(qualname: &str) -> String {
    let mut parts = qualname.split('.').collect::<Vec<_>>();
    let _ = parts.pop();
    parts
        .into_iter()
        .rev()
        .find(|part| part.chars().next().is_some_and(char::is_uppercase))
        .unwrap_or("")
        .to_string()
}

fn internal_call_candidates(
    records: &[FunctionRecord],
    maps: &CallGraphMaps,
    caller: usize,
    call: &str,
) -> Vec<usize> {
    if !call.contains('.') {
        return maps.by_name.get(call).cloned().unwrap_or_default();
    }
    if let Some(index) = maps.by_qualname.get(call) {
        return vec![*index];
    }
    if call.starts_with("self.") || call.starts_with("cls.") {
        let method_name = call.split_once('.').map(|(_, suffix)| suffix).unwrap_or("");
        if method_name.contains('.') {
            return Vec::new();
        }
        let class_name = enclosing_class(&records[caller].qualname);
        if class_name.is_empty() {
            return Vec::new();
        }
        return maps
            .by_name
            .get(method_name)
            .into_iter()
            .flatten()
            .copied()
            .filter(|index| {
                records[*index].scope == "method"
                    && enclosing_class(&records[*index].qualname) == class_name
            })
            .collect();
    }
    Vec::new()
}

fn specialization(record: &FunctionRecord) -> (bool, String) {
    if record.scope == "nested" {
        return (true, "nested_local_helper".into());
    }
    if record.incoming_call_sites.is_empty() {
        return (false, "no_internal_call_sites".into());
    }
    if record.incoming_callers.len() == 1 {
        return (true, "single_caller_helper".into());
    }
    let caller_files = record
        .incoming_callers
        .iter()
        .map(|caller| {
            caller
                .split_once(':')
                .map(|(path, _)| path)
                .unwrap_or(caller)
        })
        .collect::<BTreeSet<_>>();
    if caller_files.len() == 1 && record.incoming_callers.len() <= LOCAL_CALLER_CLUSTER_LIMIT {
        return (true, "file_local_helper_cluster".into());
    }
    (false, "shared_helper".into())
}

fn implementation_duplicate_groups(records: &[FunctionRecord]) -> HashMap<String, Vec<usize>> {
    let mut signatures: BTreeMap<String, Vec<usize>> = BTreeMap::new();
    for (index, record) in records.iter().enumerate() {
        if record.kind == "function"
            && !record.implementation_signature.is_empty()
            && record.scope != "method"
            && record.domain != "test"
        {
            signatures
                .entry(record.implementation_signature.clone())
                .or_default()
                .push(index);
        }
    }
    signatures
        .into_iter()
        .filter(|(_, records)| records.len() > 1)
        .collect()
}

fn redundancy_eligible_symbol(record: &FunctionRecord) -> bool {
    if record.scope == "nested" || record.visibility == "private" {
        return true;
    }
    local_symbol(record)
        && record.incoming_count > 0
        && PUBLIC_LOCAL_HELPER_ROLES.contains(&record.role.as_str())
}

fn pass_through_redundancy_rule(record: &FunctionRecord, shape: &str) -> String {
    if !record.outgoing_internal.is_empty() {
        format!("pass-through-{shape}-internal")
    } else {
        format!("pass-through-{shape}-external")
    }
}

fn redundancy_rule(record: &FunctionRecord) -> String {
    if record.kind != "function" || !redundancy_eligible_symbol(record) {
        return String::new();
    }
    let features = record
        .features
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let simple = features.contains("single_statement_body");
    if simple && features.contains("identity_return") {
        return "identity-return".into();
    }
    if simple && features.contains("pass_through_call_return") {
        return pass_through_redundancy_rule(record, "return");
    }
    if simple && features.contains("pass_through_call_statement") {
        return pass_through_redundancy_rule(record, "statement");
    }
    if !record.redundant_with.is_empty() {
        return "duplicate-implementation".into();
    }
    String::new()
}

fn attach_verdict(record: &mut FunctionRecord) {
    let rule = candidate_rule(record);
    let judgment = if record.redundant_helper && rule.is_empty() {
        format!("{}:{}", record.domain, record.redundancy_rule)
    } else if !rule.is_empty() {
        String::new()
    } else {
        design_judgment_rule(record)
    };
    record.helper_candidate = !rule.is_empty();
    record.candidate_rule = rule.clone();
    record.needs_user_judgment = !judgment.is_empty();
    record.judgment_rule = judgment.clone();
    if !rule.is_empty() {
        record.evidence.insert(0, format!("candidate-rule:{rule}"));
        if record.confidence == 0.0 {
            record.confidence = DEFAULT_HALF_CONFIDENCE;
        }
    } else if !judgment.is_empty() {
        record
            .evidence
            .insert(0, format!("judgment-rule:{judgment}"));
        if record.confidence == 0.0 {
            record.confidence = JUDGMENT_CONFIDENCE;
        }
    } else {
        record.confidence = 0.0;
        record.specialized_helper = false;
        record.specialization = "not_helper_candidate".into();
    }
    if record.helper_candidate && record.visibility == "private" && record.incoming_count == 0 {
        record.evidence.push("usage:no-internal-callers".into());
    }
    if record.specialized_helper {
        record
            .evidence
            .push(format!("usage:{}", record.specialization));
    }
    if record.redundant_helper {
        record
            .evidence
            .push(format!("redundant:{}", record.redundancy_rule));
        if !record.redundant_with.is_empty() {
            record.evidence.push(format!(
                "redundant-with:{}",
                record
                    .redundant_with
                    .iter()
                    .take(REDUNDANT_WITH_EVIDENCE_LIMIT)
                    .cloned()
                    .collect::<Vec<_>>()
                    .join(";")
            ));
        }
    }
    if record.helper_candidate || record.needs_user_judgment || record.redundant_helper {
        record
            .evidence
            .push(format!("name-search:{}", record.name_search_rule));
    }
}

fn apply_call_graph(records: &mut [FunctionRecord]) {
    let maps = call_graph_maps(records);
    let mut edges = CallGraphEdges::default();
    for (caller_index, record) in records.iter().enumerate() {
        let mut outgoing = BTreeSet::new();
        for call_site in &record.outgoing_call_sites {
            let Some((call, line_text)) = call_site.rsplit_once('@') else {
                continue;
            };
            let line = line_text.parse::<usize>().unwrap_or(record.line);
            let candidates = internal_call_candidates(records, &maps, caller_index, call);
            for candidate_index in &candidates {
                if *candidate_index == caller_index {
                    continue;
                }
                if records[*candidate_index].path == record.path || candidates.len() == 1 {
                    outgoing.insert(records[*candidate_index].qualname.clone());
                    edges
                        .incoming_sites
                        .entry(*candidate_index)
                        .or_default()
                        .insert(format!("{}:{line}:{}", record.path, record.qualname));
                    edges
                        .incoming_callers
                        .entry(*candidate_index)
                        .or_default()
                        .insert(format!("{}:{}", record.path, record.qualname));
                }
            }
        }
        let _ = edges.outgoing.insert(caller_index, outgoing);
    }
    for (index, record) in records.iter_mut().enumerate() {
        record.incoming_call_sites = edges
            .incoming_sites
            .get(&index)
            .map(|values| values.iter().cloned().collect())
            .unwrap_or_default();
        record.incoming_callers = edges
            .incoming_callers
            .get(&index)
            .map(|values| values.iter().cloned().collect())
            .unwrap_or_default();
        record.incoming_count = record.incoming_call_sites.len();
        record.outgoing_internal = edges
            .outgoing
            .get(&index)
            .map(|values| values.iter().cloned().collect())
            .unwrap_or_default();
        let (specialized_helper, specialization) = specialization(record);
        record.specialized_helper = specialized_helper;
        record.specialization = specialization;
    }
    let duplicate_groups = implementation_duplicate_groups(records);
    let qualnames = records
        .iter()
        .map(|record| record.qualname.clone())
        .collect::<Vec<_>>();
    for (index, record) in records.iter_mut().enumerate() {
        if let Some(group) = duplicate_groups.get(&record.implementation_signature) {
            record.redundant_with = group
                .iter()
                .filter(|peer| **peer != index)
                .map(|peer| qualnames[*peer].clone())
                .collect();
        }
        let rule = redundancy_rule(record);
        record.redundant_helper = !rule.is_empty();
        record.redundancy_rule = rule;
    }
    for record in records.iter_mut() {
        attach_verdict(record);
    }
}

fn inventory_files(root: &Path, options: &Options) -> (Vec<PathBuf>, BTreeSet<String>) {
    if !options.changed_only {
        return (
            iter_python_files(
                root,
                &options.paths,
                options.include_vendor,
                options.include_hidden,
                options.include_pyi,
            ),
            BTreeSet::new(),
        );
    }
    let changed = filtered_changed_python_files(root, options);
    let report_paths = changed
        .iter()
        .map(|path| stable_relative(root, path))
        .collect::<BTreeSet<_>>();
    if changed.is_empty() {
        return (Vec::new(), report_paths);
    }
    (
        iter_python_files(
            root,
            &[],
            options.include_vendor,
            options.include_hidden,
            options.include_pyi,
        ),
        report_paths,
    )
}

fn baseline_inventory_records(
    root: &Path,
    files: &[PathBuf],
    reference: &str,
) -> Vec<FunctionRecord> {
    if reference.is_empty() {
        return Vec::new();
    }
    let renamed_paths = git_renamed_paths(root, reference);
    let mut records = Vec::new();
    for path in files {
        let relative = stable_relative(root, path);
        let source = git_ref_text(root, reference, &relative).or_else(|| {
            renamed_paths
                .get(&relative)
                .and_then(|previous| git_ref_text(root, reference, previous))
        });
        if let Some(source) = source {
            records.extend(analyze_source(root, path, &source));
        }
    }
    apply_call_graph(&mut records);
    records
}

fn select_records(
    records: &[FunctionRecord],
    options: &Options,
    report_paths: &BTreeSet<String>,
) -> Vec<FunctionRecord> {
    let include_auto = !options.only_user_judgment;
    let include_judgment = !options.only_auto_helpers;
    let mut selected = records
        .iter()
        .filter(|record| {
            options.all_functions
                || (include_auto && record.helper_candidate)
                || (include_judgment && record.needs_user_judgment)
        })
        .filter(|record| !options.only_name_gaps || should_report_name_gap(record))
        .filter(|record| record.confidence >= options.min_confidence)
        .filter(|record| report_paths.is_empty() || report_paths.contains(&record.path))
        .cloned()
        .collect::<Vec<_>>();
    selected.sort_by(|left, right| {
        (&left.path, left.line, &left.qualname).cmp(&(&right.path, right.line, &right.qualname))
    });
    selected
}

fn record_key(record: &FunctionRecord) -> (String, String, String, String, String, String, String) {
    (
        record.path.clone(),
        record.kind.clone(),
        record.qualname.clone(),
        verdict(record).to_string(),
        record.role.clone(),
        record.candidate_rule.clone(),
        record.judgment_rule.clone(),
    )
}

fn build_inventory(root: &Path, options: &Options) -> Inventory {
    let (files, report_paths) = inventory_files(root, options);
    let baseline_records = baseline_inventory_records(root, &files, &options.baseline_ref);
    let mut all_records = Vec::new();
    for path in &files {
        all_records.extend(analyze_file(root, path));
    }
    apply_call_graph(&mut all_records);
    let mut selected = select_records(&all_records, options, &report_paths);
    let baseline_selected = select_records(&baseline_records, options, &report_paths);
    let baseline_keys = baseline_selected
        .iter()
        .map(record_key)
        .collect::<BTreeSet<_>>();
    let before_filter = selected.len();
    if !options.baseline_ref.is_empty() {
        selected.retain(|record| !baseline_keys.contains(&record_key(record)));
    }
    selected.sort_by(|left, right| {
        (&left.path, left.line, &left.qualname).cmp(&(&right.path, right.line, &right.qualname))
    });
    let mut role_counts = BTreeMap::<String, usize>::new();
    let mut verdict_counts = BTreeMap::<String, usize>::new();
    for record in &selected {
        *role_counts.entry(record.role.clone()).or_default() += 1;
        *verdict_counts
            .entry(verdict(record).to_string())
            .or_default() += 1;
    }
    Inventory {
        root: root.to_string_lossy().replace('\\', "/"),
        changed_only: options.changed_only,
        baseline_ref: options.baseline_ref.clone(),
        baseline_symbols_seen: baseline_records.len(),
        baseline_filtered: before_filter.saturating_sub(selected.len()),
        files_scanned: files.len(),
        symbols_seen: all_records.len(),
        functions_seen: all_records
            .iter()
            .filter(|record| record.kind == "function")
            .count(),
        classes_seen: all_records
            .iter()
            .filter(|record| record.kind == "class")
            .count(),
        symbols_reported: selected.len(),
        helpers_reported: selected
            .iter()
            .filter(|record| record.helper_candidate)
            .count(),
        judgment_required_reported: selected
            .iter()
            .filter(|record| record.needs_user_judgment)
            .count(),
        name_gaps_reported: selected
            .iter()
            .filter(|record| should_report_name_gap(record))
            .count(),
        role_counts,
        verdict_counts,
        records: selected,
    }
}

fn git_sha(root: &Path) -> String {
    let Some(output) = git_output(root, &["rev-parse", "--verify", "HEAD"]) else {
        return String::new();
    };
    if !output.status.success() {
        return String::new();
    }
    String::from_utf8_lossy(&output.stdout).trim().to_string()
}

fn join_or_none(values: &[String], separator: &str) -> String {
    if values.is_empty() {
        "none".into()
    } else {
        values.join(separator)
    }
}

fn render_text(inventory: &Inventory) -> String {
    let mut lines = Vec::new();
    for record in &inventory.records {
        let side_effects = join_or_none(&record.side_effects, ",");
        let features = join_or_none(&record.features, ",");
        let outgoing = join_or_none(&record.outgoing_internal, ",");
        let evidence = join_or_none(
            &record
                .evidence
                .iter()
                .take(EVIDENCE_RENDER_LIMIT)
                .cloned()
                .collect::<Vec<_>>(),
            ",",
        );
        let matched_name_tokens = join_or_none(&record.matched_role_name_tokens, ",");
        let redundant_with = join_or_none(&record.redundant_with, ";");
        let callers = join_or_none(&record.incoming_callers, ";");
        lines.push(format!(
            "SYMBOL={}:{}:{} kind={} domain={} verdict={} role={} confidence={:.2} searchable_name={} name_search_rule={} matched_name_tokens={} candidate_rule={} judgment_rule={} redundant={} redundancy_rule={} redundant_with={} scope={} visibility={} incoming={} outgoing={} specialization={} callers={} side_effects={} features={} evidence={}",
            record.path,
            record.line,
            record.qualname,
            record.kind,
            record.domain,
            verdict(record),
            record.role,
            record.confidence,
            record.searchable_name.to_string().to_lowercase(),
            record.name_search_rule,
            matched_name_tokens,
            if record.candidate_rule.is_empty() { "none" } else { &record.candidate_rule },
            if record.judgment_rule.is_empty() { "none" } else { &record.judgment_rule },
            record.redundant_helper.to_string().to_lowercase(),
            if record.redundancy_rule.is_empty() { "none" } else { &record.redundancy_rule },
            redundant_with,
            record.scope,
            record.visibility,
            record.incoming_count,
            outgoing,
            record.specialization,
            callers,
            side_effects,
            features,
            evidence,
        ));
    }
    let role_summary = inventory
        .role_counts
        .iter()
        .map(|(role, count)| format!("{role}:{count}"))
        .collect::<Vec<_>>()
        .join(",");
    let verdict_summary = inventory
        .verdict_counts
        .iter()
        .map(|(name, count)| format!("{name}:{count}"))
        .collect::<Vec<_>>()
        .join(",");
    lines.extend([
        format!("HELPER_INVENTORY_FILES={}", inventory.files_scanned),
        format!("HELPER_INVENTORY_SYMBOLS={}", inventory.symbols_seen),
        format!("HELPER_INVENTORY_FUNCTIONS={}", inventory.functions_seen),
        format!("HELPER_INVENTORY_CLASSES={}", inventory.classes_seen),
        format!(
            "HELPER_INVENTORY_SYMBOLS_REPORTED={}",
            inventory.symbols_reported
        ),
        format!("HELPER_INVENTORY_HELPERS={}", inventory.helpers_reported),
        format!(
            "HELPER_INVENTORY_JUDGMENT_REQUIRED={}",
            inventory.judgment_required_reported
        ),
        format!(
            "HELPER_INVENTORY_NAME_GAPS={}",
            inventory.name_gaps_reported
        ),
        format!(
            "HELPER_INVENTORY_CHANGED_ONLY={}",
            inventory.changed_only.to_string().to_lowercase()
        ),
        format!(
            "HELPER_INVENTORY_BASELINE_REF={}",
            if inventory.baseline_ref.is_empty() {
                "none"
            } else {
                &inventory.baseline_ref
            }
        ),
        format!(
            "HELPER_INVENTORY_BASELINE_SYMBOLS={}",
            inventory.baseline_symbols_seen
        ),
        format!(
            "HELPER_INVENTORY_BASELINE_FILTERED={}",
            inventory.baseline_filtered
        ),
        format!("HELPER_INVENTORY_ROLES={role_summary}"),
        format!("HELPER_INVENTORY_VERDICTS={verdict_summary}"),
        "HELPER_INVENTORY=pass".into(),
    ]);
    format!("{}\n", lines.join("\n"))
}

fn markdown_cell(value: &str) -> String {
    value.replace('|', "\\|").replace('\n', " ")
}

fn render_markdown(inventory: &Inventory) -> String {
    let summary_rows = vec![
        ("files scanned", inventory.files_scanned.to_string()),
        ("symbols seen", inventory.symbols_seen.to_string()),
        ("functions seen", inventory.functions_seen.to_string()),
        ("classes seen", inventory.classes_seen.to_string()),
        ("symbols reported", inventory.symbols_reported.to_string()),
        (
            "auto helpers reported",
            inventory.helpers_reported.to_string(),
        ),
        (
            "user judgment required",
            inventory.judgment_required_reported.to_string(),
        ),
        (
            "name gaps reported",
            inventory.name_gaps_reported.to_string(),
        ),
        (
            "changed only",
            inventory.changed_only.to_string().to_lowercase(),
        ),
        (
            "baseline ref",
            if inventory.baseline_ref.is_empty() {
                "none".into()
            } else {
                inventory.baseline_ref.clone()
            },
        ),
        (
            "baseline symbols seen",
            inventory.baseline_symbols_seen.to_string(),
        ),
        ("baseline filtered", inventory.baseline_filtered.to_string()),
    ];
    let verdict_rows = if inventory.verdict_counts.is_empty() {
        vec![("none".to_string(), 0)]
    } else {
        inventory
            .verdict_counts
            .iter()
            .map(|(name, count)| (name.clone(), *count))
            .collect()
    };
    let role_rows = if inventory.role_counts.is_empty() {
        vec![("none".to_string(), 0)]
    } else {
        inventory
            .role_counts
            .iter()
            .map(|(name, count)| (name.clone(), *count))
            .collect()
    };
    let mut lines = vec![
        "# Helper Symbol Inventory".to_string(),
        String::new(),
        "## Summary".into(),
        String::new(),
        "| Metric | Value |".into(),
        "| --- | --- |".into(),
    ];
    for (metric, value) in summary_rows {
        lines.push(format!(
            "| {} | {} |",
            markdown_cell(metric),
            markdown_cell(&value)
        ));
    }
    lines.extend([
        String::new(),
        "## Verdict Counts".into(),
        String::new(),
        "| Verdict | Count |".into(),
        "| --- | --- |".into(),
    ]);
    for (name, count) in verdict_rows {
        lines.push(format!("| {} | {} |", markdown_cell(&name), count));
    }
    lines.extend([
        String::new(),
        "## Role Counts".into(),
        String::new(),
        "| Role | Count |".into(),
        "| --- | --- |".into(),
    ]);
    for (name, count) in role_rows {
        lines.push(format!("| {} | {} |", markdown_cell(&name), count));
    }
    lines.extend([
        String::new(),
        "## Records".into(),
        String::new(),
        "| Path | Line | Kind | Domain | Verdict | Helper | Role | Searchable name | Name search rule | Matched name tokens | Candidate rule | Judgment rule | Redundancy rule | Redundant with | Confidence | Incoming | Specialization | Side effects | Features | Evidence |".into(),
        "| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- | --- |".into(),
    ]);
    for record in &inventory.records {
        let values = vec![
            markdown_cell(&record.path),
            record.line.to_string(),
            markdown_cell(&record.kind),
            markdown_cell(&record.domain),
            verdict(record).to_string(),
            markdown_cell(&record.qualname),
            markdown_cell(&record.role),
            record.searchable_name.to_string().to_lowercase(),
            markdown_cell(&record.name_search_rule),
            markdown_cell(&if record.matched_role_name_tokens.is_empty() {
                "none".into()
            } else {
                record.matched_role_name_tokens.join(", ")
            }),
            markdown_cell(if record.candidate_rule.is_empty() {
                "none"
            } else {
                &record.candidate_rule
            }),
            markdown_cell(if record.judgment_rule.is_empty() {
                "none"
            } else {
                &record.judgment_rule
            }),
            markdown_cell(if record.redundancy_rule.is_empty() {
                "none"
            } else {
                &record.redundancy_rule
            }),
            markdown_cell(&if record.redundant_with.is_empty() {
                "none".into()
            } else {
                record.redundant_with.join(", ")
            }),
            format!("{:.2}", record.confidence),
            record.incoming_count.to_string(),
            markdown_cell(&record.specialization),
            markdown_cell(&join_or_none(&record.side_effects, ", ")),
            markdown_cell(&join_or_none(&record.features, ", ")),
            markdown_cell(&join_or_none(
                &record
                    .evidence
                    .iter()
                    .take(MARKDOWN_EVIDENCE_LIMIT)
                    .cloned()
                    .collect::<Vec<_>>(),
                ", ",
            )),
        ];
        lines.push(format!("| {} |", values.join(" | ")));
    }
    format!("{}\n", lines.join("\n"))
}
