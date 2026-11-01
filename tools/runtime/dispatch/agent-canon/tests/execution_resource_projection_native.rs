// @dependency-start
// contract test
// responsibility Compares native execution-resource projection APIs with captured CPython outcomes.
// upstream implementation ../src/execution_resource_projection.rs owns native projection behavior.
// upstream test ../../../../../tests/fixtures/execution_resource_projection/python_golden.json freezes CPython 3.12.3 outcomes.
// @dependency-end

use agent_canon::execution_resource_projection::{
    projection_context_payload, validate_normalized_input, validate_projection_bytes,
    ProjectionError,
};
use agent_canon::python_json::{
    canonical_json_ascii_bytes, canonical_json_ascii_bytes_reject_nonfinite, parse_json,
    parse_json_reject_duplicates, JsonObject, JsonParseError, JsonString, JsonValue,
};

// Supplemental CPython 3.12.3 captures for source 88a70bddaaacd2f2d5913e7f83dc2756f0ec8fa0
// are inlined here to keep the original 31-case fixture byte-identical.
// Raw boundary capture: execution-projection-old-boundaries-hy915nk9/export/corpus.json; SHA256:
// 74048eb2ee3b62bd41f5993c96123f957e2c787735c66a2ad240301052bd862f
// Raw overflow capture: execution-projection-old-overflow-6abtnr4c/early-export/corpus.json; SHA256:
// 96af170f28416f5435aca4fe184274532c0d0aeb088fa4a282b9d5eccb932a5c

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
                let expected_type =
                    string(field(expected, "error_type").expect("expected error type"));
                assert_eq!(
                    actual_error.error_type(),
                    expected_type.as_str(),
                    "captured error type differs for {name}"
                );
                assert_eq!(
                    actual_error.message(),
                    json_string(field(expected, "error").expect("expected error message")),
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
        JsonParseError::DuplicateKey(JsonString::from_text("value"))
    );
    assert_eq!(
        parse_json_reject_duplicates("NaN")
            .err()
            .expect("strict parser rejects non-finite values"),
        JsonParseError::NonFiniteConstant("non-finite JSON constant: NaN".to_owned())
    );
    let default_nan = parse_json("NaN").expect("default parser continues accepting NaN");
    let canonical_nan =
        canonical_json_ascii_bytes(&default_nan).expect("default canonicalizer allows NaN");
    assert_eq!(canonical_nan.as_slice(), b"NaN".as_slice());
    assert_eq!(
        canonical_json_ascii_bytes_reject_nonfinite(&default_nan)
            .expect_err("strict canonicalizer rejects NaN"),
        "Out of range float values are not JSON compliant: nan"
    );
}

#[test]
fn execution_resource_projection_matches_captured_boundary_cases() {
    assert_projection_error(
        validate_projection_bytes("{\"\\ud800\":1,\"\\ud800\":2}\n"),
        "ProjectionError",
        {
            let mut message = JsonString::from_text("duplicate JSON key: ");
            message.0.push(0xd800);
            message
        },
    );
    assert_projection_error(
        validate_projection_bytes("{\"\\u00e9\":1,\"\\u00e9\":2}\n"),
        "ProjectionError",
        JsonString::from_text("duplicate JSON key: é"),
    );
    assert_projection_error(
        validate_projection_bytes("NaNx\n"),
        "ProjectionError",
        JsonString::from_text("non-finite JSON constant: NaN"),
    );
    assert_projection_error(
        validate_projection_bytes("Infinityx\n"),
        "ProjectionError",
        JsonString::from_text("non-finite JSON constant: Infinity"),
    );
    assert_projection_error(
        validate_projection_bytes("Nan\n"),
        "JSONDecodeError",
        JsonString::from_text("Expecting value: line 1 column 1 (char 0)"),
    );
    assert_projection_error(
        validate_projection_bytes("{\"admission\":\n"),
        "JSONDecodeError",
        JsonString::from_text("Expecting value: line 1 column 14 (char 13)"),
    );

    let normalized_surrogate_inputs = [
        r#"{"hook_event_name":"PostToolUse","schema_version":"agent-canon-post-tool-use-input/v1","tool_input_fingerprint":"827b867e0b5a01dcb19514626d1a3146bf8258df041fe9ad35506a84e1dc0bc5","tool_name":"\ud800","tool_input":{"command":"echo hello"},"tool_response":{"exit_code":0,"stderr":"","stdout":""}}"#,
        r#"{"hook_event_name":"PostToolUse","schema_version":"agent-canon-post-tool-use-input/v1","tool_input_fingerprint":"827b867e0b5a01dcb19514626d1a3146bf8258df041fe9ad35506a84e1dc0bc5","tool_name":"exec_command","tool_input":{"command":"echo hello"},"tool_response":{"exit_code":0,"stderr":"\ud800","stdout":""}}"#,
        r#"{"hook_event_name":"PostToolUse","schema_version":"agent-canon-post-tool-use-input/v1","tool_input_fingerprint":"827b867e0b5a01dcb19514626d1a3146bf8258df041fe9ad35506a84e1dc0bc5","tool_name":"exec_command","tool_input":{"command":"echo hello"},"tool_response":{"exit_code":0,"stderr":"","stdout":"\ud800"}}"#,
    ];
    for input in normalized_surrogate_inputs {
        let payload = parse_json(input).expect("captured normalized input parses");
        assert!(validate_normalized_input(&payload).is_ok());
    }

    for (value, expected_float) in [
        ("NaN", "nan"),
        ("Infinity", "inf"),
        ("-Infinity", "-inf"),
        ("Infinity", "inf"),
        ("-Infinity", "-inf"),
        ("1e400", "inf"),
        ("-1e400", "-inf"),
    ] {
        let input = format!(
            "{{\"hook_event_name\":\"PostToolUse\",\"schema_version\":\"agent-canon-post-tool-use-input/v1\",\"tool_input_fingerprint\":\"827b867e0b5a01dcb19514626d1a3146bf8258df041fe9ad35506a84e1dc0bc5\",\"tool_name\":\"exec_command\",\"tool_input\":{{\"value\":{value}}},\"tool_response\":{{\"exit_code\":0,\"stderr\":\"\",\"stdout\":\"\"}}}}"
        );
        let payload = parse_json(&input).expect("captured non-finite normalized input parses");
        assert_projection_error(
            validate_normalized_input(&payload).map(|()| JsonValue::Null),
            "ValueError",
            JsonString::from_text(&format!(
                "Out of range float values are not JSON compliant: {expected_float}"
            )),
        );
    }
}

fn assert_projection_error<T>(
    result: Result<T, ProjectionError>,
    expected_type: &str,
    expected_message: JsonString,
) {
    let error = result.err().expect("captured case must reject");
    assert_eq!(error.error_type(), expected_type);
    assert_eq!(error.message(), &expected_message);
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

fn json_string(value: &JsonValue) -> &JsonString {
    match value {
        JsonValue::String(value) => value,
        _ => panic!("expected captured JSON string"),
    }
}

fn boolean(value: &JsonValue) -> bool {
    match value {
        JsonValue::Bool(value) => *value,
        _ => panic!("expected captured boolean"),
    }
}
