// @dependency-start
// contract implementation
// responsibility Evaluates checked-in Codex role configuration and explicit runtime evidence.
// upstream design ../../../../../../eval/definitions/README.md Eval ownership
// upstream implementation ../runtime_boundary.rs external artifact boundaries
// @dependency-end

mod configuration;
mod model_profiles;
mod reporting;
mod routing;
mod runtime_metrics;

use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::runtime_boundary::RuntimeArtifactBoundary;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;
use std::path::PathBuf;

pub const SELECTOR: &str = "evaluate-codex-agent-roles";

pub(crate) fn check_alignment(root: &Path) -> Result<Vec<Finding>, String> {
    let configs = load_configs(root)?;
    let mut findings = configuration::evaluate(root, &configs)?;
    findings.extend(routing::evaluate(root)?);
    let registry = model_profiles::ModelProfileRegistry::load(root)?;
    if let Err(error) = model_profiles::check_role_views(&registry, root, "consumer-static") {
        findings.push(Finding::new(
            "generated-view",
            "agents/agents_config.json",
            error,
        ));
    }
    Ok(findings)
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Finding {
    pub check: String,
    pub target: String,
    pub detail: String,
}

impl Finding {
    fn new(check: &str, target: impl Into<String>, detail: impl Into<String>) -> Self {
        Self {
            check: check.into(),
            target: target.into(),
            detail: detail.into(),
        }
    }

    fn line(&self) -> String {
        format!(
            "CODEX_AGENT_ROLE_FINDING={}:{}:{}",
            self.check, self.target, self.detail
        )
    }
}

type Configs = BTreeMap<String, Value>;

#[derive(Clone, Debug, Serialize)]
struct EvalRunMetadata {
    created_at: String,
    eval_run_id: String,
    run_id: String,
    argv: Vec<String>,
    cwd: String,
    root: String,
    git_branch: String,
    git_commit: String,
    git_dirty: String,
}

#[derive(Clone, Debug, Serialize)]
struct EvalReport {
    metadata: EvalRunMetadata,
    status: String,
    findings: Vec<Finding>,
    model_matrix: Vec<String>,
    runtime_metrics_status: String,
    runtime_metrics: BTreeMap<String, runtime_metrics::RuntimeSummary>,
}

fn read_toml(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|error| error.to_string())?;
    let document = text
        .parse::<toml_edit::DocumentMut>()
        .map_err(|error| error.to_string())?;
    toml_table(document.as_table())
}

fn toml_table(table: &dyn toml_edit::TableLike) -> Result<Value, String> {
    let mut result = serde_json::Map::new();
    for (key, item) in table.iter() {
        let value = match item {
            toml_edit::Item::None => continue,
            toml_edit::Item::Value(value) => toml_value(value)?,
            toml_edit::Item::Table(table) => toml_table(table)?,
            toml_edit::Item::ArrayOfTables(tables) => Value::Array(
                tables
                    .iter()
                    .map(|table| toml_table(table))
                    .collect::<Result<_, _>>()?,
            ),
        };
        result.insert(key.to_owned(), value);
    }
    Ok(Value::Object(result))
}

fn toml_value(value: &toml_edit::Value) -> Result<Value, String> {
    Ok(match value {
        toml_edit::Value::String(value) => Value::String(value.value().clone()),
        toml_edit::Value::Integer(value) => Value::from(*value.value()),
        toml_edit::Value::Float(value) => Value::from(*value.value()),
        toml_edit::Value::Boolean(value) => Value::Bool(*value.value()),
        toml_edit::Value::Datetime(value) => Value::String(value.value().to_string()),
        toml_edit::Value::Array(values) => {
            Value::Array(values.iter().map(toml_value).collect::<Result<_, _>>()?)
        }
        toml_edit::Value::InlineTable(table) => toml_table(table)?,
    })
}

fn load_configs(root: &Path) -> Result<Configs, String> {
    let directory = root.join(".codex/agents");
    let mut files = match fs::read_dir(&directory) {
        Ok(entries) => entries
            .map(|entry| entry.map(|entry| entry.path()))
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string())?,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Vec::new(),
        Err(error) => return Err(error.to_string()),
    };
    files.retain(|path| {
        path.extension()
            .is_some_and(|extension| extension == "toml")
    });
    files.sort();
    let mut configs = BTreeMap::new();
    for path in files {
        let mut config = read_toml(&path)?;
        let stem = path
            .file_stem()
            .and_then(|stem| stem.to_str())
            .ok_or("role config filename is not UTF-8")?;
        let id = config
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or(stem)
            .to_owned();
        config["__path"] = Value::String(
            path.strip_prefix(root)
                .map_err(|error| error.to_string())?
                .to_string_lossy()
                .replace('\\', "/"),
        );
        config["__stem"] = Value::String(stem.to_owned());
        configs.insert(id, config);
    }
    Ok(configs)
}

#[derive(Default)]
struct Options {
    root: PathBuf,
    runtime_root: Option<PathBuf>,
    runtime_logs: Vec<String>,
    report_out: Option<PathBuf>,
    compact_out: Option<PathBuf>,
    accumulate: bool,
    results_dir: String,
    run_id: String,
    json: bool,
    role_view_operation: Option<bool>,
    projection: Option<String>,
}

const HELP: &str = "usage: agent-canon evaluate-codex-agent-roles [--root ROOT] [--runtime-root PATH] [--runtime-log PATH] [--report-out PATH] [--compact-out PATH] [--accumulate] [--results-dir PATH] [--run-id ID] [--format text|json] [--generate-role-views|--check-role-views] [--projection live|consumer-static]\n\nEvaluate checked-in role configuration and optional runtime metrics, or generate/check canonical role views.\n";

fn arguments(args: &[String]) -> Result<Option<Options>, String> {
    let mut options = Options {
        root: std::env::current_dir().map_err(|error| error.to_string())?,
        projection: None,
        ..Options::default()
    };
    let names = [
        "--root",
        "--runtime-root",
        "--runtime-log",
        "--report-out",
        "--compact-out",
        "--accumulate",
        "--results-dir",
        "--run-id",
        "--format",
        "--generate-role-views",
        "--check-role-views",
        "--projection",
    ];
    let known = names
        .iter()
        .enumerate()
        .map(|(index, name)| (*name, index))
        .collect::<Vec<_>>();
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if matches!(argument.as_str(), "-h" | "--help") {
            return Ok(None);
        }
        let (name, inline) = argument
            .split_once('=')
            .map_or((argument.as_str(), None), |(name, value)| {
                (name, Some(value))
            });
        let selected = match resolve_long_option_prefix(name, &known) {
            Ok(selected) => selected,
            Err(LongOptionError::Unrecognized) => {
                return Err(format!("unrecognized arguments: {argument}"));
            }
            Err(LongOptionError::Ambiguous(matches)) => {
                return Err(format!(
                    "ambiguous option: {name} could match {}",
                    matches.join(", ")
                ));
            }
        };
        if selected == 5 || selected == 9 || selected == 10 {
            if let Some(value) = inline {
                return Err(format!(
                    "argument {}: ignored explicit argument '{value}'",
                    names[selected]
                ));
            }
            match selected {
                5 => options.accumulate = true,
                9 | 10 => {
                    if options.role_view_operation.is_some() {
                        return Err(
                            "--generate-role-views and --check-role-views are mutually exclusive"
                                .to_owned(),
                        );
                    }
                    options.role_view_operation = Some(selected == 9);
                }
                _ => unreachable!(),
            }
        } else {
            let value = if let Some(value) = inline {
                value.to_owned()
            } else {
                index += 1;
                args.get(index)
                    .filter(|value| !value.starts_with('-'))
                    .cloned()
                    .ok_or_else(|| format!("argument {}: expected one argument", names[selected]))?
            };
            match selected {
                0 => options.root = PathBuf::from(value),
                1 => options.runtime_root = Some(PathBuf::from(value)),
                2 => options.runtime_logs.push(value),
                3 => options.report_out = Some(PathBuf::from(value)),
                4 => options.compact_out = Some(PathBuf::from(value)),
                6 => options.results_dir = value,
                7 => options.run_id = value,
                8 => match value.as_str() {
                    "text" => options.json = false,
                    "json" => options.json = true,
                    _ => {
                        return Err(format!(
                            "argument --format: invalid choice: '{value}' (choose from 'text', 'json')"
                        ));
                    }
                },
                11 => match value.as_str() {
                    "live" | "consumer-static" => options.projection = Some(value),
                    _ => {
                        return Err(format!(
                            "argument --projection: invalid choice: '{value}' (choose from 'live', 'consumer-static')"
                        ));
                    }
                },
                _ => unreachable!(),
            }
        }
        index += 1;
    }
    options.root = crate::path_resolution::resolve_non_strict(&options.root)?;
    Ok(Some(options))
}

fn git(root: &Path, args: &[&str]) -> String {
    crate::git_read::output(root, args, std::time::Duration::from_secs(5))
        .ok()
        .flatten()
        .map(|output| output.trim().to_owned())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "-".into())
}

fn metadata(root: &Path, run_id: &str) -> EvalRunMetadata {
    let now = time::OffsetDateTime::now_utc();
    let fraction = now.nanosecond() / 1_000;
    let base = format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}",
        now.year(),
        now.month() as u8,
        now.day(),
        now.hour(),
        now.minute(),
        now.second()
    );
    let created_at = if fraction == 0 {
        format!("{base}+00:00")
    } else {
        format!("{base}.{fraction:06}+00:00")
    };
    let stamp = format!(
        "{:04}{:02}{:02}T{:02}{:02}{:02}{fraction:06}Z",
        now.year(),
        now.month() as u8,
        now.day(),
        now.hour(),
        now.minute(),
        now.second()
    );
    let root_text = root.to_string_lossy().replace('\\', "/");
    let digest = format!(
        "{:x}",
        Sha256::digest(
            format!(
                "codex-agent-role|{}|{created_at}|{root_text}",
                run_id.trim()
            )
            .as_bytes()
        )
    );
    EvalRunMetadata {
        created_at,
        eval_run_id: format!("codex-agent-role-eval-{stamp}-{}", &digest[..10]),
        run_id: run_id.trim().into(),
        argv: std::env::args().collect(),
        cwd: std::env::current_dir()
            .unwrap_or_default()
            .to_string_lossy()
            .replace('\\', "/"),
        root: root_text,
        git_branch: git(root, &["rev-parse", "--abbrev-ref", "HEAD"]),
        git_commit: git(root, &["rev-parse", "HEAD"]),
        git_dirty: if git(root, &["status", "--short", "--untracked-files=all"]).is_empty() {
            "no"
        } else {
            "yes"
        }
        .into(),
    }
}

fn execute(options: Options) -> Result<i32, String> {
    let needs_boundary = options.report_out.is_some()
        || options.compact_out.is_some()
        || options.accumulate
        || !options.runtime_logs.is_empty();
    let boundary = needs_boundary
        .then(|| {
            RuntimeArtifactBoundary::for_source(
                &options.root,
                options.runtime_root.as_deref(),
                true,
            )
        })
        .transpose()?;
    let configs = load_configs(&options.root)?;
    let mut findings = configuration::evaluate(&options.root, &configs)?;
    findings.extend(routing::evaluate(&options.root)?);
    let (runtime_metrics_status, runtime_metrics, metric_findings) = runtime_metrics::aggregate(
        &options.root,
        &options.runtime_logs,
        boundary.as_ref().map(RuntimeArtifactBoundary::root),
    )?;
    findings.extend(metric_findings);
    let matrix = configs
        .iter()
        .map(|(id, config)| {
            format!(
                "{id}:{}:{}",
                config
                    .get("model")
                    .and_then(Value::as_str)
                    .unwrap_or("None"),
                config
                    .get("model_reasoning_effort")
                    .and_then(Value::as_str)
                    .unwrap_or("None")
            )
        })
        .collect();
    let report = EvalReport {
        metadata: metadata(&options.root, &options.run_id),
        status: if findings.is_empty() { "pass" } else { "fail" }.into(),
        findings,
        model_matrix: matrix,
        runtime_metrics_status,
        runtime_metrics,
    };
    let mut reports = Vec::new();
    if let Some(path) = &options.report_out {
        reports.push(reporting::write_report(
            boundary.as_ref().expect("report boundary selected"),
            path,
            &report,
        )?);
    }
    if let Some(path) = &options.compact_out {
        boundary
            .as_ref()
            .expect("compact boundary selected")
            .atomic_write_text(
                path,
                &(reporting::pretty(&reporting::compact(&report))? + "\n"),
                0o600,
            )?;
    }
    if options.accumulate {
        let boundary = boundary.as_ref().expect("accumulation boundary selected");
        let directory = if options.results_dir.trim().is_empty() {
            crate::eval_archive_paths::eval_results_dir(
                &options.root,
                "codex-agent-role",
                Some(boundary.root()),
            )?
        } else {
            boundary.resolve(Path::new(options.results_dir.trim()))?
        };
        reports.push(reporting::write_report(
            boundary,
            &directory.join(format!(
                "{}-{}.md",
                report.metadata.eval_run_id, report.status
            )),
            &report,
        )?);
    }
    if options.json {
        println!(
            "{}",
            reporting::pretty(&serde_json::to_value(&report).map_err(|error| error.to_string())?)?
        );
    } else {
        print!(
            "{}",
            reporting::text(
                &report,
                options.compact_out.is_none(),
                options.compact_out.as_deref()
            )
        );
        for path in &reports {
            println!("CODEX_AGENT_ROLE_EVAL_REPORT={}", path.display());
        }
        if options.accumulate {
            if let Some(path) = reports.last() {
                println!(
                    "CODEX_AGENT_ROLE_EVAL_ACCUMULATED_REPORT={}",
                    path.display()
                );
            }
        }
    }
    Ok(i32::from(report.status != "pass"))
}

pub fn run(args: &[String]) -> i32 {
    match arguments(args) {
        Ok(None) => {
            print!("{HELP}");
            0
        }
        Ok(Some(options)) => {
            if let Some(generate) = options.role_view_operation {
                let has_eval_options = options.runtime_root.is_some()
                    || !options.runtime_logs.is_empty()
                    || options.report_out.is_some()
                    || options.compact_out.is_some()
                    || options.accumulate
                    || !options.results_dir.is_empty()
                    || !options.run_id.is_empty();
                if has_eval_options {
                    eprintln!(
                        "evaluate-codex-agent-roles: role-view operation cannot be combined with Eval options"
                    );
                    return 2;
                }
                let projection = options.projection.as_deref().unwrap_or("consumer-static");
                model_profiles::run_role_view_operation(&options.root, projection, generate)
            } else if options.projection.is_some() {
                eprintln!(
                    "evaluate-codex-agent-roles: --projection requires --generate-role-views or --check-role-views"
                );
                2
            } else {
                match execute(options) {
                    Ok(status) => status,
                    Err(error) => {
                        eprintln!("evaluate_codex_agent_roles.py: runtime_root_required: {error}");
                        2
                    }
                }
            }
        }
        Err(error) => {
            eprintln!("{HELP}evaluate-codex-agent-roles: error: {error}");
            2
        }
    }
}
