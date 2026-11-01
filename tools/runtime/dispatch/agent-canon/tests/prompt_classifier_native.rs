// @dependency-start
// contract test
// responsibility Checks the native prompt classifier against captured CPython 3.12.3 input/output cases.
// upstream implementation ../src/prompt_classifier.rs owns pure prompt classification.
// upstream test ../../../../../tests/fixtures/prompt_classifier/python_golden.json freezes old API inputs and results.
// @dependency-end

use agent_canon::prompt_classifier::{
    feedback_targets, prompt_intake_signals, should_log, PromptClassifierInputs,
    PromptIntakeSignals,
};
use agent_canon::python_json::{
    canonical_json_ascii_bytes, parse_json, JsonArray, JsonObject, JsonString, JsonValue,
};
use agent_canon::skill_lane_detector::SkillLaneEvidence;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::path::PathBuf;

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/prompt_classifier/python_golden.json");
const GOLDEN_SHA256: &str = "181d0e3ffc83e364417b1f29178c261ac9bd6b06793e07678d267cf29a96e6ea";
const SOURCE_SHA256: &str = "081f8b851c2f03ed7f0a275db572d2107e416cf52a687a1922a82dda4c73c909";

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

fn string_values(value: &JsonValue) -> Vec<JsonString> {
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

fn skill_lane_evidence(value: &JsonValue) -> SkillLaneEvidence {
    SkillLaneEvidence {
        schema: text_field(value, "schema").clone(),
        lane: text_field(value, "lane").clone(),
        route_skills: string_values(
            object_field(value, "route_skills").expect("fixture route_skills exists"),
        ),
        evidence_categories: string_values(
            object_field(value, "evidence_categories").expect("fixture evidence_categories exists"),
        ),
        status: text_field(value, "status").clone(),
        source: text_field(value, "source").clone(),
    }
}

fn canonical(value: &JsonValue) -> Vec<u8> {
    canonical_json_ascii_bytes(value).expect("fixture value has Python-compatible ASCII JSON")
}

fn string_array(values: &[JsonString]) -> JsonValue {
    JsonValue::Array(JsonArray(
        values.iter().cloned().map(JsonValue::String).collect(),
    ))
}

fn signals_value(signals: &PromptIntakeSignals) -> JsonValue {
    JsonValue::Object(JsonObject(vec![
        (
            JsonString::from_text("skills"),
            string_array(&signals.skills),
        ),
        (
            JsonString::from_text("selected_workflows"),
            string_array(&signals.selected_workflows),
        ),
        (
            JsonString::from_text("candidate_skills"),
            string_array(&signals.candidate_skills),
        ),
        (
            JsonString::from_text("candidate_skill_reasons"),
            string_array(&signals.candidate_skill_reasons),
        ),
        (
            JsonString::from_text("candidate_workflows"),
            string_array(&signals.candidate_workflows),
        ),
        (
            JsonString::from_text("candidate_tools"),
            string_array(&signals.candidate_tools),
        ),
        (
            JsonString::from_text("feedback_labels"),
            string_array(&signals.feedback_labels),
        ),
        (
            JsonString::from_text("feedback_action"),
            JsonValue::String(signals.feedback_action.clone()),
        ),
        (
            JsonString::from_text("should_log"),
            JsonValue::Bool(should_log(signals)),
        ),
        (
            JsonString::from_text("feedback_targets"),
            string_array(&feedback_targets(signals)),
        ),
    ]))
}

fn skill_set(value: &JsonValue) -> BTreeSet<Vec<u32>> {
    array(value)
        .expect("skills are an array")
        .iter()
        .map(|value| string(value).expect("skill is a string").0.clone())
        .collect()
}

fn assert_skills_prefix(actual: &JsonValue, expected_prefix: &JsonValue, name: &str) {
    let actual = array(object_field(actual, "skills").expect("actual skills exist"))
        .expect("actual skills are an array");
    let expected = array(expected_prefix).expect("required skills prefix is an array");
    assert!(
        actual.len() >= expected.len(),
        "skills prefix length for {name}"
    );
    for (index, expected_item) in expected.iter().enumerate() {
        assert_eq!(
            canonical(&actual[index]),
            canonical(expected_item),
            "required skill prefix item {index} for {name}"
        );
    }
}

fn assert_non_skill_fields_exact(actual: &JsonValue, expected: &JsonValue, name: &str) {
    for field in [
        "selected_workflows",
        "candidate_skills",
        "candidate_skill_reasons",
        "candidate_workflows",
        "candidate_tools",
        "feedback_labels",
        "feedback_action",
        "should_log",
        "feedback_targets",
    ] {
        assert_eq!(
            canonical(object_field(actual, field).expect("actual output field exists")),
            canonical(object_field(expected, field).expect("expected output field exists")),
            "field {field} for {name}"
        );
    }
}

#[test]
fn prompt_classifier_matches_frozen_cpython_outputs_and_order_contract() {
    assert_eq!(sha256_hex(GOLDEN.as_bytes()), GOLDEN_SHA256);
    let golden = parse_json(GOLDEN).expect("frozen CPython classifier corpus parses");
    assert_eq!(
        text_field(&golden, "source_hash").to_text().as_deref(),
        Some(SOURCE_SHA256)
    );
    let cases = array(object_field(&golden, "cases").expect("classifier cases exist"))
        .expect("classifier cases are an array");
    assert_eq!(cases.len(), 479);

    for case in cases {
        let name = text_field(case, "name")
            .to_text()
            .expect("case name is valid text");
        let input = object_field(case, "input").expect("case input exists");
        let prompt = text_field(input, "prompt").clone();
        let repo_root = PathBuf::from(
            text_field(input, "repo_root")
                .to_text()
                .expect("repo_root is valid path text"),
        );
        let catalog = object_field(input, "catalog").expect("catalog input exists");
        let routing_rules = object_field(input, "routing_rules").expect("routing rules exist");
        let lanes = array(
            object_field(input, "structural_lane_evidence").expect("structural evidence exists"),
        )
        .expect("structural evidence is an array")
        .iter()
        .map(skill_lane_evidence)
        .collect::<Vec<_>>();
        let validation_repair = string_values(
            object_field(input, "validation_repair_evidence")
                .expect("validation repair evidence exists"),
        );
        let signals = prompt_intake_signals(&PromptClassifierInputs {
            prompt: &prompt,
            repo_root: &repo_root,
            catalog,
            routing_rules,
            structural_lane_evidence: &lanes,
            validation_repair_evidence: &validation_repair,
        });
        let actual = signals_value(&signals);
        let expected = object_field(case, "output").expect("expected output exists");
        assert_skills_prefix(
            &actual,
            object_field(case, "required_skills_prefix").expect("required skill prefix exists"),
            &name,
        );

        match text_field(case, "skills_comparison").to_text().as_deref() {
            Some("exact") => assert_eq!(canonical(&actual), canonical(expected), "case {name}"),
            Some("skills-membership") => {
                assert_non_skill_fields_exact(&actual, expected, &name);
                let actual_skills = object_field(&actual, "skills").expect("actual skills exist");
                let expected_skills =
                    object_field(expected, "skills").expect("expected skills exist");
                assert_eq!(
                    skill_set(actual_skills),
                    skill_set(expected_skills),
                    "skills membership for {name}"
                );
                assert_eq!(
                    array(actual_skills)
                        .expect("actual skills are an array")
                        .len(),
                    skill_set(actual_skills).len(),
                    "native skills contain no duplicates for {name}"
                );
            }
            other => panic!("unknown skills comparison contract {other:?} for {name}"),
        }
    }
}
