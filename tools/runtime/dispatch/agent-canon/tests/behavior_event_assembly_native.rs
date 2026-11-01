// @dependency-start
// contract test
// responsibility Checks pure native behavior-event assembly, eligibility, and record suppression against CPython 3.12.3 outputs.
// upstream implementation ../src/behavior_event_assembly.rs owns typed assembly and event identity.
// upstream test ../../../../../tests/fixtures/behavior_event_assembly/python_golden.json freezes old assembly inputs and outputs.
// @dependency-end

use agent_canon::behavior_event_assembly::{
    assemble_behavior_event, eligible_hook_invocation, record_hook_invocation, FinalHandlerResult,
    HookInvocationParts,
};
use agent_canon::prompt_classifier::PromptClassifierInputs;
use agent_canon::python_json::{
    canonical_json_ascii_bytes, parse_json, JsonObject, JsonString, JsonValue,
};
use agent_canon::subagent_selection::{select_subagents, SubagentSelection};
use agent_canon::tool_selection::{select_tools, ToolSelection};
use agent_canon::workflow_context::WorkflowContext;
use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use sha2::{Digest, Sha256};
use std::path::PathBuf;

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/behavior_event_assembly/python_golden.json");
const GOLDEN_SHA256: &str = "b2e02bf43bfd4843f1210ae2205a3169f5c6850481c554461a7f046023dd2d6b";
const SOURCE_SHA256: &str = "78b3fedbacd966d38d935eda687618c2002e5607c22f80f983d4f6dec5395fe8";

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn object_field<'a>(value: &'a JsonValue, field: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(object) = value else {
        return None;
    };
    object
        .0
        .iter()
        .rev()
        .find_map(|(key, value)| key.equals_text(field).then_some(value))
}

fn array(value: &JsonValue) -> Option<&[JsonValue]> {
    match value {
        JsonValue::Array(array) => Some(&array.0),
        _ => None,
    }
}

fn string(value: &JsonValue) -> Option<&JsonString> {
    match value {
        JsonValue::String(value) => Some(value),
        _ => None,
    }
}

fn text_field<'a>(value: &'a JsonValue, field: &str) -> &'a JsonString {
    string(object_field(value, field).expect("fixture string field exists"))
        .expect("fixture field is a JSON string")
}

fn bool_field(value: &JsonValue, field: &str) -> bool {
    match object_field(value, field).expect("fixture boolean field exists") {
        JsonValue::Bool(value) => *value,
        _ => panic!("fixture field {field} is a boolean"),
    }
}

fn optional_bool_field(value: &JsonValue, field: &str) -> bool {
    matches!(object_field(value, field), Some(JsonValue::Bool(true)))
}

fn string_list(value: &JsonValue) -> Vec<JsonString> {
    array(value)
        .expect("fixture string list is an array")
        .iter()
        .map(|value| {
            string(value)
                .expect("fixture string list contains strings")
                .clone()
        })
        .collect()
}

fn empty_object() -> JsonValue {
    JsonValue::Object(JsonObject(Vec::new()))
}

fn canonical(value: &JsonValue) -> Vec<u8> {
    canonical_json_ascii_bytes(value).expect("fixture value has Python-compatible ASCII JSON")
}

fn workflow_context(value: &JsonValue) -> WorkflowContext {
    let workflows = string_list(value);
    let has_context = !workflows.is_empty();
    WorkflowContext {
        workflows,
        timestamp: JsonString::from_text(if has_context { "context-time" } else { "" }),
        source_event: JsonString::from_text(if has_context { "context-event" } else { "" }),
    }
}

fn parts<'a>(
    case_input: &'a JsonValue,
    classifier_rules: Option<&'a PromptClassifierInputs<'a>>,
    tool_selection: Option<&'a ToolSelection>,
    subagent_selection: Option<&'a SubagentSelection>,
    workflow_context: &'a WorkflowContext,
    root: PathBuf,
) -> HookInvocationParts<'a> {
    let payload = object_field(case_input, "payload").expect("fixture payload exists");
    let payload_status = text_field(case_input, "payload_status").clone();
    let hook_payload = Some(payload);
    HookInvocationParts {
        hook_event_name: text_field(case_input, "event").clone(),
        hook_invocation_id: text_field(case_input, "invocation").clone(),
        hook_payload,
        payload_status,
        handler_result: FinalHandlerResult {
            status: text_field(case_input, "status").clone(),
            output_kind: JsonString::default(),
            safe_fields: empty_object(),
        },
        classifier_rules,
        tool_selection,
        subagent_selection,
        workflow_context,
        payload_fingerprint: text_field(case_input, "payload_fingerprint").clone(),
        timestamp: text_field(case_input, "timestamp").clone(),
        root,
        hook_log_namespace: JsonString::from_text("fixture-namespace"),
        report_dir: Some(PathBuf::from("report-root")),
    }
}

fn assert_event(
    event: &agent_canon::behavior_event_assembly::BehaviorEvent,
    expected: &JsonValue,
    expected_base64: &JsonString,
    case: &str,
) {
    assert_eq!(
        canonical(event.as_json_value()),
        canonical(expected),
        "event {case}"
    );
    let actual_bytes = event.canonical_bytes().expect("assembled event serializes");
    assert_eq!(
        STANDARD.encode(actual_bytes),
        expected_base64
            .to_text()
            .expect("canonical Base64 is ASCII"),
        "canonical bytes for {case}"
    );
}

#[test]
fn behavior_event_assembly_matches_frozen_cpython_contract() {
    assert_eq!(sha256_hex(GOLDEN.as_bytes()), GOLDEN_SHA256);
    let golden = parse_json(GOLDEN).expect("frozen CPython behavior assembly corpus parses");
    assert_eq!(
        text_field(&golden, "source_hash").to_text().as_deref(),
        Some(SOURCE_SHA256)
    );
    let cases = array(object_field(&golden, "cases").expect("behavior assembly cases exist"))
        .expect("behavior assembly cases are an array");
    assert_eq!(cases.len(), 32);

    for case in cases {
        let name = text_field(case, "name")
            .to_text()
            .expect("case name is valid text");
        let input = object_field(case, "input").expect("case input exists");
        let payload = object_field(input, "payload").expect("fixture payload exists");
        let root = PathBuf::from("root");
        let empty = empty_object();
        let no_lanes = Vec::new();
        let no_validation = Vec::new();
        let classifier_rules = match object_field(input, "classifier_prompt")
            .expect("fixture classifier prompt exists")
        {
            JsonValue::Null => None,
            JsonValue::String(prompt) => Some(PromptClassifierInputs {
                prompt,
                repo_root: &root,
                catalog: &empty,
                routing_rules: &empty,
                structural_lane_evidence: &no_lanes,
                validation_repair_evidence: &no_validation,
            }),
            _ => panic!("fixture classifier prompt is a string or null"),
        };
        let tools = if bool_field(input, "tools") {
            Some(select_tools(payload).expect("fixture tool selection succeeds"))
        } else {
            None
        };
        let subagents = if bool_field(input, "subagents") {
            Some(select_subagents(payload, None).expect("fixture subagent selection succeeds"))
        } else {
            None
        };
        let context =
            workflow_context(object_field(input, "context").expect("fixture context exists"));
        let parts = parts(
            input,
            classifier_rules.as_ref(),
            tools.as_ref(),
            subagents.as_ref(),
            &context,
            root.clone(),
        );

        match eligible_hook_invocation(&parts) {
            Ok(actual) => {
                assert!(
                    !optional_bool_field(case, "eligible_error"),
                    "eligibility error for {name}"
                );
                assert_eq!(
                    actual,
                    bool_field(case, "eligible"),
                    "eligibility for {name}"
                );
            }
            Err(_) => assert!(
                optional_bool_field(case, "eligible_error"),
                "eligibility error for {name}"
            ),
        }

        match assemble_behavior_event(&parts) {
            Ok(actual) => {
                assert!(
                    !optional_bool_field(case, "assemble_error"),
                    "assembly error for {name}"
                );
                let expected = object_field(case, "assembled").expect("assembled event exists");
                assert_event(
                    &actual,
                    expected,
                    text_field(case, "canonical_base64"),
                    &name,
                );
            }
            Err(_) => assert!(
                optional_bool_field(case, "assemble_error"),
                "assembly error for {name}"
            ),
        }

        let expected_recorded = object_field(case, "recorded").expect("record result exists");
        match (record_hook_invocation(&parts), expected_recorded) {
            (None, JsonValue::Null) => {}
            (Some(actual), expected) => assert_eq!(
                canonical(actual.as_json_value()),
                canonical(expected),
                "recorded event for {name}"
            ),
            _ => panic!("record result for {name} does not match the frozen oracle"),
        }
    }
}
