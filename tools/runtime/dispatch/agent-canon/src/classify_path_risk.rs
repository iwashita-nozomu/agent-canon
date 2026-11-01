// @dependency-start
// contract implementation
// responsibility Classifies changed paths into runtime risk profiles and canonical static-gate execution units.
// upstream design ../../../../../documents/runtime/runtime-profiles-and-check-matrix.md profile-based validation routing
// upstream design ../../../../../documents/design/responsibility-rationale.md evidence-triggered validation selection
// upstream design ../../../../../agents/TASK_WORKFLOWS.md risk-scaled workflow families
// downstream design ../../../../../documents/tools/classify_path_risk.md path-risk classification usage
// downstream implementation ../../../../../tests/agent_tools/test_classify_path_risk.py native selector behavior oracles
// downstream implementation ../../../../../tests/tools/test_standalone_static_gate_units.py selector and CI ownership oracles
// downstream implementation ../../../../../.github/workflows/agent-canon-static-gates.yml source-built unit selection
// @dependency-end
//! Classify changed paths into AgentCanon risk profiles and static-gate units.

use serde::Serialize;
use serde_json::Value;
use std::collections::HashSet;
use std::fmt::Write as _;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct PathRisk {
    pub profile: &'static str,
    pub reason: &'static str,
    pub checks: &'static [&'static str],
}

pub const STATIC_GATE_UNITS: &[&str] = &["docs", "rust", "contracts", "eval", "workflow-container"];

const DOC_SUFFIXES: &[&str] = &[".md"];
const DOC_CHECK_INPUTS: &[&str] = &[
    "tools/validation/documentation/config/lychee.toml",
    "tests/tools/test_docs_link_inputs.py",
    "tools/runtime/dispatch/agent-canon/src/docs.rs",
    "documents/runtime/runtime-profiles-and-check-matrix.json",
    "tests/tools/test_fix_mermaid.py",
];
const PYTHON_SUFFIXES: &[&str] = &[".py", ".pyi"];
const CONTAINER_PREFIXES: &[&str] = &["docker/", "bootstrap/", "tests/bootstrap/"];
const CONTAINER_PATHS: &[&str] = &[
    "bootstrap.sh",
    "tools/runtime/container/bootstrap_runtime.py",
    "tools/runtime/container/compile.sh",
    "tests/tools/test_bootstrap_container_contract.py",
    "tests/tools/test_compile_cache.py",
];
const GITHUB_PREFIXES: &[&str] = &[".github/"];
const EVAL_PREFIXES: &[&str] = &["eval/", "reports/agent-runtime-dashboard/"];
const EVAL_SOURCE_PREFIXES: &[&str] = &[
    "agents/",
    ".codex/",
    "templates/agents/",
    "tools/agent/",
    ".github/workflows/",
    "tools/validation/ci/",
    "documents/conventions/",
    "documents/operations/",
    "documents/rule/",
];
const EVAL_PATHS: &[&str] = &[
    "AGENTS.md",
    "ROOT_AGENTS.md",
    "bootstrap.sh",
    "bootstrap/host/manifest.toml",
    "bootstrap/host/lifecycle/entrypoint.sh",
    "tools/runtime/container/bootstrap_runtime.py",
    "tools/runtime/archive/runtime_log_archive_git.py",
    "tools/runtime/archive/github_eval_delivery.py",
];
const EVAL_TEST_PATHS: &[&str] = &["tests/agent_tools/test_eval_accumulation_check.py"];
const RUST_PREFIXES: &[&str] = &["tools/runtime/dispatch/agent-canon/"];
const DEPENDENCY_PATHS: &[&str] = &[
    "agents/skills/catalog.yaml",
    "agents/skills/skill-dependencies.yaml",
    "tools/catalog.yaml",
    "documents/tools/tool-docs.toml",
];
const SELECTOR_BOUNDARY_PATHS: &[&str] = &[
    // Keep the retired entrypoint path as a deletion-boundary input while the
    // new module path owns future selector changes.
    "tools/validation/semantic/path/classify_path_risk.py",
    "tools/runtime/dispatch/agent-canon/src/classify_path_risk.rs",
    "tools/validation/ci/runners/run_standalone_static_gate_unit.sh",
    "tools/validation/ci/checks/check_agent_canon_pr.sh",
    ".github/workflows/agent-canon-static-gates.yml",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
    GithubOutput,
}

#[derive(Debug)]
struct Arguments {
    paths: Vec<String>,
    paths_file: Option<PathBuf>,
    format: OutputFormat,
    full_confidence: bool,
}

/// Collect, trim, prefix-normalize, and stably deduplicate changed paths.
pub fn normalize_paths(
    paths: Vec<String>,
    paths_file: Option<&Path>,
) -> Result<Vec<String>, std::io::Error> {
    let mut collected = paths;
    if let Some(path) = paths_file.filter(|path| !path.as_os_str().is_empty()) {
        let contents = fs::read_to_string(path)?;
        collected.extend(python_splitlines(&contents).into_iter().map(str::to_owned));
    }
    let mut seen = HashSet::new();
    let mut normalized = Vec::new();
    for raw_path in collected {
        let trimmed = python_strip(&raw_path);
        let path = trimmed.strip_prefix("./").unwrap_or(trimmed);
        if !path.is_empty() && seen.insert(path.to_owned()) {
            normalized.push(path.to_owned());
        }
    }
    Ok(normalized)
}

fn python_strip(value: &str) -> &str {
    value.trim_matches(|character: char| {
        character.is_whitespace() || matches!(character, '\u{001c}'..='\u{001f}')
    })
}

fn python_splitlines(text: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut line_start = 0;
    let mut characters = text.char_indices().peekable();
    while let Some((index, character)) = characters.next() {
        let end = if character == '\r' {
            if characters.peek().is_some_and(|(_, next)| *next == '\n') {
                let (newline_index, newline) = characters.next().expect("peeked newline");
                newline_index + newline.len_utf8()
            } else {
                index + character.len_utf8()
            }
        } else if matches!(
            character,
            '\n' | '\u{000b}'
                | '\u{000c}'
                | '\u{001c}'
                | '\u{001d}'
                | '\u{001e}'
                | '\u{0085}'
                | '\u{2028}'
                | '\u{2029}'
        ) {
            index + character.len_utf8()
        } else {
            continue;
        };
        lines.push(&text[line_start..index]);
        line_start = end;
    }
    if line_start < text.len() {
        lines.push(&text[line_start..]);
    }
    lines
}

fn path_suffix(path: &str) -> &str {
    let name = Path::new(path)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or_default();
    match name.rfind('.') {
        Some(index) if index > 0 => &name[index..],
        _ => "",
    }
}

fn has_suffix(path: &str, suffixes: &[&str]) -> bool {
    suffixes.contains(&path_suffix(path))
}

fn has_prefix(path: &str, prefixes: &[&str]) -> bool {
    prefixes.iter().any(|prefix| path.starts_with(prefix))
}

/// Return active profiles and their stable validation checks in declaration order.
pub fn classify(paths: &[String]) -> Vec<PathRisk> {
    let mut active = Vec::new();
    if paths
        .iter()
        .any(|path| has_suffix(path, DOC_SUFFIXES) || DOC_CHECK_INPUTS.contains(&path.as_str()))
    {
        active.push(PathRisk {
            profile: "docs-only-or-docs-impact",
            reason: "markdown_or_docs_checker_changed",
            checks: &["tools/bin/agent-canon docs check"],
        });
    }
    if paths.iter().any(|path| has_suffix(path, PYTHON_SUFFIXES)) {
        active.push(PathRisk {
            profile: "python-tooling",
            reason: "python_path_changed",
            checks: &[
                "ruff check <changed-python-paths>",
                "basedpyright --project tools/validation/code/config/basedpyright-explicit-any.json <changed-python-paths>",
                "python3 -m pytest -q <targeted-tests>",
            ],
        });
    }
    if paths.iter().any(|path| {
        has_prefix(path, CONTAINER_PREFIXES) || CONTAINER_PATHS.contains(&path.as_str())
    }) {
        active.push(PathRisk {
            profile: "container-runtime",
            reason: "container_runtime_surface_changed",
            checks: &[
                "python3 -m pytest -q tests/tools/test_bootstrap_container_contract.py",
                "python3 -m pytest -q tests/bootstrap/test_bootstrap_runtime.py",
            ],
        });
    }
    if paths.iter().any(|path| has_prefix(path, GITHUB_PREFIXES)) {
        active.push(PathRisk {
            profile: "github-automation",
            reason: "github_surface_changed",
            checks: &["tools/bin/agent-canon check-github-workflows"],
        });
    }
    if paths.iter().any(|path| {
        has_prefix(path, EVAL_PREFIXES)
            || has_prefix(path, EVAL_SOURCE_PREFIXES)
            || EVAL_PATHS.contains(&path.as_str())
            || EVAL_TEST_PATHS.contains(&path.as_str())
    }) {
        active.push(PathRisk {
            profile: "agent-eval",
            reason: "eval_surface_changed",
            checks: &["python3 eval/producers/run_accumulated_agent_evals.py"],
        });
    }
    if paths.iter().any(|path| has_prefix(path, RUST_PREFIXES)) {
        active.push(PathRisk {
            profile: "rust",
            reason: "rust_surface_changed",
            checks: &["cargo test --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml"],
        });
    }
    if paths
        .iter()
        .any(|path| DEPENDENCY_PATHS.contains(&path.as_str()))
    {
        active.push(PathRisk {
            profile: "dependency",
            reason: "dependency_owner_changed",
            checks: &["bash tools/analysis/dependencies/run_repo_dependency_review.sh"],
        });
    }
    active
}

fn needs_contracts_fallback(path: &str) -> bool {
    let one_path = [path.to_owned()];
    !classify(&one_path)
        .iter()
        .any(|risk| risk.profile != "agent-eval")
        && !has_prefix(path, EVAL_PREFIXES)
        && !EVAL_TEST_PATHS.contains(&path)
}

/// Select the ordered union of required static-gate units, retaining unknown paths.
pub fn select_static_gate_units(paths: &[String], full_confidence: bool) -> Vec<&'static str> {
    if full_confidence
        || paths
            .iter()
            .any(|path| SELECTOR_BOUNDARY_PATHS.contains(&path.as_str()))
    {
        return STATIC_GATE_UNITS.to_vec();
    }
    let risks = classify(paths);
    let has_profile = |profile: &str| risks.iter().any(|risk| risk.profile == profile);
    let mut selected = Vec::new();
    if has_profile("docs-only-or-docs-impact") {
        selected.push("docs");
    }
    if has_profile("rust") {
        selected.push("rust");
    }
    if has_profile("python-tooling")
        || has_profile("dependency")
        || paths.iter().any(|path| needs_contracts_fallback(path))
    {
        selected.push("contracts");
    }
    if has_profile("agent-eval") {
        selected.push("eval");
    }
    if has_profile("github-automation") || has_profile("container-runtime") {
        selected.push("workflow-container");
    }
    selected
}

/// Render the stable human-readable classifier output.
pub fn render_text(paths: &[String], risks: &[PathRisk], units: &[&str]) -> String {
    let mut lines = vec![
        format!("PATH_RISK_INPUT_COUNT={}", paths.len()),
        format!(
            "PATH_RISK_ACTIVE_PROFILES={}",
            risks
                .iter()
                .map(|risk| risk.profile)
                .collect::<Vec<_>>()
                .join(",")
        ),
        format!("STATIC_GATE_UNITS={}", units.join(",")),
    ];
    for risk in risks {
        lines.push(format!(
            "PATH_RISK_PROFILE={} reason={}",
            risk.profile, risk.reason
        ));
        lines.extend(
            risk.checks
                .iter()
                .map(|check| format!("PATH_RISK_CHECK={}:{}", risk.profile, check)),
        );
    }
    lines.join("\n") + "\n"
}

/// Render stable GitHub Actions outputs from the canonical unit selection.
pub fn render_github_output(paths: &[String], units: &[&str]) -> Result<String, serde_json::Error> {
    let selected: HashSet<&str> = units.iter().copied().collect();
    let docs_paths = if paths
        .iter()
        .any(|path| DOC_CHECK_INPUTS.contains(&path.as_str()))
    {
        Vec::new()
    } else {
        paths
            .iter()
            .filter(|path| has_suffix(path, DOC_SUFFIXES))
            .collect::<Vec<_>>()
    };
    let docs_paths_json = render_json_string_array(&docs_paths)?;
    let mut lines = vec![
        format!("units={}", units.join(",")),
        format!("input_count={}", paths.len()),
        format!("docs_paths={docs_paths_json}"),
    ];
    lines.extend(STATIC_GATE_UNITS.iter().map(|unit| {
        let key = unit.replace('-', "_");
        format!("{key}={}", selected.contains(*unit))
    }));
    Ok(lines.join("\n") + "\n")
}

pub fn run(args: &[String]) -> i32 {
    let arguments = match parse_args(args) {
        Ok(Some(arguments)) => arguments,
        Ok(None) => {
            println!("{}", help_text());
            return 0;
        }
        Err(error) => return argument_error(&error),
    };
    let paths = match normalize_paths(arguments.paths, arguments.paths_file.as_deref()) {
        Ok(paths) => paths,
        Err(error) => {
            eprintln!("PATH_RISK_ERROR=paths_file_read_failed:{error}");
            return 1;
        }
    };
    let units = select_static_gate_units(&paths, arguments.full_confidence);
    let output = match arguments.format {
        OutputFormat::Text => Ok(render_text(&paths, &classify(&paths), &units)),
        OutputFormat::Json => render_json(&paths, &classify(&paths), &units),
        OutputFormat::GithubOutput => render_github_output(&paths, &units),
    };
    match output {
        Ok(output) => {
            print!("{output}");
            if !output.ends_with('\n') {
                println!();
            }
            0
        }
        Err(error) => {
            eprintln!("PATH_RISK_ERROR=serialization_failed:{error}");
            1
        }
    }
}

fn render_json(
    paths: &[String],
    risks: &[PathRisk],
    units: &[&str],
) -> Result<String, serde_json::Error> {
    let risks = risks
        .iter()
        .map(serde_json::to_value)
        .collect::<Result<Vec<Value>, _>>()?;
    let output = serde_json::json!({
        "paths": paths,
        "risks": risks,
        "units": units,
    });
    json_ensure_ascii(&serde_json::to_string_pretty(&output)?)
}

fn render_json_string_array(values: &[&String]) -> Result<String, serde_json::Error> {
    json_ensure_ascii(&serde_json::to_string(values)?)
}

fn json_ensure_ascii(serialized: &str) -> Result<String, serde_json::Error> {
    let mut output = String::with_capacity(serialized.len());
    for character in serialized.chars() {
        if character.is_ascii() {
            output.push(character);
            continue;
        }
        let codepoint = character as u32;
        if codepoint <= 0xffff {
            write!(output, "\\u{codepoint:04x}").expect("write JSON escape to String");
        } else {
            let supplementary = codepoint - 0x1_0000;
            let high = 0xd800 + (supplementary >> 10);
            let low = 0xdc00 + (supplementary & 0x3ff);
            write!(output, "\\u{high:04x}\\u{low:04x}")
                .expect("write JSON surrogate pair to String");
        }
    }
    Ok(output)
}

fn parse_args(args: &[String]) -> Result<Option<Arguments>, String> {
    let mut paths = Vec::new();
    let mut paths_file = None;
    let mut format = OutputFormat::Text;
    let mut full_confidence = false;
    let mut unknown: Vec<String> = Vec::new();
    let mut index = 0;
    let mut positional_only = false;
    while index < args.len() {
        let argument = &args[index];
        if !positional_only && matches!(argument.as_str(), "-h" | "--help") {
            return Ok(None);
        }
        if !positional_only && argument == "--" {
            positional_only = true;
            index += 1;
            continue;
        }
        if !positional_only && argument == "--full-confidence" {
            full_confidence = true;
            index += 1;
            continue;
        }
        if !positional_only && argument.starts_with('-') {
            let (name, inline_value) = argument
                .split_once('=')
                .map_or((argument.as_str(), None), |(name, value)| {
                    (name, Some(value))
                });
            if matches!(name, "--path" | "--paths-file" | "--format") {
                let value = match inline_value {
                    Some(value) => value.to_owned(),
                    None => {
                        let next = args
                            .get(index + 1)
                            .ok_or_else(|| format!("argument {name}: expected one argument"))?;
                        if next.starts_with('-') && next != "-" {
                            return Err(format!("argument {name}: expected one argument"));
                        }
                        index += 1;
                        next.to_owned()
                    }
                };
                match name {
                    "--path" => paths.push(value),
                    "--paths-file" => paths_file = Some(PathBuf::from(value)),
                    "--format" => {
                        format = match value.as_str() {
                            "text" => OutputFormat::Text,
                            "json" => OutputFormat::Json,
                            "github-output" => OutputFormat::GithubOutput,
                            _ => {
                                return Err(format!(
                                    "argument --format: invalid choice: '{value}' (choose from 'text', 'json', 'github-output')"
                                ));
                            }
                        };
                    }
                    _ => unreachable!(),
                }
            } else {
                unknown.push(argument.clone());
            }
        } else {
            unknown.push(argument.clone());
        }
        index += 1;
    }
    if !unknown.is_empty() {
        return Err(format!("unrecognized arguments: {}", unknown.join(" ")));
    }
    Ok(Some(Arguments {
        paths,
        paths_file,
        format,
        full_confidence,
    }))
}

fn argument_error(message: &str) -> i32 {
    eprintln!("usage: agent-canon classify-path-risk [-h] [options]");
    eprintln!("agent-canon classify-path-risk: error: {message}");
    2
}

fn help_text() -> &'static str {
    "usage: agent-canon classify-path-risk [-h] [options]\n\nClassify changed paths into AgentCanon risk profiles and static-gate units.\n\noptions:\n  -h, --help            show this help message and exit\n  --path PATH           changed path; repeatable\n  --paths-file PATHS_FILE\n                        newline-delimited changed paths\n  --format {text,json,github-output}\n  --full-confidence\n"
}
