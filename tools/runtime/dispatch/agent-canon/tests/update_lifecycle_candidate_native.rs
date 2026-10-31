// @dependency-start
// contract test
// responsibility Verifies candidate-stage receipts, transitions, and CAS materialization against frozen CPython outputs.
// upstream implementation ../src/update_lifecycle_contract.rs owns the lifecycle APIs.
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical compact JSON bytes.
// upstream test ../../../../../tests/fixtures/update_lifecycle/candidate_python_golden.json freezes CPython inputs, outputs, and errors.
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use agent_canon::update_lifecycle_contract::{
    materialize_candidate_cas_receipt, validate_candidate_cas_rebind_transition,
    validate_candidate_cas_receipt, validate_candidate_cas_transition,
    validate_candidate_freeze_receipt, validate_candidate_freeze_transition,
    validate_candidate_review_receipt, validate_candidate_review_transition,
    LifecycleContractError,
};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/candidate_python_golden.json");

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
        "validate_candidate_freeze_receipt" => validate_candidate_freeze_receipt(&args[0]),
        "validate_candidate_review_receipt" => validate_candidate_review_receipt(&args[0]),
        "validate_candidate_cas_receipt" => validate_candidate_cas_receipt(&args[0]),
        "validate_candidate_freeze_transition" => {
            validate_candidate_freeze_transition(&args[0], &args[1])
        }
        "validate_candidate_review_transition" => {
            validate_candidate_review_transition(&args[0], &args[1])
        }
        "validate_candidate_cas_transition" => {
            validate_candidate_cas_transition(&args[0], &args[1])
        }
        "validate_candidate_cas_rebind_transition" => {
            validate_candidate_cas_rebind_transition(&args[0], &args[1])
        }
        "materialize_candidate_cas_receipt" => {
            let kwargs = case
                .kwargs
                .as_object()
                .expect("materializer kwargs are an object");
            let review = kwargs
                .get("candidate_review_receipt")
                .expect("review receipt input exists");
            let rebind = kwargs
                .get("source_main_rebind_receipt")
                .expect("rebind receipt input exists");
            let evidence_ref = kwargs
                .get("cas_evidence_ref")
                .and_then(Value::as_str)
                .expect("CAS evidence ref input is text");
            materialize_candidate_cas_receipt(review, rebind, evidence_ref)
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
fn candidate_stage_apis_match_frozen_cpython_records_hashes_and_errors() {
    let golden: GoldenFile =
        serde_json::from_str(GOLDEN).expect("frozen CPython 3.12.3 candidate-stage golden parses");
    assert_eq!(golden.cases.len(), 28);
    let mut accepted = 0;
    let mut rejected = 0;

    for case in &golden.cases {
        match (invoke(case), &case.output, &case.error) {
            (Ok(actual), Some(expected), None) => {
                accepted += 1;
                assert_eq!(actual, *expected, "output for {}", case.name);
                let bytes = canonical_json_bytes(&actual)
                    .expect("frozen candidate-stage output has canonical bytes");
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
    assert_eq!(accepted, 9);
    assert_eq!(rejected, 19);
}
