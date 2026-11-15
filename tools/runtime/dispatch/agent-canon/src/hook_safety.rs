// @dependency-start
// contract implementation
// responsibility Owns prompt secret matching and redacted secret payloads.
// upstream design ../../../../../documents/codex/codex-configuration-reference.md prompt safety behavior
// downstream test ../tests/hook_safety_native.rs retained secret and prompt parsing oracles
// @dependency-end
//! Pure prompt safety used by the native hook dispatcher.

use crate::python_json::{JsonString, JsonValue};
use regex::Regex;
use serde_json::{json, Value};
use std::sync::LazyLock;

pub(crate) const PYTHON_15_WORD_CHAR: &str = r"[\p{Age:15.0}&&[\pL\pN_]]";
pub(crate) const PYTHON_15_NONWORD_CHAR: &str = r"[^[\p{Age:15.0}&&[\pL\pN_]]]";
pub(crate) const PYTHON_15_START_BOUNDARY: &str = r"(?:\A|[^[\p{Age:15.0}&&[\pL\pN_]]])";
pub(crate) const PYTHON_15_END_BOUNDARY: &str = r"(?:\z|[^[\p{Age:15.0}&&[\pL\pN_]]])";

static SECRET_PATTERNS: LazyLock<[(Regex, &'static str); 4]> = LazyLock::new(|| {
    [
        (
            Regex::new(r"-----BEGIN (RSA |DSA |EC |OPENSSH |)PRIVATE KEY-----")
                .expect("static private-key pattern is valid"),
            "private key block",
        ),
        (
            Regex::new(&format!(
                r"{PYTHON_15_START_BOUNDARY}AKIA[0-9A-Z]{{16}}{PYTHON_15_END_BOUNDARY}"
            ))
            .expect("static AWS key pattern is valid"),
            "AWS access key id",
        ),
        (
            Regex::new(&format!(
                r"{PYTHON_15_START_BOUNDARY}gh[pousr]_[A-Za-z0-9_]{{30,}}{PYTHON_15_END_BOUNDARY}"
            ))
            .expect("static GitHub token pattern is valid"),
            "GitHub token",
        ),
        (
            Regex::new(&format!(
                r"{PYTHON_15_START_BOUNDARY}sk-(?:[A-Za-z0-9_-]{{31,}}[A-Za-z0-9_](?:\z|{PYTHON_15_NONWORD_CHAR})|[A-Za-z0-9_-]{{31,}}-{PYTHON_15_WORD_CHAR})"
            ))
            .expect("static API key pattern is valid"),
            "OpenAI-style API key",
        ),
    ]
});

/// Return the first high-confidence secret class in prompt text.
pub fn secret_kind(prompt: &str) -> Option<&'static str> {
    SECRET_PATTERNS
        .iter()
        .find_map(|(pattern, kind)| pattern.is_match(prompt).then_some(*kind))
}

/// Return the first old secret class from a Python-compatible string.
/// Lone surrogates divide valid text runs and behave as non-word boundaries.
pub fn secret_kind_json(prompt: &JsonString) -> Option<&'static str> {
    for (pattern, kind) in SECRET_PATTERNS.iter() {
        let mut valid_run = String::new();
        for &codepoint in &prompt.0 {
            if let Some(character) = char::from_u32(codepoint) {
                valid_run.push(character);
            } else {
                if pattern.is_match(&valid_run) {
                    return Some(*kind);
                }
                valid_run.clear();
            }
        }
        if pattern.is_match(&valid_run) {
            return Some(*kind);
        }
    }
    None
}

/// Return a block payload without retaining the matched prompt.
pub fn secret_block_payload(secret: &str) -> Value {
    json!({
        "decision": "block",
        "reason": format!(
            "Prompt appears to include a {secret}. Remove the secret or replace it with a redacted placeholder."
        ),
        "next_action": "remove_secret_or_use_redacted_placeholder_then_retry",
        "remediation": [
            "Remove the secret material from the prompt.",
            format!(
                "Replace examples with redacted placeholders such as {}[REDACTED_TOKEN]{}.",
                char::from(96_u8),
                char::from(96_u8)
            ),
            "Rotate the secret if it was pasted into the session by mistake.",
        ],
    })
}

/// Return the prompt when the value is a string.
pub fn payload_prompt(payload: &Value) -> &str {
    payload.get("prompt").and_then(Value::as_str).unwrap_or("")
}

/// Return the prompt from the shared Python-compatible JSON value.
pub fn payload_prompt_json(payload: &JsonValue) -> JsonString {
    json_object_string(payload, "prompt")
        .cloned()
        .unwrap_or_default()
}

fn json_object_member<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonValue> {
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

fn json_object_string<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonString> {
    match json_object_member(value, key)? {
        JsonValue::String(value) => Some(value),
        _ => None,
    }
}
