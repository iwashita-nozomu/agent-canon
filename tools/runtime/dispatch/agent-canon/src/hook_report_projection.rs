//! Append one behavior-event line to the existing workflow monitor document.
// @dependency-start
// contract implementation
// responsibility Projects an already assembled behavior event into the existing run-local monitor document.
// upstream implementation runtime_boundary.rs owns explicit external runtime path resolution and file boundaries
// upstream implementation work_log.rs owns the host-local timestamp format used by workflow monitoring
// upstream implementation behavior_event_assembly.rs owns the behavior-event payload
// downstream test ../tests/hook_report_projection_native.rs compares complete document bytes with the old API oracle
// @dependency-end

use crate::python_json::{canonical_json_ascii_bytes, JsonValue};
use crate::python_text::is_python_whitespace;
use crate::runtime_boundary::{
    resolve_external_artifact_path, RuntimeArtifactBoundary, RUNTIME_ROOT_ENV,
};
use crate::work_log::python_timestamp_jst;
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs::{self, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

const MONITORING_FILE: &str = "workflow_monitoring.md";
const BEHAVIOR_HEADING: &str = "## Behavior Events";
const TOOL_WARNINGS_HEADING: &str = "## Tool Warnings";
const TOOL_WARNING_STATUS_KEY: &str = "tool_warnings_status";

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MonitorProjectionResult {
    pub status: String,
    pub path: PathBuf,
    pub error: String,
}

/// Project one already assembled event using the host-local monitoring timestamp.
/// `source_root` is the explicit source root used by the workspace-scope artifact boundary.
pub fn emit_behavior_projection(
    report_dir: &Path,
    source_root: &Path,
    runtime_root: Option<&Path>,
    event: &JsonValue,
) -> MonitorProjectionResult {
    let inherited_runtime_root = runtime_root
        .map(Path::to_path_buf)
        .or_else(process_runtime_root);
    emit_behavior_projection_with_timestamp(
        report_dir,
        source_root,
        inherited_runtime_root.as_deref(),
        event,
        None,
    )
}

/// Project one event with an explicit timestamp for deterministic callers and readback tests.
pub fn emit_behavior_projection_at(
    report_dir: &Path,
    source_root: &Path,
    runtime_root: Option<&Path>,
    event: &JsonValue,
    timestamp: &str,
) -> MonitorProjectionResult {
    emit_behavior_projection_with_timestamp(
        report_dir,
        source_root,
        runtime_root,
        event,
        Some(timestamp),
    )
}

fn emit_behavior_projection_with_timestamp(
    report_dir: &Path,
    source_root: &Path,
    runtime_root: Option<&Path>,
    event: &JsonValue,
    timestamp: Option<&str>,
) -> MonitorProjectionResult {
    let fallback_path = report_dir.join(MONITORING_FILE);
    let event_bytes = match canonical_json_ascii_bytes(event) {
        Ok(bytes) => bytes,
        Err(error) => return failed_projection(fallback_path, error),
    };
    let event_json = match String::from_utf8(event_bytes) {
        Ok(value) => value,
        Err(error) => return failed_projection(fallback_path, error.to_string()),
    };
    let entry = format!("behavior_event_json={event_json}");

    let target = fallback_path.clone();
    if !target.is_absolute() {
        return failed_projection(
            fallback_path,
            "explicit external runtime root required for relative artifact path".to_owned(),
        );
    }

    let result = if let Some(runtime_root) = runtime_root {
        match RuntimeArtifactBoundary::for_source(source_root, Some(runtime_root), false) {
            Ok(boundary) => match boundary.resolve(&target) {
                Ok(resolved) => match ensure_runtime_parent(&boundary, &resolved) {
                    Ok(()) => update_monitoring_file(&resolved, report_dir, &entry, timestamp),
                    Err(error) => Err(error),
                },
                Err(error) => Err(error),
            },
            Err(error) => Err(error),
        }
    } else {
        match resolve_external_artifact_path(source_root, &target) {
            Ok(resolved) => match create_external_parent(&resolved) {
                Ok(()) => update_monitoring_file(&resolved, report_dir, &entry, timestamp),
                Err(error) => Err(error),
            },
            Err(error) => Err(error),
        }
    };

    match result {
        Ok(path) => MonitorProjectionResult {
            status: "spooled".to_owned(),
            path,
            error: String::new(),
        },
        Err(error) => failed_projection(fallback_path, error),
    }
}

fn process_runtime_root() -> Option<PathBuf> {
    let value = env::var_os(RUNTIME_ROOT_ENV)?;
    let text = value.to_string_lossy();
    let trimmed = python_strip(&text);
    (!trimmed.is_empty()).then(|| PathBuf::from(trimmed))
}

fn ensure_runtime_parent(boundary: &RuntimeArtifactBoundary, target: &Path) -> Result<(), String> {
    let parent = target
        .parent()
        .ok_or_else(|| format!("monitor target has no parent: {}", target.display()))?;
    let relative = parent
        .strip_prefix(boundary.root())
        .map_err(|_| format!("path escapes runtime root: {}", target.display()))?;
    boundary.ensure_directory(if relative.as_os_str().is_empty() {
        Path::new(".")
    } else {
        relative
    })?;
    Ok(())
}

fn create_external_parent(target: &Path) -> Result<(), String> {
    let parent = target
        .parent()
        .ok_or_else(|| format!("monitor target has no parent: {}", target.display()))?;
    fs::create_dir_all(parent).map_err(|error| {
        format!(
            "cannot create monitor directory {}: {error}",
            parent.display()
        )
    })
}

fn update_monitoring_file(
    path: &Path,
    report_dir: &Path,
    entry: &str,
    timestamp: Option<&str>,
) -> Result<PathBuf, String> {
    let mut file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| format!("cannot open monitor document {}: {error}", path.display()))?;
    file.lock()
        .map_err(|error| format!("cannot lock monitor document {}: {error}", path.display()))?;

    file.seek(SeekFrom::Start(0))
        .map_err(|error| format!("cannot seek monitor document {}: {error}", path.display()))?;
    let mut text = String::new();
    file.read_to_string(&mut text)
        .map_err(|error| format!("cannot read monitor document {}: {error}", path.display()))?;
    if python_strip(&text).is_empty() {
        text = default_monitoring_text(report_dir);
    }
    let mut lines = python_splitlines(&text);
    let timestamp = match timestamp {
        Some(value) if !python_strip(value).is_empty() => python_strip(value).to_owned(),
        _ => python_timestamp_jst()?,
    };
    let behavior_entry = normalize_entry(entry, &timestamp)?;
    insert_entries(&mut lines, BEHAVIOR_HEADING, &[behavior_entry]);
    let warning_status = infer_tool_warning_status(&lines);
    set_section_status(
        &mut lines,
        TOOL_WARNINGS_HEADING,
        TOOL_WARNING_STATUS_KEY,
        &warning_status,
    );

    let document = format!("{}\n", python_strip_end(&lines.join("\n")));
    file.set_len(0).map_err(|error| {
        format!(
            "cannot truncate monitor document {}: {error}",
            path.display()
        )
    })?;
    file.seek(SeekFrom::Start(0))
        .map_err(|error| format!("cannot seek monitor document {}: {error}", path.display()))?;
    file.write_all(document.as_bytes())
        .map_err(|error| format!("cannot write monitor document {}: {error}", path.display()))?;
    file.flush()
        .map_err(|error| format!("cannot flush monitor document {}: {error}", path.display()))?;
    Ok(path.to_path_buf())
}

fn default_monitoring_text(report_dir: &Path) -> String {
    let run_id = report_dir
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or_default();
    format!(
        "# Workflow Monitoring\n<!--\n@dependency-start\nresponsibility Records workflow monitoring for this run bundle.\nupstream design ../../../templates/agents/workflow_monitoring.md template\n@dependency-end\n-->\n\n- Run ID: {run_id}\n\n## Signals\n\n## Behavior Events\n\n## Tool Warnings\n\n- tool_warnings_status: pending\n\n## Interventions\n\n## Improvement Decisions\n\n- skill_improvement_decision: pending\n- config_improvement_decision: pending\n- workflow_improvement_decision: pending\n- knowledge_learning_decision: pending\n"
    )
}

fn normalize_entry(entry: &str, timestamp: &str) -> Result<String, String> {
    let entry = python_strip(entry);
    if entry.is_empty() {
        return Err("workflow monitoring entries must not be empty".to_owned());
    }
    Ok(format!("- `{}` {entry}", python_strip(timestamp)))
}

fn insert_entries(lines: &mut Vec<String>, heading: &str, entries: &[String]) {
    if entries.is_empty() {
        return;
    }
    ensure_section(lines, heading);
    let mut insert_at = section_bounds(lines, heading).1;
    if insert_at > 0 && !python_strip(&lines[insert_at - 1]).is_empty() {
        lines.insert(insert_at, String::new());
        insert_at += 1;
    }
    let mut existing = lines.iter().cloned().collect::<BTreeSet<_>>();
    for entry in entries {
        if existing.insert(entry.clone()) {
            lines.insert(insert_at, entry.clone());
            insert_at += 1;
        }
    }
}

fn ensure_section(lines: &mut Vec<String>, heading: &str) {
    if section_start(lines, heading).is_none() {
        lines.extend([String::new(), heading.to_owned(), String::new()]);
    }
}

fn section_start(lines: &[String], heading: &str) -> Option<usize> {
    lines.iter().position(|line| python_strip(line) == heading)
}

fn section_bounds(lines: &[String], heading: &str) -> (usize, usize) {
    let Some(start) = section_start(lines, heading) else {
        return (lines.len(), lines.len());
    };
    let end = lines
        .iter()
        .enumerate()
        .skip(start + 1)
        .find(|(_, line)| line.starts_with("## "))
        .map_or(lines.len(), |(index, _)| index);
    (start, end)
}

fn infer_tool_warning_status(lines: &[String]) -> String {
    let Some((start, end)) = section_start(lines, TOOL_WARNINGS_HEADING)
        .map(|start| (start, section_bounds(lines, TOOL_WARNINGS_HEADING).1))
    else {
        return String::new();
    };
    let mut latest = BTreeMap::<String, String>::new();
    for line in &lines[start..end] {
        if !line.contains("tool_warning=recorded") {
            continue;
        }
        let fields = parse_token_fields(line);
        if let (Some(warning_id), Some(status)) = (fields.get("warning_id"), fields.get("status")) {
            if !warning_id.is_empty() && !status.is_empty() {
                latest.insert(warning_id.clone(), status.clone());
            }
        }
    }
    if latest.is_empty() {
        String::new()
    } else if latest.values().any(|status| status == "open") {
        "open".to_owned()
    } else {
        "resolved".to_owned()
    }
}

fn parse_token_fields(line: &str) -> BTreeMap<String, String> {
    line.split(is_python_whitespace)
        .filter(|token| !token.is_empty())
        .filter_map(|token| {
            token
                .split_once('=')
                .map(|(key, value)| (python_strip(key).to_owned(), python_strip(value).to_owned()))
        })
        .collect()
}

fn set_section_status(lines: &mut Vec<String>, heading: &str, key: &str, value: &str) {
    if value.is_empty() {
        return;
    }
    ensure_section(lines, heading);
    let (start, end) = section_bounds(lines, heading);
    let prefix = format!("- {key}:");
    if let Some(index) =
        (start + 1..end).find(|index| python_strip(&lines[*index]).starts_with(&prefix))
    {
        lines[index] = format!("- {key}: {value}");
        return;
    }
    let mut insert_at = start + 1;
    while insert_at < end && python_strip(&lines[insert_at]).is_empty() {
        insert_at += 1;
    }
    lines.insert(insert_at, format!("- {key}: {value}"));
}

fn python_splitlines(text: &str) -> Vec<String> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut characters = text.char_indices().peekable();
    while let Some((index, character)) = characters.next() {
        if !python_line_break(character) {
            continue;
        }
        lines.push(text[start..index].to_owned());
        let mut end = index + character.len_utf8();
        if character == '\r' && characters.peek().is_some_and(|(_, next)| *next == '\n') {
            end += 1;
            characters.next();
        }
        start = end;
    }
    if start < text.len() {
        lines.push(text[start..].to_owned());
    }
    lines
}

fn python_line_break(character: char) -> bool {
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

fn python_strip_end(value: &str) -> &str {
    value.trim_end_matches(is_python_whitespace)
}

fn failed_projection(path: PathBuf, error: impl ToString) -> MonitorProjectionResult {
    MonitorProjectionResult {
        status: "failed".to_owned(),
        path,
        error: error.to_string(),
    }
}
