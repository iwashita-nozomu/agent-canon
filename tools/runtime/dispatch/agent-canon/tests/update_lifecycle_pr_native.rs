// @dependency-start
// contract test
// responsibility Verifies PR lifecycle records, state transitions, and CAS binding against frozen CPython outputs.
// upstream implementation ../src/update_lifecycle_contract.rs owns the lifecycle APIs.
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical compact JSON bytes.
// upstream test ../../../../../tests/fixtures/update_lifecycle/pr_python_golden.json freezes CPython inputs, outputs, and errors.
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use agent_canon::update_lifecycle_contract::{
    pull_request_branch_table, validate_candidate_cas_pr_transition,
    validate_pull_request_lifecycle, validate_pull_request_transition, LifecycleContractError,
};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/pr_python_golden.json");

#[derive(Deserialize)]
struct GoldenFile {
    cases: Vec<GoldenCase>,
}

#[derive(Deserialize)]
struct GoldenCase {
    name: String,
    api: String,
    args: Vec<Value>,
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
        "pull_request_branch_table" => Ok(pull_request_branch_table()),
        "validate_pull_request_lifecycle" => validate_pull_request_lifecycle(&args[0]),
        "validate_pull_request_transition" => validate_pull_request_transition(&args[0], &args[1]),
        "validate_candidate_cas_pr_transition" => {
            validate_candidate_cas_pr_transition(&args[0], &args[1])
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
fn pull_request_lifecycle_apis_match_frozen_cpython_records_hashes_and_errors() {
    let golden: GoldenFile =
        serde_json::from_str(GOLDEN).expect("frozen CPython 3.12.3 PR-lifecycle golden parses");
    assert_eq!(golden.cases.len(), 35);
    let mut accepted = 0;
    let mut rejected = 0;

    for case in &golden.cases {
        match (invoke(case), &case.output, &case.error) {
            (Ok(actual), Some(expected), None) => {
                accepted += 1;
                assert_eq!(actual, *expected, "output for {}", case.name);
                let bytes = canonical_json_bytes(&actual)
                    .expect("frozen PR-lifecycle output has canonical bytes");
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
    assert_eq!(accepted, 18);
    assert_eq!(rejected, 17);
}

#[test]
fn evidence_list_item_errors_precede_duplicate_detection() {
    let golden: GoldenFile =
        serde_json::from_str(GOLDEN).expect("frozen PR-lifecycle inputs parse");
    let user_ready = golden
        .cases
        .iter()
        .find(|case| case.name == "user-ready")
        .expect("the frozen valid user record is available");
    let mut lifecycle = user_ready.args[0].clone();
    let valid_ref = lifecycle["pr_essence"]["evidence_refs"][0].clone();

    lifecycle["pr_essence"]["evidence_refs"] =
        serde_json::json!([valid_ref.clone(), valid_ref.clone(), "bad"]);
    let combined_failure = validate_pull_request_lifecycle(&lifecycle)
        .expect_err("all evidence refs are validated before duplicate detection");
    assert_eq!(
        combined_failure.code, "lifecycle:identity_invalid",
        "a later malformed item precedes duplicate detection"
    );
    assert_eq!(
        combined_failure.detail,
        "pull_request_lifecycle.pr_essence.evidence_refs[2]"
    );

    lifecycle["pr_essence"]["evidence_refs"] = serde_json::json!([valid_ref.clone(), valid_ref]);
    let duplicate_only = validate_pull_request_lifecycle(&lifecycle)
        .expect_err("a duplicate list with otherwise valid items is rejected");
    assert_eq!(duplicate_only.code, "lifecycle:duplicate_value");
    assert_eq!(
        duplicate_only.detail,
        "pull_request_lifecycle.pr_essence.evidence_refs"
    );
}
