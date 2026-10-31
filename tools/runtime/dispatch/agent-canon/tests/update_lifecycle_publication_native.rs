// @dependency-start
// contract test
// responsibility Verifies publication readback receipts and transitions against frozen CPython inputs, outputs, and errors.
// upstream implementation ../src/update_lifecycle_contract.rs owns publication readback lifecycle APIs.
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical compact JSON bytes.
// upstream test ../../../../../tests/fixtures/update_lifecycle/publication_python_golden.json freezes the independent oracle.
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use agent_canon::update_lifecycle_contract::{
    materialize_publication_readback_receipt, validate_publication_readback_receipt,
    validate_publication_readback_transition, LifecycleContractError,
};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/publication_python_golden.json");

#[derive(Deserialize)]
struct GoldenFile {
    cases: Vec<GoldenCase>,
}

#[derive(Deserialize)]
struct GoldenCase {
    name: String,
    api: String,
    args: Vec<Value>,
    #[serde(default)]
    kwargs: Value,
    output: Option<Value>,
    canonical_utf8: Option<String>,
    sha256: Option<String>,
    error: Option<GoldenError>,
}

#[derive(Deserialize)]
struct GoldenError {
    code: String,
    detail: String,
}

fn invoke(case: &GoldenCase) -> Result<Value, LifecycleContractError> {
    let args = &case.args;
    match case.api.as_str() {
        "validate_publication_readback_receipt" => validate_publication_readback_receipt(&args[0]),
        "validate_publication_readback_transition" => {
            validate_publication_readback_transition(&args[0], &args[1], &args[2])
        }
        "materialize_publication_readback_receipt" => {
            let kwargs = case
                .kwargs
                .as_object()
                .expect("materializer kwargs are an object");
            let cas = kwargs
                .get("candidate_cas_receipt")
                .expect("CAS input is present");
            let lifecycle = kwargs
                .get("pull_request_lifecycle")
                .expect("PR lifecycle input is present");
            let readback = kwargs
                .get("authoritative_pr_readback")
                .expect("authoritative readback input is present");
            materialize_publication_readback_receipt(cas, lifecycle, readback)
        }
        api => panic!("unmapped frozen lifecycle API {api}"),
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[test]
fn publication_readback_apis_match_frozen_cpython_records_hashes_and_errors() {
    let golden: GoldenFile = serde_json::from_str(GOLDEN)
        .expect("frozen CPython 3.12.3 publication readback golden parses");
    assert_eq!(golden.cases.len(), 25);
    let mut accepted = 0;
    let mut rejected = 0;

    for case in &golden.cases {
        match (invoke(case), &case.output, &case.error) {
            (Ok(actual), Some(expected), None) => {
                accepted += 1;
                assert_eq!(actual, *expected, "output for {}", case.name);
                let bytes = canonical_json_bytes(&actual)
                    .expect("frozen publication readback output has canonical bytes");
                assert_eq!(
                    bytes,
                    case.canonical_utf8
                        .as_ref()
                        .expect("accepted case freezes canonical bytes")
                        .as_bytes(),
                    "canonical bytes for {}",
                    case.name
                );
                assert_eq!(
                    sha256_hex(&bytes),
                    case.sha256
                        .as_deref()
                        .expect("accepted case freezes its SHA-256"),
                    "canonical digest for {}",
                    case.name
                );
            }
            (Err(actual), None, Some(expected)) => {
                rejected += 1;
                assert_eq!(actual.code, expected.code, "error code for {}", case.name);
                assert_eq!(
                    actual.detail, expected.detail,
                    "error detail for {}",
                    case.name
                );
            }
            (actual, output, error) => panic!(
                "fixture/API result shape differs for {}: result={:?}, output={}, error={}",
                case.name,
                actual.as_ref().map(|_| "accepted"),
                output.is_some(),
                error.is_some()
            ),
        }
    }
    assert_eq!(accepted, 6);
    assert_eq!(rejected, 19);
}
