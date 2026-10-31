// @dependency-start
// contract test
// responsibility Verifies fresh-clone projection aggregation, owner callback forwarding, callback failure order, and frozen packet identity.
// upstream implementation ../src/update_lifecycle_contract.rs owns the native lifecycle aggregate and callback boundary.
// upstream implementation ../src/artifacts/artifact_identity.rs owns canonical packet bytes.
// upstream test ../../../../../tests/fixtures/update_lifecycle/freshclone_python_golden.json freezes the actual old-owner callback outputs and replay oracle.
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use agent_canon::update_lifecycle_contract::{
    materialize_fresh_clone_source_projection_packet, FreshCloneSourceProjectionError,
    SourceProjectionGateOwnerApis,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::cell::RefCell;
use std::path::{Path, PathBuf};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/freshclone_python_golden.json");

#[derive(Debug, Clone, PartialEq, Eq)]
struct OwnerCallbackSentinel {
    owner: String,
    message: String,
}

fn field<'a>(value: &'a Value, key: &str) -> &'a Value {
    value.get(key).expect("frozen fresh-clone field is present")
}

fn text(value: &Value) -> &str {
    value.as_str().expect("frozen fresh-clone value is text")
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn recorded_source_root(golden: &Value) -> PathBuf {
    Path::new(text(field(golden, "source_path")))
        .ancestors()
        .nth(4)
        .expect("old Python lifecycle source has its repository root")
        .to_path_buf()
}

fn invoke_with_recorded_callbacks(
    golden: &Value,
    source_root: &Path,
    callback_order: &RefCell<Vec<String>>,
    failing_owner: Option<&str>,
) -> Result<Value, FreshCloneSourceProjectionError<OwnerCallbackSentinel, OwnerCallbackSentinel>> {
    let owner_calls = field(golden, "actual_owner_callback_calls")
        .as_array()
        .expect("old owner callback records are an array");
    let g2_call = &owner_calls[0];
    let g3_call = &owner_calls[1];
    let g2_arguments = field(g2_call, "arguments").clone();
    let g3_arguments = field(g3_call, "arguments").clone();
    let g2_output = field(g2_call, "returned").clone();
    let g3_output = field(g3_call, "returned").clone();
    let error_records = field(golden, "callback_error_order")
        .as_array()
        .expect("owner callback error records are an array");
    let sentinel = |owner: &str| {
        let record = error_records
            .iter()
            .find(|record| text(field(record, "failing_owner")) == owner)
            .expect("the old oracle freezes each owner callback failure");
        OwnerCallbackSentinel {
            owner: owner.to_owned(),
            message: text(field(record, "message")).to_owned(),
        }
    };
    let g2_error = sentinel("G2");
    let g3_error = sentinel("G3");

    let g2_callback = |g1_gate: &Value,
                       candidate_sha: &str,
                       tree_sha: &str,
                       check_results: &[Value]|
     -> Result<Value, OwnerCallbackSentinel> {
        callback_order.borrow_mut().push("G2".to_owned());
        let actual_arguments = json!({
            "g1_gate": g1_gate,
            "candidate_sha": candidate_sha,
            "tree_sha": tree_sha,
            "check_results": check_results,
        });
        assert_eq!(actual_arguments, g2_arguments, "old G2 callback arguments");
        if failing_owner == Some("G2") {
            return Err(g2_error.clone());
        }
        Ok(g2_output.clone())
    };
    let g3_callback = |lifecycle: &Value,
                       candidate_cas_receipt: &Value,
                       source_main_rebind_receipt: &Value,
                       upstream_gate_verdicts: &[Value]|
     -> Result<Value, OwnerCallbackSentinel> {
        callback_order.borrow_mut().push("G3".to_owned());
        let actual_arguments = json!({
            "lifecycle": lifecycle,
            "candidate_cas_receipt": candidate_cas_receipt,
            "source_main_rebind_receipt": source_main_rebind_receipt,
            "upstream_gate_verdicts": upstream_gate_verdicts,
        });
        assert_eq!(actual_arguments, g3_arguments, "old G3 callback arguments");
        if failing_owner == Some("G3") {
            return Err(g3_error.clone());
        }
        Ok(g3_output.clone())
    };
    let check_ids = field(golden, "g2_check_ids")
        .as_array()
        .expect("old G2 check IDs are an array")
        .iter()
        .map(|check_id| text(check_id).to_owned())
        .collect::<Vec<_>>();
    let gate_owner_apis = SourceProjectionGateOwnerApis {
        generated_completeness_check_ids: &check_ids,
        materialize_generated_completeness_receipt: &g2_callback,
        materialize_pr_identity_gate: &g3_callback,
    };
    let inputs = field(golden, "inputs");
    materialize_fresh_clone_source_projection_packet(
        text(field(inputs, "candidate_sha")),
        text(field(inputs, "candidate_tree_sha")),
        text(field(inputs, "publication_sha")),
        text(field(inputs, "publication_tree_sha")),
        source_root,
        &gate_owner_apis,
    )
}

#[test]
fn fresh_clone_projection_matches_recorded_owner_calls_packet_bytes_and_hash() {
    let golden: Value = serde_json::from_str(GOLDEN)
        .expect("frozen actual CPython and owner callback oracle parses");
    let source_root = recorded_source_root(&golden);
    let callback_order = RefCell::new(Vec::new());
    let packet = invoke_with_recorded_callbacks(&golden, &source_root, &callback_order, None)
        .expect("the recorded actual owner outputs validate the fresh-clone packet");
    let replay = field(&golden, "frozen_callback_replay");
    assert_eq!(packet, *field(replay, "packet"));

    let gates = field(&packet, "source_gate_verdicts")
        .as_array()
        .expect("source projection packet gates are an array");
    assert_eq!(
        gates
            .iter()
            .map(|gate| text(field(gate, "gate_id")))
            .collect::<Vec<_>>(),
        ["G1", "G2", "G3"]
    );
    let expected_order = field(replay, "call_order")
        .as_array()
        .expect("frozen callback order is an array")
        .iter()
        .map(|label| {
            text(label)
                .split(':')
                .next()
                .expect("owner label has a prefix")
                .to_owned()
        })
        .collect::<Vec<_>>();
    assert_eq!(
        callback_order.borrow().as_slice(),
        expected_order.as_slice()
    );

    let old_calls = field(&golden, "actual_owner_callback_calls")
        .as_array()
        .expect("actual owner callback records are an array");
    let g2_check_results = field(field(&old_calls[0], "arguments"), "check_results")
        .as_array()
        .expect("frozen G2 check results are an array");
    assert_eq!(
        g2_check_results
            .iter()
            .map(|result| text(field(result, "check_id")))
            .collect::<Vec<_>>(),
        field(&golden, "g2_check_ids")
            .as_array()
            .expect("frozen G2 check IDs are an array")
            .iter()
            .map(|check_id| text(check_id))
            .collect::<Vec<_>>()
    );

    let bytes =
        canonical_json_bytes(&packet).expect("frozen fresh-clone packet has canonical bytes");
    assert_eq!(
        bytes,
        text(field(replay, "canonical_utf8")).as_bytes(),
        "canonical packet bytes"
    );
    assert_eq!(
        sha256_hex(&bytes),
        text(field(replay, "sha256")),
        "canonical packet digest"
    );
}

#[test]
fn fresh_clone_projection_propagates_owner_errors_without_later_callbacks() {
    let golden: Value = serde_json::from_str(GOLDEN)
        .expect("frozen actual CPython and owner callback oracle parses");
    let source_root = recorded_source_root(&golden);
    let error_records = field(&golden, "callback_error_order")
        .as_array()
        .expect("frozen callback error-order records are an array");

    for error_record in error_records {
        let failing_owner = text(field(error_record, "failing_owner"));
        let callback_order = RefCell::new(Vec::new());
        let error = invoke_with_recorded_callbacks(
            &golden,
            &source_root,
            &callback_order,
            Some(failing_owner),
        )
        .expect_err("the supplied owner callback error propagates");
        let expected_order = field(error_record, "call_order")
            .as_array()
            .expect("frozen callback error order is an array")
            .iter()
            .map(|owner| text(owner).to_owned())
            .collect::<Vec<_>>();
        assert_eq!(callback_order.borrow().as_slice(), expected_order);
        let expected = OwnerCallbackSentinel {
            owner: failing_owner.to_owned(),
            message: text(field(error_record, "message")).to_owned(),
        };
        assert_eq!(
            text(field(error_record, "exception_class")),
            "OwnerCallbackSentinel"
        );
        match (failing_owner, error) {
            ("G2", FreshCloneSourceProjectionError::G2Owner(actual))
            | ("G3", FreshCloneSourceProjectionError::G3Owner(actual)) => {
                assert_eq!(actual, expected);
            }
            _ => panic!("callback error origin differs for {failing_owner}"),
        }
    }
}
