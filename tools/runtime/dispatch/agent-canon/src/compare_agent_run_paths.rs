// @dependency-start
// contract implementation
// responsibility Compares two workflow-monitoring run paths and emits route-efficiency feedback.
// upstream design ../../../../agents/skills/adaptive-improvement-loop.md owns rerun comparison meaning
// upstream design ../../../../templates/agents/workflow_monitoring.md records path events
// upstream implementation path_resolution.rs owns non-strict physical run-path resolution
// downstream implementation main.rs exposes the compare-agent-run-paths command
// downstream test ../tests/compare_agent_run_paths_native.rs freezes the Python CLI oracle
// @dependency-end

use crate::path_resolution::resolve_non_strict;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

const INEFFICIENT_VALUES: &[&str] = &["inefficient", "wasteful", "avoidable", "slow_path"];
const MONITORING_FILE: &str = "workflow_monitoring.md";
const REPORT_OWNER: &str =
    "../../tools/runtime/dispatch/agent-canon/src/compare_agent_run_paths.rs";
const HELP: &str = "usage: compare-agent-run-paths [-h] --baseline-run BASELINE_RUN --candidate-run CANDIDATE_RUN [--report-out REPORT_OUT]\n\nCompare two run bundle execution paths.\n\noptions:\n  -h, --help            show this help message and exit\n  --baseline-run BASELINE_RUN\n                        Baseline run bundle.\n  --candidate-run CANDIDATE_RUN\n                        Candidate run bundle.\n  --report-out REPORT_OUT\n                        Optional Markdown report path for the comparison.\n";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RunPath {
    pub label: String,
    pub path: PathBuf,
    pub execution_path: String,
    pub route_efficiency: String,
    pub static_analysis_feedback: String,
}

impl RunPath {
    pub fn inefficient(&self) -> bool {
        INEFFICIENT_VALUES.contains(&self.route_efficiency.as_str())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RunPathComparison {
    pub baseline: RunPath,
    pub candidate: RunPath,
}

impl RunPathComparison {
    pub fn paths_differ(&self) -> bool {
        (!self.baseline.execution_path.is_empty() || !self.candidate.execution_path.is_empty())
            && self.baseline.execution_path != self.candidate.execution_path
    }

    pub fn status(&self) -> &'static str {
        if self.candidate.inefficient() {
            "fail"
        } else {
            "pass"
        }
    }

    pub fn next_action(&self) -> &'static str {
        if self.candidate.inefficient() {
            "repair_skill_workflow_prompt"
        } else if self.candidate.static_analysis_feedback.is_empty() {
            "record_static_analysis_feedback"
        } else {
            "record_comparison_and_continue"
        }
    }

    pub fn exit_code(&self) -> i32 {
        if self.candidate.inefficient() {
            1
        } else {
            0
        }
    }
}

/// Compare two run bundles after resolving their paths with non-strict semantics.
pub fn compare_agent_run_paths(
    baseline_run: &Path,
    candidate_run: &Path,
) -> io::Result<RunPathComparison> {
    let baseline_path = resolve_non_strict(baseline_run).map_err(io::Error::other)?;
    let baseline = read_run_path("baseline", baseline_path)?;
    let candidate_path = resolve_non_strict(candidate_run).map_err(io::Error::other)?;
    let candidate = read_run_path("candidate", candidate_path)?;
    Ok(RunPathComparison {
        baseline,
        candidate,
    })
}

fn read_run_path(label: &str, run_dir: PathBuf) -> io::Result<RunPath> {
    let monitoring_path = run_dir.join(MONITORING_FILE);
    let source = match fs::metadata(&monitoring_path) {
        Ok(metadata) if metadata.is_file() => fs::read_to_string(&monitoring_path)?,
        Ok(_) => String::new(),
        Err(error)
            if matches!(
                error.kind(),
                io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
            ) =>
        {
            String::new()
        }
        Err(error) => return Err(error),
    };
    let lowered = source.to_lowercase();
    Ok(RunPath {
        label: label.to_owned(),
        path: run_dir,
        execution_path: first_match(&lowered, "execution_path="),
        route_efficiency: first_match(&lowered, "route_efficiency="),
        static_analysis_feedback: first_match(&lowered, "static_analysis_feedback="),
    })
}

fn python_word_character(character: char) -> bool {
    character.is_alphanumeric() || character == '_'
}

fn token_character(character: char) -> bool {
    character.is_ascii_alphanumeric() || matches!(character, '_' | '.' | ':' | '-')
}

fn first_match(text: &str, key: &str) -> String {
    for (index, _) in text.match_indices(key) {
        if text[..index]
            .chars()
            .next_back()
            .is_some_and(python_word_character)
        {
            continue;
        }
        let capture_start = index + key.len();
        let capture = text[capture_start..]
            .chars()
            .take_while(|character| token_character(*character))
            .collect::<String>();
        if !capture.is_empty() {
            return capture.trim().to_lowercase();
        }
    }
    String::new()
}

/// Render the deterministic Markdown comparison report.
pub fn render_report(comparison: &RunPathComparison) -> String {
    let baseline = &comparison.baseline;
    let candidate = &comparison.candidate;
    let selected = candidate;
    let status = comparison.status();
    let lines = [
        "# Agent Run Path Comparison".to_owned(),
        "<!--".to_owned(),
        "@dependency-start".to_owned(),
        "responsibility Records two-run execution path comparison evidence.".to_owned(),
        format!("upstream implementation {REPORT_OWNER} generates this report"),
        "@dependency-end".to_owned(),
        "-->".to_owned(),
        "".to_owned(),
        "## Summary".to_owned(),
        "".to_owned(),
        format!("- comparison_status: {status}"),
        format!(
            "- paths_differ: {}",
            if comparison.paths_differ() {
                "yes"
            } else {
                "no"
            }
        ),
        format!(
            "- selected_execution_path: {}",
            if selected.execution_path.is_empty() {
                "unknown"
            } else {
                &selected.execution_path
            }
        ),
        format!(
            "- selected_route_efficiency: {}",
            if selected.route_efficiency.is_empty() {
                "unknown"
            } else {
                &selected.route_efficiency
            }
        ),
        "".to_owned(),
        "## Runs".to_owned(),
        "".to_owned(),
        "| Label | Run Directory | execution_path | route_efficiency | static_analysis_feedback |"
            .to_owned(),
        "| ----- | ------------- | -------------- | ---------------- | ------------------------ |"
            .to_owned(),
        run_row(baseline),
        run_row(candidate),
        "".to_owned(),
        "## Workflow Monitoring Tokens".to_owned(),
        "".to_owned(),
        format!("- execution_path_comparison={status}"),
        format!(
            "- selected_inefficient_route={}",
            if selected.inefficient() { "yes" } else { "no" }
        ),
        format!(
            "- route_efficiency={}",
            if selected.route_efficiency.is_empty() {
                "unknown"
            } else {
                &selected.route_efficiency
            }
        ),
        if selected.static_analysis_feedback.is_empty() {
            "- static_analysis_feedback=missing".to_owned()
        } else {
            format!(
                "- static_analysis_feedback={}",
                selected.static_analysis_feedback
            )
        },
        "".to_owned(),
    ];
    lines.join("\n")
}

fn run_row(path: &RunPath) -> String {
    format!(
        "| {} | {} | {} | {} | {} |",
        path.label,
        path.path.display(),
        if path.execution_path.is_empty() {
            "unknown"
        } else {
            &path.execution_path
        },
        if path.route_efficiency.is_empty() {
            "unknown"
        } else {
            &path.route_efficiency
        },
        if path.static_analysis_feedback.is_empty() {
            "missing"
        } else {
            &path.static_analysis_feedback
        }
    )
}

/// Render the machine-readable status lines emitted by the CLI.
pub fn render_machine_status(comparison: &RunPathComparison) -> String {
    let selected = &comparison.candidate;
    format!(
        "RUN_PATH_COMPARISON={}\nRUN_PATHS_DIFFER={}\nBASELINE_EXECUTION_PATH={}\nCANDIDATE_EXECUTION_PATH={}\nSELECTED_ROUTE_EFFICIENCY={}\nSELECTED_INEFFICIENT_ROUTE={}\nSTATIC_ANALYSIS_FEEDBACK={}\nNEXT_ACTION={}\n",
        comparison.status(),
        if comparison.paths_differ() { "yes" } else { "no" },
        if comparison.baseline.execution_path.is_empty() {
            "unknown"
        } else {
            &comparison.baseline.execution_path
        },
        if selected.execution_path.is_empty() {
            "unknown"
        } else {
            &selected.execution_path
        },
        if selected.route_efficiency.is_empty() {
            "unknown"
        } else {
            &selected.route_efficiency
        },
        if selected.inefficient() { "yes" } else { "no" },
        if selected.static_analysis_feedback.is_empty() {
            "missing"
        } else {
            &selected.static_analysis_feedback
        },
        comparison.next_action()
    )
}

#[derive(Clone, Copy)]
enum OptionName {
    BaselineRun,
    CandidateRun,
    ReportOut,
}

struct CliOptions {
    baseline_run: String,
    candidate_run: String,
    report_out: Option<String>,
}

fn option_name(value: &str) -> Result<OptionName, String> {
    const OPTIONS: &[(&str, OptionName)] = &[
        ("--baseline-run", OptionName::BaselineRun),
        ("--candidate-run", OptionName::CandidateRun),
        ("--report-out", OptionName::ReportOut),
    ];
    let matches = OPTIONS
        .iter()
        .filter(|(option, _)| option.starts_with(value))
        .map(|(_, name)| *name)
        .collect::<Vec<_>>();
    match matches.as_slice() {
        [name] => Ok(*name),
        [] => Err(format!("unrecognized argument: {value}")),
        _ => Err(format!("ambiguous option: {value}")),
    }
}

fn parse_arguments(args: &[String]) -> Result<Option<CliOptions>, String> {
    if args
        .iter()
        .any(|arg| matches!(arg.as_str(), "-h" | "--help"))
    {
        return Ok(None);
    }
    let mut baseline_run = None;
    let mut candidate_run = None;
    let mut report_out = None;
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        let (option, inline_value) = argument
            .split_once('=')
            .map_or((argument.as_str(), None), |(option, value)| {
                (option, Some(value.to_owned()))
            });
        if !option.starts_with("--") {
            return Err(format!("unrecognized argument: {argument}"));
        }
        let name = option_name(option)?;
        let value = match inline_value {
            Some(value) => value,
            None => {
                index += 1;
                let Some(value) = args.get(index) else {
                    return Err(format!("argument {option}: expected one argument"));
                };
                if value.starts_with("--") {
                    return Err(format!("argument {option}: expected one argument"));
                }
                value.clone()
            }
        };
        match name {
            OptionName::BaselineRun => baseline_run = Some(value),
            OptionName::CandidateRun => candidate_run = Some(value),
            OptionName::ReportOut => report_out = Some(value),
        }
        index += 1;
    }
    let baseline_run = baseline_run
        .ok_or_else(|| "the following arguments are required: --baseline-run".to_owned())?;
    let candidate_run = candidate_run
        .ok_or_else(|| "the following arguments are required: --candidate-run".to_owned())?;
    Ok(Some(CliOptions {
        baseline_run,
        candidate_run,
        report_out,
    }))
}

fn usage_error(message: &str) -> i32 {
    eprintln!("{HELP}compare-agent-run-paths: error: {message}");
    2
}

/// Run the `compare-agent-run-paths` command with argparse-compatible option prefixes.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_arguments(args) {
        Ok(None) => {
            print!("{HELP}");
            return 0;
        }
        Ok(Some(options)) => options,
        Err(error) => return usage_error(&error),
    };
    let comparison = match compare_agent_run_paths(
        Path::new(&options.baseline_run),
        Path::new(&options.candidate_run),
    ) {
        Ok(comparison) => comparison,
        Err(error) => {
            eprintln!("compare-agent-run-paths: {error}");
            return 1;
        }
    };
    if let Some(report_path) = options.report_out {
        let report_path = PathBuf::from(report_path);
        if let Some(parent) = report_path.parent() {
            let parent = if parent.as_os_str().is_empty() {
                Path::new(".")
            } else {
                parent
            };
            if let Err(error) = fs::create_dir_all(parent) {
                eprintln!("compare-agent-run-paths: {error}");
                return 1;
            }
        }
        if let Err(error) = fs::write(&report_path, render_report(&comparison)) {
            eprintln!("compare-agent-run-paths: {error}");
            return 1;
        }
    }
    print!("{}", render_machine_status(&comparison));
    comparison.exit_code()
}
