// @dependency-start
// contract test
// responsibility Verifies G6 close-agent owner composition against the frozen old Python API oracle.
// upstream implementation ../src/agent_tool_calls.rs owns native G6 lifecycle policy.
// upstream implementation ../src/update_lifecycle_contract.rs owns terminal receipt and token primitives.
// upstream test ../../../../../tests/fixtures/update_lifecycle/g6_python_golden.json freezes direct old API premises and outputs.
// @dependency-end

use agent_canon::agent_tool_calls::{
    materialize_close_agent_tool_call, CloseAgentLifecycleEvidence, CloseAgentLifecycleOwnerInput,
    CloseAgentToolCallError,
};
use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use serde_json::Value;
use sha2::{Digest, Sha256};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/update_lifecycle/g6_python_golden.json");
const OLD_G6_SOURCE_SUFFIX: &str = "/tools/agent/orchestration/tool_calls.py";

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn path_child_mut<'a>(value: &'a mut Value, component: &Value) -> &'a mut Value {
    match component {
        Value::String(key) => value
            .as_object_mut()
            .and_then(|object| object.get_mut(key))
            .unwrap_or_else(|| panic!("fixture mutation object field {key} exists")),
        Value::Number(index) => {
            let index = index
                .as_u64()
                .and_then(|index| usize::try_from(index).ok())
                .expect("fixture mutation array index fits usize");
            value
                .as_array_mut()
                .and_then(|array| array.get_mut(index))
                .unwrap_or_else(|| panic!("fixture mutation array index {index} exists"))
        }
        other => panic!("unsupported fixture mutation path component {other}"),
    }
}

fn set_path(value: &mut Value, path: &[Value], replacement: Value) {
    let (head, tail) = path
        .split_first()
        .expect("fixture mutation path is nonempty");
    let child = path_child_mut(value, head);
    if tail.is_empty() {
        *child = replacement;
    } else {
        set_path(child, tail, replacement);
    }
}

fn apply_mutation(arguments: &mut Value, mutation: &Value) {
    if mutation.is_null() {
        return;
    }
    match mutation["operation"]
        .as_str()
        .expect("fixture mutation operation is text")
    {
        "composite" => {
            for nested in mutation["mutations"]
                .as_array()
                .expect("composite mutations are an array")
            {
                apply_mutation(arguments, nested);
            }
        }
        "set" => set_path(
            &mut arguments["evidence"],
            mutation["path"]
                .as_array()
                .expect("fixture mutation path is an array"),
            mutation["value"].clone(),
        ),
        "swap_gates" => {
            let indexes = mutation["indexes"]
                .as_array()
                .expect("gate swap indexes are an array")
                .iter()
                .map(|value| {
                    value
                        .as_u64()
                        .and_then(|index| usize::try_from(index).ok())
                        .expect("gate swap index fits usize")
                })
                .collect::<Vec<_>>();
            let gates = arguments["evidence"]["gate_verdicts"]
                .as_array_mut()
                .expect("fixture gate verdicts are an array");
            gates.swap(indexes[0], indexes[1]);
        }
        "drop_last_gate" => {
            arguments["evidence"]["gate_verdicts"]
                .as_array_mut()
                .expect("fixture gate verdicts are an array")
                .pop()
                .expect("fixture has a final gate");
        }
        "append_descendant" => {
            let mut receipt = arguments["evidence"]["descendant_close_receipts"][0].clone();
            let values = mutation["values"]
                .as_object()
                .expect("descendant mutation values are an object");
            let receipt_fields = receipt
                .as_object_mut()
                .expect("fixture descendant receipt is an object");
            for (key, value) in values {
                let _ = receipt_fields.insert(key.clone(), value.clone());
            }
            arguments["evidence"]["descendant_close_receipts"]
                .as_array_mut()
                .expect("fixture descendant receipts are an array")
                .push(receipt);
        }
        other => panic!("unmapped frozen G6 fixture mutation {other}"),
    }
}

fn invoke_g6(arguments: &Value, source_root: &str) -> Result<Value, CloseAgentToolCallError> {
    let evidence = &arguments["evidence"];
    let gate_verdicts = evidence["gate_verdicts"]
        .as_array()
        .expect("fixture gate verdicts are an array");
    materialize_close_agent_tool_call(CloseAgentLifecycleOwnerInput {
        source_root,
        run_id: arguments["run_id"].as_str().expect("run ID is text"),
        agent_id: arguments["agent_id"].as_str().expect("agent ID is text"),
        evidence: CloseAgentLifecycleEvidence {
            gate_verdicts,
            cleanup_proof: &evidence["cleanup_proof"],
            durable_handback: &evidence["durable_handback"],
            descendant_close_receipts: evidence["descendant_close_receipts"]
                .as_array()
                .expect("fixture descendant receipts are an array"),
            reservation_release_receipts: evidence["reservation_release_receipts"]
                .as_array()
                .expect("fixture reservation receipts are an array"),
        },
    })
}

fn python_error_class(error: &CloseAgentToolCallError) -> &'static str {
    match error {
        CloseAgentToolCallError::LifecycleContract(_) => "LifecycleContractError",
        CloseAgentToolCallError::ValueError(_) => "ValueError",
    }
}

#[test]
fn direct_g6_owner_cases_match_frozen_python_outputs_bytes_hashes_and_errors() {
    let golden: Value =
        serde_json::from_str(GOLDEN).expect("frozen G6 Python oracle fixture parses");
    assert_eq!(
        sha256_hex(GOLDEN.as_bytes()),
        "93c22d933ad71d43fca186c233542f7babdfbe7382ab01036af75c4382c5a2d6"
    );
    assert_eq!(
        golden["source"]["tool_calls_sha256"].as_str(),
        Some("09aadf364ac06f19aa5bdeb49b99db84a82c4b9deab800b1b0df7bd599ac2fc7")
    );
    assert_eq!(
        golden["source"]["fixture_sha256"].as_str(),
        Some("e2558586379dc142815a1e696d490ce2c821b305f596877a421180114d0be16a")
    );
    let tool_calls_path = golden["source"]["tool_calls_path"]
        .as_str()
        .expect("frozen old G6 source path is text");
    let source_root = tool_calls_path
        .strip_suffix(OLD_G6_SOURCE_SUFFIX)
        .expect("frozen old source path ends with the Python owner path");

    let direct_cases = golden["direct_g6_api_cases"]
        .as_array()
        .expect("direct G6 API cases are an array");
    assert_eq!(direct_cases.len(), 10);
    // Consumer expectations remain separate fixture metadata and are not G6 API cases.
    assert_eq!(
        golden["existing_task_close_consumer_cases"]
            .as_array()
            .expect("task-close consumer cases are an array")
            .len(),
        6
    );

    let base_arguments = &golden["fixture_g6_api_call"]["arguments"];
    let mut accepted = 0;
    let mut rejected = 0;
    for case in direct_cases {
        let name = case["name"].as_str().expect("direct case name is text");
        let mut arguments = base_arguments.clone();
        apply_mutation(&mut arguments, &case["mutation"]);
        match invoke_g6(&arguments, source_root) {
            Ok(actual) if !case["error"].is_null() => {
                panic!("{name} unexpectedly validated as {actual}");
            }
            Err(actual) if !case["error"].is_null() => {
                rejected += 1;
                assert_eq!(
                    python_error_class(&actual),
                    case["error"]["exception_class"]
                        .as_str()
                        .expect("frozen direct error class is text"),
                    "error class for {name}"
                );
                assert_eq!(
                    actual.to_string(),
                    case["error"]["message"]
                        .as_str()
                        .expect("frozen direct error message is text"),
                    "error for {name}"
                );
            }
            Ok(actual) => {
                accepted += 1;
                assert_eq!(actual, case["result"], "result for {name}");
                let bytes = canonical_json_bytes(&actual)
                    .expect("accepted G6 output has canonical JSON bytes");
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
                assert_eq!(
                    actual, golden["fixture_g6_api_call"]["result"],
                    "the valid direct case matches the recorded API fixture"
                );
            }
            Err(actual) => panic!("{name} unexpectedly failed: {actual}"),
        }
    }
    assert_eq!(accepted, 1);
    assert_eq!(rejected, 9);
}
