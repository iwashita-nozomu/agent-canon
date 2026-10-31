// @dependency-start
// contract test
// responsibility Verifies native lifecycle binding identity and gate-verdict mechanics against frozen Python output.
// upstream implementation ../src/update_lifecycle_contract.rs owns the native pure API
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical JSON bytes
// upstream design ../../../../../documents/agent-canon/agent-canon-update-route.md owns lifecycle identity semantics
// downstream implementation ../../../../../tests/agent_tools/test_publication_integrator.py preserves gate replay and distinctness oracle purpose
// downstream test ../../../../../tests/fixtures/update_lifecycle/gates_python_golden.json preserves frozen Python bytes, digests, and failure codes
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use agent_canon::update_lifecycle_contract::{
    binding_identity, materialize_gate_verdict, validate_gate_chain, validate_gate_verdict,
    validate_record_binding, GateVerdictInput, LifecycleContractError, RecordBindingIdentity,
    TRANSACTION_STATES,
};
use serde_json::Value;
use sha2::{Digest, Sha256};

const PYTHON_GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/gates_python_golden.json");

fn gate_input(value: &Value) -> GateVerdictInput {
    let refs = value["ordered_input_evidence_refs"]
        .as_array()
        .expect("golden gate refs")
        .iter()
        .map(|reference| {
            reference
                .as_str()
                .expect("golden ref is a string")
                .to_string()
        })
        .collect();
    GateVerdictInput {
        binding: value["binding"].clone(),
        gate_id: value["gate_id"]
            .as_str()
            .expect("golden gate id")
            .to_string(),
        ordered_input_evidence_refs: refs,
        invariant: value["invariant"]
            .as_str()
            .expect("golden invariant")
            .to_string(),
        output_digest: value["output_digest"]
            .as_str()
            .expect("golden output digest")
            .to_string(),
        owner: value["owner"].as_str().expect("golden owner").to_string(),
        verdict: value["verdict"]
            .as_str()
            .expect("golden verdict")
            .to_string(),
        retry_reason: value["retry_reason"].as_str().map(str::to_string),
        next_checkpoint: value["next_checkpoint"].as_str().map(str::to_string),
    }
}

fn negative_result(case: &Value) -> Result<Value, LifecycleContractError> {
    let name = case["name"].as_str().expect("golden negative name");
    let input = &case["input"];
    match name {
        "order" | "identity" | "predecessor" | "not_passed" => {
            let gates = input.as_array().expect("golden chain input");
            let expected = case["kwargs"]
                .get("expected_gate_ids")
                .and_then(Value::as_array)
                .map(|values| {
                    values
                        .iter()
                        .map(|value| value.as_str().expect("gate id string").to_string())
                        .collect::<Vec<_>>()
                });
            let expected_refs = expected
                .as_ref()
                .map(|values| values.iter().map(String::as_str).collect::<Vec<_>>());
            let require_pass = case["kwargs"]
                .get("require_pass")
                .and_then(Value::as_bool)
                .unwrap_or(true);
            validate_gate_chain(gates, expected_refs.as_deref(), require_pass)
                .map(serde_json::Value::Array)
        }
        "owner" => validate_gate_verdict(input),
        "bool_not_int" | "unknown_binding_key" => validate_record_binding(input),
        other => panic!("unrecognized frozen negative case {other}"),
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[test]
fn frozen_python_gate_bytes_states_and_error_codes_match_native_api() {
    let golden: Value = serde_json::from_str(PYTHON_GOLDEN).expect("frozen Python fixture JSON");
    assert_eq!(
        golden["source"].as_str(),
        Some("e0ab183ecf880969a8c2e677efb6fe75facec942")
    );
    assert!(golden["python"]
        .as_str()
        .is_some_and(|value| value.starts_with("3.12.")));

    let expected_states = golden["transaction_states"]
        .as_array()
        .expect("golden state list")
        .iter()
        .map(|value| value.as_str().expect("state string"))
        .collect::<Vec<_>>();
    assert_eq!(TRANSACTION_STATES, expected_states.as_slice());

    let gate_cases = golden["gates"].as_array().expect("golden gate cases");
    assert_eq!(gate_cases.len(), 6);
    let first_binding = &gate_cases[0]["input"]["binding"];
    validate_record_binding(first_binding).expect("frozen binding validates");
    assert_eq!(
        binding_identity(first_binding).unwrap(),
        RecordBindingIdentity {
            transaction_id: format!("tx:{}", "1".repeat(64)),
            snapshot_id: format!("snapshot:{}", "2".repeat(64)),
            candidate_sha: "3".repeat(40),
            tree_sha: "4".repeat(40),
            input_digest: format!("sha256:{}", "5".repeat(64)),
            tool_id: "publication-integrator".to_string(),
            tool_version: "test.v1".to_string(),
        }
    );

    let mut outputs = Vec::with_capacity(gate_cases.len());
    let mut expected_gate_ids = Vec::with_capacity(gate_cases.len());
    for case in gate_cases {
        let input = &case["input"];
        expected_gate_ids.push(
            input["gate_id"]
                .as_str()
                .expect("golden gate id")
                .to_string(),
        );
        let output =
            materialize_gate_verdict(&gate_input(input)).expect("native gate materializes");
        assert_eq!(output, case["output"], "gate {}", input["gate_id"]);
        let canonical = canonical_json_bytes(&output).expect("native canonical serializer");
        let expected_bytes = case["canonical_utf8"]
            .as_str()
            .expect("frozen canonical UTF-8 bytes");
        assert_eq!(canonical.as_slice(), expected_bytes.as_bytes());
        assert_eq!(
            sha256_hex(&canonical),
            case["sha256"].as_str().expect("frozen output digest")
        );
        outputs.push(output);
    }
    let expected_gate_refs = expected_gate_ids
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    let chain = validate_gate_chain(&outputs, Some(&expected_gate_refs), true)
        .expect("frozen six-gate chain validates");
    assert_eq!(chain, outputs);

    let negatives = golden["negative_cases"]
        .as_array()
        .expect("frozen negative cases");
    assert_eq!(negatives.len(), 7);
    for case in negatives {
        let error = negative_result(case).expect_err(case["name"].as_str().expect("negative name"));
        assert_eq!(error.code, case["code"].as_str().expect("error code"));
        assert_eq!(error.detail, case["detail"].as_str().expect("error detail"));
    }
}

#[test]
fn gate_identity_is_distinct_and_replay_stable() {
    let golden: Value = serde_json::from_str(PYTHON_GOLDEN).expect("frozen Python fixture JSON");
    let gates = golden["gates"].as_array().expect("golden gate cases");
    let g1 = materialize_gate_verdict(&gate_input(&gates[0]["input"])).unwrap();
    let g3 = materialize_gate_verdict(&gate_input(&gates[2]["input"])).unwrap();
    let g5 = materialize_gate_verdict(&gate_input(&gates[4]["input"])).unwrap();
    let replay = materialize_gate_verdict(&gate_input(&gates[2]["input"])).unwrap();
    let refs = [&g1, &g3, &g5]
        .iter()
        .map(|gate| gate["binding"]["evidence_ref"].as_str().unwrap())
        .collect::<Vec<_>>();
    assert_eq!(
        refs.iter().collect::<std::collections::BTreeSet<_>>().len(),
        3
    );
    assert_eq!(replay["binding"]["evidence_ref"].as_str(), Some(refs[1]));
}

#[test]
fn lifecycle_datetime_parser_keeps_python_owner_input_forms() {
    let golden: Value = serde_json::from_str(PYTHON_GOLDEN).expect("frozen Python fixture JSON");
    let binding = &golden["gates"][0]["input"]["binding"];
    for timestamp in [
        "2026-07-18",
        "20260718T000000",
        "2026-W29-6T00:00:00Z",
        "2026-07-18T00:00:00.123456789+00:00",
        "2026-07-18 00:00:00",
    ] {
        let mut candidate = binding.clone();
        candidate["timing"]["started_at"] = serde_json::json!(timestamp);
        assert!(validate_record_binding(&candidate).is_ok(), "{timestamp}");
    }
    let mut invalid = binding.clone();
    invalid["timing"]["started_at"] = serde_json::json!("2026-02-30T00:00:00Z");
    let error = validate_record_binding(&invalid).unwrap_err();
    assert_eq!(error.code, "lifecycle:timestamp_invalid");
    assert_eq!(error.detail, "binding.timing.started_at");
}

#[test]
fn gate_chain_and_retry_options_preserve_the_owner_contract() {
    let golden: Value = serde_json::from_str(PYTHON_GOLDEN).unwrap();
    let valid = golden["gates"][0]["output"].clone();

    let mut failed = valid.clone();
    failed["verdict"] = serde_json::json!("fail");
    let chain = vec![failed.clone()];
    assert_eq!(
        validate_gate_chain(&chain, Some(&["G1"]), false).unwrap(),
        chain
    );
    let error = validate_gate_chain(&[failed], Some(&["G1"]), true).unwrap_err();
    assert_eq!(error.code, "lifecycle:gate_not_passed");
    assert!(error.detail.is_empty());

    let mut duplicated = valid.clone();
    let reference = duplicated["ordered_input_evidence_refs"][0].clone();
    duplicated["ordered_input_evidence_refs"] = serde_json::json!([reference, reference]);
    let error = validate_gate_verdict(&duplicated).unwrap_err();
    assert_eq!(error.code, "lifecycle:duplicate_value");
    assert_eq!(error.detail, "gate_verdict.ordered_input_evidence_refs");

    let mut retry = valid.clone();
    retry["verdict"] = serde_json::json!("retry");
    retry["retry_reason"] = serde_json::json!("owner-selected retry");
    assert_eq!(validate_gate_verdict(&retry).unwrap(), retry);
    retry["retry_reason"] = Value::Null;
    let error = validate_gate_verdict(&retry).unwrap_err();
    assert_eq!(error.code, "lifecycle:string_invalid");
    assert_eq!(error.detail, "gate_verdict.retry_reason");

    let mut nonretry = valid;
    nonretry["retry_reason"] = serde_json::json!("unexpected reason");
    let error = validate_gate_verdict(&nonretry).unwrap_err();
    assert_eq!(error.code, "lifecycle:retry_reason_forbidden");
    assert_eq!(error.detail, "gate_verdict");
}
