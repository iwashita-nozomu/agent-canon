// @dependency-start
// contract test
// responsibility Checks native read-only workflow context loading against captured CPython 3.12.3 results.
// upstream implementation ../src/workflow_context.rs owns the typed fail-open context loader.
// upstream test ../../../../../tests/fixtures/workflow_context/python_golden.json freezes old input bytes and outputs.
// @dependency-end

use agent_canon::python_json::{
    canonical_json_ascii_bytes, parse_json, JsonArray, JsonObject, JsonString, JsonValue,
};
use agent_canon::workflow_context::{load_workflow_context, WorkflowContext};
use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/workflow_context/python_golden.json");
const GOLDEN_SHA256: &str = "061a7ac9ab1cec31875bd34a4742742e3dfa8ef1581a44cd61c8ddec2fcde6de";
const SOURCE_SHA256: &str = "4fe86df1e3c5df782c533dceccc13165d026e013cb91d5483f1b010c4c6c7597";
static NEXT_TEMPORARY_DIRECTORY: AtomicUsize = AtomicUsize::new(0);

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

fn string_array(values: &[JsonString]) -> JsonValue {
    JsonValue::Array(JsonArray(
        values.iter().cloned().map(JsonValue::String).collect(),
    ))
}

fn context_value(context: &WorkflowContext) -> JsonValue {
    JsonValue::Object(JsonObject(vec![
        (
            JsonString::from_text("workflows"),
            string_array(&context.workflows),
        ),
        (
            JsonString::from_text("timestamp"),
            JsonValue::String(context.timestamp.clone()),
        ),
        (
            JsonString::from_text("source_event"),
            JsonValue::String(context.source_event.clone()),
        ),
        (
            JsonString::from_text("has_workflow"),
            JsonValue::Bool(context.has_workflow()),
        ),
    ]))
}

fn temporary_directory() -> PathBuf {
    let suffix = NEXT_TEMPORARY_DIRECTORY.fetch_add(1, Ordering::Relaxed);
    let path = std::env::temp_dir().join(format!(
        "agent-canon-workflow-context-{}-{suffix}",
        std::process::id()
    ));
    fs::create_dir(&path).expect("create isolated workflow context test directory");
    path
}

fn case_bytes(case: &JsonValue) -> Option<Vec<u8>> {
    match object_field(case, "bytes_base64").expect("fixture bytes field exists") {
        JsonValue::Null => None,
        JsonValue::String(value) => Some(
            STANDARD
                .decode(value.to_text().expect("fixture base64 is valid ASCII"))
                .expect("fixture bytes decode from base64"),
        ),
        _ => panic!("fixture bytes field is a string or null"),
    }
}

fn prepare_case_path(root: &Path, case: &JsonValue, index: usize) -> PathBuf {
    let kind = text_field(case, "kind")
        .to_text()
        .expect("fixture path kind is valid text");
    let path = root.join(format!("case-{index}"));
    match kind.as_str() {
        "missing" => {}
        "directory" => fs::create_dir(&path).expect("create directory input"),
        "file" => fs::write(&path, case_bytes(case).expect("file case has input bytes"))
            .expect("write file input"),
        "symlink" => {
            let target = root.join(format!("target-{index}"));
            fs::write(
                &target,
                case_bytes(case).expect("symlink case has target bytes"),
            )
            .expect("write symlink target");
            #[cfg(unix)]
            std::os::unix::fs::symlink(&target, &path).expect("create file symlink");
            #[cfg(not(unix))]
            fs::copy(&target, &path).expect("materialize symlink target on this platform");
        }
        other => panic!("unknown fixture path kind {other}"),
    }
    path
}

#[test]
fn workflow_context_loader_matches_frozen_cpython_cases() {
    assert_eq!(sha256_hex(GOLDEN.as_bytes()), GOLDEN_SHA256);
    let golden = parse_json(GOLDEN).expect("frozen CPython workflow-context corpus parses");
    assert_eq!(
        text_field(&golden, "source_hash").to_text().as_deref(),
        Some(SOURCE_SHA256)
    );
    let cases = array(object_field(&golden, "cases").expect("workflow context cases exist"))
        .expect("workflow context cases are an array");
    assert_eq!(cases.len(), 20);

    let root = temporary_directory();
    for (index, case) in cases.iter().enumerate() {
        let name = text_field(case, "name")
            .to_text()
            .expect("case name is valid text");
        let path = prepare_case_path(&root, case, index);
        let actual = context_value(&load_workflow_context(&path));
        let expected = object_field(case, "output").expect("expected output exists");
        assert_eq!(canonical(&actual), canonical(expected), "case {name}");
    }
    fs::remove_dir_all(root).expect("remove isolated workflow context test directory");
}
