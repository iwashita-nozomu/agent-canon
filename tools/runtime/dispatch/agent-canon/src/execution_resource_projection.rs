// @dependency-start
// contract implementation
// responsibility Validates and forwards the exact PostToolUse execution-resource projection.
// upstream implementation python_json.rs owns Python-compatible JSON parsing and canonical bytes.
// upstream implementation ../../../container/execution_resource_projection.py owns existing behavior semantics.
// downstream test ../tests/execution_resource_projection_native.rs validates frozen CPython 3.12.3 behavior.
// downstream implementation ../../../../../.codex/hooks/hook_dispatcher.py maps failures to invalid_projection without consuming diagnostics.
// @dependency-end

//! Pure validation and wrapper construction for PostToolUse execution-resource projections.

use crate::python_json::{
    canonical_json_ascii_bytes_reject_nonfinite, parse_json_reject_duplicates, JsonNumber,
    JsonObject, JsonString, JsonValue,
};
use sha2::{Digest, Sha256};
use std::fmt;

const OFFICIAL_HOOK_SCHEMA: &str = "agent-canon.posttooluse-stop.v1";
const NORMALIZED_INPUT_SCHEMA: &str = "agent-canon-post-tool-use-input/v1";
const PROJECTION_SCHEMA_VERSION: &str = "execution-resource-plan-projection/v2";
const ADMISSION_GUARANTEE: &str = "run-level-opaque-uuid-admission";
const MAX_PROJECTION_BYTES: usize = 64 * 1024;
const PROJECTION_KEYS: &[&str] = &[
    "admission",
    "completion_coverage_path",
    "error",
    "exit_code",
    "plan_fingerprint",
    "plan_path",
    "projection",
    "run_id",
    "schema_version",
];
const NORMALIZED_INPUT_KEYS: &[&str] = &[
    "hook_event_name",
    "schema_version",
    "tool_input_fingerprint",
    "tool_name",
    "tool_input",
    "tool_response",
];
const ADMISSION_KEYS: &[&str] = &[
    "admission_fingerprint",
    "guarantee",
    "namespace_id",
    "runtime_identity_fingerprint",
    "selected_uuids",
];
const PROJECTION_ERROR_KINDS: &[&str] = &[
    "managed_gpu_failure",
    "managed_gpu_execution",
    "see_execution_resource_plan",
];

/// A projection validation failure with a generic native diagnostic.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectionError(String);

impl ProjectionError {
    pub fn message(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for ProjectionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for ProjectionError {}

impl From<String> for ProjectionError {
    fn from(message: String) -> Self {
        Self(message)
    }
}

/// Validate the exact dispatcher-owned six-field PostToolUse input.
pub fn validate_normalized_input(payload: &JsonValue) -> Result<(), ProjectionError> {
    let fields =
        object(payload).ok_or_else(|| "normalized PostToolUse fields are not exact".to_owned())?;
    if !has_exact_keys(fields, NORMALIZED_INPUT_KEYS) {
        return Err("normalized PostToolUse fields are not exact"
            .to_owned()
            .into());
    }
    if string_field(fields, "hook_event_name").as_deref() != Some("PostToolUse") {
        return Err("normalized Hook event is not PostToolUse".to_owned().into());
    }
    if string_field(fields, "schema_version").as_deref() != Some(NORMALIZED_INPUT_SCHEMA) {
        return Err("normalized Hook schema_version is not exact"
            .to_owned()
            .into());
    }
    if !is_string(field(fields, "tool_name").expect("exact normalized fields")) {
        return Err("normalized tool_name is not a string".to_owned().into());
    }
    let tool_input = field(fields, "tool_input").expect("exact normalized fields");
    object(tool_input).ok_or_else(|| "normalized tool_input is not an object".to_owned())?;
    let fingerprint = string_field(fields, "tool_input_fingerprint");
    require_sha256(fingerprint.as_deref(), "tool_input_fingerprint")?;
    let canonical = canonical_json_ascii_bytes_reject_nonfinite(tool_input)?;
    let expected_fingerprint = sha256_hex(&canonical);
    if fingerprint.as_deref() != Some(expected_fingerprint.as_str()) {
        return Err("tool_input_fingerprint does not match tool_input"
            .to_owned()
            .into());
    }

    let response = field(fields, "tool_response").expect("exact normalized fields");
    let response_fields = object(response);
    if !response_fields
        .is_some_and(|fields| has_exact_keys(fields, &["exit_code", "stderr", "stdout"]))
    {
        return Err("normalized tool_response fields are not exact"
            .to_owned()
            .into());
    }
    let response_fields = response_fields.expect("checked response object");
    let exit_code = field(response_fields, "exit_code").expect("exact response fields");
    if !is_integer(exit_code)
        || !is_string(field(response_fields, "stderr").expect("exact response fields"))
        || !is_string(field(response_fields, "stdout").expect("exact response fields"))
    {
        return Err("normalized tool_response field types are invalid"
            .to_owned()
            .into());
    }
    Ok(())
}

/// Validate one canonical LF-terminated projection line and return its parsed object.
pub fn validate_projection_bytes(stdout: &str) -> Result<JsonValue, ProjectionError> {
    if stdout.len() > MAX_PROJECTION_BYTES {
        return Err("projection exceeds bounded output size".to_owned().into());
    }
    if !stdout.ends_with('\n') || stdout.matches('\n').count() != 1 || stdout.contains('\r') {
        return Err("projection must be exactly one LF-terminated line"
            .to_owned()
            .into());
    }
    let line = &stdout[..stdout.len() - 1];
    if line.is_empty() {
        return Err("projection line is empty".to_owned().into());
    }
    let projection = parse_json_reject_duplicates(line)?;
    let fields = object(&projection)
        .ok_or_else(|| "projection fields are not the exact nine-key set".to_owned())?;
    if !has_exact_keys(fields, PROJECTION_KEYS) {
        return Err("projection fields are not the exact nine-key set"
            .to_owned()
            .into());
    }
    if string_field(fields, "schema_version").as_deref() != Some(PROJECTION_SCHEMA_VERSION) {
        return Err(
            "projection schema_version is not execution-resource-plan-projection/v2"
                .to_owned()
                .into(),
        );
    }
    if string_field(fields, "projection").as_deref() != Some("post_tool_use") {
        return Err("projection kind is not post_tool_use".to_owned().into());
    }
    let run_id = string_field(fields, "run_id")
        .filter(|value| is_run_id(value))
        .ok_or_else(|| "projection run_id is not safe".to_owned())?;
    let expected_runtime = format!("reports/agents/{run_id}/runtime");
    if string_field(fields, "plan_path").as_deref()
        != Some(format!("{expected_runtime}/execution_resource_plan.json").as_str())
    {
        return Err("projection plan_path is not canonical".to_owned().into());
    }
    if string_field(fields, "completion_coverage_path").as_deref()
        != Some(format!("{expected_runtime}/completion_coverage.json").as_str())
    {
        return Err("projection completion_coverage_path is not canonical"
            .to_owned()
            .into());
    }
    if !is_integer(field(fields, "exit_code").expect("exact projection fields")) {
        return Err("projection exit_code is not an integer".to_owned().into());
    }
    let plan_fingerprint = string_field(fields, "plan_fingerprint");
    require_sha256(plan_fingerprint.as_deref(), "plan_fingerprint")?;
    validate_admission(field(fields, "admission").expect("exact projection fields"))?;
    validate_error(field(fields, "error").expect("exact projection fields"))?;
    let canonical = canonical_json_ascii_bytes_reject_nonfinite(&projection)?;
    if canonical.as_slice() != line.as_bytes() {
        return Err("projection bytes are not canonical".to_owned().into());
    }
    Ok(projection)
}

/// Construct the official Hook wrapper around previously validated projection bytes.
pub fn projection_context_payload(stdout: &str) -> JsonValue {
    JsonValue::Object(JsonObject(vec![
        (
            key("schema"),
            JsonValue::String(JsonString::from_text(OFFICIAL_HOOK_SCHEMA)),
        ),
        (
            key("hookSpecificOutput"),
            JsonValue::Object(JsonObject(vec![
                (
                    key("hookEventName"),
                    JsonValue::String(JsonString::from_text("PostToolUse")),
                ),
                (
                    key("additionalContext"),
                    JsonValue::String(JsonString::from_text(stdout)),
                ),
            ])),
        ),
    ]))
}

fn validate_admission(value: &JsonValue) -> Result<(), ProjectionError> {
    if matches!(value, JsonValue::Null) {
        return Ok(());
    }
    let fields = object(value).filter(|fields| has_exact_keys(fields, ADMISSION_KEYS));
    let Some(fields) = fields else {
        return Err("admission fields are not exact".to_owned().into());
    };
    require_sha256(
        string_field(fields, "admission_fingerprint").as_deref(),
        "admission_fingerprint",
    )?;
    require_sha256(
        string_field(fields, "runtime_identity_fingerprint").as_deref(),
        "runtime_identity_fingerprint",
    )?;
    if string_field(fields, "guarantee").as_deref() != Some(ADMISSION_GUARANTEE) {
        return Err("admission guarantee is not exact".to_owned().into());
    }
    let namespace = string_field(fields, "namespace_id");
    if !namespace.as_deref().is_some_and(is_namespace) {
        return Err("admission namespace_id is not bounded opaque text"
            .to_owned()
            .into());
    }
    let selected = field(fields, "selected_uuids").expect("exact admission fields");
    let valid_uuids = match selected {
        JsonValue::Array(values) => values
            .0
            .iter()
            .all(|value| string(value).as_deref().is_some_and(is_uuid)),
        _ => false,
    };
    if !valid_uuids {
        return Err("admission selected_uuids are not opaque UUIDs"
            .to_owned()
            .into());
    }
    Ok(())
}

fn validate_error(value: &JsonValue) -> Result<(), ProjectionError> {
    if matches!(value, JsonValue::Null) {
        return Ok(());
    }
    let fields = object(value).filter(|fields| has_exact_keys(fields, &["kind"]));
    let Some(fields) = fields else {
        return Err("error fields are not exact".to_owned().into());
    };
    if !string_field(fields, "kind")
        .as_deref()
        .is_some_and(|kind| PROJECTION_ERROR_KINDS.contains(&kind))
    {
        return Err("error kind is not an exact coarse projection constant"
            .to_owned()
            .into());
    }
    Ok(())
}

fn require_sha256(value: Option<&str>, field: &str) -> Result<(), ProjectionError> {
    if value.is_some_and(is_sha256) {
        Ok(())
    } else {
        Err(format!("{field} is not a lowercase SHA-256 fingerprint").into())
    }
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn is_run_id(value: &str) -> bool {
    let mut bytes = value.bytes();
    bytes
        .next()
        .is_some_and(|byte| byte.is_ascii_alphanumeric())
        && bytes.all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'.' | b'-'))
}

fn is_namespace(value: &str) -> bool {
    let bytes = value.as_bytes();
    (1..=64).contains(&bytes.len())
        && bytes[0].is_ascii_alphanumeric()
        && bytes.iter().all(|byte| {
            byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'.' | b':' | b'[' | b']' | b'-')
        })
}

fn is_uuid(value: &str) -> bool {
    let Some(rest) = value
        .strip_prefix("GPU-")
        .or_else(|| value.strip_prefix("MIG-"))
    else {
        return false;
    };
    !rest.is_empty()
        && rest
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
}

fn is_integer(value: &JsonValue) -> bool {
    matches!(value, JsonValue::Number(JsonNumber::Integer(_)))
}

fn object(value: &JsonValue) -> Option<&JsonObject> {
    match value {
        JsonValue::Object(fields) => Some(fields),
        _ => None,
    }
}

fn field<'a>(fields: &'a JsonObject, name: &str) -> Option<&'a JsonValue> {
    fields
        .0
        .iter()
        .find(|(key, _)| key.equals_text(name))
        .map(|(_, value)| value)
}

fn string(value: &JsonValue) -> Option<String> {
    match value {
        JsonValue::String(value) => value.to_text(),
        _ => None,
    }
}

fn is_string(value: &JsonValue) -> bool {
    matches!(value, JsonValue::String(_))
}

fn string_field(fields: &JsonObject, name: &str) -> Option<String> {
    string(field(fields, name)?)
}

fn has_exact_keys(fields: &JsonObject, expected: &[&str]) -> bool {
    fields.0.len() == expected.len() && expected.iter().all(|key| field(fields, key).is_some())
}

fn key(value: &str) -> JsonString {
    JsonString::from_text(value)
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
