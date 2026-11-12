// @dependency-start
// contract test
// responsibility Preserves the original finite routing relation, error properties and captured Python CLI output.
// upstream implementation ../src/chatgpt_codex_routing.rs implements the decision relation
// upstream reference ../../../../../tests/fixtures/chatgpt_codex_routing/python_golden.json captures the old CLI
// @dependency-end

use agent_canon::chatgpt_codex_routing::{
    packet_from_value, RoutingInputError, EXECUTION_REASON_FIELDS,
};
use agent_canon::python_json::{parse_json, JsonObject, JsonValue};
use serde_json::json;
use std::io::Write;
use std::process::{Command, Stdio};

const FIELDS: &[&str] = &[
    "explicit_codex_execution",
    "workspace_or_repository_mutation",
    "repository_local_or_uncommitted_state_required",
    "command_test_build_benchmark_runtime_observation_required",
    "iterative_inspect_edit_validate_loop_required",
    "durable_repository_delivery_required",
];

fn request(mask: u8, chat_only: bool, scope: &str, oracle: &str) -> JsonValue {
    let mut facts = serde_json::Map::new();
    for (index, name) in FIELDS.iter().enumerate() {
        facts.insert((*name).to_owned(), json!(mask & (1 << index) != 0));
    }
    facts.insert("explicit_chat_only".to_owned(), json!(chat_only));
    parse_json(
        &json!({
            "requested_deliverable": "complete the requested result",
            "chatgpt_scope": "interpret the request and present the result",
            "facts": facts, "codex_scope": scope, "validation_oracle": oracle
        })
        .to_string(),
    )
    .unwrap()
}

fn packet(mask: u8, chat_only: bool) -> Result<JsonValue, RoutingInputError> {
    packet_from_value(&request(
        mask,
        chat_only,
        "edit and validate the repository",
        "selected repository checks pass",
    ))
}

fn field<'a>(value: &'a JsonValue, name: &str) -> &'a JsonValue {
    let JsonValue::Object(JsonObject(fields)) = value else {
        panic!("packet is an object");
    };
    &fields
        .iter()
        .find(|(key, _)| key.equals_text(name))
        .unwrap()
        .1
}

fn text(value: &JsonValue) -> String {
    let JsonValue::String(value) = value else {
        panic!("field is a string");
    };
    value.to_text().unwrap()
}

fn reasons(value: &JsonValue) -> Vec<String> {
    let JsonValue::Array(values) = field(value, "reason_codes") else {
        panic!("reason codes are an array");
    };
    values.0.iter().map(text).collect()
}

#[test]
fn conversation_cases_close_in_chatgpt() {
    for chat_only in [false, true] {
        let packet = packet(0, chat_only).unwrap();
        for (name, expected) in [
            ("route", "chatgpt"),
            ("handoff", "none"),
            ("codex_scope", "none"),
            ("validation_oracle", "none"),
        ] {
            assert_eq!(text(field(&packet, name)), expected);
        }
    }
}

#[test]
fn each_execution_fact_routes_to_codex() {
    assert_eq!(EXECUTION_REASON_FIELDS, FIELDS);
    for (index, name) in FIELDS.iter().enumerate() {
        let packet = packet(1 << index, false).unwrap();
        assert_eq!(text(field(&packet, "route")), "codex");
        assert_eq!(reasons(&packet), [*name]);
        assert_eq!(text(field(&packet, "handoff")), "agent-orchestration");
        assert_eq!(text(field(&packet, "blocked_dependency")), "none");
    }
}

#[test]
fn mixed_request_preserves_canonical_reason_order() {
    let packet = packet(2 | 8 | 32, false).unwrap();
    assert_eq!(reasons(&packet), [FIELDS[1], FIELDS[3], FIELDS[5]]);
    assert_eq!(text(field(&packet, "route")), "codex");
}

#[test]
fn explicit_chat_only_keeps_the_blocked_dependency_without_handoff() {
    let packet = packet(2, true).unwrap();
    assert_eq!(text(field(&packet, "route")), "chatgpt");
    assert_eq!(text(field(&packet, "handoff")), "none");
    assert_eq!(reasons(&packet)[0], "explicit_chat_only_conflict");
    assert!(text(field(&packet, "blocked_dependency")).contains("explicitly prohibited"));
    assert_ne!(text(field(&packet, "codex_scope")), "none");
}

#[test]
fn execution_scope_and_oracle_are_required() {
    assert_eq!(
        packet_from_value(&request(2, false, "none", "checks pass"))
            .err()
            .expect("input is rejected")
            .code,
        "missing_execution_scope"
    );
    assert_eq!(
        packet_from_value(&request(2, false, "edit", "none"))
            .err()
            .expect("input is rejected")
            .code,
        "missing_validation_oracle"
    );
}

#[test]
fn unknown_and_non_boolean_facts_are_rejected() {
    for (input, expected) in [
        (r#"{"facts":{"complexity_score":9}}"#, "unknown_field"),
        (
            r#"{"facts":{"workspace_or_repository_mutation":1}}"#,
            "invalid_boolean",
        ),
    ] {
        assert_eq!(
            packet_from_value(&parse_json(input).unwrap())
                .err()
                .expect("input is rejected")
                .code,
            expected
        );
    }
}

#[test]
fn codex_predicate_is_monotone_over_all_execution_fact_sets() {
    let packets: Vec<_> = (0..64).map(|mask| packet(mask, false).unwrap()).collect();
    for lower in 0u8..64 {
        for upper in 0u8..64 {
            if lower & upper == lower
                && text(field(&packets[usize::from(lower)], "route")) == "codex"
            {
                assert_eq!(text(field(&packets[usize::from(upper)], "route")), "codex");
            }
        }
    }
}

#[test]
fn input_mapping_is_exact_and_json_compatible() {
    let packet = packet(32, false).unwrap();
    assert_eq!(text(field(&packet, "route")), "codex");
    assert_eq!(reasons(&packet), ["durable_repository_delivery_required"]);
    let input = parse_json(
        r#"{"requested_deliverable":"answer","facts":{},"chatgpt_scope":"answer","score":1}"#,
    )
    .unwrap();
    assert_eq!(
        packet_from_value(&input)
            .err()
            .expect("input is rejected")
            .code,
        "unknown_field"
    );
}

#[test]
fn cli_matches_captured_python_streams_and_exits() {
    let golden: serde_json::Value = serde_json::from_str(include_str!(
        "../../../../../tests/fixtures/chatgpt_codex_routing/python_golden.json"
    ))
    .unwrap();
    assert_eq!(
        golden["source_commit"],
        "d9cbf0b4134598e0d4a77e3f1dc5b7bf855f3c42"
    );
    assert_eq!(golden["cases"].as_array().unwrap().len(), 10);
    for case in golden["cases"].as_array().unwrap() {
        let mut child = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
            .args(["chatgpt-codex-route", "--input", "-"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(case["input"].as_str().unwrap().as_bytes())
            .unwrap();
        let output = child.wait_with_output().unwrap();
        assert_eq!(
            output.status.code().unwrap(),
            case["exit"].as_i64().unwrap() as i32,
            "{}",
            case["name"]
        );
        assert_eq!(
            output.stdout,
            case["stdout"].as_str().unwrap().as_bytes(),
            "stdout {}",
            case["name"]
        );
        assert_eq!(
            output.stderr,
            case["stderr"].as_str().unwrap().as_bytes(),
            "stderr {}",
            case["name"]
        );
        if case["name"] == "conversation" {
            let path = std::env::temp_dir().join(format!(
                "agent-canon-route-input-{}.json",
                std::process::id()
            ));
            let input = case["input"].as_str().unwrap().as_bytes();
            let mut file = std::fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&path)
                .unwrap();
            file.write_all(input).unwrap();
            drop(file);
            let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
                .args(["chatgpt-codex-route", "--input"])
                .arg(&path)
                .output()
                .unwrap();
            assert!(output.status.success());
            assert_eq!(output.stdout, case["stdout"].as_str().unwrap().as_bytes());
            assert!(output.stderr.is_empty());
            assert_eq!(std::fs::read(&path).unwrap(), input);
            std::fs::remove_file(path).unwrap();
        }
    }
}
