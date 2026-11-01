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
    let (pairs, remainder) = value.as_bytes().as_chunks::<2>();
    assert!(
        remainder.is_empty(),
        "fixture byte payload has even hex length"
    );
    pairs
        .iter()
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

enum SupplementalPayload {
    Text(JsonString),
    Bytes(Vec<u8>),
}

enum SupplementalExpected {
    Canonical {
        bytes: String,
        sha256: &'static str,
    },
    Lifecycle {
        message: &'static str,
        code: &'static str,
        detail: &'static str,
    },
    ArtifactIdentity {
        message: &'static str,
        code: &'static str,
        detail: &'static str,
    },
    UnicodeEncode(&'static str),
}

#[test]
fn supplemental_cpython_surrogate_cases_match_exact_outputs_and_errors() {
    // This frozen supplement comes from the independent CPython 3.12.3 probe.
    // The 40-case fixture remains unchanged; these inputs distinguish raw code points
    // from JSON escape sequences and exercise the supported bytes decoders.
    let prefix = r#"{"schema":"agent-canon.decision-sufficiency.v1","x":""#;
    let suffix = r#""}"#;
    let text_with_codepoints = |middle: &[u32], tail: &str| {
        let mut codepoints = JsonString::from_text(prefix).0;
        codepoints.extend_from_slice(middle);
        codepoints.extend(JsonString::from_text(tail).0);
        JsonString(codepoints)
    };
    let escaped_pair_text = {
        let mut text = prefix.to_owned();
        text.push_str("\\ud800\\udc00");
        text.push_str(suffix);
        JsonString::from_text(&text)
    };
    let pair = [0xd800, 0xdc00];
    let raw_pair_text = text_with_codepoints(&pair, suffix);
    let separated_text = text_with_codepoints(&[0xd800, u32::from(b'a'), 0xdc00], suffix);
    let float_before_pair_text = text_with_codepoints(&pair, r#"","y":1.5}"#);
    let utf16_raw_pair = decode_hex(
        "7b00220073006300680065006d00610022003a0022006100670065006e0074002d00630061006e006f006e002e006400650063006900730069006f006e002d00730075006600660069006300690065006e00630079002e007600310022002c002200780022003a00220000d800dc22007d00",
    );
    let utf32_raw_pair = decode_hex(
        "7b00000022000000730000006300000068000000650000006d00000061000000220000003a000000220000006100000067000000650000006e000000740000002d00000063000000610000006e0000006f0000006e0000002e0000006400000065000000630000006900000073000000690000006f0000006e0000002d00000073000000750000006600000066000000690000006300000069000000650000006e00000063000000790000002e0000007600000031000000220000002c0000002200000078000000220000003a0000002200000000d8000000dc0000220000007d000000",
    );
    let scalar = char::from_u32(0x1_0000).expect("expected supplementary scalar");
    let expected_canonical =
        format!(r#"{{"schema":"agent-canon.decision-sufficiency.v1","x":"{scalar}"}}"#);
    let pair_error =
        "'utf-8' codec can't encode characters in position 53-54: surrogates not allowed";
    let cases = vec![
        (
            "escaped-pair-text",
            SupplementalPayload::Text(escaped_pair_text),
            SupplementalExpected::Canonical {
                bytes: expected_canonical.clone(),
                sha256: "bb2ca31448ab6c6ed9b5e8a4fab4bdbfba5696e928ae788d8ce4e14a12794c3d",
            },
        ),
        (
            "raw-pair-text",
            SupplementalPayload::Text(raw_pair_text),
            SupplementalExpected::UnicodeEncode(pair_error),
        ),
        (
            "raw-pair-utf8",
            SupplementalPayload::Bytes(decode_hex(
                "7b22736368656d61223a226167656e742d63616e6f6e2e6465636973696f6e2d73756666696369656e63792e7631222c2278223a22eda080edb080227d",
            )),
            SupplementalExpected::UnicodeEncode(pair_error),
        ),
        (
            "raw-pair-utf32le",
            SupplementalPayload::Bytes(utf32_raw_pair),
            SupplementalExpected::UnicodeEncode(pair_error),
        ),
        (
            "raw-pair-utf16le",
            SupplementalPayload::Bytes(utf16_raw_pair),
            SupplementalExpected::Canonical {
                bytes: expected_canonical.clone(),
                sha256: "bb2ca31448ab6c6ed9b5e8a4fab4bdbfba5696e928ae788d8ce4e14a12794c3d",
            },
        ),
        (
            "separated-raw-surrogates",
            SupplementalPayload::Text(separated_text),
            SupplementalExpected::UnicodeEncode(
                "'utf-8' codec can't encode character '\\ud800' in position 53: surrogates not allowed",
            ),
        ),
        (
            "wrong-schema-before-pair",
            SupplementalPayload::Bytes(decode_hex(
                "7b22736368656d61223a22626164222c2278223a22eda080edb080227d",
            )),
            SupplementalExpected::Lifecycle {
                message: "decision_sufficiency:envelope_schema_invalid",
                code: "decision_sufficiency:envelope_schema_invalid",
                detail: "",
            },
        ),
        (
            "float-before-pair",
            SupplementalPayload::Text(float_before_pair_text),
            SupplementalExpected::ArtifactIdentity {
                message: "artifact_identity:float_forbidden",
                code: "artifact_identity:float_forbidden",
                detail: "",
            },
        ),
    ];
    assert_eq!(cases.len(), 8);

    let mut accepted = 0;
    let mut rejected = 0;
    for (name, payload, expected) in cases {
        let actual = match payload {
            SupplementalPayload::Text(text) => {
                parse_decision_sufficiency_verdict(DecisionSufficiencyInput::Text(&text))
            }
            SupplementalPayload::Bytes(bytes) => {
                parse_decision_sufficiency_verdict(DecisionSufficiencyInput::Bytes(&bytes))
            }
        };
        match (actual, expected) {
            (Ok(packet), SupplementalExpected::Canonical { bytes, sha256 }) => {
                accepted += 1;
                let canonical = match serialize_decision_sufficiency_verdict(&packet) {
                    Ok(value) => value,
                    Err(error) => panic!("canonical serialization failed for {name}: {error}"),
                };
                assert_eq!(canonical, bytes.as_bytes(), "canonical bytes for {name}");
                assert_eq!(
                    sha256_hex(&canonical),
                    sha256,
                    "canonical digest for {name}"
                );
            }
            (
                Err(DecisionSufficiencyEnvelopeError::UnicodeEncodeError { message }),
                SupplementalExpected::UnicodeEncode(expected),
            ) => {
                rejected += 1;
                assert_eq!(message, expected, "UnicodeEncodeError message for {name}");
            }
            (
                Err(DecisionSufficiencyEnvelopeError::Lifecycle(error)),
                SupplementalExpected::Lifecycle {
                    message,
                    code,
                    detail,
                },
            ) => {
                rejected += 1;
                assert_eq!(error.to_string(), message, "lifecycle message for {name}");
                assert_eq!(error.code, code, "lifecycle error code for {name}");
                assert_eq!(error.detail, detail, "lifecycle error detail for {name}");
            }
            (
                Err(DecisionSufficiencyEnvelopeError::ArtifactIdentity(error)),
                SupplementalExpected::ArtifactIdentity {
                    message,
                    code,
                    detail,
                },
            ) => {
                rejected += 1;
                assert_eq!(error.to_string(), message, "artifact message for {name}");
                assert_eq!(error.code, code, "artifact error code for {name}");
                assert_eq!(error.detail, detail, "artifact error detail for {name}");
            }
            _ => panic!("result or exception class differs for {name}"),
        }
    }
    assert_eq!(accepted, 2);
    assert_eq!(rejected, 6);
}
