// @dependency-start
// contract implementation
// responsibility Dispatches the bounded active Hook contract through existing pure safety, authority, selection, assembly, and spool owners.
// upstream implementation ../../../../../.codex/hooks/hook_dispatcher.py owns the active CLI and event contract.
// upstream implementation ./hook_safety.rs owns secret and protected-Git decisions.
// upstream implementation ./mutation_authority.rs owns writer-target and child-scope admission.
// upstream implementation ./hook_event_log.rs owns append-only hook event publication.
// downstream implementation ../main.rs exposes the native codex-hook CLI route.
// downstream test ../tests/hook_dispatcher_native.rs checks the captured CPython CLI corpus.
// downstream test ../../../../../tests/fixtures/hook_dispatcher/python_golden.json freezes old CLI inputs and outputs.
// @dependency-end
//! Native active Codex hook CLI and event dispatcher.

use crate::agent_canon_source_root::{resolve_agent_canon_source_root, LAYOUT_STANDALONE};
use crate::authority::{
    AttestationRequest, AttestedParent, NonEmptyTrimmedString, Nonce128, ParentRootAttestor,
};
use crate::behavior_event_assembly::{
    record_hook_invocation, FinalHandlerResult, HookInvocationParts,
};
use crate::execution_resource_projection::{
    projection_context_payload, validate_normalized_input, validate_projection_bytes,
    ProjectionError,
};
use crate::hook_event_log::{utc_now, HookLogContext};
use crate::hook_report_projection::emit_behavior_projection;
use crate::hook_retirement::{source_digest, MOVED_SOURCE_ABSENCES, RETIRED_CHILD_TOMBSTONES};
use crate::hook_safety::{
    branch_block_payload, first_block, payload_prompt_json, payload_tool_command_json,
    payload_tool_name_json, secret_block_payload, secret_kind_json, SHELL_TOOL_NAMES,
};
use crate::mutation_authority::{
    evaluate_mutation_authority, mutation_block_payload, MutationAuthorityContext,
};
use crate::path_resolution::resolve_non_strict;
use crate::prompt_classifier::PromptClassifierInputs;
use crate::python_json::{
    canonical_json_ascii_bytes_reject_nonfinite, parse_json, parse_json_reject_duplicates,
    python_json_ascii_bytes, JsonArray, JsonNumber, JsonObject, JsonString, JsonValue,
};
use crate::python_text::python_strip;
use crate::subagent_selection::{build_coordination_receipt, select_subagents};
use crate::tool_selection::select_tools;
use crate::workflow_context::load_workflow_context;
use icu_casemap::CaseMapper;
use serde_json::Value as SerdeValue;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};

pub const OFFICIAL_HOOK_SCHEMA: &str = "agent-canon.posttooluse-stop.v1";
pub const HOOK_CONTRACT_SCHEMA: &str = "agent-canon.hook-contract.v1";
pub const POST_TOOL_USE_INPUT_SCHEMA: &str = "agent-canon-post-tool-use-input/v1";
pub const MAX_HOOK_PAYLOAD_BYTES: usize = 256 * 1024;

const SOURCE_ROOT_FALLBACK: &str = env!("CARGO_MANIFEST_DIR");
const DISPATCHER_SOURCE_ROOT_ENV: &str = "AGENT_CANON_HOOK_SOURCE_ROOT";
const WORKFLOW_MONITOR_REPORT_DIR_ENV: &str = "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR";
const ACTIVE_RUN_POINTER: &str = "reports/agents/.active_run";
const REPORT_ROOT_RELATIVE: &str = "reports/agents";
const PARENT_ROOT_ENV: &str = "AGENT_CANON_PARENT_ROOT";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct HookEventContract {
    pub active: bool,
    pub matchers: &'static [&'static str],
    pub failure: &'static str,
    pub telemetry: &'static str,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum HookRootStatus {
    Resolved,
    Override,
    Failed,
}

#[derive(Clone, Debug)]
struct HookRootState {
    active_root: PathBuf,
    standalone: bool,
    status: HookRootStatus,
}

impl HookRootState {
    fn report_projection_enabled(&self) -> bool {
        self.status != HookRootStatus::Failed
    }
}

pub const HOOK_EVENT_CONTRACTS: [(&str, HookEventContract); 4] = [
    (
        "UserPromptSubmit",
        HookEventContract {
            active: true,
            matchers: &[],
            failure: "secret_match=block; malformed_payload=fail_open; spool_failure=fail_open",
            telemetry: "one bounded fingerprint-only local spool event",
        },
    ),
    (
        "PreToolUse",
        HookEventContract {
            active: true,
            matchers: &["Bash|apply_patch|python|python3"],
            failure: "unauthorized_destructive_git=block; raw_git_merge_or_rebase=block; writer_target_packet_missing=block; writer_target_mismatch=block; malformed_payload=fail_open; spool_failure=fail_open",
            telemetry: "one bounded fingerprint-only local spool event",
        },
    ),
    (
        "PostToolUse",
        HookEventContract {
            active: true,
            matchers: &["Bash|apply_patch|python|python3|Task|spawn_agent|send_input|wait_agent|close_agent|resume_agent|send_message|followup_task|list_agents|interrupt_agent"],
            failure: "invalid_projection=fail_open; malformed_payload=fail_open; spool_failure=fail_open",
            telemetry: "one bounded fingerprint-only local spool event",
        },
    ),
    (
        "Stop",
        HookEventContract {
            active: false,
            matchers: &[],
            failure: "legacy_event_inactive_no_op",
            telemetry: "no active hook telemetry",
        },
    ),
];

pub const ACTIVE_HOOK_HANDLERS: [&str; 3] = [
    "PostToolUse.execution_resource_projection",
    "PreToolUse.destructive_git_safety",
    "UserPromptSubmit.secret_safety",
];

/// Result of one CLI invocation with caller-supplied stdin and root environment.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HookCliResult {
    pub exit_code: i32,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
}

struct ParsedCliArgs {
    event: Option<String>,
    group: Option<String>,
    list: bool,
    contract: bool,
    help: bool,
}

/// Execute the native Hook CLI using one caller-provided input buffer and environment snapshot.
pub fn run_with_input(
    arguments: &[String],
    raw_payload: &[u8],
    environment: &BTreeMap<String, String>,
    current_directory: &Path,
) -> HookCliResult {
    execute_cli(arguments, raw_payload, environment, Some(current_directory))
}

fn execute_cli(
    arguments: &[String],
    raw_payload: &[u8],
    environment: &BTreeMap<String, String>,
    current_directory: Option<&Path>,
) -> HookCliResult {
    match parse_cli_args(arguments) {
        Err(error) => cli_error(2, &format!("{error}\n")),
        Ok(arguments) if arguments.help => cli_success(help_text().as_bytes().to_vec()),
        Ok(arguments) if arguments.list || arguments.contract => {
            let raw_event = effective_event(&arguments);
            let event = match raw_event.as_deref() {
                Some(raw_event) => match normalize_event(raw_event) {
                    Ok(event) => Some(event),
                    Err(error) => return cli_error(1, &format!("{error}\n")),
                },
                None => None,
            };
            json_stdout(&contract_payload(event.as_deref()))
        }
        Ok(arguments) => {
            let Some(raw_event) = effective_event(&arguments) else {
                return cli_error(1, "hook event is required\n");
            };
            let event = match normalize_event(&raw_event) {
                Ok(event) => event,
                Err(error) => return cli_error(1, &format!("{error}\n")),
            };
            match dispatch_event(&event, raw_payload, environment, current_directory) {
                Ok(result) => result,
                Err(error) => cli_error(1, &format!("{error}\n")),
            }
        }
    }
}

/// Run with process stdin, the selected root environment, and process stdout/stderr.
pub fn run(arguments: &[String]) -> i32 {
    let needs_stdin = match parse_cli_args(arguments) {
        Ok(parsed) if !parsed.help && !parsed.list && !parsed.contract => effective_event(&parsed)
            .as_deref()
            .is_some_and(|event| normalize_event(event).is_ok()),
        _ => false,
    };
    let mut raw_payload = Vec::new();
    if needs_stdin {
        if let Err(error) = std::io::stdin().lock().read_to_end(&mut raw_payload) {
            let message = format!("cannot read Hook input: {error}\n");
            let _ = std::io::stderr().lock().write_all(message.as_bytes());
            return 1;
        }
    }
    let environment = process_environment();
    let current_directory = env::current_dir().ok();
    let result = execute_cli(
        arguments,
        &raw_payload,
        &environment,
        current_directory.as_deref(),
    );
    if std::io::stdout().lock().write_all(&result.stdout).is_err() {
        return 1;
    }
    if std::io::stderr().lock().write_all(&result.stderr).is_err() {
        return 1;
    }
    result.exit_code
}

fn parse_cli_args(arguments: &[String]) -> Result<ParsedCliArgs, String> {
    let mut event = None;
    let mut group = None;
    let mut list = false;
    let mut contract = false;
    let mut help = false;
    let mut positional_only = false;
    let mut index = 0;
    while index < arguments.len() {
        let token = &arguments[index];
        if positional_only {
            if event.replace(token.clone()).is_some() {
                return Err(format!("unrecognized arguments: {token}"));
            }
            index += 1;
            continue;
        }
        if token == "--" {
            positional_only = true;
            index += 1;
            continue;
        }
        if matches!(token.as_str(), "-h" | "--help") {
            help = true;
            index += 1;
            continue;
        }
        if token == "--list" {
            list = true;
            index += 1;
            continue;
        }
        if token == "--contract" {
            contract = true;
            index += 1;
            continue;
        }
        if token == "--group" || token.starts_with("--group=") {
            let value = if let Some((_, value)) = token.split_once('=') {
                value.to_owned()
            } else {
                index += 1;
                let Some(value) = arguments.get(index) else {
                    return Err("argument --group: expected one argument".to_owned());
                };
                value.clone()
            };
            group = Some(value);
            index += 1;
            continue;
        }
        if token.starts_with("--") {
            let (option, value) = token
                .split_once('=')
                .map_or((token.as_str(), None), |(option, value)| {
                    (option, Some(value))
                });
            let matches = ["--group", "--list", "--contract"]
                .iter()
                .copied()
                .filter(|candidate| candidate.starts_with(option))
                .collect::<Vec<_>>();
            if matches.len() == 1 {
                match (matches[0], value) {
                    ("--group", Some(value)) => group = Some(value.to_owned()),
                    ("--group", None) => {
                        index += 1;
                        let Some(value) = arguments.get(index) else {
                            return Err("argument --group: expected one argument".to_owned());
                        };
                        group = Some(value.clone());
                    }
                    ("--list", None) => list = true,
                    ("--contract", None) => contract = true,
                    _ => return Err(format!("option {option} does not take a value")),
                }
                index += 1;
                continue;
            }
            return Err(format!("unrecognized arguments: {token}"));
        }
        if token.starts_with('-') {
            return Err(format!("unrecognized arguments: {token}"));
        }
        if event.replace(token.clone()).is_some() {
            return Err(format!("unrecognized arguments: {token}"));
        }
        index += 1;
    }
    Ok(ParsedCliArgs {
        event,
        group,
        list,
        contract,
        help,
    })
}

fn effective_event(arguments: &ParsedCliArgs) -> Option<String> {
    arguments
        .group
        .as_ref()
        .filter(|group| !group.is_empty())
        .or(arguments.event.as_ref())
        .filter(|event| !event.is_empty())
        .cloned()
}

fn normalize_event(raw_event: &str) -> Result<String, String> {
    let folded = CaseMapper::new().fold_string(raw_event);
    let aliases = [
        ("userpromptsubmit", "UserPromptSubmit"),
        ("pretooluse", "PreToolUse"),
        ("posttooluse", "PostToolUse"),
        ("stop", "Stop"),
        ("user-prompt-submit", "UserPromptSubmit"),
        ("pre-tool-use", "PreToolUse"),
        ("post-tool-use", "PostToolUse"),
    ];
    aliases
        .iter()
        .find_map(|(alias, event)| (folded == *alias).then_some((*event).to_owned()))
        .ok_or_else(|| {
            format!(
                "unknown hook event '{}'; expected one of: UserPromptSubmit, PreToolUse, PostToolUse, Stop",
                raw_event.replace('\'', "\\'")
            )
        })
}

fn contract_payload(event: Option<&str>) -> JsonValue {
    let names = event.map_or_else(
        || {
            HOOK_EVENT_CONTRACTS
                .iter()
                .map(|(name, _)| *name)
                .collect::<Vec<_>>()
        },
        |event| vec![event],
    );
    let mut events = Vec::new();
    let mut active_events = Vec::new();
    let mut inactive_events = Vec::new();
    for name in &names {
        let contract = HOOK_EVENT_CONTRACTS
            .iter()
            .find(|(event_name, _)| event_name == name)
            .map(|(_, contract)| contract)
            .expect("normalized Hook event has a contract");
        let event_fields = vec![
            (key("active"), JsonValue::Bool(contract.active)),
            (key("matchers"), string_array_static(contract.matchers)),
            (key("failure"), text_value(contract.failure)),
            (key("telemetry"), text_value(contract.telemetry)),
        ];
        events.push((key(name), JsonValue::Object(JsonObject(event_fields))));
        if contract.active {
            active_events.push(JsonString::from_text(name));
        } else {
            inactive_events.push(JsonString::from_text(name));
        }
    }
    let retired = RETIRED_CHILD_TOMBSTONES
        .iter()
        .map(|row| row.to_json_value())
        .collect();
    let moved = MOVED_SOURCE_ABSENCES
        .iter()
        .map(|row| row.to_json_value())
        .collect();
    let count_fields = vec![
        (
            key("retired_child_tombstones"),
            integer_value(RETIRED_CHILD_TOMBSTONES.len()),
        ),
        (
            key("moved_source_absences"),
            integer_value(MOVED_SOURCE_ABSENCES.len()),
        ),
        (
            key("retired_filenames"),
            integer_value(RETIRED_CHILD_TOMBSTONES.len() + MOVED_SOURCE_ABSENCES.len()),
        ),
    ];
    object(vec![
        ("schema", text_value(HOOK_CONTRACT_SCHEMA)),
        ("events", JsonValue::Object(JsonObject(events))),
        ("active_events", string_array(&active_events)),
        ("inactive_events", string_array(&inactive_events)),
        (
            "active_handlers",
            string_array_static(&ACTIVE_HOOK_HANDLERS),
        ),
        (
            "retired_child_tombstones",
            JsonValue::Array(JsonArray(retired)),
        ),
        ("moved_source_absences", JsonValue::Array(JsonArray(moved))),
        ("counts", JsonValue::Object(JsonObject(count_fields))),
        ("source_digest", text_value(&source_digest())),
    ])
}

fn string_array_static(values: &[&str]) -> JsonValue {
    JsonValue::Array(JsonArray(
        values
            .iter()
            .map(|value| JsonValue::String(JsonString::from_text(value)))
            .collect(),
    ))
}

fn help_text() -> &'static str {
    "Run the canonical in-process Codex lifecycle hook contract.\n\nusage: hook_dispatcher.py [-h] [--group GROUP] [--list] [--contract] [event]\n\nCodex hook event to dispatch\nAlias for the event argument\nPrint the active/inactive hook contract\nPrint the canonical typed hook contract\n"
}

fn cli_success(stdout: Vec<u8>) -> HookCliResult {
    HookCliResult {
        exit_code: 0,
        stdout,
        stderr: Vec::new(),
    }
}

fn cli_error(exit_code: i32, message: &str) -> HookCliResult {
    HookCliResult {
        exit_code,
        stdout: Vec::new(),
        stderr: message.as_bytes().to_vec(),
    }
}

fn json_stdout(value: &JsonValue) -> HookCliResult {
    match python_json_ascii_bytes(value) {
        Ok(mut bytes) => {
            bytes.push(b'\n');
            cli_success(bytes)
        }
        Err(error) => cli_error(1, &format!("hook JSON output failed: {error}\n")),
    }
}

fn process_environment() -> BTreeMap<String, String> {
    const KEYS: &[&str] = &[
        "AGENT_CANON_HOOK_SOURCE_ROOT",
        "AGENT_CANON_TARGET_ROOT",
        "AGENT_CANON_TARGET_CONTAINER_ROOT",
        "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR",
        "AGENT_CANON_PARENT_ROOT",
        "AGENT_CANON_RUNTIME_ROOT",
        "AGENT_CANON_HOOK_RESULTS_DIR",
        "AGENT_CANON_HOOK_RUN_NAMESPACE",
        "AGENT_CANON_HOOK_EVENT_SPOOL_DIR",
        "AGENT_CANON_SOURCE_REPOSITORY_REMOTE",
        "AGENT_CANON_SOURCE_REPOSITORY_REMOTE_NAME",
        "AGENT_CANON_SOURCE_REPOSITORY_ID",
        "DEVCONTAINER_PROJECT_NAME",
        "COMPOSE_PROJECT_NAME",
        "CODEX_THREAD_ID",
        "CODEX_SESSION_ID",
        "CODEX_CONVERSATION_ID",
        "AGENT_CANON_RUNTIME_AGENT_ID",
        "AGENT_CANON_RUNTIME_ROLE_ID",
        "AGENT_CANON_RUNTIME_PARENT_AGENT_ID",
        "AGENT_CANON_CHECKOUT_ROOT",
        "AGENT_CANON_CHECKOUT_BRANCH",
        "AGENT_CANON_WRITER_ALLOWED_PATHS",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_WORK_TREE",
        "AGENT_CANON_SOURCE_ROOT",
        "AGENT_CANON_ROOT",
        "HOME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
    ];
    KEYS.iter()
        .filter_map(|key| env::var(key).ok().map(|value| ((*key).to_owned(), value)))
        .collect()
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn key(value: &str) -> JsonString {
    JsonString::from_text(value)
}

fn text_value(value: &str) -> JsonValue {
    JsonValue::String(JsonString::from_text(value))
}

fn integer_value(value: usize) -> JsonValue {
    JsonValue::Number(JsonNumber::Integer(value.to_string()))
}

fn empty_object() -> JsonValue {
    JsonValue::Object(JsonObject(Vec::new()))
}

fn object(fields: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(JsonObject(
        fields
            .into_iter()
            .map(|(name, value)| (key(name), value))
            .collect(),
    ))
}

fn string_array(values: &[JsonString]) -> JsonValue {
    JsonValue::Array(JsonArray(
        values.iter().cloned().map(JsonValue::String).collect(),
    ))
}

fn set_field(object: &mut JsonObject, name: &str, value: JsonValue) {
    if let Some((_, existing)) = object
        .0
        .iter_mut()
        .rev()
        .find(|(candidate, _)| candidate.equals_text(name))
    {
        *existing = value;
    } else {
        object.0.push((key(name), value));
    }
}

fn object_field<'a>(value: &'a JsonValue, name: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(object) = value else {
        return None;
    };
    object
        .0
        .iter()
        .rev()
        .find_map(|(candidate, value)| candidate.equals_text(name).then_some(value))
}

fn object_string<'a>(value: &'a JsonValue, name: &str) -> Option<&'a JsonString> {
    match object_field(value, name)? {
        JsonValue::String(value) => Some(value),
        _ => None,
    }
}

fn parse_payload(raw_payload: &[u8]) -> Option<JsonValue> {
    if raw_payload.len() > MAX_HOOK_PAYLOAD_BYTES {
        return None;
    }
    if raw_payload
        .iter()
        .all(|byte| matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c))
    {
        return Some(empty_object());
    }
    let text = String::from_utf8(raw_payload.to_vec()).ok()?;
    let value = parse_json_reject_duplicates(&text).ok()?;
    matches!(value, JsonValue::Object(_)).then_some(value)
}

fn normalize_post_tool_use_input(payload: &JsonValue) -> Result<JsonValue, ProjectionError> {
    let JsonValue::Object(fields) = payload else {
        return Err(ProjectionError::from(
            "raw PostToolUse fields are not exact".to_owned(),
        ));
    };
    if !object_has_exact_keys(
        fields,
        &["hookEventName", "tool_name", "tool_input", "tool_response"],
    ) || !object_string(payload, "hookEventName")
        .is_some_and(|value| value.equals_text("PostToolUse"))
    {
        return Err(ProjectionError::from(
            "raw PostToolUse fields are not exact".to_owned(),
        ));
    }
    let tool_name = object_string(payload, "tool_name").ok_or_else(|| {
        ProjectionError::from("raw PostToolUse tool fields have invalid types".to_owned())
    })?;
    let tool_input = object_field(payload, "tool_input")
        .filter(|value| matches!(value, JsonValue::Object(_)))
        .ok_or_else(|| {
            ProjectionError::from("raw PostToolUse tool fields have invalid types".to_owned())
        })?;
    let tool_response = object_field(payload, "tool_response")
        .filter(|value| matches!(value, JsonValue::Object(_)))
        .ok_or_else(|| {
            ProjectionError::from("raw PostToolUse response keys are not exact".to_owned())
        })?;
    let JsonValue::Object(response_fields) = tool_response else {
        unreachable!("response object was checked above");
    };
    if !object_has_exact_keys(response_fields, &["exit_code", "stderr", "stdout"]) {
        return Err(ProjectionError::from(
            "raw PostToolUse response keys are not exact".to_owned(),
        ));
    }
    let exit_code = object_field(tool_response, "exit_code")
        .filter(|value| matches!(value, JsonValue::Number(JsonNumber::Integer(_))))
        .ok_or_else(|| {
            ProjectionError::from("raw PostToolUse response fields have invalid types".to_owned())
        })?;
    let stderr = object_string(tool_response, "stderr").ok_or_else(|| {
        ProjectionError::from("raw PostToolUse response fields have invalid types".to_owned())
    })?;
    let stdout = object_string(tool_response, "stdout").ok_or_else(|| {
        ProjectionError::from("raw PostToolUse response fields have invalid types".to_owned())
    })?;

    let tool_input_bytes = canonical_json_ascii_bytes_reject_nonfinite(tool_input)
        .map_err(|_| ProjectionError::from("raw PostToolUse tool_input is not JSON".to_owned()))?;
    let tool_input_text = String::from_utf8(tool_input_bytes.clone())
        .map_err(|_| ProjectionError::from("raw PostToolUse tool_input is not UTF-8".to_owned()))?;
    let normalized_tool_input = parse_json(&tool_input_text)
        .map_err(|_| ProjectionError::from("raw PostToolUse tool_input is not JSON".to_owned()))?;
    let normalized_response = JsonValue::Object(JsonObject(vec![
        (key("exit_code"), clone_integer(exit_code)?),
        (key("stderr"), JsonValue::String(stderr.clone())),
        (key("stdout"), JsonValue::String(stdout.clone())),
    ]));
    let normalized = JsonValue::Object(JsonObject(vec![
        (key("hook_event_name"), text_value("PostToolUse")),
        (
            key("schema_version"),
            text_value(POST_TOOL_USE_INPUT_SCHEMA),
        ),
        (
            key("tool_input_fingerprint"),
            text_value(&sha256_hex(&tool_input_bytes)),
        ),
        (key("tool_name"), JsonValue::String(tool_name.clone())),
        (key("tool_input"), normalized_tool_input),
        (key("tool_response"), normalized_response),
    ]));
    validate_normalized_input(&normalized)?;
    Ok(normalized)
}

fn clone_integer(value: &JsonValue) -> Result<JsonValue, ProjectionError> {
    match value {
        JsonValue::Number(JsonNumber::Integer(value)) => {
            Ok(JsonValue::Number(JsonNumber::Integer(value.clone())))
        }
        _ => Err(ProjectionError::from(
            "raw PostToolUse response fields have invalid types".to_owned(),
        )),
    }
}

fn object_has_exact_keys(value: &JsonObject, expected: &[&str]) -> bool {
    value.0.len() == expected.len()
        && expected.iter().all(|key| {
            value
                .0
                .iter()
                .any(|(candidate, _)| candidate.equals_text(key))
        })
}

fn official_payload(event: &str, mut payload: JsonValue) -> Result<JsonValue, String> {
    let reason = ["reason", "systemMessage"]
        .into_iter()
        .find_map(|name| {
            object_string(&payload, name)
                .and_then(JsonString::to_text)
                .filter(|value| !value.is_empty())
        })
        .unwrap_or_default();
    let JsonValue::Object(fields) = &mut payload else {
        return Err("official Hook payload is not an object".to_owned());
    };
    let hook_specific = object(vec![
        ("hookEventName", text_value(event)),
        ("additionalContext", text_value(&reason)),
    ]);
    set_field(fields, "schema", text_value(OFFICIAL_HOOK_SCHEMA));
    set_field(fields, "hookSpecificOutput", hook_specific);
    Ok(payload)
}

fn projection_payload(stdout: &str) -> JsonValue {
    projection_context_payload(stdout)
}

fn serde_safety_payload(value: SerdeValue) -> Result<JsonValue, String> {
    let text = serde_json::to_string(&value)
        .map_err(|error| format!("safety payload serialization failed: {error}"))?;
    parse_json(&text)
}

fn hook_root(
    current_directory: Option<&Path>,
    environment: &BTreeMap<String, String>,
) -> Result<HookRootState, String> {
    let override_root = env_value(environment, DISPATCHER_SOURCE_ROOT_ENV);
    if !override_root.is_empty() {
        let path = resolve_override_path(&override_root, current_directory)?;
        return Ok(HookRootState {
            active_root: path,
            standalone: true,
            status: HookRootStatus::Override,
        });
    }
    let target_root = {
        let target = env_value(environment, "AGENT_CANON_TARGET_ROOT");
        if target.is_empty() {
            env_value(environment, "AGENT_CANON_TARGET_CONTAINER_ROOT")
        } else {
            target
        }
    };
    if !target_root.is_empty() {
        let path = resolve_override_path(&target_root, current_directory)?;
        return Ok(HookRootState {
            active_root: path,
            standalone: true,
            status: HookRootStatus::Override,
        });
    }

    if let Some(current_directory) = current_directory {
        if let Ok(resolution) = resolve_agent_canon_source_root(current_directory, environment) {
            return Ok(HookRootState {
                active_root: resolution.current_repository_root,
                standalone: resolution.layout == LAYOUT_STANDALONE,
                status: HookRootStatus::Resolved,
            });
        }
    }
    Ok(HookRootState {
        active_root: source_root_fallback(),
        standalone: false,
        status: HookRootStatus::Failed,
    })
}

fn source_root_fallback() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .unwrap_or(Path::new(env!("CARGO_MANIFEST_DIR")))
        .to_path_buf()
}

fn resolve_override_path(value: &str, current_directory: Option<&Path>) -> Result<PathBuf, String> {
    let path = PathBuf::from(value);
    let path = if path.is_absolute() {
        path
    } else if let Some(current_directory) = current_directory {
        current_directory.join(path)
    } else {
        path
    };
    resolve_non_strict(&path)
}

fn active_report_target(pointer: &Path, active_root: &Path, report_root: &Path) -> Option<PathBuf> {
    if !pointer.is_file() {
        return None;
    }
    let value = python_strip(&fs::read_to_string(pointer).ok()?).to_owned();
    if value.is_empty() {
        return None;
    }
    let declared = PathBuf::from(value);
    if declared
        .components()
        .any(|part| part == Component::ParentDir)
    {
        return None;
    }
    let target = if declared.is_absolute() {
        declared
    } else if declared.starts_with(Path::new(REPORT_ROOT_RELATIVE)) {
        active_root.join(declared)
    } else {
        report_root.join(declared)
    };
    let active_root = resolve_non_strict(active_root).ok()?;
    let report_root = resolve_non_strict(report_root).ok()?;
    if !path_is_within(&report_root, &active_root) || report_root == active_root {
        return None;
    }
    let target = resolve_non_strict(&target).ok()?;
    if !path_is_within(&target, &report_root) || target == report_root || !target.is_dir() {
        return None;
    }
    Some(target)
}

fn resolve_report_target(
    state: &HookRootState,
    environment: &BTreeMap<String, String>,
) -> Option<PathBuf> {
    if !state.report_projection_enabled() {
        return None;
    }
    let override_path = env_value(environment, WORKFLOW_MONITOR_REPORT_DIR_ENV);
    if !override_path.is_empty() {
        let path = PathBuf::from(override_path);
        let target = if path.is_absolute() {
            path
        } else {
            state.active_root.join(path)
        };
        let resolved = resolve_non_strict(&target).ok()?;
        return resolved
            .is_dir()
            .then(|| parent_bound_report(&resolved, "hook-report-projection", environment))
            .flatten();
    }
    let report_root = state.active_root.join(REPORT_ROOT_RELATIVE);
    let active_target = active_report_target(
        &state.active_root.join(ACTIVE_RUN_POINTER),
        &state.active_root,
        &report_root,
    );
    if let Some(target) = active_target {
        return parent_bound_report(&target, "hook-report-projection", environment);
    }
    if state.standalone {
        let target = active_report_target(
            &state.active_root.join(".active_run"),
            &state.active_root,
            &report_root,
        );
        return target.and_then(|target| {
            parent_bound_report(&target, "hook-report-projection", environment)
        });
    }
    None
}

fn parent_bound_report(
    path: &Path,
    purpose: &str,
    environment: &BTreeMap<String, String>,
) -> Option<PathBuf> {
    let parent = env_value(environment, PARENT_ROOT_ENV);
    if parent.is_empty() {
        return None;
    }
    let attestation = attest_parent_root(Path::new(&parent), purpose)?;
    let purpose = NonEmptyTrimmedString::new(purpose).ok()?;
    attestation
        .resolve_parent_owned_path(path, purpose)
        .ok()
        .map(|receipt| receipt.physical_path().to_path_buf())
}

fn attest_parent_root(parent_root: &Path, purpose: &str) -> Option<AttestedParent> {
    let request = AttestationRequest {
        cwd: parent_root.to_path_buf(),
        explicit_root: Some(parent_root.to_path_buf()),
        source_root: None,
        clone_root: None,
        topic_marker: None,
        gitmodules: None,
        owner_evidence: None,
        expected_remote: None,
        expected_module_digest: None,
        child_handoff_token: None,
        purpose: NonEmptyTrimmedString::new(purpose).ok()?,
        nonce: Nonce128::generate().ok()?,
    };
    ParentRootAttestor::new().attest(&request).ok()
}

fn path_is_within(path: &Path, root: &Path) -> bool {
    path == root || path.starts_with(root)
}

fn env_value(environment: &BTreeMap<String, String>, key: &str) -> String {
    environment
        .get(key)
        .map(|value| python_strip(value).to_owned())
        .unwrap_or_default()
}

fn dispatch_event(
    event: &str,
    raw_payload: &[u8],
    environment: &BTreeMap<String, String>,
    current_directory: Option<&Path>,
) -> Result<HookCliResult, String> {
    if event == "Stop" {
        return Ok(cli_success(Vec::new()));
    }

    let payload = parse_payload(raw_payload);
    let mut output = None;
    let mut status = if payload.is_some() {
        "pass".to_owned()
    } else {
        "malformed_payload".to_owned()
    };
    let mut telemetry = BTreeMap::new();
    let root_state = hook_root(current_directory, environment)?;

    if let Some(payload) = payload.as_ref() {
        if event == "UserPromptSubmit" {
            let prompt = payload_prompt_json(payload);
            if let Some(matched_kind) = secret_kind_json(&prompt) {
                output = Some(official_payload(
                    event,
                    serde_safety_payload(secret_block_payload(matched_kind))?,
                )?);
                status = "blocked_secret".to_owned();
                telemetry.insert("safety_decision".to_owned(), "block".to_owned());
            }
        } else if event == "PreToolUse" {
            let tool_name = payload_tool_name_json(payload);
            if SHELL_TOOL_NAMES
                .iter()
                .any(|shell_tool| tool_name.equals_text(shell_tool))
            {
                let command = payload_tool_command_json(payload);
                let command_text = command
                    .to_text()
                    .ok_or_else(|| "Hook shell command cannot be UTF-8 encoded".to_owned())?;
                if let Some(intent) = first_block(&command_text) {
                    let safety = branch_block_payload(&command_text, &intent);
                    let operation = safety
                        .get("operation")
                        .and_then(SerdeValue::as_str)
                        .unwrap_or_default()
                        .to_owned();
                    output = Some(official_payload(event, serde_safety_payload(safety)?)?);
                    status = "blocked_destructive_git".to_owned();
                    telemetry.insert("safety_decision".to_owned(), "block".to_owned());
                    telemetry.insert("operation".to_owned(), operation);
                }
            }
        } else if event == "PostToolUse" {
            match normalize_post_tool_use_input(payload) {
                Ok(normalized) => {
                    if object_string(&normalized, "tool_name")
                        .is_some_and(|name| name.equals_text("Bash"))
                    {
                        let response = object_field(&normalized, "tool_response")
                            .expect("normalized response exists");
                        let exit_code = object_field(response, "exit_code")
                            .expect("normalized exit code exists");
                        if integer_is_zero(exit_code) {
                            let stdout = object_string(response, "stdout")
                                .and_then(JsonString::to_text)
                                .ok_or_else(|| {
                                    "normalized projection stdout cannot be UTF-8 encoded"
                                        .to_owned()
                                });
                            match stdout {
                                Ok(stdout) => {
                                    if validate_projection_bytes(&stdout).is_ok() {
                                        output = Some(projection_payload(&stdout));
                                        status = "projection_forwarded".to_owned();
                                    } else {
                                        status = "invalid_projection".to_owned();
                                    }
                                }
                                Err(_) => status = "invalid_projection".to_owned(),
                            }
                        } else {
                            status = "unsuccessful_tool_response".to_owned();
                        }
                    }
                }
                Err(_) => status = "invalid_projection".to_owned(),
            }
        }
    }

    let report_dir = resolve_report_target(&root_state, environment);
    let (mut spool_entry, log_context, timestamp, payload_fingerprint) = spool_event(
        event,
        raw_payload,
        &status,
        &root_state.active_root,
        &telemetry,
        environment,
    )?;

    let null_payload = JsonValue::Null;
    let mutation_decision = if event == "PreToolUse" {
        let hook_spool_root = log_context
            .spool_root()
            .map_err(|error| format!("hook spool path unavailable: {error}"))?;
        Some(evaluate_mutation_authority(
            payload.as_ref().unwrap_or(&null_payload),
            &MutationAuthorityContext {
                report_dir: report_dir.as_deref(),
                active_root: &root_state.active_root,
                environment,
                hook_spool_root: Some(&hook_spool_root),
            },
        ))
    } else {
        None
    };
    if let Some(decision) = mutation_decision.as_ref() {
        if decision.status == "blocked" {
            let target_blocked = decision.reason.starts_with("writer_target");
            if output.is_none() || target_blocked {
                output = Some(official_payload(event, mutation_block_payload(decision))?);
                status = if target_blocked {
                    "blocked_writer_target".to_owned()
                } else {
                    "blocked_parent_mutation".to_owned()
                };
            }
        }
        set_field(&mut spool_entry, "mutation_control", decision.as_dict());
        set_field(&mut spool_entry, "status", text_value(&status));
    }

    let empty_payload = empty_object();
    let payload_data = payload.as_ref().unwrap_or(&empty_payload);
    let workflow_context = report_dir
        .as_ref()
        .map(|report_dir| load_workflow_context(&report_dir.join("skill_usage_context.json")))
        .unwrap_or_default();
    let classifier_prompt = object_string(payload_data, "prompt")
        .cloned()
        .unwrap_or_default();
    let empty_classifier_mapping = empty_object();
    let no_lane_evidence = Vec::new();
    let no_validation_evidence = Vec::new();
    let selection_result = select_tools(payload_data)
        .map_err(|error| error.message)
        .and_then(|tools| {
            select_subagents(payload_data, None)
                .map(|subagents| (tools, subagents))
                .map_err(str::to_owned)
        });
    let (tool_selection, subagent_selection, classifier_rules) = match selection_result {
        Ok((tools, subagents)) => {
            let rules = PromptClassifierInputs {
                prompt: &classifier_prompt,
                repo_root: &root_state.active_root,
                catalog: &empty_classifier_mapping,
                routing_rules: &empty_classifier_mapping,
                structural_lane_evidence: &no_lane_evidence,
                validation_repair_evidence: &no_validation_evidence,
            };
            (Some(tools), Some(subagents), Some(rules))
        }
        Err(_) => (None, None, None),
    };
    let handler_result = FinalHandlerResult {
        status: JsonString::from_text(&status),
        output_kind: JsonString::from_text(if output.is_some() {
            "block"
        } else if status == "projection_forwarded" {
            "additional_context"
        } else {
            ""
        }),
        safe_fields: if status.starts_with("blocked_") {
            object(vec![("safety_decision", text_value("block"))])
        } else {
            empty_object()
        },
    };
    let parts = HookInvocationParts {
        hook_event_name: JsonString::from_text(event),
        hook_invocation_id: JsonString::from_text(
            &object_string(&spool_entry, "hook_run_id")
                .and_then(JsonString::to_text)
                .unwrap_or_default(),
        ),
        hook_payload: payload.as_ref(),
        payload_status: JsonString::from_text(if payload.is_some() {
            "parsed"
        } else {
            "malformed_payload"
        }),
        handler_result,
        classifier_rules: classifier_rules.as_ref(),
        tool_selection: tool_selection.as_ref(),
        subagent_selection: subagent_selection.as_ref(),
        workflow_context: &workflow_context,
        payload_fingerprint: JsonString::from_text(&payload_fingerprint),
        timestamp: JsonString::from_text(&timestamp),
        root: root_state.active_root.clone(),
        hook_log_namespace: JsonString::default(),
        report_dir: report_dir.clone(),
    };

    let event_value = JsonValue::String(JsonString::from_text(event));
    if let Some(receipt) = build_coordination_receipt(
        payload.as_ref().unwrap_or(&null_payload),
        subagent_selection.as_ref(),
        &event_value,
    ) {
        set_field(&mut spool_entry, "coordination_receipt", receipt);
    }
    if subagent_selection
        .as_ref()
        .is_some_and(|selection| selection.action.equals_text("spawn"))
    {
        if let Some(scope_digest) = payload
            .as_ref()
            .and_then(|payload| object_field(payload, "tool_input"))
            .and_then(|tool_input| object_string(tool_input, "scope_digest"))
        {
            set_field(
                &mut spool_entry,
                "mutation_scope_digest",
                JsonValue::String(scope_digest.clone()),
            );
        }
    }

    let behavior = record_hook_invocation(&parts);
    let behavior_bytes = behavior
        .as_ref()
        .map(|event| event.canonical_bytes())
        .transpose()
        .map_err(|error| format!("behavior event serialization failed: {error:?}"))?;
    if let Some(bytes) = behavior_bytes.as_ref() {
        let event = parse_canonical_event(bytes)?;
        merge_object_fields(&mut spool_entry, event)?;
    }

    let parent_root = env_value(environment, PARENT_ROOT_ENV);
    let event_parent = if parent_root.is_empty() {
        None
    } else {
        attest_parent_root(Path::new(&parent_root), "hook-event-spool")
    };
    let append_result = log_context.append(JsonValue::Object(spool_entry), event_parent.as_ref());
    if behavior.is_some() && append_result.status == "spooled" && report_dir.is_some() {
        let runtime_root = env_value(environment, crate::runtime_boundary::RUNTIME_ROOT_ENV);
        let runtime_root = (!runtime_root.is_empty()).then(|| PathBuf::from(runtime_root));
        if let (Some(behavior), Some(report_dir)) = (behavior.as_ref(), report_dir.as_ref()) {
            let _ = emit_behavior_projection(
                report_dir,
                &root_state.active_root,
                runtime_root.as_deref(),
                behavior.as_json_value(),
            );
        }
    }

    match output {
        Some(output) => Ok(json_stdout(&output)),
        None => Ok(cli_success(Vec::new())),
    }
}

fn spool_event(
    event: &str,
    raw_payload: &[u8],
    status: &str,
    root: &Path,
    telemetry: &BTreeMap<String, String>,
    environment: &BTreeMap<String, String>,
) -> Result<(JsonObject, HookLogContext, String, String), String> {
    let timestamp = utc_now();
    let payload_fingerprint = sha256_hex(raw_payload);
    let context = HookLogContext {
        active_root: root.to_path_buf(),
        hook_name: event.to_owned(),
        override_path: String::new(),
        environment: environment.clone(),
    };
    let hook_run_id = context.run_id(&timestamp, &payload_fingerprint)?;
    let entry = object(vec![
        ("hook_run_id", text_value(&hook_run_id)),
        ("timestamp", text_value(&timestamp)),
        ("payload_fingerprint", text_value(&payload_fingerprint)),
        ("status", text_value(status)),
        ("hook_event_name", text_value(event)),
    ]);
    let JsonValue::Object(mut fields) = entry else {
        unreachable!("hook spool base entry is an object");
    };
    for (key, value) in telemetry {
        if !value.is_empty() {
            set_field(&mut fields, key, text_value(value));
        }
    }
    Ok((fields, context, timestamp, payload_fingerprint))
}

fn integer_is_zero(value: &JsonValue) -> bool {
    matches!(value, JsonValue::Number(JsonNumber::Integer(value)) if value == "0")
}

fn merge_object_fields(destination: &mut JsonObject, source: JsonValue) -> Result<(), String> {
    let JsonValue::Object(mut source) = source else {
        return Err("behavior event is not an object".to_owned());
    };
    for (name, value) in std::mem::take(&mut source.0) {
        if let Some((_, previous)) = destination
            .0
            .iter_mut()
            .rev()
            .find(|(candidate, _)| candidate == &name)
        {
            *previous = value;
        } else {
            destination.0.push((name, value));
        }
    }
    Ok(())
}

fn parse_canonical_event(bytes: &[u8]) -> Result<JsonValue, String> {
    let text = std::str::from_utf8(bytes).map_err(|error| error.to_string())?;
    parse_json(text)
}
