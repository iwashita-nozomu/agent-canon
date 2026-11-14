// @dependency-start
// contract implementation
// responsibility Runs configured Lean proof attempts and records proof-search frontiers.
// upstream design ../../../../../documents/tools/lean_recursive_proof_search.md owns the CLI and report contract
// upstream implementation lean_proof_env.rs owns Lean process capture, exit normalization, and timeout execution
// downstream implementation main.rs exposes the recursive proof-search selector
// downstream test ../../../../../tests/agent_tools/test_lean_recursive_proof_search.py preserves CLI behavior
// @dependency-end

//! Native implementation of the configured recursive Lean proof-search CLI.

use crate::lean_proof_env::run_command_with_input;
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use regex::Regex;
use serde::Serialize;
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

pub const SELECTOR: &str = "lean-recursive-proof-search";
const MAX_GOAL_CHARS: usize = 3000;
const DEPENDENCY_PATH: &str =
    "tools/runtime/dispatch/agent-canon/src/lean_recursive_proof_search.rs";
const USAGE: &str = "usage: agent-canon lean-recursive-proof-search --config CONFIG [--format {json,markdown,text}] [--out OUT] [--batch] [--target TARGET] [--target-name-regex TARGET_NAME_REGEX] [--max-targets MAX_TARGETS] [--tactic-matrix TACTIC_MATRIX] [--attempt-timeout-sec ATTEMPT_TIMEOUT_SEC]";

#[derive(Clone, Debug, Serialize)]
struct TargetResult {
    name: String,
    role: String,
    status: String,
    returncode: i32,
    tactic: String,
    stdout: String,
    stderr: String,
    suggested_proof: String,
    unresolved_goals: Vec<String>,
    next_targets: Vec<String>,
}

#[derive(Clone, Debug)]
struct TargetScript {
    target: Map<String, Value>,
    tactic: String,
    script: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum OptionName {
    Config,
    Format,
    Out,
    Batch,
    Target,
    TargetNameRegex,
    MaxTargets,
    TacticMatrix,
    AttemptTimeoutSec,
    Help,
}

const OPTIONS: &[(&str, OptionName)] = &[
    ("--config", OptionName::Config),
    ("--format", OptionName::Format),
    ("--out", OptionName::Out),
    ("--batch", OptionName::Batch),
    ("--target", OptionName::Target),
    ("--target-name-regex", OptionName::TargetNameRegex),
    ("--max-targets", OptionName::MaxTargets),
    ("--tactic-matrix", OptionName::TacticMatrix),
    ("--attempt-timeout-sec", OptionName::AttemptTimeoutSec),
    ("--help", OptionName::Help),
];

#[derive(Default)]
struct Options {
    config: Option<PathBuf>,
    format: String,
    out: Option<PathBuf>,
    batch: bool,
    targets: Vec<String>,
    target_name_regex: Option<String>,
    max_targets: Option<i64>,
    tactic_matrix: Option<String>,
    attempt_timeout_sec: Option<f64>,
}

enum ParseResult {
    Help,
    Run(Options),
}

fn parse_args(args: &[String]) -> Result<ParseResult, String> {
    let mut options = Options {
        format: "text".into(),
        ..Options::default()
    };
    let mut index = 0usize;
    while index < args.len() {
        let token = &args[index];
        if token == "-h" {
            return Ok(ParseResult::Help);
        }
        let (name, inline) = token
            .split_once('=')
            .map_or((token.as_str(), None), |(name, value)| (name, Some(value)));
        let option = resolve_long_option_prefix(name, OPTIONS).map_err(|error| match error {
            LongOptionError::Unrecognized => format!("unrecognized arguments: {name}"),
            LongOptionError::Ambiguous(values) => {
                format!("ambiguous option: {name} could match {}", values.join(", "))
            }
        })?;
        if option == OptionName::Help {
            if inline.is_some() {
                return Err(format!(
                    "argument --help: ignored explicit argument '{token}'"
                ));
            }
            return Ok(ParseResult::Help);
        }
        if option == OptionName::Batch {
            if inline.is_some() {
                return Err(format!(
                    "argument --batch: ignored explicit argument '{token}'"
                ));
            }
            options.batch = true;
            index += 1;
            continue;
        }
        let value = if let Some(value) = inline {
            value.to_owned()
        } else {
            index += 1;
            args.get(index)
                .filter(|value| !value.starts_with('-') || is_negative_number(value))
                .cloned()
                .ok_or_else(|| format!("argument {name}: expected one argument"))?
        };
        match option {
            OptionName::Config => options.config = Some(PathBuf::from(value)),
            OptionName::Format => {
                if !["json", "markdown", "text"].contains(&value.as_str()) {
                    return Err(format!(
                        "argument --format: invalid choice: '{value}' (choose from 'json', 'markdown', 'text')"
                    ));
                }
                options.format = value;
            }
            OptionName::Out => options.out = Some(PathBuf::from(value)),
            OptionName::Target => options.targets.push(value),
            OptionName::TargetNameRegex => options.target_name_regex = Some(value),
            OptionName::MaxTargets => {
                options.max_targets =
                    Some(value.parse::<i64>().map_err(|_| {
                        format!("argument --max-targets: invalid int value: '{value}'")
                    })?)
            }
            OptionName::TacticMatrix => options.tactic_matrix = Some(value),
            OptionName::AttemptTimeoutSec => {
                options.attempt_timeout_sec = Some(value.parse::<f64>().map_err(|_| {
                    format!("argument --attempt-timeout-sec: invalid float value: '{value}'")
                })?)
            }
            OptionName::Batch | OptionName::Help => unreachable!(),
        }
        index += 1;
    }
    if options.config.is_none() {
        return Err("the following arguments are required: --config".into());
    }
    Ok(ParseResult::Run(options))
}

fn is_negative_number(value: &str) -> bool {
    value.parse::<f64>().is_ok()
}

fn python_string(value: &Value) -> String {
    match value {
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::String(value) => value.clone(),
        Value::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(|value| match value {
                    Value::String(value) => format!("'{value}'"),
                    _ => python_string(value),
                })
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Object(_) => "{...}".into(),
        Value::Number(number) => number.to_string(),
    }
}

fn string_list(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .map(|values| values.iter().map(python_string).collect())
        .unwrap_or_default()
}

fn dict_list(value: Option<&Value>) -> Vec<Map<String, Value>> {
    value
        .and_then(Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(Value::as_object)
                .cloned()
                .collect()
        })
        .unwrap_or_default()
}

fn config_cwd(config_path: &Path, config: &Map<String, Value>) -> PathBuf {
    config
        .get("cwd")
        .filter(|value| !value.is_null())
        .map(|value| PathBuf::from(python_string(value)))
        .unwrap_or_else(|| {
            config_path
                .parent()
                .filter(|path| !path.as_os_str().is_empty())
                .unwrap_or(Path::new("."))
                .to_path_buf()
        })
}

fn load_config(path: &Path) -> Result<Map<String, Value>, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    let value: Value = serde_json::from_str(&text).map_err(|error| error.to_string())?;
    value
        .as_object()
        .cloned()
        .ok_or_else(|| "config must be a JSON object".into())
}

fn config_text(config: &Map<String, Value>, key: &str, default: &str) -> String {
    config
        .get(key)
        .map(python_string)
        .unwrap_or_else(|| default.to_owned())
}

fn lean_script(
    config: &Map<String, Value>,
    target: &Map<String, Value>,
    tactic: &str,
) -> Result<String, String> {
    let imports = string_list(config.get("imports"))
        .into_iter()
        .map(|item| format!("import {item}"))
        .collect::<Vec<_>>()
        .join("\n");
    let opens = string_list(config.get("opens"))
        .into_iter()
        .map(|item| format!("open {item}"))
        .collect::<Vec<_>>()
        .join("\n");
    let options = string_list(config.get("options")).join("\n");
    let prelude = config_text(config, "prelude", "");
    let binders = target.get("binders").map(python_string).unwrap_or_default();
    let binders = crate::python_text::python_strip(&binders);
    let statement = target
        .get("statement")
        .map(python_string)
        .ok_or_else(|| "target is missing required field 'statement'".to_owned())?;
    let statement = crate::python_text::python_strip(&statement);
    let setup = target.get("setup").map(python_string).unwrap_or_default();
    let setup = crate::python_text::python_strip(&setup);
    let mut body = Vec::new();
    if !setup.is_empty() {
        body.push(setup.to_owned());
    }
    body.push(tactic.to_owned());
    let body = body.join("\n  ");
    Ok(format!(
        "{imports}\n\n{opens}\n\n{options}\n\n{prelude}\n\nnoncomputable section\n\nexample\n    {binders} :\n    {statement} := by\n  {body}\n"
    ))
}

fn lean_header(config: &Map<String, Value>) -> String {
    let imports = string_list(config.get("imports"))
        .into_iter()
        .map(|item| format!("import {item}"))
        .collect::<Vec<_>>()
        .join("\n");
    let opens = string_list(config.get("opens"))
        .into_iter()
        .map(|item| format!("open {item}"))
        .collect::<Vec<_>>()
        .join("\n");
    let options = string_list(config.get("options")).join("\n");
    let prelude = config_text(config, "prelude", "");
    format!("{imports}\n\n{opens}\n\n{options}\n\n{prelude}\n\nnoncomputable section\n")
}

fn lean_example_script(
    target: &Map<String, Value>,
    tactic: &str,
    index: Option<usize>,
) -> Result<String, String> {
    let binders = target.get("binders").map(python_string).unwrap_or_default();
    let binders = crate::python_text::python_strip(&binders);
    let statement = target
        .get("statement")
        .map(python_string)
        .ok_or_else(|| "target is missing required field 'statement'".to_owned())?;
    let statement = crate::python_text::python_strip(&statement);
    let setup = target.get("setup").map(python_string).unwrap_or_default();
    let setup = crate::python_text::python_strip(&setup);
    let mut body = Vec::new();
    if !setup.is_empty() {
        body.push(setup.to_owned());
    }
    body.push(tactic.to_owned());
    let body = body.join("\n  ");
    let marker = index.map_or_else(String::new, |index| {
        format!(
            "/-- proof-search-target:{index}:{} -/\n",
            target
                .get("name")
                .map(python_string)
                .unwrap_or_else(|| "None".into())
        )
    });
    Ok(format!(
        "{marker}example\n    {binders} :\n    {statement} := by\n  {body}\n"
    ))
}

fn target_name(target: &Map<String, Value>) -> String {
    target
        .get("name")
        .map(python_string)
        .unwrap_or_else(|| "None".into())
}

fn target_tactic(target: &Map<String, Value>) -> String {
    target
        .get("tactic")
        .map(python_string)
        .unwrap_or_else(|| "aesop?".into())
}

fn target_next(target: &Map<String, Value>) -> Vec<String> {
    string_list(target.get("next_targets"))
}

fn output_uses_sorry(output: &str) -> bool {
    [
        "warning: declaration uses `sorry`",
        "warning: declaration uses 'sorry'",
        "declaration uses `sorry`",
        "declaration uses 'sorry'",
    ]
    .iter()
    .any(|marker| output.contains(marker))
}

fn extract_suggestion(output: &str) -> String {
    let Some((_, tail)) = output.split_once("Try this:") else {
        return String::new();
    };
    tail.split_once("error:")
        .map(|(suggestion, _)| suggestion.trim())
        .unwrap_or_else(|| tail.trim())
        .to_owned()
}

fn extract_remaining_subgoal_blocks(output: &str) -> Vec<String> {
    let mut blocks = Vec::new();
    for part in output.split("-- Remaining subgoals:").skip(1) {
        let mut lines = Vec::new();
        for raw_line in part.lines() {
            let line = raw_line.trim_end();
            let stripped = line.trim();
            if ["Try this:", "found a partial proof", "<stdin>:", "[apply]"]
                .iter()
                .any(|marker| stripped.starts_with(marker))
            {
                break;
            }
            if line.is_empty() {
                if !lines.is_empty() {
                    break;
                }
                continue;
            }
            lines.push(line.strip_prefix("  -- ").unwrap_or(line).trim().to_owned());
        }
        if !lines.is_empty() {
            let block = lines.join("\n");
            blocks.push(block.chars().take(MAX_GOAL_CHARS).collect());
        }
    }
    blocks
}

fn extract_unresolved_goals(output: &str) -> Vec<String> {
    let mut goals = extract_remaining_subgoal_blocks(output);
    for chunk in output.split("unsolved goals").skip(1) {
        let snippet = crate::python_text::python_strip(chunk);
        if !snippet.is_empty() {
            goals.push(snippet.chars().take(MAX_GOAL_CHARS).collect());
        }
    }
    if output.contains("Initial goal:") {
        if let Some((_, goal)) = output.split_once("Initial goal:") {
            goals.push(
                crate::python_text::python_strip(goal)
                    .chars()
                    .take(MAX_GOAL_CHARS)
                    .collect(),
            );
        }
    }
    if goals.is_empty() && !output.trim().is_empty() {
        goals.push(output.trim().chars().take(MAX_GOAL_CHARS).collect());
    }
    let mut seen = BTreeSet::new();
    goals.retain(|goal| {
        let normalized = goal
            .lines()
            .map(str::trim_end)
            .collect::<Vec<_>>()
            .join("\n");
        seen.insert(normalized)
    });
    goals
}

fn run_lean(
    config_path: &Path,
    config: &Map<String, Value>,
    target: &Map<String, Value>,
    timeout_seconds: Option<f64>,
) -> Result<TargetResult, String> {
    let tactic = target_tactic(target);
    let cwd = config_cwd(config_path, config);
    let command = string_list(config.get("command"));
    let command = if command.is_empty() {
        ["lake", "env", "lean", "--stdin"]
            .iter()
            .map(|value| value.to_string())
            .collect()
    } else {
        command
    };
    let script = lean_script(config, target, &tactic)?;
    let (process, timed_out) =
        run_command_with_input(&command, &cwd, Some(&script), timeout_seconds)
            .map_err(|error| format!("run Lean for {}: {error}", target_name(target)))?;
    let output = [process.stdout.as_str(), process.stderr.as_str()]
        .into_iter()
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join("\n");
    let suggested_proof = extract_suggestion(&output);
    let unresolved_goals = extract_unresolved_goals(&output);
    let uses_sorry = output_uses_sorry(&output);
    let status = if timed_out {
        "timeout"
    } else if process.returncode == 0 && !uses_sorry {
        "verified"
    } else if uses_sorry && !unresolved_goals.is_empty() {
        "partial_proof_with_sorry"
    } else if uses_sorry {
        "partial_proof_with_sorry_no_structured_goals"
    } else if !unresolved_goals.is_empty() {
        "unverified_with_next_goals"
    } else {
        "failed_no_structured_goals"
    };
    Ok(TargetResult {
        name: target_name(target),
        role: target
            .get("role")
            .map(python_string)
            .unwrap_or_else(|| "proof".into()),
        status: status.into(),
        returncode: process.returncode,
        tactic,
        stdout: process.stdout,
        stderr: process.stderr,
        suggested_proof,
        unresolved_goals,
        next_targets: target_next(target),
    })
}

fn run_lean_batch(
    config_path: &Path,
    config: &Map<String, Value>,
    targets: &[Map<String, Value>],
) -> Result<Vec<TargetResult>, String> {
    let cwd = config_cwd(config_path, config);
    let command = string_list(config.get("command"));
    let command = if command.is_empty() {
        ["lake", "env", "lean", "--stdin"]
            .iter()
            .map(|value| value.to_string())
            .collect()
    } else {
        command
    };
    let mut scripts = Vec::new();
    for (index, target) in targets.iter().enumerate() {
        let tactic = target_tactic(target);
        scripts.push(TargetScript {
            target: target.clone(),
            tactic: tactic.clone(),
            script: lean_example_script(target, &tactic, Some(index))?,
        });
    }
    let input = format!(
        "{}\n{}",
        lean_header(config),
        scripts
            .iter()
            .map(|script| script.script.as_str())
            .collect::<Vec<_>>()
            .join("\n\n")
    );
    let (process, _) = run_command_with_input(&command, &cwd, Some(&input), None)
        .map_err(|error| format!("run Lean batch: {error}"))?;
    if process.returncode == 0 {
        return Ok(scripts
            .into_iter()
            .map(|script| TargetResult {
                name: target_name(&script.target),
                role: script
                    .target
                    .get("role")
                    .map(python_string)
                    .unwrap_or_else(|| "proof".into()),
                status: "verified".into(),
                returncode: 0,
                tactic: script.tactic,
                stdout: String::new(),
                stderr: String::new(),
                suggested_proof: String::new(),
                unresolved_goals: Vec::new(),
                next_targets: target_next(&script.target),
            })
            .collect());
    }
    let output = [process.stdout.as_str(), process.stderr.as_str()]
        .into_iter()
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join("\n");
    Ok(vec![TargetResult {
        name: "_batch".into(),
        role: "proof".into(),
        status: "failed_no_structured_goals".into(),
        returncode: process.returncode,
        tactic: "batch".into(),
        stdout: process.stdout,
        stderr: process.stderr,
        suggested_proof: extract_suggestion(&output),
        unresolved_goals: extract_unresolved_goals(&output),
        next_targets: Vec::new(),
    }])
}

fn filtered_targets(
    targets: Vec<Map<String, Value>>,
    names: &[String],
    name_regex: Option<&str>,
    max_targets: Option<i64>,
) -> Result<Vec<Map<String, Value>>, String> {
    let mut selected = targets;
    if !names.is_empty() {
        selected.retain(|target| names.contains(&target_name(target)));
    }
    if let Some(pattern) = name_regex {
        let pattern =
            Regex::new(pattern).map_err(|error| format!("invalid target name regex: {error}"))?;
        selected.retain(|target| {
            pattern.is_match(&target.get("name").map(python_string).unwrap_or_default())
        });
    }
    if let Some(maximum) = max_targets {
        let end = if maximum < 0 {
            selected
                .len()
                .saturating_sub(maximum.unsigned_abs() as usize)
        } else {
            (maximum as usize).min(selected.len())
        };
        selected.truncate(end);
    }
    Ok(selected)
}

fn tactic_list(value: Option<&str>) -> Vec<String> {
    value
        .map(|value| {
            value
                .split(',')
                .map(str::trim)
                .filter(|item| !item.is_empty())
                .map(str::to_owned)
                .collect()
        })
        .unwrap_or_default()
}

fn with_tactic(target: &Map<String, Value>, tactic: &str) -> Map<String, Value> {
    let mut target = target.clone();
    target.insert("tactic".into(), json!(tactic));
    target
}

fn run_tactic_matrix(
    config_path: &Path,
    config: &Map<String, Value>,
    targets: &[Map<String, Value>],
    tactics: &[String],
    timeout_seconds: Option<f64>,
) -> Result<Vec<TargetResult>, String> {
    let mut results = Vec::new();
    for target in targets {
        for tactic in tactics {
            results.push(run_lean(
                config_path,
                config,
                &with_tactic(target, tactic),
                timeout_seconds,
            )?);
        }
    }
    Ok(results)
}

fn matrix_target_statuses(results: &[TargetResult]) -> BTreeMap<String, String> {
    let mut grouped = BTreeMap::<String, Vec<&TargetResult>>::new();
    for result in results {
        grouped.entry(result.name.clone()).or_default().push(result);
    }
    grouped
        .into_iter()
        .map(|(name, group)| {
            let status = if group.iter().any(|result| result.status == "verified") {
                "verified_by_some_tactic"
            } else {
                "unverified_by_all_tactics"
            };
            (name, status.to_owned())
        })
        .collect()
}

fn render_text(results: &[TargetResult]) -> String {
    let mut lines = vec![format!("LEAN_RECURSIVE_PROOF_TARGETS={}", results.len())];
    for result in results {
        let status = if result.role == "proof" {
            result.status.clone()
        } else {
            format!("{}:{}", result.status, result.role)
        };
        lines.push(format!(
            "LEAN_RECURSIVE_PROOF_TARGET={}:{}:next={}",
            result.name,
            status,
            if result.next_targets.is_empty() {
                "none".to_owned()
            } else {
                result.next_targets.join(",")
            }
        ));
    }
    lines.join("\n") + "\n"
}

fn source_root() -> PathBuf {
    env::var_os("AGENT_CANON_SOURCE_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .ancestors()
                .nth(4)
                .unwrap_or(Path::new("."))
                .to_path_buf()
        })
}

fn dependency_path_from_output(output_path: Option<&Path>) -> String {
    let implementation = source_root().join(DEPENDENCY_PATH);
    let implementation =
        crate::path_resolution::resolve_non_strict(&implementation).unwrap_or(implementation);
    let Some(output_path) = output_path else {
        return implementation.to_string_lossy().replace('\\', "/");
    };
    let output = crate::path_resolution::resolve_non_strict(output_path).unwrap_or_else(|_| {
        if output_path.is_absolute() {
            output_path.to_path_buf()
        } else {
            env::current_dir()
                .unwrap_or_else(|_| PathBuf::from("."))
                .join(output_path)
        }
    });
    let output_parent = output.parent().unwrap_or(Path::new("."));
    pathdiff::diff_paths(&implementation, output_parent)
        .unwrap_or(implementation)
        .to_string_lossy()
        .replace('\\', "/")
}

fn render_markdown(
    results: &[TargetResult],
    config: &Map<String, Value>,
    output_path: Option<&Path>,
) -> String {
    let mut groups = BTreeMap::<String, Vec<&TargetResult>>::new();
    for result in results {
        groups.entry(result.name.clone()).or_default().push(result);
    }
    let matrix_mode = groups.values().any(|group| group.len() > 1);
    let theorem = config
        .get("target_theorem")
        .map(python_string)
        .unwrap_or_else(|| "unspecified".into());
    let mut lines = vec![
        "<!--".to_owned(),
        "@dependency-start".to_owned(),
        "responsibility Records recursive Lean proof-search results for a configured theorem target.".to_owned(),
        format!(
            "upstream implementation {} generates this report from the configured Lean target file.",
            dependency_path_from_output(output_path)
        ),
        "downstream design check_finite_stop_goal.py consumes target status rows and unresolved goals.".to_owned(),
        "@dependency-end".to_owned(),
        "-->".to_owned(),
        String::new(),
        "# Recursive Lean Proof Search".to_owned(),
        String::new(),
        format!("- target theorem: `{theorem}`"),
        format!("- targets: `{}`", results.len()),
        String::new(),
        "| Target | Status | Next Targets | Suggested Proof |".to_owned(),
        "| --- | --- | --- | --- |".to_owned(),
    ];
    for result in results {
        let suggestion = result
            .suggested_proof
            .replace('|', "\\|")
            .replace('\n', "<br>");
        let status = if result.role == "proof" {
            result.status.clone()
        } else {
            format!("{}:{}", result.status, result.role)
        };
        lines.push(format!(
            "| `{}` | `{status}` | `{}` | {} |",
            result.name,
            if result.next_targets.is_empty() {
                "none".to_owned()
            } else {
                result.next_targets.join(", ")
            },
            if suggestion.is_empty() {
                "`none`".to_owned()
            } else {
                suggestion
            }
        ));
    }
    if matrix_mode {
        lines.extend([
            String::new(),
            "## Tactic Matrix Summary".to_owned(),
            String::new(),
            "| Target | Matrix Status | Verified Tactics |".to_owned(),
            "| --- | --- | --- |".to_owned(),
        ]);
        for (name, group) in &groups {
            let verified = group
                .iter()
                .filter(|result| result.status == "verified")
                .map(|result| result.tactic.clone())
                .collect::<Vec<_>>();
            let status = if verified.is_empty() {
                "unverified_by_all_tactics"
            } else {
                "verified_by_some_tactic"
            };
            lines.push(format!(
                "| `{name}` | `{status}` | `{}` |",
                if verified.is_empty() {
                    "none".to_owned()
                } else {
                    verified.join(", ")
                }
            ));
        }
    }
    for result in results {
        if result.unresolved_goals.is_empty() {
            continue;
        }
        lines.extend([
            String::new(),
            format!(
                "## `{}` / `{}` Unresolved Goals",
                result.name, result.tactic
            ),
            String::new(),
        ]);
        for (index, goal) in result.unresolved_goals.iter().enumerate() {
            lines.extend([
                format!("### Goal {}", index + 1),
                String::new(),
                "```text".to_owned(),
                goal.clone(),
                "```".to_owned(),
            ]);
        }
    }
    lines.join("\n") + "\n"
}

fn render_json(
    results: &[TargetResult],
    config: &Map<String, Value>,
    tactics: bool,
) -> Result<String, String> {
    let value = json!({
        "status": "lean_recursive_proof_search_complete",
        "target_theorem": config.get("target_theorem").cloned().unwrap_or_else(|| json!("")),
        "matrix_target_statuses": if tactics { json!(matrix_target_statuses(results)) } else { json!({}) },
        "results": results,
    });
    serde_json::to_string_pretty(&value)
        .map(|value| value + "\n")
        .map_err(|error| format!("serialize recursive proof-search output: {error}"))
}

pub fn run(args: &[String]) -> i32 {
    let options = match parse_args(args) {
        Ok(ParseResult::Help) => {
            println!("{USAGE}\n\nRun configured Lean proof targets and record unresolved goals.");
            return 0;
        }
        Ok(ParseResult::Run(options)) => options,
        Err(error) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let config_path = options
        .config
        .as_deref()
        .expect("config option is required");
    let config = match load_config(config_path) {
        Ok(config) => config,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let targets = match filtered_targets(
        dict_list(config.get("targets")),
        &options.targets,
        options.target_name_regex.as_deref(),
        options.max_targets,
    ) {
        Ok(targets) => targets,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let tactics = tactic_list(options.tactic_matrix.as_deref());
    let results = if !tactics.is_empty() {
        run_tactic_matrix(
            config_path,
            &config,
            &targets,
            &tactics,
            options.attempt_timeout_sec,
        )
    } else if options.batch {
        run_lean_batch(config_path, &config, &targets)
    } else {
        targets
            .iter()
            .map(|target| run_lean(config_path, &config, target, options.attempt_timeout_sec))
            .collect()
    };
    let results = match results {
        Ok(results) => results,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 1;
        }
    };
    let rendered = match options.format.as_str() {
        "json" => match render_json(&results, &config, !tactics.is_empty()) {
            Ok(value) => value,
            Err(error) => {
                eprintln!("agent-canon {SELECTOR}: error: {error}");
                return 1;
            }
        },
        "markdown" => render_markdown(&results, &config, options.out.as_deref()),
        _ => render_text(&results),
    };
    if let Some(path) = options.out.as_deref() {
        if let Err(error) = fs::write(path, rendered.as_bytes()) {
            eprintln!("agent-canon {SELECTOR}: {}: {error}", path.display());
            return 1;
        }
    } else {
        print!("{rendered}");
    }
    if !tactics.is_empty() {
        let statuses = matrix_target_statuses(&results);
        return if statuses
            .values()
            .all(|status| status == "verified_by_some_tactic")
        {
            0
        } else {
            1
        };
    }
    if results.iter().any(|result| result.returncode != 0) {
        1
    } else {
        0
    }
}
