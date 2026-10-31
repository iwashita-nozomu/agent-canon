// @dependency-start
// contract test
// responsibility Verifies terminal lifecycle receipts, cleanup evidence, and close-agent tokens against frozen CPython outputs.
// upstream implementation ../src/update_lifecycle_contract.rs owns terminal lifecycle APIs.
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical token bytes and body hashes.
// upstream test ../../../../../tests/fixtures/update_lifecycle/terminal_python_golden.json freezes the old Python oracle.
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use agent_canon::update_lifecycle_contract::{
    materialize_close_agent_tool_call, materialize_descendant_close_receipt,
    materialize_reservation_release_receipt, validate_cleanup_proof,
    validate_close_agent_tool_call, validate_descendant_close_receipt, validate_durable_handback,
    validate_reservation_release_receipt, CloseAgentToolCallInput, LifecycleContractError,
};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::path::Path;

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/terminal_python_golden.json");

#[derive(Deserialize)]
struct GoldenFile {
    cases: Vec<GoldenCase>,
}

#[derive(Deserialize, Clone)]
struct GoldenCase {
    name: String,
    api: String,
    args: Vec<Value>,
    #[serde(default)]
    kwargs: Value,
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
    let args = &case.args;
    match case.api.as_str() {
        "validate_durable_handback" => validate_durable_handback(&args[0]),
        "validate_descendant_close_receipt" => validate_descendant_close_receipt(&args[0]),
        "materialize_descendant_close_receipt" => {
            let kwargs = case
                .kwargs
                .as_object()
                .expect("descendant materializer kwargs are an object");
            materialize_descendant_close_receipt(
                kwargs.get("binding").expect("binding input is present"),
                kwargs
                    .get("durable_handback")
                    .expect("handback input is present"),
                kwargs
                    .get("agent_id")
                    .and_then(Value::as_str)
                    .expect("agent ID input is text"),
                kwargs
                    .get("evidence_ref")
                    .and_then(Value::as_str)
                    .expect("evidence input is text"),
            )
        }
        "validate_reservation_release_receipt" => validate_reservation_release_receipt(&args[0]),
        "materialize_reservation_release_receipt" => {
            let kwargs = case
                .kwargs
                .as_object()
                .expect("reservation materializer kwargs are an object");
            materialize_reservation_release_receipt(
                kwargs.get("binding").expect("binding input is present"),
                kwargs
                    .get("durable_handback")
                    .expect("handback input is present"),
                kwargs
                    .get("reservation_id")
                    .and_then(Value::as_str)
                    .expect("reservation ID input is text"),
                kwargs
                    .get("evidence_ref")
                    .and_then(Value::as_str)
                    .expect("evidence input is text"),
            )
        }
        "validate_cleanup_proof" => validate_cleanup_proof(&args[0]),
        "validate_close_agent_tool_call" => validate_close_agent_tool_call(&args[0]),
        "materialize_close_agent_tool_call" => {
            let kwargs = case
                .kwargs
                .as_object()
                .expect("close-agent materializer kwargs are an object");
            let gates = kwargs
                .get("gate_verdicts")
                .and_then(Value::as_array)
                .expect("gate verdicts are a sequence");
            materialize_close_agent_tool_call(CloseAgentToolCallInput {
                binding: kwargs.get("binding").expect("binding input is present"),
                run_id: kwargs
                    .get("run_id")
                    .and_then(Value::as_str)
                    .expect("run ID input is text"),
                agent_id: kwargs
                    .get("agent_id")
                    .and_then(Value::as_str)
                    .expect("agent ID input is text"),
                gate_verdicts: gates,
                cleanup_proof: kwargs
                    .get("cleanup_proof")
                    .expect("cleanup proof input is present"),
                durable_handback: kwargs
                    .get("durable_handback")
                    .expect("handback input is present"),
                descendants_closed_evidence_ref: kwargs
                    .get("descendants_closed_evidence_ref")
                    .and_then(Value::as_str)
                    .expect("descendant evidence input is text"),
                reservations_released_evidence_ref: kwargs
                    .get("reservations_released_evidence_ref")
                    .and_then(Value::as_str)
                    .expect("reservation evidence input is text"),
                completed_but_open: kwargs
                    .get("completed_but_open")
                    .and_then(Value::as_bool)
                    .unwrap_or_default(),
                unknown_descendants: kwargs
                    .get("unknown_descendants")
                    .and_then(Value::as_bool)
                    .unwrap_or_default(),
                reservation_leak: kwargs
                    .get("reservation_leak")
                    .and_then(Value::as_bool)
                    .unwrap_or_default(),
            })
        }
        api => panic!("unmapped frozen terminal lifecycle API {api}"),
    }
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
                .expect("frozen terminal lifecycle output has canonical bytes");
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
    serde_json::from_str(GOLDEN).expect("frozen CPython 3.12.3 terminal receipt golden parses")
}

#[cfg(unix)]
#[test]
fn terminal_receipt_apis_match_all_frozen_cpython_records_hashes_and_errors() {
    let golden = frozen_golden();
    assert_eq!(golden.cases.len(), 38);
    let mut accepted = 0;
    let mut rejected = 0;
    for case in &golden.cases {
        if verify_case(case) {
            accepted += 1;
        } else {
            rejected += 1;
        }
    }
    assert_eq!(accepted, 9);
    assert_eq!(rejected, 29);
}

#[cfg(not(unix))]
#[test]
fn platform_independent_terminal_cases_match_frozen_cpython() {
    let golden = frozen_golden();
    assert_eq!(golden.cases.len(), 38);
    let portable_cases = golden
        .cases
        .iter()
        .filter(|case| {
            matches!(
                (case.api.as_str(), case.name.as_str()),
                ("validate_durable_handback", "handback")
                    | ("validate_durable_handback", "handback-bad-agent")
                    | ("validate_durable_handback", "handback-duplicate-descendant")
                    | (
                        "validate_durable_handback",
                        "handback-duplicate-plus-invalid"
                    )
                    | ("validate_durable_handback", "handback-bad-reservation")
                    | ("validate_durable_handback", "handback-bad-state")
                    | ("validate_descendant_close_receipt", "descendant")
                    | ("validate_descendant_close_receipt", "not-closed")
                    | (
                        "materialize_descendant_close_receipt",
                        "materialize-descendant"
                    )
                    | ("materialize_descendant_close_receipt", "unknown-descendant")
                    | ("validate_reservation_release_receipt", "reservation")
                    | ("validate_reservation_release_receipt", "not-released")
                    | (
                        "materialize_reservation_release_receipt",
                        "materialize-reservation"
                    )
                    | (
                        "materialize_reservation_release_receipt",
                        "unknown-reservation"
                    )
                    | ("validate_cleanup_proof", "cleanup-relative-path")
                    | ("validate_close_agent_tool_call", "token")
                    | ("validate_close_agent_tool_call", "token-tool")
                    | ("validate_close_agent_tool_call", "token-state")
                    | ("validate_close_agent_tool_call", "token-gate-count")
                    | ("validate_close_agent_tool_call", "token-duplicate-gates")
                    | ("validate_close_agent_tool_call", "token-completed")
                    | ("validate_close_agent_tool_call", "token-unknown")
                    | ("validate_close_agent_tool_call", "token-reservation")
                    | ("validate_close_agent_tool_call", "token-readback")
                    | ("validate_close_agent_tool_call", "token-identity")
                    | ("validate_close_agent_tool_call", "token-id")
                    | ("validate_close_agent_tool_call", "token-body")
                    | ("validate_close_agent_tool_call", "guard-numeric-equality")
                    | (
                        "materialize_close_agent_tool_call",
                        "missing-gate-materializer"
                    )
            )
        })
        .collect::<Vec<_>>();
    assert_eq!(portable_cases.len(), 29);
    let mut accepted = 0;
    let mut rejected = 0;
    for case in portable_cases {
        if verify_case(case) {
            accepted += 1;
        } else {
            rejected += 1;
        }
    }
    assert_eq!(accepted, 7);
    assert_eq!(rejected, 22);
}

fn replace_cleanup_paths(kwargs: &mut Value, path: &str) {
    let proof = kwargs
        .get_mut("cleanup_proof")
        .and_then(Value::as_object_mut)
        .expect("cleanup proof input is an object");
    let owned_paths = proof
        .get("task_owned_paths")
        .and_then(Value::as_array)
        .expect("owned paths are a sequence");
    assert_eq!(owned_paths.len(), 1);
    let old_path = owned_paths[0]
        .as_str()
        .expect("old owned path is text")
        .to_owned();
    for field in ["task_owned_state_before", "task_owned_state_after"] {
        let state = proof
            .get_mut(field)
            .and_then(Value::as_object_mut)
            .expect("task-owned state is a mapping")
            .remove(&old_path)
            .expect("old state path is present");
        proof
            .get_mut(field)
            .and_then(Value::as_object_mut)
            .expect("task-owned state is a mapping")
            .insert(path.to_owned(), state);
    }
    proof.insert("task_owned_paths".to_owned(), serde_json::json!([path]));
    proof.insert("cleaned_paths".to_owned(), serde_json::json!([path]));
}

#[test]
fn close_agent_materializers_accept_host_absolute_cleanup_paths() {
    let golden = frozen_golden();
    let directory = std::env::current_dir().expect("test working directory is available");
    let path = directory
        .join("agent-canon-terminal-owned")
        .to_string_lossy()
        .into_owned();
    assert!(Path::new(&path).is_absolute());
    let materializer_names = [
        "materialize-token",
        "completed-materializer",
        "unknown-materializer",
        "reservation-materializer",
    ];
    let mut accepted = 0;
    let mut rejected = 0;
    for name in materializer_names {
        let mut case = golden
            .cases
            .iter()
            .find(|case| case.name == name)
            .expect("frozen close-agent materializer case is present")
            .clone();
        replace_cleanup_paths(&mut case.kwargs, &path);
        if verify_case(&case) {
            accepted += 1;
        } else {
            rejected += 1;
        }
    }
    assert_eq!(accepted, 1);
    assert_eq!(rejected, 3);
}
