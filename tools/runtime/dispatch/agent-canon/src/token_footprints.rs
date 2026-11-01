// @dependency-start
// contract implementation
// responsibility Compares Codex session token footprints and records run-bundle evidence.
// upstream design ../../../../../agents/skills/tokens.md defines the token comparison protocol
// upstream implementation python_cli_integer.rs parses Python-compatible integer options
// upstream implementation python_cli_options.rs resolves Python argparse option prefixes
// upstream implementation python_json.rs preserves Python JSON values and float formatting
// upstream implementation python_text.rs preserves Python-compatible whitespace and line splitting
// upstream implementation path_resolution.rs preserves non-strict resolved paths
// upstream implementation source_dependency_graph.rs supplies Python-compatible component matching
// upstream implementation hook_report_projection.rs appends optional run-local monitoring evidence
// downstream implementation main.rs exposes the token footprint CLI
// downstream implementation ../../../../../eval/producers/generate_agent_runtime_dashboard.py records the native command
// downstream implementation ../../../../../tests/agent_tools/test_compare_codex_token_footprints.py preserves the CLI scenarios
// @dependency-end

use crate::python_cli_integer;
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::python_text::{python_splitlines, python_strip};
use agent_canon::hook_report_projection::append_monitoring_projection;
use agent_canon::path_resolution::resolve_non_strict;
use agent_canon::python_json::{parse_json, JsonNumber, JsonValue};
use rustpython_ast::bigint::BigInt;
use rustpython_literal::format::Case as FloatFormatCase;
use std::collections::{BTreeMap, HashSet};
use std::env;
use std::fs;
use std::io;
use std::path::{Component, Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

const TARGET_RATIO: f64 = 0.5;
const DEFAULT_MOVING_AVERAGE_WINDOW: i64 = 5;
const SECONDS_PER_DAY: i64 = 24 * 60 * 60;
const REPORT_OWNER: &str = "../../tools/runtime/dispatch/agent-canon/src/token_footprints.rs";
const HELP: &str = "usage: compare_codex_token_footprints.py [-h] [--baseline-session BASELINE_SESSION]\n                                               [--candidate-session CANDIDATE_SESSION]\n                                               [--session-glob SESSION_GLOB]\n                                               [--moving-average-window MOVING_AVERAGE_WINDOW]\n                                               [--recent-days RECENT_DAYS]\n                                               [--report-out REPORT_OUT]\n                                               [--report-dir REPORT_DIR]\n\nCompare or summarize Codex session token footprints.\n\noptions:\n  -h, --help            show this help message and exit\n  --baseline-session BASELINE_SESSION\n                        Baseline Codex session JSONL file.\n  --candidate-session CANDIDATE_SESSION\n                        Candidate Codex session JSONL file.\n  --session-glob SESSION_GLOB\n                        Session JSONL glob for summary mode. May be repeated.\n                        When set, the tool emits token usage moving-average\n                        evidence.\n  --moving-average-window MOVING_AVERAGE_WINDOW\n                        Session window size for token summary moving averages.\n  --recent-days RECENT_DAYS\n                        Only include session files modified within this many\n                        days in summary mode. Uses file mtime so long-running\n                        sessions stay visible.\n  --report-out REPORT_OUT\n                        Optional Markdown report path for the comparison or\n                        summary.\n  --report-dir REPORT_DIR\n                        Optional run bundle directory to append monitoring\n                        evidence.\n";

#[derive(Clone, Debug, Eq, PartialEq)]
struct TokenFootprint {
    session_file: PathBuf,
    input_tokens: BigInt,
    cached_input_tokens: BigInt,
    output_tokens: BigInt,
    reasoning_output_tokens: BigInt,
    total_tokens: BigInt,
    token_event_count: BigInt,
}

#[derive(Clone, Copy)]
enum OptionName {
    Help,
    BaselineSession,
    CandidateSession,
    SessionGlob,
    MovingAverageWindow,
    RecentDays,
    ReportOut,
    ReportDir,
}

struct CliOptions {
    baseline_session: Option<String>,
    candidate_session: Option<String>,
    session_globs: Vec<String>,
    moving_average_window: BigInt,
    recent_days: Option<BigInt>,
    report_out: Option<String>,
    report_dir: Option<String>,
}

impl Default for CliOptions {
    fn default() -> Self {
        Self {
            baseline_session: None,
            candidate_session: None,
            session_globs: Vec::new(),
            moving_average_window: BigInt::from(DEFAULT_MOVING_AVERAGE_WINDOW),
            recent_days: None,
            report_out: None,
            report_dir: None,
        }
    }
}

enum SessionError {
    Value(String),
    Io(String),
}

impl SessionError {
    fn message(&self) -> &str {
        match self {
            Self::Value(message) | Self::Io(message) => message,
        }
    }
}

/// Run the native token-footprint command and return its process exit code.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_arguments(args) {
        Ok(None) => {
            print!("{HELP}");
            return 0;
        }
        Ok(Some(options)) => options,
        Err(error) => return usage_error(&error),
    };

    if !options.session_globs.is_empty() {
        return run_summary(options);
    }
    let (Some(baseline), Some(candidate)) = (
        options.baseline_session.as_deref(),
        options.candidate_session.as_deref(),
    ) else {
        eprintln!(
            "--baseline-session and --candidate-session are required unless --session-glob is set"
        );
        return 1;
    };

    let baseline_path = match resolve_non_strict(Path::new(baseline)) {
        Ok(path) => path,
        Err(error) => return command_error(error),
    };
    let candidate_path = match resolve_non_strict(Path::new(candidate)) {
        Ok(path) => path,
        Err(error) => return command_error(error),
    };
    let baseline = match parse_token_usage(&baseline_path) {
        Ok(footprint) => footprint,
        Err(error) => return command_error(error.message().to_owned()),
    };
    let candidate = match parse_token_usage(&candidate_path) {
        Ok(footprint) => footprint,
        Err(error) => return command_error(error.message().to_owned()),
    };
    let (value, status) = if let Some(report_path) = options.report_out.as_deref() {
        if let Err(error) = prepare_report_parent(Path::new(report_path)) {
            return command_error(error);
        }
        let value = match ratio(&candidate.total_tokens, &baseline.total_tokens) {
            Ok(value) => value,
            Err(error) => return command_error(error),
        };
        let status = comparison_status(value);
        let report = render_report(&baseline, &candidate, value, status);
        if let Err(error) = write_report(Path::new(report_path), &report) {
            return command_error(error);
        }
        (value, status)
    } else {
        let value = match ratio(&candidate.total_tokens, &baseline.total_tokens) {
            Ok(value) => value,
            Err(error) => return command_error(error),
        };
        (value, comparison_status(value))
    };
    if let Some(report_dir) = options.report_dir.as_deref() {
        let report_dir = match resolve_non_strict(Path::new(report_dir)) {
            Ok(path) => path,
            Err(error) => return command_error(error),
        };
        if let Err(error) =
            append_comparison_report_dir(&report_dir, &baseline, &candidate, value, status)
        {
            return command_error(error);
        }
    }
    print!(
        "{}",
        comparison_status_text(&baseline, &candidate, value, status)
    );
    if status == "fail" {
        1
    } else {
        0
    }
}

fn run_summary(options: CliOptions) -> i32 {
    let footprints = match read_session_globs(&options.session_globs, options.recent_days.as_ref())
    {
        Ok(footprints) => footprints,
        Err(error) => return command_error(error),
    };
    if let Some(report_path) = options.report_out.as_deref() {
        if let Err(error) = prepare_report_parent(Path::new(report_path)) {
            return command_error(error);
        }
        let report = match render_summary_report(
            &footprints,
            &options.moving_average_window,
            options.recent_days.as_ref(),
        ) {
            Ok(report) => report,
            Err(error) => return command_error(error),
        };
        if let Err(error) = write_report(Path::new(report_path), &report) {
            return command_error(error);
        }
    }
    if let Some(report_dir) = options.report_dir.as_deref() {
        let report_dir = match resolve_non_strict(Path::new(report_dir)) {
            Ok(path) => path,
            Err(error) => return command_error(error),
        };
        if let Err(error) = append_summary_report_dir(
            &report_dir,
            &footprints,
            &options.moving_average_window,
            options.recent_days.as_ref(),
        ) {
            return command_error(error);
        }
    }
    let status = match summary_status_text(
        &footprints,
        &options.moving_average_window,
        options.recent_days.as_ref(),
    ) {
        Ok(status) => status,
        Err(error) => return command_error(error),
    };
    print!("{status}");
    0
}

fn parse_arguments(args: &[String]) -> Result<Option<CliOptions>, String> {
    const OPTIONS: &[(&str, OptionName)] = &[
        ("--help", OptionName::Help),
        ("--baseline-session", OptionName::BaselineSession),
        ("--candidate-session", OptionName::CandidateSession),
        ("--session-glob", OptionName::SessionGlob),
        ("--moving-average-window", OptionName::MovingAverageWindow),
        ("--recent-days", OptionName::RecentDays),
        ("--report-out", OptionName::ReportOut),
        ("--report-dir", OptionName::ReportDir),
    ];

    let mut options = CliOptions::default();
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if argument == "-h" {
            return Ok(None);
        }
        if let Some(value) = argument.strip_prefix("-h=") {
            return Err(format!(
                "argument -h/--help: ignored explicit argument '{value}'"
            ));
        }
        let (option, inline_value) = argument
            .split_once('=')
            .map_or((argument.as_str(), None), |(option, value)| {
                (option, Some(value.to_owned()))
            });
        if !option.starts_with("--") {
            return Err(format!("unrecognized arguments: {argument}"));
        }
        let name = resolve_long_option_prefix(option, OPTIONS).map_err(|error| match error {
            LongOptionError::Unrecognized => format!("unrecognized arguments: {option}"),
            LongOptionError::Ambiguous(options) => format!(
                "ambiguous option: {option} could match {}",
                options.join(", ")
            ),
        })?;
        if matches!(name, OptionName::Help) {
            return match inline_value {
                Some(value) => Err(format!(
                    "argument -h/--help: ignored explicit argument '{value}'"
                )),
                None => Ok(None),
            };
        }
        let value = match inline_value {
            Some(value) => value,
            None => {
                index += 1;
                let Some(value) = args.get(index) else {
                    return Err(format!("argument {option}: expected one argument"));
                };
                if value.starts_with("--") || value == "-h" {
                    return Err(format!("argument {option}: expected one argument"));
                }
                value.clone()
            }
        };
        match name {
            OptionName::Help => unreachable!("help option returns before assigning a value"),
            OptionName::BaselineSession => options.baseline_session = Some(value),
            OptionName::CandidateSession => options.candidate_session = Some(value),
            OptionName::SessionGlob => options.session_globs.push(value),
            OptionName::MovingAverageWindow => {
                options.moving_average_window = parse_integer_option(option, &value)?;
            }
            OptionName::RecentDays => {
                options.recent_days = Some(parse_integer_option(option, &value)?);
            }
            OptionName::ReportOut => options.report_out = Some(value),
            OptionName::ReportDir => options.report_dir = Some(value),
        }
        index += 1;
    }
    Ok(Some(options))
}

fn parse_integer_option(option: &str, value: &str) -> Result<BigInt, String> {
    python_cli_integer::parse(value)
        .ok_or_else(|| format!("argument {option}: invalid int value: '{value}'"))
}

fn usage_error(message: &str) -> i32 {
    eprintln!("{HELP}compare_codex_token_footprints.py: error: {message}");
    2
}

fn command_error(message: String) -> i32 {
    eprintln!("compare-codex-token-footprints: {message}");
    1
}

fn parse_token_usage(session_file: &Path) -> Result<TokenFootprint, SessionError> {
    if !session_file.is_file() {
        return Err(SessionError::Io(format!(
            "session file not found: {}",
            session_file.display()
        )));
    }
    let source = fs::read_to_string(session_file).map_err(|error| {
        let message = format!("cannot read {}: {error}", session_file.display());
        if error.kind() == io::ErrorKind::InvalidData {
            SessionError::Value(message)
        } else {
            SessionError::Io(message)
        }
    })?;
    let mut last = None;
    let mut token_event_count = BigInt::from(0_u8);
    for raw_line in python_splitlines(&source) {
        let line = python_strip(raw_line);
        if line.is_empty() {
            continue;
        }
        let loaded = parse_json(line).map_err(SessionError::Value)?;
        if !object_member(&loaded, "type").is_some_and(|value| string_equals(value, "event_msg")) {
            continue;
        }
        let Some(payload) = object_member(&loaded, "payload") else {
            continue;
        };
        if !object_member(payload, "type").is_some_and(|value| string_equals(value, "token_count"))
        {
            continue;
        }
        let Some(info) = object_member(payload, "info") else {
            continue;
        };
        let Some(total_usage) = object_member(info, "total_token_usage") else {
            continue;
        };
        if !matches!(total_usage, JsonValue::Object(_)) {
            continue;
        }
        token_event_count += BigInt::from(1_u8);
        last = Some(TokenUsage {
            input_tokens: token_int(object_member(total_usage, "input_tokens"))
                .map_err(SessionError::Value)?,
            cached_input_tokens: token_int(object_member(total_usage, "cached_input_tokens"))
                .map_err(SessionError::Value)?,
            output_tokens: token_int(object_member(total_usage, "output_tokens"))
                .map_err(SessionError::Value)?,
            reasoning_output_tokens: token_int(object_member(
                total_usage,
                "reasoning_output_tokens",
            ))
            .map_err(SessionError::Value)?,
            total_tokens: token_int(object_member(total_usage, "total_tokens"))
                .map_err(SessionError::Value)?,
        });
    }
    let Some(last) = last else {
        return Err(SessionError::Value(format!(
            "no token_count event found in {}",
            session_file.display()
        )));
    };
    Ok(TokenFootprint {
        session_file: session_file.to_path_buf(),
        input_tokens: last.input_tokens,
        cached_input_tokens: last.cached_input_tokens,
        output_tokens: last.output_tokens,
        reasoning_output_tokens: last.reasoning_output_tokens,
        total_tokens: last.total_tokens,
        token_event_count,
    })
}

struct TokenUsage {
    input_tokens: BigInt,
    cached_input_tokens: BigInt,
    output_tokens: BigInt,
    reasoning_output_tokens: BigInt,
    total_tokens: BigInt,
}

fn object_member<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(object) = value else {
        return None;
    };
    object
        .0
        .iter()
        .find_map(|(candidate, value)| candidate.equals_text(key).then_some(value))
}

fn string_equals(value: &JsonValue, expected: &str) -> bool {
    matches!(value, JsonValue::String(value) if value.equals_text(expected))
}

fn token_int(value: Option<&JsonValue>) -> Result<BigInt, String> {
    match value {
        Some(JsonValue::Bool(value)) => Ok(BigInt::from(u8::from(*value))),
        Some(JsonValue::Number(JsonNumber::Integer(value))) => value
            .parse()
            .map_err(|_| "invalid integer token usage value".to_owned()),
        Some(JsonValue::Number(JsonNumber::Float(value))) => {
            float_to_integer(*value).ok_or_else(|| {
                "cannot convert non-finite float token usage value to integer".to_owned()
            })
        }
        _ => Ok(BigInt::from(0_u8)),
    }
}

fn float_to_integer(value: f64) -> Option<BigInt> {
    if !value.is_finite() {
        return None;
    }
    let bits = value.to_bits();
    let negative = bits >> 63 != 0;
    let exponent_bits = ((bits >> 52) & 0x7ff) as i32;
    let fraction = bits & ((1_u64 << 52) - 1);
    let (significand, shift) = if exponent_bits == 0 {
        (fraction, -1074)
    } else {
        ((1_u64 << 52) | fraction, exponent_bits - 1023 - 52)
    };
    if significand == 0 {
        return Some(BigInt::from(0_u8));
    }
    let integer = if shift < 0 {
        let right_shift = (-shift) as u32;
        if right_shift >= u64::BITS {
            BigInt::from(0_u8)
        } else {
            BigInt::from(significand >> right_shift)
        }
    } else {
        BigInt::from(significand) << shift as usize
    };
    Some(if negative { -integer } else { integer })
}

fn ratio(candidate: &BigInt, baseline: &BigInt) -> Result<f64, String> {
    if baseline <= &BigInt::from(0_u8) {
        return Err("baseline total_tokens must be greater than zero".to_owned());
    }
    bigint_ratio(candidate, baseline)
}

fn bigint_ratio(numerator: &BigInt, denominator: &BigInt) -> Result<f64, String> {
    let numerator_float = integer_to_f64(numerator);
    let denominator_float = integer_to_f64(denominator);
    let value = if numerator_float.is_finite() && denominator_float.is_finite() {
        numerator_float / denominator_float
    } else {
        let (numerator_mantissa, numerator_exponent) = decimal_mantissa_exponent(numerator)?;
        let (denominator_mantissa, denominator_exponent) = decimal_mantissa_exponent(denominator)?;
        let exponent = numerator_exponent
            .checked_sub(denominator_exponent)
            .ok_or_else(|| "integer division result too large for a float".to_owned())?;
        (numerator_mantissa / denominator_mantissa) * 10_f64.powi(exponent)
    };
    if value.is_finite() {
        Ok(value)
    } else {
        Err("integer division result too large for a float".to_owned())
    }
}

fn integer_to_f64(value: &BigInt) -> f64 {
    value.to_string().parse().unwrap_or_else(|_| {
        if value < &BigInt::from(0_u8) {
            f64::NEG_INFINITY
        } else {
            f64::INFINITY
        }
    })
}

fn decimal_mantissa_exponent(value: &BigInt) -> Result<(f64, i32), String> {
    let representation = value.to_string();
    let negative = representation.starts_with('-');
    let digits = representation.trim_start_matches('-');
    let count = digits.len();
    let leading = &digits[..count.min(17)];
    let leading = leading
        .parse::<f64>()
        .map_err(|_| "integer division result too large for a float".to_owned())?;
    let precision = i32::try_from(count.min(17) - 1)
        .map_err(|_| "integer division result too large for a float".to_owned())?;
    let exponent = i32::try_from(count - 1)
        .map_err(|_| "integer division result too large for a float".to_owned())?;
    let mantissa = leading / 10_f64.powi(precision);
    Ok((if negative { -mantissa } else { mantissa }, exponent))
}

fn comparison_status(value: f64) -> &'static str {
    if value <= TARGET_RATIO {
        "pass"
    } else {
        "fail"
    }
}

fn fixed(value: f64) -> String {
    rustpython_literal::float::format_fixed(3, value, FloatFormatCase::Lower, false)
}

fn render_report(
    baseline: &TokenFootprint,
    candidate: &TokenFootprint,
    value: f64,
    status: &str,
) -> String {
    let lines = [
        "# Codex Token Footprint Comparison".to_owned(),
        "<!--".to_owned(),
        "@dependency-start".to_owned(),
        "responsibility Records Codex token footprint comparison evidence.".to_owned(),
        format!("upstream implementation {REPORT_OWNER} generates this report"),
        "@dependency-end".to_owned(),
        "-->".to_owned(),
        "".to_owned(),
        "## Summary".to_owned(),
        "".to_owned(),
        format!("- comparison_status: {status}"),
        format!("- baseline_total_tokens: {}", baseline.total_tokens),
        format!("- candidate_total_tokens: {}", candidate.total_tokens),
        format!("- token_ratio: {}", fixed(value)),
        format!("- target_ratio: {}", fixed(TARGET_RATIO)),
        "".to_owned(),
        "## Sessions".to_owned(),
        "".to_owned(),
        "| Label | Session File | input | cached input | output | reasoning output | total |"
            .to_owned(),
        "| ----- | ------------ | ----- | ------------ | ------ | ---------------- | ----- |"
            .to_owned(),
        row("baseline", baseline),
        row("candidate", candidate),
        "".to_owned(),
        "## Machine Status".to_owned(),
        "".to_owned(),
        format!("- TOKEN_FOOTPRINT_COMPARISON={status}"),
        format!("- TOKEN_FOOTPRINT_RATIO={}", fixed(value)),
        format!("- TOKEN_FOOTPRINT_TARGET={}", fixed(TARGET_RATIO)),
        "".to_owned(),
    ];
    lines.join("\n")
}

fn row(label: &str, footprint: &TokenFootprint) -> String {
    format!(
        "| {label} | {} | {} | {} | {} | {} | {} |",
        footprint.session_file.display(),
        footprint.input_tokens,
        footprint.cached_input_tokens,
        footprint.output_tokens,
        footprint.reasoning_output_tokens,
        footprint.total_tokens
    )
}

fn comparison_status_text(
    baseline: &TokenFootprint,
    candidate: &TokenFootprint,
    value: f64,
    status: &str,
) -> String {
    format!(
        "TOKEN_FOOTPRINT_COMPARISON={status}\nTOKEN_FOOTPRINT_BASELINE_TOTAL={}\nTOKEN_FOOTPRINT_CANDIDATE_TOTAL={}\nTOKEN_FOOTPRINT_RATIO={}\nTOKEN_FOOTPRINT_TARGET={}\nTOKEN_FOOTPRINT_BELOW_TARGET={}\nNEXT_ACTION={}\n",
        baseline.total_tokens,
        candidate.total_tokens,
        fixed(value),
        fixed(TARGET_RATIO),
        if value <= TARGET_RATIO { "yes" } else { "no" },
        if status == "pass" {
            "record_token_efficiency_evidence"
        } else {
            "reduce_token_footprint"
        }
    )
}

fn session_glob_paths(
    patterns: &[String],
    recent_days: Option<&BigInt>,
) -> Result<Vec<PathBuf>, String> {
    let mut unique_paths = BTreeMap::<String, PathBuf>::new();
    for pattern in patterns {
        let (base, components, directory_only) = split_glob_pattern(pattern)?;
        let matches = glob_paths(&base, &components, directory_only);
        for path in matches {
            if !fs::metadata(&path).is_ok_and(|metadata| metadata.is_file()) {
                continue;
            }
            let resolved = resolve_non_strict(&path)?;
            let key = path_posix(&resolved);
            let key = if cfg!(windows) {
                key.to_lowercase()
            } else {
                key
            };
            unique_paths.entry(key).or_insert(resolved);
        }
    }
    let mut paths = unique_paths.into_values().collect::<Vec<_>>();
    paths.sort_by_key(|path| path_posix(path));
    if let Some(recent_days) = recent_days {
        let days = if recent_days < &BigInt::from(0_u8) {
            BigInt::from(0_u8)
        } else {
            recent_days.clone()
        };
        let seconds = days * BigInt::from(SECONDS_PER_DAY);
        let seconds = integer_to_f64(&seconds);
        if !seconds.is_finite() {
            return Err("int too large to convert to float".to_owned());
        }
        let cutoff = unix_time_seconds()? - seconds;
        let mut recent = Vec::with_capacity(paths.len());
        for path in paths {
            let metadata = fs::metadata(&path)
                .map_err(|error| format!("cannot stat {}: {error}", path.display()))?;
            let modified = metadata
                .modified()
                .map_err(|error| format!("cannot stat {}: {error}", path.display()))?;
            if system_time_seconds(modified) >= cutoff {
                recent.push(path);
            }
        }
        paths = recent;
    }
    Ok(paths)
}

fn read_session_globs(
    patterns: &[String],
    recent_days: Option<&BigInt>,
) -> Result<Vec<TokenFootprint>, String> {
    let mut footprints = Vec::new();
    for path in session_glob_paths(patterns, recent_days)? {
        match parse_token_usage(&path) {
            Ok(footprint) => footprints.push(footprint),
            Err(SessionError::Value(_)) => {}
            Err(SessionError::Io(error)) => return Err(error),
        }
    }
    if footprints.is_empty() {
        return Err("no session files with token_count events matched --session-glob".to_owned());
    }
    Ok(footprints)
}

fn split_glob_pattern(pattern: &str) -> Result<(PathBuf, Vec<String>, bool), String> {
    let path = Path::new(pattern);
    let components = path.components().collect::<Vec<_>>();
    let prefix = components.iter().find_map(|component| match component {
        Component::Prefix(prefix) => Some(prefix.as_os_str()),
        _ => None,
    });
    let mut base = if path.is_absolute() {
        PathBuf::new()
    } else if let Some(prefix) = prefix {
        PathBuf::from(prefix)
    } else {
        env::current_dir().map_err(|error| format!("current directory: {error}"))?
    };
    let mut patterns = Vec::new();
    for component in components {
        match component {
            Component::Prefix(prefix) => {
                if path.is_absolute() {
                    base.push(prefix.as_os_str());
                }
            }
            Component::RootDir => base.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => patterns.push("..".to_owned()),
            Component::Normal(value) => patterns.push(
                value
                    .to_str()
                    .ok_or_else(|| "glob pattern contains a non-UTF-8 path component".to_owned())?
                    .to_owned(),
            ),
        }
    }
    let directory_only =
        pattern.ends_with(std::path::MAIN_SEPARATOR) || cfg!(windows) && pattern.ends_with('/');
    Ok((base, patterns, directory_only))
}

fn glob_paths(base: &Path, components: &[String], directory_only: bool) -> Vec<PathBuf> {
    let mut matches = Vec::new();
    let mut pending = vec![(base.to_path_buf(), 0_usize)];
    let mut visited = HashSet::new();

    while let Some((current, index)) = pending.pop() {
        if index == components.len() {
            if !directory_only || fs::metadata(&current).is_ok_and(|metadata| metadata.is_dir()) {
                matches.push(current);
            }
            continue;
        }

        let pattern = &components[index];
        if pattern == "**" {
            let key = resolve_non_strict(&current).unwrap_or_else(|_| current.clone());
            if !visited.insert((key, index)) {
                continue;
            }
            pending.push((current.clone(), index + 1));
            let Ok(entries) = fs::read_dir(&current) else {
                continue;
            };
            for entry in entries.flatten() {
                let path = entry.path();
                let name = entry.file_name();
                let Some(name) = name.to_str() else {
                    continue;
                };
                if name.starts_with('.') {
                    continue;
                }
                if index + 1 == components.len() {
                    pending.push((path.clone(), index + 1));
                }
                if fs::metadata(&path).is_ok_and(|metadata| metadata.is_dir()) {
                    pending.push((path, index));
                }
            }
            continue;
        }

        let has_glob_magic = |value: &str| {
            value
                .chars()
                .any(|character| matches!(character, '*' | '?' | '['))
        };
        if !has_glob_magic(pattern) {
            let mut path = current;
            let mut next_index = index;
            while let Some(component) = components.get(next_index) {
                if component == "**" || has_glob_magic(component) {
                    break;
                }
                path.push(component);
                next_index += 1;
            }
            pending.push((path, next_index));
            continue;
        }

        let Ok(entries) = fs::read_dir(&current) else {
            continue;
        };
        for entry in entries.flatten() {
            let name = entry.file_name();
            let Some(name_text) = name.to_str() else {
                continue;
            };
            if name_text.starts_with('.') && !pattern.starts_with('.') {
                continue;
            }
            if crate::source_dependency_graph::fnmatch_case(name_text, pattern) {
                pending.push((entry.path(), index + 1));
            }
        }
    }

    matches
}

fn path_posix(path: &Path) -> String {
    let value = path.to_string_lossy();
    if cfg!(windows) {
        value.replace('\\', "/")
    } else {
        value.into_owned()
    }
}

fn unix_time_seconds() -> Result<f64, String> {
    match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(duration) => Ok(duration.as_secs() as f64 + f64::from(duration.subsec_nanos()) / 1e9),
        Err(error) => {
            let duration = error.duration();
            Ok(-(duration.as_secs() as f64 + f64::from(duration.subsec_nanos()) / 1e9))
        }
    }
}

fn system_time_seconds(value: SystemTime) -> f64 {
    match value.duration_since(UNIX_EPOCH) {
        Ok(duration) => duration.as_secs() as f64 + f64::from(duration.subsec_nanos()) / 1e9,
        Err(error) => {
            let duration = error.duration();
            -(duration.as_secs() as f64 + f64::from(duration.subsec_nanos()) / 1e9)
        }
    }
}

fn moving_average(values: &[BigInt], window: &BigInt) -> Result<Vec<f64>, String> {
    let width = if window <= &BigInt::from(1_u8) {
        1
    } else {
        window
            .to_string()
            .parse::<usize>()
            .unwrap_or(usize::MAX)
            .min(values.len())
            .max(1)
    };
    let mut averages = Vec::with_capacity(values.len());
    for index in 0..values.len() {
        let start = index.saturating_add(1).saturating_sub(width);
        let sum = values[start..=index]
            .iter()
            .fold(BigInt::from(0_u8), |sum, value| sum + value);
        averages.push(bigint_ratio(&sum, &BigInt::from(index + 1 - start))?);
    }
    Ok(averages)
}

fn token_total(footprints: &[TokenFootprint]) -> BigInt {
    footprints
        .iter()
        .fold(BigInt::from(0_u8), |sum, value| sum + &value.total_tokens)
}

fn token_event_total(footprints: &[TokenFootprint]) -> BigInt {
    footprints.iter().fold(BigInt::from(0_u8), |sum, value| {
        sum + &value.token_event_count
    })
}

fn tokens_per_event(footprints: &[TokenFootprint]) -> Result<f64, String> {
    let events = token_event_total(footprints);
    if events <= BigInt::from(0_u8) {
        return Ok(0.0);
    }
    bigint_ratio(&token_total(footprints), &events)
}

fn latest_moving_average(footprints: &[TokenFootprint], window: &BigInt) -> Result<f64, String> {
    let values = footprints
        .iter()
        .map(|footprint| footprint.total_tokens.clone())
        .collect::<Vec<_>>();
    moving_average(&values, window)?
        .last()
        .copied()
        .ok_or_else(|| "no token footprints available for moving average".to_owned())
}

fn render_summary_report(
    footprints: &[TokenFootprint],
    window: &BigInt,
    recent_days: Option<&BigInt>,
) -> Result<String, String> {
    let values = footprints
        .iter()
        .map(|footprint| footprint.total_tokens.clone())
        .collect::<Vec<_>>();
    let averages = moving_average(&values, window)?;
    let event_total = token_event_total(footprints);
    let total = token_total(footprints);
    let average_per_event = tokens_per_event(footprints)?;
    let latest_average = latest_moving_average(footprints, window)?;
    let recent_days_text = recent_days.map_or_else(|| "all".to_owned(), ToString::to_string);
    let effective_window = effective_window(window);
    let mut lines = vec![
        "# Codex Token Usage Summary".to_owned(),
        "<!--".to_owned(),
        "@dependency-start".to_owned(),
        "responsibility Records Codex token usage moving-average evidence.".to_owned(),
        format!("upstream implementation {REPORT_OWNER} generates this report"),
        "@dependency-end".to_owned(),
        "-->".to_owned(),
        "".to_owned(),
        "## Summary".to_owned(),
        "".to_owned(),
        "- token_usage_summary_status: present".to_owned(),
        format!("- token_session_count: {}", footprints.len()),
        format!("- token_event_count: {event_total}"),
        format!("- total_tokens: {total}"),
        format!("- recent_days: {recent_days_text}"),
        format!("- average_tokens_per_event: {}", fixed(average_per_event)),
        format!("- moving_average_window: {effective_window}"),
        format!("- latest_moving_average_total_tokens: {}", fixed(latest_average)),
        "".to_owned(),
        "## Sessions".to_owned(),
        "".to_owned(),
        "| Session File | token events | input | cached input | output | reasoning output | total | moving average total |".to_owned(),
        "| ------------ | ------------ | ----- | ------------ | ------ | ---------------- | ----- | -------------------- |".to_owned(),
    ];
    for (footprint, average) in footprints.iter().zip(averages) {
        lines.push(format!(
            "| {} | {} | {} | {} | {} | {} | {} | {} |",
            footprint.session_file.display(),
            footprint.token_event_count,
            footprint.input_tokens,
            footprint.cached_input_tokens,
            footprint.output_tokens,
            footprint.reasoning_output_tokens,
            footprint.total_tokens,
            fixed(average)
        ));
    }
    lines.extend([
        "".to_owned(),
        "## Machine Status".to_owned(),
        "".to_owned(),
        "- TOKEN_USAGE_SUMMARY=pass".to_owned(),
        format!("- TOKEN_USAGE_SESSION_COUNT={}", footprints.len()),
        format!("- TOKEN_USAGE_TOKEN_EVENT_COUNT={event_total}"),
        format!("- TOKEN_USAGE_TOTAL_TOKENS={total}"),
        format!("- TOKEN_USAGE_RECENT_DAYS={recent_days_text}"),
        format!(
            "- TOKEN_USAGE_AVERAGE_TOKENS_PER_EVENT={}",
            fixed(average_per_event)
        ),
        format!("- TOKEN_USAGE_MOVING_AVERAGE_WINDOW={effective_window}"),
        format!(
            "- TOKEN_USAGE_LATEST_MOVING_AVERAGE_TOTAL={}",
            fixed(latest_average)
        ),
        "".to_owned(),
    ]);
    Ok(lines.join("\n"))
}

fn summary_status_text(
    footprints: &[TokenFootprint],
    window: &BigInt,
    recent_days: Option<&BigInt>,
) -> Result<String, String> {
    let event_total = token_event_total(footprints);
    let total = token_total(footprints);
    let recent_days_text = recent_days.map_or_else(|| "all".to_owned(), ToString::to_string);
    let effective_window = effective_window(window);
    let average_per_event = fixed(tokens_per_event(footprints)?);
    let latest_average = fixed(latest_moving_average(footprints, window)?);
    Ok(format!(
        "TOKEN_USAGE_SUMMARY=pass\nTOKEN_USAGE_SESSION_COUNT={}\nTOKEN_USAGE_TOKEN_EVENT_COUNT={event_total}\nTOKEN_USAGE_TOTAL_TOKENS={total}\nTOKEN_USAGE_RECENT_DAYS={recent_days_text}\nTOKEN_USAGE_AVERAGE_TOKENS_PER_EVENT={average_per_event}\nTOKEN_USAGE_MOVING_AVERAGE_WINDOW={effective_window}\nTOKEN_USAGE_LATEST_MOVING_AVERAGE_TOTAL={latest_average}\nNEXT_ACTION=record_token_usage_summary\n",
        footprints.len()
    ))
}

fn append_comparison_report_dir(
    report_dir: &Path,
    baseline: &TokenFootprint,
    candidate: &TokenFootprint,
    value: f64,
    status: &str,
) -> Result<(), String> {
    let behavior_events = [format!(
        "token_efficiency_protocol=active token_footprint_comparison={status} baseline_total={} candidate_total={} token_ratio={} target_ratio={}",
        baseline.total_tokens,
        candidate.total_tokens,
        fixed(value),
        fixed(TARGET_RATIO)
    )];
    let baseline_name = baseline
        .session_file
        .file_name()
        .unwrap_or_default()
        .to_string_lossy();
    let candidate_name = candidate
        .session_file
        .file_name()
        .unwrap_or_default()
        .to_string_lossy();
    let interventions = [format!(
        "token footprint measured from Codex session logs baseline={baseline_name} candidate={candidate_name}"
    )];
    append_monitoring(report_dir, &behavior_events, &interventions)
}

fn append_summary_report_dir(
    report_dir: &Path,
    footprints: &[TokenFootprint],
    window: &BigInt,
    recent_days: Option<&BigInt>,
) -> Result<(), String> {
    let event_total = token_event_total(footprints);
    let total = token_total(footprints);
    let recent_days_text = recent_days.map_or_else(|| "all".to_owned(), ToString::to_string);
    let effective_window = effective_window(window);
    let latest_average = latest_moving_average(footprints, window)?;
    let average_per_event = tokens_per_event(footprints)?;
    let behavior_events = [format!(
        "token_usage_summary=present session_count={} token_event_count={event_total} total_tokens={total} recent_days={recent_days_text} moving_average_window={effective_window} latest_moving_average_total={} average_tokens_per_event={}",
        footprints.len(),
        fixed(latest_average),
        fixed(average_per_event)
    )];
    let interventions = ["token usage moving average measured from Codex session logs".to_owned()];
    append_monitoring(report_dir, &behavior_events, &interventions)
}

fn append_monitoring(
    report_dir: &Path,
    behavior_events: &[String],
    interventions: &[String],
) -> Result<(), String> {
    let source_root = source_root()?;
    append_monitoring_projection(
        report_dir,
        &source_root,
        None,
        behavior_events,
        interventions,
    )
    .map(|_| ())
}

fn source_root() -> Result<PathBuf, String> {
    let crate_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    fs::canonicalize(crate_root.join("../../../../"))
        .map_err(|error| format!("AgentCanon source root unavailable: {error}"))
}

fn write_report(path: &Path, report: &str) -> Result<(), String> {
    fs::write(path, report).map_err(|error| error.to_string())
}

fn prepare_report_parent(path: &Path) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        let parent = if parent.as_os_str().is_empty() {
            Path::new(".")
        } else {
            parent
        };
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn effective_window(window: &BigInt) -> BigInt {
    window.clone().max(BigInt::from(1_u8))
}
