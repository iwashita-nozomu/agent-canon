// @dependency-start
// contract implementation
// responsibility Reads archived skill_usage.jsonl as immutable historical evidence.
// upstream design ../../../../../documents/design/agentcanon-hook-simplification-wave3.md defines the historical-only artifact contract
// upstream implementation python_json.rs parses accepted UTF-8 JSON records with Python semantics
// upstream implementation python_text.rs owns Python bytes.splitlines line boundaries
// downstream implementation main.rs exposes the read-only historical JSON command
// downstream implementation ../../../../../eval/producers/generate_agent_improvement_guide.py consumes the readback records
// downstream implementation ../../../../../tests/agent_tools/test_historical_skill_usage_reader.py validates the native read boundary
// @dependency-end

//! Read historical skill-usage JSONL without writing or executing its contents.

use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::python_json::{parse_json, JsonValue};
use crate::python_text::python_bytes_splitlines;
use std::fs;
use std::path::{Path, PathBuf};

pub const SELECTOR: &str = "historical-skill-usage-read";

#[derive(Debug)]
struct HistoricalSkillUsageReadback {
    raw_records: Vec<String>,
    accepted_count: usize,
    malformed_count: usize,
    ignored_count: usize,
    malformed_by_reason: Option<Vec<(String, usize)>>,
    status: &'static str,
}

#[derive(Clone, Copy)]
enum CliOption {
    Help,
    Path,
}

const CLI_OPTIONS: &[(&str, CliOption)] =
    &[("--help", CliOption::Help), ("--path", CliOption::Path)];

fn empty_readback(status: &'static str) -> HistoricalSkillUsageReadback {
    HistoricalSkillUsageReadback {
        raw_records: Vec::new(),
        accepted_count: 0,
        malformed_count: 0,
        ignored_count: 0,
        malformed_by_reason: None,
        status,
    }
}

fn increment_reason(reasons: &mut Vec<(String, usize)>, reason: &str) {
    if let Some((_, count)) = reasons.iter_mut().find(|(existing, _)| existing == reason) {
        *count += 1;
    } else {
        reasons.push((reason.to_owned(), 1));
    }
}

fn malformed_readback(reason: &str) -> HistoricalSkillUsageReadback {
    let mut reasons = Vec::new();
    increment_reason(&mut reasons, reason);
    HistoricalSkillUsageReadback {
        raw_records: Vec::new(),
        accepted_count: 0,
        malformed_count: 1,
        ignored_count: 0,
        malformed_by_reason: Some(reasons),
        status: "malformed",
    }
}

/// Parse one archived skill-usage file as read-only historical evidence.
fn read_skill_usage_history(path: &Path) -> HistoricalSkillUsageReadback {
    if !path.exists() {
        return empty_readback("missing");
    }
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(_) => return malformed_readback("line_encoding"),
    };
    let mut raw_records = Vec::new();
    let mut malformed_by_reason = Vec::new();
    let mut malformed_count = 0usize;
    let mut ignored_count = 0usize;

    for raw_line in python_bytes_splitlines(&bytes) {
        if raw_line.iter().all(u8::is_ascii_whitespace) {
            ignored_count += 1;
            continue;
        }
        let Ok(line) = std::str::from_utf8(raw_line) else {
            malformed_count += 1;
            increment_reason(&mut malformed_by_reason, "json");
            continue;
        };
        match parse_json(line) {
            Ok(JsonValue::Object(_)) => raw_records.push(line.to_owned()),
            Ok(_) => {
                malformed_count += 1;
                increment_reason(&mut malformed_by_reason, "field_type");
            }
            Err(_) => {
                malformed_count += 1;
                increment_reason(&mut malformed_by_reason, "json");
            }
        }
    }

    let accepted_count = raw_records.len();
    let status = if malformed_count > 0 {
        "malformed"
    } else {
        "present"
    };
    HistoricalSkillUsageReadback {
        raw_records,
        accepted_count,
        malformed_count,
        ignored_count,
        malformed_by_reason: Some(malformed_by_reason),
        status,
    }
}

fn readback_json(readback: &HistoricalSkillUsageReadback) -> Result<String, String> {
    let reasons = match &readback.malformed_by_reason {
        Some(reasons) => {
            let entries = reasons
                .iter()
                .map(|(reason, count)| {
                    let reason = serde_json::to_string(reason)
                        .expect("historical reason strings are serializable");
                    format!("{reason}:{count}")
                })
                .collect::<Vec<_>>()
                .join(",");
            format!("{{{entries}}}")
        }
        None => "null".to_owned(),
    };
    let status = serde_json::to_string(readback.status)
        .map_err(|error| format!("serialize historical readback status: {error}"))?;
    let records = readback.raw_records.join(",");
    Ok(format!(
        "{{\"records\":[{records}],\"accepted_count\":{},\"malformed_count\":{},\"ignored_count\":{},\"malformed_by_reason\":{reasons},\"status\":{status}}}",
        readback.accepted_count,
        readback.malformed_count,
        readback.ignored_count,
    ))
}

fn print_help() {
    println!(
        "usage: agent-canon {SELECTOR} --path PATH\n\nRead archived skill_usage.jsonl as immutable historical evidence.\n\nOptions:\n  -h, --help  show this help message and exit\n  --path PATH"
    );
}

fn parse_arguments(args: &[String]) -> Result<Option<PathBuf>, String> {
    let mut path = None;
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        if token == "-h" || token == "--help" {
            return Ok(None);
        }
        let (option_text, inline_value) = match token.split_once('=') {
            Some((option, value)) => (option, Some(value)),
            None => (token.as_str(), None),
        };
        if !option_text.starts_with("--") {
            return Err(format!("unrecognized argument: {token}"));
        }
        let option =
            resolve_long_option_prefix(option_text, CLI_OPTIONS).map_err(|error| match error {
                LongOptionError::Unrecognized => format!("unrecognized argument: {token}"),
                LongOptionError::Ambiguous(_) => format!("ambiguous option: {option_text}"),
            })?;
        if matches!(option, CliOption::Help) {
            if inline_value.is_some() {
                return Err(format!("ignored explicit argument for --help: {token}"));
            }
            return Ok(None);
        }
        let value = if let Some(value) = inline_value {
            value.to_owned()
        } else {
            index += 1;
            let Some(value) = args.get(index) else {
                return Err(format!("argument {option_text}: expected one argument"));
            };
            if value.starts_with('-') {
                return Err(format!("argument {option_text}: expected one argument"));
            }
            value.clone()
        };
        match option {
            CliOption::Path => path = Some(PathBuf::from(value)),
            CliOption::Help => unreachable!("help is handled before value parsing"),
        }
        index += 1;
    }
    path.map(Some)
        .ok_or_else(|| "the --path argument is required".to_owned())
}

/// Run the read-only historical skill-usage JSON command.
pub fn run(args: &[String]) -> i32 {
    let path = match parse_arguments(args) {
        Ok(Some(path)) => path,
        Ok(None) => {
            print_help();
            return 0;
        }
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: {error}");
            return 2;
        }
    };
    let readback = read_skill_usage_history(&path);
    let output = match readback_json(&readback) {
        Ok(output) => output,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: {error}");
            return 1;
        }
    };
    println!("{output}");
    0
}
