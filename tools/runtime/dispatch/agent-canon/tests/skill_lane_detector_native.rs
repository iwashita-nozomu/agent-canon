// @dependency-start
// contract test
// responsibility Checks native structural and validation-repair lane APIs against captured CPython 3.12.3 outputs.
// upstream implementation ../src/skill_lane_detector.rs owns pure lane evidence detection.
// upstream test ../../../../../tests/fixtures/skill_lane_detector/python_golden.json freezes old API inputs and results.
// @dependency-end

use agent_canon::python_json::{
    canonical_json_ascii_bytes, parse_json, JsonArray, JsonObject, JsonString, JsonValue,
};
use agent_canon::skill_lane_detector::{
    detect_skill_lane_evidence, structural_skill_lane_concept_matches,
    validation_failure_repair_concept_matches, EvidenceGroupsByCategory, SkillLaneEvidence,
    StructuralSkillLaneConcept, StructuralSkillLaneMatch, ValidationFailureRepairConcept,
    ValidationFailureRepairMatch,
};
use sha2::{Digest, Sha256};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/skill_lane_detector/python_golden.json");
const GOLDEN_SHA256: &str = "f77c1104efaecae91e0ae868120da636864102a68f4848eed1043f2e9bbdd0c0";
const SOURCE_SHA256: &str = "62bd8973f5581ae35882a63417a415f0db36389e687377a36930cbd2eccfe518";

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

fn canonical(value: &JsonValue) -> Vec<u8> {
    canonical_json_ascii_bytes(value).expect("fixture value has Python-compatible ASCII JSON")
}

fn array_value(values: Vec<JsonValue>) -> JsonValue {
    JsonValue::Array(JsonArray(values))
}

fn output_object(fields: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(JsonObject(
        fields
            .into_iter()
            .map(|(name, value)| (JsonString::from_text(name), value))
            .collect(),
    ))
}

fn strings_value(values: &[JsonString]) -> JsonValue {
    JsonValue::Array(JsonArray(
        values.iter().cloned().map(JsonValue::String).collect(),
    ))
}

fn evidence_groups_value(groups: &[EvidenceGroupsByCategory]) -> JsonValue {
    JsonValue::Object(JsonObject(
        groups
            .iter()
            .map(|category| {
                (
                    category.category.clone(),
                    JsonValue::Array(JsonArray(
                        category
                            .groups
                            .iter()
                            .map(|group| strings_value(group))
                            .collect(),
                    )),
                )
            })
            .collect(),
    ))
}

fn structural_concept_value(concept: &StructuralSkillLaneConcept) -> JsonValue {
    output_object(vec![
        ("name", JsonValue::String(concept.name.clone())),
        (
            "required_evidence_categories",
            strings_value(&concept.required_evidence_categories),
        ),
        ("route_skills", strings_value(&concept.route_skills)),
        (
            "evidence_groups",
            evidence_groups_value(&concept.evidence_groups),
        ),
    ])
}

fn structural_match_value(matched: &StructuralSkillLaneMatch) -> JsonValue {
    output_object(vec![
        ("concept", structural_concept_value(&matched.concept)),
        (
            "observed_evidence_categories",
            strings_value(&matched.observed_evidence_categories),
        ),
        (
            "reason",
            JsonValue::String(JsonString::from_text(&matched.reason())),
        ),
    ])
}

fn repair_concept_value(concept: &ValidationFailureRepairConcept) -> JsonValue {
    output_object(vec![
        ("name", JsonValue::String(concept.name.clone())),
        (
            "required_evidence_categories",
            strings_value(&concept.required_evidence_categories),
        ),
        (
            "owner_skill",
            JsonValue::String(concept.owner_skill.clone()),
        ),
        ("secondary_skills", strings_value(&concept.secondary_skills)),
        (
            "evidence_groups",
            evidence_groups_value(&concept.evidence_groups),
        ),
    ])
}

fn repair_match_value(matched: &ValidationFailureRepairMatch) -> JsonValue {
    output_object(vec![
        ("concept", repair_concept_value(&matched.concept)),
        (
            "observed_evidence_categories",
            strings_value(&matched.observed_evidence_categories),
        ),
        (
            "reason",
            JsonValue::String(JsonString::from_text(&matched.reason())),
        ),
    ])
}

fn lane_evidence_value(evidence: &SkillLaneEvidence) -> JsonValue {
    output_object(vec![
        ("schema", JsonValue::String(evidence.schema.clone())),
        ("lane", JsonValue::String(evidence.lane.clone())),
        ("route_skills", strings_value(&evidence.route_skills)),
        (
            "evidence_categories",
            strings_value(&evidence.evidence_categories),
        ),
        ("status", JsonValue::String(evidence.status.clone())),
        ("source", JsonValue::String(evidence.source.clone())),
    ])
}

#[test]
fn skill_lane_apis_match_frozen_cpython_outputs() {
    assert_eq!(sha256_hex(GOLDEN.as_bytes()), GOLDEN_SHA256);
    let golden = parse_json(GOLDEN).expect("frozen CPython lane corpus parses");
    assert_eq!(
        text_field(&golden, "source_hash").to_text().as_deref(),
        Some(SOURCE_SHA256)
    );
    let cases = array(object_field(&golden, "cases").expect("lane cases exist"))
        .expect("lane cases are an array");
    assert_eq!(cases.len(), 11);

    for case in cases {
        let name = text_field(case, "name")
            .to_text()
            .expect("case name is valid text");
        let input = object_field(case, "input").expect("case input exists");
        let prompt = text_field(input, "prompt");
        let structural = structural_skill_lane_concept_matches(prompt)
            .into_iter()
            .map(|matched| structural_match_value(&matched))
            .collect();
        let repair = validation_failure_repair_concept_matches(prompt)
            .into_iter()
            .map(|matched| repair_match_value(&matched))
            .collect();
        let evidence = detect_skill_lane_evidence(prompt)
            .iter()
            .map(lane_evidence_value)
            .collect();
        let actual = output_object(vec![
            ("structural_matches", array_value(structural)),
            ("repair_matches", array_value(repair)),
            ("lane_evidence", array_value(evidence)),
        ]);
        let expected = object_field(case, "output").expect("expected output exists");
        assert_eq!(canonical(&actual), canonical(expected), "case {name}");
    }
}
