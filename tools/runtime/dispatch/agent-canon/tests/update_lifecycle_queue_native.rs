// @dependency-start
// contract test
// responsibility Verifies queue projection, raw once-key bytes, queue receipts, and immutable replay against frozen CPython outputs.
// upstream implementation ../src/update_lifecycle_contract.rs owns lifecycle queue and replay APIs.
// upstream implementation ../src/python_json.rs owns recursive Python-compatible integer/bool equality after float rejection.
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical bytes and float refusal.
// upstream test ../../../../../tests/fixtures/update_lifecycle/queue_python_golden.json freezes the old Python oracle.
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use agent_canon::update_lifecycle_contract::{
    materialize_queue_receipt, queue_once_key, source_publication_identity,
    validate_immutable_replay, validate_queue_receipt, LifecycleContractError,
};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::path::Path;

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/queue_python_golden.json");

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
        "source_publication_identity" => source_publication_identity(&args[0]),
        "queue_once_key" => {
            let namespace = args[0].as_str().expect("queue namespace input is text");
            queue_once_key(namespace, &args[1], &args[2]).map(Value::String)
        }
        "validate_queue_receipt" => validate_queue_receipt(&args[0]),
        "materialize_queue_receipt" => {
            let kwargs = case
                .kwargs
                .as_object()
                .expect("queue materializer kwargs are an object");
            materialize_queue_receipt(
                kwargs.get("binding").expect("binding input is present"),
                kwargs
                    .get("source_namespace")
                    .and_then(Value::as_str)
                    .expect("source namespace input is text"),
                kwargs
                    .get("source_main_rebind_receipt_id")
                    .and_then(Value::as_str)
                    .expect("rebind receipt ID input is text"),
                kwargs
                    .get("source_main_readback_evidence_ref")
                    .and_then(Value::as_str)
                    .expect("source-main readback evidence input is text"),
                kwargs
                    .get("publication_readback_receipt")
                    .expect("publication readback input is present"),
                kwargs
                    .get("state")
                    .and_then(Value::as_str)
                    .expect("queue state input is text"),
            )
        }
        "validate_immutable_replay" => {
            let field = case
                .kwargs
                .get("field")
                .and_then(Value::as_str)
                .expect("replay field input is text");
            validate_immutable_replay(&args[0], &args[1], field)?;
            Ok(Value::Null)
        }
        api => panic!("unmapped frozen queue API {api}"),
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
            let bytes =
                canonical_json_bytes(&actual).expect("frozen queue API output has canonical bytes");
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
    serde_json::from_str(GOLDEN).expect("frozen CPython 3.12.3 queue golden parses")
}

#[cfg(unix)]
#[test]
fn queue_apis_match_all_frozen_cpython_records_hashes_and_errors() {
    let golden = frozen_golden();
    assert_eq!(golden.cases.len(), 24);
    let mut accepted = 0;
    let mut rejected = 0;
    for case in &golden.cases {
        if verify_case(case) {
            accepted += 1;
        } else {
            rejected += 1;
        }
    }
    assert_eq!(accepted, 12);
    assert_eq!(rejected, 12);
}

#[cfg(not(unix))]
#[test]
fn platform_independent_queue_cases_match_frozen_cpython_records_hashes_and_errors() {
    let golden = frozen_golden();
    assert_eq!(golden.cases.len(), 24);
    let portable_cases = golden
        .cases
        .iter()
        .filter(|case| {
            matches!(
                case.name.as_str(),
                "projection"
                    | "key"
                    | "key-unescaped-namespace"
                    | "key-relative-namespace-is-not-validated-here"
                    | "relative"
                    | "empty"
                    | "relative-materializer"
                    | "replay-timing-only"
                    | "replay-int-float"
                    | "replay-int-bool"
                    | "replay-nested-numeric"
                    | "replay-changed"
                    | "replay-missing-binding"
                    | "replay-binding-extra"
            )
        })
        .collect::<Vec<_>>();
    assert_eq!(portable_cases.len(), 14);
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
    assert_eq!(rejected, 7);
}

#[test]
fn immutable_replay_keeps_arbitrary_precision_integer_semantics() {
    let existing: Value = serde_json::from_str(
        r#"{"binding":{},"nested":[{"value":340282366920938463463374607431768211456}]}"#,
    )
    .expect("large integer record parses");
    let equal: Value = serde_json::from_str(
        r#"{"binding":{},"nested":[{"value":340282366920938463463374607431768211456}]}"#,
    )
    .expect("equal large integer record parses");
    assert!(
        validate_immutable_replay(&existing, &equal, "test-replay").is_ok(),
        "equal arbitrary-precision integers remain equal"
    );

    let changed: Value = serde_json::from_str(
        r#"{"binding":{},"nested":[{"value":340282366920938463463374607431768211457}]}"#,
    )
    .expect("adjacent large integer record parses");
    let error = validate_immutable_replay(&existing, &changed, "test-replay")
        .expect_err("adjacent arbitrary-precision integers differ");
    assert_eq!(error.code, "input_identity_mismatch");
    assert_eq!(error.detail, "test-replay");
}

#[test]
fn queue_materialization_accepts_a_host_absolute_namespace() {
    let golden = frozen_golden();
    let materializer = golden
        .cases
        .iter()
        .find(|case| case.name == "materialize-accepted")
        .expect("valid frozen materializer inputs are present");
    let mut kwargs = materializer.kwargs.clone();
    let namespace = std::env::current_dir()
        .expect("test working directory is available")
        .to_string_lossy()
        .into_owned();
    assert!(Path::new(&namespace).is_absolute());
    kwargs["source_namespace"] = Value::String(namespace.clone());
    let binding = kwargs.get("binding").expect("binding input is present");
    let publication = kwargs
        .get("publication_readback_receipt")
        .expect("publication readback input is present");
    let publication_identity = &publication["pr_identity"];
    let body = format!(
        "{}|{}|{}|{}|{}|{}",
        namespace,
        binding["candidate_sha"]
            .as_str()
            .expect("candidate SHA is text"),
        binding["tree_sha"].as_str().expect("tree SHA is text"),
        binding["input_digest"]
            .as_str()
            .expect("input digest is text"),
        publication_identity["merge_commit_sha"]
            .as_str()
            .expect("merge commit is text"),
        publication_identity["merge_tree_sha"]
            .as_str()
            .expect("merge tree is text"),
    );
    let expected_key = format!("queue-key:{}", sha256_hex(body.as_bytes()));
    let receipt = materialize_queue_receipt(
        binding,
        &namespace,
        kwargs["source_main_rebind_receipt_id"]
            .as_str()
            .expect("rebind receipt ID is text"),
        kwargs["source_main_readback_evidence_ref"]
            .as_str()
            .expect("source-main readback evidence is text"),
        publication,
        kwargs["state"].as_str().expect("queue state is text"),
    )
    .expect("host-absolute namespace is accepted by the queue materializer");
    assert_eq!(
        receipt["source_namespace"].as_str(),
        Some(namespace.as_str())
    );
    assert_eq!(
        receipt["enqueue_once_key"].as_str(),
        Some(expected_key.as_str())
    );
    let expected_receipt_id = format!("queue:{}", sha256_hex(expected_key.as_bytes()));
    assert_eq!(
        receipt["queue_receipt_id"].as_str(),
        Some(expected_receipt_id.as_str())
    );
}
