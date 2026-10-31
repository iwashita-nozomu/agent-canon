// @dependency-start
// contract test
// responsibility Verifies snapshot, evidence identity, and checkpoint receipt validation against frozen CPython records.
// upstream implementation ../src/update_lifecycle_contract.rs owns the native lifecycle validators.
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical compact JSON bytes.
// upstream test ../../../../../tests/fixtures/update_lifecycle/records_python_golden.json freezes CPython 3.12.3 inputs, outputs, and errors.
// @dependency-end

use agent_canon::update_lifecycle_contract::{
    validate_checkpoint_receipt, validate_evidence_identity, validate_snapshot,
    LifecycleContractError,
};
use serde_json::Value;

#[cfg(unix)]
use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
#[cfg(unix)]
use sha2::{Digest, Sha256};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/records_python_golden.json");

fn golden() -> Value {
    serde_json::from_str(GOLDEN).expect("frozen CPython 3.12.3 record golden parses")
}

fn case_input(golden: &Value, name: &str) -> Value {
    golden["cases"]
        .as_array()
        .expect("frozen record cases are an array")
        .iter()
        .find(|case| case["name"].as_str() == Some(name))
        .unwrap_or_else(|| panic!("frozen record case {name} exists"))["input"]
        .clone()
}

#[cfg(unix)]
fn invoke(api: &str, input: &Value) -> Result<Value, LifecycleContractError> {
    match api {
        "validate_snapshot" => validate_snapshot(input),
        "validate_evidence_identity" => validate_evidence_identity(input),
        "validate_checkpoint_receipt" => validate_checkpoint_receipt(input),
        other => panic!("unmapped frozen lifecycle API {other}"),
    }
}

#[cfg(unix)]
fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[cfg(unix)]
#[test]
fn record_validators_match_frozen_cpython_outputs_bytes_hashes_and_errors() {
    let golden = golden();
    assert_eq!(
        golden["source"].as_str(),
        Some("06e720e0190c4e803efbdef3920d283a213c1f76")
    );
    assert!(golden["python"]
        .as_str()
        .is_some_and(|version| version.starts_with("3.12.")));
    assert_eq!(golden["host_path_flavor"].as_str(), Some("POSIX"));
    assert_eq!(
        sha256_hex(GOLDEN.as_bytes()),
        "6e25123b5f099fe2a2aa73f5ce41302f8084c79235412a98ec05c666e58c07ea"
    );

    let cases = golden["cases"]
        .as_array()
        .expect("frozen record cases are an array");
    assert_eq!(cases.len(), 28);
    let mut accepted = 0;
    let mut rejected = 0;
    for case in cases {
        let name = case["name"].as_str().expect("frozen case name is text");
        let api = case["api"].as_str().expect("frozen API name is text");
        match (invoke(api, &case["input"]), case.get("output"), case.get("error")) {
            (Ok(actual), Some(expected), None) => {
                accepted += 1;
                assert_eq!(actual, *expected, "validated record for {name}");
                let bytes = canonical_json_bytes(&actual)
                    .expect("accepted frozen record has canonical JSON bytes");
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
    assert_eq!(accepted, 6);
    assert_eq!(rejected, 22);
}

#[test]
fn snapshot_and_evidence_accept_host_absolute_paths_without_resolution() {
    let golden = golden();
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("clock is after the Unix epoch")
        .as_nanos();
    let namespace = std::env::current_dir()
        .expect("current directory is available")
        .join(format!(
            "agent-canon-unmaterialized-lifecycle-path-{}-{nonce}",
            std::process::id()
        ));
    assert!(namespace.is_absolute());
    assert!(!namespace.exists(), "test namespace remains unmaterialized");
    let namespace = namespace
        .to_str()
        .expect("host test path is representable as JSON text")
        .to_owned();

    let mut snapshot = case_input(&golden, "snapshot-valid-posix-absolute-path");
    snapshot["source_namespace"] = Value::String(namespace.clone());
    assert_eq!(
        validate_snapshot(&snapshot).expect("host absolute namespace validates"),
        snapshot
    );

    let mut evidence = case_input(&golden, "evidence-valid");
    evidence["producer_path"] = Value::String(namespace);
    assert_eq!(
        validate_evidence_identity(&evidence).expect("host absolute producer path validates"),
        evidence
    );
}

#[test]
fn relative_paths_keep_the_python_error_order_on_every_host() {
    let golden = golden();
    let snapshot = case_input(&golden, "snapshot-nonabsolute-path-before-invalid-base");
    let error = validate_snapshot(&snapshot).expect_err("relative snapshot path is rejected");
    assert_eq!(error.code, "lifecycle:path_not_absolute");
    assert_eq!(error.detail, "snapshot.source_namespace");

    let evidence = case_input(&golden, "evidence-relative-path-before-invalid-time");
    let error =
        validate_evidence_identity(&evidence).expect_err("relative evidence path is rejected");
    assert_eq!(error.code, "lifecycle:path_not_absolute");
    assert_eq!(error.detail, "evidence_identity.producer_path");
}
