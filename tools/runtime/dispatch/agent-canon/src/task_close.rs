//! Native TaskClose terminal consumer.
// @dependency-start
// contract implementation
// responsibility Owns the read-only TaskClose terminal predicates and CLI output.
// upstream implementation agent_tool_calls.rs owns G6 close-agent materialization
// upstream implementation owner_guarantee.rs owns owner receipt normalization and compatibility
// upstream implementation report_artifact_checks.rs owns shared report checks and placement
// upstream implementation run_evaluation.rs owns selected run artifact parsing helpers
// upstream implementation runtime_boundary.rs owns external runtime artifact reads
// upstream implementation authority/mod.rs owns authenticated parent-root validation
// upstream data ../../../../../tests/fixtures/task_close/python_golden.json freezes the old TaskClose API and CLI results
// downstream implementation main.rs routes the native task-close CLI
// downstream implementation ../../../../../tools/catalog.yaml registers the native TaskClose command
// downstream test ../tests/task_close_native.rs checks frozen TaskClose API and CLI behavior
// @dependency-end

use crate::agent_tool_calls::{
    materialize_close_agent_tool_call as materialize_g6, CloseAgentLifecycleEvidence,
    CloseAgentLifecycleOwnerInput,
};
use crate::authority::{AttestationRequest, NonEmptyTrimmedString, Nonce128, ParentRootAttestor};
use crate::owner_guarantee::{
    normalize_owner_guarantee_packet, owner_receipt_closeout_state, owner_receipt_is_compatible,
    owner_receipt_key, OwnerReceiptCloseoutInput, OwnerReceiptCompatibility,
};
use crate::python_json::{
    canonical_json_ascii_bytes, parse_json, JsonArray, JsonNumber, JsonObject, JsonString,
    JsonValue,
};
use crate::report_artifact_checks::{
    check_final_review_artifact, check_work_log_artifact, parse_markdown_status_lines,
    parse_markdown_status_section, report_artifact_placement_blockers, token_fields,
};
use crate::runtime_boundary::{RuntimeArtifactBoundary, RUNTIME_ROOT_ENV};
use crate::update_lifecycle_contract::{
    binding_identity, validate_cleanup_proof, validate_durable_handback, validate_gate_chain,
    LifecycleContractError,
};
use serde_json::{Map as SerdeMap, Value as SerdeValue};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

const OWNER_GUARANTEE_RECEIPTS_ARTIFACT_NAME: &str = "owner_guarantee_receipts.json";
const UPDATE_LIFECYCLE_CLOSEOUT_ARTIFACT_NAME: &str = "update_lifecycle_closeout.json";
const UPDATE_LIFECYCLE_CLOSEOUT_SCHEMA: &str = "agent-canon.update-lifecycle-closeout.v1";
const VERIFIER_RECEIPT_SCHEMA: &str = "agent-canon.verifier-receipt.v1";
const PARENT_MUTATION_EVIDENCE_SCHEMA: &str = "agent-canon.parent-mutation-evidence.v1";
const GATE_IDS: &[&str] = &["G1", "G2", "G3", "G4", "G5", "G6"];
const STATIC_ANALYSIS_COMPLETE_STATUSES: &[&str] = &["yes", "profile_selected"];
const COMMIT_PUSH_COMPLETE_STATUSES: &[&str] = &["yes", "not_applicable"];
const DOCUMENT_STRUCTURE_MISSING_VALUES: &[&str] = &["", "missing", "none", "not_applicable"];
const DOCUMENT_STRUCTURE_VALUE_MISSING: &[&str] = &["", "missing", "none", "not_applicable"];
const DOCUMENT_SPLIT_DECISION_PREFIXES: &[&str] =
    &["keep:", "split:", "merge:", "inline:", "rename:"];
const DOCUMENT_SPLIT_DECISION_FORMAT_ONLY_PREFIX: &str = "not_applicable:format-only:";

#[derive(Clone, Debug)]
pub struct TaskCloseRequest {
    pub workspace_root: PathBuf,
    pub report_dir: PathBuf,
    pub parent_root: PathBuf,
    pub source_root: PathBuf,
    pub runtime_root: Option<PathBuf>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TaskClosePredicate {
    pub name: &'static str,
    pub passed: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TaskCloseResult {
    pub report_dir: PathBuf,
    pub ready: bool,
    pub predicates: Vec<TaskClosePredicate>,
    pub stdout: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TaskCloseError {
    pub message: String,
}

impl TaskCloseError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl fmt::Display for TaskCloseError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for TaskCloseError {}

impl From<String> for TaskCloseError {
    fn from(message: String) -> Self {
        Self::new(message)
    }
}

impl From<LifecycleContractError> for TaskCloseError {
    fn from(error: LifecycleContractError) -> Self {
        Self::new(error.to_string())
    }
}

pub type TaskCloseStatus = BTreeMap<String, String>;
type Status = TaskCloseStatus;

fn text<'a>(status: &'a Status, key: &str) -> &'a str {
    status.get(key).map(String::as_str).unwrap_or("")
}

fn python_bool(value: bool) -> &'static str {
    if value {
        "True"
    } else {
        "False"
    }
}

fn status_is(status: &Status, key: &str, expected: &str) -> bool {
    text(status, key) == expected
}

fn status_is_one_of(status: &Status, key: &str, expected: &[&str]) -> bool {
    expected.contains(&text(status, key))
}

fn status_fallback<'a>(first: &'a Status, second: &'a Status, key: &str) -> &'a str {
    first
        .get(key)
        .map(String::as_str)
        .unwrap_or_else(|| text(second, key))
}

fn read_text(
    boundary: &RuntimeArtifactBoundary,
    path: &Path,
) -> Result<Option<String>, TaskCloseError> {
    boundary
        .read_bytes(path)
        .map_err(TaskCloseError::from)?
        .map(|bytes| {
            String::from_utf8(bytes).map_err(|error| {
                TaskCloseError::new(format!("runtime artifact is not UTF-8: {error}"))
            })
        })
        .transpose()
}

fn is_regular_file(
    boundary: &RuntimeArtifactBoundary,
    path: &Path,
) -> Result<bool, TaskCloseError> {
    let resolved = boundary.resolve(path).map_err(TaskCloseError::from)?;
    match fs::symlink_metadata(&resolved) {
        Ok(metadata) => Ok(metadata.file_type().is_file()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(TaskCloseError::new(format!(
            "cannot inspect runtime artifact {}: {error}",
            resolved.display()
        ))),
    }
}

fn read_required_text(
    boundary: &RuntimeArtifactBoundary,
    path: &Path,
    name: &str,
) -> Result<String, TaskCloseError> {
    read_text(boundary, path)?
        .ok_or_else(|| TaskCloseError::new(format!("{name} not found: {}", path.display())))
}

fn parse_key_values(input: &str) -> Status {
    let mut result = Status::new();
    for line in input.lines() {
        let line = crate::python_text::python_strip(line);
        if line.is_empty() {
            continue;
        }
        if let Some((key, value)) = line.split_once('=') {
            result.insert(
                crate::python_text::python_strip(key).to_owned(),
                crate::python_text::python_strip(value).to_owned(),
            );
        }
    }
    result
}

fn status_section_text(input: &str, heading: &str) -> String {
    let target = format!("## {heading}");
    let mut selected = Vec::new();
    let mut in_section = false;
    for line in input.lines() {
        let stripped = crate::python_text::python_strip(line);
        if stripped == target {
            in_section = true;
            selected.push(line);
            continue;
        }
        if in_section && stripped.starts_with("## ") {
            break;
        }
        if in_section {
            selected.push(line);
        }
    }
    selected.join("\n")
}

fn parse_status_section(input: &str, heading: &str) -> Result<Status, TaskCloseError> {
    parse_markdown_status_section(input, heading)
        .map_err(|error| TaskCloseError::new(error.to_string()))
}

fn artifact_path(report_dir: &Path, value: &str) -> Result<Option<PathBuf>, TaskCloseError> {
    if value.is_empty() {
        return Ok(None);
    }
    let raw = PathBuf::from(value);
    let candidate = if raw.is_absolute() {
        raw
    } else {
        report_dir.join(raw)
    };
    let resolved =
        crate::path_resolution::resolve_non_strict(&candidate).map_err(TaskCloseError::from)?;
    if resolved.starts_with(report_dir) {
        Ok(Some(resolved))
    } else {
        Ok(None)
    }
}

fn join_blockers(blockers: &[String]) -> String {
    blockers.join(",")
}

fn is_not_missing(value: &str) -> bool {
    !["", "missing", "none"].contains(&value)
}

fn string_value(value: &SerdeValue) -> Option<&str> {
    value.as_str()
}

fn python_json_equal(left: &SerdeValue, right: &SerdeValue) -> bool {
    crate::python_json::python_json_equal_after_float_rejection(left, right)
}

fn object_value<'a>(object: &'a SerdeMap<String, SerdeValue>, key: &str) -> Option<&'a SerdeValue> {
    object.get(key)
}

fn object_list(value: Option<&SerdeValue>) -> Option<&Vec<SerdeValue>> {
    value.and_then(SerdeValue::as_array)
}

fn json_string<'a>(value: &'a JsonValue) -> Option<&'a JsonString> {
    match value {
        JsonValue::String(value) => Some(value),
        _ => None,
    }
}

fn json_array(value: &JsonValue) -> Option<&[JsonValue]> {
    match value {
        JsonValue::Array(values) => Some(&values.0),
        _ => None,
    }
}

fn json_object(value: &JsonValue) -> Option<&JsonObject> {
    match value {
        JsonValue::Object(values) => Some(values),
        _ => None,
    }
}

fn json_field<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonValue> {
    json_object(value)?
        .0
        .iter()
        .rev()
        .find_map(|(name, value)| name.equals_text(key).then_some(value))
}

fn json_string_text(value: &JsonString) -> String {
    let mut output = String::new();
    for codepoint in &value.0 {
        if let Some(character) = char::from_u32(*codepoint) {
            output.push(character);
        } else {
            output.push_str(&format!("\\u{codepoint:04x}"));
        }
    }
    output
}

fn json_python_string(value: &JsonValue) -> JsonString {
    match value {
        JsonValue::String(value) => value.clone(),
        JsonValue::Null => JsonString::from_text("None"),
        JsonValue::Bool(value) => JsonString::from_text(if *value { "True" } else { "False" }),
        JsonValue::Number(JsonNumber::Integer(value)) => JsonString::from_text(value),
        JsonValue::Number(JsonNumber::Float(value)) => {
            JsonString::from_text(&crate::python_json::python_float(*value))
        }
        JsonValue::Array(_) | JsonValue::Object(_) => {
            JsonString::from_text(&json_python_repr(value))
        }
    }
}

fn json_python_repr(value: &JsonValue) -> String {
    enum Action<'a> {
        Value(&'a JsonValue),
        String(&'a JsonString),
        Text(&'static str),
    }
    let mut actions = vec![Action::Value(value)];
    let mut output = String::new();
    while let Some(action) = actions.pop() {
        match action {
            Action::Text(text) => output.push_str(text),
            Action::String(value) => output.push_str(&json_string_python_repr(value)),
            Action::Value(JsonValue::Null) => output.push_str("None"),
            Action::Value(JsonValue::Bool(value)) => {
                output.push_str(if *value { "True" } else { "False" });
            }
            Action::Value(JsonValue::Number(JsonNumber::Integer(value))) => {
                output.push_str(value);
            }
            Action::Value(JsonValue::Number(JsonNumber::Float(value))) => {
                output.push_str(&crate::python_json::python_float(*value));
            }
            Action::Value(JsonValue::String(value)) => actions.push(Action::String(value)),
            Action::Value(JsonValue::Array(values)) => {
                actions.push(Action::Text("]"));
                for index in (0..values.0.len()).rev() {
                    actions.push(Action::Value(&values.0[index]));
                    if index > 0 {
                        actions.push(Action::Text(", "));
                    }
                }
                actions.push(Action::Text("["));
            }
            Action::Value(JsonValue::Object(values)) => {
                actions.push(Action::Text("}"));
                for index in (0..values.0.len()).rev() {
                    let (key, value) = &values.0[index];
                    actions.push(Action::Value(value));
                    actions.push(Action::Text(": "));
                    actions.push(Action::String(key));
                    if index > 0 {
                        actions.push(Action::Text(", "));
                    }
                }
                actions.push(Action::Text("{"));
            }
        }
    }
    output
}

fn json_string_python_repr(value: &JsonString) -> String {
    let text = json_string_text(value);
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut rendered = String::with_capacity(text.len() + 2);
    rendered.push(quote);
    for character in text.chars() {
        if character == quote || character == '\\' {
            rendered.push('\\');
            rendered.push(character);
        } else if character == '\n' {
            rendered.push_str("\\n");
        } else if character == '\r' {
            rendered.push_str("\\r");
        } else if character == '\t' {
            rendered.push_str("\\t");
        } else if character.is_control() {
            rendered.push_str(&format!("\\x{:02x}", character as u32));
        } else {
            rendered.push(character);
        }
    }
    rendered.push(quote);
    rendered
}

fn clone_json(value: &JsonValue) -> JsonValue {
    enum Action<'a> {
        Visit(&'a JsonValue),
        BuildArray(usize),
        BuildObject(Vec<JsonString>),
    }
    let mut actions = vec![Action::Visit(value)];
    let mut values: Vec<JsonValue> = Vec::new();
    while let Some(action) = actions.pop() {
        match action {
            Action::Visit(JsonValue::Null) => values.push(JsonValue::Null),
            Action::Visit(JsonValue::Bool(value)) => values.push(JsonValue::Bool(*value)),
            Action::Visit(JsonValue::Number(JsonNumber::Integer(value))) => {
                values.push(JsonValue::Number(JsonNumber::Integer(value.clone())))
            }
            Action::Visit(JsonValue::Number(JsonNumber::Float(value))) => {
                values.push(JsonValue::Number(JsonNumber::Float(*value)))
            }
            Action::Visit(JsonValue::String(value)) => {
                values.push(JsonValue::String(value.clone()))
            }
            Action::Visit(JsonValue::Array(array)) => {
                actions.push(Action::BuildArray(array.0.len()));
                for child in array.0.iter().rev() {
                    actions.push(Action::Visit(child));
                }
            }
            Action::Visit(JsonValue::Object(object)) => {
                let keys = object.0.iter().map(|(key, _)| key.clone()).collect();
                actions.push(Action::BuildObject(keys));
                for (_, child) in object.0.iter().rev() {
                    actions.push(Action::Visit(child));
                }
            }
            Action::BuildArray(count) => {
                let start = values.len().saturating_sub(count);
                let children = values.drain(start..).collect();
                values.push(JsonValue::Array(JsonArray(children)));
            }
            Action::BuildObject(keys) => {
                let start = values.len().saturating_sub(keys.len());
                let children = values.drain(start..).collect::<Vec<_>>();
                let entries = keys.into_iter().zip(children).collect();
                values.push(JsonValue::Object(JsonObject(entries)));
            }
        }
    }
    values.pop().expect("one JSON value is cloned")
}

fn validate_parent_workspace(request: &TaskCloseRequest) -> Result<PathBuf, TaskCloseError> {
    let parent_root = fs::canonicalize(&request.parent_root).map_err(|error| {
        TaskCloseError::new(format!("task-close parent root is unavailable: {error}"))
    })?;
    let workspace = fs::canonicalize(&request.workspace_root).map_err(|error| {
        TaskCloseError::new(format!("task-close workspace is unavailable: {error}"))
    })?;
    let purpose = NonEmptyTrimmedString::new("task-close-workspace")
        .expect("fixed TaskClose authority purpose is non-empty");
    let attestation = ParentRootAttestor::new()
        .attest(&AttestationRequest {
            cwd: parent_root.clone(),
            explicit_root: Some(parent_root.clone()),
            source_root: None,
            clone_root: None,
            topic_marker: None,
            gitmodules: None,
            owner_evidence: None,
            expected_remote: None,
            expected_module_digest: None,
            child_handoff_token: None,
            purpose: purpose.clone(),
            nonce: Nonce128::generate().map_err(|error| TaskCloseError::new(error.to_string()))?,
        })
        .map_err(|error| TaskCloseError::new(error.to_string()))?;
    if workspace != parent_root {
        attestation
            .resolve_parent_owned_path(&workspace, purpose)
            .map_err(|error| TaskCloseError::new(error.to_string()))?;
    }
    Ok(workspace)
}

fn runtime_boundary(request: &TaskCloseRequest) -> Result<RuntimeArtifactBoundary, TaskCloseError> {
    RuntimeArtifactBoundary::for_source(
        &request.source_root,
        request.runtime_root.as_deref(),
        false,
    )
    .map_err(TaskCloseError::from)
}

fn validated_runtime_receipt(
    boundary: &RuntimeArtifactBoundary,
    report_dir: &Path,
    reference: &str,
    schema: &str,
) -> Option<JsonValue> {
    let reference_path = Path::new(reference);
    if reference_path.is_absolute()
        || reference_path
            .components()
            .any(|component| matches!(component, std::path::Component::ParentDir))
    {
        return None;
    }
    let target = report_dir.join(reference_path);
    let bytes = boundary.read_bytes(&target).ok().flatten()?;
    let raw = parse_json(std::str::from_utf8(&bytes).ok()?).ok()?;
    if !json_object(&raw).is_some_and(|_| {
        json_field(&raw, "schema")
            .and_then(json_string)
            .is_some_and(|value| value.equals_text(schema))
    }) {
        return None;
    }
    let Some(receipt_sha) = json_field(&raw, "receipt_sha256").and_then(json_string) else {
        return None;
    };
    if receipt_sha.contains_surrogate() {
        return None;
    }
    let receipt_sha = json_string_text(receipt_sha);
    let object = json_object(&raw)?;
    let unsigned = JsonValue::Object(JsonObject(
        object
            .0
            .iter()
            .filter(|(key, _)| !key.equals_text("receipt_sha256"))
            .map(|(key, value)| (key.clone(), clone_json(value)))
            .collect(),
    ));
    let canonical = canonical_json_ascii_bytes(&unsigned).ok()?;
    let digest = Sha256::digest(canonical)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    (digest == receipt_sha).then_some(raw)
}

fn object_list_from_custom<'a>(value: Option<&'a JsonValue>) -> Option<&'a [JsonValue]> {
    value.and_then(json_array)
}

pub fn child_closeout_evidence(
    boundary: &RuntimeArtifactBoundary,
    report_dir: &Path,
    closeout: &TaskCloseStatus,
) -> (bool, Vec<String>) {
    let required = [
        "verifier_role_id",
        "verifier_runtime_agent_id",
        "verifier_receipt_ref",
        "parent_mutation_status",
        "parent_mutation_evidence_ref",
    ];
    let missing = required
        .iter()
        .filter(|field| crate::python_text::python_strip(text(closeout, field)).is_empty())
        .map(|field| format!("runtime_child_closeout_missing:{field}"))
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        return (false, missing);
    }

    let verifier = validated_runtime_receipt(
        boundary,
        report_dir,
        text(closeout, "verifier_receipt_ref"),
        VERIFIER_RECEIPT_SCHEMA,
    );
    let parent_evidence = validated_runtime_receipt(
        boundary,
        report_dir,
        text(closeout, "parent_mutation_evidence_ref"),
        PARENT_MUTATION_EVIDENCE_SCHEMA,
    );
    let mut blockers = Vec::new();
    if let Some(verifier) = verifier {
        let source_events = object_list_from_custom(json_field(&verifier, "source_event_ids"));
        if !json_field(&verifier, "role_id")
            .and_then(json_string)
            .is_some_and(|value| value.equals_text("verifier"))
            || !json_field(&verifier, "runtime_agent_id")
                .and_then(json_string)
                .is_some_and(|value| value.equals_text(text(closeout, "verifier_runtime_agent_id")))
            || !json_field(&verifier, "status")
                .and_then(json_string)
                .is_some_and(|value| value.equals_text("pass"))
            || !source_events.is_some_and(|values| !values.is_empty())
        {
            blockers.push("runtime_verifier_provenance_mismatch".to_owned());
        }
    } else {
        blockers.push("runtime_verifier_receipt_invalid".to_owned());
    }

    if let Some(parent_evidence) = parent_evidence {
        let mutation_events =
            object_list_from_custom(json_field(&parent_evidence, "mutation_event_ids"));
        let source_events =
            object_list_from_custom(json_field(&parent_evidence, "source_event_ids"));
        let ledger_ref = json_field(&parent_evidence, "event_ledger_ref").and_then(json_string);
        let mut ledger_ids = BTreeSet::<JsonString>::new();
        let mut ledger_mutations = Vec::<JsonValue>::new();
        if let Some(ledger_ref) = ledger_ref {
            let reference = json_string_text(ledger_ref);
            let path = Path::new(&reference);
            if !path.is_absolute()
                && !path
                    .components()
                    .any(|component| matches!(component, std::path::Component::ParentDir))
            {
                if let Ok(Some(bytes)) = boundary.read_bytes(&report_dir.join(path)) {
                    if let Ok(source) = std::str::from_utf8(&bytes) {
                        for line in source.lines() {
                            let Ok(event) = parse_json(line) else {
                                break;
                            };
                            if json_object(&event).is_none() {
                                continue;
                            }
                            if let Some(event_id) =
                                json_field(&event, "hook_run_id").and_then(json_string)
                            {
                                ledger_ids.insert(event_id.clone());
                                if let Some(control) = json_field(&event, "mutation_control") {
                                    if json_object(control).is_some() {
                                        ledger_mutations.push(clone_json(control));
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        let source_event_ids = source_events.unwrap_or_default();
        let source_event_ids_are_strings = source_event_ids
            .iter()
            .all(|event_id| json_string(event_id).is_some());
        let source_event_ids_are_subset = source_event_ids.iter().all(|event_id| {
            json_string(event_id).is_some_and(|event_id| ledger_ids.contains(event_id))
        });
        let mutation_is_allowed = ledger_mutations.iter().any(|control| {
            json_field(control, "status")
                .and_then(json_string)
                .is_some_and(|status| status.equals_text("allowed"))
        });
        if text(closeout, "parent_mutation_status") != "no_parent_mutation"
            || !json_field(&parent_evidence, "status")
                .and_then(json_string)
                .is_some_and(|value| value.equals_text("no_parent_mutation"))
            || !mutation_events.is_some_and(|values| values.is_empty())
            || !source_events.is_some_and(|values| !values.is_empty())
            || ledger_ref.is_none()
            || !source_event_ids_are_strings
            || !source_event_ids_are_subset
            || mutation_is_allowed
        {
            blockers.push("parent_mutation_provenance_mismatch".to_owned());
        }
    } else {
        blockers.push("parent_mutation_evidence_invalid".to_owned());
    }
    (blockers.is_empty(), blockers)
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OwnerReceiptCloseoutDecision {
    pub ready: bool,
    pub applicable: bool,
    pub reason: String,
    pub owner_receipt_refs: Vec<String>,
    pub dependency_edges: Vec<String>,
}

impl OwnerReceiptCloseoutDecision {
    pub fn to_json_value(&self) -> SerdeValue {
        let mut result = serde_json::Map::new();
        result.insert("ready".to_owned(), SerdeValue::Bool(self.ready));
        result.insert("applicable".to_owned(), SerdeValue::Bool(self.applicable));
        result.insert("reason".to_owned(), SerdeValue::String(self.reason.clone()));
        if self.applicable
            && self.reason != "receipts_not_list"
            && !self.reason.starts_with("unreadable:")
        {
            result.insert(
                "owner_receipt_refs".to_owned(),
                SerdeValue::Array(
                    self.owner_receipt_refs
                        .iter()
                        .cloned()
                        .map(SerdeValue::String)
                        .collect(),
                ),
            );
            result.insert(
                "dependency_edges".to_owned(),
                SerdeValue::Array(
                    self.dependency_edges
                        .iter()
                        .cloned()
                        .map(SerdeValue::String)
                        .collect(),
                ),
            );
        }
        SerdeValue::Object(result)
    }
}

pub fn owner_receipt_closeout_consumer(
    boundary: &RuntimeArtifactBoundary,
    report_dir: &Path,
) -> OwnerReceiptCloseoutDecision {
    let path = report_dir.join(OWNER_GUARANTEE_RECEIPTS_ARTIFACT_NAME);
    match is_regular_file(boundary, &path) {
        Ok(true) => {}
        Ok(false) => {
            return OwnerReceiptCloseoutDecision {
                ready: true,
                applicable: false,
                reason: "not_applicable".to_owned(),
                owner_receipt_refs: Vec::new(),
                dependency_edges: Vec::new(),
            };
        }
        Err(error) => {
            return OwnerReceiptCloseoutDecision {
                ready: false,
                applicable: true,
                reason: format!("unreadable:{error}"),
                owner_receipt_refs: Vec::new(),
                dependency_edges: Vec::new(),
            };
        }
    }
    let bytes = match boundary.read_bytes(&path) {
        Ok(Some(bytes)) => bytes,
        Ok(None) => {
            return OwnerReceiptCloseoutDecision {
                ready: true,
                applicable: false,
                reason: "not_applicable".to_owned(),
                owner_receipt_refs: Vec::new(),
                dependency_edges: Vec::new(),
            };
        }
        Err(error) => {
            return OwnerReceiptCloseoutDecision {
                ready: false,
                applicable: true,
                reason: format!("unreadable:{error}"),
                owner_receipt_refs: Vec::new(),
                dependency_edges: Vec::new(),
            };
        }
    };
    let source = match std::str::from_utf8(&bytes) {
        Ok(source) => source,
        Err(error) => {
            return OwnerReceiptCloseoutDecision {
                ready: false,
                applicable: true,
                reason: format!("unreadable:{error}"),
                owner_receipt_refs: Vec::new(),
                dependency_edges: Vec::new(),
            };
        }
    };
    let raw = match parse_json(source) {
        Ok(raw) => raw,
        Err(error) => {
            return OwnerReceiptCloseoutDecision {
                ready: false,
                applicable: true,
                reason: format!("unreadable:{error}"),
                owner_receipt_refs: Vec::new(),
                dependency_edges: Vec::new(),
            };
        }
    };
    let is_artifact = json_object(&raw).is_some();
    let receipts = if is_artifact {
        json_field(&raw, "owner_receipts")
    } else {
        Some(&raw)
    };
    let candidate_digest = if is_artifact {
        json_field(&raw, "candidate_digest").and_then(json_string)
    } else {
        None
    };
    let artifact_required = if is_artifact {
        json_field(&raw, "required_owner_refs")
    } else {
        None
    };
    let artifact_edges = if is_artifact {
        json_field(&raw, "dependency_edges")
    } else {
        None
    };
    let receipt_values = match receipts.and_then(json_array) {
        Some(values) => values,
        None => {
            return OwnerReceiptCloseoutDecision {
                ready: false,
                applicable: true,
                reason: "receipts_not_list".to_owned(),
                owner_receipt_refs: Vec::new(),
                dependency_edges: Vec::new(),
            };
        }
    };
    let required_owner_refs = artifact_required
        .and_then(json_array)
        .filter(|values| !values.is_empty())
        .unwrap_or(&[])
        .iter()
        .map(json_python_string)
        .collect::<Vec<_>>();
    let dependency_edges = artifact_edges
        .and_then(json_array)
        .unwrap_or(&[])
        .iter()
        .map(json_python_string)
        .collect::<Vec<_>>();
    let api_input = OwnerReceiptCloseoutInput {
        owner_receipts: receipt_values,
        candidate_digest,
        required_owner_refs: &required_owner_refs,
        dependency_edges: &dependency_edges,
    };
    let decision = match owner_receipt_closeout_state(&api_input) {
        Ok(decision) => decision,
        Err(error) => {
            return OwnerReceiptCloseoutDecision {
                ready: false,
                applicable: true,
                reason: error.to_string(),
                owner_receipt_refs: Vec::new(),
                dependency_edges: dependency_edges.iter().map(json_string_text).collect(),
            };
        }
    };
    let mut seen = BTreeSet::new();
    let mut owner_receipt_refs = Vec::new();
    for (index, receipt) in receipt_values.iter().enumerate() {
        let prefix = JsonString::from_text(&format!("owner_receipts[{index}]"));
        let Ok(packet) = normalize_owner_guarantee_packet(receipt, Some(&prefix)) else {
            continue;
        };
        let Ok(key) = owner_receipt_key(&packet) else {
            continue;
        };
        if !seen.insert(key) {
            continue;
        }
        let compatible = owner_receipt_is_compatible(
            &packet,
            &OwnerReceiptCompatibility {
                candidate_digest,
                ..OwnerReceiptCompatibility::default()
            },
        )
        .unwrap_or(false);
        if compatible {
            if let Some(reference) =
                json_field(&packet, "primary_observation_ref").and_then(json_string)
            {
                owner_receipt_refs.push(json_string_text(reference));
            }
        }
    }
    let reason = if decision.reasons.is_empty() {
        "pass".to_owned()
    } else {
        decision
            .reasons
            .iter()
            .map(json_string_text)
            .collect::<Vec<_>>()
            .join(";")
    };
    OwnerReceiptCloseoutDecision {
        ready: decision.ready,
        applicable: true,
        reason,
        owner_receipt_refs,
        dependency_edges: dependency_edges.iter().map(json_string_text).collect(),
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UpdateLifecycleCloseoutDecision {
    pub ready: bool,
    pub applicable: bool,
    pub reason: String,
    pub gate_evidence_refs: Vec<String>,
    pub close_agent_token_id: Option<String>,
}

impl UpdateLifecycleCloseoutDecision {
    fn not_applicable() -> Self {
        Self {
            ready: true,
            applicable: false,
            reason: "not_applicable".to_owned(),
            gate_evidence_refs: Vec::new(),
            close_agent_token_id: None,
        }
    }

    fn rejected(reason: impl Into<String>) -> Self {
        Self {
            ready: false,
            applicable: true,
            reason: reason.into(),
            gate_evidence_refs: Vec::new(),
            close_agent_token_id: None,
        }
    }

    pub fn to_json_value(&self) -> SerdeValue {
        let mut result = serde_json::Map::new();
        result.insert("ready".to_owned(), SerdeValue::Bool(self.ready));
        result.insert("applicable".to_owned(), SerdeValue::Bool(self.applicable));
        result.insert("reason".to_owned(), SerdeValue::String(self.reason.clone()));
        if self.ready {
            result.insert(
                "gate_evidence_refs".to_owned(),
                SerdeValue::Array(
                    self.gate_evidence_refs
                        .iter()
                        .cloned()
                        .map(SerdeValue::String)
                        .collect(),
                ),
            );
            if let Some(token_id) = &self.close_agent_token_id {
                result.insert(
                    "close_agent_token_id".to_owned(),
                    SerdeValue::String(token_id.clone()),
                );
            }
        }
        SerdeValue::Object(result)
    }
}

pub fn update_lifecycle_closeout_consumer(
    boundary: &RuntimeArtifactBoundary,
    report_dir: &Path,
    source_root: &str,
) -> UpdateLifecycleCloseoutDecision {
    let artifact_path = report_dir.join(UPDATE_LIFECYCLE_CLOSEOUT_ARTIFACT_NAME);
    match is_regular_file(boundary, &artifact_path) {
        Ok(true) => {}
        Ok(false) => return UpdateLifecycleCloseoutDecision::not_applicable(),
        Err(error) => {
            return UpdateLifecycleCloseoutDecision::rejected(format!(
                "close_agent:artifact_unreadable:{error}"
            ));
        }
    }
    let bytes = match boundary.read_bytes(&artifact_path) {
        Ok(Some(bytes)) => bytes,
        Ok(None) => return UpdateLifecycleCloseoutDecision::not_applicable(),
        Err(error) => {
            return UpdateLifecycleCloseoutDecision::rejected(format!(
                "close_agent:artifact_unreadable:{error}"
            ));
        }
    };
    let closeout: SerdeValue = match serde_json::from_slice(&bytes) {
        Ok(value) => value,
        Err(error) => {
            return UpdateLifecycleCloseoutDecision::rejected(format!(
                "close_agent:artifact_unreadable:{error}"
            ));
        }
    };
    let Some(closeout) = closeout.as_object() else {
        return UpdateLifecycleCloseoutDecision::rejected("close_agent:schema_invalid");
    };
    if object_value(closeout, "schema").and_then(string_value)
        != Some(UPDATE_LIFECYCLE_CLOSEOUT_SCHEMA)
    {
        return UpdateLifecycleCloseoutDecision::rejected("close_agent:schema_invalid");
    }
    let required = [
        "schema",
        "gate_verdicts",
        "durable_handback",
        "descendants",
        "reservations",
        "descendants_closed_evidence_ref",
        "reservations_released_evidence_ref",
        "cleanup_proof",
        "close_agent_tool_call",
    ];
    if closeout.len() != required.len() || required.iter().any(|key| !closeout.contains_key(*key)) {
        return UpdateLifecycleCloseoutDecision::rejected("close_agent:artifact_fields_invalid");
    }
    let Some(raw_gate_values) = object_list(object_value(closeout, "gate_verdicts")) else {
        return UpdateLifecycleCloseoutDecision::rejected(
            "close_agent:all_six_gate_evidence_required",
        );
    };
    if raw_gate_values.len() != GATE_IDS.len() {
        return UpdateLifecycleCloseoutDecision::rejected(
            "close_agent:all_six_gate_evidence_required",
        );
    }
    let source_gates = match validate_gate_chain(&raw_gate_values[..5], Some(&GATE_IDS[..5]), true)
    {
        Ok(gates) => gates,
        Err(error) => return UpdateLifecycleCloseoutDecision::rejected(error.to_string()),
    };
    let identity = match source_gates
        .first()
        .and_then(|gate| gate.get("binding"))
        .map(binding_identity)
    {
        Some(Ok(identity)) => identity,
        Some(Err(error)) => return UpdateLifecycleCloseoutDecision::rejected(error.to_string()),
        None => return UpdateLifecycleCloseoutDecision::rejected("close_agent:identity_mismatch"),
    };
    for gate in source_gates.iter().skip(1) {
        let Some(binding) = gate.get("binding") else {
            return UpdateLifecycleCloseoutDecision::rejected("close_agent:identity_mismatch");
        };
        match binding_identity(binding) {
            Ok(found) if found == identity => {}
            Ok(_) => {
                return UpdateLifecycleCloseoutDecision::rejected("close_agent:identity_mismatch")
            }
            Err(error) => return UpdateLifecycleCloseoutDecision::rejected(error.to_string()),
        }
    }
    let handback = match object_value(closeout, "durable_handback").map(validate_durable_handback) {
        Some(Ok(value)) => value,
        Some(Err(error)) => return UpdateLifecycleCloseoutDecision::rejected(error.to_string()),
        None => {
            return UpdateLifecycleCloseoutDecision::rejected(
                "close_agent:durable_handback_invalid",
            )
        }
    };
    let cleanup = match object_value(closeout, "cleanup_proof").map(validate_cleanup_proof) {
        Some(Ok(value)) => value,
        Some(Err(error)) => return UpdateLifecycleCloseoutDecision::rejected(error.to_string()),
        None => {
            return UpdateLifecycleCloseoutDecision::rejected("close_agent:cleanup_proof_invalid")
        }
    };
    for record in [&handback, &cleanup] {
        let Some(binding) = record.get("binding") else {
            return UpdateLifecycleCloseoutDecision::rejected("close_agent:identity_mismatch");
        };
        match binding_identity(binding) {
            Ok(found) if found == identity => {}
            Ok(_) => {
                return UpdateLifecycleCloseoutDecision::rejected("close_agent:identity_mismatch")
            }
            Err(error) => return UpdateLifecycleCloseoutDecision::rejected(error.to_string()),
        }
    }
    let Some(descendant_values) = object_list(object_value(closeout, "descendants")) else {
        return UpdateLifecycleCloseoutDecision::rejected(
            "close_agent:descendant_evidence_invalid",
        );
    };
    if descendant_values.iter().any(|value| {
        value.as_object().is_some_and(|value| {
            value.get("state").and_then(SerdeValue::as_str) == Some("completed")
        })
    }) {
        return UpdateLifecycleCloseoutDecision::rejected("close_agent:completed_but_open");
    }
    let Some(reservation_values) = object_list(object_value(closeout, "reservations")) else {
        return UpdateLifecycleCloseoutDecision::rejected(
            "close_agent:reservation_evidence_invalid",
        );
    };
    let Some(supplied_token) =
        object_value(closeout, "close_agent_tool_call").and_then(SerdeValue::as_object)
    else {
        return UpdateLifecycleCloseoutDecision::rejected("close_agent:token_invalid");
    };
    let Some(supplied_args) = supplied_token.get("args").and_then(SerdeValue::as_object) else {
        return UpdateLifecycleCloseoutDecision::rejected("close_agent:token_invalid");
    };
    let Some(run_id) = supplied_args
        .get("run_id")
        .and_then(SerdeValue::as_str)
        .filter(|run_id| !crate::python_text::python_strip(run_id).is_empty())
    else {
        return UpdateLifecycleCloseoutDecision::rejected("close_agent:token_invalid");
    };
    let Some(agent_id) = handback.get("agent_id").and_then(SerdeValue::as_str) else {
        return UpdateLifecycleCloseoutDecision::rejected("close_agent:token_invalid");
    };
    let materialized = match materialize_g6(CloseAgentLifecycleOwnerInput {
        source_root,
        run_id,
        agent_id,
        evidence: CloseAgentLifecycleEvidence {
            gate_verdicts: &source_gates,
            cleanup_proof: &cleanup,
            durable_handback: &handback,
            descendant_close_receipts: descendant_values,
            reservation_release_receipts: reservation_values,
        },
    }) {
        Ok(value) => value,
        Err(error) => return UpdateLifecycleCloseoutDecision::rejected(error.to_string()),
    };
    let Some(canonical_g6) = materialized.get("g6_gate") else {
        return UpdateLifecycleCloseoutDecision::rejected("close_agent:g6_not_owner_materialized");
    };
    let Some(token) = materialized.get("close_agent_tool_call") else {
        return UpdateLifecycleCloseoutDecision::rejected("close_agent:token_evidence_mismatch");
    };
    let gate_values = match object_list(object_value(closeout, "gate_verdicts")) {
        Some(values) => values,
        None => unreachable!("gate values were checked above"),
    };
    if !python_json_equal(&gate_values[5], canonical_g6) {
        return UpdateLifecycleCloseoutDecision::rejected("close_agent:g6_not_owner_materialized");
    }
    for (key, expected) in [
        (
            "descendants_closed_evidence_ref",
            materialized.get("descendants_closed_evidence_ref"),
        ),
        (
            "reservations_released_evidence_ref",
            materialized.get("reservations_released_evidence_ref"),
        ),
    ] {
        let (Some(actual), Some(expected)) = (object_value(closeout, key), expected) else {
            return UpdateLifecycleCloseoutDecision::rejected(
                "close_agent:lifecycle_evidence_mismatch",
            );
        };
        if !python_json_equal(actual, expected) {
            return UpdateLifecycleCloseoutDecision::rejected(
                "close_agent:lifecycle_evidence_mismatch",
            );
        }
    }
    if !python_json_equal(&SerdeValue::Object(supplied_token.clone()), token) {
        return UpdateLifecycleCloseoutDecision::rejected("close_agent:token_evidence_mismatch");
    }
    let mut gate_evidence_refs = Vec::new();
    for gate in source_gates.iter().chain(std::iter::once(canonical_g6)) {
        let Some(evidence_ref) = gate
            .get("binding")
            .and_then(SerdeValue::as_object)
            .and_then(|binding| binding.get("evidence_ref"))
            .and_then(SerdeValue::as_str)
        else {
            return UpdateLifecycleCloseoutDecision::rejected(
                "close_agent:lifecycle_evidence_mismatch",
            );
        };
        gate_evidence_refs.push(evidence_ref.to_owned());
    }
    let Some(token_id) = token.get("token_id").and_then(SerdeValue::as_str) else {
        return UpdateLifecycleCloseoutDecision::rejected("close_agent:token_evidence_mismatch");
    };
    UpdateLifecycleCloseoutDecision {
        ready: true,
        applicable: true,
        reason: "pass".to_owned(),
        gate_evidence_refs,
        close_agent_token_id: Some(token_id.to_owned()),
    }
}

pub fn document_structure_evidence_ready(
    changed_markdown: &[String],
    evidence: &TaskCloseStatus,
) -> (bool, bool, bool) {
    if changed_markdown.is_empty() {
        return (true, true, true);
    }
    let recorded = parse_document_structure_paths(text(evidence, "document_structure_paths"));
    let normalized_changed = changed_markdown
        .iter()
        .map(|path| posix_path(path))
        .collect::<BTreeSet<_>>();
    let paths_recorded = normalized_changed.is_subset(&recorded);
    let status = text(evidence, "document_structure_status");
    let activation = text(evidence, "structure_activation");
    let structure_contract = text(evidence, "structure_contract");
    let split_decision_ready =
        document_split_decision_ready(status, text(evidence, "document_split_decision"));
    let graph_activation = text(evidence, "prose_graph_activation");
    let graph_status = text(evidence, "prose_graph");
    let optional_graph_evidence_ready = (graph_activation == "selected"
        && graph_status == "complete")
        || (graph_activation == "not_selected" && graph_status == "not_selected")
        || (matches!(graph_activation, "" | "not_applicable")
            && matches!(graph_status, "" | "not_applicable"));
    let identity_ready = [
        "structure_owner",
        "structure_source",
        "structure_reader",
        "structure_layout",
        "structure_validation_topology",
    ]
    .iter()
    .all(|field| !DOCUMENT_STRUCTURE_VALUE_MISSING.contains(&text(evidence, field)));
    let required_route = activation == "required"
        && text(evidence, "structure_planning") == "complete"
        && optional_graph_evidence_ready
        && structure_contract.starts_with("required:")
        && identity_ready;
    let existing_topology_route = activation == "not_required"
        && text(evidence, "structure_planning") == "not_required"
        && optional_graph_evidence_ready
        && structure_contract.starts_with("not_required:existing-topology:")
        && identity_ready;
    let complete_route = status == "complete"
        && matches!(activation, "required" | "not_required")
        && (required_route || existing_topology_route);
    let skipped_route = status == "skipped"
        && activation == "format_only"
        && text(evidence, "md_style_check") == "pass"
        && text(evidence, "document_split_decision")
            .starts_with(DOCUMENT_SPLIT_DECISION_FORMAT_ONLY_PREFIX)
        && structure_contract.starts_with("skipped:")
        && !DOCUMENT_STRUCTURE_VALUE_MISSING.contains(&text(evidence, "format_only_reason"));
    (
        paths_recorded,
        split_decision_ready,
        split_decision_ready && (complete_route || skipped_route),
    )
}

fn parse_document_structure_paths(value: &str) -> BTreeSet<String> {
    if ["", "missing", "none"].contains(&value) {
        return BTreeSet::new();
    }
    value
        .split(|character: char| character == ',' || character.is_whitespace())
        .filter(|item| !item.is_empty() && !["missing", "none"].contains(item))
        .map(posix_path)
        .collect()
}

fn document_split_decision_ready(status: &str, decision: &str) -> bool {
    let decision = crate::python_text::python_strip(decision);
    if DOCUMENT_STRUCTURE_MISSING_VALUES.contains(&decision) {
        return false;
    }
    if status == "skipped" {
        decision.starts_with(DOCUMENT_SPLIT_DECISION_FORMAT_ONLY_PREFIX)
    } else if status == "complete" {
        DOCUMENT_SPLIT_DECISION_PREFIXES
            .iter()
            .any(|prefix| decision.starts_with(prefix))
    } else {
        false
    }
}

fn posix_path(value: &str) -> String {
    let mut normalized = String::new();
    for component in Path::new(value).components() {
        match component {
            std::path::Component::Prefix(prefix) => {
                if !normalized.is_empty() {
                    normalized.push('/');
                }
                normalized.push_str(&prefix.as_os_str().to_string_lossy());
            }
            std::path::Component::RootDir => {
                if normalized.is_empty() {
                    normalized.push('/');
                }
            }
            std::path::Component::CurDir => {}
            std::path::Component::ParentDir => {
                if !normalized.is_empty() && !normalized.ends_with('/') {
                    normalized.push('/');
                }
                normalized.push_str("..");
            }
            std::path::Component::Normal(part) => {
                if !normalized.is_empty() && !normalized.ends_with('/') {
                    normalized.push('/');
                }
                normalized.push_str(&part.to_string_lossy());
            }
        }
    }
    normalized
}

fn git_output(workspace: &Path, args: &[&str]) -> Option<Output> {
    Command::new("git")
        .args(args)
        .current_dir(workspace)
        .output()
        .ok()
}

fn current_git_head(workspace: &Path) -> String {
    let Some(output) = git_output(workspace, &["rev-parse", "HEAD"]) else {
        return String::new();
    };
    if !output.status.success() {
        return String::new();
    }
    String::from_utf8_lossy(&output.stdout).trim().to_owned()
}

#[cfg(unix)]
fn git_path(raw: &[u8]) -> PathBuf {
    use std::os::unix::ffi::OsStrExt;
    PathBuf::from(std::ffi::OsStr::from_bytes(raw))
}

#[cfg(not(unix))]
fn git_path(raw: &[u8]) -> PathBuf {
    PathBuf::from(String::from_utf8_lossy(raw).into_owned())
}

pub fn current_diff_ref(workspace: &Path) -> Result<String, TaskCloseError> {
    let head = current_git_head(workspace);
    if head.is_empty() {
        return Err(TaskCloseError::new(format!(
            "Unable to resolve git HEAD from workspace: {}",
            workspace.display()
        )));
    }
    let unstaged = git_output(workspace, &["diff", "--binary"])
        .map(|output| output.stdout)
        .unwrap_or_default();
    let staged = git_output(workspace, &["diff", "--cached", "--binary"])
        .map(|output| output.stdout)
        .unwrap_or_default();
    let untracked = git_output(
        workspace,
        &["ls-files", "--others", "--exclude-standard", "-z"],
    );
    let mut diff_bytes = unstaged;
    diff_bytes.extend(staged);
    if let Some(output) = untracked.filter(|output| output.status.success()) {
        let mut paths = output
            .stdout
            .split(|byte| *byte == 0)
            .filter(|path| !path.is_empty())
            .filter(|path| !path.starts_with(b"reports/agents/"))
            .collect::<Vec<_>>();
        paths.sort();
        for raw_path in paths {
            let path = workspace.join(git_path(raw_path));
            diff_bytes.extend_from_slice(b"\0UNTRACKED\0");
            diff_bytes.extend_from_slice(raw_path);
            diff_bytes.push(0);
            if fs::metadata(&path).is_ok_and(|metadata| metadata.is_file()) {
                if let Ok(bytes) = fs::read(&path) {
                    diff_bytes.extend(bytes);
                }
            }
        }
    }
    if diff_bytes.is_empty() {
        return Ok(head);
    }
    let digest = Sha256::digest(diff_bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    Ok(format!("{head}-dirty-{digest}"))
}

fn changed_file_paths(workspace: &Path) -> Vec<String> {
    let commands: [&[&str]; 3] = [
        &["diff", "--name-only"],
        &["diff", "--cached", "--name-only"],
        &["ls-files", "--others", "--exclude-standard"],
    ];
    let mut paths = BTreeSet::new();
    for args in commands {
        let Some(output) = git_output(workspace, args) else {
            continue;
        };
        if !output.status.success() {
            continue;
        }
        let Ok(text) = std::str::from_utf8(&output.stdout) else {
            continue;
        };
        for line in text.lines() {
            let path = crate::python_text::python_strip(line);
            if path.is_empty()
                || path.starts_with("reports/")
                || path.starts_with(".agent-canon/log-archive/")
            {
                continue;
            }
            paths.insert(path.to_owned());
        }
    }
    paths.into_iter().collect()
}

fn active_run_name(
    boundary: &RuntimeArtifactBoundary,
    report_dir: &Path,
) -> Result<Option<String>, TaskCloseError> {
    let path = report_dir
        .parent()
        .unwrap_or(report_dir)
        .join(".active_run");
    if !is_regular_file(boundary, &path)? {
        return Ok(None);
    }
    read_text(boundary, &path)
        .map(|value| value.map(|value| crate::python_text::python_strip(&value).to_owned()))
}

fn active_run_matches(active_run: Option<&str>, report_dir: &Path) -> bool {
    let Some(active_run) = active_run else {
        return false;
    };
    active_run
        == report_dir
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or_default()
        || active_run == report_dir.to_string_lossy().as_ref()
}

fn workflow_tool_warning_problems(
    workflow_monitoring: Option<&str>,
) -> Result<Vec<String>, TaskCloseError> {
    let Some(workflow_monitoring) = workflow_monitoring else {
        return Ok(vec!["workflow_monitoring.md missing".to_owned()]);
    };
    let status = parse_markdown_status_lines(workflow_monitoring)
        .get("tool_warnings_status")
        .map(String::as_str)
        .unwrap_or("")
        .to_lowercase();
    let mut problems = Vec::new();
    if !["none", "resolved"].contains(&status.as_str()) {
        problems.push("tool_warnings_status must be none or resolved".to_owned());
    }
    let section = status_section_text(workflow_monitoring, "Tool Warnings");
    let mut latest_by_id = BTreeMap::<String, Status>::new();
    for line in section.lines() {
        if !line.contains("tool_warning=recorded") {
            continue;
        }
        let fields = token_fields(line);
        let warning_id = fields.get("warning_id").cloned().unwrap_or_default();
        if warning_id.is_empty() {
            problems.push("tool_warning entry missing warning_id".to_owned());
            continue;
        }
        latest_by_id.insert(warning_id, fields);
    }
    for (warning_id, fields) in latest_by_id {
        let warning_status = text(&fields, "status").to_lowercase();
        let severity = text(&fields, "severity").to_lowercase();
        if ["", "open", "pending", "observed", "unresolved"].contains(&warning_status.as_str()) {
            problems.push(format!("tool warning remains open: {warning_id}"));
        }
        if ["fix-now", "s0", "s1", "blocker"].contains(&severity.as_str())
            && warning_status != "resolved"
        {
            problems.push(format!(
                "fix-now tool warning must be resolved: {warning_id}"
            ));
        }
    }
    Ok(problems)
}

fn markdown_section_status(input: &str, heading: &str) -> Result<Status, TaskCloseError> {
    parse_status_section(input, heading)
}

pub fn check_task_close(request: &TaskCloseRequest) -> Result<TaskCloseResult, TaskCloseError> {
    let workspace = validate_parent_workspace(request)?;
    let boundary = runtime_boundary(request)?;
    check_task_close_with_context(request, workspace, boundary)
}

fn check_task_close_with_context(
    request: &TaskCloseRequest,
    workspace: PathBuf,
    boundary: RuntimeArtifactBoundary,
) -> Result<TaskCloseResult, TaskCloseError> {
    let declared_report_dir = if request.report_dir.is_absolute() {
        request.report_dir.clone()
    } else {
        workspace.join(&request.report_dir)
    };
    let report_dir = boundary
        .resolve(&declared_report_dir)
        .map_err(TaskCloseError::from)?;
    let active_run = active_run_name(&boundary, &report_dir)?;

    let required_paths = [
        ("verification.txt", "verification.txt"),
        ("closeout_gate.md", "closeout_gate.md"),
        ("user_request_contract.md", "user_request_contract.md"),
        ("schedule.md", "schedule.md"),
        ("work_log.md", "work_log.md"),
        ("agent_evaluation.md", "agent_evaluation.md"),
    ];
    for (filename, display_name) in required_paths {
        let path = report_dir.join(filename);
        if !is_regular_file(&boundary, &path)? {
            return Err(TaskCloseError::new(format!(
                "{display_name} not found: {}",
                path.display()
            )));
        }
    }
    let verification_text = read_required_text(
        &boundary,
        &report_dir.join("verification.txt"),
        "verification.txt",
    )?;
    let closeout_text = read_required_text(
        &boundary,
        &report_dir.join("closeout_gate.md"),
        "closeout_gate.md",
    )?;
    let request_contract_text = read_required_text(
        &boundary,
        &report_dir.join("user_request_contract.md"),
        "user_request_contract.md",
    )?;
    let schedule_text =
        read_required_text(&boundary, &report_dir.join("schedule.md"), "schedule.md")?;
    let work_log_text =
        read_required_text(&boundary, &report_dir.join("work_log.md"), "work_log.md")?;
    let agent_evaluation_text = read_required_text(
        &boundary,
        &report_dir.join("agent_evaluation.md"),
        "agent_evaluation.md",
    )?;
    let workflow_monitoring_path = report_dir.join("workflow_monitoring.md");
    let workflow_monitoring_text = if is_regular_file(&boundary, &workflow_monitoring_path)? {
        read_text(&boundary, &workflow_monitoring_path)?
    } else {
        None
    };
    let final_review_path = report_dir.join("final_review.md");
    let final_review_text = if is_regular_file(&boundary, &final_review_path)? {
        read_text(&boundary, &final_review_path)?
    } else {
        None
    };

    let verification = parse_key_values(&verification_text);
    let closeout = markdown_section_status(&closeout_text, "Gate Status")?;
    let tool_warning_evidence = markdown_section_status(&closeout_text, "Tool Warning Evidence")?;
    let document_structure =
        markdown_section_status(&closeout_text, "Document Structure Evidence")?;
    let subagent_lifecycle =
        markdown_section_status(&closeout_text, "Subagent Lifecycle Evidence")?;
    let agent_canon_latest = markdown_section_status(&closeout_text, "AgentCanon Latest Evidence")?;
    let canonical_evidence =
        markdown_section_status(&closeout_text, "Canonical Formatter And Static Evidence")?;
    let runtime_log_archive =
        markdown_section_status(&closeout_text, "Runtime Log Archive Evidence")?;
    let (child_closeout_ready, child_closeout_blockers) =
        child_closeout_evidence(&boundary, &report_dir, &closeout);
    let diff_check = markdown_section_status(&closeout_text, "Diff-Check Agent Evidence")?;
    let diff_check_artifact_path =
        artifact_path(&report_dir, text(&diff_check, "diff_check_artifact"))?;
    let diff_check_artifact = match diff_check_artifact_path.as_deref() {
        Some(path) if is_regular_file(&boundary, path)? => read_text(&boundary, path)?
            .map(|text| markdown_section_status(&text, "Diff-Check Review"))
            .transpose()?
            .unwrap_or_default(),
        _ => Status::new(),
    };
    let diff_check_not_applicable =
        text(&closeout, "diff_check_agent_complete").trim() == "not_applicable";
    let active_diff_ref = current_diff_ref(&workspace)?;
    let changed_all = changed_file_paths(&workspace);
    let changed_markdown = changed_all
        .iter()
        .filter(|path| path.ends_with(".md"))
        .cloned()
        .collect::<Vec<_>>();
    let diff_check_route_unselected = (text(&closeout, "required_reviews_complete").trim()
        == "not_applicable"
        || text(&diff_check, "diff_check_agent_role").trim() == "not_applicable")
        && [
            "diff_check_agent_role",
            "diff_check_agent_decision",
            "diff_check_latest_diff_ref",
            "diff_check_artifact",
        ]
        .iter()
        .all(|field| ["", "not_applicable"].contains(&text(&diff_check, field).trim()));
    let diff_check_not_applicable_valid = !diff_check_not_applicable
        || (diff_check_route_unselected
            && changed_all.is_empty()
            && active_diff_ref == current_git_head(&workspace));
    let (
        document_structure_paths_ready,
        document_split_decision_route_ready,
        document_structure_route_ready,
    ) = document_structure_evidence_ready(&changed_markdown, &document_structure);
    let agent_evaluation = parse_markdown_status_lines(&agent_evaluation_text);
    let workflow_tool_warning_blockers =
        workflow_tool_warning_problems(workflow_monitoring_text.as_deref())?;
    let request_contract = parse_markdown_status_lines(&request_contract_text);
    let work_log_blockers = check_work_log_artifact(&work_log_text);
    let final_review_blockers = final_review_text
        .as_deref()
        .map(check_final_review_artifact)
        .unwrap_or_default();
    let report_artifact_blockers = report_artifact_placement_blockers(&workspace, &report_dir)
        .map_err(TaskCloseError::from)?;
    let owner_receipt_decision = owner_receipt_closeout_consumer(&boundary, &report_dir);
    let source_root = request
        .source_root
        .to_str()
        .ok_or_else(|| TaskCloseError::new("AgentCanon source root is not valid Unicode"))?;
    let update_lifecycle_decision =
        update_lifecycle_closeout_consumer(&boundary, &report_dir, source_root);

    let active_run_match = active_run_matches(active_run.as_deref(), &report_dir);
    let diff_check_artifact_exists = diff_check_artifact_path
        .as_deref()
        .map(|path| is_regular_file(&boundary, path))
        .transpose()?
        .unwrap_or(false);
    // The old owner disables parent projection checks for the standalone source tree.
    let mut predicates = vec![
        (
            "verification_status",
            status_is(&verification, "status", "pass"),
        ),
        (
            "closeout_verifier_status",
            status_is(&closeout, "verifier_status", "pass"),
        ),
        (
            "closeout_auditor_status",
            status_is(&closeout, "auditor_status", "resolved"),
        ),
        ("verifier_child_provenance", child_closeout_ready),
        ("parent_nonmutation_evidence", child_closeout_ready),
        (
            "required_reviews_complete",
            status_is_one_of(
                &closeout,
                "required_reviews_complete",
                &["yes", "not_applicable"],
            ),
        ),
        (
            "validation_complete",
            status_is(&closeout, "validation_complete", "yes"),
        ),
        (
            "request_contract_complete",
            status_is(&closeout, "request_contract_complete", "yes"),
        ),
        ("owner_receipts_consumer", owner_receipt_decision.ready),
        (
            "update_lifecycle_closeout_consumer",
            update_lifecycle_decision.ready,
        ),
        (
            "overall_delivery_complete",
            status_is(&closeout, "overall_delivery_complete", "yes"),
        ),
        (
            "dependency_headers_complete",
            status_is(&closeout, "dependency_headers_complete", "yes"),
        ),
        (
            "repo_wide_dependency_tools_complete",
            status_is(&closeout, "repo_wide_dependency_tools_complete", "yes"),
        ),
        (
            "repo_wide_static_analysis_complete",
            status_is_one_of(
                &closeout,
                "repo_wide_static_analysis_complete",
                STATIC_ANALYSIS_COMPLETE_STATUSES,
            ),
        ),
        (
            "agent_canon_latest_complete",
            status_is_one_of(
                &closeout,
                "agent_canon_latest_complete",
                &["yes", "not_applicable"],
            ),
        ),
        ("agent_canon_latest_command", true),
        ("agent_canon_latest_status", true),
        ("agent_canon_submodule_status", true),
        ("agent_canon_source_head", true),
        ("agent_canon_parent_pin", true),
        ("agent_canon_parent_gitlink_commit", true),
        (
            "mapping_error_sets_empty",
            status_fallback(&closeout, &canonical_evidence, "mapping_error_sets_empty") == "yes",
        ),
        (
            "typed_owner_boundary_status",
            status_fallback(
                &closeout,
                &canonical_evidence,
                "typed_owner_boundary_status",
            ) == "pass",
        ),
        (
            "canonical_format_check_status",
            status_fallback(
                &canonical_evidence,
                &closeout,
                "canonical_format_check_status",
            ) == "pass",
        ),
        (
            "canonical_dispatcher_schema_status",
            status_fallback(
                &closeout,
                &canonical_evidence,
                "canonical_dispatcher_schema_status",
            ) == "pass",
        ),
        (
            "review_findings_integrated",
            status_is(&closeout, "review_findings_integrated", "yes"),
        ),
        (
            "focused_recheck_complete",
            status_is_one_of(
                &closeout,
                "focused_recheck_complete",
                &["yes", "not_applicable"],
            ),
        ),
        (
            "tool_warnings_resolved",
            status_is(&closeout, "tool_warnings_resolved", "yes"),
        ),
        (
            "tool_warning_monitoring_status",
            status_is_one_of(
                &tool_warning_evidence,
                "tool_warning_monitoring_status",
                &["none", "resolved"],
            ),
        ),
        (
            "tool_warning_open_items",
            status_is(&tool_warning_evidence, "tool_warning_open_items", "none"),
        ),
        (
            "tool_warning_resolution_evidence",
            is_not_missing(text(
                &tool_warning_evidence,
                "tool_warning_resolution_evidence",
            )),
        ),
        (
            "workflow_tool_warnings_closed",
            workflow_tool_warning_blockers.is_empty(),
        ),
        (
            "document_structure_paths_recorded",
            document_structure_paths_ready,
        ),
        (
            "document_split_decision_evidence",
            document_split_decision_route_ready,
        ),
        (
            "document_structure_evidence",
            document_structure_route_ready,
        ),
        (
            "subagents_closed",
            status_is(&closeout, "subagents_closed", "yes"),
        ),
        (
            "subagent_closeout_status",
            status_is_one_of(
                &subagent_lifecycle,
                "subagent_closeout_status",
                &["closed", "not_applicable"],
            ),
        ),
        (
            "open_subagent_instances",
            status_is(&subagent_lifecycle, "open_subagent_instances", "none"),
        ),
        (
            "close_agent_evidence",
            !["", "none", "missing"].contains(&text(&subagent_lifecycle, "close_agent_evidence")),
        ),
        (
            "diff_check_not_applicable_route",
            diff_check_not_applicable_valid,
        ),
        (
            "diff_check_agent_complete",
            diff_check_not_applicable || status_is(&closeout, "diff_check_agent_complete", "yes"),
        ),
        (
            "diff_check_agent_role",
            diff_check_not_applicable
                || !["", "parent", "self", "codex"]
                    .contains(&text(&diff_check, "diff_check_agent_role")),
        ),
        (
            "diff_check_agent_decision",
            diff_check_not_applicable
                || status_is(&diff_check, "diff_check_agent_decision", "approve"),
        ),
        (
            "diff_check_latest_diff_ref",
            diff_check_not_applicable
                || text(&diff_check, "diff_check_latest_diff_ref") == active_diff_ref,
        ),
        (
            "diff_check_artifact_path",
            diff_check_not_applicable || diff_check_artifact_path.is_some(),
        ),
        (
            "diff_check_artifact_exists",
            diff_check_not_applicable || diff_check_artifact_exists,
        ),
        (
            "diff_check_artifact_role",
            diff_check_not_applicable
                || text(&diff_check_artifact, "diff_check_agent_role")
                    == text(&diff_check, "diff_check_agent_role"),
        ),
        (
            "diff_check_artifact_decision",
            diff_check_not_applicable
                || status_is(&diff_check_artifact, "diff_check_agent_decision", "approve"),
        ),
        (
            "diff_check_artifact_latest_diff_ref",
            diff_check_not_applicable
                || text(&diff_check_artifact, "diff_check_latest_diff_ref")
                    == text(&diff_check, "diff_check_latest_diff_ref"),
        ),
        (
            "diff_check_artifact_read_only",
            diff_check_not_applicable
                || status_is(&diff_check_artifact, "diff_check_read_only", "yes"),
        ),
        (
            "diff_check_artifact_independent",
            diff_check_not_applicable
                || status_is(&diff_check_artifact, "diff_check_independent_agent", "yes"),
        ),
        (
            "diff_check_artifact_findings_status",
            diff_check_not_applicable
                || status_is_one_of(
                    &diff_check_artifact,
                    "diff_check_findings_status",
                    &["none", "resolved"],
                ),
        ),
        (
            "canonical_tree_head_complete",
            status_is(&closeout, "canonical_tree_head_complete", "yes"),
        ),
        (
            "agent_evaluation_complete",
            status_is(&closeout, "agent_evaluation_complete", "yes"),
        ),
        (
            "runtime_log_archive_synced",
            status_is(&closeout, "runtime_log_archive_synced", "yes"),
        ),
        (
            "runtime_log_archive_sync_command",
            is_not_missing(text(
                &runtime_log_archive,
                "runtime_log_archive_sync_command",
            )),
        ),
        (
            "runtime_log_archive_sync_status",
            status_is(
                &runtime_log_archive,
                "runtime_log_archive_sync_status",
                "pass",
            ),
        ),
        (
            "runtime_log_archive_check_clean_status",
            status_is(
                &runtime_log_archive,
                "runtime_log_archive_check_clean_status",
                "pass",
            ),
        ),
        (
            "runtime_log_archive_dirty",
            status_is(&runtime_log_archive, "runtime_log_archive_dirty", "no"),
        ),
        (
            "runtime_log_archive_foreign_dirty",
            status_is(
                &runtime_log_archive,
                "runtime_log_archive_foreign_dirty",
                "no",
            ),
        ),
        (
            "runtime_log_archive_branch_match",
            status_is(
                &runtime_log_archive,
                "runtime_log_archive_branch_match",
                "yes",
            ),
        ),
        (
            "runtime_log_archive_commit_or_noop",
            is_not_missing(text(&runtime_log_archive, "runtime_log_archive_commit")),
        ),
        (
            "runtime_log_archive_push_or_noop",
            is_not_missing(text(&runtime_log_archive, "runtime_log_archive_push")),
        ),
        (
            "agent_evaluation_status",
            status_is(&agent_evaluation, "evaluation_status", "pass"),
        ),
        (
            "agent_feedback_resolved",
            status_is(&agent_evaluation, "feedback_actions_resolved", "yes"),
        ),
        (
            "agent_learning_capture_complete",
            status_is(&agent_evaluation, "learning_capture_complete", "yes"),
        ),
        (
            "request_contract_resolved",
            status_is(&request_contract, "all_clauses_resolved", "yes"),
        ),
        (
            "no_forbidden_drift",
            status_is(&request_contract, "forbidden_drift_detected", "no"),
        ),
        ("work_log_complete", work_log_blockers.is_empty()),
        (
            "final_review_artifact_complete",
            final_review_blockers.is_empty(),
        ),
        ("report_active_run_match", active_run_match),
        (
            "report_artifact_placement_clean",
            report_artifact_blockers.is_empty(),
        ),
        (
            "commit_created",
            status_is_one_of(&closeout, "commit_created", COMMIT_PUSH_COMPLETE_STATUSES),
        ),
        (
            "push_completed",
            status_is_one_of(&closeout, "push_completed", COMMIT_PUSH_COMPLETE_STATUSES),
        ),
        (
            "closeout_unlock",
            status_is(&closeout, "user_completion_report", "unlocked"),
        ),
    ];
    if predicates.len() != 75 {
        return Err(TaskCloseError::new(format!(
            "native TaskClose predicate table has {} entries, expected 75",
            predicates.len()
        )));
    }
    let ready = predicates.iter().all(|(_, passed)| *passed);
    let predicate_records = predicates
        .iter()
        .map(|(name, passed)| TaskClosePredicate {
            name,
            passed: *passed,
        })
        .collect::<Vec<_>>();
    let mut stdout = Vec::new();
    let mut line = |value: String| stdout.push(value);
    line(format!("REPORT_DIR={}", report_dir.display()));
    line(format!(
        "VERIFICATION_STATUS={}",
        text(&verification, "status")
    ));
    line(format!(
        "CLOSEOUT_VERIFIER_STATUS={}",
        text(&closeout, "verifier_status")
    ));
    line(format!(
        "CLOSEOUT_AUDITOR_STATUS={}",
        text(&closeout, "auditor_status")
    ));
    line(format!(
        "VERIFIER_CHILD_PROVENANCE={}",
        if child_closeout_ready { "pass" } else { "fail" }
    ));
    line(format!(
        "PARENT_NONMUTATION_EVIDENCE={}",
        if child_closeout_ready { "pass" } else { "fail" }
    ));
    line(format!(
        "CHILD_CLOSEOUT_BLOCKERS={}",
        join_blockers(&child_closeout_blockers)
    ));
    line(format!(
        "REQUIRED_REVIEWS_COMPLETE={}",
        text(&closeout, "required_reviews_complete")
    ));
    line(format!(
        "VALIDATION_COMPLETE={}",
        text(&closeout, "validation_complete")
    ));
    line(format!(
        "REQUEST_CONTRACT_COMPLETE={}",
        text(&closeout, "request_contract_complete")
    ));
    line(format!(
        "OVERALL_DELIVERY_COMPLETE={}",
        text(&closeout, "overall_delivery_complete")
    ));
    line(format!(
        "OWNER_RECEIPTS_CONSUMER={}",
        if owner_receipt_decision.ready {
            "yes"
        } else {
            "no"
        }
    ));
    line(format!(
        "OWNER_RECEIPTS_CONSUMER_REASON={}",
        owner_receipt_decision.reason
    ));
    line(format!(
        "UPDATE_LIFECYCLE_CLOSEOUT_APPLICABLE={}",
        python_bool(update_lifecycle_decision.applicable)
    ));
    line(format!(
        "UPDATE_LIFECYCLE_CLOSEOUT_READY={}",
        python_bool(update_lifecycle_decision.ready)
    ));
    line(format!(
        "UPDATE_LIFECYCLE_CLOSEOUT_REASON={}",
        update_lifecycle_decision.reason
    ));
    line(format!(
        "MAPPING_ERROR_SETS_EMPTY={}",
        status_fallback(&closeout, &canonical_evidence, "mapping_error_sets_empty")
    ));
    line(format!(
        "TYPED_OWNER_BOUNDARY_STATUS={}",
        status_fallback(
            &closeout,
            &canonical_evidence,
            "typed_owner_boundary_status"
        )
    ));
    line(format!(
        "CANONICAL_FORMAT_CHECK_STATUS={}",
        status_fallback(
            &canonical_evidence,
            &closeout,
            "canonical_format_check_status"
        )
    ));
    line(format!(
        "CANONICAL_DISPATCHER_SCHEMA_STATUS={}",
        status_fallback(
            &closeout,
            &canonical_evidence,
            "canonical_dispatcher_schema_status"
        )
    ));
    line(format!(
        "DEPENDENCY_HEADERS_COMPLETE={}",
        text(&closeout, "dependency_headers_complete")
    ));
    line(format!(
        "REPO_WIDE_DEPENDENCY_TOOLS_COMPLETE={}",
        text(&closeout, "repo_wide_dependency_tools_complete")
    ));
    line(format!(
        "REPO_WIDE_STATIC_ANALYSIS_COMPLETE={}",
        text(&closeout, "repo_wide_static_analysis_complete")
    ));
    line(format!(
        "AGENT_CANON_LATEST_COMPLETE={}",
        text(&closeout, "agent_canon_latest_complete")
    ));
    line(format!(
        "AGENT_CANON_LATEST_COMMAND={}",
        text(&agent_canon_latest, "agent_canon_latest_command")
    ));
    line(format!(
        "AGENT_CANON_LATEST_STATUS={}",
        text(&agent_canon_latest, "agent_canon_latest_status")
    ));
    line(format!(
        "AGENT_CANON_SUBMODULE_STATUS={}",
        text(&agent_canon_latest, "agent_canon_submodule_status")
    ));
    line(format!(
        "AGENT_CANON_SOURCE_HEAD={}",
        text(&agent_canon_latest, "agent_canon_source_head")
    ));
    line(format!(
        "AGENT_CANON_PARENT_PIN={}",
        text(&agent_canon_latest, "agent_canon_parent_pin")
    ));
    line(format!(
        "REVIEW_FINDINGS_INTEGRATED={}",
        text(&closeout, "review_findings_integrated")
    ));
    line(format!(
        "FOCUSED_RECHECK_COMPLETE={}",
        text(&closeout, "focused_recheck_complete")
    ));
    line(format!(
        "TOOL_WARNINGS_RESOLVED={}",
        text(&closeout, "tool_warnings_resolved")
    ));
    line(format!(
        "TOOL_WARNING_MONITORING_STATUS={}",
        text(&tool_warning_evidence, "tool_warning_monitoring_status")
    ));
    line(format!(
        "TOOL_WARNING_OPEN_ITEMS={}",
        text(&tool_warning_evidence, "tool_warning_open_items")
    ));
    line(format!(
        "TOOL_WARNING_RESOLUTION_EVIDENCE={}",
        text(&tool_warning_evidence, "tool_warning_resolution_evidence")
    ));
    line(format!(
        "WORKFLOW_TOOL_WARNING_BLOCKERS={}",
        join_blockers(&workflow_tool_warning_blockers)
    ));
    line(format!(
        "DOCUMENT_STRUCTURE_REQUIRED={}",
        if changed_markdown.is_empty() {
            "no"
        } else {
            "yes"
        }
    ));
    line(format!(
        "DOCUMENT_STRUCTURE_CHANGED_MARKDOWN={}",
        if changed_markdown.is_empty() {
            "none".to_owned()
        } else {
            changed_markdown.join(",")
        }
    ));
    line(format!(
        "DOCUMENT_STRUCTURE_STATUS={}",
        text(&document_structure, "document_structure_status")
    ));
    line(format!(
        "DOCUMENT_STRUCTURE_PATHS={}",
        text(&document_structure, "document_structure_paths")
    ));
    line(format!(
        "DOCUMENT_SPLIT_DECISION={}",
        text(&document_structure, "document_split_decision")
    ));
    line(format!(
        "DOCUMENT_SPLIT_DECISION_EVIDENCE={}",
        if document_split_decision_route_ready {
            "yes"
        } else {
            "no"
        }
    ));
    line(format!(
        "DOCUMENT_STRUCTURE_EVIDENCE={}",
        if document_structure_route_ready {
            "yes"
        } else {
            "no"
        }
    ));
    line(format!(
        "SUBAGENT_CLOSEOUT_STATUS={}",
        text(&subagent_lifecycle, "subagent_closeout_status")
    ));
    line(format!(
        "SUBAGENT_OPEN_INSTANCES={}",
        text(&subagent_lifecycle, "open_subagent_instances")
    ));
    line(format!(
        "DIFF_CHECK_AGENT_COMPLETE={}",
        text(&closeout, "diff_check_agent_complete")
    ));
    line(format!(
        "DIFF_CHECK_AGENT_ROLE={}",
        text(&diff_check, "diff_check_agent_role")
    ));
    line(format!(
        "DIFF_CHECK_AGENT_DECISION={}",
        text(&diff_check, "diff_check_agent_decision")
    ));
    line(format!(
        "DIFF_CHECK_LATEST_DIFF_REF={}",
        text(&diff_check, "diff_check_latest_diff_ref")
    ));
    line(format!("DIFF_CHECK_CURRENT_DIFF_REF={active_diff_ref}"));
    line(format!(
        "DIFF_CHECK_ARTIFACT={}",
        text(&diff_check, "diff_check_artifact")
    ));
    line(format!(
        "DIFF_CHECK_ARTIFACT_EXISTS={}",
        if diff_check_artifact_exists {
            "yes"
        } else {
            "no"
        }
    ));
    line(format!(
        "CANONICAL_TREE_HEAD_COMPLETE={}",
        text(&closeout, "canonical_tree_head_complete")
    ));
    line(format!(
        "AGENT_EVALUATION_COMPLETE={}",
        text(&closeout, "agent_evaluation_complete")
    ));
    line(format!(
        "RUNTIME_LOG_ARCHIVE_SYNCED={}",
        text(&closeout, "runtime_log_archive_synced")
    ));
    line(format!(
        "RUNTIME_LOG_ARCHIVE_SYNC_COMMAND={}",
        text(&runtime_log_archive, "runtime_log_archive_sync_command")
    ));
    line(format!(
        "RUNTIME_LOG_ARCHIVE_SYNC_STATUS={}",
        text(&runtime_log_archive, "runtime_log_archive_sync_status")
    ));
    line(format!(
        "RUNTIME_LOG_ARCHIVE_CHECK_CLEAN_STATUS={}",
        text(
            &runtime_log_archive,
            "runtime_log_archive_check_clean_status"
        )
    ));
    line(format!(
        "RUNTIME_LOG_ARCHIVE_DIRTY={}",
        text(&runtime_log_archive, "runtime_log_archive_dirty")
    ));
    line(format!(
        "RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY={}",
        text(&runtime_log_archive, "runtime_log_archive_foreign_dirty")
    ));
    line(format!(
        "RUNTIME_LOG_ARCHIVE_BRANCH_MATCH={}",
        text(&runtime_log_archive, "runtime_log_archive_branch_match")
    ));
    line(format!(
        "AGENT_EVALUATION_STATUS={}",
        text(&agent_evaluation, "evaluation_status")
    ));
    line(format!(
        "AGENT_FEEDBACK_RESOLVED={}",
        text(&agent_evaluation, "feedback_actions_resolved")
    ));
    line(format!(
        "AGENT_LEARNING_CAPTURE_COMPLETE={}",
        text(&agent_evaluation, "learning_capture_complete")
    ));
    line(format!(
        "REQUEST_CONTRACT_RESOLVED={}",
        text(&request_contract, "all_clauses_resolved")
    ));
    line(format!(
        "FORBIDDEN_DRIFT_DETECTED={}",
        text(&request_contract, "forbidden_drift_detected")
    ));
    line(format!(
        "UNRESOLVED_CLAUSE_IDS={}",
        text(&request_contract, "unresolved_clause_ids")
    ));
    line(format!(
        "WORK_LOG_COMPLETE={}",
        if work_log_blockers.is_empty() {
            "yes"
        } else {
            "no"
        }
    ));
    line(format!(
        "WORK_LOG_BLOCKERS={}",
        join_blockers(&work_log_blockers)
    ));
    line(format!(
        "FINAL_REVIEW_ARTIFACT_COMPLETE={}",
        if final_review_blockers.is_empty() {
            "yes"
        } else {
            "no"
        }
    ));
    line(format!(
        "FINAL_REVIEW_ARTIFACT_BLOCKERS={}",
        join_blockers(&final_review_blockers)
    ));
    line(format!(
        "REPORT_ACTIVE_RUN={}",
        active_run.as_deref().unwrap_or("")
    ));
    line(format!(
        "REPORT_ACTIVE_RUN_MATCH={}",
        if active_run_match { "yes" } else { "no" }
    ));
    line(format!(
        "REPORT_ARTIFACT_PLACEMENT_CLEAN={}",
        if report_artifact_blockers.is_empty() {
            "yes"
        } else {
            "no"
        }
    ));
    line(format!(
        "REPORT_ARTIFACT_PLACEMENT_BLOCKERS={}",
        join_blockers(&report_artifact_blockers)
    ));
    line(format!(
        "COMMIT_CREATED={}",
        text(&closeout, "commit_created")
    ));
    line(format!(
        "PUSH_COMPLETED={}",
        text(&closeout, "push_completed")
    ));
    line(format!(
        "USER_COMPLETION_REPORT={}",
        text(&closeout, "user_completion_report")
    ));
    line(format!(
        "CLOSEOUT_READY={}",
        if ready { "yes" } else { "no" }
    ));
    if !ready {
        let blockers = predicates
            .iter()
            .filter_map(|(name, passed)| (!passed).then_some(*name))
            .collect::<Vec<_>>()
            .join(",");
        line(format!("CLOSEOUT_BLOCKERS={blockers}"));
    }
    let mut stdout = stdout.join("\n");
    stdout.push('\n');
    Ok(TaskCloseResult {
        report_dir,
        ready,
        predicates: predicate_records,
        stdout,
    })
}

#[derive(Default)]
struct CliOptions {
    run_id: Option<String>,
    report_dir: Option<PathBuf>,
    report_root: Option<PathBuf>,
    runtime_root: Option<PathBuf>,
}

const USAGE: &str = "usage: agent-canon task-close (--run-id RUN_ID | --report-dir PATH) [--report-root PATH] [--runtime-root PATH]";

fn parse_cli_args(args: &[String]) -> Result<CliOptions, String> {
    let mut parsed = CliOptions::default();
    let mut index = 0;
    while index < args.len() {
        let option = args[index].as_str();
        if matches!(option, "-h" | "--help") {
            return Err("__help__".to_owned());
        }
        let value = args
            .get(index + 1)
            .ok_or_else(|| format!("{option} requires a value"))?;
        match option {
            "--run-id" => parsed.run_id = Some(value.clone()),
            "--report-dir" => parsed.report_dir = Some(PathBuf::from(value)),
            "--report-root" => parsed.report_root = Some(PathBuf::from(value)),
            "--runtime-root" => parsed.runtime_root = Some(PathBuf::from(value)),
            _ => return Err(format!("unrecognized arguments: {option}")),
        }
        index += 2;
    }
    if parsed.run_id.is_some() == parsed.report_dir.is_some() {
        return Err("Provide exactly one of --run-id or --report-dir.".to_owned());
    }
    Ok(parsed)
}

fn environment_path(name: &str, required: bool) -> Result<Option<PathBuf>, TaskCloseError> {
    let Some(value) = env::var_os(name) else {
        return if required {
            Err(TaskCloseError::new(format!("{name} is required")))
        } else {
            Ok(None)
        };
    };
    let value = value.to_string_lossy();
    let value = crate::python_text::python_strip(&value);
    if value.is_empty() {
        return if required {
            Err(TaskCloseError::new(format!("{name} is required")))
        } else {
            Ok(None)
        };
    }
    Ok(Some(PathBuf::from(value)))
}

pub fn run_cli(args: &[String]) -> i32 {
    let parsed = match parse_cli_args(args) {
        Ok(parsed) => parsed,
        Err(message) if message == "__help__" => {
            println!("{USAGE}\n\nChecks the current run bundle before reporting task completion.");
            return 0;
        }
        Err(message) => {
            eprintln!("{USAGE}\nagent-canon task-close: error: {message}");
            return 2;
        }
    };
    let workspace = match env::current_dir()
        .and_then(|path| fs::canonicalize(path))
        .map_err(|error| TaskCloseError::new(format!("current workspace is unavailable: {error}")))
    {
        Ok(path) => path,
        Err(error) => {
            eprintln!("task-close: {error}");
            return 1;
        }
    };
    let parent_root = match environment_path("AGENT_CANON_PARENT_ROOT", true) {
        Ok(Some(path)) => match fs::canonicalize(&path) {
            Ok(path) => path,
            Err(error) => {
                eprintln!("task-close: parent root is unavailable: {error}");
                return 1;
            }
        },
        Ok(None) => unreachable!("required parent root is present"),
        Err(error) => {
            eprintln!("task-close: {error}");
            return 1;
        }
    };
    let authority_request = TaskCloseRequest {
        workspace_root: workspace.clone(),
        report_dir: PathBuf::new(),
        parent_root: parent_root.clone(),
        source_root: PathBuf::new(),
        runtime_root: None,
    };
    if let Err(error) = validate_parent_workspace(&authority_request) {
        eprintln!("task-close: {error}");
        return 1;
    }
    let source_root = match environment_path("AGENT_CANON_SOURCE_ROOT", true) {
        Ok(Some(path)) => match fs::canonicalize(&path) {
            Ok(path) => path,
            Err(error) => {
                eprintln!("task-close: AgentCanon source root is unavailable: {error}");
                return 1;
            }
        },
        Ok(None) => unreachable!("required source root is present"),
        Err(error) => {
            eprintln!("task-close: {error}");
            return 1;
        }
    };
    let runtime_root = parsed
        .runtime_root
        .or_else(|| environment_path(RUNTIME_ROOT_ENV, false).ok().flatten());
    let provisional = TaskCloseRequest {
        workspace_root: workspace.clone(),
        report_dir: PathBuf::new(),
        parent_root,
        source_root,
        runtime_root,
    };
    let boundary = match runtime_boundary(&provisional) {
        Ok(boundary) => boundary,
        Err(error) => {
            eprintln!("task-close: {error}");
            return 1;
        }
    };
    let report_dir = if let Some(report_dir) = parsed.report_dir {
        if report_dir.is_absolute() {
            report_dir
        } else {
            workspace.join(report_dir)
        }
    } else {
        let report_root = parsed
            .report_root
            .unwrap_or_else(|| PathBuf::from("reports/agents"));
        let report_root = match boundary.resolve(&report_root) {
            Ok(path) => path,
            Err(error) => {
                eprintln!("task-close: {error}");
                return 1;
            }
        };
        report_root.join(parsed.run_id.expect("run-id was selected"))
    };
    let request = TaskCloseRequest {
        report_dir,
        ..provisional
    };
    match check_task_close_with_context(&request, workspace, boundary) {
        Ok(result) => {
            print!("{}", result.stdout);
            if result.ready {
                0
            } else {
                1
            }
        }
        Err(error) => {
            eprintln!("task-close: {error}");
            1
        }
    }
}
