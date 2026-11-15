// @dependency-start
// contract test
// responsibility Verifies retained prompt secret matching and prompt extraction against captured independent inputs.
// upstream implementation ../src/hook_safety.rs prompt safety API
// upstream reference ../../../../../tests/fixtures/hook_safety/python_golden.json captured prompt inputs and secret outputs
// @dependency-end

use agent_canon::hook_safety::{payload_prompt, secret_block_payload, secret_kind};
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
fn prompt_accessor_matches_frozen_json_inputs() {
    let golden: Value = serde_json::from_str(GOLDEN).expect("frozen old-API corpus parses");
    let payload_cases = cases(&golden, "payload_accessor_results");
    assert_eq!(payload_cases.len(), 5);
    for case in payload_cases {
        let case_id = text(field(case, "case_id"));
        let input = field(case, "synthetic_input");
        assert_eq!(
            payload_prompt(input),
            text(field(case, "prompt")),
            "prompt for {case_id}"
        );
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
