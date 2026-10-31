// @dependency-start
// contract test
// responsibility Verifies lifecycle transition guards against frozen CPython outputs, errors, and unit-result bytes.
// upstream implementation ../src/update_lifecycle_contract.rs owns the pure lifecycle transition guard.
// upstream test ../../../../../tests/fixtures/update_lifecycle/transition_python_golden.json freezes the old Python oracle.
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use agent_canon::update_lifecycle_contract::{guard_transition, LifecycleContractError};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::path::Path;

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/transition_python_golden.json");

#[derive(Deserialize)]
struct GoldenFile {
    cases: Vec<GoldenCase>,
}

#[derive(Deserialize, Clone)]
struct GoldenCase {
    name: String,
    current_state: String,
    next_state: String,
    evidence: Value,
    #[serde(default, deserialize_with = "deserialize_present_json")]
    output: Option<Value>,
    canonical_utf8: Option<String>,
    sha256: Option<String>,
    error: Option<GoldenError>,
}

#[derive(Deserialize, Clone)]
struct GoldenError {
    code: String,
    detail: String,
}

fn deserialize_present_json<'de, D>(deserializer: D) -> Result<Option<Value>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    Value::deserialize(deserializer).map(Some)
}

fn invoke(case: &GoldenCase) -> Result<Value, LifecycleContractError> {
    guard_transition(&case.current_state, &case.next_state, &case.evidence).map(|()| Value::Null)
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn verify_case(case: &GoldenCase) -> bool {
    match (invoke(case), &case.output, &case.error) {
        (Ok(actual), Some(expected), None) => {
            assert_eq!(actual, *expected, "output for {}", case.name);
            let bytes = canonical_json_bytes(&actual)
                .expect("frozen transition result has canonical bytes");
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
            true
        }
        (Err(actual), None, Some(expected)) => {
            assert_eq!(actual.code, expected.code, "error code for {}", case.name);
            assert_eq!(
                actual.detail, expected.detail,
                "error detail for {}",
                case.name
            );
            false
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

fn frozen_golden() -> GoldenFile {
    serde_json::from_str(GOLDEN).expect("frozen CPython 3.12.3 transition golden parses")
}

#[cfg(unix)]
#[test]
fn transition_guard_matches_all_frozen_cpython_outputs_and_errors() {
    let golden = frozen_golden();
    assert_eq!(golden.cases.len(), 30);
    let mut accepted = 0;
    let mut rejected = 0;
    for case in &golden.cases {
        if verify_case(case) {
            accepted += 1;
        } else {
            rejected += 1;
        }
    }
    assert_eq!(accepted, 18);
    assert_eq!(rejected, 12);
}

#[cfg(not(unix))]
#[test]
fn platform_independent_transition_cases_match_frozen_cpython() {
    let golden = frozen_golden();
    assert_eq!(golden.cases.len(), 30);
    let portable_cases = golden
        .cases
        .iter()
        .filter(|case| {
            !matches!(
                case.name.as_str(),
                "valid-queue_enqueued"
                    | "valid-frontier_accepted"
                    | "valid-cleanup_proven"
                    | "valid-nested_lifecycle_cleanup"
                    | "queue-notaccepted"
                    | "frontier-notaccepted"
            )
        })
        .collect::<Vec<_>>();
    assert_eq!(portable_cases.len(), 24);
    let mut accepted = 0;
    let mut rejected = 0;
    for case in portable_cases {
        if verify_case(case) {
            accepted += 1;
        } else {
            rejected += 1;
        }
    }
    assert_eq!(accepted, 14);
    assert_eq!(rejected, 10);
}

fn replace_cleanup_path(evidence: &mut Value, path: &str) {
    let proof = evidence
        .get_mut("cleanup_proof")
        .and_then(Value::as_object_mut)
        .expect("cleanup proof is present as a mapping");
    let paths = proof
        .get("task_owned_paths")
        .and_then(Value::as_array)
        .expect("task-owned paths are a sequence");
    assert_eq!(paths.len(), 1);
    let old_path = paths[0]
        .as_str()
        .expect("task-owned path is text")
        .to_owned();
    for field in ["task_owned_state_before", "task_owned_state_after"] {
        let map = proof
            .get_mut(field)
            .and_then(Value::as_object_mut)
            .expect("task-owned state is a mapping");
        let state = map
            .remove(&old_path)
            .expect("task-owned state has the old path key");
        map.insert(path.to_owned(), state);
    }
    proof.insert("task_owned_paths".to_owned(), serde_json::json!([path]));
    proof.insert("cleaned_paths".to_owned(), serde_json::json!([path]));
}

#[test]
fn nested_cleanup_transition_accepts_a_host_absolute_path() {
    let golden = frozen_golden();
    let mut case = golden
        .cases
        .iter()
        .find(|case| case.name == "valid-nested_lifecycle_cleanup")
        .expect("valid nested-cleanup transition fixture is present")
        .clone();
    let path = std::env::current_dir()
        .expect("test working directory is available")
        .join("agent-canon-transition-owned")
        .to_string_lossy()
        .into_owned();
    assert!(Path::new(&path).is_absolute());
    replace_cleanup_path(&mut case.evidence, &path);
    assert!(verify_case(&case));
}
