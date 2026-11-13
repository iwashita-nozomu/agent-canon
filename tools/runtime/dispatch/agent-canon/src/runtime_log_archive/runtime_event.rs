//! Source-bound runtime-event materialization and durable outcome receipt.

use super::context_discovery::{self, RuntimeEventSource};
use super::{ArchiveContext, ArchiveError, CommandOptions, archive_runtime_root};
use crate::graph;
use agent_canon::authority::{
    AttestationRequest, NonEmptyTrimmedString, Nonce128, ParentOwnedNoReplaceOutcome,
    ParentOwnedPathReceipt, ParentRootAttestor,
};
use agent_canon::eval_archive_paths;
use agent_canon::report_artifact_checks;
use agent_canon::runtime_boundary::{RuntimeFileLock, RuntimeSpoolBoundary};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::Command;

const EVENT_SCHEMA: &str = "agent_canon.runtime_event.v1";
const MATERIALIZATION_SCHEMA: &str = "agent_canon.runtime_event.materialization.v1";
const ATTEMPT_SCHEMA: &str = "agent_canon.runtime_event.publication_attempt.v1";
const INTENT_SCHEMA: &str = "agent_canon.runtime_event.publication_intent.v1";
const OBSERVATION_SCHEMA: &str = "agent_canon.runtime_event.publication_outcome_observation.v1";
const RECEIPT_SCHEMA: &str = "agent_canon.runtime_event.publication_outcome_receipt.v1";
const RESULT_INPUT_SCHEMA: &str = "agent_canon.runtime_result_input.v1";

#[derive(Clone, Copy)]
struct ResultFamilySpec {
    family: &'static str,
    gate_id: &'static str,
    artifact_name: &'static str,
    schema: &'static str,
}

const RESULT_FAMILIES: &[ResultFamilySpec] = &[
    ResultFamilySpec {
        family: "requirements",
        gate_id: "requirements-review",
        artifact_name: "requirements_review.md",
        schema: "ReviewArtifactV1",
    },
    ResultFamilySpec {
        family: "design",
        gate_id: "design-review",
        artifact_name: "design_review.md",
        schema: "ReviewArtifactV1",
    },
    ResultFamilySpec {
        family: "review",
        gate_id: "change-review",
        artifact_name: "change_review.md",
        schema: "ReviewArtifactV1",
    },
    ResultFamilySpec {
        family: "validation",
        gate_id: "validation",
        artifact_name: "validation_result.json",
        schema: RESULT_INPUT_SCHEMA,
    },
    ResultFamilySpec {
        family: "lifecycle",
        gate_id: "closeout",
        artifact_name: "closeout_gate.md",
        schema: "CloseoutGateV1",
    },
];

#[derive(Deserialize, Serialize, Clone)]
struct Gate {
    id: String,
    result: String,
}

#[derive(Deserialize, Serialize, Clone)]
struct TargetIdentity {
    path: String,
    content_sha256: String,
    git_blob_oid: String,
    base_present: bool,
    base_content_sha256: Option<String>,
    base_git_blob_oid: Option<String>,
}

#[derive(Deserialize, Serialize, Clone)]
struct SourceSnapshot {
    head_oid: String,
    base_ref: String,
    base_oid: String,
    porcelain_v1: Vec<String>,
}

#[derive(Deserialize, Serialize, Clone)]
struct ResultArtifact {
    path: String,
    schema: String,
    artifact_sha256: String,
    artifact_blob_oid: String,
    gate_id: String,
    gate_result: String,
    target_paths: Vec<String>,
    base_ref: String,
    base_oid: String,
}

#[derive(Serialize, Clone)]
struct PublicationIntent {
    schema: String,
    attempt_id: String,
    target_path: String,
    prepared_state: String,
}

#[derive(Serialize, Clone)]
struct RuntimeEventRecord {
    schema: String,
    materialization_id: String,
    result_family: String,
    gate: Gate,
    source_event: RuntimeEventSource,
    result_artifact: ResultArtifact,
    target_identities: Vec<TargetIdentity>,
    source_snapshot: SourceSnapshot,
    publication_intent: PublicationIntent,
    artifact_sha256: String,
}

#[derive(Serialize)]
struct MaterializationPreimage<'a> {
    schema: &'static str,
    result_family: &'a str,
    gate: Gate,
    source_event: SourceEventPreimage<'a>,
    result_artifact: ResultArtifactPreimage<'a>,
    target_identities: &'a [TargetIdentity],
    source_snapshot: SourceSnapshotPreimage<'a>,
}

#[derive(Serialize)]
struct SourceEventPreimage<'a> {
    stable_record_id: &'a str,
    rollout_path_sha256: &'a str,
    rollout_file_sha256: &'a str,
    record_line: usize,
    record_byte_offset: usize,
    record_byte_length: usize,
}

#[derive(Serialize)]
struct ResultArtifactPreimage<'a> {
    artifact_sha256: &'a str,
    artifact_blob_oid: &'a str,
    gate_id: &'a str,
}

#[derive(Serialize)]
struct SourceSnapshotPreimage<'a> {
    head_oid: &'a str,
    base_ref: &'a str,
    base_oid: &'a str,
}

#[derive(Clone, Deserialize, Eq, PartialEq, Serialize)]
struct ObservationEvidence {
    source: String,
    causal_gap: bool,
    target_presence: String,
    rename_status: String,
    target_directory_fsync_status: String,
    readback_status: String,
    readback_sha256: Option<String>,
}

#[derive(Eq, PartialEq, Serialize, Deserialize, Clone)]
struct Observation {
    schema: String,
    attempt_id: String,
    artifact_path: String,
    artifact_sha256: String,
    materialization_id: String,
    sequence: u64,
    prior_observation_sha256: Option<String>,
    outcome: String,
    evidence: ObservationEvidence,
    observation_sha256: String,
}

#[derive(Serialize, Deserialize, Clone)]
struct Receipt {
    schema: String,
    attempt_id: String,
    artifact_path: String,
    artifact_sha256: String,
    materialization_id: String,
    sequence: u64,
    prior_receipt_sha256: Option<String>,
    observation: Observation,
    receipt_sha256: String,
}

#[derive(Clone)]
struct DurableReceipt {
    path: PathBuf,
    bytes: Vec<u8>,
    value: Receipt,
}

struct PublicationChain {
    observations: Vec<(Observation, Vec<u8>)>,
    receipts: Vec<DurableReceipt>,
}

struct OutcomeAttempt {
    boundary: RuntimeSpoolBoundary,
    directory: PathBuf,
    _lock: RuntimeFileLock,
}

struct ResultInput {
    gate_result: String,
    decision: String,
    target_paths: Vec<String>,
    base_ref: Option<String>,
    observations: Option<Value>,
    review_target_sha256: Option<String>,
    evidence_path: Option<String>,
    evidence_sha256: Option<String>,
}

fn error(code: &str, detail: impl Into<String>) -> ArchiveError {
    ArchiveError::new(code, detail)
}

#[cfg(unix)]
fn validate_attempt_directory(path: &Path) -> Result<(), ArchiveError> {
    use std::os::unix::fs::MetadataExt;
    let metadata = fs::symlink_metadata(path).map_err(|detail| {
        ArchiveError::new("publication_attempt_lock_invalid", detail.to_string())
    })?;
    if metadata.file_type().is_symlink()
        || !metadata.is_dir()
        || metadata.uid() != nix::unistd::geteuid().as_raw()
        || metadata.mode() & 0o700 != 0o700
        || metadata.mode() & 0o022 != 0
    {
        return Err(error(
            "publication_attempt_lock_invalid",
            "publication attempt directory metadata is invalid",
        ));
    }
    Ok(())
}

#[cfg(not(unix))]
fn validate_attempt_directory(_path: &Path) -> Result<(), ArchiveError> {
    Err(error(
        "publication_attempt_lock_invalid",
        "publication attempt receipts require a no-follow Unix runtime",
    ))
}

fn hash(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn spec(family: &str, gate_id: &str) -> Result<ResultFamilySpec, ArchiveError> {
    let value = RESULT_FAMILIES
        .iter()
        .find(|value| value.family == family)
        .ok_or_else(|| {
            error(
                "result_authority_mismatch",
                "result family and gate id do not match",
            )
        })?;
    if value.gate_id != gate_id {
        return Err(error(
            "result_authority_mismatch",
            "result family and gate id do not match",
        ));
    }
    Ok(*value)
}

fn relative_safe(value: &str) -> bool {
    let path = Path::new(value);
    !value.is_empty()
        && !path.is_absolute()
        && !value.contains('\\')
        && !value.contains('\0')
        && !path.components().any(|part| {
            matches!(
                part,
                Component::ParentDir
                    | Component::CurDir
                    | Component::RootDir
                    | Component::Prefix(_)
            )
        })
}

fn is_source_snapshot_path(value: &str) -> bool {
    let path = Path::new(value);
    let parts = path
        .components()
        .map(|part| part.as_os_str().to_string_lossy().into_owned())
        .collect::<Vec<_>>();
    if parts.is_empty()
        || parts.iter().any(|part| {
            matches!(
                part.as_str(),
                ".git"
                    | ".agent-canon"
                    | "__pycache__"
                    | ".pytest_cache"
                    | ".mypy_cache"
                    | ".ruff_cache"
            )
        })
    {
        return false;
    }
    if parts.len() >= 3
        && parts[0] == "experiments"
        && matches!(parts[2].as_str(), "result" | "report")
    {
        return false;
    }
    let normalized = value.replace('\\', "/");
    for root in [
        "reports/agent-eval-runs",
        "reports/agent-improvement-guide",
        "reports/agent-runtime-dashboard",
        "reports/dependency-review",
        "reports/hooks",
        "reports/.cache",
    ] {
        if normalized == root || normalized.starts_with(&format!("{root}/")) {
            return false;
        }
    }
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or_default();
    if name.starts_with("runtime_event.") || name.starts_with("runtime_event_archive_manifest.") {
        return false;
    }
    !report_artifact_checks::is_mechanically_regenerated_report_path(&normalized)
}

fn parse_validation(bytes: &[u8], gate_id: &str) -> Result<ResultInput, ArchiveError> {
    use agent_canon::python_json::{JsonValue, parse_json_bytes_unique_keys};
    let parsed = parse_json_bytes_unique_keys(bytes).map_err(|_| {
        error(
            "result_authority_mismatch",
            "validation result is not UTF-8 JSON",
        )
    })?;
    let JsonValue::Object(object) = &parsed else {
        return Err(error(
            "result_authority_mismatch",
            "validation result keys or schema mismatch",
        ));
    };
    let keys = object
        .0
        .iter()
        .map(|(key, _)| key.to_text().unwrap_or_default())
        .collect::<Vec<_>>();
    let expected = [
        "schema",
        "result",
        "gate_id",
        "target_paths",
        "base_ref",
        "observations",
    ];
    if keys.iter().map(String::as_str).ne(expected) {
        return Err(error(
            "result_authority_mismatch",
            "validation result keys or schema mismatch",
        ));
    }
    let value: Value = serde_json::from_slice(bytes)
        .map_err(|_| error("result_authority_mismatch", "validation result is invalid"))?;
    if value.get("schema").and_then(Value::as_str) != Some(RESULT_INPUT_SCHEMA)
        || value.get("gate_id").and_then(Value::as_str) != Some(gate_id)
    {
        return Err(error(
            "result_authority_mismatch",
            "validation result gate mismatch",
        ));
    }
    let gate_result = value
        .get("result")
        .and_then(Value::as_str)
        .filter(|item| ["PASS", "FAIL", "BLOCKED"].contains(item))
        .ok_or_else(|| {
            error(
                "result_authority_mismatch",
                "validation result gate mismatch",
            )
        })?
        .to_owned();
    let paths = value
        .get("target_paths")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            error(
                "result_authority_mismatch",
                "validation target_paths are invalid",
            )
        })?;
    let mut target_paths = Vec::new();
    for path in paths {
        let path = path.as_str().ok_or_else(|| {
            error(
                "result_authority_mismatch",
                "validation target_paths are invalid",
            )
        })?;
        if !relative_safe(path) || target_paths.iter().any(|prior| prior == path) {
            return Err(error(
                "result_authority_mismatch",
                "validation target_paths are invalid",
            ));
        }
        target_paths.push(path.to_owned());
    }
    if target_paths.is_empty() {
        return Err(error(
            "result_authority_mismatch",
            "validation target_paths are invalid",
        ));
    }
    let base_ref = value
        .get("base_ref")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            error(
                "result_authority_mismatch",
                "validation identity fields are incomplete",
            )
        })?
        .to_owned();
    let observations = value
        .get("observations")
        .filter(|value| value.is_object())
        .cloned()
        .ok_or_else(|| {
            error(
                "result_authority_mismatch",
                "validation identity fields are incomplete",
            )
        })?;
    for field in ["head_oid", "base_oid"] {
        if !observations
            .get(field)
            .and_then(Value::as_str)
            .is_some_and(|value| hex(value, 40))
        {
            return Err(ArchiveError::new(
                "result_authority_mismatch",
                format!("validation {field} is invalid"),
            ));
        }
    }
    if observations
        .get("targets")
        .is_some_and(|targets| !targets.is_object())
    {
        return Err(error(
            "target_identity_mismatch",
            "target observations are invalid",
        ));
    }
    Ok(ResultInput {
        gate_result,
        decision: "NONE".to_owned(),
        target_paths,
        base_ref: Some(base_ref),
        observations: Some(observations),
        review_target_sha256: None,
        evidence_path: None,
        evidence_sha256: None,
    })
}

fn parse_review(text: &str) -> Result<ResultInput, ArchiveError> {
    let identity = report_artifact_checks::parse_review_identity(text);
    let decisions = report_artifact_checks::final_review_decision_lines(text);
    if decisions.len() != 1
        || !["APPROVE", "REVISE", "ESCALATE"].contains(&decisions[0].to_ascii_uppercase().as_str())
    {
        return Err(error(
            "result_authority_mismatch",
            "review decision is not exactly one supported value",
        ));
    }
    let decision = decisions[0].to_ascii_uppercase();
    if identity.decision_approved != (decision == "APPROVE") {
        return Err(error(
            "result_authority_mismatch",
            "review decision disagrees with canonical identity authority",
        ));
    }
    let path = identity.design_artifact_path.ok_or_else(|| {
        error(
            "result_authority_mismatch",
            "review identity fields are incomplete",
        )
    })?;
    let sha = identity.review_target_sha256.ok_or_else(|| {
        error(
            "result_authority_mismatch",
            "review identity fields are incomplete",
        )
    })?;
    if !relative_safe(&path) || !hex(&sha, 64) {
        return Err(error(
            "result_authority_mismatch",
            "review identity fields are incomplete",
        ));
    }
    if decision == "APPROVE"
        && !report_artifact_checks::check_final_review_artifact(text).is_empty()
    {
        return Err(error(
            "result_authority_mismatch",
            report_artifact_checks::check_final_review_artifact(text).join("; "),
        ));
    }
    Ok(ResultInput {
        gate_result: decision.clone(),
        decision,
        target_paths: vec![path],
        base_ref: None,
        observations: None,
        review_target_sha256: Some(sha),
        evidence_path: None,
        evidence_sha256: None,
    })
}

fn parse_lifecycle(text: &str, gate_id: &str) -> Result<ResultInput, ArchiveError> {
    let lines = text.lines().collect::<Vec<_>>();
    let starts = lines
        .iter()
        .enumerate()
        .filter(|(_, line)| line.trim() == "## Completion Readiness")
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    if starts.len() != 1 {
        return Err(error(
            "result_authority_mismatch",
            "closeout readiness section is not exactly one",
        ));
    }
    let start = starts[0];
    let end = lines
        .iter()
        .enumerate()
        .skip(start + 1)
        .find(|(_, line)| {
            let line = line.trim();
            line.starts_with('#') && line.trim_start_matches('#').starts_with(' ')
        })
        .map(|(index, _)| index)
        .unwrap_or(lines.len());
    let owned = [
        "status",
        "closeout_gate_id",
        "target_paths",
        "base_ref",
        "evidence_path",
        "evidence_sha256",
    ];
    let mut fields = std::collections::BTreeMap::new();
    for (index, line) in lines.iter().enumerate() {
        let Some((key, value)) = line.split_once(':') else {
            continue;
        };
        let key = key.trim().to_ascii_lowercase();
        if !owned.contains(&key.as_str()) {
            continue;
        }
        if index <= start || index >= end {
            return Err(error(
                "result_authority_mismatch",
                "closeout field appears outside readiness section",
            ));
        }
        if fields.insert(key, value.trim().to_owned()).is_some() {
            return Err(error(
                "result_authority_mismatch",
                "closeout field is duplicated",
            ));
        }
    }
    if fields.len() != owned.len()
        || fields.get("closeout_gate_id").map(String::as_str) != Some(gate_id)
    {
        return Err(error(
            "result_authority_mismatch",
            "closeout readiness fields are incomplete or gate id mismatch",
        ));
    }
    let status = fields["status"].clone();
    if !["READY", "BLOCKED", "INCOMPLETE"].contains(&status.as_str()) {
        return Err(error(
            "result_authority_mismatch",
            "closeout status is unsupported",
        ));
    }
    let paths = fields["target_paths"]
        .split(',')
        .map(str::trim)
        .filter(|path| !path.is_empty())
        .map(str::to_owned)
        .collect::<Vec<_>>();
    let evidence = fields["evidence_path"].clone();
    if paths.is_empty()
        || !relative_safe(&evidence)
        || paths.iter().any(|path| !relative_safe(path))
        || !paths.contains(&evidence)
    {
        return Err(error(
            "result_authority_mismatch",
            "closeout target or evidence paths are invalid",
        ));
    }
    let sha = fields["evidence_sha256"].clone();
    if !hex(&sha, 64) || fields["base_ref"].is_empty() {
        return Err(error(
            "result_authority_mismatch",
            "closeout evidence hash is invalid",
        ));
    }
    let base_ref = fields["base_ref"].clone();
    Ok(ResultInput {
        gate_result: status,
        decision: "NONE".to_owned(),
        target_paths: paths,
        base_ref: Some(base_ref),
        observations: None,
        review_target_sha256: None,
        evidence_path: Some(evidence),
        evidence_sha256: Some(sha),
    })
}

fn git(root: &Path, args: &[&str], error_code: &str) -> Result<String, ArchiveError> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|detail| ArchiveError::new(error_code, detail.to_string()))?;
    if !output.status.success() {
        return Err(ArchiveError::new(
            error_code,
            String::from_utf8_lossy(&output.stderr).trim().to_owned(),
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

fn git_blob(root: &Path, path: &str) -> Result<String, ArchiveError> {
    git(
        root,
        &["hash-object", "--", path],
        "result_authority_mismatch",
    )
}

fn target_identities(
    root: &Path,
    result: &ResultInput,
    base_ref: &str,
) -> Result<(Vec<TargetIdentity>, String, String), ArchiveError> {
    let base = git(
        root,
        &["rev-parse", "--verify", base_ref],
        "target_identity_mismatch",
    )?;
    let head = git(
        root,
        &["rev-parse", "--verify", "HEAD"],
        "target_identity_mismatch",
    )?;
    if !hex(&base, 40) || !hex(&head, 40) {
        return Err(error(
            "target_identity_mismatch",
            "Git base/head identity is invalid",
        ));
    }
    let base_oid = base;
    let mut paths = result.target_paths.clone();
    paths.sort_by(|left, right| left.as_bytes().cmp(right.as_bytes()));
    if paths.is_empty() || paths.windows(2).any(|pair| pair[0] == pair[1]) {
        return Err(error(
            "target_identity_mismatch",
            "target paths are empty or duplicated",
        ));
    }
    let mut identities = Vec::new();
    for path in paths {
        if !relative_safe(&path) || !is_source_snapshot_path(&path) {
            return Err(ArchiveError::new(
                "target_identity_mismatch",
                format!("target path is outside source scope: {path}"),
            ));
        }
        let target = root.join(&path);
        let resolved_root = fs::canonicalize(root)
            .map_err(|detail| error("target_identity_mismatch", detail.to_string()))?;
        let resolved = fs::canonicalize(&target).map_err(|detail| {
            ArchiveError::new(
                "target_identity_mismatch",
                format!("target cannot be read: {path}: {detail}"),
            )
        })?;
        if !resolved.starts_with(&resolved_root) {
            return Err(ArchiveError::new(
                "target_identity_mismatch",
                format!("target path escapes source: {path}"),
            ));
        }
        let bytes = super::read_file_nofollow(&resolved).map_err(|detail| {
            ArchiveError::new(
                "target_identity_mismatch",
                format!("target cannot be read: {path}: {detail}"),
            )
        })?;
        let content_sha = hash(&bytes);
        if result
            .review_target_sha256
            .as_ref()
            .is_some_and(|expected| expected != &content_sha)
        {
            return Err(ArchiveError::new(
                "target_identity_mismatch",
                format!("target sha mismatch: {path}"),
            ));
        }
        let blob = git_blob(root, &path)?;
        if !hex(&blob, 40) {
            return Err(ArchiveError::new(
                "target_identity_mismatch",
                format!("target blob is unavailable: {path}"),
            ));
        }
        if let Some(observed) = result
            .observations
            .as_ref()
            .and_then(|observations| observations.get("targets"))
            .and_then(|targets| targets.get(&path))
        {
            if observed.get("content_sha256").and_then(Value::as_str) != Some(&content_sha)
                || observed.get("git_blob_oid").and_then(Value::as_str) != Some(&blob)
            {
                return Err(ArchiveError::new(
                    "target_identity_mismatch",
                    format!("recorded target mismatch: {path}"),
                ));
            }
        }
        let base_present = Command::new("git")
            .arg("-C")
            .arg(root)
            .args(["cat-file", "-e", &format!("{base_oid}:{path}")])
            .status()
            .is_ok_and(|status| status.success());
        let (base_content_sha256, base_git_blob_oid) = if base_present {
            let content = Command::new("git")
                .arg("-C")
                .arg(root)
                .args(["show", &format!("{base_oid}:{path}")])
                .output()
                .map_err(|detail| error("target_identity_mismatch", detail.to_string()))?;
            if !content.status.success() {
                return Err(ArchiveError::new(
                    "target_identity_mismatch",
                    format!("base target cannot be read: {path}"),
                ));
            }
            let oid = git(
                root,
                &["rev-parse", "--verify", &format!("{base_oid}:{path}")],
                "target_identity_mismatch",
            )?;
            (Some(hash(&content.stdout)), Some(oid))
        } else {
            (None, None)
        };
        identities.push(TargetIdentity {
            path,
            content_sha256: content_sha,
            git_blob_oid: blob,
            base_present,
            base_content_sha256,
            base_git_blob_oid,
        });
    }
    Ok((identities, head, base_oid))
}

fn porcelain_paths(root: &Path) -> Result<Vec<String>, ArchiveError> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["status", "--porcelain=v1", "--untracked-files=all"])
        .output()
        .map_err(|detail| error("source_snapshot_invalid", detail.to_string()))?;
    if !output.status.success() {
        return Err(error(
            "source_snapshot_invalid",
            String::from_utf8_lossy(&output.stderr).trim(),
        ));
    }
    let text = String::from_utf8_lossy(&output.stdout);
    let mut result = Vec::new();
    for line in text.lines() {
        if line.len() < 3
            || line.as_bytes()[2] != b' '
            || line.contains('\0')
            || line.contains('\n')
            || line.contains('\r')
        {
            return Err(error(
                "source_snapshot_invalid",
                "porcelain-v1 line is malformed",
            ));
        }
        let path = &line[3..];
        for value in path.split(" -> ") {
            let value = value.trim().trim_matches('"');
            if !relative_safe(value) {
                return Err(error(
                    "source_snapshot_invalid",
                    "porcelain-v1 path is unsafe",
                ));
            }
        }
        if path
            .split(" -> ")
            .all(|path| is_source_snapshot_path(path.trim().trim_matches('"')))
        {
            result.push(line.to_owned());
        }
    }
    Ok(result)
}

fn self_hashed_event(record: &mut RuntimeEventRecord) -> Result<Vec<u8>, ArchiveError> {
    let mut zeroed = record.clone();
    zeroed.artifact_sha256 = "0".repeat(64);
    let bytes = serde_json::to_vec(&zeroed)
        .map_err(|detail| error("schema_invalid", detail.to_string()))?;
    let mut preimage = bytes;
    preimage.push(b'\n');
    record.artifact_sha256 = hash(&preimage);
    let mut output =
        serde_json::to_vec(record).map_err(|detail| error("schema_invalid", detail.to_string()))?;
    output.push(b'\n');
    Ok(output)
}

fn publication_target(
    context: &ArchiveContext,
    path: &Path,
    bytes: &[u8],
) -> Result<(ParentOwnedPathReceipt, String, bool), ArchiveError> {
    let attested = ParentRootAttestor::new()
        .attest(&AttestationRequest {
            cwd: context.source_root.clone(),
            explicit_root: Some(context.source_root.clone()),
            source_root: None,
            clone_root: None,
            topic_marker: None,
            gitmodules: None,
            owner_evidence: None,
            expected_remote: None,
            expected_module_digest: None,
            child_handoff_token: None,
            purpose: NonEmptyTrimmedString::new("runtime-event-publication")
                .map_err(|detail| error("parent_root_invalid", detail.to_string()))?,
            nonce: Nonce128::generate()
                .map_err(|detail| error("parent_root_invalid", detail.to_string()))?,
        })
        .map_err(|detail| error("parent_root_invalid", detail.to_string()))?;
    let purpose = NonEmptyTrimmedString::new("runtime-event-publication").unwrap();
    match attested
        .publish_parent_owned_file_noreplace(path, bytes, purpose.clone())
        .map_err(|detail| error("publication_failure", detail.to_string()))?
    {
        ParentOwnedNoReplaceOutcome::Published(receipt) => {
            let readback = attested
                .read_parent_owned_file(&receipt)
                .map_err(|detail| error("publication_uncertain", detail.to_string()))?;
            if readback != bytes {
                return Err(error(
                    "publication_uncertain",
                    "published runtime event readback differs",
                ));
            }
            Ok((receipt, "publish".to_owned(), false))
        }
        ParentOwnedNoReplaceOutcome::Duplicate(receipt) => {
            if attested
                .read_parent_owned_file(&receipt)
                .map_err(|detail| error("publication_uncertain", detail.to_string()))?
                != bytes
            {
                return Err(error(
                    "record_collision",
                    "runtime event target bytes differ",
                ));
            }
            Ok((receipt, "recovery".to_owned(), true))
        }
        ParentOwnedNoReplaceOutcome::Conflict(_) => Err(error(
            "record_collision",
            "runtime event target bytes differ",
        )),
    }
}

fn observation_bytes(value: &mut Observation) -> Result<Vec<u8>, ArchiveError> {
    let mut zeroed = value.clone();
    zeroed.observation_sha256 = "0".repeat(64);
    let mut bytes = serde_json::to_vec(&zeroed)
        .map_err(|detail| error("publication_observation_invalid", detail.to_string()))?;
    bytes.push(b'\n');
    value.observation_sha256 = hash(&bytes);
    let mut output = serde_json::to_vec(value)
        .map_err(|detail| error("publication_observation_invalid", detail.to_string()))?;
    output.push(b'\n');
    Ok(output)
}

fn receipt_bytes(value: &mut Receipt) -> Result<Vec<u8>, ArchiveError> {
    let mut zeroed = value.clone();
    zeroed.receipt_sha256 = "0".repeat(64);
    let mut bytes = serde_json::to_vec(&zeroed)
        .map_err(|detail| error("publication_receipt_invalid", detail.to_string()))?;
    bytes.push(b'\n');
    value.receipt_sha256 = hash(&bytes);
    let mut output = serde_json::to_vec(value)
        .map_err(|detail| error("publication_receipt_invalid", detail.to_string()))?;
    output.push(b'\n');
    Ok(output)
}

fn load_publication_chain(
    context: &ArchiveContext,
    attempt: &OutcomeAttempt,
    target: &Path,
    attempt_id: &str,
    artifact_sha: &str,
    materialization_id: &str,
) -> Result<PublicationChain, ArchiveError> {
    static OBSERVATION_NAME: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    static RECEIPT_NAME: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    let observation_name = OBSERVATION_NAME.get_or_init(|| {
        regex::Regex::new(r"^(?P<sequence>[0-9]{6})-(?P<sha>[0-9a-f]{64})\.json$")
            .expect("static outcome observation filename regex")
    });
    let receipt_name = RECEIPT_NAME.get_or_init(|| {
        regex::Regex::new(r"^runtime_event\.(?P<unit>[0-9a-f]{16})\.outcome\.(?P<attempt>[0-9a-f]{64})\.(?P<sequence>[0-9]{6})\.json$")
            .expect("static outcome receipt filename regex")
    });
    let mut observations = Vec::new();
    let attempt_absolute = attempt
        .boundary
        .resolve(&attempt.directory)
        .map_err(|detail| error("publication_attempt_lock_invalid", detail))?;
    for entry in fs::read_dir(&attempt_absolute)
        .map_err(|detail| ArchiveError::new("publication_attempt_collision", detail.to_string()))?
    {
        let entry = entry.map_err(|detail| {
            ArchiveError::new("publication_attempt_collision", detail.to_string())
        })?;
        let name = entry.file_name().to_string_lossy().into_owned();
        if name == ".attempt.lock" {
            continue;
        }
        let Some(captures) = observation_name.captures(&name) else {
            return Err(error(
                "publication_attempt_collision",
                "unexpected attempt-local semantic file",
            ));
        };
        let metadata = fs::symlink_metadata(entry.path())
            .map_err(|detail| error("publication_observation_invalid", detail.to_string()))?;
        if !metadata.is_file() || metadata.file_type().is_symlink() {
            return Err(error(
                "publication_observation_invalid",
                "observation is not a regular file",
            ));
        }
        let relative = attempt.directory.join(&name);
        let raw = attempt
            .boundary
            .read_bytes(&relative)
            .map_err(|detail| error("publication_observation_uncertain", detail))?
            .ok_or_else(|| {
                error(
                    "publication_observation_uncertain",
                    "observation disappeared",
                )
            })?;
        let value = graph::validate_runtime_publication_observation(&raw)
            .map_err(|detail| error("publication_observation_invalid", detail))?;
        let observation: Observation = serde_json::from_value(value)
            .map_err(|detail| error("publication_observation_invalid", detail.to_string()))?;
        let sequence = captures
            .name("sequence")
            .unwrap()
            .as_str()
            .parse::<u64>()
            .unwrap_or(0);
        if sequence != observation.sequence
            || captures.name("sha").unwrap().as_str() != observation.observation_sha256
            || observation.attempt_id != attempt_id
            || observation.artifact_sha256 != artifact_sha
            || observation.materialization_id != materialization_id
            || observation.artifact_path
                != target
                    .strip_prefix(&context.source_root)
                    .unwrap_or(target)
                    .to_string_lossy()
                    .replace('\\', "/")
        {
            return Err(error(
                "publication_observation_invalid",
                "observation identity does not match this attempt",
            ));
        }
        observations.push((observation, raw));
    }
    observations.sort_by_key(|(observation, _)| observation.sequence);
    if observations.len() > 2
        || observations
            .iter()
            .enumerate()
            .any(|(index, (observation, _))| observation.sequence != index as u64 + 1)
        || (observations.len() == 2
            && (observations[0].0.outcome != "uncertain"
                || observations[1].0.outcome != "committed"))
        || observations
            .iter()
            .enumerate()
            .any(|(index, (observation, _))| {
                observation.prior_observation_sha256
                    != if index == 0 {
                        None
                    } else {
                        Some(observations[index - 1].0.observation_sha256.clone())
                    }
            })
    {
        return Err(error(
            "publication_observation_invalid",
            "observation chain is not monotone",
        ));
    }
    let mut receipts = Vec::new();
    let target_prefix = format!(
        "{}.outcome.",
        target.file_stem().unwrap_or_default().to_string_lossy()
    );
    let target_unit = target
        .file_stem()
        .and_then(|name| name.to_str())
        .and_then(|name| name.strip_prefix("runtime_event."))
        .unwrap_or_default();
    for entry in fs::read_dir(
        target
            .parent()
            .ok_or_else(|| error("publication_receipt_invalid", "receipt parent is absent"))?,
    )
    .map_err(|detail| ArchiveError::new("publication_receipt_invalid", detail.to_string()))?
    {
        let entry = entry.map_err(|detail| {
            ArchiveError::new("publication_receipt_invalid", detail.to_string())
        })?;
        let name = entry.file_name().to_string_lossy().into_owned();
        if !name.starts_with(&target_prefix) {
            continue;
        }
        let captures = receipt_name
            .captures(&name)
            .ok_or_else(|| error("publication_receipt_invalid", "receipt basename is invalid"))?;
        if captures.name("attempt").unwrap().as_str() != attempt_id {
            return Err(error(
                "publication_attempt_collision",
                "receipt belongs to another attempt",
            ));
        }
        if captures.name("unit").unwrap().as_str() != target_unit {
            return Err(error(
                "publication_receipt_invalid",
                "receipt unit does not match artifact",
            ));
        }
        let metadata = fs::symlink_metadata(entry.path())
            .map_err(|detail| error("publication_receipt_invalid", detail.to_string()))?;
        if !metadata.is_file() || metadata.file_type().is_symlink() {
            return Err(error(
                "publication_receipt_invalid",
                "receipt is not a regular file",
            ));
        }
        let raw = super::read_file_nofollow(&entry.path())
            .map_err(|detail| error("publication_receipt_uncertain", detail.to_string()))?;
        let value = graph::validate_runtime_publication_receipt(&raw)
            .map_err(|detail| error("publication_receipt_invalid", detail))?;
        let receipt: Receipt = serde_json::from_value(value)
            .map_err(|detail| error("publication_receipt_invalid", detail.to_string()))?;
        let sequence = captures
            .name("sequence")
            .unwrap()
            .as_str()
            .parse::<u64>()
            .unwrap_or(0);
        if sequence != receipt.sequence
            || receipt.attempt_id != attempt_id
            || receipt.artifact_path
                != target
                    .strip_prefix(&context.source_root)
                    .unwrap_or(target)
                    .to_string_lossy()
                    .replace('\\', "/")
            || receipt.artifact_sha256 != artifact_sha
            || receipt.materialization_id != materialization_id
        {
            return Err(error(
                "publication_receipt_invalid",
                "receipt identity does not match this attempt",
            ));
        }
        receipts.push(DurableReceipt {
            path: entry.path(),
            bytes: raw,
            value: receipt,
        });
    }
    receipts.sort_by_key(|receipt| receipt.value.sequence);
    if receipts.len() > 2
        || receipts
            .iter()
            .enumerate()
            .any(|(index, receipt)| receipt.value.sequence != index as u64 + 1)
        || receipts.iter().enumerate().any(|(index, receipt)| {
            let Some((observation, _)) = observations.get(index) else {
                return true;
            };
            receipt.value.observation.observation_sha256 != observation.observation_sha256
                || &receipt.value.observation != observation
                || receipt.value.prior_receipt_sha256
                    != if index == 0 {
                        None
                    } else {
                        Some(receipts[index - 1].value.receipt_sha256.clone())
                    }
        })
        || (receipts.len() == 2
            && (receipts[0].value.observation.outcome != "uncertain"
                || receipts[1].value.observation.outcome != "committed"))
    {
        return Err(error(
            "publication_receipt_invalid",
            "receipt chain is not monotone",
        ));
    }
    Ok(PublicationChain {
        observations,
        receipts,
    })
}

fn persist_outcome(
    context: &ArchiveContext,
    attempt: &OutcomeAttempt,
    target: &Path,
    attempt_id: &str,
    artifact_sha: &str,
    materialization_id: &str,
    sequence: u64,
    prior_observation_sha: Option<String>,
    prior_receipt_sha: Option<String>,
    evidence: ObservationEvidence,
) -> Result<DurableReceipt, ArchiveError> {
    let committed = evidence.causal_gap == false
        && evidence.target_directory_fsync_status == "succeeded"
        && evidence.readback_status == "verified"
        && evidence.readback_sha256.as_deref() == Some(artifact_sha);
    let mut observation = Observation {
        schema: OBSERVATION_SCHEMA.to_owned(),
        attempt_id: attempt_id.to_owned(),
        artifact_path: target
            .strip_prefix(&context.source_root)
            .map_err(|_| error("schema_invalid", "event target escapes source root"))?
            .to_string_lossy()
            .replace('\\', "/"),
        artifact_sha256: artifact_sha.to_owned(),
        materialization_id: materialization_id.to_owned(),
        sequence,
        prior_observation_sha256: prior_observation_sha,
        outcome: if committed { "committed" } else { "uncertain" }.to_owned(),
        evidence,
        observation_sha256: "0".repeat(64),
    };
    let raw_observation = observation_bytes(&mut observation)?;
    let boundary = &attempt.boundary;
    let obs_sha = observation.observation_sha256.clone();
    let observation_relative = attempt
        .directory
        .join(format!("{sequence:06}-{obs_sha}.json"));
    boundary
        .boundary()
        .write_once_bytes(&observation_relative, &raw_observation)
        .map_err(|detail| error("publication_observation_failed", detail))?;
    if boundary
        .read_bytes(&observation_relative)
        .map_err(|detail| error("publication_observation_uncertain", detail))?
        .as_deref()
        != Some(raw_observation.as_slice())
    {
        return Err(error(
            "publication_observation_uncertain",
            "observation readback differs",
        ));
    }
    let mut receipt = Receipt {
        schema: RECEIPT_SCHEMA.to_owned(),
        attempt_id: attempt_id.to_owned(),
        artifact_path: observation.artifact_path.clone(),
        artifact_sha256: artifact_sha.to_owned(),
        materialization_id: materialization_id.to_owned(),
        sequence,
        prior_receipt_sha256: prior_receipt_sha,
        observation,
        receipt_sha256: "0".repeat(64),
    };
    let raw_receipt = receipt_bytes(&mut receipt)?;
    let receipt_path = target.with_file_name(format!(
        "{}.outcome.{}.{}.json",
        target.file_stem().unwrap().to_string_lossy(),
        attempt_id,
        format!("{sequence:06}")
    ));
    let parent = ParentRootAttestor::new()
        .attest(&AttestationRequest {
            cwd: context.source_root.clone(),
            explicit_root: Some(context.source_root.clone()),
            source_root: None,
            clone_root: None,
            topic_marker: None,
            gitmodules: None,
            owner_evidence: None,
            expected_remote: None,
            expected_module_digest: None,
            child_handoff_token: None,
            purpose: NonEmptyTrimmedString::new("runtime-receipt-publication").unwrap(),
            nonce: Nonce128::generate()
                .map_err(|detail| error("publication_receipt_failed", detail.to_string()))?,
        })
        .map_err(|detail| error("publication_receipt_failed", detail.to_string()))?;
    let outcome = parent
        .publish_parent_owned_file_noreplace(
            &receipt_path,
            &raw_receipt,
            NonEmptyTrimmedString::new("runtime-receipt-publication").unwrap(),
        )
        .map_err(|detail| error("publication_receipt_failed", detail.to_string()))?;
    let receipt_capability = match outcome {
        ParentOwnedNoReplaceOutcome::Published(receipt_capability)
        | ParentOwnedNoReplaceOutcome::Duplicate(receipt_capability) => receipt_capability,
        ParentOwnedNoReplaceOutcome::Conflict(_) => {
            return Err(error(
                "publication_receipt_collision",
                "receipt bytes differ",
            ));
        }
    };
    if parent
        .read_parent_owned_file(&receipt_capability)
        .map_err(|detail| error("publication_receipt_uncertain", detail.to_string()))?
        != raw_receipt
    {
        return Err(error(
            "publication_receipt_uncertain",
            "receipt readback differs",
        ));
    }
    if let Err(detail) = parent.sync_parent_owned_directory(&receipt_capability) {
        return Err(error("publication_receipt_uncertain", detail.to_string()));
    }
    let receipt_relative = receipt_path
        .strip_prefix(&context.source_root)
        .map_err(|_| error("publication_receipt_invalid", "receipt escapes source root"))?;
    let receipt_relative = context.source_root.join(receipt_relative);
    let validated = graph::validate_runtime_publication_receipt(&raw_receipt)
        .map_err(|detail| error("publication_receipt_invalid", detail))?;
    Ok(DurableReceipt {
        path: receipt_relative,
        bytes: raw_receipt,
        value: serde_json::from_value(validated)
            .map_err(|detail| error("publication_receipt_invalid", detail.to_string()))?,
    })
}

fn confirm_source_file(
    context: &ArchiveContext,
    path: &Path,
    purpose: &str,
) -> Result<Vec<u8>, ArchiveError> {
    let attested = ParentRootAttestor::new()
        .attest(&AttestationRequest {
            cwd: context.source_root.clone(),
            explicit_root: Some(context.source_root.clone()),
            source_root: None,
            clone_root: None,
            topic_marker: None,
            gitmodules: None,
            owner_evidence: None,
            expected_remote: None,
            expected_module_digest: None,
            child_handoff_token: None,
            purpose: NonEmptyTrimmedString::new(purpose)
                .map_err(|detail| error("parent_root_invalid", detail.to_string()))?,
            nonce: Nonce128::generate()
                .map_err(|detail| error("parent_root_invalid", detail.to_string()))?,
        })
        .map_err(|detail| error("parent_root_invalid", detail.to_string()))?;
    let receipt = attested
        .resolve_parent_owned_path(
            path,
            NonEmptyTrimmedString::new(purpose)
                .map_err(|detail| error("parent_root_invalid", detail.to_string()))?,
        )
        .map_err(|detail| error("publication_uncertain", detail.to_string()))?;
    let bytes = attested
        .read_parent_owned_file(&receipt)
        .map_err(|detail| error("publication_uncertain", detail.to_string()))?;
    attested
        .sync_parent_owned_directory(&receipt)
        .map_err(|detail| error("publication_uncertain", detail.to_string()))?;
    let confirmed = attested
        .read_parent_owned_file(&receipt)
        .map_err(|detail| error("publication_uncertain", detail.to_string()))?;
    if bytes != confirmed {
        return Err(error(
            "publication_uncertain",
            "parent-owned readback changed",
        ));
    }
    Ok(confirmed)
}

fn print_success(
    context: &ArchiveContext,
    target_path: &str,
    unit_id: &str,
    record_sha: &str,
    attempt_id: &str,
    materialization_id: &str,
    receipt: &DurableReceipt,
) {
    println!("RUNTIME_EVENT_PATH={target_path}");
    println!("RUNTIME_EVENT_UNIT_ID={unit_id}");
    println!("RUNTIME_EVENT_RECORD_SHA256={record_sha}");
    println!("RUNTIME_EVENT_MATERIALIZATION_ID={materialization_id}");
    println!("RUNTIME_EVENT_ATTEMPT_ID={attempt_id}");
    println!(
        "RUNTIME_EVENT_RECEIPT_PATH={}",
        receipt
            .path
            .strip_prefix(&context.source_root)
            .unwrap_or(&receipt.path)
            .to_string_lossy()
            .replace('\\', "/")
    );
    println!(
        "RUNTIME_EVENT_RECEIPT_SHA256={}",
        receipt.value.receipt_sha256
    );
    println!("RUNTIME_EVENT_OUTCOME=committed");
    println!("RUNTIME_EVENT_MATERIALIZE=pass");
}

fn acquire_outcome_attempt(
    context: &ArchiveContext,
    attempt_id: &str,
) -> Result<OutcomeAttempt, ArchiveError> {
    let runtime_root = archive_runtime_root(context)?;
    let boundary =
        RuntimeSpoolBoundary::for_source(&context.source_root, Some(&runtime_root), true)
            .map_err(|detail| error("publication_attempt_lock_invalid", detail))?;
    let spool_root = eval_archive_paths::runtime_event_publication_outcome_spool_root(
        &context.source_root,
        Some(&runtime_root),
    )
    .map_err(|detail| error("publication_attempt_lock_invalid", detail))?;
    let relative_root = spool_root.strip_prefix(boundary.root()).map_err(|_| {
        error(
            "publication_attempt_lock_invalid",
            "outcome spool root is outside runtime",
        )
    })?;
    if relative_root != Path::new("spool/publication-outcome") {
        return Err(error(
            "publication_attempt_lock_invalid",
            "outcome spool root is not canonical",
        ));
    }
    let directory = relative_root.join(attempt_id);
    boundary
        .boundary()
        .ensure_directory(&directory)
        .map_err(|detail| error("publication_attempt_lock_invalid", detail))?;
    validate_attempt_directory(boundary.root())?;
    validate_attempt_directory(&spool_root)?;
    validate_attempt_directory(&boundary.root().join(&directory))?;
    let lock = boundary
        .boundary()
        .try_lock_with_empty_marker(&directory.join(".attempt.lock"))
        .map_err(|detail| error("publication_attempt_busy", detail))?;
    Ok(OutcomeAttempt {
        boundary,
        directory,
        _lock: lock,
    })
}

pub(super) fn materialize(
    context: &ArchiveContext,
    options: &CommandOptions,
) -> Result<i32, ArchiveError> {
    let family = options.required("result-family")?;
    let run_id = options.required("run-id")?;
    let gate_id = options.required("gate-id")?;
    let base_ref = options.required("base-ref")?;
    if run_id.is_empty()
        || run_id.contains('/')
        || run_id.contains('\\')
        || matches!(run_id, "." | "..")
    {
        return Err(error("run_id_invalid", run_id));
    }
    let spec = spec(family, gate_id)?;
    let active = context.source_root.join("reports/agents").join(run_id);
    let active = fs::canonicalize(&active)
        .map_err(|_| error("source_unavailable", "active run directory is absent"))?;
    let pointer = fs::read_to_string(context.source_root.join("reports/agents/.active_run"))
        .map_err(|_| error("source_unavailable", "active run pointer is absent"))?;
    let pointer = pointer.trim();
    let pointed = PathBuf::from(pointer);
    let pointed = if pointed.is_absolute() {
        pointed
    } else {
        context.source_root.join("reports/agents").join(pointed)
    };
    if fs::canonicalize(pointed)
        .map_err(|_| error("source_unavailable", "active run directory is absent"))?
        != active
    {
        return Err(error(
            "source_identity_mismatch",
            "run id does not match the active run pointer",
        ));
    }
    let result_path = active.join(spec.artifact_name);
    let result_bytes = super::read_file_nofollow(&result_path).map_err(|_| {
        error(
            "result_authority_mismatch",
            format!("fixed result artifact is absent: {}", result_path.display()),
        )
    })?;
    let parsed = match spec.family {
        "requirements" | "design" | "review" => {
            let text = std::str::from_utf8(&result_bytes)
                .map_err(|_| error("result_authority_mismatch", "review artifact is not UTF-8"))?;
            parse_review(text)?
        }
        "validation" => parse_validation(&result_bytes, spec.gate_id)?,
        "lifecycle" => parse_lifecycle(
            std::str::from_utf8(&result_bytes).map_err(|_| {
                error(
                    "result_authority_mismatch",
                    "closeout artifact is not UTF-8",
                )
            })?,
            spec.gate_id,
        )?,
        _ => unreachable!(),
    };
    if parsed
        .base_ref
        .as_deref()
        .is_some_and(|value| value != base_ref)
    {
        return Err(error(
            "target_identity_mismatch",
            "result base_ref differs from selected base ref",
        ));
    }
    if let Some(evidence) = parsed.evidence_path.as_deref() {
        if !is_source_snapshot_path(evidence) {
            return Err(error(
                "result_authority_mismatch",
                "lifecycle evidence_path is outside source scope",
            ));
        }
        let evidence_path = context.source_root.join(evidence);
        let evidence_bytes = super::read_file_nofollow(&evidence_path)
            .map_err(|detail| ArchiveError::new("result_authority_mismatch", detail.to_string()))?;
        if parsed.evidence_sha256.as_deref() != Some(hash(&evidence_bytes).as_str()) {
            return Err(error(
                "result_authority_mismatch",
                "lifecycle evidence hash does not match bytes",
            ));
        }
        if !parsed.target_paths.contains(&evidence.to_owned()) {
            return Err(error(
                "result_authority_mismatch",
                "lifecycle evidence_path is not a target path",
            ));
        }
    }
    let artifact_sha = hash(&result_bytes);
    let artifact_relative = result_path
        .strip_prefix(&context.source_root)
        .map_err(|_| {
            error(
                "result_authority_mismatch",
                "result artifact escapes source root",
            )
        })?
        .to_string_lossy()
        .replace('\\', "/");
    let artifact_blob = git_blob(&context.source_root, &artifact_relative)?;
    if !hex(&artifact_blob, 40) {
        return Err(error(
            "result_authority_mismatch",
            "result artifact Git blob is unavailable",
        ));
    }
    let (targets, head_oid, base_oid) = target_identities(&context.source_root, &parsed, base_ref)?;
    if spec.family == "validation" {
        let observations = parsed.observations.as_ref().unwrap();
        if observations.get("head_oid").and_then(Value::as_str) != Some(&head_oid)
            || observations.get("base_oid").and_then(Value::as_str) != Some(&base_oid)
        {
            return Err(error(
                "target_identity_mismatch",
                "validation observations do not match Git identities",
            ));
        }
    }
    let source_snapshot = SourceSnapshot {
        head_oid: head_oid.clone(),
        base_ref: base_ref.to_owned(),
        base_oid: base_oid.clone(),
        porcelain_v1: porcelain_paths(&context.source_root)?,
    };
    let gate_result = parsed.gate_result.clone();
    let source_event = context_discovery::load_source_event(context, &active)?;
    let record_sha = source_event.record_sha256.clone();
    let unit_id = options.value("unit-id").unwrap_or(&record_sha[..16]);
    if !hex(unit_id, 16) || unit_id != &record_sha[..16] {
        return Err(error(
            "source_identity_mismatch",
            "unit id does not match source record hash",
        ));
    }
    let target = active.join(format!("runtime_event.{unit_id}.json"));
    let target_path = target
        .strip_prefix(&context.source_root)
        .map_err(|_| error("schema_invalid", "event target escapes source root"))?
        .to_string_lossy()
        .replace('\\', "/");
    let source_event = RuntimeEventSource {
        decision: parsed.decision.clone(),
        applicable_gate_result: gate_result.clone(),
        ..source_event
    };
    let result_artifact = ResultArtifact {
        path: artifact_relative,
        schema: spec.schema.to_owned(),
        artifact_sha256: artifact_sha,
        artifact_blob_oid: artifact_blob,
        gate_id: spec.gate_id.to_owned(),
        gate_result: gate_result.clone(),
        target_paths: targets.iter().map(|target| target.path.clone()).collect(),
        base_ref: base_ref.to_owned(),
        base_oid: base_oid.clone(),
    };
    let gate = Gate {
        id: spec.gate_id.to_owned(),
        result: gate_result,
    };
    let preimage = MaterializationPreimage {
        schema: MATERIALIZATION_SCHEMA,
        result_family: spec.family,
        gate: gate.clone(),
        source_event: SourceEventPreimage {
            stable_record_id: &source_event.stable_record_id,
            rollout_path_sha256: &source_event.rollout_path_sha256,
            rollout_file_sha256: &source_event.rollout_file_sha256,
            record_line: source_event.record_line,
            record_byte_offset: source_event.record_byte_offset,
            record_byte_length: source_event.record_byte_length,
        },
        result_artifact: ResultArtifactPreimage {
            artifact_sha256: &result_artifact.artifact_sha256,
            artifact_blob_oid: &result_artifact.artifact_blob_oid,
            gate_id: &result_artifact.gate_id,
        },
        target_identities: &targets,
        source_snapshot: SourceSnapshotPreimage {
            head_oid: &source_snapshot.head_oid,
            base_ref: &source_snapshot.base_ref,
            base_oid: &source_snapshot.base_oid,
        },
    };
    let preimage_bytes = serde_json::to_vec(&preimage)
        .map_err(|detail| error("schema_invalid", detail.to_string()))?;
    let mut preimage_bytes = preimage_bytes;
    preimage_bytes.push(b'\n');
    let mut materialization_hash = MATERIALIZATION_SCHEMA.as_bytes().to_vec();
    materialization_hash.push(0);
    materialization_hash.extend_from_slice(&preimage_bytes);
    let materialization_id = hash(&materialization_hash);
    let mut attempt_hash = ATTEMPT_SCHEMA.as_bytes().to_vec();
    attempt_hash.push(0);
    attempt_hash.extend_from_slice(materialization_id.as_bytes());
    attempt_hash.push(0);
    attempt_hash.extend_from_slice(target_path.as_bytes());
    let attempt_id = hash(&attempt_hash);
    let intent = PublicationIntent {
        schema: INTENT_SCHEMA.to_owned(),
        attempt_id: attempt_id.clone(),
        target_path: target_path.clone(),
        prepared_state: "prepared".to_owned(),
    };
    let mut record = RuntimeEventRecord {
        schema: EVENT_SCHEMA.to_owned(),
        materialization_id,
        result_family: spec.family.to_owned(),
        gate,
        source_event,
        result_artifact,
        target_identities: targets,
        source_snapshot,
        publication_intent: intent,
        artifact_sha256: "0".repeat(64),
    };
    let event_bytes = self_hashed_event(&mut record)?;
    let attempt = acquire_outcome_attempt(context, &attempt_id)?;
    let chain = load_publication_chain(
        context,
        &attempt,
        &target,
        &attempt_id,
        &record.artifact_sha256,
        &record.materialization_id,
    )?;
    if !chain.observations.is_empty() || !chain.receipts.is_empty() {
        let existing = confirm_source_file(context, &target, "runtime-event-publication")?;
        if existing != event_bytes {
            return Err(error("record_collision", "artifact target bytes differ"));
        }
    }
    if let Some(latest) = chain.receipts.last() {
        if latest.value.observation.outcome == "committed" {
            if confirm_source_file(context, &latest.path, "runtime-receipt-publication")?
                != latest.bytes
            {
                return Err(error(
                    "publication_receipt_uncertain",
                    "receipt readback changed",
                ));
            }
            print_success(
                context,
                &target_path,
                unit_id,
                &record_sha,
                &attempt_id,
                &record.materialization_id,
                latest,
            );
            return Ok(0);
        }
    }

    let latest_durable = if chain.observations.is_empty() {
        let (_target_receipt, publication_source, causal_gap) =
            publication_target(context, &target, &event_bytes)?;
        let artifact_readback = confirm_source_file(context, &target, "runtime-event-publication")?;
        if artifact_readback != event_bytes {
            return Err(error(
                "record_collision",
                "runtime event target bytes differ",
            ));
        }
        let evidence = ObservationEvidence {
            source: publication_source,
            causal_gap,
            target_presence: "present".to_owned(),
            rename_status: if causal_gap {
                "recovered_present"
            } else {
                "completed"
            }
            .to_owned(),
            target_directory_fsync_status: "succeeded".to_owned(),
            readback_status: "verified".to_owned(),
            readback_sha256: Some(hash(&artifact_readback)),
        };
        persist_outcome(
            context,
            &attempt,
            &target,
            &attempt_id,
            &record.artifact_sha256,
            &record.materialization_id,
            1,
            None,
            None,
            evidence,
        )?
    } else {
        let prior = &chain.observations[0].0;
        let receipt = chain.receipts.first();
        if receipt.is_none() {
            persist_outcome(
                context,
                &attempt,
                &target,
                &attempt_id,
                &record.artifact_sha256,
                &record.materialization_id,
                prior.sequence,
                prior.prior_observation_sha256.clone(),
                None,
                prior.evidence.clone(),
            )?
        } else {
            receipt.unwrap().clone()
        }
    };
    if latest_durable.value.observation.outcome == "committed" {
        print_success(
            context,
            &target_path,
            unit_id,
            &record_sha,
            &attempt_id,
            &record.materialization_id,
            &latest_durable,
        );
        return Ok(0);
    }
    if latest_durable.value.sequence != 1 {
        return Err(error(
            "publication_uncertain",
            "latest confirmed outcome is uncertain",
        ));
    }
    let artifact_readback = confirm_source_file(context, &target, "runtime-event-publication")?;
    if artifact_readback != event_bytes {
        return Err(error(
            "publication_observation_invalid",
            "artifact recovery readback differs",
        ));
    }
    let recovery = ObservationEvidence {
        source: "recovery".to_owned(),
        causal_gap: false,
        target_presence: "present".to_owned(),
        rename_status: "recovered_present".to_owned(),
        target_directory_fsync_status: "succeeded".to_owned(),
        readback_status: "verified".to_owned(),
        readback_sha256: Some(hash(&artifact_readback)),
    };
    let second = persist_outcome(
        context,
        &attempt,
        &target,
        &attempt_id,
        &record.artifact_sha256,
        &record.materialization_id,
        2,
        Some(latest_durable.value.observation.observation_sha256.clone()),
        Some(latest_durable.value.receipt_sha256.clone()),
        recovery,
    )?;
    if second.value.observation.outcome != "committed" {
        return Err(error(
            "publication_uncertain",
            "latest confirmed outcome is uncertain",
        ));
    }
    print_success(
        context,
        &target_path,
        unit_id,
        &record_sha,
        &attempt_id,
        &record.materialization_id,
        &second,
    );
    Ok(0)
}

#[cfg(test)]
mod tests {
    use super::{parse_review, relative_safe, spec};

    #[test]
    fn fixed_result_families_are_closed_by_family_and_gate() {
        assert_eq!(
            spec("requirements", "requirements-review")
                .unwrap()
                .artifact_name,
            "requirements_review.md"
        );
        assert_eq!(
            spec("design", "design-review").unwrap().schema,
            "ReviewArtifactV1"
        );
        assert_eq!(
            spec("validation", "validation").unwrap().artifact_name,
            "validation_result.json"
        );
        assert!(spec("review", "design-review").is_err());
        assert!(spec("unknown", "unknown").is_err());
    }

    #[test]
    fn review_result_uses_the_canonical_decision_identity() {
        let review = format!(
            "# Review\n\n- Design artifact path: `docs/design.md`\n- review_target_sha256={}\n\n## Decision\n\nAPPROVE\n\n## Evidence\n\nConcrete source-bound review.\n",
            "a".repeat(64)
        );
        let result = parse_review(&review).unwrap();
        assert_eq!(result.gate_result, "APPROVE");
        assert_eq!(result.decision, "APPROVE");
        assert_eq!(result.target_paths, ["docs/design.md"]);
        assert!(parse_review("## Decision\nREVISE\n",).is_err());
    }

    #[test]
    fn source_snapshot_paths_reject_traversal_and_non_posix_seams() {
        assert!(relative_safe("docs/design.md"));
        assert!(!relative_safe("../outside.md"));
        assert!(!relative_safe("docs\\design.md"));
        assert!(!relative_safe("/absolute.md"));
    }
}
