// @dependency-start
// contract implementation
// responsibility Reads and validates existing semantic work-log snapshots.
// upstream implementation python_json.rs owns Python-compatible JSON parsing, canonical bytes, and equality.
// upstream implementation runtime_boundary.rs owns external runtime path and read capabilities.
// downstream implementation report_artifact_checks.rs validates the visible work-log completion view.
// downstream implementation ../tests/work_log_native.rs preserves read and digest oracles.
// @dependency-end

use crate::python_json::{
    canonical_json_ascii_bytes, parse_json, JsonObject, JsonString, JsonValue,
};
use crate::runtime_boundary::{RuntimeArtifactBoundary, RuntimeDirectory};
use sha2::{Digest, Sha256};
use std::env;
use std::fmt::Write as _;
use std::fs;
use std::path::{Path, PathBuf};

pub const LEDGER_SEMANTIC_KINDS: &[&str] = &[
    "request_clause",
    "responsibility_unit",
    "decision",
    "change",
    "review_finding",
    "validation",
    "failure",
    "publication_state",
    "deferral",
];

const NON_GROUPABLE_SEMANTIC_KINDS: &[&str] = &[
    "responsibility_unit",
    "decision",
    "failure",
    "deferral",
    "publication_state",
];
const MONITOR_PASSTHROUGH_FIELDS: &[&str] = &[
    "gate_evidence",
    "failure_response",
    "resource_certificate",
    "source_binding",
    "monitor_evidence",
    "monitoring_evidence",
];
const MIN_GROUP_MEMBER_COUNT: usize = 2;
const LEDGER_EVENT_PREFIX: &str = "- ledger_event=";

pub struct LedgerSnapshot {
    pub snapshot_identity: String,
    pub events: Vec<JsonValue>,
    pub event_identities: Vec<JsonString>,
    pub snapshot_digest: String,
}

struct WorkLogStore {
    directory: RuntimeDirectory,
    work_log_relative: PathBuf,
    work_log_path: PathBuf,
    report_id: String,
}

impl WorkLogStore {
    fn open(report_dir: &Path, runtime_root: Option<&Path>) -> Result<Self, String> {
        if !report_dir.is_absolute() {
            return Err(format!(
                "explicit external runtime path required for relative report directory: {}",
                report_dir.display()
            ));
        }
        let source = agent_canon_source_root();
        let configured_root = configured_runtime_root(runtime_root);
        let (boundary, report_relative) = if let Some(root) = configured_root.as_deref() {
            let boundary = RuntimeArtifactBoundary::for_source(&source, Some(root), false)?;
            let resolved = if report_dir == boundary.root()
                || fs::canonicalize(report_dir).ok().as_deref() == Some(boundary.root())
            {
                boundary.root().to_path_buf()
            } else {
                boundary.resolve(report_dir)?
            };
            let relative = resolved
                .strip_prefix(boundary.root())
                .map_err(|_| format!("path escapes runtime root: {}", report_dir.display()))?
                .to_path_buf();
            (boundary, relative)
        } else {
            let boundary = RuntimeArtifactBoundary::for_source(&source, Some(report_dir), false)?;
            (boundary, PathBuf::new())
        };
        let directory = RuntimeDirectory::open_nofollow(boundary.root(), false)
            .map_err(|error| format!("runtime root is unavailable: {error}"))?;
        let runtime_root = boundary.root();
        let work_log_relative = report_relative.join("work_log.md");
        let work_log_path = runtime_root.join(&work_log_relative);
        let report_id = report_dir
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or_else(|| "report directory requires a UTF-8 run id".to_string())?
            .to_owned();
        Ok(Self {
            directory,
            work_log_relative,
            work_log_path,
            report_id,
        })
    }

    fn read_work_log(&self) -> Result<Option<Vec<u8>>, String> {
        self.directory
            .read(&self.work_log_relative)
            .map_err(|error| {
                format!(
                    "cannot read work log {}: {error}",
                    self.work_log_path.display()
                )
            })
    }
}

fn agent_canon_source_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .expect("AgentCanon crate lives below the repository root")
        .to_path_buf()
}

fn configured_runtime_root(explicit: Option<&Path>) -> Option<PathBuf> {
    if let Some(root) = explicit {
        return Some(root.to_path_buf());
    }
    env::var_os("AGENT_CANON_RUNTIME_ROOT")
        .filter(|value| !value.to_string_lossy().trim().is_empty())
        .map(PathBuf::from)
}

fn object_get<'a>(object: &'a JsonObject, key: &str) -> Option<&'a JsonValue> {
    object
        .0
        .iter()
        .find_map(|(candidate, value)| candidate.equals_text(key).then_some(value))
}

fn object_get_any<'a>(object: &'a JsonObject, first: &str, second: &str) -> Option<&'a JsonValue> {
    object_get(object, first).or_else(|| object_get(object, second))
}

fn as_object(value: &JsonValue) -> Option<&JsonObject> {
    match value {
        JsonValue::Object(object) => Some(object),
        _ => None,
    }
}

fn as_string(value: &JsonValue) -> Option<&JsonString> {
    match value {
        JsonValue::String(text) => Some(text),
        _ => None,
    }
}

fn py_whitespace(codepoint: u32) -> bool {
    matches!(
        codepoint,
        0x09..=0x0d
            | 0x1c..=0x20
            | 0x85
            | 0xa0
            | 0x1680
            | 0x2000..=0x200a
            | 0x2028..=0x2029
            | 0x202f
            | 0x205f
            | 0x3000
    )
}

fn strip_python_whitespace(value: &JsonString) -> JsonString {
    let mut start = 0;
    let mut end = value.0.len();
    while start < end && py_whitespace(value.0[start]) {
        start += 1;
    }
    while start < end && py_whitespace(value.0[end - 1]) {
        end -= 1;
    }
    JsonString(value.0[start..end].to_vec())
}

fn required_text(event: &JsonObject, field: &str) -> Result<JsonString, String> {
    let value = object_get(event, field).and_then(as_string);
    let Some(value) = value else {
        return Err(format!("ledger event requires {field}"));
    };
    let value = strip_python_whitespace(value);
    if value.is_empty() {
        return Err(format!("ledger event requires {field}"));
    }
    Ok(value)
}

fn printable(value: &JsonString) -> String {
    value.to_text().unwrap_or_else(|| {
        let mut output = String::new();
        for codepoint in &value.0 {
            if let Some(character) = char::from_u32(*codepoint) {
                output.push(character);
            } else {
                let _ = write!(output, "\\u{codepoint:04x}");
            }
        }
        output
    })
}

fn required_refs(event: &JsonObject, field: &str) -> Result<(), String> {
    let Some(JsonValue::Array(items)) = object_get(event, field) else {
        return Err(format!("ledger event requires non-empty {field}"));
    };
    if items.0.is_empty() {
        return Err(format!("ledger event requires non-empty {field}"));
    }
    for item in &items.0 {
        let Some(text) = as_string(item) else {
            return Err(format!(
                "ledger event {field} must contain only non-empty strings"
            ));
        };
        if strip_python_whitespace(text).is_empty() {
            return Err(format!(
                "ledger event {field} must contain only non-empty strings"
            ));
        }
    }
    Ok(())
}

fn event_identity_value(event: &JsonObject) -> Option<&JsonValue> {
    object_get(event, "event_id").or_else(|| object_get(event, "sequence"))
}

fn validate_ledger_event(event: &JsonValue, report_id: &str) -> Result<JsonString, String> {
    let Some(event) = as_object(event) else {
        return Err("ledger event must be an object".to_owned());
    };
    let run_id = required_text(event, "run_id")?;
    if !run_id.equals_text(report_id) {
        return Err("ledger event run_id does not match report directory".to_owned());
    }
    let context_id = required_text(event, "context_id")?;
    let identity = event_identity_value(event)
        .and_then(as_string)
        .map(strip_python_whitespace)
        .filter(|identity| !identity.is_empty())
        .ok_or_else(|| "ledger event requires event_id or sequence".to_owned())?;
    let semantic_kind = required_text(event, "semantic_kind")?;
    if !LEDGER_SEMANTIC_KINDS
        .iter()
        .any(|kind| semantic_kind.equals_text(kind))
    {
        return Err(format!(
            "unsupported semantic_kind: {}",
            printable(&semantic_kind)
        ));
    }
    for field in [
        "owner",
        "state_owner",
        "api_owner",
        "dependency_owner",
        "responsibility_unit",
        "intent_id",
        "outcome",
    ] {
        required_text(event, field)?;
    }
    required_refs(event, "evidence_refs")?;
    required_refs(event, "artifact_refs")?;

    if let Some(clause_id) = object_get(event, "clause_id") {
        match clause_id {
            JsonValue::Null => {}
            JsonValue::String(value) if !strip_python_whitespace(value).is_empty() => {}
            _ => return Err("ledger event clause_id must be null or non-empty text".into()),
        }
    }

    let mapping_mode = match object_get(event, "mapping_mode") {
        None => JsonString::from_text("direct"),
        Some(value) => as_string(value)
            .map(strip_python_whitespace)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| "ledger event mapping_mode must be non-empty text".to_owned())?,
    };
    if !mapping_mode.equals_text("direct") && !mapping_mode.equals_text("group") {
        return Err("ledger event mapping_mode must be direct or group".into());
    }
    if mapping_mode.equals_text("group") {
        if NON_GROUPABLE_SEMANTIC_KINDS
            .iter()
            .any(|kind| semantic_kind.equals_text(kind))
        {
            return Err(format!(
                "{} ledger events cannot be grouped",
                printable(&semantic_kind)
            ));
        }
        let group_identity = object_get_any(event, "group_identity", "group_id")
            .and_then(as_string)
            .map(strip_python_whitespace)
            .filter(|value| !value.is_empty());
        if group_identity.is_none() {
            return Err("group ledger events require group_identity".into());
        }
        let Some(JsonValue::Array(members)) = object_get(event, "member_clause_ids") else {
            return Err("group ledger events require member_clause_ids".into());
        };
        if members.0.len() < MIN_GROUP_MEMBER_COUNT {
            return Err("group ledger events require member_clause_ids".into());
        }
        let mut normalized = Vec::with_capacity(members.0.len());
        for member in &members.0 {
            let Some(member) = as_string(member) else {
                return Err("group member_clause_ids must be non-empty text".into());
            };
            let member = strip_python_whitespace(member);
            if member.is_empty() {
                return Err("group member_clause_ids must be non-empty text".into());
            }
            if normalized.contains(&member) {
                return Err("group member_clause_ids must be unique".into());
            }
            normalized.push(member);
        }
    }

    if let Some(source_binding) = object_get(event, "source_binding") {
        if !matches!(source_binding, JsonValue::Null) {
            let Some(binding) = as_object(source_binding) else {
                return Err("ledger event source_binding must be an object".into());
            };
            let binding_run_id = object_get(binding, "run_id")
                .and_then(as_string)
                .map(strip_python_whitespace)
                .filter(|value| !value.is_empty())
                .ok_or_else(|| "ledger event source_binding requires run_id".to_owned())?;
            let binding_context_id = object_get(binding, "context_id")
                .and_then(as_string)
                .map(strip_python_whitespace)
                .filter(|value| !value.is_empty())
                .ok_or_else(|| "ledger event source_binding requires context_id".to_owned())?;
            if binding_run_id != run_id {
                return Err("ledger event source_binding.run_id does not match run_id".into());
            }
            if binding_context_id != context_id {
                return Err(
                    "ledger event source_binding.context_id does not match context_id".into(),
                );
            }
        }
    }

    for field in MONITOR_PASSTHROUGH_FIELDS {
        if *field == "source_binding" {
            continue;
        }
        if let Some(value) = object_get(event, field) {
            if !matches!(
                value,
                JsonValue::Null | JsonValue::Object(_) | JsonValue::Array(_)
            ) {
                return Err(format!(
                    "ledger event {field} must remain structured evidence"
                ));
            }
        }
    }
    Ok(identity)
}

pub fn read_ledger_snapshot(
    report_dir: &Path,
    snapshot_identity: &str,
    runtime_root: Option<&Path>,
) -> Result<LedgerSnapshot, String> {
    let snapshot_identity = strip_python_whitespace(&JsonString::from_text(snapshot_identity));
    if snapshot_identity.is_empty() {
        return Err("snapshot_identity must not be empty".into());
    }
    let snapshot_identity = snapshot_identity
        .to_text()
        .expect("Rust text contains no surrogate code points");
    if !report_dir.is_absolute() {
        return Err(format!(
            "explicit external runtime path required for relative report directory: {}",
            report_dir.display()
        ));
    }
    if !report_dir.is_dir() {
        return Err(format!(
            "missing work log: {}",
            report_dir.join("work_log.md").display()
        ));
    }
    let store = WorkLogStore::open(report_dir, runtime_root)?;
    let Some(bytes) = store.read_work_log()? else {
        return Err(format!(
            "missing work log: {}",
            store.work_log_path.display()
        ));
    };
    let text = String::from_utf8(bytes)
        .map_err(|error| format!("work log is not valid UTF-8: {error}"))?;
    let mut events = Vec::new();
    let mut identities = Vec::<JsonString>::new();
    for line in python_split_lines(&text) {
        let Some(serialized) = line.strip_prefix(LEDGER_EVENT_PREFIX) else {
            continue;
        };
        let event = parse_json(serialized).map_err(|_| "malformed ledger event".to_owned())?;
        if !matches!(&event, JsonValue::Object(_)) {
            return Err("ledger event must be an object".into());
        }
        let identity = validate_ledger_event(&event, &store.report_id)?;
        if identities.contains(&identity) {
            return Err(format!(
                "duplicate ledger event identity: {}",
                printable(&identity)
            ));
        }
        identities.push(identity);
        events.push(event);
    }

    let mut keyed_events: Vec<(JsonString, JsonString, JsonValue)> = events
        .into_iter()
        .map(|event| {
            let object = as_object(&event).expect("events are validated objects");
            let sequence = object_get(object, "sequence")
                .map(python_string)
                .unwrap_or_default();
            let event_id = object_get(object, "event_id")
                .or_else(|| object_get(object, "sequence"))
                .map(python_string)
                .unwrap_or_default();
            (sequence, event_id, event)
        })
        .collect();
    keyed_events.sort_by(|left, right| (&left.0, &left.1).cmp(&(&right.0, &right.1)));
    let events = keyed_events
        .into_iter()
        .map(|(_, _, event)| event)
        .collect();
    identities.sort();
    let mut snapshot = LedgerSnapshot {
        snapshot_identity,
        events,
        event_identities: identities,
        snapshot_digest: String::new(),
    };
    snapshot.snapshot_digest = ledger_snapshot_digest(&snapshot)?;
    Ok(snapshot)
}

pub fn ledger_snapshot_digest(snapshot: &LedgerSnapshot) -> Result<String, String> {
    let bytes = canonical_event_array_bytes(&snapshot.events)?;
    Ok(Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

fn canonical_event_array_bytes(events: &[JsonValue]) -> Result<Vec<u8>, String> {
    let mut bytes = Vec::new();
    bytes.push(b'[');
    for (index, event) in events.iter().enumerate() {
        if !matches!(event, &JsonValue::Object(_)) {
            return Err("ledger snapshot events must be a list".into());
        }
        if index > 0 {
            bytes.push(b',');
        }
        bytes.extend_from_slice(&canonical_json_ascii_bytes(event)?);
    }
    bytes.push(b']');
    Ok(bytes)
}

enum ReprAction<'a> {
    Value(&'a JsonValue),
    String(&'a JsonString),
    Text(&'static str),
}

fn python_string(value: &JsonValue) -> JsonString {
    match value {
        JsonValue::Null => JsonString::from_text("None"),
        JsonValue::Bool(true) => JsonString::from_text("True"),
        JsonValue::Bool(false) => JsonString::from_text("False"),
        JsonValue::Number(value) => JsonString::from_text(&value.python_string()),
        JsonValue::String(value) => value.clone(),
        JsonValue::Array(_) | JsonValue::Object(_) => python_repr(value),
    }
}

fn python_repr(value: &JsonValue) -> JsonString {
    let mut output = JsonString::default();
    let mut actions = vec![ReprAction::Value(value)];
    while let Some(action) = actions.pop() {
        match action {
            ReprAction::Text(text) => output.push_text(text),
            ReprAction::String(value) => output.0.extend(python_string_repr(value).0),
            ReprAction::Value(value) => match value {
                JsonValue::Null => output.push_text("None"),
                JsonValue::Bool(true) => output.push_text("True"),
                JsonValue::Bool(false) => output.push_text("False"),
                JsonValue::Number(value) => output.push_text(&value.python_string()),
                JsonValue::String(value) => output.0.extend(python_string_repr(value).0),
                JsonValue::Array(values) => {
                    output.push_text("[");
                    actions.push(ReprAction::Text("]"));
                    for index in (0..values.0.len()).rev() {
                        actions.push(ReprAction::Value(&values.0[index]));
                        if index > 0 {
                            actions.push(ReprAction::Text(", "));
                        }
                    }
                }
                JsonValue::Object(values) => {
                    output.push_text("{");
                    actions.push(ReprAction::Text("}"));
                    for index in (0..values.0.len()).rev() {
                        let (key, value) = &values.0[index];
                        actions.push(ReprAction::Value(value));
                        actions.push(ReprAction::Text(": "));
                        actions.push(ReprAction::String(key));
                        if index > 0 {
                            actions.push(ReprAction::Text(", "));
                        }
                    }
                }
            },
        }
    }
    output
}

fn python_string_repr(value: &JsonString) -> JsonString {
    let Some(text) = value.to_text() else {
        return python_string_repr_with_surrogates(value);
    };
    JsonString::from_text(&rustpython_ast::Constant::Str(text).to_string())
}

fn python_string_repr_with_surrogates(value: &JsonString) -> JsonString {
    let scalar_projection: String = value
        .0
        .iter()
        .filter_map(|codepoint| char::from_u32(*codepoint))
        .collect();
    let probe = rustpython_ast::Constant::Str(scalar_projection).to_string();
    let quote = probe
        .chars()
        .next()
        .expect("RustPython string repr has quotes");
    let mut rendered = String::with_capacity(probe.len() + value.0.len() * 6);
    rendered.push(quote);
    let mut segment = String::new();
    for &codepoint in &value.0 {
        if let Some(character) = char::from_u32(codepoint) {
            segment.push(character);
        } else {
            rendered.push_str(&rustpython_string_repr_segment(&segment, quote));
            segment.clear();
            let _ = write!(rendered, "\\u{codepoint:04x}");
        }
    }
    rendered.push_str(&rustpython_string_repr_segment(&segment, quote));
    rendered.push(quote);
    JsonString::from_text(&rendered)
}

fn rustpython_string_repr_segment(segment: &str, quote: char) -> String {
    if segment.is_empty() {
        return String::new();
    }
    let helper_quote = if quote == '\'' { '"' } else { '\'' };
    let mut with_helper_quote = segment.to_owned();
    with_helper_quote.push(helper_quote);
    let repr = rustpython_ast::Constant::Str(with_helper_quote).to_string();
    let body = repr
        .strip_prefix(quote)
        .and_then(|repr| repr.strip_suffix(quote))
        .expect("RustPython repr quote matches the whole string quote");
    body.strip_suffix(helper_quote)
        .expect("the helper quote remains a trailing literal character")
        .to_owned()
}

fn python_split_lines(text: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut chars = text.char_indices().peekable();
    while let Some((index, character)) = chars.next() {
        if matches!(
            character,
            '\n' | '\r'
                | '\u{000b}'
                | '\u{000c}'
                | '\u{001c}'
                | '\u{001d}'
                | '\u{001e}'
                | '\u{0085}'
                | '\u{2028}'
                | '\u{2029}'
        ) {
            lines.push(&text[start..index]);
            if character == '\r' {
                if let Some((next_index, '\n')) = chars.peek().copied() {
                    chars.next();
                    start = next_index + '\n'.len_utf8();
                    continue;
                }
            }
            start = index + character.len_utf8();
        }
    }
    if start < text.len() {
        lines.push(&text[start..]);
    }
    lines
}
