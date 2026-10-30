//! Provider readback acknowledgements bound to canonical local review events.
// @dependency-start
// contract implementation
// responsibility Materializes and verifies provider acknowledgements subordinate to local events.
// upstream design ../../../../../../agents/COMMUNICATION_PROTOCOL.md owns external projection acknowledgement schemas
// upstream implementation artifact_identity.rs provides canonical JSON and body hashing
// @dependency-end

use super::artifact_identity::{
    canonical_body_sha256, canonical_json_bytes, ArtifactIdentityError,
};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fmt;

pub(crate) const ACK_SCHEMA: &str = "agent-canon.external-projection-acknowledgement.v1";
pub(crate) const LOCAL_EVENT_SCHEMA: &str = "agent-canon.terminal-resume-event.v3";
const FORBIDDEN_RECEIPT_FIELDS: [&str; 6] = [
    "provider_receipt_bytes_sha256",
    "receipt_artifact_identity_record_id",
    "receipt_artifact_identity_record_body_sha256",
    "dispatch_receipt_path",
    "dispatch_receipt_sha256",
    "dispatch_receipt_blob",
];
const CODEX_STATUS_MAP: [(&str, &str, &str); 4] = [
    ("running", "dispatch_pending", "dispatched"),
    ("completed", "review_pending", "review_returned"),
    ("errored", "dispatch_pending", "dispatch_blocked"),
    ("shutdown", "dispatch_pending", "dispatch_blocked"),
];
const GITHUB_STATUS_MAP: [(&str, &str, &str); 4] = [
    ("pending", "review_pending", "review_pending"),
    ("approved", "review_pending", "approved"),
    ("changes_requested", "review_pending", "revise"),
    ("dismissed", "review_pending", "review_pending"),
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ExternalProjectionError {
    pub(crate) code: &'static str,
    pub(crate) detail: String,
}

impl ExternalProjectionError {
    fn new(code: &'static str) -> Self {
        Self {
            code,
            detail: String::new(),
        }
    }

    fn with_detail(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for ExternalProjectionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.detail.is_empty() {
            formatter.write_str(self.code)
        } else {
            write!(formatter, "{}:{}", self.code, self.detail)
        }
    }
}

impl std::error::Error for ExternalProjectionError {}

type Result<T> = std::result::Result<T, ExternalProjectionError>;

fn identity_error(error: ArtifactIdentityError) -> ExternalProjectionError {
    ExternalProjectionError {
        code: error.code,
        detail: error.detail,
    }
}

fn object<'a>(value: &'a Value) -> Result<&'a Map<String, Value>> {
    value
        .as_object()
        .ok_or_else(|| ExternalProjectionError::new("external_projection:local_event_mismatch"))
}

fn contains_forbidden_field(value: &Value) -> Option<String> {
    match value {
        Value::Object(values) => {
            for (key, item) in values {
                if FORBIDDEN_RECEIPT_FIELDS.contains(&key.as_str()) {
                    return Some(key.clone());
                }
                if let Some(nested) = contains_forbidden_field(item) {
                    return Some(nested);
                }
            }
            None
        }
        Value::Array(values) => values.iter().find_map(contains_forbidden_field),
        _ => None,
    }
}

fn required_text(mapping: &Map<String, Value>, field: &str) -> Result<String> {
    mapping
        .get(field)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .ok_or_else(|| {
            ExternalProjectionError::with_detail("external_projection:field_missing", field)
        })
}

fn required_int(mapping: &Map<String, Value>, field: &str) -> Result<u64> {
    mapping
        .get(field)
        .and_then(Value::as_u64)
        .filter(|value| *value >= 1)
        .ok_or_else(|| {
            ExternalProjectionError::with_detail("external_projection:field_invalid", field)
        })
}

fn candidate_fields(local_event: &Map<String, Value>) -> Result<BTreeMap<String, Value>> {
    let mut candidate = BTreeMap::new();
    candidate.insert(
        "candidate_id".to_string(),
        json!(required_text(local_event, "candidate_id")?),
    );
    candidate.insert(
        "candidate_revision".to_string(),
        json!(required_int(local_event, "candidate_revision")?),
    );
    candidate.insert(
        "candidate_body_sha256".to_string(),
        json!(required_text(local_event, "candidate_body_sha256")?),
    );
    candidate.insert(
        "candidate_commit".to_string(),
        json!(required_text(local_event, "candidate_commit")?),
    );
    candidate.insert(
        "candidate_tree".to_string(),
        json!(required_text(local_event, "candidate_tree")?),
    );
    Ok(candidate)
}

fn projection_kind(
    local_event: &Map<String, Value>,
    provider: &Map<String, Value>,
) -> Result<&'static str> {
    let provider_kind = required_text(provider, "provider_kind")?;
    let event_kind = required_text(local_event, "event_kind")?;
    match (provider_kind.as_str(), event_kind.as_str()) {
        ("codex_runtime", "terminal_resume_dispatch_observed") => Ok("codex_review_dispatch"),
        ("github", "review_decision_recorded") => Ok("github_review_decision"),
        ("github", "candidate_materialized") => Ok("github_pr_head"),
        _ => Err(ExternalProjectionError::new(
            "external_projection:projection_kind_mismatch",
        )),
    }
}

fn mapped_status(
    projection: &str,
    provider_status: &str,
) -> Result<(&'static str, &'static str, &'static str)> {
    let rule = match projection {
        "codex_review_dispatch" => "agent-canon.projection-map.codex-dispatch.v1",
        "github_review_decision" => "agent-canon.projection-map.github-review.v1",
        _ => "agent-canon.projection-map.github-pr-head.v1",
    };
    let mappings = if projection == "codex_review_dispatch" {
        &CODEX_STATUS_MAP
    } else {
        &GITHUB_STATUS_MAP
    };
    mappings
        .iter()
        .find(|(status, _, _)| *status == provider_status)
        .map(|(_, before, after)| (*before, *after, rule))
        .ok_or_else(|| ExternalProjectionError::new("external_projection:provider_status_invalid"))
}

fn value_or_null(mapping: &Map<String, Value>, field: &str) -> Value {
    mapping.get(field).cloned().unwrap_or(Value::Null)
}

fn required_value(mapping: &Map<String, Value>, field: &str) -> Result<Value> {
    mapping.get(field).cloned().ok_or_else(|| {
        ExternalProjectionError::with_detail("external_projection:field_missing", field)
    })
}

fn hex_sha256(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn acknowledgement_seed(record: &Value) -> Result<Value> {
    let record = object(record)?;
    let mut seed = record.clone();
    seed.remove("external_projection_ack_id");
    seed.remove("external_projection_ack_body_sha256");
    Ok(Value::Object(seed))
}

pub(crate) fn materialize_external_projection_acknowledgement(
    local_event: &Value,
    provider_readback: &Value,
) -> Result<Value> {
    let local_event = object(local_event)?;
    let provider_readback = object(provider_readback)?;
    if let Some(forbidden) = contains_forbidden_field(&Value::Object(local_event.clone()))
        .or_else(|| contains_forbidden_field(&Value::Object(provider_readback.clone())))
    {
        return Err(ExternalProjectionError::with_detail(
            "external_projection:receipt_byte_identity_forbidden",
            forbidden,
        ));
    }
    let local_schema = local_event
        .get("schema")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if ![
        LOCAL_EVENT_SCHEMA,
        "agent-canon.review-decision-event.v1",
        "agent-canon.review-candidate-event.v1",
    ]
    .contains(&local_schema)
    {
        return Err(ExternalProjectionError::new(
            "external_projection:local_event_mismatch",
        ));
    }
    let projection = projection_kind(local_event, provider_readback)?;
    let provider_status = required_text(provider_readback, "provider_status")?;
    let (local_from, local_to, rule) = mapped_status(projection, &provider_status)?;
    let candidate = candidate_fields(local_event)?;
    let provider_kind = required_text(provider_readback, "provider_kind")?;
    let provider_object_id = required_text(provider_readback, "provider_object_id")?;
    let provider_object_version = required_text(provider_readback, "provider_object_version")?;
    let provider_object_kind = required_text(provider_readback, "provider_object_kind")?;

    let mut provider_payload = provider_readback.clone();
    provider_payload.remove("provider_readback_sha256");
    let readback_sha = hex_sha256(
        &canonical_json_bytes(&Value::Object(provider_payload)).map_err(identity_error)?,
    );
    if let Some(supplied) = provider_readback.get("provider_readback_sha256") {
        if !supplied.is_null() && supplied.as_str() != Some(readback_sha.as_str()) {
            return Err(ExternalProjectionError::new(
                "external_projection:provider_readback_hash_mismatch",
            ));
        }
    }
    let local_id_field = if local_schema == LOCAL_EVENT_SCHEMA {
        "resume_event_id"
    } else {
        "event_id"
    };
    let local_hash_field = if local_schema == LOCAL_EVENT_SCHEMA {
        "resume_event_body_sha256"
    } else {
        "event_body_sha256"
    };
    let mut record = Map::new();
    record.insert("schema".to_string(), json!(ACK_SCHEMA));
    record.insert("schema_version".to_string(), json!(1));
    record.insert("external_projection_ack_id".to_string(), json!(""));
    record.insert("projection_kind".to_string(), json!(projection));
    for (output, input) in [
        ("aggregate_identity", "aggregate_identity"),
        ("local_event_schema", "schema"),
        ("local_event_kind", "event_kind"),
    ] {
        record.insert(
            output.to_string(),
            json!(required_text(local_event, input)?),
        );
    }
    record.insert(
        "local_event_id".to_string(),
        json!(required_text(local_event, local_id_field)?),
    );
    record.insert(
        "local_event_body_sha256".to_string(),
        json!(required_text(local_event, local_hash_field)?),
    );
    record.insert(
        "local_event_order_index".to_string(),
        json!(required_int(local_event, "event_order_index")?),
    );
    for field in [
        "review_lineage_id",
        "review_request_id",
        "review_context_id",
    ] {
        record.insert(field.to_string(), json!(required_text(local_event, field)?));
    }
    record.insert(
        "review_frame_id".to_string(),
        value_or_null(local_event, "review_frame_id"),
    );
    record.extend(candidate);
    record.insert("provider_kind".to_string(), json!(provider_kind));
    for field in [
        "provider_instance_id",
        "provider_account_id",
        "provider_repository_id",
    ] {
        record.insert(field.to_string(), value_or_null(provider_readback, field));
    }
    record.insert(
        "provider_object_kind".to_string(),
        json!(provider_object_kind),
    );
    record.insert("provider_object_id".to_string(), json!(provider_object_id));
    record.insert(
        "provider_object_version".to_string(),
        json!(provider_object_version),
    );
    for field in [
        "provider_parent_object_id",
        "provider_operation_id",
        "head_ref",
        "head_oid",
        "head_tree",
    ] {
        record.insert(field.to_string(), value_or_null(provider_readback, field));
    }
    record.insert("local_from_status".to_string(), json!(local_from));
    record.insert("local_to_status".to_string(), json!(local_to));
    record.insert("provider_status".to_string(), json!(provider_status));
    record.insert("status_mapping_rule_id".to_string(), json!(rule));
    record.insert("provider_readback_sha256".to_string(), json!(readback_sha));
    record.insert(
        "acknowledgement_order_index".to_string(),
        json!(required_int(
            provider_readback,
            "acknowledgement_order_index"
        )?),
    );
    record.insert("external_projection_ack_body_sha256".to_string(), json!(""));
    if provider_kind == "codex_runtime" {
        for field in ["head_ref", "head_oid", "head_tree"] {
            if !record[field].is_null() {
                return Err(ExternalProjectionError::with_detail(
                    "external_projection:null_rule_mismatch",
                    field,
                ));
            }
        }
        if record["provider_instance_id"].is_null() || record["provider_parent_object_id"].is_null()
        {
            return Err(ExternalProjectionError::new(
                "external_projection:null_rule_mismatch",
            ));
        }
    } else {
        if record["provider_repository_id"].is_null() {
            return Err(ExternalProjectionError::new(
                "external_projection:null_rule_mismatch",
            ));
        }
        if projection == "github_pr_head" {
            for field in ["head_ref", "head_oid", "head_tree"] {
                if !record[field]
                    .as_str()
                    .is_some_and(|value| !value.is_empty())
                {
                    return Err(ExternalProjectionError::with_detail(
                        "external_projection:null_rule_mismatch",
                        field,
                    ));
                }
            }
            if record["head_oid"] != record["candidate_commit"]
                || record["head_tree"] != record["candidate_tree"]
            {
                return Err(ExternalProjectionError::new(
                    "external_projection:head_mismatch",
                ));
            }
        }
    }
    let mut record = Value::Object(record);
    let ack_id = format!(
        "external-projection-ack:{}",
        hex_sha256(&canonical_json_bytes(&acknowledgement_seed(&record)?).map_err(identity_error)?,)
    );
    record["external_projection_ack_id"] = json!(ack_id);
    let body_sha = canonical_body_sha256(&record, "external_projection_ack_body_sha256")
        .map_err(identity_error)?;
    record["external_projection_ack_body_sha256"] = json!(body_sha);
    Ok(record)
}

pub(crate) fn verify_external_projection_acknowledgement(
    local_event: &Value,
    acknowledgement: &Value,
) -> Result<Value> {
    let local_event = object(local_event)?;
    let acknowledgement = object(acknowledgement)?;
    if acknowledgement.get("schema").and_then(Value::as_str) != Some(ACK_SCHEMA)
        || acknowledgement
            .get("schema_version")
            .and_then(Value::as_u64)
            != Some(1)
    {
        return Err(ExternalProjectionError::new(
            "external_projection:schema_mismatch",
        ));
    }
    if let Some(forbidden) = contains_forbidden_field(&Value::Object(acknowledgement.clone())) {
        return Err(ExternalProjectionError::with_detail(
            "external_projection:receipt_byte_identity_forbidden",
            forbidden,
        ));
    }
    let local_schema = local_event
        .get("schema")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let local_id_field = if local_schema == LOCAL_EVENT_SCHEMA {
        "resume_event_id"
    } else {
        "event_id"
    };
    let local_hash_field = if local_schema == LOCAL_EVENT_SCHEMA {
        "resume_event_body_sha256"
    } else {
        "event_body_sha256"
    };
    if acknowledgement.get("local_event_id") != local_event.get(local_id_field) {
        return Err(ExternalProjectionError::new(
            "external_projection:local_event_mismatch",
        ));
    }
    if acknowledgement.get("local_event_body_sha256") != local_event.get(local_hash_field) {
        return Err(ExternalProjectionError::new(
            "external_projection:local_event_hash_mismatch",
        ));
    }
    for (field, expected) in candidate_fields(local_event)? {
        if acknowledgement.get(&field) != Some(&expected) {
            return Err(ExternalProjectionError::with_detail(
                "external_projection:candidate_mismatch",
                field,
            ));
        }
    }
    let body_sha = canonical_body_sha256(
        &Value::Object(acknowledgement.clone()),
        "external_projection_ack_body_sha256",
    )
    .map_err(identity_error)?;
    if acknowledgement
        .get("external_projection_ack_body_sha256")
        .and_then(Value::as_str)
        != Some(body_sha.as_str())
    {
        return Err(ExternalProjectionError::new(
            "external_projection:body_hash_mismatch",
        ));
    }
    let ack_value = Value::Object(acknowledgement.clone());
    let expected_id = format!(
        "external-projection-ack:{}",
        hex_sha256(
            &canonical_json_bytes(&acknowledgement_seed(&ack_value)?).map_err(identity_error)?,
        )
    );
    if acknowledgement
        .get("external_projection_ack_id")
        .and_then(Value::as_str)
        != Some(expected_id.as_str())
    {
        return Err(ExternalProjectionError::new(
            "external_projection:id_mismatch",
        ));
    }
    Ok(json!({
        "schema": "agent-canon.external-projection-verification.v1",
        "ok": true,
        "external_projection_ack_id": expected_id,
        "local_event_id": required_value(acknowledgement, "local_event_id")?,
        "provider_object_id": required_value(acknowledgement, "provider_object_id")?,
        "provider_status": required_value(acknowledgement, "provider_status")?,
    }))
}
