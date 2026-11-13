//! Pure tool-selection evidence derived from one supplied payload.
// @dependency-start
// contract implementation
// responsibility Selects privacy-preserving tool, command, key, and input-fingerprint evidence.
// upstream implementation python_json.rs owns Python-compatible JSON values and strict canonical bytes
// upstream implementation python_text.rs owns Python-compatible whitespace
// downstream test ../tests/tool_selection_native.rs compares the frozen CPython selection oracle
// @dependency-end

use crate::python_json::{
    canonical_json_ascii_bytes_reject_nonfinite, JsonArray, JsonObject, JsonString, JsonValue,
};
use crate::python_text::{is_python_whitespace, python_strip};
use sha2::{Digest, Sha256};
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ToolSelection {
    pub tool_name: JsonString,
    pub command_verb: String,
    pub selected_tools: Vec<JsonString>,
    pub tool_input_fingerprint: String,
    pub tool_input_keys: Vec<JsonString>,
    pub tool_input_key_count: usize,
    pub selection_kind: String,
}

impl ToolSelection {
    pub fn should_log(&self) -> bool {
        !self.tool_name.is_empty() || !self.selected_tools.is_empty()
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ToolSelectionError {
    pub error_type: &'static str,
    pub message: String,
}

impl ToolSelectionError {
    fn value_error(message: String) -> Self {
        Self {
            error_type: "ValueError",
            message,
        }
    }
}

impl fmt::Display for ToolSelectionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for ToolSelectionError {}

/// Select tool evidence without scanning or unwrapping command arguments.
pub fn select_tools(payload: &JsonValue) -> Result<ToolSelection, ToolSelectionError> {
    let JsonValue::Object(_) = payload else {
        return Ok(empty_selection());
    };

    let tool_name = object_string(payload, "tool_name")
        .cloned()
        .unwrap_or_default();
    let tool_input_value = object_member(payload, "tool_input");
    let tool_input = tool_input_value.and_then(as_object);

    let mut command = first_string(tool_input_value, &["command", "cmd"]);
    if command.is_none_or(JsonString::is_empty) {
        command = first_string(Some(payload), &["command", "cmd"]);
    }
    let command_verb = command.map(command_verb).unwrap_or_default();

    let mut selected_tools = match object_member(payload, "selected_tools") {
        Some(JsonValue::Array(JsonArray(values))) => values
            .iter()
            .filter_map(|value| match value {
                JsonValue::String(value) if !value.is_empty() => Some(value.clone()),
                _ => None,
            })
            .collect::<Vec<_>>(),
        _ => Vec::new(),
    };
    if selected_tools.is_empty() && !tool_name.is_empty() {
        selected_tools.push(tool_name.clone());
    }

    let mut tool_input_keys = tool_input
        .map(|object| {
            object
                .0
                .iter()
                .map(|(key, _)| key.clone())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    tool_input_keys.sort();
    tool_input_keys.dedup();

    let tool_input_fingerprint = match (tool_input_value, tool_input) {
        (Some(JsonValue::Object(_)), Some(object)) if !object.0.is_empty() => {
            let encoded = canonical_json_ascii_bytes_reject_nonfinite(
                tool_input_value.expect("nonempty object has its JSON value"),
            )
            .map_err(ToolSelectionError::value_error)?;
            format!("{:x}", Sha256::digest(encoded))[..12].to_owned()
        }
        _ => String::new(),
    };

    Ok(ToolSelection {
        selection_kind: if tool_name.is_empty() {
            String::new()
        } else {
            "executed_tool".to_owned()
        },
        tool_input_key_count: tool_input_keys.len(),
        tool_input_keys,
        tool_input_fingerprint,
        selected_tools,
        command_verb,
        tool_name,
    })
}

/// Singular alias retained by the original pure API.
pub fn select_tool(payload: &JsonValue) -> Result<ToolSelection, ToolSelectionError> {
    select_tools(payload)
}

fn empty_selection() -> ToolSelection {
    ToolSelection {
        tool_name: JsonString::default(),
        command_verb: String::new(),
        selected_tools: Vec::new(),
        tool_input_fingerprint: String::new(),
        tool_input_keys: Vec::new(),
        tool_input_key_count: 0,
        selection_kind: String::new(),
    }
}

fn object_member<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(JsonObject(entries)) = value else {
        return None;
    };
    entries
        .iter()
        .rev()
        .find(|(candidate, _)| candidate.equals_text(key))
        .map(|(_, value)| value)
}

fn as_object(value: &JsonValue) -> Option<&JsonObject> {
    match value {
        JsonValue::Object(object) => Some(object),
        _ => None,
    }
}

fn object_string<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonString> {
    match object_member(value, key)? {
        JsonValue::String(value) => Some(value),
        _ => None,
    }
}

fn first_string<'a>(value: Option<&'a JsonValue>, keys: &[&str]) -> Option<&'a JsonString> {
    keys.iter()
        .find_map(|key| value.and_then(|object| object_string(object, key)))
}

fn command_verb(value: &JsonString) -> String {
    if let Some(text) = value.to_text() {
        return command_verb_text(&text);
    }

    let codepoints = &value.0;
    let mut start = 0;
    while codepoints
        .get(start)
        .is_some_and(|codepoint| codepoint_is_python_whitespace(*codepoint))
    {
        start += 1;
    }
    let mut end = start;
    while codepoints
        .get(end)
        .is_some_and(|codepoint| is_ascii_bare_command_character(*codepoint))
    {
        end += 1;
    }
    if end == start
        || codepoints
            .get(end)
            .is_some_and(|codepoint| !codepoint_is_python_whitespace(*codepoint))
    {
        return String::new();
    }
    codepoints[start..end]
        .iter()
        .map(|codepoint| *codepoint as u8)
        .collect::<Vec<_>>()
        .into_iter()
        .map(char::from)
        .collect()
}

fn command_verb_text(value: &str) -> String {
    let value = python_strip(value);
    let bytes = value.as_bytes();
    let mut end = 0;
    while bytes
        .get(end)
        .is_some_and(|byte| is_ascii_bare_command_character(u32::from(*byte)))
    {
        end += 1;
    }
    if end == 0
        || value[end..]
            .chars()
            .next()
            .is_some_and(|character| !is_python_whitespace(character))
    {
        String::new()
    } else {
        value[..end].to_owned()
    }
}

fn codepoint_is_python_whitespace(codepoint: u32) -> bool {
    char::from_u32(codepoint).is_some_and(is_python_whitespace)
}

fn is_ascii_bare_command_character(codepoint: u32) -> bool {
    matches!(codepoint, 0x41..=0x5a | 0x61..=0x7a | 0x30..=0x39 | 0x5f | 0x2e | 0x2d)
}
