// @dependency-start
// contract test
// responsibility Verifies update transaction validation against frozen CPython records, canonical bytes, and errors.
// upstream implementation ../src/update_lifecycle_contract.rs owns the native transaction validator.
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical compact JSON bytes.
// upstream test ../../../../../tests/fixtures/update_lifecycle/transaction_python_golden.json freezes CPython 3.12.3 inputs, outputs, and errors.
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use agent_canon::update_lifecycle_contract::validate_update_transaction;
use serde_json::Value;
use sha2::{Digest, Sha256};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/transaction_python_golden.json");

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[test]
fn update_transactions_match_frozen_cpython_records_bytes_hashes_and_errors() {
    let golden: Value =
        serde_json::from_str(GOLDEN).expect("frozen CPython 3.12.3 transaction golden parses");
    assert_eq!(
        golden["source"].as_str(),
        Some("55d605188ac3e90d264ad4c0c64596270aa6e561")
    );
    assert!(golden["python"]
        .as_str()
        .is_some_and(|version| version.starts_with("3.12.")));
    assert_eq!(
        sha256_hex(GOLDEN.as_bytes()),
        "d20fa978b1c873fea24aba6c9c2c51d6cabaedbe125164c03ef0d7b7795e348a"
    );

    let cases = golden["cases"]
        .as_array()
        .expect("frozen transaction cases are an array");
    assert_eq!(cases.len(), 41);
    let mut accepted = 0;
    let mut rejected = 0;
    for case in cases {
        let name = case["name"].as_str().expect("frozen case name is text");
        let actual = validate_update_transaction(&case["input"]);
        match (actual, case.get("output"), case.get("error")) {
            (Ok(actual), Some(expected), None) => {
                accepted += 1;
                assert_eq!(actual, *expected, "validated transaction for {name}");
                let bytes = canonical_json_bytes(&actual)
                    .expect("accepted frozen transaction has canonical JSON bytes");
                assert_eq!(
                    bytes,
                    case["canonical_utf8"]
                        .as_str()
                        .expect("accepted case freezes canonical bytes")
                        .as_bytes(),
                    "canonical bytes for {name}"
                );
                assert_eq!(
                    sha256_hex(&bytes),
                    case["sha256"]
                        .as_str()
                        .expect("accepted case freezes its SHA-256"),
                    "canonical digest for {name}"
                );
            }
            (Err(actual), None, Some(expected)) => {
                rejected += 1;
                assert_eq!(
                    expected["exception_class"].as_str(),
                    Some("LifecycleContractError"),
                    "Python error class for {name}"
                );
                assert_eq!(
                    actual.code,
                    expected["code"].as_str().expect("error code is text"),
                    "error code for {name}"
                );
                assert_eq!(
                    actual.detail,
                    expected["detail"].as_str().expect("error detail is text"),
                    "error detail for {name}"
                );
            }
            (actual, output, error) => panic!(
                "unexpected validation result for {name}: result={actual:?}, output={output:?}, error={error:?}"
            ),
        }
    }
    assert_eq!(accepted, 21);
    assert_eq!(rejected, 20);
}
