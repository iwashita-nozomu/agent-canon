// @dependency-start
// contract implementation
// responsibility Owns pure subagent invocation observation and honest collaboration receipts.
// upstream implementation ../../../../../tools/agent/orchestration/subagent_selection.py owns the current Python API contract.
// upstream implementation ./python_json.rs owns Python-compatible strings and JSON values.
// upstream implementation ./agent_search.rs reuses ICU CaseMapper::fold_string for Unicode 15 case folding.
// downstream implementation ../tests/subagent_selection_native.rs checks the frozen CPython 3.12.3 API corpus.
// downstream test ../../../../../tests/fixtures/subagent_selection/python_golden.json freezes old API inputs and outputs.
// @dependency-end
//! Pure observation of subagent selection and collaboration-result receipts.

use crate::python_json::{JsonArray, JsonNumber, JsonObject, JsonString, JsonValue};
use icu_casemap::CaseMapper;
use sha2::{Digest, Sha256};

/// Collaboration operations for which the old owner emits a coordination receipt.
pub const COLLABORATION_OPERATIONS: [&str; 4] = [
    "send_message",
    "followup_task",
    "list_agents",
    "interrupt_agent",
];

/// Schema label for an honest collaboration-result receipt.
pub const COORDINATION_RECEIPT_SCHEMA: &str = "agent-canon.coordination-receipt.v1";

const ALIASED_OPERATIONS: [&str; 9] = [
    "send_message",
    "followup_task",
    "list_agents",
    "interrupt_agent",
    "spawn",
    "send_input",
    "wait",
    "close",
    "resume",
];

/// The normalized, observational selection consumed by hook event assembly.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct SubagentSelection {
    pub invoked: bool,
    pub action: JsonString,
    pub tool_name: JsonString,
    pub agent_type: JsonString,
    pub target: JsonString,
    pub targets: Vec<JsonString>,
    pub model: JsonString,
    pub reasoning_effort: JsonString,
    pub fork_context: bool,
    pub prompt_fingerprint: String,
    pub prompt_char_count: usize,
    pub item_count: usize,
}

impl SubagentSelection {
    /// Match the old dataclass observation method.
    pub const fn should_log(&self) -> bool {
        self.invoked
    }

    /// Materialize the old dataclass fields and the derived should-log value.
    pub fn to_json_value(&self) -> JsonValue {
        JsonValue::Object(JsonObject(vec![
            (
                JsonString::from_text("invoked"),
                JsonValue::Bool(self.invoked),
            ),
            (
                JsonString::from_text("action"),
                JsonValue::String(self.action.clone()),
            ),
            (
                JsonString::from_text("tool_name"),
                JsonValue::String(self.tool_name.clone()),
            ),
            (
                JsonString::from_text("agent_type"),
                JsonValue::String(self.agent_type.clone()),
            ),
            (
                JsonString::from_text("target"),
                JsonValue::String(self.target.clone()),
            ),
            (
                JsonString::from_text("targets"),
                JsonValue::Array(JsonArray(
                    self.targets
                        .iter()
                        .cloned()
                        .map(JsonValue::String)
                        .collect(),
                )),
            ),
            (
                JsonString::from_text("model"),
                JsonValue::String(self.model.clone()),
            ),
            (
                JsonString::from_text("reasoning_effort"),
                JsonValue::String(self.reasoning_effort.clone()),
            ),
            (
                JsonString::from_text("fork_context"),
                JsonValue::Bool(self.fork_context),
            ),
            (
                JsonString::from_text("prompt_fingerprint"),
                JsonValue::String(JsonString::from_text(&self.prompt_fingerprint)),
            ),
            (
                JsonString::from_text("prompt_char_count"),
                JsonValue::Number(JsonNumber::Integer(self.prompt_char_count.to_string())),
            ),
            (
                JsonString::from_text("item_count"),
                JsonValue::Number(JsonNumber::Integer(self.item_count.to_string())),
            ),
            (
                JsonString::from_text("should_log"),
                JsonValue::Bool(self.should_log()),
            ),
        ]))
    }
}

/// The Python-visible error produced when a selected prompt cannot be UTF-8 encoded.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SubagentSelectionError {
    pub error_type: &'static str,
    pub message: String,
}

fn object_field<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(object) = value else {
        return None;
    };
    object
        .0
        .iter()
        .rev()
        .find(|(candidate, _)| candidate.equals_text(key))
        .map(|(_, value)| value)
}

fn string_field(payload: &JsonValue, keys: &[&str]) -> JsonString {
    for key in keys {
        if let Some(JsonValue::String(value)) = object_field(payload, key) {
            if !value.is_empty() {
                return value.clone();
            }
        }
    }
    JsonString::default()
}

fn python_truthy(value: Option<&JsonValue>) -> bool {
    match value {
        None | Some(JsonValue::Null) => false,
        Some(JsonValue::Bool(value)) => *value,
        Some(JsonValue::Number(JsonNumber::Integer(value))) => value != "0" && value != "-0",
        Some(JsonValue::Number(JsonNumber::Float(value))) => *value != 0.0,
        Some(JsonValue::String(value)) => !value.is_empty(),
        Some(JsonValue::Array(value)) => !value.0.is_empty(),
        Some(JsonValue::Object(value)) => !value.0.is_empty(),
    }
}

fn normalize_operation(tool_name: &JsonString, action: JsonString) -> JsonString {
    if ALIASED_OPERATIONS
        .iter()
        .any(|operation| action.equals_text(*operation))
    {
        return action;
    }
    if let Some(tool_name) = tool_name.to_text() {
        let folded = CaseMapper::new().fold_string(&tool_name);
        for operation in ALIASED_OPERATIONS {
            if folded.as_str() == operation
                || folded == format!("tools.{operation}")
                || folded == format!("tools.collaboration.{operation}")
                || folded == format!("functions.{operation}")
                || folded == format!("functions.collaboration.{operation}")
            {
                return JsonString::from_text(operation);
            }
        }
    }
    if tool_name.equals_text("Task") || tool_name.equals_text("spawn_agent") {
        return JsonString::from_text("spawn");
    }
    if tool_name.equals_text("wait_agent") {
        return JsonString::from_text("wait");
    }
    if tool_name.equals_text("close_agent") {
        return JsonString::from_text("close");
    }
    if tool_name.equals_text("resume_agent") {
        return JsonString::from_text("resume");
    }
    action
}

fn prompt_encode_error(prompt: &JsonString) -> SubagentSelectionError {
    let position = prompt
        .0
        .iter()
        .position(|codepoint| (0xd800..=0xdfff).contains(codepoint))
        .unwrap_or(0);
    let codepoint = prompt.0[position];
    let message = format!(
        "'utf-8' codec can't encode character '\\u{codepoint:04x}' in position {position}: surrogates not allowed"
    );
    SubagentSelectionError {
        error_type: "UnicodeEncodeError",
        message,
    }
}

fn prompt_fingerprint(prompt: &JsonString) -> Result<String, SubagentSelectionError> {
    if prompt.is_empty() {
        return Ok(String::new());
    }
    let Some(text) = prompt.to_text() else {
        return Err(prompt_encode_error(prompt));
    };
    let digest = Sha256::digest(text.as_bytes());
    Ok(digest[..8]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

/// Preserve the old pure observation behavior; workflow context remains unused.
pub fn select_subagents(
    payload: &JsonValue,
    _workflow_context: Option<&JsonValue>,
) -> Result<SubagentSelection, SubagentSelectionError> {
    if !matches!(payload, JsonValue::Object(_)) {
        return Ok(SubagentSelection::default());
    }
    let tool_name = string_field(payload, &["tool_name", "subagent_tool_name"]);
    let action = normalize_operation(
        &tool_name,
        string_field(payload, &["subagent_event_kind", "action", "event"]),
    );
    let raw_targets =
        object_field(payload, "subagent_targets").or_else(|| object_field(payload, "targets"));
    let targets = match raw_targets {
        Some(JsonValue::Array(values)) => values
            .0
            .iter()
            .filter_map(|value| match value {
                JsonValue::String(value) if !value.is_empty() => Some(value.clone()),
                _ => None,
            })
            .collect::<Vec<_>>(),
        _ => Vec::new(),
    };
    let target = string_field(payload, &["subagent_target", "target"]);
    let prompt = string_field(payload, &["subagent_prompt", "prompt"]);
    let invoked = !action.is_empty()
        || !targets.is_empty()
        || !target.is_empty()
        || python_truthy(object_field(payload, "subagent_invoked"));
    let fork_context = python_truthy(
        object_field(payload, "subagent_fork_context")
            .or_else(|| object_field(payload, "fork_context")),
    );
    let prompt_char_count = prompt.0.len();
    let prompt_fingerprint = prompt_fingerprint(&prompt)?;

    Ok(SubagentSelection {
        invoked,
        action,
        tool_name,
        agent_type: string_field(payload, &["subagent_agent_type", "agent_type"]),
        target,
        item_count: targets.len(),
        targets,
        model: string_field(payload, &["subagent_model", "model"]),
        reasoning_effort: string_field(payload, &["subagent_reasoning_effort", "reasoning_effort"]),
        fork_context,
        prompt_fingerprint,
        prompt_char_count,
    })
}

fn object_has_exact_keys(value: &JsonValue, expected: &[&str]) -> bool {
    let JsonValue::Object(object) = value else {
        return false;
    };
    expected.iter().all(|key| {
        object
            .0
            .iter()
            .any(|(candidate, _)| candidate.equals_text(key))
    }) && object
        .0
        .iter()
        .all(|(candidate, _)| expected.iter().any(|key| candidate.equals_text(key)))
}

fn exact_post_tool_payload(payload: &JsonValue) -> bool {
    object_has_exact_keys(
        payload,
        &["hookEventName", "tool_name", "tool_input", "tool_response"],
    ) && matches!(
        object_field(payload, "hookEventName"),
        Some(JsonValue::String(event)) if event.equals_text("PostToolUse")
    ) && matches!(
        object_field(payload, "tool_name"),
        Some(JsonValue::String(_))
    ) && matches!(
        object_field(payload, "tool_input"),
        Some(JsonValue::Object(_))
    )
}

fn result_exit_status(payload: &JsonValue) -> Option<bool> {
    if !exact_post_tool_payload(payload) {
        return None;
    }
    let response = object_field(payload, "tool_response")?;
    if !object_has_exact_keys(response, &["exit_code", "stderr", "stdout"])
        || !matches!(object_field(response, "stderr"), Some(JsonValue::String(_)))
        || !matches!(object_field(response, "stdout"), Some(JsonValue::String(_)))
    {
        return None;
    }
    match object_field(response, "exit_code") {
        Some(JsonValue::Number(JsonNumber::Integer(value))) => Some(value == "0"),
        _ => None,
    }
}

/// Build one honest receipt from the exact PostToolUse payload and real tool result.
pub fn build_coordination_receipt(
    payload: &JsonValue,
    selection: Option<&SubagentSelection>,
    hook_event_name: &JsonValue,
) -> Option<JsonValue> {
    let JsonValue::String(event_name) = hook_event_name else {
        return None;
    };
    let selection = selection?;
    if !event_name.equals_text("PostToolUse")
        || !COLLABORATION_OPERATIONS
            .iter()
            .any(|operation| selection.action.equals_text(*operation))
    {
        return None;
    }
    let status = match result_exit_status(payload) {
        Some(true) => "succeeded",
        Some(false) => "failed",
        None => "invalid_tool_result",
    };
    Some(JsonValue::Object(JsonObject(vec![
        (
            JsonString::from_text("schema"),
            JsonValue::String(JsonString::from_text(COORDINATION_RECEIPT_SCHEMA)),
        ),
        (
            JsonString::from_text("operation"),
            JsonValue::String(selection.action.clone()),
        ),
        (
            JsonString::from_text("capability_status"),
            JsonValue::String(JsonString::from_text("unverified")),
        ),
        (
            JsonString::from_text("effective_operations"),
            JsonValue::Array(JsonArray(Vec::new())),
        ),
        (
            JsonString::from_text("evidence_ref"),
            JsonValue::String(JsonString::default()),
        ),
        (
            JsonString::from_text("transport"),
            JsonValue::String(JsonString::from_text("durable_artifact")),
        ),
        (JsonString::from_text("direct_peer"), JsonValue::Bool(false)),
        (
            JsonString::from_text("status"),
            JsonValue::String(JsonString::from_text(status)),
        ),
    ])))
}
