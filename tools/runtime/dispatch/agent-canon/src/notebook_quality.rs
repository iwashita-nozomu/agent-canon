// @dependency-start
// contract implementation
// responsibility Validates notebooks as readable runnable demos instead of fine-grained tests.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md owns native tool migration and caller closure
// upstream implementation ../../../../../tools/catalog.yaml registers the notebook-quality selector
// upstream implementation python_cli_integer.rs parses Python-compatible integer thresholds
// downstream implementation main.rs exposes the notebook-quality selector
// downstream implementation ../../../../../tools/validation/ci/runners/run_all_checks.sh runs default notebook validation
// downstream implementation ../../../../../tools/validation/semantic/tools/tool_rejection_preflight.py predicts the notebook quality contract check
// downstream implementation ../../../../../tests/tools/test_notebook_quality.py preserves notebook checker CLI oracles
// downstream design ../../../../../documents/tools/notebook_quality.md documents the command contract
// @dependency-end

use crate::python_cli_integer::{is_argparse_negative_number, parse as parse_python_cli_integer};
use regex::Regex;
use rustpython_ast::bigint::BigInt;
use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeSet;
use std::fs;
use std::io::Read;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::str::FromStr;
use std::sync::OnceLock;
use std::thread;
use std::time::{Duration, Instant};

const NOTEBOOK_SUFFIX: &str = ".ipynb";
const DEFAULT_NOTEBOOK_DIRS: &[&str] = &["jupyter", "notebooks"];
const MAX_CODE_CELL_LINES: i64 = 80;
const MIN_MARKDOWN_CHARS: i64 = 120;
const GIT_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Clone, Debug, Serialize)]
struct Finding {
    cell: usize,
    check: String,
    detail: String,
    #[serde(serialize_with = "serialize_bigint_line")]
    line: BigInt,
    path: String,
}

impl Finding {
    fn new(
        path: &str,
        cell: usize,
        line: impl Into<BigInt>,
        check: &str,
        detail: impl Into<String>,
    ) -> Self {
        Self {
            cell,
            check: check.to_owned(),
            detail: detail.into(),
            line: line.into(),
            path: path.to_owned(),
        }
    }

    fn render(&self) -> String {
        format!(
            "NOTEBOOK_QUALITY_FINDING={}:cell={}:line={}:{}:{}",
            self.path, self.cell, self.line, self.check, self.detail
        )
    }
}

#[derive(Clone, Debug, Serialize)]
struct Warning {
    cell: usize,
    check: String,
    detail: String,
    line: i64,
    path: String,
}

impl Warning {
    fn new(path: &str, cell: usize, line: i64, check: &str, detail: impl Into<String>) -> Self {
        Self {
            cell,
            check: check.to_owned(),
            detail: detail.into(),
            line,
            path: path.to_owned(),
        }
    }

    fn render(&self) -> String {
        format!(
            "NOTEBOOK_QUALITY_WARNING={}:cell={}:line={}:{}:{}",
            self.path, self.cell, self.line, self.check, self.detail
        )
    }
}

#[derive(Clone, Debug, Serialize)]
struct NotebookMetrics {
    code_cells: usize,
    error_outputs: usize,
    markdown_cells: usize,
    markdown_chars: usize,
    path: String,
    visualization_cells: usize,
}

#[derive(Debug)]
struct NotebookReport {
    findings: Vec<Finding>,
    warnings: Vec<Warning>,
    metrics: Vec<NotebookMetrics>,
}

#[derive(Serialize)]
struct JsonReport<'a> {
    findings: &'a [Finding],
    metrics: &'a [NotebookMetrics],
    status: &'static str,
    warnings: &'a [Warning],
}

#[derive(Default)]
struct NotebookScanState {
    findings: Vec<Finding>,
    warnings: Vec<Warning>,
    markdown_cells: usize,
    code_cells: usize,
    visualization_cells: usize,
    error_outputs: usize,
    markdown_chars: usize,
    previous_was_code: bool,
    first_non_empty_type: String,
}

impl NotebookScanState {
    fn metrics(&self, path: &str) -> NotebookMetrics {
        NotebookMetrics {
            code_cells: self.code_cells,
            error_outputs: self.error_outputs,
            markdown_cells: self.markdown_cells,
            markdown_chars: self.markdown_chars,
            path: path.to_owned(),
            visualization_cells: self.visualization_cells,
        }
    }
}

struct Options {
    paths: Vec<String>,
    root: String,
    changed: bool,
    all: bool,
    max_code_cell_lines: BigInt,
    min_markdown_chars: BigInt,
    format: OutputFormat,
}

#[derive(Clone, Copy)]
enum OutputFormat {
    Text,
    Json,
}

enum ParseResult {
    Help,
    Options(Options),
}

/// Run `agent-canon notebook-quality`.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_args(args) {
        Ok(ParseResult::Help) => {
            print_help();
            return 0;
        }
        Ok(ParseResult::Options(options)) => options,
        Err(error) => {
            eprintln!("usage: agent-canon notebook-quality [paths...] [options]");
            eprintln!("agent-canon notebook-quality: error: {error}");
            return 2;
        }
    };

    let root = resolve_root(Path::new(&options.root));
    let paths = match notebook_paths(&root, &options.paths, options.changed, options.all) {
        Ok(paths) => paths,
        Err(error) => {
            eprintln!("agent-canon notebook-quality: {error}");
            return 1;
        }
    };
    let report = validate_paths(
        &root,
        &paths,
        &options.max_code_cell_lines,
        &options.min_markdown_chars,
    );
    match options.format {
        OutputFormat::Text => println!("{}", render_text(&report)),
        OutputFormat::Json => println!("{}", render_json(&report)),
    }
    if report.findings.is_empty() {
        0
    } else {
        1
    }
}

fn parse_args(raw: &[String]) -> Result<ParseResult, String> {
    let mut options = Options {
        paths: Vec::new(),
        root: ".".to_owned(),
        changed: false,
        all: false,
        max_code_cell_lines: BigInt::from(MAX_CODE_CELL_LINES),
        min_markdown_chars: BigInt::from(MIN_MARKDOWN_CHARS),
        format: OutputFormat::Text,
    };
    let mut index = 0;
    let mut positional_only = false;
    while index < raw.len() {
        let token = &raw[index];
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
            return Ok(ParseResult::Help);
        }
        if token == "--changed" {
            options.changed = true;
        } else if token == "--all" {
            options.all = true;
        } else if let Some(value) = token.strip_prefix("--root=") {
            options.root = value.to_owned();
        } else if token == "--root" {
            options.root = required_value(raw, index, token)?.to_owned();
            index += 1;
        } else if let Some(value) = token.strip_prefix("--max-code-cell-lines=") {
            options.max_code_cell_lines = parse_threshold(value, "--max-code-cell-lines")?;
        } else if token == "--max-code-cell-lines" {
            options.max_code_cell_lines =
                parse_threshold(required_value(raw, index, token)?, "--max-code-cell-lines")?;
            index += 1;
        } else if let Some(value) = token.strip_prefix("--min-markdown-chars=") {
            options.min_markdown_chars = parse_threshold(value, "--min-markdown-chars")?;
        } else if token == "--min-markdown-chars" {
            options.min_markdown_chars =
                parse_threshold(required_value(raw, index, token)?, "--min-markdown-chars")?;
            index += 1;
        } else if let Some(value) = token.strip_prefix("--format=") {
            options.format = parse_format(value)?;
        } else if token == "--format" {
            options.format = parse_format(required_value(raw, index, token)?)?;
            index += 1;
        } else if token.starts_with('-') && token != "-" && !is_argparse_negative_number(token) {
            return Err(format!("unrecognized arguments: {token}"));
        } else {
            options.paths.push(token.clone());
        }
        index += 1;
    }
    Ok(ParseResult::Options(options))
}

fn required_value<'a>(raw: &'a [String], index: usize, option: &str) -> Result<&'a str, String> {
    let value = raw
        .get(index + 1)
        .filter(|value| {
            !value.starts_with('-') || *value == "-" || is_argparse_negative_number(value)
        })
        .ok_or_else(|| format!("argument {option}: expected one argument"))?;
    Ok(value)
}

fn parse_threshold(raw: &str, option: &str) -> Result<BigInt, String> {
    parse_python_cli_integer(raw)
        .ok_or_else(|| format!("argument {option}: invalid int value: {raw:?}"))
}

fn parse_format(raw: &str) -> Result<OutputFormat, String> {
    match raw {
        "text" => Ok(OutputFormat::Text),
        "json" => Ok(OutputFormat::Json),
        _ => Err(format!(
            "argument --format: invalid choice: {raw:?} (choose from 'text', 'json')"
        )),
    }
}

fn print_help() {
    println!(
        "Validate notebooks as practical, readable, visualization-oriented demos.\n\n\
         usage: agent-canon notebook-quality [paths...] [options]\n\n\
         positional arguments:\n\
           paths                   Notebook files or directories to check.\n\n\
         options:\n\
           -h, --help              show this help message and exit\n\
           --root ROOT             Repository root. Defaults to cwd.\n\
           --changed               Check changed notebooks relative to HEAD plus untracked notebooks.\n\
           --all                   Check notebooks under the default notebook directories.\n\
           --max-code-cell-lines N Maximum source lines allowed in one code cell. Default: 80.\n\
           --min-markdown-chars N  Minimum total Markdown characters required. Default: 120.\n\
           --format {{text,json}}   Output format. Default: text."
    );
}

fn resolve_root(root: &Path) -> PathBuf {
    if let Ok(path) = fs::canonicalize(root) {
        return path;
    }
    let absolute = if root.is_absolute() {
        root.to_path_buf()
    } else {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(root)
    };
    normalize_absolute(&absolute)
}

fn normalize_absolute(path: &Path) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                if !normalized.pop() && !normalized.has_root() {
                    normalized.push(component.as_os_str());
                }
            }
            other => normalized.push(other.as_os_str()),
        }
    }
    normalized
}

fn notebook_paths(
    root: &Path,
    raw_paths: &[String],
    changed: bool,
    all: bool,
) -> Result<Vec<PathBuf>, String> {
    let paths = if !raw_paths.is_empty() {
        explicit_notebook_paths(root, raw_paths)
    } else if changed {
        changed_notebook_paths(root)?
    } else if all {
        all_notebook_paths(root)
    } else {
        changed_notebook_paths(root)?
    };
    Ok(sort_deduplicate_paths(paths))
}

fn explicit_notebook_paths(root: &Path, raw_paths: &[String]) -> Vec<PathBuf> {
    let mut paths = Vec::new();
    for raw_path in raw_paths {
        let path = PathBuf::from(raw_path);
        let candidate = if path.is_absolute() {
            path
        } else {
            root.join(path)
        };
        if candidate.is_dir() {
            collect_notebook_paths(&candidate, true, &mut paths);
        } else if has_notebook_suffix(&candidate) && candidate.is_file() {
            paths.push(candidate);
        }
    }
    paths
}

fn all_notebook_paths(root: &Path) -> Vec<PathBuf> {
    let mut paths = Vec::new();
    for relative_dir in DEFAULT_NOTEBOOK_DIRS {
        let directory = root.join(relative_dir);
        if directory.is_dir() {
            collect_notebook_paths(&directory, true, &mut paths);
        }
    }
    paths
}

fn collect_notebook_paths(directory: &Path, is_root: bool, paths: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(directory) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let Ok(file_type) = entry.file_type() else {
            continue;
        };
        if file_type.is_dir() {
            collect_notebook_paths(&path, false, paths);
        } else if file_type.is_symlink() {
            if is_root && path.is_dir() {
                collect_notebook_paths(&path, false, paths);
            } else if has_notebook_suffix(&path) && path.is_file() {
                paths.push(path);
            }
        } else if has_notebook_suffix(&path) && path.is_file() {
            paths.push(path);
        }
    }
}

fn changed_notebook_paths(root: &Path) -> Result<Vec<PathBuf>, String> {
    let mut names = BTreeSet::new();
    for args in [
        ["diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"].as_slice(),
        [
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMR",
            "--",
        ]
        .as_slice(),
        ["ls-files", "--others", "--exclude-standard"].as_slice(),
    ] {
        names.extend(git_lines(root, args)?);
    }
    Ok(names
        .into_iter()
        .filter(|name| name.ends_with(NOTEBOOK_SUFFIX))
        .map(|name| root.join(name))
        .filter(|path| path.is_file())
        .collect())
}

fn git_lines(root: &Path, args: &[&str]) -> Result<Vec<String>, String> {
    let mut child = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("could not start git: {error}"))?;
    let mut stdout = child
        .stdout
        .take()
        .ok_or_else(|| "could not capture git output".to_owned())?;
    let reader = thread::spawn(move || {
        let mut bytes = Vec::new();
        let result = stdout.read_to_end(&mut bytes);
        (result, bytes)
    });
    let started = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if started.elapsed() < GIT_TIMEOUT => {
                thread::sleep(Duration::from_millis(10));
            }
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                break None;
            }
            Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                break None;
            }
        }
    };
    let (read_result, bytes) = reader
        .join()
        .map_err(|_| "could not read git output".to_owned())?;
    if status.is_none() {
        return Err("git command timed out or failed while waiting (10 seconds)".to_owned());
    }
    if read_result.is_err() {
        return Err("could not read git output".to_owned());
    }
    if !status.is_some_and(|status| status.success()) {
        return Ok(Vec::new());
    }
    let output =
        String::from_utf8(bytes).map_err(|error| format!("git output is not UTF-8: {error}"))?;
    Ok(output
        .split('\n')
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(str::to_owned)
        .collect())
}

fn sort_deduplicate_paths(paths: Vec<PathBuf>) -> Vec<PathBuf> {
    let mut paths = paths
        .into_iter()
        .map(|path| normalize_path_components(&path))
        .collect::<Vec<_>>();
    paths.sort_by(|left, right| {
        left.components()
            .map(|component| component.as_os_str().to_os_string())
            .collect::<Vec<_>>()
            .cmp(
                &right
                    .components()
                    .map(|component| component.as_os_str().to_os_string())
                    .collect::<Vec<_>>(),
            )
    });
    paths.dedup();
    paths
}

fn normalize_path_components(path: &Path) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        if component != Component::CurDir {
            normalized.push(component.as_os_str());
        }
    }
    normalized
}

fn has_notebook_suffix(path: &Path) -> bool {
    path.extension()
        .is_some_and(|extension| extension == "ipynb")
}

fn display_path(root: &Path, path: &Path) -> String {
    let resolved = fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
    let resolved_root = fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    if let Ok(relative) = resolved.strip_prefix(resolved_root) {
        return relative.to_string_lossy().into_owned();
    }
    path.to_string_lossy().into_owned()
}

fn validate_paths(
    root: &Path,
    paths: &[PathBuf],
    max_code_cell_lines: &BigInt,
    min_markdown_chars: &BigInt,
) -> NotebookReport {
    let mut report = NotebookReport {
        findings: Vec::new(),
        warnings: Vec::new(),
        metrics: Vec::new(),
    };
    for path in paths {
        let display_path = display_path(root, path);
        let (findings, warnings, metrics) =
            validate_notebook(path, &display_path, max_code_cell_lines, min_markdown_chars);
        report.findings.extend(findings);
        report.warnings.extend(warnings);
        if let Some(metrics) = metrics {
            report.metrics.push(metrics);
        }
    }
    report
}

fn validate_notebook(
    path: &Path,
    display_path: &str,
    max_code_cell_lines: &BigInt,
    min_markdown_chars: &BigInt,
) -> (Vec<Finding>, Vec<Warning>, Option<NotebookMetrics>) {
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(error) => {
            return (
                vec![Finding::new(
                    display_path,
                    0,
                    0,
                    "invalid-json",
                    io_error_name(&error),
                )],
                Vec::new(),
                None,
            );
        }
    };
    let notebook: Value = match serde_json::from_slice(&bytes) {
        Ok(value) => value,
        Err(_) => {
            return (
                vec![Finding::new(
                    display_path,
                    0,
                    0,
                    "invalid-json",
                    "JSONDecodeError",
                )],
                Vec::new(),
                None,
            );
        }
    };
    let Some(object) = notebook.as_object() else {
        return (
            vec![Finding::new(
                display_path,
                0,
                0,
                "invalid-notebook",
                "top-level must be an object",
            )],
            Vec::new(),
            None,
        );
    };
    let Some(cells) = object.get("cells").and_then(Value::as_array) else {
        return (
            vec![Finding::new(
                display_path,
                0,
                0,
                "invalid-notebook",
                "cells must be a list",
            )],
            Vec::new(),
            None,
        );
    };

    let mut state = NotebookScanState::default();
    for (index, cell) in cells.iter().enumerate() {
        record_cell(
            &mut state,
            index + 1,
            cell,
            display_path,
            max_code_cell_lines,
        );
    }
    state.findings.extend(final_notebook_findings(
        &state,
        display_path,
        min_markdown_chars,
    ));
    let metrics = state.metrics(display_path);
    (state.findings, state.warnings, Some(metrics))
}

fn io_error_name(error: &std::io::Error) -> &'static str {
    match error.kind() {
        std::io::ErrorKind::NotFound => "FileNotFoundError",
        std::io::ErrorKind::PermissionDenied => "PermissionError",
        std::io::ErrorKind::IsADirectory => "IsADirectoryError",
        _ => "OSError",
    }
}

fn record_cell(
    state: &mut NotebookScanState,
    index: usize,
    value: &Value,
    display_path: &str,
    max_code_cell_lines: &BigInt,
) {
    let Some(cell) = value.as_object() else {
        state.findings.push(Finding::new(
            display_path,
            index,
            0,
            "invalid-cell",
            "cell must be an object",
        ));
        state.previous_was_code = false;
        return;
    };
    let kind = cell.get("cell_type").and_then(Value::as_str).unwrap_or("");
    let source = cell_source(cell.get("source"));
    if !python_strip(&source).is_empty() && state.first_non_empty_type.is_empty() {
        state.first_non_empty_type = kind.to_owned();
    }
    match kind {
        "markdown" => {
            state.markdown_cells += 1;
            state.markdown_chars += python_strip(&source).chars().count();
            state.previous_was_code = false;
        }
        "code" => record_code_cell(
            state,
            index,
            cell,
            &source,
            display_path,
            max_code_cell_lines,
        ),
        _ => state.previous_was_code = false,
    }
}

fn cell_source(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(source)) => source.clone(),
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(Value::as_str)
            .collect::<Vec<_>>()
            .join(""),
        _ => String::new(),
    }
}

fn record_code_cell(
    state: &mut NotebookScanState,
    index: usize,
    cell: &serde_json::Map<String, Value>,
    source: &str,
    display_path: &str,
    max_code_cell_lines: &BigInt,
) {
    state.code_cells += 1;
    if state.previous_was_code {
        state.findings.push(Finding::new(
            display_path,
            index,
            1,
            "consecutive-code-cells",
            "add a Markdown explanation between runnable steps",
        ));
    }
    let line_count = python_splitlines_count(source);
    if &BigInt::from(line_count) > max_code_cell_lines {
        state.findings.push(Finding::new(
            display_path,
            index,
            max_code_cell_lines.clone() + BigInt::from(1),
            "oversized-code-cell",
            format!("{line_count} lines exceeds {max_code_cell_lines}"),
        ));
    }
    state.previous_was_code = true;
    if has_visualization_code(source) {
        state.visualization_cells += 1;
    }
    let cell_errors = output_error_count(cell.get("outputs"));
    state.error_outputs += cell_errors;
    if cell_errors > 0 {
        state.warnings.push(Warning::new(
            display_path,
            index,
            0,
            "error-output",
            format!("{cell_errors} stored error output(s)"),
        ));
    }
    for (pattern, check, detail) in forbidden_patterns() {
        for matched in pattern.find_iter(source) {
            let line = source[..matched.start()]
                .bytes()
                .filter(|byte| *byte == b'\n')
                .count()
                + 1;
            state.findings.push(Finding::new(
                display_path,
                index,
                BigInt::from(line),
                check,
                *detail,
            ));
        }
    }
}

fn final_notebook_findings(
    state: &NotebookScanState,
    display_path: &str,
    min_markdown_chars: &BigInt,
) -> Vec<Finding> {
    let mut findings = Vec::new();
    if state.first_non_empty_type != "markdown" {
        findings.push(Finding::new(
            display_path,
            1,
            1,
            "missing-title-markdown",
            "first non-empty cell should be Markdown",
        ));
    }
    if state.markdown_cells == 0 {
        findings.push(Finding::new(
            display_path,
            0,
            0,
            "missing-markdown",
            "notebooks need narrative cells",
        ));
    }
    if state.code_cells == 0 {
        findings.push(Finding::new(
            display_path,
            0,
            0,
            "missing-code",
            "notebooks need runnable code cells",
        ));
    }
    if &BigInt::from(state.markdown_chars) < min_markdown_chars {
        findings.push(Finding::new(
            display_path,
            0,
            0,
            "thin-narrative",
            format!(
                "{} Markdown chars is below {min_markdown_chars}",
                state.markdown_chars
            ),
        ));
    }
    if state.visualization_cells == 0 {
        findings.push(Finding::new(
            display_path,
            0,
            0,
            "missing-visualization",
            "include runnable visualization code such as matplotlib, display, plotly, or dataframe plotting",
        ));
    }
    findings
}

fn output_error_count(value: Option<&Value>) -> usize {
    value
        .and_then(Value::as_array)
        .map(|outputs| {
            outputs
                .iter()
                .filter(|output| {
                    output
                        .as_object()
                        .and_then(|output| output.get("output_type"))
                        .and_then(Value::as_str)
                        == Some("error")
                })
                .count()
        })
        .unwrap_or(0)
}

fn forbidden_patterns() -> &'static [(Regex, &'static str, &'static str)] {
    static PATTERNS: OnceLock<Vec<(Regex, &'static str, &'static str)>> = OnceLock::new();
    PATTERNS.get_or_init(|| {
        [
            (
                r"(?m)^\s*assert\b",
                "fine-grained-assertion",
                "move assertions to tests/",
            ),
            (
                r"\bpytest\b",
                "pytest-in-notebook",
                "move pytest usage to tests/",
            ),
            (
                r"\bunittest\b",
                "unittest-in-notebook",
                "move unittest usage to tests/",
            ),
            (
                r"(?m)^\s*def\s+test_[A-Za-z0-9_]*\s*\(",
                "test-function",
                "move test functions to tests/",
            ),
            (
                r"\braise\s+AssertionError\b",
                "assertion-error",
                "move assertion failures to tests/",
            ),
            (
                r"\b(?:np|numpy)\.testing\b",
                "testing-helper",
                "move testing helpers to tests/",
            ),
        ]
        .into_iter()
        .map(|(pattern, check, detail)| {
            (
                Regex::new(pattern).expect("static notebook quality regular expression"),
                check,
                detail,
            )
        })
        .collect()
    })
}

fn visualization_patterns() -> &'static [Regex] {
    static PATTERNS: OnceLock<Vec<Regex>> = OnceLock::new();
    PATTERNS.get_or_init(|| {
        [
            r"\bplt\.(?:figure|subplots|plot|scatter|imshow|show)\b",
            r"\bdisplay\s*\(",
            r"\b(?:altair|plotly|bokeh|seaborn)\b",
            r"\.(?:plot|hist|imshow)\s*\(",
        ]
        .into_iter()
        .map(|pattern| Regex::new(pattern).expect("static visualization expression"))
        .collect()
    })
}

fn has_visualization_code(source: &str) -> bool {
    visualization_patterns()
        .iter()
        .any(|pattern| pattern.is_match(source))
}

fn python_splitlines_count(value: &str) -> usize {
    let mut lines = 0;
    let mut content_since_break = false;
    let mut characters = value.chars().peekable();
    while let Some(character) = characters.next() {
        if is_python_line_break(character) {
            lines += 1;
            content_since_break = false;
            if character == '\r' && characters.peek() == Some(&'\n') {
                characters.next();
            }
        } else {
            content_since_break = true;
        }
    }
    lines + usize::from(content_since_break)
}

fn is_python_line_break(character: char) -> bool {
    matches!(
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
    )
}

fn python_strip(value: &str) -> &str {
    value.trim_matches(is_python_whitespace)
}

fn is_python_whitespace(character: char) -> bool {
    character.is_whitespace()
        || matches!(character, '\u{001c}' | '\u{001d}' | '\u{001e}' | '\u{001f}')
}

fn render_text(report: &NotebookReport) -> String {
    let mut lines = vec![
        format!("NOTEBOOK_QUALITY_FILES={}", report.metrics.len()),
        format!("NOTEBOOK_QUALITY_FINDINGS={}", report.findings.len()),
        format!("NOTEBOOK_QUALITY_WARNINGS={}", report.warnings.len()),
    ];
    for metrics in &report.metrics {
        lines.push(format!(
            "NOTEBOOK_QUALITY_METRICS={}:markdown_cells={}:code_cells={}:visualization_cells={}:error_outputs={}:markdown_chars={}",
            metrics.path,
            metrics.markdown_cells,
            metrics.code_cells,
            metrics.visualization_cells,
            metrics.error_outputs,
            metrics.markdown_chars
        ));
    }
    lines.extend(report.findings.iter().map(Finding::render));
    lines.extend(report.warnings.iter().map(Warning::render));
    lines.push(format!(
        "NOTEBOOK_QUALITY={}",
        if report.findings.is_empty() {
            "pass"
        } else {
            "fail"
        }
    ));
    lines.join("\n")
}

fn render_json(report: &NotebookReport) -> String {
    let payload = JsonReport {
        findings: &report.findings,
        metrics: &report.metrics,
        status: if report.findings.is_empty() {
            "pass"
        } else {
            "fail"
        },
        warnings: &report.warnings,
    };
    serde_json::to_string(&payload)
        .expect("BigInt finding lines are valid arbitrary-precision JSON numbers")
}

fn serialize_bigint_line<S>(value: &BigInt, serializer: S) -> Result<S::Ok, S::Error>
where
    S: serde::Serializer,
{
    let number =
        serde_json::Number::from_str(&value.to_string()).map_err(serde::ser::Error::custom)?;
    number.serialize(serializer)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn cell_source_concatenates_only_string_fragments() {
        let cell = json!({"source": ["alpha", 3, "β", null, false]});
        assert_eq!(cell_source(cell.get("source")), "alphaβ");
    }

    #[test]
    fn markdown_character_count_uses_unicode_code_points() {
        assert_eq!(python_strip("  日本語🙂  ").chars().count(), 4);
    }

    #[test]
    fn code_source_line_count_matches_python_splitlines() {
        assert_eq!(python_splitlines_count(""), 0);
        assert_eq!(python_splitlines_count("a\r\nb\u{2028}c\n"), 3);
    }

    #[test]
    fn report_json_uses_python_sorted_key_order_and_schema() {
        let report = NotebookReport {
            findings: vec![Finding::new("demo.ipynb", 1, 2, "check", "detail")],
            warnings: Vec::new(),
            metrics: vec![NotebookMetrics {
                code_cells: 1,
                error_outputs: 0,
                markdown_cells: 1,
                markdown_chars: 4,
                path: "demo.ipynb".to_owned(),
                visualization_cells: 1,
            }],
        };
        let rendered = render_json(&report);
        assert!(rendered.starts_with("{\"findings\":[{\"cell\":1,\"check\":\"check\""));
        assert!(rendered.contains("\"metrics\":[{\"code_cells\":1,\"error_outputs\":0"));
        assert!(rendered.ends_with("\"status\":\"fail\",\"warnings\":[]}"));
    }
}
