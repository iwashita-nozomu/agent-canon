// @dependency-start
// contract test
// responsibility Checks the shared Python JSON value and canonical byte API against independent CPython goldens.
// upstream implementation ../src/python_json.rs owns Python-compatible parsing and canonicalization.
// upstream test ../../../../../tests/fixtures/python_json/ledger_golden.json freezes CPython 3.12.3 bytes and digests.
// @dependency-end

use agent_canon::python_json::{canonical_json_ascii_bytes, parse_json};
use serde::Deserialize;
use sha2::{Digest, Sha256};

#[test]
fn unique_key_decoder_retains_python_constants_and_byte_encodings() {
    use agent_canon::python_json::{
        parse_json_bytes_unique_keys, parse_json_unique_keys, JsonNumber, JsonValue,
    };
    let JsonValue::Object(object) =
        parse_json_unique_keys("{\"metric\":NaN}").expect("Python permits NaN constants")
    else {
        panic!("object expected");
    };
    assert!(
        matches!(&object.0[0].1, JsonValue::Number(JsonNumber::Float(value)) if value.is_nan())
    );
    assert!(parse_json_unique_keys("{\"metric\":NaN,\"nested\":{\"x\":1,\"x\":2}}").is_err());
    let mut utf16 = vec![0xff, 0xfe];
    utf16.extend(
        "{\"name\":\"result\"}"
            .encode_utf16()
            .flat_map(u16::to_le_bytes),
    );
    assert!(matches!(
        parse_json_bytes_unique_keys(&utf16),
        Ok(JsonValue::Object(_))
    ));
    let mut repeated = vec![0xff, 0xfe];
    repeated.extend(
        "{\"x\":1,\"x\":2}"
            .encode_utf16()
            .flat_map(u16::to_le_bytes),
    );
    assert!(parse_json_bytes_unique_keys(&repeated).is_err());
}

#[derive(Deserialize)]
struct GoldenFile {
    cases: Vec<GoldenCase>,
}

#[derive(Deserialize)]
struct GoldenCase {
    name: String,
    input_json: String,
    canonical_ascii: String,
    sha256: String,
}

#[test]
fn python_json_canonical_bytes_match_frozen_cpython_goldens() {
    let golden: GoldenFile = serde_json::from_str(include_str!(
        "../../../../../tests/fixtures/python_json/ledger_golden.json"
    ))
    .expect("frozen CPython golden fixture parses");
    assert_eq!(golden.cases.len(), 4);

    for case in golden.cases {
        let value = parse_json(&case.input_json).expect("Python-compatible JSON input parses");
        let actual = canonical_json_ascii_bytes(&value).expect("canonical ASCII JSON serializes");

        assert_eq!(
            actual,
            case.canonical_ascii.as_bytes(),
            "canonical bytes differ for {}",
            case.name
        );
        assert_eq!(
            sha256_hex(&actual),
            case.sha256,
            "canonical digest differs for {}",
            case.name
        );
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
