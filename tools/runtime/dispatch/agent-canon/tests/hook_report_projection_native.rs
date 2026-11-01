// @dependency-start
// contract implementation
// responsibility Preserves native hook projection bytes and verifies the generic locked monitoring append.
// upstream implementation ../src/hook_report_projection.rs owns the shared monitor projection.
// upstream implementation ../src/runtime_boundary.rs owns explicit external path resolution.
// upstream reference ../../../../../tests/fixtures/hook_report_projection/python_golden.json freezes actual old API results and document bytes.
// @dependency-end

use agent_canon::hook_report_projection::{
    append_monitoring_projection_at, emit_behavior_projection_at, MonitorProjectionResult,
};
use agent_canon::python_json::{
    parse_json, JsonArray, JsonNumber, JsonObject, JsonString, JsonValue,
};
use base64::engine::general_purpose::STANDARD;
use base64::Engine as _;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

const PYTHON_GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/hook_report_projection/python_golden.json");
const PYTHON_GOLDEN_SHA256: &str =
    "734aabaef4c00eb8963a8ba6f96e47f1b67eee924af43dbf202f7c001832733d";

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct TempRoot(PathBuf);

impl TempRoot {
    fn new() -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock is after epoch")
            .as_nanos();
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-hook-report-{}-{sequence}-{nonce}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("temporary source root is created");
        Self(
            path.canonicalize()
                .expect("temporary source root is canonical"),
        )
    }
}

impl Drop for TempRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn hook_report_projection_matches_frozen_old_api_results_and_document_bytes() {
    assert_eq!(sha256(PYTHON_GOLDEN.as_bytes()), PYTHON_GOLDEN_SHA256);
    let corpus = parse_json(PYTHON_GOLDEN).expect("frozen old API oracle parses");
    let cases = array_field(&corpus, "cases");
    assert_eq!(cases.len(), 8);
    let report_name = string_field(&corpus, "report_name")
        .to_text()
        .expect("report name is text");

    for case in cases {
        verify_case(case, &report_name);
    }
}

#[test]
fn concurrent_identical_behavior_projection_entries_are_written_once() {
    let root = TempRoot::new();
    let report_dir = root.0.join("reports").join("run-concurrent");
    fs::create_dir_all(&report_dir).expect("report directory is created");
    let event = parse_json(
        r#"{"schema":"agent-canon.behavior-event.v1","event_id":"concurrent-event","status":"pass"}"#,
    )
    .expect("behavior event parses");
    let source_root = workspace_scope_source_root();
    let timestamp = "2026-01-02 03:04 JST";

    std::thread::scope(|scope| {
        let results = (0..8)
            .map(|_| {
                scope.spawn(|| {
                    emit_behavior_projection_at(&report_dir, source_root, None, &event, timestamp)
                })
            })
            .collect::<Vec<_>>();
        for result in results {
            let result = result.join().expect("projection thread completes");
            assert_eq!(result.status, "spooled", "{}", result.error);
        }
    });

    let text = fs::read_to_string(report_dir.join("workflow_monitoring.md"))
        .expect("monitor document is readable");
    assert_eq!(text.matches("behavior_event_json=").count(), 1);
}

#[test]
fn generic_monitoring_append_preserves_sections_and_writes_behavior_and_intervention_entries() {
    let root = TempRoot::new();
    let report_dir = root.0.join("reports").join("run-token-summary");
    let behavior_events = vec!["token_usage_summary=present session_count=2".to_owned()];
    let interventions =
        vec!["token usage moving average measured from Codex session logs".to_owned()];
    let path = append_monitoring_projection_at(
        &report_dir,
        workspace_scope_source_root(),
        None,
        &behavior_events,
        &interventions,
        "2026-11-02 12:34 JST",
    )
    .expect("generic monitor append succeeds");

    assert_eq!(path, report_dir.join("workflow_monitoring.md"));
    assert_eq!(
        fs::read_to_string(path).expect("monitor document is readable"),
        "# Workflow Monitoring\n<!--\n@dependency-start\nresponsibility Records workflow monitoring for this run bundle.\nupstream design ../../../templates/agents/workflow_monitoring.md template\n@dependency-end\n-->\n\n- Run ID: run-token-summary\n\n## Signals\n\n## Behavior Events\n\n- `2026-11-02 12:34 JST` token_usage_summary=present session_count=2\n## Tool Warnings\n\n- tool_warnings_status: pending\n\n## Interventions\n\n- `2026-11-02 12:34 JST` token usage moving average measured from Codex session logs\n## Improvement Decisions\n\n- skill_improvement_decision: pending\n- config_improvement_decision: pending\n- workflow_improvement_decision: pending\n- knowledge_learning_decision: pending\n"
    );
}

#[test]
fn configured_runtime_root_keeps_projection_inside_the_external_boundary() {
    let root = TempRoot::new();
    let runtime_root = root.0.join("runtime");
    fs::create_dir_all(&runtime_root).expect("runtime root is created");
    let report_dir = runtime_root.join("reports").join("run-boundary");
    let event = parse_json(
        r#"{"schema":"agent-canon.behavior-event.v1","event_id":"runtime-event","status":"pass"}"#,
    )
    .expect("behavior event parses");
    let source_root = workspace_scope_source_root();
    let result = emit_behavior_projection_at(
        &report_dir,
        source_root,
        Some(&runtime_root),
        &event,
        "2026-01-02 03:04 JST",
    );

    assert_eq!(result.status, "spooled", "{}", result.error);
    assert_eq!(result.path, report_dir.join("workflow_monitoring.md"));
    assert!(result.path.is_file());
}

fn verify_case(case: &JsonValue, report_name: &str) {
    let name = string_field(case, "name")
        .to_text()
        .expect("case name is text");
    let root = TempRoot::new();
    let report_dir = root.0.join("reports").join(report_name);
    let monitor_path = report_dir.join("workflow_monitoring.md");
    let kind = string_field(case, "kind")
        .to_text()
        .expect("case kind is text");

    match object_member(case, "initial_base64") {
        Some(JsonValue::String(value)) => {
            let encoded = value.to_text().expect("initial base64 is text");
            fs::create_dir_all(&report_dir).expect("report directory is created");
            fs::write(
                &monitor_path,
                STANDARD
                    .decode(encoded.as_bytes())
                    .expect("old initial document bytes decode"),
            )
            .expect("initial monitor document is written");
        }
        Some(JsonValue::Null) => {}
        _ => panic!("{name}: initial_base64 is a string or null"),
    }
    if kind == "directory" {
        fs::create_dir_all(&report_dir).expect("report directory is created");
        fs::create_dir(&monitor_path).expect("directory failure premise is created");
    }

    let event = object_member(case, "event").expect("case has a behavior event");
    let timestamp = string_field(case, "timestamp")
        .to_text()
        .expect("case timestamp is text");
    let outcomes = array_field(case, "outcomes");
    let repeat = integer_field(case, "repeat");
    assert_eq!(
        outcomes.len(),
        repeat,
        "{name}: outcome count matches repeat"
    );
    let source_root = workspace_scope_source_root();

    for outcome in outcomes {
        let result = emit_behavior_projection_at(&report_dir, source_root, None, event, &timestamp);
        assert_result_fields(outcome, &result, &root.0, &name);
    }

    match object_member(case, "output_base64") {
        Some(JsonValue::String(value)) => {
            let encoded = value.to_text().expect("output base64 is text");
            let expected = STANDARD
                .decode(encoded.as_bytes())
                .expect("old output bytes decode");
            assert_eq!(
                fs::read(&monitor_path).expect("projected monitor document is readable"),
                expected,
                "{name}: complete workflow_monitoring.md bytes"
            );
        }
        Some(JsonValue::Null) if kind == "directory" => {
            assert!(
                monitor_path.is_dir(),
                "{name}: failure leaves directory premise"
            );
        }
        Some(JsonValue::Null) => assert!(
            !monitor_path.exists(),
            "{name}: failed projection did not create a monitor document"
        ),
        _ => panic!("{name}: output_base64 is a string or null"),
    }
}

fn assert_result_fields(
    expected: &JsonValue,
    actual: &MonitorProjectionResult,
    root: &Path,
    case_name: &str,
) {
    assert_eq!(
        actual.status,
        string_field(expected, "status")
            .to_text()
            .expect("result status is text"),
        "{case_name}: result status: {}",
        actual.error
    );
    assert_eq!(
        actual.path,
        fixture_path(
            &string_field(expected, "path")
                .to_text()
                .expect("result path is text"),
            root
        ),
        "{case_name}: result path"
    );
    let expected_error = string_field(expected, "error")
        .to_text()
        .expect("result error is text");
    assert_eq!(
        actual.error.is_empty(),
        expected_error.is_empty(),
        "{case_name}: success/failure diagnostic presence"
    );
}

fn fixture_path(value: &str, root: &Path) -> PathBuf {
    let suffix = value
        .strip_prefix("$ROOT")
        .expect("fixture output path starts at $ROOT");
    let mut path = root.to_path_buf();
    for component in suffix.split('/') {
        if !component.is_empty() {
            path.push(component);
        }
    }
    path
}

fn workspace_scope_source_root() -> &'static Path {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .expect("native crate is below the AgentCanon tools source root")
}

fn array_field<'a>(value: &'a JsonValue, key: &str) -> &'a [JsonValue] {
    let Some(JsonValue::Array(JsonArray(values))) = object_member(value, key) else {
        panic!("frozen {key} field is an array");
    };
    values
}

fn string_field<'a>(value: &'a JsonValue, key: &str) -> &'a JsonString {
    match object_member(value, key) {
        Some(JsonValue::String(value)) => value,
        _ => panic!("frozen {key} field is text"),
    }
}

fn integer_field(value: &JsonValue, key: &str) -> usize {
    let Some(JsonValue::Number(JsonNumber::Integer(value))) = object_member(value, key) else {
        panic!("frozen {key} field is an integer");
    };
    value.parse().expect("frozen repeat count fits usize")
}

fn object_member<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(JsonObject(entries)) = value else {
        return None;
    };
    entries
        .iter()
        .rev()
        .find(|(candidate, _)| candidate.equals_text(key))
        .map(|(_, value)| value)
}

fn sha256(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
