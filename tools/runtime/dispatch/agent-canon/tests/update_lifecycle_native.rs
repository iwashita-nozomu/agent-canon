// @dependency-start
// contract test
// responsibility Verifies native lifecycle binding identity and gate-verdict mechanics against the old owner contract.
// upstream implementation ../src/update_lifecycle_contract.rs owns the native pure API
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical JSON bytes
// upstream design ../../../../../documents/agent-canon/agent-canon-update-route.md owns lifecycle identity semantics
// downstream implementation ../../../../../tests/agent_tools/test_publication_integrator.py preserves gate replay and distinctness oracle purpose
// @dependency-end

use agent_canon::update_lifecycle_contract::{
    binding_identity, materialize_gate_verdict, validate_gate_chain, validate_gate_verdict,
    validate_record_binding, GateVerdictInput, LifecycleContractError, RecordBindingIdentity,
    TRANSACTION_STATES,
};
use serde_json::{json, Value};

fn binding() -> Value {
    json!({
        "transaction_id": format!("tx:{}", "1".repeat(64)),
        "snapshot_id": format!("snapshot:{}", "2".repeat(64)),
        "candidate_sha": "3".repeat(40),
        "tree_sha": "4".repeat(40),
        "input_digest": format!("sha256:{}", "5".repeat(64)),
        "tool_id": "publication-integrator",
        "tool_version": "test.v1",
        "evidence_ref": format!("evidence:{}", "6".repeat(64)),
        "evidence_digest": format!("sha256:{}", "7".repeat(64)),
        "timing": {
            "started_at": "2026-07-18T00:00:00Z",
            "finished_at": "2026-07-18T00:00:00Z",
            "last_attempt_at": "2026-07-18T00:00:00Z",
            "duration_ms": 0,
            "attempt": 1,
            "replayed": false
        }
    })
}

fn owner_for(gate_id: &str) -> &'static str {
    match gate_id {
        "G1" => "/repo/tools/repository/github/publication_integrator.py#resolve_publication_eligibility",
        "G2" => "/repo/tools/validation/ci/checks/check_agent_canon_pr.py#materialize_generated_completeness_receipt",
        "G3" => "/repo/tools/repository/github/github_publish.py#materialize_pr_identity_gate",
        "G4" => "/repo/tools/repository/workspace/repository_topic_clone.py#_ensure_branch",
        "G5" => "/repo/tools/repository/github/publication_integrator.py#integrate_publication",
        "G6" => "/repo/tools/agent/orchestration/tool_calls.py#materialize_close_agent_tool_call",
        _ => panic!("test requested an unknown gate"),
    }
}

fn invariant_for(gate_id: &str) -> &'static str {
    match gate_id {
        "G1" => "source_correctness",
        "G2" => "generated_completeness",
        "G3" => "pr_identity_cas",
        "G4" => "standalone_source_branch_integrity",
        "G5" => "remote_publication_readback",
        "G6" => "nested_lifecycle_cleanup",
        _ => panic!("test requested an unknown gate"),
    }
}

fn materialize(binding: &Value, gate_id: &str, refs: &[String], verdict: &str) -> Value {
    materialize_gate_verdict(&GateVerdictInput {
        binding: binding.clone(),
        gate_id: gate_id.to_string(),
        ordered_input_evidence_refs: refs.to_vec(),
        invariant: invariant_for(gate_id).to_string(),
        output_digest: format!("sha256:{}", "a".repeat(64)),
        owner: owner_for(gate_id).to_string(),
        verdict: verdict.to_string(),
        retry_reason: if verdict == "retry" {
            Some("retry after rebase".to_string())
        } else {
            None
        },
        next_checkpoint: None,
    })
    .unwrap()
}

fn evidence_ref(gate: &Value) -> String {
    gate["binding"]["evidence_ref"]
        .as_str()
        .unwrap()
        .to_string()
}

#[test]
fn transaction_state_vocabulary_and_binding_projection_are_stable() {
    assert_eq!(
        TRANSACTION_STATES,
        [
            "created",
            "prepared",
            "generated",
            "gates_ready",
            "reviewed",
            "pr_open",
            "pr_merged",
            "source_main_readback",
            "queue_enqueued",
            "frontier_accepted",
            "remote_readback",
            "durable_handback",
            "descendants_closed",
            "reservations_released",
            "cleanup_proven",
            "nested_lifecycle_cleanup",
            "closed",
            "failed",
            "successor_required",
        ]
        .as_slice()
    );
    let input = binding();
    let checked = validate_record_binding(&input).unwrap();
    assert_eq!(checked, input);
    assert_eq!(
        binding_identity(&checked).unwrap(),
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
}

#[test]
fn binding_validation_keeps_exact_field_and_python_integer_boundaries() {
    let mut extra = binding();
    extra["extra"] = json!("forbidden");
    let error = validate_record_binding(&extra).unwrap_err();
    assert_eq!(error.code, "lifecycle:field_forbidden");
    assert_eq!(error.detail, "binding:extra");

    let mut boolean_attempt = binding();
    boolean_attempt["timing"]["attempt"] = Value::Bool(true);
    let error = validate_record_binding(&boolean_attempt).unwrap_err();
    assert_eq!(error.code, "lifecycle:integer_invalid");
    assert_eq!(error.detail, "binding.timing.attempt");

    let mut bad_candidate = binding();
    bad_candidate["candidate_sha"] = json!("3".repeat(39));
    let error = validate_record_binding(&bad_candidate).unwrap_err();
    assert_eq!(error.code, "lifecycle:identity_invalid");
    assert_eq!(error.detail, "binding.candidate_sha");
}

#[test]
fn binding_time_validation_accepts_existing_iso_forms() {
    for timestamp in [
        "2026-07-18",
        "20260718T000000",
        "2026-W29-6T00:00:00Z",
        "2026-07-18T00:00:00.123456789+00:00",
        "2026-07-18 00:00:00",
    ] {
        let mut input = binding();
        input["timing"]["started_at"] = json!(timestamp);
        assert!(validate_record_binding(&input).is_ok(), "{timestamp}");
    }
    let mut invalid = binding();
    invalid["timing"]["started_at"] = json!("2026-02-30T00:00:00Z");
    let error = validate_record_binding(&invalid).unwrap_err();
    assert_eq!(error.code, "lifecycle:timestamp_invalid");
    assert_eq!(error.detail, "binding.timing.started_at");
}

#[test]
fn binding_time_validation_preserves_existing_isoformat_forms() {
    for timestamp in [
        "2026-07-18",
        "20260718T000000",
        "2026-W29-6T00:00:00Z",
        "2026-07-18T00:00:00.123456789+00:00",
        "2026-07-18 00:00:00",
    ] {
        let mut input = binding();
        input["timing"]["started_at"] = json!(timestamp);
        assert!(validate_record_binding(&input).is_ok(), "{timestamp}");
    }
    let mut invalid = binding();
    invalid["timing"]["started_at"] = json!("2026-02-30T00:00:00Z");
    let error = validate_record_binding(&invalid).unwrap_err();
    assert_eq!(error.code, "lifecycle:timestamp_invalid");
    assert_eq!(error.detail, "binding.timing.started_at");
}

#[test]
fn gate_identity_is_distinct_and_replay_stable() {
    let binding = binding();
    let seed = format!("evidence:{}", "8".repeat(64));
    let gates = [
        materialize(&binding, "G1", std::slice::from_ref(&seed), "pass"),
        materialize(&binding, "G3", std::slice::from_ref(&seed), "pass"),
        materialize(&binding, "G5", std::slice::from_ref(&seed), "pass"),
    ];
    let replay = materialize(&binding, "G3", std::slice::from_ref(&seed), "pass");
    let refs = gates.iter().map(evidence_ref).collect::<Vec<_>>();
    assert_eq!(
        refs.iter().collect::<std::collections::BTreeSet<_>>().len(),
        3
    );
    assert_eq!(evidence_ref(&replay), refs[1]);
    for gate in &gates {
        validate_gate_verdict(gate).unwrap();
    }
}

#[test]
fn gate_chain_preserves_predecessor_and_identity_invariants() {
    let binding = binding();
    let seed = format!("evidence:{}", "8".repeat(64));
    let g1 = materialize(&binding, "G1", std::slice::from_ref(&seed), "pass");
    let g1_ref = evidence_ref(&g1);
    let g2 = materialize(&binding, "G2", std::slice::from_ref(&g1_ref), "pass");
    let g2_ref = evidence_ref(&g2);
    let g3 = materialize(&binding, "G3", &[g1_ref.clone(), g2_ref.clone()], "pass");
    let g3_ref = evidence_ref(&g3);
    let g4 = materialize(&binding, "G4", std::slice::from_ref(&g3_ref), "pass");
    let g4_ref = evidence_ref(&g4);
    let g5 = materialize(&binding, "G5", std::slice::from_ref(&g4_ref), "pass");
    let g5_ref = evidence_ref(&g5);
    let g6 = materialize(
        &binding,
        "G6",
        &[g1_ref, g2_ref, g3_ref, g4_ref, g5_ref],
        "pass",
    );
    let chain = vec![g1.clone(), g2, g3, g4, g5, g6];
    assert!(validate_gate_chain(&chain, Some(&["G1", "G2", "G3", "G4", "G5", "G6"]), true).is_ok());

    let mut wrong_predecessor = chain.clone();
    wrong_predecessor[1]["ordered_input_evidence_refs"] =
        json!([format!("evidence:{}", "9".repeat(64))]);
    let error = validate_gate_chain(&wrong_predecessor[..2], None, true).unwrap_err();
    assert_eq!(error.code, "lifecycle:gate_predecessor_mismatch");

    let mut wrong_identity = chain[..2].to_vec();
    wrong_identity[1]["binding"]["candidate_sha"] = json!("f".repeat(40));
    let error = validate_gate_chain(&wrong_identity, None, true).unwrap_err();
    assert_eq!(error.code, "lifecycle:gate_identity_mismatch");

    let error = validate_gate_chain(&chain, Some(&["G2", "G1"]), true).unwrap_err();
    assert_eq!(error.code, "lifecycle:gate_order_invalid");
}

#[test]
fn gate_verdict_retry_fields_keep_existing_failure_semantics() {
    let binding = binding();
    let seed = format!("evidence:{}", "8".repeat(64));
    let retry = materialize(&binding, "G1", std::slice::from_ref(&seed), "retry");
    assert_eq!(retry["verdict"], "retry");
    assert_eq!(retry["retry_reason"], "retry after rebase");
    let mut invalid = retry;
    invalid["retry_reason"] = Value::Null;
    let error = validate_gate_verdict(&invalid).unwrap_err();
    assert_eq!(error.code, "lifecycle:string_invalid");
    assert_eq!(error.detail, "gate_verdict.retry_reason");
}
