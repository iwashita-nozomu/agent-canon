// @dependency-start
// contract test
// responsibility Verifies native work-log ledger, idempotency, snapshot, and boundary behavior.
// upstream implementation ../src/work_log.rs owns run-local logs and semantic events.
// upstream implementation ../src/python_json.rs owns Python-compatible event parsing and canonical bytes.
// @dependency-end

use agent_canon::python_json::{JsonArray, JsonNumber, JsonObject, JsonString, JsonValue};
use agent_canon::work_log::{
    append_ledger_event, append_work_entry, ledger_snapshot_digest, read_ledger_snapshot,
};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_FIXTURE: AtomicU64 = AtomicU64::new(0);

struct RuntimeRoot(PathBuf);

impl RuntimeRoot {
    fn new() -> Self {
        let sequence = NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-native-work-log-{}-{sequence}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("external runtime fixture is created");
        Self(fs::canonicalize(path).expect("runtime fixture has a physical path"))
    }

    fn report_dir(&self, run_id: &str) -> PathBuf {
        self.0.join("reports/agents").join(run_id)
    }
}

impl Drop for RuntimeRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
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
    reverse_keys: bool,
) -> JsonValue {
    let gate = object([
        ("score", JsonValue::Number(score)),
        ("measured", string("observed")),
    ]);
    let source_binding = object([
        ("run_id", string(run_id)),
        ("context_id", string("context-1")),
    ]);
    let fields = vec![
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
        ("source_binding", source_binding),
        ("gate_evidence", gate),
    ];
    if reverse_keys {
        object(fields.into_iter().rev())
    } else {
        object(fields)
    }
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

#[test]
fn append_is_idempotent_conflict_safe_and_snapshot_ordered() {
    let runtime = RuntimeRoot::new();
    let report_dir = runtime.report_dir("run-1");
    let first = event(
        "run-1",
        "event-2",
        "2",
        "completed",
        JsonNumber::Float(1.0),
        false,
    );
    let first_path =
        append_ledger_event(&report_dir, &first, Some(&runtime.0)).expect("first event appends");
    let before_duplicate = fs::read(&first_path).expect("ledger bytes read");

    let equivalent = event(
        "run-1",
        "event-2",
        "2",
        "completed",
        JsonNumber::Integer("1".into()),
        true,
    );
    let duplicate_path = append_ledger_event(&report_dir, &equivalent, Some(&runtime.0))
        .expect("Python-equal event is idempotent despite key order and int/float equality");
    assert_eq!(duplicate_path, first_path);
    assert_eq!(
        fs::read(&first_path).expect("ledger bytes read"),
        before_duplicate
    );

    let conflicting = event(
        "run-1",
        "event-2",
        "2",
        "different outcome",
        JsonNumber::Float(1.0),
        false,
    );
    let error = append_ledger_event(&report_dir, &conflicting, Some(&runtime.0))
        .expect_err("identity reuse with changed content conflicts");
    assert!(error.contains("ledger event conflict"));

    let second = event(
        "run-1",
        "event-10",
        "10",
        "checked",
        JsonNumber::Float(2.5),
        false,
    );
    append_ledger_event(&report_dir, &second, Some(&runtime.0)).expect("second event appends");
    let snapshot = read_ledger_snapshot(&report_dir, " snapshot-1 ", Some(&runtime.0))
        .expect("snapshot reads");
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
    assert_eq!(snapshot.snapshot_digest.len(), 64);
    assert_eq!(
        ledger_snapshot_digest(&snapshot).expect("snapshot digest repeats deterministically"),
        snapshot.snapshot_digest
    );
}

#[test]
fn grouped_events_and_source_binding_keep_validation_rules() {
    let runtime = RuntimeRoot::new();
    let report_dir = runtime.report_dir("run-2");
    let group = object([
        ("run_id", string("run-2")),
        ("context_id", string("context-2")),
        ("event_id", string("group-event")),
        ("semantic_kind", string("change")),
        ("owner", string("agent")),
        ("state_owner", string("workflow")),
        ("api_owner", string("work-log")),
        ("dependency_owner", string("runtime")),
        ("responsibility_unit", string("ledger")),
        ("intent_id", string("intent-2")),
        ("outcome", string("mapped")),
        ("evidence_refs", array([string("evidence:two")])),
        ("artifact_refs", array([string("artifact:two")])),
        ("mapping_mode", string("group")),
        ("group_identity", string("group-2")),
        ("member_clause_ids", array([string("R2"), string("R3")])),
        (
            "source_binding",
            object([
                ("run_id", string("run-2")),
                ("context_id", string("context-2")),
            ]),
        ),
    ]);
    append_ledger_event(&report_dir, &group, Some(&runtime.0))
        .expect("valid group event and matching source binding append");

    let mut forbidden = event(
        "run-2",
        "bad-group",
        "3",
        "invalid",
        JsonNumber::Integer("1".into()),
        false,
    );
    set_field(&mut forbidden, "mapping_mode", string("group"));
    set_field(
        &mut forbidden,
        "member_clause_ids",
        array([string("R1"), string("R2")]),
    );
    set_field(&mut forbidden, "group_identity", string("g"));
    set_field(&mut forbidden, "semantic_kind", string("decision"));
    let error = append_ledger_event(&report_dir, &forbidden, Some(&runtime.0))
        .expect_err("decision events cannot be grouped");
    assert!(error.contains("decision ledger events cannot be grouped"));

    let mut duplicate_members = event(
        "run-2",
        "duplicate-members",
        "3",
        "invalid",
        JsonNumber::Integer("1".into()),
        false,
    );
    set_field(&mut duplicate_members, "mapping_mode", string("group"));
    set_field(&mut duplicate_members, "group_identity", string("g"));
    set_field(
        &mut duplicate_members,
        "member_clause_ids",
        array([string("R1"), string("R1")]),
    );
    let error = append_ledger_event(&report_dir, &duplicate_members, Some(&runtime.0))
        .expect_err("group members must be unique");
    assert!(error.contains("member_clause_ids must be unique"));

    let mut mismatched = event(
        "run-2",
        "bad-binding",
        "4",
        "invalid",
        JsonNumber::Integer("1".into()),
        false,
    );
    if let JsonValue::Object(fields) = &mut mismatched {
        if let Some((_, JsonValue::Object(binding))) = fields
            .0
            .iter_mut()
            .find(|(key, _)| key.equals_text("source_binding"))
        {
            if let Some((_, value)) = binding
                .0
                .iter_mut()
                .find(|(key, _)| key.equals_text("context_id"))
            {
                *value = string("other-context");
            }
        }
    }
    let error = append_ledger_event(&report_dir, &mismatched, Some(&runtime.0))
        .expect_err("source binding context must match the event");
    assert!(error.contains("source_binding.context_id does not match context_id"));

    let mismatched_run = event(
        "another-run",
        "wrong-run",
        "5",
        "invalid",
        JsonNumber::Integer("1".into()),
        false,
    );
    let error = append_ledger_event(&report_dir, &mismatched_run, Some(&runtime.0))
        .expect_err("event run id must match its report directory");
    assert!(error.contains("run_id does not match report directory"));
}

#[test]
fn append_skips_malformed_old_lines_while_snapshot_fails_closed() {
    let runtime = RuntimeRoot::new();
    let report_dir = runtime.report_dir("run-3");
    fs::create_dir_all(&report_dir).expect("run directory is prepared");
    let work_log = report_dir.join("work_log.md");
    fs::write(
        &work_log,
        "# Work Log\n\n## Entries\n\n- ledger_event={malformed\n",
    )
    .expect("malformed legacy line fixture is created");

    let valid = event(
        "run-3",
        "event-1",
        "1",
        "appended",
        JsonNumber::Float(1.25),
        false,
    );
    append_ledger_event(&report_dir, &valid, Some(&runtime.0))
        .expect("append ignores malformed previous event lines");
    let text = fs::read_to_string(&work_log).expect("work log text is readable");
    assert!(text.contains("- ledger_event={malformed"));
    assert!(text.contains("\"event_id\":\"event-1\""));
    let error = match read_ledger_snapshot(&report_dir, "snapshot", Some(&runtime.0)) {
        Ok(_) => panic!("snapshot reading rejects malformed event lines"),
        Err(error) => error,
    };
    assert!(error.contains("malformed ledger event"));
}

#[test]
fn work_log_api_rejects_agent_canon_source_paths() {
    let source_path = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/work-log-source-write");
    let error = append_work_entry(&source_path, "must not write", None)
        .expect_err("work logs cannot write below AgentCanon source");
    assert!(error.contains("inside source root") || error.contains("path escapes runtime root"));
    assert!(!source_path.exists());
}
