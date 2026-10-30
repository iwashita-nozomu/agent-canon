// @dependency-start
// contract implementation
// responsibility Checks Python run-log ownership and Info summary emission contracts.
// upstream design ../../../../../documents/conventions/coding-conventions-logging.md logging convention overview
// upstream design ../../../../../documents/conventions/common/01_principles.md canonical simplicity principle
// upstream implementation python_ast.rs reuses Python AST parsing and source line offsets
// upstream implementation ../../../../../tools/support/path_filters.py shared path exclusion contract
// downstream implementation ../../../../../tests/agent_tools/test_check_run_log_contract.py CLI behavior oracles
// @dependency-end

use crate::python_ast::{line_at_offset, node_line, normalize_python_newlines};
use rustpython_ast::{self as ast, Visitor};
use rustpython_parser::Parse;
use serde::Serialize;
use serde_json::json;
use std::collections::{BTreeSet, HashMap};
use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};

const DEFAULT_PATHS: &[&str] = &["python/jax_util"];
const DEFAULT_EXCLUDES: &[&str] = &[
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "python/tests",
    "reports",
    "tests",
    "vendor",
];
const RUN_LOG_INTERNAL_MODULES: &[&str] = &["python/jax_util/base/_run_log.py"];
const DIRECT_RUN_LOG_NAMES: &[&str] = &[
    "RunLogWriter",
    "InfoRunLogEmitter",
    "begin_run_log",
    "child_run_log_context",
    "write_device_run_log_event",
    "write_host_run_log_event",
    "write_info_run_log_event",
];
const SUMMARY_FIELD_LIST_SUFFIXES: &[&str] = &[
    "_INFO_FIELD_NAMES",
    "_SUMMARY_FIELD_NAMES",
    "_RUN_LOG_FIELD_NAMES",
];

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Finding {
    pub path: String,
    pub line: usize,
    pub code: String,
    pub symbol: String,
    pub reason: String,
}

impl Finding {
    fn new(path: &str, line: usize, code: &str, symbol: &str, reason: &str) -> Self {
        Self {
            path: path.to_owned(),
            line,
            code: code.to_owned(),
            symbol: symbol.to_owned(),
            reason: reason.to_owned(),
        }
    }

    pub fn render(&self) -> String {
        format!(
            "RUN_LOG_CONTRACT_FINDING={}:{}:{}:{}:{}",
            self.path, self.line, self.code, self.symbol, self.reason
        )
    }
}

struct FindingVisitor<'a> {
    relative_path: &'a str,
    source: &'a str,
    findings: Vec<Finding>,
}

impl FindingVisitor<'_> {
    fn push(&mut self, line: usize, code: &str, symbol: &str, reason: &str) {
        self.findings
            .push(Finding::new(self.relative_path, line, code, symbol, reason));
    }
}

impl Visitor for FindingVisitor<'_> {
    fn visit_stmt_import_from(&mut self, node: ast::StmtImportFrom) {
        let line = node_line(self.source, &node);
        for alias in &node.names {
            let name = alias.name.as_str();
            if DIRECT_RUN_LOG_NAMES.contains(&name) {
                self.push(
                    line,
                    "direct-run-log-writer-import",
                    name,
                    "use RunLog.submit/submit_device/submit_info; low-level writers are implementation details",
                );
            }
        }
        self.generic_visit_stmt_import_from(node);
    }

    fn visit_expr_call(&mut self, node: ast::ExprCall) {
        let line = node_line(self.source, &node);
        let called_name = base_name(&node.func)
            .rsplit('.')
            .next()
            .unwrap_or("")
            .to_owned();
        if DIRECT_RUN_LOG_NAMES.contains(&called_name.as_str()) {
            self.push(
                line,
                "direct-run-log-writer-call",
                &called_name,
                "use RunLog.submit/submit_device/submit_info; low-level writers are implementation details",
            );
        }
        if called_name == "submit_info" && has_keyword(&node, "field_names") {
            self.push(
                line,
                "manual-info-field-list",
                "submit_info.field_names",
                "Info summary logs should auto-resolve public amp.Info fields; pass field_names only in explicit alias tests",
            );
        }
        if matches!(called_name.as_str(), "submit" | "submit_device")
            && keyword_string_value(&node, "event").as_deref() == Some("iter")
        {
            let symbol = format!("{called_name}(event='iter')");
            self.push(
                line,
                "iteration-log-without-info",
                &symbol,
                "iteration diagnostics must use the module Info type via RunLog.submit_info(..., event='iter')",
            );
        }
        self.generic_visit_expr_call(node);
    }

    fn visit_stmt_assign(&mut self, node: ast::StmtAssign) {
        self.visit_assignment(
            node.targets.iter(),
            Some(node.value.as_ref()),
            node_line(self.source, &node),
        );
        self.generic_visit_stmt_assign(node);
    }

    fn visit_stmt_ann_assign(&mut self, node: ast::StmtAnnAssign) {
        self.visit_assignment(
            std::iter::once(node.target.as_ref()),
            node.value.as_deref(),
            node_line(self.source, &node),
        );
        self.generic_visit_stmt_ann_assign(node);
    }
}

impl FindingVisitor<'_> {
    fn visit_assignment<'a>(
        &mut self,
        targets: impl IntoIterator<Item = &'a ast::Expr>,
        value: Option<&ast::Expr>,
        line: usize,
    ) {
        let matched_callee = value.and_then(calls_name);
        for target in targets {
            for name in target_names(target) {
                if SUMMARY_FIELD_LIST_SUFFIXES
                    .iter()
                    .any(|suffix| name.ends_with(suffix))
                {
                    self.push(
                        line,
                        "summary-field-list-constant",
                        &name,
                        "summary log field lists duplicate amp.Info annotations; let RunLog.submit_info resolve fields",
                    );
                }
                if let Some(callee) = matched_callee.as_deref() {
                    let symbol = format!("{name}={callee}");
                    self.push(
                        line,
                        "direct-run-log-writer-object",
                        &symbol,
                        "do not create dedicated summary/log writer objects; use the algorithm RunLog",
                    );
                }
            }
        }
    }
}

fn base_name(expression: &ast::Expr) -> String {
    match expression {
        ast::Expr::Name(node) => node.id.to_string(),
        ast::Expr::Attribute(node) => {
            let prefix = base_name(&node.value);
            if prefix.is_empty() {
                node.attr.to_string()
            } else {
                format!("{prefix}.{}", node.attr)
            }
        }
        ast::Expr::Call(node) => base_name(&node.func),
        _ => String::new(),
    }
}

fn has_keyword(call: &ast::ExprCall, name: &str) -> bool {
    call.keywords
        .iter()
        .any(|keyword| keyword.arg.as_deref() == Some(name))
}

fn keyword_string_value(call: &ast::ExprCall, name: &str) -> Option<String> {
    call.keywords.iter().find_map(|keyword| {
        if keyword.arg.as_deref() != Some(name) {
            return None;
        }
        match &keyword.value {
            ast::Expr::Constant(value) => match &value.value {
                ast::Constant::Str(value) => Some(value.clone()),
                _ => None,
            },
            _ => None,
        }
    })
}

fn target_names(expression: &ast::Expr) -> Vec<String> {
    match expression {
        ast::Expr::Name(node) => vec![node.id.to_string()],
        ast::Expr::Tuple(node) => node.elts.iter().flat_map(target_names).collect(),
        ast::Expr::List(node) => node.elts.iter().flat_map(target_names).collect(),
        _ => Vec::new(),
    }
}

fn calls_name(expression: &ast::Expr) -> Option<String> {
    let ast::Expr::Call(call) = expression else {
        return None;
    };
    let name = base_name(&call.func)
        .rsplit('.')
        .next()
        .unwrap_or("")
        .to_owned();
    DIRECT_RUN_LOG_NAMES
        .contains(&name.as_str())
        .then_some(name)
}

fn analyze_file(root: &Path, path: &Path) -> Result<Vec<Finding>, String> {
    let relative = relative_path(root, path);
    let source = fs::read_to_string(path)
        .map_err(|error| format!("failed to read Python source {relative}: {error}"))?;
    let source = normalize_python_newlines(&source);
    let suite = ast::Suite::parse(&source, &relative).map_err(|error| {
        format!(
            "failed to parse Python source {relative} at line {}: {error}",
            line_at_offset(&source, error.offset.to_usize())
        )
    })?;
    if RUN_LOG_INTERNAL_MODULES.contains(&relative.as_str()) {
        return Ok(Vec::new());
    }
    let mut visitor = FindingVisitor {
        relative_path: &relative,
        source: &source,
        findings: Vec::new(),
    };
    for statement in suite {
        visitor.visit_stmt(statement);
    }
    Ok(visitor.findings)
}

fn collect_findings(root: &Path, files: &[PathBuf]) -> Result<Vec<Finding>, String> {
    let mut findings = Vec::new();
    for path in files {
        findings.extend(analyze_file(root, path)?);
    }
    findings.sort_by(|left, right| {
        (&left.path, left.line, &left.code, &left.symbol).cmp(&(
            &right.path,
            right.line,
            &right.code,
            &right.symbol,
        ))
    });
    Ok(findings)
}

fn absolute_path(path: &Path) -> PathBuf {
    if path.is_absolute() {
        path.canonicalize().unwrap_or_else(|_| path.to_path_buf())
    } else {
        let candidate = std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(path);
        candidate.canonicalize().unwrap_or(candidate)
    }
}

fn relative_path(root: &Path, path: &Path) -> String {
    let root = absolute_path(root);
    let path = absolute_path(path);
    path.strip_prefix(&root)
        .map(Path::to_path_buf)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn is_hidden(path: &Path) -> bool {
    path.components()
        .any(|component| component.as_os_str().to_string_lossy().starts_with('.'))
}

fn path_is_excluded(relative: &Path, exclude_patterns: &[String]) -> bool {
    let relative_posix = relative.to_string_lossy().replace('\\', "/");
    for raw_pattern in exclude_patterns {
        let pattern = raw_pattern.trim().trim_matches('/');
        if pattern.is_empty() {
            continue;
        }
        if pattern
            .chars()
            .any(|character| matches!(character, '*' | '?' | '[' | ']'))
        {
            if fnmatchcase(&relative_posix, pattern) {
                return true;
            }
            continue;
        }
        if relative_posix == pattern
            || relative_posix.starts_with(&format!("{pattern}/"))
            || relative
                .components()
                .any(|part| part.as_os_str().to_string_lossy() == pattern)
        {
            return true;
        }
    }
    false
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
    let mut class_start = start + 1;
    let negated = pattern.get(class_start) == Some(&'!');
    if negated {
        class_start += 1;
    }
    let search_start = if pattern.get(class_start) == Some(&']') {
        class_start + 1
    } else {
        class_start
    };
    let end = (search_start..pattern.len()).find(|index| pattern[*index] == ']')?;
    if end == class_start {
        return None;
    }
    let mut matched = false;
    let mut index = class_start;
    while index < end {
        if index + 2 < end && pattern[index + 1] == '-' {
            let lower = pattern[index];
            let upper = pattern[index + 2];
            if lower <= upper {
                matched |= lower <= *value && *value <= upper;
            } else {
                matched |= *value == lower || *value == '-' || *value == upper;
            }
            index += 3;
        } else {
            matched |= pattern[index] == *value;
            index += 1;
        }
    }
    Some((end + 1, if negated { !matched } else { matched }))
}

fn add_python_file(root: &Path, path: &Path, excludes: &[String], files: &mut BTreeSet<PathBuf>) {
    if path.extension() != Some(OsStr::new("py")) || !path.is_file() {
        return;
    }
    let path = absolute_path(path);
    let relative = PathBuf::from(relative_path(root, &path));
    if is_hidden(&relative) || path_is_excluded(&relative, excludes) {
        return;
    }
    files.insert(path);
}

fn collect_python_directory(
    root: &Path,
    directory: &Path,
    excludes: &[String],
    files: &mut BTreeSet<PathBuf>,
) {
    let Ok(entries) = fs::read_dir(directory) else {
        return;
    };
    let mut paths = entries
        .flatten()
        .map(|entry| entry.path())
        .collect::<Vec<_>>();
    paths.sort();
    for path in paths {
        if fs::symlink_metadata(&path).is_ok_and(|metadata| metadata.file_type().is_dir()) {
            collect_python_directory(root, &path, excludes, files);
        } else {
            add_python_file(root, &path, excludes, files);
        }
    }
}

fn iter_python_files(root: &Path, raw_paths: &[String], excludes: &[String]) -> Vec<PathBuf> {
    let targets = if raw_paths.is_empty() {
        DEFAULT_PATHS
            .iter()
            .map(|path| root.join(path))
            .collect::<Vec<_>>()
    } else {
        raw_paths
            .iter()
            .map(|path| root.join(path))
            .collect::<Vec<_>>()
    };
    let mut files = BTreeSet::new();
    for target in targets {
        if target.is_file() && target.extension() == Some(OsStr::new("py")) {
            files.insert(absolute_path(&target));
        } else if target.is_dir() {
            collect_python_directory(root, &target, excludes, &mut files);
        }
    }
    files.into_iter().collect()
}

pub fn render_json(files: &[PathBuf], findings: &[Finding]) -> String {
    let value = json!({
        "summary": {"files": files.len(), "findings": findings.len()},
        "findings": findings,
    });
    let rendered =
        serde_json::to_string_pretty(&value).expect("run-log contract JSON serialization");
    escape_non_ascii_json(&rendered)
}

fn escape_non_ascii_json(value: &str) -> String {
    let mut escaped = String::with_capacity(value.len());
    for character in value.chars() {
        let codepoint = character as u32;
        if codepoint <= 0x7f {
            escaped.push(character);
        } else if codepoint <= 0xffff {
            escaped.push_str(&format!("\\u{codepoint:04x}"));
        } else {
            let supplementary = codepoint - 0x1_0000;
            let high = 0xd800 + (supplementary >> 10);
            let low = 0xdc00 + (supplementary & 0x3ff);
            escaped.push_str(&format!("\\u{high:04x}\\u{low:04x}"));
        }
    }
    escaped
}

pub fn render_text(files: &[PathBuf], findings: &[Finding]) -> String {
    let mut lines = vec![format!("RUN_LOG_CONTRACT_FILES={}", files.len())];
    lines.push(format!("RUN_LOG_CONTRACT_FINDINGS={}", findings.len()));
    lines.extend(findings.iter().map(Finding::render));
    lines.push(format!(
        "RUN_LOG_CONTRACT={}",
        if findings.is_empty() { "pass" } else { "fail" }
    ));
    lines.join("\n")
}

#[derive(Debug)]
struct Args {
    paths: Vec<String>,
    root: PathBuf,
    excludes: Vec<String>,
    format: OutputFormat,
    fail_on_finding: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

enum ParsedArgs {
    Help,
    Run(Args),
}

const CLI_USAGE: &str = "usage: check_run_log_contract.py [-h] [--root ROOT] [--exclude EXCLUDE] [--format {text,json}] [--fail-on-finding] [paths ...]";

const CLI_HELP: &str = "Check run-log conventions: Info summaries should auto-resolve from amp.Info, product code should not call low-level run-log writers, and summary field-name constants should not duplicate Info fields.";

fn parse_args(args: &[String]) -> Result<ParsedArgs, String> {
    let mut paths = Vec::new();
    let mut root = PathBuf::from(".");
    let mut excludes = DEFAULT_EXCLUDES
        .iter()
        .map(|pattern| (*pattern).to_owned())
        .collect::<Vec<_>>();
    let mut format = OutputFormat::Text;
    let mut fail_on_finding = false;
    let mut index = 0;
    let mut positional_only = false;
    while index < args.len() {
        let argument = args[index].as_str();
        if positional_only {
            paths.push(args[index].clone());
            index += 1;
            continue;
        }
        if argument == "--" {
            positional_only = true;
            index += 1;
            continue;
        }
        if matches!(argument, "-h" | "--help") {
            return Ok(ParsedArgs::Help);
        }
        if argument == "--fail-on-finding" {
            fail_on_finding = true;
            index += 1;
            continue;
        }
        if matches!(argument, "--root" | "--exclude" | "--format") {
            let option = argument;
            let value = args
                .get(index + 1)
                .ok_or_else(|| format!("argument {option}: expected one argument"))?;
            if value.starts_with('-') {
                return Err(format!("argument {option}: expected one argument"));
            }
            match option {
                "--root" => {
                    root = if value.is_empty() {
                        PathBuf::from(".")
                    } else {
                        PathBuf::from(value)
                    }
                }
                "--exclude" => excludes.push(value.clone()),
                "--format" => {
                    format = match value.as_str() {
                        "text" => OutputFormat::Text,
                        "json" => OutputFormat::Json,
                        _ => return Err(format!("argument --format: invalid choice: '{value}' (choose from 'text', 'json')")),
                    };
                }
                _ => unreachable!(),
            }
            index += 2;
            continue;
        }
        if let Some(value) = argument.strip_prefix("--root=") {
            root = if value.is_empty() {
                PathBuf::from(".")
            } else {
                PathBuf::from(value)
            };
            index += 1;
            continue;
        }
        if let Some(value) = argument.strip_prefix("--exclude=") {
            excludes.push(value.to_owned());
            index += 1;
            continue;
        }
        if let Some(value) = argument.strip_prefix("--format=") {
            format = match value {
                "text" => OutputFormat::Text,
                "json" => OutputFormat::Json,
                _ => {
                    return Err(format!(
                        "argument --format: invalid choice: '{value}' (choose from 'text', 'json')"
                    ))
                }
            };
            index += 1;
            continue;
        }
        if argument.starts_with('-') {
            return Err(format!("unrecognized arguments: {argument}"));
        }
        paths.push(args[index].clone());
        index += 1;
    }
    Ok(ParsedArgs::Run(Args {
        paths,
        root,
        excludes,
        format,
        fail_on_finding,
    }))
}

fn write_help() {
    println!("{CLI_USAGE}\n\n{CLI_HELP}\n\noptions:");
    println!("  -h, --help            show this help message and exit");
    println!("  --root ROOT           Repository root. Defaults to cwd.");
    println!(
        "  --exclude EXCLUDE     Path, path prefix, path part, or glob to exclude. Repeatable."
    );
    println!("  --format {{text,json}}");
    println!("  --fail-on-finding");
}

/// Runs the run-log contract checker through the native AgentCanon CLI.
pub fn run(raw_args: &[String]) -> i32 {
    let args = match parse_args(raw_args) {
        Ok(ParsedArgs::Help) => {
            write_help();
            return 0;
        }
        Ok(ParsedArgs::Run(args)) => args,
        Err(error) => {
            eprintln!("{CLI_USAGE}");
            eprintln!("check_run_log_contract.py: error: {error}");
            return 2;
        }
    };
    let root = absolute_path(&args.root);
    let files = iter_python_files(&root, &args.paths, &args.excludes);
    let findings = match collect_findings(&root, &files) {
        Ok(findings) => findings,
        Err(error) => {
            eprintln!("RUN_LOG_CONTRACT_ERROR={error}");
            return 1;
        }
    };
    match args.format {
        OutputFormat::Json => println!("{}", render_json(&files, &findings)),
        OutputFormat::Text => println!("{}", render_text(&files, &findings)),
    }
    if args.fail_on_finding && !findings.is_empty() {
        1
    } else {
        0
    }
}
