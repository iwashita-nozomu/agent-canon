// @dependency-start
// contract test
// responsibility Calls the native subagent-selection and receipt APIs from frozen Python inputs and compares old outputs.
// upstream implementation ../src/subagent_selection.rs owns the pure native APIs.
// upstream test ../../../../../tests/fixtures/subagent_selection/python_golden.json freezes CPython 3.12.3 outputs.
// @dependency-end

use agent_canon::python_json::{
    canonical_json_ascii_bytes, parse_json, JsonArray, JsonObject, JsonString, JsonValue,
};
use agent_canon::subagent_selection::{build_coordination_receipt, select_subagents};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/subagent_selection/python_golden.json");

fn field<'a>(value: &'a JsonValue, key: &str) -> &'a JsonValue {
    let JsonValue::Object(object) = value else {
        panic!("frozen subagent-selection value is an object");
    };
    object
        .0
        .iter()
        .rev()
        .find(|(candidate, _)| candidate.equals_text(key))
        .map(|(_, value)| value)
        .unwrap_or_else(|| panic!("frozen subagent-selection field is present: {key}"))
}

fn text(value: &JsonValue) -> &JsonString {
    let JsonValue::String(value) = value else {
        panic!("frozen subagent-selection value is a string");
    };
    value
}

fn object(fields: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(JsonObject(
        fields
            .into_iter()
            .map(|(key, value)| (JsonString::from_text(key), value))
            .collect(),
    ))
}

fn native_output(case: &JsonValue) -> JsonValue {
    let payload = field(case, "payload");
    let hook_event_name = field(case, "hook_event_name");
    match select_subagents(payload, None) {
        Ok(selection) => {
            let mut result = selection.to_json_value();
            if !matches!(hook_event_name, JsonValue::Null) {
                let receipt =
                    build_coordination_receipt(payload, Some(&selection), hook_event_name)
                        .unwrap_or(JsonValue::Null);
                let JsonValue::Object(result) = &mut result else {
                    panic!("native selection serializes as an object");
                };
                result
                    .0
                    .push((JsonString::from_text("coordination_receipt"), receipt));
            }
            object(vec![("ok", JsonValue::Bool(true)), ("result", result)])
        }
        Err(error) => object(vec![
            ("ok", JsonValue::Bool(false)),
            (
                "error_type",
                JsonValue::String(JsonString::from_text(error.error_type)),
            ),
            (
                "error",
                JsonValue::String(JsonString::from_text(&error.message)),
            ),
        ]),
    }
}

#[test]
fn subagent_selection_and_receipt_match_all_frozen_cpython_cases() {
    let golden = parse_json(GOLDEN).expect("frozen CPython subagent corpus parses");
    let source_hash = text(field(&golden, "source_hash"))
        .to_text()
        .expect("frozen source hash is valid Unicode");
    assert_eq!(
        source_hash,
        "d150068d613d119d7dc305cdf0329c6367b6d13d604d16e7425c49dec0136bd9"
    );
    let cases = field(&golden, "cases");
    let JsonValue::Array(JsonArray(cases)) = cases else {
        panic!("frozen subagent cases are an array");
    };
    assert_eq!(cases.len(), 58);

    for case in cases {
        let case_name = text(field(case, "name"))
            .to_text()
            .expect("frozen case name is valid Unicode");
        let expected = field(case, "output");
        let actual = native_output(case);
        assert_eq!(
            canonical_json_ascii_bytes(&actual).expect("native result serializes"),
            canonical_json_ascii_bytes(expected).expect("frozen old result serializes"),
            "subagent selection case {case_name}"
        );
    }
}
