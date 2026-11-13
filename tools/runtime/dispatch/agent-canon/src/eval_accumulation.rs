// @dependency-start
// contract implementation
// responsibility Runs the registered native Eval producers and captures bounded output under the external runtime owner.
// upstream implementation ./runtime_boundary.rs validates runtime output paths and propagates root capabilities
// upstream design ../../../../../eval/definitions/README.md owns the Eval family and accumulation contract
// upstream implementation ./codex_agent_role_eval/mod.rs owns the Codex role Eval producer
// upstream implementation ./workflow_selection_eval.rs owns the workflow selection Eval producer
// downstream test ../../../../../tests/agent_tools/test_run_accumulated_agent_evals.py checks the native Shell route and capture semantics
// @dependency-end

use crate::path_resolution::resolve_non_strict;
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::runtime_boundary::{root_capability_environment, RuntimeArtifactBoundary};
use std::collections::BTreeMap;
use std::ffi::OsString;
use std::io;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

pub const SELECTOR: &str = "run-accumulated-agent-evals";
pub const PRODUCER_SELECTORS: &[(&str, &str)] = &[
    ("codex-agent-role", "evaluate-codex-agent-roles"),
    ("workflow-selection", "evaluate-workflow-selection"),
];
const DEFAULT_RUN_ID: &str = "agent-canon-accumulated-eval";
const USAGE: &str = "usage: agent-canon run-accumulated-agent-evals [--root ROOT] [--target-root ROOT] [--runtime-root ROOT] [--run-id RUN_ID] [--log-dir DIR]";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum OptionName {
    Help,
    Root,
    TargetRoot,
    RuntimeRoot,
    RunId,
    LogDir,
}

const OPTIONS: &[(&str, OptionName)] = &[
    ("--help", OptionName::Help),
    ("--root", OptionName::Root),
    ("--target-root", OptionName::TargetRoot),
    ("--runtime-root", OptionName::RuntimeRoot),
    ("--run-id", OptionName::RunId),
    ("--log-dir", OptionName::LogDir),
];

#[derive(Clone, Debug, Eq, PartialEq)]
struct Options {
    root: PathBuf,
    target_root: Option<PathBuf>,
    runtime_root: Option<PathBuf>,
    run_id: String,
    log_dir: Option<PathBuf>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Producer {
    name: &'static str,
    command: Vec<OsString>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ProducerResult {
    name: &'static str,
    returncode: i32,
    stdout_log: PathBuf,
    stderr_log: PathBuf,
}

/// Run both registered Eval producers, preserving their exit status and captured output.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_args(args) {
        Ok(None) => {
            println!("{USAGE}\n\nRun the native role and workflow Eval producers and capture their output in the external runtime root.");
            return 0;
        }
        Ok(Some(options)) => options,
        Err(error) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    match run_with(&options, &mut execute_producer) {
        Ok((results, rendered)) => {
            print!("{rendered}");
            if results.iter().any(|result| result.returncode != 0) {
                1
            } else {
                0
            }
        }
        Err(error) => {
            eprintln!("{SELECTOR}: {error}");
            2
        }
    }
}

fn parse_args(args: &[String]) -> Result<Option<Options>, String> {
    let mut root = None;
    let mut target_root = None;
    let mut runtime_root = None;
    let mut run_id = DEFAULT_RUN_ID.to_owned();
    let mut log_dir = None;
    let mut index = 0;
    while index < args.len() {
        let argument = args[index].as_str();
        if argument == "-h" {
            return Ok(None);
        }
        let (option, inline_value) = argument
            .split_once('=')
            .map_or((argument, None), |(option, value)| (option, Some(value)));
        let selected =
            resolve_long_option_prefix(option, OPTIONS).map_err(|error| match error {
                LongOptionError::Unrecognized => format!("unrecognized arguments: {argument}"),
                LongOptionError::Ambiguous(matches) => format!(
                    "ambiguous option: {option} could match {}",
                    matches.join(", ")
                ),
            })?;
        if selected == OptionName::Help {
            return Ok(None);
        }
        let value = if let Some(value) = inline_value {
            value
        } else {
            index += 1;
            args.get(index)
                .ok_or_else(|| format!("argument {option}: expected one argument"))?
                .as_str()
        };
        match selected {
            OptionName::Help => return Ok(None),
            OptionName::Root => root = Some(PathBuf::from(value)),
            OptionName::TargetRoot => target_root = Some(PathBuf::from(value)),
            OptionName::RuntimeRoot => runtime_root = Some(PathBuf::from(value)),
            OptionName::RunId => run_id = value.to_owned(),
            OptionName::LogDir => log_dir = Some(PathBuf::from(value)),
        }
        index += 1;
    }
    let raw_root = match root {
        Some(root) => root,
        None => std::env::current_dir()
            .map_err(|error| format!("resolve current directory: {error}"))?,
    };
    Ok(Some(Options {
        root: resolve_non_strict(&raw_root)?,
        target_root: target_root
            .map(|path| resolve_non_strict(&path))
            .transpose()?,
        runtime_root,
        run_id,
        log_dir,
    }))
}

fn safe_slug(value: &str) -> String {
    let mut slug = String::new();
    let mut separator = false;
    for character in value.chars() {
        if character.is_ascii_alphanumeric() || matches!(character, '_' | '.' | '-') {
            slug.push(character);
            separator = false;
        } else if !separator {
            slug.push('-');
            separator = true;
        }
    }
    let slug = slug.trim_matches(|character| matches!(character, '.' | '_' | '-'));
    if slug.is_empty() {
        "run".to_owned()
    } else {
        slug.to_owned()
    }
}

fn build_producers(root: &Path, run_id: &str, runtime_root: &Path) -> Vec<Producer> {
    let executable = root.join("tools/bin/agent-canon");
    let command = |selector: &str| {
        vec![
            executable.as_os_str().to_owned(),
            OsString::from(selector),
            OsString::from("--root"),
            root.as_os_str().to_owned(),
            OsString::from("--accumulate"),
            OsString::from("--run-id"),
            OsString::from(run_id),
            OsString::from("--runtime-root"),
            runtime_root.as_os_str().to_owned(),
        ]
    };
    PRODUCER_SELECTORS
        .iter()
        .map(|&(name, selector)| Producer {
            name,
            command: command(selector),
        })
        .collect()
}

fn run_with(
    options: &Options,
    runner: &mut impl FnMut(&Producer, &Path, &BTreeMap<String, String>) -> io::Result<Output>,
) -> Result<(Vec<ProducerResult>, String), String> {
    let boundary =
        RuntimeArtifactBoundary::for_source(&options.root, options.runtime_root.as_deref(), false)?;
    let log_dir = match &options.log_dir {
        Some(path) => boundary.resolve(path)?,
        None => boundary.resolve(
            &PathBuf::from("tasks")
                .join(safe_slug(&options.run_id))
                .join("logs"),
        )?,
    };
    let relative_log_dir = log_dir.strip_prefix(boundary.root()).map_err(|_| {
        format!(
            "log directory is outside runtime root: {}",
            log_dir.display()
        )
    })?;
    boundary.ensure_directory(relative_log_dir)?;
    let target_root = options.target_root.as_deref().unwrap_or(&options.root);
    let child_environment =
        root_capability_environment(&options.root, boundary.root(), None, Some(target_root))?;
    let producers = build_producers(&options.root, &options.run_id, boundary.root());
    let mut results = Vec::with_capacity(producers.len());
    for (index, producer) in producers.iter().enumerate() {
        let output = runner(producer, &options.root, &child_environment)
            .map_err(|error| format!("run {}: {error}", producer.name))?;
        let stdout = String::from_utf8(output.stdout)
            .map_err(|error| format!("{} stdout is not valid UTF-8: {error}", producer.name))?;
        let stderr = String::from_utf8(output.stderr)
            .map_err(|error| format!("{} stderr is not valid UTF-8: {error}", producer.name))?;
        let prefix = format!("{:02}-{}", index + 1, safe_slug(producer.name));
        let stdout_log = log_dir.join(format!("{prefix}.stdout.txt"));
        let stderr_log = log_dir.join(format!("{prefix}.stderr.txt"));
        boundary.atomic_write_text(
            stdout_log.strip_prefix(boundary.root()).map_err(|_| {
                format!(
                    "stdout log is outside runtime root: {}",
                    stdout_log.display()
                )
            })?,
            &stdout,
            0o600,
        )?;
        boundary.atomic_write_text(
            stderr_log.strip_prefix(boundary.root()).map_err(|_| {
                format!(
                    "stderr log is outside runtime root: {}",
                    stderr_log.display()
                )
            })?,
            &stderr,
            0o600,
        )?;
        results.push(ProducerResult {
            name: producer.name,
            returncode: output.status.code().unwrap_or(128),
            stdout_log,
            stderr_log,
        });
    }
    let rendered = render_results(&options.root, &results);
    Ok((results, rendered))
}

fn execute_producer(
    producer: &Producer,
    cwd: &Path,
    environment: &BTreeMap<String, String>,
) -> io::Result<Output> {
    let (program, args) = producer
        .command
        .split_first()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "producer command is empty"))?;
    Command::new(program)
        .args(args)
        .current_dir(cwd)
        .env_clear()
        .envs(environment)
        .output()
}

fn relative(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn render_results(root: &Path, results: &[ProducerResult]) -> String {
    let mut lines = Vec::new();
    for result in results {
        let status = if result.returncode == 0 {
            "pass"
        } else {
            "fail"
        };
        lines.push(format!(
            "ACCUMULATED_AGENT_EVAL_PRODUCER={}:{}:stdout={}:stderr={}",
            result.name,
            status,
            relative(root, &result.stdout_log),
            relative(root, &result.stderr_log),
        ));
    }
    let failed = results
        .iter()
        .filter(|result| result.returncode != 0)
        .map(|result| result.name)
        .collect::<Vec<_>>();
    lines.push(format!(
        "ACCUMULATED_AGENT_EVAL_PRODUCERS={}",
        results.len()
    ));
    lines.push(format!(
        "ACCUMULATED_AGENT_EVAL_FAILED={}",
        if failed.is_empty() {
            "-".to_owned()
        } else {
            failed.join(",")
        }
    ));
    lines.push(format!(
        "ACCUMULATED_AGENT_EVAL={}",
        if failed.is_empty() { "pass" } else { "fail" }
    ));
    format!("{}\n", lines.join("\n"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn producer_commands_preserve_registered_native_families_and_archive_ownership() {
        let root = Path::new("/source");
        let runtime = Path::new("/runtime");
        let producers = build_producers(root, "run-123", runtime);
        assert_eq!(
            producers
                .iter()
                .map(|producer| producer.name)
                .collect::<Vec<_>>(),
            ["codex-agent-role", "workflow-selection"]
        );
        for producer in &producers {
            assert!(producer
                .command
                .iter()
                .any(|argument| argument == "--accumulate"));
            assert!(!producer
                .command
                .iter()
                .any(|argument| argument == "--results-dir"));
            assert!(producer
                .command
                .iter()
                .any(|argument| argument == "/runtime"));
        }
        assert!(producers[1]
            .command
            .iter()
            .any(|argument| argument == "run-123"));
    }

    #[test]
    fn slug_and_result_lines_match_the_python_collector_contract() {
        assert_eq!(safe_slug("run / 日本語"), "run");
        assert_eq!(safe_slug("._--"), "run");
        let results = [
            ProducerResult {
                name: "ok-family",
                returncode: 0,
                stdout_log: PathBuf::from("/runtime/logs/01-ok.stdout.txt"),
                stderr_log: PathBuf::from("/runtime/logs/01-ok.stderr.txt"),
            },
            ProducerResult {
                name: "bad-family",
                returncode: 1,
                stdout_log: PathBuf::from("/runtime/logs/02-bad.stdout.txt"),
                stderr_log: PathBuf::from("/runtime/logs/02-bad.stderr.txt"),
            },
        ];
        assert_eq!(
            render_results(Path::new("/source"), &results),
            concat!(
                "ACCUMULATED_AGENT_EVAL_PRODUCER=ok-family:pass:stdout=/runtime/logs/01-ok.stdout.txt:stderr=/runtime/logs/01-ok.stderr.txt\n",
                "ACCUMULATED_AGENT_EVAL_PRODUCER=bad-family:fail:stdout=/runtime/logs/02-bad.stdout.txt:stderr=/runtime/logs/02-bad.stderr.txt\n",
                "ACCUMULATED_AGENT_EVAL_PRODUCERS=2\n",
                "ACCUMULATED_AGENT_EVAL_FAILED=bad-family\n",
                "ACCUMULATED_AGENT_EVAL=fail\n"
            )
        );
    }

    #[test]
    fn child_environment_keeps_parent_target_and_runtime_roots_distinct() {
        let temporary = tempfile::tempdir().expect("root capability fixture creates");
        let source = temporary.path().join("source");
        let target = temporary.path().join("target");
        let runtime = temporary.path().join("runtime");
        std::fs::create_dir_all(&source).expect("source root creates");
        std::fs::create_dir_all(&target).expect("target root creates");
        std::fs::create_dir_all(&runtime).expect("runtime root creates");
        let boundary = RuntimeArtifactBoundary::for_source(&source, Some(&runtime), false)
            .expect("external runtime root resolves");
        let environment = root_capability_environment(
            &source,
            boundary.root(),
            Some(&BTreeMap::new()),
            Some(&target),
        )
        .expect("typed roots are propagated");
        assert_eq!(
            environment.get("AGENT_CANON_PARENT_ROOT"),
            Some(&source.canonicalize().unwrap().display().to_string())
        );
        assert_eq!(
            environment.get("AGENT_CANON_TARGET_ROOT"),
            Some(&target.canonicalize().unwrap().display().to_string())
        );
        assert_eq!(
            environment.get("AGENT_CANON_RUNTIME_ROOT"),
            Some(&runtime.canonicalize().unwrap().display().to_string())
        );
        let parent_capability: serde_json::Value = serde_json::from_str(
            environment
                .get("AGENT_CANON_PARENT_ROOT_CAPABILITY")
                .expect("parent capability is propagated"),
        )
        .expect("parent capability is JSON");
        assert_eq!(parent_capability["kind"], "parent-root");
        let target_capability: serde_json::Value = serde_json::from_str(
            environment
                .get("AGENT_CANON_TARGET_ROOT_CAPABILITY")
                .expect("target capability is propagated"),
        )
        .expect("target capability is JSON");
        assert_eq!(target_capability["kind"], "target-root");
    }
}
