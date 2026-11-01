// @dependency-start
// contract implementation
// responsibility Captures bounded, redacted prompt evidence without side effects.
// upstream implementation ../../../../../tools/agent/orchestration/prompt_capture.py owns the current pure API contract.
// upstream implementation ./hook_safety.rs owns shared Python Unicode 15 word boundaries for secret patterns.
// upstream implementation ./python_json.rs owns Python-compatible strings and JSON values.
// downstream implementation ../tests/prompt_capture_native.rs checks frozen CPython 3.12.3 results.
// downstream test ../../../../../tests/fixtures/prompt_capture/python_golden.json freezes old capture and redaction inputs/results.
// @dependency-end
//! Pure prompt redaction and bounded prompt evidence capture.

use crate::hook_safety::PYTHON_15_WORD_CHAR;
use crate::python_json::{JsonObject, JsonString, JsonValue};
use regex::Regex;
use sha2::{Digest, Sha256};
use std::sync::LazyLock;

pub const DEFAULT_EXCERPT_LIMIT: usize = 600;
const REDACTED_SECRET: &str = "[REDACTED_SECRET]";

static SECRET_BODY_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"-----BEGIN (RSA |DSA |EC |OPENSSH |)PRIVATE KEY-----|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{32,}",
    )
    .expect("static prompt redaction body pattern is valid")
});
static PYTHON_15_WORD_CHAR_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(PYTHON_15_WORD_CHAR).expect("shared Python Unicode 15 word class is valid")
});

/// One bounded, redacted prompt observation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PromptCapture {
    pub status: JsonString,
    pub excerpt_redacted: JsonString,
    pub char_count: usize,
    pub fingerprint: String,
    pub truncated: bool,
}

impl PromptCapture {
    pub fn should_log(&self) -> bool {
        self.status.equals_text("present")
    }

    pub fn prompt_excerpt_redacted(&self) -> &JsonString {
        &self.excerpt_redacted
    }

    pub fn prompt_char_count(&self) -> usize {
        self.char_count
    }
}

/// Native refusal reasons for the selected capture contract.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PromptCaptureError {
    NegativeExcerptLimit,
    PromptNotUtf8,
}

/// Redact the fixed default secret patterns without encoding the input string.
/// Lone surrogate code points are retained and act as non-word boundaries.
pub fn redact_sensitive_text(text: &JsonString) -> JsonString {
    let mut output = Vec::with_capacity(text.0.len());
    let mut valid_run = String::new();

    for &codepoint in &text.0 {
        if let Some(character) = char::from_u32(codepoint) {
            valid_run.push(character);
        } else {
            append_redacted_run(&valid_run, &mut output);
            valid_run.clear();
            output.push(codepoint);
        }
    }
    append_redacted_run(&valid_run, &mut output);
    JsonString(output)
}

fn append_redacted_run(value: &str, output: &mut Vec<u32>) {
    let mut output_offset = 0;
    let mut search_offset = 0;

    while let Some(candidate) = SECRET_BODY_RE.find_at(value, search_offset) {
        let body = candidate.as_str();
        let body_end = if body.starts_with("-----BEGIN ") {
            candidate.end()
        } else {
            if !has_python_15_left_boundary(value, candidate.start()) {
                search_offset = candidate.start() + 1;
                continue;
            }
            let Some(end) = secret_body_end(value, candidate.start(), candidate.end(), body) else {
                search_offset = candidate.start() + 1;
                continue;
            };
            end
        };

        output.extend(
            value[output_offset..candidate.start()]
                .chars()
                .map(u32::from),
        );
        output.extend(REDACTED_SECRET.chars().map(u32::from));
        output_offset = body_end;
        // Python's \b is zero-width. Resume at the body end so this same
        // boundary can establish the next adjacent secret match.
        search_offset = body_end;
    }

    output.extend(value[output_offset..].chars().map(u32::from));
}

fn secret_body_end(value: &str, start: usize, greedy_end: usize, body: &str) -> Option<usize> {
    if body.starts_with("sk-") {
        let minimum_end = start + "sk-".len() + 32;
        let mut end = greedy_end;
        while end >= minimum_end {
            if has_python_15_right_boundary(value, end) {
                return Some(end);
            }
            // The OpenAI-style body alphabet is ASCII, so each regex
            // backtracking step moves one byte and one code point.
            end -= 1;
        }
        None
    } else if has_python_15_right_boundary(value, greedy_end) {
        Some(greedy_end)
    } else {
        None
    }
}

fn has_python_15_left_boundary(value: &str, index: usize) -> bool {
    let previous = value[..index].chars().next_back();
    let first = value[index..].chars().next();
    is_python_15_word_char(previous) != is_python_15_word_char(first)
}

fn has_python_15_right_boundary(value: &str, index: usize) -> bool {
    let previous = value[..index].chars().next_back();
    let next = value[index..].chars().next();
    is_python_15_word_char(previous) != is_python_15_word_char(next)
}

fn is_python_15_word_char(character: Option<char>) -> bool {
    let Some(character) = character else {
        return false;
    };
    let mut buffer = [0; 4];
    PYTHON_15_WORD_CHAR_RE.is_match(character.encode_utf8(&mut buffer))
}

/// Capture a JSON prompt using the standard 600-codepoint excerpt bound.
pub fn capture_prompt(payload: &JsonValue) -> Result<PromptCapture, PromptCaptureError> {
    capture_prompt_with_limit(payload, DEFAULT_EXCERPT_LIMIT as i64)
}

/// Capture a JSON prompt with an explicit nonnegative codepoint limit.
pub fn capture_prompt_with_limit(
    payload: &JsonValue,
    excerpt_limit: i64,
) -> Result<PromptCapture, PromptCaptureError> {
    if excerpt_limit < 0 {
        return Err(PromptCaptureError::NegativeExcerptLimit);
    }

    let Some(prompt) = object_prompt(payload).filter(|prompt| !prompt.is_empty()) else {
        return Ok(missing_capture());
    };

    let redacted = redact_sensitive_text(prompt);
    let limit = usize::try_from(excerpt_limit).unwrap_or(usize::MAX);
    let excerpt_end = redacted.0.len().min(limit);
    let excerpt_redacted = JsonString(redacted.0[..excerpt_end].to_vec());
    let prompt_text = prompt.to_text().ok_or(PromptCaptureError::PromptNotUtf8)?;
    let fingerprint = Sha256::digest(prompt_text.as_bytes())[..8]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();

    Ok(PromptCapture {
        status: JsonString::from_text("present"),
        excerpt_redacted,
        char_count: prompt.0.len(),
        fingerprint,
        truncated: redacted.0.len() > limit,
    })
}

fn object_prompt(payload: &JsonValue) -> Option<&JsonString> {
    let JsonValue::Object(JsonObject(fields)) = payload else {
        return None;
    };
    let prompt = fields
        .iter()
        .rev()
        .find_map(|(key, value)| key.equals_text("prompt").then_some(value))?;
    match prompt {
        JsonValue::String(prompt) => Some(prompt),
        _ => None,
    }
}

fn missing_capture() -> PromptCapture {
    PromptCapture {
        status: JsonString::from_text("missing"),
        excerpt_redacted: JsonString::default(),
        char_count: 0,
        fingerprint: String::new(),
        truncated: false,
    }
}
