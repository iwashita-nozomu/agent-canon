//! Native owner-guarantee packet normalization and closeout projection.
// @dependency-start
// contract implementation
// responsibility Owns closed owner-guarantee and invalidation packet APIs plus the pure local closeout projection.
// upstream implementation python_json.rs preserves Python code-point strings and canonical ASCII bytes
// upstream implementation python_text.rs owns Python-compatible whitespace stripping
// downstream implementation packets.py remains active for Python publication and TaskClose consumers
// downstream test ../tests/owner_guarantee_native.rs freezes the old packet APIs and projection
// @dependency-end

use crate::python_json::{JsonArray, JsonObject, JsonString, JsonValue};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fmt;

const OWNER_GUARANTEE_FIELDS: &[&str] = &[
    "schema",
    "owner_ref",
    "candidate_digest",
    "property_ref",
    "mechanism_ref",
    "mechanism_transition",
    "mechanism_sufficiency",
    "not_guaranteed",
    "failure_semantics",
    "execution_plane",
    "tool_input_locator",
    "primary_observation_ref",
    "observation_outcome",
    "correspondence_state",
    "invalidation_inputs",
    "downstream_edges",
    "source_snapshot",
    "authority_ref",
];
const OWNER_INVALIDATION_FIELDS: &[&str] = &[
    "schema",
    "from_owner",
    "to_owner",
    "candidate_digest",
    "changed_mechanism_ref",
    "invalidated_property_ref",
    "invalidated_receipt_ref",
    "reason",
    "affected_edge",
    "owner_action",
];
const OWNER_OBSERVATION_OUTCOMES: &[&str] = &[
    "observed_pass",
    "observed_fail",
    "inconclusive",
    "not_applicable",
];
const OWNER_CORRESPONDENCE_STATES: &[&str] = &[
    "unmapped",
    "mapped",
    "observer_assigned",
    "verified",
    "unresolved",
    "refuted",
    "advisory",
];
const OWNER_INVALIDATION_REASONS: &[&str] = &[
    "mechanism_changed",
    "effect_closure_changed",
    "input_changed",
    "source_snapshot_changed",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OwnerGuaranteeError {
    pub message: JsonString,
}

impl fmt::Display for OwnerGuaranteeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        for codepoint in &self.message.0 {
            if let Some(character) = char::from_u32(*codepoint) {
                write!(formatter, "{character}")?;
            } else {
                write!(formatter, "\\u{codepoint:04x}")?;
            }
        }
        Ok(())
    }
}

impl std::error::Error for OwnerGuaranteeError {}

#[derive(Debug, Clone, Copy, Default)]
pub struct OwnerReceiptCompatibility<'a> {
    pub candidate_digest: Option<&'a JsonString>,
    pub property_ref: Option<&'a JsonString>,
    pub owner_ref: Option<&'a JsonString>,
    pub execution_plane: Option<&'a JsonString>,
    pub tool_input_locator: Option<&'a JsonString>,
    pub mechanism_ref: Option<&'a JsonString>,
}

pub struct OwnerReceiptCloseoutInput<'a> {
    pub owner_receipts: &'a [JsonValue],
    pub candidate_digest: Option<&'a JsonString>,
    pub required_owner_refs: &'a [JsonString],
    pub dependency_edges: &'a [JsonString],
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OwnerReceiptCloseoutDecision {
    pub ready: bool,
    pub reasons: Vec<JsonString>,
}

fn error_message(message: JsonString) -> OwnerGuaranteeError {
    OwnerGuaranteeError { message }
}

fn error_suffix(prefix: &JsonString, suffix: &str) -> OwnerGuaranteeError {
    let mut message = prefix.clone();
    message.push_text(suffix);
    error_message(message)
}

fn error_value(prefix: &JsonString, suffix: &str, value: &JsonString) -> OwnerGuaranteeError {
    let mut message = prefix.clone();
    message.push_text(suffix);
    message.0.extend_from_slice(&value.0);
    error_message(message)
}

fn error_fields(prefix: &JsonString, reason: &str, fields: &[JsonString]) -> OwnerGuaranteeError {
    let mut message = prefix.clone();
    message.push_text(reason);
    for (index, field) in fields.iter().enumerate() {
        if index > 0 {
            message.push_text(",");
        }
        message.0.extend_from_slice(&field.0);
    }
    error_message(message)
}

fn error_for_field(prefix: &JsonString, field: &str, suffix: &str) -> OwnerGuaranteeError {
    let mut message = prefix.clone();
    message.push_text(".");
    message.push_text(field);
    message.push_text(suffix);
    error_message(message)
}

fn is_python_whitespace(codepoint: u32) -> bool {
    let Some(character) = char::from_u32(codepoint) else {
        return false;
    };
    let mut buffer = [0; 4];
    crate::python_text::python_strip(character.encode_utf8(&mut buffer)).is_empty()
}

fn python_strip(value: &JsonString) -> JsonString {
    let mut start = 0;
    let mut end = value.0.len();
    while start < end && is_python_whitespace(value.0[start]) {
        start += 1;
    }
    while start < end && is_python_whitespace(value.0[end - 1]) {
        end -= 1;
    }
    JsonString(value.0[start..end].to_vec())
}

fn as_object(value: &JsonValue) -> Option<&JsonObject> {
    match value {
        JsonValue::Object(object) => Some(object),
        _ => None,
    }
}

fn as_array(value: &JsonValue) -> Option<&JsonArray> {
    match value {
        JsonValue::Array(array) => Some(array),
        _ => None,
    }
}

fn as_string(value: &JsonValue) -> Option<&JsonString> {
    match value {
        JsonValue::String(text) => Some(text),
        _ => None,
    }
}

fn object_field<'a>(object: &'a JsonObject, field: &str) -> Option<&'a JsonValue> {
    object
        .0
        .iter()
        .rev()
        .find_map(|(key, value)| key.equals_text(field).then_some(value))
}

fn check_fields(
    object: &JsonObject,
    allowed_fields: &[&str],
    prefix: &JsonString,
) -> Result<(), OwnerGuaranteeError> {
    let allowed = allowed_fields
        .iter()
        .copied()
        .map(|field| JsonString::from_text(field))
        .collect::<BTreeSet<_>>();
    let actual = object
        .0
        .iter()
        .map(|(key, _)| key.clone())
        .collect::<BTreeSet<_>>();
    let unknown = actual.difference(&allowed).cloned().collect::<Vec<_>>();
    if !unknown.is_empty() {
        return Err(error_fields(prefix, ":field_unknown:", &unknown));
    }
    let missing = allowed.difference(&actual).cloned().collect::<Vec<_>>();
    if !missing.is_empty() {
        return Err(error_fields(prefix, ":field_missing:", &missing));
    }
    Ok(())
}

fn required_text(
    object: &JsonObject,
    field: &str,
    prefix: &JsonString,
) -> Result<JsonString, OwnerGuaranteeError> {
    let Some(value) = object_field(object, field).and_then(as_string) else {
        return Err(error_for_field(prefix, field, ":required"));
    };
    let value = python_strip(value);
    if value.is_empty() {
        return Err(error_for_field(prefix, field, ":required"));
    }
    Ok(value)
}

fn required_text_list(
    object: &JsonObject,
    field: &str,
    prefix: &JsonString,
    allow_empty: bool,
) -> Result<Vec<JsonString>, OwnerGuaranteeError> {
    let Some(values) = object_field(object, field).and_then(as_array) else {
        return Err(error_for_field(prefix, field, ":list_required"));
    };
    if !allow_empty && values.0.is_empty() {
        return Err(error_for_field(prefix, field, ":list_required"));
    }
    let mut normalized = Vec::with_capacity(values.0.len());
    for (index, item) in values.0.iter().enumerate() {
        let Some(text) = as_string(item) else {
            return Err(error_for_field(
                prefix,
                field,
                &format!("[{index}]:required"),
            ));
        };
        let text = python_strip(text);
        if text.is_empty() {
            return Err(error_for_field(
                prefix,
                field,
                &format!("[{index}]:required"),
            ));
        }
        normalized.push(text);
    }
    Ok(normalized)
}

fn string_entry(field: &str, value: JsonString) -> (JsonString, JsonValue) {
    (JsonString::from_text(field), JsonValue::String(value))
}

fn string_list_entry(field: &str, values: Vec<JsonString>) -> (JsonString, JsonValue) {
    (
        JsonString::from_text(field),
        JsonValue::Array(JsonArray(
            values.into_iter().map(JsonValue::String).collect(),
        )),
    )
}

fn normalized_text<'a>(record: &'a JsonValue, field: &str) -> &'a JsonString {
    let object = as_object(record).expect("normalized owner packet is an object");
    object_field(object, field)
        .and_then(as_string)
        .expect("normalized owner packet has all text fields")
}

fn normalized_string_list<'a>(record: &'a JsonValue, field: &str) -> &'a [JsonValue] {
    let object = as_object(record).expect("normalized owner packet is an object");
    object_field(object, field)
        .and_then(as_array)
        .map(|array| array.0.as_slice())
        .expect("normalized owner packet has its list field")
}

pub fn normalize_owner_guarantee_packet(
    raw_packet: &JsonValue,
    field_prefix: Option<&JsonString>,
) -> Result<JsonValue, OwnerGuaranteeError> {
    let default_prefix = JsonString::from_text("owner_guarantee");
    let prefix = field_prefix.unwrap_or(&default_prefix);
    let Some(raw) = as_object(raw_packet) else {
        return Err(error_suffix(prefix, ":mapping_required"));
    };
    check_fields(raw, OWNER_GUARANTEE_FIELDS, prefix)?;

    let schema = required_text(raw, "schema", prefix)?;
    if !schema.equals_text("agent-canon.owner-guarantee.v1") {
        return Err(error_value(prefix, ".schema:unknown:", &schema));
    }
    let observation_outcome = required_text(raw, "observation_outcome", prefix)?;
    if !OWNER_OBSERVATION_OUTCOMES
        .iter()
        .any(|allowed| observation_outcome.equals_text(allowed))
    {
        return Err(error_for_field(prefix, "observation_outcome", ":invalid"));
    }
    let correspondence_state = required_text(raw, "correspondence_state", prefix)?;
    if !OWNER_CORRESPONDENCE_STATES
        .iter()
        .any(|allowed| correspondence_state.equals_text(allowed))
    {
        return Err(error_for_field(prefix, "correspondence_state", ":invalid"));
    }

    let owner_ref = required_text(raw, "owner_ref", prefix)?;
    let candidate_digest = required_text(raw, "candidate_digest", prefix)?;
    let property_ref = required_text(raw, "property_ref", prefix)?;
    let mechanism_ref = required_text(raw, "mechanism_ref", prefix)?;
    let mechanism_transition = required_text(raw, "mechanism_transition", prefix)?;
    let mechanism_sufficiency = required_text(raw, "mechanism_sufficiency", prefix)?;
    let not_guaranteed = required_text_list(raw, "not_guaranteed", prefix, false)?;
    let failure_semantics = required_text(raw, "failure_semantics", prefix)?;
    let execution_plane = required_text(raw, "execution_plane", prefix)?;
    let tool_input_locator = required_text(raw, "tool_input_locator", prefix)?;
    let primary_observation_ref = required_text(raw, "primary_observation_ref", prefix)?;
    let invalidation_inputs = required_text_list(raw, "invalidation_inputs", prefix, false)?;
    let downstream_edges = required_text_list(raw, "downstream_edges", prefix, true)?;
    let source_snapshot = required_text(raw, "source_snapshot", prefix)?;
    let authority_ref = required_text(raw, "authority_ref", prefix)?;
    if !invalidation_inputs
        .iter()
        .any(|value| value.equals_text("candidate_digest"))
    {
        return Err(error_for_field(
            prefix,
            "invalidation_inputs",
            ":candidate_digest_missing",
        ));
    }

    Ok(JsonValue::Object(JsonObject(vec![
        string_entry("schema", schema),
        string_entry("owner_ref", owner_ref),
        string_entry("candidate_digest", candidate_digest),
        string_entry("property_ref", property_ref),
        string_entry("mechanism_ref", mechanism_ref),
        string_entry("mechanism_transition", mechanism_transition),
        string_entry("mechanism_sufficiency", mechanism_sufficiency),
        string_list_entry("not_guaranteed", not_guaranteed),
        string_entry("failure_semantics", failure_semantics),
        string_entry("execution_plane", execution_plane),
        string_entry("tool_input_locator", tool_input_locator),
        string_entry("primary_observation_ref", primary_observation_ref),
        string_entry("observation_outcome", observation_outcome),
        string_entry("correspondence_state", correspondence_state),
        string_list_entry("invalidation_inputs", invalidation_inputs),
        string_list_entry("downstream_edges", downstream_edges),
        string_entry("source_snapshot", source_snapshot),
        string_entry("authority_ref", authority_ref),
    ])))
}

pub fn owner_receipt_key(packet: &JsonValue) -> Result<[JsonString; 5], OwnerGuaranteeError> {
    let packet = normalize_owner_guarantee_packet(packet, None)?;
    Ok([
        normalized_text(&packet, "candidate_digest").clone(),
        normalized_text(&packet, "property_ref").clone(),
        normalized_text(&packet, "owner_ref").clone(),
        normalized_text(&packet, "execution_plane").clone(),
        normalized_text(&packet, "tool_input_locator").clone(),
    ])
}

pub fn owner_receipt_is_compatible(
    packet: &JsonValue,
    expected: &OwnerReceiptCompatibility<'_>,
) -> Result<bool, OwnerGuaranteeError> {
    let packet = normalize_owner_guarantee_packet(packet, None)?;
    if !normalized_text(&packet, "correspondence_state").equals_text("verified") {
        return Ok(false);
    }
    if !normalized_text(&packet, "observation_outcome").equals_text("observed_pass") {
        return Ok(false);
    }
    for (field, value) in [
        ("candidate_digest", expected.candidate_digest),
        ("property_ref", expected.property_ref),
        ("owner_ref", expected.owner_ref),
        ("execution_plane", expected.execution_plane),
        ("tool_input_locator", expected.tool_input_locator),
        ("mechanism_ref", expected.mechanism_ref),
    ] {
        if value.is_some_and(|value| normalized_text(&packet, field) != value) {
            return Ok(false);
        }
    }
    Ok(true)
}

pub fn normalize_owner_invalidation_packet(
    raw_packet: &JsonValue,
    field_prefix: Option<&JsonString>,
) -> Result<JsonValue, OwnerGuaranteeError> {
    let default_prefix = JsonString::from_text("owner_invalidation");
    let prefix = field_prefix.unwrap_or(&default_prefix);
    let Some(raw) = as_object(raw_packet) else {
        return Err(error_suffix(prefix, ":mapping_required"));
    };
    check_fields(raw, OWNER_INVALIDATION_FIELDS, prefix)?;

    let schema = required_text(raw, "schema", prefix)?;
    let from_owner = required_text(raw, "from_owner", prefix)?;
    let to_owner = required_text(raw, "to_owner", prefix)?;
    let candidate_digest = required_text(raw, "candidate_digest", prefix)?;
    let changed_mechanism_ref = required_text(raw, "changed_mechanism_ref", prefix)?;
    let invalidated_property_ref = required_text(raw, "invalidated_property_ref", prefix)?;
    let invalidated_receipt_ref = required_text(raw, "invalidated_receipt_ref", prefix)?;
    let reason = required_text(raw, "reason", prefix)?;
    let affected_edge = required_text(raw, "affected_edge", prefix)?;
    let owner_action = required_text(raw, "owner_action", prefix)?;

    if !schema.equals_text("agent-canon.owner-invalidation.v1") {
        return Err(error_value(prefix, ".schema:unknown:", &schema));
    }
    if !OWNER_INVALIDATION_REASONS
        .iter()
        .any(|allowed| reason.equals_text(allowed))
    {
        return Err(error_for_field(prefix, "reason", ":invalid"));
    }
    if !owner_action.equals_text("reevaluate_local_correspondence") {
        return Err(error_for_field(prefix, "owner_action", ":invalid"));
    }

    Ok(JsonValue::Object(JsonObject(vec![
        string_entry("schema", schema),
        string_entry("from_owner", from_owner),
        string_entry("to_owner", to_owner),
        string_entry("candidate_digest", candidate_digest),
        string_entry("changed_mechanism_ref", changed_mechanism_ref),
        string_entry("invalidated_property_ref", invalidated_property_ref),
        string_entry("invalidated_receipt_ref", invalidated_receipt_ref),
        string_entry("reason", reason),
        string_entry("affected_edge", affected_edge),
        string_entry("owner_action", owner_action),
    ])))
}

pub fn owner_receipt_is_invalidated(
    packet: &JsonValue,
    invalidation: &JsonValue,
) -> Result<bool, OwnerGuaranteeError> {
    let packet = normalize_owner_guarantee_packet(packet, None)?;
    let invalidation = normalize_owner_invalidation_packet(invalidation, None)?;
    if normalized_text(&packet, "candidate_digest")
        != normalized_text(&invalidation, "candidate_digest")
    {
        return Ok(false);
    }
    if normalized_text(&invalidation, "invalidated_receipt_ref")
        == normalized_text(&packet, "primary_observation_ref")
    {
        return Ok(true);
    }
    Ok(
        normalized_text(&invalidation, "to_owner") == normalized_text(&packet, "owner_ref")
            && normalized_text(&invalidation, "invalidated_property_ref")
                == normalized_text(&packet, "property_ref"),
    )
}

fn prefix_value(prefix: &str, value: &JsonString) -> JsonString {
    let mut message = JsonString::from_text(prefix);
    message.0.extend_from_slice(&value.0);
    message
}

pub fn owner_receipt_closeout_state(
    input: &OwnerReceiptCloseoutInput<'_>,
) -> Result<OwnerReceiptCloseoutDecision, OwnerGuaranteeError> {
    let mut seen = BTreeSet::<[JsonString; 5]>::new();
    let mut owners = BTreeSet::<JsonString>::new();
    let mut declared_edges = BTreeSet::<JsonString>::new();
    let mut reasons = Vec::new();

    for (index, raw) in input.owner_receipts.iter().enumerate() {
        let prefix = JsonString::from_text(&format!("owner_receipts[{index}]"));
        let packet = match normalize_owner_guarantee_packet(raw, Some(&prefix)) {
            Ok(packet) => packet,
            Err(error) => {
                reasons.push(error.message);
                continue;
            }
        };
        let key = match owner_receipt_key(&packet) {
            Ok(key) => key,
            Err(error) => {
                reasons.push(error.message);
                continue;
            }
        };
        if !seen.insert(key) {
            continue;
        }
        if !normalized_text(&packet, "correspondence_state").equals_text("verified")
            || !normalized_text(&packet, "observation_outcome").equals_text("observed_pass")
        {
            continue;
        }
        if !owner_receipt_is_compatible(
            &packet,
            &OwnerReceiptCompatibility {
                candidate_digest: input.candidate_digest,
                ..OwnerReceiptCompatibility::default()
            },
        )? {
            reasons.push(prefix_value(
                "incompatible:",
                normalized_text(&packet, "primary_observation_ref"),
            ));
            continue;
        }
        owners.insert(normalized_text(&packet, "owner_ref").clone());
        for edge in normalized_string_list(&packet, "downstream_edges") {
            let JsonValue::String(edge) = edge else {
                unreachable!("normalized downstream edges are strings")
            };
            declared_edges.insert(edge.clone());
        }
    }

    for owner in input.required_owner_refs {
        if !owners.contains(owner) {
            reasons.push(prefix_value("missing_owner:", owner));
        }
    }
    for edge in input.dependency_edges {
        if !declared_edges.contains(edge) {
            reasons.push(prefix_value("missing_dependency_edge:", edge));
        }
    }
    Ok(OwnerReceiptCloseoutDecision {
        ready: reasons.is_empty(),
        reasons,
    })
}
