// @dependency-start
// contract implementation
// responsibility Owns native immutable update-lifecycle records, binding, and gate-verdict mechanics.
// upstream design ../../../../../documents/agent-canon/agent-canon-update-route.md owns update lifecycle meaning
// upstream implementation artifacts/artifact_identity.rs owns canonical JSON bytes and body hashes
// upstream implementation ../../../../../tools/runtime/lifecycle/update_lifecycle_contract.py remains the full lifecycle owner until later slices migrate
// downstream implementation ../../../../../tests/agent_tools/test_publication_integrator.py checks gate identity replay stability
// downstream implementation ../../../../../tests/agent_tools/test_github_publish.py consumes G3 gate verdicts
// downstream implementation ../../../../../tests/agent_tools/test_bootstrap_and_close.py consumes gate chains at closeout
// downstream test ../tests/update_lifecycle_records_native.rs freezes snapshot, evidence, and checkpoint record validation
// downstream test ../tests/update_lifecycle_transaction_native.rs freezes update transaction validation
// downstream test ../tests/update_lifecycle_pr_native.rs freezes the native PR lifecycle APIs against CPython outputs
// downstream test ../tests/update_lifecycle_publication_native.rs freezes publication readback receipts and transitions
// downstream test ../tests/update_lifecycle_queue_native.rs freezes queue keys, receipts, and replay behavior
// downstream test ../tests/update_lifecycle_frontier_native.rs freezes ordered frontier validation and transitions
// downstream test ../tests/update_lifecycle_terminal_native.rs freezes closeout receipts, cleanup, and token hashes
// @dependency-end

use crate::artifacts::artifact_identity::{canonical_body_sha256, canonical_json_bytes};
use crate::python_json::python_json_equal_after_float_rejection;
use serde_json::{Map as JsonMap, Value as JsonValue};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::path::Path;

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

#[derive(Clone, Copy)]
struct TransactionTransition {
    current_state: &'static str,
    next_state: &'static str,
    required_evidence: &'static [&'static str],
}

const TRANSACTION_TRANSITIONS: &[TransactionTransition] = &[
    TransactionTransition {
        current_state: "created",
        next_state: "prepared",
        required_evidence: &["prepare_receipt"],
    },
    TransactionTransition {
        current_state: "prepared",
        next_state: "generated",
        required_evidence: &["generate_receipt"],
    },
    TransactionTransition {
        current_state: "generated",
        next_state: "gates_ready",
        required_evidence: &["gate_verdicts"],
    },
    TransactionTransition {
        current_state: "gates_ready",
        next_state: "reviewed",
        required_evidence: &["candidate_review_receipt", "candidate_cas_receipt"],
    },
    TransactionTransition {
        current_state: "reviewed",
        next_state: "pr_open",
        required_evidence: &["pr_lifecycle"],
    },
    TransactionTransition {
        current_state: "pr_open",
        next_state: "pr_merged",
        required_evidence: &["pr_lifecycle"],
    },
    TransactionTransition {
        current_state: "pr_merged",
        next_state: "source_main_readback",
        required_evidence: &["publication_readback_receipt"],
    },
    TransactionTransition {
        current_state: "source_main_readback",
        next_state: "queue_enqueued",
        required_evidence: &["queue_receipt"],
    },
    TransactionTransition {
        current_state: "queue_enqueued",
        next_state: "frontier_accepted",
        required_evidence: &["dependency_frontier"],
    },
    TransactionTransition {
        current_state: "frontier_accepted",
        next_state: "remote_readback",
        required_evidence: &["gate_verdicts"],
    },
    TransactionTransition {
        current_state: "remote_readback",
        next_state: "durable_handback",
        required_evidence: &["durable_handback"],
    },
    TransactionTransition {
        current_state: "durable_handback",
        next_state: "descendants_closed",
        required_evidence: &["descendants_closed_evidence_ref"],
    },
    TransactionTransition {
        current_state: "descendants_closed",
        next_state: "reservations_released",
        required_evidence: &["reservations_released_evidence_ref"],
    },
    TransactionTransition {
        current_state: "reservations_released",
        next_state: "cleanup_proven",
        required_evidence: &["cleanup_proof"],
    },
    TransactionTransition {
        current_state: "cleanup_proven",
        next_state: "nested_lifecycle_cleanup",
        required_evidence: &["gate_verdicts", "cleanup_proof"],
    },
    TransactionTransition {
        current_state: "nested_lifecycle_cleanup",
        next_state: "closed",
        required_evidence: &["close_agent_tool_call"],
    },
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
const STATE_CHECKPOINT_PREFIX: &[(&str, usize)] = &[
    ("created", 0),
    ("prepared", 1),
    ("generated", 2),
    ("gates_ready", 4),
    ("reviewed", 4),
    ("pr_open", 5),
    ("pr_merged", 5),
    ("source_main_readback", 6),
    ("queue_enqueued", 7),
    ("frontier_accepted", 9),
    ("remote_readback", 11),
    ("durable_handback", 12),
    ("descendants_closed", 13),
    ("reservations_released", 14),
    ("cleanup_proven", 15),
    ("nested_lifecycle_cleanup", 17),
    ("closed", CHECKPOINT_IDS.len()),
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
const CANDIDATE_FREEZE_SCHEMA: &str = "agent-canon.candidate-freeze-receipt.v1";
const CANDIDATE_REVIEW_SCHEMA: &str = "agent-canon.candidate-review-receipt.v1";
const CANDIDATE_CAS_SCHEMA: &str = "agent-canon.candidate-cas-receipt.v1";
const SNAPSHOT_SCHEMA: &str = "agent-canon.snapshot.v1";
const EVIDENCE_IDENTITY_SCHEMA: &str = "agent-canon.evidence-identity.v1";
const CHECKPOINT_RECEIPT_SCHEMA: &str = "agent-canon.checkpoint-receipt.v1";
const UPDATE_TRANSACTION_SCHEMA: &str = "agent-canon.update-transaction.v1";
const QUEUE_RECEIPT_SCHEMA: &str = "agent-canon.queue-receipt.v1";
const DEPENDENCY_FRONTIER_SCHEMA: &str = "agent-canon.dependency-frontier.v1";
const DURABLE_HANDBACK_SCHEMA: &str = "agent-canon.durable-handback.v1";
const DESCENDANT_CLOSE_RECEIPT_SCHEMA: &str = "agent-canon.descendant-close-receipt.v1";
const RESERVATION_RELEASE_RECEIPT_SCHEMA: &str = "agent-canon.reservation-release-receipt.v1";
const CLEANUP_PROOF_SCHEMA: &str = "agent-canon.cleanup-proof.v1";
const CLOSE_AGENT_TOOL_CALL_SCHEMA: &str = "agent-canon.close-agent-tool-call.v1";
const CLOSE_AGENT_ARGS_SCHEMA: &str = "agent-canon.close-agent.args.v1";
const PUBLICATION_READBACK_SCHEMA: &str = "agent-canon.publication-readback-receipt.v1";
const SOURCE_PROJECTION_PACKET_SCHEMA: &str = "agent-canon.source-projection-packet.v1";
const PULL_REQUEST_LIFECYCLE_SCHEMA: &str = "agent-canon.pull-request-lifecycle.v1";
const PR_KINDS: &[&str] = &["user", "fork", "contributor"];
const PR_STATES: &[&str] = &[
    "draft",
    "ready",
    "permission_unknown",
    "permission_denied",
    "changes_requested",
    "external_review",
    "merged",
    "closed_head",
    "multiple_remotes",
    "conflict_successor",
];
const PR_OPEN_STATES: &[&str] = &[
    "draft",
    "ready",
    "permission_unknown",
    "permission_denied",
    "changes_requested",
    "external_review",
];
const PR_REVIEWABLE_STATES: &[&str] = &["ready", "changes_requested", "external_review"];
const PULL_REQUEST_TRANSITIONS: &[(&str, &str)] = &[
    ("draft", "ready"),
    ("draft", "permission_unknown"),
    ("permission_unknown", "permission_denied"),
    ("permission_unknown", "ready"),
    ("permission_denied", "ready"),
    ("ready", "changes_requested"),
    ("ready", "external_review"),
    ("changes_requested", "ready"),
    ("external_review", "ready"),
    ("multiple_remotes", "ready"),
    ("ready", "merged"),
];
const PR_BRANCH_RULES: &[(&str, &[&str], &[&str])] = &[
    (
        "user",
        &["user_identity"],
        &["fork_identity", "contributor_identity", "contributor_diff"],
    ),
    (
        "fork",
        &["fork_identity"],
        &["user_identity", "contributor_identity", "contributor_diff"],
    ),
    (
        "contributor",
        &["contributor_identity", "contributor_diff"],
        &["user_identity", "fork_identity"],
    ),
];
pub const SOURCE_MAIN_REBIND_SCHEMA: &str = "agent-canon.source-main-rebind-receipt.v1";

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
pub struct SourceMainReadbackIdentity {
    pub commit_sha: String,
    pub tree_sha: String,
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

#[derive(Debug, Clone, Copy)]
pub struct CloseAgentToolCallInput<'a> {
    pub binding: &'a JsonValue,
    pub run_id: &'a str,
    pub agent_id: &'a str,
    pub gate_verdicts: &'a [JsonValue],
    pub cleanup_proof: &'a JsonValue,
    pub durable_handback: &'a JsonValue,
    pub descendants_closed_evidence_ref: &'a str,
    pub reservations_released_evidence_ref: &'a str,
    pub completed_but_open: bool,
    pub unknown_descendants: bool,
    pub reservation_leak: bool,
}

#[derive(Debug, Clone, Copy)]
pub struct SourceProjectionPacketInput<'a> {
    pub binding: &'a JsonValue,
    pub source_main_rebind_receipt: &'a JsonValue,
    pub candidate_cas_receipt: &'a JsonValue,
    pub pull_request_lifecycle: &'a JsonValue,
    pub publication_readback_receipt: &'a JsonValue,
    pub source_gate_verdicts: &'a [JsonValue],
    pub ordered_predecessor_evidence: &'a [JsonValue],
    pub acceptance_evidence_ref: &'a str,
}

pub type SourceProjectionG2Callback<'a, Error> =
    dyn Fn(&JsonValue, &str, &str, &[JsonValue]) -> Result<JsonValue, Error> + 'a;
pub type SourceProjectionG3Callback<'a, Error> =
    dyn Fn(&JsonValue, &JsonValue, &JsonValue, &[JsonValue]) -> Result<JsonValue, Error> + 'a;

pub struct SourceProjectionGateOwnerApis<'a, G2Error, G3Error> {
    pub generated_completeness_check_ids: &'a [String],
    pub materialize_generated_completeness_receipt: &'a SourceProjectionG2Callback<'a, G2Error>,
    pub materialize_pr_identity_gate: &'a SourceProjectionG3Callback<'a, G3Error>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FreshCloneSourceProjectionError<G2Error, G3Error> {
    Lifecycle(LifecycleContractError),
    G2Owner(G2Error),
    G3Owner(G3Error),
}

impl<G2Error, G3Error> From<LifecycleContractError>
    for FreshCloneSourceProjectionError<G2Error, G3Error>
{
    fn from(error: LifecycleContractError) -> Self {
        Self::Lifecycle(error)
    }
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
    let number = value
        .as_number()
        .ok_or_else(|| fail("lifecycle:integer_invalid", field))?;
    let text = number.to_string();
    if text.bytes().all(|byte| byte.is_ascii_digit())
        && (zero_allowed || text.bytes().any(|byte| byte != b'0'))
    {
        Ok(())
    } else {
        Err(fail("lifecycle:integer_invalid", field))
    }
}

fn frontier_queue_number_matches(value: &JsonValue, expected: u16) -> bool {
    match value {
        JsonValue::Number(number) if number.is_f64() => number.as_f64().is_some_and(|number| {
            number.partial_cmp(&f64::from(expected)) == Some(std::cmp::Ordering::Equal)
        }),
        JsonValue::Number(number) => number.to_string() == expected.to_string(),
        _ => false,
    }
}

fn boolean_value(value: &JsonValue, field: &str) -> Result<(), LifecycleContractError> {
    if value.is_boolean() {
        Ok(())
    } else {
        Err(fail("lifecycle:boolean_invalid", field))
    }
}

fn leap_year(year: u32) -> bool {
    year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400))
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
    if value.len() >= 8
        && bytes.get(4).is_some_and(u8::is_ascii_digit)
        && value.get(0..8)?.bytes().all(|byte| byte.is_ascii_digit())
    {
        let month = decimal(value.get(4..6)?)?;
        let day = decimal(value.get(6..8)?)?;
        return valid_calendar_date(year, month, day).then_some(8);
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
    let (clock, has_fraction) = match value.find(['.', ',']) {
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
    let (clock, has_fraction) = match offset.find(['.', ',']) {
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

pub fn validate_snapshot(value: &JsonValue) -> Result<JsonValue, LifecycleContractError> {
    let snapshot = mapping(value, "snapshot")?;
    exact_keys(
        snapshot,
        &["schema", "binding", "source_namespace", "base_identity"],
        &[],
        "snapshot",
    )?;
    if snapshot.get("schema").and_then(JsonValue::as_str) != Some(SNAPSHOT_SCHEMA) {
        return Err(fail("lifecycle:schema_invalid", SNAPSHOT_SCHEMA));
    }
    validate_record_binding(required_value(snapshot, "binding", "snapshot")?)?;
    let source_namespace = required_string(snapshot, "source_namespace", "snapshot")?;
    if !std::path::Path::new(&source_namespace).is_absolute() {
        return Err(fail(
            "lifecycle:path_not_absolute",
            "snapshot.source_namespace",
        ));
    }
    validate_remote_git_identity(
        required_value(snapshot, "base_identity", "snapshot")?,
        "snapshot.base_identity",
    )?;
    canonical_clone(value)
}

pub fn validate_evidence_identity(value: &JsonValue) -> Result<JsonValue, LifecycleContractError> {
    let evidence = mapping(value, "evidence_identity")?;
    exact_keys(
        evidence,
        &[
            "schema",
            "binding",
            "producer_path",
            "producer_symbol",
            "observed_at",
            "sequence",
        ],
        &[],
        "evidence_identity",
    )?;
    if evidence.get("schema").and_then(JsonValue::as_str) != Some(EVIDENCE_IDENTITY_SCHEMA) {
        return Err(fail("lifecycle:schema_invalid", EVIDENCE_IDENTITY_SCHEMA));
    }
    validate_record_binding(required_value(evidence, "binding", "evidence_identity")?)?;
    let producer_path = required_string(evidence, "producer_path", "evidence_identity")?;
    if !std::path::Path::new(&producer_path).is_absolute() {
        return Err(fail(
            "lifecycle:path_not_absolute",
            "evidence_identity.producer_path",
        ));
    }
    required_string(evidence, "producer_symbol", "evidence_identity")?;
    rfc3339(
        required_value(evidence, "observed_at", "evidence_identity")?,
        "evidence_identity.observed_at",
    )?;
    positive_integer(
        required_value(evidence, "sequence", "evidence_identity")?,
        "evidence_identity.sequence",
        false,
    )?;
    canonical_clone(value)
}

pub fn validate_checkpoint_receipt(value: &JsonValue) -> Result<JsonValue, LifecycleContractError> {
    let receipt = mapping(value, "checkpoint_receipt")?;
    exact_keys(
        receipt,
        &[
            "schema",
            "binding",
            "checkpoint_id",
            "verdict",
            "failure_code",
        ],
        &[],
        "checkpoint_receipt",
    )?;
    if receipt.get("schema").and_then(JsonValue::as_str) != Some(CHECKPOINT_RECEIPT_SCHEMA) {
        return Err(fail("lifecycle:schema_invalid", CHECKPOINT_RECEIPT_SCHEMA));
    }
    validate_record_binding(required_value(receipt, "binding", "checkpoint_receipt")?)?;
    one_of(
        required_value(receipt, "checkpoint_id", "checkpoint_receipt")?,
        CHECKPOINT_IDS,
        "checkpoint_receipt.checkpoint_id",
    )?;
    let verdict = one_of(
        required_value(receipt, "verdict", "checkpoint_receipt")?,
        &["pass", "fail", "skip"],
        "checkpoint_receipt.verdict",
    )?;
    let failure_code = required_value(receipt, "failure_code", "checkpoint_receipt")?;
    if verdict == "fail" {
        string_value(failure_code, "checkpoint_receipt.failure_code")?;
    } else if !failure_code.is_null() {
        return Err(fail(
            "lifecycle:failure_code_forbidden",
            "checkpoint_receipt",
        ));
    }
    canonical_clone(value)
}

pub fn validate_update_transaction(value: &JsonValue) -> Result<JsonValue, LifecycleContractError> {
    let transaction = mapping(value, "update_transaction")?;
    exact_keys(
        transaction,
        &[
            "schema",
            "binding",
            "state",
            "checkpoints",
            "first_missing_checkpoint",
            "gate_verdict_evidence_refs",
            "queue_receipt_id",
            "frontier_id",
            "successor_transaction_id",
            "source_main_rebind_receipt_id",
        ],
        &[],
        "update_transaction",
    )?;
    if transaction.get("schema").and_then(JsonValue::as_str) != Some(UPDATE_TRANSACTION_SCHEMA) {
        return Err(fail("lifecycle:schema_invalid", UPDATE_TRANSACTION_SCHEMA));
    }
    let binding = validate_record_binding(required_value(
        transaction,
        "binding",
        "update_transaction",
    )?)?;
    let state = one_of(
        required_value(transaction, "state", "update_transaction")?,
        TRANSACTION_STATES,
        "update_transaction.state",
    )?;
    let checkpoint_values = required_value(transaction, "checkpoints", "update_transaction")?
        .as_array()
        .ok_or_else(|| {
            fail(
                "lifecycle:sequence_required",
                "update_transaction.checkpoints",
            )
        })?;
    let mut checkpoints = Vec::with_capacity(checkpoint_values.len());
    for checkpoint in checkpoint_values {
        checkpoints.push(validate_checkpoint_receipt(checkpoint)?);
    }

    let expected_binding_identity = binding_identity(&binding)?;
    let mut seen = BTreeMap::new();
    for receipt in checkpoints {
        let receipt_map = mapping(&receipt, "checkpoint_receipt")?;
        let receipt_binding = required_value(receipt_map, "binding", "checkpoint_receipt")?;
        if binding_identity(receipt_binding)? != expected_binding_identity {
            return Err(fail(
                "input_identity_mismatch",
                "update_transaction.checkpoints",
            ));
        }
        let checkpoint_id = required_string(receipt_map, "checkpoint_id", "checkpoint_receipt")?;
        if seen.contains_key(&checkpoint_id) {
            return Err(fail("lifecycle:checkpoint_duplicate", &checkpoint_id));
        }
        seen.insert(checkpoint_id, receipt);
    }

    let passed = seen
        .iter()
        .filter_map(|(checkpoint_id, receipt)| {
            matches!(
                receipt.get("verdict").and_then(JsonValue::as_str),
                Some("pass" | "skip")
            )
            .then_some(checkpoint_id.clone())
        })
        .collect::<BTreeSet<_>>();
    let passed_prefix = CHECKPOINT_IDS
        .iter()
        .take_while(|checkpoint_id| passed.contains(**checkpoint_id))
        .count();
    if CHECKPOINT_IDS
        .iter()
        .skip(passed_prefix + 1)
        .any(|checkpoint_id| passed.contains(*checkpoint_id))
    {
        return Err(fail("lifecycle:checkpoint_out_of_order", ""));
    }

    let computed_missing = CHECKPOINT_IDS.iter().copied().find(|checkpoint_id| {
        seen.get(*checkpoint_id).is_none_or(|receipt| {
            !matches!(
                receipt.get("verdict").and_then(JsonValue::as_str),
                Some("pass" | "skip")
            )
        })
    });
    let computed_missing = computed_missing
        .map(|checkpoint_id| JsonValue::String(checkpoint_id.to_owned()))
        .unwrap_or(JsonValue::Null);
    if required_value(
        transaction,
        "first_missing_checkpoint",
        "update_transaction",
    )? != &computed_missing
    {
        return Err(fail("lifecycle:first_missing_checkpoint_mismatch", ""));
    }

    let gate_refs = string_list(
        required_value(
            transaction,
            "gate_verdict_evidence_refs",
            "update_transaction",
        )?,
        "update_transaction.gate_verdict_evidence_refs",
        false,
        true,
        Some(valid_evidence_ref),
    )?;
    let mut passed_gate_refs = Vec::new();
    for gate_id in GATE_IDS {
        if let Some(receipt) = seen.get(*gate_id) {
            let receipt_map = mapping(receipt, "checkpoint_receipt")?;
            if matches!(
                required_value(receipt_map, "verdict", "checkpoint_receipt")?.as_str(),
                Some("pass" | "skip")
            ) {
                let receipt_binding = mapping(
                    required_value(receipt_map, "binding", "checkpoint_receipt")?,
                    "binding",
                )?;
                passed_gate_refs.push(required_string(receipt_binding, "evidence_ref", "binding")?);
            }
        }
    }
    if gate_refs != passed_gate_refs {
        return Err(fail("lifecycle:gate_evidence_mismatch", ""));
    }

    for (field, prefix) in [
        ("queue_receipt_id", "queue:"),
        ("frontier_id", "frontier:"),
        ("successor_transaction_id", "tx:"),
        ("source_main_rebind_receipt_id", "rebind:"),
    ] {
        let value = required_value(transaction, field, "update_transaction")?;
        if !value.is_null() {
            let error_field = format!("update_transaction.{field}");
            let identity = pattern_value(value, &error_field, valid_hash_id)?;
            if !identity.starts_with(prefix) {
                return Err(fail("lifecycle:identity_invalid", &error_field));
            }
        }
    }

    let successor_transaction_id = required_value(
        transaction,
        "successor_transaction_id",
        "update_transaction",
    )?;
    if state == "successor_required" && successor_transaction_id.is_null() {
        return Err(fail("lifecycle:successor_missing", ""));
    }
    if state != "successor_required" && !successor_transaction_id.is_null() {
        return Err(fail("lifecycle:successor_forbidden", ""));
    }

    if let Some((_, required_prefix)) = STATE_CHECKPOINT_PREFIX
        .iter()
        .find(|(prefix_state, _)| *prefix_state == state.as_str())
    {
        if passed_prefix != *required_prefix {
            return Err(fail("lifecycle:state_checkpoint_mismatch", &state));
        }
    }

    let source_main_rebind_receipt_id = required_value(
        transaction,
        "source_main_rebind_receipt_id",
        "update_transaction",
    )?;
    if matches!(
        state.as_str(),
        "reviewed"
            | "pr_open"
            | "pr_merged"
            | "source_main_readback"
            | "queue_enqueued"
            | "frontier_accepted"
            | "remote_readback"
            | "durable_handback"
            | "descendants_closed"
            | "reservations_released"
            | "cleanup_proven"
            | "nested_lifecycle_cleanup"
            | "closed"
    ) && source_main_rebind_receipt_id.is_null()
    {
        return Err(fail("lifecycle:rebind_receipt_required", &state));
    }

    let queue_receipt_id = required_value(transaction, "queue_receipt_id", "update_transaction")?;
    if matches!(
        state.as_str(),
        "queue_enqueued"
            | "frontier_accepted"
            | "remote_readback"
            | "durable_handback"
            | "descendants_closed"
            | "reservations_released"
            | "cleanup_proven"
            | "nested_lifecycle_cleanup"
            | "closed"
    ) && queue_receipt_id.is_null()
    {
        return Err(fail("lifecycle:queue_receipt_required", &state));
    }

    let frontier_id = required_value(transaction, "frontier_id", "update_transaction")?;
    if matches!(
        state.as_str(),
        "frontier_accepted"
            | "remote_readback"
            | "durable_handback"
            | "descendants_closed"
            | "reservations_released"
            | "cleanup_proven"
            | "nested_lifecycle_cleanup"
            | "closed"
    ) && frontier_id.is_null()
    {
        return Err(fail("lifecycle:frontier_required", &state));
    }
    canonical_clone(value)
}

pub fn binding_identity(
    value: &JsonValue,
) -> Result<RecordBindingIdentity, LifecycleContractError> {
    let binding = validate_record_binding(value)?;
    binding_identity_from_validated(&binding)
}

/// Validate the immutable packet consumed by the source projection stage.
pub fn validate_source_projection_packet(
    value: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let packet = mapping(value, "source_projection_packet")?;
    exact_keys(
        packet,
        &[
            "schema",
            "binding",
            "source_main_rebind_receipt",
            "candidate_cas_receipt",
            "pull_request_lifecycle",
            "publication_readback_receipt",
            "source_gate_verdicts",
            "ordered_predecessor_evidence",
            "acceptance_evidence_ref",
        ],
        &[],
        "source_projection_packet",
    )?;
    if packet.get("schema").and_then(JsonValue::as_str) != Some(SOURCE_PROJECTION_PACKET_SCHEMA) {
        return Err(fail(
            "lifecycle:schema_invalid",
            SOURCE_PROJECTION_PACKET_SCHEMA,
        ));
    }

    let binding = validate_record_binding(required_value(
        packet,
        "binding",
        "source_projection_packet",
    )?)?;
    let rebind = validate_source_main_rebind_receipt(required_value(
        packet,
        "source_main_rebind_receipt",
        "source_projection_packet",
    )?)?;
    let cas = validate_candidate_cas_receipt(required_value(
        packet,
        "candidate_cas_receipt",
        "source_projection_packet",
    )?)?;
    let lifecycle = validate_candidate_cas_pr_transition(
        &cas,
        required_value(packet, "pull_request_lifecycle", "source_projection_packet")?,
    )?;
    let readback = validate_publication_readback_transition(
        &cas,
        &lifecycle,
        required_value(
            packet,
            "publication_readback_receipt",
            "source_projection_packet",
        )?,
    )?;
    let gates_value = required_value(packet, "source_gate_verdicts", "source_projection_packet")?;
    let gates = gates_value.as_array().ok_or_else(|| {
        fail(
            "lifecycle:sequence_required",
            "source_projection_packet.source_gate_verdicts",
        )
    })?;
    let source_gates = validate_gate_chain(gates, Some(&["G1", "G2", "G3"]), true)?;

    for (field, record) in [
        ("rebind", &rebind),
        ("cas", &cas),
        ("pr", &lifecycle),
        ("readback", &readback),
    ] {
        let record = mapping(record, field)?;
        same_binding(
            &binding,
            required_value(record, "binding", field)?,
            &format!("source_projection_packet.{field}"),
        )?;
    }
    validate_candidate_cas_rebind_transition(&rebind, &cas)?;

    let packet_binding_identity = binding_identity(&binding)?;
    for gate in &source_gates {
        let gate = mapping(gate, "gate_verdict")?;
        let gate_binding = required_value(gate, "binding", "gate_verdict")?;
        if binding_identity(gate_binding)? != packet_binding_identity {
            return Err(fail("lifecycle:gate_identity_mismatch", ""));
        }
    }

    let g3 = source_gates
        .get(2)
        .expect("the validated G1-G2-G3 chain contains G3");
    let g3 = mapping(g3, "gate_verdict")?;
    let g3_inputs = required_value(g3, "ordered_input_evidence_refs", "gate_verdict")?
        .as_array()
        .expect("validated gate input evidence is an array");
    let cas_map = mapping(&cas, "candidate_cas_receipt")?;
    let cas_binding = mapping(
        required_value(cas_map, "binding", "candidate_cas_receipt")?,
        "candidate_cas_receipt.binding",
    )?;
    let cas_evidence =
        required_value(cas_binding, "evidence_ref", "candidate_cas_receipt.binding")?;
    if !g3_inputs.contains(cas_evidence) {
        return Err(fail("lifecycle:gate_predecessor_mismatch", "G3"));
    }

    let readback = mapping(&readback, "publication_readback_receipt")?;
    let rebind = mapping(&rebind, "source_main_rebind_receipt")?;
    if required_value(
        readback,
        "rebind_receipt_evidence_id",
        "publication_readback_receipt",
    )? != required_value(rebind, "rebind_receipt_id", "source_main_rebind_receipt")?
    {
        return Err(fail(
            "lifecycle:rebind_mismatch",
            "source_projection_packet",
        ));
    }

    let predecessors_value = required_value(
        packet,
        "ordered_predecessor_evidence",
        "source_projection_packet",
    )?;
    let predecessors = predecessors_value.as_array().ok_or_else(|| {
        fail(
            "lifecycle:sequence_required",
            "source_projection_packet.ordered_predecessor_evidence",
        )
    })?;
    if predecessors.len() != 2 {
        return Err(fail("frontier:predecessor_order_invalid", ""));
    }
    for (index, (value, (expected_number, expected_pr))) in predecessors
        .iter()
        .zip([(388, "#388"), (389, "#389")])
        .enumerate()
    {
        let field = format!("source_projection_packet.ordered_predecessor_evidence[{index}]");
        let item = mapping(value, &field)?;
        let optional = if index == 1 {
            &["source_pr_sha"][..]
        } else {
            &[][..]
        };
        exact_keys(
            item,
            &["queue_number", "source_pr", "publication_evidence_id"],
            optional,
            &field,
        )?;
        if !frontier_queue_number_matches(
            required_value(item, "queue_number", &field)?,
            expected_number,
        ) || required_value(item, "source_pr", &field)?.as_str() != Some(expected_pr)
        {
            return Err(fail("frontier:predecessor_order_invalid", ""));
        }
        pattern_value(
            required_value(item, "publication_evidence_id", &field)?,
            &format!("{field}.publication_evidence_id"),
            valid_evidence_ref,
        )?;
        if index == 1 {
            let missing = JsonValue::Null;
            pattern_value(
                item.get("source_pr_sha").unwrap_or(&missing),
                "source_projection_packet.ordered_predecessor_evidence[1].source_pr_sha",
                |text| lower_hex(text, 40),
            )?;
        }
    }
    pattern_value(
        required_value(
            packet,
            "acceptance_evidence_ref",
            "source_projection_packet",
        )?,
        "source_projection_packet.acceptance_evidence_ref",
        valid_evidence_ref,
    )?;
    canonical_clone(value)
}

/// Build a source projection packet from already-materialized lifecycle receipts.
pub fn materialize_source_projection_packet(
    input: &SourceProjectionPacketInput<'_>,
) -> Result<JsonValue, LifecycleContractError> {
    let mut packet = JsonMap::new();
    packet.insert(
        "schema".to_owned(),
        JsonValue::String(SOURCE_PROJECTION_PACKET_SCHEMA.to_owned()),
    );
    packet.insert("binding".to_owned(), input.binding.clone());
    packet.insert(
        "source_main_rebind_receipt".to_owned(),
        input.source_main_rebind_receipt.clone(),
    );
    packet.insert(
        "candidate_cas_receipt".to_owned(),
        input.candidate_cas_receipt.clone(),
    );
    packet.insert(
        "pull_request_lifecycle".to_owned(),
        input.pull_request_lifecycle.clone(),
    );
    packet.insert(
        "publication_readback_receipt".to_owned(),
        input.publication_readback_receipt.clone(),
    );
    packet.insert(
        "source_gate_verdicts".to_owned(),
        JsonValue::Array(input.source_gate_verdicts.to_vec()),
    );
    packet.insert(
        "ordered_predecessor_evidence".to_owned(),
        JsonValue::Array(input.ordered_predecessor_evidence.to_vec()),
    );
    packet.insert(
        "acceptance_evidence_ref".to_owned(),
        JsonValue::String(input.acceptance_evidence_ref.to_owned()),
    );
    validate_source_projection_packet(&JsonValue::Object(packet))
}

fn fresh_clone_projection_digest(
    label: &str,
    value: &JsonValue,
) -> Result<String, LifecycleContractError> {
    let record = serde_json::json!({"label": label, "value": value});
    let canonical = canonical_json_bytes(&record).map_err(LifecycleContractError::from)?;
    Ok(Sha256::digest(canonical)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

fn fresh_clone_projection_evidence(
    label: &str,
    value: &JsonValue,
) -> Result<String, LifecycleContractError> {
    Ok(format!(
        "evidence:{}",
        fresh_clone_projection_digest(label, value)?
    ))
}

/// Materialize a fresh-clone source packet from observed identities and owner callbacks.
/// `source_root` is the resolved Python lifecycle module root serialized in owner paths.
pub fn materialize_fresh_clone_source_projection_packet<G2Error, G3Error>(
    candidate_sha: &str,
    candidate_tree_sha: &str,
    publication_sha: &str,
    publication_tree_sha: &str,
    source_root: &Path,
    gate_owner_apis: &SourceProjectionGateOwnerApis<'_, G2Error, G3Error>,
) -> Result<JsonValue, FreshCloneSourceProjectionError<G2Error, G3Error>> {
    for (value, field) in [
        (candidate_sha, "fresh_clone.candidate_sha"),
        (candidate_tree_sha, "fresh_clone.candidate_tree_sha"),
        (publication_sha, "fresh_clone.publication_sha"),
        (publication_tree_sha, "fresh_clone.publication_tree_sha"),
    ] {
        pattern_value(&JsonValue::String(value.to_owned()), field, |text| {
            lower_hex(text, 40)
        })?;
    }

    let identity = serde_json::json!({
        "candidate_sha": candidate_sha,
        "candidate_tree_sha": candidate_tree_sha,
        "publication_sha": publication_sha,
        "publication_tree_sha": publication_tree_sha,
    });
    let input_digest = format!(
        "sha256:{}",
        fresh_clone_projection_digest("fresh-clone-input", &identity)?
    );
    let transaction_id = format!(
        "tx:{}",
        fresh_clone_projection_digest("fresh-clone-transaction", &identity)?
    );
    let snapshot_id = format!(
        "snapshot:{}",
        fresh_clone_projection_digest("fresh-clone-snapshot", &identity)?
    );
    let binding_evidence = fresh_clone_projection_evidence("fresh-clone-binding", &identity)?;
    let binding_evidence_digest = format!(
        "sha256:{}",
        fresh_clone_projection_digest("fresh-clone-binding", &identity)?
    );
    let binding = serde_json::json!({
        "transaction_id": transaction_id,
        "snapshot_id": snapshot_id,
        "candidate_sha": candidate_sha,
        "tree_sha": candidate_tree_sha,
        "input_digest": input_digest,
        "tool_id": "update-agent-canon",
        "tool_version": "fresh-clone-acceptance.v1",
        "evidence_ref": binding_evidence,
        "evidence_digest": binding_evidence_digest,
        "timing": {
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:00:00Z",
            "last_attempt_at": "2026-01-01T00:00:00Z",
            "duration_ms": 0,
            "attempt": 1,
            "replayed": false,
        },
    });
    let checked_binding = validate_record_binding(&binding)?;
    let base_identity = serde_json::json!({
        "remote": "origin",
        "ref": "refs/heads/main",
        "commit_sha": candidate_sha,
        "tree_sha": candidate_tree_sha,
    });
    let rebind_readback_evidence =
        fresh_clone_projection_evidence("fresh-clone-origin-main-readback", &identity)?;
    let rebind = materialize_source_main_rebind_receipt(
        &checked_binding,
        &base_identity,
        &base_identity,
        &rebind_readback_evidence,
    )?;

    let cas_evidence_digest = fresh_clone_projection_digest("fresh-clone-cas", &identity)?;
    let cas_evidence_ref = format!("evidence:{cas_evidence_digest}");
    let mut cas_binding = checked_binding.clone();
    let cas_binding = cas_binding
        .as_object_mut()
        .expect("validated binding is an object");
    cas_binding.insert(
        "evidence_ref".to_owned(),
        JsonValue::String(cas_evidence_ref.clone()),
    );
    cas_binding.insert(
        "evidence_digest".to_owned(),
        JsonValue::String(format!("sha256:{cas_evidence_digest}")),
    );
    let rebind_map = rebind
        .as_object()
        .expect("validated source-main rebind receipt is an object");
    let binding_map = checked_binding
        .as_object()
        .expect("validated binding is an object");
    let cas_receipt = serde_json::json!({
        "schema": CANDIDATE_CAS_SCHEMA,
        "cas_receipt_id": format!(
            "cas:{}",
            fresh_clone_projection_digest("fresh-clone-cas-id", &identity)?
        ),
        "binding": JsonValue::Object(cas_binding.clone()),
        "predecessor_evidence_id": binding_map.get("evidence_ref").expect("validated binding has evidence"),
        "rebind_receipt_evidence_id": rebind_map.get("rebind_receipt_id").expect("validated rebind has an ID"),
        "candidate_identity": {
            "candidate_sha": candidate_sha,
            "tree_sha": candidate_tree_sha,
        },
        "cas_base_identity": {
            "commit_sha": candidate_sha,
            "tree_sha": candidate_tree_sha,
        },
        "cas_evidence_ref": cas_evidence_ref,
        "cas_stage": "cas",
    });
    let cas = validate_candidate_cas_rebind_transition(&rebind, &cas_receipt)?;

    let repository_digest = format!(
        "sha256:{}",
        fresh_clone_projection_digest("fresh-clone-remote-url", &identity)?
    );
    let branch_ref = "refs/heads/canon/fresh-clone-acceptance";
    let lifecycle_evidence =
        fresh_clone_projection_evidence("fresh-clone-pr-lifecycle", &identity)?;
    let lifecycle_evidence_digest = format!(
        "sha256:{}",
        fresh_clone_projection_digest("fresh-clone-pr-lifecycle", &identity)?
    );
    let mut lifecycle_binding = checked_binding.clone();
    let lifecycle_binding = lifecycle_binding
        .as_object_mut()
        .expect("validated binding is an object");
    lifecycle_binding.insert(
        "evidence_ref".to_owned(),
        JsonValue::String(lifecycle_evidence),
    );
    lifecycle_binding.insert(
        "evidence_digest".to_owned(),
        JsonValue::String(lifecycle_evidence_digest),
    );
    let lifecycle = serde_json::json!({
        "schema": PULL_REQUEST_LIFECYCLE_SCHEMA,
        "kind": "user",
        "binding": JsonValue::Object(lifecycle_binding.clone()),
        "state": "merged",
        "remote_identity": {
            "repo_owner": "fresh-clone-acceptance",
            "repo_name": "agent-canon",
            "remote_name": "origin",
            "url_digest": repository_digest,
            "ref": branch_ref,
            "commit_sha": candidate_sha,
            "tree_sha": candidate_tree_sha,
        },
        "base_identity": {
            "repo_owner": "fresh-clone-acceptance",
            "repo_name": "agent-canon",
            "ref": "refs/heads/main",
            "commit_sha": candidate_sha,
            "tree_sha": candidate_tree_sha,
        },
        "head_identity": {
            "repo_owner": "fresh-clone-acceptance",
            "repo_name": "agent-canon",
            "ref": branch_ref,
            "commit_sha": candidate_sha,
            "tree_sha": candidate_tree_sha,
        },
        "branch": pull_request_branch_table(),
        "permission_identity": {
            "actor_id": "fresh-clone-acceptance",
            "permission_state": "verified_true",
            "permission_evidence_id": fresh_clone_projection_evidence(
                "fresh-clone-permission", &identity
            )?,
            "authority_source": "canonical fresh-clone acceptance fixture",
            "assumption_forbidden": true,
        },
        "pr_essence": {
            "problem": "exercise standalone source publication from a fresh clone",
            "intent": "queue the observed AgentCanon source branch update",
            "canonical_owner": "tools/repository/workspace/repository_topic_clone.py",
            "contract_delta": "fresh-clone source PR",
            "evidence_refs": [fresh_clone_projection_evidence(
                "fresh-clone-pr-essence", &identity
            )?],
        },
        "reviews": [],
        "user_identity": {
            "actor_id": "fresh-clone-acceptance",
            "display_name": "Fresh Clone Acceptance",
        },
    });
    let checked_lifecycle = validate_candidate_cas_pr_transition(&cas, &lifecycle)?;

    let authoritative_pr_readback = serde_json::json!({
        "number": 1,
        "state": "MERGED",
        "baseRefName": "main",
        "baseRefOid": publication_sha,
        "mergeCasBaseOid": candidate_sha,
        "mergeCasBaseTreeOid": candidate_tree_sha,
        "headRefName": "canon/fresh-clone-acceptance",
        "headRefOid": candidate_sha,
        "headRepository": {
            "nameWithOwner": "fresh-clone-acceptance/agent-canon",
        },
        "mergeCommit": {"oid": publication_sha},
        "mergeTreeOid": publication_tree_sha,
    });
    let readback = materialize_publication_readback_receipt(
        &cas,
        &checked_lifecycle,
        &authoritative_pr_readback,
    )?;

    let g1_owner_path = "tools/repository/github/publication_integrator.py";
    let g1_owner = format!(
        "{}#resolve_publication_eligibility",
        source_root.join(g1_owner_path).to_string_lossy()
    );
    let g1_output_digest = format!(
        "sha256:{}",
        fresh_clone_projection_digest("fresh-clone-g1", &identity)?
    );
    let g1 = materialize_gate_verdict(&GateVerdictInput {
        binding: checked_binding.clone(),
        gate_id: "G1".to_owned(),
        ordered_input_evidence_refs: vec![binding_map
            .get("evidence_ref")
            .and_then(JsonValue::as_str)
            .expect("validated binding has evidence")
            .to_owned()],
        invariant: "source_correctness".to_owned(),
        output_digest: g1_output_digest,
        owner: g1_owner,
        verdict: "pass".to_owned(),
        retry_reason: None,
        next_checkpoint: None,
    })?;

    let check_results = gate_owner_apis
        .generated_completeness_check_ids
        .iter()
        .map(|check_id| serde_json::json!({"check_id": check_id, "status": "pass"}))
        .collect::<Vec<_>>();
    let g2 = (gate_owner_apis.materialize_generated_completeness_receipt)(
        &g1,
        candidate_sha,
        candidate_tree_sha,
        &check_results,
    )
    .map_err(FreshCloneSourceProjectionError::G2Owner)?;
    let upstream_gates = [g1.clone(), g2.clone()];
    let g3 = (gate_owner_apis.materialize_pr_identity_gate)(
        &checked_lifecycle,
        &cas,
        &rebind,
        &upstream_gates,
    )
    .map_err(FreshCloneSourceProjectionError::G3Owner)?;

    let predecessor_388 =
        fresh_clone_projection_evidence("fresh-clone-predecessor-388", &identity)?;
    let predecessor_389_digest =
        fresh_clone_projection_digest("fresh-clone-predecessor-389", &identity)?;
    let predecessor_389_sha = predecessor_389_digest[..40].to_owned();
    let predecessor_389 = format!("evidence:{predecessor_389_digest}");
    let acceptance_evidence_ref =
        fresh_clone_projection_evidence("fresh-clone-frontier-acceptance", &identity)?;
    let predecessors = [
        serde_json::json!({
            "queue_number": 388,
            "source_pr": "#388",
            "publication_evidence_id": predecessor_388,
        }),
        serde_json::json!({
            "queue_number": 389,
            "source_pr": "#389",
            "source_pr_sha": predecessor_389_sha,
            "publication_evidence_id": predecessor_389,
        }),
    ];
    let gates = [g1, g2, g3];
    materialize_source_projection_packet(&SourceProjectionPacketInput {
        binding: &checked_binding,
        source_main_rebind_receipt: &rebind,
        candidate_cas_receipt: &cas,
        pull_request_lifecycle: &checked_lifecycle,
        publication_readback_receipt: &readback,
        source_gate_verdicts: &gates,
        ordered_predecessor_evidence: &predecessors,
        acceptance_evidence_ref: &acceptance_evidence_ref,
    })
    .map_err(FreshCloneSourceProjectionError::Lifecycle)
}

#[derive(Clone, Copy)]
struct CandidateStageSpec {
    field: &'static str,
    schema: &'static str,
    receipt_id_field: &'static str,
    receipt_id_prefix: &'static str,
    stage_field: &'static str,
    stage_value: &'static str,
    extra_fields: &'static [&'static str],
}

const CANDIDATE_FREEZE_SPEC: CandidateStageSpec = CandidateStageSpec {
    field: "candidate_freeze_receipt",
    schema: CANDIDATE_FREEZE_SCHEMA,
    receipt_id_field: "freeze_receipt_id",
    receipt_id_prefix: "freeze:",
    stage_field: "freeze_stage",
    stage_value: "candidate_freeze",
    extra_fields: &["freeze_evidence_ref"],
};
const CANDIDATE_REVIEW_SPEC: CandidateStageSpec = CandidateStageSpec {
    field: "candidate_review_receipt",
    schema: CANDIDATE_REVIEW_SCHEMA,
    receipt_id_field: "review_receipt_id",
    receipt_id_prefix: "review:",
    stage_field: "review_stage",
    stage_value: "independent_exact_review",
    extra_fields: &["reviewer_id", "independent_review_evidence_ref"],
};
const CANDIDATE_CAS_SPEC: CandidateStageSpec = CandidateStageSpec {
    field: "candidate_cas_receipt",
    schema: CANDIDATE_CAS_SCHEMA,
    receipt_id_field: "cas_receipt_id",
    receipt_id_prefix: "cas:",
    stage_field: "cas_stage",
    stage_value: "cas",
    extra_fields: &["cas_base_identity", "cas_evidence_ref"],
};
const PUBLICATION_READBACK_SPEC: CandidateStageSpec = CandidateStageSpec {
    field: "publication_readback_receipt",
    schema: PUBLICATION_READBACK_SCHEMA,
    receipt_id_field: "readback_receipt_id",
    receipt_id_prefix: "publication-readback:",
    stage_field: "readback_stage",
    stage_value: "publication_readback",
    extra_fields: &[
        "pr_identity",
        "publication_evidence_ref",
        "authoritative_readback_digest",
    ],
};

fn validate_candidate_identity(
    value: &JsonValue,
    field: &str,
) -> Result<JsonValue, LifecycleContractError> {
    let identity = mapping(value, field)?;
    exact_keys(identity, &["candidate_sha", "tree_sha"], &[], field)?;
    pattern_value(
        required_value(identity, "candidate_sha", field)?,
        &format!("{field}.candidate_sha"),
        |text| lower_hex(text, 40),
    )?;
    pattern_value(
        required_value(identity, "tree_sha", field)?,
        &format!("{field}.tree_sha"),
        |text| lower_hex(text, 40),
    )?;
    canonical_clone(value)
}

fn candidate_matches_binding(
    candidate: &JsonValue,
    binding: &JsonValue,
    field: &str,
) -> Result<(), LifecycleContractError> {
    let binding = validate_record_binding(binding)?;
    let candidate = mapping(candidate, &format!("{field}.candidate_identity"))?;
    let binding = mapping(&binding, "binding")?;
    for key in ["candidate_sha", "tree_sha"] {
        if required_value(candidate, key, &format!("{field}.candidate_identity"))?
            != required_value(binding, key, "binding")?
        {
            return Err(fail("lifecycle:candidate_identity_mismatch", field));
        }
    }
    Ok(())
}

fn validate_candidate_stage_receipt(
    value: &JsonValue,
    spec: CandidateStageSpec,
) -> Result<JsonValue, LifecycleContractError> {
    let receipt = mapping(value, spec.field)?;
    let mut required_fields = vec![
        "schema",
        spec.receipt_id_field,
        "binding",
        "predecessor_evidence_id",
        "rebind_receipt_evidence_id",
        "candidate_identity",
    ];
    required_fields.extend_from_slice(spec.extra_fields);
    required_fields.push(spec.stage_field);
    exact_keys(receipt, &required_fields, &[], spec.field)?;
    if receipt.get("schema").and_then(JsonValue::as_str) != Some(spec.schema) {
        return Err(fail("lifecycle:schema_invalid", spec.schema));
    }
    let receipt_id = pattern_value(
        required_value(receipt, spec.receipt_id_field, spec.field)?,
        &format!("{}.{}", spec.field, spec.receipt_id_field),
        valid_hash_id,
    )?;
    if !receipt_id.starts_with(spec.receipt_id_prefix) {
        return Err(fail(
            "lifecycle:identity_invalid",
            &format!("{}.{}", spec.field, spec.receipt_id_field),
        ));
    }
    let binding = validate_record_binding(required_value(receipt, "binding", spec.field)?)?;
    pattern_value(
        required_value(receipt, "predecessor_evidence_id", spec.field)?,
        &format!("{}.predecessor_evidence_id", spec.field),
        valid_evidence_ref,
    )?;
    let rebind_id = pattern_value(
        required_value(receipt, "rebind_receipt_evidence_id", spec.field)?,
        &format!("{}.rebind_receipt_evidence_id", spec.field),
        valid_hash_id,
    )?;
    if !rebind_id.starts_with("rebind:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            &format!("{}.rebind_receipt_evidence_id", spec.field),
        ));
    }
    let candidate = validate_candidate_identity(
        required_value(receipt, "candidate_identity", spec.field)?,
        &format!("{}.candidate_identity", spec.field),
    )?;
    candidate_matches_binding(&candidate, &binding, spec.field)?;
    if required_value(receipt, spec.stage_field, spec.field)?.as_str() != Some(spec.stage_value) {
        return Err(fail("lifecycle:stage_invalid", spec.field));
    }
    canonical_clone(value)
}

pub fn validate_candidate_freeze_receipt(
    value: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let receipt = validate_candidate_stage_receipt(value, CANDIDATE_FREEZE_SPEC)?;
    let mapping = mapping(&receipt, CANDIDATE_FREEZE_SPEC.field)?;
    pattern_value(
        required_value(mapping, "freeze_evidence_ref", CANDIDATE_FREEZE_SPEC.field)?,
        "candidate_freeze_receipt.freeze_evidence_ref",
        valid_evidence_ref,
    )?;
    Ok(receipt)
}

pub fn validate_candidate_review_receipt(
    value: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let receipt = validate_candidate_stage_receipt(value, CANDIDATE_REVIEW_SPEC)?;
    let mapping = mapping(&receipt, CANDIDATE_REVIEW_SPEC.field)?;
    let reviewer_id = required_string(mapping, "reviewer_id", CANDIDATE_REVIEW_SPEC.field)?;
    if !reviewer_id.starts_with("reviewer:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            "candidate_review_receipt.reviewer_id",
        ));
    }
    pattern_value(
        required_value(
            mapping,
            "independent_review_evidence_ref",
            CANDIDATE_REVIEW_SPEC.field,
        )?,
        "candidate_review_receipt.independent_review_evidence_ref",
        valid_evidence_ref,
    )?;
    Ok(receipt)
}

fn validate_candidate_cas_base_identity(value: &JsonValue) -> Result<(), LifecycleContractError> {
    let field = "candidate_cas_receipt.cas_base_identity";
    let identity = mapping(value, field)?;
    exact_keys(identity, &["commit_sha", "tree_sha"], &[], field)?;
    pattern_value(
        required_value(identity, "commit_sha", field)?,
        "candidate_cas_receipt.cas_base_identity.commit_sha",
        |text| lower_hex(text, 40),
    )?;
    pattern_value(
        required_value(identity, "tree_sha", field)?,
        "candidate_cas_receipt.cas_base_identity.tree_sha",
        |text| lower_hex(text, 40),
    )?;
    Ok(())
}

pub fn validate_candidate_cas_receipt(
    value: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let receipt = validate_candidate_stage_receipt(value, CANDIDATE_CAS_SPEC)?;
    let mapping = mapping(&receipt, CANDIDATE_CAS_SPEC.field)?;
    validate_candidate_cas_base_identity(required_value(
        mapping,
        "cas_base_identity",
        CANDIDATE_CAS_SPEC.field,
    )?)?;
    pattern_value(
        required_value(mapping, "cas_evidence_ref", CANDIDATE_CAS_SPEC.field)?,
        "candidate_cas_receipt.cas_evidence_ref",
        valid_evidence_ref,
    )?;
    Ok(receipt)
}

fn same_binding(
    left: &JsonValue,
    right: &JsonValue,
    field: &str,
) -> Result<(), LifecycleContractError> {
    if binding_identity(left)? != binding_identity(right)? {
        return Err(fail("input_identity_mismatch", field));
    }
    Ok(())
}

fn validate_candidate_stage_transition(
    previous: &JsonValue,
    current: &JsonValue,
    field: &str,
) -> Result<JsonValue, LifecycleContractError> {
    let previous = mapping(previous, field)?;
    let current = mapping(current, field)?;
    same_binding(
        required_value(previous, "binding", field)?,
        required_value(current, "binding", field)?,
        field,
    )?;
    if required_value(previous, "candidate_identity", field)?
        != required_value(current, "candidate_identity", field)?
    {
        return Err(fail("lifecycle:candidate_identity_mismatch", field));
    }
    let previous_binding = mapping(required_value(previous, "binding", field)?, "binding")?;
    if required_value(current, "predecessor_evidence_id", field)?
        != required_value(previous_binding, "evidence_ref", "binding")?
    {
        return Err(fail("lifecycle:predecessor_mismatch", field));
    }
    if required_value(current, "rebind_receipt_evidence_id", field)?
        != required_value(previous, "rebind_receipt_evidence_id", field)?
    {
        return Err(fail("lifecycle:rebind_mismatch", field));
    }
    Ok(JsonValue::Object(current.clone()))
}

pub fn validate_candidate_freeze_transition(
    rebind: &JsonValue,
    freeze: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let checked_rebind = validate_source_main_rebind_receipt(rebind)?;
    let checked_freeze = validate_candidate_freeze_receipt(freeze)?;
    let rebind_map = mapping(&checked_rebind, "source_main_rebind_receipt")?;
    let freeze_map = mapping(&checked_freeze, "candidate_freeze_receipt")?;
    same_binding(
        required_value(rebind_map, "binding", "source_main_rebind_receipt")?,
        required_value(freeze_map, "binding", "candidate_freeze_receipt")?,
        "candidate_freeze",
    )?;
    let rebind_binding = mapping(
        required_value(rebind_map, "binding", "source_main_rebind_receipt")?,
        "binding",
    )?;
    if required_value(
        freeze_map,
        "predecessor_evidence_id",
        "candidate_freeze_receipt",
    )? != required_value(rebind_binding, "evidence_ref", "binding")?
    {
        return Err(fail("lifecycle:predecessor_mismatch", "candidate_freeze"));
    }
    if required_value(
        freeze_map,
        "rebind_receipt_evidence_id",
        "candidate_freeze_receipt",
    )? != required_value(
        rebind_map,
        "rebind_receipt_id",
        "source_main_rebind_receipt",
    )? {
        return Err(fail("lifecycle:rebind_mismatch", "candidate_freeze"));
    }
    Ok(checked_freeze)
}

pub fn validate_candidate_review_transition(
    freeze: &JsonValue,
    review: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let checked_freeze = validate_candidate_freeze_receipt(freeze)?;
    let checked_review = validate_candidate_review_receipt(review)?;
    validate_candidate_stage_transition(&checked_freeze, &checked_review, "candidate_review")
}

pub fn validate_candidate_cas_transition(
    review: &JsonValue,
    cas: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let checked_review = validate_candidate_review_receipt(review)?;
    let checked_cas = validate_candidate_cas_receipt(cas)?;
    validate_candidate_stage_transition(&checked_review, &checked_cas, "candidate_cas")
}

pub fn validate_candidate_cas_rebind_transition(
    rebind: &JsonValue,
    cas: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let checked_rebind = validate_source_main_rebind_receipt(rebind)?;
    let checked_cas = validate_candidate_cas_receipt(cas)?;
    let rebind_map = mapping(&checked_rebind, "source_main_rebind_receipt")?;
    let cas_map = mapping(&checked_cas, "candidate_cas_receipt")?;
    same_binding(
        required_value(rebind_map, "binding", "source_main_rebind_receipt")?,
        required_value(cas_map, "binding", "candidate_cas_receipt")?,
        "candidate_cas.rebind",
    )?;
    if required_value(
        cas_map,
        "rebind_receipt_evidence_id",
        "candidate_cas_receipt",
    )? != required_value(
        rebind_map,
        "rebind_receipt_id",
        "source_main_rebind_receipt",
    )? {
        return Err(fail("lifecycle:rebind_mismatch", "candidate_cas"));
    }
    let rebind_base = mapping(
        required_value(
            rebind_map,
            "new_base_identity",
            "source_main_rebind_receipt",
        )?,
        "source_main_rebind_receipt.new_base_identity",
    )?;
    let cas_base = mapping(
        required_value(cas_map, "cas_base_identity", "candidate_cas_receipt")?,
        "candidate_cas_receipt.cas_base_identity",
    )?;
    if required_value(
        rebind_base,
        "remote",
        "source_main_rebind_receipt.new_base_identity",
    )?
    .as_str()
        != Some("origin")
        || required_value(
            rebind_base,
            "ref",
            "source_main_rebind_receipt.new_base_identity",
        )?
        .as_str()
            != Some("refs/heads/main")
        || required_value(
            cas_base,
            "commit_sha",
            "candidate_cas_receipt.cas_base_identity",
        )? != required_value(
            rebind_base,
            "commit_sha",
            "source_main_rebind_receipt.new_base_identity",
        )?
        || required_value(
            cas_base,
            "tree_sha",
            "candidate_cas_receipt.cas_base_identity",
        )? != required_value(
            rebind_base,
            "tree_sha",
            "source_main_rebind_receipt.new_base_identity",
        )?
    {
        return Err(LifecycleContractError::code(
            "lifecycle:rebind_cas_base_identity_mismatch",
        ));
    }
    Ok(checked_cas)
}

pub fn materialize_candidate_cas_receipt(
    candidate_review_receipt: &JsonValue,
    source_main_rebind_receipt: &JsonValue,
    cas_evidence_ref: &str,
) -> Result<JsonValue, LifecycleContractError> {
    let review = validate_candidate_review_receipt(candidate_review_receipt)?;
    let rebind = validate_source_main_rebind_receipt(source_main_rebind_receipt)?;
    let review_map = mapping(&review, "candidate_review_receipt")?;
    let rebind_map = mapping(&rebind, "source_main_rebind_receipt")?;
    same_binding(
        required_value(review_map, "binding", "candidate_review_receipt")?,
        required_value(rebind_map, "binding", "source_main_rebind_receipt")?,
        "candidate_cas.rebind",
    )?;
    if required_value(
        review_map,
        "rebind_receipt_evidence_id",
        "candidate_review_receipt",
    )? != required_value(
        rebind_map,
        "rebind_receipt_id",
        "source_main_rebind_receipt",
    )? {
        return Err(fail("lifecycle:rebind_mismatch", "candidate_cas"));
    }
    let rebind_base = mapping(
        required_value(
            rebind_map,
            "new_base_identity",
            "source_main_rebind_receipt",
        )?,
        "source_main_rebind_receipt.new_base_identity",
    )?;
    let mut cas_base_fields = JsonMap::new();
    cas_base_fields.insert(
        "commit_sha".to_owned(),
        required_value(
            rebind_base,
            "commit_sha",
            "source_main_rebind_receipt.new_base_identity",
        )?
        .clone(),
    );
    cas_base_fields.insert(
        "tree_sha".to_owned(),
        required_value(
            rebind_base,
            "tree_sha",
            "source_main_rebind_receipt.new_base_identity",
        )?
        .clone(),
    );
    let cas_base = JsonValue::Object(cas_base_fields);
    let cas_evidence_ref = pattern_value(
        &JsonValue::String(cas_evidence_ref.to_owned()),
        "candidate_cas_receipt.cas_evidence_ref",
        valid_evidence_ref,
    )?;
    let review_binding = mapping(
        required_value(review_map, "binding", "candidate_review_receipt")?,
        "binding",
    )?;
    let mut binding = review_binding.clone();
    let evidence_hex = cas_evidence_ref.strip_prefix("evidence:").ok_or_else(|| {
        fail(
            "lifecycle:identity_invalid",
            "candidate_cas_receipt.cas_evidence_ref",
        )
    })?;
    binding.insert(
        "evidence_ref".to_owned(),
        JsonValue::String(cas_evidence_ref.clone()),
    );
    binding.insert(
        "evidence_digest".to_owned(),
        JsonValue::String(format!("sha256:{evidence_hex}")),
    );
    let binding = JsonValue::Object(binding);
    let identity = binding_identity(&binding)?;
    let predecessor_evidence_id =
        required_value(review_binding, "evidence_ref", "binding")?.clone();
    let rebind_receipt_evidence_id = required_value(
        review_map,
        "rebind_receipt_evidence_id",
        "candidate_review_receipt",
    )?
    .clone();
    let candidate_identity =
        required_value(review_map, "candidate_identity", "candidate_review_receipt")?.clone();
    let key = serde_json::json!({
        "binding_identity": [
            identity.transaction_id,
            identity.snapshot_id,
            identity.candidate_sha,
            identity.tree_sha,
            identity.input_digest,
            identity.tool_id,
            identity.tool_version,
        ],
        "predecessor_evidence_id": predecessor_evidence_id,
        "rebind_receipt_evidence_id": rebind_receipt_evidence_id,
        "candidate_identity": candidate_identity,
        "cas_base_identity": cas_base.clone(),
        "cas_evidence_ref": cas_evidence_ref.clone(),
    });
    let canonical = canonical_json_bytes(&key).map_err(LifecycleContractError::from)?;
    let digest = Sha256::digest(canonical)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let mut receipt = JsonMap::new();
    receipt.insert(
        "schema".to_owned(),
        JsonValue::String(CANDIDATE_CAS_SCHEMA.to_owned()),
    );
    receipt.insert(
        "cas_receipt_id".to_owned(),
        JsonValue::String(format!("cas:{digest}")),
    );
    receipt.insert("binding".to_owned(), binding);
    receipt.insert(
        "predecessor_evidence_id".to_owned(),
        required_value(review_binding, "evidence_ref", "binding")?.clone(),
    );
    receipt.insert(
        "rebind_receipt_evidence_id".to_owned(),
        required_value(
            review_map,
            "rebind_receipt_evidence_id",
            "candidate_review_receipt",
        )?
        .clone(),
    );
    receipt.insert(
        "candidate_identity".to_owned(),
        required_value(review_map, "candidate_identity", "candidate_review_receipt")?.clone(),
    );
    receipt.insert("cas_base_identity".to_owned(), cas_base);
    receipt.insert(
        "cas_evidence_ref".to_owned(),
        JsonValue::String(cas_evidence_ref),
    );
    receipt.insert("cas_stage".to_owned(), JsonValue::String("cas".to_owned()));
    let receipt = JsonValue::Object(receipt);
    let checked = validate_candidate_cas_transition(&review, &receipt)?;
    validate_candidate_cas_rebind_transition(&rebind, &checked)
}

pub fn pull_request_branch_table() -> JsonValue {
    let mut table = JsonMap::new();
    for (kind, required, forbidden) in PR_BRANCH_RULES {
        table.insert(
            (*kind).to_owned(),
            serde_json::json!({
                "required": *required,
                "forbidden": *forbidden,
            }),
        );
    }
    JsonValue::Object(table)
}

fn validate_pr_repo_identity(
    value: &JsonValue,
    field: &str,
    remote: bool,
) -> Result<JsonValue, LifecycleContractError> {
    let identity = mapping(value, field)?;
    let required = if remote {
        &[
            "repo_owner",
            "repo_name",
            "remote_name",
            "url_digest",
            "ref",
            "commit_sha",
            "tree_sha",
        ][..]
    } else {
        &["repo_owner", "repo_name", "ref", "commit_sha", "tree_sha"][..]
    };
    exact_keys(identity, required, &[], field)?;
    for key in ["repo_owner", "repo_name", "ref"] {
        string_value(
            required_value(identity, key, field)?,
            &format!("{field}.{key}"),
        )?;
    }
    if remote {
        string_value(
            required_value(identity, "remote_name", field)?,
            &format!("{field}.remote_name"),
        )?;
        pattern_value(
            required_value(identity, "url_digest", field)?,
            &format!("{field}.url_digest"),
            valid_sha256,
        )?;
    }
    for key in ["commit_sha", "tree_sha"] {
        pattern_value(
            required_value(identity, key, field)?,
            &format!("{field}.{key}"),
            |text| lower_hex(text, 40),
        )?;
    }
    canonical_clone(value)
}

fn validate_pr_actor(value: &JsonValue, field: &str) -> Result<JsonValue, LifecycleContractError> {
    let actor = mapping(value, field)?;
    exact_keys(actor, &["actor_id", "display_name"], &[], field)?;
    for key in ["actor_id", "display_name"] {
        string_value(
            required_value(actor, key, field)?,
            &format!("{field}.{key}"),
        )?;
    }
    canonical_clone(value)
}

fn validate_pr_branch_table(value: &JsonValue) -> Result<(), LifecycleContractError> {
    let table = mapping(value, "pull_request_lifecycle.branch")?;
    exact_keys(table, PR_KINDS, &[], "pull_request_lifecycle.branch")?;
    for (kind, expected_required, expected_forbidden) in PR_BRANCH_RULES {
        let field = format!("pull_request_lifecycle.branch.{kind}");
        let rule = mapping(
            required_value(table, kind, "pull_request_lifecycle.branch")?,
            &field,
        )?;
        exact_keys(rule, &["required", "forbidden"], &[], &field)?;
        let required = string_list(
            required_value(rule, "required", &field)?,
            &format!("{field}.required"),
            false,
            true,
            None,
        )?;
        let forbidden = string_list(
            required_value(rule, "forbidden", &field)?,
            &format!("{field}.forbidden"),
            false,
            true,
            None,
        )?;
        let expected_required = expected_required
            .iter()
            .map(|field| (*field).to_owned())
            .collect::<Vec<_>>();
        let expected_forbidden = expected_forbidden
            .iter()
            .map(|field| (*field).to_owned())
            .collect::<Vec<_>>();
        if required != expected_required || forbidden != expected_forbidden {
            return Err(fail("pr_lifecycle:branch_rule_mismatch", kind));
        }
    }
    Ok(())
}

pub fn validate_pull_request_lifecycle(
    value: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let lifecycle = mapping(value, "pull_request_lifecycle")?;
    let common = [
        "schema",
        "kind",
        "binding",
        "state",
        "remote_identity",
        "base_identity",
        "head_identity",
        "branch",
        "permission_identity",
        "pr_essence",
        "reviews",
    ];
    let optional = [
        "user_identity",
        "fork_identity",
        "contributor_identity",
        "contributor_diff",
        "successor_ref",
    ];
    exact_keys(lifecycle, &common, &optional, "pull_request_lifecycle")?;
    if lifecycle.get("schema").and_then(JsonValue::as_str) != Some(PULL_REQUEST_LIFECYCLE_SCHEMA) {
        return Err(fail(
            "lifecycle:schema_invalid",
            PULL_REQUEST_LIFECYCLE_SCHEMA,
        ));
    }
    let kind = one_of(
        required_value(lifecycle, "kind", "pull_request_lifecycle")?,
        PR_KINDS,
        "pull_request_lifecycle.kind",
    )?;
    let state = one_of(
        required_value(lifecycle, "state", "pull_request_lifecycle")?,
        PR_STATES,
        "pull_request_lifecycle.state",
    )?;
    let binding = validate_record_binding(required_value(
        lifecycle,
        "binding",
        "pull_request_lifecycle",
    )?)?;
    let remote = validate_pr_repo_identity(
        required_value(lifecycle, "remote_identity", "pull_request_lifecycle")?,
        "pull_request_lifecycle.remote_identity",
        true,
    )?;
    let base = validate_pr_repo_identity(
        required_value(lifecycle, "base_identity", "pull_request_lifecycle")?,
        "pull_request_lifecycle.base_identity",
        false,
    )?;
    let head = validate_pr_repo_identity(
        required_value(lifecycle, "head_identity", "pull_request_lifecycle")?,
        "pull_request_lifecycle.head_identity",
        false,
    )?;
    let binding_map = mapping(&binding, "binding")?;
    let head_map = mapping(&head, "pull_request_lifecycle.head_identity")?;
    if required_value(
        head_map,
        "commit_sha",
        "pull_request_lifecycle.head_identity",
    )? != required_value(binding_map, "candidate_sha", "binding")?
        || required_value(head_map, "tree_sha", "pull_request_lifecycle.head_identity")?
            != required_value(binding_map, "tree_sha", "binding")?
    {
        return Err(fail("pr_lifecycle:head_binding_mismatch", ""));
    }
    let remote_map = mapping(&remote, "pull_request_lifecycle.remote_identity")?;
    for field in ["repo_owner", "repo_name", "ref", "commit_sha", "tree_sha"] {
        if required_value(remote_map, field, "pull_request_lifecycle.remote_identity")?
            != required_value(head_map, field, "pull_request_lifecycle.head_identity")?
        {
            return Err(fail("pr_lifecycle:remote_head_identity_mismatch", ""));
        }
    }
    validate_pr_branch_table(required_value(
        lifecycle,
        "branch",
        "pull_request_lifecycle",
    )?)?;
    let (_, required_branch_fields, forbidden_branch_fields) = PR_BRANCH_RULES
        .iter()
        .copied()
        .find(|(rule_kind, _, _)| *rule_kind == kind.as_str())
        .ok_or_else(|| fail("lifecycle:enum_invalid", "pull_request_lifecycle.kind"))?;
    for &field in required_branch_fields {
        if !lifecycle.contains_key(field) {
            return Err(fail("pr_lifecycle:branch_field_missing", field));
        }
    }
    for &field in forbidden_branch_fields {
        if lifecycle.contains_key(field) {
            return Err(fail("pr_lifecycle:branch_field_forbidden", field));
        }
    }

    let mut user_identity = None;
    match kind.as_str() {
        "user" => {
            user_identity = Some(validate_pr_actor(
                required_value(lifecycle, "user_identity", "pull_request_lifecycle")?,
                "pull_request_lifecycle.user_identity",
            )?);
            let base_map = mapping(&base, "pull_request_lifecycle.base_identity")?;
            for field in ["repo_owner", "repo_name"] {
                if required_value(base_map, field, "pull_request_lifecycle.base_identity")?
                    != required_value(head_map, field, "pull_request_lifecycle.head_identity")?
                {
                    return Err(fail("pr_lifecycle:user_repository_mismatch", ""));
                }
            }
        }
        "fork" => {
            let field = "pull_request_lifecycle.fork_identity";
            let fork = mapping(
                required_value(lifecycle, "fork_identity", "pull_request_lifecycle")?,
                field,
            )?;
            exact_keys(
                fork,
                &[
                    "repo_owner",
                    "repo_name",
                    "parent_repo_owner",
                    "parent_repo_name",
                    "ref",
                ],
                &[],
                field,
            )?;
            for key in [
                "repo_owner",
                "repo_name",
                "parent_repo_owner",
                "parent_repo_name",
                "ref",
            ] {
                string_value(required_value(fork, key, field)?, &format!("{field}.{key}"))?;
            }
            let base_map = mapping(&base, "pull_request_lifecycle.base_identity")?;
            let comparisons = [
                (
                    "repo_owner",
                    head_map,
                    "pull_request_lifecycle.head_identity",
                    "repo_owner",
                ),
                (
                    "repo_name",
                    head_map,
                    "pull_request_lifecycle.head_identity",
                    "repo_name",
                ),
                (
                    "parent_repo_owner",
                    base_map,
                    "pull_request_lifecycle.base_identity",
                    "repo_owner",
                ),
                (
                    "parent_repo_name",
                    base_map,
                    "pull_request_lifecycle.base_identity",
                    "repo_name",
                ),
                (
                    "ref",
                    head_map,
                    "pull_request_lifecycle.head_identity",
                    "ref",
                ),
            ];
            for (source_field, target, target_parent, target_field) in comparisons {
                if required_value(fork, source_field, field)?
                    != required_value(target, target_field, target_parent)?
                {
                    return Err(fail("pr_lifecycle:fork_identity_mismatch", ""));
                }
            }
        }
        "contributor" => {
            validate_pr_actor(
                required_value(lifecycle, "contributor_identity", "pull_request_lifecycle")?,
                "pull_request_lifecycle.contributor_identity",
            )?;
            let field = "pull_request_lifecycle.contributor_diff";
            let diff = mapping(
                required_value(lifecycle, "contributor_diff", "pull_request_lifecycle")?,
                field,
            )?;
            exact_keys(diff, &["commit_sha", "tree_sha", "diff_sha256"], &[], field)?;
            for key in ["commit_sha", "tree_sha"] {
                pattern_value(
                    required_value(diff, key, field)?,
                    &format!("{field}.{key}"),
                    |text| lower_hex(text, 40),
                )?;
            }
            pattern_value(
                required_value(diff, "diff_sha256", field)?,
                &format!("{field}.diff_sha256"),
                valid_sha256,
            )?;
            if required_value(diff, "commit_sha", field)?
                != required_value(
                    head_map,
                    "commit_sha",
                    "pull_request_lifecycle.head_identity",
                )?
                || required_value(diff, "tree_sha", field)?
                    != required_value(head_map, "tree_sha", "pull_request_lifecycle.head_identity")?
            {
                return Err(fail("pr_lifecycle:contributor_diff_identity_mismatch", ""));
            }
        }
        _ => {
            return Err(fail(
                "lifecycle:enum_invalid",
                "pull_request_lifecycle.kind",
            ))
        }
    }

    let permission_field = "pull_request_lifecycle.permission_identity";
    let permission = mapping(
        required_value(lifecycle, "permission_identity", "pull_request_lifecycle")?,
        permission_field,
    )?;
    exact_keys(
        permission,
        &[
            "actor_id",
            "permission_state",
            "permission_evidence_id",
            "authority_source",
            "assumption_forbidden",
        ],
        &[],
        permission_field,
    )?;
    let permission_actor = string_value(
        required_value(permission, "actor_id", permission_field)?,
        "pull_request_lifecycle.permission_identity.actor_id",
    )?;
    let permission_state = one_of(
        required_value(permission, "permission_state", permission_field)?,
        &["unknown", "verified_true", "verified_false"],
        "pull_request_lifecycle.permission_identity.permission_state",
    )?;
    pattern_value(
        required_value(permission, "permission_evidence_id", permission_field)?,
        "pull_request_lifecycle.permission_identity.permission_evidence_id",
        valid_evidence_ref,
    )?;
    string_value(
        required_value(permission, "authority_source", permission_field)?,
        "pull_request_lifecycle.permission_identity.authority_source",
    )?;
    if required_value(permission, "assumption_forbidden", permission_field)?
        != &JsonValue::Bool(true)
    {
        return Err(fail("pr_lifecycle:permission_assumption_forbidden", ""));
    }
    if kind == "user"
        && user_identity
            .as_ref()
            .and_then(|identity| identity.get("actor_id"))
            != Some(&JsonValue::String(permission_actor))
    {
        return Err(fail("pr_lifecycle:actor_identity_mismatch", ""));
    }
    if (state == "permission_unknown" && permission_state != "unknown")
        || (state == "permission_denied" && permission_state != "verified_false")
    {
        return Err(fail("pr_lifecycle:permission_state_mismatch", ""));
    }
    if (PR_REVIEWABLE_STATES.contains(&state.as_str()) || state == "merged")
        && permission_state != "verified_true"
    {
        return Err(fail("pr_lifecycle:verified_permission_required", &state));
    }

    let essence_field = "pull_request_lifecycle.pr_essence";
    let essence = mapping(
        required_value(lifecycle, "pr_essence", "pull_request_lifecycle")?,
        essence_field,
    )?;
    exact_keys(
        essence,
        &[
            "problem",
            "intent",
            "canonical_owner",
            "contract_delta",
            "evidence_refs",
        ],
        &[],
        essence_field,
    )?;
    for key in ["problem", "intent", "canonical_owner", "contract_delta"] {
        string_value(
            required_value(essence, key, essence_field)?,
            &format!("{essence_field}.{key}"),
        )?;
    }
    string_list(
        required_value(essence, "evidence_refs", essence_field)?,
        "pull_request_lifecycle.pr_essence.evidence_refs",
        true,
        true,
        Some(valid_evidence_ref),
    )?;

    let reviews = required_value(lifecycle, "reviews", "pull_request_lifecycle")?
        .as_array()
        .ok_or_else(|| {
            fail(
                "lifecycle:sequence_required",
                "pull_request_lifecycle.reviews",
            )
        })?;
    for (index, review_value) in reviews.iter().enumerate() {
        let field = format!("pull_request_lifecycle.reviews[{index}]");
        let review = mapping(review_value, &field)?;
        exact_keys(
            review,
            &["review_id", "reviewer_id", "state", "body_digest"],
            &[],
            &field,
        )?;
        for key in ["review_id", "reviewer_id"] {
            string_value(
                required_value(review, key, &field)?,
                &format!("{field}.{key}"),
            )?;
        }
        one_of(
            required_value(review, "state", &field)?,
            &["approved", "changes_requested", "commented", "dismissed"],
            &format!("{field}.state"),
        )?;
        pattern_value(
            required_value(review, "body_digest", &field)?,
            &format!("{field}.body_digest"),
            valid_sha256,
        )?;
    }

    let successor = lifecycle.get("successor_ref").unwrap_or(&JsonValue::Null);
    if state == "conflict_successor" {
        let successor = pattern_value(
            successor,
            "pull_request_lifecycle.successor_ref",
            valid_hash_id,
        )?;
        if !successor.starts_with("pr-successor:") {
            return Err(fail(
                "lifecycle:identity_invalid",
                "pull_request_lifecycle.successor_ref",
            ));
        }
    } else if !successor.is_null() {
        return Err(fail("pr_lifecycle:successor_forbidden", ""));
    }
    canonical_clone(value)
}

pub fn validate_pull_request_transition(
    previous: &JsonValue,
    current: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let old = validate_pull_request_lifecycle(previous)?;
    let new = validate_pull_request_lifecycle(current)?;
    let old_map = mapping(&old, "pull_request_lifecycle")?;
    let new_map = mapping(&new, "pull_request_lifecycle")?;
    let old_state = required_string(old_map, "state", "pull_request_lifecycle")?;
    let new_state = required_string(new_map, "state", "pull_request_lifecycle")?;
    same_binding(
        required_value(old_map, "binding", "pull_request_lifecycle")?,
        required_value(new_map, "binding", "pull_request_lifecycle")?,
        "pull_request_lifecycle",
    )?;
    let mut allowed = PULL_REQUEST_TRANSITIONS.contains(&(old_state.as_str(), new_state.as_str()))
        || (old_state == new_state && PR_OPEN_STATES.contains(&old_state.as_str()));
    if PR_OPEN_STATES.contains(&old_state.as_str())
        && matches!(new_state.as_str(), "closed_head" | "multiple_remotes")
    {
        allowed = true;
    }
    if PR_REVIEWABLE_STATES.contains(&old_state.as_str()) && new_state == "conflict_successor" {
        allowed = true;
    }
    if !allowed {
        return Err(fail(
            "pr_lifecycle:transition_invalid",
            &format!("{old_state}->{new_state}"),
        ));
    }

    for field in [
        "kind",
        "remote_identity",
        "base_identity",
        "head_identity",
        "branch",
        "permission_identity",
    ] {
        if required_value(old_map, field, "pull_request_lifecycle")?
            != required_value(new_map, field, "pull_request_lifecycle")?
        {
            let permission_refresh = field == "permission_identity"
                && ((matches!(
                    old_state.as_str(),
                    "permission_unknown" | "permission_denied" | "multiple_remotes"
                ) && new_state == "ready")
                    || (old_state == "permission_unknown" && new_state == "permission_denied"));
            if !permission_refresh {
                return Err(fail("pr_lifecycle:immutable_identity_changed", field));
            }
        }
    }
    if required_value(old_map, "pr_essence", "pull_request_lifecycle")?
        != required_value(new_map, "pr_essence", "pull_request_lifecycle")?
    {
        return Err(fail("pr_lifecycle:retained_field_changed", "pr_essence"));
    }
    let old_reviews = required_value(old_map, "reviews", "pull_request_lifecycle")?
        .as_array()
        .ok_or_else(|| {
            fail(
                "lifecycle:sequence_required",
                "pull_request_lifecycle.reviews",
            )
        })?;
    let new_reviews = required_value(new_map, "reviews", "pull_request_lifecycle")?
        .as_array()
        .ok_or_else(|| {
            fail(
                "lifecycle:sequence_required",
                "pull_request_lifecycle.reviews",
            )
        })?;
    if new_reviews.get(..old_reviews.len()) != Some(old_reviews.as_slice()) {
        return Err(fail("pr_lifecycle:retained_field_changed", "reviews"));
    }
    if required_value(old_map, "kind", "pull_request_lifecycle")?
        == &JsonValue::String("contributor".to_owned())
        && required_value(old_map, "contributor_diff", "pull_request_lifecycle")?
            != required_value(new_map, "contributor_diff", "pull_request_lifecycle")?
    {
        return Err(fail(
            "pr_lifecycle:retained_field_changed",
            "contributor_diff",
        ));
    }
    Ok(new)
}

pub fn validate_candidate_cas_pr_transition(
    cas: &JsonValue,
    pr_lifecycle: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let checked_cas = validate_candidate_cas_receipt(cas)?;
    let checked_pr = validate_pull_request_lifecycle(pr_lifecycle)?;
    let cas_map = mapping(&checked_cas, "candidate_cas_receipt")?;
    let pr_map = mapping(&checked_pr, "pull_request_lifecycle")?;
    same_binding(
        required_value(cas_map, "binding", "candidate_cas_receipt")?,
        required_value(pr_map, "binding", "pull_request_lifecycle")?,
        "candidate_cas.pr",
    )?;
    let candidate = mapping(
        required_value(cas_map, "candidate_identity", "candidate_cas_receipt")?,
        "candidate_cas_receipt.candidate_identity",
    )?;
    let head = mapping(
        required_value(pr_map, "head_identity", "pull_request_lifecycle")?,
        "pull_request_lifecycle.head_identity",
    )?;
    if required_value(
        candidate,
        "candidate_sha",
        "candidate_cas_receipt.candidate_identity",
    )? != required_value(head, "commit_sha", "pull_request_lifecycle.head_identity")?
        || required_value(
            candidate,
            "tree_sha",
            "candidate_cas_receipt.candidate_identity",
        )? != required_value(head, "tree_sha", "pull_request_lifecycle.head_identity")?
    {
        return Err(fail(
            "lifecycle:candidate_identity_mismatch",
            "candidate_cas.pr",
        ));
    }
    let cas_base = mapping(
        required_value(cas_map, "cas_base_identity", "candidate_cas_receipt")?,
        "candidate_cas_receipt.cas_base_identity",
    )?;
    let pr_base = mapping(
        required_value(pr_map, "base_identity", "pull_request_lifecycle")?,
        "pull_request_lifecycle.base_identity",
    )?;
    if required_value(
        cas_base,
        "commit_sha",
        "candidate_cas_receipt.cas_base_identity",
    )? != required_value(
        pr_base,
        "commit_sha",
        "pull_request_lifecycle.base_identity",
    )? || required_value(
        cas_base,
        "tree_sha",
        "candidate_cas_receipt.cas_base_identity",
    )? != required_value(pr_base, "tree_sha", "pull_request_lifecycle.base_identity")?
    {
        return Err(fail("lifecycle:cas_base_identity_mismatch", ""));
    }
    Ok(checked_pr)
}

pub fn validate_publication_readback_receipt(
    value: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let receipt = validate_candidate_stage_receipt(value, PUBLICATION_READBACK_SPEC)?;
    let receipt_map = mapping(&receipt, PUBLICATION_READBACK_SPEC.field)?;
    let pr_field = "publication_readback_receipt.pr_identity";
    let pr = mapping(
        required_value(receipt_map, "pr_identity", PUBLICATION_READBACK_SPEC.field)?,
        pr_field,
    )?;
    exact_keys(
        pr,
        &[
            "number",
            "remote_name",
            "base_ref",
            "head_ref",
            "head_repo_owner",
            "head_repo_name",
            "post_merge_base_ref_sha",
            "merge_cas_base_sha",
            "merge_cas_base_tree_sha",
            "head_sha",
            "merge_commit_sha",
            "merge_tree_sha",
        ],
        &[],
        pr_field,
    )?;
    positive_integer(
        required_value(pr, "number", pr_field)?,
        "publication_readback_receipt.pr_identity.number",
        false,
    )?;
    if required_value(pr, "remote_name", pr_field)?.as_str() != Some("origin")
        || required_value(pr, "base_ref", pr_field)?.as_str() != Some("refs/heads/main")
    {
        return Err(fail("lifecycle:publication_remote_identity_mismatch", ""));
    }
    for field in ["head_ref", "head_repo_owner", "head_repo_name"] {
        string_value(
            required_value(pr, field, pr_field)?,
            &format!("{pr_field}.{field}"),
        )?;
    }
    for field in [
        "post_merge_base_ref_sha",
        "merge_cas_base_sha",
        "merge_cas_base_tree_sha",
        "head_sha",
        "merge_commit_sha",
        "merge_tree_sha",
    ] {
        pattern_value(
            required_value(pr, field, pr_field)?,
            &format!("{pr_field}.{field}"),
            |text| lower_hex(text, 40),
        )?;
    }
    let candidate = mapping(
        required_value(
            receipt_map,
            "candidate_identity",
            PUBLICATION_READBACK_SPEC.field,
        )?,
        "publication_readback_receipt.candidate_identity",
    )?;
    if required_value(pr, "head_sha", pr_field)?
        != required_value(
            candidate,
            "candidate_sha",
            "publication_readback_receipt.candidate_identity",
        )?
    {
        return Err(fail("lifecycle:publication_candidate_mismatch", ""));
    }
    pattern_value(
        required_value(
            receipt_map,
            "publication_evidence_ref",
            PUBLICATION_READBACK_SPEC.field,
        )?,
        "publication_readback_receipt.publication_evidence_ref",
        valid_evidence_ref,
    )?;
    pattern_value(
        required_value(
            receipt_map,
            "authoritative_readback_digest",
            PUBLICATION_READBACK_SPEC.field,
        )?,
        "publication_readback_receipt.authoritative_readback_digest",
        valid_sha256,
    )?;
    Ok(receipt)
}

pub fn validate_publication_readback_transition(
    cas: &JsonValue,
    pr_lifecycle: &JsonValue,
    readback: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let checked_cas = validate_candidate_cas_receipt(cas)?;
    let checked_pr = validate_pull_request_lifecycle(pr_lifecycle)?;
    let checked_readback = validate_publication_readback_receipt(readback)?;
    let cas_map = mapping(&checked_cas, "candidate_cas_receipt")?;
    let pr_map = mapping(&checked_pr, "pull_request_lifecycle")?;
    let readback_map = mapping(&checked_readback, "publication_readback_receipt")?;
    if required_string(pr_map, "state", "pull_request_lifecycle")? != "merged" {
        return Err(fail("lifecycle:pr_not_merged", ""));
    }
    same_binding(
        required_value(cas_map, "binding", "candidate_cas_receipt")?,
        required_value(pr_map, "binding", "pull_request_lifecycle")?,
        "publication_readback.pr",
    )?;
    same_binding(
        required_value(pr_map, "binding", "pull_request_lifecycle")?,
        required_value(readback_map, "binding", "publication_readback_receipt")?,
        "publication_readback",
    )?;
    if required_value(cas_map, "candidate_identity", "candidate_cas_receipt")?
        != required_value(
            readback_map,
            "candidate_identity",
            "publication_readback_receipt",
        )?
    {
        return Err(fail(
            "lifecycle:candidate_identity_mismatch",
            "publication_readback",
        ));
    }
    let cas_base = mapping(
        required_value(cas_map, "cas_base_identity", "candidate_cas_receipt")?,
        "candidate_cas_receipt.cas_base_identity",
    )?;
    let pr_base = mapping(
        required_value(pr_map, "base_identity", "pull_request_lifecycle")?,
        "pull_request_lifecycle.base_identity",
    )?;
    let pr_head = mapping(
        required_value(pr_map, "head_identity", "pull_request_lifecycle")?,
        "pull_request_lifecycle.head_identity",
    )?;
    let readback_pr = mapping(
        required_value(readback_map, "pr_identity", "publication_readback_receipt")?,
        "publication_readback_receipt.pr_identity",
    )?;
    if required_value(
        cas_base,
        "commit_sha",
        "candidate_cas_receipt.cas_base_identity",
    )? != required_value(
        pr_base,
        "commit_sha",
        "pull_request_lifecycle.base_identity",
    )? || required_value(
        cas_base,
        "tree_sha",
        "candidate_cas_receipt.cas_base_identity",
    )? != required_value(pr_base, "tree_sha", "pull_request_lifecycle.base_identity")?
        || required_value(
            readback_pr,
            "merge_cas_base_sha",
            "publication_readback_receipt.pr_identity",
        )? != required_value(
            cas_base,
            "commit_sha",
            "candidate_cas_receipt.cas_base_identity",
        )?
        || required_value(
            readback_pr,
            "merge_cas_base_tree_sha",
            "publication_readback_receipt.pr_identity",
        )? != required_value(
            cas_base,
            "tree_sha",
            "candidate_cas_receipt.cas_base_identity",
        )?
    {
        return Err(fail("lifecycle:cas_base_identity_mismatch", ""));
    }
    if required_value(
        readback_pr,
        "head_sha",
        "publication_readback_receipt.pr_identity",
    )? != required_value(
        pr_head,
        "commit_sha",
        "pull_request_lifecycle.head_identity",
    )? {
        return Err(fail("lifecycle:publication_head_identity_mismatch", ""));
    }
    let remote = mapping(
        required_value(pr_map, "remote_identity", "pull_request_lifecycle")?,
        "pull_request_lifecycle.remote_identity",
    )?;
    for (readback_field, identity, identity_field, identity_parent) in [
        (
            "remote_name",
            remote,
            "remote_name",
            "pull_request_lifecycle.remote_identity",
        ),
        (
            "base_ref",
            pr_base,
            "ref",
            "pull_request_lifecycle.base_identity",
        ),
        (
            "head_ref",
            pr_head,
            "ref",
            "pull_request_lifecycle.head_identity",
        ),
        (
            "head_repo_owner",
            pr_head,
            "repo_owner",
            "pull_request_lifecycle.head_identity",
        ),
        (
            "head_repo_name",
            pr_head,
            "repo_name",
            "pull_request_lifecycle.head_identity",
        ),
    ] {
        if required_value(
            readback_pr,
            readback_field,
            "publication_readback_receipt.pr_identity",
        )? != required_value(identity, identity_field, identity_parent)?
        {
            return Err(fail("lifecycle:publication_remote_identity_mismatch", ""));
        }
    }
    let pr_binding = mapping(
        required_value(pr_map, "binding", "pull_request_lifecycle")?,
        "binding",
    )?;
    if required_value(
        readback_map,
        "predecessor_evidence_id",
        "publication_readback_receipt",
    )? != required_value(pr_binding, "evidence_ref", "binding")?
    {
        return Err(fail(
            "lifecycle:predecessor_mismatch",
            "publication_readback",
        ));
    }
    if required_value(
        readback_map,
        "rebind_receipt_evidence_id",
        "publication_readback_receipt",
    )? != required_value(
        cas_map,
        "rebind_receipt_evidence_id",
        "candidate_cas_receipt",
    )? {
        return Err(fail("lifecycle:rebind_mismatch", "publication_readback"));
    }
    Ok(checked_readback)
}

pub fn materialize_publication_readback_receipt(
    candidate_cas_receipt: &JsonValue,
    pull_request_lifecycle: &JsonValue,
    authoritative_pr_readback: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let cas = validate_candidate_cas_receipt(candidate_cas_receipt)?;
    let lifecycle = validate_candidate_cas_pr_transition(&cas, pull_request_lifecycle)?;
    let lifecycle_map = mapping(&lifecycle, "pull_request_lifecycle")?;
    if required_string(lifecycle_map, "state", "pull_request_lifecycle")? != "merged" {
        return Err(fail("lifecycle:pr_not_merged", ""));
    }
    let readback = mapping(authoritative_pr_readback, "authoritative_pr_readback")?;
    let pr_number = readback.get("number").unwrap_or(&JsonValue::Null);
    positive_integer(pr_number, "authoritative_pr_readback.number", false)?;
    if readback
        .get("state")
        .and_then(JsonValue::as_str)
        .is_none_or(|state| state.to_uppercase() != "MERGED")
    {
        return Err(fail("lifecycle:pr_not_merged", ""));
    }
    let cas_map = mapping(&cas, "candidate_cas_receipt")?;
    let lifecycle_binding = mapping(
        required_value(lifecycle_map, "binding", "pull_request_lifecycle")?,
        "binding",
    )?;
    let candidate = required_value(cas_map, "candidate_identity", "candidate_cas_receipt")?;
    let base = mapping(
        required_value(lifecycle_map, "base_identity", "pull_request_lifecycle")?,
        "pull_request_lifecycle.base_identity",
    )?;
    let head = mapping(
        required_value(lifecycle_map, "head_identity", "pull_request_lifecycle")?,
        "pull_request_lifecycle.head_identity",
    )?;
    let remote = mapping(
        required_value(lifecycle_map, "remote_identity", "pull_request_lifecycle")?,
        "pull_request_lifecycle.remote_identity",
    )?;
    let head_repository = mapping(
        readback.get("headRepository").unwrap_or(&JsonValue::Null),
        "authoritative_pr_readback.headRepository",
    )?;
    let head_repo = string_value(
        head_repository
            .get("nameWithOwner")
            .unwrap_or(&JsonValue::Null),
        "authoritative_pr_readback.headRepository.nameWithOwner",
    )?;
    let expected_head_repo = format!(
        "{}/{}",
        required_string(head, "repo_owner", "pull_request_lifecycle.head_identity")?,
        required_string(head, "repo_name", "pull_request_lifecycle.head_identity")?
    );
    let merge_commit = mapping(
        readback.get("mergeCommit").unwrap_or(&JsonValue::Null),
        "authoritative_pr_readback.mergeCommit",
    )?;
    let merge_commit_sha = pattern_value(
        merge_commit.get("oid").unwrap_or(&JsonValue::Null),
        "authoritative_pr_readback.mergeCommit.oid",
        |text| lower_hex(text, 40),
    )?;
    let merge_tree_sha = pattern_value(
        readback.get("mergeTreeOid").unwrap_or(&JsonValue::Null),
        "authoritative_pr_readback.mergeTreeOid",
        |text| lower_hex(text, 40),
    )?;
    let post_merge_base_ref_sha = pattern_value(
        readback.get("baseRefOid").unwrap_or(&JsonValue::Null),
        "authoritative_pr_readback.baseRefOid",
        |text| lower_hex(text, 40),
    )?;
    let merge_cas_base_sha = pattern_value(
        readback.get("mergeCasBaseOid").unwrap_or(&JsonValue::Null),
        "authoritative_pr_readback.mergeCasBaseOid",
        |text| lower_hex(text, 40),
    )?;
    let merge_cas_base_tree_sha = pattern_value(
        readback
            .get("mergeCasBaseTreeOid")
            .unwrap_or(&JsonValue::Null),
        "authoritative_pr_readback.mergeCasBaseTreeOid",
        |text| lower_hex(text, 40),
    )?;
    let head_sha = pattern_value(
        readback.get("headRefOid").unwrap_or(&JsonValue::Null),
        "authoritative_pr_readback.headRefOid",
        |text| lower_hex(text, 40),
    )?;
    let base_ref = required_string(base, "ref", "pull_request_lifecycle.base_identity")?;
    let head_ref = required_string(head, "ref", "pull_request_lifecycle.head_identity")?;
    let expected_base_ref = base_ref.strip_prefix("refs/heads/").unwrap_or(&base_ref);
    let expected_head_ref = head_ref.strip_prefix("refs/heads/").unwrap_or(&head_ref);
    if readback.get("baseRefName").and_then(JsonValue::as_str) != Some(expected_base_ref)
        || readback.get("headRefName").and_then(JsonValue::as_str) != Some(expected_head_ref)
        || head_sha != required_string(head, "commit_sha", "pull_request_lifecycle.head_identity")?
        || head_repo != expected_head_repo
        || merge_cas_base_sha
            != required_string(base, "commit_sha", "pull_request_lifecycle.base_identity")?
        || merge_cas_base_tree_sha
            != required_string(base, "tree_sha", "pull_request_lifecycle.base_identity")?
    {
        return Err(fail("lifecycle:authoritative_pr_readback_mismatch", ""));
    }

    let pr_identity = serde_json::json!({
        "number": pr_number,
        "remote_name": required_value(remote, "remote_name", "pull_request_lifecycle.remote_identity")?,
        "base_ref": required_value(base, "ref", "pull_request_lifecycle.base_identity")?,
        "head_ref": required_value(head, "ref", "pull_request_lifecycle.head_identity")?,
        "head_repo_owner": required_value(head, "repo_owner", "pull_request_lifecycle.head_identity")?,
        "head_repo_name": required_value(head, "repo_name", "pull_request_lifecycle.head_identity")?,
        "post_merge_base_ref_sha": post_merge_base_ref_sha,
        "merge_cas_base_sha": merge_cas_base_sha,
        "merge_cas_base_tree_sha": merge_cas_base_tree_sha,
        "head_sha": head_sha,
        "merge_commit_sha": merge_commit_sha,
        "merge_tree_sha": merge_tree_sha,
    });
    let pr_identity_bytes =
        canonical_json_bytes(&pr_identity).map_err(LifecycleContractError::from)?;
    let readback_digest_hex = Sha256::digest(pr_identity_bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let authoritative_readback_digest = format!("sha256:{readback_digest_hex}");
    let publication_evidence_ref = format!("evidence:{readback_digest_hex}");

    let mut binding = lifecycle_binding.clone();
    binding.insert(
        "evidence_ref".to_owned(),
        JsonValue::String(publication_evidence_ref.clone()),
    );
    binding.insert(
        "evidence_digest".to_owned(),
        JsonValue::String(authoritative_readback_digest.clone()),
    );
    let binding = JsonValue::Object(binding);
    let identity = binding_identity(&binding)?;
    let predecessor_evidence_id =
        required_value(lifecycle_binding, "evidence_ref", "binding")?.clone();
    let rebind_receipt_evidence_id = required_value(
        cas_map,
        "rebind_receipt_evidence_id",
        "candidate_cas_receipt",
    )?
    .clone();
    let key = serde_json::json!({
        "binding_identity": [
            identity.transaction_id,
            identity.snapshot_id,
            identity.candidate_sha,
            identity.tree_sha,
            identity.input_digest,
            identity.tool_id,
            identity.tool_version,
        ],
        "predecessor_evidence_id": predecessor_evidence_id,
        "rebind_receipt_evidence_id": rebind_receipt_evidence_id,
        "candidate_identity": candidate,
        "pr_identity": pr_identity,
        "publication_evidence_ref": publication_evidence_ref,
        "authoritative_readback_digest": authoritative_readback_digest,
    });
    let key_bytes = canonical_json_bytes(&key).map_err(LifecycleContractError::from)?;
    let receipt_id_hex = Sha256::digest(key_bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let receipt = serde_json::json!({
        "schema": PUBLICATION_READBACK_SCHEMA,
        "readback_receipt_id": format!("publication-readback:{receipt_id_hex}"),
        "binding": binding,
        "predecessor_evidence_id": predecessor_evidence_id,
        "rebind_receipt_evidence_id": rebind_receipt_evidence_id,
        "candidate_identity": candidate,
        "pr_identity": pr_identity,
        "publication_evidence_ref": publication_evidence_ref,
        "authoritative_readback_digest": authoritative_readback_digest,
        "readback_stage": "publication_readback",
    });
    validate_publication_readback_transition(&cas, &lifecycle, &receipt)
}

pub fn source_publication_identity(value: &JsonValue) -> Result<JsonValue, LifecycleContractError> {
    let readback = validate_publication_readback_receipt(value)?;
    let readback_map = mapping(&readback, "publication_readback_receipt")?;
    let pr = mapping(
        required_value(readback_map, "pr_identity", "publication_readback_receipt")?,
        "publication_readback_receipt.pr_identity",
    )?;
    let mut identity = JsonMap::new();
    for (field, source, parent) in [
        (
            "readback_receipt_id",
            readback_map,
            "publication_readback_receipt",
        ),
        (
            "merge_commit_sha",
            pr,
            "publication_readback_receipt.pr_identity",
        ),
        (
            "merge_tree_sha",
            pr,
            "publication_readback_receipt.pr_identity",
        ),
        (
            "publication_evidence_ref",
            readback_map,
            "publication_readback_receipt",
        ),
    ] {
        identity.insert(
            field.to_owned(),
            required_value(source, field, parent)?.clone(),
        );
    }
    Ok(JsonValue::Object(identity))
}

fn validate_source_publication_identity(
    value: &JsonValue,
    field: &str,
) -> Result<JsonValue, LifecycleContractError> {
    let identity = mapping(value, field)?;
    exact_keys(
        identity,
        &[
            "readback_receipt_id",
            "merge_commit_sha",
            "merge_tree_sha",
            "publication_evidence_ref",
        ],
        &[],
        field,
    )?;
    let readback_id = pattern_value(
        required_value(identity, "readback_receipt_id", field)?,
        &format!("{field}.readback_receipt_id"),
        valid_hash_id,
    )?;
    if !readback_id.starts_with("publication-readback:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            &format!("{field}.readback_receipt_id"),
        ));
    }
    for key in ["merge_commit_sha", "merge_tree_sha"] {
        pattern_value(
            required_value(identity, key, field)?,
            &format!("{field}.{key}"),
            |text| lower_hex(text, 40),
        )?;
    }
    pattern_value(
        required_value(identity, "publication_evidence_ref", field)?,
        &format!("{field}.publication_evidence_ref"),
        valid_evidence_ref,
    )?;
    canonical_clone(value)
}

pub fn queue_once_key(
    source_namespace: &str,
    binding: &JsonValue,
    publication_identity: &JsonValue,
) -> Result<String, LifecycleContractError> {
    let checked_binding = validate_record_binding(binding)?;
    let publication = validate_source_publication_identity(
        publication_identity,
        "queue_once_key.publication_identity",
    )?;
    let binding = mapping(&checked_binding, "binding")?;
    let publication = mapping(&publication, "queue_once_key.publication_identity")?;
    let body = format!(
        "{}|{}|{}|{}|{}|{}",
        source_namespace,
        required_string(binding, "candidate_sha", "binding")?,
        required_string(binding, "tree_sha", "binding")?,
        required_string(binding, "input_digest", "binding")?,
        required_string(
            publication,
            "merge_commit_sha",
            "queue_once_key.publication_identity",
        )?,
        required_string(
            publication,
            "merge_tree_sha",
            "queue_once_key.publication_identity",
        )?,
    );
    let digest = Sha256::digest(body.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    Ok(format!("queue-key:{digest}"))
}

pub fn validate_queue_receipt(value: &JsonValue) -> Result<JsonValue, LifecycleContractError> {
    let receipt = mapping(value, "queue_receipt")?;
    let fields = [
        "schema",
        "queue_receipt_id",
        "binding",
        "source_namespace",
        "source_main_rebind_receipt_id",
        "source_main_readback_evidence_ref",
        "source_publication_identity",
        "enqueue_once_key",
        "state",
    ];
    exact_keys(receipt, &fields, &[], "queue_receipt")?;
    if receipt.get("schema").and_then(JsonValue::as_str) != Some(QUEUE_RECEIPT_SCHEMA) {
        return Err(fail("lifecycle:schema_invalid", QUEUE_RECEIPT_SCHEMA));
    }
    let queue_id = pattern_value(
        required_value(receipt, "queue_receipt_id", "queue_receipt")?,
        "queue_receipt.queue_receipt_id",
        valid_hash_id,
    )?;
    if !queue_id.starts_with("queue:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            "queue_receipt.queue_receipt_id",
        ));
    }
    let binding = validate_record_binding(required_value(receipt, "binding", "queue_receipt")?)?;
    let source_namespace = string_value(
        required_value(receipt, "source_namespace", "queue_receipt")?,
        "queue_receipt.source_namespace",
    )?;
    if !Path::new(&source_namespace).is_absolute() {
        return Err(fail(
            "lifecycle:path_not_absolute",
            "queue_receipt.source_namespace",
        ));
    }
    let rebind_id = pattern_value(
        required_value(receipt, "source_main_rebind_receipt_id", "queue_receipt")?,
        "queue_receipt.source_main_rebind_receipt_id",
        valid_hash_id,
    )?;
    if !rebind_id.starts_with("rebind:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            "queue_receipt.source_main_rebind_receipt_id",
        ));
    }
    pattern_value(
        required_value(
            receipt,
            "source_main_readback_evidence_ref",
            "queue_receipt",
        )?,
        "queue_receipt.source_main_readback_evidence_ref",
        valid_evidence_ref,
    )?;
    let publication = validate_source_publication_identity(
        required_value(receipt, "source_publication_identity", "queue_receipt")?,
        "queue_receipt.source_publication_identity",
    )?;
    let expected_key = queue_once_key(&source_namespace, &binding, &publication)?;
    if required_value(receipt, "enqueue_once_key", "queue_receipt")?.as_str()
        != Some(expected_key.as_str())
    {
        return Err(fail("lifecycle:queue_key_mismatch", ""));
    }
    one_of(
        required_value(receipt, "state", "queue_receipt")?,
        &["accepted", "retry_pending", "failed"],
        "queue_receipt.state",
    )?;
    canonical_clone(value)
}

pub fn materialize_queue_receipt(
    binding: &JsonValue,
    source_namespace: &str,
    source_main_rebind_receipt_id: &str,
    source_main_readback_evidence_ref: &str,
    publication_readback_receipt: &JsonValue,
    state: &str,
) -> Result<JsonValue, LifecycleContractError> {
    let checked_binding = validate_record_binding(binding)?;
    let publication = source_publication_identity(publication_readback_receipt)?;
    let enqueue_once_key = queue_once_key(source_namespace, &checked_binding, &publication)?;
    let receipt_digest = Sha256::digest(enqueue_once_key.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let receipt = serde_json::json!({
        "schema": QUEUE_RECEIPT_SCHEMA,
        "queue_receipt_id": format!("queue:{receipt_digest}"),
        "binding": checked_binding,
        "source_namespace": source_namespace,
        "source_main_rebind_receipt_id": source_main_rebind_receipt_id,
        "source_main_readback_evidence_ref": source_main_readback_evidence_ref,
        "source_publication_identity": publication,
        "enqueue_once_key": enqueue_once_key,
        "state": state,
    });
    validate_queue_receipt(&receipt)
}

fn immutable_replay_record(
    value: &JsonValue,
    field: &str,
) -> Result<JsonValue, LifecycleContractError> {
    mapping(value, field)?;
    let mut cloned = canonical_clone(value)?;
    let mut binding = {
        let record = mapping(&cloned, field)?;
        mapping(
            record.get("binding").unwrap_or(&JsonValue::Null),
            &format!("{field}.binding"),
        )?
        .clone()
    };
    binding.remove("timing");
    let record = cloned
        .as_object_mut()
        .ok_or_else(|| fail("lifecycle:mapping_required", field))?;
    record.insert("binding".to_owned(), JsonValue::Object(binding));
    Ok(cloned)
}

pub fn validate_immutable_replay(
    existing: &JsonValue,
    requested: &JsonValue,
    field: &str,
) -> Result<(), LifecycleContractError> {
    let existing = immutable_replay_record(existing, field)?;
    let requested = immutable_replay_record(requested, field)?;
    if !python_json_equal_after_float_rejection(&existing, &requested) {
        return Err(fail("input_identity_mismatch", field));
    }
    Ok(())
}

pub fn frontier_key(
    source_namespace: &str,
    binding: &JsonValue,
    publication_identity: &JsonValue,
) -> Result<String, LifecycleContractError> {
    let checked_binding = validate_record_binding(binding)?;
    let publication = validate_source_publication_identity(
        publication_identity,
        "frontier_key.publication_identity",
    )?;
    let binding_map = mapping(&checked_binding, "binding")?;
    let publication_map = mapping(&publication, "frontier_key.publication_identity")?;
    let body = format!(
        "{}|{}|{}|{}|{}|{}",
        source_namespace,
        required_string(binding_map, "candidate_sha", "binding")?,
        required_string(binding_map, "tree_sha", "binding")?,
        required_string(binding_map, "input_digest", "binding")?,
        required_string(
            publication_map,
            "merge_commit_sha",
            "frontier_key.publication_identity",
        )?,
        required_string(
            publication_map,
            "merge_tree_sha",
            "frontier_key.publication_identity",
        )?,
    );
    let digest = Sha256::digest(body.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    Ok(format!("frontier-key:{digest}"))
}

pub fn validate_dependency_frontier(
    value: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let frontier = mapping(value, "dependency_frontier")?;
    let fields = [
        "schema",
        "frontier_id",
        "binding",
        "frontier_state",
        "queue_receipt_id",
        "source_namespace",
        "source_main_rebind_receipt_id",
        "source_main_rebind_evidence_ref",
        "source_main_readback_evidence_ref",
        "source_publication_identity",
        "ordered_predecessor_evidence",
        "frontier_key",
        "preceding_frontier_evidence_id",
        "acceptance_evidence_ref",
        "parent_projection_evidence_ref",
    ];
    exact_keys(frontier, &fields, &[], "dependency_frontier")?;
    if frontier.get("schema").and_then(JsonValue::as_str) != Some(DEPENDENCY_FRONTIER_SCHEMA) {
        return Err(fail("lifecycle:schema_invalid", DEPENDENCY_FRONTIER_SCHEMA));
    }
    let frontier_id = pattern_value(
        required_value(frontier, "frontier_id", "dependency_frontier")?,
        "dependency_frontier.frontier_id",
        valid_hash_id,
    )?;
    if !frontier_id.starts_with("frontier:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            "dependency_frontier.frontier_id",
        ));
    }
    let binding =
        validate_record_binding(required_value(frontier, "binding", "dependency_frontier")?)?;
    let state = one_of(
        required_value(frontier, "frontier_state", "dependency_frontier")?,
        &["pending", "accepted", "failed"],
        "dependency_frontier.frontier_state",
    )?;
    let queue_id = pattern_value(
        required_value(frontier, "queue_receipt_id", "dependency_frontier")?,
        "dependency_frontier.queue_receipt_id",
        valid_hash_id,
    )?;
    if !queue_id.starts_with("queue:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            "dependency_frontier.queue_receipt_id",
        ));
    }
    let source_namespace = string_value(
        required_value(frontier, "source_namespace", "dependency_frontier")?,
        "dependency_frontier.source_namespace",
    )?;
    if !Path::new(&source_namespace).is_absolute() {
        return Err(fail(
            "lifecycle:path_not_absolute",
            "dependency_frontier.source_namespace",
        ));
    }
    let rebind_id = pattern_value(
        required_value(
            frontier,
            "source_main_rebind_receipt_id",
            "dependency_frontier",
        )?,
        "dependency_frontier.source_main_rebind_receipt_id",
        valid_hash_id,
    )?;
    if !rebind_id.starts_with("rebind:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            "dependency_frontier.source_main_rebind_receipt_id",
        ));
    }
    pattern_value(
        required_value(
            frontier,
            "source_main_rebind_evidence_ref",
            "dependency_frontier",
        )?,
        "dependency_frontier.source_main_rebind_evidence_ref",
        valid_evidence_ref,
    )?;
    pattern_value(
        required_value(
            frontier,
            "source_main_readback_evidence_ref",
            "dependency_frontier",
        )?,
        "dependency_frontier.source_main_readback_evidence_ref",
        valid_evidence_ref,
    )?;
    let publication = validate_source_publication_identity(
        required_value(
            frontier,
            "source_publication_identity",
            "dependency_frontier",
        )?,
        "dependency_frontier.source_publication_identity",
    )?;
    let predecessors_field = "dependency_frontier.ordered_predecessor_evidence";
    let predecessors = required_value(
        frontier,
        "ordered_predecessor_evidence",
        "dependency_frontier",
    )?
    .as_array()
    .ok_or_else(|| fail("lifecycle:sequence_required", predecessors_field))?;
    if predecessors.len() != 2 {
        return Err(fail("frontier:predecessor_order_invalid", ""));
    }
    for (index, (item, (queue_number, source_pr))) in predecessors
        .iter()
        .zip([(388_u16, "#388"), (389_u16, "#389")])
        .enumerate()
    {
        let item_field = format!("{predecessors_field}[{index}]");
        let record = mapping(item, &item_field)?;
        let required = ["queue_number", "source_pr", "publication_evidence_id"];
        let optional: &[&str] = if queue_number == 389 {
            &["source_pr_sha"]
        } else {
            &[]
        };
        exact_keys(record, &required, optional, &item_field)?;
        if !frontier_queue_number_matches(
            required_value(record, "queue_number", &item_field)?,
            queue_number,
        ) || required_value(record, "source_pr", &item_field)?.as_str() != Some(source_pr)
        {
            return Err(fail("frontier:predecessor_order_invalid", ""));
        }
        pattern_value(
            required_value(record, "publication_evidence_id", &item_field)?,
            &format!("{item_field}.publication_evidence_id"),
            valid_evidence_ref,
        )?;
        if queue_number == 389 {
            pattern_value(
                record.get("source_pr_sha").unwrap_or(&JsonValue::Null),
                "dependency_frontier.ordered_predecessor_evidence[1].source_pr_sha",
                |text| lower_hex(text, 40),
            )?;
        }
    }
    let expected_key = frontier_key(&source_namespace, &binding, &publication)?;
    if required_value(frontier, "frontier_key", "dependency_frontier")?.as_str()
        != Some(expected_key.as_str())
    {
        return Err(fail("frontier:key_mismatch", ""));
    }
    let preceding = required_value(
        frontier,
        "preceding_frontier_evidence_id",
        "dependency_frontier",
    )?;
    let acceptance = required_value(frontier, "acceptance_evidence_ref", "dependency_frontier")?;
    match state.as_str() {
        "pending" if !acceptance.is_null() || !preceding.is_null() => {
            return Err(fail("frontier:pending_evidence_forbidden", ""));
        }
        "accepted" => {
            pattern_value(
                acceptance,
                "dependency_frontier.acceptance_evidence_ref",
                valid_evidence_ref,
            )?;
            pattern_value(
                preceding,
                "dependency_frontier.preceding_frontier_evidence_id",
                valid_evidence_ref,
            )?;
        }
        "failed" if !acceptance.is_null() => {
            pattern_value(
                acceptance,
                "dependency_frontier.acceptance_evidence_ref",
                valid_evidence_ref,
            )?;
        }
        _ => {}
    }
    if !required_value(
        frontier,
        "parent_projection_evidence_ref",
        "dependency_frontier",
    )?
    .is_null()
    {
        return Err(fail("frontier:parent_projection_before_acceptance", ""));
    }
    canonical_clone(value)
}

pub fn materialize_dependency_frontier(
    binding: &JsonValue,
    queue_receipt: &JsonValue,
    rebind_receipt: &JsonValue,
    source_main_readback_evidence_ref: &str,
    ordered_predecessor_evidence: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let checked_binding = validate_record_binding(binding)?;
    let queue = validate_queue_receipt(queue_receipt)?;
    let rebind = validate_source_main_rebind_receipt(rebind_receipt)?;
    let queue_map = mapping(&queue, "queue_receipt")?;
    let rebind_map = mapping(&rebind, "source_main_rebind_receipt")?;
    same_binding(
        &checked_binding,
        required_value(queue_map, "binding", "queue_receipt")?,
        "dependency_frontier.queue",
    )?;
    same_binding(
        &checked_binding,
        required_value(rebind_map, "binding", "source_main_rebind_receipt")?,
        "dependency_frontier.rebind",
    )?;
    if required_string(queue_map, "state", "queue_receipt")? != "accepted" {
        return Err(fail("frontier:queue_not_accepted", ""));
    }
    if required_value(queue_map, "source_main_rebind_receipt_id", "queue_receipt")?
        != required_value(
            rebind_map,
            "rebind_receipt_id",
            "source_main_rebind_receipt",
        )?
    {
        return Err(fail("frontier:rebind_mismatch", ""));
    }
    let publication = validate_source_publication_identity(
        required_value(queue_map, "source_publication_identity", "queue_receipt")?,
        "dependency_frontier.queue.source_publication_identity",
    )?;
    let source_namespace = required_string(queue_map, "source_namespace", "queue_receipt")?;
    let key = frontier_key(&source_namespace, &checked_binding, &publication)?;
    let frontier_id_hex = Sha256::digest(key.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let rebind_binding = mapping(
        required_value(rebind_map, "binding", "source_main_rebind_receipt")?,
        "binding",
    )?;
    let frontier = serde_json::json!({
        "schema": DEPENDENCY_FRONTIER_SCHEMA,
        "frontier_id": format!("frontier:{frontier_id_hex}"),
        "binding": checked_binding,
        "frontier_state": "pending",
        "queue_receipt_id": required_value(queue_map, "queue_receipt_id", "queue_receipt")?,
        "source_namespace": source_namespace,
        "source_main_rebind_receipt_id": required_value(rebind_map, "rebind_receipt_id", "source_main_rebind_receipt")?,
        "source_main_rebind_evidence_ref": required_value(rebind_binding, "evidence_ref", "binding")?,
        "source_main_readback_evidence_ref": source_main_readback_evidence_ref,
        "source_publication_identity": publication,
        "ordered_predecessor_evidence": ordered_predecessor_evidence,
        "frontier_key": key,
        "preceding_frontier_evidence_id": null,
        "acceptance_evidence_ref": null,
        "parent_projection_evidence_ref": null,
    });
    validate_dependency_frontier(&frontier)
}

pub fn validate_dependency_frontier_transition(
    pending: &JsonValue,
    accepted: &JsonValue,
    queue_receipt: &JsonValue,
    rebind_receipt: &JsonValue,
    origin_main_readback: &SourceMainReadbackIdentity,
    ordered_oracle: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let before = validate_dependency_frontier(pending)?;
    let after = validate_dependency_frontier(accepted)?;
    let queue = validate_queue_receipt(queue_receipt)?;
    let rebind = validate_source_main_rebind_receipt(rebind_receipt)?;
    let before_map = mapping(&before, "dependency_frontier")?;
    let after_map = mapping(&after, "dependency_frontier")?;
    let queue_map = mapping(&queue, "queue_receipt")?;
    let rebind_map = mapping(&rebind, "source_main_rebind_receipt")?;
    if required_string(before_map, "frontier_state", "dependency_frontier")? != "pending"
        || required_string(after_map, "frontier_state", "dependency_frontier")? != "accepted"
    {
        return Err(fail("frontier:transition_invalid", ""));
    }
    same_binding(
        required_value(before_map, "binding", "dependency_frontier")?,
        required_value(after_map, "binding", "dependency_frontier")?,
        "dependency_frontier",
    )?;
    for field in [
        "frontier_id",
        "queue_receipt_id",
        "source_namespace",
        "source_main_rebind_receipt_id",
        "source_main_rebind_evidence_ref",
        "source_main_readback_evidence_ref",
        "source_publication_identity",
        "ordered_predecessor_evidence",
        "frontier_key",
        "parent_projection_evidence_ref",
    ] {
        if required_value(before_map, field, "dependency_frontier")?
            != required_value(after_map, field, "dependency_frontier")?
        {
            return Err(fail("frontier:immutable_field_changed", field));
        }
    }
    let before_binding = mapping(
        required_value(before_map, "binding", "dependency_frontier")?,
        "binding",
    )?;
    if required_value(
        after_map,
        "preceding_frontier_evidence_id",
        "dependency_frontier",
    )? != required_value(before_binding, "evidence_ref", "binding")?
    {
        return Err(fail("frontier:preceding_evidence_mismatch", ""));
    }
    if required_string(queue_map, "state", "queue_receipt")? != "accepted"
        || required_value(queue_map, "queue_receipt_id", "queue_receipt")?
            != required_value(after_map, "queue_receipt_id", "dependency_frontier")?
    {
        return Err(fail("frontier:queue_not_accepted", ""));
    }
    same_binding(
        required_value(queue_map, "binding", "queue_receipt")?,
        required_value(after_map, "binding", "dependency_frontier")?,
        "dependency_frontier.queue",
    )?;
    if required_value(
        rebind_map,
        "rebind_receipt_id",
        "source_main_rebind_receipt",
    )? != required_value(
        after_map,
        "source_main_rebind_receipt_id",
        "dependency_frontier",
    )? {
        return Err(fail("frontier:rebind_mismatch", ""));
    }
    let rebind_binding = mapping(
        required_value(rebind_map, "binding", "source_main_rebind_receipt")?,
        "binding",
    )?;
    if required_value(rebind_binding, "evidence_ref", "binding")?
        != required_value(
            after_map,
            "source_main_rebind_evidence_ref",
            "dependency_frontier",
        )?
    {
        return Err(fail("frontier:rebind_evidence_mismatch", ""));
    }
    let publication = mapping(
        required_value(
            after_map,
            "source_publication_identity",
            "dependency_frontier",
        )?,
        "dependency_frontier.source_publication_identity",
    )?;
    let origin_main_commit_sha = pattern_value(
        &JsonValue::String(origin_main_readback.commit_sha.clone()),
        "dependency_frontier.origin_main_readback.commit_sha",
        |text| lower_hex(text, 40),
    )?;
    let origin_main_tree_sha = pattern_value(
        &JsonValue::String(origin_main_readback.tree_sha.clone()),
        "dependency_frontier.origin_main_readback.tree_sha",
        |text| lower_hex(text, 40),
    )?;
    if required_string(
        publication,
        "merge_commit_sha",
        "dependency_frontier.source_publication_identity",
    )? != origin_main_commit_sha
        || required_string(
            publication,
            "merge_tree_sha",
            "dependency_frontier.source_publication_identity",
        )? != origin_main_tree_sha
    {
        return Err(fail("frontier:origin_main_readback_mismatch", ""));
    }
    let transaction_id = after_binding_transaction(&after)?;
    let expected_oracle = serde_json::json!([
        "source_pr:#388",
        "source_pr:#389",
        format!("transaction:{transaction_id}"),
    ]);
    if ordered_oracle != &expected_oracle {
        return Err(fail("frontier:ordered_oracle_mismatch", ""));
    }
    Ok(after)
}

pub fn after_binding_transaction(frontier: &JsonValue) -> Result<String, LifecycleContractError> {
    let frontier = mapping(frontier, "dependency_frontier")?;
    let binding = mapping(
        required_value(frontier, "binding", "dependency_frontier")?,
        "dependency_frontier.binding",
    )?;
    required_string(binding, "transaction_id", "dependency_frontier.binding")
}

pub fn validate_durable_handback(value: &JsonValue) -> Result<JsonValue, LifecycleContractError> {
    let handback = mapping(value, "durable_handback")?;
    exact_keys(
        handback,
        &[
            "schema",
            "binding",
            "agent_id",
            "descendant_ids",
            "reservation_ids",
            "evidence_ref",
            "state",
        ],
        &[],
        "durable_handback",
    )?;
    if handback.get("schema").and_then(JsonValue::as_str) != Some(DURABLE_HANDBACK_SCHEMA) {
        return Err(fail("lifecycle:schema_invalid", DURABLE_HANDBACK_SCHEMA));
    }
    validate_record_binding(required_value(handback, "binding", "durable_handback")?)?;
    let agent_id = string_value(
        required_value(handback, "agent_id", "durable_handback")?,
        "durable_handback.agent_id",
    )?;
    if !agent_id.starts_with("agent:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            "durable_handback.agent_id",
        ));
    }
    let descendants = string_list(
        required_value(handback, "descendant_ids", "durable_handback")?,
        "durable_handback.descendant_ids",
        false,
        true,
        None,
    )?;
    let reservations = string_list(
        required_value(handback, "reservation_ids", "durable_handback")?,
        "durable_handback.reservation_ids",
        false,
        true,
        None,
    )?;
    if descendants.iter().any(|item| !item.starts_with("agent:")) {
        return Err(fail(
            "lifecycle:identity_invalid",
            "durable_handback.descendant_ids",
        ));
    }
    if reservations
        .iter()
        .any(|item| !item.starts_with("reservation:"))
    {
        return Err(fail(
            "lifecycle:identity_invalid",
            "durable_handback.reservation_ids",
        ));
    }
    pattern_value(
        required_value(handback, "evidence_ref", "durable_handback")?,
        "durable_handback.evidence_ref",
        valid_evidence_ref,
    )?;
    if required_value(handback, "state", "durable_handback")?.as_str() != Some("durable_handback") {
        return Err(fail("lifecycle:state_invalid", "durable_handback"));
    }
    canonical_clone(value)
}

pub fn validate_descendant_close_receipt(
    value: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let receipt = mapping(value, "descendant_close_receipt")?;
    exact_keys(
        receipt,
        &[
            "schema",
            "binding",
            "agent_id",
            "state",
            "durable_handback_evidence_ref",
            "evidence_ref",
        ],
        &[],
        "descendant_close_receipt",
    )?;
    if receipt.get("schema").and_then(JsonValue::as_str) != Some(DESCENDANT_CLOSE_RECEIPT_SCHEMA) {
        return Err(fail(
            "lifecycle:schema_invalid",
            DESCENDANT_CLOSE_RECEIPT_SCHEMA,
        ));
    }
    validate_record_binding(required_value(
        receipt,
        "binding",
        "descendant_close_receipt",
    )?)?;
    let agent_id = string_value(
        required_value(receipt, "agent_id", "descendant_close_receipt")?,
        "descendant_close_receipt.agent_id",
    )?;
    if !agent_id.starts_with("agent:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            "descendant_close_receipt.agent_id",
        ));
    }
    if required_value(receipt, "state", "descendant_close_receipt")?.as_str() != Some("closed") {
        return Err(fail("close_agent:descendant_not_closed", ""));
    }
    pattern_value(
        required_value(
            receipt,
            "durable_handback_evidence_ref",
            "descendant_close_receipt",
        )?,
        "descendant_close_receipt.durable_handback_evidence_ref",
        valid_evidence_ref,
    )?;
    pattern_value(
        required_value(receipt, "evidence_ref", "descendant_close_receipt")?,
        "descendant_close_receipt.evidence_ref",
        valid_evidence_ref,
    )?;
    canonical_clone(value)
}

pub fn materialize_descendant_close_receipt(
    binding: &JsonValue,
    durable_handback: &JsonValue,
    agent_id: &str,
    evidence_ref: &str,
) -> Result<JsonValue, LifecycleContractError> {
    let checked_binding = validate_record_binding(binding)?;
    let handback = validate_durable_handback(durable_handback)?;
    let handback_map = mapping(&handback, "durable_handback")?;
    same_binding(
        &checked_binding,
        required_value(handback_map, "binding", "durable_handback")?,
        "descendant_close",
    )?;
    let descendants = required_value(handback_map, "descendant_ids", "durable_handback")?
        .as_array()
        .expect("validated handback descendant IDs are a sequence");
    if !descendants.contains(&JsonValue::String(agent_id.to_owned())) {
        return Err(fail("close_agent:unknown_descendant", ""));
    }
    let receipt = serde_json::json!({
        "schema": DESCENDANT_CLOSE_RECEIPT_SCHEMA,
        "binding": checked_binding,
        "agent_id": agent_id,
        "state": "closed",
        "durable_handback_evidence_ref": required_value(handback_map, "evidence_ref", "durable_handback")?,
        "evidence_ref": evidence_ref,
    });
    validate_descendant_close_receipt(&receipt)
}

pub fn validate_reservation_release_receipt(
    value: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let receipt = mapping(value, "reservation_release_receipt")?;
    exact_keys(
        receipt,
        &[
            "schema",
            "binding",
            "reservation_id",
            "state",
            "durable_handback_evidence_ref",
            "evidence_ref",
        ],
        &[],
        "reservation_release_receipt",
    )?;
    if receipt.get("schema").and_then(JsonValue::as_str) != Some(RESERVATION_RELEASE_RECEIPT_SCHEMA)
    {
        return Err(fail(
            "lifecycle:schema_invalid",
            RESERVATION_RELEASE_RECEIPT_SCHEMA,
        ));
    }
    validate_record_binding(required_value(
        receipt,
        "binding",
        "reservation_release_receipt",
    )?)?;
    let reservation_id = string_value(
        required_value(receipt, "reservation_id", "reservation_release_receipt")?,
        "reservation_release_receipt.reservation_id",
    )?;
    if !reservation_id.starts_with("reservation:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            "reservation_release_receipt.reservation_id",
        ));
    }
    if required_value(receipt, "state", "reservation_release_receipt")?.as_str() != Some("released")
    {
        return Err(fail("close_agent:reservation_leak", ""));
    }
    pattern_value(
        required_value(
            receipt,
            "durable_handback_evidence_ref",
            "reservation_release_receipt",
        )?,
        "reservation_release_receipt.durable_handback_evidence_ref",
        valid_evidence_ref,
    )?;
    pattern_value(
        required_value(receipt, "evidence_ref", "reservation_release_receipt")?,
        "reservation_release_receipt.evidence_ref",
        valid_evidence_ref,
    )?;
    canonical_clone(value)
}

pub fn materialize_reservation_release_receipt(
    binding: &JsonValue,
    durable_handback: &JsonValue,
    reservation_id: &str,
    evidence_ref: &str,
) -> Result<JsonValue, LifecycleContractError> {
    let checked_binding = validate_record_binding(binding)?;
    let handback = validate_durable_handback(durable_handback)?;
    let handback_map = mapping(&handback, "durable_handback")?;
    same_binding(
        &checked_binding,
        required_value(handback_map, "binding", "durable_handback")?,
        "reservation_release",
    )?;
    let reservations = required_value(handback_map, "reservation_ids", "durable_handback")?
        .as_array()
        .expect("validated handback reservation IDs are a sequence");
    if !reservations.contains(&JsonValue::String(reservation_id.to_owned())) {
        return Err(fail("close_agent:reservation_leak", ""));
    }
    let receipt = serde_json::json!({
        "schema": RESERVATION_RELEASE_RECEIPT_SCHEMA,
        "binding": checked_binding,
        "reservation_id": reservation_id,
        "state": "released",
        "durable_handback_evidence_ref": required_value(handback_map, "evidence_ref", "durable_handback")?,
        "evidence_ref": evidence_ref,
    });
    validate_reservation_release_receipt(&receipt)
}

pub fn validate_cleanup_proof(value: &JsonValue) -> Result<JsonValue, LifecycleContractError> {
    let proof = mapping(value, "cleanup_proof")?;
    exact_keys(
        proof,
        &[
            "schema",
            "binding",
            "remote_readback_evidence_ref",
            "task_owned_paths",
            "task_owned_state_before",
            "task_owned_state_after",
            "cleaned_paths",
            "unknown_shared_state_before_digest",
            "unknown_shared_state_after_digest",
            "unknown_shared_state_unchanged_evidence_ref",
            "evidence_ref",
            "state",
        ],
        &[],
        "cleanup_proof",
    )?;
    if proof.get("schema").and_then(JsonValue::as_str) != Some(CLEANUP_PROOF_SCHEMA) {
        return Err(fail("lifecycle:schema_invalid", CLEANUP_PROOF_SCHEMA));
    }
    validate_record_binding(required_value(proof, "binding", "cleanup_proof")?)?;
    pattern_value(
        required_value(proof, "remote_readback_evidence_ref", "cleanup_proof")?,
        "cleanup_proof.remote_readback_evidence_ref",
        valid_evidence_ref,
    )?;
    let owned_paths = string_list(
        required_value(proof, "task_owned_paths", "cleanup_proof")?,
        "cleanup_proof.task_owned_paths",
        false,
        true,
        None,
    )?;
    let cleaned_paths = string_list(
        required_value(proof, "cleaned_paths", "cleanup_proof")?,
        "cleanup_proof.cleaned_paths",
        false,
        true,
        None,
    )?;
    if owned_paths
        .iter()
        .chain(&cleaned_paths)
        .any(|path| !Path::new(path).is_absolute())
    {
        return Err(fail("lifecycle:path_not_absolute", "cleanup_proof"));
    }
    let owned_path_set = owned_paths.iter().cloned().collect::<BTreeSet<_>>();
    if cleaned_paths
        .iter()
        .any(|path| !owned_path_set.contains(path))
    {
        return Err(fail("cleanup:non_task_owned_path", ""));
    }
    let before = mapping(
        required_value(proof, "task_owned_state_before", "cleanup_proof")?,
        "cleanup_proof.task_owned_state_before",
    )?;
    let after = mapping(
        required_value(proof, "task_owned_state_after", "cleanup_proof")?,
        "cleanup_proof.task_owned_state_after",
    )?;
    let expected_keys = owned_paths
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let before_keys = before.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let after_keys = after.keys().map(String::as_str).collect::<BTreeSet<_>>();
    if before_keys != expected_keys || after_keys != expected_keys {
        return Err(fail("cleanup:task_owned_state_incomplete", ""));
    }
    for path in &owned_paths {
        string_value(
            required_value(before, path, "cleanup_proof.task_owned_state_before")?,
            &format!("cleanup_proof.task_owned_state_before.{path}"),
        )?;
        string_value(
            required_value(after, path, "cleanup_proof.task_owned_state_after")?,
            &format!("cleanup_proof.task_owned_state_after.{path}"),
        )?;
    }
    let before_digest = pattern_value(
        required_value(proof, "unknown_shared_state_before_digest", "cleanup_proof")?,
        "cleanup_proof.unknown_shared_state_before_digest",
        valid_sha256,
    )?;
    let after_digest = pattern_value(
        required_value(proof, "unknown_shared_state_after_digest", "cleanup_proof")?,
        "cleanup_proof.unknown_shared_state_after_digest",
        valid_sha256,
    )?;
    if before_digest != after_digest {
        return Err(fail("cleanup:unknown_shared_state_changed", ""));
    }
    pattern_value(
        required_value(
            proof,
            "unknown_shared_state_unchanged_evidence_ref",
            "cleanup_proof",
        )?,
        "cleanup_proof.unknown_shared_state_unchanged_evidence_ref",
        valid_evidence_ref,
    )?;
    pattern_value(
        required_value(proof, "evidence_ref", "cleanup_proof")?,
        "cleanup_proof.evidence_ref",
        valid_evidence_ref,
    )?;
    if required_value(proof, "state", "cleanup_proof")?.as_str() != Some("cleanup_proven") {
        return Err(fail("lifecycle:state_invalid", "cleanup_proof"));
    }
    canonical_clone(value)
}

fn validate_close_agent_gate_sequence(
    values: &[JsonValue],
    binding: &JsonValue,
) -> Result<Vec<JsonValue>, LifecycleContractError> {
    let gates = match validate_gate_chain(values, Some(GATE_IDS), true) {
        Ok(gates) => gates,
        Err(error)
            if matches!(
                error.code.as_str(),
                "lifecycle:gate_order_invalid" | "lifecycle:gate_sequence_empty"
            ) =>
        {
            return Err(fail("close_agent:all_six_gate_evidence_required", ""));
        }
        Err(error) => return Err(error),
    };
    for gate in &gates {
        let gate = mapping(gate, "gate_verdict")?;
        same_binding(
            binding,
            required_value(gate, "binding", "gate_verdict")?,
            "close_agent.gates",
        )?;
    }
    Ok(gates)
}

fn terminal_guard_boolean_matches(value: &JsonValue, expected: bool) -> bool {
    if let JsonValue::Number(number) = value {
        if number.is_f64() {
            let expected_number = if expected { 1.0 } else { 0.0 };
            return number.as_f64().is_some_and(|number| {
                number.partial_cmp(&expected_number) == Some(std::cmp::Ordering::Equal)
            });
        }
    }
    python_json_equal_after_float_rejection(value, &JsonValue::Bool(expected))
}

fn terminal_guard_matches(guard: &JsonMap<String, JsonValue>) -> bool {
    guard
        .get("all_six_gates_pass")
        .is_some_and(|value| terminal_guard_boolean_matches(value, true))
        && guard.get("lifecycle_state").and_then(JsonValue::as_str) == Some("terminal")
        && guard
            .get("completed_but_open")
            .is_some_and(|value| terminal_guard_boolean_matches(value, false))
        && guard
            .get("unknown_descendants")
            .is_some_and(|value| terminal_guard_boolean_matches(value, false))
        && guard
            .get("reservation_leak")
            .is_some_and(|value| terminal_guard_boolean_matches(value, false))
        && guard
            .get("remote_readback_before_cleanup")
            .is_some_and(|value| terminal_guard_boolean_matches(value, true))
        && guard
            .get("identity_match")
            .is_some_and(|value| terminal_guard_boolean_matches(value, true))
}

pub fn validate_close_agent_tool_call(
    value: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let token = mapping(value, "close_agent_tool_call")?;
    exact_keys(
        token,
        &[
            "schema",
            "binding",
            "tool_id",
            "state",
            "agent_id",
            "args_schema",
            "args",
            "terminal_guard",
            "token_id",
            "token_body_sha256",
        ],
        &[],
        "close_agent_tool_call",
    )?;
    if token.get("schema").and_then(JsonValue::as_str) != Some(CLOSE_AGENT_TOOL_CALL_SCHEMA) {
        return Err(fail(
            "lifecycle:schema_invalid",
            CLOSE_AGENT_TOOL_CALL_SCHEMA,
        ));
    }
    validate_record_binding(required_value(token, "binding", "close_agent_tool_call")?)?;
    if required_value(token, "tool_id", "close_agent_tool_call")?.as_str() != Some("close_agent") {
        return Err(fail("close_agent:tool_id_invalid", ""));
    }
    if required_value(token, "state", "close_agent_tool_call")?.as_str() != Some("terminal") {
        return Err(fail("close_agent:not_terminal", ""));
    }
    let agent_id = string_value(
        required_value(token, "agent_id", "close_agent_tool_call")?,
        "close_agent_tool_call.agent_id",
    )?;
    if !agent_id.starts_with("agent:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            "close_agent_tool_call.agent_id",
        ));
    }
    if required_value(token, "args_schema", "close_agent_tool_call")?.as_str()
        != Some(CLOSE_AGENT_ARGS_SCHEMA)
    {
        return Err(fail("close_agent:args_schema_invalid", ""));
    }
    let args = mapping(
        required_value(token, "args", "close_agent_tool_call")?,
        "close_agent_tool_call.args",
    )?;
    exact_keys(
        args,
        &[
            "run_id",
            "gate_verdict_evidence_refs",
            "cleanup_proof_evidence_ref",
            "durable_handback_evidence_ref",
            "descendants_closed_evidence_ref",
            "reservations_released_evidence_ref",
        ],
        &[],
        "close_agent_tool_call.args",
    )?;
    string_value(
        required_value(args, "run_id", "close_agent_tool_call.args")?,
        "close_agent_tool_call.args.run_id",
    )?;
    let gate_refs = string_list(
        required_value(
            args,
            "gate_verdict_evidence_refs",
            "close_agent_tool_call.args",
        )?,
        "close_agent_tool_call.args.gate_verdict_evidence_refs",
        true,
        true,
        Some(valid_evidence_ref),
    )?;
    if gate_refs.len() != GATE_IDS.len() {
        return Err(fail("close_agent:all_six_gate_evidence_required", ""));
    }
    for field in [
        "cleanup_proof_evidence_ref",
        "durable_handback_evidence_ref",
        "descendants_closed_evidence_ref",
        "reservations_released_evidence_ref",
    ] {
        pattern_value(
            required_value(args, field, "close_agent_tool_call.args")?,
            &format!("close_agent_tool_call.args.{field}"),
            valid_evidence_ref,
        )?;
    }
    let guard = mapping(
        required_value(token, "terminal_guard", "close_agent_tool_call")?,
        "close_agent_tool_call.terminal_guard",
    )?;
    exact_keys(
        guard,
        &[
            "all_six_gates_pass",
            "lifecycle_state",
            "completed_but_open",
            "unknown_descendants",
            "reservation_leak",
            "remote_readback_before_cleanup",
            "identity_match",
        ],
        &[],
        "close_agent_tool_call.terminal_guard",
    )?;
    if !terminal_guard_matches(guard) {
        if guard.get("completed_but_open").and_then(JsonValue::as_bool) == Some(true) {
            return Err(fail("close_agent:completed_but_open", ""));
        }
        if guard
            .get("unknown_descendants")
            .and_then(JsonValue::as_bool)
            == Some(true)
        {
            return Err(fail("close_agent:unknown_descendant", ""));
        }
        if guard.get("reservation_leak").and_then(JsonValue::as_bool) == Some(true) {
            return Err(fail("close_agent:reservation_leak", ""));
        }
        if guard
            .get("remote_readback_before_cleanup")
            .and_then(JsonValue::as_bool)
            != Some(true)
        {
            return Err(fail("close_agent:cleanup_before_remote_readback", ""));
        }
        return Err(fail("close_agent:terminal_guard_failed", ""));
    }
    let token_id = pattern_value(
        required_value(token, "token_id", "close_agent_tool_call")?,
        "close_agent_tool_call.token_id",
        valid_hash_id,
    )?;
    if !token_id.starts_with("close-token:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            "close_agent_tool_call.token_id",
        ));
    }
    let mut token_id_body = token.clone();
    token_id_body.remove("token_id");
    token_id_body.remove("token_body_sha256");
    let token_id_bytes = canonical_json_bytes(&JsonValue::Object(token_id_body))
        .map_err(LifecycleContractError::from)?;
    let token_id_digest = Sha256::digest(token_id_bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    if token_id != format!("close-token:{token_id_digest}") {
        return Err(fail("close_agent:token_id_mismatch", ""));
    }
    let body_digest =
        canonical_body_sha256(value, "token_body_sha256").map_err(LifecycleContractError::from)?;
    let expected_body = format!("sha256:{body_digest}");
    if required_value(token, "token_body_sha256", "close_agent_tool_call")?.as_str()
        != Some(expected_body.as_str())
    {
        return Err(fail("close_agent:token_body_mismatch", ""));
    }
    canonical_clone(value)
}

pub fn materialize_close_agent_tool_call(
    input: CloseAgentToolCallInput<'_>,
) -> Result<JsonValue, LifecycleContractError> {
    let CloseAgentToolCallInput {
        binding,
        run_id,
        agent_id,
        gate_verdicts,
        cleanup_proof,
        durable_handback,
        descendants_closed_evidence_ref,
        reservations_released_evidence_ref,
        completed_but_open,
        unknown_descendants,
        reservation_leak,
    } = input;
    let checked_binding = validate_record_binding(binding)?;
    let gates = validate_close_agent_gate_sequence(gate_verdicts, &checked_binding)?;
    let proof = validate_cleanup_proof(cleanup_proof)?;
    let handback = validate_durable_handback(durable_handback)?;
    let proof_map = mapping(&proof, "cleanup_proof")?;
    let handback_map = mapping(&handback, "durable_handback")?;
    same_binding(
        &checked_binding,
        required_value(proof_map, "binding", "cleanup_proof")?,
        "close_agent.cleanup_proof",
    )?;
    same_binding(
        &checked_binding,
        required_value(handback_map, "binding", "durable_handback")?,
        "close_agent.durable_handback",
    )?;
    if required_value(proof_map, "remote_readback_evidence_ref", "cleanup_proof")?.is_null() {
        return Err(fail("close_agent:cleanup_before_remote_readback", ""));
    }
    let mut gate_refs = Vec::with_capacity(gates.len());
    for gate in &gates {
        let gate = mapping(gate, "gate_verdict")?;
        let gate_binding = mapping(required_value(gate, "binding", "gate_verdict")?, "binding")?;
        gate_refs.push(required_value(gate_binding, "evidence_ref", "binding")?.clone());
    }
    let record = serde_json::json!({
        "schema": CLOSE_AGENT_TOOL_CALL_SCHEMA,
        "binding": checked_binding,
        "tool_id": "close_agent",
        "state": "terminal",
        "agent_id": agent_id,
        "args_schema": CLOSE_AGENT_ARGS_SCHEMA,
        "args": {
            "run_id": run_id,
            "gate_verdict_evidence_refs": gate_refs,
            "cleanup_proof_evidence_ref": required_value(proof_map, "evidence_ref", "cleanup_proof")?,
            "durable_handback_evidence_ref": required_value(handback_map, "evidence_ref", "durable_handback")?,
            "descendants_closed_evidence_ref": descendants_closed_evidence_ref,
            "reservations_released_evidence_ref": reservations_released_evidence_ref,
        },
        "terminal_guard": {
            "all_six_gates_pass": true,
            "lifecycle_state": "terminal",
            "completed_but_open": completed_but_open,
            "unknown_descendants": unknown_descendants,
            "reservation_leak": reservation_leak,
            "remote_readback_before_cleanup": true,
            "identity_match": true,
        },
    });
    let token_id_bytes = canonical_json_bytes(&record).map_err(LifecycleContractError::from)?;
    let token_id_digest = Sha256::digest(token_id_bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let mut record = mapping(&record, "close_agent_tool_call")?.clone();
    record.insert(
        "token_id".to_owned(),
        JsonValue::String(format!("close-token:{token_id_digest}")),
    );
    let record = JsonValue::Object(record);
    let body_digest = canonical_body_sha256(&record, "token_body_sha256")
        .map_err(LifecycleContractError::from)?;
    let mut record = mapping(&record, "close_agent_tool_call")?.clone();
    record.insert(
        "token_body_sha256".to_owned(),
        JsonValue::String(format!("sha256:{body_digest}")),
    );
    validate_close_agent_tool_call(&JsonValue::Object(record))
}

pub fn guard_transition(
    current_state: &str,
    next_state: &str,
    evidence: &JsonValue,
) -> Result<(), LifecycleContractError> {
    let current_state = one_of(
        &JsonValue::String(current_state.to_owned()),
        TRANSACTION_STATES,
        "transition.current_state",
    )?;
    let next_state = one_of(
        &JsonValue::String(next_state.to_owned()),
        TRANSACTION_STATES,
        "transition.next_state",
    )?;
    if next_state == "failed" || next_state == "successor_required" {
        let required = if next_state == "failed" {
            "failure_code"
        } else {
            "successor_transaction_id"
        };
        string_value(
            evidence
                .as_object()
                .and_then(|record| record.get(required))
                .unwrap_or(&JsonValue::Null),
            &format!("transition.{required}"),
        )?;
        return Ok(());
    }
    let Some(transition) = TRANSACTION_TRANSITIONS.iter().find(|transition| {
        transition.current_state == current_state.as_str()
            && transition.next_state == next_state.as_str()
    }) else {
        return Err(fail(
            "lifecycle:transition_invalid",
            &format!("{current_state}->{next_state}"),
        ));
    };
    let evidence = mapping(evidence, "transition.evidence")?;
    for field in transition.required_evidence {
        if !evidence.contains_key(*field) {
            return Err(fail("lifecycle:transition_evidence_missing", field));
        }
    }
    match (current_state.as_str(), next_state.as_str()) {
        ("generated", "gates_ready") => {
            let Some(gates) = evidence.get("gate_verdicts").and_then(JsonValue::as_array) else {
                return Err(fail("lifecycle:gates_not_ready", ""));
            };
            if let Err(error) = validate_gate_chain(gates, Some(&["G1", "G2"]), true) {
                if error.code.starts_with("artifact_identity:") {
                    return Err(error);
                }
                return Err(fail("lifecycle:gates_not_ready", ""));
            }
        }
        ("reviewed", "pr_open") => {
            let lifecycle = validate_pull_request_lifecycle(
                evidence
                    .get("pr_lifecycle")
                    .expect("required PR lifecycle evidence is present"),
            )?;
            let pr_state = lifecycle.get("state").and_then(JsonValue::as_str);
            if pr_state != Some("ready") && pr_state != Some("external_review") {
                return Err(fail("lifecycle:pr_not_open_ready", ""));
            }
        }
        ("pr_open", "pr_merged") => {
            let lifecycle = validate_pull_request_lifecycle(
                evidence
                    .get("pr_lifecycle")
                    .expect("required PR lifecycle evidence is present"),
            )?;
            if lifecycle.get("state").and_then(JsonValue::as_str) != Some("merged") {
                return Err(fail("lifecycle:pr_not_merged", ""));
            }
        }
        ("source_main_readback", "queue_enqueued") => {
            let queue = validate_queue_receipt(
                evidence
                    .get("queue_receipt")
                    .expect("required queue receipt evidence is present"),
            )?;
            if queue.get("state").and_then(JsonValue::as_str) != Some("accepted") {
                return Err(fail("lifecycle:queue_not_accepted", ""));
            }
        }
        ("queue_enqueued", "frontier_accepted") => {
            let frontier = validate_dependency_frontier(
                evidence
                    .get("dependency_frontier")
                    .expect("required dependency frontier evidence is present"),
            )?;
            if frontier.get("frontier_state").and_then(JsonValue::as_str) != Some("accepted") {
                return Err(fail("lifecycle:frontier_not_accepted", ""));
            }
        }
        ("remote_readback", "durable_handback") => {
            validate_durable_handback(
                evidence
                    .get("durable_handback")
                    .expect("required durable handback evidence is present"),
            )?;
        }
        ("reservations_released", "cleanup_proven") => {
            validate_cleanup_proof(
                evidence
                    .get("cleanup_proof")
                    .expect("required cleanup proof evidence is present"),
            )?;
        }
        ("cleanup_proven", "nested_lifecycle_cleanup") => {
            let Some(gates) = evidence.get("gate_verdicts").and_then(JsonValue::as_array) else {
                return Err(fail(
                    "lifecycle:sequence_required",
                    "transition.gate_verdicts",
                ));
            };
            let gates = gates
                .iter()
                .map(validate_gate_verdict)
                .collect::<Result<Vec<_>, _>>()?;
            let last_gate = gates.last();
            if last_gate
                .and_then(|gate| gate.get("gate_id"))
                .and_then(JsonValue::as_str)
                != Some("G6")
                || last_gate
                    .and_then(|gate| gate.get("verdict"))
                    .and_then(JsonValue::as_str)
                    != Some("pass")
            {
                return Err(fail("lifecycle:g6_not_passed", ""));
            }
            validate_cleanup_proof(
                evidence
                    .get("cleanup_proof")
                    .expect("required cleanup proof evidence is present"),
            )?;
        }
        ("nested_lifecycle_cleanup", "closed") => {
            validate_close_agent_tool_call(
                evidence
                    .get("close_agent_tool_call")
                    .expect("required close-agent token evidence is present"),
            )?;
        }
        _ => {}
    }
    Ok(())
}

fn validate_remote_git_identity(
    value: &JsonValue,
    field: &str,
) -> Result<(String, String, String), LifecycleContractError> {
    let identity = mapping(value, field)?;
    exact_keys(
        identity,
        &["remote", "ref", "commit_sha", "tree_sha"],
        &[],
        field,
    )?;
    let remote = required_string(identity, "remote", field)?;
    let ref_name = required_string(identity, "ref", field)?;
    if !ref_name.starts_with("refs/") {
        return Err(fail("lifecycle:ref_invalid", &format!("{field}.ref")));
    }
    let commit_sha = pattern_value(
        required_value(identity, "commit_sha", field)?,
        &format!("{field}.commit_sha"),
        |value| lower_hex(value, 40),
    )?;
    pattern_value(
        required_value(identity, "tree_sha", field)?,
        &format!("{field}.tree_sha"),
        |value| lower_hex(value, 40),
    )?;
    Ok((remote, ref_name, commit_sha))
}

pub fn validate_source_main_rebind_receipt(
    value: &JsonValue,
) -> Result<JsonValue, LifecycleContractError> {
    let receipt = mapping(value, "source_main_rebind_receipt")?;
    exact_keys(
        receipt,
        &[
            "schema",
            "rebind_receipt_id",
            "binding",
            "input_identity",
            "old_base_identity",
            "new_base_identity",
            "origin_main_readback",
        ],
        &[],
        "source_main_rebind_receipt",
    )?;
    if receipt.get("schema").and_then(JsonValue::as_str) != Some(SOURCE_MAIN_REBIND_SCHEMA) {
        return Err(fail("lifecycle:schema_invalid", SOURCE_MAIN_REBIND_SCHEMA));
    }
    // Like the Python validator, this checks the receipt ID shape but does not recompute it.
    let rebind_id = pattern_value(
        required_value(receipt, "rebind_receipt_id", "source_main_rebind_receipt")?,
        "source_main_rebind_receipt.rebind_receipt_id",
        valid_hash_id,
    )?;
    if !rebind_id.starts_with("rebind:") {
        return Err(fail(
            "lifecycle:identity_invalid",
            "source_main_rebind_receipt.rebind_receipt_id",
        ));
    }

    let binding = validate_record_binding(required_value(
        receipt,
        "binding",
        "source_main_rebind_receipt",
    )?)?;
    let input_identity_field = "source_main_rebind_receipt.input_identity";
    let input_identity = mapping(
        required_value(receipt, "input_identity", "source_main_rebind_receipt")?,
        input_identity_field,
    )?;
    exact_keys(
        input_identity,
        &["tool", "input_digest"],
        &[],
        input_identity_field,
    )?;
    if required_value(input_identity, "tool", input_identity_field)?.as_str() != Some("cmd_latest")
    {
        return Err(fail(
            "lifecycle:tool_id_invalid",
            "source_main_rebind_receipt.input_identity.tool",
        ));
    }
    let input_digest = pattern_value(
        required_value(input_identity, "input_digest", input_identity_field)?,
        "source_main_rebind_receipt.input_identity.input_digest",
        valid_sha256,
    )?;
    let binding_map = mapping(&binding, "binding")?;
    let binding_input_digest = required_string(binding_map, "input_digest", "binding")?;
    if input_digest != binding_input_digest {
        return Err(fail(
            "input_identity_mismatch",
            "source_main_rebind_receipt.input_identity",
        ));
    }

    let (old_remote, old_ref, _) = validate_remote_git_identity(
        required_value(receipt, "old_base_identity", "source_main_rebind_receipt")?,
        "source_main_rebind_receipt.old_base_identity",
    )?;
    let (new_remote, new_ref, new_commit_sha) = validate_remote_git_identity(
        required_value(receipt, "new_base_identity", "source_main_rebind_receipt")?,
        "source_main_rebind_receipt.new_base_identity",
    )?;
    for (field, remote, ref_name) in [
        ("old_base_identity", old_remote.as_str(), old_ref.as_str()),
        ("new_base_identity", new_remote.as_str(), new_ref.as_str()),
    ] {
        if remote != "origin" || ref_name != "refs/heads/main" {
            return Err(fail("lifecycle:source_main_identity_invalid", field));
        }
    }

    let readback_field = "source_main_rebind_receipt.origin_main_readback";
    let readback = mapping(
        required_value(
            receipt,
            "origin_main_readback",
            "source_main_rebind_receipt",
        )?,
        readback_field,
    )?;
    exact_keys(
        readback,
        &["remote", "ref", "commit_sha", "command", "evidence_ref"],
        &[],
        readback_field,
    )?;
    let readback_remote = required_string(readback, "remote", readback_field)?;
    let readback_ref = required_string(readback, "ref", readback_field)?;
    let readback_commit_sha = pattern_value(
        required_value(readback, "commit_sha", readback_field)?,
        "source_main_rebind_receipt.origin_main_readback.commit_sha",
        |value| lower_hex(value, 40),
    )?;
    if required_value(readback, "command", readback_field)?.as_str()
        != Some("git ls-remote origin refs/heads/main")
    {
        return Err(LifecycleContractError::code(
            "lifecycle:readback_command_invalid",
        ));
    }
    pattern_value(
        required_value(readback, "evidence_ref", readback_field)?,
        "source_main_rebind_receipt.origin_main_readback.evidence_ref",
        valid_evidence_ref,
    )?;
    if readback_remote != new_remote
        || readback_ref != new_ref
        || readback_commit_sha != new_commit_sha
    {
        return Err(LifecycleContractError::code(
            "lifecycle:source_main_readback_mismatch",
        ));
    }
    canonical_clone(value)
}

pub fn materialize_source_main_rebind_receipt(
    binding: &JsonValue,
    old_base_identity: &JsonValue,
    new_base_identity: &JsonValue,
    origin_main_readback_evidence_ref: &str,
) -> Result<JsonValue, LifecycleContractError> {
    let checked_binding = validate_record_binding(binding)?;
    let identity = binding_identity_from_validated(&checked_binding)?;
    let old_base = mapping(old_base_identity, "old_base_identity")?;
    let new_base = mapping(new_base_identity, "new_base_identity")?;
    let input_identity = serde_json::json!({
        "tool": "cmd_latest",
        "input_digest": identity.input_digest.clone(),
    });
    let key = serde_json::json!({
        "transaction_id": identity.transaction_id.clone(),
        "snapshot_id": identity.snapshot_id.clone(),
        "input_identity": input_identity.clone(),
        "old_base_identity": JsonValue::Object((*old_base).clone()),
        "new_base_identity": JsonValue::Object((*new_base).clone()),
    });
    let canonical = canonical_json_bytes(&key).map_err(LifecycleContractError::from)?;
    let digest = Sha256::digest(canonical)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let mut readback = JsonMap::new();
    readback.insert(
        "remote".to_owned(),
        required_value(new_base, "remote", "new_base_identity")?.clone(),
    );
    readback.insert(
        "ref".to_owned(),
        required_value(new_base, "ref", "new_base_identity")?.clone(),
    );
    readback.insert(
        "commit_sha".to_owned(),
        required_value(new_base, "commit_sha", "new_base_identity")?.clone(),
    );
    readback.insert(
        "command".to_owned(),
        JsonValue::String("git ls-remote origin refs/heads/main".to_owned()),
    );
    readback.insert(
        "evidence_ref".to_owned(),
        JsonValue::String(origin_main_readback_evidence_ref.to_owned()),
    );
    let mut record = JsonMap::new();
    record.insert(
        "schema".to_owned(),
        JsonValue::String(SOURCE_MAIN_REBIND_SCHEMA.to_owned()),
    );
    record.insert(
        "rebind_receipt_id".to_owned(),
        JsonValue::String(format!("rebind:{digest}")),
    );
    record.insert("binding".to_owned(), checked_binding);
    record.insert("input_identity".to_owned(), input_identity);
    record.insert(
        "old_base_identity".to_owned(),
        JsonValue::Object((*old_base).clone()),
    );
    record.insert(
        "new_base_identity".to_owned(),
        JsonValue::Object((*new_base).clone()),
    );
    record.insert(
        "origin_main_readback".to_owned(),
        JsonValue::Object(readback),
    );
    validate_source_main_rebind_receipt(&JsonValue::Object(record))
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
    for (index, value) in values.iter().enumerate() {
        let item_field = format!("{field}[{index}]");
        let text = string_value(value, &item_field)?;
        if predicate.is_some_and(|predicate| !predicate(&text)) {
            return Err(fail("lifecycle:identity_invalid", &item_field));
        }
        result.push(text);
    }
    if unique {
        let mut seen = BTreeSet::new();
        if result.iter().any(|text| !seen.insert(text)) {
            return Err(fail("lifecycle:duplicate_value", field));
        }
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
