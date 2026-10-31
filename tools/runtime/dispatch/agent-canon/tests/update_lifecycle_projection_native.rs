// @dependency-start
// contract test
// responsibility Verifies pure source projection packet validation and materialization against frozen CPython inputs, canonical bytes, hashes, and errors.
// upstream implementation ../src/update_lifecycle_contract.rs owns source projection packet lifecycle APIs.
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical compact JSON bytes.
// upstream test ../../../../../tests/fixtures/update_lifecycle/projection_python_golden.json freezes the independent oracle.
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use agent_canon::update_lifecycle_contract::{
    materialize_source_projection_packet, validate_source_projection_packet, LifecycleContractError,
};
use serde_json::Value;
use sha2::{Digest, Sha256};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/projection_python_golden.json");

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn field<'a>(value: &'a Value, key: &str) -> &'a Value {
    value.get(key).expect("frozen projection field is present")
}

fn invoke(api: &str, input: &Value) -> Result<Value, LifecycleContractError> {
    match api {
        "validate_source_projection_packet" => validate_source_projection_packet(input),
        "materialize_source_projection_packet" => {
            let gates = field(input, "source_gate_verdicts")
                .as_array()
                .expect("materializer gate inputs are an array");
            let predecessors = field(input, "ordered_predecessor_evidence")
                .as_array()
                .expect("materializer predecessor inputs are an array");
            let acceptance_evidence_ref = field(input, "acceptance_evidence_ref")
                .as_str()
                .expect("materializer acceptance evidence input is text");
            materialize_source_projection_packet(
                field(input, "binding"),
                field(input, "source_main_rebind_receipt"),
                field(input, "candidate_cas_receipt"),
                field(input, "pull_request_lifecycle"),
                field(input, "publication_readback_receipt"),
                gates,
                predecessors,
                acceptance_evidence_ref,
            )
        }
        other => panic!("unmapped frozen source projection API {other}"),
    }
}

#[test]
fn source_projection_apis_match_frozen_cpython_records_bytes_hashes_and_errors() {
    let golden: Value = serde_json::from_str(GOLDEN)
        .expect("frozen CPython 3.12.3 source projection oracle parses");
    let cases = field(&golden, "cases")
        .as_array()
        .expect("frozen source projection cases are an array");
    assert_eq!(cases.len(), 11);

    let mut accepted = 0;
    let mut rejected = 0;
    for case in cases {
        let name = field(case, "name")
            .as_str()
            .expect("frozen case name is text");
        let api = field(case, "api")
            .as_str()
            .expect("frozen API name is text");
        let input = field(case, "input");
        match (invoke(api, input), case.get("output"), case.get("error")) {
            (Ok(actual), Some(expected), None) => {
                accepted += 1;
                assert_eq!(actual, *expected, "output for {name}");
                let bytes = canonical_json_bytes(&actual)
                    .expect("accepted source projection has canonical bytes");
                assert_eq!(
                    bytes,
                    field(case, "canonical_utf8")
                        .as_str()
                        .expect("accepted case freezes canonical bytes")
                        .as_bytes(),
                    "canonical bytes for {name}"
                );
                assert_eq!(
                    sha256_hex(&bytes),
                    field(case, "sha256")
                        .as_str()
                        .expect("accepted case freezes its SHA-256"),
                    "canonical digest for {name}"
                );
            }
            (Err(actual), None, Some(expected)) => {
                rejected += 1;
                assert_eq!(
                    field(expected, "exception_class").as_str(),
                    Some("LifecycleContractError"),
                    "exception class for {name}"
                );
                let code = field(expected, "code")
                    .as_str()
                    .expect("frozen error code is text");
                let detail = field(expected, "detail")
                    .as_str()
                    .expect("frozen error detail is text");
                assert_eq!(actual.code, code, "error code for {name}");
                assert_eq!(actual.detail, detail, "error detail for {name}");
                let message = if detail.is_empty() {
                    code.to_owned()
                } else {
                    format!("{code}:{detail}")
                };
                assert_eq!(actual.to_string(), message, "error message for {name}");
            }
            (actual, output, error) => panic!(
                "fixture/API result shape differs for {name}: result={}, output={}, error={}",
                actual.as_ref().map(|_| "accepted").unwrap_or("rejected"),
                output.is_some(),
                error.is_some()
            ),
        }
    }
    assert_eq!(accepted, 2);
    assert_eq!(rejected, 9);
}

#[test]
fn predecessor_numbers_preserve_python_equality_before_final_canonicalization() {
    let golden: Value = serde_json::from_str(GOLDEN)
        .expect("frozen CPython 3.12.3 source projection oracle parses");
    let cases = field(&golden, "cases")
        .as_array()
        .expect("frozen source projection cases are an array");
    let valid_case = cases
        .iter()
        .find(|case| field(case, "name").as_str() == Some("valid-packet"))
        .expect("valid source projection packet is frozen");
    let mut float_packet = field(valid_case, "input").clone();
    float_packet["ordered_predecessor_evidence"][0]["queue_number"] = serde_json::json!(388.0);
    let error = validate_source_projection_packet(&float_packet)
        .expect_err("388.0 matches locally, then canonical JSON rejects the float");
    assert_eq!(error.code, "artifact_identity:float_forbidden");
    assert_eq!(error.detail, "");

    let mut bool_packet = field(valid_case, "input").clone();
    bool_packet["ordered_predecessor_evidence"][0]["queue_number"] = serde_json::json!(true);
    let error = validate_source_projection_packet(&bool_packet)
        .expect_err("true is not the Python integer value 388");
    assert_eq!(error.code, "frontier:predecessor_order_invalid");
    assert_eq!(error.detail, "");
}
