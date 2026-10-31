// @dependency-start
// contract implementation
// responsibility Owns native immutable update-lifecycle record binding and gate-verdict mechanics.
// upstream design ../../../../../documents/agent-canon/agent-canon-update-route.md owns update lifecycle meaning
// upstream implementation artifacts/artifact_identity.rs owns canonical JSON bytes and body hashes
// upstream implementation ../../../../../tools/runtime/lifecycle/update_lifecycle_contract.py remains the full lifecycle owner until later slices migrate
// downstream implementation ../../../../../tests/agent_tools/test_publication_integrator.py checks gate identity replay stability
// downstream implementation ../../../../../tests/agent_tools/test_github_publish.py consumes G3 gate verdicts
// downstream implementation ../../../../../tests/agent_tools/test_bootstrap_and_close.py consumes gate chains at closeout
// @dependency-end

use crate::artifacts::artifact_identity::canonical_json_bytes;
use serde_json::{Map as JsonMap, Value as JsonValue};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

pub const TRANSACTION_STATES: &[&str] = &[
    "created",
    "prepared",
    "generated",
    "gates_ready",
    "reviewed",
    "pr_open",
    "pr_merged",
    "source_main_readback",
    "queue_enqueued",
    "frontier_accepted",
    "remote_readback",
    "durable_handback",
    "descendants_closed",
    "reservations_released",
    "cleanup_proven",
    "nested_lifecycle_cleanup",
    "closed",
    "failed",
    "successor_required",
];

const GATE_IDS: &[&str] = &["G1", "G2", "G3", "G4", "G5", "G6"];
const CHECKPOINT_IDS: &[&str] = &[
    "prepare",
    "generate",
    "G1",
    "G2",
    "G3",
    "source_main_readback",
    "queue",
    "frontier",
    "G4",
    "remote_readback",
    "G5",
    "handback",
    "descendants",
    "reservations",
    "cleanup",
    "G6",
    "nested_lifecycle_cleanup",
];
const BINDING_FIELDS: &[&str] = &[
    "transaction_id",
    "snapshot_id",
    "candidate_sha",
    "tree_sha",
    "input_digest",
    "tool_id",
    "tool_version",
    "evidence_ref",
    "evidence_digest",
    "timing",
];
const TIMING_FIELDS: &[&str] = &[
    "started_at",
    "finished_at",
    "last_attempt_at",
    "duration_ms",
    "attempt",
    "replayed",
];
const GATE_VERDICT_FIELDS: &[&str] = &[
    "schema",
    "binding",
    "gate_id",
    "ordered_input_evidence_refs",
    "invariant",
    "output_digest",
    "owner",
    "verdict",
    "retry_reason",
    "next_checkpoint",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LifecycleContractError {
    pub code: String,
    pub detail: String,
}
impl LifecycleContractError {
    fn new(code: impl Into<String>, detail: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            detail: detail.into(),
        }
    }
    fn code(code: impl Into<String>) -> Self {
        Self::new(code, "")
    }
}
impl fmt::Display for LifecycleContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.detail.is_empty() {
            formatter.write_str(&self.code)
        } else {
            write!(formatter, "{}:{}", self.code, self.detail)
        }
    }
}
impl std::error::Error for LifecycleContractError {}
impl From<crate::artifacts::artifact_identity::ArtifactIdentityError> for LifecycleContractError {
    fn from(error: crate::artifacts::artifact_identity::ArtifactIdentityError) -> Self {
        Self::new(error.code, error.detail)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct RecordBindingIdentity {
    pub transaction_id: String,
    pub snapshot_id: String,
    pub candidate_sha: String,
    pub tree_sha: String,
    pub input_digest: String,
    pub tool_id: String,
    pub tool_version: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GateVerdictInput {
    pub binding: JsonValue,
    pub gate_id: String,
    pub ordered_input_evidence_refs: Vec<String>,
    pub invariant: String,
    pub output_digest: String,
    pub owner: String,
    pub verdict: String,
    pub retry_reason: Option<String>,
    pub next_checkpoint: Option<String>,
}

fn fail(code: &str, detail: &str) -> LifecycleContractError {
    LifecycleContractError::new(code, detail)
}

fn mapping<'a>(
    value: &'a JsonValue,
    field: &str,
) -> Result<&'a JsonMap<String, JsonValue>, LifecycleContractError> {
    value
        .as_object()
        .ok_or_else(|| fail("lifecycle:mapping_required", field))
}

fn exact_keys(
    record: &JsonMap<String, JsonValue>,
    required: &[&str],
    optional: &[&str],
    field: &str,
) -> Result<(), LifecycleContractError> {
    let actual = record.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let required = required.iter().copied().collect::<BTreeSet<_>>();
    let mut allowed = required.clone();
    allowed.extend(optional.iter().copied());
    let missing = required.difference(&actual).copied().collect::<Vec<_>>();
    let extra = actual.difference(&allowed).copied().collect::<Vec<_>>();
    if !missing.is_empty() {
        return Err(fail(
            "lifecycle:field_missing",
            &format!("{field}:{}", missing.join(",")),
        ));
    }
    if !extra.is_empty() {
        return Err(fail(
            "lifecycle:field_forbidden",
            &format!("{field}:{}", extra.join(",")),
        ));
    }
    Ok(())
}

fn required_value<'a>(
    record: &'a JsonMap<String, JsonValue>,
    key: &str,
    parent: &str,
) -> Result<&'a JsonValue, LifecycleContractError> {
    record
        .get(key)
        .ok_or_else(|| fail("lifecycle:field_missing", &format!("{parent}.{key}")))
}

fn string_value(value: &JsonValue, field: &str) -> Result<String, LifecycleContractError> {
    value
        .as_str()
        .filter(|text| !text.is_empty())
        .map(str::to_string)
        .ok_or_else(|| fail("lifecycle:string_invalid", field))
}

fn required_string(
    record: &JsonMap<String, JsonValue>,
    key: &str,
    parent: &str,
) -> Result<String, LifecycleContractError> {
    string_value(
        required_value(record, key, parent)?,
        &format!("{parent}.{key}"),
    )
}

fn lower_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn valid_hash_id(value: &str) -> bool {
    let Some((prefix, digest)) = value.split_once(':') else {
        return false;
    };
    matches!(
        prefix,
        "tx" | "snapshot"
            | "rebind"
            | "freeze"
            | "review"
            | "cas"
            | "publication-readback"
            | "queue"
            | "queue-key"
            | "frontier"
            | "frontier-key"
            | "pr-successor"
            | "close-token"
    ) && lower_hex(digest, 64)
}

fn valid_sha256(value: &str) -> bool {
    value
        .strip_prefix("sha256:")
        .is_some_and(|digest| lower_hex(digest, 64))
}

fn valid_evidence_ref(value: &str) -> bool {
    value
        .strip_prefix("evidence:")
        .is_some_and(|digest| lower_hex(digest, 64))
}

fn pattern_value(
    value: &JsonValue,
    field: &str,
    predicate: impl FnOnce(&str) -> bool,
) -> Result<String, LifecycleContractError> {
    let rendered = string_value(value, field)?;
    if !predicate(&rendered) {
        return Err(fail("lifecycle:identity_invalid", field));
    }
    Ok(rendered)
}

fn positive_integer(
    value: &JsonValue,
    field: &str,
    zero_allowed: bool,
) -> Result<(), LifecycleContractError> {
    let integer = value
        .as_i64()
        .filter(|integer| *integer >= 0)
        .map(|integer| integer as u64)
        .or_else(|| value.as_u64())
        .filter(|integer| if zero_allowed { true } else { *integer >= 1 });
    integer
        .map(|_| ())
        .ok_or_else(|| fail("lifecycle:integer_invalid", field))
}

fn boolean_value(value: &JsonValue, field: &str) -> Result<(), LifecycleContractError> {
    if value.is_boolean() {
        Ok(())
    } else {
        Err(fail("lifecycle:boolean_invalid", field))
    }
}

fn leap_year(year: u32) -> bool {
    year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
}

fn valid_calendar_date(year: u32, month: u32, day: u32) -> bool {
    if year == 0 || year > 9999 || !(1..=12).contains(&month) {
        return false;
    }
    let days = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if leap_year(year) => 29,
        2 => 28,
        _ => return false,
    };
    (1..=days).contains(&day)
}

fn decimal(value: &str) -> Option<u32> {
    if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    value.parse().ok()
}

fn valid_iso_week_date(year: u32, week: u32, weekday: u32) -> bool {
    if year == 0 || year > 9999 || !(1..=7).contains(&weekday) {
        return false;
    }
    let prior = year - 1;
    let days_before_year = 365 * prior + prior / 4 - prior / 100 + prior / 400;
    let jan_first_weekday = days_before_year % 7 + 1;
    let weeks = if jan_first_weekday == 4 || (jan_first_weekday == 3 && leap_year(year)) {
        53
    } else {
        52
    };
    (1..=weeks).contains(&week)
}

fn date_prefix_length(value: &str) -> Option<usize> {
    let bytes = value.as_bytes();
    let year = decimal(value.get(0..4)?)?;
    if value.len() >= 10 && bytes.get(4) == Some(&b'-') && bytes.get(7) == Some(&b'-') {
        let month = decimal(value.get(5..7)?)?;
        let day = decimal(value.get(8..10)?)?;
        return valid_calendar_date(year, month, day).then_some(10);
    }
    if value.len() >= 8 && bytes.get(4) == Some(&b'-') && bytes.get(5) == Some(&b'W') {
        let week = decimal(value.get(6..8)?)?;
        if value.len() >= 10 && bytes.get(8) == Some(&b'-') {
            return valid_iso_week_date(year, week, decimal(value.get(9..10)?)?).then_some(10);
        }
        return None;
    }
    if value.len() >= 8 && bytes.get(4).is_some_and(u8::is_ascii_digit) {
        if value.get(0..8)?.bytes().all(|byte| byte.is_ascii_digit()) {
            let month = decimal(value.get(4..6)?)?;
            let day = decimal(value.get(6..8)?)?;
            return valid_calendar_date(year, month, day).then_some(8);
        }
    }
    if value.len() >= 7 && bytes.get(4) == Some(&b'W') {
        let week = decimal(value.get(5..7)?)?;
        if value.len() >= 8 && bytes.get(7).is_some_and(u8::is_ascii_digit) {
            return valid_iso_week_date(year, week, decimal(value.get(7..8)?)?).then_some(8);
        }
        return None;
    }
    None
}

fn parse_clock_components(value: &str) -> Option<(u32, u32, u32, bool)> {
    let parts = if value.contains(':') {
        let parts = value.split(':').collect::<Vec<_>>();
        if !(2..=3).contains(&parts.len()) || parts.iter().any(|part| part.len() != 2) {
            return None;
        }
        parts
    } else {
        if !matches!(value.len(), 2 | 4 | 6) || !value.bytes().all(|byte| byte.is_ascii_digit()) {
            return None;
        }
        value
            .as_bytes()
            .chunks(2)
            .map(|part| std::str::from_utf8(part).ok())
            .collect::<Option<Vec<_>>>()?
    };
    let hour = decimal(parts[0])?;
    let minute = decimal(parts[1])?;
    let second = if parts.len() == 3 {
        decimal(parts[2])?
    } else {
        0
    };
    Some((hour, minute, second, parts.len() == 3))
}

fn valid_clock(value: &str) -> bool {
    let (clock, has_fraction) = match value.find(|character| character == '.' || character == ',') {
        Some(index) => {
            let clock = &value[..index];
            let fraction = &value[index + 1..];
            if fraction.is_empty() || !fraction.bytes().all(|byte| byte.is_ascii_digit()) {
                return false;
            }
            (clock, true)
        }
        None => (value, false),
    };
    let Some((hour, minute, second, has_seconds)) = parse_clock_components(clock) else {
        return false;
    };
    (!has_fraction || has_seconds) && hour < 24 && minute < 60 && second < 60
}

fn valid_timezone_offset(value: &str) -> bool {
    let Some(sign) = value.chars().next() else {
        return false;
    };
    if sign != '+' && sign != '-' {
        return false;
    }
    let offset = &value[sign.len_utf8()..];
    let (clock, has_fraction) = match offset.find(|character| character == '.' || character == ',')
    {
        Some(index) => {
            let clock = &offset[..index];
            let fraction = &offset[index + 1..];
            if fraction.is_empty() || !fraction.bytes().all(|byte| byte.is_ascii_digit()) {
                return false;
            }
            (clock, true)
        }
        None => (offset, false),
    };
    let Some((hour, minute, second, has_seconds)) = parse_clock_components(clock) else {
        return false;
    };
    (!has_fraction || has_seconds) && hour < 24 && minute < 60 && second < 60
}

fn valid_iso_time(value: &str) -> bool {
    if let Some(clock) = value.strip_suffix('Z') {
        return valid_clock(clock);
    }
    if let Some((index, _)) = value
        .char_indices()
        .find(|(index, character)| *index > 0 && (*character == '+' || *character == '-'))
    {
        return valid_clock(&value[..index]) && valid_timezone_offset(&value[index..]);
    }
    valid_clock(value)
}

fn valid_iso_datetime(value: &str) -> bool {
    let Some(date_len) = date_prefix_length(value) else {
        return false;
    };
    if value.len() == date_len {
        return true;
    }
    let Some((separator, time)) = value.get(date_len..).and_then(|suffix| {
        let mut characters = suffix.chars();
        Some((characters.next()?, characters.as_str()))
    }) else {
        return false;
    };
    separator != 'Z' && !time.is_empty() && valid_iso_time(time)
}

fn rfc3339(value: &JsonValue, field: &str) -> Result<(), LifecycleContractError> {
    let rendered = string_value(value, field)?;
    if valid_iso_datetime(&rendered) {
        Ok(())
    } else {
        Err(fail("lifecycle:timestamp_invalid", field))
    }
}

fn validate_timing(value: &JsonValue) -> Result<(), LifecycleContractError> {
    let timing = mapping(value, "binding.timing")?;
    exact_keys(timing, TIMING_FIELDS, &[], "binding.timing")?;
    rfc3339(
        required_value(timing, "started_at", "binding.timing")?,
        "binding.timing.started_at",
    )?;
    let finished = required_value(timing, "finished_at", "binding.timing")?;
    if !finished.is_null() {
        rfc3339(finished, "binding.timing.finished_at")?;
    }
    rfc3339(
        required_value(timing, "last_attempt_at", "binding.timing")?,
        "binding.timing.last_attempt_at",
    )?;
    positive_integer(
        required_value(timing, "duration_ms", "binding.timing")?,
        "binding.timing.duration_ms",
        true,
    )?;
    positive_integer(
        required_value(timing, "attempt", "binding.timing")?,
        "binding.timing.attempt",
        false,
    )?;
    boolean_value(
        required_value(timing, "replayed", "binding.timing")?,
        "binding.timing.replayed",
    )
}

fn canonical_clone(value: &JsonValue) -> Result<JsonValue, LifecycleContractError> {
    let bytes = canonical_json_bytes(value).map_err(LifecycleContractError::from)?;
    serde_json::from_slice(&bytes)
        .map_err(|error| fail("lifecycle:canonical_json_invalid", &error.to_string()))
}

fn binding_identity_from_validated(
    binding: &JsonValue,
) -> Result<RecordBindingIdentity, LifecycleContractError> {
    let mapping = mapping(binding, "binding")?;
    Ok(RecordBindingIdentity {
        transaction_id: required_string(mapping, "transaction_id", "binding")?,
        snapshot_id: required_string(mapping, "snapshot_id", "binding")?,
        candidate_sha: required_string(mapping, "candidate_sha", "binding")?,
        tree_sha: required_string(mapping, "tree_sha", "binding")?,
        input_digest: required_string(mapping, "input_digest", "binding")?,
        tool_id: required_string(mapping, "tool_id", "binding")?,
        tool_version: required_string(mapping, "tool_version", "binding")?,
    })
}

pub fn validate_record_binding(value: &JsonValue) -> Result<JsonValue, LifecycleContractError> {
    let binding = mapping(value, "binding")?;
    exact_keys(binding, BINDING_FIELDS, &[], "binding")?;
    let transaction_id = pattern_value(
        required_value(binding, "transaction_id", "binding")?,
        "binding.transaction_id",
        valid_hash_id,
    )?;
    let snapshot_id = pattern_value(
        required_value(binding, "snapshot_id", "binding")?,
        "binding.snapshot_id",
        valid_hash_id,
    )?;
    if !transaction_id.starts_with("tx:") {
        return Err(fail("lifecycle:identity_invalid", "binding.transaction_id"));
    }
    if !snapshot_id.starts_with("snapshot:") {
        return Err(fail("lifecycle:identity_invalid", "binding.snapshot_id"));
    }
    pattern_value(
        required_value(binding, "candidate_sha", "binding")?,
        "binding.candidate_sha",
        |text| lower_hex(text, 40),
    )?;
    pattern_value(
        required_value(binding, "tree_sha", "binding")?,
        "binding.tree_sha",
        |text| lower_hex(text, 40),
    )?;
    pattern_value(
        required_value(binding, "input_digest", "binding")?,
        "binding.input_digest",
        valid_sha256,
    )?;
    string_value(
        required_value(binding, "tool_id", "binding")?,
        "binding.tool_id",
    )?;
    string_value(
        required_value(binding, "tool_version", "binding")?,
        "binding.tool_version",
    )?;
    pattern_value(
        required_value(binding, "evidence_ref", "binding")?,
        "binding.evidence_ref",
        valid_evidence_ref,
    )?;
    pattern_value(
        required_value(binding, "evidence_digest", "binding")?,
        "binding.evidence_digest",
        valid_sha256,
    )?;
    validate_timing(required_value(binding, "timing", "binding")?)?;
    canonical_clone(value)
}

pub fn binding_identity(
    value: &JsonValue,
) -> Result<RecordBindingIdentity, LifecycleContractError> {
    let binding = validate_record_binding(value)?;
    binding_identity_from_validated(&binding)
}

fn gate_contract(gate_id: &str) -> Option<(&'static str, &'static [&'static str])> {
    match gate_id {
        "G1" => Some((
            "source_correctness",
            &["publication_integrator.py#resolve_publication_eligibility"],
        )),
        "G2" => Some((
            "generated_completeness",
            &["check_agent_canon_pr.py#materialize_generated_completeness_receipt"],
        )),
        "G3" => Some((
            "pr_identity_cas",
            &[
                "publication_integrator.py#resolve_publication_authority",
                "github_publish.py#materialize_pr_identity_gate",
            ],
        )),
        "G4" => Some((
            "standalone_source_branch_integrity",
            &[
                "repository_topic_clone.py#_ensure_branch",
                "agents/skills/agent-canon-update.md",
            ],
        )),
        "G5" => Some((
            "remote_publication_readback",
            &["publication_integrator.py#integrate_publication"],
        )),
        "G6" => Some((
            "nested_lifecycle_cleanup",
            &["tool_calls.py#materialize_close_agent_tool_call"],
        )),
        _ => None,
    }
}

fn one_of(
    value: &JsonValue,
    allowed: &[&str],
    field: &str,
) -> Result<String, LifecycleContractError> {
    let rendered = string_value(value, field)?;
    if !allowed.contains(&rendered.as_str()) {
        return Err(fail("lifecycle:enum_invalid", field));
    }
    Ok(rendered)
}

fn string_list(
    value: &JsonValue,
    field: &str,
    nonempty: bool,
    unique: bool,
    predicate: Option<fn(&str) -> bool>,
) -> Result<Vec<String>, LifecycleContractError> {
    let values = value
        .as_array()
        .ok_or_else(|| fail("lifecycle:sequence_required", field))?;
    if nonempty && values.is_empty() {
        return Err(fail("lifecycle:sequence_empty", field));
    }
    let mut result = Vec::with_capacity(values.len());
    let mut seen = BTreeSet::new();
    for (index, value) in values.iter().enumerate() {
        let item_field = format!("{field}[{index}]");
        let text = string_value(value, &item_field)?;
        if predicate.is_some_and(|predicate| !predicate(&text)) {
            return Err(fail("lifecycle:identity_invalid", &item_field));
        }
        if unique && !seen.insert(text.clone()) {
            return Err(fail("lifecycle:duplicate_value", field));
        }
        result.push(text);
    }
    Ok(result)
}

pub fn validate_gate_verdict(value: &JsonValue) -> Result<JsonValue, LifecycleContractError> {
    let verdict = mapping(value, "gate_verdict")?;
    exact_keys(verdict, GATE_VERDICT_FIELDS, &[], "gate_verdict")?;
    if verdict.get("schema").and_then(JsonValue::as_str) != Some("agent-canon.gate-verdict.v1") {
        return Err(fail(
            "lifecycle:schema_invalid",
            "agent-canon.gate-verdict.v1",
        ));
    }
    let binding = required_value(verdict, "binding", "gate_verdict")?;
    validate_record_binding(binding)?;
    let gate_id = one_of(
        required_value(verdict, "gate_id", "gate_verdict")?,
        GATE_IDS,
        "gate_verdict.gate_id",
    )?;
    string_list(
        required_value(verdict, "ordered_input_evidence_refs", "gate_verdict")?,
        "gate_verdict.ordered_input_evidence_refs",
        true,
        true,
        Some(valid_evidence_ref),
    )?;
    let invariant = string_value(
        required_value(verdict, "invariant", "gate_verdict")?,
        "gate_verdict.invariant",
    )?;
    pattern_value(
        required_value(verdict, "output_digest", "gate_verdict")?,
        "gate_verdict.output_digest",
        valid_sha256,
    )?;
    let owner = string_value(
        required_value(verdict, "owner", "gate_verdict")?,
        "gate_verdict.owner",
    )?;
    if !owner.starts_with('/') || !owner.contains('#') {
        return Err(fail("lifecycle:owner_invalid", "gate_verdict.owner"));
    }
    let (expected_invariant, expected_owners) =
        gate_contract(&gate_id).expect("validated gate id has a contract");
    if invariant != expected_invariant {
        return Err(fail("lifecycle:gate_invariant_mismatch", &gate_id));
    }
    if !expected_owners
        .iter()
        .any(|expected| owner.ends_with(expected))
    {
        return Err(fail("lifecycle:gate_owner_mismatch", &gate_id));
    }
    let state = one_of(
        required_value(verdict, "verdict", "gate_verdict")?,
        &["pass", "fail", "retry"],
        "gate_verdict.verdict",
    )?;
    let retry_reason = required_value(verdict, "retry_reason", "gate_verdict")?;
    if state == "retry" {
        string_value(retry_reason, "gate_verdict.retry_reason")?;
    } else if !retry_reason.is_null() {
        return Err(fail("lifecycle:retry_reason_forbidden", "gate_verdict"));
    }
    let next_checkpoint = required_value(verdict, "next_checkpoint", "gate_verdict")?;
    if !next_checkpoint.is_null() {
        one_of(
            next_checkpoint,
            CHECKPOINT_IDS,
            "gate_verdict.next_checkpoint",
        )?;
    }
    canonical_clone(value)
}

pub fn validate_gate_chain(
    values: &[JsonValue],
    expected_gate_ids: Option<&[&str]>,
    require_pass: bool,
) -> Result<Vec<JsonValue>, LifecycleContractError> {
    let gates = values
        .iter()
        .map(validate_gate_verdict)
        .collect::<Result<Vec<_>, _>>()?;
    let gate_ids = gates
        .iter()
        .map(|gate| {
            gate.get("gate_id")
                .and_then(JsonValue::as_str)
                .unwrap_or_default()
        })
        .collect::<Vec<_>>();
    if expected_gate_ids.is_some_and(|expected| expected != gate_ids.as_slice()) {
        return Err(LifecycleContractError::code("lifecycle:gate_order_invalid"));
    }
    if gates.is_empty() {
        return Err(LifecycleContractError::code(
            "lifecycle:gate_sequence_empty",
        ));
    }
    let identity = binding_identity(gates[0].get("binding").expect("validated gate has binding"))?;
    for gate in gates.iter().skip(1) {
        if binding_identity(gate.get("binding").expect("validated gate has binding"))? != identity {
            return Err(LifecycleContractError::code(
                "lifecycle:gate_identity_mismatch",
            ));
        }
    }
    if require_pass
        && gates
            .iter()
            .any(|gate| gate.get("verdict").and_then(JsonValue::as_str) != Some("pass"))
    {
        return Err(LifecycleContractError::code("lifecycle:gate_not_passed"));
    }
    let mut by_id: BTreeMap<String, &JsonValue> = BTreeMap::new();
    for gate in &gates {
        let gate_id = gate
            .get("gate_id")
            .and_then(JsonValue::as_str)
            .expect("validated gate id");
        by_id.insert(gate_id.to_string(), gate);
    }
    let mut evidence = BTreeMap::new();
    for (gate_id, gate) in &by_id {
        let binding = gate
            .get("binding")
            .and_then(JsonValue::as_object)
            .expect("validated gate binding");
        let evidence_ref = binding
            .get("evidence_ref")
            .and_then(JsonValue::as_str)
            .expect("validated evidence ref");
        evidence.insert(gate_id.as_str(), evidence_ref);
    }
    if let Some(g1) = by_id.get("G1") {
        if g1
            .get("ordered_input_evidence_refs")
            .and_then(JsonValue::as_array)
            .is_none_or(Vec::is_empty)
        {
            return Err(fail("lifecycle:gate_predecessor_missing", "G1"));
        }
    }
    let require_prefix = |gate_id: &str, prefix: &[&str]| -> Result<(), LifecycleContractError> {
        let Some(gate) = by_id.get(gate_id) else {
            return Ok(());
        };
        let refs = gate
            .get("ordered_input_evidence_refs")
            .and_then(JsonValue::as_array)
            .expect("validated input refs");
        let matches = refs
            .iter()
            .take(prefix.len())
            .map(|value| value.as_str().unwrap_or_default())
            .eq(prefix.iter().copied());
        if !matches {
            return Err(fail("lifecycle:gate_predecessor_mismatch", gate_id));
        }
        Ok(())
    };
    if let Some(g1) = evidence.get("G1") {
        require_prefix("G2", &[*g1])?;
    }
    if let (Some(g1), Some(g2)) = (evidence.get("G1"), evidence.get("G2")) {
        require_prefix("G3", &[*g1, *g2])?;
    }
    if let Some(g3) = evidence.get("G3") {
        require_prefix("G4", &[*g3])?;
    }
    if let Some(g4) = evidence.get("G4") {
        require_prefix("G5", &[*g4])?;
    }
    if GATE_IDS[..5]
        .iter()
        .all(|gate_id| evidence.contains_key(gate_id))
    {
        let prefix = GATE_IDS[..5]
            .iter()
            .map(|gate_id| {
                evidence
                    .get(*gate_id)
                    .copied()
                    .expect("gate evidence was checked")
            })
            .collect::<Vec<_>>();
        require_prefix("G6", &prefix)?;
    }
    let unique = evidence.values().copied().collect::<BTreeSet<_>>();
    if unique.len() != evidence.len() {
        return Err(LifecycleContractError::code(
            "lifecycle:gate_evidence_reused",
        ));
    }
    Ok(gates)
}

pub fn materialize_gate_verdict(
    input: &GateVerdictInput,
) -> Result<JsonValue, LifecycleContractError> {
    let checked_binding = validate_record_binding(&input.binding)?;
    let identity = binding_identity_from_validated(&checked_binding)?;
    let evidence_seed = serde_json::json!({
        "identity": {
            "transaction_id": identity.transaction_id,
            "snapshot_id": identity.snapshot_id,
            "candidate_sha": identity.candidate_sha,
            "tree_sha": identity.tree_sha,
            "input_digest": identity.input_digest,
            "tool_id": identity.tool_id,
            "tool_version": identity.tool_version,
        },
        "gate_id": input.gate_id,
        "ordered_input_evidence_refs": input.ordered_input_evidence_refs,
        "invariant": input.invariant,
        "output_digest": input.output_digest,
        "owner": input.owner,
        "verdict": input.verdict,
        "retry_reason": input.retry_reason,
        "next_checkpoint": input.next_checkpoint,
    });
    let canonical_bytes =
        canonical_json_bytes(&evidence_seed).map_err(LifecycleContractError::from)?;
    let digest = Sha256::digest(canonical_bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let evidence_digest = format!("sha256:{digest}");
    let mut gate_binding = checked_binding
        .as_object()
        .expect("validated binding object")
        .clone();
    gate_binding.insert(
        "evidence_ref".to_string(),
        JsonValue::String(format!("evidence:{digest}")),
    );
    gate_binding.insert(
        "evidence_digest".to_string(),
        JsonValue::String(evidence_digest),
    );
    let record = serde_json::json!({
        "schema": "agent-canon.gate-verdict.v1",
        "binding": gate_binding,
        "gate_id": input.gate_id,
        "ordered_input_evidence_refs": input.ordered_input_evidence_refs,
        "invariant": input.invariant,
        "output_digest": input.output_digest,
        "owner": input.owner,
        "verdict": input.verdict,
        "retry_reason": input.retry_reason,
        "next_checkpoint": input.next_checkpoint,
    });
    validate_gate_verdict(&record)
}
