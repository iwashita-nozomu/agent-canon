// @dependency-start
// contract implementation
// responsibility Owns the one-build AgentCanon dependency graph and persisted runtime-evidence snapshot.
// upstream implementation dependency_manifest.rs provides the complete-file source snapshot
// upstream implementation structured_analysis.rs provides the graph storage schema
// downstream implementation main.rs dispatches the public graph command
// downstream implementation ../../../tools/agent_tools/graph_client.py consumes typed graph responses
// @dependency-end

use crate::dependency_manifest::{
    capture_snapshot, probe_snapshot_identity, write_snapshot_jsonl, DependencyDeclaration,
    ManifestSnapshot, SnapshotRequest, SourceIdentity, SourceSpan,
};
use crate::structured_analysis::{initialize_graph_schema, validate_graph_connection};
use rusqlite::{params, Connection, OpenFlags, OptionalExtension};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::fs::File;
use std::path::{Path, PathBuf};
use std::process::Command;

const GRAPH_SCHEMA_VERSION: &str = "graph_storage_core.v1";
const RUNTIME_EVENT_SCHEMA: &str = "agent_canon.runtime_event.v1";
const RUNTIME_EVIDENCE_SCHEMA: &str = "agent_canon.runtime_evidence_snapshot.v2";
const RUNTIME_PUBLICATION_INTENT_SCHEMA: &str = "agent_canon.runtime_event.publication_intent.v1";
const RUNTIME_OBSERVATION_SCHEMA: &str =
    "agent_canon.runtime_event.publication_outcome_observation.v1";
const RUNTIME_RECEIPT_SCHEMA: &str = "agent_canon.runtime_event.publication_outcome_receipt.v1";

#[derive(Debug, Clone)]
struct RuntimeEvidenceSnapshot {
    artifact_path: String,
    artifact_sha256: String,
    artifact_schema: String,
    materialization_id: String,
    attempt_id: String,
    receipt_path: String,
    receipt_sha256: String,
    receipt_schema: String,
    receipt_sequence: u8,
    receipt_outcome: String,
    result_family: String,
    gate_id: String,
    gate_result: String,
    source_event_id: String,
    source_event_sha256: String,
    rollout_path: String,
    rollout_file_sha256: String,
    source_head_oid: String,
    base_ref: String,
    base_oid: String,
    result_path: String,
    result_schema: String,
    result_blob_oid: String,
    target_paths: Value,
    porcelain_v1: Value,
    publication_intent: Value,
    publication_observation: Value,
    target_identities: Value,
    freshness_certificate: Value,
    live_identity_fingerprint: String,
    artifact_bytes: Vec<u8>,
    artifact_value: Value,
    receipt_bytes: Vec<u8>,
    receipt_value: Value,
}

#[derive(Debug, Clone)]
struct InputFingerprintProbe {
    input_fingerprint: Option<String>,
    artifact_sha256: Option<String>,
    receipt_sha256: Option<String>,
    live_identity_fingerprint: Option<String>,
    source_fingerprint: String,
    source_head_oid: String,
    dirty_fingerprint: String,
    profile: String,
    reason: Option<String>,
}

#[derive(Debug, Clone, Default)]
struct PersistedInputIdentity {
    input_fingerprint: String,
    artifact_sha256: String,
    receipt_sha256: String,
    live_identity_fingerprint: String,
    source_fingerprint: String,
    source_head_oid: String,
    dirty_fingerprint: String,
    profile: String,
}

#[derive(Debug, Clone)]
struct ProducerArtifact {
    producer_id: String,
    version: String,
    command: String,
    root: String,
    content_sha256: String,
    relation_families: Vec<String>,
    artifact_ref: String,
    payload: Vec<u8>,
}

impl ProducerArtifact {
    fn json(&self) -> Value {
        json!({"producer_id":self.producer_id,"version":self.version,"command":self.command,"root":self.root,"content_sha256":self.content_sha256,"payload_sha256":sha256(&self.payload),"relation_families":self.relation_families,"artifact_ref":self.artifact_ref})
    }
}

#[derive(Debug, Clone)]
struct GraphIntegrationRecord {
    root: String,
    db_path: String,
    profile: String,
    source_snapshot_profile: String,
    snapshot_head: String,
    input_fingerprint: String,
    graph_fingerprint: String,
    contract_fingerprint: String,
    producer_artifacts: Vec<ProducerArtifact>,
    runtime_evidence: Value,
    verified: bool,
    verification_code: String,
}

impl GraphIntegrationRecord {
    fn json(&self) -> Value {
        json!({"schema":"agent-canon.graph.integration.v1","root":self.root,"db_path":self.db_path,"schema_version":GRAPH_SCHEMA_VERSION,"profile":self.profile,"source_snapshot_profile":self.source_snapshot_profile,"snapshot_head":self.snapshot_head,"input_fingerprint":self.input_fingerprint,"graph_fingerprint":self.graph_fingerprint,"contract_fingerprint":self.contract_fingerprint,"producer_artifacts":self.producer_artifacts.iter().map(ProducerArtifact::json).collect::<Vec<_>>(),"runtime_evidence":self.runtime_evidence.clone(),"verified":self.verified,"verification_code":self.verification_code})
    }
}

#[derive(Debug)]
enum GraphError {
    Usage(String),
    Unavailable(String),
    Validation(String),
    Io(String),
    RuntimeBoundary { reason: String, detail: String },
}

impl std::fmt::Display for GraphError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Usage(value)
            | Self::Unavailable(value)
            | Self::Validation(value)
            | Self::Io(value) => formatter.write_str(value),
            Self::RuntimeBoundary { reason, detail } => {
                write!(formatter, "{reason}: {detail}")
            }
        }
    }
}

#[derive(Debug, Clone)]
struct GraphArgs {
    root: PathBuf,
    profile: String,
    format: String,
    path: Option<String>,
    all: bool,
    relation: String,
    direction: String,
    depth: usize,
    token: Option<String>,
}

#[derive(Debug, Clone)]
struct BuildMaterial {
    root: PathBuf,
    graph_root: PathBuf,
    profile: String,
    snapshot: ManifestSnapshot,
    runtime_evidence: RuntimeEvidenceSnapshot,
    nodes: Vec<Value>,
    facts: Vec<Value>,
    producer_artifacts: Vec<ProducerArtifact>,
    input_fingerprint: String,
    graph_fingerprint: String,
}

fn sha256(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

fn required_string(object: &Map<String, Value>, field: &str) -> Result<String, GraphError> {
    object
        .get(field)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .ok_or_else(|| GraphError::Validation(format!("runtime evidence field {field} is missing")))
}

fn runtime_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn runtime_uuid(value: &str) -> bool {
    value.len() == 36
        && value.bytes().enumerate().all(|(index, byte)| match index {
            8 | 13 | 18 | 23 => byte == b'-',
            _ => byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase(),
        })
}

fn runtime_relative_path(value: &str) -> bool {
    !value.is_empty()
        && !value.starts_with('/')
        && !value.contains('\\')
        && !value.split('/').any(|part| matches!(part, "" | "." | ".."))
}

fn runtime_absolute_path(value: &str) -> bool {
    value.starts_with('/')
        && !value.contains('\0')
        && !value.contains('\\')
        && !value
            .split('/')
            .skip(1)
            .any(|part| matches!(part, "." | ".."))
}

fn runtime_family_spec(family: &str) -> Option<(&'static str, &'static str, &'static str)> {
    match family {
        "requirements" => Some((
            "requirements_review.md",
            "requirements-review",
            "ReviewArtifactV1",
        )),
        "design" => Some(("design_review.md", "design-review", "ReviewArtifactV1")),
        "review" => Some(("change_review.md", "change-review", "ReviewArtifactV1")),
        "validation" => Some((
            "validation_result.json",
            "validation",
            "agent_canon.runtime_result_input.v1",
        )),
        "lifecycle" => Some(("closeout_gate.md", "closeout", "CloseoutGateV1")),
        _ => None,
    }
}

fn runtime_object<'a>(
    value: &'a Value,
    name: &str,
    keys: &[&str],
) -> Result<&'a Map<String, Value>, GraphError> {
    let object = value.as_object().ok_or_else(|| {
        GraphError::Validation(format!("runtime evidence {name} is not an object"))
    })?;
    if object.len() != keys.len() || keys.iter().any(|key| !object.contains_key(*key)) {
        return Err(GraphError::Validation(format!(
            "runtime evidence {name} fields mismatch"
        )));
    }
    Ok(object)
}

fn runtime_ordered_object(
    output: &mut String,
    object: &Map<String, Value>,
    keys: &[&str],
    nested: fn(&mut String, &str, &Value) -> Result<(), GraphError>,
) -> Result<(), GraphError> {
    output.push('{');
    for (index, key) in keys.iter().enumerate() {
        if index > 0 {
            output.push(',');
        }
        output.push_str(&serde_json::to_string(key).unwrap_or_default());
        output.push(':');
        let value = object
            .get(*key)
            .ok_or_else(|| GraphError::Validation(format!("runtime evidence {key} is missing")))?;
        nested(output, key, value)?;
    }
    output.push('}');
    Ok(())
}

fn runtime_identity_value(
    output: &mut String,
    _key: &str,
    value: &Value,
) -> Result<(), GraphError> {
    output.push_str(
        &serde_json::to_string(value).map_err(|error| GraphError::Validation(error.to_string()))?,
    );
    Ok(())
}

fn runtime_nested_value(output: &mut String, key: &str, value: &Value) -> Result<(), GraphError> {
    let shape = match key {
        "gate" => Some(&["id", "result"][..]),
        "source_event" => Some(
            &[
                "agent_id",
                "agent_context_id",
                "codex_thread_id",
                "parent_id",
                "turn_id",
                "role",
                "decision",
                "applicable_gate_result",
                "rollout_path",
                "rollout_path_bytes_b64",
                "rollout_path_sha256",
                "rollout_file_sha256",
                "record_line",
                "record_byte_offset",
                "record_byte_length",
                "record_bytes_b64",
                "record_sha256",
                "stable_record_id",
            ][..],
        ),
        "result_artifact" => Some(
            &[
                "path",
                "schema",
                "artifact_sha256",
                "artifact_blob_oid",
                "gate_id",
                "gate_result",
                "target_paths",
                "base_ref",
                "base_oid",
            ][..],
        ),
        "source_snapshot" => Some(&["head_oid", "base_ref", "base_oid", "porcelain_v1"][..]),
        "publication_intent" => {
            Some(&["schema", "attempt_id", "target_path", "prepared_state"][..])
        }
        _ => None,
    };
    if let Some(keys) = shape {
        let object = runtime_object(value, key, keys)?;
        return runtime_ordered_object(output, object, keys, runtime_identity_value);
    }
    if key == "target_identities" {
        let identities = value.as_array().ok_or_else(|| {
            GraphError::Validation(
                "runtime evidence target identities are not an array".to_string(),
            )
        })?;
        output.push('[');
        for (index, identity) in identities.iter().enumerate() {
            if index > 0 {
                output.push(',');
            }
            let keys = [
                "path",
                "content_sha256",
                "git_blob_oid",
                "base_present",
                "base_content_sha256",
                "base_git_blob_oid",
            ];
            let object = runtime_object(identity, "target identity", &keys)?;
            runtime_ordered_object(output, object, &keys, runtime_identity_value)?;
        }
        output.push(']');
        return Ok(());
    }
    runtime_identity_value(output, key, value)
}

fn runtime_canonical_bytes(value: &Value, zero_artifact: bool) -> Result<Vec<u8>, GraphError> {
    let mut normalized = value.clone();
    let object = normalized
        .as_object_mut()
        .ok_or_else(|| GraphError::Validation("runtime evidence is not an object".to_string()))?;
    if zero_artifact {
        object.insert("artifact_sha256".to_string(), Value::String("0".repeat(64)));
    }
    let keys = [
        "schema",
        "materialization_id",
        "result_family",
        "gate",
        "source_event",
        "result_artifact",
        "target_identities",
        "source_snapshot",
        "publication_intent",
        "artifact_sha256",
    ];
    let object = runtime_object(&normalized, "certificate", &keys)?;
    let mut output = String::new();
    runtime_ordered_object(&mut output, object, &keys, runtime_nested_value)?;
    output.push('\n');
    Ok(output.into_bytes())
}

fn runtime_materialization_preimage(value: &Value) -> Result<Vec<u8>, GraphError> {
    let object = value
        .as_object()
        .ok_or_else(|| GraphError::Validation("runtime evidence is not an object".to_string()))?;
    let gate = runtime_object(
        object.get("gate").unwrap_or(&Value::Null),
        "gate",
        &["id", "result"],
    )?;
    let source = object
        .get("source_event")
        .and_then(Value::as_object)
        .ok_or_else(|| GraphError::Validation("runtime source_event missing".to_string()))?;
    let artifact = object
        .get("result_artifact")
        .and_then(Value::as_object)
        .ok_or_else(|| GraphError::Validation("runtime result_artifact missing".to_string()))?;
    let snapshot = object
        .get("source_snapshot")
        .and_then(Value::as_object)
        .ok_or_else(|| GraphError::Validation("runtime source_snapshot missing".to_string()))?;
    let scalar = |value: &Value| serde_json::to_string(value).unwrap_or_default();
    let mut output = String::from("{");
    output.push_str("\"schema\":\"agent_canon.runtime_event.materialization.v1\",");
    output.push_str(&format!(
        "\"result_family\":{},",
        scalar(object.get("result_family").unwrap_or(&Value::Null))
    ));
    output.push_str("\"gate\":");
    runtime_ordered_object(&mut output, gate, &["id", "result"], runtime_identity_value)?;
    output.push_str(",\"source_event\":{");
    for (index, key) in [
        "stable_record_id",
        "rollout_path_sha256",
        "rollout_file_sha256",
        "record_line",
        "record_byte_offset",
        "record_byte_length",
    ]
    .iter()
    .enumerate()
    {
        if index > 0 {
            output.push(',');
        }
        output.push_str(&format!(
            "{}:{}",
            scalar(&Value::String((*key).to_string())),
            scalar(source.get(*key).unwrap_or(&Value::Null))
        ));
    }
    output.push_str("},\"result_artifact\":{");
    for (index, key) in ["artifact_sha256", "artifact_blob_oid", "gate_id"]
        .iter()
        .enumerate()
    {
        if index > 0 {
            output.push(',');
        }
        output.push_str(&format!(
            "{}:{}",
            scalar(&Value::String((*key).to_string())),
            scalar(artifact.get(*key).unwrap_or(&Value::Null))
        ));
    }
    output.push_str("},\"target_identities\":");
    runtime_nested_value(
        &mut output,
        "target_identities",
        object.get("target_identities").unwrap_or(&Value::Null),
    )?;
    output.push_str(",\"source_snapshot\":{");
    for (index, key) in ["head_oid", "base_ref", "base_oid"].iter().enumerate() {
        if index > 0 {
            output.push(',');
        }
        output.push_str(&format!(
            "{}:{}",
            scalar(&Value::String((*key).to_string())),
            scalar(snapshot.get(*key).unwrap_or(&Value::Null))
        ));
    }
    output.push_str("}}\n");
    Ok(output.into_bytes())
}

fn decode_base64(value: &str) -> Result<Vec<u8>, GraphError> {
    fn digit(byte: u8) -> Option<u8> {
        match byte {
            b'A'..=b'Z' => Some(byte - b'A'),
            b'a'..=b'z' => Some(byte - b'a' + 26),
            b'0'..=b'9' => Some(byte - b'0' + 52),
            b'+' => Some(62),
            b'/' => Some(63),
            _ => None,
        }
    }
    let bytes = value.as_bytes();
    if !bytes.len().is_multiple_of(4) {
        return Err(GraphError::Validation(
            "runtime base64 length is invalid".to_string(),
        ));
    }
    let mut output = Vec::new();
    for (index, chunk) in bytes.chunks_exact(4).enumerate() {
        let final_chunk = index + 1 == bytes.len() / 4;
        if chunk[0] == b'='
            || chunk[1] == b'='
            || (chunk[2] == b'=' && chunk[3] != b'=')
            || (!final_chunk && (chunk[2] == b'=' || chunk[3] == b'='))
        {
            return Err(GraphError::Validation(
                "runtime base64 padding is invalid".to_string(),
            ));
        }
        let a = digit(chunk[0])
            .ok_or_else(|| GraphError::Validation("runtime base64 is invalid".to_string()))?;
        let b = digit(chunk[1])
            .ok_or_else(|| GraphError::Validation("runtime base64 is invalid".to_string()))?;
        let c = if chunk[2] == b'=' {
            0
        } else {
            digit(chunk[2])
                .ok_or_else(|| GraphError::Validation("runtime base64 is invalid".to_string()))?
        };
        let d = if chunk[3] == b'=' {
            0
        } else {
            digit(chunk[3])
                .ok_or_else(|| GraphError::Validation("runtime base64 is invalid".to_string()))?
        };
        output.push((a << 2) | (b >> 4));
        if chunk[2] != b'=' {
            output.push((b << 4) | (c >> 2));
        }
        if chunk[3] != b'=' {
            output.push((c << 6) | d);
        }
    }
    Ok(output)
}

fn git_value(root: &Path, args: &[&str]) -> Result<Vec<u8>, GraphError> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|error| GraphError::Unavailable(error.to_string()))?;
    if !output.status.success() {
        return Err(GraphError::Unavailable(
            String::from_utf8_lossy(&output.stderr).trim().to_string(),
        ));
    }
    Ok(output.stdout)
}

fn git_text_value(root: &Path, args: &[&str]) -> Result<String, GraphError> {
    Ok(String::from_utf8_lossy(&git_value(root, args)?)
        .trim()
        .to_string())
}

fn git_value_exists(root: &Path, args: &[&str]) -> Result<bool, GraphError> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|error| GraphError::Unavailable(error.to_string()))?;
    Ok(output.status.success())
}

fn runtime_string_array(value: &Value, name: &str) -> Result<Vec<String>, GraphError> {
    value
        .as_array()
        .ok_or_else(|| GraphError::Validation(format!("runtime evidence {name} is not an array")))?
        .iter()
        .map(|item| {
            item.as_str().map(str::to_string).ok_or_else(|| {
                GraphError::Validation(format!("runtime evidence {name} contains a non-string"))
            })
        })
        .collect()
}

fn runtime_porcelain_paths(line: &str) -> Result<Vec<String>, GraphError> {
    let bytes = line.as_bytes();
    if bytes.len() < 4
        || bytes[2] != b' '
        || bytes.iter().any(|byte| matches!(*byte, 0 | b'\n' | b'\r'))
    {
        return Err(GraphError::Validation(
            "runtime porcelain-v1 line is invalid".to_string(),
        ));
    }
    let path = line.get(3..).unwrap_or_default();
    if path.is_empty() {
        return Err(GraphError::Validation(
            "runtime porcelain-v1 path is empty".to_string(),
        ));
    }
    let paths = path
        .split(" -> ")
        .map(|part| part.trim().trim_matches('"').to_string())
        .collect::<Vec<_>>();
    if paths.iter().any(|path| {
        !runtime_relative_path(path)
            || path == ".git"
            || path.starts_with(".git/")
            || path == ".agent-canon"
            || path.starts_with(".agent-canon/")
            || path
                .rsplit('/')
                .next()
                .map(|name| {
                    name.starts_with("runtime_event.")
                        || name.starts_with("runtime_event_archive_manifest.")
                })
                .unwrap_or(false)
    }) {
        return Err(GraphError::Validation(
            "runtime porcelain-v1 path is unsafe or generated".to_string(),
        ));
    }
    Ok(paths)
}

fn runtime_event_name(name: &str) -> Option<&str> {
    let unit = name.strip_prefix("runtime_event.")?.strip_suffix(".json")?;
    (runtime_hex(unit, 16)).then_some(unit)
}

fn runtime_boundary(reason: &str, detail: impl Into<String>) -> GraphError {
    GraphError::RuntimeBoundary {
        reason: reason.to_string(),
        detail: detail.into(),
    }
}

fn runtime_live_identity(
    root: &Path,
    artifact: &Map<String, Value>,
    snapshot: &Map<String, Value>,
    identities: &[Value],
) -> Result<String, GraphError> {
    let current = |result: Result<String, GraphError>| {
        result.map_err(|error| runtime_boundary("source_changed", error.to_string()))
    };
    let source_head = current(git_text_value(root, &["rev-parse", "--verify", "HEAD"]))?;
    let base_ref = required_string(snapshot, "base_ref")?;
    let observed_base = current(git_text_value(root, &["rev-parse", "--verify", &base_ref]))?;
    let result_path = required_string(artifact, "path")?;
    let result_bytes = fs::read(root.join(&result_path)).map_err(|error| {
        runtime_boundary(
            "source_changed",
            format!("runtime result artifact: {error}"),
        )
    })?;
    let result_sha256 = sha256(&result_bytes);
    let result_blob = current(git_text_value(root, &["hash-object", "--", &result_path]))?;
    let target_paths = runtime_string_array(
        artifact.get("target_paths").unwrap_or(&Value::Null),
        "target_paths",
    )?;
    let mut observed_targets = Vec::new();
    for (path, declared) in target_paths.iter().zip(identities.iter()) {
        let declared = declared.as_object().ok_or_else(|| {
            runtime_boundary(
                "runtime_evidence_changed",
                "target identity is not an object",
            )
        })?;
        let bytes = fs::read(root.join(path)).map_err(|error| {
            runtime_boundary("source_changed", format!("runtime target {path}: {error}"))
        })?;
        let content_sha256 = sha256(&bytes);
        let blob = current(git_text_value(root, &["hash-object", "--", path]))?;
        let base_spec = format!("{observed_base}:{path}");
        let base_present = git_value_exists(root, &["cat-file", "-e", &base_spec])
            .map_err(|error| runtime_boundary("source_changed", error.to_string()))?;
        let (base_sha256, base_blob) = if base_present {
            let base_bytes = git_value(root, &["show", &base_spec])
                .map_err(|error| runtime_boundary("source_changed", error.to_string()))?;
            let blob = current(git_text_value(root, &["rev-parse", "--verify", &base_spec]))?;
            (Some(sha256(&base_bytes)), Some(blob))
        } else {
            (None, None)
        };
        if declared.get("path").and_then(Value::as_str) != Some(path.as_str())
            || declared.get("content_sha256").and_then(Value::as_str)
                != Some(content_sha256.as_str())
            || declared.get("git_blob_oid").and_then(Value::as_str) != Some(blob.as_str())
            || declared.get("base_present").and_then(Value::as_bool) != Some(base_present)
            || declared.get("base_content_sha256").and_then(Value::as_str) != base_sha256.as_deref()
            || declared.get("base_git_blob_oid").and_then(Value::as_str) != base_blob.as_deref()
        {
            return Err(runtime_boundary(
                "source_changed",
                format!("runtime target identity changed: {path}"),
            ));
        }
        observed_targets.push(json!({
            "path": path,
            "content_sha256": content_sha256,
            "git_blob_oid": blob,
            "base_present": base_present,
            "base_content_sha256": base_sha256,
            "base_git_blob_oid": base_blob,
        }));
    }
    if snapshot.get("head_oid").and_then(Value::as_str) != Some(source_head.as_str())
        || snapshot.get("base_oid").and_then(Value::as_str) != Some(observed_base.as_str())
        || artifact.get("artifact_sha256").and_then(Value::as_str) != Some(result_sha256.as_str())
        || artifact.get("artifact_blob_oid").and_then(Value::as_str) != Some(result_blob.as_str())
    {
        return Err(runtime_boundary(
            "source_changed",
            "runtime result, head, or base identity changed",
        ));
    }

    let mut canonical = String::from("{\"schema\":\"agent_canon.runtime_event.live_identity.v1\",");
    canonical.push_str(&format!(
        "\"source_head_oid\":{},\"base_ref\":{},\"base_oid\":{},",
        serde_json::to_string(&source_head).unwrap_or_default(),
        serde_json::to_string(&base_ref).unwrap_or_default(),
        serde_json::to_string(&observed_base).unwrap_or_default(),
    ));
    canonical.push_str(&format!(
        "\"result_artifact\":{{\"path\":{},\"artifact_sha256\":{},\"artifact_blob_oid\":{}}},\"target_identities\":",
        serde_json::to_string(&result_path).unwrap_or_default(),
        serde_json::to_string(&result_sha256).unwrap_or_default(),
        serde_json::to_string(&result_blob).unwrap_or_default(),
    ));
    runtime_nested_value(
        &mut canonical,
        "target_identities",
        &Value::Array(observed_targets),
    )?;
    canonical.push_str("}\n");
    Ok(sha256(
        &[
            b"agent_canon.runtime_event.live_identity.v1\0".as_slice(),
            canonical.as_bytes(),
        ]
        .concat(),
    ))
}

fn active_runtime_event(root: &Path) -> Result<(PathBuf, Vec<u8>), GraphError> {
    let pointer = root.join("reports/agents/.active_run");
    let active = fs::read_to_string(&pointer)
        .map_err(|error| GraphError::Unavailable(format!("active run pointer: {error}")))?;
    let active_value = active.trim();
    if active_value.is_empty() || active_value.contains('\0') {
        return Err(GraphError::Validation(
            "active run pointer is empty or unsafe".to_string(),
        ));
    }
    let active_path = PathBuf::from(active_value);
    let candidate = if active_path.is_absolute() {
        active_path
    } else {
        pointer.parent().unwrap_or(root).join(active_path)
    };
    let run_dir = candidate
        .canonicalize()
        .map_err(|error| GraphError::Unavailable(format!("active run: {error}")))?;
    let report_root = root
        .join("reports/agents")
        .canonicalize()
        .map_err(|error| GraphError::Unavailable(format!("agent report root: {error}")))?;
    let run_name = run_dir
        .strip_prefix(&report_root)
        .ok()
        .and_then(|relative| {
            let mut components = relative.components();
            let first = components.next()?.as_os_str().to_str()?;
            components.next().is_none().then_some(first)
        })
        .filter(|value| !matches!(*value, "" | "." | ".."))
        .ok_or_else(|| {
            GraphError::Validation("active run pointer escapes reports/agents".to_string())
        })?;
    let mut events = fs::read_dir(&run_dir)
        .map_err(|error| GraphError::Unavailable(format!("active run: {error}")))?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| {
            fs::symlink_metadata(path)
                .map(|metadata| metadata.file_type().is_file())
                .unwrap_or(false)
                && path
                    .file_name()
                    .and_then(|name| name.to_str())
                    .and_then(runtime_event_name)
                    .is_some()
        })
        .collect::<Vec<_>>();
    events.sort();
    if events.len() != 1 {
        return Err(GraphError::Unavailable(format!(
            "expected one runtime-event certificate, found {}",
            events.len()
        )));
    }
    let event = events.remove(0);
    let expected_prefix = format!("reports/agents/{run_name}/");
    let relative = event
        .strip_prefix(root)
        .ok()
        .and_then(Path::to_str)
        .map(|value| value.replace('\\', "/"));
    if event.parent() != Some(run_dir.as_path())
        || !relative
            .as_deref()
            .map(|value| value.starts_with(&expected_prefix))
            .unwrap_or(false)
    {
        return Err(GraphError::Validation(
            "runtime-event path does not match active run".to_string(),
        ));
    }
    let bytes = fs::read(&event).map_err(|error| GraphError::Unavailable(error.to_string()))?;
    Ok((event, bytes))
}

fn publication_attempt_id(materialization_id: &str, target_path: &str) -> String {
    sha256(
        &[
            b"agent_canon.runtime_event.publication_attempt.v1\0".as_slice(),
            materialization_id.as_bytes(),
            b"\0".as_slice(),
            target_path.as_bytes(),
        ]
        .concat(),
    )
}

fn observation_nested_value(
    output: &mut String,
    key: &str,
    value: &Value,
) -> Result<(), GraphError> {
    if key == "evidence" {
        let keys = [
            "source",
            "causal_gap",
            "target_presence",
            "rename_status",
            "target_directory_fsync_status",
            "readback_status",
            "readback_sha256",
        ];
        let object = runtime_object(value, "publication observation evidence", &keys)?;
        return runtime_ordered_object(output, object, &keys, runtime_identity_value);
    }
    runtime_identity_value(output, key, value)
}

fn observation_canonical_bytes(value: &Value, zero_hash: bool) -> Result<Vec<u8>, GraphError> {
    let mut normalized = value.clone();
    if zero_hash {
        normalized
            .as_object_mut()
            .ok_or_else(|| {
                runtime_boundary("runtime_receipt_invalid", "observation is not an object")
            })?
            .insert(
                "observation_sha256".to_string(),
                Value::String("0".repeat(64)),
            );
    }
    let keys = [
        "schema",
        "attempt_id",
        "artifact_path",
        "artifact_sha256",
        "materialization_id",
        "sequence",
        "prior_observation_sha256",
        "outcome",
        "evidence",
        "observation_sha256",
    ];
    let object = runtime_object(&normalized, "publication observation", &keys)?;
    let mut output = String::new();
    runtime_ordered_object(&mut output, object, &keys, observation_nested_value)?;
    output.push('\n');
    Ok(output.into_bytes())
}

fn validate_observation(value: &Value) -> Result<(), GraphError> {
    let invalid = |detail: &str| runtime_boundary("runtime_receipt_invalid", detail);
    let keys = [
        "schema",
        "attempt_id",
        "artifact_path",
        "artifact_sha256",
        "materialization_id",
        "sequence",
        "prior_observation_sha256",
        "outcome",
        "evidence",
        "observation_sha256",
    ];
    let observation = runtime_object(value, "publication observation", &keys)
        .map_err(|error| invalid(&error.to_string()))?;
    let evidence_keys = [
        "source",
        "causal_gap",
        "target_presence",
        "rename_status",
        "target_directory_fsync_status",
        "readback_status",
        "readback_sha256",
    ];
    let evidence = runtime_object(
        observation.get("evidence").unwrap_or(&Value::Null),
        "publication observation evidence",
        &evidence_keys,
    )
    .map_err(|error| invalid(&error.to_string()))?;
    let attempt_id = required_string(observation, "attempt_id")?;
    let artifact_path = required_string(observation, "artifact_path")?;
    let artifact_sha256 = required_string(observation, "artifact_sha256")?;
    let materialization_id = required_string(observation, "materialization_id")?;
    let observation_sha256 = required_string(observation, "observation_sha256")?;
    let sequence = observation
        .get("sequence")
        .and_then(Value::as_u64)
        .filter(|value| matches!(*value, 1 | 2))
        .ok_or_else(|| invalid("observation sequence is invalid"))?;
    let prior = observation
        .get("prior_observation_sha256")
        .unwrap_or(&Value::Null);
    let source = evidence.get("source").and_then(Value::as_str);
    let causal_gap = evidence.get("causal_gap").and_then(Value::as_bool);
    let readback_status = evidence.get("readback_status").and_then(Value::as_str);
    let readback_sha = evidence.get("readback_sha256").unwrap_or(&Value::Null);
    if observation.get("schema").and_then(Value::as_str) != Some(RUNTIME_OBSERVATION_SCHEMA)
        || !runtime_hex(&attempt_id, 64)
        || !runtime_relative_path(&artifact_path)
        || !runtime_hex(&artifact_sha256, 64)
        || !runtime_hex(&materialization_id, 64)
        || !runtime_hex(&observation_sha256, 64)
        || (sequence == 1 && !prior.is_null())
        || (sequence == 2
            && !prior
                .as_str()
                .map(|value| runtime_hex(value, 64))
                .unwrap_or(false))
        || !matches!(
            observation.get("outcome").and_then(Value::as_str),
            Some("committed" | "uncertain")
        )
        || !matches!(source, Some("publish" | "recovery"))
        || causal_gap.is_none()
        || evidence.get("target_presence").and_then(Value::as_str) != Some("present")
        || !matches!(
            evidence
                .get("target_directory_fsync_status")
                .and_then(Value::as_str),
            Some("succeeded" | "failed" | "unknown")
        )
        || !matches!(readback_status, Some("verified" | "failed" | "mismatch"))
        || (readback_status == Some("failed") && !readback_sha.is_null())
        || (readback_status != Some("failed")
            && !readback_sha
                .as_str()
                .map(|value| runtime_hex(value, 64))
                .unwrap_or(false))
        || (source == Some("publish")
            && (causal_gap != Some(false)
                || evidence.get("rename_status").and_then(Value::as_str) != Some("completed")))
        || (source == Some("recovery")
            && evidence.get("rename_status").and_then(Value::as_str) != Some("recovered_present"))
        || (causal_gap == Some(true) && (source != Some("recovery") || sequence != 1))
    {
        return Err(invalid("observation values are invalid"));
    }
    if sha256(&observation_canonical_bytes(value, true)?) != observation_sha256 {
        return Err(invalid("observation hash is invalid"));
    }
    Ok(())
}

fn receipt_nested_value(output: &mut String, key: &str, value: &Value) -> Result<(), GraphError> {
    if key == "observation" {
        let bytes = observation_canonical_bytes(value, false)?;
        let text = std::str::from_utf8(&bytes)
            .map_err(|error| runtime_boundary("runtime_receipt_invalid", error.to_string()))?;
        output.push_str(text.trim_end_matches('\n'));
        return Ok(());
    }
    runtime_identity_value(output, key, value)
}

fn receipt_canonical_bytes(value: &Value, zero_hash: bool) -> Result<Vec<u8>, GraphError> {
    let mut normalized = value.clone();
    if zero_hash {
        normalized
            .as_object_mut()
            .ok_or_else(|| runtime_boundary("runtime_receipt_invalid", "receipt is not an object"))?
            .insert("receipt_sha256".to_string(), Value::String("0".repeat(64)));
    }
    let keys = [
        "schema",
        "attempt_id",
        "artifact_path",
        "artifact_sha256",
        "materialization_id",
        "sequence",
        "prior_receipt_sha256",
        "observation",
        "receipt_sha256",
    ];
    let object = runtime_object(&normalized, "publication receipt", &keys)?;
    let mut output = String::new();
    runtime_ordered_object(&mut output, object, &keys, receipt_nested_value)?;
    output.push('\n');
    Ok(output.into_bytes())
}

fn validate_receipt(value: &Value, raw: &[u8]) -> Result<(), GraphError> {
    let invalid = |detail: &str| runtime_boundary("runtime_receipt_invalid", detail);
    let keys = [
        "schema",
        "attempt_id",
        "artifact_path",
        "artifact_sha256",
        "materialization_id",
        "sequence",
        "prior_receipt_sha256",
        "observation",
        "receipt_sha256",
    ];
    let receipt = runtime_object(value, "publication receipt", &keys)
        .map_err(|error| invalid(&error.to_string()))?;
    let observation = receipt.get("observation").unwrap_or(&Value::Null);
    validate_observation(observation)?;
    let sequence = receipt
        .get("sequence")
        .and_then(Value::as_u64)
        .filter(|value| matches!(*value, 1 | 2))
        .ok_or_else(|| invalid("receipt sequence is invalid"))?;
    let prior = receipt.get("prior_receipt_sha256").unwrap_or(&Value::Null);
    let receipt_sha256 = required_string(receipt, "receipt_sha256")?;
    if receipt.get("schema").and_then(Value::as_str) != Some(RUNTIME_RECEIPT_SCHEMA)
        || !runtime_hex(&required_string(receipt, "attempt_id")?, 64)
        || !runtime_relative_path(&required_string(receipt, "artifact_path")?)
        || !runtime_hex(&required_string(receipt, "artifact_sha256")?, 64)
        || !runtime_hex(&required_string(receipt, "materialization_id")?, 64)
        || !runtime_hex(&receipt_sha256, 64)
        || (sequence == 1 && !prior.is_null())
        || (sequence == 2
            && !prior
                .as_str()
                .map(|value| runtime_hex(value, 64))
                .unwrap_or(false))
        || [
            "attempt_id",
            "artifact_path",
            "artifact_sha256",
            "materialization_id",
            "sequence",
        ]
        .iter()
        .any(|field| receipt.get(*field) != observation.get(*field))
        || sha256(&receipt_canonical_bytes(value, true)?) != receipt_sha256
        || receipt_canonical_bytes(value, false)? != raw
    {
        return Err(invalid(
            "receipt values, hash, or canonical bytes are invalid",
        ));
    }
    Ok(())
}

fn load_latest_receipt(
    root: &Path,
    artifact_path: &Path,
    artifact_relative: &str,
    artifact_sha256: &str,
    materialization_id: &str,
    attempt_id: &str,
) -> Result<(String, Vec<u8>, Value), GraphError> {
    let run_dir = artifact_path
        .parent()
        .ok_or_else(|| runtime_boundary("runtime_receipt_invalid", "artifact parent is absent"))?;
    let unit = artifact_path
        .file_name()
        .and_then(|name| name.to_str())
        .and_then(runtime_event_name)
        .ok_or_else(|| runtime_boundary("runtime_receipt_invalid", "artifact unit is invalid"))?;
    let prefix = format!("runtime_event.{unit}.outcome.");
    let mut candidates = Vec::new();
    for entry in fs::read_dir(run_dir)
        .map_err(|error| runtime_boundary("runtime_receipt_invalid", error.to_string()))?
    {
        let entry = entry
            .map_err(|error| runtime_boundary("runtime_receipt_invalid", error.to_string()))?;
        let name = entry.file_name().into_string().map_err(|_| {
            runtime_boundary("runtime_receipt_invalid", "receipt name is not UTF-8")
        })?;
        if !name.starts_with(&prefix) {
            continue;
        }
        let metadata = fs::symlink_metadata(entry.path())
            .map_err(|error| runtime_boundary("runtime_receipt_invalid", error.to_string()))?;
        if !metadata.file_type().is_file() {
            return Err(runtime_boundary(
                "runtime_receipt_invalid",
                "receipt is a symlink or non-regular file",
            ));
        }
        let suffix = name
            .strip_prefix(&prefix)
            .and_then(|value| value.strip_suffix(".json"))
            .ok_or_else(|| {
                runtime_boundary("runtime_receipt_invalid", "receipt name is invalid")
            })?;
        let parts = suffix.split('.').collect::<Vec<_>>();
        if parts.len() != 2
            || parts[0] != attempt_id
            || !runtime_hex(parts[0], 64)
            || parts[1].len() != 6
            || !parts[1].bytes().all(|byte| byte.is_ascii_digit())
        {
            return Err(runtime_boundary(
                "runtime_receipt_invalid",
                "receipt attempt or basename is invalid",
            ));
        }
        let sequence = parts[1]
            .parse::<u8>()
            .ok()
            .filter(|value| matches!(*value, 1 | 2))
            .ok_or_else(|| {
                runtime_boundary("runtime_receipt_invalid", "receipt sequence is invalid")
            })?;
        let bytes = fs::read(entry.path())
            .map_err(|error| runtime_boundary("runtime_receipt_invalid", error.to_string()))?;
        if !bytes.ends_with(b"\n") || bytes.len() <= 1 || bytes[..bytes.len() - 1].contains(&b'\n')
        {
            return Err(runtime_boundary(
                "runtime_receipt_invalid",
                "receipt is not one canonical JSON line",
            ));
        }
        let value: Value = serde_json::from_slice(&bytes)
            .map_err(|error| runtime_boundary("runtime_receipt_invalid", error.to_string()))?;
        validate_receipt(&value, &bytes).map_err(|error| match error {
            GraphError::RuntimeBoundary { .. } => error,
            other => runtime_boundary("runtime_receipt_invalid", other.to_string()),
        })?;
        candidates.push((sequence, name, bytes, value));
    }
    candidates.sort_by_key(|item| item.0);
    if candidates.is_empty() {
        return Err(runtime_boundary(
            "runtime_receipt_missing",
            "runtime outcome receipt is absent",
        ));
    }
    if candidates.len() > 2
        || candidates
            .iter()
            .enumerate()
            .any(|(index, item)| item.0 as usize != index + 1)
    {
        return Err(runtime_boundary(
            "runtime_receipt_invalid",
            "receipt chain is duplicated or skips a sequence",
        ));
    }
    let mut prior_receipt: Option<String> = None;
    let mut prior_observation: Option<String> = None;
    let mut prior_outcome: Option<String> = None;
    for (sequence, _name, _bytes, value) in &candidates {
        let receipt = value.as_object().ok_or_else(|| {
            runtime_boundary("runtime_receipt_invalid", "receipt is not an object")
        })?;
        let observation = receipt
            .get("observation")
            .and_then(Value::as_object)
            .ok_or_else(|| {
                runtime_boundary("runtime_receipt_invalid", "receipt observation is absent")
            })?;
        if receipt.get("attempt_id").and_then(Value::as_str) != Some(attempt_id)
            || receipt.get("artifact_path").and_then(Value::as_str) != Some(artifact_relative)
            || receipt.get("artifact_sha256").and_then(Value::as_str) != Some(artifact_sha256)
            || receipt.get("materialization_id").and_then(Value::as_str) != Some(materialization_id)
            || receipt.get("sequence").and_then(Value::as_u64) != Some(*sequence as u64)
            || receipt.get("prior_receipt_sha256").and_then(Value::as_str)
                != prior_receipt.as_deref()
            || observation
                .get("prior_observation_sha256")
                .and_then(Value::as_str)
                != prior_observation.as_deref()
        {
            return Err(runtime_boundary(
                "runtime_receipt_invalid",
                "receipt chain identity or prior link is invalid",
            ));
        }
        let outcome = observation
            .get("outcome")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        if *sequence == 2
            && (prior_outcome.as_deref() != Some("uncertain") || outcome != "committed")
        {
            return Err(runtime_boundary(
                "runtime_receipt_invalid",
                "receipt transition is not uncertain-to-committed",
            ));
        }
        prior_receipt = receipt
            .get("receipt_sha256")
            .and_then(Value::as_str)
            .map(str::to_string);
        prior_observation = observation
            .get("observation_sha256")
            .and_then(Value::as_str)
            .map(str::to_string);
        prior_outcome = Some(outcome);
    }
    let (_sequence, name, bytes, value) = candidates.pop().unwrap();
    let outcome = value
        .get("observation")
        .and_then(|observation| observation.get("outcome"))
        .and_then(Value::as_str);
    if outcome != Some("committed") {
        return Err(runtime_boundary(
            "runtime_receipt_uncertain",
            "latest runtime outcome receipt is uncertain",
        ));
    }
    let receipt_relative = artifact_path
        .with_file_name(name)
        .strip_prefix(root)
        .map_err(|_| runtime_boundary("runtime_receipt_invalid", "receipt path escapes root"))?
        .to_str()
        .ok_or_else(|| runtime_boundary("runtime_receipt_invalid", "receipt path is not UTF-8"))?
        .replace('\\', "/");
    Ok((receipt_relative, bytes, value))
}

fn load_runtime_evidence_snapshot(root: &Path) -> Result<RuntimeEvidenceSnapshot, GraphError> {
    let (path, artifact_bytes) = active_runtime_event(root)
        .map_err(|error| runtime_boundary("runtime_evidence_changed", error.to_string()))?;
    if !artifact_bytes.ends_with(b"\n")
        || artifact_bytes[..artifact_bytes.len().saturating_sub(1)].contains(&b'\n')
        || artifact_bytes.len() <= 1
    {
        return Err(GraphError::Validation(
            "runtime-event certificate is not one canonical JSON line".to_string(),
        ));
    }
    let value: Value = serde_json::from_slice(&artifact_bytes)
        .map_err(|error| GraphError::Validation(format!("runtime-event JSON: {error}")))?;
    let object = runtime_object(
        &value,
        "certificate",
        &[
            "schema",
            "materialization_id",
            "result_family",
            "gate",
            "source_event",
            "result_artifact",
            "target_identities",
            "source_snapshot",
            "publication_intent",
            "artifact_sha256",
        ],
    )?;
    if object.get("schema").and_then(Value::as_str) != Some(RUNTIME_EVENT_SCHEMA) {
        return Err(GraphError::Validation(
            "runtime-event schema mismatch".to_string(),
        ));
    }
    let gate = runtime_object(
        object.get("gate").unwrap_or(&Value::Null),
        "gate",
        &["id", "result"],
    )?;
    let source_event = runtime_object(
        object.get("source_event").unwrap_or(&Value::Null),
        "source_event",
        &[
            "agent_id",
            "agent_context_id",
            "codex_thread_id",
            "parent_id",
            "turn_id",
            "role",
            "decision",
            "applicable_gate_result",
            "rollout_path",
            "rollout_path_bytes_b64",
            "rollout_path_sha256",
            "rollout_file_sha256",
            "record_line",
            "record_byte_offset",
            "record_byte_length",
            "record_bytes_b64",
            "record_sha256",
            "stable_record_id",
        ],
    )?;
    let artifact = runtime_object(
        object.get("result_artifact").unwrap_or(&Value::Null),
        "result_artifact",
        &[
            "path",
            "schema",
            "artifact_sha256",
            "artifact_blob_oid",
            "gate_id",
            "gate_result",
            "target_paths",
            "base_ref",
            "base_oid",
        ],
    )?;
    let snapshot = runtime_object(
        object.get("source_snapshot").unwrap_or(&Value::Null),
        "source_snapshot",
        &["head_oid", "base_ref", "base_oid", "porcelain_v1"],
    )?;
    let publication_intent_object = runtime_object(
        object.get("publication_intent").unwrap_or(&Value::Null),
        "publication_intent",
        &["schema", "attempt_id", "target_path", "prepared_state"],
    )?;

    let materialization_id = required_string(object, "materialization_id")?;
    let artifact_sha256 = required_string(object, "artifact_sha256")?;
    let result_family = required_string(object, "result_family")?;
    let (artifact_name, expected_gate_id, expected_schema) = runtime_family_spec(&result_family)
        .ok_or_else(|| GraphError::Validation("runtime result family is not finite".to_string()))?;
    let gate_id = required_string(gate, "id")?;
    let gate_result = required_string(gate, "result")?;
    if gate_id != expected_gate_id
        || !matches!(
            gate_result.as_str(),
            "APPROVE"
                | "REVISE"
                | "ESCALATE"
                | "PASS"
                | "FAIL"
                | "BLOCKED"
                | "READY"
                | "INCOMPLETE"
        )
        || artifact.get("gate_id").and_then(Value::as_str) != Some(gate_id.as_str())
        || artifact.get("gate_result").and_then(Value::as_str) != Some(gate_result.as_str())
        || artifact.get("schema").and_then(Value::as_str) != Some(expected_schema)
    {
        return Err(GraphError::Validation(
            "runtime result-family, gate, or schema authority mismatch".to_string(),
        ));
    }

    for field in [
        "agent_id",
        "agent_context_id",
        "codex_thread_id",
        "parent_id",
        "turn_id",
    ] {
        if !runtime_uuid(&required_string(source_event, field)?) {
            return Err(GraphError::Validation(format!(
                "runtime source event {field} is not a canonical UUID"
            )));
        }
    }
    let source_event_id = required_string(source_event, "stable_record_id")?;
    let source_event_sha256 = required_string(source_event, "record_sha256")?;
    let rollout_path = required_string(source_event, "rollout_path")?;
    let rollout_file_sha256 = required_string(source_event, "rollout_file_sha256")?;
    if required_string(source_event, "role")?.is_empty()
        || !matches!(
            required_string(source_event, "decision")?.as_str(),
            "APPROVE" | "REVISE" | "ESCALATE" | "NONE"
        )
        || source_event
            .get("applicable_gate_result")
            .and_then(Value::as_str)
            != Some(gate_result.as_str())
        || !runtime_absolute_path(&rollout_path)
        || source_event.get("record_line").and_then(Value::as_u64) != Some(872)
        || source_event
            .get("record_byte_offset")
            .and_then(Value::as_u64)
            .is_none()
    {
        return Err(GraphError::Validation(
            "runtime source event authority is invalid".to_string(),
        ));
    }
    let rollout_path_bytes =
        decode_base64(&required_string(source_event, "rollout_path_bytes_b64")?)?;
    let record_bytes = decode_base64(&required_string(source_event, "record_bytes_b64")?)?;
    let record_length = source_event
        .get("record_byte_length")
        .and_then(Value::as_u64)
        .filter(|value| *value > 0)
        .ok_or_else(|| GraphError::Validation("runtime record length is invalid".to_string()))?;
    let rollout_path_hash = sha256(&rollout_path_bytes);
    if rollout_path_bytes != rollout_path.as_bytes()
        || source_event
            .get("rollout_path_sha256")
            .and_then(Value::as_str)
            != Some(rollout_path_hash.as_str())
        || record_bytes.len() as u64 != record_length
        || source_event_sha256 != sha256(&record_bytes)
        || source_event_id != source_event_sha256
        || !runtime_hex(&rollout_file_sha256, 64)
    {
        return Err(GraphError::Validation(
            "runtime source byte identity mismatch".to_string(),
        ));
    }

    let source_head_oid = required_string(snapshot, "head_oid")?;
    let base_ref = required_string(snapshot, "base_ref")?;
    let base_oid = required_string(snapshot, "base_oid")?;
    let result_path = required_string(artifact, "path")?;
    let result_schema = required_string(artifact, "schema")?;
    let result_blob_oid = required_string(artifact, "artifact_blob_oid")?;
    if !runtime_hex(&materialization_id, 64)
        || !runtime_hex(&artifact_sha256, 64)
        || !runtime_hex(&required_string(artifact, "artifact_sha256")?, 64)
        || !runtime_hex(&result_blob_oid, 40)
        || !runtime_hex(&source_head_oid, 40)
        || !runtime_hex(&base_oid, 40)
        || snapshot.get("base_ref").and_then(Value::as_str)
            != artifact.get("base_ref").and_then(Value::as_str)
        || snapshot.get("base_oid").and_then(Value::as_str)
            != artifact.get("base_oid").and_then(Value::as_str)
    {
        return Err(GraphError::Validation(
            "runtime materialization, artifact, head, or base hash is invalid".to_string(),
        ));
    }
    let target_path_values = runtime_string_array(
        artifact.get("target_paths").unwrap_or(&Value::Null),
        "target_paths",
    )?;
    if target_path_values.is_empty()
        || target_path_values
            .iter()
            .any(|path| !runtime_relative_path(path))
        || target_path_values
            .windows(2)
            .any(|pair| pair[0].as_bytes() >= pair[1].as_bytes())
    {
        return Err(GraphError::Validation(
            "runtime target paths are empty, unsafe, duplicated, or unsorted".to_string(),
        ));
    }
    let target_paths = artifact.get("target_paths").cloned().unwrap_or(Value::Null);
    let porcelain_values = runtime_string_array(
        snapshot.get("porcelain_v1").unwrap_or(&Value::Null),
        "porcelain_v1",
    )?;
    for line in &porcelain_values {
        runtime_porcelain_paths(line)?;
    }
    let porcelain_v1 = snapshot.get("porcelain_v1").cloned().unwrap_or(Value::Null);
    let target_identities = object
        .get("target_identities")
        .and_then(Value::as_array)
        .ok_or_else(|| GraphError::Validation("target identities missing".to_string()))?;
    if target_identities.len() != target_path_values.len() || target_identities.is_empty() {
        return Err(GraphError::Validation(
            "runtime target identities do not match target paths".to_string(),
        ));
    }
    for (path_value, identity) in target_path_values.iter().zip(target_identities.iter()) {
        let identity = runtime_object(
            identity,
            "target identity",
            &[
                "path",
                "content_sha256",
                "git_blob_oid",
                "base_present",
                "base_content_sha256",
                "base_git_blob_oid",
            ],
        )?;
        let base_present = identity
            .get("base_present")
            .and_then(Value::as_bool)
            .ok_or_else(|| GraphError::Validation("runtime base_present is invalid".to_string()))?;
        if identity.get("path").and_then(Value::as_str) != Some(path_value.as_str())
            || !runtime_hex(&required_string(identity, "content_sha256")?, 64)
            || !runtime_hex(&required_string(identity, "git_blob_oid")?, 40)
            || (base_present
                && (!identity
                    .get("base_content_sha256")
                    .and_then(Value::as_str)
                    .map(|value| runtime_hex(value, 64))
                    .unwrap_or(false)
                    || !identity
                        .get("base_git_blob_oid")
                        .and_then(Value::as_str)
                        .map(|value| runtime_hex(value, 40))
                        .unwrap_or(false)))
            || (!base_present
                && (!identity
                    .get("base_content_sha256")
                    .unwrap_or(&Value::Null)
                    .is_null()
                    || !identity
                        .get("base_git_blob_oid")
                        .unwrap_or(&Value::Null)
                        .is_null()))
        {
            return Err(GraphError::Validation(
                "runtime target identity value is invalid".to_string(),
            ));
        }
    }

    let publication_intent = object
        .get("publication_intent")
        .cloned()
        .unwrap_or(Value::Null);
    let relative = path
        .strip_prefix(root)
        .map_err(|_| GraphError::Validation("runtime-event path escapes root".to_string()))?
        .to_str()
        .ok_or_else(|| GraphError::Validation("runtime-event path is not UTF-8".to_string()))?
        .replace('\\', "/");
    let run_name = path
        .parent()
        .and_then(Path::file_name)
        .and_then(|value| value.to_str())
        .ok_or_else(|| GraphError::Validation("runtime-event run id is invalid".to_string()))?;
    let event_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| GraphError::Validation("runtime-event filename is invalid".to_string()))?;
    let unit = runtime_event_name(event_name)
        .ok_or_else(|| GraphError::Validation("runtime-event filename is invalid".to_string()))?;
    let expected_result_path = format!("reports/agents/{run_name}/{artifact_name}");
    if !runtime_relative_path(&relative)
        || result_path != expected_result_path
        || publication_intent_object
            .get("target_path")
            .and_then(Value::as_str)
            != Some(relative.as_str())
        || unit != &source_event_sha256[..16]
        || publication_intent_object
            .get("schema")
            .and_then(Value::as_str)
            != Some(RUNTIME_PUBLICATION_INTENT_SCHEMA)
        || publication_intent_object
            .get("prepared_state")
            .and_then(Value::as_str)
            != Some("prepared")
    {
        return Err(GraphError::Validation(
            "runtime publication intent, run, unit, or result path is inconsistent".to_string(),
        ));
    }
    let attempt_id = required_string(publication_intent_object, "attempt_id")?;
    if !runtime_hex(&attempt_id, 64)
        || attempt_id != publication_attempt_id(&materialization_id, &relative)
    {
        return Err(GraphError::Validation(
            "runtime publication attempt identity is invalid".to_string(),
        ));
    }
    let materialization_preimage = runtime_materialization_preimage(&value)?;
    let expected_materialization = sha256(
        &[
            b"agent_canon.runtime_event.materialization.v1\0".as_slice(),
            materialization_preimage.as_slice(),
        ]
        .concat(),
    );
    let expected_artifact = sha256(&runtime_canonical_bytes(&value, true)?);
    if materialization_id != expected_materialization
        || artifact_sha256 != expected_artifact
        || runtime_canonical_bytes(&value, false)? != artifact_bytes
    {
        return Err(GraphError::Validation(
            "runtime artifact canonical hash coverage mismatch".to_string(),
        ));
    }
    let (receipt_path, receipt_bytes, receipt_value) = load_latest_receipt(
        root,
        &path,
        &relative,
        &artifact_sha256,
        &materialization_id,
        &attempt_id,
    )?;
    let receipt_object = receipt_value.as_object().ok_or_else(|| {
        runtime_boundary("runtime_receipt_invalid", "latest receipt is not an object")
    })?;
    let publication_observation = receipt_object.get("observation").cloned().ok_or_else(|| {
        runtime_boundary("runtime_receipt_invalid", "latest observation is absent")
    })?;
    let receipt_sha256 = required_string(receipt_object, "receipt_sha256")?;
    let receipt_sequence = receipt_object
        .get("sequence")
        .and_then(Value::as_u64)
        .and_then(|value| u8::try_from(value).ok())
        .ok_or_else(|| runtime_boundary("runtime_receipt_invalid", "latest sequence is invalid"))?;
    let receipt_outcome = publication_observation
        .get("outcome")
        .and_then(Value::as_str)
        .ok_or_else(|| runtime_boundary("runtime_receipt_invalid", "latest outcome is absent"))?
        .to_string();
    let live_identity_fingerprint =
        runtime_live_identity(root, artifact, snapshot, target_identities)?;
    let target_identities_value = object
        .get("target_identities")
        .cloned()
        .unwrap_or(Value::Null);
    let freshness_certificate = json!({"artifact_sha256":artifact_sha256,"receipt_sha256":receipt_sha256,"attempt_id":attempt_id,"receipt_sequence":receipt_sequence,"receipt_outcome":receipt_outcome,"source_head_oid":source_head_oid,"base_ref":base_ref,"base_oid":base_oid,"target_identities":target_identities_value,"live_identity_fingerprint":live_identity_fingerprint});
    Ok(RuntimeEvidenceSnapshot {
        artifact_path: relative,
        artifact_sha256,
        artifact_schema: RUNTIME_EVENT_SCHEMA.to_string(),
        materialization_id,
        attempt_id,
        receipt_path,
        receipt_sha256,
        receipt_schema: RUNTIME_RECEIPT_SCHEMA.to_string(),
        receipt_sequence,
        receipt_outcome,
        result_family,
        gate_id,
        gate_result,
        source_event_id,
        source_event_sha256,
        rollout_path,
        rollout_file_sha256,
        source_head_oid,
        base_ref,
        base_oid,
        result_path,
        result_schema,
        result_blob_oid,
        target_paths,
        porcelain_v1,
        publication_intent,
        publication_observation,
        target_identities: target_identities_value,
        freshness_certificate,
        live_identity_fingerprint,
        artifact_bytes,
        artifact_value: value,
        receipt_bytes,
        receipt_value,
    })
}

fn runtime_evidence_json(snapshot: &RuntimeEvidenceSnapshot) -> Value {
    debug_assert_eq!(
        snapshot
            .artifact_value
            .get("schema")
            .and_then(Value::as_str),
        Some(snapshot.artifact_schema.as_str())
    );
    debug_assert_eq!(
        snapshot.receipt_value.get("schema").and_then(Value::as_str),
        Some(snapshot.receipt_schema.as_str())
    );
    json!({"schema":RUNTIME_EVIDENCE_SCHEMA,"artifact_path":snapshot.artifact_path,"artifact_sha256":snapshot.artifact_sha256,"materialization_id":snapshot.materialization_id,"attempt_id":snapshot.attempt_id,"receipt_path":snapshot.receipt_path,"receipt_sha256":snapshot.receipt_sha256,"receipt_sequence":snapshot.receipt_sequence,"receipt_outcome":snapshot.receipt_outcome,"result_family":snapshot.result_family,"gate_id":snapshot.gate_id,"gate_result":snapshot.gate_result,"source_event_id":snapshot.source_event_id,"source_event_sha256":snapshot.source_event_sha256,"rollout_path":snapshot.rollout_path,"rollout_file_sha256":snapshot.rollout_file_sha256,"source_head_oid":snapshot.source_head_oid,"base_ref":snapshot.base_ref,"base_oid":snapshot.base_oid,"result_artifact":{"path":snapshot.result_path,"schema":snapshot.result_schema,"artifact_blob_oid":snapshot.result_blob_oid,"target_paths":snapshot.target_paths},"source_snapshot":{"head_oid":snapshot.source_head_oid,"base_ref":snapshot.base_ref,"base_oid":snapshot.base_oid,"porcelain_v1":snapshot.porcelain_v1},"publication_intent":snapshot.publication_intent,"publication_observation":snapshot.publication_observation,"target_identities":snapshot.target_identities,"freshness_certificate":snapshot.freshness_certificate,"artifact":snapshot.artifact_value,"receipt":snapshot.receipt_value})
}

fn runtime_evidence_producer(snapshot: &RuntimeEvidenceSnapshot) -> ProducerArtifact {
    ProducerArtifact {
        producer_id: "runtime-event-materializer".to_string(),
        version: "agent_canon.runtime_event.v1".to_string(),
        command: "tools/agent_tools/runtime_log_archive_git.py materialize-runtime-event"
            .to_string(),
        root: snapshot.rollout_path.clone(),
        content_sha256: sha256(&snapshot.artifact_bytes),
        relation_families: vec!["runtime-evidence".to_string()],
        artifact_ref: "runtime_event_materialization".to_string(),
        payload: snapshot.artifact_bytes.clone(),
    }
}

fn runtime_evidence_fingerprint(snapshot: &RuntimeEvidenceSnapshot) -> String {
    sha256(
        &[
            b"agent_canon.runtime_evidence_fingerprint.v2\0".as_slice(),
            snapshot.artifact_sha256.as_bytes(),
            b"\0".as_slice(),
            snapshot.receipt_sha256.as_bytes(),
            b"\0".as_slice(),
            snapshot.live_identity_fingerprint.as_bytes(),
        ]
        .concat(),
    )
}

fn graph_input_fingerprint(
    source_fingerprint: &str,
    source_head: &str,
    dirty_fingerprint: &str,
    runtime_fingerprint: &str,
    profile: &str,
) -> String {
    sha256(
        format!(
            "{source_fingerprint}\0{source_head}\0{dirty_fingerprint}\0{runtime_fingerprint}\0{profile}"
        )
        .as_bytes(),
    )
}

fn source_node(snapshot: &ManifestSnapshot, identity: &SourceIdentity) -> Value {
    let manifest = snapshot.manifests.get(&identity.repo_rel_path);
    json!({"id":format!("node:source:{}",identity.repo_rel_path),"layer":"source","kind":"file","path":identity.repo_rel_path,"label":identity.repo_rel_path,"payload":{"manifest_present":manifest.is_some(),"contract_kind":manifest.map(|value| value.contract_kind.clone()).unwrap_or_default(),"responsibility":manifest.map(|value| value.responsibility.clone()).unwrap_or_default(),"content_sha256":identity.content_hash,"source_identity_id":identity.identity_id,"git_blob_oid":identity.git_blob_or_gitlink}})
}

fn source_span_json(span: &SourceSpan) -> Value {
    json!({"path":span.path,"start_line":span.start_line,"start_column":span.start_column,"end_line":span.end_line,"end_column":span.end_column})
}

fn dependency_fact(
    snapshot: &ManifestSnapshot,
    declaration: &DependencyDeclaration,
) -> Option<Value> {
    let from = snapshot
        .source_identities
        .iter()
        .find(|identity| identity.identity_id == declaration.source_identity_id)
        .map(|identity| format!("node:source:{}", identity.repo_rel_path))
        .unwrap_or_else(|| format!("node:source:{}", declaration.source_identity_id));
    let to = declaration
        .resolved_target_identity_id
        .as_ref()
        .and_then(|id| {
            snapshot
                .source_identities
                .iter()
                .find(|identity| &identity.identity_id == id)
        })
        .map(|identity| format!("node:source:{}", identity.repo_rel_path));
    to.map(|target| json!({"id":format!("fact:dependency:{}",declaration.declaration_id),"layer":"source","kind":"dependency","inferred":false,"from":from,"to":target,"producer":"source-snapshot","source_path":declaration.source_span.path,"source_span":source_span_json(&declaration.source_span),"evidence_ref":format!("{}:{}",declaration.source_span.path,declaration.source_span.start_line),"authority":"ManifestParser","dependency_detail":{"direction":declaration.declared_direction,"kind":declaration.declared_kind,"reason":declaration.reason}}))
}

fn graph_fingerprint(
    nodes: &[Value],
    facts: &[Value],
    runtime: &RuntimeEvidenceSnapshot,
) -> String {
    let value = json!({"nodes":nodes,"facts":facts,"runtime":runtime_evidence_json(runtime)});
    sha256(serde_json::to_string(&value).unwrap_or_default().as_bytes())
}

fn capture_runtime_dashboard(snapshot: &RuntimeEvidenceSnapshot) -> ProducerArtifact {
    runtime_evidence_producer(snapshot)
}

fn collect_build_material(root: &Path, profile: &str) -> Result<BuildMaterial, GraphError> {
    collect_build_material_with_mode(root, profile, false)
}

fn collect_build_material_with_mode(
    root: &Path,
    profile: &str,
    _probe: bool,
) -> Result<BuildMaterial, GraphError> {
    let runtime_evidence = load_runtime_evidence_snapshot(root)?;
    let snapshot_request = SnapshotRequest {
        root: root.to_path_buf(),
        profile: "parent".to_string(),
        output_jsonl: root.join(".agent-canon/knowledge-graph/source_snapshot.jsonl"),
    };
    let snapshot = capture_snapshot(&snapshot_request)
        .map_err(|error| GraphError::Validation(error.to_string()))?;
    fs::create_dir_all(root.join(".agent-canon/knowledge-graph"))
        .map_err(|error| GraphError::Io(error.to_string()))?;
    let mut snapshot_file = File::create(&snapshot_request.output_jsonl)
        .map_err(|error| GraphError::Io(error.to_string()))?;
    write_snapshot_jsonl(&snapshot, &mut snapshot_file)
        .map_err(|error| GraphError::Io(error.to_string()))?;
    let eligible = snapshot
        .source_universe
        .eligible_paths
        .iter()
        .map(String::as_str)
        .collect::<std::collections::BTreeSet<_>>();
    let nodes = snapshot
        .source_identities
        .iter()
        .filter(|identity| eligible.contains(identity.repo_rel_path.as_str()))
        .map(|identity| source_node(&snapshot, identity))
        .collect::<Vec<_>>();
    let facts = snapshot
        .declarations
        .iter()
        .filter_map(|declaration| dependency_fact(&snapshot, declaration))
        .collect::<Vec<_>>();
    let runtime_fp = runtime_evidence_fingerprint(&runtime_evidence);
    let input_fingerprint = graph_input_fingerprint(
        &snapshot.header.source_fingerprint,
        &snapshot.header.git_head,
        &snapshot.header.git_status_hash,
        &runtime_fp,
        profile,
    );
    let graph_fingerprint = graph_fingerprint(&nodes, &facts, &runtime_evidence);
    let producer = capture_runtime_dashboard(&runtime_evidence);
    Ok(BuildMaterial {
        root: root.to_path_buf(),
        graph_root: root.join(".agent-canon/knowledge-graph"),
        profile: profile.to_string(),
        snapshot,
        runtime_evidence,
        nodes,
        facts,
        producer_artifacts: vec![producer],
        input_fingerprint,
        graph_fingerprint,
    })
}

fn metadata(connection: &Connection, key: &str) -> Result<String, GraphError> {
    connection
        .query_row(
            "SELECT value FROM metadata WHERE key=?1",
            params![key],
            |row| row.get(0),
        )
        .map_err(|error| GraphError::Unavailable(error.to_string()))
}

fn metadata_optional(connection: &Connection, key: &str) -> Result<Option<String>, GraphError> {
    connection
        .query_row(
            "SELECT value FROM metadata WHERE key=?1",
            params![key],
            |row| row.get(0),
        )
        .optional()
        .map_err(|error| GraphError::Unavailable(error.to_string()))
}

fn materialize_graph_store(material: &BuildMaterial) -> Result<GraphIntegrationRecord, GraphError> {
    fs::create_dir_all(&material.graph_root).map_err(|error| GraphError::Io(error.to_string()))?;
    let temporary = material
        .graph_root
        .join(format!("graph.sqlite.tmp.{}", std::process::id()));
    let _ = fs::remove_file(&temporary);
    let connection =
        Connection::open(&temporary).map_err(|error| GraphError::Io(error.to_string()))?;
    initialize_graph_schema(&connection).map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute("DELETE FROM metadata", [])
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute("DELETE FROM documents", [])
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute("DELETE FROM nodes", [])
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute("DELETE FROM edges", [])
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection.execute("INSERT INTO documents(id,path,title,kind,created_at) VALUES('doc:source','.', 'AgentCanon source', 'source', datetime('now'))", []).map_err(|error| GraphError::Io(error.to_string()))?;
    for node in &material.nodes {
        let id = node.get("id").and_then(Value::as_str).unwrap_or_default();
        let path = node.get("path").and_then(Value::as_str).unwrap_or_default();
        connection.execute("INSERT INTO nodes(id,document_id,layer,kind,label,text,source_start,source_end,confidence,payload_json) VALUES(?1,'doc:source','source','file',?2,?2,0,0,1.0,?3)", params![id, path, serde_json::to_string(node).unwrap_or_default()]).map_err(|error| GraphError::Io(error.to_string()))?;
    }
    for fact in &material.facts {
        let id = fact.get("id").and_then(Value::as_str).unwrap_or_default();
        let from = fact.get("from").and_then(Value::as_str).unwrap_or_default();
        let to = fact.get("to").and_then(Value::as_str).unwrap_or_default();
        connection.execute("INSERT INTO edges(id,layer,kind,from_node_id,to_node_id,order_kind,confidence,evidence_node_id,payload_json) VALUES(?1,'source','dependency',?2,?3,'none',1.0,NULL,?4)", params![id, from, to, serde_json::to_string(fact).unwrap_or_default()]).map_err(|error| GraphError::Io(error.to_string()))?;
    }
    for diagnostic in &material.snapshot.diagnostics {
        let target_node = diagnostic
            .source_span
            .as_ref()
            .map(|span| format!("node:source:{}", span.path))
            .unwrap_or_default();
        let id = format!("diagnostic:{}", sha256(diagnostic.message.as_bytes()));
        connection.execute("INSERT INTO diagnostics(id,layer,target_node_id,target_edge_id,severity,rule,message,suggested_action_json) VALUES(?1,'source',?2,'',?3,?4,?5,'{}')", params![id, target_node, if diagnostic.severity == "error" { "blocker" } else { diagnostic.severity.as_str() }, diagnostic.code, diagnostic.message]).map_err(|error| GraphError::Io(error.to_string()))?;
    }
    let runtime_json = runtime_evidence_json(&material.runtime_evidence);
    let runtime_artifact = String::from_utf8(material.runtime_evidence.artifact_bytes.clone())
        .map_err(|error| GraphError::Validation(error.to_string()))?;
    let runtime_receipt = String::from_utf8(material.runtime_evidence.receipt_bytes.clone())
        .map_err(|error| GraphError::Validation(error.to_string()))?;
    let producer_json = serde_json::to_string(
        &material
            .producer_artifacts
            .iter()
            .map(ProducerArtifact::json)
            .collect::<Vec<_>>(),
    )
    .unwrap_or_default();
    let integration = GraphIntegrationRecord {
        root: material.root.display().to_string(),
        db_path: material
            .graph_root
            .join("graph.sqlite")
            .display()
            .to_string(),
        profile: material.profile.clone(),
        source_snapshot_profile: "parent".to_string(),
        snapshot_head: material.snapshot.header.git_head.clone(),
        input_fingerprint: material.input_fingerprint.clone(),
        graph_fingerprint: material.graph_fingerprint.clone(),
        contract_fingerprint: GRAPH_SCHEMA_VERSION.to_string(),
        producer_artifacts: material.producer_artifacts.clone(),
        runtime_evidence: runtime_json.clone(),
        verified: true,
        verification_code: "runtime-evidence-readback-v2".to_string(),
    };
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('integration_record',?1)",
            params![serde_json::to_string(&integration.json()).unwrap_or_default()],
        )
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('runtime_event_materialization',?1)",
            params![serde_json::to_string(&runtime_json).unwrap_or_default()],
        )
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('runtime_event_artifact',?1)",
            params![runtime_artifact],
        )
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('runtime_event_artifact_sha256',?1)",
            params![sha256(&material.runtime_evidence.artifact_bytes)],
        )
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('runtime_event_outcome_receipt',?1)",
            params![runtime_receipt],
        )
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('runtime_event_outcome_receipt_sha256',?1)",
            params![sha256(&material.runtime_evidence.receipt_bytes)],
        )
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('runtime_live_identity_fingerprint',?1)",
            params![material.runtime_evidence.live_identity_fingerprint],
        )
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('snapshot_head',?1)",
            params![material.snapshot.header.git_head],
        )
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('dirty_fingerprint',?1)",
            params![material.snapshot.header.git_status_hash],
        )
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('source_fingerprint',?1)",
            params![material.snapshot.header.source_fingerprint],
        )
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('input_fingerprint',?1)",
            params![material.input_fingerprint],
        )
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('graph_fingerprint',?1)",
            params![material.graph_fingerprint],
        )
        .map_err(|error| GraphError::Io(error.to_string()))?;
    connection
        .execute(
            "INSERT INTO metadata(key,value) VALUES('producer_artifacts',?1)",
            params![producer_json],
        )
        .map_err(|error| GraphError::Io(error.to_string()))?;
    validate_graph_connection(&connection)
        .map_err(|error| GraphError::Validation(error.to_string()))?;
    drop(connection);
    let published = material.graph_root.join("graph.sqlite");
    fs::rename(&temporary, &published).map_err(|error| GraphError::Io(error.to_string()))?;
    File::open(&published)
        .and_then(|file| file.sync_all())
        .map_err(|error| GraphError::Io(error.to_string()))?;
    File::open(&material.graph_root)
        .and_then(|directory| directory.sync_all())
        .map_err(|error| GraphError::Io(error.to_string()))?;
    let readback = Connection::open_with_flags(&published, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|error| GraphError::Unavailable(error.to_string()))?;
    validate_graph_connection(&readback)
        .map_err(|error| GraphError::Validation(error.to_string()))?;
    let expected_integration = serde_json::to_string(&integration.json()).unwrap_or_default();
    if metadata(&readback, "integration_record")? != expected_integration
        || metadata(&readback, "runtime_event_materialization")?
            != serde_json::to_string(&runtime_json).unwrap_or_default()
        || metadata(&readback, "runtime_event_artifact")?
            != String::from_utf8(material.runtime_evidence.artifact_bytes.clone())
                .map_err(|error| GraphError::Validation(error.to_string()))?
        || metadata(&readback, "runtime_event_artifact_sha256")?
            != sha256(&material.runtime_evidence.artifact_bytes)
        || metadata(&readback, "runtime_event_outcome_receipt")?
            != String::from_utf8(material.runtime_evidence.receipt_bytes.clone())
                .map_err(|error| GraphError::Validation(error.to_string()))?
        || metadata(&readback, "runtime_event_outcome_receipt_sha256")?
            != sha256(&material.runtime_evidence.receipt_bytes)
        || metadata(&readback, "runtime_live_identity_fingerprint")?
            != material.runtime_evidence.live_identity_fingerprint
        || metadata(&readback, "input_fingerprint")? != material.input_fingerprint
        || metadata(&readback, "graph_fingerprint")? != material.graph_fingerprint
        || metadata(&readback, "snapshot_head")? != material.snapshot.header.git_head
        || metadata(&readback, "dirty_fingerprint")? != material.snapshot.header.git_status_hash
        || metadata(&readback, "source_fingerprint")? != material.snapshot.header.source_fingerprint
    {
        return Err(GraphError::Validation(
            "persisted graph/runtime certificate readback mismatch".to_string(),
        ));
    }
    Ok(integration)
}

fn parse_args(args: &[String]) -> Result<GraphArgs, GraphError> {
    let mut result = GraphArgs {
        root: PathBuf::from("."),
        profile: "default".to_string(),
        format: "text".to_string(),
        path: None,
        all: false,
        relation: "dependency".to_string(),
        direction: "both".to_string(),
        depth: 0,
        token: None,
    };
    let mut index = 0;
    while index < args.len() {
        let flag = args[index].as_str();
        let value = |index: &mut usize| -> Result<String, GraphError> {
            *index += 1;
            args.get(*index)
                .cloned()
                .ok_or_else(|| GraphError::Usage(format!("missing value for {flag}")))
        };
        match flag {
            "--root" => result.root = PathBuf::from(value(&mut index)?),
            "--profile" => result.profile = value(&mut index)?,
            "--format" => result.format = value(&mut index)?,
            "--path" => result.path = Some(value(&mut index)?),
            "--all" => result.all = true,
            "--relation" => result.relation = value(&mut index)?,
            "--direction" => result.direction = value(&mut index)?,
            "--depth" => {
                result.depth = value(&mut index)?
                    .parse()
                    .map_err(|_| GraphError::Usage("invalid depth".to_string()))?
            }
            "--token" => result.token = Some(value(&mut index)?),
            "--help" | "-h" => {
                return Err(GraphError::Usage(
                    "graph <build|status|query|context> [--root PATH] [--format json]".to_string(),
                ))
            }
            unknown => return Err(GraphError::Usage(format!("unknown graph option {unknown}"))),
        }
        index += 1;
    }
    if !matches!(result.format.as_str(), "text" | "json") {
        return Err(GraphError::Usage("format must be text or json".to_string()));
    }
    Ok(result)
}

fn open_db(root: &Path) -> Result<Connection, GraphError> {
    let path = root.join(".agent-canon/knowledge-graph/graph.sqlite");
    Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|error| GraphError::Unavailable(error.to_string()))
}

fn load_graph_records(root: &Path) -> Result<(Vec<Value>, Vec<Value>), GraphError> {
    let connection = open_db(root)?;
    let mut nodes = Vec::new();
    let mut statement = connection
        .prepare("SELECT payload_json FROM nodes ORDER BY id")
        .map_err(|error| GraphError::Io(error.to_string()))?;
    let rows = statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(|error| GraphError::Io(error.to_string()))?;
    for row in rows {
        nodes.push(
            serde_json::from_str(&row.map_err(|error| GraphError::Io(error.to_string()))?)
                .map_err(|error| GraphError::Validation(error.to_string()))?,
        );
    }
    let mut facts = Vec::new();
    let mut statement = connection
        .prepare("SELECT payload_json FROM edges ORDER BY id")
        .map_err(|error| GraphError::Io(error.to_string()))?;
    let rows = statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(|error| GraphError::Io(error.to_string()))?;
    for row in rows {
        facts.push(
            serde_json::from_str(&row.map_err(|error| GraphError::Io(error.to_string()))?)
                .map_err(|error| GraphError::Validation(error.to_string()))?,
        );
    }
    Ok((nodes, facts))
}

fn persisted_input_identity(
    values: &BTreeMap<String, String>,
    integration: &Value,
) -> Result<PersistedInputIdentity, GraphError> {
    let mismatch =
        |detail: &str| runtime_boundary("persisted_readback_mismatch", detail.to_string());
    let required = |key: &str| {
        values
            .get(key)
            .cloned()
            .ok_or_else(|| mismatch(&format!("metadata {key} is absent")))
    };
    let materialization_text = required("runtime_event_materialization")?;
    let artifact_text = required("runtime_event_artifact")?;
    let artifact_bytes_sha = required("runtime_event_artifact_sha256")?;
    let receipt_text = required("runtime_event_outcome_receipt")?;
    let receipt_bytes_sha = required("runtime_event_outcome_receipt_sha256")?;
    let live_identity_fingerprint = required("runtime_live_identity_fingerprint")?;
    if sha256(artifact_text.as_bytes()) != artifact_bytes_sha
        || sha256(receipt_text.as_bytes()) != receipt_bytes_sha
    {
        return Err(mismatch("persisted runtime byte hash is invalid"));
    }
    let materialization: Value = serde_json::from_str(&materialization_text)
        .map_err(|_| mismatch("runtime materialization JSON is invalid"))?;
    let artifact: Value = serde_json::from_str(&artifact_text)
        .map_err(|_| mismatch("runtime artifact JSON is invalid"))?;
    let receipt: Value = serde_json::from_str(&receipt_text)
        .map_err(|_| mismatch("runtime receipt JSON is invalid"))?;
    if runtime_canonical_bytes(&artifact, false)
        .map_err(|_| mismatch("persisted artifact schema is invalid"))?
        != artifact_text.as_bytes()
    {
        return Err(mismatch("persisted artifact bytes are not canonical"));
    }
    let artifact_object = artifact
        .as_object()
        .ok_or_else(|| mismatch("persisted artifact is not an object"))?;
    let artifact_sha256 = required_string(artifact_object, "artifact_sha256")
        .map_err(|_| mismatch("persisted artifact self hash is absent"))?;
    if sha256(
        &runtime_canonical_bytes(&artifact, true)
            .map_err(|_| mismatch("persisted artifact preimage is invalid"))?,
    ) != artifact_sha256
    {
        return Err(mismatch("persisted artifact self hash is invalid"));
    }
    validate_receipt(&receipt, receipt_text.as_bytes())
        .map_err(|_| mismatch("persisted receipt is invalid"))?;
    let receipt_object = receipt
        .as_object()
        .ok_or_else(|| mismatch("persisted receipt is not an object"))?;
    let receipt_sha256 = required_string(receipt_object, "receipt_sha256")
        .map_err(|_| mismatch("persisted receipt self hash is absent"))?;
    let artifact_materialization_id = required_string(artifact_object, "materialization_id")
        .map_err(|_| mismatch("persisted materialization id is absent"))?;
    let expected_materialization_id = sha256(
        &[
            b"agent_canon.runtime_event.materialization.v1\0".as_slice(),
            runtime_materialization_preimage(&artifact)
                .map_err(|_| mismatch("persisted materialization preimage is invalid"))?
                .as_slice(),
        ]
        .concat(),
    );
    let publication_intent = artifact
        .get("publication_intent")
        .and_then(Value::as_object)
        .ok_or_else(|| mismatch("persisted publication intent is absent"))?;
    let artifact_path = required_string(publication_intent, "target_path")
        .map_err(|_| mismatch("persisted artifact path is absent"))?;
    let attempt_id = required_string(publication_intent, "attempt_id")
        .map_err(|_| mismatch("persisted attempt id is absent"))?;
    if artifact_materialization_id != expected_materialization_id
        || attempt_id != publication_attempt_id(&artifact_materialization_id, &artifact_path)
    {
        return Err(mismatch(
            "persisted materialization or attempt identity is invalid",
        ));
    }
    let receipt_sequence = receipt_object
        .get("sequence")
        .and_then(Value::as_u64)
        .ok_or_else(|| mismatch("persisted receipt sequence is absent"))?;
    let receipt_path = artifact_path
        .strip_suffix(".json")
        .map(|prefix| format!("{prefix}.outcome.{attempt_id}.{receipt_sequence:06}.json"))
        .ok_or_else(|| mismatch("persisted artifact path is invalid"))?;
    let source_event = artifact
        .get("source_event")
        .and_then(Value::as_object)
        .ok_or_else(|| mismatch("persisted source event is absent"))?;
    let result_artifact = artifact
        .get("result_artifact")
        .and_then(Value::as_object)
        .ok_or_else(|| mismatch("persisted result artifact is absent"))?;
    let source_snapshot = artifact
        .get("source_snapshot")
        .and_then(Value::as_object)
        .ok_or_else(|| mismatch("persisted source snapshot is absent"))?;
    let observation = receipt_object
        .get("observation")
        .cloned()
        .ok_or_else(|| mismatch("persisted publication observation is absent"))?;
    let receipt_outcome = observation
        .get("outcome")
        .and_then(Value::as_str)
        .ok_or_else(|| mismatch("persisted receipt outcome is absent"))?;
    if !runtime_hex(&live_identity_fingerprint, 64) {
        return Err(mismatch("persisted live identity fingerprint is invalid"));
    }
    let target_identities = artifact
        .get("target_identities")
        .cloned()
        .ok_or_else(|| mismatch("persisted target identities are absent"))?;
    let freshness = json!({
        "artifact_sha256": artifact_sha256,
        "receipt_sha256": receipt_sha256,
        "attempt_id": attempt_id,
        "receipt_sequence": receipt_sequence,
        "receipt_outcome": receipt_outcome,
        "source_head_oid": source_snapshot.get("head_oid").cloned().unwrap_or(Value::Null),
        "base_ref": source_snapshot.get("base_ref").cloned().unwrap_or(Value::Null),
        "base_oid": source_snapshot.get("base_oid").cloned().unwrap_or(Value::Null),
        "target_identities": target_identities,
        "live_identity_fingerprint": live_identity_fingerprint,
    });
    let expected_materialization = json!({
        "schema": RUNTIME_EVIDENCE_SCHEMA,
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha256,
        "materialization_id": artifact_materialization_id,
        "attempt_id": attempt_id,
        "receipt_path": receipt_path,
        "receipt_sha256": receipt_sha256,
        "receipt_sequence": receipt_sequence,
        "receipt_outcome": receipt_outcome,
        "result_family": artifact.get("result_family").cloned().unwrap_or(Value::Null),
        "gate_id": artifact.get("gate").and_then(|value| value.get("id")).cloned().unwrap_or(Value::Null),
        "gate_result": artifact.get("gate").and_then(|value| value.get("result")).cloned().unwrap_or(Value::Null),
        "source_event_id": source_event.get("stable_record_id").cloned().unwrap_or(Value::Null),
        "source_event_sha256": source_event.get("record_sha256").cloned().unwrap_or(Value::Null),
        "rollout_path": source_event.get("rollout_path").cloned().unwrap_or(Value::Null),
        "rollout_file_sha256": source_event.get("rollout_file_sha256").cloned().unwrap_or(Value::Null),
        "source_head_oid": source_snapshot.get("head_oid").cloned().unwrap_or(Value::Null),
        "base_ref": source_snapshot.get("base_ref").cloned().unwrap_or(Value::Null),
        "base_oid": source_snapshot.get("base_oid").cloned().unwrap_or(Value::Null),
        "result_artifact": {
            "path": result_artifact.get("path").cloned().unwrap_or(Value::Null),
            "schema": result_artifact.get("schema").cloned().unwrap_or(Value::Null),
            "artifact_blob_oid": result_artifact.get("artifact_blob_oid").cloned().unwrap_or(Value::Null),
            "target_paths": result_artifact.get("target_paths").cloned().unwrap_or(Value::Null),
        },
        "source_snapshot": {
            "head_oid": source_snapshot.get("head_oid").cloned().unwrap_or(Value::Null),
            "base_ref": source_snapshot.get("base_ref").cloned().unwrap_or(Value::Null),
            "base_oid": source_snapshot.get("base_oid").cloned().unwrap_or(Value::Null),
            "porcelain_v1": source_snapshot.get("porcelain_v1").cloned().unwrap_or(Value::Null),
        },
        "publication_intent": artifact.get("publication_intent").cloned().unwrap_or(Value::Null),
        "publication_observation": observation,
        "target_identities": artifact.get("target_identities").cloned().unwrap_or(Value::Null),
        "freshness_certificate": freshness,
        "artifact": artifact,
        "receipt": receipt,
    });
    let materialization_object = runtime_object(
        &materialization,
        "runtime evidence snapshot",
        &[
            "schema",
            "artifact_path",
            "artifact_sha256",
            "materialization_id",
            "attempt_id",
            "receipt_path",
            "receipt_sha256",
            "receipt_sequence",
            "receipt_outcome",
            "result_family",
            "gate_id",
            "gate_result",
            "source_event_id",
            "source_event_sha256",
            "rollout_path",
            "rollout_file_sha256",
            "source_head_oid",
            "base_ref",
            "base_oid",
            "result_artifact",
            "source_snapshot",
            "publication_intent",
            "publication_observation",
            "target_identities",
            "freshness_certificate",
            "artifact",
            "receipt",
        ],
    )
    .map_err(|_| mismatch("runtime materialization fields are invalid"))?;
    runtime_object(
        materialization_object
            .get("freshness_certificate")
            .unwrap_or(&Value::Null),
        "freshness certificate",
        &[
            "artifact_sha256",
            "receipt_sha256",
            "attempt_id",
            "receipt_sequence",
            "receipt_outcome",
            "source_head_oid",
            "base_ref",
            "base_oid",
            "target_identities",
            "live_identity_fingerprint",
        ],
    )
    .map_err(|_| mismatch("freshness certificate is absent or malformed"))?;
    let integration_runtime = integration
        .get("runtime_evidence")
        .ok_or_else(|| mismatch("integration runtime evidence is absent"))?;
    if materialization_object.get("schema").and_then(Value::as_str) != Some(RUNTIME_EVIDENCE_SCHEMA)
        || integration_runtime != &materialization
        || materialization != expected_materialization
        || receipt_outcome != "committed"
        || integration.get("verified").and_then(Value::as_bool) != Some(true)
    {
        return Err(mismatch("persisted runtime values disagree"));
    }
    let input_fingerprint = required("input_fingerprint")?;
    let source_fingerprint = required("source_fingerprint")?;
    let source_head_oid = required("snapshot_head")?;
    let dirty_fingerprint = required("dirty_fingerprint")?;
    let profile = integration
        .get("profile")
        .and_then(Value::as_str)
        .ok_or_else(|| mismatch("persisted profile is absent"))?
        .to_string();
    if integration.get("input_fingerprint").and_then(Value::as_str)
        != Some(input_fingerprint.as_str())
        || integration.get("snapshot_head").and_then(Value::as_str)
            != Some(source_head_oid.as_str())
    {
        return Err(mismatch("persisted graph identity disagrees"));
    }
    Ok(PersistedInputIdentity {
        input_fingerprint,
        artifact_sha256,
        receipt_sha256,
        live_identity_fingerprint,
        source_fingerprint,
        source_head_oid,
        dirty_fingerprint,
        profile,
    })
}

fn probe_input_fingerprint(
    root: &Path,
    profile: &str,
) -> Result<InputFingerprintProbe, GraphError> {
    let source = probe_snapshot_identity(root, "parent")
        .map_err(|error| GraphError::Validation(error.to_string()))?;
    let base = InputFingerprintProbe {
        input_fingerprint: None,
        artifact_sha256: None,
        receipt_sha256: None,
        live_identity_fingerprint: None,
        source_fingerprint: source.source_fingerprint,
        source_head_oid: source.git_head,
        dirty_fingerprint: source.git_status_hash,
        profile: profile.to_string(),
        reason: None,
    };
    match load_runtime_evidence_snapshot(root) {
        Ok(runtime) => {
            let runtime_fingerprint = runtime_evidence_fingerprint(&runtime);
            Ok(InputFingerprintProbe {
                input_fingerprint: Some(graph_input_fingerprint(
                    &base.source_fingerprint,
                    &base.source_head_oid,
                    &base.dirty_fingerprint,
                    &runtime_fingerprint,
                    profile,
                )),
                artifact_sha256: Some(runtime.artifact_sha256),
                receipt_sha256: Some(runtime.receipt_sha256),
                live_identity_fingerprint: Some(runtime.live_identity_fingerprint),
                ..base
            })
        }
        Err(GraphError::RuntimeBoundary { reason, .. }) => Ok(InputFingerprintProbe {
            reason: Some(reason),
            ..base
        }),
        Err(_error) => Ok(InputFingerprintProbe {
            reason: Some("runtime_evidence_changed".to_string()),
            ..base
        }),
    }
}

fn read_graph_status(args: &GraphArgs) -> Result<Value, GraphError> {
    let root = args
        .root
        .canonicalize()
        .map_err(|error| GraphError::Io(error.to_string()))?;
    let connection = open_db(&root)?;
    let keys = [
        "integration_record",
        "runtime_event_materialization",
        "runtime_event_artifact",
        "runtime_event_artifact_sha256",
        "runtime_event_outcome_receipt",
        "runtime_event_outcome_receipt_sha256",
        "runtime_live_identity_fingerprint",
        "input_fingerprint",
        "source_fingerprint",
        "snapshot_head",
        "dirty_fingerprint",
        "graph_fingerprint",
    ];
    let mut values = BTreeMap::new();
    for key in keys {
        if let Some(value) = metadata_optional(&connection, key)? {
            values.insert(key.to_string(), value);
        }
    }
    let integration = values
        .get("integration_record")
        .and_then(|value| serde_json::from_str::<Value>(value).ok())
        .unwrap_or(Value::Null);
    let persisted_result = persisted_input_identity(&values, &integration);
    let persisted_mismatch = persisted_result.is_err();
    let persisted = persisted_result.unwrap_or_default();
    let probe = probe_input_fingerprint(&root, &args.profile)?;
    let probe_reason = if persisted_mismatch {
        Some("persisted_readback_mismatch".to_string())
    } else if matches!(
        probe.reason.as_deref(),
        Some("runtime_receipt_invalid" | "runtime_receipt_missing" | "runtime_receipt_uncertain")
    ) {
        probe.reason.clone()
    } else if probe.reason.as_deref() == Some("runtime_evidence_changed")
        || (probe.reason.is_none()
            && (probe.artifact_sha256.as_deref() != Some(persisted.artifact_sha256.as_str())
                || probe.receipt_sha256.as_deref() != Some(persisted.receipt_sha256.as_str())))
    {
        Some("runtime_evidence_changed".to_string())
    } else if probe.reason.as_deref() == Some("source_changed")
        || probe.live_identity_fingerprint.as_deref()
            != Some(persisted.live_identity_fingerprint.as_str())
        || probe.source_fingerprint != persisted.source_fingerprint
        || probe.source_head_oid != persisted.source_head_oid
        || probe.dirty_fingerprint != persisted.dirty_fingerprint
    {
        Some("source_changed".to_string())
    } else if probe.profile != persisted.profile
        || probe.input_fingerprint.as_deref() != Some(persisted.input_fingerprint.as_str())
    {
        Some("runtime_evidence_changed".to_string())
    } else {
        None
    };
    let fresh = probe_reason.is_none();
    Ok(
        json!({"schema":"agent-canon.graph.status.v1","command":"status","status":if fresh {"fresh"} else {"stale"},"profile":args.profile,"root":root,"db_path":root.join(".agent-canon/knowledge-graph/graph.sqlite"),"input_fingerprint":persisted.input_fingerprint,"graph_fingerprint":integration.get("graph_fingerprint"),"integration_record":integration,"probe_reason":probe_reason,"reason":probe_reason,"exit_code":if fresh {0} else {2}}),
    )
}

fn query_graph(args: &GraphArgs) -> Result<Value, GraphError> {
    let status = read_graph_status(args)?;
    if status.get("status").and_then(Value::as_str) != Some("fresh") {
        return Ok(
            json!({"schema":"agent-canon.graph.query.v1","command":"query","status":status["status"],"profile":args.profile,"root":args.root,"path":args.path,"all":args.all,"relation":args.relation,"direction":args.direction,"depth":args.depth,"nodes":[],"facts":[],"reason":status["reason"],"exit_code":2}),
        );
    }
    let root = args
        .root
        .canonicalize()
        .map_err(|error| GraphError::Io(error.to_string()))?;
    let (all_nodes, all_facts) = load_graph_records(&root)?;
    let nodes = all_nodes
        .into_iter()
        .filter(|value| {
            args.path
                .as_ref()
                .map(|path| value.get("path").and_then(Value::as_str) == Some(path))
                .unwrap_or(true)
                || args.all
        })
        .collect::<Vec<_>>();
    let facts = all_facts
        .into_iter()
        .filter(|value| {
            args.relation == "all"
                || value.get("kind").and_then(Value::as_str) == Some(args.relation.as_str())
        })
        .collect::<Vec<_>>();
    Ok(
        json!({"schema":"agent-canon.graph.query.v1","command":"query","status":"fresh","profile":args.profile,"root":root,"path":args.path,"all":args.all,"relation":args.relation,"direction":args.direction,"depth":args.depth,"graph_fingerprint":status["graph_fingerprint"],"nodes":nodes,"facts":facts,"reason":Value::Null,"exit_code":0}),
    )
}

fn context_graph(args: &GraphArgs) -> Result<Value, GraphError> {
    let status = read_graph_status(args)?;
    if status.get("status").and_then(Value::as_str) != Some("fresh") {
        return Ok(
            json!({"schema":"agent-canon.graph.context.v1","command":"context","status":status["status"],"profile":args.profile,"root":args.root,"claim_path":args.path,"token":args.token,"items":[],"dependency_witnesses":[],"reason":status["reason"],"exit_code":2}),
        );
    }
    let root = args
        .root
        .canonicalize()
        .map_err(|error| GraphError::Io(error.to_string()))?;
    let (nodes, facts) = load_graph_records(&root)?;
    let path = args.path.clone().unwrap_or_default();
    let node = nodes
        .iter()
        .find(|node| node.get("path").and_then(Value::as_str) == Some(path.as_str()))
        .cloned();
    let items = node.as_ref().map(|node| vec![json!({"kind":"manifest.present","value":node.get("payload").and_then(|payload| payload.get("manifest_present")).cloned().unwrap_or(Value::Bool(false)),"source_store":"manifest","producer":"source-snapshot","source_path":path,"authority":"ManifestParser"})]).unwrap_or_default();
    let witnesses = facts
        .iter()
        .filter(|fact| fact.get("source_path").and_then(Value::as_str) == Some(path.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    let node_paths = nodes
        .iter()
        .filter_map(|value| {
            Some((
                value.get("id")?.as_str()?.to_string(),
                value.get("path")?.as_str()?.to_string(),
            ))
        })
        .collect::<BTreeMap<_, _>>();
    let mut evidence_paths = vec![path.clone()];
    let mut parent_paths = Vec::new();
    for fact in &witnesses {
        for endpoint in ["from", "to"] {
            if let Some(endpoint_path) = fact
                .get(endpoint)
                .and_then(Value::as_str)
                .and_then(|id| node_paths.get(id))
            {
                evidence_paths.push(endpoint_path.clone());
            }
        }
        let detail = fact.get("dependency_detail").and_then(Value::as_object);
        if detail
            .and_then(|value| value.get("direction"))
            .and_then(Value::as_str)
            == Some("upstream")
            && detail
                .and_then(|value| value.get("kind"))
                .and_then(Value::as_str)
                == Some("design")
        {
            if let Some(parent) = fact
                .get("to")
                .and_then(Value::as_str)
                .and_then(|id| node_paths.get(id))
            {
                parent_paths.push(parent.clone());
            }
        }
    }
    evidence_paths.sort();
    evidence_paths.dedup();
    parent_paths.sort();
    parent_paths.dedup();
    Ok(
        json!({"schema":"agent-canon.graph.context.v1","command":"context","status":"fresh","profile":args.profile,"root":args.root,"claim_path":path,"token":args.token,"resolved_path":node.as_ref().and_then(|value| value.get("path")).cloned(),"source_identity":node.as_ref().map(|value| json!({"snapshot_commit":status["integration_record"].get("snapshot_head"),"source_path":value.get("path"),"content_sha256":value.get("payload").and_then(|payload| payload.get("content_sha256"))})),"items":items,"dependency_witnesses":witnesses,"evidence_paths":evidence_paths,"parent_paths":parent_paths,"runtime_measurements":[],"context_diagnostics":[],"graph_fingerprint":status["graph_fingerprint"],"reason":Value::Null,"exit_code":0}),
    )
}

fn build_graph_with_failure(args: &GraphArgs) -> Result<Value, GraphError> {
    let root = args
        .root
        .canonicalize()
        .map_err(|error| GraphError::Io(error.to_string()))?;
    let material = collect_build_material(&root, &args.profile)?;
    let integration = materialize_graph_store(&material)?;
    Ok(
        json!({"schema":"agent-canon.graph.build.v1","command":"build","status":"fresh","graph_status":"fresh","profile":args.profile,"root":root,"db_path":integration.db_path,"input_fingerprint":integration.input_fingerprint,"graph_fingerprint":integration.graph_fingerprint,"unresolved_count":material.snapshot.diagnostics.len(),"unresolved":material.snapshot.diagnostics.iter().map(|diagnostic| json!({"code":diagnostic.code,"message":diagnostic.message})).collect::<Vec<_>>(),"producer_artifacts":integration.producer_artifacts.iter().map(ProducerArtifact::json).collect::<Vec<_>>(),"integration_record":integration.json(),"publication":"published","durability":"durable","exit_code":0}),
    )
}

fn emit(value: &Value, format: &str) -> i32 {
    if format == "text" {
        println!(
            "{}",
            serde_json::to_string_pretty(value).unwrap_or_else(|_| "{}".to_string())
        );
    } else {
        println!(
            "{}",
            serde_json::to_string(value).unwrap_or_else(|_| "{}".to_string())
        );
    }
    value.get("exit_code").and_then(Value::as_i64).unwrap_or(1) as i32
}

pub(crate) fn run(args: &[String]) -> i32 {
    let Some(command) = args.first() else {
        eprintln!("graph <build|status|query|context>");
        return 2;
    };
    let parsed = match parse_args(&args[1..]) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("graph: {error}");
            return 2;
        }
    };
    let result = match command.as_str() {
        "build" => build_graph_with_failure(&parsed),
        "status" => read_graph_status(&parsed),
        "query" => query_graph(&parsed),
        "context" => context_graph(&parsed),
        "help" | "--help" | "-h" => {
            eprintln!("graph <build|status|query|context> [--root PATH] [--format json]");
            return 2;
        }
        _ => Err(GraphError::Usage(format!(
            "unknown graph command {command}"
        ))),
    };
    match result {
        Ok(value) => emit(&value, &parsed.format),
        Err(error) => {
            let value = json!({"schema":format!("agent-canon.graph.{}.v1",command),"command":command,"status":"unavailable","reason":error.to_string(),"exit_code":1});
            emit(&value, &parsed.format)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Mutex;
    use std::time::{SystemTime, UNIX_EPOCH};

    static FIXTURE_COUNTER: AtomicUsize = AtomicUsize::new(0);
    static GRAPH_TEST_LOCK: Mutex<()> = Mutex::new(());

    struct GraphFixture {
        root: PathBuf,
        target: PathBuf,
        artifact: PathBuf,
        artifact_value: Value,
        artifact_bytes: Vec<u8>,
        receipt: PathBuf,
        receipt_value: Value,
        receipt_bytes: Vec<u8>,
        base_oid: String,
    }

    impl Drop for GraphFixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.root);
        }
    }

    fn fixture_git(root: &Path, args: &[&str]) -> String {
        let output = Command::new("git")
            .arg("-C")
            .arg(root)
            .args(args)
            .output()
            .expect("git command starts");
        assert!(
            output.status.success(),
            "git {:?}: {}",
            args,
            String::from_utf8_lossy(&output.stderr)
        );
        String::from_utf8_lossy(&output.stdout).trim().to_string()
    }

    fn test_base64(bytes: &[u8]) -> String {
        const DIGITS: &[u8; 64] =
            b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        let mut output = String::new();
        for chunk in bytes.chunks(3) {
            let a = chunk[0];
            let b = *chunk.get(1).unwrap_or(&0);
            let c = *chunk.get(2).unwrap_or(&0);
            output.push(DIGITS[(a >> 2) as usize] as char);
            output.push(DIGITS[(((a & 0x03) << 4) | (b >> 4)) as usize] as char);
            output.push(if chunk.len() > 1 {
                DIGITS[(((b & 0x0f) << 2) | (c >> 6)) as usize] as char
            } else {
                '='
            });
            output.push(if chunk.len() > 2 {
                DIGITS[(c & 0x3f) as usize] as char
            } else {
                '='
            });
        }
        output
    }

    fn finalize_artifact(value: &mut Value) -> Vec<u8> {
        value["artifact_sha256"] = Value::String("0".repeat(64));
        let preimage = runtime_materialization_preimage(value).expect("materialization preimage");
        value["materialization_id"] = Value::String(sha256(
            &[
                b"agent_canon.runtime_event.materialization.v1\0".as_slice(),
                preimage.as_slice(),
            ]
            .concat(),
        ));
        let materialization_id = value["materialization_id"]
            .as_str()
            .expect("materialization id")
            .to_string();
        let target_path = value["publication_intent"]["target_path"]
            .as_str()
            .expect("target path")
            .to_string();
        value["publication_intent"]["attempt_id"] =
            Value::String(publication_attempt_id(&materialization_id, &target_path));
        let artifact = sha256(&runtime_canonical_bytes(value, true).expect("artifact preimage"));
        value["artifact_sha256"] = Value::String(artifact);
        runtime_canonical_bytes(value, false).expect("canonical artifact")
    }

    fn finalize_observation(value: &mut Value) {
        value["observation_sha256"] = Value::String("0".repeat(64));
        let hash = sha256(&observation_canonical_bytes(value, true).expect("observation preimage"));
        value["observation_sha256"] = Value::String(hash);
    }

    fn finalize_receipt(value: &mut Value) -> Vec<u8> {
        value["receipt_sha256"] = Value::String("0".repeat(64));
        let hash = sha256(&receipt_canonical_bytes(value, true).expect("receipt preimage"));
        value["receipt_sha256"] = Value::String(hash);
        receipt_canonical_bytes(value, false).expect("canonical receipt")
    }

    fn graph_fixture() -> GraphFixture {
        let counter = FIXTURE_COUNTER.fetch_add(1, Ordering::SeqCst);
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "agent-canon-graph-{}-{counter}-{nanos}",
            std::process::id()
        ));
        fs::create_dir_all(root.join("src")).expect("fixture root");
        fixture_git(&root, &["init", "-q"]);
        fixture_git(&root, &["config", "user.email", "test@example.invalid"]);
        fixture_git(&root, &["config", "user.name", "Graph Test"]);
        let target = root.join("src/target.txt");
        fs::write(&target, b"base target\n").expect("base target");
        fixture_git(&root, &["add", "src/target.txt"]);
        fixture_git(&root, &["commit", "-qm", "base"]);
        let base_oid = fixture_git(&root, &["rev-parse", "HEAD"]);
        fixture_git(&root, &["tag", "runtime-base", &base_oid]);

        let run_dir = root.join("reports/agents/run-graph");
        fs::create_dir_all(&run_dir).expect("run dir");
        let result = run_dir.join("validation_result.json");
        fs::write(
            &result,
            b"{\"schema\":\"agent_canon.runtime_result_input.v1\",\"result\":\"PASS\"}\n",
        )
        .expect("result artifact");
        fs::write(&target, b"current target\n").expect("current target");
        fixture_git(
            &root,
            &[
                "add",
                "src/target.txt",
                "reports/agents/run-graph/validation_result.json",
            ],
        );
        fixture_git(&root, &["commit", "-qm", "current"]);
        let head_oid = fixture_git(&root, &["rev-parse", "HEAD"]);

        let rollout = root.join("sessions/rollout.jsonl");
        fs::create_dir_all(rollout.parent().expect("rollout parent")).expect("sessions");
        let mut rollout_bytes = Vec::new();
        for _ in 0..871 {
            rollout_bytes.extend_from_slice(b"{}\n");
        }
        let record_offset = rollout_bytes.len();
        let record = b"{\"type\":\"task_complete\"}\n";
        rollout_bytes.extend_from_slice(record);
        fs::write(&rollout, &rollout_bytes).expect("rollout");

        fs::write(root.join("reports/agents/.active_run"), b"run-graph\n").expect("active pointer");
        let record_sha256 = sha256(record);
        let artifact_target = run_dir.join(format!("runtime_event.{}.json", &record_sha256[..16]));
        let target_bytes = fs::read(&target).expect("target bytes");
        let base_bytes =
            git_value(&root, &["show", &format!("{base_oid}:src/target.txt")]).expect("base bytes");
        let target_blob = fixture_git(&root, &["hash-object", "--", "src/target.txt"]);
        let base_blob = fixture_git(
            &root,
            &[
                "rev-parse",
                "--verify",
                &format!("{base_oid}:src/target.txt"),
            ],
        );
        let result_bytes = fs::read(&result).expect("result bytes");
        let result_blob = fixture_git(
            &root,
            &[
                "hash-object",
                "--",
                "reports/agents/run-graph/validation_result.json",
            ],
        );
        let rollout_path = rollout.display().to_string();
        let publication_path = artifact_target
            .strip_prefix(&root)
            .expect("artifact relative")
            .to_str()
            .expect("UTF-8 artifact")
            .replace('\\', "/");
        let mut artifact_value = json!({
            "schema": RUNTIME_EVENT_SCHEMA,
            "materialization_id": "0".repeat(64),
            "result_family": "validation",
            "gate": {"id": "validation", "result": "PASS"},
            "source_event": {
                "agent_id": "11111111-1111-4111-8111-111111111111",
                "agent_context_id": "22222222-2222-4222-8222-222222222222",
                "codex_thread_id": "33333333-3333-4333-8333-333333333333",
                "parent_id": "44444444-4444-4444-8444-444444444444",
                "turn_id": "55555555-5555-4555-8555-555555555555",
                "role": "worker",
                "decision": "NONE",
                "applicable_gate_result": "PASS",
                "rollout_path": rollout_path,
                "rollout_path_bytes_b64": test_base64(rollout_path.as_bytes()),
                "rollout_path_sha256": sha256(rollout_path.as_bytes()),
                "rollout_file_sha256": sha256(&rollout_bytes),
                "record_line": 872,
                "record_byte_offset": record_offset,
                "record_byte_length": record.len(),
                "record_bytes_b64": test_base64(record),
                "record_sha256": record_sha256,
                "stable_record_id": record_sha256,
            },
            "result_artifact": {
                "path": "reports/agents/run-graph/validation_result.json",
                "schema": "agent_canon.runtime_result_input.v1",
                "artifact_sha256": sha256(&result_bytes),
                "artifact_blob_oid": result_blob,
                "gate_id": "validation",
                "gate_result": "PASS",
                "target_paths": ["src/target.txt"],
                "base_ref": "refs/tags/runtime-base",
                "base_oid": base_oid,
            },
            "target_identities": [{
                "path": "src/target.txt",
                "content_sha256": sha256(&target_bytes),
                "git_blob_oid": target_blob,
                "base_present": true,
                "base_content_sha256": sha256(&base_bytes),
                "base_git_blob_oid": base_blob,
            }],
            "source_snapshot": {
                "head_oid": head_oid,
                "base_ref": "refs/tags/runtime-base",
                "base_oid": base_oid,
                "porcelain_v1": ["?? sessions/rollout.jsonl"],
            },
            "publication_intent": {
                "schema": RUNTIME_PUBLICATION_INTENT_SCHEMA,
                "attempt_id": "0".repeat(64),
                "target_path": publication_path.clone(),
                "prepared_state": "prepared",
            },
            "artifact_sha256": "0".repeat(64),
        });
        let artifact_bytes = finalize_artifact(&mut artifact_value);
        fs::write(&artifact_target, &artifact_bytes).expect("artifact");
        let attempt_id = artifact_value["publication_intent"]["attempt_id"]
            .as_str()
            .expect("attempt id")
            .to_string();
        let artifact_sha256 = artifact_value["artifact_sha256"]
            .as_str()
            .expect("artifact hash")
            .to_string();
        let materialization_id = artifact_value["materialization_id"]
            .as_str()
            .expect("materialization id")
            .to_string();
        let mut observation = json!({
            "schema": RUNTIME_OBSERVATION_SCHEMA,
            "attempt_id": attempt_id.clone(),
            "artifact_path": publication_path.clone(),
            "artifact_sha256": artifact_sha256.clone(),
            "materialization_id": materialization_id.clone(),
            "sequence": 1,
            "prior_observation_sha256": Value::Null,
            "outcome": "committed",
            "evidence": {
                "source": "publish",
                "causal_gap": false,
                "target_presence": "present",
                "rename_status": "completed",
                "target_directory_fsync_status": "succeeded",
                "readback_status": "verified",
                "readback_sha256": artifact_sha256.clone(),
            },
            "observation_sha256": "0".repeat(64),
        });
        finalize_observation(&mut observation);
        let mut receipt_value = json!({
            "schema": RUNTIME_RECEIPT_SCHEMA,
            "attempt_id": attempt_id.clone(),
            "artifact_path": publication_path,
            "artifact_sha256": artifact_sha256,
            "materialization_id": materialization_id,
            "sequence": 1,
            "prior_receipt_sha256": Value::Null,
            "observation": observation,
            "receipt_sha256": "0".repeat(64),
        });
        let receipt_bytes = finalize_receipt(&mut receipt_value);
        let receipt = run_dir.join(format!(
            "runtime_event.{}.outcome.{}.000001.json",
            &record_sha256[..16],
            attempt_id
        ));
        fs::write(&receipt, &receipt_bytes).expect("receipt");
        GraphFixture {
            root,
            target,
            artifact: artifact_target,
            artifact_value,
            artifact_bytes,
            receipt,
            receipt_value,
            receipt_bytes,
            base_oid,
        }
    }

    fn graph_args(root: &Path) -> GraphArgs {
        GraphArgs {
            root: root.to_path_buf(),
            profile: "default".to_string(),
            format: "json".to_string(),
            path: Some("src/target.txt".to_string()),
            all: false,
            relation: "all".to_string(),
            direction: "both".to_string(),
            depth: 1,
            token: None,
        }
    }

    #[test]
    fn test_graph_status_query_context_consume_persisted_runtime_event() {
        let _guard = GRAPH_TEST_LOCK.lock().expect("graph test lock");
        let fixture = graph_fixture();
        let args = graph_args(&fixture.root);
        let build = build_graph_with_failure(&args).expect("graph build");
        assert_eq!(build["status"], "fresh");

        let connection = Connection::open(
            fixture
                .root
                .join(".agent-canon/knowledge-graph/graph.sqlite"),
        )
        .expect("persisted graph");
        let mut statement = connection
            .prepare("SELECT key FROM metadata WHERE key LIKE 'runtime_%' ORDER BY key")
            .expect("runtime metadata query");
        let keys = statement
            .query_map([], |row| row.get::<_, String>(0))
            .expect("runtime metadata rows")
            .collect::<Result<Vec<_>, _>>()
            .expect("runtime metadata values");
        assert_eq!(
            keys,
            vec![
                "runtime_event_artifact",
                "runtime_event_artifact_sha256",
                "runtime_event_materialization",
                "runtime_event_outcome_receipt",
                "runtime_event_outcome_receipt_sha256",
                "runtime_live_identity_fingerprint",
            ]
        );
        drop(statement);
        drop(connection);

        let probe = probe_input_fingerprint(&fixture.root, &args.profile)
            .expect("component-complete probe");
        assert!(probe.reason.is_none());
        assert_eq!(
            probe.artifact_sha256.as_deref(),
            fixture.artifact_value["artifact_sha256"].as_str()
        );
        assert_eq!(
            probe.receipt_sha256.as_deref(),
            fixture.receipt_value["receipt_sha256"].as_str()
        );
        assert!(probe
            .live_identity_fingerprint
            .as_deref()
            .map(|value| runtime_hex(value, 64))
            .unwrap_or(false));
        assert_eq!(probe.profile, "default");

        let graph_path = fixture
            .root
            .join(".agent-canon/knowledge-graph/graph.sqlite");
        let persisted_graph = fs::read(&graph_path).expect("persisted graph bytes");
        let persisted_artifact = fs::read(&fixture.artifact).expect("artifact bytes");
        let persisted_receipt = fs::read(&fixture.receipt).expect("receipt bytes");
        let status = read_graph_status(&args).expect("status");
        let query = query_graph(&args).expect("query");
        let context = context_graph(&args).expect("context");
        assert_eq!(status["status"], "fresh");
        assert_eq!(query["status"], "fresh");
        assert_eq!(context["status"], "fresh");
        assert_eq!(query["graph_fingerprint"], status["graph_fingerprint"]);
        assert_eq!(context["graph_fingerprint"], status["graph_fingerprint"]);
        assert_eq!(
            fs::read(graph_path).expect("graph readback"),
            persisted_graph
        );
        assert_eq!(
            fs::read(&fixture.artifact).expect("artifact readback"),
            persisted_artifact
        );
        assert_eq!(
            fs::read(&fixture.receipt).expect("receipt readback"),
            persisted_receipt
        );
    }

    #[test]
    fn freshness_probe_covers_artifact_receipt_source_head_base_and_target() {
        let _guard = GRAPH_TEST_LOCK.lock().expect("graph test lock");
        let mut fixture = graph_fixture();
        let args = graph_args(&fixture.root);
        build_graph_with_failure(&args).expect("graph build");

        fs::write(&fixture.artifact, b"{}\n").expect("changed artifact");
        let status = read_graph_status(&args).expect("artifact status");
        assert_eq!(status["status"], "stale");
        assert_eq!(status["probe_reason"], "runtime_evidence_changed");
        fs::write(&fixture.artifact, &fixture.artifact_bytes).expect("restore artifact");
        assert_eq!(
            read_graph_status(&args).expect("restored artifact")["status"],
            "fresh"
        );

        fs::write(&fixture.receipt, b"{}\n").expect("invalid receipt");
        let status = read_graph_status(&args).expect("invalid receipt status");
        assert_eq!(status["status"], "stale");
        assert_eq!(status["probe_reason"], "runtime_receipt_invalid");
        fs::write(&fixture.receipt, &fixture.receipt_bytes).expect("restore valid receipt");

        fixture.receipt_value["observation"]["outcome"] = Value::String("uncertain".to_string());
        fixture.receipt_value["observation"]["evidence"]["target_directory_fsync_status"] =
            Value::String("failed".to_string());
        finalize_observation(&mut fixture.receipt_value["observation"]);
        let uncertain_receipt = finalize_receipt(&mut fixture.receipt_value);
        fs::write(&fixture.receipt, uncertain_receipt).expect("uncertain receipt");
        let status = read_graph_status(&args).expect("uncertain status");
        assert_eq!(status["status"], "stale");
        assert_eq!(status["probe_reason"], "runtime_receipt_uncertain");
        fs::write(&fixture.receipt, &fixture.receipt_bytes).expect("restore receipt");
        assert_eq!(
            read_graph_status(&args).expect("restored receipt")["status"],
            "fresh"
        );

        fs::remove_file(&fixture.receipt).expect("remove receipt");
        let status = read_graph_status(&args).expect("missing receipt status");
        assert_eq!(status["probe_reason"], "runtime_receipt_missing");
        fs::write(&fixture.receipt, &fixture.receipt_bytes).expect("restore missing receipt");

        fs::write(&fixture.target, b"changed target\n").expect("changed target");
        let status = read_graph_status(&args).expect("target status");
        assert_eq!(status["status"], "stale");
        assert_eq!(status["probe_reason"], "source_changed");
        fs::write(&fixture.target, b"current target\n").expect("restore target");
        assert_eq!(
            read_graph_status(&args).expect("restored target status")["status"],
            "fresh"
        );

        let current_head = fixture_git(&fixture.root, &["rev-parse", "HEAD"]);
        fixture_git(&fixture.root, &["tag", "-f", "runtime-base", &current_head]);
        let status = read_graph_status(&args).expect("base status");
        assert_eq!(status["status"], "stale");
        assert_eq!(status["probe_reason"], "source_changed");
        fixture_git(
            &fixture.root,
            &["tag", "-f", "runtime-base", &fixture.base_oid],
        );
        assert_eq!(
            read_graph_status(&args).expect("restored base status")["status"],
            "fresh"
        );

        fs::write(fixture.root.join("head-change.txt"), b"head change\n").expect("head change");
        fixture_git(&fixture.root, &["add", "head-change.txt"]);
        fixture_git(&fixture.root, &["commit", "-qm", "head change"]);
        let status = read_graph_status(&args).expect("head status");
        assert_eq!(status["status"], "stale");
        assert_eq!(status["probe_reason"], "source_changed");
    }

    #[test]
    fn graph_build_rejects_missing_uncertain_invalid_and_nonlatest_receipts() {
        let _guard = GRAPH_TEST_LOCK.lock().expect("graph test lock");

        let missing = graph_fixture();
        fs::remove_file(&missing.receipt).expect("remove receipt");
        assert!(matches!(
            build_graph_with_failure(&graph_args(&missing.root)),
            Err(GraphError::RuntimeBoundary { reason, .. })
                if reason == "runtime_receipt_missing"
        ));

        let mut uncertain = graph_fixture();
        uncertain.receipt_value["observation"]["outcome"] = Value::String("uncertain".to_string());
        uncertain.receipt_value["observation"]["evidence"]["target_directory_fsync_status"] =
            Value::String("failed".to_string());
        finalize_observation(&mut uncertain.receipt_value["observation"]);
        let uncertain_bytes = finalize_receipt(&mut uncertain.receipt_value);
        fs::write(&uncertain.receipt, uncertain_bytes).expect("uncertain receipt");
        assert!(matches!(
            build_graph_with_failure(&graph_args(&uncertain.root)),
            Err(GraphError::RuntimeBoundary { reason, .. })
                if reason == "runtime_receipt_uncertain"
        ));

        let invalid = graph_fixture();
        fs::write(&invalid.receipt, b"{}\n").expect("invalid receipt");
        assert!(matches!(
            build_graph_with_failure(&graph_args(&invalid.root)),
            Err(GraphError::RuntimeBoundary { reason, .. })
                if reason == "runtime_receipt_invalid"
        ));

        let nonlatest = graph_fixture();
        let second = nonlatest.receipt.with_file_name(
            nonlatest
                .receipt
                .file_name()
                .and_then(|value| value.to_str())
                .expect("receipt name")
                .replace(".000001.json", ".000002.json"),
        );
        fs::write(second, &nonlatest.receipt_bytes).expect("non-latest receipt");
        assert!(matches!(
            build_graph_with_failure(&graph_args(&nonlatest.root)),
            Err(GraphError::RuntimeBoundary { reason, .. })
                if reason == "runtime_receipt_invalid"
        ));
    }

    #[test]
    fn persisted_readback_and_profile_changes_use_ordered_probe_reasons() {
        let _guard = GRAPH_TEST_LOCK.lock().expect("graph test lock");
        let fixture = graph_fixture();
        let args = graph_args(&fixture.root);
        build_graph_with_failure(&args).expect("graph build");
        let db = fixture
            .root
            .join(".agent-canon/knowledge-graph/graph.sqlite");
        let connection = Connection::open(&db).expect("graph database");
        connection
            .execute(
                "UPDATE metadata SET value=?1 WHERE key='runtime_event_artifact_sha256'",
                params!["0".repeat(64)],
            )
            .expect("tamper persisted hash");
        drop(connection);
        let status = read_graph_status(&args).expect("persisted mismatch status");
        assert_eq!(status["status"], "stale");
        assert_eq!(status["probe_reason"], "persisted_readback_mismatch");

        let profile_fixture = graph_fixture();
        let mut profile_args = graph_args(&profile_fixture.root);
        build_graph_with_failure(&profile_args).expect("profile graph build");
        profile_args.profile = "different-profile".to_string();
        let status = read_graph_status(&profile_args).expect("profile status");
        assert_eq!(status["status"], "stale");
        assert_eq!(status["probe_reason"], "runtime_evidence_changed");
    }
}
