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
    parse_json_reject_duplicates, JsonObject, JsonValue,
};

// Supplemental CPython 3.12.3 captures for source 88a70bddaaacd2f2d5913e7f83dc2756f0ec8fa0
// are inlined here to keep the original 31-case fixture byte-identical.
// Raw boundary capture: execution-projection-old-boundaries-hy915nk9/export/corpus.json; SHA256:
// 74048eb2ee3b62bd41f5993c96123f957e2c787735c66a2ad240301052bd862f
// Raw overflow capture: execution-projection-old-overflow-6abtnr4c/early-export/corpus.json; SHA256:
// 96af170f28416f5435aca4fe184274532c0d0aeb088fa4a282b9d5eccb932a5c
// Raw syntax capture: execution-projection-old-syntax-apbns7b9/early-export/corpus.json; SHA256:
// 2a4155497b12c771ddc1421f7c9126565a54b03e5e33af31f9522f09b130c647
// Raw number-syntax capture: execution-projection-old-number-syntax-zokbbdpb/early-export/corpus.json; SHA256:
// 5f5bca190e8edeb8320b3668755f83e8439b6a39b02b67bd47f0efcfc2675f4b

#[test]
fn execution_resource_projection_preserves_captured_acceptance_and_success_values() {
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

        match actual {
            Ok(actual) => {
                assert!(expected_ok, "captured case unexpectedly succeeds: {name}");
                let expected_result = field(expected, "result").expect("expected result");
                assert_eq!(
                    canonical_json_ascii_bytes(&actual).expect("actual canonical JSON"),
                    canonical_json_ascii_bytes(expected_result).expect("expected canonical JSON"),
                    "normalized result differs for {name}"
                );
            }
            Err(_) => {
                assert!(!expected_ok, "captured case unexpectedly succeeds: {name}");
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
    assert!(parse_json_reject_duplicates(input).is_err());
    assert!(parse_json_reject_duplicates("NaN").is_err());
    let default_nan = parse_json("NaN").expect("default parser continues accepting NaN");
    let canonical_nan =
        canonical_json_ascii_bytes(&default_nan).expect("default canonicalizer allows NaN");
    assert_eq!(canonical_nan.as_slice(), b"NaN".as_slice());
    assert!(canonical_json_ascii_bytes_reject_nonfinite(&default_nan).is_err());
    assert!(parse_json("1.").is_err());
    assert!(parse_json("1e").is_err());
    assert!(parse_json("-").is_err());
}

#[test]
fn execution_resource_projection_preserves_captured_boundary_rejections() {
    let syntax_inputs = [
        "{\"x\"1}\n",
        "{\"x\":1 \"y\":2}\n",
        "[1 2]\n",
        "{}x\n",
        "1.\n",
        "1e\n",
        "1e+\n",
        "-\n",
        "-.\n",
        "01\n",
        "-01\n",
        "{\"x\":1.}\n",
        "{\"x\":1e}\n",
        "[1e]\n",
        "[01]\n",
        "\"abc\n",
        concat!(r#""\q""#, "\n"),
        concat!(r#""\u12x4""#, "\n"),
        "\"a\tb\"\n",
        "{\"x\":}\n",
        "[}\n",
        " \n",
        "\u{feff}{}\n",
        "{\"é\"1}\n",
        "{\"x\":1,}\n",
        "[1,]\n",
    ];
    for input in syntax_inputs {
        assert_projection_rejected(validate_projection_bytes(input), input);
    }

    for input in [
        "{\"\\ud800\":1,\"\\ud800\":2}\n",
        "{\"\\u00e9\":1,\"\\u00e9\":2}\n",
        "NaNx\n",
        "Infinityx\n",
        "Nan\n",
        "{\"admission\":\n",
    ] {
        assert_projection_rejected(validate_projection_bytes(input), input);
    }

    let normalized_surrogate_inputs = [
        r#"{"hook_event_name":"PostToolUse","schema_version":"agent-canon-post-tool-use-input/v1","tool_input_fingerprint":"827b867e0b5a01dcb19514626d1a3146bf8258df041fe9ad35506a84e1dc0bc5","tool_name":"\ud800","tool_input":{"command":"echo hello"},"tool_response":{"exit_code":0,"stderr":"","stdout":""}}"#,
        r#"{"hook_event_name":"PostToolUse","schema_version":"agent-canon-post-tool-use-input/v1","tool_input_fingerprint":"827b867e0b5a01dcb19514626d1a3146bf8258df041fe9ad35506a84e1dc0bc5","tool_name":"exec_command","tool_input":{"command":"echo hello"},"tool_response":{"exit_code":0,"stderr":"\ud800","stdout":""}}"#,
        r#"{"hook_event_name":"PostToolUse","schema_version":"agent-canon-post-tool-use-input/v1","tool_input_fingerprint":"827b867e0b5a01dcb19514626d1a3146bf8258df041fe9ad35506a84e1dc0bc5","tool_name":"exec_command","tool_input":{"command":"echo hello"},"tool_response":{"exit_code":0,"stderr":"","stdout":"\ud800"}}"#,
    ];
    for input in normalized_surrogate_inputs {
        let payload = parse_json(input).expect("captured normalized input parses");
        assert!(validate_normalized_input(&payload).is_ok());
    }

    for value in [
        "NaN",
        "Infinity",
        "-Infinity",
        "Infinity",
        "-Infinity",
        "1e400",
        "-1e400",
    ] {
        let input = format!(
            "{{\"hook_event_name\":\"PostToolUse\",\"schema_version\":\"agent-canon-post-tool-use-input/v1\",\"tool_input_fingerprint\":\"827b867e0b5a01dcb19514626d1a3146bf8258df041fe9ad35506a84e1dc0bc5\",\"tool_name\":\"exec_command\",\"tool_input\":{{\"value\":{value}}},\"tool_response\":{{\"exit_code\":0,\"stderr\":\"\",\"stdout\":\"\"}}}}"
        );
        let payload = parse_json(&input).expect("captured non-finite normalized input parses");
        assert_projection_rejected(
            validate_normalized_input(&payload).map(|()| JsonValue::Null),
            &input,
        );
    }
}

fn assert_projection_rejected<T>(result: Result<T, ProjectionError>, input: &str) {
    assert!(result.is_err(), "input should be rejected: {input:?}");
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
