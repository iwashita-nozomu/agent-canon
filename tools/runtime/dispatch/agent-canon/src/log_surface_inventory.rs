// @dependency-start
// contract implementation
// responsibility Inventories machine-readable log and hook output fields from hooks, skills, Python tools, shell tools, and Rust CLI tools.
// upstream implementation ../../../archive/log_surface_inventory.py frozen scanner and output contract
// upstream implementation python_ast.rs Python source normalization and source positions
// upstream implementation authority/mod.rs captures and verifies inherited child authority context
// downstream implementation main.rs exposes the stable log-surface-inventory command
// downstream implementation ../../../../../tests/agent_tools/test_log_surface_inventory.py verifies extraction and baseline behavior
// @dependency-end

//! Inventory machine-readable fields emitted by hooks, skills, and tools.

use crate::python_ast::{line_at_offset, normalize_python_newlines};
use agent_canon::authority::{
    NonEmptyTrimmedString, Nonce128, ParentRootAttestor, ParentRootReject,
};
use regex::Regex;
use rustpython_ast::{Ranged, Visitor};
use rustpython_parser::{ast, Parse};
use serde_json::{Map, Number, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::env;
use std::ffi::OsStr;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::Command;
use std::sync::OnceLock;

const EXCLUDED_PARTS: &[&str] = &[
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "reports",
];
const SKILL_PATTERNS: &[&str] = &[".codex/personal/skills/*/SKILL.md", "agents/skills/*.md"];
const HOOK_PATTERNS: &[&str] = &[".codex/hooks/*.py", ".codex/hooks/*.sh"];
const TOOL_PATTERNS: &[&str] = &[
    ".github/scripts/*.sh",
    "tools/*.py",
    "tools/*.sh",
    "tools/**/*.py",
    "tools/**/*.sh",
    "tools/**/*.bash",
];
const RUST_TOOL_PATTERNS: &[&str] = &[
    "tools/runtime/dispatch/agent-canon/src/*.rs",
    "tools/runtime/dispatch/agent-canon/src/**/*.rs",
];
const OUTPUT_LINE_VARIABLES: &[&str] = &["lines", "output_lines", "report_lines"];
const MAX_DIFF_RECORDS: usize = 20;
const PURPOSE: &str = "log-surface-inventory";

static KEY_VALUE_RE: OnceLock<Regex> = OnceLock::new();
static SHELL_ECHO_RE: OnceLock<Regex> = OnceLock::new();
static RUST_PRINT_RE: OnceLock<Regex> = OnceLock::new();

type FieldIdentity = (String, SurfaceKind, String, String, Certainty);

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub enum SurfaceKind {
    Hook,
    Skill,
    Tool,
}

impl SurfaceKind {
    fn as_str(self) -> &'static str {
        match self {
            Self::Hook => "hook",
            Self::Skill => "skill",
            Self::Tool => "tool",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub enum Certainty {
    Dynamic,
    Static,
}

impl Certainty {
    fn as_str(self) -> &'static str {
        match self {
            Self::Static => "static",
            Self::Dynamic => "dynamic",
        }
    }
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct FieldRecord {
    pub path: String,
    pub surface: SurfaceKind,
    pub emitter: String,
    pub field: String,
    pub line: i64,
    pub certainty: Certainty,
}

impl FieldRecord {
    pub fn machine_line(&self, prefix: &str) -> String {
        format!(
            "{prefix}={}:{}:{}:{}:{}:{}",
            self.path,
            self.line,
            self.surface.as_str(),
            self.emitter,
            self.certainty.as_str(),
            self.field
        )
    }

    fn identity(&self) -> FieldIdentity {
        (
            self.path.clone(),
            self.surface,
            self.emitter.clone(),
            self.field.clone(),
            self.certainty,
        )
    }

    fn json_value(&self) -> Value {
        let mut value = Map::new();
        value.insert("path".into(), Value::String(self.path.clone()));
        value.insert(
            "surface".into(),
            Value::String(self.surface.as_str().into()),
        );
        value.insert("emitter".into(), Value::String(self.emitter.clone()));
        value.insert("field".into(), Value::String(self.field.clone()));
        value.insert("line".into(), Value::Number(Number::from(self.line)));
        value.insert(
            "certainty".into(),
            Value::String(self.certainty.as_str().into()),
        );
        Value::Object(value)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Inventory {
    pub schema_version: i64,
    pub scanned_files: Vec<String>,
    pub records: Vec<FieldRecord>,
}

impl Inventory {
    pub fn json_value(&self) -> Value {
        let mut value = Map::new();
        value.insert(
            "schema_version".into(),
            Value::Number(Number::from(self.schema_version)),
        );
        value.insert(
            "scanned_files".into(),
            Value::Array(
                self.scanned_files
                    .iter()
                    .cloned()
                    .map(Value::String)
                    .collect(),
            ),
        );
        value.insert(
            "records".into(),
            Value::Array(self.records.iter().map(FieldRecord::json_value).collect()),
        );
        Value::Object(value)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BaselineDiff {
    pub added: Vec<FieldRecord>,
    pub removed: Vec<FieldRecord>,
}

impl BaselineDiff {
    pub fn has_drift(&self) -> bool {
        !self.added.is_empty() || !self.removed.is_empty()
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum OutputFormat {
    Text,
    Json,
}

#[derive(Clone, Debug)]
struct Arguments {
    paths: Vec<String>,
    root: PathBuf,
    output: Option<PathBuf>,
    baseline: Option<PathBuf>,
    check: bool,
    format: OutputFormat,
    quiet: bool,
}

enum ParseResult {
    Help,
    Arguments(Arguments),
}

struct PythonLogSurfaceVisitor<'a> {
    relative_path: String,
    source: &'a str,
    surface: SurfaceKind,
    records: Vec<FieldRecord>,
    dict_assignments: HashMap<String, Vec<(String, Certainty)>>,
}

impl<'a> PythonLogSurfaceVisitor<'a> {
    fn new(relative_path: &str, source: &'a str, surface: SurfaceKind) -> Self {
        Self {
            relative_path: relative_path.to_owned(),
            source,
            surface,
            records: Vec::new(),
            dict_assignments: HashMap::new(),
        }
    }

    fn record(&mut self, emitter: &str, field: String, line: usize, certainty: Certainty) {
        self.records.push(FieldRecord {
            path: self.relative_path.clone(),
            surface: self.surface,
            emitter: emitter.to_owned(),
            field,
            line: line as i64,
            certainty,
        });
    }

    fn call_name(expression: &ast::Expr) -> String {
        match expression {
            ast::Expr::Name(name) => name.id.to_string(),
            ast::Expr::Attribute(attribute) => {
                let prefix = Self::call_name(&attribute.value);
                if prefix.is_empty() {
                    attribute.attr.to_string()
                } else {
                    format!("{prefix}.{}", attribute.attr)
                }
            }
            _ => String::new(),
        }
    }

    fn dict_fields(expression: &ast::Expr) -> Vec<(String, Certainty)> {
        let ast::Expr::Dict(dictionary) = expression else {
            return Vec::new();
        };
        dictionary
            .keys
            .iter()
            .map(|key| match key {
                None => ("<dynamic>".into(), Certainty::Dynamic),
                Some(ast::Expr::Constant(value)) => match &value.value {
                    ast::Constant::Str(value) => (value.clone(), Certainty::Static),
                    _ => ("<dynamic>".into(), Certainty::Dynamic),
                },
                Some(_) => ("<dynamic>".into(), Certainty::Dynamic),
            })
            .collect()
    }

    fn fields_from_node(&self, expression: &ast::Expr) -> Vec<(String, Certainty)> {
        match expression {
            ast::Expr::Dict(_) => Self::dict_fields(expression),
            ast::Expr::Name(name) => self
                .dict_assignments
                .get(name.id.as_str())
                .cloned()
                .unwrap_or_else(|| vec![("<dynamic>".into(), Certainty::Dynamic)]),
            _ => vec![("<dynamic>".into(), Certainty::Dynamic)],
        }
    }

    fn key_value_fields(expression: &ast::Expr) -> Vec<(String, Certainty)> {
        match expression {
            ast::Expr::Constant(value) => match &value.value {
                ast::Constant::Str(value) => key_value_field(value)
                    .map(|field| vec![(field, Certainty::Static)])
                    .unwrap_or_default(),
                _ => Vec::new(),
            },
            ast::Expr::JoinedStr(joined) => match joined.values.first() {
                None => Vec::new(),
                Some(ast::Expr::Constant(value)) => match &value.value {
                    ast::Constant::Str(value) => key_value_field(value)
                        .map(|field| vec![(field, Certainty::Static)])
                        .unwrap_or_default(),
                    _ => vec![("<dynamic>".into(), Certainty::Dynamic)],
                },
                Some(_) => vec![("<dynamic>".into(), Certainty::Dynamic)],
            },
            _ => Vec::new(),
        }
    }

    fn record_key_value_literals(&mut self, expression: &ast::Expr) {
        match expression {
            ast::Expr::Constant(_) | ast::Expr::JoinedStr(_) => {
                let line = expression_line(self.source, expression);
                for (field, certainty) in Self::key_value_fields(expression) {
                    self.record("key_value_literal", field, line, certainty);
                }
            }
            ast::Expr::List(value) => {
                for element in &value.elts {
                    self.record_key_value_literals(element);
                }
            }
            ast::Expr::Tuple(value) => {
                for element in &value.elts {
                    self.record_key_value_literals(element);
                }
            }
            ast::Expr::Set(value) => {
                for element in &value.elts {
                    self.record_key_value_literals(element);
                }
            }
            _ => {}
        }
    }

    fn record_json_arg(&mut self, call: &ast::ExprCall, emitter: &str) {
        if let Some(argument) = call.args.first() {
            let line = expression_line(self.source, call);
            for (field, certainty) in self.fields_from_node(argument) {
                self.record(emitter, field, line, certainty);
            }
        }
    }

    fn record_print_call(&mut self, call: &ast::ExprCall) {
        let print_line = expression_line(self.source, call);
        for argument in &call.args {
            if let ast::Expr::Call(inner) = argument {
                if Self::call_name(&inner.func).ends_with("json.dumps") {
                    self.record_json_arg(inner, "json_stdout");
                    continue;
                }
            }
            for (field, certainty) in Self::key_value_fields(argument) {
                self.record("key_value_stdout", field, print_line, certainty);
            }
        }
    }

    fn is_output_line_mutator(expression: &ast::Expr) -> bool {
        let ast::Expr::Attribute(attribute) = expression else {
            return false;
        };
        if attribute.attr.as_str() != "append" && attribute.attr.as_str() != "extend" {
            return false;
        }
        matches!(&*attribute.value, ast::Expr::Name(name) if OUTPUT_LINE_VARIABLES.contains(&name.id.as_str()))
    }

    fn record_structured_helper_args(&mut self, call: &ast::ExprCall, line: usize) {
        for argument in &call.args {
            if matches!(argument, ast::Expr::Dict(_))
                || matches!(argument, ast::Expr::Name(name) if self.dict_assignments.contains_key(name.id.as_str()))
            {
                for (field, certainty) in self.fields_from_node(argument) {
                    self.record("json_log_helper", field, line, certainty);
                }
            }
        }
    }
}

impl Visitor for PythonLogSurfaceVisitor<'_> {
    fn visit_stmt_assign(&mut self, node: ast::StmtAssign) {
        let fields = Self::dict_fields(&node.value);
        if !fields.is_empty() {
            for target in &node.targets {
                if let ast::Expr::Name(name) = target {
                    self.dict_assignments
                        .insert(name.id.to_string(), fields.clone());
                }
            }
        }
        if self.surface == SurfaceKind::Tool
            && node.targets.iter().any(|target| {
                matches!(target, ast::Expr::Name(name) if OUTPUT_LINE_VARIABLES.contains(&name.id.as_str()))
            })
        {
            self.record_key_value_literals(&node.value);
        }
        self.generic_visit_stmt_assign(node);
    }

    fn visit_stmt_ann_assign(&mut self, node: ast::StmtAnnAssign) {
        if let (ast::Expr::Name(name), Some(value)) = (&*node.target, node.value.as_deref()) {
            let fields = Self::dict_fields(value);
            if !fields.is_empty() {
                self.dict_assignments.insert(name.id.to_string(), fields);
            }
            if self.surface == SurfaceKind::Tool
                && OUTPUT_LINE_VARIABLES.contains(&name.id.as_str())
            {
                self.record_key_value_literals(value);
            }
        }
        self.generic_visit_stmt_ann_assign(node);
    }

    fn visit_expr_call(&mut self, node: ast::ExprCall) {
        let call_name = Self::call_name(&node.func);
        let line = expression_line(self.source, &node);
        if call_name == "print" {
            self.record_print_call(&node);
        }
        if call_name.ends_with("json.dump") || call_name.ends_with("json.dumps") {
            self.record_json_arg(&node, "json_object");
        }
        if call_name.contains("log") && call_name != "logging.getLogger" {
            self.record_structured_helper_args(&node, line);
        }
        if self.surface == SurfaceKind::Tool && Self::is_output_line_mutator(&node.func) {
            for argument in &node.args {
                self.record_key_value_literals(argument);
            }
        }
        self.generic_visit_expr_call(node);
    }

    fn visit_stmt_return(&mut self, node: ast::StmtReturn) {
        if self.surface == SurfaceKind::Tool {
            if let Some(value) = node.value.as_deref() {
                self.record_key_value_literals(value);
            }
        }
        self.generic_visit_stmt_return(node);
    }
}

#[derive(Clone, Debug)]
pub struct ShellLogSurfaceScanner {
    relative_path: String,
    surface: SurfaceKind,
}

impl ShellLogSurfaceScanner {
    pub fn new(relative_path: impl Into<String>, surface: SurfaceKind) -> Self {
        Self {
            relative_path: relative_path.into(),
            surface,
        }
    }

    pub fn scan(&self, text: &str) -> Vec<FieldRecord> {
        let mut records = Vec::new();
        let regex = SHELL_ECHO_RE.get_or_init(|| {
            Regex::new(r"^\s*(?:echo|printf)\s+(?:--\s+)?(?P<value>.+)$")
                .expect("shell output regex is valid")
        });
        for (index, line) in python_split_lines(text).into_iter().enumerate() {
            let Some(captures) = regex.captures(line) else {
                continue;
            };
            let value = first_shell_value(captures.name("value").map_or("", |m| m.as_str()));
            if let Some((field, certainty)) = shell_key(&value) {
                records.push(FieldRecord {
                    path: self.relative_path.clone(),
                    surface: self.surface,
                    emitter: "shell_key_value_stdout".into(),
                    field,
                    line: index as i64 + 1,
                    certainty,
                });
            }
        }
        records
    }
}

#[derive(Clone, Debug)]
pub struct RustLogSurfaceScanner {
    relative_path: String,
    surface: SurfaceKind,
}

impl RustLogSurfaceScanner {
    pub fn new(relative_path: impl Into<String>, surface: SurfaceKind) -> Self {
        Self {
            relative_path: relative_path.into(),
            surface,
        }
    }

    pub fn scan(&self, text: &str) -> Vec<FieldRecord> {
        let mut records = Vec::new();
        let regex = RUST_PRINT_RE.get_or_init(|| {
            Regex::new(r#"^\s*(?:e?println)\s*!\s*\(\s*"(?P<value>[^"]*)"#)
                .expect("Rust output regex is valid")
        });
        for (index, line) in python_split_lines(text).into_iter().enumerate() {
            let Some(captures) = regex.captures(line) else {
                continue;
            };
            let value = captures.name("value").map_or("", |m| m.as_str());
            if let Some(field) = key_value_field(value) {
                records.push(FieldRecord {
                    path: self.relative_path.clone(),
                    surface: self.surface,
                    emitter: "rust_key_value_stdout".into(),
                    field,
                    line: index as i64 + 1,
                    certainty: Certainty::Static,
                });
            }
        }
        records
    }
}

fn key_value_field(value: &str) -> Option<String> {
    let regex = KEY_VALUE_RE.get_or_init(|| {
        Regex::new(r"^([A-Za-z][A-Za-z0-9_.-]*)=").expect("key-value regex is valid")
    });
    regex
        .captures(value)
        .and_then(|captures| captures.get(1))
        .map(|capture| capture.as_str().to_owned())
}

fn shell_key(value: &str) -> Option<(String, Certainty)> {
    if value.starts_with('$') || value.starts_with("${") {
        return Some(("<dynamic>".into(), Certainty::Dynamic));
    }
    key_value_field(value).map(|field| (field, Certainty::Static))
}

fn first_shell_value(value: &str) -> String {
    let stripped = value.trim();
    let quote = stripped
        .chars()
        .next()
        .filter(|quote| matches!(quote, '\'' | '"'));
    if let Some(quote) = quote {
        if let Some(end) = stripped[quote.len_utf8()..].find(quote) {
            return stripped[quote.len_utf8()..quote.len_utf8() + end].to_owned();
        }
    }
    stripped
        .split_whitespace()
        .next()
        .unwrap_or_default()
        .to_owned()
}

fn python_split_lines(text: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut characters = text.char_indices().peekable();
    while let Some((offset, character)) = characters.next() {
        if !matches!(
            character,
            '\n' | '\r'
                | '\u{000b}'
                | '\u{000c}'
                | '\u{001c}'
                | '\u{001d}'
                | '\u{001e}'
                | '\u{0085}'
                | '\u{2028}'
                | '\u{2029}'
        ) {
            continue;
        }
        lines.push(&text[start..offset]);
        let mut next = offset + character.len_utf8();
        if character == '\r' && characters.peek().is_some_and(|(_, next)| *next == '\n') {
            if let Some((next_offset, next_character)) = characters.next() {
                next = next_offset + next_character.len_utf8();
            }
        }
        start = next;
    }
    if start < text.len() {
        lines.push(&text[start..]);
    }
    lines
}

fn expression_line(source: &str, expression: &impl Ranged) -> usize {
    line_at_offset(source, expression.start().to_usize())
}

fn scan_python_file(relative_path: &str, surface: SurfaceKind, source: &str) -> Vec<FieldRecord> {
    let suite = match ast::Suite::parse(source, relative_path) {
        Ok(suite) => suite,
        Err(parse_error) => {
            return vec![FieldRecord {
                path: relative_path.to_owned(),
                surface,
                emitter: "python_syntax_error".into(),
                field: "<syntax-error>".into(),
                line: line_at_offset(source, parse_error.offset.to_usize()) as i64,
                certainty: Certainty::Dynamic,
            }];
        }
    };
    let mut visitor = PythonLogSurfaceVisitor::new(relative_path, source, surface);
    for statement in suite {
        visitor.visit_stmt(statement);
    }
    visitor.records
}

fn scan_markdown_key_values(
    relative_path: &str,
    surface: SurfaceKind,
    text: &str,
) -> Vec<FieldRecord> {
    let mut records = Vec::new();
    let mut in_fence = false;
    for (index, raw_line) in python_split_lines(text).into_iter().enumerate() {
        if raw_line.starts_with("```") {
            in_fence = !in_fence;
            continue;
        }
        if !in_fence {
            continue;
        }
        if let Some(field) = key_value_field(raw_line.trim()) {
            records.push(FieldRecord {
                path: relative_path.to_owned(),
                surface,
                emitter: "markdown_key_value_example".into(),
                field,
                line: index as i64 + 1,
                certainty: Certainty::Static,
            });
        }
    }
    records
}

fn scan_one_file(
    path: &Path,
    relative_path: &str,
    surface: SurfaceKind,
) -> Result<Vec<FieldRecord>, String> {
    let bytes = fs::read(path)
        .map_err(|error| format!("failed to read source {}: {error}", path.display()))?;
    let text = normalize_python_newlines(&String::from_utf8_lossy(&bytes));
    match path.extension().and_then(|extension| extension.to_str()) {
        Some("py") => Ok(scan_python_file(relative_path, surface, &text)),
        Some("sh" | "bash") => Ok(ShellLogSurfaceScanner::new(relative_path, surface).scan(&text)),
        Some("rs") => Ok(RustLogSurfaceScanner::new(relative_path, surface).scan(&text)),
        _ if path
            .file_name()
            .and_then(OsStr::to_str)
            .is_some_and(|name| name == "SKILL.md")
            || path
                .extension()
                .and_then(OsStr::to_str)
                .is_some_and(|extension| extension == "md") =>
        {
            Ok(scan_markdown_key_values(relative_path, surface, &text))
        }
        _ => Ok(Vec::new()),
    }
}

/// Build the same stable inventory payload as the existing public tool.
pub fn build_inventory(root: &Path, raw_paths: &[String]) -> Result<Inventory, String> {
    let root = resolve_non_strict(root);
    let candidates = if raw_paths.is_empty() {
        tracked_surface_files(&root)
    } else {
        selected_files(&root, raw_paths)
    };
    let mut files = BTreeSet::new();
    for candidate in candidates {
        let metadata = match fs::symlink_metadata(&candidate) {
            Ok(metadata) => metadata,
            Err(_) => continue,
        };
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            continue;
        }
        let Ok(relative) = candidate.strip_prefix(&root) else {
            continue;
        };
        if should_skip(relative) || surface_kind(relative).is_none() {
            continue;
        }
        files.insert(candidate);
    }

    let mut scanned_files = Vec::with_capacity(files.len());
    let mut records = Vec::new();
    for path in files {
        let relative = path
            .strip_prefix(&root)
            .map_err(|_| "selected surface path escaped inventory root".to_owned())?;
        let relative_path = path_posix(relative);
        let Some(surface) = surface_kind(Path::new(&relative_path)) else {
            continue;
        };
        scanned_files.push(relative_path.clone());
        records.extend(scan_one_file(&path, &relative_path, surface)?);
    }
    scanned_files.sort();
    records.sort();
    Ok(Inventory {
        schema_version: 1,
        scanned_files,
        records,
    })
}

fn selected_files(root: &Path, raw_paths: &[String]) -> Vec<PathBuf> {
    let mut files = Vec::new();
    for raw_path in raw_paths {
        let candidate = resolve_non_strict(&root.join(raw_path));
        if candidate.is_file() {
            files.push(candidate);
        } else if candidate.is_dir() {
            walk_files(root, &candidate, &mut files);
        }
    }
    files
}

fn tracked_surface_files(root: &Path) -> Vec<PathBuf> {
    let tracked = git_tracked_files(root);
    if tracked.is_empty() {
        return filesystem_surface_files(root);
    }
    tracked
        .into_iter()
        .filter_map(|relative| {
            let path = root.join(relative);
            surface_kind(path.strip_prefix(root).ok()?).map(|_| path)
        })
        .collect()
}

fn git_tracked_files(root: &Path) -> Vec<PathBuf> {
    let output = match Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["ls-files", "--cached", "--others", "--exclude-standard"])
        .output()
    {
        Ok(output) if output.status.success() => output,
        _ => return Vec::new(),
    };
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter(|line| !line.is_empty())
        .map(|line| root.join(line))
        .collect()
}

fn filesystem_surface_files(root: &Path) -> Vec<PathBuf> {
    let mut files = Vec::new();
    for relative_root in [".codex", "agents", ".github", "tools"] {
        let directory = root.join(relative_root);
        if directory.is_dir() {
            walk_files(root, &directory, &mut files);
        }
    }
    files
        .into_iter()
        .filter(|path| {
            path.strip_prefix(root).ok().is_some_and(|relative| {
                !should_skip(relative) && fs_glob_matches_any(&path_posix(relative))
            })
        })
        .collect()
}

fn walk_files(root: &Path, directory: &Path, files: &mut Vec<PathBuf>) {
    if !directory.starts_with(root) {
        return;
    }
    let Ok(entries) = fs::read_dir(directory) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let Ok(relative) = path.strip_prefix(root) else {
            continue;
        };
        if should_skip(relative) {
            continue;
        }
        let Ok(metadata) = fs::symlink_metadata(&path) else {
            continue;
        };
        if metadata.file_type().is_dir() {
            walk_files(root, &path, files);
        } else if metadata.is_file() || metadata.file_type().is_symlink() {
            files.push(path);
        }
    }
}

fn path_posix(path: &Path) -> String {
    path.components()
        .map(|component| component.as_os_str().to_string_lossy().into_owned())
        .collect::<Vec<_>>()
        .join("/")
}

fn surface_kind(relative: &Path) -> Option<SurfaceKind> {
    let path = path_posix(relative);
    if matches_any(&path, HOOK_PATTERNS) {
        Some(SurfaceKind::Hook)
    } else if matches_any(&path, SKILL_PATTERNS) {
        Some(SurfaceKind::Skill)
    } else if matches_any(&path, TOOL_PATTERNS) || matches_any(&path, RUST_TOOL_PATTERNS) {
        Some(SurfaceKind::Tool)
    } else {
        None
    }
}

fn should_skip(relative: &Path) -> bool {
    relative.components().any(|component| {
        EXCLUDED_PARTS
            .iter()
            .any(|excluded| component.as_os_str() == OsStr::new(excluded))
    })
}

fn matches_any(path: &str, patterns: &[&str]) -> bool {
    patterns.iter().any(|pattern| fnmatch_case(path, pattern))
}

fn fnmatch_case(path: &str, pattern: &str) -> bool {
    let path = path.chars().collect::<Vec<_>>();
    let pattern = pattern.chars().collect::<Vec<_>>();
    let (mut path_index, mut pattern_index) = (0, 0);
    let (mut star_index, mut star_path_index) = (None, 0);
    while path_index < path.len() {
        if pattern_index < pattern.len()
            && (pattern[pattern_index] == '?' || pattern[pattern_index] == path[path_index])
        {
            pattern_index += 1;
            path_index += 1;
        } else if pattern_index < pattern.len() && pattern[pattern_index] == '*' {
            star_index = Some(pattern_index);
            pattern_index += 1;
            star_path_index = path_index;
        } else if let Some(star) = star_index {
            star_path_index += 1;
            path_index = star_path_index;
            pattern_index = star + 1;
        } else {
            return false;
        }
    }
    pattern[pattern_index..]
        .iter()
        .all(|character| *character == '*')
}

fn fs_glob_matches_any(path: &str) -> bool {
    HOOK_PATTERNS
        .iter()
        .chain(SKILL_PATTERNS)
        .chain(TOOL_PATTERNS)
        .chain(RUST_TOOL_PATTERNS)
        .any(|pattern| fs_glob_match(path, pattern))
}

fn fs_glob_match(path: &str, pattern: &str) -> bool {
    let mut regex = String::from("^");
    let mut characters = pattern.chars().peekable();
    while let Some(character) = characters.next() {
        match character {
            '*' if characters.peek() == Some(&'*') => {
                characters.next();
                if characters.peek() == Some(&'/') {
                    characters.next();
                    regex.push_str("(?:.*/)?");
                } else {
                    regex.push_str(".*");
                }
            }
            '*' => regex.push_str("[^/]*"),
            '?' => regex.push_str("[^/]"),
            other => regex.push_str(&regex::escape(&other.to_string())),
        }
    }
    regex.push('$');
    Regex::new(&regex).is_ok_and(|matcher| matcher.is_match(path))
}

/// Compare inventory records by the stable identity that deliberately omits line.
pub fn diff_inventory(current: &Inventory, baseline: &Inventory) -> BaselineDiff {
    let current_records = records_by_identity(&current.records);
    let baseline_records = records_by_identity(&baseline.records);
    let current_keys = current_records.keys().cloned().collect::<BTreeSet<_>>();
    let baseline_keys = baseline_records.keys().cloned().collect::<BTreeSet<_>>();
    let mut added = current_keys
        .difference(&baseline_keys)
        .filter_map(|key| current_records.get(key).cloned())
        .collect::<Vec<_>>();
    let mut removed = baseline_keys
        .difference(&current_keys)
        .filter_map(|key| baseline_records.get(key).cloned())
        .collect::<Vec<_>>();
    added.sort();
    removed.sort();
    BaselineDiff { added, removed }
}

fn records_by_identity(records: &[FieldRecord]) -> BTreeMap<FieldIdentity, FieldRecord> {
    let mut sorted = records.to_vec();
    sorted.sort();
    let mut result = BTreeMap::new();
    for record in sorted {
        result.insert(record.identity(), record);
    }
    result
}

fn load_inventory(path: &Path) -> Result<Inventory, String> {
    let raw = fs::read(path).map_err(|error| {
        format!(
            "failed to read inventory baseline {}: {error}",
            path.display()
        )
    })?;
    let payload: Value = serde_json::from_slice(&raw).map_err(|error| {
        format!(
            "failed to parse inventory baseline {}: {error}",
            path.display()
        )
    })?;
    let object = payload
        .as_object()
        .ok_or_else(|| "inventory baseline must be a JSON object".to_owned())?;
    let records = object
        .get("records")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(record_from_payload)
        .collect::<Vec<_>>();
    let mut records = records;
    records.sort();
    let scanned_files = object
        .get("scanned_files")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .map(python_string)
        .collect::<Vec<_>>();
    let schema_version = object
        .get("schema_version")
        .and_then(python_integer)
        .unwrap_or(1);
    let mut scanned_files = scanned_files;
    scanned_files.sort();
    Ok(Inventory {
        schema_version,
        scanned_files,
        records,
    })
}

fn record_from_payload(value: &Value) -> Option<FieldRecord> {
    let object = value.as_object()?;
    let line = object.get("line").and_then(python_integer).unwrap_or(0);
    Some(FieldRecord {
        path: object.get("path").map(python_string).unwrap_or_default(),
        surface: object
            .get("surface")
            .map(parse_surface_kind)
            .unwrap_or(SurfaceKind::Tool),
        emitter: object.get("emitter").map(python_string).unwrap_or_default(),
        field: object.get("field").map(python_string).unwrap_or_default(),
        line,
        certainty: object
            .get("certainty")
            .map(parse_certainty)
            .unwrap_or(Certainty::Dynamic),
    })
}

fn python_integer(value: &Value) -> Option<i64> {
    match value {
        Value::Number(number) if number.is_i64() => number.as_i64(),
        Value::Number(number) if number.is_u64() => {
            number.as_u64().and_then(|n| i64::try_from(n).ok())
        }
        Value::Bool(value) => Some(i64::from(*value)),
        Value::String(value) => value.parse().ok(),
        _ => None,
    }
}

fn python_string(value: &Value) -> String {
    match value {
        Value::Null => "None".into(),
        Value::Bool(value) => (if *value { "True" } else { "False" }).into(),
        Value::String(value) => value.clone(),
        Value::Number(value) => value.to_string(),
        Value::Array(_) | Value::Object(_) => value.to_string(),
    }
}

fn parse_surface_kind(value: &Value) -> SurfaceKind {
    match value.as_str() {
        Some("hook") => SurfaceKind::Hook,
        Some("skill") => SurfaceKind::Skill,
        Some("tool") => SurfaceKind::Tool,
        _ => SurfaceKind::Tool,
    }
}

fn parse_certainty(value: &Value) -> Certainty {
    match value.as_str() {
        Some("static") => Certainty::Static,
        Some("dynamic") => Certainty::Dynamic,
        _ => Certainty::Dynamic,
    }
}

const USAGE: &str = "usage: agent-canon log-surface-inventory [--root ROOT] [--output OUTPUT] [--baseline BASELINE] [--check] [--format {text,json}] [--quiet] [paths ...]";

/// Run the stable on-demand inventory command.
pub fn run(raw_args: &[String]) -> i32 {
    let args = match parse_args(raw_args) {
        Ok(ParseResult::Help) => {
            print_help();
            return 0;
        }
        Ok(ParseResult::Arguments(args)) => args,
        Err(message) => {
            eprintln!("agent-canon log-surface-inventory: {message}");
            eprintln!("{USAGE}");
            return 2;
        }
    };
    let root = resolve_non_strict(&args.root);
    if args.check && args.baseline.is_none() {
        println!("LOG_SURFACE_INVENTORY=fail");
        println!("LOG_SURFACE_INVENTORY_ERROR=explicit_baseline_required");
        return 1;
    }
    let inventory = match build_inventory(&root, &args.paths) {
        Ok(inventory) => inventory,
        Err(message) => {
            println!("LOG_SURFACE_INVENTORY=fail");
            println!("LOG_SURFACE_INVENTORY_ERROR={message}");
            return 1;
        }
    };

    if let Some(output) = args.output.as_ref() {
        let output_path = resolve_non_strict(&root.join(output));
        let mut payload = render_json(&inventory.json_value()).into_bytes();
        payload.push(b'\n');
        if let Err(reject) = write_parent_output(&output_path, &payload) {
            println!("LOG_SURFACE_INVENTORY=fail");
            println!("LOG_SURFACE_INVENTORY_ERROR={}", reject.as_str());
            return 1;
        }
        if !args.quiet {
            println!("LOG_SURFACE_INVENTORY_OUTPUT={}", output.display());
        }
    }

    if args.check {
        let baseline = resolve_baseline_path(&root, args.baseline.as_deref().unwrap());
        if !baseline.is_file() {
            println!("LOG_SURFACE_INVENTORY=fail");
            println!("LOG_SURFACE_BASELINE_MISSING={}", baseline.display());
            return 1;
        }
        let baseline_inventory = match load_inventory(&baseline) {
            Ok(inventory) => inventory,
            Err(message) => {
                println!("LOG_SURFACE_INVENTORY=fail");
                println!("LOG_SURFACE_INVENTORY_ERROR={message}");
                return 1;
            }
        };
        let difference = diff_inventory(&inventory, &baseline_inventory);
        if difference.has_drift() {
            println!("{}", render_check_failure(&difference, &baseline));
            return 1;
        }
        if !args.quiet {
            println!("LOG_SURFACE_INVENTORY=pass");
        }
        return 0;
    }

    match args.format {
        OutputFormat::Json => println!("{}", render_json(&inventory.json_value())),
        OutputFormat::Text if !args.quiet => println!("{}", render_text(&inventory)),
        OutputFormat::Text => {}
    }
    0
}

fn print_help() {
    println!("{USAGE}");
    println!(
        "\nStatically inventory machine-readable field names emitted by AgentCanon hooks, skills, and tools."
    );
}

fn parse_args(raw_args: &[String]) -> Result<ParseResult, String> {
    let mut paths = Vec::new();
    let mut root = PathBuf::from(".");
    let mut output = None;
    let mut baseline = None;
    let mut check = false;
    let mut format = OutputFormat::Text;
    let mut quiet = false;
    let mut positional_only = false;
    let mut index = 0;
    while index < raw_args.len() {
        let raw = raw_args[index].as_str();
        if positional_only {
            paths.push(raw.to_owned());
            index += 1;
            continue;
        }
        if raw == "--" {
            positional_only = true;
            index += 1;
            continue;
        }
        let (raw_option, inline_value) = raw
            .split_once('=')
            .map_or((raw, None), |(option, value)| (option, Some(value)));
        if raw_option == "-h" || raw_option == "--help" {
            if inline_value.is_some() {
                return Err(format!("argument {raw_option} does not take a value"));
            }
            return Ok(ParseResult::Help);
        }
        if raw_option.starts_with('-') && raw_option != "-" && looks_like_option(raw_option) {
            let option = resolve_option(raw_option)?;
            match option {
                "--root" | "--output" | "--baseline" | "--format" => {
                    let (value, consumed) = match inline_value {
                        Some(value) => (value, 1),
                        None => (next_option_value(raw_args, index, raw_option)?, 2),
                    };
                    match option {
                        "--root" => root = PathBuf::from(value),
                        "--output" => output = Some(PathBuf::from(value)),
                        "--baseline" => baseline = Some(PathBuf::from(value)),
                        _ => {
                            format = match value {
                                "text" => OutputFormat::Text,
                                "json" => OutputFormat::Json,
                                _ => {
                                    return Err(format!(
                                        "invalid choice: '{value}' (choose from 'text', 'json')"
                                    ));
                                }
                            };
                        }
                    }
                    index += consumed;
                }
                "--check" => {
                    if inline_value.is_some() {
                        return Err("argument --check does not take a value".into());
                    }
                    check = true;
                    index += 1;
                }
                "--quiet" => {
                    if inline_value.is_some() {
                        return Err("argument --quiet does not take a value".into());
                    }
                    quiet = true;
                    index += 1;
                }
                _ => return Err(format!("unrecognized argument: {raw_option}")),
            }
        } else if raw.starts_with('-') && raw != "-" && !is_negative_number(raw) {
            return Err(format!("unrecognized argument: {raw}"));
        } else {
            paths.push(raw.to_owned());
            index += 1;
        }
    }
    Ok(ParseResult::Arguments(Arguments {
        paths,
        root,
        output,
        baseline,
        check,
        format,
        quiet,
    }))
}

fn resolve_option(raw: &str) -> Result<&'static str, String> {
    const OPTIONS: &[&str] = &[
        "--help",
        "--root",
        "--output",
        "--baseline",
        "--check",
        "--format",
        "--quiet",
    ];
    if let Some(option) = OPTIONS.iter().copied().find(|option| *option == raw) {
        return Ok(option);
    }
    let matches = OPTIONS
        .iter()
        .copied()
        .filter(|option| option.starts_with(raw))
        .collect::<Vec<_>>();
    match matches.as_slice() {
        [option] => Ok(option),
        [] => Err(format!("unrecognized argument: {raw}")),
        _ => Err(format!("ambiguous option: {raw}")),
    }
}

fn next_option_value<'a>(
    args: &'a [String],
    index: usize,
    option: &str,
) -> Result<&'a str, String> {
    let value = args
        .get(index + 1)
        .ok_or_else(|| format!("{option} requires a value"))?;
    if looks_like_option(value) {
        return Err(format!("{option} requires a value"));
    }
    Ok(value)
}

fn looks_like_option(value: &str) -> bool {
    value.starts_with('-') && value != "-" && !is_negative_number(value)
}

fn is_negative_number(value: &str) -> bool {
    let Some(value) = value.strip_prefix('-') else {
        return false;
    };
    if !value.is_empty() && value.chars().all(|character| character.is_ascii_digit()) {
        return true;
    }
    let Some((whole, fraction)) = value.split_once('.') else {
        return false;
    };
    (whole.is_empty() || whole.chars().all(|character| character.is_ascii_digit()))
        && !fraction.is_empty()
        && fraction.chars().all(|character| character.is_ascii_digit())
}

fn resolve_non_strict(path: &Path) -> PathBuf {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(path)
    };
    let mut probe = absolute.clone();
    let mut suffix = Vec::new();
    loop {
        if let Ok(mut physical) = fs::canonicalize(&probe) {
            for component in suffix.iter().rev() {
                physical.push(component);
            }
            return physical;
        }
        let Some(name) = probe.file_name() else {
            return absolute;
        };
        suffix.push(name.to_os_string());
        if !probe.pop() {
            return absolute;
        }
    }
}

fn resolve_baseline_path(root: &Path, baseline: &Path) -> PathBuf {
    if baseline.is_absolute() {
        baseline.to_path_buf()
    } else {
        resolve_non_strict(&root.join(baseline))
    }
}

fn render_check_failure(diff: &BaselineDiff, baseline_path: &Path) -> String {
    let mut lines = vec![
        "LOG_SURFACE_INVENTORY=fail".to_owned(),
        format!("LOG_SURFACE_BASELINE={baseline_path}"),
        format!("LOG_SURFACE_ADDED={}", diff.added.len()),
        format!("LOG_SURFACE_REMOVED={}", diff.removed.len()),
    ];
    lines.extend(
        diff.added
            .iter()
            .take(MAX_DIFF_RECORDS)
            .map(|record| record.machine_line("LOG_SURFACE_FIELD_ADDED")),
    );
    lines.extend(
        diff.removed
            .iter()
            .take(MAX_DIFF_RECORDS)
            .map(|record| record.machine_line("LOG_SURFACE_FIELD_REMOVED")),
    );
    lines.join("\n")
}

fn render_text(inventory: &Inventory) -> String {
    let dynamic_count = inventory
        .records
        .iter()
        .filter(|record| record.certainty == Certainty::Dynamic)
        .count();
    let mut lines = vec![
        "LOG_SURFACE_INVENTORY=pass".to_owned(),
        format!("LOG_SURFACE_FILES={}", inventory.scanned_files.len()),
        format!("LOG_SURFACE_FIELDS={}", inventory.records.len()),
        format!("LOG_SURFACE_DYNAMIC_FIELDS={dynamic_count}"),
    ];
    lines.extend(
        inventory
            .records
            .iter()
            .map(|record| record.machine_line("LOG_SURFACE_FIELD")),
    );
    lines.join("\n")
}

fn render_json(value: &Value) -> String {
    let mut output = String::new();
    write_pretty_json(value, 0, &mut output);
    output
}

fn write_pretty_json(value: &Value, indent: usize, output: &mut String) {
    match value {
        Value::Null => output.push_str("null"),
        Value::Bool(value) => output.push_str(if *value { "true" } else { "false" }),
        Value::Number(value) => output.push_str(&value.to_string()),
        Value::String(value) => write_ascii_json_string(value, output),
        Value::Array(values) if values.is_empty() => output.push_str("[]"),
        Value::Array(values) => {
            output.push_str("[\n");
            for (index, value) in values.iter().enumerate() {
                write_indent(output, indent + 2);
                write_pretty_json(value, indent + 2, output);
                if index + 1 != values.len() {
                    output.push(',');
                }
                output.push('\n');
            }
            write_indent(output, indent);
            output.push(']');
        }
        Value::Object(values) if values.is_empty() => output.push_str("{}"),
        Value::Object(values) => {
            let mut keys = values.keys().collect::<Vec<_>>();
            keys.sort_unstable();
            output.push_str("{\n");
            for (index, key) in keys.iter().enumerate() {
                let key = key.as_str();
                write_indent(output, indent + 2);
                write_ascii_json_string(key, output);
                output.push_str(": ");
                write_pretty_json(&values[key], indent + 2, output);
                if index + 1 != keys.len() {
                    output.push(',');
                }
                output.push('\n');
            }
            write_indent(output, indent);
            output.push('}');
        }
    }
}

fn write_indent(output: &mut String, indent: usize) {
    output.extend(std::iter::repeat(' ').take(indent));
}

fn write_ascii_json_string(value: &str, output: &mut String) {
    output.push('"');
    for character in value.chars() {
        match character {
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            '\u{0008}' => output.push_str("\\b"),
            '\u{000c}' => output.push_str("\\f"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            character if character <= '\u{001f}' => write_unicode_escape(character as u32, output),
            character if !character.is_ascii() => {
                let codepoint = character as u32;
                if codepoint <= 0xffff {
                    write_unicode_escape(codepoint, output);
                } else {
                    let adjusted = codepoint - 0x1_0000;
                    write_unicode_escape(0xd800 + (adjusted >> 10), output);
                    write_unicode_escape(0xdc00 + (adjusted & 0x3ff), output);
                }
            }
            character => output.push(character),
        }
    }
    output.push('"');
}

fn write_unicode_escape(codepoint: u32, output: &mut String) {
    use std::fmt::Write as _;
    let _ = write!(output, "\\u{codepoint:04x}");
}

fn write_parent_output(path: &Path, bytes: &[u8]) -> Result<(), ParentRootReject> {
    let purpose = NonEmptyTrimmedString::new(PURPOSE).map_err(|error| error.reject)?;
    let attested = ParentRootAttestor::new()
        .attest_parent_from_process_environment(
            purpose.clone(),
            Nonce128::generate().map_err(|error| error.reject)?,
        )
        .map_err(|error| error.reject)?;
    attested
        .write_parent_owned_file(path, bytes, purpose)
        .map_err(|error| error.reject)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static NEXT_ROOT: AtomicUsize = AtomicUsize::new(0);

    struct TempRoot(PathBuf);

    impl TempRoot {
        fn new() -> Self {
            let id = NEXT_ROOT.fetch_add(1, Ordering::Relaxed);
            let path = env::temp_dir().join(format!(
                "agent-canon-log-surface-native-{}-{id}",
                std::process::id()
            ));
            fs::create_dir_all(&path).expect("create temporary source root");
            Self(resolve_non_strict(&path))
        }

        fn write(&self, relative: &str, contents: &str) {
            let path = self.0.join(relative);
            fs::create_dir_all(path.parent().expect("fixture file parent"))
                .expect("create fixture file parent");
            fs::write(path, contents).expect("write fixture source");
        }
    }

    impl Drop for TempRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn core_inventory_extracts_python_shell_rust_and_markdown_fields() {
        let root = TempRoot::new();
        root.write(
            ".codex/hooks/sample.py",
            "import json\nentry = {'status': 'pass', 'hook_run_id': 'h'}\nprint('SAMPLE_STATUS=pass')\nprint(json.dumps(entry))\n",
        );
        root.write(
            "tools/sample.py",
            "lines = [f'LIST_STATUS={1}']\nlines.append('APPEND_STATUS=1')\ndef render():\n    return f'RETURN_STATUS={1}'\nprint('\\n'.join(lines))\nprint(render())\n",
        );
        root.write("tools/sample.sh", "echo TOOL_STATUS=pass\n");
        root.write(
            ".github/scripts/sample.sh",
            "echo GITHUB_SCRIPT_STATUS=pass\n",
        );
        root.write(
            "tools/runtime/dispatch/agent-canon/src/sample.rs",
            "fn main() {\n    println!(\"RUST_TOOL_STATUS=pass\");\n}\n",
        );
        root.write(
            "agents/skills/sample.md",
            "```text\nSKILL_RESULT=pass\n```\n",
        );

        let inventory = build_inventory(
            &root.0,
            &[
                ".codex".into(),
                "tools".into(),
                ".github".into(),
                "tools/runtime/dispatch".into(),
                "agents".into(),
            ],
        )
        .expect("build source inventory through the reusable native API");
        let fields = inventory
            .records
            .iter()
            .map(|record| record.field.as_str())
            .collect::<BTreeSet<_>>();
        for expected in [
            "SAMPLE_STATUS",
            "LIST_STATUS",
            "APPEND_STATUS",
            "RETURN_STATUS",
            "status",
            "hook_run_id",
            "TOOL_STATUS",
            "GITHUB_SCRIPT_STATUS",
            "RUST_TOOL_STATUS",
            "SKILL_RESULT",
        ] {
            assert!(
                fields.contains(expected),
                "missing emitted field {expected}"
            );
        }
        assert_eq!(inventory.schema_version, 1);
        assert!(inventory
            .scanned_files
            .windows(2)
            .all(|pair| pair[0] <= pair[1]));
        assert!(inventory.records.windows(2).all(|pair| pair[0] <= pair[1]));
    }

    #[test]
    fn baseline_identity_ignores_line_only_movement() {
        let record = FieldRecord {
            path: "tools/sample.py".into(),
            surface: SurfaceKind::Tool,
            emitter: "key_value_stdout".into(),
            field: "SAMPLE_STATUS".into(),
            line: 2,
            certainty: Certainty::Static,
        };
        let mut moved = record.clone();
        moved.line = 20;
        let current = Inventory {
            schema_version: 1,
            scanned_files: vec![record.path.clone()],
            records: vec![moved],
        };
        let baseline = Inventory {
            schema_version: 1,
            scanned_files: vec![record.path.clone()],
            records: vec![record],
        };
        let difference = diff_inventory(&current, &baseline);
        assert!(!difference.has_drift());
        assert!(difference.added.is_empty());
        assert!(difference.removed.is_empty());
    }
}
