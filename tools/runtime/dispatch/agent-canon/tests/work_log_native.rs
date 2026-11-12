// @dependency-start
// contract test
// responsibility Preserves read-only work-log ledger snapshot, validation, ordering, and digest behavior.
// upstream implementation ../src/work_log.rs owns read-only ledger snapshots and canonical digest values
// upstream implementation ../src/python_json.rs owns Python-compatible event parsing and canonical bytes
// @dependency-end

use agent_canon::python_json::{
    canonical_json_ascii_bytes, JsonArray, JsonNumber, JsonObject, JsonString, JsonValue,
};
use agent_canon::work_log::{ledger_snapshot_digest, read_ledger_snapshot};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use tempfile::TempDir;

struct RuntimeRoot(TempDir);

impl RuntimeRoot {
    fn new() -> Self {
        Self(tempfile::tempdir().expect("external runtime fixture creates"))
    }

    fn path(&self) -> &Path {
        self.0.path()
    }

    fn report_dir(&self, run_id: &str) -> PathBuf {
        self.path().join("reports/agents").join(run_id)
    }
}

fn string(value: &str) -> JsonValue {
    JsonValue::String(JsonString::from_text(value))
}

fn object(entries: impl IntoIterator<Item = (&'static str, JsonValue)>) -> JsonValue {
    JsonValue::Object(JsonObject(
        entries
            .into_iter()
            .map(|(key, value)| (JsonString::from_text(key), value))
            .collect(),
    ))
}

fn array(values: impl IntoIterator<Item = JsonValue>) -> JsonValue {
    JsonValue::Array(JsonArray(values.into_iter().collect()))
}

fn set_field(object: &mut JsonValue, name: &str, value: JsonValue) {
    let JsonValue::Object(object) = object else {
        panic!("value is an object")
    };
    if let Some((_, existing)) = object.0.iter_mut().find(|(key, _)| key.equals_text(name)) {
        *existing = value;
    } else {
        object.0.push((JsonString::from_text(name), value));
    }
}

fn event(
    run_id: &str,
    event_id: &str,
    sequence: &str,
    outcome: &str,
    score: JsonNumber,
) -> JsonValue {
    object([
        ("run_id", string(run_id)),
        ("context_id", string("context-1")),
        ("event_id", string(event_id)),
        ("sequence", string(sequence)),
        ("semantic_kind", string("change")),
        ("owner", string("agent")),
        ("state_owner", string("workflow")),
        ("api_owner", string("work-log")),
        ("dependency_owner", string("runtime")),
        ("responsibility_unit", string("ledger")),
        ("intent_id", string("intent-1")),
        ("outcome", string(outcome)),
        ("evidence_refs", array([string("evidence:one")])),
        ("artifact_refs", array([string("artifact:one")])),
        (
            "source_binding",
            object([
                ("run_id", string(run_id)),
                ("context_id", string("context-1")),
            ]),
        ),
        (
            "gate_evidence",
            object([
                ("score", JsonValue::Number(score)),
                ("measured", string("observed")),
            ]),
        ),
    ])
}

fn write_ledger(report_dir: &Path, events: &[JsonValue]) {
    fs::create_dir_all(report_dir).expect("report fixture directory creates");
    let mut text = "# Work Log\n\n## Entries\n\n".to_owned();
    for event in events {
        let encoded = canonical_json_ascii_bytes(event).expect("event serializes canonically");
        text.push_str("- ledger_event=");
        text.push_str(std::str::from_utf8(&encoded).expect("canonical JSON is ASCII"));
        text.push('\n');
    }
    fs::write(report_dir.join("work_log.md"), text).expect("archived ledger fixture writes");
}

fn field_text<'a>(event: &'a JsonValue, key: &str) -> &'a JsonString {
    let JsonValue::Object(object) = event else {
        panic!("event is an object")
    };
    let key = JsonString::from_text(key);
    let (_, value) = object
        .0
        .iter()
        .find(|(candidate, _)| candidate == &key)
        .expect("field exists");
    let JsonValue::String(value) = value else {
        panic!("field is text")
    };
    value
}

fn expected_snapshot_digest(events: &[JsonValue]) -> String {
    let encoded = events
        .iter()
        .map(|event| canonical_json_ascii_bytes(event).expect("event serializes canonically"))
        .collect::<Vec<_>>();
    let mut bytes = b"[".to_vec();
    for (index, event) in encoded.iter().enumerate() {
        if index > 0 {
            bytes.push(b',');
        }
        bytes.extend_from_slice(event);
    }
    bytes.push(b']');
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[test]
fn snapshot_reads_sorted_events_and_reproduces_the_canonical_digest() {
    let runtime = RuntimeRoot::new();
    let report_dir = runtime.report_dir("run-1");
    let first = event("run-1", "event-2", "2", "completed", JsonNumber::Float(1.0));
    let second = event("run-1", "event-10", "10", "checked", JsonNumber::Float(2.5));
    let mut events = [first, second];
    write_ledger(&report_dir, &events);

    let snapshot = read_ledger_snapshot(&report_dir, " snapshot-1 ", Some(runtime.path()))
        .expect("read-only snapshot succeeds");

    assert_eq!(snapshot.snapshot_identity, "snapshot-1");
    assert_eq!(snapshot.events.len(), 2);
    assert_eq!(
        field_text(&snapshot.events[0], "event_id")
            .to_text()
            .as_deref(),
        Some("event-10")
    );
    assert_eq!(
        field_text(&snapshot.events[1], "event_id")
            .to_text()
            .as_deref(),
        Some("event-2")
    );
    assert_eq!(
        snapshot
            .event_identities
            .iter()
            .map(JsonString::to_text)
            .collect::<Option<Vec<_>>>()
            .expect("event identities are Unicode text"),
        vec!["event-10".to_owned(), "event-2".to_owned()]
    );
    events.swap(0, 1);
    let expected = expected_snapshot_digest(&events);
    assert_eq!(snapshot.snapshot_digest, expected);
    assert_eq!(
        ledger_snapshot_digest(&snapshot).expect("snapshot digest is reproducible"),
        expected
    );
}

#[test]
fn snapshot_rejects_duplicate_identity_with_conflicting_event_content() {
    let runtime = RuntimeRoot::new();
    let report_dir = runtime.report_dir("run-2");
    let first = event("run-2", "event-1", "1", "completed", JsonNumber::Float(1.0));
    let conflicting = event(
        "run-2",
        "event-1",
        "2",
        "different outcome",
        JsonNumber::Float(1.0),
    );
    write_ledger(&report_dir, &[first, conflicting]);

    let error = read_ledger_snapshot(&report_dir, "snapshot", Some(runtime.path()))
        .err()
        .expect("a repeated event identity is rejected");

    assert!(error.contains("duplicate ledger event identity"));
}

#[test]
fn snapshot_validates_group_and_source_binding_semantics() {
    let runtime = RuntimeRoot::new();
    let report_dir = runtime.report_dir("run-3");
    let mut forbidden_group = event(
        "run-3",
        "event-1",
        "1",
        "invalid",
        JsonNumber::Integer("1".into()),
    );
    set_field(&mut forbidden_group, "mapping_mode", string("group"));
    set_field(&mut forbidden_group, "group_identity", string("group-1"));
    set_field(
        &mut forbidden_group,
        "member_clause_ids",
        array([string("R1"), string("R2")]),
    );
    set_field(&mut forbidden_group, "semantic_kind", string("decision"));
    write_ledger(&report_dir, &[forbidden_group]);

    let error = read_ledger_snapshot(&report_dir, "snapshot", Some(runtime.path()))
        .err()
        .expect("decision events cannot be grouped");
    assert!(error.contains("decision ledger events cannot be grouped"));

    let mut mismatched_binding = event(
        "run-3",
        "event-2",
        "2",
        "invalid",
        JsonNumber::Integer("1".into()),
    );
    set_field(
        &mut mismatched_binding,
        "source_binding",
        object([
            ("run_id", string("run-3")),
            ("context_id", string("other-context")),
        ]),
    );
    write_ledger(&report_dir, &[mismatched_binding]);

    let error = read_ledger_snapshot(&report_dir, "snapshot", Some(runtime.path()))
        .err()
        .expect("source binding context must match the event");
    assert!(error.contains("source_binding.context_id does not match context_id"));
}

#[test]
fn snapshot_rejects_malformed_archived_event_text() {
    let runtime = RuntimeRoot::new();
    let report_dir = runtime.report_dir("run-4");
    fs::create_dir_all(&report_dir).expect("report fixture directory creates");
    fs::write(
        report_dir.join("work_log.md"),
        "# Work Log\n\n## Entries\n\n- ledger_event={malformed\n",
    )
    .expect("malformed archived record writes");

    let error = read_ledger_snapshot(&report_dir, "snapshot", Some(runtime.path()))
        .err()
        .expect("malformed event text is rejected");

    assert!(error.contains("malformed ledger event"));
}
