// @dependency-start
// contract implementation
// responsibility Checks Python algorithm-module public surface, nested ownership, and diagnostics from Python ASTs.
// upstream design ../../../../../documents/design/jax_util/algorithm_module_contract.md algorithm module contract
// upstream implementation python_structure_hash.rs provides the Python-AST-to-Rust analysis pattern
// downstream implementation main.rs exposes python-algorithm-contract-check
// @dependency-end

use serde::Serialize;
use serde_json::{json, Value};
use rustpython_ast::{Expr, Ranged, Stmt, Visitor};
use rustpython_parser::{ast, Parse};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs;
use std::path::{Path, PathBuf};

const DEFAULT_EXCLUDES: &[&str] = &[
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "reports",
    "vendor",
    "python/jax_util.egg-info",
];

const EXPECTED_PUBLIC_NAMES: &[&str] = &[
    "InitializeConfig",
    "SolveConfig",
    "Problem",
    "State",
    "Answer",
    "Info",
    "Algorithm",
    "initialize",
];

const CONTRACT_CLASSES: &[&str] = &["InitializeConfig", "SolveConfig", "Info", "Algorithm"];
const ALLOWED_EXTRA_PUBLIC_PREFIXES: &[&str] = &["STATUS_"];

const NON_ALGORITHM_IMPORT_ALLOWLIST: &[&str] = &[
    "python/jax_util/base",
    "python/jax_util/canon",
    "python/tests",
    "tests",
];

const STOPPING_POLICY_TYPES: &[&str] = &[
    "ResidualNormConvergenceCriterion",
    "MaxRelativeRayleighResidualCriterion",
    "RuntimeToleranceConfig",
];

const STOPPING_PRIMITIVE_CALLS: &[&str] = &[
    "residual_converged",
    "residual_tolerance",
    "rayleigh_residual_tolerance",
    "forcing_tolerance",
    "reference_residual_norm",
];

#[derive(Debug, PartialEq, Eq)]
struct Args {
    root: PathBuf,
    paths: Vec<String>,
    excludes: Vec<String>,
    format: OutputFormat,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum AllState {
    Missing,
    Dynamic,
    Literal,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ModuleAst {
    path: String,
    module: String,
    imports_amp: bool,
    public_definitions: BTreeMap<String, PublicDefinitionAst>,
    all_state: AllState,
    all_names: Vec<String>,
    all_line: usize,
    imports: BTreeMap<String, ImportAst>,
    aliases: BTreeMap<String, String>,
    classes: BTreeMap<String, ClassAst>,
    alias_attrs: BTreeMap<String, BTreeSet<String>>,
    calls: Vec<NamedLine>,
    references: Vec<NamedLine>,
    initialize_calls: Vec<InitializeCallAst>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct PublicDefinitionAst {
    line: usize,
    kind: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ImportAst {
    module: String,
    from_module: String,
    imported_name: String,
    level: usize,
    line: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ClassAst {
    line: usize,
    bases: Vec<String>,
    fields: Vec<FieldAst>,
    methods: BTreeSet<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct FieldAst {
    name: String,
    annotation: String,
    line: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct NamedLine {
    name: String,
    line: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct InitializeCallAst {
    alias: String,
    line: usize,
    uses_parent_config: bool,
    local_child_config: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Finding {
    path: String,
    line: usize,
    kind: String,
    subject: String,
    detail: String,
}

impl Finding {
    fn new(path: &str, line: usize, kind: &str, subject: &str, detail: &str) -> Self {
        Self {
            path: path.to_string(),
            line,
            kind: kind.to_string(),
            subject: subject.to_string(),
            detail: detail.to_string(),
        }
    }

    fn render(&self) -> String {
        format!(
            "PY_ALGORITHM_CONTRACT_FINDING={}:{}:{}:{}:{}",
            self.path, self.line, self.kind, self.subject, self.detail
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct ParseError {
    path: String,
    line: usize,
    kind: String,
    detail: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct DependencyReport {
    alias: String,
    module: String,
    contract_classes: Vec<String>,
    sources: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct ModuleReport {
    path: String,
    public_names: Vec<String>,
    all_names: Vec<String>,
    dependencies: Vec<DependencyReport>,
}

#[derive(Debug, PartialEq, Eq)]
struct Report {
    files: usize,
    algorithm_modules: Vec<String>,
    modules: Vec<ModuleReport>,
    findings: Vec<Finding>,
    parse_errors: Vec<ParseError>,
    format: OutputFormat,
}

#[derive(Debug, Serialize)]
struct JsonSummary {
    files: usize,
    algorithm_modules: usize,
    findings: usize,
    parse_errors: usize,
    status: &'static str,
}

#[derive(Debug, Serialize)]
struct JsonFinding<'a> {
    path: &'a str,
    line: usize,
    kind: &'a str,
    subject: &'a str,
    detail: &'a str,
}

#[derive(Debug, Serialize)]
struct JsonReport<'a> {
    summary: JsonSummary,
    algorithm_modules: &'a [String],
    modules: &'a [ModuleReport],
    parse_errors: &'a [ParseError],
    findings: Vec<JsonFinding<'a>>,
}

pub fn run(args: &[String]) -> i32 {
    match Args::parse(args).and_then(run_check) {
        Ok(report) => {
            render_report(&report);
            if report.findings.is_empty() && report.parse_errors.is_empty() {
                0
            } else {
                1
            }
        }
        Err(message) => {
            eprintln!("PY_ALGORITHM_CONTRACT=fail");
            eprintln!("PY_ALGORITHM_CONTRACT_FINDING=tool:1:tool_error:arguments:{message}");
            2
        }
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut root = PathBuf::from(".");
        let mut paths = Vec::new();
        let mut excludes = DEFAULT_EXCLUDES
            .iter()
            .map(|value| value.to_string())
            .collect::<Vec<_>>();
        let mut format = OutputFormat::Text;
        let mut index = 0;
        while index < args.len() {
            match args[index].as_str() {
                "--root" => {
                    root = PathBuf::from(value_after(args, index, "--root")?);
                    index += 2;
                }
                "--exclude" => {
                    excludes.push(value_after(args, index, "--exclude")?);
                    index += 2;
                }
                "--format" => {
                    format = match value_after(args, index, "--format")?.as_str() {
                        "text" => OutputFormat::Text,
                        "json" => OutputFormat::Json,
                        value => return Err(format!("--format must be text or json, got {value}")),
                    };
                    index += 2;
                }
                value if value.starts_with("--") => {
                    return Err(format!("unknown argument {value}"))
                }
                value => {
                    paths.push(value.to_string());
                    index += 1;
                }
            }
        }
        Ok(Self {
            root,
            paths,
            excludes,
            format,
        })
    }
}

fn value_after(args: &[String], index: usize, flag: &str) -> Result<String, String> {
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("{flag} requires a value"))
}

fn run_check(args: Args) -> Result<Report, String> {
    let root = resolve_like_cwd(&args.root);
    // Keep file identities canonical before parsing source into the native AST.
    let root = fs::canonicalize(&root).unwrap_or(root);
    let files = source_files(&root, &args.paths, &args.excludes);
    let payload = extract_ast_modules(&root, &files)?;
    let parse_errors = payload
        .get("errors")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(parse_parse_error)
        .collect::<Result<Vec<_>, _>>()?;
    let modules = payload
        .get("modules")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .map(parse_module_ast)
        .collect::<Result<Vec<_>, _>>()?;
    let algorithm_modules = modules
        .iter()
        .filter(|module| module_is_algorithm(module))
        .map(|module| module.path.clone())
        .collect::<Vec<_>>();
    let (findings, reports) = analyze_modules(&modules);
    Ok(Report {
        files: files.len(),
        algorithm_modules,
        modules: reports,
        findings,
        parse_errors,
        format: args.format,
    })
}

fn resolve_like_cwd(path: &Path) -> PathBuf {
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(path)
    }
}

fn source_files(root: &Path, raw_paths: &[String], excludes: &[String]) -> Vec<PathBuf> {
    let targets = if raw_paths.is_empty() {
        vec![root.to_path_buf()]
    } else {
        raw_paths.iter().map(|path| root.join(path)).collect()
    };
    let mut files = BTreeSet::new();
    for target in targets {
        collect_python_files(root, &target, excludes, &mut files);
    }
    files.into_iter().collect()
}

fn collect_python_files(
    root: &Path,
    target: &Path,
    excludes: &[String],
    files: &mut BTreeSet<PathBuf>,
) {
    if target.is_file() {
        if target.extension().and_then(|value| value.to_str()) == Some("py")
            && !excluded(root, target, excludes)
        {
            files.insert(fs::canonicalize(target).unwrap_or_else(|_| target.to_path_buf()));
        }
        return;
    }
    let Ok(entries) = fs::read_dir(target) else {
        return;
    };
    for entry in entries.flatten() {
        collect_python_files(root, &entry.path(), excludes, files);
    }
}

fn excluded(root: &Path, path: &Path, excludes: &[String]) -> bool {
    let relative = path.strip_prefix(root).unwrap_or(path);
    if relative
        .components()
        .any(|component| component.as_os_str().to_string_lossy().starts_with('.'))
    {
        return true;
    }
    let relative_text = relative.to_string_lossy().replace('\\', "/");
    excludes.iter().any(|raw_pattern| {
        let pattern = raw_pattern.trim().trim_matches('/');
        if pattern.is_empty() {
            return false;
        }
        if pattern.chars().any(|character| "*?[]".contains(character)) {
            return fnmatchcase(&relative_text, pattern);
        }
        relative_text == pattern
            || relative_text.starts_with(&format!("{pattern}/"))
            || relative_text.split('/').any(|part| part == pattern)
    })
}

fn fnmatchcase(value: &str, pattern: &str) -> bool {
    let value = value.chars().collect::<Vec<_>>();
    let pattern = pattern.chars().collect::<Vec<_>>();
    let mut cache = HashMap::new();
    fn matches(
        value: &[char],
        pattern: &[char],
        value_index: usize,
        pattern_index: usize,
        cache: &mut HashMap<(usize, usize), bool>,
    ) -> bool {
        if let Some(result) = cache.get(&(value_index, pattern_index)) {
            return *result;
        }
        let result = if pattern_index == pattern.len() {
            value_index == value.len()
        } else if pattern[pattern_index] == '*' {
            matches(value, pattern, value_index, pattern_index + 1, cache)
                || (value_index < value.len()
                    && matches(value, pattern, value_index + 1, pattern_index, cache))
        } else if value_index == value.len() {
            false
        } else if pattern[pattern_index] == '?' {
            matches(value, pattern, value_index + 1, pattern_index + 1, cache)
        } else if pattern[pattern_index] == '[' {
            if let Some((next, matched)) =
                match_character_class(&value[value_index], pattern, pattern_index)
            {
                matched && matches(value, pattern, value_index + 1, next, cache)
            } else {
                value[value_index] == '['
                    && matches(value, pattern, value_index + 1, pattern_index + 1, cache)
            }
        } else {
            value[value_index] == pattern[pattern_index]
                && matches(value, pattern, value_index + 1, pattern_index + 1, cache)
        };
        cache.insert((value_index, pattern_index), result);
        result
    }
    matches(&value, &pattern, 0, 0, &mut cache)
}

fn match_character_class(value: &char, pattern: &[char], start: usize) -> Option<(usize, bool)> {
    let mut index = start + 1;
    if index >= pattern.len() {
        return None;
    }
    let negated = matches!(pattern[index], '!' | '^');
    if negated {
        index += 1;
    }
    let mut matched = false;
    let mut has_member = false;
    while index < pattern.len() && pattern[index] != ']' {
        has_member = true;
        if index + 2 < pattern.len() && pattern[index + 1] == '-' && pattern[index + 2] != ']' {
            matched |= pattern[index] <= *value && *value <= pattern[index + 2];
            index += 3;
        } else {
            matched |= pattern[index] == *value;
            index += 1;
        }
    }
    if index >= pattern.len() || !has_member {
        return None;
    }
    Some((index + 1, if negated { !matched } else { matched }))
}

fn extract_ast_modules(root: &Path, files: &[PathBuf]) -> Result<Value, String> {
    let mut modules = Vec::new();
    let mut errors = Vec::new();
    for path in files {
        let source = fs::read_to_string(path)
            .map_err(|error| format!("failed to read Python source {}: {error}", path.display()))?;
        let source = normalize_python_newlines(&source);
        let source_path = path.to_string_lossy();
        let suite = match ast::Suite::parse(&source, source_path.as_ref()) {
            Ok(suite) => suite,
            Err(error) => {
                let relative = relative_source_path(root, path)?;
                errors.push(json!({
                    "path": relative,
                    "line": line_at_offset(&source, error.offset.to_usize()),
                    "kind": "syntax_error",
                    "detail": "parseable"
                }));
                continue;
            }
        };
        modules.push(extract_module_json(root, path, &source, &suite)?);
    }
    Ok(json!({"modules": modules, "errors": errors}))
}

fn extract_module_json(
    root: &Path,
    path: &Path,
    source: &str,
    suite: &ast::Suite,
) -> Result<Value, String> {
    let relative = relative_source_path(root, path)?;
    let module_path = PathBuf::from(&relative);
    let mut import_aliases = Vec::new();
    let mut imports_amp = false;
    for statement in suite {
        match statement {
            Stmt::Import(import) => {
                for alias in &import.names {
                    let name = alias.name.to_string();
                    if name.ends_with("algorithm_module_protocol") {
                        imports_amp = true;
                        continue;
                    }
                    import_aliases.push(json!({
                        "alias": alias.asname.as_ref().map(ToString::to_string).unwrap_or_else(|| {
                            name.rsplit('.').next().unwrap_or(name.as_str()).to_string()
                        }),
                        "module": name,
                        "from_module": "",
                        "name": "",
                        "level": 0,
                        "line": node_line(source, statement)
                    }));
                }
            }
            Stmt::ImportFrom(import) => {
                let module = import.module.as_ref().map(ToString::to_string).unwrap_or_default();
                if module.ends_with("algorithm_module_protocol")
                    || import.names.iter().any(|alias| alias.name.as_str() == "algorithm_module_protocol")
                {
                    imports_amp = true;
                }
                let level = import.level.as_ref()
                    .map(|value| value.to_usize())
                    .unwrap_or(0);
                for alias in &import.names {
                    let name = alias.name.to_string();
                    if module.ends_with("algorithm_module_protocol") || name == "algorithm_module_protocol" {
                        continue;
                    }
                    let mut imported = ".".repeat(level);
                    imported.push_str(&module);
                    if !module.is_empty() {
                        imported.push('.');
                        imported.push_str(&name);
                    }
                    import_aliases.push(json!({
                        "alias": alias.asname.as_ref().unwrap_or(&alias.name).to_string(),
                        "module": imported,
                        "from_module": module,
                        "name": name,
                        "level": level,
                        "line": node_line(source, statement)
                    }));
                }
            }
            _ => {}
        }
    }

    let public_definitions = public_definitions(source, suite);
    let (all_state, all_names, all_line) = all_state(source, suite);
    let aliases = top_level_aliases(suite);
    let classes = class_definitions(source, suite);
    let usage = usage(source, suite, &import_aliases);
    let module = module_name(&module_path);
    Ok(json!({
        "path": relative,
        "module": module,
        "imports_amp": imports_amp,
        "public_definitions": public_definitions,
        "all_state": all_state,
        "all_names": all_names,
        "all_line": all_line,
        "imports": import_aliases,
        "aliases": aliases,
        "classes": classes,
        "usage": usage
    }))
}

fn relative_source_path(root: &Path, path: &Path) -> Result<String, String> {
    let relative = path.strip_prefix(root).map_err(|_| {
        format!(
            "Python source path {} is outside root {}",
            path.display(),
            root.display()
        )
    })?;
    Ok(posix_path(relative))
}

fn posix_path(path: &Path) -> String {
    let value = path.to_string_lossy();
    #[cfg(windows)]
    {
        value.replace('\\', "/")
    }
    #[cfg(not(windows))]
    {
        value.into_owned()
    }
}

fn normalize_python_newlines(source: &str) -> String {
    source.replace("\r\n", "\n").replace('\r', "\n")
}

fn module_name(relative_path: &Path) -> String {
    let mut module_path = relative_path.to_path_buf();
    module_path.set_extension("");
    if module_path
        .file_name()
        .is_some_and(|name| name.to_string_lossy() == "__init__")
    {
        module_path.pop();
    }
    module_path
        .components()
        .map(|component| component.as_os_str().to_string_lossy().into_owned())
        .collect::<Vec<_>>()
        .join(".")
}

fn line_at_offset(source: &str, offset: usize) -> usize {
    source
        .as_bytes()
        .iter()
        .take(offset.min(source.len()))
        .filter(|byte| **byte == b'\n')
        .count()
        + 1
}

fn node_line(source: &str, node: &impl Ranged) -> usize {
    line_at_offset(source, node.start().to_usize())
}

fn expr_name(expr: &Expr) -> Option<String> {
    match expr {
        Expr::Name(name) => Some(name.id.to_string()),
        _ => None,
    }
}

fn ref_name(expr: &Expr) -> String {
    match expr {
        Expr::Name(name) => name.id.to_string(),
        Expr::Attribute(attribute) => {
            let parent = ref_name(&attribute.value);
            if parent.is_empty() {
                attribute.attr.to_string()
            } else {
                format!("{parent}.{}", attribute.attr)
            }
        }
        Expr::Subscript(subscript) => ref_name(&subscript.value),
        Expr::Call(call) => ref_name(&call.func),
        Expr::Constant(constant) => constant.value.to_string(),
        _ => ast_dump_expr(expr),
    }
}

fn ast_dump_expr(expr: &Expr) -> String {
    use ast::Expr as E;
    match expr {
        E::BoolOp(node) => ast_dump_node(
            "BoolOp",
            [ast_dump_node(&format!("{:?}", node.op), []), ast_dump_expr_list(&node.values)],
        ),
        E::NamedExpr(node) => ast_dump_node(
            "NamedExpr",
            [ast_dump_expr(&node.target), ast_dump_expr(&node.value)],
        ),
        E::BinOp(node) => ast_dump_node(
            "BinOp",
            [
                ast_dump_expr(&node.left),
                ast_dump_node(&format!("{:?}", node.op), []),
                ast_dump_expr(&node.right),
            ],
        ),
        E::UnaryOp(node) => ast_dump_node(
            "UnaryOp",
            [
                ast_dump_node(&format!("{:?}", node.op), []),
                ast_dump_expr(&node.operand),
            ],
        ),
        E::Lambda(node) => ast_dump_node(
            "Lambda",
            [ast_dump_arguments(&node.args), ast_dump_expr(&node.body)],
        ),
        E::IfExp(node) => ast_dump_node(
            "IfExp",
            [
                ast_dump_expr(&node.test),
                ast_dump_expr(&node.body),
                ast_dump_expr(&node.orelse),
            ],
        ),
        E::Dict(node) => ast_dump_node(
            "Dict",
            [
                ast_dump_list(node.keys.iter().map(|key| {
                    key.as_ref().map(ast_dump_expr).unwrap_or_else(|| "None".into())
                })),
                ast_dump_expr_list(&node.values),
            ],
        ),
        E::Set(node) => ast_dump_node("Set", [ast_dump_expr_list(&node.elts)]),
        E::ListComp(node) => ast_dump_node(
            "ListComp",
            [ast_dump_expr(&node.elt), ast_dump_comprehensions(&node.generators)],
        ),
        E::SetComp(node) => ast_dump_node(
            "SetComp",
            [ast_dump_expr(&node.elt), ast_dump_comprehensions(&node.generators)],
        ),
        E::DictComp(node) => ast_dump_node(
            "DictComp",
            [
                ast_dump_expr(&node.key),
                ast_dump_expr(&node.value),
                ast_dump_comprehensions(&node.generators),
            ],
        ),
        E::GeneratorExp(node) => ast_dump_node(
            "GeneratorExp",
            [ast_dump_expr(&node.elt), ast_dump_comprehensions(&node.generators)],
        ),
        E::Await(node) => ast_dump_node("Await", [ast_dump_expr(&node.value)]),
        E::Yield(node) => ast_dump_node(
            "Yield",
            [node.value.as_ref().map(|value| ast_dump_expr(value)).unwrap_or_else(|| "None".into())],
        ),
        E::YieldFrom(node) => ast_dump_node("YieldFrom", [ast_dump_expr(&node.value)]),
        E::Compare(node) => ast_dump_node(
            "Compare",
            [
                ast_dump_expr(&node.left),
                ast_dump_list(node.ops.iter().map(|op| ast_dump_node(&format!("{op:?}"), []))),
                ast_dump_expr_list(&node.comparators),
            ],
        ),
        E::Call(node) => ast_dump_node(
            "Call",
            [
                ast_dump_expr(&node.func),
                ast_dump_expr_list(&node.args),
                ast_dump_list(node.keywords.iter().map(ast_dump_keyword)),
            ],
        ),
        E::FormattedValue(node) => ast_dump_node(
            "FormattedValue",
            [
                ast_dump_expr(&node.value),
                (node.conversion as i8).to_string(),
                node.format_spec
                    .as_ref()
                    .map(|spec| ast_dump_expr(spec))
                    .unwrap_or_else(|| "None".into()),
            ],
        ),
        E::JoinedStr(node) => ast_dump_node("JoinedStr", [ast_dump_expr_list(&node.values)]),
        E::Constant(node) => ast_dump_node(
            "Constant",
            [
                node.value.to_string(),
                node.kind
                    .as_ref()
                    .map(|kind| ast_dump_string(kind))
                    .unwrap_or_else(|| "None".into()),
            ],
        ),
        E::Attribute(node) => ast_dump_node(
            "Attribute",
            [
                ast_dump_expr(&node.value),
                ast_dump_string(node.attr.as_str()),
                ast_dump_context(&node.ctx),
            ],
        ),
        E::Subscript(node) => ast_dump_node(
            "Subscript",
            [
                ast_dump_expr(&node.value),
                ast_dump_expr(&node.slice),
                ast_dump_context(&node.ctx),
            ],
        ),
        E::Starred(node) => ast_dump_node(
            "Starred",
            [ast_dump_expr(&node.value), ast_dump_context(&node.ctx)],
        ),
        E::Name(node) => ast_dump_node(
            "Name",
            [ast_dump_string(node.id.as_str()), ast_dump_context(&node.ctx)],
        ),
        E::List(node) => ast_dump_node(
            "List",
            [ast_dump_expr_list(&node.elts), ast_dump_context(&node.ctx)],
        ),
        E::Tuple(node) => ast_dump_node(
            "Tuple",
            [ast_dump_expr_list(&node.elts), ast_dump_context(&node.ctx)],
        ),
        E::Slice(node) => ast_dump_node(
            "Slice",
            [
                node.lower.as_ref().map(|value| ast_dump_expr(value)).unwrap_or_else(|| "None".into()),
                node.upper.as_ref().map(|value| ast_dump_expr(value)).unwrap_or_else(|| "None".into()),
                node.step.as_ref().map(|value| ast_dump_expr(value)).unwrap_or_else(|| "None".into()),
            ],
        ),
    }
}

fn ast_dump_node<const N: usize>(name: &str, fields: [String; N]) -> String {
    format!("{name}({})", fields.join(", "))
}

fn ast_dump_list(values: impl IntoIterator<Item = String>) -> String {
    format!("[{}]", values.into_iter().collect::<Vec<_>>().join(", "))
}

fn ast_dump_expr_list(values: &[Expr]) -> String {
    ast_dump_list(values.iter().map(ast_dump_expr))
}

fn ast_dump_string(value: &str) -> String {
    ast::Constant::Str(value.to_string()).to_string()
}

fn ast_dump_context(context: &ast::ExprContext) -> String {
    ast_dump_node(&format!("{context:?}"), [])
}

fn ast_dump_keyword(keyword: &ast::Keyword) -> String {
    ast_dump_node(
        "keyword",
        [
            keyword
                .arg
                .as_ref()
                .map(|name| ast_dump_string(name.as_str()))
                .unwrap_or_else(|| "None".into()),
            ast_dump_expr(&keyword.value),
        ],
    )
}

fn ast_dump_comprehensions(values: &[ast::Comprehension]) -> String {
    ast_dump_list(values.iter().map(|value| {
        ast_dump_node(
            "comprehension",
            [
                ast_dump_expr(&value.target),
                ast_dump_expr(&value.iter),
                ast_dump_expr_list(&value.ifs),
                u8::from(value.is_async).to_string(),
            ],
        )
    }))
}

fn ast_dump_arg(argument: &ast::Arg) -> String {
    ast_dump_node(
        "arg",
        [
            ast_dump_string(argument.arg.as_str()),
            argument
                .annotation
                .as_ref()
                .map(|annotation| ast_dump_expr(annotation))
                .unwrap_or_else(|| "None".into()),
            argument
                .type_comment
                .as_ref()
                .map(|comment| ast_dump_string(comment))
                .unwrap_or_else(|| "None".into()),
        ],
    )
}

fn ast_dump_arguments(arguments: &ast::Arguments) -> String {
    ast_dump_node(
        "arguments",
        [
            ast_dump_list(arguments.posonlyargs.iter().map(|argument| ast_dump_arg(&argument.def))),
            ast_dump_list(arguments.args.iter().map(|argument| ast_dump_arg(&argument.def))),
            arguments
                .vararg
                .as_ref()
                .map(|argument| ast_dump_arg(argument))
                .unwrap_or_else(|| "None".into()),
            ast_dump_list(arguments.kwonlyargs.iter().map(|argument| ast_dump_arg(&argument.def))),
            ast_dump_list(arguments.kwonlyargs.iter().map(|argument| {
                argument
                    .default
                    .as_deref()
                    .map(ast_dump_expr)
                    .unwrap_or_else(|| "None".into())
            })),
            arguments
                .kwarg
                .as_ref()
                .map(|argument| ast_dump_arg(argument))
                .unwrap_or_else(|| "None".into()),
            ast_dump_list(arguments.posonlyargs.iter().chain(&arguments.args).filter_map(|argument| {
                argument.default.as_deref().map(ast_dump_expr)
            })),
        ],
    )
}

fn literal_string_sequence(expr: &Expr) -> Option<Vec<String>> {
    let elements = match expr {
        Expr::List(list) => &list.elts,
        Expr::Tuple(tuple) => &tuple.elts,
        Expr::Set(set) => &set.elts,
        _ => return None,
    };
    elements
        .iter()
        .map(|element| match element {
            Expr::Constant(constant) => match &constant.value {
                ast::Constant::Str(value) => Some(value.clone()),
                _ => None,
            },
            _ => None,
        })
        .collect()
}

fn public_definitions(source: &str, suite: &ast::Suite) -> Vec<Value> {
    let mut definitions = Vec::new();
    for statement in suite {
        let line = node_line(source, statement);
        match statement {
            Stmt::ClassDef(class) if is_public_name(class.name.as_str()) => {
                definitions.push(json!({"name": class.name.to_string(), "line": line, "kind": "class"}));
            }
            Stmt::FunctionDef(function) if is_public_name(function.name.as_str()) => {
                definitions.push(json!({"name": function.name.to_string(), "line": line, "kind": "function"}));
            }
            Stmt::AsyncFunctionDef(function) if is_public_name(function.name.as_str()) => {
                definitions.push(json!({"name": function.name.to_string(), "line": line, "kind": "async_function"}));
            }
            Stmt::Assign(assign) => {
                for target in &assign.targets {
                    if let Some(name) = expr_name(target).filter(|name| is_public_name(name)) {
                        definitions.push(json!({"name": name, "line": line, "kind": "assignment"}));
                    }
                }
            }
            Stmt::AnnAssign(assign) => {
                if let Some(name) = expr_name(&assign.target).filter(|name| is_public_name(name)) {
                    definitions.push(json!({"name": name, "line": line, "kind": "annotation"}));
                }
            }
            _ => {}
        }
    }
    definitions
}

fn is_public_name(name: &str) -> bool {
    !name.starts_with('_') && name != "__all__"
}

fn all_state(source: &str, suite: &ast::Suite) -> (&'static str, Vec<String>, usize) {
    for statement in suite {
        let value = match statement {
            Stmt::Assign(assign)
                if assign.targets.iter().any(|target| expr_name(target).as_deref() == Some("__all__")) =>
            {
                Some(assign.value.as_ref())
            }
            Stmt::AnnAssign(assign) if expr_name(&assign.target).as_deref() == Some("__all__") => {
                assign.value.as_deref()
            }
            _ => None,
        };
        if let Stmt::AnnAssign(assign) = statement {
            if expr_name(&assign.target).as_deref() == Some("__all__") && assign.value.is_none() {
                return ("dynamic", Vec::new(), node_line(source, statement));
            }
        }
        if let Some(value) = value {
            return match literal_string_sequence(value) {
                Some(names) => ("literal", names, node_line(source, statement)),
                None => ("dynamic", Vec::new(), node_line(source, statement)),
            };
        }
    }
    ("missing", Vec::new(), 1)
}

fn top_level_aliases(suite: &ast::Suite) -> BTreeMap<String, String> {
    let mut aliases = BTreeMap::new();
    for statement in suite {
        match statement {
            Stmt::AnnAssign(assign) => {
                if let (Some(name), Some(value)) = (expr_name(&assign.target), assign.value.as_deref()) {
                    aliases.insert(name, value.to_string());
                }
            }
            Stmt::Assign(assign) if assign.targets.len() == 1 => {
                if let Some(name) = expr_name(&assign.targets[0]) {
                    aliases.insert(name, assign.value.to_string());
                }
            }
            _ => {}
        }
    }
    aliases
}

fn class_definitions(source: &str, suite: &ast::Suite) -> Vec<Value> {
    let mut classes = Vec::new();
    for statement in suite {
        let Stmt::ClassDef(class) = statement else {
            continue;
        };
        let mut fields = Vec::new();
        let mut methods = Vec::new();
        for child in &class.body {
            match child {
                Stmt::AnnAssign(assign) => fields.push(json!({
                    "name": ref_name(&assign.target),
                    "annotation": assign.annotation.to_string(),
                    "line": node_line(source, child)
                })),
                Stmt::FunctionDef(function) => methods.push(function.name.to_string()),
                Stmt::AsyncFunctionDef(function) => methods.push(function.name.to_string()),
                _ => {}
            }
        }
        let bases = class.bases.iter().map(ref_name).collect::<Vec<_>>();
        classes.push(json!({
            "name": class.name.to_string(),
            "line": node_line(source, statement),
            "bases": bases,
            "fields": fields,
            "methods": methods
        }));
    }
    classes
}

struct UsageCollector<'a> {
    source: &'a str,
    aliases: BTreeSet<String>,
    alias_attrs: BTreeMap<String, BTreeSet<String>>,
    calls: Vec<Value>,
    references: Vec<Value>,
    initialize_calls: Vec<Value>,
}

impl<'a> UsageCollector<'a> {
    fn new(source: &'a str, aliases: BTreeSet<String>) -> Self {
        Self {
            source,
            aliases,
            alias_attrs: BTreeMap::new(),
            calls: Vec::new(),
            references: Vec::new(),
            initialize_calls: Vec::new(),
        }
    }

    fn as_json(self) -> Value {
        json!({
            "alias_attrs": self.alias_attrs,
            "calls": self.calls,
            "references": self.references,
            "initialize_calls": self.initialize_calls
        })
    }
}

impl Visitor for UsageCollector<'_> {
    fn visit_expr_attribute(&mut self, node: ast::ExprAttribute) {
        let line = node_line(self.source, &node);
        if let Expr::Name(name) = node.value.as_ref() {
            let alias = name.id.to_string();
            if self.aliases.contains(&alias) {
                self.alias_attrs
                    .entry(alias)
                    .or_default()
                    .insert(node.attr.to_string());
            }
        }
        let parent = ref_name(&node.value);
        let name = if parent.is_empty() {
            node.attr.to_string()
        } else {
            format!("{parent}.{}", node.attr)
        };
        if !name.is_empty() {
            self.references.push(json!({"name": name, "line": line}));
        }
        self.generic_visit_expr_attribute(node);
    }

    fn visit_expr_name(&mut self, node: ast::ExprName) {
        self.references.push(json!({
            "name": node.id.to_string(),
            "line": node_line(self.source, &node)
        }));
        self.generic_visit_expr_name(node);
    }

    fn visit_expr_call(&mut self, node: ast::ExprCall) {
        let line = node_line(self.source, &node);
        let name = ref_name(&node.func);
        if !name.is_empty() {
            self.calls.push(json!({"name": name, "line": line}));
        }
        if let Expr::Attribute(function) = node.func.as_ref() {
            if function.attr.as_str() == "initialize" {
                if let Expr::Name(alias) = function.value.as_ref() {
                    let alias_name = alias.id.to_string();
                    if self.aliases.contains(&alias_name) {
                        let first_arg = node.args.first();
                        let uses_parent_config = first_arg.is_some_and(uses_parent_config_field);
                        let local_child_config = first_arg
                            .is_some_and(|argument| is_local_child_config(argument, &alias_name));
                        self.initialize_calls.push(json!({
                            "alias": alias_name,
                            "line": line,
                            "uses_parent_config": uses_parent_config,
                            "local_child_config": local_child_config
                        }));
                    }
                }
            }
        }
        self.generic_visit_expr_call(node);
    }
}

struct ParentConfigVisitor(bool);

impl Visitor for ParentConfigVisitor {
    fn visit_expr_attribute(&mut self, node: ast::ExprAttribute) {
        if matches!(node.value.as_ref(), Expr::Name(name) if name.id.as_str() == "config") {
            self.0 = true;
        }
        self.generic_visit_expr_attribute(node);
    }
}

fn usage(source: &str, suite: &ast::Suite, imports: &[Value]) -> Value {
    let aliases = imports
        .iter()
        .filter_map(|import| import.get("alias").and_then(Value::as_str).map(str::to_string))
        .collect::<BTreeSet<_>>();
    let mut visitor = UsageCollector::new(source, aliases);
    for statement in suite.iter().cloned() {
        visitor.visit_stmt(statement);
    }
    visitor.as_json()
}

fn uses_parent_config_field(expr: &Expr) -> bool {
    let mut visitor = ParentConfigVisitor(false);
    visitor.visit_expr(expr.clone());
    visitor.0
}

fn is_local_child_config(expr: &Expr, dependency_alias: &str) -> bool {
    matches!(
        expr,
        Expr::Call(call)
            if matches!(call.func.as_ref(), Expr::Attribute(attribute)
                if attribute.attr.as_str() == "InitializeConfig"
                    && matches!(attribute.value.as_ref(), Expr::Name(name)
                        if name.id.as_str() == dependency_alias))
    )
}

fn parse_parse_error(value: &Value) -> Result<ParseError, String> {
    Ok(ParseError {
        path: string_field(value, "path")?,
        line: usize_field(value, "line")?,
        kind: string_field(value, "kind")?,
        detail: string_field(value, "detail")?,
    })
}

fn parse_module_ast(value: Value) -> Result<ModuleAst, String> {
    let path = string_field(&value, "path")?;
    let imports = value
        .get("imports")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{path}: imports must be array"))?
        .iter()
        .map(parse_import_ast)
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .map(|item| (item.0, item.1))
        .collect::<BTreeMap<_, _>>();
    let classes = value
        .get("classes")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{path}: classes must be array"))?
        .iter()
        .map(parse_class_ast)
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .map(|item| (item.0, item.1))
        .collect::<BTreeMap<_, _>>();
    let public_definitions = value
        .get("public_definitions")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{path}: public_definitions must be array"))?
        .iter()
        .map(parse_public_definition)
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .map(|item| (item.0, item.1))
        .collect::<BTreeMap<_, _>>();
    let all_state = match string_field(&value, "all_state")?.as_str() {
        "missing" => AllState::Missing,
        "dynamic" => AllState::Dynamic,
        "literal" => AllState::Literal,
        state => return Err(format!("{path}: invalid all_state {state}")),
    };
    let all_names = value
        .get("all_names")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{path}: all_names must be array"))?
        .iter()
        .filter_map(Value::as_str)
        .map(str::to_string)
        .collect();
    let initialize_calls = value
        .get("usage")
        .and_then(|usage| usage.get("initialize_calls"))
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{path}: initialize_calls must be array"))?
        .iter()
        .map(parse_initialize_call)
        .collect::<Result<Vec<_>, _>>()?;
    Ok(ModuleAst {
        path,
        module: string_field(&value, "module")?,
        imports_amp: value
            .get("imports_amp")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        public_definitions,
        all_state,
        all_names,
        all_line: usize_field(&value, "all_line")?,
        imports,
        aliases: parse_string_map(value.get("aliases"))?,
        classes,
        alias_attrs: parse_alias_attrs(&value)?,
        calls: parse_named_lines(
            value
                .get("usage")
                .and_then(|usage| usage.get("calls"))
                .unwrap_or(&Value::Null),
        )?,
        references: parse_named_lines(
            value
                .get("usage")
                .and_then(|usage| usage.get("references"))
                .unwrap_or(&Value::Null),
        )?,
        initialize_calls,
    })
}

fn parse_public_definition(value: &Value) -> Result<(String, PublicDefinitionAst), String> {
    let name = string_field(value, "name")?;
    Ok((
        name,
        PublicDefinitionAst {
            line: usize_field(value, "line")?,
            kind: string_field(value, "kind")?,
        },
    ))
}

fn parse_initialize_call(value: &Value) -> Result<InitializeCallAst, String> {
    Ok(InitializeCallAst {
        alias: string_field(value, "alias")?,
        line: usize_field(value, "line")?,
        uses_parent_config: value
            .get("uses_parent_config")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        local_child_config: value
            .get("local_child_config")
            .and_then(Value::as_bool)
            .unwrap_or(false),
    })
}

fn parse_import_ast(value: &Value) -> Result<(String, ImportAst), String> {
    let alias = string_field(value, "alias")?;
    Ok((
        alias,
        ImportAst {
            module: string_field(value, "module")?,
            from_module: value
                .get("from_module")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            imported_name: value
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            level: value
                .get("level")
                .and_then(Value::as_u64)
                .and_then(|number| usize::try_from(number).ok())
                .unwrap_or(0),
            line: usize_field(value, "line")?,
        },
    ))
}

fn parse_class_ast(value: &Value) -> Result<(String, ClassAst), String> {
    let name = string_field(value, "name")?;
    let fields = value
        .get("fields")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(|field| {
            Ok(FieldAst {
                name: string_field(field, "name")?,
                annotation: string_field(field, "annotation")?,
                line: usize_field(field, "line")?,
            })
        })
        .collect::<Result<Vec<_>, String>>()?;
    let methods = value
        .get("methods")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .iter()
        .filter_map(Value::as_str)
        .map(str::to_string)
        .collect::<BTreeSet<_>>();
    let bases = value
        .get("bases")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .iter()
        .filter_map(Value::as_str)
        .map(str::to_string)
        .collect::<Vec<_>>();
    Ok((
        name,
        ClassAst {
            line: usize_field(value, "line")?,
            bases,
            fields,
            methods,
        },
    ))
}

fn parse_string_map(value: Option<&Value>) -> Result<BTreeMap<String, String>, String> {
    let Some(Value::Object(entries)) = value else {
        return Ok(BTreeMap::new());
    };
    Ok(entries
        .iter()
        .filter_map(|(key, value)| value.as_str().map(|text| (key.clone(), text.to_string())))
        .collect())
}

fn parse_alias_attrs(value: &Value) -> Result<BTreeMap<String, BTreeSet<String>>, String> {
    let Some(Value::Object(entries)) = value
        .get("usage")
        .and_then(|usage| usage.get("alias_attrs"))
    else {
        return Ok(BTreeMap::new());
    };
    Ok(entries
        .iter()
        .map(|(key, value)| {
            let attrs = value
                .as_array()
                .cloned()
                .unwrap_or_default()
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect::<BTreeSet<_>>();
            (key.clone(), attrs)
        })
        .collect())
}

fn parse_named_lines(value: &Value) -> Result<Vec<NamedLine>, String> {
    Ok(value
        .as_array()
        .cloned()
        .unwrap_or_default()
        .iter()
        .filter_map(|item| {
            Some(NamedLine {
                name: item.get("name")?.as_str()?.to_string(),
                line: item
                    .get("line")
                    .and_then(Value::as_u64)
                    .and_then(|number| usize::try_from(number).ok())
                    .unwrap_or(1),
            })
        })
        .collect())
}

fn string_field(value: &Value, field: &str) -> Result<String, String> {
    value
        .get(field)
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| format!("field {field} must be a string"))
}

fn usize_field(value: &Value, field: &str) -> Result<usize, String> {
    value
        .get(field)
        .and_then(Value::as_u64)
        .and_then(|number| usize::try_from(number).ok())
        .ok_or_else(|| format!("field {field} must be a positive integer"))
}

fn analyze_modules(modules: &[ModuleAst]) -> (Vec<Finding>, Vec<ModuleReport>) {
    let algorithm_module_names = modules
        .iter()
        .filter(|module| module_is_algorithm(module))
        .map(|module| module.module.clone())
        .collect::<BTreeSet<_>>();
    let mut findings = Vec::new();
    let mut reports = Vec::new();
    for module in modules {
        if !module.imports_amp || module_has_expected_public_name(module) {
            if module_is_algorithm(module) {
                findings.extend(analyze_algorithm_module_surface(module));
                let (nested_findings, dependencies) =
                    analyze_nested_contract(module, &algorithm_module_names);
                findings.extend(nested_findings);
                findings.extend(analyze_legacy_stopping_usage(module));
                reports.push(module_report(module, dependencies));
            }
        } else if !is_allowed_non_algorithm_import(&module.path) {
            findings.push(Finding::new(
                &module.path,
                1,
                "non_algorithm_protocol_import",
                "algorithm_module_protocol",
                "define-standard-public-surface-or-remove-import",
            ));
        }
    }
    findings.sort_by(|left, right| {
        left.path
            .cmp(&right.path)
            .then_with(|| left.line.cmp(&right.line))
            .then_with(|| left.kind.cmp(&right.kind))
            .then_with(|| left.subject.cmp(&right.subject))
            .then_with(|| left.detail.cmp(&right.detail))
    });
    findings.dedup_by(|right, left| {
        right.path == left.path
            && right.line == left.line
            && right.kind == left.kind
            && right.subject == left.subject
            && right.detail == left.detail
    });
    reports.sort_by(|left, right| left.path.cmp(&right.path));
    (findings, reports)
}

fn module_report(
    module: &ModuleAst,
    dependencies: BTreeMap<String, DependencyReport>,
) -> ModuleReport {
    ModuleReport {
        path: module.path.clone(),
        public_names: module.public_definitions.keys().cloned().collect(),
        all_names: module.all_names.clone(),
        dependencies: dependencies.into_values().collect(),
    }
}

fn module_has_expected_public_name(module: &ModuleAst) -> bool {
    module
        .public_definitions
        .keys()
        .any(|name| EXPECTED_PUBLIC_NAMES.contains(&name.as_str()))
}

fn is_allowed_non_algorithm_import(relative: &str) -> bool {
    NON_ALGORITHM_IMPORT_ALLOWLIST
        .iter()
        .any(|prefix| relative == *prefix || relative.starts_with(&format!("{prefix}/")))
}

fn module_is_algorithm(module: &ModuleAst) -> bool {
    module.imports_amp && module_has_expected_public_name(module)
}

fn analyze_algorithm_module_surface(module: &ModuleAst) -> Vec<Finding> {
    let mut findings = Vec::new();
    if !matches!(module.all_state, AllState::Literal) {
        let kind = if matches!(module.all_state, AllState::Dynamic) {
            "dynamic_all"
        } else {
            "missing_all"
        };
        findings.push(Finding::new(
            &module.path,
            module.all_line,
            kind,
            "__all__",
            "literal-standard-public-names-required",
        ));
    }
    let all_name_set = module.all_names.iter().cloned().collect::<BTreeSet<_>>();
    for name in all_name_set.difference(&expected_public_name_set()) {
        if !is_allowed_extra_public_name(name) {
            findings.push(Finding::new(
                &module.path,
                module.all_line,
                "extra_all",
                name,
                "remove-from-__all__",
            ));
        }
    }
    for name in expected_public_name_set().difference(&all_name_set) {
        findings.push(Finding::new(
            &module.path,
            module.all_line,
            "missing_all_name",
            name,
            "add-to-__all__",
        ));
    }
    for (name, definition) in &module.public_definitions {
        if !EXPECTED_PUBLIC_NAMES.contains(&name.as_str()) && !is_allowed_extra_public_name(name) {
            findings.push(Finding::new(
                &module.path,
                definition.line,
                "extra_public_definition",
                name,
                "make-private-or-remove",
            ));
        }
    }
    for name in
        expected_public_name_set().difference(&module.public_definitions.keys().cloned().collect())
    {
        findings.push(Finding::new(
            &module.path,
            module.all_line,
            "missing_public_definition",
            name,
            "define-standard-public-name",
        ));
    }
    match module.classes.get("Algorithm") {
        Some(class_node) if class_node.methods.contains("__call__") => {}
        Some(class_node) => findings.push(Finding::new(
            &module.path,
            class_node.line,
            "algorithm_not_callable",
            "Algorithm",
            "define __call__(Problem, State, SolveConfig) returning Answer, State, Info",
        )),
        None => findings.push(Finding::new(
            &module.path,
            module
                .public_definitions
                .get("Algorithm")
                .map(|definition| definition.line)
                .unwrap_or(1),
            "missing_algorithm_function_object",
            "Algorithm",
            "define callable Algorithm",
        )),
    }
    if let Some(info) = module.public_definitions.get("Info") {
        if info.kind != "class" {
            findings.push(Finding::new(
                &module.path,
                info.line,
                "info_not_concrete",
                "Info",
                "define concrete class Info",
            ));
        }
    }
    findings
}

fn expected_public_name_set() -> BTreeSet<String> {
    EXPECTED_PUBLIC_NAMES
        .iter()
        .map(|name| (*name).to_string())
        .collect()
}

fn is_allowed_extra_public_name(name: &str) -> bool {
    ALLOWED_EXTRA_PUBLIC_PREFIXES
        .iter()
        .any(|prefix| name.starts_with(prefix))
}

fn analyze_nested_contract(
    module: &ModuleAst,
    algorithm_module_names: &BTreeSet<String>,
) -> (Vec<Finding>, BTreeMap<String, DependencyReport>) {
    let requirements = nested_requirements(module);
    let mut dependencies = BTreeMap::new();
    for ((alias, contract_class), sources) in &requirements {
        let dependency_module = dependency_module(module, alias, algorithm_module_names);
        let key = format!("{alias}\0{dependency_module}");
        let dependency = dependencies.entry(key).or_insert_with(|| DependencyReport {
            alias: alias.clone(),
            module: dependency_module,
            contract_classes: Vec::new(),
            sources: Vec::new(),
        });
        if !dependency.contract_classes.contains(contract_class) {
            dependency.contract_classes.push(contract_class.clone());
        }
        for source in sources {
            if !dependency.sources.contains(source) {
                dependency.sources.push(source.clone());
            }
        }
    }
    for dependency in dependencies.values_mut() {
        dependency.contract_classes.sort();
        dependency.sources.sort();
    }
    let mut findings = Vec::new();
    for ((alias, contract_class), _) in requirements {
        let Some(class_node) = module.classes.get(&contract_class) else {
            findings.push(Finding::new(
                &module.path,
                1,
                "missing_contract_class",
                &format!("{alias}.{contract_class}"),
                &format!("define {contract_class}"),
            ));
            continue;
        };
        if class_annotations_contain(module, class_node, &alias, &contract_class) {
            continue;
        }
        let detail = nested_field_detail(module, class_node, &alias, &contract_class);
        findings.push(Finding::new(
            &module.path,
            class_node.line,
            "missing_nested_field",
            &format!("{alias}.{contract_class}"),
            &detail,
        ));
    }
    (findings, dependencies)
}

fn nested_requirements(module: &ModuleAst) -> BTreeMap<(String, String), BTreeSet<String>> {
    let mut requirements = BTreeMap::new();
    for contract_class in CONTRACT_CLASSES {
        let Some(class_node) = module.classes.get(*contract_class) else {
            continue;
        };
        for field in &class_node.fields {
            for dependency_alias in module.imports.keys() {
                for dependency_class in CONTRACT_CLASSES {
                    if annotation_contains_dependency(
                        module,
                        &field.annotation,
                        dependency_alias,
                        dependency_class,
                    ) {
                        requirements
                            .entry((dependency_alias.clone(), (*dependency_class).to_string()))
                            .or_insert_with(BTreeSet::new)
                            .insert("annotation".to_string());
                    }
                }
            }
        }
    }
    for call in &module.initialize_calls {
        requirements
            .entry((call.alias.clone(), "Algorithm".to_string()))
            .or_insert_with(BTreeSet::new)
            .insert("initialize_call".to_string());
        if call.uses_parent_config && !call.local_child_config {
            requirements
                .entry((call.alias.clone(), "InitializeConfig".to_string()))
                .or_insert_with(BTreeSet::new)
                .insert("initialize_parent_config".to_string());
        }
    }
    requirements
}

fn dependency_module(
    module: &ModuleAst,
    alias: &str,
    algorithm_module_names: &BTreeSet<String>,
) -> String {
    let Some(import) = module.imports.get(alias) else {
        return alias.to_string();
    };
    let candidates = import_candidate_modules(&module.module, import);
    candidates
        .iter()
        .find(|candidate| algorithm_module_names.contains(*candidate))
        .cloned()
        .or_else(|| candidates.last().cloned())
        .unwrap_or_else(|| import.module.trim_start_matches('.').to_string())
}

fn import_candidate_modules(current_module: &str, import: &ImportAst) -> Vec<String> {
    if import.level > 0 {
        let base = resolve_relative_import(current_module, import.level, &import.from_module);
        if let Some(base) = base {
            let mut candidates = vec![base.clone()];
            if !import.imported_name.is_empty() && import.imported_name != "*" {
                candidates.push(format!("{base}.{}", import.imported_name));
            }
            return candidates;
        }
        return Vec::new();
    }
    if !import.from_module.is_empty() {
        let mut candidates = vec![import.from_module.clone()];
        if !import.imported_name.is_empty() && import.imported_name != "*" {
            candidates.push(format!("{}.{}", import.from_module, import.imported_name));
        }
        return candidates;
    }
    vec![import.module.clone()]
}

fn resolve_relative_import(
    current_module: &str,
    level: usize,
    from_module: &str,
) -> Option<String> {
    let mut package = current_module
        .split('.')
        .map(str::to_string)
        .collect::<Vec<_>>();
    package.pop();
    let drop_count = level.saturating_sub(1);
    if drop_count > package.len() {
        return None;
    }
    package.truncate(package.len() - drop_count);
    if !from_module.is_empty() {
        package.extend(from_module.split('.').map(str::to_string));
    }
    (!package.is_empty()).then(|| package.join("."))
}

fn annotation_contains_dependency(
    module: &ModuleAst,
    annotation: &str,
    dependency_alias: &str,
    dependency_class: &str,
) -> bool {
    let required = format!("{dependency_alias}.{dependency_class}");
    annotation.contains(&required)
        || expand_annotation(annotation, &module.aliases).contains(&required)
}

fn class_annotations_contain(
    module: &ModuleAst,
    class_node: &ClassAst,
    dependency_alias: &str,
    dependency_class: &str,
) -> bool {
    class_node.fields.iter().any(|field| {
        annotation_contains_dependency(
            module,
            &field.annotation,
            dependency_alias,
            dependency_class,
        )
    })
}

fn expand_annotation(annotation: &str, aliases: &BTreeMap<String, String>) -> String {
    let mut current = annotation.to_string();
    let mut seen = BTreeSet::new();
    while let Some(next) = aliases.get(&current) {
        if !seen.insert(current.clone()) {
            break;
        }
        current = next.clone();
    }
    current
}

fn nested_field_detail(
    module: &ModuleAst,
    class_node: &ClassAst,
    dependency_alias: &str,
    dependency_class: &str,
) -> String {
    let field_hint = dependency_alias.to_lowercase();
    let generic = format!("amp.{dependency_class}");
    if let Some(field) = class_node.fields.iter().find(|field| {
        field.name.to_lowercase().contains(&field_hint)
            && (field.annotation == "Any"
                || field.annotation.contains(&generic)
                || expand_annotation(&field.annotation, &module.aliases).contains(&generic))
    }) {
        return format!(
            "field-{}-uses-{}; annotate as {}.{}",
            field.name, field.annotation, dependency_alias, dependency_class
        );
    }
    format!("add-field-annotated-{dependency_alias}.{dependency_class}")
}

fn analyze_legacy_stopping_usage(module: &ModuleAst) -> Vec<Finding> {
    let mut findings = Vec::new();
    if let Some(class_node) = module.classes.get("SolveConfig") {
        for field in &class_node.fields {
            if STOPPING_POLICY_TYPES.iter().any(|name| {
                annotation_mentions(module, &field.annotation, name)
                    && !module_defines_name(module, name)
            }) {
                findings.push(Finding::new(&module.path, field.line, "legacy_stopping_policy_field", &field.name, "use imported stopping.SolveConfig so the nested algorithm contract is inferred"));
            }
        }
    }
    for call in &module.calls {
        if STOPPING_PRIMITIVE_CALLS.iter().any(|name| {
            call.name.ends_with(&format!(".{name}"))
                || (call.name == *name && !module_defines_name(module, name))
        }) {
            findings.push(Finding::new(
                &module.path,
                call.line,
                "stopping_primitive_direct_call",
                &call.name,
                "call the configured stopping object and record stopping.Info",
            ));
        }
    }
    findings
}

fn module_defines_name(module: &ModuleAst, name: &str) -> bool {
    module.public_definitions.contains_key(name) || module.classes.contains_key(name)
}

fn annotation_mentions(module: &ModuleAst, annotation: &str, needle: &str) -> bool {
    annotation.contains(needle) || expand_annotation(annotation, &module.aliases).contains(needle)
}

fn render_report(report: &Report) {
    match report.format {
        OutputFormat::Json => {
            let payload = JsonReport {
                summary: JsonSummary {
                    files: report.files,
                    algorithm_modules: report.algorithm_modules.len(),
                    findings: report.findings.len(),
                    parse_errors: report.parse_errors.len(),
                    status: if report.findings.is_empty() && report.parse_errors.is_empty() {
                        "pass"
                    } else {
                        "fail"
                    },
                },
                algorithm_modules: &report.algorithm_modules,
                modules: &report.modules,
                parse_errors: &report.parse_errors,
                findings: report
                    .findings
                    .iter()
                    .map(|finding| JsonFinding {
                        path: &finding.path,
                        line: finding.line,
                        kind: &finding.kind,
                        subject: &finding.subject,
                        detail: &finding.detail,
                    })
                    .collect(),
            };
            println!(
                "{}",
                serde_json::to_string_pretty(&payload).expect("json payload serializes")
            );
        }
        OutputFormat::Text => {
            for error in &report.parse_errors {
                println!(
                    "PY_ALGORITHM_CONTRACT_PARSE_ERROR={}:{}:parseable",
                    error.path, error.line
                );
            }
            for finding in &report.findings {
                println!("{}", finding.render());
            }
            println!("PY_ALGORITHM_CONTRACT_FILES={}", report.files);
            println!(
                "PY_ALGORITHM_CONTRACT_MODULES={}",
                report.algorithm_modules.len()
            );
            println!("PY_ALGORITHM_CONTRACT_FINDINGS={}", report.findings.len());
            println!(
                "PY_ALGORITHM_CONTRACT_PARSE_ERRORS={}",
                report.parse_errors.len()
            );
            println!(
                "PY_ALGORITHM_CONTRACT={}",
                if report.findings.is_empty() && report.parse_errors.is_empty() {
                    "pass"
                } else {
                    "fail"
                }
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn field(name: &str, annotation: &str) -> FieldAst {
        FieldAst {
            name: name.to_string(),
            annotation: annotation.to_string(),
            line: 10,
        }
    }

    fn class(line: usize, fields: Vec<FieldAst>, methods: &[&str]) -> ClassAst {
        ClassAst {
            line,
            bases: Vec::new(),
            fields,
            methods: methods.iter().map(|name| (*name).to_string()).collect(),
        }
    }

    fn algorithm_module() -> ModuleAst {
        let public_definitions = EXPECTED_PUBLIC_NAMES
            .iter()
            .map(|name| {
                (
                    (*name).to_string(),
                    PublicDefinitionAst {
                        line: 1,
                        kind: if *name == "Info" || *name == "Algorithm" {
                            "class".to_string()
                        } else {
                            "function".to_string()
                        },
                    },
                )
            })
            .collect();
        ModuleAst {
            path: "python/pkg/parent.py".to_string(),
            module: "python.pkg.parent".to_string(),
            imports_amp: true,
            public_definitions,
            all_state: AllState::Literal,
            all_names: EXPECTED_PUBLIC_NAMES
                .iter()
                .map(|name| (*name).to_string())
                .collect(),
            all_line: 1,
            imports: BTreeMap::from([(
                "child".to_string(),
                ImportAst {
                    module: ".child".to_string(),
                    from_module: String::new(),
                    imported_name: "child".to_string(),
                    level: 1,
                    line: 1,
                },
            )]),
            aliases: BTreeMap::new(),
            classes: BTreeMap::from([
                (
                    "InitializeConfig".to_string(),
                    class(
                        3,
                        vec![field("child_initialize", "child.InitializeConfig")],
                        &[],
                    ),
                ),
                (
                    "SolveConfig".to_string(),
                    class(6, vec![field("child_solve", "child.SolveConfig")], &[]),
                ),
                ("Problem".to_string(), class(9, Vec::new(), &[])),
                ("State".to_string(), class(12, Vec::new(), &[])),
                ("Answer".to_string(), class(15, Vec::new(), &[])),
                ("Info".to_string(), class(18, Vec::new(), &[])),
                (
                    "Algorithm".to_string(),
                    class(
                        21,
                        vec![field("child_algorithm", "child.Algorithm")],
                        &["__call__"],
                    ),
                ),
            ]),
            alias_attrs: BTreeMap::new(),
            calls: Vec::new(),
            references: Vec::new(),
            initialize_calls: vec![InitializeCallAst {
                alias: "child".to_string(),
                line: 30,
                uses_parent_config: true,
                local_child_config: false,
            }],
        }
    }

    #[test]
    fn compliant_nested_contract_passes_and_records_sources() {
        let (findings, reports) = analyze_modules(&[algorithm_module()]);
        assert!(findings.is_empty());
        assert_eq!(
            reports[0].dependencies[0].contract_classes,
            vec!["Algorithm", "InitializeConfig", "SolveConfig"]
        );
        assert_eq!(
            reports[0].dependencies[0].sources,
            vec!["annotation", "initialize_call", "initialize_parent_config"]
        );
    }

    #[test]
    fn local_child_config_does_not_require_parent_initialize_config() {
        let mut module = algorithm_module();
        module
            .classes
            .get_mut("InitializeConfig")
            .unwrap()
            .fields
            .clear();
        module.initialize_calls[0].uses_parent_config = false;
        module.initialize_calls[0].local_child_config = true;
        let (findings, reports) = analyze_modules(&[module]);
        assert!(!findings
            .iter()
            .any(|finding| finding.subject == "child.InitializeConfig"));
        assert_eq!(
            reports[0].dependencies[0].contract_classes,
            vec!["Algorithm", "SolveConfig"]
        );
    }

    #[test]
    fn protocol_only_import_is_one_finding_and_not_a_module() {
        let module = ModuleAst {
            path: "helper.py".to_string(),
            module: "helper".to_string(),
            imports_amp: true,
            public_definitions: BTreeMap::new(),
            all_state: AllState::Missing,
            all_names: Vec::new(),
            all_line: 1,
            imports: BTreeMap::new(),
            aliases: BTreeMap::new(),
            classes: BTreeMap::new(),
            alias_attrs: BTreeMap::new(),
            calls: Vec::new(),
            references: Vec::new(),
            initialize_calls: Vec::new(),
        };
        let (findings, reports) = analyze_modules(&[module]);
        assert_eq!(reports.len(), 0);
        assert_eq!(findings[0].kind, "non_algorithm_protocol_import");
    }

    #[test]
    fn glob_matching_matches_fnmatchcase_shapes() {
        assert!(fnmatchcase("pkg/generated/a.py", "pkg/generated/*.py"));
        assert!(fnmatchcase("pkg/a_generated.py", "*_generated.py"));
        assert!(!fnmatchcase("pkg/keep.py", "*_generated.py"));
    }
}
