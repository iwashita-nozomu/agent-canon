// @dependency-start
// contract implementation
// responsibility Finds duplicate Python function and class structures by normalized AST hash.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md Rust tool migration policy
// upstream implementation python_ast.rs shares native Python source, span, and expression-dump helpers
// downstream implementation ../../../../bin/agent-canon invokes this command through the CLI wrapper
// @dependency-end

use crate::python_ast::{
    ast_dump_expr, line_at_offset, module_name, node_line, normalize_python_newlines,
};
use rustpython_ast::{Ranged, Visitor};
use rustpython_parser::{ast, Parse};
use serde::Serialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
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
    "python/jax_util.egg-info",
];
const DEFAULT_MIN_TOKENS: usize = 8;
const DEFAULT_MAX_FINDINGS: usize = usize::MAX;

#[derive(Debug, PartialEq, Eq)]
struct Args {
    root: PathBuf,
    paths: Vec<String>,
    excludes: Vec<String>,
    min_tokens: usize,
    max_findings: usize,
    format: OutputFormat,
}

#[derive(Debug, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Block {
    path: String,
    module: String,
    line: usize,
    end_line: usize,
    kind: String,
    role: String,
    name: String,
    qualname: String,
    parent_kind: Option<String>,
    parent_name: Option<String>,
    parameter_count: usize,
    decorators_hash: String,
    bases_hash: String,
    import_hash: String,
    structure_hash: String,
    context_hash: String,
    token_count: usize,
    public_api: bool,
    calls: Vec<CallRef>,
    references: Vec<CallRef>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct CallRef {
    name: String,
    line: usize,
}

#[derive(Debug, Clone, Serialize)]
struct ExtractedBlock {
    path: String,
    module: String,
    line: usize,
    end_line: usize,
    kind: String,
    name: String,
    qualname: String,
    parent_kind: Option<String>,
    parent_name: Option<String>,
    role: String,
    public_api: bool,
    parameter_count: usize,
    decorators: Vec<String>,
    bases: Vec<String>,
    imports: Vec<Value>,
    calls: Vec<CallRef>,
    references: Vec<CallRef>,
    canonical: Value,
}

struct ParsedModule {
    relative_path: String,
    module: String,
    source: String,
    suite: ast::Suite,
}

struct AstExtraction {
    blocks: Vec<ExtractedBlock>,
    #[cfg(test)]
    protocol_symbol_count: usize,
    parse_error_count: usize,
}

#[derive(Debug, PartialEq, Eq)]
struct DuplicateGroup {
    structure_hash: String,
    role: String,
    kind: String,
    parameter_count: usize,
    token_count: usize,
    module_scope: ModuleScope,
    import_scope: ImportScope,
    decorator_scope: DecoratorScope,
    base_scope: BaseScope,
    blocks: Vec<Block>,
}

#[derive(Debug, PartialEq, Eq)]
struct Analysis {
    groups: Vec<DuplicateGroup>,
    single_callers: Vec<SingleCallerFinding>,
    single_callees: Vec<SingleCalleeFinding>,
    analyzed_files: Vec<String>,
}

#[derive(Debug, PartialEq, Eq)]
struct SingleCallerFinding {
    target: Block,
    caller: CallerEvidence,
    call_site_count: usize,
    similar_callers: Vec<SimilarCallerEvidence>,
    hash: String,
}

#[derive(Debug, PartialEq, Eq)]
struct CallerEvidence {
    path: String,
    module: String,
    qualname: String,
    line: usize,
    end_line: usize,
    call_lines: Vec<usize>,
}

#[derive(Debug, PartialEq, Eq)]
struct SingleCalleeFinding {
    caller: Block,
    callee: CalleeEvidence,
    call_site_count: usize,
    hash: String,
}

#[derive(Debug, PartialEq, Eq)]
struct CalleeEvidence {
    path: String,
    module: String,
    qualname: String,
    line: usize,
    end_line: usize,
    call_lines: Vec<usize>,
}

#[derive(Debug, PartialEq, Eq)]
struct SimilarCallerEvidence {
    path: String,
    module: String,
    qualname: String,
    line: usize,
    end_line: usize,
    token_count: usize,
    structure_hash: String,
    parent_scope: String,
    score: usize,
    shared_call_count: usize,
    shared_profile: Vec<String>,
    reason_codes: Vec<String>,
}

#[derive(Debug, PartialEq, Eq)]
enum ModuleScope {
    SameModule,
    CrossModule,
}

#[derive(Debug, PartialEq, Eq)]
enum ImportScope {
    SameImports,
    MixedImports,
}

#[derive(Debug, PartialEq, Eq)]
enum DecoratorScope {
    SameDecorators,
    MixedDecorators,
}

#[derive(Debug, PartialEq, Eq)]
enum BaseScope {
    SameBases,
    MixedBases,
}

pub fn run(args: &[String]) -> i32 {
    match Args::parse(args) {
        Ok(parsed) => match analyze(&parsed) {
            Ok(analysis) => render(analysis, &parsed),
            Err(message) => {
                eprintln!("PY_STRUCTURE_HASH=fail");
                eprintln!("PY_STRUCTURE_HASH_FINDING=analysis-error:{message}");
                2
            }
        },
        Err(message) => {
            eprintln!("PY_STRUCTURE_HASH=fail");
            eprintln!("PY_STRUCTURE_HASH_FINDING=invalid-arguments:{message}");
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
        let mut min_tokens = DEFAULT_MIN_TOKENS;
        let mut max_findings = DEFAULT_MAX_FINDINGS;
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
                "--min-tokens" => {
                    min_tokens = positive_usize(&value_after(args, index, "--min-tokens")?)?;
                    index += 2;
                }
                "--max-findings" => {
                    max_findings = positive_usize(&value_after(args, index, "--max-findings")?)?;
                    index += 2;
                }
                "--format" => {
                    let value = value_after(args, index, "--format")?;
                    format = match value.as_str() {
                        "text" => OutputFormat::Text,
                        "json" => OutputFormat::Json,
                        _ => return Err(format!("--format must be text or json, got {value}")),
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
            min_tokens,
            max_findings,
            format,
        })
    }
}

fn value_after(args: &[String], index: usize, flag: &str) -> Result<String, String> {
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("{flag} requires a value"))
}

fn positive_usize(value: &str) -> Result<usize, String> {
    let parsed = value
        .parse::<usize>()
        .map_err(|_| format!("expected positive integer, got {value}"))?;
    if parsed == 0 {
        return Err("expected positive integer greater than zero".to_string());
    }
    Ok(parsed)
}

fn analyze(args: &Args) -> Result<Analysis, String> {
    let root = resolve_like_cwd(&args.root);
    // File discovery canonicalizes paths; use the same identity for their source root.
    let root = fs::canonicalize(&root).unwrap_or(root);
    let files = source_files(&root, &args.paths, &args.excludes);
    let files = expand_with_repo_import_neighborhood(&root, files, &args.excludes);
    let analyzed_files = files
        .iter()
        .map(|path| relative_path(&root, path))
        .collect::<Vec<_>>();
    let extraction = extract_ast_blocks(&root, &files)?;
    if extraction.parse_error_count > 0 {
        eprintln!(
            "PY_STRUCTURE_HASH_PARSE_ERRORS={}",
            extraction.parse_error_count
        );
    }
    let mut all_blocks = Vec::new();
    let mut buckets: BTreeMap<String, Vec<Block>> = BTreeMap::new();
    for extracted in extraction.blocks {
        let block = block_from_extracted(extracted)?;
        all_blocks.push(block.clone());
        if block.token_count < args.min_tokens {
            continue;
        }
        buckets
            .entry(block.structure_hash.clone())
            .or_default()
            .push(block);
    }

    let mut groups = buckets
        .into_iter()
        .filter_map(|(structure_hash, blocks)| {
            if blocks.len() < 2 {
                return None;
            }
            let first = blocks.first()?;
            Some(DuplicateGroup {
                structure_hash,
                role: first.role.clone(),
                kind: first.kind.clone(),
                parameter_count: first.parameter_count,
                token_count: first.token_count,
                module_scope: module_scope(&blocks),
                import_scope: import_scope(&blocks),
                decorator_scope: decorator_scope(&blocks),
                base_scope: base_scope(&blocks),
                blocks,
            })
        })
        .collect::<Vec<_>>();
    groups.sort_by(|left, right| {
        right
            .blocks
            .len()
            .cmp(&left.blocks.len())
            .then_with(|| right.token_count.cmp(&left.token_count))
            .then_with(|| left.structure_hash.cmp(&right.structure_hash))
    });
    groups.truncate(args.max_findings);
    let mut single_callers = single_caller_findings(&all_blocks, args.min_tokens);
    single_callers.sort_by(|left, right| {
        right
            .target
            .token_count
            .cmp(&left.target.token_count)
            .then_with(|| left.hash.cmp(&right.hash))
    });
    single_callers.truncate(args.max_findings);
    let mut single_callees = single_callee_findings(&all_blocks, args.min_tokens);
    single_callees.sort_by(|left, right| {
        right
            .caller
            .token_count
            .cmp(&left.caller.token_count)
            .then_with(|| left.hash.cmp(&right.hash))
    });
    single_callees.truncate(args.max_findings);
    Ok(Analysis {
        groups,
        single_callers,
        single_callees,
        analyzed_files,
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

fn expand_with_repo_import_neighborhood(
    root: &Path,
    initial_files: Vec<PathBuf>,
    excludes: &[String],
) -> Vec<PathBuf> {
    let mut files = initial_files
        .into_iter()
        .map(|path| fs::canonicalize(&path).unwrap_or(path))
        .collect::<BTreeSet<_>>();
    let all_repo_files = source_files(root, &[], excludes);
    let import_targets = all_repo_files
        .iter()
        .map(|path| {
            (
                fs::canonicalize(path).unwrap_or_else(|_| path.clone()),
                repo_import_targets(root, path, excludes)
                    .into_iter()
                    .collect::<BTreeSet<_>>(),
            )
        })
        .collect::<BTreeMap<_, _>>();

    loop {
        let before = files.len();
        for path in files.clone() {
            if let Some(targets) = import_targets.get(&path) {
                files.extend(targets.iter().cloned());
            }
        }
        for (path, targets) in &import_targets {
            if files.contains(path) {
                continue;
            }
            if targets.iter().any(|target| files.contains(target)) {
                files.insert(path.clone());
            }
        }
        if files.len() == before {
            break;
        }
    }
    files.into_iter().collect()
}

fn repo_import_targets(root: &Path, path: &Path, excludes: &[String]) -> Vec<PathBuf> {
    let Ok(text) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let Some(current_module) = module_name_from_path(root, path) else {
        return Vec::new();
    };
    let mut targets = BTreeSet::new();
    for fact in collect_import_facts(&text) {
        for module in imported_modules(&current_module, &fact) {
            for candidate in module_file_candidates(root, &module) {
                if !excluded(root, &candidate, excludes) {
                    targets.insert(fs::canonicalize(&candidate).unwrap_or(candidate));
                }
            }
        }
    }
    targets.into_iter().collect()
}

fn collect_import_facts(text: &str) -> Vec<String> {
    let mut facts = Vec::new();
    let mut pending_from_module: Option<String> = None;
    for line in text.lines() {
        let trimmed = line.trim();
        if let Some(module) = pending_from_module.clone() {
            add_from_import_names(&mut facts, &module, trimmed);
            if trimmed.contains(')') {
                pending_from_module = None;
            }
            continue;
        }
        if trimmed.starts_with("import ") {
            let rest = trimmed
                .trim_start_matches("import ")
                .split('#')
                .next()
                .unwrap_or("");
            for item in rest.split(',') {
                let name = item.split_whitespace().next().unwrap_or("");
                if !name.is_empty() {
                    facts.push(format!("import:{name}"));
                }
            }
        } else if trimmed.starts_with("from ") {
            let rest = trimmed.trim_start_matches("from ");
            if let Some((module, names)) = rest.split_once(" import ") {
                let module = module.trim();
                if names.trim().starts_with('(') && !names.contains(')') {
                    pending_from_module = Some(module.to_string());
                } else {
                    add_from_import_names(&mut facts, module, names);
                }
            }
        }
    }
    facts.sort();
    facts.dedup();
    facts
}

fn add_from_import_names(facts: &mut Vec<String>, module: &str, names: &str) {
    let cleaned = names
        .split('#')
        .next()
        .unwrap_or("")
        .trim()
        .trim_start_matches('(')
        .trim_end_matches(')')
        .trim();
    for item in cleaned.split(',') {
        let name = item.split_whitespace().next().unwrap_or("");
        if !module.is_empty() && !name.is_empty() && name != "(" && name != ")" {
            facts.push(format!("from:{module}:{name}"));
        }
    }
}

fn imported_modules(current_module: &str, fact: &str) -> Vec<String> {
    if let Some(module) = fact.strip_prefix("import:") {
        return vec![module.to_string()];
    }
    let Some(rest) = fact.strip_prefix("from:") else {
        return Vec::new();
    };
    let Some((module, name)) = rest.split_once(':') else {
        return Vec::new();
    };
    let Some(resolved) = resolve_import_module(current_module, module) else {
        return Vec::new();
    };
    let mut modules = vec![resolved.clone()];
    if !name.is_empty() && name != "*" {
        modules.push(format!("{resolved}.{name}"));
    }
    modules
}

fn resolve_import_module(current_module: &str, module: &str) -> Option<String> {
    if !module.starts_with('.') {
        return Some(module.to_string());
    }
    let dots = module.chars().take_while(|value| *value == '.').count();
    let suffix = module.trim_start_matches('.');
    let mut package = current_module
        .split('.')
        .map(str::to_string)
        .collect::<Vec<_>>();
    package.pop();
    let drop_count = dots.saturating_sub(1);
    if drop_count > package.len() {
        return None;
    }
    let keep = package.len() - drop_count;
    package.truncate(keep);
    if !suffix.is_empty() {
        package.extend(suffix.split('.').map(str::to_string));
    }
    if package.is_empty() {
        None
    } else {
        Some(package.join("."))
    }
}

fn module_name_from_path(root: &Path, path: &Path) -> Option<String> {
    let mut relative = path.strip_prefix(root).ok()?.with_extension("");
    if relative.file_name().and_then(|value| value.to_str()) == Some("__init__") {
        relative = relative.parent()?.to_path_buf();
    }
    Some(
        relative
            .components()
            .map(|component| component.as_os_str().to_string_lossy())
            .collect::<Vec<_>>()
            .join("."),
    )
}

fn module_file_candidates(root: &Path, module: &str) -> Vec<PathBuf> {
    let relative = module.replace('.', "/");
    let mut candidates = Vec::new();
    for source_root in ["", "python", "src"] {
        let base = if source_root.is_empty() {
            root.to_path_buf()
        } else {
            root.join(source_root)
        };
        candidates.push(base.join(format!("{relative}.py")));
        candidates.push(base.join(&relative).join("__init__.py"));
    }
    candidates
        .into_iter()
        .filter(|path| exact_file_exists(path))
        .collect()
}

fn exact_file_exists(path: &Path) -> bool {
    if !path.is_file() {
        return false;
    }
    let Some(parent) = path.parent() else {
        return false;
    };
    let Some(file_name) = path.file_name() else {
        return false;
    };
    let Ok(entries) = fs::read_dir(parent) else {
        return false;
    };
    entries
        .flatten()
        .any(|entry| entry.file_name() == file_name)
}

fn relative_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn collect_python_files(
    root: &Path,
    target: &Path,
    excludes: &[String],
    files: &mut BTreeSet<PathBuf>,
) {
    if excluded(root, target, excludes) {
        return;
    }
    if target.is_file() {
        if target.extension().and_then(|value| value.to_str()) == Some("py") {
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
    excludes.iter().any(|pattern| {
        let pattern = pattern.trim().trim_matches('/');
        !pattern.is_empty()
            && (relative_text == pattern
                || relative_text.starts_with(&format!("{pattern}/"))
                || relative_text.split('/').any(|part| part == pattern))
    })
}

fn extract_ast_blocks(root: &Path, files: &[PathBuf]) -> Result<AstExtraction, String> {
    let mut modules = Vec::new();
    let mut parse_error_count = 0;
    for path in files {
        let source = match fs::read_to_string(path) {
            Ok(source) => normalize_python_newlines(&source),
            Err(_) => {
                parse_error_count += 1;
                continue;
            }
        };
        let source_path = path.to_string_lossy();
        let suite = match ast::Suite::parse(&source, source_path.as_ref()) {
            Ok(suite) => suite,
            Err(_) => {
                parse_error_count += 1;
                continue;
            }
        };
        let relative_path = relative_path(root, path);
        let module = module_name(Path::new(&relative_path));
        modules.push(ParsedModule {
            relative_path,
            module,
            source,
            suite,
        });
    }

    let protocol_names = build_protocol_names(&modules);
    #[cfg(test)]
    let protocol_symbol_count = protocol_names.len();
    let mut blocks = Vec::new();
    for module in &modules {
        let imports = import_facts(&module.suite);
        let module_all = module_all_names(&module.suite);
        let mut collector = BlockCollector {
            path: module.relative_path.clone(),
            module: module.module.clone(),
            source: &module.source,
            imports: &imports,
            module_all: &module_all,
            protocol_names: &protocol_names,
            stack: Vec::new(),
            blocks: Vec::new(),
        };
        for statement in &module.suite {
            collector.visit_stmt(statement.clone());
        }
        blocks.extend(collector.blocks);
    }

    Ok(AstExtraction {
        blocks,
        #[cfg(test)]
        protocol_symbol_count,
        parse_error_count,
    })
}

fn canonical_node(name: &str, fields: Vec<(&'static str, Value)>) -> Value {
    let fields = fields
        .into_iter()
        .filter_map(|(field, value)| {
            if matches!(
                field,
                "name"
                    | "id"
                    | "arg"
                    | "attr"
                    | "asname"
                    | "lineno"
                    | "col_offset"
                    | "end_lineno"
                    | "end_col_offset"
                    | "ctx"
                    | "type_comment"
            ) {
                None
            } else if matches!(field, "returns" | "annotation") {
                Some(json!([field, "TYPE"]))
            } else {
                Some(json!([field, value]))
            }
        })
        .collect::<Vec<_>>();
    json!([name, fields])
}

fn canonical_array<T>(items: &[T], canonicalize: impl Fn(&T) -> Value) -> Value {
    Value::Array(items.iter().map(canonicalize).collect())
}

fn canonical_optional<T>(item: Option<&T>, canonicalize: impl Fn(&T) -> Value) -> Value {
    item.map(canonicalize).unwrap_or(Value::Null)
}

fn canonical_string(_value: &str) -> Value {
    json!("STR")
}

fn canonical_constant_value(value: &ast::Constant) -> Value {
    match value {
        ast::Constant::None => Value::Null,
        ast::Constant::Bool(_) | ast::Constant::Int(_) | ast::Constant::Float(_) => json!("NUM"),
        ast::Constant::Complex { .. } => json!("NUM"),
        ast::Constant::Str(_) => json!("STR"),
        ast::Constant::Bytes(_) => json!("BYTES"),
        ast::Constant::Tuple(items) => canonical_array(items, canonical_constant_value),
        ast::Constant::Ellipsis => json!("ellipsis"),
    }
}

fn canonical_expr(expr: &ast::Expr) -> Value {
    use ast::Expr as E;
    match expr {
        E::BoolOp(node) => canonical_node(
            "BoolOp",
            vec![
                ("op", json!([format!("{:?}", node.op), []])),
                ("values", canonical_array(&node.values, canonical_expr)),
            ],
        ),
        E::NamedExpr(node) => canonical_node(
            "NamedExpr",
            vec![
                ("target", canonical_expr(&node.target)),
                ("value", canonical_expr(&node.value)),
            ],
        ),
        E::BinOp(node) => canonical_node(
            "BinOp",
            vec![
                ("left", canonical_expr(&node.left)),
                ("op", json!([format!("{:?}", node.op), []])),
                ("right", canonical_expr(&node.right)),
            ],
        ),
        E::UnaryOp(node) => canonical_node(
            "UnaryOp",
            vec![
                ("op", json!([format!("{:?}", node.op), []])),
                ("operand", canonical_expr(&node.operand)),
            ],
        ),
        E::Lambda(node) => canonical_node(
            "Lambda",
            vec![
                ("args", canonical_arguments(&node.args)),
                ("body", canonical_expr(&node.body)),
            ],
        ),
        E::IfExp(node) => canonical_node(
            "IfExp",
            vec![
                ("test", canonical_expr(&node.test)),
                ("body", canonical_expr(&node.body)),
                ("orelse", canonical_expr(&node.orelse)),
            ],
        ),
        E::Dict(node) => canonical_node(
            "Dict",
            vec![
                (
                    "keys",
                    Value::Array(
                        node.keys
                            .iter()
                            .map(|key| canonical_optional(key.as_ref(), canonical_expr))
                            .collect(),
                    ),
                ),
                ("values", canonical_array(&node.values, canonical_expr)),
            ],
        ),
        E::Set(node) => canonical_node(
            "Set",
            vec![("elts", canonical_array(&node.elts, canonical_expr))],
        ),
        E::ListComp(node) => canonical_node(
            "ListComp",
            vec![
                ("elt", canonical_expr(&node.elt)),
                (
                    "generators",
                    canonical_array(&node.generators, canonical_comprehension),
                ),
            ],
        ),
        E::SetComp(node) => canonical_node(
            "SetComp",
            vec![
                ("elt", canonical_expr(&node.elt)),
                (
                    "generators",
                    canonical_array(&node.generators, canonical_comprehension),
                ),
            ],
        ),
        E::DictComp(node) => canonical_node(
            "DictComp",
            vec![
                ("key", canonical_expr(&node.key)),
                ("value", canonical_expr(&node.value)),
                (
                    "generators",
                    canonical_array(&node.generators, canonical_comprehension),
                ),
            ],
        ),
        E::GeneratorExp(node) => canonical_node(
            "GeneratorExp",
            vec![
                ("elt", canonical_expr(&node.elt)),
                (
                    "generators",
                    canonical_array(&node.generators, canonical_comprehension),
                ),
            ],
        ),
        E::Await(node) => canonical_node("Await", vec![("value", canonical_expr(&node.value))]),
        E::Yield(node) => canonical_node(
            "Yield",
            vec![(
                "value",
                canonical_optional(node.value.as_deref(), canonical_expr),
            )],
        ),
        E::YieldFrom(node) => {
            canonical_node("YieldFrom", vec![("value", canonical_expr(&node.value))])
        }
        E::Compare(node) => canonical_node(
            "Compare",
            vec![
                ("left", canonical_expr(&node.left)),
                (
                    "ops",
                    Value::Array(
                        node.ops
                            .iter()
                            .map(|op| json!([format!("{op:?}"), []]))
                            .collect(),
                    ),
                ),
                (
                    "comparators",
                    canonical_array(&node.comparators, canonical_expr),
                ),
            ],
        ),
        E::Call(node) => canonical_node(
            "Call",
            vec![
                ("func", canonical_expr(&node.func)),
                ("args", canonical_array(&node.args, canonical_expr)),
                (
                    "keywords",
                    canonical_array(&node.keywords, canonical_keyword),
                ),
            ],
        ),
        E::FormattedValue(node) => canonical_node(
            "FormattedValue",
            vec![
                ("value", canonical_expr(&node.value)),
                ("conversion", json!("NUM")),
                (
                    "format_spec",
                    canonical_optional(node.format_spec.as_deref(), canonical_expr),
                ),
            ],
        ),
        E::JoinedStr(node) => canonical_node(
            "JoinedStr",
            vec![("values", canonical_array(&node.values, canonical_expr))],
        ),
        E::Constant(node) => canonical_node(
            "Constant",
            vec![
                ("value", canonical_constant_value(&node.value)),
                (
                    "kind",
                    node.kind
                        .as_deref()
                        .map(canonical_string)
                        .unwrap_or(Value::Null),
                ),
            ],
        ),
        E::Attribute(node) => canonical_node(
            "Attribute",
            vec![
                ("value", canonical_expr(&node.value)),
                ("attr", canonical_string(node.attr.as_str())),
                ("ctx", Value::Null),
            ],
        ),
        E::Subscript(node) => canonical_node(
            "Subscript",
            vec![
                ("value", canonical_expr(&node.value)),
                ("slice", canonical_expr(&node.slice)),
                ("ctx", Value::Null),
            ],
        ),
        E::Starred(node) => canonical_node(
            "Starred",
            vec![("value", canonical_expr(&node.value)), ("ctx", Value::Null)],
        ),
        E::Name(node) => canonical_node(
            "Name",
            vec![
                ("id", canonical_string(node.id.as_str())),
                ("ctx", Value::Null),
            ],
        ),
        E::List(node) => canonical_node(
            "List",
            vec![
                ("elts", canonical_array(&node.elts, canonical_expr)),
                ("ctx", Value::Null),
            ],
        ),
        E::Tuple(node) => canonical_node(
            "Tuple",
            vec![
                ("elts", canonical_array(&node.elts, canonical_expr)),
                ("ctx", Value::Null),
            ],
        ),
        E::Slice(node) => canonical_node(
            "Slice",
            vec![
                (
                    "lower",
                    canonical_optional(node.lower.as_deref(), canonical_expr),
                ),
                (
                    "upper",
                    canonical_optional(node.upper.as_deref(), canonical_expr),
                ),
                (
                    "step",
                    canonical_optional(node.step.as_deref(), canonical_expr),
                ),
            ],
        ),
    }
}

fn canonical_comprehension(node: &ast::Comprehension) -> Value {
    canonical_node(
        "comprehension",
        vec![
            ("target", canonical_expr(&node.target)),
            ("iter", canonical_expr(&node.iter)),
            ("ifs", canonical_array(&node.ifs, canonical_expr)),
            ("is_async", json!("NUM")),
        ],
    )
}

fn canonical_keyword(node: &ast::Keyword) -> Value {
    canonical_node(
        "keyword",
        vec![
            (
                "arg",
                node.arg
                    .as_ref()
                    .map(|arg| canonical_string(arg.as_str()))
                    .unwrap_or(Value::Null),
            ),
            ("value", canonical_expr(&node.value)),
        ],
    )
}

fn canonical_arg(node: &ast::Arg) -> Value {
    canonical_node(
        "arg",
        vec![
            ("arg", canonical_string(node.arg.as_str())),
            (
                "annotation",
                node.annotation
                    .as_deref()
                    .map(canonical_expr)
                    .unwrap_or(Value::Null),
            ),
            (
                "type_comment",
                node.type_comment
                    .as_deref()
                    .map(canonical_string)
                    .unwrap_or(Value::Null),
            ),
        ],
    )
}

fn canonical_arguments(node: &ast::Arguments) -> Value {
    canonical_node(
        "arguments",
        vec![
            (
                "posonlyargs",
                canonical_array(&node.posonlyargs, |arg| canonical_arg(&arg.def)),
            ),
            (
                "args",
                canonical_array(&node.args, |arg| canonical_arg(&arg.def)),
            ),
            (
                "vararg",
                canonical_optional(node.vararg.as_deref(), canonical_arg),
            ),
            (
                "kwonlyargs",
                canonical_array(&node.kwonlyargs, |arg| canonical_arg(&arg.def)),
            ),
            (
                "kw_defaults",
                Value::Array(
                    node.kwonlyargs
                        .iter()
                        .map(|arg| canonical_optional(arg.default.as_deref(), canonical_expr))
                        .collect(),
                ),
            ),
            (
                "kwarg",
                canonical_optional(node.kwarg.as_deref(), canonical_arg),
            ),
            (
                "defaults",
                Value::Array(
                    node.posonlyargs
                        .iter()
                        .chain(&node.args)
                        .filter_map(|arg| arg.default.as_deref().map(canonical_expr))
                        .collect(),
                ),
            ),
        ],
    )
}

fn canonical_stmt(stmt: &ast::Stmt) -> Value {
    use ast::Stmt as S;
    match stmt {
        S::FunctionDef(node) => canonical_node(
            "FunctionDef",
            vec![
                ("name", canonical_string(node.name.as_str())),
                ("args", canonical_arguments(&node.args)),
                ("body", canonical_array(&node.body, canonical_stmt)),
                (
                    "decorator_list",
                    canonical_array(&node.decorator_list, canonical_expr),
                ),
                (
                    "returns",
                    canonical_optional(node.returns.as_deref(), canonical_expr),
                ),
                (
                    "type_comment",
                    node.type_comment
                        .as_deref()
                        .map(canonical_string)
                        .unwrap_or(Value::Null),
                ),
                (
                    "type_params",
                    canonical_array(&node.type_params, canonical_type_param),
                ),
            ],
        ),
        S::AsyncFunctionDef(node) => canonical_node(
            "AsyncFunctionDef",
            vec![
                ("name", canonical_string(node.name.as_str())),
                ("args", canonical_arguments(&node.args)),
                ("body", canonical_array(&node.body, canonical_stmt)),
                (
                    "decorator_list",
                    canonical_array(&node.decorator_list, canonical_expr),
                ),
                (
                    "returns",
                    canonical_optional(node.returns.as_deref(), canonical_expr),
                ),
                (
                    "type_comment",
                    node.type_comment
                        .as_deref()
                        .map(canonical_string)
                        .unwrap_or(Value::Null),
                ),
                (
                    "type_params",
                    canonical_array(&node.type_params, canonical_type_param),
                ),
            ],
        ),
        S::ClassDef(node) => canonical_node(
            "ClassDef",
            vec![
                ("name", canonical_string(node.name.as_str())),
                ("bases", canonical_array(&node.bases, canonical_expr)),
                (
                    "keywords",
                    canonical_array(&node.keywords, canonical_keyword),
                ),
                ("body", canonical_array(&node.body, canonical_stmt)),
                (
                    "decorator_list",
                    canonical_array(&node.decorator_list, canonical_expr),
                ),
                (
                    "type_params",
                    canonical_array(&node.type_params, canonical_type_param),
                ),
            ],
        ),
        S::Return(node) => canonical_node(
            "Return",
            vec![(
                "value",
                canonical_optional(node.value.as_deref(), canonical_expr),
            )],
        ),
        S::Delete(node) => canonical_node(
            "Delete",
            vec![("targets", canonical_array(&node.targets, canonical_expr))],
        ),
        S::Assign(node) => canonical_node(
            "Assign",
            vec![
                ("targets", canonical_array(&node.targets, canonical_expr)),
                ("value", canonical_expr(&node.value)),
                (
                    "type_comment",
                    node.type_comment
                        .as_deref()
                        .map(canonical_string)
                        .unwrap_or(Value::Null),
                ),
            ],
        ),
        S::TypeAlias(node) => canonical_node(
            "TypeAlias",
            vec![
                ("name", canonical_expr(&node.name)),
                (
                    "type_params",
                    canonical_array(&node.type_params, canonical_type_param),
                ),
                ("value", canonical_expr(&node.value)),
            ],
        ),
        S::AugAssign(node) => canonical_node(
            "AugAssign",
            vec![
                ("target", canonical_expr(&node.target)),
                ("op", json!([format!("{:?}", node.op), []])),
                ("value", canonical_expr(&node.value)),
            ],
        ),
        S::AnnAssign(node) => canonical_node(
            "AnnAssign",
            vec![
                ("target", canonical_expr(&node.target)),
                ("annotation", canonical_expr(&node.annotation)),
                (
                    "value",
                    canonical_optional(node.value.as_deref(), canonical_expr),
                ),
                ("simple", json!("NUM")),
            ],
        ),
        S::For(node) => canonical_for(
            "For",
            &node.target,
            &node.iter,
            &node.body,
            &node.orelse,
            node.type_comment.as_deref(),
        ),
        S::AsyncFor(node) => canonical_for(
            "AsyncFor",
            &node.target,
            &node.iter,
            &node.body,
            &node.orelse,
            node.type_comment.as_deref(),
        ),
        S::While(node) => canonical_node(
            "While",
            vec![
                ("test", canonical_expr(&node.test)),
                ("body", canonical_array(&node.body, canonical_stmt)),
                ("orelse", canonical_array(&node.orelse, canonical_stmt)),
            ],
        ),
        S::If(node) => canonical_node(
            "If",
            vec![
                ("test", canonical_expr(&node.test)),
                ("body", canonical_array(&node.body, canonical_stmt)),
                ("orelse", canonical_array(&node.orelse, canonical_stmt)),
            ],
        ),
        S::With(node) => canonical_with(
            "With",
            &node.items,
            &node.body,
            node.type_comment.as_deref(),
        ),
        S::AsyncWith(node) => canonical_with(
            "AsyncWith",
            &node.items,
            &node.body,
            node.type_comment.as_deref(),
        ),
        S::Match(node) => canonical_node(
            "Match",
            vec![
                ("subject", canonical_expr(&node.subject)),
                ("cases", canonical_array(&node.cases, canonical_match_case)),
            ],
        ),
        S::Raise(node) => canonical_node(
            "Raise",
            vec![
                (
                    "exc",
                    canonical_optional(node.exc.as_deref(), canonical_expr),
                ),
                (
                    "cause",
                    canonical_optional(node.cause.as_deref(), canonical_expr),
                ),
            ],
        ),
        S::Try(node) => canonical_try(
            "Try",
            &node.body,
            &node.handlers,
            &node.orelse,
            &node.finalbody,
        ),
        S::TryStar(node) => canonical_try(
            "TryStar",
            &node.body,
            &node.handlers,
            &node.orelse,
            &node.finalbody,
        ),
        S::Assert(node) => canonical_node(
            "Assert",
            vec![
                ("test", canonical_expr(&node.test)),
                (
                    "msg",
                    canonical_optional(node.msg.as_deref(), canonical_expr),
                ),
            ],
        ),
        S::Import(node) => canonical_node(
            "Import",
            vec![("names", canonical_array(&node.names, canonical_alias))],
        ),
        S::ImportFrom(node) => canonical_node(
            "ImportFrom",
            vec![
                (
                    "module",
                    node.module
                        .as_ref()
                        .map(|module| canonical_string(module.as_str()))
                        .unwrap_or(Value::Null),
                ),
                ("names", canonical_array(&node.names, canonical_alias)),
                // Python AST always has an integer level; RustPython uses None for absolute imports.
                ("level", json!("NUM")),
            ],
        ),
        S::Global(node) => canonical_node(
            "Global",
            vec![(
                "names",
                Value::Array(node.names.iter().map(|_| json!("STR")).collect()),
            )],
        ),
        S::Nonlocal(node) => canonical_node(
            "Nonlocal",
            vec![(
                "names",
                Value::Array(node.names.iter().map(|_| json!("STR")).collect()),
            )],
        ),
        S::Expr(node) => canonical_node("Expr", vec![("value", canonical_expr(&node.value))]),
        S::Pass(_) => canonical_node("Pass", vec![]),
        S::Break(_) => canonical_node("Break", vec![]),
        S::Continue(_) => canonical_node("Continue", vec![]),
    }
}

fn canonical_for(
    name: &str,
    target: &ast::Expr,
    iter: &ast::Expr,
    body: &[ast::Stmt],
    orelse: &[ast::Stmt],
    type_comment: Option<&str>,
) -> Value {
    canonical_node(
        name,
        vec![
            ("target", canonical_expr(target)),
            ("iter", canonical_expr(iter)),
            ("body", canonical_array(body, canonical_stmt)),
            ("orelse", canonical_array(orelse, canonical_stmt)),
            (
                "type_comment",
                type_comment.map(canonical_string).unwrap_or(Value::Null),
            ),
        ],
    )
}

fn canonical_with(
    name: &str,
    items: &[ast::WithItem],
    body: &[ast::Stmt],
    type_comment: Option<&str>,
) -> Value {
    canonical_node(
        name,
        vec![
            ("items", canonical_array(items, canonical_with_item)),
            ("body", canonical_array(body, canonical_stmt)),
            (
                "type_comment",
                type_comment.map(canonical_string).unwrap_or(Value::Null),
            ),
        ],
    )
}

fn canonical_try(
    name: &str,
    body: &[ast::Stmt],
    handlers: &[ast::ExceptHandler],
    orelse: &[ast::Stmt],
    finalbody: &[ast::Stmt],
) -> Value {
    canonical_node(
        name,
        vec![
            ("body", canonical_array(body, canonical_stmt)),
            (
                "handlers",
                canonical_array(handlers, canonical_except_handler),
            ),
            ("orelse", canonical_array(orelse, canonical_stmt)),
            ("finalbody", canonical_array(finalbody, canonical_stmt)),
        ],
    )
}

fn canonical_alias(node: &ast::Alias) -> Value {
    canonical_node(
        "alias",
        vec![
            ("name", canonical_string(node.name.as_str())),
            (
                "asname",
                node.asname
                    .as_ref()
                    .map(|name| canonical_string(name.as_str()))
                    .unwrap_or(Value::Null),
            ),
        ],
    )
}

fn canonical_with_item(node: &ast::WithItem) -> Value {
    canonical_node(
        "withitem",
        vec![
            ("context_expr", canonical_expr(&node.context_expr)),
            (
                "optional_vars",
                canonical_optional(node.optional_vars.as_deref(), canonical_expr),
            ),
        ],
    )
}

fn canonical_match_case(node: &ast::MatchCase) -> Value {
    canonical_node(
        "match_case",
        vec![
            ("pattern", canonical_pattern(&node.pattern)),
            (
                "guard",
                canonical_optional(node.guard.as_deref(), canonical_expr),
            ),
            ("body", canonical_array(&node.body, canonical_stmt)),
        ],
    )
}

fn canonical_except_handler(node: &ast::ExceptHandler) -> Value {
    match node {
        ast::ExceptHandler::ExceptHandler(node) => canonical_node(
            "ExceptHandler",
            vec![
                (
                    "type",
                    canonical_optional(node.type_.as_deref(), canonical_expr),
                ),
                (
                    "name",
                    node.name
                        .as_ref()
                        .map(|name| canonical_string(name.as_str()))
                        .unwrap_or(Value::Null),
                ),
                ("body", canonical_array(&node.body, canonical_stmt)),
            ],
        ),
    }
}

fn canonical_pattern(pattern: &ast::Pattern) -> Value {
    use ast::Pattern as P;
    match pattern {
        P::MatchValue(node) => {
            canonical_node("MatchValue", vec![("value", canonical_expr(&node.value))])
        }
        P::MatchSingleton(node) => canonical_node(
            "MatchSingleton",
            vec![("value", canonical_constant_value(&node.value))],
        ),
        P::MatchSequence(node) => canonical_node(
            "MatchSequence",
            vec![(
                "patterns",
                canonical_array(&node.patterns, canonical_pattern),
            )],
        ),
        P::MatchMapping(node) => canonical_node(
            "MatchMapping",
            vec![
                ("keys", canonical_array(&node.keys, canonical_expr)),
                (
                    "patterns",
                    canonical_array(&node.patterns, canonical_pattern),
                ),
                (
                    "rest",
                    node.rest
                        .as_ref()
                        .map(|rest| canonical_string(rest.as_str()))
                        .unwrap_or(Value::Null),
                ),
            ],
        ),
        P::MatchClass(node) => canonical_node(
            "MatchClass",
            vec![
                ("cls", canonical_expr(&node.cls)),
                (
                    "patterns",
                    canonical_array(&node.patterns, canonical_pattern),
                ),
                (
                    "kwd_attrs",
                    Value::Array(node.kwd_attrs.iter().map(|_| json!("STR")).collect()),
                ),
                (
                    "kwd_patterns",
                    canonical_array(&node.kwd_patterns, canonical_pattern),
                ),
            ],
        ),
        P::MatchStar(node) => canonical_node(
            "MatchStar",
            vec![(
                "name",
                node.name
                    .as_ref()
                    .map(|name| canonical_string(name.as_str()))
                    .unwrap_or(Value::Null),
            )],
        ),
        P::MatchAs(node) => canonical_node(
            "MatchAs",
            vec![
                (
                    "pattern",
                    canonical_optional(node.pattern.as_deref(), canonical_pattern),
                ),
                (
                    "name",
                    node.name
                        .as_ref()
                        .map(|name| canonical_string(name.as_str()))
                        .unwrap_or(Value::Null),
                ),
            ],
        ),
        P::MatchOr(node) => canonical_node(
            "MatchOr",
            vec![(
                "patterns",
                canonical_array(&node.patterns, canonical_pattern),
            )],
        ),
    }
}

fn canonical_type_param(param: &ast::TypeParam) -> Value {
    use ast::TypeParam as T;
    match param {
        T::TypeVar(node) => canonical_node(
            "TypeVar",
            vec![
                ("name", canonical_string(node.name.as_str())),
                (
                    "bound",
                    canonical_optional(node.bound.as_deref(), canonical_expr),
                ),
            ],
        ),
        T::ParamSpec(node) => canonical_node(
            "ParamSpec",
            vec![("name", canonical_string(node.name.as_str()))],
        ),
        T::TypeVarTuple(node) => canonical_node(
            "TypeVarTuple",
            vec![("name", canonical_string(node.name.as_str()))],
        ),
    }
}

fn expr_name(expr: &ast::Expr) -> Option<String> {
    match expr {
        ast::Expr::Name(name) => Some(name.id.to_string()),
        _ => None,
    }
}

fn ref_name(expr: &ast::Expr) -> String {
    match expr {
        ast::Expr::Name(name) => name.id.to_string(),
        ast::Expr::Attribute(attribute) => {
            let parent = ref_name(&attribute.value);
            if parent.is_empty() {
                attribute.attr.to_string()
            } else {
                format!("{parent}.{}", attribute.attr)
            }
        }
        ast::Expr::Subscript(subscript) => ref_name(&subscript.value),
        ast::Expr::Call(call) => ref_name(&call.func),
        _ => ast_dump_expr(expr),
    }
}

fn import_facts(suite: &ast::Suite) -> Vec<Value> {
    let mut facts = Vec::<Vec<String>>::new();
    for statement in suite {
        match statement {
            ast::Stmt::Import(import) => {
                facts.extend(
                    import
                        .names
                        .iter()
                        .map(|alias| vec!["import".to_string(), alias.name.to_string()]),
                );
            }
            ast::Stmt::ImportFrom(import) => {
                let level = import
                    .level
                    .as_ref()
                    .map(|value| value.to_usize())
                    .unwrap_or(0);
                let module = format!(
                    "{}{}",
                    ".".repeat(level),
                    import
                        .module
                        .as_ref()
                        .map(ToString::to_string)
                        .unwrap_or_default()
                );
                facts.extend(
                    import.names.iter().map(|alias| {
                        vec!["from".to_string(), module.clone(), alias.name.to_string()]
                    }),
                );
            }
            _ => {}
        }
    }
    facts.sort();
    facts.into_iter().map(|fact| json!(fact)).collect()
}

fn decorator_facts(node: &[ast::Expr]) -> Vec<String> {
    let mut facts = node.iter().map(ref_name).collect::<Vec<_>>();
    facts.sort();
    facts
}

fn base_facts(node: &[ast::Expr]) -> Vec<String> {
    let mut facts = node.iter().map(ref_name).collect::<Vec<_>>();
    facts.sort();
    facts
}

fn module_all_names(suite: &ast::Suite) -> Option<BTreeSet<String>> {
    let mut names = BTreeSet::new();
    let mut found = false;
    for statement in suite {
        let ast::Stmt::Assign(assign) = statement else {
            continue;
        };
        if !assign
            .targets
            .iter()
            .any(|target| expr_name(target).as_deref() == Some("__all__"))
        {
            continue;
        }
        found = true;
        let values = match assign.value.as_ref() {
            ast::Expr::List(list) => Some(&list.elts),
            ast::Expr::Tuple(tuple) => Some(&tuple.elts),
            ast::Expr::Set(set) => Some(&set.elts),
            _ => None,
        };
        if let Some(values) = values {
            for value in values {
                if let ast::Expr::Constant(constant) = value {
                    if let ast::Constant::Str(name) = &constant.value {
                        names.insert(name.clone());
                    }
                }
            }
        }
    }
    found.then_some(names)
}

#[derive(Clone)]
struct ClassInfo {
    module: String,
    qualname: String,
    bases: Vec<String>,
}

struct ClassIndexVisitor<'a> {
    module: &'a str,
    stack: Vec<String>,
    classes: Vec<ClassInfo>,
}

impl Visitor for ClassIndexVisitor<'_> {
    fn visit_stmt_class_def(&mut self, node: ast::StmtClassDef) {
        let name = node.name.to_string();
        let qualname = self
            .stack
            .iter()
            .chain(std::iter::once(&name))
            .cloned()
            .collect::<Vec<_>>()
            .join(".");
        self.classes.push(ClassInfo {
            module: self.module.to_string(),
            qualname,
            bases: base_facts(&node.bases),
        });
        self.stack.push(name);
        self.generic_visit_stmt_class_def(node);
        self.stack.pop();
    }
}

fn class_identities(module: &str, qualname: &str) -> [String; 3] {
    let simple = qualname.rsplit('.').next().unwrap_or(qualname);
    [
        simple.to_string(),
        qualname.to_string(),
        format!("{module}.{qualname}"),
    ]
}

fn is_direct_protocol_base(base: &str) -> bool {
    base == "Protocol" || base.ends_with(".Protocol")
}

fn base_matches_known_protocol(base: &str, protocol_names: &BTreeSet<String>) -> bool {
    if is_direct_protocol_base(base) {
        return true;
    }
    let base_tail = base.rsplit('.').next().unwrap_or(base);
    protocol_names.contains(base) || protocol_names.contains(base_tail)
}

fn build_protocol_names(modules: &[ParsedModule]) -> BTreeSet<String> {
    let mut classes = Vec::new();
    for module in modules {
        let mut visitor = ClassIndexVisitor {
            module: &module.module,
            stack: Vec::new(),
            classes: Vec::new(),
        };
        for statement in &module.suite {
            visitor.visit_stmt(statement.clone());
        }
        classes.extend(visitor.classes);
    }

    let mut protocol_names = BTreeSet::new();
    loop {
        let before = protocol_names.len();
        for class in &classes {
            if class
                .bases
                .iter()
                .any(|base| base_matches_known_protocol(base, &protocol_names))
            {
                protocol_names.extend(class_identities(&class.module, &class.qualname));
            }
        }
        if protocol_names.len() == before {
            return protocol_names;
        }
    }
}

#[derive(Clone)]
struct ParentEntry {
    kind: String,
    name: String,
    inside_protocol: bool,
    public_api: bool,
}

struct BlockFacts {
    kind: &'static str,
    parameter_count: usize,
    decorators: Vec<String>,
    bases: Vec<String>,
    canonical: Value,
    calls: Vec<CallRef>,
    references: Vec<CallRef>,
    is_alias: bool,
}

struct BlockCollector<'a> {
    path: String,
    module: String,
    source: &'a str,
    imports: &'a [Value],
    module_all: &'a Option<BTreeSet<String>>,
    protocol_names: &'a BTreeSet<String>,
    stack: Vec<ParentEntry>,
    blocks: Vec<ExtractedBlock>,
}

impl BlockCollector<'_> {
    fn public_api(&self, name: &str) -> bool {
        if let Some(parent) = self.stack.last() {
            parent.kind == "Class" && parent.public_api && !name.starts_with('_')
        } else if let Some(module_all) = self.module_all {
            module_all.contains(name)
        } else {
            !name.starts_with('_')
        }
    }

    fn add_block(
        &mut self,
        name: &str,
        node: &impl Ranged,
        facts: BlockFacts,
    ) -> ParentEntry {
        let BlockFacts {
            kind,
            parameter_count,
            decorators,
            bases,
            canonical,
            calls,
            references,
            is_alias,
        } = facts;
        let parent = self.stack.last();
        let parent_kind = parent.map(|value| value.kind.clone());
        let parent_name = parent.map(|value| value.name.clone());
        let qualname = self
            .stack
            .iter()
            .map(|value| value.name.as_str())
            .chain(std::iter::once(name))
            .collect::<Vec<_>>()
            .join(".");
        let class_is_protocol = kind == "Class"
            && class_identities(&self.module, &qualname)
                .iter()
                .any(|identity| self.protocol_names.contains(identity));
        let inside_protocol =
            class_is_protocol || parent.map(|value| value.inside_protocol).unwrap_or(false);
        let role = if is_alias {
            "alias"
        } else if inside_protocol {
            "protocol"
        } else {
            "implementation"
        };
        let public_api = if is_alias {
            if let Some(module_all) = self.module_all {
                module_all.contains(name)
            } else {
                parent.is_none() && !name.starts_with('_')
            }
        } else {
            self.public_api(name)
        };
        let end_offset = node.end().to_usize();
        self.blocks.push(ExtractedBlock {
            path: self.path.clone(),
            module: self.module.clone(),
            line: node_line(self.source, node),
            end_line: line_at_offset(self.source, end_offset.saturating_sub(1)),
            kind: kind.to_string(),
            name: name.to_string(),
            qualname,
            parent_kind,
            parent_name,
            role: role.to_string(),
            public_api,
            parameter_count,
            decorators,
            bases,
            imports: self.imports.to_vec(),
            calls,
            references,
            canonical,
        });
        ParentEntry {
            kind: kind.to_string(),
            name: name.to_string(),
            inside_protocol,
            public_api,
        }
    }

    fn add_function(
        &mut self,
        name: &str,
        node: &impl Ranged,
        args: &ast::Arguments,
        body: &[ast::Stmt],
        decorators: &[ast::Expr],
        returns: Option<&ast::Expr>,
    ) -> ParentEntry {
        let parameter_count = function_parameter_count(args);
        let canonical = canonical_body(body);
        let calls = block_calls(self.source, body);
        let references = function_references(self.source, args, returns, body);
        self.add_block(
            name,
            node,
            BlockFacts {
                kind: "Function",
                parameter_count,
                decorators: decorator_facts(decorators),
                bases: Vec::new(),
                canonical,
                calls,
                references,
                is_alias: false,
            },
        )
    }

    fn add_class(
        &mut self,
        name: &str,
        node: &impl Ranged,
        bases: &[ast::Expr],
        decorators: &[ast::Expr],
        body: &[ast::Stmt],
    ) -> ParentEntry {
        let canonical = canonical_body(body);
        let calls = block_calls(self.source, body);
        let references = class_references(self.source, bases, body);
        self.add_block(
            name,
            node,
            BlockFacts {
                kind: "Class",
                parameter_count: bases.len(),
                decorators: decorator_facts(decorators),
                bases: base_facts(bases),
                canonical,
                calls,
                references,
                is_alias: false,
            },
        )
    }

    fn add_alias(&mut self, name: &str, node: &impl Ranged, canonical: &ast::Expr) {
        self.add_block(
            name,
            node,
            BlockFacts {
                kind: "Alias",
                parameter_count: 0,
                decorators: Vec::new(),
                bases: Vec::new(),
                canonical: canonical_expr(canonical),
                calls: Vec::new(),
                references: Vec::new(),
                is_alias: true,
            },
        );
    }
}

impl Visitor for BlockCollector<'_> {
    fn visit_stmt_function_def(&mut self, node: ast::StmtFunctionDef) {
        let name = node.name.to_string();
        let parent = self.add_function(
            &name,
            &node,
            &node.args,
            &node.body,
            &node.decorator_list,
            node.returns.as_deref(),
        );
        self.stack.push(parent);
        self.generic_visit_stmt_function_def(node);
        self.stack.pop();
    }

    fn visit_stmt_async_function_def(&mut self, node: ast::StmtAsyncFunctionDef) {
        let name = node.name.to_string();
        let parent = self.add_function(
            &name,
            &node,
            &node.args,
            &node.body,
            &node.decorator_list,
            node.returns.as_deref(),
        );
        self.stack.push(parent);
        self.generic_visit_stmt_async_function_def(node);
        self.stack.pop();
    }

    fn visit_stmt_class_def(&mut self, node: ast::StmtClassDef) {
        let name = node.name.to_string();
        let parent = self.add_class(&name, &node, &node.bases, &node.decorator_list, &node.body);
        self.stack.push(parent);
        self.generic_visit_stmt_class_def(node);
        self.stack.pop();
    }

    fn visit_stmt_ann_assign(&mut self, node: ast::StmtAnnAssign) {
        if let Some(name) = expr_name(&node.target) {
            let annotation = ref_name(&node.annotation);
            if annotation == "TypeAlias" || annotation.ends_with(".TypeAlias") {
                self.add_alias(
                    &name,
                    &node,
                    node.value.as_deref().unwrap_or(&node.annotation),
                );
                return;
            }
        }
        self.generic_visit_stmt_ann_assign(node);
    }

    fn visit_stmt_assign(&mut self, node: ast::StmtAssign) {
        let value_name = if let ast::Expr::Subscript(value) = node.value.as_ref() {
            ref_name(&value.value)
        } else {
            String::new()
        };
        if matches!(value_name.as_str(), "TypeAlias" | "typing.TypeAlias") {
            for target in &node.targets {
                if let Some(name) = expr_name(target) {
                    self.add_alias(&name, &node, &node.value);
                }
            }
            return;
        }
        self.generic_visit_stmt_assign(node);
    }
}

fn function_parameter_count(args: &ast::Arguments) -> usize {
    args.posonlyargs
        .iter()
        .chain(&args.args)
        .chain(&args.kwonlyargs)
        .map(|argument| argument.def.arg.as_str())
        .chain(args.vararg.iter().map(|argument| argument.arg.as_str()))
        .chain(args.kwarg.iter().map(|argument| argument.arg.as_str()))
        .filter(|name| !matches!(*name, "self" | "cls"))
        .count()
}

fn body_without_docstring(body: &[ast::Stmt]) -> &[ast::Stmt] {
    match body.first() {
        Some(ast::Stmt::Expr(expr)) if matches!(&*expr.value, ast::Expr::Constant(value) if matches!(value.value, ast::Constant::Str(_))) => {
            &body[1..]
        }
        _ => body,
    }
}

fn canonical_body(body: &[ast::Stmt]) -> Value {
    canonical_array(body_without_docstring(body), canonical_stmt)
}

struct BlockCallVisitor<'a> {
    source: &'a str,
    calls: Vec<CallRef>,
}

impl Visitor for BlockCallVisitor<'_> {
    fn visit_stmt_function_def(&mut self, _node: ast::StmtFunctionDef) {}
    fn visit_stmt_async_function_def(&mut self, _node: ast::StmtAsyncFunctionDef) {}
    fn visit_stmt_class_def(&mut self, _node: ast::StmtClassDef) {}

    fn visit_expr_call(&mut self, node: ast::ExprCall) {
        self.calls.push(CallRef {
            name: ref_name(&node.func),
            line: node_line(self.source, &node),
        });
        self.generic_visit_expr_call(node);
    }
}

fn block_calls(source: &str, body: &[ast::Stmt]) -> Vec<CallRef> {
    let mut visitor = BlockCallVisitor {
        source,
        calls: Vec::new(),
    };
    for statement in body_without_docstring(body) {
        visitor.visit_stmt(statement.clone());
    }
    visitor
        .calls
        .sort_by(|left, right| (left.line, &left.name).cmp(&(right.line, &right.name)));
    visitor.calls
}

struct AnnotationReferenceVisitor {
    line: usize,
    references: Vec<CallRef>,
}

impl AnnotationReferenceVisitor {
    fn record(&mut self, name: String) {
        if !name.is_empty() {
            self.references.push(CallRef {
                name,
                line: self.line,
            });
        }
    }
}

impl Visitor for AnnotationReferenceVisitor {
    fn visit_expr_name(&mut self, node: ast::ExprName) {
        self.record(ref_name(&ast::Expr::Name(node.clone())));
        self.generic_visit_expr_name(node);
    }

    fn visit_expr_attribute(&mut self, node: ast::ExprAttribute) {
        self.record(ref_name(&ast::Expr::Attribute(node.clone())));
        self.generic_visit_expr_attribute(node);
    }

    fn visit_expr_subscript(&mut self, node: ast::ExprSubscript) {
        self.record(ref_name(&ast::Expr::Subscript(node.clone())));
        self.generic_visit_expr_subscript(node);
    }

    fn visit_expr_call(&mut self, node: ast::ExprCall) {
        self.record(ref_name(&ast::Expr::Call(node.clone())));
        self.generic_visit_expr_call(node);
    }
}

struct BlockReferenceVisitor<'a> {
    source: &'a str,
    references: Vec<CallRef>,
}

impl BlockReferenceVisitor<'_> {
    fn add_annotation(&mut self, annotation: &ast::Expr) {
        let mut visitor = AnnotationReferenceVisitor {
            line: node_line(self.source, annotation),
            references: Vec::new(),
        };
        visitor.visit_expr(annotation.clone());
        self.references.extend(visitor.references);
    }
}

impl Visitor for BlockReferenceVisitor<'_> {
    fn visit_stmt_function_def(&mut self, _node: ast::StmtFunctionDef) {}
    fn visit_stmt_async_function_def(&mut self, _node: ast::StmtAsyncFunctionDef) {}
    fn visit_stmt_class_def(&mut self, _node: ast::StmtClassDef) {}

    fn visit_stmt_ann_assign(&mut self, node: ast::StmtAnnAssign) {
        self.add_annotation(&node.annotation);
        self.generic_visit_stmt_ann_assign(node);
    }
}

fn sort_unique_references(references: Vec<CallRef>) -> Vec<CallRef> {
    let mut references = references
        .into_iter()
        .map(|reference| ((reference.line, reference.name.clone()), reference))
        .collect::<BTreeMap<_, _>>();
    std::mem::take(&mut references).into_values().collect()
}

fn function_references(
    source: &str,
    args: &ast::Arguments,
    returns: Option<&ast::Expr>,
    body: &[ast::Stmt],
) -> Vec<CallRef> {
    let mut visitor = BlockReferenceVisitor {
        source,
        references: Vec::new(),
    };
    for argument in args
        .posonlyargs
        .iter()
        .chain(&args.args)
        .chain(&args.kwonlyargs)
    {
        if let Some(annotation) = argument.def.annotation.as_deref() {
            visitor.add_annotation(annotation);
        }
    }
    if let Some(argument) = args.vararg.as_deref() {
        if let Some(annotation) = argument.annotation.as_deref() {
            visitor.add_annotation(annotation);
        }
    }
    if let Some(argument) = args.kwarg.as_deref() {
        if let Some(annotation) = argument.annotation.as_deref() {
            visitor.add_annotation(annotation);
        }
    }
    if let Some(returns) = returns {
        visitor.add_annotation(returns);
    }
    for statement in body_without_docstring(body) {
        visitor.visit_stmt(statement.clone());
    }
    sort_unique_references(visitor.references)
}

fn class_references(source: &str, bases: &[ast::Expr], body: &[ast::Stmt]) -> Vec<CallRef> {
    let mut visitor = BlockReferenceVisitor {
        source,
        references: Vec::new(),
    };
    for base in bases {
        visitor.add_annotation(base);
    }
    for statement in body_without_docstring(body) {
        visitor.visit_stmt(statement.clone());
    }
    sort_unique_references(visitor.references)
}

fn block_from_extracted(extracted: ExtractedBlock) -> Result<Block, String> {
    let canonical_text = serde_json::to_string(&extracted.canonical)
        .map_err(|error| format!("failed to serialize canonical AST: {error}"))?;
    let imports_text = serde_json::to_string(&extracted.imports)
        .map_err(|error| format!("failed to serialize import facts: {error}"))?;
    let decorators_text = serde_json::to_string(&extracted.decorators)
        .map_err(|error| format!("failed to serialize decorator facts: {error}"))?;
    let bases_text = serde_json::to_string(&extracted.bases)
        .map_err(|error| format!("failed to serialize base facts: {error}"))?;
    let owner_text = format!(
        "{}:{}",
        extracted.parent_kind.as_deref().unwrap_or("<module>"),
        extracted.parent_name.as_deref().unwrap_or("<module>")
    );
    let context_text = format!(
        "{}:{imports_text}:{decorators_text}:{bases_text}:{owner_text}",
        extracted.module
    );
    Ok(Block {
        path: extracted.path,
        module: extracted.module,
        line: extracted.line,
        end_line: extracted.end_line,
        kind: extracted.kind.clone(),
        role: extracted.role.clone(),
        name: extracted.name,
        qualname: extracted.qualname,
        parent_kind: extracted.parent_kind,
        parent_name: extracted.parent_name,
        parameter_count: extracted.parameter_count,
        decorators_hash: stable_hash(&decorators_text),
        bases_hash: stable_hash(&bases_text),
        import_hash: stable_hash(&imports_text),
        structure_hash: stable_hash(&format!(
            "{}:{}:{}:{canonical_text}",
            extracted.role, extracted.kind, extracted.parameter_count
        )),
        context_hash: stable_hash(&context_text),
        token_count: ast_token_count(&extracted.canonical),
        public_api: extracted.public_api,
        calls: extracted.calls,
        references: extracted.references,
    })
}

fn ast_token_count(value: &Value) -> usize {
    match value {
        Value::Array(items) => 1 + items.iter().map(ast_token_count).sum::<usize>(),
        Value::Object(entries) => 1 + entries.values().map(ast_token_count).sum::<usize>(),
        Value::String(_) | Value::Number(_) | Value::Bool(_) | Value::Null => 1,
    }
}

fn stable_hash(text: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(text.as_bytes());
    format!("{:x}", hasher.finalize())[..16].to_string()
}

fn module_scope(blocks: &[Block]) -> ModuleScope {
    let modules = blocks
        .iter()
        .map(|block| block.module.as_str())
        .collect::<BTreeSet<_>>();
    if modules.len() == 1 {
        ModuleScope::SameModule
    } else {
        ModuleScope::CrossModule
    }
}

fn import_scope(blocks: &[Block]) -> ImportScope {
    let imports = blocks
        .iter()
        .map(|block| block.import_hash.as_str())
        .collect::<BTreeSet<_>>();
    if imports.len() == 1 {
        ImportScope::SameImports
    } else {
        ImportScope::MixedImports
    }
}

fn decorator_scope(blocks: &[Block]) -> DecoratorScope {
    let decorators = blocks
        .iter()
        .map(|block| block.decorators_hash.as_str())
        .collect::<BTreeSet<_>>();
    if decorators.len() == 1 {
        DecoratorScope::SameDecorators
    } else {
        DecoratorScope::MixedDecorators
    }
}

fn base_scope(blocks: &[Block]) -> BaseScope {
    let bases = blocks
        .iter()
        .map(|block| block.bases_hash.as_str())
        .collect::<BTreeSet<_>>();
    if bases.len() == 1 {
        BaseScope::SameBases
    } else {
        BaseScope::MixedBases
    }
}

fn single_caller_findings(blocks: &[Block], min_tokens: usize) -> Vec<SingleCallerFinding> {
    let mut by_name = BTreeMap::<String, Vec<usize>>::new();
    let mut by_qualname = BTreeMap::<String, usize>::new();
    for (index, block) in blocks.iter().enumerate() {
        by_name.entry(block.name.clone()).or_default().push(index);
        by_qualname.insert(block.qualname.clone(), index);
    }

    let mut target_callers = BTreeMap::<String, BTreeMap<String, CallerAccumulator>>::new();
    for caller in blocks {
        for call in &caller.calls {
            if let Some(target_index) =
                resolve_call_target(blocks, &by_name, &by_qualname, caller, call)
            {
                record_single_caller_usage(
                    blocks,
                    min_tokens,
                    &mut target_callers,
                    caller,
                    target_index,
                    call.line,
                );
            }
        }
        for reference in &caller.references {
            if let Some(target_index) =
                resolve_reference_target(blocks, &by_name, &by_qualname, caller, reference)
            {
                record_single_caller_usage(
                    blocks,
                    min_tokens,
                    &mut target_callers,
                    caller,
                    target_index,
                    reference.line,
                );
            }
        }
    }

    let block_by_key = blocks
        .iter()
        .map(|block| (block_key(block), block))
        .collect::<BTreeMap<_, _>>();
    target_callers
        .into_iter()
        .filter_map(|(target_key, callers)| {
            if callers.len() != 1 {
                return None;
            }
            let target = (*block_by_key.get(&target_key)?).clone();
            let (caller_key, caller) = callers.into_iter().next()?;
            let caller_block = *block_by_key.get(&caller_key)?;
            let call_lines = caller.call_lines.into_iter().collect::<Vec<_>>();
            let similar_callers = similar_responsibility_callers(blocks, caller_block, &target_key);
            Some(SingleCallerFinding {
                hash: stable_hash(&format!(
                    "single-caller:{}:{}:{}:{}",
                    target.kind, target.role, target.structure_hash, caller.qualname
                )),
                target,
                call_site_count: call_lines.len(),
                similar_callers,
                caller: CallerEvidence {
                    path: caller.path,
                    module: caller.module,
                    qualname: caller.qualname,
                    line: caller.line,
                    end_line: caller.end_line,
                    call_lines,
                },
            })
        })
        .collect()
}

fn single_callee_findings(blocks: &[Block], min_tokens: usize) -> Vec<SingleCalleeFinding> {
    let mut by_name = BTreeMap::<String, Vec<usize>>::new();
    let mut by_qualname = BTreeMap::<String, usize>::new();
    for (index, block) in blocks.iter().enumerate() {
        by_name.entry(block.name.clone()).or_default().push(index);
        by_qualname.insert(block.qualname.clone(), index);
    }

    let block_by_key = blocks
        .iter()
        .map(|block| (block_key(block), block))
        .collect::<BTreeMap<_, _>>();
    blocks
        .iter()
        .filter_map(|caller| {
            if !single_callee_caller_eligible(caller, min_tokens) {
                return None;
            }
            let mut callees = BTreeMap::<String, CalleeAccumulator>::new();
            for call in &caller.calls {
                if let Some(target_index) =
                    resolve_call_target(blocks, &by_name, &by_qualname, caller, call)
                {
                    record_single_callee_usage(
                        blocks,
                        &mut callees,
                        caller,
                        target_index,
                        call.line,
                    );
                }
            }
            if callees.len() != 1 {
                return None;
            }
            let (callee_key, callee) = callees.into_iter().next()?;
            let target = *block_by_key.get(&callee_key)?;
            let call_lines = callee.call_lines.into_iter().collect::<Vec<_>>();
            Some(SingleCalleeFinding {
                hash: stable_hash(&format!(
                    "single-callee:{}:{}:{}:{}",
                    caller.kind, caller.role, caller.structure_hash, target.qualname
                )),
                caller: caller.clone(),
                call_site_count: call_lines.len(),
                callee: CalleeEvidence {
                    path: callee.path,
                    module: callee.module,
                    qualname: callee.qualname,
                    line: callee.line,
                    end_line: callee.end_line,
                    call_lines,
                },
            })
        })
        .collect()
}

fn record_single_caller_usage(
    blocks: &[Block],
    min_tokens: usize,
    target_callers: &mut BTreeMap<String, BTreeMap<String, CallerAccumulator>>,
    caller: &Block,
    target_index: usize,
    line: usize,
) {
    let target = &blocks[target_index];
    if !single_caller_target_eligible(target, min_tokens) {
        return;
    }
    let target_key = block_key(target);
    let caller_key = block_key(caller);
    if target_key == caller_key {
        return;
    }
    target_callers
        .entry(target_key)
        .or_default()
        .entry(caller_key)
        .or_insert_with(|| CallerAccumulator::new(caller))
        .call_lines
        .insert(line);
}

fn record_single_callee_usage(
    blocks: &[Block],
    caller_callees: &mut BTreeMap<String, CalleeAccumulator>,
    caller: &Block,
    target_index: usize,
    line: usize,
) {
    let target = &blocks[target_index];
    if !single_callee_target_eligible(target) {
        return;
    }
    let caller_key = block_key(caller);
    let target_key = block_key(target);
    if caller_key == target_key {
        return;
    }
    caller_callees
        .entry(target_key)
        .or_insert_with(|| CalleeAccumulator::new(target))
        .call_lines
        .insert(line);
}

fn similar_responsibility_callers(
    blocks: &[Block],
    caller: &Block,
    target_key: &str,
) -> Vec<SimilarCallerEvidence> {
    let caller_profile = responsibility_profile(caller);
    let caller_key = block_key(caller);
    let mut peers = blocks
        .iter()
        .filter(|candidate| {
            let candidate_key = block_key(candidate);
            candidate_key != caller_key && candidate_key != target_key
        })
        .filter(|candidate| candidate.role == "implementation")
        .filter(|candidate| candidate.kind == caller.kind)
        .filter(|candidate| candidate.module == caller.module)
        .filter_map(|candidate| similar_caller_evidence(caller, &caller_profile, candidate))
        .collect::<Vec<_>>();
    peers.sort_by(|left, right| {
        right
            .score
            .cmp(&left.score)
            .then_with(|| right.shared_call_count.cmp(&left.shared_call_count))
            .then_with(|| left.path.cmp(&right.path))
            .then_with(|| left.qualname.cmp(&right.qualname))
    });
    peers.truncate(5);
    peers
}

fn similar_caller_evidence(
    caller: &Block,
    caller_profile: &BTreeSet<String>,
    candidate: &Block,
) -> Option<SimilarCallerEvidence> {
    let candidate_profile = responsibility_profile(candidate);
    let shared_profile = caller_profile
        .intersection(&candidate_profile)
        .cloned()
        .collect::<Vec<_>>();
    let shared_call_count = shared_profile.len();
    let same_structure = caller.structure_hash == candidate.structure_hash;
    let same_non_module_parent = same_non_module_parent_scope(caller, candidate);
    if !same_structure
        && shared_call_count < 2
        && !(same_non_module_parent && shared_call_count >= 1)
    {
        return None;
    }

    let mut score = 0usize;
    let mut reason_codes = Vec::new();
    if same_structure {
        score += 10;
        reason_codes.push("same_caller_structure".to_string());
    }
    if same_non_module_parent {
        score += 4;
        reason_codes.push("same_parent_scope".to_string());
    }
    if same_token_band(caller, candidate) {
        score += 1;
        reason_codes.push("similar_token_band".to_string());
    }
    if shared_call_count > 0 {
        score += shared_call_count * 2;
        reason_codes.push("shared_call_profile".to_string());
    }
    Some(SimilarCallerEvidence {
        path: candidate.path.clone(),
        module: candidate.module.clone(),
        qualname: candidate.qualname.clone(),
        line: candidate.line,
        end_line: candidate.end_line,
        token_count: candidate.token_count,
        structure_hash: candidate.structure_hash.clone(),
        parent_scope: parent_scope_value(candidate),
        score,
        shared_call_count,
        shared_profile,
        reason_codes,
    })
}

fn responsibility_profile(block: &Block) -> BTreeSet<String> {
    block
        .calls
        .iter()
        .chain(block.references.iter())
        .map(|call| normalized_reference_name(&call.name))
        .filter(|name| !name.is_empty())
        .collect()
}

fn normalized_reference_name(name: &str) -> String {
    name.strip_prefix("self.")
        .map(|value| format!("self.{value}"))
        .or_else(|| {
            name.strip_prefix("cls.")
                .map(|value| format!("cls.{value}"))
        })
        .unwrap_or_else(|| name.to_string())
}

fn same_non_module_parent_scope(left: &Block, right: &Block) -> bool {
    if left.parent_kind.is_none() || right.parent_kind.is_none() {
        return false;
    }
    left.parent_kind == right.parent_kind && left.parent_name == right.parent_name
}

fn parent_scope_value(block: &Block) -> String {
    match (&block.parent_kind, &block.parent_name) {
        (Some(kind), Some(name)) => format!("{kind}:{name}"),
        _ => "<module>".to_string(),
    }
}

fn same_token_band(left: &Block, right: &Block) -> bool {
    let min = left.token_count.min(right.token_count).max(1);
    let max = left.token_count.max(right.token_count);
    max <= min * 2
}

#[derive(Debug)]
struct CallerAccumulator {
    path: String,
    module: String,
    qualname: String,
    line: usize,
    end_line: usize,
    call_lines: BTreeSet<usize>,
}

impl CallerAccumulator {
    fn new(block: &Block) -> Self {
        Self {
            path: block.path.clone(),
            module: block.module.clone(),
            qualname: block.qualname.clone(),
            line: block.line,
            end_line: block.end_line,
            call_lines: BTreeSet::new(),
        }
    }
}

#[derive(Debug)]
struct CalleeAccumulator {
    path: String,
    module: String,
    qualname: String,
    line: usize,
    end_line: usize,
    call_lines: BTreeSet<usize>,
}

impl CalleeAccumulator {
    fn new(block: &Block) -> Self {
        Self {
            path: block.path.clone(),
            module: block.module.clone(),
            qualname: block.qualname.clone(),
            line: block.line,
            end_line: block.end_line,
            call_lines: BTreeSet::new(),
        }
    }
}

fn single_caller_target_eligible(block: &Block, min_tokens: usize) -> bool {
    block.role == "implementation"
        && matches!(block.kind.as_str(), "Function" | "Class")
        && block.token_count >= min_tokens
}

fn single_callee_caller_eligible(block: &Block, min_tokens: usize) -> bool {
    block.role == "implementation"
        && block.kind == "Function"
        && block.token_count >= min_tokens
        && !block.public_api
}

fn single_callee_target_eligible(block: &Block) -> bool {
    block.role == "implementation" && matches!(block.kind.as_str(), "Function" | "Class")
}

fn resolve_call_target(
    blocks: &[Block],
    by_name: &BTreeMap<String, Vec<usize>>,
    by_qualname: &BTreeMap<String, usize>,
    caller: &Block,
    call: &CallRef,
) -> Option<usize> {
    if let Some(index) = by_qualname.get(&call.name) {
        let target = &blocks[*index];
        if target.module == caller.module {
            return Some(*index);
        }
    }
    if let Some(method_name) = call
        .name
        .strip_prefix("self.")
        .or_else(|| call.name.strip_prefix("cls."))
    {
        if method_name.contains('.') {
            return None;
        }
        let class_name = caller.parent_name.as_deref()?;
        return unique_candidate(blocks, by_name.get(method_name)?, |target| {
            target.module == caller.module
                && target.parent_kind.as_deref() == Some("Class")
                && target.parent_name.as_deref() == Some(class_name)
        });
    }
    if call.name.contains('.') {
        return None;
    }
    unique_candidate(blocks, by_name.get(&call.name)?, |target| {
        target.module == caller.module
    })
}

fn resolve_reference_target(
    blocks: &[Block],
    by_name: &BTreeMap<String, Vec<usize>>,
    by_qualname: &BTreeMap<String, usize>,
    caller: &Block,
    reference: &CallRef,
) -> Option<usize> {
    if let Some(index) = by_qualname.get(&reference.name) {
        let target = &blocks[*index];
        if target.module == caller.module && target.kind == "Class" {
            return Some(*index);
        }
    }
    if reference.name.contains('.') {
        return None;
    }
    unique_candidate(blocks, by_name.get(&reference.name)?, |target| {
        target.module == caller.module && target.kind == "Class"
    })
}

fn unique_candidate<F>(blocks: &[Block], candidates: &[usize], predicate: F) -> Option<usize>
where
    F: Fn(&Block) -> bool,
{
    let mut matching = candidates
        .iter()
        .copied()
        .filter(|index| predicate(&blocks[*index]))
        .collect::<Vec<_>>();
    matching.sort_unstable();
    matching.dedup();
    if matching.len() == 1 {
        matching.first().copied()
    } else {
        None
    }
}

fn block_key(block: &Block) -> String {
    format!("{}:{}", block.path, block.qualname)
}

fn render(analysis: Analysis, args: &Args) -> i32 {
    match args.format {
        OutputFormat::Json => render_json(&analysis),
        OutputFormat::Text => render_text(&analysis),
    }
    analysis_exit_status(&analysis)
}

fn analysis_exit_status(analysis: &Analysis) -> i32 {
    if analysis.groups.is_empty()
        && analysis.single_callers.is_empty()
        && analysis.single_callees.is_empty()
    {
        0
    } else {
        1
    }
}

fn render_text(analysis: &Analysis) {
    print!("{}", render_text_output(analysis));
}

fn render_text_output(analysis: &Analysis) -> String {
    use std::fmt::Write as _;

    let mut output = String::new();
    for group in &analysis.groups {
        let symbols = group
            .blocks
            .iter()
            .map(|block| {
                format!(
                    "{}:{}-{}:{}:{}:{}:context={}",
                    block.path,
                    block.line,
                    block.end_line,
                    block.module,
                    block.qualname,
                    compatibility_label(block),
                    block.context_hash
                )
            })
            .collect::<Vec<_>>()
            .join(",");
        writeln!(
            output,
            "PY_STRUCTURE_HASH_FINDING=duplicate_structural_hash:role={}:{}:params={}:tokens={}:hash={}:count={}:module_scope={:?}:import_scope={:?}:decorator_scope={:?}:base_scope={:?}:{}",
            group.role,
            group.kind,
            group.parameter_count,
            group.token_count,
            group.structure_hash,
            group.blocks.len(),
            group.module_scope,
            group.import_scope,
            group.decorator_scope,
            group.base_scope,
            symbols
        )
        .expect("writing to a String cannot fail");
    }
    for finding in &analysis.single_callers {
        let target = &finding.target;
        writeln!(
            output,
            "PY_STRUCTURE_HASH_FINDING=single_caller_structural_helper:role={}:{}:params={}:tokens={}:hash={}:count=1:caller_count=1:call_site_count={}:caller={}:similar_callers={}:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:{}",
            target.role,
            target.kind,
            target.parameter_count,
            target.token_count,
            finding.hash,
            finding.call_site_count,
            caller_label(&finding.caller),
            similar_callers_label(&finding.similar_callers),
            instance_label(target)
        )
        .expect("writing to a String cannot fail");
    }
    for finding in &analysis.single_callees {
        let caller = &finding.caller;
        writeln!(
            output,
            "PY_STRUCTURE_HASH_FINDING=single_callee_structural_wrapper:role={}:{}:params={}:tokens={}:hash={}:count=1:callee_count=1:call_site_count={}:public_api=false:callee={}:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:{}",
            caller.role,
            caller.kind,
            caller.parameter_count,
            caller.token_count,
            finding.hash,
            finding.call_site_count,
            callee_label(&finding.callee),
            instance_label(caller)
        )
        .expect("writing to a String cannot fail");
    }
    writeln!(
        output,
        "PY_STRUCTURE_HASH_ANALYZED_FILES={}",
        analysis.analyzed_files.len()
    )
    .expect("writing to a String cannot fail");
    for path in &analysis.analyzed_files {
        writeln!(output, "PY_STRUCTURE_HASH_ANALYZED_FILE={path}")
            .expect("writing to a String cannot fail");
    }
    writeln!(
        output,
        "PY_STRUCTURE_HASH_DUPLICATE_GROUPS={}",
        analysis.groups.len()
    )
    .expect("writing to a String cannot fail");
    writeln!(
        output,
        "PY_STRUCTURE_HASH_SINGLE_CALLER_FINDINGS={}",
        analysis.single_callers.len()
    )
    .expect("writing to a String cannot fail");
    writeln!(
        output,
        "PY_STRUCTURE_HASH_SINGLE_CALLEE_FINDINGS={}",
        analysis.single_callees.len()
    )
    .expect("writing to a String cannot fail");
    writeln!(
        output,
        "PY_STRUCTURE_HASH_GROUPS={}",
        analysis.groups.len() + analysis.single_callers.len() + analysis.single_callees.len()
    )
    .expect("writing to a String cannot fail");
    writeln!(
        output,
        "PY_STRUCTURE_HASH={}",
        if analysis.groups.is_empty()
            && analysis.single_callers.is_empty()
            && analysis.single_callees.is_empty()
        {
            "pass"
        } else {
            "fail"
        }
    )
    .expect("writing to a String cannot fail");
    output
}

fn similar_callers_label(similar_callers: &[SimilarCallerEvidence]) -> String {
    if similar_callers.is_empty() {
        return "none".to_string();
    }
    similar_callers
        .iter()
        .map(|caller| {
            format!(
                "{}@{}-{}@{}@{}@tokens={}@structure={}@parent={}@score={}@shared={}@profile={}@reasons={}",
                caller.path,
                caller.line,
                caller.end_line,
                caller.module,
                caller.qualname,
                caller.token_count,
                caller.structure_hash,
                caller.parent_scope.replace(':', "~"),
                caller.score,
                caller.shared_call_count,
                caller.shared_profile.join("|"),
                caller.reason_codes.join("|")
            )
        })
        .collect::<Vec<_>>()
        .join(";")
}

fn instance_label(block: &Block) -> String {
    format!(
        "{}:{}-{}:{}:{}:{}:context={}",
        block.path,
        block.line,
        block.end_line,
        block.module,
        block.qualname,
        compatibility_label(block),
        block.context_hash
    )
}

fn caller_label(caller: &CallerEvidence) -> String {
    format!(
        "{}@{}-{}@{}@{}@sites={}",
        caller.path,
        caller.line,
        caller.end_line,
        caller.module,
        caller.qualname,
        caller
            .call_lines
            .iter()
            .map(usize::to_string)
            .collect::<Vec<_>>()
            .join("|")
    )
}

fn callee_label(callee: &CalleeEvidence) -> String {
    format!(
        "{}@{}-{}@{}@{}@sites={}",
        callee.path,
        callee.line,
        callee.end_line,
        callee.module,
        callee.qualname,
        callee
            .call_lines
            .iter()
            .map(usize::to_string)
            .collect::<Vec<_>>()
            .join("|")
    )
}

fn parent_label(block: &Block) -> String {
    match (&block.parent_kind, &block.parent_name) {
        (Some(kind), Some(name)) => format!("parent={kind}:{name}"),
        _ => "parent=<module>".to_string(),
    }
}

fn compatibility_label(block: &Block) -> String {
    format!(
        "{}:imports={}:decorators={}:bases={}",
        parent_label(block),
        block.import_hash,
        block.decorators_hash,
        block.bases_hash
    )
}

fn render_json(analysis: &Analysis) {
    println!("{}", render_json_output(analysis));
}

fn render_json_output(analysis: &Analysis) -> String {
    let duplicate_findings = analysis.groups.iter().map(|group| {
        json!({
            "kind": "duplicate_structural_hash",
            "hash": group.structure_hash,
            "block_kind": group.kind,
            "role": group.role,
            "parameter_count": group.parameter_count,
            "token_count": group.token_count,
            "module_scope": format!("{:?}", group.module_scope),
            "import_scope": format!("{:?}", group.import_scope),
            "decorator_scope": format!("{:?}", group.decorator_scope),
            "base_scope": format!("{:?}", group.base_scope),
            "instances": group.blocks.iter().map(|block| {
                json!({
                    "path": block.path,
                    "line": block.line,
                    "end_line": block.end_line,
                    "module": block.module,
                    "name": block.name,
                    "qualname": block.qualname,
                    "parent_kind": block.parent_kind,
                    "parent_name": block.parent_name,
                    "import_hash": block.import_hash,
                    "decorators_hash": block.decorators_hash,
                    "bases_hash": block.bases_hash,
                    "context_hash": block.context_hash,
                    "public_api": block.public_api,
                })
            }).collect::<Vec<_>>(),
        })
    });
    let single_caller_findings = analysis.single_callers.iter().map(|finding| {
        let block = &finding.target;
        json!({
            "kind": "single_caller_structural_helper",
            "hash": finding.hash,
            "block_kind": block.kind,
            "role": block.role,
            "parameter_count": block.parameter_count,
            "token_count": block.token_count,
            "module_scope": "SameModule",
            "import_scope": "SameImports",
            "decorator_scope": "SameDecorators",
            "base_scope": "SameBases",
            "caller_count": 1,
            "call_site_count": finding.call_site_count,
            "caller": {
                "path": finding.caller.path,
                "line": finding.caller.line,
                "end_line": finding.caller.end_line,
                "module": finding.caller.module,
                "qualname": finding.caller.qualname,
                "call_lines": finding.caller.call_lines,
            },
            "similar_responsibility_callers": finding.similar_callers.iter().map(|caller| {
                json!({
                    "path": caller.path,
                    "line": caller.line,
                    "end_line": caller.end_line,
                    "module": caller.module,
                    "qualname": caller.qualname,
                    "token_count": caller.token_count,
                    "structure_hash": caller.structure_hash,
                    "parent_scope": caller.parent_scope,
                    "score": caller.score,
                    "shared_call_count": caller.shared_call_count,
                    "shared_profile": caller.shared_profile,
                    "reason_codes": caller.reason_codes,
                })
            }).collect::<Vec<_>>(),
            "caller_analysis": {
                "caller_count": 1,
                "call_site_count": finding.call_site_count,
                "callers": [json!({
                    "path": finding.caller.path,
                    "line": finding.caller.line,
                    "end_line": finding.caller.end_line,
                    "module": finding.caller.module,
                    "qualname": finding.caller.qualname,
                    "call_lines": finding.caller.call_lines,
                })],
                "similar_responsibility_callers": finding.similar_callers.iter().map(|caller| {
                    json!({
                        "path": caller.path,
                        "line": caller.line,
                        "end_line": caller.end_line,
                        "module": caller.module,
                        "qualname": caller.qualname,
                        "token_count": caller.token_count,
                        "structure_hash": caller.structure_hash,
                        "parent_scope": caller.parent_scope,
                        "score": caller.score,
                        "shared_call_count": caller.shared_call_count,
                        "shared_profile": caller.shared_profile,
                        "reason_codes": caller.reason_codes,
                    })
                }).collect::<Vec<_>>(),
                "integration_candidates": direct_integration_candidates_json(finding),
                "enrichment_note": "python-structure-hash-report adds dependency-tree features to these AST/use-graph candidates",
            },
            "instances": [json!({
                "path": block.path,
                "line": block.line,
                "end_line": block.end_line,
                "module": block.module,
                "name": block.name,
                "qualname": block.qualname,
                "parent_kind": block.parent_kind,
                "parent_name": block.parent_name,
                "import_hash": block.import_hash,
                "decorators_hash": block.decorators_hash,
                "bases_hash": block.bases_hash,
                "context_hash": block.context_hash,
                "public_api": block.public_api,
            })],
        })
    });
    let single_callee_findings = analysis.single_callees.iter().map(|finding| {
        let block = &finding.caller;
        json!({
            "kind": "single_callee_structural_wrapper",
            "hash": finding.hash,
            "block_kind": block.kind,
            "role": block.role,
            "parameter_count": block.parameter_count,
            "token_count": block.token_count,
            "module_scope": "SameModule",
            "import_scope": "SameImports",
            "decorator_scope": "SameDecorators",
            "base_scope": "SameBases",
            "callee_count": 1,
            "call_site_count": finding.call_site_count,
            "public_api": false,
            "callee_analysis": {
                "callee_count": 1,
                "call_site_count": finding.call_site_count,
                "callees": [json!({
                    "path": finding.callee.path,
                    "line": finding.callee.line,
                    "end_line": finding.callee.end_line,
                    "module": finding.callee.module,
                    "qualname": finding.callee.qualname,
                    "call_lines": finding.callee.call_lines,
                })],
                "candidate_schema_scope": "ast_use_graph_only",
            },
            "instances": [json!({
                "path": block.path,
                "line": block.line,
                "end_line": block.end_line,
                "module": block.module,
                "name": block.name,
                "qualname": block.qualname,
                "parent_kind": block.parent_kind,
                "parent_name": block.parent_name,
                "import_hash": block.import_hash,
                "decorators_hash": block.decorators_hash,
                "bases_hash": block.bases_hash,
                "context_hash": block.context_hash,
                "public_api": block.public_api,
            })],
        })
    });
    let payload = json!({
        "summary": {
            "groups": analysis.groups.len() + analysis.single_callers.len() + analysis.single_callees.len(),
            "duplicate_groups": analysis.groups.len(),
            "single_caller_findings": analysis.single_callers.len(),
            "single_callee_findings": analysis.single_callees.len(),
            "status": if analysis.groups.is_empty() && analysis.single_callers.is_empty() && analysis.single_callees.is_empty() { "pass" } else { "fail" },
            "analyzed_file_count": analysis.analyzed_files.len(),
            "analyzed_files": analysis.analyzed_files,
        },
        "findings": duplicate_findings.chain(single_caller_findings).chain(single_callee_findings).collect::<Vec<_>>(),
    });
    serde_json::to_string_pretty(&payload).expect("json payload serializes")
}

fn direct_integration_candidates_json(finding: &SingleCallerFinding) -> Vec<Value> {
    let target = &finding.target;
    let base_features = vec![
        json!({"code": "unique_owner", "weight": 40, "detail": "caller_count=1"}),
        json!({"code": "module_local_ownership", "weight": 20, "detail": format!("module={}", target.module)}),
        json!({"code": "usage_site_count", "weight": finding.call_site_count.min(5) * 4, "detail": format!("call_site_count={}", finding.call_site_count)}),
        json!({"code": "target_structure_size", "weight": target.token_count.min(50), "detail": format!("block_kind={},token_count={}", target.kind, target.token_count)}),
        json!({"code": "ast_block_kind", "weight": 8, "detail": target.kind}),
    ];
    let mut candidates = vec![json!({
        "candidate_kind": direct_single_owner_candidate_kind(&target.kind),
        "candidate_schema_scope": "ast_use_graph_only",
        "target": direct_block_json(target),
        "destination_caller": direct_caller_json(&finding.caller),
        "score": base_features.iter().filter_map(|feature| feature.get("weight").and_then(Value::as_u64)).sum::<u64>(),
        "reason_codes": feature_codes(&base_features),
        "features": base_features,
    })];
    candidates.extend(finding.similar_callers.iter().map(|similar| {
        let mut features = vec![
            json!({"code": "unique_owner", "weight": 40, "detail": "caller_count=1"}),
            json!({"code": "similar_responsibility_caller", "weight": 30, "detail": format!("similar={}", similar.qualname)}),
            json!({"code": "shared_call_profile_count", "weight": similar.shared_call_count * 8, "detail": format!("shared_call_count={}", similar.shared_call_count)}),
        ];
        features.extend(similar.reason_codes.iter().map(|reason| {
            json!({"code": "similarity_reason", "weight": direct_similarity_reason_weight(reason), "detail": reason})
        }));
        json!({
            "candidate_kind": "consolidate_owner_with_similar_responsibility_caller",
            "candidate_schema_scope": "ast_use_graph_only",
            "target": direct_block_json(target),
            "destination_caller": direct_caller_json(&finding.caller),
            "similar_caller": {
                "path": similar.path,
                "line": similar.line,
                "end_line": similar.end_line,
                "module": similar.module,
                "qualname": similar.qualname,
                "token_count": similar.token_count,
                "structure_hash": similar.structure_hash,
                "parent_scope": similar.parent_scope,
                "shared_profile": similar.shared_profile,
                "reason_codes": similar.reason_codes,
            },
            "score": features.iter().filter_map(|feature| feature.get("weight").and_then(Value::as_u64)).sum::<u64>(),
            "reason_codes": feature_codes(&features),
            "features": features,
        })
    }));
    candidates
}

fn feature_codes(features: &[Value]) -> Vec<String> {
    features
        .iter()
        .filter_map(|feature| feature.get("code").and_then(Value::as_str))
        .map(str::to_string)
        .collect()
}

fn direct_block_json(block: &Block) -> Value {
    json!({
        "path": block.path,
        "line": block.line,
        "end_line": block.end_line,
        "module": block.module,
        "qualname": block.qualname,
        "block_kind": block.kind,
        "token_count": block.token_count,
        "structure_hash": block.structure_hash,
        "parent_scope": parent_scope_value(block),
    })
}

fn direct_caller_json(caller: &CallerEvidence) -> Value {
    json!({
        "path": caller.path,
        "line": caller.line,
        "end_line": caller.end_line,
        "module": caller.module,
        "qualname": caller.qualname,
        "call_lines": caller.call_lines,
    })
}

fn direct_single_owner_candidate_kind(block_kind: &str) -> &'static str {
    match block_kind {
        "Class" => "move_or_nest_single_owner_type",
        "Alias" => "inline_single_owner_alias",
        _ => "inline_target_into_owner",
    }
}

fn direct_similarity_reason_weight(reason: &str) -> usize {
    match reason {
        "same_caller_structure" => 20,
        "same_parent_scope" => 12,
        "shared_call_profile" => 10,
        "similar_token_band" => 4,
        _ => 1,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frozen_fixture_root() -> PathBuf {
        use std::time::{SystemTime, UNIX_EPOCH};

        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock after Unix epoch")
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "agent-canon-python-structure-hash-frozen-{}-{nonce}",
            std::process::id()
        ));
        let fixtures: [(&str, &[u8]); 5] = [
            (
                "pkg/__init__.py",
                include_bytes!("../../../../../tests/fixtures/python_structure_hash/pkg/__init__.py.fixture"),
            ),
            (
                "pkg/alpha.py",
                include_bytes!("../../../../../tests/fixtures/python_structure_hash/pkg/alpha.py.fixture"),
            ),
            (
                "pkg/beta.py",
                include_bytes!("../../../../../tests/fixtures/python_structure_hash/pkg/beta.py.fixture"),
            ),
            (
                "pkg/crlf.py",
                include_bytes!("../../../../../tests/fixtures/python_structure_hash/pkg/crlf.py.fixture"),
            ),
            (
                "pkg/excluded/unwanted.py",
                include_bytes!("../../../../../tests/fixtures/python_structure_hash/pkg/excluded/unwanted.py.fixture"),
            ),
        ];
        for (relative, bytes) in fixtures {
            let path = root.join(relative);
            fs::create_dir_all(path.parent().expect("fixture parent"))
                .expect("create fixture parent");
            fs::write(path, bytes).expect("write frozen Python fixture");
        }
        root
    }

    fn expected_duplicate_hash(report: &Value, names: &[&str], role: &str) -> String {
        report["findings"]
            .as_array()
            .expect("findings array")
            .iter()
            .find(|finding| {
                finding["kind"] == "duplicate_structural_hash"
                    && finding["role"] == role
                    && finding["instances"].as_array().is_some_and(|instances| {
                        names
                            .iter()
                            .all(|name| instances.iter().any(|instance| instance["name"] == *name))
                    })
            })
            .and_then(|finding| finding["hash"].as_str())
            .expect("duplicate pair in report")
            .to_string()
    }

    #[test]
    fn native_ast_records_match_frozen_cpython_extractor() {
        let root = frozen_fixture_root();
        let root = root.canonicalize().expect("canonical fixture root");
        let initial = source_files(&root, &["pkg".to_string()], &["pkg/excluded".to_string()]);
        let files =
            expand_with_repo_import_neighborhood(&root, initial, &["pkg/excluded".to_string()]);
        let extraction = extract_ast_blocks(&root, &files).expect("native AST extraction");
        let actual =
            serde_json::to_value(&extraction.blocks).expect("serialize native AST records");
        let expected: Value = serde_json::from_str(include_str!(
            "../../../../../tests/fixtures/python_structure_hash/expected/extractor-output.json"
        ))
        .expect("frozen extractor JSON");

        assert_eq!(extraction.parse_error_count, 0);
        assert_eq!(
            extraction.protocol_symbol_count as u64,
            expected["summary"]["protocol_symbols"]
                .as_u64()
                .expect("protocol symbol count")
        );
        assert_eq!(actual, expected["blocks"]);
        let crlf_bytes = fs::read(root.join("pkg/crlf.py")).expect("CRLF fixture bytes");
        let frozen_crlf_bytes: &[u8] = include_bytes!(
            "../../../../../tests/fixtures/python_structure_hash/pkg/crlf.py.fixture"
        );
        assert_eq!(crlf_bytes.as_slice(), frozen_crlf_bytes);
        fs::remove_dir_all(root).expect("remove frozen fixture root");
    }

    #[test]
    fn native_cli_outputs_and_hashes_match_frozen_baseline() {
        let root = frozen_fixture_root();
        let cli_args = [
            "--root",
            root.to_str().expect("fixture root UTF-8"),
            "--exclude",
            "pkg/excluded",
            "--min-tokens",
            "1",
            "--max-findings",
            "500",
            "pkg",
            "--format",
            "json",
        ]
        .into_iter()
        .map(str::to_string)
        .collect::<Vec<_>>();
        let args = Args::parse(&cli_args).expect("public CLI argument shape");
        let analysis = analyze(&args).expect("native frozen fixture analysis");
        let text_args = cli_args
            .iter()
            .cloned()
            .map(|arg| {
                if arg == "json" {
                    "text".to_string()
                } else {
                    arg
                }
            })
            .collect::<Vec<_>>();
        assert_eq!(
            Args::parse(&text_args)
                .expect("text output CLI arguments")
                .format,
            OutputFormat::Text
        );
        let report_text = render_json_output(&analysis);
        let report: Value = serde_json::from_str(&report_text).expect("native report JSON");
        let expected_json = include_str!(
            "../../../../../tests/fixtures/python_structure_hash/expected/cli-json.stdout"
        );
        let expected_text = include_str!(
            "../../../../../tests/fixtures/python_structure_hash/expected/cli-text.stdout"
        );
        let hashes: Value = serde_json::from_str(include_str!(
            "../../../../../tests/fixtures/python_structure_hash/expected/baseline-hashes.json"
        ))
        .expect("baseline hash manifest");

        assert_eq!(format!("{report_text}\n"), expected_json);
        assert_eq!(render_text_output(&analysis), expected_text);
        assert_eq!(analysis_exit_status(&analysis), 1);
        assert_eq!(report["summary"]["analyzed_file_count"], 4);
        assert_eq!(report["summary"]["groups"], 13);
        assert_eq!(
            expected_duplicate_hash(&report, &["alpha", "beta"], "implementation"),
            hashes["duplicate_pair_hashes"]["alpha_beta"]
                .as_str()
                .expect("alpha/beta baseline hash")
        );
        assert_eq!(
            expected_duplicate_hash(&report, &["FirstRecord", "SecondRecord"], "implementation"),
            hashes["duplicate_pair_hashes"]["first_second_record"]
                .as_str()
                .expect("record baseline hash")
        );
        assert_eq!(
            expected_duplicate_hash(&report, &["Proto", "SecondProto"], "protocol"),
            hashes["duplicate_pair_hashes"]["protocol_pair"]
                .as_str()
                .expect("protocol baseline hash")
        );
        assert_eq!(
            expected_duplicate_hash(
                &report,
                &["Implementation", "ImplementationTwo"],
                "implementation"
            ),
            hashes["duplicate_pair_hashes"]["implementation_pair"]
                .as_str()
                .expect("implementation baseline hash")
        );
        assert_eq!(
            expected_duplicate_hash(&report, &["FirstAlias", "SecondAlias"], "alias"),
            hashes["duplicate_pair_hashes"]["alias_pair"]
                .as_str()
                .expect("alias baseline hash")
        );
        fs::remove_dir_all(root).expect("remove frozen fixture root");
    }

    #[test]
    fn stable_hash_ignores_names_when_canonical_payload_is_equal() {
        let canonical = json!(["Return", [["value", ["Name", []]]]]);
        let left = stable_hash(&format!("Function:2:{canonical}"));
        let right = stable_hash(&format!("Function:2:{canonical}"));
        assert_eq!(left, right);
    }

    #[test]
    fn import_hash_tracks_import_surface_separately() {
        let left = stable_hash(r#"[["import","jax.numpy"]]"#);
        let right = stable_hash(r#"[["import","numpy"]]"#);
        assert_ne!(left, right);
    }

    #[test]
    fn module_scope_detects_cross_module_groups() {
        let blocks = vec![block_for_test("a.b"), block_for_test("a.c")];
        assert_eq!(module_scope(&blocks), ModuleScope::CrossModule);
    }

    #[test]
    fn source_files_expand_repo_import_neighborhood() {
        let root = std::env::temp_dir().join(format!(
            "agent-canon-python-structure-hash-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&root);
        let pkg = root.join("pkg");
        let python_pkg = root.join("python").join("pkg");
        fs::create_dir_all(&pkg).expect("pkg dir");
        fs::create_dir_all(&python_pkg).expect("python pkg dir");
        fs::write(pkg.join("a.py"), "from .b import B\n").expect("a.py");
        fs::write(
            pkg.join("b.py"),
            "from .c import C\nimport pkg.d\nclass B: pass\n",
        )
        .expect("b.py");
        fs::write(pkg.join("c.py"), "class C: pass\n").expect("c.py");
        fs::write(python_pkg.join("d.py"), "class D: pass\n").expect("d.py");

        let requested_root = root.clone();
        let root = root.canonicalize().expect("canonical fixture root");
        let initial = source_files(&root, &["pkg/a.py".to_string()], &[]);
        let expanded = expand_with_repo_import_neighborhood(&root, initial, &[]);
        let relative = expanded
            .iter()
            .map(|path| {
                path.strip_prefix(&root)
                    .unwrap_or(path)
                    .to_string_lossy()
                    .replace('\\', "/")
            })
            .collect::<BTreeSet<_>>();

        assert_eq!(
            relative,
            BTreeSet::from([
                "pkg/a.py".to_string(),
                "pkg/b.py".to_string(),
                "pkg/c.py".to_string(),
                "python/pkg/d.py".to_string()
            ])
        );
        let analysis = analyze(&Args {
            root: requested_root,
            paths: vec!["pkg/a.py".to_string()],
            excludes: Vec::new(),
            min_tokens: 1,
            max_findings: 20,
            format: OutputFormat::Json,
        })
        .expect("public analysis accepts the requested root spelling");
        assert_eq!(
            analysis.analyzed_files.into_iter().collect::<BTreeSet<_>>(),
            relative
        );
        fs::remove_dir_all(root).expect("cleanup temp tree");
    }

    fn block_for_test(module: &str) -> Block {
        Block {
            path: format!("{}.py", module.replace('.', "/")),
            module: module.to_string(),
            line: 1,
            end_line: 2,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "f".to_string(),
            qualname: "f".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 0,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("Function:0:[]"),
            context_hash: stable_hash(module),
            token_count: 8,
            public_api: false,
            calls: Vec::new(),
            references: Vec::new(),
        }
    }

    #[test]
    fn single_caller_groups_multiple_call_sites_by_enclosing_block() {
        let helper = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 1,
            end_line: 2,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "_helper".to_string(),
            qualname: "_helper".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("helper"),
            context_hash: stable_hash("sample"),
            token_count: 12,
            public_api: false,
            calls: vec![
                CallRef {
                    name: "load_config".to_string(),
                    line: 1,
                },
                CallRef {
                    name: "validate_inputs".to_string(),
                    line: 2,
                },
            ],
            references: Vec::new(),
        };
        let caller = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 4,
            end_line: 7,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "public_api".to_string(),
            qualname: "public_api".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("caller"),
            context_hash: stable_hash("sample"),
            token_count: 20,
            public_api: true,
            calls: vec![
                CallRef {
                    name: "_helper".to_string(),
                    line: 5,
                },
                CallRef {
                    name: "_helper".to_string(),
                    line: 6,
                },
                CallRef {
                    name: "load_config".to_string(),
                    line: 7,
                },
                CallRef {
                    name: "validate_inputs".to_string(),
                    line: 8,
                },
            ],
            references: Vec::new(),
        };
        let peer = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 9,
            end_line: 12,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "other_api".to_string(),
            qualname: "other_api".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("peer"),
            context_hash: stable_hash("sample"),
            token_count: 18,
            public_api: true,
            calls: vec![
                CallRef {
                    name: "load_config".to_string(),
                    line: 10,
                },
                CallRef {
                    name: "validate_inputs".to_string(),
                    line: 11,
                },
            ],
            references: Vec::new(),
        };
        let findings = single_caller_findings(&[helper, caller, peer], 8);
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].target.qualname, "_helper");
        assert_eq!(findings[0].caller.qualname, "public_api");
        assert_eq!(findings[0].call_site_count, 2);
        assert_eq!(findings[0].caller.call_lines, vec![5, 6]);
        assert_eq!(findings[0].similar_callers[0].qualname, "other_api");
        assert_eq!(findings[0].similar_callers[0].shared_call_count, 2);
        assert!(!findings[0]
            .similar_callers
            .iter()
            .any(|caller| caller.qualname == "_helper"));
        let candidates = direct_integration_candidates_json(&findings[0]);
        assert_eq!(
            candidates[0]["candidate_schema_scope"],
            "ast_use_graph_only"
        );
        assert!(candidates[0]["reason_codes"]
            .as_array()
            .expect("reason codes")
            .iter()
            .any(|code| code == "unique_owner"));
    }

    #[test]
    fn one_shared_module_level_call_does_not_create_similar_caller() {
        let helper = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 1,
            end_line: 2,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "_helper".to_string(),
            qualname: "_helper".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("helper"),
            context_hash: stable_hash("sample"),
            token_count: 12,
            public_api: false,
            calls: Vec::new(),
            references: Vec::new(),
        };
        let caller = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 4,
            end_line: 7,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "public_api".to_string(),
            qualname: "public_api".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("caller"),
            context_hash: stable_hash("sample"),
            token_count: 20,
            public_api: true,
            calls: vec![
                CallRef {
                    name: "_helper".to_string(),
                    line: 5,
                },
                CallRef {
                    name: "load".to_string(),
                    line: 6,
                },
            ],
            references: Vec::new(),
        };
        let peer = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 9,
            end_line: 12,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "other_api".to_string(),
            qualname: "other_api".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("peer"),
            context_hash: stable_hash("sample"),
            token_count: 18,
            public_api: true,
            calls: vec![CallRef {
                name: "load".to_string(),
                line: 10,
            }],
            references: Vec::new(),
        };

        let findings = single_caller_findings(&[helper, caller, peer], 8);

        assert_eq!(findings.len(), 1);
        assert!(findings[0].similar_callers.is_empty());
    }

    #[test]
    fn single_caller_class_target_detects_annotation_owner() {
        let class_target = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 1,
            end_line: 8,
            kind: "Class".to_string(),
            role: "implementation".to_string(),
            name: "Carry".to_string(),
            qualname: "Carry".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 0,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("class"),
            context_hash: stable_hash("sample"),
            token_count: 16,
            public_api: false,
            calls: Vec::new(),
            references: Vec::new(),
        };
        let owner = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 10,
            end_line: 15,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "solve".to_string(),
            qualname: "solve".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 0,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("owner"),
            context_hash: stable_hash("sample"),
            token_count: 20,
            public_api: true,
            calls: Vec::new(),
            references: vec![CallRef {
                name: "Carry".to_string(),
                line: 11,
            }],
        };

        let findings = single_caller_findings(&[class_target, owner], 8);

        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].target.kind, "Class");
        assert_eq!(findings[0].target.qualname, "Carry");
        assert_eq!(findings[0].caller.qualname, "solve");
        assert_eq!(findings[0].call_site_count, 1);
    }

    #[test]
    fn single_callee_reports_only_non_public_wrappers() {
        let callee = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 1,
            end_line: 4,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "_target".to_string(),
            qualname: "_target".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("target"),
            context_hash: stable_hash("sample"),
            token_count: 16,
            public_api: false,
            calls: Vec::new(),
            references: Vec::new(),
        };
        let wrapper = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 6,
            end_line: 12,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "_wrapper".to_string(),
            qualname: "_wrapper".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("wrapper"),
            context_hash: stable_hash("sample"),
            token_count: 24,
            public_api: false,
            calls: vec![
                CallRef {
                    name: "_target".to_string(),
                    line: 8,
                },
                CallRef {
                    name: "_target".to_string(),
                    line: 10,
                },
            ],
            references: Vec::new(),
        };
        let public_wrapper = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 14,
            end_line: 20,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "public_wrapper".to_string(),
            qualname: "public_wrapper".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("public_wrapper"),
            context_hash: stable_hash("sample"),
            token_count: 24,
            public_api: true,
            calls: vec![CallRef {
                name: "_target".to_string(),
                line: 16,
            }],
            references: Vec::new(),
        };

        let findings = single_callee_findings(&[callee, wrapper, public_wrapper], 8);

        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].caller.qualname, "_wrapper");
        assert_eq!(findings[0].callee.qualname, "_target");
        assert_eq!(findings[0].call_site_count, 2);
        assert_eq!(findings[0].callee.call_lines, vec![8, 10]);
    }

    #[test]
    fn single_callee_ignores_annotation_only_references() {
        let target = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 1,
            end_line: 4,
            kind: "Class".to_string(),
            role: "implementation".to_string(),
            name: "Target".to_string(),
            qualname: "Target".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("target"),
            context_hash: stable_hash("sample"),
            token_count: 16,
            public_api: false,
            calls: Vec::new(),
            references: Vec::new(),
        };
        let annotation_only_wrapper = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 6,
            end_line: 12,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "_typed_wrapper".to_string(),
            qualname: "_typed_wrapper".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("typed_wrapper"),
            context_hash: stable_hash("sample"),
            token_count: 24,
            public_api: false,
            calls: Vec::new(),
            references: vec![CallRef {
                name: "Target".to_string(),
                line: 8,
            }],
        };

        let findings = single_callee_findings(&[target, annotation_only_wrapper], 8);

        assert!(findings.is_empty());
    }
}
