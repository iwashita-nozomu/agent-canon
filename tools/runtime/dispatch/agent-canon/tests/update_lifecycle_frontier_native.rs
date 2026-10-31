// @dependency-start
// contract test
// responsibility Verifies dependency frontiers, ordered transitions, and frontier identities against frozen CPython outputs.
// upstream implementation ../src/update_lifecycle_contract.rs owns lifecycle frontier APIs.
// upstream test ../../../../../tests/fixtures/update_lifecycle/frontier_python_golden.json freezes the old Python oracle.
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use agent_canon::update_lifecycle_contract::{
    after_binding_transaction, frontier_key, materialize_dependency_frontier,
    validate_dependency_frontier, validate_dependency_frontier_transition, LifecycleContractError,
    SourceMainReadbackIdentity,
};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::path::Path;

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/frontier_python_golden.json");

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
    #[serde(default, deserialize_with = "deserialize_present_json")]
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

fn deserialize_present_json<'de, D>(deserializer: D) -> Result<Option<Value>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    Value::deserialize(deserializer).map(Some)
}

fn invoke(case: &GoldenCase) -> Result<Value, LifecycleContractError> {
    let args = &case.args;
    match case.api.as_str() {
        "frontier_key" => {
            let namespace = args[0].as_str().expect("frontier namespace input is text");
            frontier_key(namespace, &args[1], &args[2]).map(Value::String)
        }
        "validate_dependency_frontier" => validate_dependency_frontier(&args[0]),
        "materialize_dependency_frontier" => {
            let kwargs = case
                .kwargs
                .as_object()
                .expect("frontier materializer kwargs are an object");
            materialize_dependency_frontier(
                kwargs.get("binding").expect("binding input is present"),
                kwargs
                    .get("queue_receipt")
                    .expect("queue receipt input is present"),
                kwargs
                    .get("rebind_receipt")
                    .expect("rebind receipt input is present"),
                kwargs
                    .get("source_main_readback_evidence_ref")
                    .and_then(Value::as_str)
                    .expect("source-main readback evidence input is text"),
                kwargs
                    .get("ordered_predecessor_evidence")
                    .expect("ordered predecessor evidence input is present"),
            )
        }
        "validate_dependency_frontier_transition" => {
            let kwargs = case
                .kwargs
                .as_object()
                .expect("frontier transition kwargs are an object");
            let readback = kwargs
                .get("origin_main_readback")
                .expect("origin-main readback input is present");
            let readback = SourceMainReadbackIdentity {
                commit_sha: readback["commit_sha"]
                    .as_str()
                    .expect("origin-main commit SHA is text")
                    .to_owned(),
                tree_sha: readback["tree_sha"]
                    .as_str()
                    .expect("origin-main tree SHA is text")
                    .to_owned(),
            };
            validate_dependency_frontier_transition(
                &args[0],
                &args[1],
                kwargs
                    .get("queue_receipt")
                    .expect("queue receipt input is present"),
                kwargs
                    .get("rebind_receipt")
                    .expect("rebind receipt input is present"),
                &readback,
                kwargs
                    .get("ordered_oracle")
                    .expect("ordered oracle input is present"),
            )
        }
        "after_binding_transaction" => after_binding_transaction(&args[0]).map(Value::String),
        api => panic!("unmapped frozen frontier API {api}"),
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
                canonical_json_bytes(&actual).expect("frozen frontier output has canonical bytes");
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
    serde_json::from_str(GOLDEN).expect("frozen CPython 3.12.3 frontier golden parses")
}

#[cfg(unix)]
#[test]
fn frontier_apis_match_all_frozen_cpython_records_hashes_and_errors() {
    let golden = frozen_golden();
    assert_eq!(golden.cases.len(), 23);
    let mut accepted = 0;
    let mut rejected = 0;
    for case in &golden.cases {
        if verify_case(case) {
            accepted += 1;
        } else {
            rejected += 1;
        }
    }
    assert_eq!(accepted, 8);
    assert_eq!(rejected, 15);
}

#[cfg(not(unix))]
#[test]
fn platform_independent_frontier_cases_match_frozen_cpython() {
    let golden = frozen_golden();
    assert_eq!(golden.cases.len(), 23);
    let portable_cases = golden
        .cases
        .iter()
        .filter(|case| {
            matches!(
                (case.name.as_str(), case.api.as_str()),
                ("key", "frontier_key")
                    | ("transaction-id", "after_binding_transaction")
                    | ("missing", "validate_dependency_frontier")
            )
        })
        .collect::<Vec<_>>();
    assert_eq!(portable_cases.len(), 3);
    let mut accepted = 0;
    let mut rejected = 0;
    for case in portable_cases {
        if verify_case(case) {
            accepted += 1;
        } else {
            rejected += 1;
        }
    }
    assert_eq!(accepted, 2);
    assert_eq!(rejected, 1);
}

#[test]
fn frontier_materialization_accepts_a_host_absolute_namespace() {
    let golden = frozen_golden();
    let materializer = golden
        .cases
        .iter()
        .find(|case| case.name == "pending-materializer")
        .expect("valid pending materializer inputs are present");
    let kwargs = materializer
        .kwargs
        .as_object()
        .expect("frontier materializer kwargs are an object");
    let namespace = std::env::current_dir()
        .expect("test working directory is available")
        .to_string_lossy()
        .into_owned();
    assert!(Path::new(&namespace).is_absolute());

    let binding = kwargs.get("binding").expect("binding input is present");
    let mut queue = kwargs
        .get("queue_receipt")
        .expect("queue receipt input is present")
        .clone();
    let publication = queue["source_publication_identity"].clone();
    queue["source_namespace"] = Value::String(namespace.clone());
    let queue_body = format!(
        "{}|{}|{}|{}|{}|{}",
        namespace,
        binding["candidate_sha"]
            .as_str()
            .expect("candidate SHA is text"),
        binding["tree_sha"].as_str().expect("tree SHA is text"),
        binding["input_digest"]
            .as_str()
            .expect("input digest is text"),
        publication["merge_commit_sha"]
            .as_str()
            .expect("merge commit is text"),
        publication["merge_tree_sha"]
            .as_str()
            .expect("merge tree is text"),
    );
    let queue_key = format!("queue-key:{}", sha256_hex(queue_body.as_bytes()));
    queue["enqueue_once_key"] = Value::String(queue_key.clone());
    let expected_frontier_key = format!(
        "frontier-key:{}",
        queue_key
            .strip_prefix("queue-key:")
            .expect("queue key has its schema prefix")
    );
    let expected_frontier_id = format!("frontier:{}", sha256_hex(expected_frontier_key.as_bytes()));
    let frontier = materialize_dependency_frontier(
        binding,
        &queue,
        kwargs
            .get("rebind_receipt")
            .expect("rebind receipt input is present"),
        kwargs["source_main_readback_evidence_ref"]
            .as_str()
            .expect("source-main readback evidence is text"),
        kwargs
            .get("ordered_predecessor_evidence")
            .expect("ordered predecessor evidence input is present"),
    )
    .expect("host-absolute namespace is accepted by the frontier materializer");
    assert_eq!(
        frontier["source_namespace"].as_str(),
        Some(namespace.as_str())
    );
    assert_eq!(
        frontier["frontier_key"].as_str(),
        Some(expected_frontier_key.as_str())
    );
    assert_eq!(
        frontier["frontier_id"].as_str(),
        Some(expected_frontier_id.as_str())
    );
    assert_eq!(frontier["frontier_state"].as_str(), Some("pending"));
}
