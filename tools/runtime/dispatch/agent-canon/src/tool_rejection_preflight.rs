// @dependency-start
// contract implementation
// responsibility Predicts optional tool and hook rejection gates for planned edit paths.
// upstream design ../../../../../agents/COMMUNICATION_PROTOCOL.md defines optional rejection prediction
// upstream design ../../../../../agents/skills/codex-task-workflow.md owns implementation preflight routing
// upstream design ../../../../../agents/skills/experiment-lifecycle.md owns managed experiment routing
// upstream design ../../../../../documents/experiments/experiment-registry.md defines the managed registry contract
// upstream design ../../../../../tools/README.md documents tool entrypoints
// upstream design ../../../../../documents/tools/README.md documents user-facing tool routes
// upstream implementation classify_path_risk.rs provides Python-compatible splitlines and JSON escaping
// upstream implementation responsibility_scope.rs validates and projects planned path owners
// upstream implementation ../../../../../tools/bin/agent-canon owns the stable native CLI
// downstream implementation main.rs registers the native selector
// downstream implementation ../../../../../tools/catalog.yaml publishes the native command
// downstream implementation ../../../../../tools/runtime/manifest/manifest_rendering.py projects the optional diagnostic
// downstream test ../../../../../tests/agent_tools/test_tool_rejection_preflight.py validates predicted gate routing
// @dependency-end

use crate::classify_path_risk::{json_ensure_ascii, python_splitlines};
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::responsibility_scope::{self, Scope, ScopeReport};
use agent_canon::path_resolution::resolve_non_strict;
use serde::Serialize;
use serde_json::json;
use std::collections::BTreeSet;
use std::env;
use std::ffi::OsStr;
use std::path::{Path, PathBuf};
use std::process::Command;

pub const SELECTOR: &str = "tool-rejection-preflight";
const USAGE: &str = "usage: agent-canon tool-rejection-preflight [--root ROOT] [--changed] [--format {text,json}] [paths ...]";
const HELP: &str = "Optionally predict candidate tool/hook checks for planned paths. Prediction is diagnostic, not edit authorization or required validation.\n\noptions:\n  --root ROOT          Repository root. Defaults to cwd.\n  --changed            Use git changed paths when explicit paths are not supplied.\n  --format {text,json} Output format.\n  -h, --help           Show this help message and exit.";
const RESPONSIBILITY_SCOPE_COMMAND: &str =
    "tools/bin/agent-canon responsibility-scope --root . --format json";
const NOTEBOOK_QUALITY_SOURCE_PATH: &str =
    "tools/runtime/dispatch/agent-canon/src/notebook_quality.rs";

const PYTHON_SUFFIXES: &[&str] = &[".py"];
const CPP_SUFFIXES: &[&str] = &[".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"];
const NOTEBOOK_SUFFIXES: &[&str] = &[".ipynb"];
const MARKDOWN_SUFFIXES: &[&str] = &[".md"];
const TEXT_SUFFIXES: &[&str] = &[
    ".bash", ".cfg", ".css", ".h", ".hpp", ".html", ".c", ".cc", ".cpp", ".json", ".md", ".py",
    ".rst", ".sh", ".toml", ".txt", ".yaml", ".yml", ".zsh",
];
const CODE_SUFFIXES: &[&str] = &[
    ".c", ".cc", ".cpp", ".cxx", ".go", ".h", ".hpp", ".java", ".js", ".jsx", ".kt", ".py", ".rs",
    ".sh", ".swift", ".ts", ".tsx",
];
const HOOK_SURFACE_PREFIXES: &[&str] = &[".codex/hooks/"];
const HOOK_CONFIG_PATHS: &[&str] = &[".codex/hooks.json"];
const SKILL_SURFACE_PREFIXES: &[&str] = &[".codex/personal/skills/", "agents/skills/"];
const SKILL_MIRROR_GATE_TEMPLATES: &[GateTemplate] = &[];
const TOOL_SURFACE_PREFIXES: &[&str] = &["tools/"];
const GITHUB_SURFACE_PREFIXES: &[&str] = &[".github/workflows/", ".github/actions/"];
const AGENT_PROTOCOL_PATHS: &[&str] = &[
    "agents/COMMUNICATION_PROTOCOL.md",
    "agents/canonical/CODEX_WORKFLOW.md",
    "agents/canonical/CODEX_SUBAGENTS.md",
    "eval/definitions/README.md",
    "templates/agents/workflow_monitoring.md",
    "agents/skills/agent-learning.md",
];
const EXPERIMENT_EXECUTION_SURFACE_PATHS: &[&str] = &[
    ".codex/personal/skills/experiment-lifecycle/SKILL.md",
    "agents/skills/experiment-lifecycle.md",
    "documents/experiments/experiment-registry.md",
    "documents/design/experiment_runner.md",
    "experiments/registry.toml",
    "tools/validation/ci/checks/check_experiment_registry.py",
    "tools/experiments/artifacts/save_experiment_result_annex.py",
    "tools/experiments/registry/registry_lib.py",
    "tools/experiments/execution/run_managed_experiment.py",
];
const LIBRARY_SURFACE_PREFIXES: &[&str] = &[
    "vendor/",
    "third_party/",
    "third-party/",
    "external/",
    "node_modules/",
    ".venv/",
];

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize)]
struct PredictedGate {
    path: String,
    gate: String,
    command: String,
    handoff: String,
}

#[derive(Clone, Copy)]
struct GateTemplate {
    gate: &'static str,
    command_template: &'static str,
    handoff: &'static str,
}

impl GateTemplate {
    fn for_path(self, path: &str) -> PredictedGate {
        PredictedGate {
            path: path.to_owned(),
            gate: self.gate.to_owned(),
            command: self.command_template.replace("{path}", path),
            handoff: self.handoff.trim().to_owned(),
        }
    }
}

const CAUSE_INVESTIGATION_GATE_TEMPLATES: &[GateTemplate] = &[GateTemplate {
    gate: "cause_investigation_guard",
    command_template: r#"printf '%s' '{"hookEventName":"PreToolUse","tool_name":"apply_patch","tool_input":{"patch":"*** Begin Patch\n*** Update File: {path}\n*** End Patch\n"}}' | tools/bin/agent-canon tool-rejection-preflight --gate cause_investigation"#,
    handoff: "record Observation, Hypothesis or Root Cause, Expected Fix Surface or Selected Surface, and Validation Before Edit or Support Evidence before code edits; for validation failures include failing_contract, observation_level, cause_classification, intent_preservation, and evidence for same-intent repair or escalation before write-capable repair",
}];
const PYTHON_GATE_TEMPLATES: &[GateTemplate] = &[
    GateTemplate {
        gate: "oop_readability_guard",
        command_template: "python3 tools/validation/code/oop/python/readability.py --root . {path}",
        handoff: "include OOP readability risk, repair plan, and the non-blocking review_oop_boundary_signal / OOP_READABILITY_REVIEW_SIGNAL_FINDINGS disposition before implementation edits",
    },
    GateTemplate {
        gate: "solid_evidence_gate",
        command_template: "tools/bin/agent-canon check-solid-evidence --root . {path} --evidence <oop-readability-report>",
        handoff: "attach a path-covered OOP readability JSON or Markdown report for SOLID-sensitive Python boundaries before closeout",
    },
];
const CPP_GATE_TEMPLATES: &[GateTemplate] = &[GateTemplate {
    gate: "oop_readability_guard",
    command_template: "python3 tools/validation/code/oop/cpp/readability.py --root . {path}",
    handoff: "include C/C++ OOP readability risk before edits",
}];
const STYLE_CHECK_GATE_TEMPLATES: &[GateTemplate] = &[GateTemplate {
    gate: "style_checker_guard",
    command_template: r#"printf '%s' '{"hookEventName":"PostToolUse","tool_name":"apply_patch"}' | tools/bin/agent-canon docs check"#,
    handoff: "include selected style checker families and unchecked changed-file coverage before continuing",
}];
const DEPENDENCY_GATE_TEMPLATES: &[GateTemplate] = &[GateTemplate {
    gate: "dependency_review",
    command_template: "bash tools/analysis/dependencies/run_repo_dependency_review.sh --root . --list-changed-dependencies",
    handoff: "include available dependency evidence and the related edit-scope plan; resolve ordinary dependencies from their actual source",
}];
const STRICT_SCHEMA_DEPENDENCY_GATE_TEMPLATES: &[GateTemplate] = &[GateTemplate {
    gate: "dependency_review",
    command_template: "bash tools/analysis/dependencies/run_repo_dependency_review.sh --root . --list-changed-dependencies",
    handoff: "preserve the strict JSON schema with top-level hooks only; record dependency context in owner docs, tests, or review artifacts",
}];
const GITHUB_GATE_TEMPLATES: &[GateTemplate] = &[GateTemplate {
    gate: "github_workflow_check",
    command_template: "python3 tools/validation/ci/checks/check_github_workflows.py",
    handoff: "include workflow checkout, permissions, and artifact evidence",
}];
const HOOK_RUNTIME_GATE_TEMPLATES: &[GateTemplate] = &[GateTemplate {
    gate: "codex_hook_runtime_alignment",
    command_template: "python3 tools/validation/semantic/runtime/check_agent_runtime_alignment.py && python3 -m pytest tests/agent_tools/test_codex_hooks.py -q",
    handoff: "include hook wiring, quiet-pass behavior, and runtime alignment evidence",
}];
const AGENT_PROTOCOL_GATE_TEMPLATES: &[GateTemplate] = &[GateTemplate {
    gate: "agent_protocol_convention",
    command_template: "python3 tools/validation/semantic/convention/check_convention_compliance.py",
    handoff:
        "include whether workflow, skill-routing, and hook/tool feedback protocol checks still pass",
}];
const TOOL_CATALOG_GATE_TEMPLATES: &[GateTemplate] = &[GateTemplate {
    gate: "tool_catalog",
    command_template: "tools/bin/agent-canon tool-catalog",
    handoff: "include catalog/docs/tests wiring for changed canonical tool surfaces",
}];
const NOTEBOOK_QUALITY_GATE_TEMPLATES: &[GateTemplate] = &[GateTemplate {
    gate: "notebook_quality_contract",
    command_template: "python3 -m pytest -q tests/tools/test_notebook_quality.py",
    handoff: "preserve the notebook-quality CLI contract and run its existing Rust-backed path, content, metric, warning, output, and exit oracles",
}];
const AGENT_CANON_NEW_TOOL_SOURCE_ROUTE_GATE_TEMPLATES: &[GateTemplate] = &[GateTemplate {
    gate: "agentcanon_new_tool_source_route",
    command_template: "git status --short --branch",
    handoff: "treat this planned path as AgentCanon-owned source: add it on the standalone AgentCanon branch/PR; do not create a parent-local copy",
}];
const EXPERIMENT_EXECUTION_SURFACE_GATE_TEMPLATES: &[GateTemplate] = &[GateTemplate {
    gate: "experiment_execution_surface_guard",
    command_template: "if [ -e experiments/registry.toml ]; then python3 -m tools.validation.ci.checks.check_experiment_registry; else echo EXPERIMENT_REGISTRY_CHECK=skipped_no_project_registry; fi && python3 -m pytest tests/tools/test_run_managed_experiment.py -q",
    handoff: "route planned edits through $experiment-lifecycle and $test-design; preserve the managed runner, registry checker, registry contract, and deterministic raw-only git-annex retention contract with lightweight registry and runner validation evidence",
}];
const LIBRARY_GATE_TEMPLATES: &[GateTemplate] = &[GateTemplate {
    gate: "library_implementation_guard",
    command_template: r#"printf '%s' '{"hookEventName":"PostToolUse","tool_name":"apply_patch"}' | import-only:tools.runtime.authority.task_authority:first_party_library_authorized"#,
    handoff: "do not rewrite vendored or installed library internals; use wrapper, adapter, fork/upstream patch, or manifest-backed vendor import",
}];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OptionName {
    Root,
    Changed,
    Format,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Args {
    root: PathBuf,
    use_changed: bool,
    format: OutputFormat,
    paths: Vec<String>,
    help: bool,
}

pub fn run(args: &[String]) -> i32 {
    let args = match parse_args(args) {
        Ok(args) => args,
        Err(message) => {
            eprintln!("tool-rejection-preflight: {message}");
            eprintln!("{USAGE}");
            return 2;
        }
    };
    if args.help {
        println!("{USAGE}\n\n{HELP}");
        return 0;
    }

    let root = match resolve_non_strict(&args.root) {
        Ok(root) => root,
        Err(error) => {
            eprintln!("tool-rejection-preflight: cannot resolve repository root: {error}");
            return 1;
        }
    };
    let paths = match planned_paths(&root, &args.paths, args.use_changed) {
        Ok(paths) => paths,
        Err(error) => {
            eprintln!("tool-rejection-preflight: {error}");
            return 1;
        }
    };
    let report = responsibility_scope::validate(&root, "responsibility-scope.toml");
    let ownerships = responsibility_scope::owners_for_paths(&report.scopes, &paths);
    let gates = predict_gates(&root, &paths, &report, &ownerships);
    match args.format {
        OutputFormat::Json => print_json(&gates),
        OutputFormat::Text => println!("{}", text_output(&gates)),
    }
    0
}

fn parse_args(args: &[String]) -> Result<Args, String> {
    let options = [
        ("--root", OptionName::Root),
        ("--changed", OptionName::Changed),
        ("--format", OptionName::Format),
    ];
    let mut root = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let mut use_changed = false;
    let mut format = OutputFormat::Text;
    let mut paths = Vec::new();
    let mut positional_only = false;
    let mut index = 0;

    while index < args.len() {
        let argument = &args[index];
        if !positional_only && matches!(argument.as_str(), "-h" | "--help") {
            return Ok(Args {
                root,
                use_changed,
                format,
                paths,
                help: true,
            });
        }
        if positional_only {
            paths.push(argument.clone());
            index += 1;
            continue;
        }
        if argument == "--" {
            positional_only = true;
            index += 1;
            continue;
        }
        if !argument.starts_with('-') || argument == "-" {
            paths.push(argument.clone());
            index += 1;
            continue;
        }

        let (raw_option, inline_value) = argument
            .split_once('=')
            .map_or((argument.as_str(), None), |(name, value)| {
                (name, Some(value))
            });
        let option = match resolve_long_option_prefix(raw_option, &options) {
            Ok(option) => option,
            Err(LongOptionError::Unrecognized) => {
                return Err(format!("unrecognized arguments: {argument}"));
            }
            Err(LongOptionError::Ambiguous(matches)) => {
                return Err(format!(
                    "ambiguous option: {raw_option} could match {}",
                    matches.join(", ")
                ));
            }
        };
        match option {
            OptionName::Changed => {
                if inline_value.is_some() {
                    return Err(format!("option {raw_option} does not take an argument"));
                }
                use_changed = true;
            }
            OptionName::Root | OptionName::Format => {
                let value = if let Some(value) = inline_value {
                    value.to_owned()
                } else {
                    index += 1;
                    let Some(value) = args.get(index) else {
                        return Err(format!("argument {raw_option}: expected one argument"));
                    };
                    if value.starts_with("--") || matches!(value.as_str(), "-h" | "--help") {
                        return Err(format!("argument {raw_option}: expected one argument"));
                    }
                    value.clone()
                };
                match option {
                    OptionName::Root => root = PathBuf::from(value),
                    OptionName::Format => {
                        format = match value.as_str() {
                            "text" => OutputFormat::Text,
                            "json" => OutputFormat::Json,
                            _ => {
                                return Err(format!(
                                    "argument --format: invalid choice: '{value}' (choose from 'text', 'json')"
                                ));
                            }
                        };
                    }
                    OptionName::Changed => unreachable!(),
                }
            }
        }
        index += 1;
    }

    Ok(Args {
        root,
        use_changed,
        format,
        paths,
        help: false,
    })
}

fn planned_paths(
    root: &Path,
    raw_paths: &[String],
    use_changed: bool,
) -> Result<Vec<String>, String> {
    let selected = if !raw_paths.is_empty() {
        raw_paths.to_vec()
    } else if use_changed {
        changed_paths(root)?
    } else {
        Vec::new()
    };
    let mut seen = BTreeSet::new();
    let mut paths = Vec::new();
    for raw_path in selected {
        let normalized = normalize_path(root, &raw_path)?;
        if seen.insert(normalized.clone()) {
            paths.push(normalized);
        }
    }
    Ok(paths)
}

fn changed_paths(root: &Path) -> Result<Vec<String>, String> {
    let mut paths = git_output_lines(
        root,
        &["diff", "--name-only", "--diff-filter=ACMRT", "HEAD"],
    )?;
    paths.extend(git_output_lines(
        root,
        &["ls-files", "--others", "--exclude-standard"],
    )?);
    paths.sort();
    paths.dedup();
    Ok(paths)
}

fn git_output_lines(root: &Path, arguments: &[&str]) -> Result<Vec<String>, String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(arguments)
        .output()
        .map_err(|error| format!("cannot run git {:?}: {error}", arguments))?;
    if !output.status.success() {
        return Ok(Vec::new());
    }
    let stdout = String::from_utf8(output.stdout)
        .map_err(|error| format!("git {:?} output is not valid UTF-8: {error}", arguments))?;
    Ok(python_splitlines(&stdout)
        .into_iter()
        .filter(|line| !line.is_empty())
        .map(str::to_owned)
        .collect())
}

fn normalize_path(root: &Path, raw_path: &str) -> Result<String, String> {
    let candidate = resolve_non_strict(&root.join(raw_path))
        .map_err(|error| format!("cannot resolve planned path {raw_path}: {error}"))?;
    Ok(match candidate.strip_prefix(root) {
        Ok(relative) => path_text(relative),
        Err(_) => raw_path.to_owned(),
    })
}

fn path_text(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn predict_gates(
    root: &Path,
    paths: &[String],
    report: &ScopeReport,
    ownerships: &[responsibility_scope::PathOwnership],
) -> BTreeSet<PredictedGate> {
    let mut gates = BTreeSet::new();
    for path in paths {
        gates.extend(path_gates(root, path, report, ownerships));
    }
    gates
}

fn path_gates(
    root: &Path,
    path: &str,
    report: &ScopeReport,
    ownerships: &[responsibility_scope::PathOwnership],
) -> Vec<PredictedGate> {
    let suffix = Path::new(path)
        .extension()
        .and_then(OsStr::to_str)
        .map(|extension| format!(".{extension}"))
        .unwrap_or_default();
    let mut gates = vec![render_responsibility_scope_gate(path, report, ownerships)];
    let mut templates = Vec::new();

    if contains(CODE_SUFFIXES, &suffix) {
        templates.extend_from_slice(CAUSE_INVESTIGATION_GATE_TEMPLATES);
    }
    if contains(PYTHON_SUFFIXES, &suffix) {
        templates.extend_from_slice(PYTHON_GATE_TEMPLATES);
    }
    if contains(CPP_SUFFIXES, &suffix) {
        templates.extend_from_slice(CPP_GATE_TEMPLATES);
    }
    if contains(PYTHON_SUFFIXES, &suffix)
        || contains(CPP_SUFFIXES, &suffix)
        || contains(NOTEBOOK_SUFFIXES, &suffix)
        || contains(MARKDOWN_SUFFIXES, &suffix)
    {
        templates.extend_from_slice(STYLE_CHECK_GATE_TEMPLATES);
    }
    if contains(TEXT_SUFFIXES, &suffix) {
        if HOOK_CONFIG_PATHS.contains(&path) {
            templates.extend_from_slice(STRICT_SCHEMA_DEPENDENCY_GATE_TEMPLATES);
        } else {
            templates.extend_from_slice(DEPENDENCY_GATE_TEMPLATES);
        }
    }
    if starts_with_any(path, HOOK_SURFACE_PREFIXES) || HOOK_CONFIG_PATHS.contains(&path) {
        templates.extend_from_slice(HOOK_RUNTIME_GATE_TEMPLATES);
    }
    if (path == "tools" || starts_with_any(path, TOOL_SURFACE_PREFIXES))
        && !root.join(path).exists()
    {
        templates.extend_from_slice(AGENT_CANON_NEW_TOOL_SOURCE_ROUTE_GATE_TEMPLATES);
    }
    if starts_with_any(path, SKILL_SURFACE_PREFIXES) {
        templates.extend_from_slice(SKILL_MIRROR_GATE_TEMPLATES);
    }
    if starts_with_any(path, GITHUB_SURFACE_PREFIXES) {
        templates.extend_from_slice(GITHUB_GATE_TEMPLATES);
    }
    if AGENT_PROTOCOL_PATHS.contains(&path) {
        templates.extend_from_slice(AGENT_PROTOCOL_GATE_TEMPLATES);
    }
    if EXPERIMENT_EXECUTION_SURFACE_PATHS.contains(&path) {
        templates.extend_from_slice(EXPERIMENT_EXECUTION_SURFACE_GATE_TEMPLATES);
    }
    if path == "tools/catalog.yaml" || starts_with_any(path, TOOL_SURFACE_PREFIXES) {
        templates.extend_from_slice(TOOL_CATALOG_GATE_TEMPLATES);
    }
    if path == NOTEBOOK_QUALITY_SOURCE_PATH {
        templates.extend_from_slice(NOTEBOOK_QUALITY_GATE_TEMPLATES);
    }
    if starts_with_any(path, LIBRARY_SURFACE_PREFIXES) {
        templates.extend_from_slice(LIBRARY_GATE_TEMPLATES);
    }

    gates.extend(
        templates
            .into_iter()
            .map(|template| template.for_path(path)),
    );
    gates
}

fn contains(values: &[&str], value: &str) -> bool {
    values.contains(&value)
}

fn starts_with_any(value: &str, prefixes: &[&str]) -> bool {
    prefixes.iter().any(|prefix| value.starts_with(prefix))
}

fn render_responsibility_scope_gate(
    path: &str,
    report: &ScopeReport,
    ownerships: &[responsibility_scope::PathOwnership],
) -> PredictedGate {
    let handoff = if !report.findings.is_empty() {
        format!(
            "repair responsibility-scope.toml or run from the repository owner root before editing; findings:{}",
            report.findings.len()
        )
    } else {
        let owner_ids = ownerships
            .iter()
            .find(|ownership| ownership.path == path)
            .map(|ownership| ownership.scope_ids.as_slice())
            .unwrap_or_default();
        let scopes = owner_ids
            .iter()
            .filter_map(|scope_id| {
                report
                    .scopes
                    .iter()
                    .find(|scope| &scope.scope_id == scope_id)
            })
            .collect::<Vec<_>>();
        match scopes.as_slice() {
            [scope] => render_scope_handoff(scope),
            [] => "assign this planned path to exactly one responsibility-scope.toml scope or move the edit to an existing owner surface before editing".to_owned(),
            overlaps => format!(
                "resolve planned path responsibility overlap before editing; {}",
                overlaps
                    .iter()
                    .map(|scope| render_scope_handoff(scope))
                    .collect::<Vec<_>>()
                    .join(" | ")
            ),
        }
    };
    PredictedGate {
        path: path.to_owned(),
        gate: "responsibility_scope".to_owned(),
        command: RESPONSIBILITY_SCOPE_COMMAND.to_owned(),
        handoff,
    }
}

fn render_scope_handoff(scope: &Scope) -> String {
    format!(
        "scope:{} owner:{} class:{} protecting_tools:{}",
        scope.scope_id,
        scope.owner,
        scope.scope_class,
        scope.protecting_tools.join(",")
    )
}

fn text_output(gates: &BTreeSet<PredictedGate>) -> String {
    let status = if gates.is_empty() { "pass" } else { "warn" };
    let mut lines = vec![
        format!("TOOL_REJECTION_PREFLIGHT={status}"),
        format!("TOOL_REJECTION_PREDICTED_GATES={}", gates.len()),
    ];
    lines.extend(gates.iter().map(|gate| {
        format!(
            "TOOL_REJECTION_PREDICTED_GATE=path:{}\tgate:{}\tcommand:{}\thandoff:{}",
            gate.path, gate.gate, gate.command, gate.handoff
        )
    }));
    lines.join("\n")
}

fn print_json(gates: &BTreeSet<PredictedGate>) {
    let output = json!({
        "status": if gates.is_empty() { "pass" } else { "warn" },
        "predicted_gate_count": gates.len(),
        "predicted_gates": gates,
    });
    let serialized =
        serde_json::to_string_pretty(&output).expect("tool rejection preflight report serializes");
    let ascii = json_ensure_ascii(&serialized).expect("serialized JSON can be ASCII escaped");
    println!("{ascii}");
}
