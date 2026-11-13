// @dependency-start
// contract implementation
// responsibility Collects and renders read-only AgentCanon improvement-guide and runtime-dashboard evidence.
// upstream implementation eval_archive_paths.rs owns mounted hook/eval archive resolution
// upstream implementation historical_skill_usage.rs owns archived skill-usage JSONL parsing
// upstream implementation issue_sync.rs owns Issue identity and finding qualification
// upstream implementation runtime_boundary.rs owns external runtime reads and writes
// downstream implementation main.rs exposes the guide and dashboard CLI routes
// downstream implementation ../../../../../tests/agent_tools/test_generate_agent_improvement_guide.py preserves the guide output contract
// downstream implementation ../../../../../tests/agent_tools/test_generate_agent_runtime_dashboard.py preserves dashboard, compact, and API contracts
// @dependency-end

//! Read-only aggregation and rendering for AgentCanon improvement evidence.

use crate::eval_archive_paths::{
    eval_result_search_dirs, hook_result_search_dirs, mounted_log_archive_root,
};
use crate::historical_skill_usage::read_skill_usage_records;
use crate::issue_sync;
use crate::path_resolution::python_pathlib_glob_paths;
use crate::runtime_boundary::RuntimeArtifactBoundary;
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

pub const GUIDE_SELECTOR: &str = "generate-agent-improvement-guide";
pub const DASHBOARD_SELECTOR: &str = "generate-agent-runtime-dashboard";
const ISSUE_PACKET_DIR: &str = "feedback/issue-packets";
const SKILL_USAGE_FILE: &str = "skill_usage.jsonl";
const MAX_COUNTER_LINES: usize = 20;
const MAX_FAILURE_LINES: usize = 20;
const SOURCE_SYNC_SCHEMA: &str = "agent-canon.source-sync.v1";
const DASHBOARD_API_SCHEMA: &str = "agent_runtime_dashboard.v1";

#[derive(Clone, Debug)]
struct ResultFamily {
    family: String,
    directory: PathBuf,
    reports: Vec<PathBuf>,
    statuses: Counter,
}

#[derive(Clone, Debug)]
struct IssueReceipt {
    repository: String,
    number: String,
    url: String,
    state: String,
    action: String,
    responsibility: Vec<String>,
    occurrence_locations: Vec<String>,
    source_finding_kind: String,
    timestamp: String,
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
struct Counter(Vec<(String, u64)>);

impl Counter {
    fn add(&mut self, key: impl Into<String>) {
        self.add_by(key, 1);
    }

    fn add_by(&mut self, key: impl Into<String>, amount: u64) {
        let key = key.into();
        if let Some((_, count)) = self.0.iter_mut().find(|(existing, _)| existing == &key) {
            *count += amount;
        } else {
            self.0.push((key, amount));
        }
    }

    fn get(&self, key: &str) -> u64 {
        self.0
            .iter()
            .find_map(|(name, value)| (name == key).then_some(*value))
            .unwrap_or(0)
    }

    fn total(&self) -> u64 {
        self.0.iter().map(|(_, value)| value).sum()
    }

    fn sorted(&self) -> Vec<(&str, u64)> {
        let mut values = self
            .0
            .iter()
            .map(|(name, count)| (name.as_str(), *count))
            .collect::<Vec<_>>();
        values.sort_by_key(|item| std::cmp::Reverse(item.1));
        values
    }

    fn json(&self) -> Value {
        let mut value = Map::new();
        for (key, count) in &self.0 {
            value.insert(key.clone(), json!(count));
        }
        Value::Object(value)
    }

    fn python_repr(&self) -> String {
        let body = self
            .0
            .iter()
            .map(|(key, value)| {
                format!(
                    "'{}': {}",
                    key.replace('\\', "\\\\").replace('\'', "\\'"),
                    value
                )
            })
            .collect::<Vec<_>>()
            .join(", ");
        format!("{{{body}}}")
    }

    fn markdown(&self, limit: usize) -> Vec<String> {
        if self.0.is_empty() {
            return vec!["- none".into()];
        }
        self.sorted()
            .into_iter()
            .take(limit)
            .map(|(name, count)| format!("- `{name}`: `{count}`"))
            .collect()
    }
}

#[derive(Clone, Debug, Default)]
struct EvidenceCounts {
    statuses: Counter,
    failures: Counter,
    files: Counter,
    events: Counter,
    namespaces: Counter,
    tools: Counter,
    skills: Counter,
    candidate_skills: Counter,
    candidate_workflows: Counter,
    candidate_tools: Counter,
    skill_events: Counter,
    skill_sources: Counter,
    feedback_labels: Counter,
    feedback_targets: Counter,
    feedback_actions: Counter,
    checker_targets: Counter,
    failure_targets: Counter,
    quality: Counter,
}

#[derive(Clone, Debug)]
struct Evidence {
    root: PathBuf,
    issue_refs: Vec<String>,
    knowledge_entries: BTreeMap<String, u64>,
    records: Vec<(PathBuf, Value)>,
    counts: EvidenceCounts,
}

#[derive(Clone, Debug)]
struct Options {
    root: PathBuf,
    runtime_root: Option<PathBuf>,
    output: PathBuf,
    compact_output: Option<PathBuf>,
    api_output: Option<PathBuf>,
    recent_days: Option<i64>,
    output_mode: u32,
}

fn parse_options(args: &[String], dashboard: bool) -> Result<Options, String> {
    let mut options = Options {
        root: env::current_dir().map_err(|error| error.to_string())?,
        runtime_root: None,
        output: PathBuf::from(if dashboard {
            "reports/agent-runtime-dashboard/agent-runtime-dashboard.md"
        } else {
            "reports/agent-improvement-guide/agent-improvement-guide.md"
        }),
        compact_output: None,
        api_output: None,
        recent_days: None,
        output_mode: 0o600,
    };
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        if token == "-h" || token == "--help" {
            return Err(String::new());
        }
        let (name, inline) = token
            .split_once('=')
            .map_or((token.as_str(), None), |(name, value)| (name, Some(value)));
        let value = if let Some(value) = inline {
            value.to_owned()
        } else {
            index += 1;
            args.get(index)
                .filter(|value| !value.starts_with('-') || name == "--recent-days")
                .cloned()
                .ok_or_else(|| format!("argument {name}: expected one argument"))?
        };
        match name {
            "--root" => options.root = PathBuf::from(value),
            "--runtime-root" => options.runtime_root = Some(PathBuf::from(value)),
            "--out" | "--output" => options.output = PathBuf::from(value),
            "--compact-out" => options.compact_output = Some(PathBuf::from(value)),
            "--api-out" | "--api-output" => options.api_output = Some(PathBuf::from(value)),
            "--recent-days" if dashboard => {
                options.recent_days = Some(
                    value
                        .parse::<i64>()
                        .map_err(|_| "argument --recent-days: invalid integer".to_owned())?,
                )
            }
            "--output-mode" if !dashboard => {
                options.output_mode = match value.as_str() {
                    "600" => 0o600,
                    "644" => 0o644,
                    _ => return Err("argument --output-mode: choose from 600, 644".into()),
                }
            }
            _ => return Err(format!("unrecognized argument: {name}")),
        }
        index += 1;
    }
    Ok(options)
}

fn known_skill_ids(root: &Path) -> BTreeSet<String> {
    let mut skills = BTreeSet::new();
    for pattern in [
        root.join(".codex/personal/skills/*/SKILL.md"),
        root.join("agents/skills/*.md"),
    ] {
        if let Ok(paths) = python_pathlib_glob_paths(&pattern.to_string_lossy()) {
            for path in paths {
                if path.file_name().and_then(|name| name.to_str()) == Some("README.md") {
                    continue;
                }
                let id = if path.file_name().and_then(|name| name.to_str()) == Some("SKILL.md") {
                    path.parent().and_then(Path::file_name)
                } else {
                    path.file_stem()
                };
                if let Some(id) = id.and_then(|value| value.to_str()) {
                    skills.insert(id.to_owned());
                }
            }
        }
    }
    skills
}

fn values(value: Option<&Value>) -> Vec<String> {
    match value {
        Some(Value::String(value)) if !value.is_empty() => vec![value.clone()],
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(Value::as_str)
            .filter(|value| !value.is_empty())
            .map(str::to_owned)
            .collect(),
        _ => Vec::new(),
    }
}

fn str_field<'a>(value: &'a Value, key: &str) -> &'a str {
    value.get(key).and_then(Value::as_str).unwrap_or("")
}

fn add_issue_refs(root: &Path, runtime_root: Option<&Path>) -> Vec<String> {
    let mut roots = BTreeSet::new();
    if let Some(configured) = env::var_os("AGENT_CANON_LOG_ROOT") {
        roots.insert(PathBuf::from(configured));
    }
    if let Ok(archive) = mounted_log_archive_root(root, runtime_root) {
        roots.insert(archive);
    }
    let mut refs = BTreeSet::new();
    for directory in roots
        .into_iter()
        .map(|value| value.join(ISSUE_PACKET_DIR).join("pending"))
    {
        let Ok(paths) = python_pathlib_glob_paths(&directory.join("*.json").to_string_lossy())
        else {
            continue;
        };
        for path in paths {
            if let Ok(bytes) = fs::read(&path) {
                if let Ok(value) = serde_json::from_slice::<Value>(&bytes) {
                    if let Some(url) = value.get("issue_url").and_then(Value::as_str) {
                        if url.starts_with("https://github.com/") {
                            refs.insert(url.to_owned());
                            continue;
                        }
                    }
                    if let (Some(repository), Some(number)) = (
                        value.get("repository").and_then(Value::as_str),
                        value.get("number").and_then(Value::as_str),
                    ) {
                        refs.insert(format!("https://github.com/{repository}/issues/{number}"));
                    }
                }
            }
        }
    }
    refs.into_iter().collect()
}

fn knowledge_entries() -> BTreeMap<String, u64> {
    let mut counts = BTreeMap::new();
    let key = "agent-canon-log/knowledge".to_owned();
    let count = env::var_os("AGENT_CANON_LOG_ROOT")
        .map(PathBuf::from)
        .map(|root| root.join("knowledge/topics/*/candidate.md"))
        .and_then(|pattern| python_pathlib_glob_paths(&pattern.to_string_lossy()).ok())
        .map_or(0, |paths| paths.len() as u64);
    counts.insert(key, count);
    counts
}

fn hook_paths(
    requested_root: &Path,
    source_root: &Path,
    runtime_root: Option<&Path>,
) -> Result<Vec<PathBuf>, String> {
    let mut paths = BTreeSet::new();
    for directory in hook_result_search_dirs(requested_root, source_root, runtime_root)? {
        if let Ok(entries) = fs::read_dir(&directory) {
            for entry in entries.flatten() {
                if entry.path().extension().and_then(|value| value.to_str()) == Some("jsonl") {
                    paths.insert(entry.path());
                }
            }
        }
        let pattern = directory.join("**/*.jsonl");
        if let Ok(nested) = python_pathlib_glob_paths(&pattern.to_string_lossy()) {
            paths.extend(nested);
        }
    }
    Ok(paths.into_iter().collect())
}

fn hook_epoch(entry: &Value) -> Option<i64> {
    let timestamp = str_field(entry, "timestamp");
    let normalized = timestamp.strip_suffix('Z').unwrap_or(timestamp);
    if normalized.is_empty() {
        return None;
    }
    // Accept the canonical UTC timestamps emitted by the hook writer.
    let normalized_timestamp;
    let value = if timestamp.ends_with('Z') {
        normalized_timestamp = format!("{}+00:00", normalized);
        normalized_timestamp.as_str()
    } else {
        timestamp
    };
    let parsed =
        time::OffsetDateTime::parse(value, &time::format_description::well_known::Rfc3339).ok()?;
    Some(parsed.unix_timestamp())
}

fn source_epoch(root: &Path, skill: &str) -> Option<i64> {
    let slug = skill.strip_prefix('$').unwrap_or(skill);
    let paths = [
        PathBuf::from(format!(".codex/personal/skills/{slug}/SKILL.md")),
        PathBuf::from(format!("agents/skills/{slug}.md")),
    ];
    let existing = paths
        .iter()
        .filter(|path| root.join(path).exists())
        .map(|path| path.to_string_lossy().into_owned())
        .collect::<Vec<_>>();
    if existing.is_empty() {
        return None;
    }
    let mut command = Command::new("git");
    command
        .arg("-C")
        .arg(root)
        .args(["log", "-1", "--format=%ct", "--"]);
    command.args(existing);
    let output = command.output().ok()?;
    if !output.status.success() {
        return None;
    }
    String::from_utf8_lossy(&output.stdout).trim().parse().ok()
}

fn field_values(entry: &Value, field: &str) -> Vec<String> {
    values(entry.get(field))
}

fn add_quality(counts: &mut EvidenceCounts, key: &str) {
    counts.quality.add(key.to_owned());
}

fn checker_executable(value: &str) -> bool {
    value.ends_with("readability.py")
        || value.ends_with("oop_readability_check.py")
        || matches!(value, "oop-python-readability" | "oop-cpp-readability")
        || matches!(value, "pyright" | "ruff")
        || value.ends_with("/pyright")
        || value.ends_with("/ruff")
}

const OPTION_VALUE_FLAGS: &[&str] = &[
    "--config",
    "--output",
    "--format",
    "--root",
    "--mode",
    "--report-out",
    "--timeout",
    "--project",
    "--pythonversion",
    "--python-platform",
    "--level",
    "--select",
    "--ignore",
    "--target-version",
    "--exclude",
    "--include",
    "--baseline",
    "--evidence",
];

const CHECKER_SUFFIXES: &[&str] = &[
    ".c", ".cc", ".cpp", ".h", ".hpp", ".json", ".md", ".py", ".rs", ".toml", ".yaml", ".yml",
];

fn command_targets(command: &[String]) -> Vec<String> {
    let mut output = Vec::new();
    let mut skip_next = false;
    for token in command {
        if skip_next {
            skip_next = false;
            continue;
        }
        if OPTION_VALUE_FLAGS.contains(&token.as_str()) {
            skip_next = true;
            continue;
        }
        if checker_executable(token) || token.starts_with('-') {
            continue;
        }
        if token.contains('/')
            && CHECKER_SUFFIXES
                .iter()
                .any(|suffix| token.ends_with(suffix))
        {
            output.push(token.clone());
        }
    }
    output
}

fn add_hook_entry(
    counts: &mut EvidenceCounts,
    path: &Path,
    entry: &Value,
    known_skills: &BTreeSet<String>,
    reset_epochs: &mut BTreeMap<String, Option<i64>>,
    source_root: &Path,
) {
    if str_field(entry, "hook_run_id").is_empty() {
        add_quality(counts, "missing_hook_run_id");
    }
    if str_field(entry, "payload_fingerprint").is_empty() {
        add_quality(counts, "missing_payload_fingerprint");
    }
    let namespace = str_field(entry, "hook_log_namespace");
    if namespace.is_empty() {
        add_quality(counts, "missing_hook_log_namespace");
    } else {
        counts.namespaces.add(namespace.to_owned());
    }
    let status = if str_field(entry, "status").is_empty()
        && path.file_name().and_then(|v| v.to_str()) == Some(SKILL_USAGE_FILE)
    {
        "pass"
    } else if str_field(entry, "status").is_empty() {
        "unknown"
    } else {
        str_field(entry, "status")
    };
    counts.statuses.add(status.to_owned());
    let event = if str_field(entry, "event").is_empty() {
        "missing_event"
    } else {
        str_field(entry, "event")
    };
    counts.events.add(event.to_owned());
    if matches!(event, "UnknownHookEvent" | "missing_event") {
        add_quality(counts, "unknown_event");
    }
    if entry.get("event_declared") == Some(&Value::Bool(false)) {
        add_quality(counts, "missing_declared_event");
    }
    if entry.get("payload_empty") == Some(&Value::Bool(true)) {
        add_quality(counts, "empty_payload");
    }
    let payload_status = str_field(entry, "payload_status");
    if !payload_status.is_empty() && payload_status != "valid" {
        add_quality(counts, &format!("payload_status:{payload_status}"));
    }
    let fingerprint = str_field(entry, "failure_fingerprint");
    if status == "fail" && !fingerprint.is_empty() {
        counts.failures.add(fingerprint.to_owned());
    }
    if status == "fail" && fingerprint.is_empty() {
        add_quality(counts, "failed_entry_without_failure_fingerprint");
    }
    let tool_name = str_field(entry, "tool_name");
    if !tool_name.is_empty() {
        counts.tools.add(tool_name.to_owned());
    }
    for command_entry in entry
        .get("commands")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let command = command_entry
            .get("command")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
            .map(str::to_owned)
            .collect::<Vec<_>>();
        if command.iter().any(|value| checker_executable(value)) {
            for target in command_targets(&command) {
                counts.checker_targets.add(target);
            }
        }
    }
    if status == "fail" {
        let Some(commands) = entry.get("commands").and_then(Value::as_array) else {
            add_quality(counts, "failed_entry_without_commands");
            return;
        };
        let mut saw_failed = false;
        for command_entry in commands {
            let code = command_entry
                .get("returncode")
                .and_then(Value::as_i64)
                .unwrap_or(0);
            if code == 0 {
                continue;
            }
            saw_failed = true;
            if str_field(command_entry, "output_snippet").is_empty() {
                add_quality(counts, "failed_command_without_output_snippet");
            }
            let command = command_entry
                .get("command")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(Value::as_str)
                .map(str::to_owned)
                .collect::<Vec<_>>();
            for target in command_targets(&command) {
                counts.failure_targets.add(target);
            }
        }
        if !saw_failed {
            add_quality(counts, "failed_entry_without_failed_command");
        }
    }
    if path.file_name().and_then(|value| value.to_str()) != Some(SKILL_USAGE_FILE) {
        return;
    }
    let sources = field_values(entry, "skill_source_fields");
    if sources.is_empty() {
        add_quality(counts, "missing_skill_source_fields");
    } else {
        for source in &sources {
            counts.skill_sources.add(source.clone());
        }
    }
    if entry.get("observed_text_field_count").is_none() {
        add_quality(counts, "missing_observed_text_field_count");
    }
    let trusted = sources.is_empty()
        || sources.iter().any(|source| {
            matches!(
                source.as_str(),
                "prompt" | "last_assistant_message" | "message"
            )
        });
    let entry_epoch = hook_epoch(entry);
    let in_skill_window = |skill: &str, resets: &mut BTreeMap<String, Option<i64>>| {
        let reset = *resets
            .entry(skill.to_owned())
            .or_insert_with(|| source_epoch(source_root, skill));
        match (entry_epoch, reset) {
            (_, None) | (None, _) => true,
            (Some(epoch), Some(reset)) => epoch >= reset,
        }
    };
    for skill in field_values(entry, "candidate_skills") {
        if in_skill_window(&skill, reset_epochs) {
            counts.candidate_skills.add(skill);
        } else {
            add_quality(
                counts,
                &format!("skill_routing_signal_before_cutover_ignored:{skill}"),
            );
            add_quality(counts, "skill_routing_signal_before_cutover_ignored");
        }
    }
    for workflow in field_values(entry, "candidate_workflows") {
        counts.candidate_workflows.add(workflow);
    }
    for tool in field_values(entry, "candidate_tools") {
        counts.candidate_tools.add(tool);
    }
    for label in field_values(entry, "feedback_labels") {
        counts.feedback_labels.add(label);
    }
    for target in field_values(entry, "feedback_targets") {
        let skill_target = target.strip_prefix("skill:");
        if let Some(skill) = skill_target {
            if !trusted {
                add_quality(counts, "tool_input_skill_feedback_target_ignored");
                continue;
            }
            if !known_skills.is_empty() && !known_skills.contains(skill) {
                add_quality(counts, "noncanonical_skill_feedback_target_ignored");
                add_quality(
                    counts,
                    &format!("noncanonical_skill_feedback_target_ignored:{skill}"),
                );
                continue;
            }
            if !in_skill_window(skill, reset_epochs) {
                add_quality(counts, "skill_routing_signal_before_cutover_ignored");
                add_quality(
                    counts,
                    &format!("skill_routing_signal_before_cutover_ignored:{skill}"),
                );
                continue;
            }
        }
        counts.feedback_targets.add(target);
    }
    let action = str_field(entry, "feedback_action");
    if !action.is_empty() {
        counts.feedback_actions.add(action.to_owned());
    }
    if entry.get("prompt_feedback_detected") == Some(&Value::Bool(true))
        && field_values(entry, "feedback_labels").is_empty()
    {
        add_quality(counts, "feedback_detected_without_labels");
    }
    let skills = field_values(entry, "skills");
    let has_candidates = !field_values(entry, "candidate_skills").is_empty()
        || !field_values(entry, "candidate_workflows").is_empty()
        || !field_values(entry, "candidate_tools").is_empty()
        || !field_values(entry, "feedback_labels").is_empty();
    let mut accepted = Vec::new();
    for skill in skills {
        if !trusted {
            add_quality(counts, "tool_input_skill_usage_ignored");
            add_quality(counts, &format!("tool_input_skill_usage_ignored:{skill}"));
            continue;
        }
        if !known_skills.is_empty() && !known_skills.contains(&skill) {
            add_quality(counts, "noncanonical_skill_usage_ignored");
            add_quality(counts, &format!("noncanonical_skill_usage_ignored:{skill}"));
            continue;
        }
        if in_skill_window(&skill, reset_epochs) {
            accepted.push(skill);
        } else {
            add_quality(counts, "skill_routing_signal_before_cutover_ignored");
            add_quality(
                counts,
                &format!("skill_routing_signal_before_cutover_ignored:{skill}"),
            );
        }
    }
    if accepted.is_empty() && !has_candidates {
        add_quality(counts, "empty_skill_usage");
    }
    for skill in accepted {
        counts.skills.add(skill.clone());
        counts.skill_events.add(format!("{skill}@{event}"));
    }
}

fn collect_evidence(
    requested_root: &Path,
    runtime_root: Option<&Path>,
) -> Result<Evidence, String> {
    let root = fs::canonicalize(requested_root)
        .map_err(|error| format!("resolve source root: {error}"))?;
    let hook_files = match hook_paths(requested_root, &root, runtime_root) {
        Ok(paths) => paths,
        Err(error) if error.starts_with("AgentCanon log archive root is required;") => Vec::new(),
        Err(error) => return Err(error),
    };
    let known = known_skill_ids(&root);
    let mut counts = EvidenceCounts::default();
    let mut reset_epochs = BTreeMap::new();
    let mut records = Vec::new();
    for path in &hook_files {
        let name = path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("");
        if name == SKILL_USAGE_FILE {
            for entry in read_skill_usage_records(path)? {
                counts.files.add(name.to_owned());
                records.push((path.clone(), entry.clone()));
                add_hook_entry(&mut counts, path, &entry, &known, &mut reset_epochs, &root);
            }
            continue;
        }
        let text = fs::read_to_string(path)
            .map_err(|error| format!("read hook log {}: {error}", path.display()))?;
        for line in text.lines().filter(|line| !line.trim().is_empty()) {
            counts.files.add(name.to_owned());
            match serde_json::from_str::<Value>(line) {
                Ok(value @ Value::Object(_)) => {
                    records.push((path.clone(), value.clone()));
                    add_hook_entry(&mut counts, path, &value, &known, &mut reset_epochs, &root)
                }
                Ok(_) => {
                    counts.statuses.add("invalid_entry");
                    add_quality(&mut counts, "invalid_entry");
                }
                Err(_) => {
                    counts.statuses.add("invalid_json");
                    add_quality(&mut counts, "invalid_json");
                }
            }
        }
    }
    Ok(Evidence {
        root,
        issue_refs: add_issue_refs(requested_root, runtime_root),
        knowledge_entries: knowledge_entries(),
        records,
        counts,
    })
}

fn evidence_summary_lines(evidence: &Evidence) -> Vec<String> {
    let c = &evidence.counts;
    vec![
        format!("- evidence_root: `{}`", evidence.root.display()),
        format!("- github_issue_refs: `{}`", evidence.issue_refs.len()),
        format!(
            "- knowledge_entries: `{}`",
            evidence.knowledge_entries.values().sum::<u64>()
        ),
        format!("- hook_status_counts: `{}`", c.statuses.python_repr()),
        format!("- hook_file_counts: `{}`", c.files.python_repr()),
        format!("- hook_event_counts: `{}`", c.events.python_repr()),
        format!("- hook_namespace_counts: `{}`", c.namespaces.python_repr()),
        format!("- hook_tool_counts: `{}`", c.tools.python_repr()),
        format!("- skill_usage_counts: `{}`", c.skills.python_repr()),
        format!(
            "- prompt_candidate_skill_counts: `{}`",
            c.candidate_skills.python_repr()
        ),
        format!(
            "- prompt_candidate_workflow_counts: `{}`",
            c.candidate_workflows.python_repr()
        ),
        format!(
            "- prompt_candidate_tool_counts: `{}`",
            c.candidate_tools.python_repr()
        ),
        format!("- skill_source_counts: `{}`", c.skill_sources.python_repr()),
        format!(
            "- human_feedback_label_counts: `{}`",
            c.feedback_labels.python_repr()
        ),
        format!(
            "- human_feedback_target_counts: `{}`",
            c.feedback_targets.python_repr()
        ),
        format!(
            "- human_feedback_action_counts: `{}`",
            c.feedback_actions.python_repr()
        ),
        format!(
            "- hook_failure_target_counts: `{}`",
            c.failure_targets.python_repr()
        ),
        format!("- hook_quality_counts: `{}`", c.quality.python_repr()),
    ]
}

fn named_section(name: &str, lines: Vec<String>) -> Vec<String> {
    let mut output = vec![format!("## {name}"), String::new()];
    output.extend(lines);
    output.push(String::new());
    output
}

fn render_guide(evidence: &Evidence) -> String {
    let mut lines = vec![
        "# Agent Improvement Guide".into(), String::new(), "<!--".into(), "@dependency-start".into(),
        "responsibility Records generated AgentCanon improvement guidance.".into(),
        "upstream implementation tools/runtime/dispatch/agent-canon/src/agent_runtime_dashboard.rs generates this report".into(),
        "@dependency-end".into(), "-->".into(), String::new(),
        "This generated guide reports observations from the scanned inputs.".into(),
        "It does not establish a repair scope or authorize changes.".into(), String::new(),
        "## Evidence Summary".into(), String::new(),
    ];
    lines.extend(evidence_summary_lines(evidence));
    lines.push(String::new());
    let mut guidance = Vec::new();
    if !evidence.issue_refs.is_empty() {
        guidance.push("- Use linked Issues to confirm the current owner and authorized scope; their presence does not make resolving every Issue part of this task.".to_owned());
    }
    if !evidence.counts.failures.0.is_empty() {
        guidance.push("- Inspect repeated hook failure fingerprints to locate the concrete cause before choosing an in-scope repair.".to_owned());
    }
    if !evidence.counts.failure_targets.0.is_empty() {
        guidance.push("- Observed Failure Targets are affected inputs, not established cause locations; trace the failing operation to its responsible code.".to_owned());
    }
    if !evidence.counts.checker_targets.0.is_empty() {
        guidance.push("- Inspect repeated checker targets against the selected contract; decide whether the tool, skill, or target code owns the cause.".to_owned());
    }
    if !evidence.counts.quality.0.is_empty() {
        guidance.push("- Treat missing or historical fields as observability limits until the producing contract establishes that those fields were required.".to_owned());
    }
    if guidance.is_empty() {
        guidance.push("- No failing hook evidence was found in the scanned inputs.".into());
    }
    lines.extend(named_section("Improvement Guidance", guidance));
    for (name, counter) in [
        ("Skill Usage Evidence", &evidence.counts.skills),
        ("Prompt Candidate Skills", &evidence.counts.candidate_skills),
        (
            "Prompt Candidate Workflows",
            &evidence.counts.candidate_workflows,
        ),
        ("Prompt Candidate Tools", &evidence.counts.candidate_tools),
        ("Skill Event Coverage", &evidence.counts.skill_events),
        ("Skill Source Fields", &evidence.counts.skill_sources),
        ("Human Feedback Labels", &evidence.counts.feedback_labels),
        ("Human Feedback Targets", &evidence.counts.feedback_targets),
        ("Human Feedback Actions", &evidence.counts.feedback_actions),
        ("Hook Runtime Namespaces", &evidence.counts.namespaces),
        ("Hook Tool Evidence", &evidence.counts.tools),
        ("Code Checker Targets", &evidence.counts.checker_targets),
        ("Observed Failure Targets", &evidence.counts.failure_targets),
        ("Hook Observability Counters", &evidence.counts.quality),
    ] {
        lines.extend(named_section(name, counter.markdown(MAX_COUNTER_LINES)));
    }
    lines.extend(named_section(
        "GitHub Issues",
        evidence
            .issue_refs
            .iter()
            .map(|value| format!("- {value}"))
            .collect::<Vec<_>>()
            .into_iter()
            .chain(if evidence.issue_refs.is_empty() {
                vec!["- No repository-qualified Issue URL in the scanned private packets.".into()]
            } else {
                Vec::new()
            })
            .collect(),
    ));
    lines.extend(named_section(
        "Repeated Hook Failures",
        evidence.counts.failures.markdown(MAX_FAILURE_LINES),
    ));
    let knowledge = evidence
        .knowledge_entries
        .iter()
        .map(|(path, count)| format!("- `{path}`: `{count}`"))
        .collect();
    lines.extend(named_section("Private Knowledge Entry Counts", knowledge));
    lines.join("\n")
}

fn is_recent(path: &Path, epoch: Option<i64>) -> bool {
    epoch.is_none_or(|cutoff| {
        path.metadata()
            .ok()
            .and_then(|meta| meta.modified().ok())
            .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
            .is_some_and(|time| time.as_secs() as i64 >= cutoff)
    })
}

fn report_status(path: &Path) -> String {
    let name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("");
    if name.contains("-fail") {
        return "fail".into();
    }
    if name.contains("-skip") {
        return "skip".into();
    }
    if name.contains("-pass") {
        return "pass".into();
    }
    fs::read_to_string(path)
        .ok()
        .and_then(|text| {
            text.split("STATUS=").find_map(|part| {
                let value = part
                    .split(|ch: char| !ch.is_ascii_alphabetic())
                    .next()
                    .unwrap_or("");
                ["pass", "fail", "skip"]
                    .contains(&value)
                    .then(|| value.to_owned())
            })
        })
        .unwrap_or_else(|| "unknown".into())
}

fn result_families(
    root: &Path,
    runtime_root: Option<&Path>,
    cutoff: Option<i64>,
) -> Result<Vec<ResultFamily>, String> {
    ["workflow-selection", "codex-agent-role"]
        .into_iter()
        .map(|family| {
            let directories = match eval_result_search_dirs(root, family, runtime_root) {
                Ok(directories) => directories,
                Err(error) if error.starts_with("AgentCanon log archive root is required;") => {
                    vec![root.join("agents/evals/results").join(family)]
                }
                Err(error) => return Err(error),
            };
            let mut reports = BTreeSet::new();
            for directory in &directories {
                if let Ok(entries) = fs::read_dir(directory) {
                    for entry in entries.flatten() {
                        let path = entry.path();
                        if path.extension().and_then(|value| value.to_str()) == Some("md")
                            && path.file_name().and_then(|value| value.to_str())
                                != Some("README.md")
                            && is_recent(&path, cutoff)
                        {
                            reports.insert(path);
                        }
                    }
                }
            }
            let mut statuses = Counter::default();
            for path in &reports {
                statuses.add(report_status(path));
            }
            Ok(ResultFamily {
                family: family.into(),
                directory: directories[0].clone(),
                reports: reports.into_iter().collect(),
                statuses,
            })
        })
        .collect()
}

fn valid_source_sync(path: &Path) -> Option<Value> {
    if fs::symlink_metadata(path).ok()?.file_type().is_symlink() {
        return None;
    }
    let value: Value = serde_json::from_slice(&fs::read(path).ok()?).ok()?;
    let object = value.as_object()?;
    let required = [
        "status",
        "code",
        "source_root",
        "source_head",
        "source_tree",
        "remote",
        "branch",
        "updated_at",
    ];
    if object.get("schema")?.as_str()? != SOURCE_SYNC_SCHEMA
        || required.iter().any(|key| !object.contains_key(*key))
        || !object.contains_key("remote_url")
    {
        return None;
    }
    let expected_len = required.len() + 2 + usize::from(object.contains_key("failure"));
    if object.len() != expected_len
        || object.keys().any(|key| {
            !required.contains(&key.as_str())
                && !["schema", "remote_url", "failure"].contains(&key.as_str())
        })
    {
        return None;
    }
    let status = object.get("status")?.as_str()?;
    let code = object.get("code")?.as_str()?;
    let source_root = object.get("source_root")?.as_str()?;
    let head = object.get("source_head")?.as_str()?;
    let tree = object.get("source_tree")?.as_str()?;
    let remote = object.get("remote")?.as_str()?;
    let branch = object.get("branch")?.as_str()?;
    let updated = object.get("updated_at")?.as_str()?;
    let remote_url = object.get("remote_url")?.as_str()?;
    let valid_identity = |value: &str| {
        value == "unknown"
            || (value.len() == 40
                && value
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
    };
    let valid_code = |value: &str| {
        !value.is_empty()
            && value.as_bytes()[0].is_ascii_lowercase()
            && value
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
    };
    if !["success", "failed"].contains(&status)
        || !valid_code(code)
        || !source_root.starts_with('/')
        || !valid_identity(head)
        || !valid_identity(tree)
        || remote.is_empty()
        || !remote
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_.-".contains(&b))
        || branch.is_empty()
        || !branch
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._/-".contains(&b))
        || !updated.ends_with('Z')
        || time::OffsetDateTime::parse(updated, &time::format_description::well_known::Rfc3339)
            .is_err()
        || remote_url.is_empty()
        || remote_url
            .chars()
            .any(|value| value == '"' || value == '\\')
        || source_root.bytes().any(|b| b < 0x20)
        || remote_url.bytes().any(|b| b < 0x20)
    {
        return None;
    }
    if status == "failed" {
        if !valid_code(object.get("failure")?.as_str()?) {
            return None;
        }
    } else if object.contains_key("failure") {
        return None;
    }
    let mut clean = Map::new();
    for key in required {
        clean.insert(key.into(), object.get(key)?.clone());
    }
    clean.insert("remote_url".into(), object.get("remote_url")?.clone());
    if status == "failed" {
        clean.insert("failure".into(), object.get("failure")?.clone());
    }
    Some(Value::Object(clean))
}

fn hook_family(path: &Path) -> String {
    let stem = path
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("unknown");
    let mut family = stem.to_owned();
    if let Some((base, suffix)) = stem.rsplit_once('-') {
        if suffix == "no-git-head"
            || (suffix.len() >= 7
                && suffix.len() <= 40
                && suffix.bytes().all(|b| b.is_ascii_hexdigit()))
        {
            family = base.to_owned();
        }
    }
    family
}

fn selected_values(entry: &Value, path: &Path, responsibility: &str) -> Vec<String> {
    let mut result = Vec::new();
    let mut add = |value: Option<&Value>| match value {
        Some(Value::String(value)) if !value.is_empty() => result.push(value.clone()),
        Some(Value::Array(values)) => result.extend(
            values
                .iter()
                .filter_map(Value::as_str)
                .filter(|value| !value.is_empty())
                .map(str::to_owned),
        ),
        _ => {}
    };
    match responsibility {
        "skill" => {
            add(entry.get("skills"));
            if hook_family(path) == "oop_readability_guard" {
                result.push("oop-readability-check".into());
            }
        }
        "workflow" => {
            for key in [
                "workflows",
                "workflow",
                "workflow_family",
                "selected_workflow",
            ] {
                add(entry.get(key));
            }
        }
        "tool" => {
            add(entry.get("tool_name"));
            add(entry.get("tool_command_verb"));
            add(entry.get("selected_tools"));
            for command_entry in entry
                .get("commands")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
            {
                if let Some(command) = command_entry.get("command").and_then(Value::as_array) {
                    let mut first = true;
                    for part in command.iter().filter_map(Value::as_str) {
                        if first
                            || part.contains("tools/")
                                && (part.ends_with(".py") || part.ends_with(".sh"))
                        {
                            result.push(part.rsplit('/').next().unwrap_or(part).to_owned());
                        }
                        first = false;
                    }
                }
            }
        }
        _ => {}
    }
    let mut unique = BTreeSet::new();
    result.retain(|value| unique.insert(value.clone()));
    result
}

fn candidate_values(entry: &Value, responsibility: &str) -> Vec<String> {
    let key = match responsibility {
        "skill" => "candidate_skills",
        "workflow" => "candidate_workflows",
        "tool" => "candidate_tools",
        _ => return Vec::new(),
    };
    let candidates = values(entry.get(key));
    if responsibility != "skill" {
        return candidates;
    }
    let reasons = values(entry.get("candidate_skill_reasons"));
    if reasons.is_empty() {
        let event = str_field(entry, "hook_event_name");
        let event = if event.is_empty() {
            str_field(entry, "event")
        } else {
            event
        };
        if (event.is_empty() || event == "UnknownHookEvent")
            && values(entry.get("prompt")).is_empty()
            && values(entry.get("last_assistant_message")).is_empty()
        {
            return Vec::new();
        }
        return candidates;
    }
    candidates
        .into_iter()
        .filter(|candidate| {
            let candidate_reasons = reasons
                .iter()
                .filter_map(|reason| {
                    reason
                        .split_once(':')
                        .filter(|(skill, _)| *skill == candidate)
                        .map(|(_, detail)| detail)
                })
                .collect::<Vec<_>>();
            candidate_reasons.is_empty()
                || candidate_reasons
                    .iter()
                    .any(|detail| !detail.contains("related_to="))
        })
        .collect()
}

fn canonical_selection(responsibility: &str, value: &str) -> String {
    let normalized = value.trim().trim_start_matches('$').to_owned();
    if responsibility == "tool" {
        return match normalized.as_str() {
            "docs check" | "docs format" | "docs links" => "agent-canon-cli".into(),
            _ => normalized,
        };
    }
    if responsibility == "workflow" {
        let normalized = normalized.to_ascii_lowercase();
        let mut output = String::new();
        let mut dash = false;
        for ch in normalized.chars() {
            if ch.is_ascii_alphanumeric() {
                output.push(ch);
                dash = false;
            } else if !dash && !output.is_empty() {
                output.push('-');
                dash = true;
            }
        }
        return output.trim_matches('-').to_owned();
    }
    normalized
}

fn known_workflow_names(root: &Path) -> BTreeSet<String> {
    let Ok(text) = fs::read_to_string(root.join("agents/task_catalog.yaml")) else {
        return BTreeSet::new();
    };
    let mut active = false;
    let mut names = BTreeSet::new();
    for line in text.lines() {
        if line.trim() == "workflow_families:" {
            active = true;
            continue;
        }
        if active && !line.is_empty() && !line.starts_with(' ') {
            break;
        }
        if active {
            if let Some(value) = line.trim().strip_prefix("- id:") {
                names.insert(canonical_selection("workflow", value.trim()));
            }
        }
    }
    names
}

fn known_component(
    responsibility: &str,
    name: &str,
    known_skills: &BTreeSet<String>,
    known_workflows: &BTreeSet<String>,
) -> bool {
    if responsibility == "skill" && !known_skills.is_empty() {
        return known_skills.contains(name);
    }
    if responsibility == "workflow" && !known_workflows.is_empty() {
        return known_workflows.contains(name);
    }
    true
}

fn reset_info(root: &Path, responsibility: &str, name: &str) -> (String, i64, String) {
    let slug = name.trim_start_matches('$');
    if slug.is_empty()
        || slug.split('/').any(|part| {
            part.is_empty()
                || part == "."
                || part == ".."
                || !part
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || b"_.-".contains(&byte))
        })
        || (responsibility != "tool" && slug.contains('/'))
    {
        return (
            "untracked-or-unknown".into(),
            0,
            "untracked-or-unknown".into(),
        );
    }
    let paths: Vec<PathBuf> = match responsibility {
        "skill" => vec![
            PathBuf::from(format!(".agents/skills/{slug}/SKILL.md")),
            PathBuf::from(format!("agents/skills/{slug}.md")),
        ],
        "workflow" => vec![
            PathBuf::from(format!("agents/workflows/{slug}.md")),
            PathBuf::from(format!("agents/workflows/{slug}-workflow.md")),
            PathBuf::from(format!(".agents/skills/{slug}/SKILL.md")),
            PathBuf::from("agents/TASK_WORKFLOWS.md"),
        ],
        "tool" if slug.contains('/') => vec![PathBuf::from(slug)],
        "tool" => [
            ".codex/hooks",
            "tools/agent",
            "tools/agent/orchestration",
            "tools/agent/skills",
            "tools/agent/templates",
            "tools/analysis/code",
            "tools/analysis/dependencies",
            "tools/repository/github",
            "tools/repository/git",
            "tools/repository/workspace",
            "tools/runtime/archive",
            "tools/runtime/artifacts",
            "tools/runtime/authority",
            "tools/runtime/lifecycle",
            "tools/runtime/manifest",
            "tools/runtime/source",
            "tools/validation/dependencies",
            "tools/validation/semantic",
            "tools/ci",
            "tools/docs",
            "tools/oop/python",
            "tools",
        ]
        .into_iter()
        .map(|directory| PathBuf::from(directory).join(slug))
        .collect(),
        _ => Vec::new(),
    };
    let mut resets = Vec::new();
    for path in paths.iter().filter(|path| root.join(path).exists()) {
        let output = Command::new("git")
            .arg("-C")
            .arg(root)
            .args(["log", "-1", "--format=%ct%x00%H", "--"])
            .arg(path)
            .output();
        let reset = output
            .ok()
            .filter(|output| output.status.success())
            .and_then(|output| {
                let raw = String::from_utf8_lossy(&output.stdout);
                let (epoch, commit) = raw.trim().split_once('\0')?;
                Some((
                    path.display().to_string(),
                    epoch.parse::<i64>().ok()?,
                    commit.chars().take(12).collect::<String>(),
                ))
            })
            .unwrap_or_else(|| (path.display().to_string(), 0, "untracked-or-unknown".into()));
        resets.push(reset);
    }
    resets
        .into_iter()
        .max_by_key(|reset| reset.1)
        .unwrap_or_else(|| {
            (
                "untracked-or-unknown".into(),
                0,
                "untracked-or-unknown".into(),
            )
        })
}

fn read_receipts(root: &Path, runtime_root: Option<&Path>) -> Vec<IssueReceipt> {
    let mut roots = BTreeSet::new();
    if let Some(path) = env::var_os("AGENT_CANON_LOG_ROOT") {
        roots.insert(PathBuf::from(path));
    }
    if let Ok(path) = mounted_log_archive_root(root, runtime_root) {
        roots.insert(path);
    }
    let mut receipts = BTreeMap::new();
    for base in roots {
        let published = base.join(ISSUE_PACKET_DIR).join("published");
        if !published.is_dir()
            || published
                .symlink_metadata()
                .is_ok_and(|meta| meta.file_type().is_symlink())
        {
            continue;
        }
        let Ok(owners) = fs::read_dir(&published) else {
            continue;
        };
        for owner in owners.flatten() {
            let owner_path = owner.path();
            if !owner_path.is_dir()
                || owner_path
                    .symlink_metadata()
                    .is_ok_and(|m| m.file_type().is_symlink())
            {
                continue;
            }
            let Ok(repos) = fs::read_dir(&owner_path) else {
                continue;
            };
            for repo in repos.flatten() {
                let repo_path = repo.path();
                if !repo_path.is_dir()
                    || repo_path
                        .symlink_metadata()
                        .is_ok_and(|m| m.file_type().is_symlink())
                {
                    continue;
                }
                let Ok(files) = fs::read_dir(&repo_path) else {
                    continue;
                };
                for file in files.flatten() {
                    let path = file.path();
                    if path.extension().and_then(|v| v.to_str()) != Some("json")
                        || path
                            .symlink_metadata()
                            .is_ok_and(|m| m.file_type().is_symlink())
                    {
                        continue;
                    }
                    let Ok(value) = fs::read(&path)
                        .map_err(|_| ())
                        .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).map_err(|_| ()))
                    else {
                        continue;
                    };
                    let Some(object) = value.as_object() else {
                        continue;
                    };
                    let expected = [
                        "repository",
                        "number",
                        "url",
                        "state",
                        "action",
                        "responsibility",
                        "occurrence_locations",
                        "source_finding_kind",
                        "timestamp",
                    ];
                    if object.len() != expected.len()
                        || expected.iter().any(|key| !object.contains_key(*key))
                    {
                        continue;
                    }
                    let (Some(repository), Some(number), Some(url), Some(action), Some(state)) = (
                        value["repository"].as_str(),
                        value["number"].as_str(),
                        value["url"].as_str(),
                        value["action"].as_str(),
                        value["state"].as_str(),
                    ) else {
                        continue;
                    };
                    if value["source_finding_kind"].as_str().is_none()
                        || value["timestamp"].as_str().is_none()
                        || !value["responsibility"].is_array()
                        || !value["occurrence_locations"].is_array()
                    {
                        continue;
                    }
                    if !["create", "update", "reopen", "reorganize", "noop"].contains(&action) {
                        continue;
                    }
                    let Ok(reference) = issue_sync::reference(url, repository) else {
                        continue;
                    };
                    let Ok(state) = issue_sync::state(state) else {
                        continue;
                    };
                    if reference.repo != repository
                        || reference.number != number
                        || reference.url != url
                    {
                        continue;
                    }
                    let Some(path_number) = path.file_stem().and_then(|v| v.to_str()) else {
                        continue;
                    };
                    if path_number != number
                        || format!(
                            "{}/{}",
                            owner.file_name().to_string_lossy(),
                            repo.file_name().to_string_lossy()
                        ) != repository
                    {
                        continue;
                    }
                    let strings = |key: &str| {
                        value[key]
                            .as_array()
                            .map(|items| {
                                items
                                    .iter()
                                    .filter_map(Value::as_str)
                                    .map(str::trim)
                                    .filter(|v| !v.is_empty())
                                    .map(str::to_owned)
                                    .collect::<Vec<_>>()
                            })
                            .unwrap_or_default()
                    };
                    let receipt = IssueReceipt {
                        repository: repository.into(),
                        number: number.into(),
                        url: url.into(),
                        state,
                        action: action.into(),
                        responsibility: strings("responsibility"),
                        occurrence_locations: strings("occurrence_locations"),
                        source_finding_kind: value["source_finding_kind"]
                            .as_str()
                            .unwrap_or("")
                            .into(),
                        timestamp: value["timestamp"].as_str().unwrap_or("").into(),
                    };
                    receipts.insert(
                        (receipt.repository.clone(), receipt.number.clone()),
                        receipt,
                    );
                }
            }
        }
    }
    let mut values = receipts.into_values().collect::<Vec<_>>();
    values.sort_by(|left, right| {
        left.repository
            .cmp(&right.repository)
            .then_with(|| left.number.len().cmp(&right.number.len()))
            .then_with(|| left.number.cmp(&right.number))
    });
    values
}

fn dashboard_outputs(
    options: &Options,
    evidence: &Evidence,
    cutoff: Option<i64>,
) -> Result<(String, String, String, usize, usize), String> {
    let token = crate::dashboard_token_usage::read(
        &evidence.root,
        cutoff,
        options.runtime_root.as_deref(),
    )?;
    let mut records = Vec::new();
    let mut files = BTreeSet::new();
    for (path, entry) in &evidence.records {
        let epoch = hook_epoch(entry);
        let recent = cutoff.is_none_or(|cutoff| {
            epoch.map_or_else(|| is_recent(path, Some(cutoff)), |value| value >= cutoff)
        });
        if recent {
            records.push((path, entry));
            files.insert(path.clone());
        }
    }
    // Selection confirmation follows source file/event order; workflow attribution
    // and prompt/token trends use timestamp order below.
    let selection_records = records.clone();
    let mut ordered = records
        .into_iter()
        .enumerate()
        .map(|(index, record)| {
            let epoch = hook_epoch(record.1)
                .filter(|value| *value > 0)
                .unwrap_or(index as i64);
            (epoch, index, record)
        })
        .collect::<Vec<_>>();
    ordered.sort_by_key(|(epoch, index, _)| (*epoch, *index));
    let records = ordered
        .into_iter()
        .map(|(_, _, record)| record)
        .collect::<Vec<_>>();
    let receipts = read_receipts(&evidence.root, options.runtime_root.as_deref());
    let mut refs = evidence.issue_refs.iter().cloned().collect::<BTreeSet<_>>();
    let mut receipt_actions = Counter::default();
    for receipt in &receipts {
        refs.insert(receipt.url.clone());
        receipt_actions.add(receipt.action.clone());
    }
    let mut status_by_family: BTreeMap<String, Counter> = BTreeMap::new();
    let mut failure_by_family: BTreeMap<String, Counter> = BTreeMap::new();
    let mut skip_by_family: BTreeMap<String, Counter> = BTreeMap::new();
    let mut unknown_by_file = Counter::default();
    let mut namespace_debt = Counter::default();
    let mut oop_applicable = 0u64;
    let mut oop_not_applicable = 0u64;
    let mut oop_missing_reason = 0u64;
    let mut oop_reasons: BTreeMap<String, Counter> = BTreeMap::new();
    let mut qualified = 0usize;
    let mut routeable = 0usize;
    let mut handoff = 0usize;
    let mut no_action = 0usize;
    let mut reasons = Counter::default();
    let mut handoffs = Vec::new();
    let known_skills = known_skill_ids(&evidence.root);
    let known_workflows = known_workflow_names(&evidence.root);
    let mut hook_counts = EvidenceCounts::default();
    let mut hook_reset_epochs = BTreeMap::new();
    let mut latest_workflows: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut workflow_counts = Counter::default();
    let mut workflow_events = Counter::default();
    let mut missing_workflow_by_file = Counter::default();
    let mut missing_workflow_events = Counter::default();
    let mut missing_workflow_namespaces = Counter::default();
    let mut missing_workflow_statuses = Counter::default();
    let mut missing_workflow_tools = Counter::default();
    let mut entries_with_workflow = 0usize;
    let mut entries_without_workflow = 0usize;
    let mut context_attributed_entries = 0usize;
    let mut prompt_entries = 0usize;
    let mut prompt_excerpt_entries = 0usize;
    let mut prompt_missing_excerpt_entries = 0usize;
    let mut prompt_total_chars = 0u64;
    let mut prompt_char_counts = Vec::new();
    let mut timed_prompt_char_counts = Vec::new();
    let mut tool_selection_entries = 0usize;
    let mut prompt_tools = Counter::default();
    let mut command_verbs = Counter::default();
    let mut selected_tools = Counter::default();
    let mut reference_entries = 0usize;
    let mut reference_url_observations = 0u64;
    let mut reference_registered_observations = 0u64;
    let mut reference_missing_observations = 0u64;
    let mut reference_blocked_entries = 0usize;
    let mut reference_source_fields = Counter::default();
    let mut reference_events = Counter::default();
    let mut reference_urls = Counter::default();
    let mut registered_urls = Counter::default();
    let mut missing_urls = Counter::default();
    for (path, entry) in &records {
        let file_name = path.file_name().and_then(|v| v.to_str()).unwrap_or("");
        hook_counts.files.add(file_name.to_owned());
        add_hook_entry(
            &mut hook_counts,
            path,
            entry,
            &known_skills,
            &mut hook_reset_epochs,
            &evidence.root,
        );
        let namespace = {
            let value = str_field(entry, "hook_log_namespace");
            if value.is_empty() {
                "missing_namespace".to_owned()
            } else {
                value.to_owned()
            }
        };
        let canonical = str_field(entry, "schema") == "agent-canon.behavior-event.v1";
        let attribution = str_field(entry, "workflow_attribution_kind");
        let mut workflows = Vec::new();
        let mut inherited = false;
        if canonical {
            let field = if attribution == "owner" {
                "workflow_owner_workflows"
            } else if attribution == "context" {
                "workflow_context_workflows"
            } else {
                ""
            };
            workflows = values((!field.is_empty()).then(|| entry.get(field)).flatten());
            inherited = attribution == "context";
        } else {
            for field in [
                "workflows",
                "workflow",
                "workflow_family",
                "selected_workflow",
                "workflow_owner_workflows",
                "workflow_context_workflows",
            ] {
                workflows.extend(values(entry.get(field)));
            }
            workflows.sort();
            workflows.dedup();
            if workflows.is_empty() {
                workflows = latest_workflows
                    .get(&namespace)
                    .cloned()
                    .unwrap_or_default();
                inherited = !workflows.is_empty();
            } else {
                latest_workflows.insert(namespace.clone(), workflows.clone());
            }
        }
        context_attributed_entries += usize::from(inherited);
        if workflows.is_empty() {
            entries_without_workflow += 1;
            let label = path
                .strip_prefix(&evidence.root)
                .unwrap_or(path)
                .to_string_lossy()
                .to_string();
            missing_workflow_by_file.add(label);
            let event = str_field(entry, "hook_event_name");
            missing_workflow_events.add(if event.is_empty() {
                let event = str_field(entry, "event");
                if event.is_empty() {
                    "missing_event"
                } else {
                    event
                }
            } else {
                event
            });
            missing_workflow_namespaces.add(namespace);
            let status = str_field(entry, "status");
            missing_workflow_statuses.add(if status.is_empty() {
                "missing_status"
            } else {
                status
            });
            let tool = str_field(entry, "tool_name");
            let tool = if tool.is_empty() {
                str_field(entry, "tool_command_verb")
            } else {
                tool
            };
            if !tool.is_empty() {
                missing_workflow_tools.add(tool);
            }
        } else {
            entries_with_workflow += 1;
            let event = str_field(entry, "hook_event_name");
            let event = if event.is_empty() {
                let value = str_field(entry, "event");
                if value.is_empty() {
                    "missing_event"
                } else {
                    value
                }
            } else {
                event
            };
            for workflow in workflows {
                workflow_counts.add(workflow.clone());
                workflow_events.add(format!("{workflow}@{event}"));
            }
        }
        if str_field(entry, "prompt_capture_status") == "present" {
            let chars = entry
                .get("prompt_char_count")
                .and_then(Value::as_u64)
                .unwrap_or(0);
            prompt_entries += 1;
            prompt_total_chars += chars;
            prompt_char_counts.push(chars);
            if let Some(epoch) = hook_epoch(entry) {
                timed_prompt_char_counts.push(json!({"epoch":epoch,"value":chars}));
            }
            if str_field(entry, "prompt_excerpt_redacted").is_empty() {
                prompt_missing_excerpt_entries += 1;
            } else {
                prompt_excerpt_entries += 1;
            }
        }
        let tool_name = str_field(entry, "tool_name");
        if !tool_name.is_empty() {
            tool_selection_entries += 1;
            prompt_tools.add(tool_name);
        }
        let command_verb = str_field(entry, "tool_command_verb");
        if !command_verb.is_empty() {
            command_verbs.add(command_verb);
        }
        for tool in values(entry.get("selected_tools")) {
            selected_tools.add(tool);
        }
        if entry.get("url_count").is_some()
            || str_field(entry, "hook_name") == "reference_capture_guard"
        {
            reference_entries += 1;
            reference_url_observations +=
                entry.get("url_count").and_then(Value::as_u64).unwrap_or(0);
            reference_registered_observations += entry
                .get("registered_count")
                .and_then(Value::as_u64)
                .unwrap_or(0);
            reference_missing_observations += entry
                .get("missing_count")
                .and_then(Value::as_u64)
                .unwrap_or(0);
            reference_blocked_entries += usize::from(str_field(entry, "decision") == "block");
            let event = str_field(entry, "hook_event_name");
            reference_events.add(if event.is_empty() {
                let event = str_field(entry, "event");
                if event.is_empty() {
                    "missing_event"
                } else {
                    event
                }
            } else {
                event
            });
            for value in values(entry.get("source_fields")) {
                reference_source_fields.add(value);
            }
            for value in values(entry.get("urls")) {
                reference_urls.add(value);
            }
            for value in values(entry.get("registered_urls")) {
                registered_urls.add(value);
            }
            for value in values(entry.get("missing_urls")) {
                missing_urls.add(value);
            }
        }
    }
    let mut selection: BTreeMap<(String, String), (u64, u64, u64)> = BTreeMap::new();
    let mut selection_resets: BTreeMap<(String, String), (String, i64, String)> = BTreeMap::new();
    let mut filtered_observations = 0usize;
    let mut future_selection: BTreeMap<(String, String, String), Vec<usize>> = BTreeMap::new();
    for (sequence, (path, entry)) in selection_records.iter().enumerate() {
        let namespace = {
            let value = str_field(entry, "hook_log_namespace");
            if value.is_empty() {
                path.parent()
                    .and_then(Path::file_name)
                    .and_then(|v| v.to_str())
                    .unwrap_or("missing_namespace")
                    .to_owned()
            } else {
                value.to_owned()
            }
        };
        for responsibility in ["skill", "workflow", "tool"] {
            for name in selected_values(entry, path, responsibility) {
                let canonical = canonical_selection(responsibility, &name);
                if !known_component(responsibility, &canonical, &known_skills, &known_workflows) {
                    continue;
                }
                let key = (namespace.clone(), responsibility.into(), canonical);
                future_selection
                    .entry(key.clone())
                    .or_default()
                    .push(sequence);
                if responsibility == "workflow"
                    || responsibility == "skill" && key.2 == "oop-readability-check"
                {
                    future_selection
                        .entry(("*".into(), key.1, key.2))
                        .or_default()
                        .push(sequence);
                }
            }
        }
    }
    let mut workflow_report_selections = Vec::new();
    if let Ok(paths) = crate::dashboard_token_usage::candidate_paths(
        &evidence.root,
        options.runtime_root.as_deref(),
    ) {
        for path in paths.into_iter().filter(|path| {
            path.file_name().and_then(|v| v.to_str()) == Some("workflow_monitoring.md")
        }) {
            let Ok(text) = fs::read_to_string(&path) else {
                continue;
            };
            let epoch = crate::dashboard_token_usage::evidence_epoch(&path, &text);
            if cutoff.is_some_and(|cutoff| {
                if epoch > 0 {
                    epoch < cutoff
                } else {
                    !is_recent(&path, Some(cutoff))
                }
            }) {
                continue;
            }
            for part in text.split("workflow=").skip(1) {
                let mut value = part;
                for delimiter in [", skills=", " skills=", "\n", "\r"] {
                    if let Some(index) = value.find(delimiter) {
                        value = &value[..index];
                    }
                }
                let name = canonical_selection(
                    "workflow",
                    value.trim().trim_matches('`').trim_matches(','),
                );
                if !name.is_empty()
                    && known_component("workflow", &name, &known_skills, &known_workflows)
                {
                    workflow_report_selections.push((epoch, name));
                }
            }
        }
    }
    for (index, (_, name)) in workflow_report_selections.iter().enumerate() {
        future_selection
            .entry(("*".into(), "workflow".into(), name.clone()))
            .or_default()
            .push(selection_records.len() + index);
    }
    for (sequence, (path, entry)) in selection_records.iter().enumerate() {
        let namespace = {
            let value = str_field(entry, "hook_log_namespace");
            if value.is_empty() {
                path.parent()
                    .and_then(Path::file_name)
                    .and_then(|v| v.to_str())
                    .unwrap_or("missing_namespace")
                    .to_owned()
            } else {
                value.to_owned()
            }
        };
        for responsibility in ["skill", "workflow", "tool"] {
            let selected = selected_values(entry, path, responsibility)
                .into_iter()
                .map(|value| canonical_selection(responsibility, &value))
                .filter(|value| {
                    known_component(responsibility, value, &known_skills, &known_workflows)
                })
                .collect::<BTreeSet<_>>();
            let entry_epoch = hook_epoch(entry).unwrap_or(0);
            for value in &selected {
                let key = (responsibility.into(), value.clone());
                let reset = selection_resets
                    .entry(key.clone())
                    .or_insert_with(|| reset_info(&evidence.root, responsibility, value));
                if reset.1 == 0 || entry_epoch == 0 || entry_epoch >= reset.1 {
                    let row = selection.entry(key).or_default();
                    row.0 += 1;
                } else {
                    filtered_observations += 1;
                }
            }
            let candidates = candidate_values(entry, responsibility)
                .into_iter()
                .map(|value| canonical_selection(responsibility, &value))
                .filter(|value| {
                    known_component(responsibility, value, &known_skills, &known_workflows)
                })
                .collect::<BTreeSet<_>>();
            for value in candidates {
                if value.is_empty() {
                    continue;
                }
                let key = (responsibility.into(), value.clone());
                let reset = selection_resets
                    .entry(key.clone())
                    .or_insert_with(|| reset_info(&evidence.root, responsibility, &value));
                if reset.1 != 0 && entry_epoch != 0 && entry_epoch < reset.1 {
                    filtered_observations += 1;
                    continue;
                }
                let selected_same = selected.contains(&value);
                let later_in_namespace = future_selection
                    .get(&(namespace.clone(), responsibility.into(), value.clone()))
                    .is_some_and(|positions| {
                        positions.iter().any(|position| *position >= sequence)
                    });
                let later_cross_namespace = (responsibility == "workflow"
                    || responsibility == "skill" && value == "oop-readability-check")
                    && future_selection
                        .get(&("*".into(), responsibility.into(), value.clone()))
                        .is_some_and(|positions| !positions.is_empty());
                let future = later_in_namespace || later_cross_namespace;
                let row = selection.entry(key).or_default();
                row.1 += 1;
                if !selected_same && !future {
                    row.2 += 1;
                }
            }
        }
    }
    for (epoch, name) in &workflow_report_selections {
        let key = ("workflow".to_owned(), name.clone());
        let reset = selection_resets
            .entry(key.clone())
            .or_insert_with(|| reset_info(&evidence.root, "workflow", name));
        if reset.1 == 0 || *epoch == 0 || *epoch >= reset.1 {
            selection.entry(key).or_default().0 += 1;
        } else {
            filtered_observations += 1;
        }
    }
    let mut selection_rows = selection.iter().map(|((responsibility, name), (selected, candidate, missed))| {
        let reset = selection_resets.get(&(responsibility.clone(), name.clone())).cloned().unwrap_or_else(|| reset_info(&evidence.root, responsibility, name));
        let reset_label = if reset.1 == 0 { "untracked-or-unknown".to_owned() } else { time::OffsetDateTime::from_unix_timestamp(reset.1).ok().map(|value| format!("{:04}-{:02}-{:02}", value.year(), u8::from(value.month()), value.day())).unwrap_or_else(|| "untracked-or-unknown".into()) };
        let rate = if *candidate == 0 { "unknown".to_owned() } else { format!("{:.1}%", (*missed as f64 / *candidate as f64) * 100.0) };
        json!({"responsibility": responsibility, "name": name, "selected": selected, "candidate": candidate, "missed": missed, "miss_rate": rate, "reset_basis": if reset.0 == "untracked-or-unknown" { reset.0 } else { format!("{} {} {}", reset_label, reset.2, reset.0) }})
    }).collect::<Vec<_>>();
    selection_rows.sort_by(|left, right| {
        let order = |value: &Value| match value["responsibility"].as_str().unwrap_or("") {
            "skill" => 0,
            "workflow" => 1,
            "tool" => 2,
            _ => 3,
        };
        order(left)
            .cmp(&order(right))
            .then_with(|| right["missed"].as_u64().cmp(&left["missed"].as_u64()))
            .then_with(|| right["candidate"].as_u64().cmp(&left["candidate"].as_u64()))
            .then_with(|| left["name"].as_str().cmp(&right["name"].as_str()))
    });
    let selection_metric_rows = selection_rows.clone();
    let mut selection_misses = selection_rows
        .iter()
        .filter(|row| row["missed"].as_u64().unwrap_or(0) > 0)
        .cloned()
        .collect::<Vec<_>>();
    selection_misses.sort_by(|left, right| {
        right["missed"]
            .as_u64()
            .cmp(&left["missed"].as_u64())
            .then_with(|| {
                left["responsibility"]
                    .as_str()
                    .cmp(&right["responsibility"].as_str())
            })
            .then_with(|| left["name"].as_str().cmp(&right["name"].as_str()))
    });
    selection_misses.truncate(8);
    for (path, entry) in &records {
        let family = hook_family(path);
        let status = str_field(entry, "status");
        let status = if status.is_empty() { "unknown" } else { status };
        status_by_family
            .entry(family.clone())
            .or_default()
            .add(status);
        let event = entry
            .get("hook_event_name")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| {
                let event = str_field(entry, "event");
                if event.is_empty() {
                    "missing_event"
                } else {
                    event
                }
            });
        if ["UnknownHookEvent", "missing_event"].contains(&event) {
            unknown_by_file.add(
                path.strip_prefix(&evidence.root)
                    .unwrap_or(path)
                    .to_string_lossy()
                    .to_string(),
            );
        }
        if str_field(entry, "hook_log_namespace").trim().is_empty() {
            namespace_debt.add(family.clone());
        }
        let failure = str_field(entry, "failure_fingerprint").trim();
        if !failure.is_empty() {
            failure_by_family
                .entry(family.clone())
                .or_default()
                .add(failure);
        } else if ["fail", "warn", "error"].contains(&status) {
            failure_by_family
                .entry(family.clone())
                .or_default()
                .add(status);
        }
        if ["skip", "skipped"].contains(&status) {
            let reason = str_field(entry, "skip_reason");
            skip_by_family
                .entry(family.clone())
                .or_default()
                .add(if reason.is_empty() {
                    "missing_reason"
                } else {
                    reason
                });
        }
        if family == "oop_readability_guard" {
            let checked = entry.get("checked").and_then(Value::as_bool);
            let applicable = checked == Some(true)
                || (checked.is_none() && !["skip", "skipped", "unknown"].contains(&status));
            if applicable {
                oop_applicable += 1;
            } else {
                oop_not_applicable += 1;
                let reason = str_field(entry, "skip_reason").trim();
                if reason.is_empty() {
                    oop_missing_reason += 1;
                    oop_reasons
                        .entry(status.into())
                        .or_default()
                        .add("missing_reason");
                } else {
                    oop_reasons.entry(status.into()).or_default().add(reason);
                }
            }
        }
        for key in ["issue_worker_candidates", "issue_worker_candidate"] {
            let candidates: Vec<&Value> = match entry.get(key) {
                Some(Value::Object(_)) => vec![&entry[key]],
                Some(Value::Array(values)) => values.iter().filter(|v| v.is_object()).collect(),
                _ => Vec::new(),
            };
            for candidate in candidates {
                let authenticated = entry
                    .get("checkout_identity")
                    .and_then(|v| v.get("remote"))
                    .and_then(Value::as_str)
                    .unwrap_or("");
                let qualified_finding = issue_sync::qualify_finding(candidate, authenticated);
                let status = qualified_finding
                    .get("status")
                    .and_then(Value::as_str)
                    .unwrap_or("no-action");
                let reason = qualified_finding
                    .get("reason")
                    .and_then(Value::as_str)
                    .unwrap_or("");
                let can_route = status == "qualified"
                    || (status == "handoff"
                        && ["owner-unresolved", "fix-unresolved"].contains(&reason));
                match status {
                    "qualified" => {
                        qualified += 1;
                    }
                    "handoff" => handoff += 1,
                    "no-action" => no_action += 1,
                    _ => no_action += 1,
                }
                if can_route {
                    routeable += 1;
                }
                reasons.add(reason);
                handoffs.push(json!({"schema":qualified_finding["schema"],"status":status,"reason":reason,"repository":qualified_finding["repository"],"owner":qualified_finding["owner"],"fix":qualified_finding["fix"],"occurrence_locations":qualified_finding["occurrence_locations"],"related_issue_refs":qualified_finding["related_issue_refs"],"responsibility":qualified_finding["responsibility"],"source_finding_kind":qualified_finding["source_finding_kind"],"can_route":can_route}));
            }
        }
    }
    let nested = |mapping: &BTreeMap<String, Counter>| -> Value {
        let mut result = Map::new();
        for (key, value) in mapping {
            if !value.0.is_empty() {
                result.insert(key.clone(), value.json());
            }
        }
        Value::Object(result)
    };
    let oop_value = json!({"applicable_count":oop_applicable,"not_applicable_count":oop_not_applicable,"missing_reason_count":oop_missing_reason,"reasons_by_status":nested(&oop_reasons)});
    let hook_schema_value = json!({"unknown_event_count":unknown_by_file.total(),"unknown_events_by_file":unknown_by_file.json(),"status_by_hook_family":nested(&status_by_family),"failure_by_hook_family":nested(&failure_by_family),"skip_by_hook_family":nested(&skip_by_family),"namespace_debt_by_hook_family":namespace_debt.json(),"oop_applicability":oop_value});
    let top_failure = hook_counts
        .failures
        .sorted()
        .first()
        .map(|(name, _)| (*name).to_owned())
        .unwrap_or_else(|| "none".into());
    let mut failure_namespaces = Counter::default();
    let mut failure_events = Counter::default();
    let mut failure_tools = Counter::default();
    for (_, entry) in &records {
        if str_field(entry, "status") != "fail" {
            continue;
        }
        let fingerprint = str_field(entry, "failure_fingerprint");
        let key = if fingerprint.is_empty() {
            "fail"
        } else {
            fingerprint
        };
        if key != top_failure {
            continue;
        }
        let namespace = str_field(entry, "hook_log_namespace");
        if !namespace.is_empty() {
            failure_namespaces.add(namespace);
        }
        let event = str_field(entry, "hook_event_name");
        let event = if event.is_empty() {
            str_field(entry, "event")
        } else {
            event
        };
        if !event.is_empty() {
            failure_events.add(event);
        }
        let tool = str_field(entry, "tool_name");
        if !tool.is_empty() {
            failure_tools.add(tool);
        }
    }
    let hook_failure_drilldown = json!({"fingerprint":top_failure,"count":hook_counts.failures.get(&top_failure),"namespaces":failure_namespaces.json(),"events":failure_events.json(),"tools":failure_tools.json()});
    let source_sync = valid_source_sync(Path::new(
        "/var/lib/agent-canon/source-sync/source-sync.json",
    ));
    let families = result_families(&evidence.root, options.runtime_root.as_deref(), cutoff)?;
    let family_values = families.iter().map(|family| json!({"family":family.family,"directory":family.directory,"reports":family.reports,"failed_reports":family.reports.iter().filter(|path| report_status(path) == "fail").collect::<Vec<_>>(),"status_counts":family.statuses.json()})).collect::<Vec<_>>();
    let count_value = |counts: &EvidenceCounts| json!({"statuses":counts.statuses.json(),"failures":counts.failures.json(),"files":counts.files.json(),"events":counts.events.json(),"namespaces":counts.namespaces.json(),"tools":counts.tools.json(),"skills":counts.skills.json(),"candidate_skills":counts.candidate_skills.json(),"candidate_workflows":counts.candidate_workflows.json(),"candidate_tools":counts.candidate_tools.json(),"skill_events":counts.skill_events.json(),"skill_sources":counts.skill_sources.json(),"feedback_labels":counts.feedback_labels.json(),"feedback_targets":counts.feedback_targets.json(),"feedback_actions":counts.feedback_actions.json(),"checker_targets":counts.checker_targets.json(),"failure_targets":counts.failure_targets.json(),"quality":counts.quality.json()});
    let timed_int = |values: &[crate::dashboard_token_usage::TimedIntMetric]| {
        values
            .iter()
            .map(|value| json!({"epoch":value.epoch,"value":value.value.to_string()}))
            .collect::<Vec<_>>()
    };
    let timed_float = |values: &[crate::dashboard_token_usage::TimedFloatMetric]| {
        values
            .iter()
            .map(|value| json!({"epoch":value.epoch,"value":value.value}))
            .collect::<Vec<_>>()
    };
    let token_value = json!({"comparison_files":token.comparison_files,"comparison_count":token.comparison_count,"summary_files":token.summary_files,"summary_count":token.summary_count,"baseline_total_tokens":token.baseline_total_tokens.to_string(),"candidate_total_tokens":token.candidate_total_tokens.to_string(),"baseline_token_counts":token.baseline_token_counts.iter().map(ToString::to_string).collect::<Vec<_>>(),"candidate_token_counts":token.candidate_token_counts.iter().map(ToString::to_string).collect::<Vec<_>>(),"token_ratios":token.token_ratios,"session_count":token.session_count.to_string(),"token_event_count":token.token_event_count.to_string(),"total_tokens":token.total_tokens.to_string(),"latest_moving_average_total":token.latest_moving_average_total,"average_tokens_per_event":token.average_tokens_per_event,"timed_candidate_token_counts":timed_int(&token.timed_candidate_token_counts),"timed_token_ratios":timed_float(&token.timed_token_ratios),"objective_selected":token.objective_selected,"objective_not_selected":token.objective_not_selected});
    let selection_metrics = selection_metric_rows.iter().map(|row| {
        let responsibility = row["responsibility"].as_str().unwrap_or("").to_owned();
        let name = row["name"].as_str().unwrap_or("").to_owned();
        let reset = selection_resets.get(&(responsibility.clone(), name.clone())).cloned().unwrap_or_else(|| reset_info(&evidence.root, &responsibility, &name));
        let reset_at = if reset.1 == 0 { "untracked-or-unknown".to_owned() } else { time::OffsetDateTime::from_unix_timestamp(reset.1).ok().map(|value| format!("{:04}-{:02}-{:02}", value.year(), u8::from(value.month()), value.day())).unwrap_or_else(|| "untracked-or-unknown".into()) };
        json!({"responsibility":responsibility,"name":name,"selected_count":row["selected"],"candidate_count":row["candidate"],"missed_count":row["missed"],"reset_path":reset.0,"reset_at":reset_at,"reset_commit":reset.2})
    }).collect::<Vec<_>>();
    let mut entries_with_candidates = 0usize;
    let mut entries_with_selection = 0usize;
    for (path, entry) in &selection_records {
        let has_candidates = ["skill", "workflow", "tool"]
            .into_iter()
            .any(|responsibility| {
                candidate_values(entry, responsibility)
                    .into_iter()
                    .map(|value| canonical_selection(responsibility, &value))
                    .any(|value| {
                        known_component(responsibility, &value, &known_skills, &known_workflows)
                    })
            });
        let has_selection = ["skill", "workflow", "tool"]
            .into_iter()
            .any(|responsibility| {
                selected_values(entry, path, responsibility)
                    .into_iter()
                    .map(|value| canonical_selection(responsibility, &value))
                    .any(|value| {
                        known_component(responsibility, &value, &known_skills, &known_workflows)
                    })
            });
        entries_with_candidates += usize::from(has_candidates);
        entries_with_selection += usize::from(has_selection);
    }
    let mut workflow_attribution = Counter::default();
    workflow_attribution.add_by(
        "owner",
        entries_with_workflow.saturating_sub(context_attributed_entries) as u64,
    );
    workflow_attribution.add_by("context", context_attributed_entries as u64);
    workflow_attribution.add_by("missing", entries_without_workflow as u64);
    let hook_workflow_value = json!({"workflows":workflow_counts.json(),"workflow_events":workflow_events.json(),"missing_workflow_by_file":missing_workflow_by_file.json(),"missing_workflow_events":missing_workflow_events.json(),"missing_workflow_namespaces":missing_workflow_namespaces.json(),"missing_workflow_statuses":missing_workflow_statuses.json(),"missing_workflow_tools":missing_workflow_tools.json(),"entries_with_workflow":entries_with_workflow,"entries_without_workflow":entries_without_workflow,"context_attributed_entries":context_attributed_entries,"workflow_attribution":workflow_attribution.json()});
    let prompt_value = json!({"prompt_entries":prompt_entries,"prompt_excerpt_entries":prompt_excerpt_entries,"prompt_missing_excerpt_entries":prompt_missing_excerpt_entries,"prompt_total_chars":prompt_total_chars,"prompt_char_counts":prompt_char_counts,"timed_prompt_char_counts":timed_prompt_char_counts,"tool_selection_entries":tool_selection_entries,"tools":prompt_tools.json(),"command_verbs":command_verbs.json(),"selected_tools":selected_tools.json()});
    let markdown_tools = hook_counts
        .candidate_tools
        .0
        .iter()
        .filter(|(name, count)| {
            [
                "agent-canon-cli",
                "audit_and_fix_links.py",
                "fix_markdown_docs.py",
                "fix_markdown_headers.py",
            ]
            .contains(&name.as_str())
                && *count > 0
        })
        .map(|(name, count)| (name.clone(), *count))
        .collect::<Vec<_>>();
    let markdown_value = json!({"candidate_skill_entries":hook_counts.candidate_skills.get("md-style-check"),"candidate_tool_entries":markdown_tools.iter().map(|(_, count)| count).sum::<u64>(),"candidate_tools":markdown_tools.into_iter().collect::<BTreeMap<_,_>>()});
    let reference_value = json!({"entries":reference_entries,"url_observations":reference_url_observations,"registered_url_observations":reference_registered_observations,"missing_url_observations":reference_missing_observations,"blocked_entries":reference_blocked_entries,"source_fields":reference_source_fields.json(),"events":reference_events.json(),"urls":reference_urls.json(),"registered_urls":registered_urls.json(),"missing_urls":missing_urls.json()});
    let receipt_values = receipts.iter().map(|receipt| json!({"repository":receipt.repository,"number":receipt.number,"url":receipt.url,"state":receipt.state,"action":receipt.action,"responsibility":receipt.responsibility,"occurrence_locations":receipt.occurrence_locations,"source_finding_kind":receipt.source_finding_kind,"timestamp":receipt.timestamp})).collect::<Vec<_>>();
    let hook_paths_value = files
        .iter()
        .map(|path| path.to_string_lossy().to_string())
        .collect::<Vec<_>>();
    let mut counter_rows = Map::new();
    for (field, counter) in [
        ("evidence.hook_counts.statuses", &hook_counts.statuses),
        ("evidence.hook_counts.failures", &hook_counts.failures),
        ("evidence.hook_counts.files", &hook_counts.files),
        ("evidence.hook_counts.events", &hook_counts.events),
        ("evidence.hook_counts.namespaces", &hook_counts.namespaces),
        ("evidence.hook_counts.tools", &hook_counts.tools),
        ("evidence.hook_counts.skills", &hook_counts.skills),
        (
            "evidence.hook_counts.candidate_skills",
            &hook_counts.candidate_skills,
        ),
        (
            "evidence.hook_counts.candidate_workflows",
            &hook_counts.candidate_workflows,
        ),
        (
            "evidence.hook_counts.candidate_tools",
            &hook_counts.candidate_tools,
        ),
        (
            "evidence.hook_counts.skill_events",
            &hook_counts.skill_events,
        ),
        (
            "evidence.hook_counts.skill_sources",
            &hook_counts.skill_sources,
        ),
        (
            "evidence.hook_counts.feedback_labels",
            &hook_counts.feedback_labels,
        ),
        (
            "evidence.hook_counts.feedback_targets",
            &hook_counts.feedback_targets,
        ),
        (
            "evidence.hook_counts.feedback_actions",
            &hook_counts.feedback_actions,
        ),
        (
            "evidence.hook_counts.checker_targets",
            &hook_counts.checker_targets,
        ),
        (
            "evidence.hook_counts.failure_targets",
            &hook_counts.failure_targets,
        ),
        ("evidence.hook_counts.quality", &hook_counts.quality),
        ("hook_workflow_breakdown.workflows", &workflow_counts),
        ("hook_workflow_breakdown.workflow_events", &workflow_events),
        (
            "hook_workflow_breakdown.workflow_attribution",
            &workflow_attribution,
        ),
        (
            "hook_workflow_breakdown.missing_workflow_by_file",
            &missing_workflow_by_file,
        ),
        (
            "hook_workflow_breakdown.missing_workflow_events",
            &missing_workflow_events,
        ),
        (
            "hook_workflow_breakdown.missing_workflow_namespaces",
            &missing_workflow_namespaces,
        ),
        (
            "hook_workflow_breakdown.missing_workflow_statuses",
            &missing_workflow_statuses,
        ),
        (
            "hook_workflow_breakdown.missing_workflow_tools",
            &missing_workflow_tools,
        ),
        ("hook_schema.unknown_events_by_file", &unknown_by_file),
        ("hook_schema.namespace_debt_by_hook_family", &namespace_debt),
        ("hook_failure_drilldown.namespaces", &failure_namespaces),
        ("hook_failure_drilldown.events", &failure_events),
        ("hook_failure_drilldown.tools", &failure_tools),
        ("prompt_tool_breakdown.tools", &prompt_tools),
        ("prompt_tool_breakdown.command_verbs", &command_verbs),
        ("prompt_tool_breakdown.selected_tools", &selected_tools),
        (
            "reference_capture_breakdown.source_fields",
            &reference_source_fields,
        ),
        ("reference_capture_breakdown.events", &reference_events),
        ("reference_capture_breakdown.urls", &reference_urls),
        (
            "reference_capture_breakdown.registered_urls",
            &registered_urls,
        ),
        ("reference_capture_breakdown.missing_urls", &missing_urls),
    ] {
        counter_rows.insert(
            field.into(),
            Value::Array(
                counter
                    .sorted()
                    .into_iter()
                    .map(|(key, count)| json!([key, count]))
                    .collect(),
            ),
        );
    }
    for (prefix, mapping) in [
        ("hook_schema.status_by_hook_family", &status_by_family),
        ("hook_schema.failure_by_hook_family", &failure_by_family),
        ("hook_schema.skip_by_hook_family", &skip_by_family),
        (
            "hook_schema.oop_applicability.reasons_by_status",
            &oop_reasons,
        ),
    ] {
        for (name, counter) in mapping {
            counter_rows.insert(
                format!("{prefix}.{name}"),
                Value::Array(
                    counter
                        .sorted()
                        .into_iter()
                        .map(|(key, count)| json!([key, count]))
                        .collect(),
                ),
            );
        }
    }
    for family in &families {
        counter_rows.insert(
            format!("result_families.{}.status_counts", family.family),
            Value::Array(
                family
                    .statuses
                    .sorted()
                    .into_iter()
                    .map(|(name, count)| json!([name, count]))
                    .collect(),
            ),
        );
    }
    let mut summary = json!({"root":evidence.root,"recent_days":options.recent_days,"recent_cutoff_epoch":cutoff,"evidence":{"github_issue_refs":refs.iter().cloned().collect::<Vec<_>>(),"knowledge_entries":evidence.knowledge_entries,"hook_counts":count_value(&hook_counts)},"hook_files":hook_paths_value,"hook_entries":records.len(),"result_families":family_values,"hook_workflow_breakdown":hook_workflow_value,"hook_schema":hook_schema_value,"hook_failure_drilldown":hook_failure_drilldown,"token_usage_breakdown":token_value,"prompt_tool_breakdown":prompt_value,"markdown_docs_breakdown":markdown_value,"reference_capture_breakdown":reference_value,"selection_metrics_breakdown":{"metrics":selection_metrics,"entries_seen":records.len(),"entries_with_candidates":entries_with_candidates,"entries_with_selection":entries_with_selection,"filtered_observations":filtered_observations},"issue_worker_handoffs":handoffs,"issue_publication_receipts":receipt_values,"source_sync_state":source_sync,"counter_rows":Value::Object(counter_rows)});
    let issue_worker = json!({"qualified": qualified, "routeable": routeable, "handoff": handoff, "no_action": no_action, "reasons": reasons.json(), "github_issue_refs": receipts.iter().map(|r| r.url.clone()).collect::<Vec<_>>(), "published_receipts": receipts.len(), "issue_publication_action_counts": receipt_actions.json()});
    let mut problems = Vec::new();
    let failed_hooks = hook_counts.statuses.get("fail");
    if failed_hooks > 0 {
        problems.push(json!({"component_type":"hook","name":"hook evidence","status":"fail","problem":format!("{failed_hooks} hook entries report status=fail"),"evidence":"compact report Hook Failure Drilldown","next_action":"repair failing hook evidence"}));
    }
    if reference_entries == 0 || reference_missing_observations > 0 {
        let (status, problem) = if reference_entries == 0 {
            (
                "missing",
                "reference_capture_guard has no entries".to_owned(),
            )
        } else {
            (
                "attention",
                format!("{reference_missing_observations} referenced URLs are unregistered"),
            )
        };
        problems.push(json!({"component_type":"hook","name":"reference_capture_guard","status":status,"problem":problem,"evidence":"compact report Reference Capture Drilldown","next_action":"materialize references or repair hook logging"}));
    }
    for row in &selection_metric_rows {
        let missed = row["missed"].as_u64().unwrap_or(0);
        if missed == 0 {
            continue;
        }
        let responsibility = row["responsibility"].as_str().unwrap_or("");
        let name = row["name"].as_str().unwrap_or("");
        problems.push(json!({"component_type":responsibility,"name":name,"status":"attention","problem":format!("{missed} candidate miss(es); miss rate {}",row["miss_rate"].as_str().unwrap_or("unknown")),"evidence":"compact report Selection Evidence Drilldown","next_action":format!("repair {responsibility} selection or logging")}));
    }
    if entries_without_workflow > 0 {
        problems.push(json!({"component_type":"workflow","name":"_unattributed_hook_entries","status":"attention","problem":format!("{entries_without_workflow} hook entries lack workflow attribution"),"evidence":"compact report Workflow Attribution Drilldown","next_action":"repair workflow attribution logging"}));
    }
    if prompt_entries == 0 || tool_selection_entries == 0 {
        problems.push(json!({"component_type":"hook","name":"prompt_classifier_and_behavior_event_assembly","status":"missing","problem":"prompt or tool selection evidence is missing","evidence":"compact report Markdown And Prompt Drilldown","next_action":"repair prompt classification and behavior-event evidence assembly"}));
    }
    if token.objective_selected && token.comparison_count + token.summary_count == 0 {
        problems.push(json!({"component_type":"workflow","name":"token_consumption_evidence","status":"missing","problem":"no token footprint comparison or moving-average evidence found","evidence":"compact report Token Consumption Drilldown","next_action":"record token usage evidence"}));
    }
    problems.sort_by(|left, right| {
        let rank = |value: &Value| match value["status"].as_str().unwrap_or("") {
            "fail" => 0,
            "attention" => 1,
            "missing" => 2,
            _ => 9,
        };
        rank(left)
            .cmp(&rank(right))
            .then_with(|| {
                left["component_type"]
                    .as_str()
                    .cmp(&right["component_type"].as_str())
            })
            .then_with(|| left["name"].as_str().cmp(&right["name"].as_str()))
    });
    problems.truncate(MAX_COUNTER_LINES);
    let mut next_actions = Vec::new();
    let issue = "missing-local-issue";
    if failed_hooks > 0 {
        next_actions.push(json!({"priority":"P0","action":"repair failing hook evidence","reason":format!("{failed_hooks} hook entries report status=fail"),"evidence":"compact report Hook Failure Drilldown","owner_surface":".codex/hooks/ and hook accumulation tooling","command":"tools/bin/agent-canon eval-accumulation-check","done_condition":"hook status fail count is 0","issue":issue,"automation":"agent-fix"}));
    }
    if reference_entries == 0 {
        next_actions.push(json!({"priority":"P1","action":"confirm reference capture hook is producing evidence","reason":"no reference_capture_guard entries are present","evidence":"compact report Reference Capture Drilldown","owner_surface":"tools/runtime/dispatch/agent-canon/src/reference_materializer.rs","command":"tools/bin/agent-canon generate-agent-runtime-dashboard","done_condition":"AGENT_RUNTIME_DASHBOARD_REFERENCE_CAPTURE_ENTRIES>0","issue":issue,"automation":"agent-fix"}));
    } else if reference_missing_observations > 0 || reference_blocked_entries > 0 {
        next_actions.push(json!({"priority":"P1","action":"materialize missing consulted source URLs","reason":format!("{reference_missing_observations} observed URLs are not registered"),"evidence":"compact report Reference Capture Drilldown","owner_surface":"references/external/ and tools/runtime/dispatch/agent-canon/src/reference_materializer.rs","command":"tools/bin/agent-canon reference-materializer --url <url> --input <pdf-or-html>","done_condition":"AGENT_RUNTIME_DASHBOARD_REFERENCE_MISSING_URLS=0","issue":issue,"automation":"agent-fix-with-source-file"}));
    }
    if entries_without_workflow > 0 {
        next_actions.push(json!({"priority":"P1","action":"repair workflow attribution logging","reason":format!("{entries_without_workflow} hook entries lack workflow attribution"),"evidence":"compact report Workflow Attribution Drilldown","owner_surface":"tools/runtime/dispatch/agent-canon/src/behavior_event_assembly.rs and workflow_monitoring.md","command":"tools/bin/agent-canon generate-agent-runtime-dashboard","done_condition":"AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_MISSING=0 or entries are explicitly exempt","issue":issue,"automation":"agent-fix"}));
    }
    let missed_total = selection_metric_rows
        .iter()
        .map(|row| row["missed"].as_u64().unwrap_or(0))
        .sum::<u64>();
    if missed_total > 0 {
        let mut top_missed = None;
        for row in &selection_metric_rows {
            if top_missed.is_none_or(|current: &Value| {
                row["missed"].as_u64().unwrap_or(0) > current["missed"].as_u64().unwrap_or(0)
            }) {
                top_missed = Some(row);
            }
        }
        if let Some(row) = top_missed {
            let responsibility = row["responsibility"].as_str().unwrap_or("");
            let name = row["name"].as_str().unwrap_or("");
            let reset_path = selection_resets
                .get(&(responsibility.into(), name.into()))
                .map(|value| value.0.as_str())
                .unwrap_or("untracked-or-unknown");
            next_actions.push(json!({"priority":"P1","action":format!("repair {responsibility} selection for {name}"),"reason":format!("{missed_total} candidate selections were not confirmed"),"evidence":"compact report Selection Evidence Drilldown","owner_surface":reset_path,"command":"tools/bin/agent-canon generate-agent-runtime-dashboard","done_condition":format!("{responsibility}:{name} miss rate is 0% after its reset window"),"issue":issue,"automation":"human-review-then-agent-fix"}));
        }
    }
    let markdown_signal_count = hook_counts.candidate_skills.get("md-style-check")
        + [
            "agent-canon-cli",
            "audit_and_fix_links.py",
            "fix_markdown_docs.py",
            "fix_markdown_headers.py",
        ]
        .iter()
        .map(|name| hook_counts.candidate_tools.get(name))
        .sum::<u64>();
    if markdown_signal_count == 0 {
        next_actions.push(json!({"priority":"P2","action":"repair Markdown/docs checking signal","reason":"Markdown/docs hook signals are missing","evidence":"compact report Markdown And Prompt Drilldown","owner_surface":".codex/personal/skills/md-style-check/SKILL.md and tools/runtime/dispatch/agent-canon/src/docs.rs","command":"tools/bin/agent-canon docs check","done_condition":"markdown_hook_signal_status=present","issue":issue,"automation":"agent-fix"}));
    }
    if prompt_entries == 0 || tool_selection_entries == 0 || prompt_missing_excerpt_entries > 0 {
        next_actions.push(json!({"priority":"P2","action":"repair prompt and tool selection evidence","reason":"prompt excerpts or tool selection entries are missing","evidence":"compact report Markdown And Prompt Drilldown","owner_surface":"tools/runtime/dispatch/agent-canon/src/behavior_event_assembly.rs","command":"tools/bin/agent-canon generate-agent-runtime-dashboard","done_condition":"prompt_entries>0, tool_selection_entries>0, prompt_missing_excerpt_entries=0","issue":issue,"automation":"agent-fix"}));
    }
    if token.objective_selected && token.comparison_count + token.summary_count == 0 {
        next_actions.push(json!({"priority":"P2","action":"add token consumption moving-average evidence","reason":"no token footprint comparison or moving-average evidence found","evidence":"compact report Token Consumption Drilldown","owner_surface":"workflow_monitoring.md and token logging hooks","command":"tools/bin/agent-canon compare-codex-token-footprints --session-glob '<sessions>' --report-dir <run>","done_condition":"AGENT_RUNTIME_DASHBOARD_TOKEN_COMPARISONS>0 or AGENT_RUNTIME_DASHBOARD_TOKEN_SUMMARIES>0","issue":issue,"automation":"human-review-then-agent-fix"}));
    }
    if routeable > 0 {
        let repositories = handoffs
            .iter()
            .filter(|item| item["can_route"] == true)
            .filter_map(|item| item["repository"].as_str())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>();
        let unresolved = routeable.saturating_sub(qualified);
        let action = if unresolved > 0 {
            "investigate IssueWorker evidence gaps"
        } else {
            "publish explicit IssueWorker candidates"
        };
        let reason = if unresolved > 0 {
            format!("{unresolved} same-repository candidate(s) need publisher investigation")
        } else {
            format!("{qualified} same-repository candidate(s) require host publication")
        };
        next_actions.push(json!({"priority":"P1","action":action,"reason":reason,"evidence":repositories.join(", "),"owner_surface":"IssueWorker publisher and GitHub Issue readback","command":"route the typed handoff to the publisher role; dashboard remains read-only","done_condition":"each candidate is created, updated, reorganized, or explicitly deferred with readback","issue":"`issue-worker`","automation":"host-publisher"}));
    } else {
        let published = receipts
            .iter()
            .map(|receipt| receipt.url.as_str())
            .collect::<BTreeSet<_>>();
        let pending = refs
            .iter()
            .filter(|reference| !published.contains(reference.as_str()))
            .collect::<Vec<_>>();
        if let Some(reference) = pending.first() {
            next_actions.push(json!({"priority":"P2","action":"triage oldest open durable issue","reason":format!("{} repository-qualified GitHub Issue references are pending",pending.len()),"evidence":reference,"owner_surface":"GitHub Issue URL/number and private packet locator","command":"python3 tools/repository/github/issue_sync.py --sync-pending","done_condition":"GitHub Issue URL/number is read back or lookup is explicitly deferred","issue":format!("`{reference}`"),"automation":"human-review"}));
        }
    }
    next_actions.sort_by(|left, right| {
        let rank = |value: &Value| match value["priority"].as_str().unwrap_or("") {
            "P0" => 0,
            "P1" => 1,
            "P2" => 2,
            _ => 9,
        };
        rank(left)
            .cmp(&rank(right))
            .then_with(|| left["action"].as_str().cmp(&right["action"].as_str()))
    });
    let problem_components = problems.iter().map(|item| json!({"component_type":item["component_type"],"name":item["name"],"status":item["status"],"problem":item["problem"],"evidence":item["evidence"],"next_action":item["next_action"]})).collect::<Vec<_>>();
    let next_actions_for_render = next_actions.clone();
    summary["problem_components"] = json!(problem_components);
    summary["next_actions"] = json!(next_actions_for_render);
    let api_problems = problems.iter().take(8).map(|item| json!({"type":item["component_type"],"component":item["name"],"status":item["status"],"problem":item["problem"],"evidence":item["evidence"],"next_action":item["next_action"]})).collect::<Vec<_>>();
    next_actions.truncate(8);
    let api = json!({"schema": DASHBOARD_API_SCHEMA, "root": evidence.root, "recent_days": options.recent_days.map_or(json!("all"), |days| json!(days)), "hook_files": files.len(), "hook_entries": records.len(), "github_issue_refs": refs, "issue_publication_action_counts": receipt_actions.json(), "source_sync_state": source_sync, "unknown_event_count": unknown_by_file.total(), "unknown_events_by_file": unknown_by_file.json(), "status_by_hook_family": nested(&status_by_family), "failure_by_hook_family": nested(&failure_by_family), "skip_by_hook_family": nested(&skip_by_family), "namespace_debt_by_hook_family": namespace_debt.json(), "oop_applicability": {"applicable_count":oop_applicable,"not_applicable_count":oop_not_applicable,"missing_reason_count":oop_missing_reason,"reasons_by_status":nested(&oop_reasons)}, "priority_problems":api_problems, "priority_next_actions":next_actions, "selection_misses": selection_misses, "issue_worker": issue_worker});
    let (markdown, compact) = crate::dashboard_render::render(&summary)?;
    let api_text = serde_json::to_string_pretty(&api).map_err(|error| error.to_string())? + "\n";
    Ok((markdown, compact, api_text, files.len(), records.len()))
}

fn runtime_boundary(
    root: &Path,
    runtime_root: Option<&Path>,
) -> Result<RuntimeArtifactBoundary, String> {
    RuntimeArtifactBoundary::for_source(root, runtime_root, true)
}

fn run_guide(options: Options) -> Result<PathBuf, String> {
    let source_root =
        fs::canonicalize(&options.root).map_err(|error| format!("resolve source root: {error}"))?;
    let boundary = runtime_boundary(&source_root, options.runtime_root.as_deref())?;
    let evidence = collect_evidence(&source_root, Some(boundary.root()))?;
    boundary.atomic_write_text(
        &options.output,
        &render_guide(&evidence),
        options.output_mode,
    )
}

/// Run the read-only improvement-guide command.
pub fn run_guide_cli(args: &[String]) -> i32 {
    match parse_options(args, false).and_then(run_guide) {
        Ok(path) => {
            println!("AGENT_IMPROVEMENT_GUIDE={}", path.display());
            0
        }
        Err(error) if error.is_empty() => {
            println!("usage: agent-canon {GUIDE_SELECTOR} [--root ROOT] [--runtime-root ROOT] [--out PATH] [--output-mode 600|644]");
            0
        }
        Err(error) => {
            eprintln!("agent-canon {GUIDE_SELECTOR}: {error}");
            2
        }
    }
}

/// Run the read-only runtime-dashboard command.
pub fn run_dashboard_cli(args: &[String]) -> i32 {
    match parse_options(args, true).and_then(|options| {
        let root = fs::canonicalize(&options.root)
            .map_err(|error| format!("resolve source root: {error}"))?;
        let boundary = runtime_boundary(&root, options.runtime_root.as_deref())?;
        let evidence = collect_evidence(&root, Some(boundary.root()))?;
        let cutoff = options.recent_days.map(|days| {
            (SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs() as i64)
                .saturating_sub(days.saturating_mul(86_400))
        });
        let (markdown, compact, api, files, entries) =
            dashboard_outputs(&options, &evidence, cutoff)?;
        boundary.atomic_write_text(&options.output, &markdown, 0o600)?;
        if let Some(path) = options.compact_output.as_ref() {
            boundary.atomic_write_text(path, &compact, 0o600)?;
        }
        if let Some(path) = options.api_output.as_ref() {
            boundary.atomic_write_text(path, &api, 0o600)?;
        }
        Ok((
            options.output,
            evidence.root,
            options.recent_days,
            files,
            entries,
        ))
    }) {
        Ok((path, root, recent_days, files, entries)) => {
            println!("AGENT_RUNTIME_DASHBOARD={}", path.display());
            println!("AGENT_RUNTIME_DASHBOARD_STATUS=pass");
            println!("AGENT_RUNTIME_DASHBOARD_EVIDENCE_ROOT={}", root.display());
            println!(
                "AGENT_RUNTIME_DASHBOARD_RECENT_DAYS={}",
                recent_days.map_or_else(|| "all".to_owned(), |days| days.to_string())
            );
            println!("AGENT_RUNTIME_DASHBOARD_HOOK_FILES={files}");
            println!("AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES={entries}");
            0
        }
        Err(error) if error.is_empty() => {
            println!("usage: agent-canon {DASHBOARD_SELECTOR} [--root ROOT] [--runtime-root ROOT] [--out PATH] [--compact-out PATH] [--api-out PATH] [--recent-days DAYS]");
            0
        }
        Err(error) => {
            eprintln!("agent-canon {DASHBOARD_SELECTOR}: {error}");
            2
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{valid_source_sync, Counter, SOURCE_SYNC_SCHEMA};
    use serde_json::json;
    use std::fs;
    use std::path::Path;

    #[test]
    fn counter_retains_first_seen_order_and_most_common_ties() {
        let mut counter = Counter::default();
        counter.add("z");
        counter.add("a");
        counter.add("z");
        assert_eq!(counter.sorted(), vec![("z", 2), ("a", 1)]);
    }

    #[test]
    fn source_sync_projection_validates_identity_and_drops_schema_marker() {
        let temp = tempfile::tempdir().expect("temporary source-sync root");
        let path = temp.path().join("source-sync.json");
        let valid = json!({
            "schema": SOURCE_SYNC_SCHEMA,
            "status": "failed",
            "code": "source_sync_candidate_failed",
            "source_root": "/home/agent-canon",
            "source_head": "a".repeat(40),
            "source_tree": "b".repeat(40),
            "remote": "origin",
            "remote_url": "git@github.com:owner/repo.git",
            "branch": "main",
            "updated_at": "2026-08-27T00:00:00Z",
            "failure": "source_sync_candidate_failed"
        });
        fs::write(&path, serde_json::to_vec(&valid).unwrap()).unwrap();
        let projection = valid_source_sync(&path).expect("valid mounted record is projected");
        assert_eq!(projection["status"], "failed");
        assert_eq!(projection["source_head"], "a".repeat(40));
        assert!(projection.get("schema").is_none());

        fs::write(
            &path,
            serde_json::to_vec(&json!({
                "schema": SOURCE_SYNC_SCHEMA,
                "status": "success",
                "code": "up_to_date",
                "source_root": "/home/agent-canon",
                "source_head": "A".repeat(40),
                "source_tree": "b".repeat(40),
                "remote": "origin",
                "remote_url": "git@github.com:owner/repo.git",
                "branch": "main",
                "updated_at": "2026-08-27T00:00:00Z"
            }))
            .unwrap(),
        )
        .unwrap();
        assert!(valid_source_sync(&path).is_none());
        assert!(valid_source_sync(Path::new("/path/that/does/not/exist")).is_none());
    }
}
