//! Native G6 close-agent owner composition.
// @dependency-start
// contract implementation
// responsibility Owns G6 close-agent lifecycle policy while composing existing lifecycle receipt and terminal-token APIs.
// upstream implementation update_lifecycle_contract.rs owns lifecycle receipt, gate, and terminal-token primitives
// upstream design ../../../../../documents/agent-canon/agent-canon-update-route.md owns lifecycle identity meaning
// downstream test ../tests/update_lifecycle_g6_native.rs freezes the old Python G6 owner output and errors
// @dependency-end

use crate::artifacts::artifact_identity::canonical_json_bytes;
use crate::update_lifecycle_contract::{
    binding_identity,
    materialize_close_agent_tool_call as materialize_terminal_close_agent_tool_call,
    materialize_gate_verdict, validate_cleanup_proof, validate_descendant_close_receipt,
    validate_durable_handback, validate_gate_chain, validate_record_binding,
    validate_reservation_release_receipt, CloseAgentToolCallInput, GateVerdictInput,
    LifecycleContractError,
};
use serde_json::Value as JsonValue;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

const G6_LOGICAL_OWNER_PATH: &str =
    "tools/agent/orchestration/tool_calls.py#materialize_close_agent_tool_call";
const G6_MATERIALIZATION_SCHEMA: &str = "agent-canon.close-agent-materialization.v1";
const G1_G5_GATE_IDS: &[&str] = &["G1", "G2", "G3", "G4", "G5"];

#[derive(Debug, Clone, Copy)]
pub struct CloseAgentLifecycleEvidence<'a> {
    pub gate_verdicts: &'a [JsonValue],
    pub cleanup_proof: &'a JsonValue,
    pub durable_handback: &'a JsonValue,
    pub descendant_close_receipts: &'a [JsonValue],
    pub reservation_release_receipts: &'a [JsonValue],
}

#[derive(Debug, Clone, Copy)]
pub struct CloseAgentLifecycleOwnerInput<'a> {
    pub source_root: &'a str,
    pub run_id: &'a str,
    pub agent_id: &'a str,
    pub evidence: CloseAgentLifecycleEvidence<'a>,
}

fn close_agent_error(code: &str) -> LifecycleContractError {
    LifecycleContractError {
        code: code.to_owned(),
        detail: String::new(),
    }
}

fn canonical_sha256(value: &JsonValue) -> Result<String, LifecycleContractError> {
    let bytes = canonical_json_bytes(value).map_err(LifecycleContractError::from)?;
    Ok(Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

pub fn materialize_close_agent_tool_call(
    input: CloseAgentLifecycleOwnerInput<'_>,
) -> Result<JsonValue, LifecycleContractError> {
    let handback = validate_durable_handback(input.evidence.durable_handback)?;
    let handback_binding = handback
        .get("binding")
        .expect("validated durable handback has a binding");
    let checked_binding = validate_record_binding(handback_binding)?;
    let gates = validate_gate_chain(input.evidence.gate_verdicts, Some(G1_G5_GATE_IDS), true)?;
    let descendants = input
        .evidence
        .descendant_close_receipts
        .iter()
        .map(validate_descendant_close_receipt)
        .collect::<Result<Vec<_>, _>>()?;
    let reservations = input
        .evidence
        .reservation_release_receipts
        .iter()
        .map(validate_reservation_release_receipt)
        .collect::<Result<Vec<_>, _>>()?;

    let declared_descendants = handback["descendant_ids"]
        .as_array()
        .expect("validated handback descendant IDs are a sequence")
        .iter()
        .map(|value| {
            value
                .as_str()
                .expect("validated descendant ID is text")
                .to_owned()
        })
        .collect::<BTreeSet<_>>();
    let observed_descendants = descendants
        .iter()
        .map(|receipt| {
            receipt["agent_id"]
                .as_str()
                .expect("validated descendant agent ID is text")
                .to_owned()
        })
        .collect::<BTreeSet<_>>();
    if observed_descendants != declared_descendants {
        return Err(close_agent_error("close_agent:unknown_descendant"));
    }

    let declared_reservations = handback["reservation_ids"]
        .as_array()
        .expect("validated handback reservation IDs are a sequence")
        .iter()
        .map(|value| {
            value
                .as_str()
                .expect("validated reservation ID is text")
                .to_owned()
        })
        .collect::<BTreeSet<_>>();
    let observed_reservations = reservations
        .iter()
        .map(|receipt| {
            receipt["reservation_id"]
                .as_str()
                .expect("validated reservation ID is text")
                .to_owned()
        })
        .collect::<BTreeSet<_>>();
    if observed_reservations != declared_reservations {
        return Err(close_agent_error("close_agent:reservation_leak"));
    }

    let expected_identity = binding_identity(&checked_binding)?;
    if handback_binding != &checked_binding {
        return Err(close_agent_error("close_agent:identity_mismatch"));
    }
    if handback["agent_id"].as_str() != Some(input.agent_id) {
        return Err(close_agent_error("close_agent:agent_identity_mismatch"));
    }
    let durable_handback_evidence_ref = handback["evidence_ref"]
        .as_str()
        .expect("validated durable handback evidence reference is text");
    for receipt in descendants.iter().chain(&reservations) {
        if binding_identity(&receipt["binding"])? != expected_identity {
            return Err(close_agent_error("close_agent:identity_mismatch"));
        }
        if receipt["durable_handback_evidence_ref"].as_str() != Some(durable_handback_evidence_ref)
        {
            return Err(close_agent_error("close_agent:durable_handback_mismatch"));
        }
    }

    let descendants_closed_evidence_ref = format!(
        "evidence:{}",
        canonical_sha256(&JsonValue::Array(descendants.clone()))?
    );
    let reservations_released_evidence_ref = format!(
        "evidence:{}",
        canonical_sha256(&JsonValue::Array(reservations.clone()))?
    );

    let cleanup = validate_cleanup_proof(input.evidence.cleanup_proof)?;
    if binding_identity(&cleanup["binding"])? != expected_identity {
        return Err(close_agent_error("close_agent:identity_mismatch"));
    }
    let gate_refs = gates
        .iter()
        .map(|gate| {
            gate["binding"]["evidence_ref"]
                .as_str()
                .expect("validated gate evidence reference is text")
                .to_owned()
        })
        .collect::<Vec<_>>();
    if cleanup["remote_readback_evidence_ref"].as_str() != gate_refs.get(4).map(String::as_str) {
        return Err(close_agent_error(
            "close_agent:cleanup_before_remote_readback",
        ));
    }

    let mut ordered_input_evidence_refs = gate_refs;
    ordered_input_evidence_refs.push(durable_handback_evidence_ref.to_owned());
    ordered_input_evidence_refs.push(descendants_closed_evidence_ref.clone());
    ordered_input_evidence_refs.push(reservations_released_evidence_ref.clone());
    ordered_input_evidence_refs.push(
        cleanup["evidence_ref"]
            .as_str()
            .expect("validated cleanup evidence reference is text")
            .to_owned(),
    );
    let output_digest = format!(
        "sha256:{}",
        canonical_sha256(&serde_json::json!({
            "durable_handback": handback.clone(),
            "descendants": descendants.clone(),
            "reservations": reservations.clone(),
            "cleanup": cleanup.clone(),
        }))?
    );
    let owner = format!(
        "{}/{}",
        input.source_root.trim_end_matches('/'),
        G6_LOGICAL_OWNER_PATH
    );
    let g6_gate = materialize_gate_verdict(&GateVerdictInput {
        binding: checked_binding.clone(),
        gate_id: "G6".to_owned(),
        ordered_input_evidence_refs,
        invariant: "nested_lifecycle_cleanup".to_owned(),
        output_digest,
        owner,
        verdict: "pass".to_owned(),
        retry_reason: None,
        next_checkpoint: None,
    })?;

    let mut gate_verdicts = gates;
    gate_verdicts.push(g6_gate.clone());
    let close_agent_tool_call =
        materialize_terminal_close_agent_tool_call(CloseAgentToolCallInput {
            binding: &checked_binding,
            run_id: input.run_id,
            agent_id: input.agent_id,
            gate_verdicts: &gate_verdicts,
            cleanup_proof: &cleanup,
            durable_handback: &handback,
            descendants_closed_evidence_ref: &descendants_closed_evidence_ref,
            reservations_released_evidence_ref: &reservations_released_evidence_ref,
            completed_but_open: false,
            unknown_descendants: false,
            reservation_leak: false,
        })?;

    Ok(serde_json::json!({
        "schema": G6_MATERIALIZATION_SCHEMA,
        "g6_gate": g6_gate,
        "descendants_closed_evidence_ref": descendants_closed_evidence_ref,
        "reservations_released_evidence_ref": reservations_released_evidence_ref,
        "close_agent_tool_call": close_agent_tool_call,
    }))
}
