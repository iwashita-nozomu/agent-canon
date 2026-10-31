// @dependency-start
// contract test
// responsibility Verifies source-main rebind receipt validation and materialization against frozen CPython outputs.
// upstream implementation ../src/update_lifecycle_contract.rs owns native rebind APIs.
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical compact JSON bytes.
// upstream test ../../../../../tests/fixtures/update_lifecycle/rebind_python_golden.json freezes CPython 3.12.3 outputs and errors.
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use agent_canon::update_lifecycle_contract::{
    materialize_source_main_rebind_receipt, validate_source_main_rebind_receipt,
};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/rebind_python_golden.json");

#[derive(Deserialize)]
struct GoldenFile {
    positive: Vec<PositiveCase>,
    validation_cases: Vec<ValidationCase>,
}

#[derive(Deserialize)]
struct PositiveCase {
    name: String,
    input: Value,
    output: Value,
    canonical_utf8: String,
    sha256: String,
}

#[derive(Deserialize)]
struct ValidationCase {
    name: String,
    input: Value,
    output: Option<Value>,
    error: Option<ExpectedError>,
}

#[derive(Deserialize)]
struct ExpectedError {
    code: String,
    detail: String,
}

fn golden() -> GoldenFile {
    serde_json::from_str(GOLDEN).expect("frozen CPython 3.12.3 golden parses")
}

fn materialize(input: &Value) -> Result<Value, String> {
    let binding = input
        .get("binding")
        .ok_or_else(|| "golden materializer input requires binding".to_owned())?;
    let old_base_identity = input
        .get("old_base_identity")
        .ok_or_else(|| "golden materializer input requires old_base_identity".to_owned())?;
    let new_base_identity = input
        .get("new_base_identity")
        .ok_or_else(|| "golden materializer input requires new_base_identity".to_owned())?;
    let evidence_ref = input
        .get("origin_main_readback_evidence_ref")
        .and_then(Value::as_str)
        .ok_or_else(|| "golden materializer input requires evidence ref".to_owned())?;
    materialize_source_main_rebind_receipt(
        binding,
        old_base_identity,
        new_base_identity,
        evidence_ref,
    )
    .map_err(|error| format!("{}:{}", error.code, error.detail))
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[test]
fn materialized_rebind_receipts_match_frozen_bytes_and_hashes() {
    let golden = golden();
    assert_eq!(golden.positive.len(), 2);

    for case in golden.positive {
        let receipt = materialize(&case.input)
            .unwrap_or_else(|error| panic!("{} materialization failed: {error}", case.name));
        assert_eq!(
            receipt, case.output,
            "materialized fields for {}",
            case.name
        );
        let bytes = canonical_json_bytes(&receipt).expect("golden receipt has canonical bytes");
        assert_eq!(
            bytes,
            case.canonical_utf8.as_bytes(),
            "canonical bytes for {}",
            case.name
        );
        assert_eq!(
            sha256_hex(&bytes),
            case.sha256,
            "receipt digest for {}",
            case.name
        );
    }
}

#[test]
fn rebind_validation_matches_frozen_codes_details_and_nonrecomputed_id() {
    let golden = golden();
    assert_eq!(golden.validation_cases.len(), 17);

    for case in golden.validation_cases {
        let actual = validate_source_main_rebind_receipt(&case.input);
        match case.error {
            Some(expected) => {
                let error = actual.expect_err("invalid Python golden input must be rejected");
                assert_eq!(error.code, expected.code, "error code for {}", case.name);
                assert_eq!(
                    error.detail, expected.detail,
                    "error detail for {}",
                    case.name
                );
            }
            None => {
                assert_eq!(
                    actual.expect("accepted Python golden input validates"),
                    case.output
                        .expect("accepted fixture carries expected output"),
                    "accepted fields for {}",
                    case.name
                );
            }
        }
    }
}
