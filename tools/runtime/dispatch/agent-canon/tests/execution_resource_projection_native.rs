// @dependency-start
// contract test
// responsibility Compares native execution-resource projection APIs with captured CPython outcomes.
// upstream implementation ../src/execution_resource_projection.rs owns native projection behavior.
// upstream test ../../../../../tests/fixtures/execution_resource_projection/python_golden.json freezes CPython 3.12.3 outcomes.
// @dependency-end

use agent_canon::execution_resource_projection::{
    projection_context_payload, validate_normalized_input, validate_projection_bytes,
};
use agent_canon::python_json::{
    canonical_json_ascii_bytes, parse_json, parse_json_reject_duplicates, JsonObject, JsonValue,
};

#[test]
fn execution_resource_projection_matches_captured_cpython_cases() {
    let corpus = parse_json(include_str!(
        "../../../../../tests/fixtures/execution_resource_projection/python_golden.json"
    ))
    .expect("captured projection corpus parses");
    let metadata = object(&corpus).expect("corpus object");
    assert_eq!(
        string(field(metadata, "source").expect("source")),
        "88a70bddaaacd2f2d5913e7f83dc2756f0ec8fa0"
    );
    assert_eq!(string(field(metadata, "python").expect("python")), "3.12.3");
    let cases = array(field(metadata, "cases").expect("cases")).expect("cases array");
    assert_eq!(cases.len(), 31, "all captured cases remain represented");

    for case in cases {
        let case = object(case).expect("case object");
        let name = string(field(case, "name").expect("case name"));
        let api = string(field(case, "api").expect("case API"));
        let input = field(case, "input").expect("case input");
        let expected =
            object(field(case, "output").expect("case output")).expect("expected outcome object");
        let expected_ok = boolean(field(expected, "ok").expect("expected ok"));

        let actual = match api.as_str() {
            "validate_projection_bytes" => validate_projection_bytes(&string(input)),
            "validate_normalized_input" => {
                validate_normalized_input(input).map(|()| JsonValue::Null)
            }
            "projection_context_payload" => Ok(projection_context_payload(&string(input))),
            other => panic!("unknown captured API {other:?} in case {name:?}"),
        };

        assert_eq!(actual.is_ok(), expected_ok, "outcome differs for {name}");
        match actual {
            Ok(actual) => {
                let expected_result = field(expected, "result").expect("expected result");
                assert_eq!(
                    canonical_json_ascii_bytes(&actual).expect("actual canonical JSON"),
                    canonical_json_ascii_bytes(expected_result).expect("expected canonical JSON"),
                    "normalized result differs for {name}"
                );
            }
            Err(actual_error) => {
                assert_eq!(
                    string(field(expected, "error_type").expect("expected error type")),
                    "ProjectionError",
                    "captured error type differs for {name}"
                );
                assert_eq!(
                    actual_error,
                    string(field(expected, "error").expect("expected error message")),
                    "exact error differs for {name}"
                );
            }
        }
    }
}

#[test]
fn duplicate_rejection_is_opt_in_for_the_shared_json_parser() {
    let input = "{\"value\":1,\"value\":2}";
    let default_value = parse_json(input).expect("default parser keeps last-key-wins behavior");
    let canonical_default =
        canonical_json_ascii_bytes(&default_value).expect("canonical default value");
    assert_eq!(canonical_default.as_slice(), br#"{"value":2}"#.as_slice());
    assert_eq!(
        parse_json_reject_duplicates(input)
            .err()
            .expect("strict parser rejects duplicate keys"),
        "duplicate JSON key: value"
    );
    assert_eq!(
        parse_json_reject_duplicates("NaN")
            .err()
            .expect("strict parser rejects non-finite values"),
        "non-finite JSON constant: NaN"
    );
}

fn object(value: &JsonValue) -> Option<&JsonObject> {
    match value {
        JsonValue::Object(fields) => Some(fields),
        _ => None,
    }
}

fn array(value: &JsonValue) -> Option<&[JsonValue]> {
    match value {
        JsonValue::Array(values) => Some(&values.0),
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

fn string(value: &JsonValue) -> String {
    match value {
        JsonValue::String(value) => value.to_text().expect("captured string is Unicode"),
        _ => panic!("expected captured string"),
    }
}

fn boolean(value: &JsonValue) -> bool {
    match value {
        JsonValue::Bool(value) => *value,
        _ => panic!("expected captured boolean"),
    }
}
