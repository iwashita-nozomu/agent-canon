// @dependency-start
// contract test
// responsibility Checks the native prompt classifier against captured CPython 3.12.3 input/output cases.
// upstream implementation ../src/prompt_classifier.rs owns pure prompt classification.
// upstream reference ../../../../../tests/fixtures/prompt_classifier/python_golden.json freezes old API inputs and results.
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
const GOLDEN_SHA256: &str = "9cb92118b3b0aada788448833079cbb59e85aa515302b672516de85374564dea";
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

fn expected_with_native_tool_locator(value: &JsonValue) -> JsonValue {
    let serialized = canonical(value);
    let mut expected = parse_json(std::str::from_utf8(&serialized).unwrap()).unwrap();
    let JsonValue::Object(fields) = &mut expected else {
        panic!("classifier output is an object");
    };
    let tools = fields
        .0
        .iter_mut()
        .find(|(key, _)| key.equals_text("candidate_tools"));
    let Some((_, JsonValue::Array(tools))) = tools else {
        panic!("classifier output supplies candidate tools");
    };
    for tool in &mut tools.0 {
        if let JsonValue::String(name) = tool {
            if name.equals_text("tool_rejection_preflight.py") {
                *name = JsonString::from_text("tool-rejection-preflight");
            }
        }
    }
    // Preserve the frozen oracle while removing the explicitly retired monitor.
    tools.0.retain(
        |tool| !matches!(tool, JsonValue::String(name) if name.equals_text("workflow_monitor.py")),
    );
    let should_log = [
        "skills",
        "selected_workflows",
        "candidate_skills",
        "candidate_workflows",
        "candidate_tools",
        "feedback_labels",
    ]
    .iter()
    .any(|field| {
        fields.0.iter().any(|(key, value)| {
            key.equals_text(field)
                && matches!(value, JsonValue::Array(items) if !items.0.is_empty())
        })
    });
    if let Some((_, value)) = fields
        .0
        .iter_mut()
        .find(|(key, _)| key.equals_text("should_log"))
    {
        *value = JsonValue::Bool(should_log);
    }
    expected
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

fn classify_without_context(prompt_text: &str) -> PromptIntakeSignals {
    let prompt = JsonString::from_text(prompt_text);
    let repo_root = PathBuf::from(".");
    let empty_context = JsonValue::Object(JsonObject(Vec::new()));
    let lanes = Vec::<SkillLaneEvidence>::new();
    let validation_repair = Vec::<JsonString>::new();
    prompt_intake_signals(&PromptClassifierInputs {
        prompt: &prompt,
        repo_root: &repo_root,
        catalog: &empty_context,
        routing_rules: &empty_context,
        structural_lane_evidence: &lanes,
        validation_repair_evidence: &validation_repair,
    })
}

fn has_text(values: &[JsonString], expected: &str) -> bool {
    values.iter().any(|value| value.equals_text(expected))
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
fn native_archive_name_routes_to_the_current_tool_and_preserves_legacy_hints() {
    let native = classify_without_context("runtime-log-archive-git で結果を書き出して");
    assert!(has_text(&native.candidate_tools, "runtime-log-archive-git"));
    assert!(has_text(&native.candidate_workflows, "codex-task-workflow"));
    assert!(has_text(
        &native.candidate_skills,
        "result-artifact-writeout"
    ));
    let legacy = classify_without_context("runtime_log_archive_git.py");
    assert!(has_text(
        &legacy.candidate_tools,
        "runtime_log_archive_git.py"
    ));
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
        let expected_storage = expected_with_native_tool_locator(
            object_field(case, "output").expect("expected output exists"),
        );
        let expected = &expected_storage;
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

#[test]
fn prompt_classifier_preserves_direct_python_classifier_cases() {
    let cases: &[(&str, &str, &[&str], &[&str])] = &[
        (
            "validation-repair",
            "failed validation; do not delete tests or weaken oracle before repairing the failing contract",
            &[],
            &[],
        ),
        (
            "declared-skill",
            "Use $codex-task-workflow for a validation failure; do not delete tests or weaken the oracle.",
            &["codex-task-workflow"],
            &["codex-task-workflow"],
        ),
        (
            "oracle-mismatch",
            "The test oracle has a spec mismatch; fix test design.",
            &[],
            &[],
        ),
        (
            "user-guided-debugging",
            "Use user-guided refactor cadence: show one concrete issue, patch only that target, and do not run validation unless I ask.",
            &[],
            &["user-guided-debugging"],
        ),
        (
            "ordinary-docs",
            "Please update the docs; no validation unless asked.",
            &[],
            &["user-guided-debugging"],
        ),
        (
            "parent-repo-skill-lane",
            "親レポに固有スキルを置けるようにする設計修正",
            &[],
            &["task-routing", "structure-refactor"],
        ),
        (
            "advisory-routing",
            "Which route contract applies for this repository task?",
            &[],
            &["codex-task-workflow"],
        ),
    ];

    for (name, prompt, expected_selected, forbidden_candidates) in cases {
        let signals = classify_without_context(prompt);
        for expected in *expected_selected {
            assert!(
                has_text(&signals.skills, expected),
                "selected {expected} in {name}"
            );
        }
        for forbidden in *forbidden_candidates {
            assert!(
                !has_text(&signals.candidate_skills, forbidden),
                "unexpected candidate {forbidden} in {name}"
            );
        }
    }
}

#[test]
fn prompt_classifier_preserves_focused_python_routing_oracles() {
    let declared = classify_without_context("use $task-routing");
    assert_eq!(declared.skills, vec![JsonString::from_text("task-routing")]);

    for prompt in [
        "Use the parent/same-repository branch with linked-worktree for the AgentCanon update.",
        "Use the dependency repository's independent-clone for the AgentCanon update.",
    ] {
        let signals = classify_without_context(prompt);
        assert!(has_text(&signals.candidate_workflows, "agent-canon-update"));
        assert!(has_text(
            &signals.candidate_workflows,
            "agent-canon-update-route"
        ));
    }

    let refactor = classify_without_context(
        "複数の関係ファイルに及ぶ routing evaluator refactor を既存 oracle と一致させて",
    );
    assert!(has_text(&refactor.candidate_workflows, "large-delivery"));
    assert!(has_text(&refactor.candidate_skills, "refactor-loop"));
}

#[test]
fn experiment_wrapper_removal_route_inputs_keep_direct_owner_oracles() {
    let cases: &[(&str, &str, &[&str], &[&str])] = &[
        (
            "existing-html-results",
            "Render the existing experiment results as a browser-readable HTML page",
            &["html-output"],
            &["experiment-lifecycle"],
        ),
        (
            "rerun-and-render-html",
            "Rerun the experiment and render its result as a browser-readable HTML page",
            &["experiment-lifecycle", "html-output"],
            &[],
        ),
        (
            "persist-experiment-artifacts",
            "Persist experiment artifact evidence without writing a report",
            &["experiment-lifecycle", "result-artifact-writeout"],
            &[],
        ),
    ];
    let removed = ["html-experiment-report", "save-experiment-results"];

    for (name, prompt, expected_candidates, forbidden_candidates) in cases {
        let signals = classify_without_context(prompt);
        for expected in *expected_candidates {
            assert!(
                has_text(&signals.candidate_skills, expected),
                "missing candidate {expected} in {name}"
            );
        }
        for forbidden in *forbidden_candidates {
            assert!(
                !has_text(&signals.candidate_skills, forbidden),
                "unexpected candidate {forbidden} in {name}"
            );
        }
        for retired in removed {
            assert!(
                !has_text(&signals.candidate_skills, retired),
                "retired candidate {retired} in {name}"
            );
        }
    }
}
