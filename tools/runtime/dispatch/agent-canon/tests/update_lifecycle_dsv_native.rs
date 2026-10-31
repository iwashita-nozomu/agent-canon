// @dependency-start
// contract test
// responsibility Verifies DSV mapping, text, byte parsing, canonical output, import digests, and errors against frozen CPython results.
// upstream implementation ../src/update_lifecycle_contract.rs owns DSV envelope schema and APIs.
// upstream implementation ../src/python_json.rs owns Python JSON values, duplicate-key behavior, and raw-byte decoding.
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical UTF-8 JSON bytes and float refusal.
// upstream test ../../../../../tests/fixtures/update_lifecycle/dsv_python_golden.json freezes the independent old-Python oracle.
// @dependency-end

use agent_canon::python_json::{parse_json, JsonString, JsonValue};
use agent_canon::update_lifecycle_contract::{
    import_decision_sufficiency_verdict, parse_decision_sufficiency_verdict,
    serialize_decision_sufficiency_verdict, DecisionSufficiencyEnvelopeError,
    DecisionSufficiencyInput,
};
use sha2::{Digest, Sha256};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/dsv_python_golden.json");

enum ActualOutput {
    Packet(JsonValue),
    Bytes(Vec<u8>),
}

fn object_get<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonValue> {
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

fn text(value: &JsonValue) -> Option<String> {
    match value {
        JsonValue::String(value) => value.to_text(),
        _ => None,
    }
}

fn text_field(value: &JsonValue, key: &str) -> String {
    text(object_get(value, key).expect("fixture string field is present"))
        .expect("fixture field is a string")
}

fn bool_field(value: &JsonValue, key: &str) -> Option<bool> {
    match object_get(value, key) {
        Some(JsonValue::Bool(value)) => Some(*value),
        _ => None,
    }
}

fn decode_hex(value: &str) -> Vec<u8> {
    assert_eq!(
        value.len() % 2,
        0,
        "fixture byte payload has even hex length"
    );
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let pair = std::str::from_utf8(pair).expect("fixture byte payload is ASCII");
            u8::from_str_radix(pair, 16).expect("fixture byte payload is hexadecimal")
        })
        .collect()
}

fn encode_hex(value: &[u8]) -> String {
    value.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn sha256_hex(value: &[u8]) -> String {
    Sha256::digest(value)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn invoke_payload(
    payload: DecisionSufficiencyInput<'_>,
    api: &str,
    expected_digest: Option<&str>,
) -> Result<ActualOutput, DecisionSufficiencyEnvelopeError> {
    match api {
        "parse" => parse_decision_sufficiency_verdict(payload).map(ActualOutput::Packet),
        "import" => {
            import_decision_sufficiency_verdict(payload, expected_digest).map(ActualOutput::Packet)
        }
        api => panic!("unmapped DSV payload API {api}"),
    }
}

fn invoke(case: &JsonValue) -> Result<ActualOutput, DecisionSufficiencyEnvelopeError> {
    let api = text_field(case, "api");
    let payload = object_get(case, "payload").expect("DSV payload input is present");
    match api.as_str() {
        "parse" | "import" => {
            let expected_digest =
                if api == "import" && bool_field(case, "digest_supplied") == Some(true) {
                    Some(text_field(case, "expected_digest"))
                } else {
                    None
                };
            let expected_digest = expected_digest.as_deref();
            let kind = text_field(payload, "kind");
            match kind.as_str() {
                "mapping" => {
                    let value = object_get(payload, "value").expect("mapping payload exists");
                    invoke_payload(
                        DecisionSufficiencyInput::Mapping(value),
                        &api,
                        expected_digest,
                    )
                }
                "text" => {
                    let JsonValue::String(value) =
                        object_get(payload, "value").expect("text payload exists")
                    else {
                        panic!("text payload is a Python string value");
                    };
                    invoke_payload(DecisionSufficiencyInput::Text(value), &api, expected_digest)
                }
                "bytes" => {
                    let bytes = decode_hex(&text_field(payload, "hex"));
                    invoke_payload(
                        DecisionSufficiencyInput::Bytes(&bytes),
                        &api,
                        expected_digest,
                    )
                }
                kind => panic!("unmapped DSV payload kind {kind}"),
            }
        }
        "serialize" => {
            let JsonValue::String(kind) =
                object_get(payload, "kind").expect("payload kind is present")
            else {
                panic!("DSV payload kind is text");
            };
            assert!(kind.equals_text("mapping"));
            let value = object_get(payload, "value").expect("mapping payload exists");
            serialize_decision_sufficiency_verdict(value).map(ActualOutput::Bytes)
        }
        api => panic!("unmapped DSV API {api}"),
    }
}

fn compare_error(actual: &DecisionSufficiencyEnvelopeError, expected: &JsonValue, name: &str) {
    let expected_class = text_field(expected, "exception_class");
    match actual {
        DecisionSufficiencyEnvelopeError::Lifecycle(error) => {
            assert_eq!(
                expected_class, "LifecycleContractError",
                "exception class for {name}"
            );
            let expected_code = text_field(expected, "code");
            assert_eq!(
                error.code.as_str(),
                expected_code.as_str(),
                "error code for {name}"
            );
            assert_eq!(
                error.detail,
                text_field(expected, "detail"),
                "error detail for {name}"
            );
        }
        DecisionSufficiencyEnvelopeError::ArtifactIdentity(error) => {
            assert_eq!(
                expected_class, "ArtifactIdentityError",
                "exception class for {name}"
            );
            let expected_code = text_field(expected, "code");
            assert_eq!(error.code, expected_code.as_str(), "error code for {name}");
            assert_eq!(
                error.detail,
                text_field(expected, "detail"),
                "error detail for {name}"
            );
        }
        DecisionSufficiencyEnvelopeError::UnicodeEncodeError { message } => {
            assert_eq!(
                expected_class, "UnicodeEncodeError",
                "exception class for {name}"
            );
            assert_eq!(
                message,
                &text_field(expected, "message"),
                "error message for {name}"
            );
        }
    }
}

fn verify_case(case: &JsonValue) -> bool {
    let name = text_field(case, "name");
    let expected_error =
        object_get(case, "error").filter(|value| !matches!(value, JsonValue::Null));
    match (invoke(case), expected_error) {
        (Ok(ActualOutput::Packet(actual)), None) => {
            assert!(
                object_get(case, "output").is_some(),
                "accepted DSV packet output is present for {name}"
            );
            let expected = text_field(case, "canonical_utf8");
            let bytes = serialize_decision_sufficiency_verdict(&actual)
                .expect("accepted DSV packet serializes canonically");
            assert_eq!(bytes, expected.as_bytes(), "canonical bytes for {name}");
            assert_eq!(
                sha256_hex(&bytes),
                text_field(case, "sha256"),
                "canonical digest for {name}"
            );
            true
        }
        (Ok(ActualOutput::Bytes(actual)), None) => {
            assert!(
                object_get(case, "output_bytes_hex").is_some(),
                "serialized byte output is present for {name}"
            );
            assert_eq!(
                encode_hex(&actual),
                text_field(case, "output_bytes_hex"),
                "serialized bytes for {name}"
            );
            assert_eq!(
                sha256_hex(&actual),
                text_field(case, "sha256"),
                "serialized digest for {name}"
            );
            true
        }
        (Err(actual), Some(expected)) => {
            compare_error(&actual, expected, &name);
            false
        }
        (actual, expected_error) => panic!(
            "fixture/API result shape differs for {name}: result={}, error={}",
            match actual {
                Ok(_) => "accepted",
                Err(_) => "rejected",
            },
            expected_error.is_some()
        ),
    }
}

#[test]
fn dsv_envelope_apis_match_all_frozen_cpython_values_bytes_and_errors() {
    let golden = parse_json(GOLDEN)
        .expect("frozen DSV golden uses the existing Python-compatible JSON parser");
    let cases = match object_get(&golden, "cases") {
        Some(JsonValue::Array(values)) => &values.0,
        _ => panic!("frozen DSV cases are an array"),
    };
    assert_eq!(cases.len(), 40);
    let mut accepted = 0;
    let mut rejected = 0;
    for case in cases {
        if verify_case(case) {
            accepted += 1;
        } else {
            rejected += 1;
        }
    }
    assert_eq!(accepted, 14);
    assert_eq!(rejected, 26);
}

#[test]
fn raw_surrogate_pair_remains_distinct_from_an_escaped_json_pair() {
    let prefix = r#"{"schema":"agent-canon.decision-sufficiency.v1","value":""#;
    let suffix = r#""}"#;
    let mut raw_codepoints = JsonString::from_text(prefix).0;
    raw_codepoints.extend([0xd800, 0xdc00]);
    raw_codepoints.extend(JsonString::from_text(suffix).0);
    let raw_text = JsonString(raw_codepoints);

    let error = match parse_decision_sufficiency_verdict(DecisionSufficiencyInput::Text(&raw_text))
    {
        Ok(_) => panic!("raw adjacent surrogate code points cannot be UTF-8 canonicalized"),
        Err(error) => error,
    };
    let position = prefix.chars().count();
    assert_eq!(
        error,
        DecisionSufficiencyEnvelopeError::UnicodeEncodeError {
            message: format!(
                "'utf-8' codec can't encode character '\\ud800' in position {position}: surrogates not allowed"
            ),
        }
    );

    let escaped_text = JsonString::from_text(
        r#"{"schema":"agent-canon.decision-sufficiency.v1","value":"\ud800\udc00"}"#,
    );
    let packet = parse_decision_sufficiency_verdict(DecisionSufficiencyInput::Text(&escaped_text))
        .expect("escaped high/low pair decodes as one Unicode scalar");
    let bytes = serialize_decision_sufficiency_verdict(&packet)
        .expect("decoded Unicode scalar is valid canonical UTF-8");
    let scalar = char::from_u32(0x1_0000).expect("expected supplementary scalar");
    assert_eq!(
        bytes,
        format!(r#"{{"schema":"agent-canon.decision-sufficiency.v1","value":"{scalar}"}}"#)
            .as_bytes()
    );
}
