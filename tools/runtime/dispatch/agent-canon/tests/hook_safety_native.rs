// @dependency-start
// contract test
// responsibility Calls the native hook-safety API from frozen synthetic inputs and compares independent CPython 3.12.3 outputs.
// upstream implementation ../src/hook_safety.rs owns the pure native API.
// upstream evidence ../../../../../tests/fixtures/hook_safety/python_golden.json freezes old Python inputs and outputs.
// @dependency-end

use agent_canon::hook_safety::{
    branch_block_payload, command_sha256, first_block, payload_prompt, payload_tool_command,
    payload_tool_name, secret_block_payload, secret_kind, SHELL_TOOL_NAMES,
};
use serde_json::{json, Value};

const GOLDEN: &str = include_str!("../../../../../tests/fixtures/hook_safety/python_golden.json");

const EVAL_GOLDEN: &str = r####"
{
  "source_sha256": "7906504e9f927614713b044ec21880ec31341961e1f58e262af02145135841d0",
  "cases": [
    {
      "case": "quoted-reset",
      "synthetic_command": "eval 'git reset --mixed HEAD'",
      "intent": {
        "kind": "destructive_git",
        "subcommand": "reset",
        "evidence": "git reset",
        "requires_creation": false,
        "requires_destructive": true
      },
      "payload": {
        "decision": "block",
        "reason": "DESTRUCTIVE_GIT_GUARD=block: protected shared-checkout Git intent lacks required authority. operation=destructive_git:reset; requires=same-segment AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval and nonempty AGENT_CANON_DESTRUCTIVE_GIT_REASON",
        "next_action": "inspect_status_preserve_other_task_changes_or_record_explicit_user_approval",
        "remediation": [
          "Inspect status and preserve changes owned by the user or another concurrent chat.",
          "Continue only on proven task-owned exact paths; that evidence bounds an approval request and never bypasses explicit destructive approval.",
          "If the user explicitly approves the protected action, place every required authority and reason assignment in the same shell segment immediately before Git."
        ],
        "operation": "destructive_git:reset",
        "command_sha256": "9a9defd5cbef39b547338b7c5b533c19e92e4913bfb6645e6155f291f16ac270"
      }
    },
    {
      "case": "quoted-comment-backtick",
      "synthetic_command": "eval 'echo safe # `git reset --hard`'",
      "intent": null,
      "payload": null
    },
    {
      "case": "quoted-backtick",
      "synthetic_command": "eval 'echo `git reset --hard`'",
      "intent": {
        "kind": "destructive_git",
        "subcommand": "reset",
        "evidence": "git reset",
        "requires_creation": false,
        "requires_destructive": true
      },
      "payload": {
        "decision": "block",
        "reason": "DESTRUCTIVE_GIT_GUARD=block: protected shared-checkout Git intent lacks required authority. operation=destructive_git:reset; requires=same-segment AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval and nonempty AGENT_CANON_DESTRUCTIVE_GIT_REASON",
        "next_action": "inspect_status_preserve_other_task_changes_or_record_explicit_user_approval",
        "remediation": [
          "Inspect status and preserve changes owned by the user or another concurrent chat.",
          "Continue only on proven task-owned exact paths; that evidence bounds an approval request and never bypasses explicit destructive approval.",
          "If the user explicitly approves the protected action, place every required authority and reason assignment in the same shell segment immediately before Git."
        ],
        "operation": "destructive_git:reset",
        "command_sha256": "efd1a0d3bc8d85c83ddd86f06512b08147330f755b6ddc7477a7c9d2c2480d30"
      }
    },
    {
      "case": "authority-inside-eval",
      "synthetic_command": "eval 'AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval AGENT_CANON_DESTRUCTIVE_GIT_REASON=approved git reset --hard'",
      "intent": null,
      "payload": null
    },
    {
      "case": "authority-does-not-leak",
      "synthetic_command": "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval AGENT_CANON_DESTRUCTIVE_GIT_REASON=approved true; eval git reset --hard",
      "intent": {
        "kind": "destructive_git",
        "subcommand": "reset",
        "evidence": "git reset",
        "requires_creation": false,
        "requires_destructive": true
      },
      "payload": {
        "decision": "block",
        "reason": "DESTRUCTIVE_GIT_GUARD=block: protected shared-checkout Git intent lacks required authority. operation=destructive_git:reset; requires=same-segment AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval and nonempty AGENT_CANON_DESTRUCTIVE_GIT_REASON",
        "next_action": "inspect_status_preserve_other_task_changes_or_record_explicit_user_approval",
        "remediation": [
          "Inspect status and preserve changes owned by the user or another concurrent chat.",
          "Continue only on proven task-owned exact paths; that evidence bounds an approval request and never bypasses explicit destructive approval.",
          "If the user explicitly approves the protected action, place every required authority and reason assignment in the same shell segment immediately before Git."
        ],
        "operation": "destructive_git:reset",
        "command_sha256": "3dcc9746a61bd6a7f5e47b421fdb032bf9be797371315cba9a472cb23c1ecd33"
      }
    },
    {
      "case": "nested-bare",
      "synthetic_command": "eval eval git checkout main",
      "intent": {
        "kind": "destructive_git",
        "subcommand": "checkout",
        "evidence": "current-checkout mutation",
        "requires_creation": false,
        "requires_destructive": true
      },
      "payload": {
        "decision": "block",
        "reason": "DESTRUCTIVE_GIT_GUARD=block: protected shared-checkout Git intent lacks required authority. operation=destructive_git:checkout; requires=same-segment AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval and nonempty AGENT_CANON_DESTRUCTIVE_GIT_REASON",
        "next_action": "inspect_status_preserve_other_task_changes_or_record_explicit_user_approval",
        "remediation": [
          "Inspect status and preserve changes owned by the user or another concurrent chat.",
          "Continue only on proven task-owned exact paths; that evidence bounds an approval request and never bypasses explicit destructive approval.",
          "If the user explicitly approves the protected action, place every required authority and reason assignment in the same shell segment immediately before Git."
        ],
        "operation": "destructive_git:checkout",
        "command_sha256": "84fc27ef930ed470f00444d6b5910cfe37cfb343d6c7645152b3ce9360e1da64"
      }
    },
    {
      "case": "quoted-separator",
      "synthetic_command": "eval 'true; git reset --hard'",
      "intent": {
        "kind": "destructive_git",
        "subcommand": "reset",
        "evidence": "git reset",
        "requires_creation": false,
        "requires_destructive": true
      },
      "payload": {
        "decision": "block",
        "reason": "DESTRUCTIVE_GIT_GUARD=block: protected shared-checkout Git intent lacks required authority. operation=destructive_git:reset; requires=same-segment AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval and nonempty AGENT_CANON_DESTRUCTIVE_GIT_REASON",
        "next_action": "inspect_status_preserve_other_task_changes_or_record_explicit_user_approval",
        "remediation": [
          "Inspect status and preserve changes owned by the user or another concurrent chat.",
          "Continue only on proven task-owned exact paths; that evidence bounds an approval request and never bypasses explicit destructive approval.",
          "If the user explicitly approves the protected action, place every required authority and reason assignment in the same shell segment immediately before Git."
        ],
        "operation": "destructive_git:reset",
        "command_sha256": "1e3fc0f7bce1bf8d1209359710cda095ac9a1ed2e714cdbc3b3e8832bfdcef71"
      }
    },
    {
      "case": "empty-quoted-token",
      "synthetic_command": "eval '' git reset --hard",
      "intent": {
        "kind": "destructive_git",
        "subcommand": "reset",
        "evidence": "git reset",
        "requires_creation": false,
        "requires_destructive": true
      },
      "payload": {
        "decision": "block",
        "reason": "DESTRUCTIVE_GIT_GUARD=block: protected shared-checkout Git intent lacks required authority. operation=destructive_git:reset; requires=same-segment AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval and nonempty AGENT_CANON_DESTRUCTIVE_GIT_REASON",
        "next_action": "inspect_status_preserve_other_task_changes_or_record_explicit_user_approval",
        "remediation": [
          "Inspect status and preserve changes owned by the user or another concurrent chat.",
          "Continue only on proven task-owned exact paths; that evidence bounds an approval request and never bypasses explicit destructive approval.",
          "If the user explicitly approves the protected action, place every required authority and reason assignment in the same shell segment immediately before Git."
        ],
        "operation": "destructive_git:reset",
        "command_sha256": "24a187980f6625b8d792c42f5a1ef07adc6a4ca6e17b5910d7b200ad1d9100c0"
      }
    },
    {
      "case": "escaped-space",
      "synthetic_command": "eval git\\ reset --hard",
      "intent": {
        "kind": "destructive_git",
        "subcommand": "reset",
        "evidence": "git reset",
        "requires_creation": false,
        "requires_destructive": true
      },
      "payload": {
        "decision": "block",
        "reason": "DESTRUCTIVE_GIT_GUARD=block: protected shared-checkout Git intent lacks required authority. operation=destructive_git:reset; requires=same-segment AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval and nonempty AGENT_CANON_DESTRUCTIVE_GIT_REASON",
        "next_action": "inspect_status_preserve_other_task_changes_or_record_explicit_user_approval",
        "remediation": [
          "Inspect status and preserve changes owned by the user or another concurrent chat.",
          "Continue only on proven task-owned exact paths; that evidence bounds an approval request and never bypasses explicit destructive approval.",
          "If the user explicitly approves the protected action, place every required authority and reason assignment in the same shell segment immediately before Git."
        ],
        "operation": "destructive_git:reset",
        "command_sha256": "1a394723b38bb95c817ca33216627721da509f85b9494f24ba740d979f63be47"
      }
    },
    {
      "case": "literal-hash-token",
      "synthetic_command": "eval 'echo #comment' git reset --hard",
      "intent": null,
      "payload": null
    }
  ]
}
"####;

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
    // Exact synthetic inputs and old results from the parent-accepted probe.
    let cases: [(&str, &str, Option<&str>); 41] = [
        (
            "combining-prefix",
            "\u{301}ghp_test_canary_00000000000000000000000000000000",
            Some("GitHub token"),
        ),
        (
            "combining-suffix",
            "ghp_test_canary_00000000000000000000000000000000\u{301}",
            Some("GitHub token"),
        ),
        (
            "joiner-prefix",
            "\u{200d}ghp_test_canary_00000000000000000000000000000000",
            Some("GitHub token"),
        ),
        (
            "letter-prefix",
            "\u{e9}ghp_test_canary_00000000000000000000000000000000",
            None,
        ),
        (
            "unicode16-prefix",
            "\u{1c89}ghp_test_canary_00000000000000000000000000000000",
            Some("GitHub token"),
        ),
        ("sk-5", "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", None),
        ("sk-6", "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\u{e9}", None),
        ("sk-7", "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\u{301}", None),
        (
            "sk-8",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaX",
            Some("OpenAI-style API key"),
        ),
        ("sk-9", "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-", None),
        ("sk-10", "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-\u{e9}", None),
        ("sk-11", "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-\u{301}", None),
        (
            "sk-12",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-X",
            Some("OpenAI-style API key"),
        ),
        ("sk-13", "sk--------------------------------", None),
        ("sk-14", "sk--------------------------------\u{e9}", None),
        ("sk-15", "sk--------------------------------\u{301}", None),
        (
            "sk-16",
            "sk--------------------------------X",
            Some("OpenAI-style API key"),
        ),
        (
            "sk-17",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            Some("OpenAI-style API key"),
        ),
        ("sk-18", "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\u{e9}", None),
        (
            "sk-19",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\u{301}",
            Some("OpenAI-style API key"),
        ),
        (
            "sk-20",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaX",
            Some("OpenAI-style API key"),
        ),
        ("sk-21", "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-", None),
        (
            "sk-22",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-\u{e9}",
            Some("OpenAI-style API key"),
        ),
        ("sk-23", "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-\u{301}", None),
        (
            "sk-24",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-X",
            Some("OpenAI-style API key"),
        ),
        ("sk-25", "sk---------------------------------", None),
        (
            "sk-26",
            "sk---------------------------------\u{e9}",
            Some("OpenAI-style API key"),
        ),
        ("sk-27", "sk---------------------------------\u{301}", None),
        (
            "sk-28",
            "sk---------------------------------X",
            Some("OpenAI-style API key"),
        ),
        (
            "sk-29",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            Some("OpenAI-style API key"),
        ),
        ("sk-30", "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\u{e9}", None),
        (
            "sk-31",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\u{301}",
            Some("OpenAI-style API key"),
        ),
        (
            "sk-32",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaX",
            Some("OpenAI-style API key"),
        ),
        (
            "sk-33",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-",
            Some("OpenAI-style API key"),
        ),
        (
            "sk-34",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-\u{e9}",
            Some("OpenAI-style API key"),
        ),
        (
            "sk-35",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-\u{301}",
            Some("OpenAI-style API key"),
        ),
        (
            "sk-36",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-X",
            Some("OpenAI-style API key"),
        ),
        ("sk-37", "sk----------------------------------", None),
        (
            "sk-38",
            "sk----------------------------------\u{e9}",
            Some("OpenAI-style API key"),
        ),
        ("sk-39", "sk----------------------------------\u{301}", None),
        (
            "sk-40",
            "sk----------------------------------X",
            Some("OpenAI-style API key"),
        ),
    ];
    for (case_id, prompt, expected) in cases {
        assert_eq!(secret_kind(prompt), expected, "{case_id}");
    }
}

#[test]
fn deep_eval_chain_matches_frozen_old_git_intent() {
    let golden: Value = serde_json::from_str(GOLDEN).expect("frozen old-API corpus parses");
    let eval_case = cases(&golden, "git_intent_and_payload_results")
        .iter()
        .find(|case| text(field(case, "case_id")) == "eval-script-wrapper")
        .expect("frozen corpus has the low-depth eval wrapper case");
    let expected = field(eval_case, "intent");

    let low_depth_command = text(field(field(eval_case, "synthetic_input"), "command"));
    let low_depth_intent = first_block(low_depth_command)
        .as_ref()
        .map(|intent| serde_json::to_value(intent).expect("Git intent serializes"))
        .unwrap_or(Value::Null);
    assert_eq!(
        low_depth_intent, *expected,
        "the frozen low-depth eval intent is the deep-chain oracle"
    );

    let deep_command = format!("{}git reset --mixed HEAD", "eval ".repeat(4000));
    let deep_intent = first_block(&deep_command)
        .as_ref()
        .map(|intent| serde_json::to_value(intent).expect("Git intent serializes"))
        .unwrap_or(Value::Null);
    assert_eq!(
        deep_intent, *expected,
        "deep eval wrappers preserve the frozen old Git intent"
    );
}

#[test]
fn eval_quote_and_authority_semantics_match_captured_old_api_results() {
    let golden: Value =
        serde_json::from_str(EVAL_GOLDEN).expect("captured old eval API cases parse");
    assert_eq!(
        text(field(&golden, "source_sha256")),
        "7906504e9f927614713b044ec21880ec31341961e1f58e262af02145135841d0"
    );
    let captured_cases = field(&golden, "cases")
        .as_array()
        .expect("captured old eval API cases are an array");
    assert_eq!(captured_cases.len(), 10);

    for case in captured_cases {
        let case_id = text(field(case, "case"));
        let command = text(field(case, "synthetic_command"));
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
            *field(case, "payload"),
            "redacted payload for {case_id}"
        );
    }
}
