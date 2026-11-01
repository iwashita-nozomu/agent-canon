// @dependency-start
// contract test
// responsibility Checks native prompt redaction and bounded capture against captured CPython 3.12.3 results.
// upstream implementation ../src/prompt_capture.rs owns default redaction and prompt capture.
// upstream test ../../../../../tests/fixtures/prompt_capture/python_golden.json freezes old API inputs and results.
// @dependency-end

use agent_canon::prompt_capture::{
    capture_prompt, capture_prompt_with_limit, redact_sensitive_text, PromptCapture,
};
use agent_canon::python_json::{
    canonical_json_ascii_bytes, parse_json, JsonNumber, JsonObject, JsonString, JsonValue,
};
use sha2::{Digest, Sha256};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/prompt_capture/python_golden.json");
const GOLDEN_SHA256: &str = "def92477121a61b7c7e598101fba45dbffcd1fd0292485677e0f11e985c131df";
const SOURCE_SHA256: &str = "f6637eba22f8515de8cd432d8fcf69c7a6f10f86c8e3697949b74fc0619ae904";

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn object_field<'a>(value: &'a JsonValue, field: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(object) = value else {
        return None;
    };
    object
        .0
        .iter()
        .rev()
        .find_map(|(key, value)| key.equals_text(field).then_some(value))
}

fn array(value: &JsonValue) -> Option<&[JsonValue]> {
    match value {
        JsonValue::Array(array) => Some(&array.0),
        _ => None,
    }
}

fn string(value: &JsonValue) -> Option<&JsonString> {
    match value {
        JsonValue::String(value) => Some(value),
        _ => None,
    }
}

fn text_field<'a>(value: &'a JsonValue, field: &str) -> &'a JsonString {
    string(object_field(value, field).expect("fixture string field exists"))
        .expect("fixture field is a JSON string")
}

fn bool_field(value: &JsonValue, field: &str) -> bool {
    match object_field(value, field).expect("fixture boolean field exists") {
        JsonValue::Bool(value) => *value,
        _ => panic!("fixture field {field} is a boolean"),
    }
}

fn integer_field(value: &JsonValue, field: &str) -> i64 {
    match object_field(value, field).expect("fixture integer field exists") {
        JsonValue::Number(JsonNumber::Integer(value)) => {
            value.parse().expect("fixture integer fits i64")
        }
        _ => panic!("fixture field {field} is an integer"),
    }
}

fn canonical(value: &JsonValue) -> Vec<u8> {
    canonical_json_ascii_bytes(value).expect("fixture value has Python-compatible ASCII JSON")
}

fn capture_value(capture: &PromptCapture) -> JsonValue {
    JsonValue::Object(JsonObject(vec![
        (
            JsonString::from_text("status"),
            JsonValue::String(capture.status.clone()),
        ),
        (
            JsonString::from_text("excerpt_redacted"),
            JsonValue::String(capture.prompt_excerpt_redacted().clone()),
        ),
        (
            JsonString::from_text("char_count"),
            JsonValue::Number(JsonNumber::Integer(capture.prompt_char_count().to_string())),
        ),
        (
            JsonString::from_text("fingerprint"),
            JsonValue::String(JsonString::from_text(&capture.fingerprint)),
        ),
        (
            JsonString::from_text("truncated"),
            JsonValue::Bool(capture.truncated),
        ),
        (
            JsonString::from_text("should_log"),
            JsonValue::Bool(capture.should_log()),
        ),
    ]))
}

#[test]
fn prompt_capture_matches_frozen_cpython_cases_and_rejections() {
    assert_eq!(sha256_hex(GOLDEN.as_bytes()), GOLDEN_SHA256);
    let golden = parse_json(GOLDEN).expect("frozen CPython prompt-capture corpus parses");
    assert_eq!(
        text_field(&golden, "source_hash").to_text().as_deref(),
        Some(SOURCE_SHA256)
    );
    let cases = array(object_field(&golden, "cases").expect("capture cases exist"))
        .expect("capture cases are an array");
    assert_eq!(cases.len(), 154);

    for case in cases {
        let name = text_field(case, "name")
            .to_text()
            .expect("case name is valid text");
        let input = object_field(case, "input").expect("capture input exists");
        let payload = object_field(input, "payload").expect("payload input exists");
        let excerpt_limit = integer_field(input, "excerpt_limit");
        match capture_prompt_with_limit(payload, excerpt_limit) {
            Ok(actual) => {
                assert!(
                    bool_field(case, "accepted"),
                    "unexpected success for {name}"
                );
                let expected = object_field(case, "output").expect("accepted result exists");
                assert_eq!(
                    canonical(&capture_value(&actual)),
                    canonical(expected),
                    "case {name}"
                );
                if excerpt_limit == 600 {
                    assert_eq!(
                        capture_prompt(payload).expect("default 600-codepoint capture succeeds"),
                        actual,
                        "default excerpt limit for {name}"
                    );
                }
            }
            Err(_) => assert!(
                !bool_field(case, "accepted"),
                "unexpected refusal for {name}"
            ),
        }
    }
}

#[test]
fn default_redaction_matches_frozen_cpython_cases_including_surrogates() {
    let golden = parse_json(GOLDEN).expect("frozen CPython prompt-capture corpus parses");
    let redactions = array(object_field(&golden, "redactions").expect("redaction cases exist"))
        .expect("redaction cases are an array");
    assert_eq!(redactions.len(), 15);

    for case in redactions {
        let name = text_field(case, "name")
            .to_text()
            .expect("redaction case name is valid text");
        let input = text_field(case, "input");
        let expected = text_field(case, "output");
        let actual = JsonValue::String(redact_sensitive_text(input));
        assert_eq!(
            canonical(&actual),
            canonical(&JsonValue::String(expected.clone())),
            "redaction case {name}"
        );
    }
}
