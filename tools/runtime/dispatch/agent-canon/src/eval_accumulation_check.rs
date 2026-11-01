// @dependency-start
// contract implementation
// responsibility Validates append-only hook and registered eval-family accumulation from the read-only external archive.
// upstream design ../../../../../eval/definitions/README.md eval usage contract
// upstream design ../../../../../eval/definitions/eval_result_families.toml eval family artifact registry
// upstream design ../../../../../documents/runtime/runtime-log-archive.md eval archive contract
// upstream implementation eval_archive_paths.rs resolves the checker's mounted archive search paths
// upstream implementation eval_manifest_paths.rs resolves canonical and legacy registry paths
// upstream implementation runtime_boundary.rs owns external artifact reads and compact summary writes
// upstream implementation prompt_capture.rs owns prompt secret redaction patterns
// upstream implementation python_json.rs owns Python-compatible JSON values and parsing
// upstream implementation python_text.rs owns Python-compatible Unicode text and line splitting
// downstream implementation ../../../../../tools/validation/ci/runners/run_all_checks.sh runs eval accumulation checks
// downstream implementation ../../../../../tests/agent_tools/test_eval_accumulation_check.py exercises the native CLI
// @dependency-end

//! Validate accumulated AgentCanon eval and hook results.

use crate::eval_archive_paths::{
    eval_result_search_dirs, hook_result_search_dirs, mounted_log_archive_root,
    HOOK_SPOOL_INDEX_NAME,
};
use crate::eval_manifest_paths::{eval_manifest_path, resolve_eval_manifest};
use crate::prompt_capture::redact_sensitive_text;
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::python_json::{parse_json, JsonArray, JsonNumber, JsonObject, JsonString, JsonValue};
use crate::python_text::{is_python_whitespace, python_splitlines, python_strip};
use crate::runtime_boundary::{RuntimeArtifactBoundary, RUNTIME_ROOT_ENV};
use regex::Regex;
use serde_json::{json, Value as JsonOutput};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::LazyLock;
use toml_edit::{DocumentMut, TableLike};

pub const SELECTOR: &str = "eval-accumulation-check";

const HOOK_REQUIRED_FIELDS: &[&str] =
    &["hook_run_id", "timestamp", "status", "payload_fingerprint"];
const BEHAVIOR_EVENT_SCHEMA: &str = "agent-canon.behavior-event.v1";
const BEHAVIOR_EVENT_KIND: &str = "behavior_snapshot";
const BEHAVIOR_HOOK_EVENTS: &[&str] = &["UserPromptSubmit", "PreToolUse", "PostToolUse"];
const WORKFLOW_ATTRIBUTION_KINDS: &[&str] = &["owner", "context", "missing"];
const PROMPT_CAPTURE_STATUSES: &[&str] = &["present", "missing"];
const BEHAVIOR_HINT_FIELDS: &[&str] = &[
    "event_kind",
    "workflow_attribution_kind",
    "selected_workflow",
    "selected_workflows",
    "workflow",
    "workflow_family",
    "workflow_selection_kind",
    "workflow_owner",
    "workflow_owner_workflows",
    "workflow_context_kind",
    "workflow_context_source",
    "workflow_context_workflows",
    "workflow_context_timestamp",
    "workflow_context_source_event",
    "selected_workflow_count",
    "candidate_workflows",
    "prompt_capture_status",
    "prompt_excerpt_redacted",
    "prompt_fingerprint",
    "prompt_char_count",
];
const COMPACT_FINDING_SAMPLE_LIMIT: usize = 25;
const ERROR_NEXT_ACTION: &str = "pass --runtime-root or set AGENT_CANON_RUNTIME_ROOT";

static PROMPT_FINGERPRINT_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[0-9a-f]{16}$").expect("static fingerprint regex is valid"));
static PROMPT_CAPTURE_CAUSE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[a-z][a-z0-9_-]*$").expect("static prompt-cause regex is valid")
});
static BEHAVIOR_EVENT_ID_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[0-9a-f]{64}$").expect("static event-id regex is valid"));

#[derive(Clone, Debug, Eq, PartialEq)]
struct Finding {
    check: String,
    path: String,
    detail: String,
}

impl Finding {
    fn new(check: &str, path: &str, detail: impl Into<String>) -> Self {
        Self {
            check: check.to_owned(),
            path: path.to_owned(),
            detail: detail.into(),
        }
    }

    fn render(&self) -> String {
        format!(
            "EVAL_ACCUMULATION_FINDING={}:{}:{}",
            self.check, self.path, self.detail
        )
    }

    fn as_json(&self) -> JsonOutput {
        json!({"check": &self.check, "path": &self.path, "detail": &self.detail})
    }
}

#[derive(Clone, Debug)]
struct EvalFamilyContract {
    family_id: String,
    check_id: String,
    count_label: String,
    filename_regex: String,
    run_id_regex: String,
    missing_reports_detail: String,
    missing_run_id_detail: String,
    duplicate_run_id_detail: String,
}

#[derive(Debug)]
struct EvalAccumulationReport {
    hook_files: usize,
    hook_entries: usize,
    hook_legacy_missing_namespace: usize,
    eval_report_counts: BTreeMap<String, usize>,
    findings: Vec<Finding>,
}

#[derive(Debug)]
enum ValidationError {
    Archive(String),
    Other(String),
}

#[derive(Clone, Copy)]
enum CliOption {
    Help,
    Root,
    RuntimeRoot,
    FamilyRegistry,
    Format,
    CompactOut,
}

struct CliOptions {
    root: PathBuf,
    runtime_root: Option<PathBuf>,
    family_registry: String,
    format: String,
    compact_out: Option<PathBuf>,
}

const CLI_OPTIONS: &[(&str, CliOption)] = &[
    ("--help", CliOption::Help),
    ("--root", CliOption::Root),
    ("--runtime-root", CliOption::RuntimeRoot),
    ("--family-registry", CliOption::FamilyRegistry),
    ("--format", CliOption::Format),
    ("--compact-out", CliOption::CompactOut),
];

fn usage() -> &'static str {
    "usage: agent-canon eval-accumulation-check [--root ROOT] [--runtime-root RUNTIME_ROOT] [--family-registry FAMILY_REGISTRY] [--format {text,json}] [--compact-out COMPACT_OUT]"
}

fn print_help() {
    println!(
        "Validate accumulated AgentCanon eval and hook results.\n\n{}\n\nOptions:\n  -h, --help            show this help message and exit\n  --root ROOT\n  --runtime-root RUNTIME_ROOT\n                        Explicit external runtime root containing eval and hook archives.\n  --family-registry FAMILY_REGISTRY\n                        TOML registry that declares accumulated eval result families.\n  --format {{text,json}}\n  --compact-out COMPACT_OUT\n                        Optional JSON summary path. When set, stdout omits full finding detail.",
        usage()
    );
}

fn parse_arguments(args: &[String]) -> Result<Option<CliOptions>, String> {
    let mut root = env::current_dir().map_err(|error| format!("current directory: {error}"))?;
    let mut runtime_root = None;
    let mut family_registry = eval_manifest_path("eval_result_families.toml")
        .to_string_lossy()
        .into_owned();
    let mut format = "text".to_owned();
    let mut compact_out = None;
    let mut index = 0;

    while index < args.len() {
        let token = &args[index];
        if token == "-h" || token == "--help" {
            return Ok(None);
        }
        if token.starts_with("--") {
            let (option_text, inline_value) = match token.split_once('=') {
                Some((option, value)) => (option, Some(value)),
                None => (token.as_str(), None),
            };
            let option =
                resolve_long_option_prefix(option_text, CLI_OPTIONS).map_err(
                    |error| match error {
                        LongOptionError::Unrecognized => {
                            format!("unrecognized argument: {token}")
                        }
                        LongOptionError::Ambiguous(_) => format!("ambiguous option: {option_text}"),
                    },
                )?;
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
                if value.starts_with('-')
                    && !crate::python_cli_integer::is_argparse_negative_number(value)
                {
                    return Err(format!("argument {option_text}: expected one argument"));
                }
                value.clone()
            };
            match option {
                CliOption::Root => root = PathBuf::from(value),
                CliOption::RuntimeRoot => runtime_root = Some(PathBuf::from(value)),
                CliOption::FamilyRegistry => family_registry = value,
                CliOption::Format if matches!(value.as_str(), "text" | "json") => format = value,
                CliOption::Format => {
                    return Err(format!(
                        "argument {option_text}: invalid choice: '{}' (choose from 'text', 'json')",
                        value
                    ));
                }
                CliOption::CompactOut => compact_out = Some(PathBuf::from(value)),
                CliOption::Help => unreachable!("help is handled before value parsing"),
            }
            index += 1;
            continue;
        }
        return Err(format!("unrecognized argument: {token}"));
    }

    Ok(Some(CliOptions {
        root,
        runtime_root,
        family_registry,
        format,
        compact_out,
    }))
}

fn path_as_posix(path: &Path) -> String {
    let value = path.to_string_lossy();
    #[cfg(windows)]
    {
        value.replace('\\', "/")
    }
    #[cfg(not(windows))]
    {
        value.into_owned()
    }
}

fn relative(root: &Path, path: &Path) -> String {
    path_as_posix(path.strip_prefix(root).unwrap_or(path))
}

fn path_sort_key(path: &Path) -> Vec<String> {
    path.components()
        .map(|component| {
            let value = component.as_os_str().to_string_lossy().into_owned();
            #[cfg(windows)]
            {
                value.to_lowercase()
            }
            #[cfg(not(windows))]
            {
                value
            }
        })
        .collect()
}

fn regex_fullmatch(regex: &Regex, value: &JsonString) -> bool {
    let Some(text) = value.to_text() else {
        return false;
    };
    regex
        .find(&text)
        .is_some_and(|matched| matched.start() == 0 && matched.end() == text.len())
}

fn string_is_nonempty(value: &JsonString) -> bool {
    !value
        .0
        .iter()
        .all(|codepoint| char::from_u32(*codepoint).is_some_and(is_python_whitespace))
}

fn object_value<'a>(object: &'a JsonObject, field: &str) -> Option<&'a JsonValue> {
    object
        .0
        .iter()
        .rev()
        .find(|(key, _)| key.equals_text(field))
        .map(|(_, value)| value)
}

fn object_has_field(object: &JsonObject, field: &str) -> bool {
    object.0.iter().any(|(key, _)| key.equals_text(field))
}

fn is_nonnegative_int(value: Option<&JsonValue>) -> bool {
    matches!(value, Some(JsonValue::Number(JsonNumber::Integer(number))) if !number.starts_with('-'))
}

fn is_string_list(value: Option<&JsonValue>) -> bool {
    match value {
        None => true,
        Some(JsonValue::Array(JsonArray(values))) => values
            .iter()
            .all(|value| matches!(value, JsonValue::String(_))),
        _ => false,
    }
}

fn as_array(value: Option<&JsonValue>) -> Option<&[JsonValue]> {
    match value {
        Some(JsonValue::Array(JsonArray(values))) => Some(values),
        _ => None,
    }
}

fn as_string(value: Option<&JsonValue>) -> Option<&JsonString> {
    match value {
        Some(JsonValue::String(text)) => Some(text),
        _ => None,
    }
}

fn string_equals(value: Option<&JsonValue>, expected: &str) -> bool {
    as_string(value).is_some_and(|value| value.equals_text(expected))
}

fn value_equals_usize(value: &JsonValue, expected: usize) -> bool {
    match value {
        JsonValue::Bool(boolean) => (if *boolean { 1 } else { 0 }) == expected,
        JsonValue::Number(JsonNumber::Integer(integer)) => integer
            .parse::<usize>()
            .is_ok_and(|value| value == expected),
        JsonValue::Number(JsonNumber::Float(float)) => *float == expected as f64,
        _ => false,
    }
}

fn integer_float_equal(integer: &str, float: f64) -> bool {
    if !float.is_finite() || float.fract() != 0.0 {
        return false;
    }
    let formatted = if float == 0.0 {
        "0".to_owned()
    } else {
        format!("{float:.0}")
    };
    integer == formatted.as_str()
}

fn numbers_equal(left: &JsonNumber, right: &JsonNumber) -> bool {
    match (left, right) {
        (JsonNumber::Integer(left), JsonNumber::Integer(right)) => left == right,
        (JsonNumber::Float(left), JsonNumber::Float(right)) => left == right,
        (JsonNumber::Integer(integer), JsonNumber::Float(float))
        | (JsonNumber::Float(float), JsonNumber::Integer(integer)) => {
            integer_float_equal(integer, *float)
        }
    }
}

fn bool_number_equal(boolean: bool, number: &JsonNumber) -> bool {
    match number {
        JsonNumber::Integer(integer) => integer.as_str() == if boolean { "1" } else { "0" },
        JsonNumber::Float(float) => *float == f64::from(u8::from(boolean)),
    }
}

fn python_json_equal(left: &JsonValue, right: &JsonValue) -> bool {
    let mut pending = vec![(left, right)];
    while let Some((left, right)) = pending.pop() {
        match (left, right) {
            (JsonValue::Null, JsonValue::Null) => {}
            (JsonValue::Bool(left), JsonValue::Bool(right)) if left == right => {}
            (JsonValue::Bool(boolean), JsonValue::Number(number))
            | (JsonValue::Number(number), JsonValue::Bool(boolean))
                if bool_number_equal(*boolean, number) => {}
            (JsonValue::Number(left), JsonValue::Number(right)) if numbers_equal(left, right) => {}
            (JsonValue::String(left), JsonValue::String(right)) if left == right => {}
            (JsonValue::Array(JsonArray(left)), JsonValue::Array(JsonArray(right))) => {
                if left.len() != right.len() {
                    return false;
                }
                pending.extend(left.iter().zip(right));
            }
            (JsonValue::Object(JsonObject(left)), JsonValue::Object(JsonObject(right))) => {
                if left.len() != right.len() {
                    return false;
                }
                for (left_key, left_value) in left {
                    let Some((_, right_value)) = right.iter().find(|(key, _)| key == left_key)
                    else {
                        return false;
                    };
                    pending.push((left_value, right_value));
                }
            }
            _ => return false,
        }
    }
    true
}

fn workflow_value_present(value: Option<&JsonValue>) -> bool {
    match value {
        None | Some(JsonValue::Null) | Some(JsonValue::Bool(false)) => false,
        Some(JsonValue::String(value)) => !value.is_empty(),
        Some(JsonValue::Array(JsonArray(values))) => !values.is_empty(),
        Some(JsonValue::Number(JsonNumber::Integer(value))) => value != "0",
        Some(JsonValue::Number(JsonNumber::Float(value))) => *value != 0.0,
        Some(JsonValue::Bool(true)) | Some(JsonValue::Object(_)) => true,
    }
}

fn finding(check: &str, label: &str, detail: impl Into<String>) -> Finding {
    Finding::new(check, label, detail)
}

fn json_sequences_equal(left: &[JsonValue], right: &[JsonValue]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    left.iter()
        .zip(right)
        .all(|(left, right)| python_json_equal(left, right))
}

fn behavior_envelope_findings(label: &str, entry: &JsonObject) -> Vec<Finding> {
    let mut findings = Vec::new();
    for field in [
        "event_id",
        "hook_invocation_id",
        "hook_event_name",
        "event_kind",
        "timestamp",
        "source",
        "workflow_attribution_kind",
        "prompt_capture_status",
    ] {
        if !as_string(object_value(entry, field)).is_some_and(string_is_nonempty) {
            findings.push(finding(
                "behavior_event",
                label,
                format!("missing-field:{field}"),
            ));
        }
    }

    let prompt_excerpt = object_value(entry, "prompt_excerpt_redacted");
    if !matches!(prompt_excerpt, Some(JsonValue::String(_))) {
        findings.push(finding(
            "behavior_event",
            label,
            "missing-field:prompt_excerpt_redacted",
        ));
    }
    if !matches!(
        object_value(entry, "prompt_fingerprint"),
        Some(JsonValue::String(_))
    ) {
        findings.push(finding(
            "behavior_event",
            label,
            "missing-field:prompt_fingerprint",
        ));
    }
    if !is_nonnegative_int(object_value(entry, "prompt_char_count")) {
        findings.push(finding(
            "behavior_event",
            label,
            "missing-field:prompt_char_count",
        ));
    }
    if !matches!(
        object_value(entry, "prompt_excerpt_truncated"),
        Some(JsonValue::Bool(_))
    ) {
        findings.push(finding(
            "behavior_event",
            label,
            "missing-field:prompt_excerpt_truncated",
        ));
    }

    if let Some(event_id) = as_string(object_value(entry, "event_id")) {
        if !regex_fullmatch(&BEHAVIOR_EVENT_ID_RE, event_id) {
            findings.push(finding("behavior_event", label, "invalid-event-id"));
        }
    }
    if !BEHAVIOR_HOOK_EVENTS
        .iter()
        .any(|event| string_equals(object_value(entry, "hook_event_name"), event))
    {
        findings.push(finding("behavior_event", label, "invalid-hook-event-name"));
    }
    if !string_equals(object_value(entry, "event_kind"), BEHAVIOR_EVENT_KIND) {
        findings.push(finding("behavior_event", label, "invalid-event-kind"));
    }
    findings
}

fn behavior_workflow_findings(label: &str, entry: &JsonObject) -> Vec<Finding> {
    let mut findings = Vec::new();
    for field in [
        "selected_workflows",
        "workflow_owner_workflows",
        "workflow_context_workflows",
    ] {
        if !is_string_list(object_value(entry, field)) {
            findings.push(finding(
                "behavior_event",
                label,
                format!("invalid-list:{field}"),
            ));
        }
    }
    findings.extend(workflow_kind_findings(label, entry));
    findings
}

fn workflow_kind_findings(label: &str, entry: &JsonObject) -> Vec<Finding> {
    let attribution = object_value(entry, "workflow_attribution_kind");
    let kind = WORKFLOW_ATTRIBUTION_KINDS
        .iter()
        .find(|kind| string_equals(attribution, kind));
    let mut findings = Vec::new();
    let Some(kind) = kind else {
        findings.push(finding(
            "behavior_event",
            label,
            "invalid-workflow-attribution-kind",
        ));
        return findings;
    };
    match *kind {
        "owner" => findings.extend(workflow_owner_findings(label, entry)),
        "context" => findings.extend(workflow_context_findings(label, entry)),
        "missing" => findings.extend(workflow_missing_findings(label, entry)),
        _ => unreachable!("attribution kind is selected from its closed set"),
    }
    findings
}

fn workflow_owner_findings(label: &str, entry: &JsonObject) -> Vec<Finding> {
    let owner = as_string(object_value(entry, "workflow_owner"));
    let selected = as_array(object_value(entry, "selected_workflows"));
    let owner_workflows = as_array(object_value(entry, "workflow_owner_workflows"));
    let coherent_lists = match (owner, selected, owner_workflows) {
        (Some(owner), Some(selected), Some(owner_workflows))
            if string_is_nonempty(owner) && !selected.is_empty() && !owner_workflows.is_empty() =>
        {
            let first_selected_matches = matches!(
                selected.first(),
                Some(JsonValue::String(selected_owner)) if selected_owner == owner
            );
            first_selected_matches && json_sequences_equal(owner_workflows, selected)
        }
        _ => false,
    };
    if !coherent_lists || workflow_owner_optional_mismatch(entry, owner, selected) {
        return vec![finding(
            "behavior_event",
            label,
            "workflow-owner-fields-incoherent",
        )];
    }
    if [
        "workflow_context_kind",
        "workflow_context_source",
        "workflow_context_workflows",
        "workflow_context_timestamp",
        "workflow_context_source_event",
    ]
    .iter()
    .any(|field| workflow_value_present(object_value(entry, field)))
    {
        return vec![finding(
            "behavior_event",
            label,
            "workflow-owner-fields-incoherent",
        )];
    }
    Vec::new()
}

fn workflow_owner_optional_mismatch(
    entry: &JsonObject,
    owner: Option<&JsonString>,
    selected: Option<&[JsonValue]>,
) -> bool {
    if object_has_field(entry, "selected_workflow")
        && !matches!(
            (owner, object_value(entry, "selected_workflow")),
            (Some(owner), Some(JsonValue::String(value))) if owner == value
        )
    {
        return true;
    }
    if object_has_field(entry, "workflow")
        && !matches!(
            (selected, as_array(object_value(entry, "workflow"))),
            (Some(selected), Some(workflow)) if json_sequences_equal(workflow, selected)
        )
    {
        return true;
    }
    if object_has_field(entry, "workflow_family")
        && !matches!(
            (owner, object_value(entry, "workflow_family")),
            (Some(owner), Some(JsonValue::String(value))) if owner == value
        )
    {
        return true;
    }
    if object_has_field(entry, "workflow_selection_kind")
        && !string_equals(
            object_value(entry, "workflow_selection_kind"),
            "declared_workflow",
        )
    {
        return true;
    }
    object_value(entry, "selected_workflow_count")
        .is_some_and(|value| !value_equals_usize(value, selected.map_or(0, <[JsonValue]>::len)))
}

fn workflow_context_findings(label: &str, entry: &JsonObject) -> Vec<Finding> {
    let workflows = as_array(object_value(entry, "workflow_context_workflows"));
    let coherent_context = workflows.is_some_and(|workflows| !workflows.is_empty())
        && [
            "workflow_context_kind",
            "workflow_context_source",
            "workflow_context_timestamp",
            "workflow_context_source_event",
        ]
        .iter()
        .all(|field| as_string(object_value(entry, field)).is_some_and(string_is_nonempty))
        && string_equals(
            object_value(entry, "workflow_selection_kind"),
            "context_workflow",
        );
    let owner_fields_present = [
        "selected_workflow",
        "selected_workflows",
        "workflow",
        "workflow_family",
        "workflow_owner",
        "workflow_owner_workflows",
        "selected_workflow_count",
    ]
    .iter()
    .any(|field| workflow_value_present(object_value(entry, field)));
    if coherent_context && !owner_fields_present {
        Vec::new()
    } else {
        vec![finding(
            "behavior_event",
            label,
            "workflow-context-fields-incoherent",
        )]
    }
}

fn workflow_missing_findings(label: &str, entry: &JsonObject) -> Vec<Finding> {
    let fields = [
        "selected_workflow",
        "selected_workflows",
        "workflow",
        "workflow_family",
        "workflow_selection_kind",
        "workflow_owner",
        "workflow_owner_workflows",
        "workflow_context_kind",
        "workflow_context_source",
        "workflow_context_workflows",
        "workflow_context_timestamp",
        "workflow_context_source_event",
        "selected_workflow_count",
    ];
    if fields
        .iter()
        .all(|field| !workflow_value_present(object_value(entry, field)))
    {
        Vec::new()
    } else {
        vec![finding(
            "behavior_event",
            label,
            "workflow-missing-fields-incoherent",
        )]
    }
}

fn prompt_missing_fields_are_coherent(entry: &JsonObject) -> bool {
    let empty_string = JsonValue::String(JsonString::default());
    let zero = JsonValue::Number(JsonNumber::Integer("0".to_owned()));
    let false_value = JsonValue::Bool(false);
    [
        object_value(entry, "prompt_excerpt_redacted"),
        object_value(entry, "prompt_fingerprint"),
        object_value(entry, "prompt_char_count"),
        object_value(entry, "prompt_excerpt_truncated"),
    ]
    .into_iter()
    .zip([&empty_string, &empty_string, &zero, &false_value])
    .all(|(actual, expected)| actual.is_some_and(|actual| python_json_equal(actual, expected)))
}

fn prompt_char_count_is_positive_int_instance(value: Option<&JsonValue>) -> bool {
    match value {
        Some(JsonValue::Bool(value)) => *value,
        Some(JsonValue::Number(JsonNumber::Integer(value))) => {
            !value.starts_with('-') && value != "0"
        }
        _ => false,
    }
}

fn behavior_prompt_findings(label: &str, entry: &JsonObject) -> Vec<Finding> {
    let mut findings = Vec::new();
    let prompt_status = object_value(entry, "prompt_capture_status");
    let excerpt = as_string(object_value(entry, "prompt_excerpt_redacted"));
    let fingerprint = as_string(object_value(entry, "prompt_fingerprint"));
    let char_count = object_value(entry, "prompt_char_count");
    let truncated = object_value(entry, "prompt_excerpt_truncated");

    if !PROMPT_CAPTURE_STATUSES
        .iter()
        .any(|status| string_equals(prompt_status, status))
    {
        findings.push(finding(
            "behavior_event",
            label,
            "invalid-prompt-capture-status",
        ));
    }
    if excerpt.is_none_or(|excerpt| excerpt.0.len() > 600) {
        findings.push(finding("behavior_event", label, "invalid-prompt-excerpt"));
    }
    if fingerprint.is_none() {
        findings.push(finding(
            "behavior_event",
            label,
            "invalid-prompt-fingerprint",
        ));
    }
    if !is_nonnegative_int(char_count) {
        findings.push(finding(
            "behavior_event",
            label,
            "invalid-prompt-char-count",
        ));
    }
    if !matches!(truncated, Some(JsonValue::Bool(_))) {
        findings.push(finding("behavior_event", label, "invalid-prompt-truncated"));
    }

    if string_equals(prompt_status, "present") {
        let coherent_present = fingerprint
            .is_some_and(|fingerprint| regex_fullmatch(&PROMPT_FINGERPRINT_RE, fingerprint))
            && prompt_char_count_is_positive_int_instance(char_count);
        if !coherent_present {
            findings.push(finding(
                "behavior_event",
                label,
                "prompt-present-fields-incoherent",
            ));
        }
        if excerpt.is_some_and(|excerpt| &redact_sensitive_text(excerpt) != excerpt) {
            findings.push(finding(
                "behavior_event",
                label,
                "prompt-excerpt-secret-material",
            ));
        }
    } else if string_equals(prompt_status, "missing") && !prompt_missing_fields_are_coherent(entry)
    {
        findings.push(finding(
            "behavior_event",
            label,
            "prompt-missing-fields-incoherent",
        ));
    }

    if let Some(cause) = object_value(entry, "prompt_capture_reason") {
        if !matches!(cause, JsonValue::Null)
            && !as_string(Some(cause))
                .is_some_and(|cause| regex_fullmatch(&PROMPT_CAPTURE_CAUSE_RE, cause))
        {
            findings.push(finding(
                "behavior_event",
                label,
                "invalid-prompt-capture-reason",
            ));
        }
    }
    findings
}

fn behavior_event_findings(label: &str, entry: &JsonObject) -> Vec<Finding> {
    if !string_equals(object_value(entry, "schema"), BEHAVIOR_EVENT_SCHEMA) {
        if BEHAVIOR_HINT_FIELDS
            .iter()
            .any(|field| object_has_field(entry, field))
        {
            return vec![finding("behavior_event", label, "legacy-behavior-schema")];
        }
        return Vec::new();
    }
    let mut findings = behavior_envelope_findings(label, entry);
    findings.extend(behavior_workflow_findings(label, entry));
    findings.extend(behavior_prompt_findings(label, entry));
    findings
}

fn parse_hook_line(
    root: &Path,
    path: &Path,
    line_number: usize,
    raw_line: &str,
) -> (Vec<u32>, usize, Vec<Finding>) {
    let label = format!("{}:{line_number}", relative(root, path));
    let loaded = match parse_json(raw_line) {
        Ok(value) => value,
        Err(_) => {
            return (
                Vec::new(),
                0,
                vec![finding("hook_jsonl", &label, "invalid-json")],
            )
        }
    };
    let JsonValue::Object(entry) = loaded else {
        return (
            Vec::new(),
            0,
            vec![finding("hook_jsonl", &label, "entry-not-object")],
        );
    };
    let parent_name = path
        .parent()
        .and_then(Path::file_name)
        .map(|name| name.to_string_lossy());
    let namespaced = !matches!(parent_name.as_deref(), Some("hook-runs" | "legacy-import"));
    let required_fields: &[&str] = if namespaced {
        HOOK_REQUIRED_FIELDS
    } else {
        &["hook_run_id", "timestamp", "payload_fingerprint"]
    };
    let mut findings = Vec::new();
    for field in required_fields {
        if !as_string(object_value(&entry, field)).is_some_and(string_is_nonempty) {
            findings.push(finding(
                "hook_jsonl",
                &label,
                format!("missing-field:{field}"),
            ));
        }
    }
    let legacy_missing_namespace = usize::from(
        namespaced
            && !matches!(
                object_value(&entry, "hook_log_namespace"),
                Some(JsonValue::String(_))
            ),
    );
    findings.extend(behavior_event_findings(&label, &entry));
    let run_id = match object_value(&entry, "hook_run_id") {
        Some(JsonValue::String(run_id)) => run_id.0.clone(),
        _ => Vec::new(),
    };
    (run_id, legacy_missing_namespace, findings)
}

fn collect_hook_files(directory: &Path, files: &mut HashSet<PathBuf>) -> Result<(), String> {
    let mut pending = vec![directory.to_path_buf()];
    while let Some(directory) = pending.pop() {
        let entries = fs::read_dir(&directory).map_err(|error| {
            format!(
                "read hook result directory {}: {error}",
                directory.display()
            )
        })?;
        for entry in entries {
            let entry = entry.map_err(|error| {
                format!(
                    "read hook result directory {}: {error}",
                    directory.display()
                )
            })?;
            let path = entry.path();
            let file_type = entry
                .file_type()
                .map_err(|error| format!("inspect hook result {}: {error}", path.display()))?;
            if file_type.is_dir() {
                pending.push(path.clone());
            }
            if path.extension().and_then(|extension| extension.to_str()) == Some("jsonl")
                && path.file_name().and_then(|name| name.to_str()) != Some(HOOK_SPOOL_INDEX_NAME)
            {
                files.insert(path);
            }
        }
    }
    Ok(())
}

fn git_check_ignored(root: &Path, path: &Path) -> Result<bool, String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["check-ignore", "-q", "--"])
        .arg(relative(root, path))
        .output()
        .map_err(|error| format!("run git check-ignore: {error}"))?;
    Ok(output.status.code() == Some(0))
}

fn intentionally_ignored_archive_path(path: &Path) -> bool {
    let mut has_archive = false;
    let mut has_archive_repository = false;
    for component in path.components() {
        let value = component.as_os_str().to_string_lossy();
        has_archive |= value == "archive";
        has_archive_repository |= value == "agent-canon-log";
    }
    has_archive && has_archive_repository
}

fn ignored_path_findings(root: &Path, paths: &[PathBuf]) -> Result<Vec<Finding>, String> {
    let mut findings = Vec::new();
    for path in paths {
        if !intentionally_ignored_archive_path(path) && git_check_ignored(root, path)? {
            findings.push(finding(
                "gitignore",
                &relative(root, path),
                "ignored-result-path",
            ));
        }
    }
    Ok(findings)
}

fn hook_result_findings(
    root: &Path,
    hook_dirs: &[PathBuf],
) -> Result<(usize, usize, usize, Vec<Finding>), String> {
    let mut files = HashSet::new();
    for directory in hook_dirs {
        if directory.is_dir() {
            collect_hook_files(directory, &mut files)?;
        }
    }
    let mut files: Vec<PathBuf> = files.into_iter().collect();
    files.sort_by_key(|path| path_sort_key(path));
    let mut findings = Vec::new();
    let mut seen_run_ids: HashMap<Vec<u32>, String> = HashMap::new();
    let mut entries = 0usize;
    let mut legacy_missing_namespace = 0usize;

    for path in &files {
        let content = fs::read_to_string(path)
            .map_err(|error| format!("read hook result {}: {error}", path.display()))?;
        for (index, raw_line) in python_splitlines(&content).into_iter().enumerate() {
            if python_strip(raw_line).is_empty() {
                continue;
            }
            entries += 1;
            let (run_id, line_legacy_missing_namespace, line_findings) =
                parse_hook_line(root, path, index + 1, raw_line);
            legacy_missing_namespace += line_legacy_missing_namespace;
            findings.extend(line_findings);
            if run_id.is_empty() {
                continue;
            }
            let label = format!("{}:{}", relative(root, path), index + 1);
            if let Some(previous) = seen_run_ids.get(&run_id) {
                findings.push(finding(
                    "hook_run_id",
                    &label,
                    format!("duplicate:{previous}"),
                ));
            }
            seen_run_ids.insert(run_id, label);
        }
    }
    if !files.is_empty() && entries == 0 {
        let labels = hook_dirs
            .iter()
            .map(|directory| relative(root, directory))
            .collect::<Vec<_>>()
            .join(",");
        findings.push(finding("hook_jsonl", &labels, "no-hook-entries"));
    }
    findings.extend(ignored_path_findings(root, &files)?);
    Ok((files.len(), entries, legacy_missing_namespace, findings))
}

fn markdown_reports(results_dirs: &[PathBuf]) -> Result<Vec<PathBuf>, String> {
    let mut reports = HashSet::new();
    for directory in results_dirs {
        if !directory.is_dir() {
            continue;
        }
        let entries = fs::read_dir(directory).map_err(|error| {
            format!(
                "read eval result directory {}: {error}",
                directory.display()
            )
        })?;
        for entry in entries {
            let entry = entry.map_err(|error| {
                format!(
                    "read eval result directory {}: {error}",
                    directory.display()
                )
            })?;
            let path = entry.path();
            if path.extension().and_then(|extension| extension.to_str()) == Some("md")
                && path.file_name().and_then(|name| name.to_str()) != Some("README.md")
            {
                reports.insert(path);
            }
        }
    }
    let mut reports: Vec<PathBuf> = reports.into_iter().collect();
    reports.sort_by_key(|path| path_sort_key(path));
    Ok(reports)
}

fn missing_reports_label(root: &Path, results_dirs: &[PathBuf]) -> String {
    results_dirs
        .iter()
        .map(|path| relative(root, path))
        .collect::<Vec<_>>()
        .join(",")
}

fn reports_required(results_dirs: &[PathBuf], archive_mounted: bool) -> bool {
    archive_mounted || results_dirs.iter().any(|directory| directory.is_dir())
}

fn registry_string(table: &dyn TableLike, field: &str) -> Result<String, String> {
    table
        .get(field)
        .and_then(toml_edit::Item::as_str)
        .map(python_strip)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| format!("eval family registry entry missing string field: {field}"))
}

fn load_family_contracts(registry_path: &Path) -> Result<Vec<EvalFamilyContract>, String> {
    let source = fs::read_to_string(registry_path).map_err(|error| {
        format!(
            "read eval family registry {}: {error}",
            registry_path.display()
        )
    })?;
    let document = source.parse::<DocumentMut>().map_err(|error| {
        format!(
            "parse eval family registry {}: {error}",
            registry_path.display()
        )
    })?;
    let families_item = document.get("families");
    let families: Vec<&dyn TableLike> = if let Some(families) =
        families_item.and_then(toml_edit::Item::as_array_of_tables)
    {
        families
            .iter()
            .map(|family| family as &dyn TableLike)
            .collect()
    } else if let Some(families) = families_item.and_then(toml_edit::Item::as_array) {
        families
            .iter()
            .map(|family| {
                family
                    .as_inline_table()
                    .map(|family| family as &dyn TableLike)
                    .ok_or_else(|| "eval family registry entries must be TOML tables".to_owned())
            })
            .collect::<Result<Vec<_>, _>>()?
    } else {
        return Err("eval family registry must define at least one [[families]] entry".to_owned());
    };
    if families.is_empty() {
        return Err("eval family registry must define at least one [[families]] entry".to_owned());
    }
    let mut contracts = Vec::with_capacity(families.len());
    let mut seen_ids = HashSet::new();
    let mut seen_labels = HashSet::new();
    for family in families.iter() {
        let family_id = registry_string(family, "id")?;
        let check_id = registry_string(family, "check_id")?;
        let count_label = registry_string(family, "count_label")?;
        let _summary = registry_string(family, "summary")?;
        let _producer = registry_string(family, "producer")?;
        let filename_regex = registry_string(family, "filename_regex")?;
        let run_id_regex = registry_string(family, "run_id_regex")?;
        let missing_reports_detail = registry_string(family, "missing_reports_detail")?;
        let missing_run_id_detail = registry_string(family, "missing_run_id_detail")?;
        let duplicate_run_id_detail = registry_string(family, "duplicate_run_id_detail")?;
        let contract = EvalFamilyContract {
            family_id,
            check_id,
            count_label,
            filename_regex,
            run_id_regex,
            missing_reports_detail,
            missing_run_id_detail,
            duplicate_run_id_detail,
        };
        if !seen_ids.insert(contract.family_id.clone()) {
            return Err(format!("duplicate eval family id: {}", contract.family_id));
        }
        if !seen_labels.insert(contract.count_label.clone()) {
            return Err(format!(
                "duplicate eval family count label: {}",
                contract.count_label
            ));
        }
        Regex::new(&contract.filename_regex).map_err(|error| {
            format!("invalid filename regex for {}: {error}", contract.family_id)
        })?;
        Regex::new(&contract.run_id_regex)
            .map_err(|error| format!("invalid run-id regex for {}: {error}", contract.family_id))?;
        contracts.push(contract);
    }
    Ok(contracts)
}

fn eval_family_findings(
    root: &Path,
    contract: &EvalFamilyContract,
    results_dirs: &[PathBuf],
    require_reports: bool,
) -> Result<(usize, Vec<Finding>), String> {
    let reports = markdown_reports(results_dirs)?;
    let filename_pattern = Regex::new(&contract.filename_regex)
        .map_err(|error| format!("invalid filename regex for {}: {error}", contract.family_id))?;
    let run_id_pattern = Regex::new(&contract.run_id_regex)
        .map_err(|error| format!("invalid run-id regex for {}: {error}", contract.family_id))?;
    let mut findings = Vec::new();
    let mut seen_run_ids: HashMap<String, String> = HashMap::new();
    if reports.is_empty() && require_reports {
        findings.push(finding(
            &contract.check_id,
            &missing_reports_label(root, results_dirs),
            &contract.missing_reports_detail,
        ));
    }
    for path in &reports {
        let label = relative(root, path);
        let file_name = path
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or_default();
        if filename_pattern.find(file_name).is_none_or(|matched| {
            matched.start() != 0 || matched.end() != file_name.len()
        }) {
            findings.push(finding(&contract.check_id, &label, "invalid-report-name"));
        }
        let text = fs::read_to_string(path)
            .map_err(|error| format!("read eval report {}: {error}", path.display()))?;
        let run_id = run_id_pattern
            .captures(&text)
            .and_then(|captures| captures.get(1))
            .map(|capture| capture.as_str().to_owned());
        let Some(run_id) = run_id else {
            findings.push(finding(
                &contract.check_id,
                &label,
                &contract.missing_run_id_detail,
            ));
            continue;
        };
        if let Some(previous) = seen_run_ids.get(&run_id) {
            findings.push(finding(
                &contract.check_id,
                &label,
                format!("{}:{previous}", contract.duplicate_run_id_detail),
            ));
        }
        seen_run_ids.insert(run_id, label);
    }
    findings.extend(ignored_path_findings(root, &reports)?);
    Ok((reports.len(), findings))
}

fn validate(
    requested_root: &Path,
    family_registry: &str,
    runtime_root: Option<&Path>,
) -> Result<EvalAccumulationReport, ValidationError> {
    let requested_root = crate::path_resolution::resolve_non_strict(requested_root)
        .map_err(ValidationError::Other)?;
    let canon_root = requested_root.clone();
    let registry_path = resolve_eval_manifest(&canon_root, family_registry);
    let contracts = load_family_contracts(&registry_path).map_err(ValidationError::Other)?;
    let hook_dirs = hook_result_search_dirs(&requested_root, &canon_root, runtime_root)
        .map_err(ValidationError::Archive)?;
    let (hook_files, hook_entries, hook_legacy_missing_namespace, hook_findings) =
        hook_result_findings(&canon_root, &hook_dirs).map_err(ValidationError::Other)?;
    let archive_mounted = mounted_log_archive_root(&canon_root, runtime_root)
        .map_err(ValidationError::Archive)?
        .is_dir();
    let mut eval_report_counts = BTreeMap::new();
    let mut findings = hook_findings;
    for contract in &contracts {
        let results_dirs = eval_result_search_dirs(&canon_root, &contract.family_id, runtime_root)
            .map_err(ValidationError::Archive)?;
        let (report_count, family_findings) = eval_family_findings(
            &canon_root,
            contract,
            &results_dirs,
            reports_required(&results_dirs, archive_mounted),
        )
        .map_err(ValidationError::Other)?;
        eval_report_counts.insert(contract.family_id.clone(), report_count);
        findings.extend(family_findings);
    }
    findings.sort_by(|left, right| {
        (&left.check, &left.path, &left.detail).cmp(&(&right.check, &right.path, &right.detail))
    });
    Ok(EvalAccumulationReport {
        hook_files,
        hook_entries,
        hook_legacy_missing_namespace,
        eval_report_counts,
        findings,
    })
}

fn mounted_archive_path_label(path_label: &str) -> bool {
    let path = if cfg!(windows) {
        path_label.replace('\\', "/")
    } else {
        path_label.to_owned()
    };
    path.contains("archive/agent-canon-log/")
}

fn is_warning_finding(finding: &Finding) -> bool {
    if finding.check == "hook_jsonl" && mounted_archive_path_label(&finding.path) {
        return true;
    }
    (finding.detail.starts_with("missing-")
        && finding.detail.ends_with("-eval-run-id")
        && finding
            .path
            .contains("archive/agent-canon-log/eval-results/legacy-import/"))
        || (finding.check == "behavior_event" && finding.detail == "legacy-behavior-schema")
}

fn blocking_findings(report: &EvalAccumulationReport) -> Vec<&Finding> {
    report
        .findings
        .iter()
        .filter(|finding| !is_warning_finding(finding))
        .collect()
}

fn warning_findings(report: &EvalAccumulationReport) -> Vec<&Finding> {
    report
        .findings
        .iter()
        .filter(|finding| is_warning_finding(finding))
        .collect()
}

fn report_status(report: &EvalAccumulationReport) -> &'static str {
    if blocking_findings(report).is_empty() {
        "pass"
    } else {
        "fail"
    }
}

fn eval_report_count(report: &EvalAccumulationReport, family_id: &str) -> usize {
    report
        .eval_report_counts
        .get(family_id)
        .copied()
        .unwrap_or(0)
}

fn family_count_lines(report: &EvalAccumulationReport) -> Vec<String> {
    report
        .eval_report_counts
        .iter()
        .map(|(family_id, count)| format!("EVAL_ACCUMULATION_FAMILY_REPORTS={family_id}:{count}"))
        .collect()
}

fn python_ascii_json(pretty_json: String) -> String {
    let mut output = String::with_capacity(pretty_json.len());
    let mut in_string = false;
    let mut escaped = false;
    for character in pretty_json.chars() {
        if !in_string {
            output.push(character);
            if character == '"' {
                in_string = true;
            }
            continue;
        }
        if escaped {
            output.push(character);
            escaped = false;
        } else if character == '\\' {
            output.push(character);
            escaped = true;
        } else if character == '"' {
            output.push(character);
            in_string = false;
        } else if character.is_ascii() {
            output.push(character);
        } else {
            let codepoint = character as u32;
            if codepoint <= 0xffff {
                output.push_str(&format!("\\u{codepoint:04x}"));
            } else {
                let adjusted = codepoint - 0x1_0000;
                let high = 0xd800 + (adjusted >> 10);
                let low = 0xdc00 + (adjusted & 0x3ff);
                output.push_str(&format!("\\u{high:04x}\\u{low:04x}"));
            }
        }
    }
    output
}

fn pretty_json(value: &JsonOutput) -> String {
    python_ascii_json(
        serde_json::to_string_pretty(value).expect("eval accumulation JSON is serializable"),
    )
}

fn render_json(report: &EvalAccumulationReport) -> String {
    let blocking = blocking_findings(report);
    let warnings = warning_findings(report);
    let findings: Vec<JsonOutput> = report.findings.iter().map(Finding::as_json).collect();
    pretty_json(&json!({
        "status": report_status(report),
        "hook_files": report.hook_files,
        "hook_entries": report.hook_entries,
        "hook_legacy_missing_namespace": report.hook_legacy_missing_namespace,
        "hook_namespace_debt": report.hook_legacy_missing_namespace,
        "eval_report_counts": &report.eval_report_counts,
        "workflow_selection_reports": eval_report_count(report, "workflow-selection"),
        "codex_agent_role_reports": eval_report_count(report, "codex-agent-role"),
        "blocking_finding_count": blocking.len(),
        "warning_count": warnings.len(),
        "findings": findings,
    }))
}

fn compact_summary(report: &EvalAccumulationReport) -> JsonOutput {
    let mut finding_counts = BTreeMap::new();
    for finding in &report.findings {
        *finding_counts
            .entry(finding.check.clone())
            .or_insert(0usize) += 1;
    }
    let blocking = blocking_findings(report);
    let warnings = warning_findings(report);
    let finding_samples: Vec<JsonOutput> = report
        .findings
        .iter()
        .take(COMPACT_FINDING_SAMPLE_LIMIT)
        .map(Finding::as_json)
        .collect();
    let blocking_samples: Vec<JsonOutput> = blocking
        .iter()
        .take(COMPACT_FINDING_SAMPLE_LIMIT)
        .map(|finding| finding.as_json())
        .collect();
    let warning_samples: Vec<JsonOutput> = warnings
        .iter()
        .take(COMPACT_FINDING_SAMPLE_LIMIT)
        .map(|finding| finding.as_json())
        .collect();
    json!({
        "status": report_status(report),
        "finding_count": report.findings.len(),
        "blocking_finding_count": blocking.len(),
        "warning_count": warnings.len(),
        "finding_counts": finding_counts,
        "hook_files": report.hook_files,
        "hook_entries": report.hook_entries,
        "hook_legacy_missing_namespace": report.hook_legacy_missing_namespace,
        "hook_namespace_debt": report.hook_legacy_missing_namespace,
        "eval_report_counts": &report.eval_report_counts,
        "workflow_selection_reports": eval_report_count(report, "workflow-selection"),
        "codex_agent_role_reports": eval_report_count(report, "codex-agent-role"),
        "blocking_finding_samples": blocking_samples,
        "warning_samples": warning_samples,
        "finding_samples": finding_samples,
    })
}

fn write_compact_summary(
    source_root: &Path,
    runtime_root: Option<&Path>,
    path: &Path,
    report: &EvalAccumulationReport,
) -> Result<(), String> {
    RuntimeArtifactBoundary::resolve_read_path(source_root, runtime_root, path)?;
    let selected_runtime_root = runtime_root.map(Path::to_path_buf).or_else(|| {
        env::var_os(RUNTIME_ROOT_ENV)
            .and_then(|value| value.into_string().ok())
            .map(|value| python_strip(&value).to_owned())
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
    });
    let boundary =
        RuntimeArtifactBoundary::for_source(source_root, selected_runtime_root.as_deref(), true)?;
    let mut text = pretty_json(&compact_summary(report));
    text.push('\n');
    boundary.atomic_write_text(path, &text, 0o600)?;
    Ok(())
}

fn render_text(
    report: &EvalAccumulationReport,
    include_details: bool,
    compact_out: Option<&Path>,
) -> String {
    let blocking = blocking_findings(report);
    let warnings = warning_findings(report);
    let mut lines = Vec::new();
    if include_details {
        lines.extend(report.findings.iter().map(Finding::render));
    }
    lines.extend([
        format!("EVAL_ACCUMULATION_HOOK_FILES={}", report.hook_files),
        format!("EVAL_ACCUMULATION_HOOK_ENTRIES={}", report.hook_entries),
        format!(
            "EVAL_ACCUMULATION_HOOK_LEGACY_MISSING_NAMESPACE={}",
            report.hook_legacy_missing_namespace
        ),
        format!(
            "EVAL_ACCUMULATION_HOOK_NAMESPACE_DEBT={}",
            report.hook_legacy_missing_namespace
        ),
        format!(
            "EVAL_ACCUMULATION_WORKFLOW_SELECTION_REPORTS={}",
            eval_report_count(report, "workflow-selection")
        ),
        format!(
            "EVAL_ACCUMULATION_CODEX_AGENT_ROLE_REPORTS={}",
            eval_report_count(report, "codex-agent-role")
        ),
    ]);
    lines.extend(family_count_lines(report));
    lines.extend([
        format!("EVAL_ACCUMULATION_FINDINGS={}", report.findings.len()),
        format!("EVAL_ACCUMULATION_BLOCKING_FINDINGS={}", blocking.len()),
        format!("EVAL_ACCUMULATION_WARNINGS={}", warnings.len()),
        format!("EVAL_ACCUMULATION={}", report_status(report)),
    ]);
    if let Some(compact_out) = compact_out {
        lines.push(format!(
            "EVAL_ACCUMULATION_COMPACT_OUT={}",
            path_as_posix(compact_out)
        ));
    }
    let mut text = lines.join("\n");
    text.push('\n');
    text
}

fn print_archive_error(format: &str, error: &str) {
    if format == "json" {
        println!(
            "{}",
            pretty_json(&json!({
                "status": "error",
                "error_code": "log_archive_required",
                "message": error,
                "next_action": ERROR_NEXT_ACTION,
            }))
        );
    } else {
        println!("EVAL_ACCUMULATION=error");
        println!("EVAL_ACCUMULATION_ERROR_CODE=log_archive_required");
        println!("EVAL_ACCUMULATION_ERROR={error}");
        println!("NEXT_ACTION=pass_--runtime-root_or_set_AGENT_CANON_RUNTIME_ROOT");
    }
}

/// Run the native eval accumulation checker CLI.
pub fn run_cli(args: &[String]) -> i32 {
    let options = match parse_arguments(args) {
        Ok(Some(options)) => options,
        Ok(None) => {
            print_help();
            return 0;
        }
        Err(error) => {
            eprintln!("{}", usage());
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let root = match crate::path_resolution::resolve_non_strict(&options.root) {
        Ok(root) => root,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: {error}");
            return 1;
        }
    };
    let report = match validate(
        &root,
        &options.family_registry,
        options.runtime_root.as_deref(),
    ) {
        Ok(report) => report,
        Err(ValidationError::Archive(error)) => {
            print_archive_error(&options.format, &error);
            return 1;
        }
        Err(ValidationError::Other(error)) => {
            eprintln!("agent-canon {SELECTOR}: {error}");
            return 1;
        }
    };
    if let Some(compact_out) = options.compact_out.as_deref() {
        if let Err(error) =
            write_compact_summary(&root, options.runtime_root.as_deref(), compact_out, &report)
        {
            eprintln!("agent-canon {SELECTOR}: {error}");
            return 1;
        }
    }
    if options.format == "json" {
        println!("{}", render_json(&report));
    } else {
        print!(
            "{}",
            render_text(
                &report,
                options.compact_out.is_none(),
                options.compact_out.as_deref()
            )
        );
    }
    i32::from(!blocking_findings(&report).is_empty())
}
