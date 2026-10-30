// @dependency-start
// contract implementation
// responsibility Checks SOLID-sensitive Python changes have path-covered OOP readability evidence.
// upstream design ../../../../../documents/conventions/coding-conventions-python.md SOLID evidence route policy
// upstream implementation python_ast.rs shares Python AST source and span helpers
// downstream test ../../../../../tests/agent_tools/test_check_solid_evidence.py preserves checker behavior
// @dependency-end

use crate::python_ast::{ast_dump_expr, line_at_offset, node_line, normalize_python_newlines};
use regex::Regex;
use rustpython_ast::{Expr, Ranged};
use rustpython_parser::{ast, Parse};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::Command;
use std::sync::LazyLock;

pub const SELECTOR: &str = "check-solid-evidence";

const DEFAULT_EXCLUDES: &[&str] = &[
    ".git",
    ".ruff_cache",
    "__pycache__",
    "build",
    "reports",
    "vendor",
];
const REQUIRED_JSON_SUMMARY_KEYS: &[&str] = &[
    "dimension_counts",
    "findings",
    "kind_counts",
    "scanned_paths",
    "solid_counts",
    "status",
];
const MARKDOWN_REQUIRED_MARKERS: &[&str] = &[
    "## SOLID Principle Signals",
    "## Dimensions",
    "## Finding Kinds",
];
const USAGE: &str = "usage: agent-canon check-solid-evidence [-h] [paths ...] [--root ROOT] [--changed] [--base-ref BASE_REF] [--evidence EVIDENCE] [--exclude EXCLUDE] [--verbose] [--format {text,json}]";
static DIFF_HUNK: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
        .expect("static unified diff hunk expression is valid")
});
static MARKDOWN_SCANNED_PATHS: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?m)^- scanned_paths: `([^`]*)`$")
        .expect("static Markdown scanned_paths expression is valid")
});

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
struct SensitiveChange {
    path: String,
    line: usize,
    kind: String,
    symbol: String,
}

impl SensitiveChange {
    fn render(&self) -> String {
        format!("{}:{}:{}:{}", self.path, self.line, self.kind, self.symbol)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct LineSelection {
    full_file: bool,
    lines: BTreeSet<usize>,
}

impl LineSelection {
    fn full_file() -> Self {
        Self {
            full_file: true,
            lines: BTreeSet::new(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct Finding {
    path: String,
    detail: String,
}

impl Finding {
    fn render(&self) -> String {
        format!("SOLID_EVIDENCE_FINDING={}:{}", self.path, self.detail)
    }
}

#[derive(Debug)]
struct Args {
    paths: Vec<String>,
    root: PathBuf,
    changed: bool,
    base_ref: String,
    evidence: Vec<String>,
    excludes: Vec<String>,
    verbose: bool,
    format: OutputFormat,
}

#[derive(Debug, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

enum ParseResult {
    Help,
    Args(Args),
}

pub fn run(argv: &[String]) -> i32 {
    let args = match parse_args(argv) {
        Ok(ParseResult::Help) => {
            println!("{USAGE}\n\nCheck that SOLID-sensitive Python paths are covered by an OOP readability report.");
            return 0;
        }
        Ok(ParseResult::Args(args)) => args,
        Err(message) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon {SELECTOR}: error: {message}");
            return 2;
        }
    };
    let root = resolve_non_strict(&args.root);
    let path_lines = match selected_python_paths(
        &root,
        &args.paths,
        args.changed,
        &args.base_ref,
        &args.excludes,
    ) {
        Ok(paths) => paths,
        Err(message) => {
            eprintln!("agent-canon {SELECTOR}: {message}");
            return 1;
        }
    };
    let sensitive_changes = match collect_sensitive_changes(&root, &path_lines) {
        Ok(changes) => changes,
        Err(message) => {
            eprintln!("agent-canon {SELECTOR}: {message}");
            return 1;
        }
    };
    let (findings, covered_paths) = check_evidence(&root, &sensitive_changes, &args.evidence);
    let output = match args.format {
        OutputFormat::Json => json_output(&sensitive_changes, &findings, &covered_paths),
        OutputFormat::Text => {
            text_output(&sensitive_changes, &findings, &covered_paths, args.verbose)
        }
    };
    println!("{output}");
    if findings.is_empty() {
        0
    } else {
        1
    }
}

fn parse_args(argv: &[String]) -> Result<ParseResult, String> {
    let mut args = Args {
        paths: Vec::new(),
        root: PathBuf::from("."),
        changed: false,
        base_ref: String::from("HEAD"),
        evidence: Vec::new(),
        excludes: DEFAULT_EXCLUDES
            .iter()
            .map(|value| (*value).to_owned())
            .collect(),
        verbose: false,
        format: OutputFormat::Text,
    };
    let mut options = true;
    let mut index = 0;
    while index < argv.len() {
        let token = &argv[index];
        if options && token == "--" {
            options = false;
            index += 1;
            continue;
        }
        if options && matches!(token.as_str(), "-h" | "--help") {
            return Ok(ParseResult::Help);
        }
        if options {
            if let Some((option, inline)) = parse_option(token) {
                match option {
                    "--changed" => {
                        if inline.is_some() {
                            return Err(format!(
                                "argument --changed: ignored explicit argument '{}'",
                                inline.unwrap()
                            ));
                        }
                        args.changed = true;
                    }
                    "--verbose" => {
                        if inline.is_some() {
                            return Err(format!(
                                "argument --verbose: ignored explicit argument '{}'",
                                inline.unwrap()
                            ));
                        }
                        args.verbose = true;
                    }
                    "--root" | "--base-ref" | "--evidence" | "--exclude" | "--format" => {
                        let value = match inline {
                            Some(value) => value.to_owned(),
                            None => {
                                index += 1;
                                let Some(value) = argv.get(index) else {
                                    return Err(format!(
                                        "argument {option}: expected one argument"
                                    ));
                                };
                                if starts_option(value) {
                                    return Err(format!(
                                        "argument {option}: expected one argument"
                                    ));
                                }
                                value.clone()
                            }
                        };
                        match option {
                            "--root" => args.root = PathBuf::from(value),
                            "--base-ref" => args.base_ref = value,
                            "--evidence" => args.evidence.push(value),
                            "--exclude" => args.excludes.push(value),
                            "--format" => {
                                args.format = match value.as_str() {
                                    "text" => OutputFormat::Text,
                                    "json" => OutputFormat::Json,
                                    _ => {
                                        return Err(format!(
                                            "argument --format: invalid choice: '{value}' (choose from 'text', 'json')"
                                        ));
                                    }
                                }
                            }
                            _ => unreachable!("matched value-taking option"),
                        }
                    }
                    _ => unreachable!("option parser only returns known options"),
                }
            } else if starts_option(token) {
                return Err(format!("unrecognized arguments: {token}"));
            } else {
                args.paths.push(token.clone());
            }
        } else {
            args.paths.push(token.clone());
        }
        index += 1;
    }
    Ok(ParseResult::Args(args))
}

fn parse_option(token: &str) -> Option<(&'static str, Option<&str>)> {
    const OPTIONS: &[&str] = &[
        "--root",
        "--changed",
        "--base-ref",
        "--evidence",
        "--exclude",
        "--verbose",
        "--format",
    ];
    let (name, value) = token
        .split_once('=')
        .map_or((token, None), |(name, value)| (name, Some(value)));
    let mut matches = OPTIONS.iter().filter(|option| option.starts_with(name));
    let first = matches.next().copied()?;
    if matches.next().is_some() {
        return None;
    }
    Some((first, value))
}

fn starts_option(value: &str) -> bool {
    value.starts_with('-') && value != "-" && !negative_number(value)
}

fn negative_number(value: &str) -> bool {
    let digits = value.strip_prefix('-').unwrap_or_default();
    !digits.is_empty()
        && digits
            .chars()
            .all(|character| character.is_ascii_digit() || character == '.')
        && digits.chars().any(|character| character.is_ascii_digit())
}

fn git_lines(root: &Path, args: &[String]) -> Vec<String> {
    let output = match Command::new("git").arg("-C").arg(root).args(args).output() {
        Ok(output) if output.status.success() => output,
        _ => return Vec::new(),
    };
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter(|line| !line.is_empty())
        .map(str::to_owned)
        .collect()
}

fn git_changed_paths(root: &Path, base_ref: &str) -> BTreeSet<String> {
    let mut paths = BTreeSet::new();
    paths.extend(git_lines(
        root,
        &[
            "diff".into(),
            "--name-only".into(),
            "--diff-filter=ACMRT".into(),
            base_ref.to_owned(),
            "--".into(),
        ],
    ));
    paths.extend(git_lines(
        root,
        &[
            "ls-files".into(),
            "--others".into(),
            "--exclude-standard".into(),
        ],
    ));
    paths
}

fn git_diff_text(root: &Path, base_ref: &str, relative_path: &str) -> String {
    let args = [
        "diff".to_owned(),
        "--unified=0".to_owned(),
        base_ref.to_owned(),
        "--".to_owned(),
        relative_path.to_owned(),
    ];
    let output = match Command::new("git").arg("-C").arg(root).args(args).output() {
        Ok(output) if output.status.success() => output,
        _ => return String::new(),
    };
    let text = String::from_utf8_lossy(&output.stdout).into_owned();
    if text.trim().is_empty() {
        String::new()
    } else {
        text
    }
}

fn line_selection_from_diff(diff: &str) -> LineSelection {
    if diff.trim().is_empty() {
        return LineSelection::full_file();
    }
    let mut selected = BTreeSet::new();
    for line in diff.lines() {
        let Some(captures) = DIFF_HUNK.captures(line) else {
            continue;
        };
        let Some(start) = captures
            .get(1)
            .and_then(|value| value.as_str().parse::<usize>().ok())
        else {
            continue;
        };
        let length = captures
            .get(2)
            .and_then(|value| value.as_str().parse::<usize>().ok())
            .unwrap_or(1);
        selected.extend(start..start.saturating_add(length));
    }
    LineSelection {
        full_file: false,
        lines: selected,
    }
}

fn selected_lines_intersect(start: usize, end: usize, selection: &LineSelection) -> bool {
    selection.full_file
        || selection
            .lines
            .iter()
            .any(|line| start <= *line && *line <= end)
}

fn path_is_excluded(relative: &Path, excludes: &[String]) -> bool {
    let parts: BTreeSet<String> = relative
        .components()
        .map(|component| component.as_os_str().to_string_lossy().into_owned())
        .collect();
    let relative_text = posix_path(relative);
    excludes.iter().any(|raw| {
        let pattern = raw.trim().trim_matches('/');
        !pattern.is_empty()
            && (relative_text == pattern
                || relative_text.starts_with(&format!("{pattern}/"))
                || parts.contains(pattern))
    })
}

fn selected_python_paths(
    root: &Path,
    raw_paths: &[String],
    changed: bool,
    base_ref: &str,
    excludes: &[String],
) -> Result<BTreeMap<PathBuf, LineSelection>, String> {
    let from_changed = changed && raw_paths.is_empty();
    let source_paths: Vec<String> = if from_changed {
        git_changed_paths(root, base_ref).into_iter().collect()
    } else {
        raw_paths.to_vec()
    };
    let mut path_lines = BTreeMap::new();
    for raw_path in source_paths {
        let unresolved = root.join(&raw_path);
        let candidate = match fs::canonicalize(&unresolved) {
            Ok(path) => path,
            Err(error)
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::NotFound | std::io::ErrorKind::NotADirectory
                ) =>
            {
                continue;
            }
            Err(error) => return Err(format!("resolve {}: {error}", unresolved.display())),
        };
        let mut files = Vec::new();
        if candidate.is_file() {
            files.push(candidate);
        } else if candidate.is_dir() {
            collect_python_files(&candidate, &mut files);
            files.sort();
        }
        for path in files {
            if !has_python_suffix(&path) {
                continue;
            }
            let Ok(relative) = path.strip_prefix(root) else {
                continue;
            };
            if path_is_excluded(relative, excludes) {
                continue;
            }
            let relative_text = posix_path(relative);
            let selection = if from_changed {
                line_selection_from_diff(&git_diff_text(root, base_ref, &relative_text))
            } else {
                LineSelection::full_file()
            };
            path_lines.insert(path, selection);
        }
    }
    Ok(path_lines)
}

fn collect_python_files(directory: &Path, files: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(directory) else {
        return;
    };
    let mut paths: Vec<PathBuf> = entries
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .collect();
    paths.sort();
    for path in paths {
        if has_python_suffix(&path) {
            files.push(path.clone());
        }
        if fs::symlink_metadata(&path).is_ok_and(|metadata| metadata.file_type().is_dir()) {
            collect_python_files(&path, files);
        }
    }
}

fn has_python_suffix(path: &Path) -> bool {
    path.extension().is_some_and(|extension| extension == "py")
}

fn posix_path(path: &Path) -> String {
    let text = path.to_string_lossy();
    #[cfg(windows)]
    {
        text.replace('\\', "/")
    }
    #[cfg(not(windows))]
    {
        text.into_owned()
    }
}

fn normalize_path(path: PathBuf) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                if !normalized.pop() && !normalized.has_root() {
                    normalized.push("..");
                }
            }
            other => normalized.push(other.as_os_str()),
        }
    }
    normalized
}

fn resolve_non_strict(path: &Path) -> PathBuf {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(path)
    };
    if let Ok(canonical) = fs::canonicalize(&absolute) {
        return canonical;
    }
    let mut cursor = absolute.clone();
    let mut tail = Vec::new();
    while !cursor.exists() {
        let Some(name) = cursor.file_name() else {
            break;
        };
        tail.push(name.to_os_string());
        if !cursor.pop() {
            break;
        }
    }
    let mut resolved = fs::canonicalize(&cursor).unwrap_or(cursor);
    for component in tail.iter().rev() {
        resolved.push(component);
    }
    normalize_path(resolved)
}

fn node_end_line(source: &str, node: &impl Ranged) -> usize {
    line_at_offset(source, node.end().to_usize().saturating_sub(1))
}

fn expression_name(expression: &Expr) -> String {
    match expression {
        Expr::Name(name) => name.id.to_string(),
        Expr::Attribute(attribute) => {
            format!("{}.{}", expression_name(&attribute.value), attribute.attr)
        }
        Expr::Call(call) => expression_name(&call.func),
        other => ast_dump_expr(other)
            .split_once('(')
            .map(|(name, _)| name.to_owned())
            .unwrap_or_else(|| "Expr".to_owned()),
    }
}

fn sensitive_changes_for_file(
    root: &Path,
    path: &Path,
    selection: &LineSelection,
) -> Result<BTreeSet<SensitiveChange>, String> {
    let relative = path
        .strip_prefix(root)
        .map_err(|_| format!("Python path outside root: {}", path.display()))?;
    let relative = posix_path(relative);
    let source = fs::read_to_string(path)
        .map_err(|error| format!("read Python source {}: {error}", path.display()))?;
    let source = normalize_python_newlines(&source);
    let suite = match ast::Suite::parse(&source, &relative) {
        Ok(suite) => suite,
        Err(error) => {
            return Ok(BTreeSet::from([SensitiveChange {
                path: relative,
                line: line_at_offset(&source, error.offset.to_usize()),
                kind: "parse_boundary".to_owned(),
                symbol: "python-syntax".to_owned(),
            }]));
        }
    };
    let mut changes = BTreeSet::new();
    for statement in &suite {
        match statement {
            ast::Stmt::ClassDef(node) => {
                changes.extend(class_sensitive_changes(&relative, &source, node, selection));
            }
            ast::Stmt::FunctionDef(node) => {
                if !node.name.as_str().starts_with('_') {
                    let line = node_line(&source, node);
                    if selected_lines_intersect(line, line, selection) {
                        changes.insert(SensitiveChange {
                            path: relative.clone(),
                            line,
                            kind: "public_api".to_owned(),
                            symbol: node.name.to_string(),
                        });
                    }
                }
            }
            ast::Stmt::AsyncFunctionDef(node) => {
                if !node.name.as_str().starts_with('_') {
                    let line = node_line(&source, node);
                    if selected_lines_intersect(line, line, selection) {
                        changes.insert(SensitiveChange {
                            path: relative.clone(),
                            line,
                            kind: "public_api".to_owned(),
                            symbol: node.name.to_string(),
                        });
                    }
                }
            }
            ast::Stmt::Import(node) => {
                let start = node_line(&source, node);
                let end = node_end_line(&source, node);
                if selected_lines_intersect(start, end, selection) {
                    changes.insert(SensitiveChange {
                        path: relative.clone(),
                        line: start,
                        kind: "dependency_direction".to_owned(),
                        symbol: "import".to_owned(),
                    });
                }
            }
            ast::Stmt::ImportFrom(node) => {
                let start = node_line(&source, node);
                let end = node_end_line(&source, node);
                if selected_lines_intersect(start, end, selection) {
                    changes.insert(SensitiveChange {
                        path: relative.clone(),
                        line: start,
                        kind: "dependency_direction".to_owned(),
                        symbol: "import".to_owned(),
                    });
                }
            }
            _ => {}
        }
    }
    Ok(changes)
}

fn class_sensitive_changes(
    relative: &str,
    source: &str,
    node: &ast::StmtClassDef,
    selection: &LineSelection,
) -> BTreeSet<SensitiveChange> {
    let mut changes = BTreeSet::new();
    let line = node_line(source, node);
    if selected_lines_intersect(line, node_end_line(source, node), selection) {
        changes.insert(SensitiveChange {
            path: relative.to_owned(),
            line,
            kind: "class_boundary".to_owned(),
            symbol: node.name.to_string(),
        });
    }
    if !node.bases.is_empty() && selected_lines_intersect(line, line, selection) {
        changes.insert(SensitiveChange {
            path: relative.to_owned(),
            line,
            kind: "inheritance_boundary".to_owned(),
            symbol: node
                .bases
                .iter()
                .map(expression_name)
                .collect::<Vec<_>>()
                .join(","),
        });
    }
    let decorators: BTreeSet<String> = node.decorator_list.iter().map(expression_name).collect();
    if (decorators.contains("dataclass") || decorators.contains("dataclasses.dataclass"))
        && selected_lines_intersect(line, line, selection)
    {
        changes.insert(SensitiveChange {
            path: relative.to_owned(),
            line,
            kind: "dataclass_boundary".to_owned(),
            symbol: node.name.to_string(),
        });
    }
    if node
        .bases
        .iter()
        .map(expression_name)
        .any(|base| base.ends_with("Protocol"))
    {
        changes.insert(SensitiveChange {
            path: relative.to_owned(),
            line,
            kind: "protocol_boundary".to_owned(),
            symbol: node.name.to_string(),
        });
    }
    changes
}

fn collect_sensitive_changes(
    root: &Path,
    path_lines: &BTreeMap<PathBuf, LineSelection>,
) -> Result<Vec<SensitiveChange>, String> {
    let mut changes = BTreeSet::new();
    for (path, selection) in path_lines {
        changes.extend(sensitive_changes_for_file(root, path, selection)?);
    }
    Ok(changes.into_iter().collect())
}

fn parse_markdown_scanned_paths(text: &str) -> BTreeSet<String> {
    let Some(captures) = MARKDOWN_SCANNED_PATHS.captures(text) else {
        return BTreeSet::new();
    };
    let value = captures.get(1).map_or("", |value| value.as_str()).trim();
    if value.is_empty() || value == "none" {
        return BTreeSet::new();
    }
    value
        .split(',')
        .map(str::trim)
        .filter(|path| !path.is_empty())
        .map(str::to_owned)
        .collect()
}

fn resolve_evidence_path(root: &Path, raw_path: &str) -> (PathBuf, String) {
    let path = resolve_non_strict(&root.join(raw_path));
    let relative = path
        .strip_prefix(root)
        .map(posix_path)
        .unwrap_or_else(|_| raw_path.to_owned());
    (path, relative)
}

fn scanned_paths_from_markdown(relative: &str, text: &str) -> (BTreeSet<String>, Option<Finding>) {
    if let Some(marker) = MARKDOWN_REQUIRED_MARKERS
        .iter()
        .find(|marker| !text.contains(**marker))
    {
        return (
            BTreeSet::new(),
            Some(Finding {
                path: relative.to_owned(),
                detail: format!("invalid-markdown-evidence:{marker}"),
            }),
        );
    }
    let scanned_paths = parse_markdown_scanned_paths(text);
    if scanned_paths.is_empty() {
        return (
            BTreeSet::new(),
            Some(Finding {
                path: relative.to_owned(),
                detail: "missing-scanned_paths".to_owned(),
            }),
        );
    }
    (scanned_paths, None)
}

fn scanned_paths_from_json(relative: &str, payload: &Value) -> (BTreeSet<String>, Option<Finding>) {
    let Some(payload) = payload.as_object() else {
        return (
            BTreeSet::new(),
            Some(Finding {
                path: relative.to_owned(),
                detail: "invalid-json-evidence".to_owned(),
            }),
        );
    };
    let Some(summary) = payload.get("summary").and_then(Value::as_object) else {
        return (
            BTreeSet::new(),
            Some(Finding {
                path: relative.to_owned(),
                detail: "missing-json-summary".to_owned(),
            }),
        );
    };
    if let Some(missing) = REQUIRED_JSON_SUMMARY_KEYS
        .iter()
        .find(|key| !summary.contains_key(**key))
    {
        return (
            BTreeSet::new(),
            Some(Finding {
                path: relative.to_owned(),
                detail: format!("missing-json-key:{missing}"),
            }),
        );
    }
    let Some(scanned_paths) = summary.get("scanned_paths").and_then(Value::as_array) else {
        return (
            BTreeSet::new(),
            Some(Finding {
                path: relative.to_owned(),
                detail: "invalid-scanned_paths".to_owned(),
            }),
        );
    };
    let mut paths = BTreeSet::new();
    for scanned_path in scanned_paths {
        let Some(scanned_path) = scanned_path.as_str() else {
            return (
                BTreeSet::new(),
                Some(Finding {
                    path: relative.to_owned(),
                    detail: "invalid-scanned_paths".to_owned(),
                }),
            );
        };
        paths.insert(scanned_path.to_owned());
    }
    (paths, None)
}

fn scanned_paths_from_evidence_text(
    relative: &str,
    text: &str,
) -> (BTreeSet<String>, Option<Finding>) {
    match serde_json::from_str::<Value>(text) {
        Ok(payload) => scanned_paths_from_json(relative, &payload),
        Err(_) => scanned_paths_from_markdown(relative, text),
    }
}

fn evidence_covered_paths(
    root: &Path,
    evidence_paths: &[String],
) -> (BTreeSet<String>, Vec<Finding>) {
    let mut covered = BTreeSet::new();
    let mut findings = Vec::new();
    for raw_path in evidence_paths {
        let (path, relative) = resolve_evidence_path(root, raw_path);
        let text = match fs::read_to_string(path) {
            Ok(text) => text,
            Err(_) => {
                findings.push(Finding {
                    path: relative,
                    detail: "missing-evidence-file".to_owned(),
                });
                continue;
            }
        };
        let (scanned_paths, finding) = scanned_paths_from_evidence_text(&relative, &text);
        if let Some(finding) = finding {
            findings.push(finding);
        } else {
            covered.extend(scanned_paths);
        }
    }
    (covered, findings)
}

fn check_evidence(
    root: &Path,
    sensitive_changes: &[SensitiveChange],
    evidence_paths: &[String],
) -> (Vec<Finding>, BTreeSet<String>) {
    let required_paths: BTreeSet<String> = sensitive_changes
        .iter()
        .map(|change| change.path.clone())
        .collect();
    if required_paths.is_empty() {
        return (Vec::new(), BTreeSet::new());
    }
    if evidence_paths.is_empty() {
        return (
            vec![Finding {
                path: "<evidence>".to_owned(),
                detail: "missing-oop-readability-evidence".to_owned(),
            }],
            BTreeSet::new(),
        );
    }
    let (covered, mut findings) = evidence_covered_paths(root, evidence_paths);
    for path in required_paths.difference(&covered) {
        findings.push(Finding {
            path: path.clone(),
            detail: "missing-path-coverage".to_owned(),
        });
    }
    (findings, covered)
}

fn text_output(
    sensitive_changes: &[SensitiveChange],
    findings: &[Finding],
    covered_paths: &BTreeSet<String>,
    verbose: bool,
) -> String {
    let mut lines = vec![
        format!(
            "SOLID_EVIDENCE={}",
            if findings.is_empty() { "pass" } else { "fail" }
        ),
        format!(
            "SOLID_EVIDENCE_SENSITIVE_CHANGES={}",
            sensitive_changes.len()
        ),
        format!("SOLID_EVIDENCE_COVERED_PATHS={}", covered_paths.len()),
    ];
    if verbose || !findings.is_empty() {
        lines.extend(
            sensitive_changes
                .iter()
                .map(|change| format!("SOLID_EVIDENCE_SENSITIVE_CHANGE={}", change.render())),
        );
    }
    lines.extend(findings.iter().map(Finding::render));
    lines.join("\n")
}

fn json_output(
    sensitive_changes: &[SensitiveChange],
    findings: &[Finding],
    covered_paths: &BTreeSet<String>,
) -> String {
    let changes: Vec<Value> = sensitive_changes
        .iter()
        .map(|change| {
            json!({
                "path": change.path,
                "line": change.line,
                "kind": change.kind,
                "symbol": change.symbol,
            })
        })
        .collect();
    let findings: Vec<Value> = findings
        .iter()
        .map(|finding| json!({"path": finding.path, "detail": finding.detail}))
        .collect();
    let payload = json!({
        "status": if findings.is_empty() { "pass" } else { "fail" },
        "sensitive_changes": changes,
        "covered_paths": covered_paths,
        "findings": findings,
    });
    let rendered = serde_json::to_string_pretty(&payload).unwrap_or_else(|_| "{}".to_owned());
    escape_non_ascii_json(&rendered)
}

fn escape_non_ascii_json(value: &str) -> String {
    let mut result = String::with_capacity(value.len());
    let mut in_string = false;
    let mut escaped = false;
    for character in value.chars() {
        if in_string && u32::from(character) > 0x7f {
            let scalar = u32::from(character);
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
