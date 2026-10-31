// @dependency-start
// contract test
// responsibility Checks the shared Python JSON value and canonical byte API against independent CPython goldens.
// upstream implementation ../src/python_json.rs owns Python-compatible parsing and canonicalization.
// upstream test ../../../../../tests/fixtures/python_json/ledger_golden.json freezes CPython 3.12.3 bytes and digests.
// @dependency-end

use agent_canon::python_json::{canonical_json_ascii_bytes, parse_json};
use serde::Deserialize;
use sha2::{Digest, Sha256};

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
