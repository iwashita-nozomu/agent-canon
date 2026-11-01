// @dependency-start
// contract test
// responsibility Compares native tool selection with the frozen CPython API oracle.
// upstream implementation ../src/tool_selection.rs owns the pure selection API
// upstream implementation ../src/python_json.rs owns Python-compatible JSON values
// upstream implementation ../src/python_text.rs owns Python-compatible whitespace
// upstream evidence ../../../../../tests/fixtures/tool_selection/python_golden.json freezes actual old API outcomes
// @dependency-end

use agent_canon::python_json::{
    parse_json, JsonArray, JsonNumber, JsonObject, JsonString, JsonValue,
};
use agent_canon::tool_selection::{select_tool, select_tools, ToolSelection};
use sha2::{Digest, Sha256};

const PYTHON_GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/tool_selection/python_golden.json");
const PYTHON_GOLDEN_SHA256: &str =
    "8281aabdecd3dd056554527e3a50b2a136b39a33696eb51f3a12f74707c3b8a7";

#[test]
fn native_tool_selection_matches_frozen_python_api_oracle() {
    assert_eq!(
        format!("{:x}", Sha256::digest(PYTHON_GOLDEN.as_bytes())),
        PYTHON_GOLDEN_SHA256,
        "the actual CPython corpus bytes are immutable"
    );
    let corpus = parse_json(PYTHON_GOLDEN).expect("frozen corpus parses with shared JSON owner");
    let cases = match object_member(&corpus, "cases") {
        Some(JsonValue::Array(JsonArray(values))) => values,
        _ => panic!("frozen corpus has a cases array"),
    };
    assert_eq!(cases.len(), 38, "the old API corpus has 38 cases");

    for case in cases {
        let name = string_value(case, "name")
            .to_text()
            .expect("case name is Unicode text");
        let input = object_member(case, "input").expect("case has an input");
        let expected = object_member(case, "output").expect("case has a result");
        let success = matches!(object_member(expected, "ok"), Some(JsonValue::Bool(true)));

        match select_tools(input) {
            Ok(selection) => {
                assert!(
                    success,
                    "{name}: expected a Python exception, got {selection:?}"
                );
                assert_selection(
                    &selection,
                    object_member(expected, "result").unwrap(),
                    &name,
                );
            }
            Err(_error) => {
                // The active Hook caller catches every exception and discards
                // tool-selection evidence; only rejection is observable here.
                assert!(!success, "{name}: expected tool selection to reject input");
            }
        }
    }
}

#[test]
fn singular_selection_alias_returns_the_same_typed_result() {
    let payload = parse_json(r#"{"tool_name":"Bash","tool_input":{"command":"git status"}}"#)
        .expect("payload parses");
    assert_eq!(
        select_tool(&payload),
        select_tools(&payload),
        "the singular API name remains an exact alias"
    );
}

fn assert_selection(actual: &ToolSelection, expected: &JsonValue, case_name: &str) {
    assert_eq!(
        &actual.tool_name,
        string_value(expected, "tool_name"),
        "{case_name}: tool name"
    );
    assert_eq!(
        actual.command_verb,
        string_value(expected, "command_verb")
            .to_text()
            .expect("command verb is Unicode text"),
        "{case_name}: command verb"
    );
    assert_string_array(
        &actual.selected_tools,
        array_value(expected, "selected_tools"),
        case_name,
        "selected tools",
    );
    assert_eq!(
        actual.tool_input_fingerprint,
        string_value(expected, "tool_input_fingerprint")
            .to_text()
            .expect("fingerprint is ASCII text"),
        "{case_name}: input fingerprint"
    );
    assert_string_array(
        &actual.tool_input_keys,
        array_value(expected, "tool_input_keys"),
        case_name,
        "tool input keys",
    );
    assert_eq!(
        actual.tool_input_key_count,
        integer_value(expected, "tool_input_key_count"),
        "{case_name}: input key count"
    );
    assert_eq!(
        actual.selection_kind,
        string_value(expected, "selection_kind")
            .to_text()
            .expect("selection kind is Unicode text"),
        "{case_name}: selection kind"
    );
    assert_eq!(
        actual.should_log(),
        bool_value(expected, "should_log"),
        "{case_name}: logging predicate"
    );
}

fn assert_string_array(actual: &[JsonString], expected: &JsonArray, case_name: &str, field: &str) {
    assert_eq!(
        actual.len(),
        expected.0.len(),
        "{case_name}: {field} length"
    );
    for (index, (actual, expected)) in actual.iter().zip(&expected.0).enumerate() {
        let JsonValue::String(expected) = expected else {
            panic!("{case_name}: {field}[{index}] is a string in the frozen oracle");
        };
        assert_eq!(actual, expected, "{case_name}: {field}[{index}]");
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

fn string_value<'a>(value: &'a JsonValue, key: &str) -> &'a JsonString {
    match object_member(value, key) {
        Some(JsonValue::String(value)) => value,
        _ => panic!("frozen {key} field is a string"),
    }
}

fn array_value<'a>(value: &'a JsonValue, key: &str) -> &'a JsonArray {
    match object_member(value, key) {
        Some(JsonValue::Array(value)) => value,
        _ => panic!("frozen {key} field is an array"),
    }
}

fn integer_value(value: &JsonValue, key: &str) -> usize {
    let Some(JsonValue::Number(JsonNumber::Integer(value))) = object_member(value, key) else {
        panic!("frozen {key} field is an integer");
    };
    value.parse().expect("frozen key count fits usize")
}

fn bool_value(value: &JsonValue, key: &str) -> bool {
    match object_member(value, key) {
        Some(JsonValue::Bool(value)) => *value,
        _ => panic!("frozen {key} field is a boolean"),
    }
}
