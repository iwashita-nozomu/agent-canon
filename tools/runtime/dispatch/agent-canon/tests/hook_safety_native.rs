// @dependency-start
// contract test
// responsibility Calls the native hook-safety API from frozen synthetic inputs and compares independent CPython 3.12.3 outputs.
// upstream implementation ../src/hook_safety.rs owns the pure native API.
// upstream test ../../../../../tests/fixtures/hook_safety/python_golden.json freezes old Python inputs and outputs.
// @dependency-end

use agent_canon::hook_safety::{
    branch_block_payload, command_sha256, first_block, payload_prompt, payload_tool_command,
    payload_tool_name, secret_block_payload, secret_kind, SHELL_TOOL_NAMES,
};
use serde_json::{json, Value};

const GOLDEN: &str = include_str!("../../../../../tests/fixtures/hook_safety/python_golden.json");

fn field<'a>(value: &'a Value, key: &str) -> &'a Value {
    value
        .get(key)
        .unwrap_or_else(|| panic!("frozen hook-safety field is present: {key}"))
}

fn text(value: &Value) -> &str {
    value.as_str().expect("frozen hook-safety value is text")
}

fn cases<'a>(golden: &'a Value, group: &str) -> &'a [Value] {
    field(field(golden, "fixtures"), group)
        .as_array()
        .expect("frozen hook-safety cases are an array")
}

#[test]
fn secret_api_matches_frozen_inputs_and_keeps_canaries_out_of_payloads() {
    let golden: Value = serde_json::from_str(GOLDEN).expect("frozen old-API corpus parses");
    let expected_names = field(field(&golden, "constants"), "SHELL_TOOL_NAMES");
    assert_eq!(json!(SHELL_TOOL_NAMES), *expected_names);

    let secret_cases = cases(&golden, "secret_results");
    assert_eq!(secret_cases.len(), 5);
    for case in secret_cases {
        let case_id = text(field(case, "case_id"));
        let prompt = text(field(field(case, "synthetic_input"), "prompt"));
        let kind = secret_kind(prompt);
        assert_eq!(
            json!(kind),
            *field(case, "secret_kind"),
            "secret classification for {case_id}"
        );
        let payload = kind.map(secret_block_payload).unwrap_or(Value::Null);
        assert_eq!(
            payload,
            *field(case, "block_payload"),
            "secret block payload for {case_id}"
        );
        if kind.is_some() {
            let serialized = serde_json::to_string(&payload).expect("payload serializes");
            assert!(
                !serialized.contains(prompt),
                "synthetic canary leaked from block payload for {case_id}"
            );
        }
    }
}

#[test]
fn payload_accessors_match_frozen_json_inputs_and_old_api_results() {
    let golden: Value = serde_json::from_str(GOLDEN).expect("frozen old-API corpus parses");
    let payload_cases = cases(&golden, "payload_accessor_results");
    assert_eq!(payload_cases.len(), 5);
    for case in payload_cases {
        let case_id = text(field(case, "case_id"));
        let input = field(case, "synthetic_input");
        assert_eq!(
            payload_tool_name(input),
            text(field(case, "tool_name")),
            "tool name for {case_id}"
        );
        assert_eq!(
            payload_tool_command(input),
            text(field(case, "tool_command")),
            "tool command for {case_id}"
        );
        assert_eq!(
            payload_prompt(input),
            text(field(case, "prompt")),
            "prompt for {case_id}"
        );
    }
}

#[test]
fn git_intent_and_redacted_payload_match_frozen_commands_and_old_api_results() {
    let golden: Value = serde_json::from_str(GOLDEN).expect("frozen old-API corpus parses");
    let git_cases = cases(&golden, "git_intent_and_payload_results");
    assert_eq!(git_cases.len(), 87);
    for case in git_cases {
        let case_id = text(field(case, "case_id"));
        let command = text(field(field(case, "synthetic_input"), "command"));
        assert_eq!(
            command_sha256(command),
            text(field(case, "synthetic_input_sha256")),
            "input command hash for {case_id}"
        );

        let intent = first_block(command);
        let actual_intent = intent
            .as_ref()
            .map(|value| serde_json::to_value(value).expect("Git intent serializes"))
            .unwrap_or(Value::Null);
        assert_eq!(
            actual_intent,
            *field(case, "intent"),
            "Git intent for {case_id}"
        );

        let payload = intent
            .as_ref()
            .map(|value| branch_block_payload(command, value))
            .unwrap_or(Value::Null);
        assert_eq!(
            payload,
            *field(case, "block_payload"),
            "redacted block payload for {case_id}"
        );
        if intent.is_some() {
            let serialized = serde_json::to_string(&payload).expect("payload serializes");
            assert!(
                !serialized.contains(command),
                "synthetic command leaked from block payload for {case_id}"
            );
        }
    }
}

#[test]
fn unicode_secret_boundaries_match_supplemental_python_probe_results() {
    let github = "ghp_test_canary_00000000000000000000000000000000";
    let github_cases = [
        (
            "combining-prefix",
            format!("\u{0301}{github}"),
            Some("GitHub token"),
        ),
        (
            "combining-suffix",
            format!("{github}\u{0301}"),
            Some("GitHub token"),
        ),
        (
            "joiner-prefix",
            format!("\u{200d}{github}"),
            Some("GitHub token"),
        ),
        ("letter-prefix", format!("é{github}"), None),
        (
            "unicode16-prefix",
            format!("\u{1c89}{github}"),
            Some("GitHub token"),
        ),
    ];
    let mut case_count = 0;
    for (case_id, prompt, expected) in github_cases {
        assert_eq!(secret_kind(&prompt), expected, "{case_id}");
        case_count += 1;
    }

    let openai = Some("OpenAI-style API key");
    let openai_tail_cases = [
        ("a31", "a".repeat(31), [None, None, None, openai]),
        (
            "a30-dash",
            format!("{}-", "a".repeat(30)),
            [None, None, None, openai],
        ),
        ("dashes32", "-".repeat(32), [None, None, None, openai]),
        ("a32", "a".repeat(32), [openai, None, openai, openai]),
        (
            "a31-dash",
            format!("{}-", "a".repeat(31)),
            [None, openai, None, openai],
        ),
        ("dashes33", "-".repeat(33), [None, openai, None, openai]),
        ("a33", "a".repeat(33), [openai, None, openai, openai]),
        (
            "a32-dash",
            format!("{}-", "a".repeat(32)),
            [openai, openai, openai, openai],
        ),
        ("dashes34", "-".repeat(34), [None, openai, None, openai]),
    ];
    let suffixes = ["", "é", "\u{0301}", "X"];
    for (tail_case, tail, expected_by_suffix) in openai_tail_cases {
        for (suffix_index, suffix) in suffixes.iter().enumerate() {
            let prompt = format!("sk-{tail}{suffix}");
            assert_eq!(
                secret_kind(&prompt),
                expected_by_suffix[suffix_index],
                "OpenAI synthetic tail case {tail_case}, suffix index {suffix_index}"
            );
            case_count += 1;
        }
    }
    assert_eq!(case_count, 41);
}
