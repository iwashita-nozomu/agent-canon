//! Native producer for immutable ContextDiscoveryV1 certificates.

use super::{ArchiveContext, ArchiveError, CommandOptions};
use agent_canon::authority::{
    AttestationRequest, NonEmptyTrimmedString, Nonce128, ParentRootAttestor,
};
use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::OnceLock;
use time::format_description::well_known::Rfc3339;
use time::OffsetDateTime;

const SESSION_ROOT_ENV: &str = "AGENT_CANON_CODEX_SESSION_ROOT";
const CERTIFICATE_SCHEMA: &str = "agent_canon.context_discovery_certificate.v1";
const CONTEXT_SCHEMA: &str = "codex.context_discovery.v1";
const ACTIVE_RUN_POINTER: &str = "reports/agents/.active_run";

#[derive(Deserialize, Serialize)]
struct Certificate {
    schema: String,
    certificate_id: String,
    context: CertificateContext,
    repository: RepositoryIdentity,
    rollout: RolloutIdentity,
}

#[derive(Deserialize, Serialize)]
struct CertificateContext {
    schema: String,
    agent_id: String,
    agent_context_id: String,
    codex_thread_id: String,
    parent_id: String,
    turn_id: String,
    role: String,
}

#[derive(Deserialize, Serialize)]
struct RepositoryIdentity {
    root: String,
    root_path_sha256: String,
    head_oid: String,
    tree_oid: String,
}

#[derive(Deserialize, Serialize)]
struct RolloutIdentity {
    path: String,
    path_sha256: String,
    file_sha256: String,
    session_cwd: String,
    session_meta: RecordRange,
    task_complete: RecordRange,
}

#[derive(Deserialize, Serialize)]
struct RecordRange {
    line: usize,
    byte_offset: usize,
    byte_length: usize,
    record_sha256: String,
}

struct SourceRecord {
    line: usize,
    offset: usize,
    bytes: Vec<u8>,
    value: Value,
}

#[derive(Clone, Serialize)]
pub(super) struct RuntimeEventSource {
    pub agent_id: String,
    pub agent_context_id: String,
    pub codex_thread_id: String,
    pub parent_id: String,
    pub turn_id: String,
    pub role: String,
    pub decision: String,
    pub applicable_gate_result: String,
    pub rollout_path: String,
    pub rollout_path_bytes_b64: String,
    pub rollout_path_sha256: String,
    pub rollout_file_sha256: String,
    pub record_line: usize,
    pub record_byte_offset: usize,
    pub record_byte_length: usize,
    pub record_bytes_b64: String,
    pub record_sha256: String,
    pub stable_record_id: String,
}

fn error(code: &str, detail: impl Into<String>) -> ArchiveError {
    ArchiveError::new(code, detail)
}

fn sha256(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn is_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn uuid_pattern() -> &'static regex::Regex {
    static UUID: OnceLock<regex::Regex> = OnceLock::new();
    UUID.get_or_init(|| {
        regex::Regex::new(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
            .expect("static UUID regex")
    })
}

fn rollout_pattern() -> &'static regex::Regex {
    static ROLLOUT: OnceLock<regex::Regex> = OnceLock::new();
    ROLLOUT.get_or_init(|| {
        regex::Regex::new(r"^rollout-(?P<timestamp>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:+.\-]+Z?)-(?P<context>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$")
            .expect("static rollout regex")
    })
}

fn rollout_identity(path: &Path) -> Option<(String, String)> {
    let captures = rollout_pattern().captures(path.file_name()?.to_str()?)?;
    let timestamp = captures.name("timestamp")?.as_str();
    let normalized = timestamp.strip_suffix('Z').unwrap_or(timestamp);
    let (date, time) = normalized.split_once('T')?;
    let time = if time.contains(':') {
        time.to_owned()
    } else {
        let rest = time.get(8..)?;
        format!(
            "{}:{}:{}{}",
            time.get(..2)?,
            time.get(3..5)?,
            time.get(6..8)?,
            rest
        )
    };
    let has_offset = time
        .get(8..)
        .is_some_and(|tail| tail.contains('+') || tail.contains('-'));
    let value = if has_offset {
        format!("{date}T{time}")
    } else {
        format!("{date}T{time}Z")
    };
    let parsed = OffsetDateTime::parse(&value, &Rfc3339).ok()?;
    Some((
        parsed.date().to_string(),
        captures.name("context")?.as_str().to_owned(),
    ))
}

fn session_root() -> Result<PathBuf, ArchiveError> {
    let value = std::env::var(SESSION_ROOT_ENV).unwrap_or_default();
    let value = value.trim();
    if value.is_empty() {
        return Err(error(
            "context_source_absent",
            "no Codex session root exists",
        ));
    }
    let path = PathBuf::from(value);
    if !path.is_absolute() {
        return Err(error(
            "context_source_absent",
            "session root is not absolute",
        ));
    }
    let root = fs::canonicalize(&path)
        .map_err(|detail| error("context_source_absent", detail.to_string()))?;
    if !fs::symlink_metadata(&root)
        .map_err(|detail| error("context_source_absent", detail.to_string()))?
        .is_dir()
    {
        return Err(error(
            "context_source_absent",
            "session root is not a directory",
        ));
    }
    Ok(root)
}

fn directory_names(path: &Path, pattern: &regex::Regex) -> Result<Vec<PathBuf>, ArchiveError> {
    let entries =
        fs::read_dir(path).map_err(|detail| error("source_unavailable", detail.to_string()))?;
    let mut result = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|detail| error("source_unavailable", detail.to_string()))?;
        let entry_path = entry.path();
        let metadata = fs::symlink_metadata(&entry_path)
            .map_err(|detail| error("source_unavailable", detail.to_string()))?;
        if metadata.is_dir()
            && !metadata.file_type().is_symlink()
            && entry
                .file_name()
                .to_str()
                .is_some_and(|name| pattern.is_match(name))
        {
            result.push(entry_path);
        }
    }
    result.sort_by_key(|path| path.file_name().unwrap_or_default().to_os_string());
    Ok(result)
}

fn rollout_files(root: &Path, context_id: &str) -> Result<Vec<PathBuf>, ArchiveError> {
    let year = regex::Regex::new(r"^[0-9]{4}$").unwrap();
    let month_day = regex::Regex::new(r"^[0-9]{2}$").unwrap();
    let mut files = Vec::new();
    for year_path in directory_names(root, &year)? {
        let year_name = year_path
            .file_name()
            .unwrap()
            .to_string_lossy()
            .into_owned();
        for month_path in directory_names(&year_path, &month_day)? {
            let month_name = month_path
                .file_name()
                .unwrap()
                .to_string_lossy()
                .into_owned();
            for day_path in directory_names(&month_path, &month_day)? {
                let day_name = day_path.file_name().unwrap().to_string_lossy().into_owned();
                for entry in fs::read_dir(&day_path)
                    .map_err(|detail| error("source_unavailable", detail.to_string()))?
                {
                    let entry =
                        entry.map_err(|detail| error("source_unavailable", detail.to_string()))?;
                    let path = entry.path();
                    let metadata = fs::symlink_metadata(&path)
                        .map_err(|detail| error("source_unavailable", detail.to_string()))?;
                    if !metadata.is_file() || metadata.file_type().is_symlink() {
                        continue;
                    }
                    let Some((date, identity)) = rollout_identity(&path) else {
                        continue;
                    };
                    if identity == context_id
                        && date == format!("{year_name}-{month_name}-{day_name}")
                    {
                        let resolved = fs::canonicalize(&path)
                            .map_err(|detail| error("source_unavailable", detail.to_string()))?;
                        if resolved.starts_with(root) {
                            files.push(resolved);
                        }
                    }
                }
            }
        }
    }
    files.sort_by_key(|path| path.to_string_lossy().into_owned());
    files.dedup();
    Ok(files)
}

fn source_records(bytes: &[u8]) -> Vec<SourceRecord> {
    let mut records = Vec::new();
    let mut offset = 0;
    for (index, raw) in bytes.split_inclusive(|byte| *byte == b'\n').enumerate() {
        let line = index + 1;
        let length = raw.len();
        if raw.ends_with(b"\n") {
            if let Ok(value) = serde_json::from_slice::<Value>(&raw[..length - 1]) {
                if value.is_object() {
                    records.push(SourceRecord {
                        line,
                        offset,
                        bytes: raw.to_vec(),
                        value,
                    });
                }
            }
        }
        offset += length;
    }
    records
}

fn find_record<'a>(
    records: &'a [SourceRecord],
    descriptor: &RecordRange,
) -> Result<&'a SourceRecord, ArchiveError> {
    let matches = records
        .iter()
        .filter(|record| {
            record.line == descriptor.line
                && record.offset == descriptor.byte_offset
                && record.bytes.len() == descriptor.byte_length
                && sha256(&record.bytes) == descriptor.record_sha256
        })
        .collect::<Vec<_>>();
    if matches.len() != 1 {
        return Err(error(
            "source_identity_mismatch",
            "certificate record range is not unique",
        ));
    }
    Ok(matches[0])
}

fn active_run(context: &ArchiveContext, run_id: &str) -> Result<PathBuf, ArchiveError> {
    if run_id.is_empty()
        || matches!(run_id, "." | "..")
        || run_id.contains('/')
        || run_id.contains('\\')
    {
        return Err(error("run_id_invalid", run_id));
    }
    let pointer = context.source_root.join(ACTIVE_RUN_POINTER);
    let value = fs::read_to_string(&pointer)
        .map_err(|_| error("source_unavailable", "active run pointer is absent"))?;
    let value = value.trim();
    if value.is_empty() {
        return Err(error("source_unavailable", "active run pointer is empty"));
    }
    let active = PathBuf::from(value);
    let active = if active.is_absolute() {
        active
    } else {
        pointer.parent().unwrap().join(active)
    };
    let active = fs::canonicalize(active)
        .map_err(|_| error("source_unavailable", "active run directory is absent"))?;
    let expected = fs::canonicalize(context.source_root.join("reports/agents").join(run_id))
        .map_err(|_| error("source_unavailable", "active run directory is absent"))?;
    if active != expected || !active.is_dir() {
        return Err(error(
            "source_identity_mismatch",
            "run id does not match the active run pointer",
        ));
    }
    Ok(active)
}

fn identity(context: &ArchiveContext) -> Result<(String, String), ArchiveError> {
    let run = |arg: &str| {
        Command::new("git")
            .arg("-C")
            .arg(&context.source_root)
            .args(["rev-parse", "--verify", arg])
            .output()
            .map_err(|detail| error("source_identity_mismatch", detail.to_string()))
    };
    let head = run("HEAD")?;
    let tree = run("HEAD^{tree}")?;
    let head = String::from_utf8_lossy(&head.stdout).trim().to_owned();
    let tree = String::from_utf8_lossy(&tree.stdout).trim().to_owned();
    if !is_hex(&head, 40) || !is_hex(&tree, 40) {
        return Err(error(
            "source_identity_mismatch",
            "source Git HEAD/tree identity is unavailable",
        ));
    }
    Ok((head, tree))
}

fn render(value: &Certificate) -> Result<Vec<u8>, ArchiveError> {
    let mut bytes = serde_json::to_vec(value)
        .map_err(|detail| error("context_schema_invalid", detail.to_string()))?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn publish(context: &ArchiveContext, target: &Path, bytes: &[u8]) -> Result<(), ArchiveError> {
    let root = context.source_root.clone();
    let parent = ParentRootAttestor::new()
        .attest(&AttestationRequest {
            cwd: root.clone(),
            explicit_root: Some(root),
            source_root: None,
            clone_root: None,
            topic_marker: None,
            gitmodules: None,
            owner_evidence: None,
            expected_remote: None,
            expected_module_digest: None,
            child_handoff_token: None,
            purpose: NonEmptyTrimmedString::new("runtime-context-publication")
                .map_err(|detail| error("context_publication_failure", detail.to_string()))?,
            nonce: Nonce128::generate()
                .map_err(|detail| error("context_publication_failure", detail.to_string()))?,
        })
        .map_err(|detail| error("context_publication_failure", detail.to_string()))?;
    match parent
        .publish_parent_owned_file_noreplace(
            target,
            bytes,
            NonEmptyTrimmedString::new("runtime-context-publication")
                .map_err(|detail| error("context_publication_failure", detail.to_string()))?,
        )
        .map_err(|detail| error("context_publication_failure", detail.to_string()))?
    {
        agent_canon::authority::ParentOwnedNoReplaceOutcome::Published(_) => Ok(()),
        agent_canon::authority::ParentOwnedNoReplaceOutcome::Duplicate(_) => Ok(()),
        agent_canon::authority::ParentOwnedNoReplaceOutcome::Conflict(_) => Err(error(
            "context_record_collision",
            "publication target collision",
        )),
    }
}

pub(super) fn append(
    context: &ArchiveContext,
    options: &CommandOptions,
) -> Result<i32, ArchiveError> {
    let run_id = options.required("run-id")?;
    let context_id = options.required("agent-context-id")?;
    let turn_id = options.required("turn-id")?;
    if !uuid_pattern().is_match(context_id) || !uuid_pattern().is_match(turn_id) {
        return Err(error(
            "source_identity_mismatch",
            "context or turn selector is not a UUID",
        ));
    }
    let active = active_run(context, run_id)?;
    let session_root = session_root()?;
    let files = rollout_files(&session_root, context_id)?;
    if files.is_empty() {
        return Err(error(
            "context_source_absent",
            "no rollout file matches the context selector",
        ));
    }
    if files.len() != 1 {
        return Err(error(
            "context_source_ambiguous",
            "rollout path is not unique for the context selector",
        ));
    }
    let path = &files[0];
    let file_bytes =
        fs::read(path).map_err(|detail| error("source_unavailable", detail.to_string()))?;
    let records = source_records(&file_bytes);
    let mut sessions = Vec::new();
    let mut completions = Vec::new();
    for record in records {
        let Some(object) = record.value.as_object() else {
            continue;
        };
        match object.get("type").and_then(Value::as_str) {
            Some("session_meta") => {
                let payload = object
                    .get("payload")
                    .and_then(Value::as_object)
                    .ok_or_else(|| {
                        error(
                            "context_schema_invalid",
                            "session_meta payload is not an object",
                        )
                    })?;
                let get = |name: &str| payload.get(name).and_then(Value::as_str).unwrap_or("");
                let agent_id = get("id");
                let parent_id = get("parent_thread_id");
                let role = get("agent_role");
                let cwd = get("cwd");
                if !uuid_pattern().is_match(agent_id)
                    || !uuid_pattern().is_match(parent_id)
                    || role.is_empty()
                    || cwd.is_empty()
                {
                    return Err(error(
                        "context_schema_invalid",
                        "session_meta native identity is invalid",
                    ));
                }
                let spawn = payload
                    .get("source")
                    .and_then(Value::as_object)
                    .and_then(|source| source.get("subagent"))
                    .and_then(Value::as_object)
                    .and_then(|subagent| subagent.get("thread_spawn"))
                    .and_then(Value::as_object)
                    .ok_or_else(|| {
                        error(
                            "context_schema_invalid",
                            "session_meta thread_spawn is absent",
                        )
                    })?;
                if spawn.get("parent_thread_id").and_then(Value::as_str) != Some(parent_id)
                    || spawn.get("agent_role").and_then(Value::as_str) != Some(role)
                {
                    return Err(error(
                        "source_identity_mismatch",
                        "session_meta structural joins do not match",
                    ));
                }
                if agent_id != context_id {
                    return Err(error(
                        "source_identity_mismatch",
                        "session_meta id does not match selector",
                    ));
                }
                let parent_id = parent_id.to_owned();
                let role = role.to_owned();
                let cwd = cwd.to_owned();
                sessions.push((record, parent_id, role, cwd));
            }
            Some("event_msg") => {
                let payload = object.get("payload").and_then(Value::as_object);
                if payload
                    .and_then(|value| value.get("type"))
                    .and_then(Value::as_str)
                    == Some("task_complete")
                {
                    let native_turn = payload
                        .and_then(|value| value.get("turn_id"))
                        .and_then(Value::as_str)
                        .unwrap_or("");
                    if !uuid_pattern().is_match(native_turn) {
                        return Err(error(
                            "context_schema_invalid",
                            "task_complete turn id is invalid",
                        ));
                    }
                    if native_turn == turn_id {
                        completions.push(record);
                    }
                }
            }
            _ => {}
        }
    }
    if sessions.is_empty() {
        return Err(error(
            "context_source_absent",
            "native session_meta record is absent",
        ));
    }
    if sessions.len() != 1 {
        return Err(error(
            "context_source_ambiguous",
            "native session_meta record is not unique",
        ));
    }
    if completions.is_empty() {
        return Err(error(
            "source_identity_mismatch",
            "selected task_complete record is absent",
        ));
    }
    if completions.len() != 1 {
        return Err(error(
            "context_source_ambiguous",
            "selected task_complete record is not unique",
        ));
    }
    let (session, parent_id, role, cwd) = sessions.remove(0);
    let task = completions.remove(0);
    if session.line == 0 || task.line == 0 {
        return Err(error(
            "source_identity_mismatch",
            "rollout record is invalid",
        ));
    }
    if rollout_identity(path)
        .as_ref()
        .map(|identity| identity.1.as_str())
        != Some(context_id)
    {
        return Err(error(
            "source_identity_mismatch",
            "rollout filename does not match context selector",
        ));
    }
    let path_text = path
        .to_str()
        .ok_or_else(|| error("source_identity_mismatch", "rollout path is not UTF-8"))?;
    let path_bytes = path_text.as_bytes();
    let record_sha = sha256(&task.bytes);
    let (head_oid, tree_oid) = identity(context)?;
    let root_bytes = context.source_root.to_str().unwrap_or_default().as_bytes();
    let mut certificate = Certificate {
        schema: CERTIFICATE_SCHEMA.to_owned(),
        certificate_id: "0".repeat(64),
        context: CertificateContext {
            schema: CONTEXT_SCHEMA.to_owned(),
            agent_id: context_id.to_owned(),
            agent_context_id: context_id.to_owned(),
            codex_thread_id: context_id.to_owned(),
            parent_id,
            turn_id: turn_id.to_owned(),
            role,
        },
        repository: RepositoryIdentity {
            root: context.source_root.to_str().unwrap_or_default().to_owned(),
            root_path_sha256: sha256(root_bytes),
            head_oid,
            tree_oid,
        },
        rollout: RolloutIdentity {
            path: path_text.to_owned(),
            path_sha256: sha256(path_bytes),
            file_sha256: sha256(&file_bytes),
            session_cwd: cwd,
            session_meta: RecordRange {
                line: session.line,
                byte_offset: session.offset,
                byte_length: session.bytes.len(),
                record_sha256: sha256(&session.bytes),
            },
            task_complete: RecordRange {
                line: task.line,
                byte_offset: task.offset,
                byte_length: task.bytes.len(),
                record_sha256: record_sha.clone(),
            },
        },
    };
    let mut preimage = b"agent_canon.context_discovery_certificate.v1\0".to_vec();
    preimage.extend_from_slice(&render(&certificate)?);
    certificate.certificate_id = sha256(&preimage);
    let bytes = render(&certificate)?;
    let target = active.join(format!(
        "context_discovery.{}.json",
        certificate.certificate_id
    ));
    publish(context, &target, &bytes)?;
    let relative = target
        .strip_prefix(&context.source_root)
        .map_err(|_| {
            error(
                "context_publication_failure",
                "certificate path escapes source root",
            )
        })?
        .to_str()
        .ok_or_else(|| {
            error(
                "context_publication_failure",
                "certificate path is not UTF-8",
            )
        })?;
    println!("CONTEXT_DISCOVERY_PATH={relative}");
    println!(
        "CONTEXT_DISCOVERY_CERTIFICATE_ID={}",
        certificate.certificate_id
    );
    println!("CONTEXT_DISCOVERY_RECORD_SHA256={record_sha}");
    println!("CONTEXT_DISCOVERY_APPEND=pass");
    Ok(0)
}

pub(super) fn load_source_event(
    context: &ArchiveContext,
    active: &Path,
) -> Result<RuntimeEventSource, ArchiveError> {
    static NAME: OnceLock<regex::Regex> = OnceLock::new();
    let name = NAME.get_or_init(|| {
        regex::Regex::new(r"^context_discovery\.(?P<id>[0-9a-f]{64})\.json$")
            .expect("static context certificate name regex")
    });
    let mut candidates = Vec::new();
    for entry in
        fs::read_dir(active).map_err(|detail| error("source_unavailable", detail.to_string()))?
    {
        let entry = entry.map_err(|detail| error("source_unavailable", detail.to_string()))?;
        if name.is_match(&entry.file_name().to_string_lossy()) {
            candidates.push(entry.path());
        }
    }
    candidates.sort_by_key(|path| path.file_name().unwrap_or_default().to_os_string());
    if candidates.is_empty() {
        return Err(error(
            "context_source_absent",
            "context discovery certificate is absent",
        ));
    }
    if candidates.len() != 1 {
        return Err(error(
            "context_source_ambiguous",
            "context discovery certificate is not unique",
        ));
    }
    let certificate_path = &candidates[0];
    let metadata = fs::symlink_metadata(certificate_path)
        .map_err(|detail| error("source_unavailable", detail.to_string()))?;
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err(error(
            "context_schema_invalid",
            "context discovery certificate is not a regular file",
        ));
    }
    let raw = fs::read(certificate_path)
        .map_err(|detail| error("source_unavailable", detail.to_string()))?;
    if !raw.ends_with(b"\n") || raw[..raw.len().saturating_sub(1)].contains(&b'\n') {
        return Err(error(
            "context_schema_invalid",
            "context certificate must be one JSON line",
        ));
    }
    let certificate: Certificate = serde_json::from_slice(&raw[..raw.len() - 1]).map_err(|_| {
        error(
            "context_schema_invalid",
            "context certificate JSON is invalid",
        )
    })?;
    if render(&certificate)? != raw || certificate.schema != CERTIFICATE_SCHEMA {
        return Err(error(
            "context_schema_invalid",
            "context certificate bytes are not canonical",
        ));
    }
    if certificate.context.schema != CONTEXT_SCHEMA
        || !uuid_pattern().is_match(&certificate.context.agent_id)
        || !uuid_pattern().is_match(&certificate.context.agent_context_id)
        || !uuid_pattern().is_match(&certificate.context.codex_thread_id)
        || !uuid_pattern().is_match(&certificate.context.parent_id)
        || !uuid_pattern().is_match(&certificate.context.turn_id)
        || certificate.context.agent_id != certificate.context.agent_context_id
        || certificate.context.agent_context_id != certificate.context.codex_thread_id
        || certificate.context.role.is_empty()
    {
        return Err(error(
            "context_schema_invalid",
            "context certificate context identity is invalid",
        ));
    }
    let filename = certificate_path.file_name().unwrap().to_string_lossy();
    let filename_id = name
        .captures(&filename)
        .and_then(|captures| captures.name("id"))
        .map(|value| value.as_str())
        .ok_or_else(|| {
            error(
                "context_schema_invalid",
                "context certificate filename is invalid",
            )
        })?;
    if filename_id != certificate.certificate_id || !is_hex(filename_id, 64) {
        return Err(error(
            "source_identity_mismatch",
            "certificate filename id differs",
        ));
    }
    let mut preimage = certificate;
    let expected_id = preimage.certificate_id.clone();
    preimage.certificate_id = "0".repeat(64);
    let mut bytes = b"agent_canon.context_discovery_certificate.v1\0".to_vec();
    bytes.extend_from_slice(&render(&preimage)?);
    if sha256(&bytes) != expected_id {
        return Err(error(
            "context_schema_invalid",
            "context certificate id does not cover canonical bytes",
        ));
    }

    if preimage.repository.root != context.source_root.to_string_lossy()
        || preimage.repository.root_path_sha256
            != sha256(context.source_root.to_string_lossy().as_bytes())
    {
        return Err(error(
            "source_identity_mismatch",
            "certificate repository path identity differs",
        ));
    }
    let (head, tree) = identity(context)?;
    if preimage.repository.head_oid != head || preimage.repository.tree_oid != tree {
        return Err(error(
            "source_identity_mismatch",
            "certificate repository Git identity differs",
        ));
    }
    let session_root = session_root()?;
    let rollout_path = PathBuf::from(&preimage.rollout.path);
    let resolved = fs::canonicalize(&rollout_path).map_err(|_| {
        error(
            "source_unavailable",
            "certificate rollout path is unavailable",
        )
    })?;
    if resolved != rollout_path
        || !resolved.starts_with(&session_root)
        || rollout_identity(&resolved)
            .as_ref()
            .map(|identity| identity.1.as_str())
            != Some(preimage.context.agent_context_id.as_str())
    {
        return Err(error(
            "source_identity_mismatch",
            "certificate rollout path identity differs",
        ));
    }
    let eligible = rollout_files(&session_root, &preimage.context.agent_context_id)?;
    if eligible.len() != 1 || eligible[0] != resolved {
        return Err(error(
            "context_source_ambiguous",
            "certificate rollout is absent or not unique",
        ));
    }
    let file_bytes =
        fs::read(&resolved).map_err(|detail| error("source_unavailable", detail.to_string()))?;
    let path_bytes = resolved.to_string_lossy().as_bytes().to_vec();
    if sha256(&path_bytes) != preimage.rollout.path_sha256
        || sha256(&file_bytes) != preimage.rollout.file_sha256
    {
        return Err(error(
            "source_identity_mismatch",
            "certificate rollout bytes differ",
        ));
    }
    let records = source_records(&file_bytes);
    let session_record = find_record(&records, &preimage.rollout.session_meta)?;
    let task_record = find_record(&records, &preimage.rollout.task_complete)?;
    let session_payload = session_record
        .value
        .get("payload")
        .and_then(Value::as_object)
        .ok_or_else(|| {
            error(
                "source_identity_mismatch",
                "session_meta payload is invalid",
            )
        })?;
    let session_id = session_payload
        .get("id")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let parent_id = session_payload
        .get("parent_thread_id")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let role = session_payload
        .get("agent_role")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let cwd = session_payload
        .get("cwd")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let spawn = session_payload
        .get("source")
        .and_then(Value::as_object)
        .and_then(|source| source.get("subagent"))
        .and_then(Value::as_object)
        .and_then(|subagent| subagent.get("thread_spawn"))
        .and_then(Value::as_object)
        .ok_or_else(|| {
            error(
                "source_identity_mismatch",
                "session_meta thread_spawn is absent",
            )
        })?;
    if session_id != preimage.context.agent_context_id
        || parent_id != preimage.context.parent_id
        || role != preimage.context.role
        || cwd != preimage.rollout.session_cwd
        || spawn.get("parent_thread_id").and_then(Value::as_str) != Some(parent_id)
        || spawn.get("agent_role").and_then(Value::as_str) != Some(role)
        || task_record.value.get("type").and_then(Value::as_str) != Some("event_msg")
        || task_record
            .value
            .get("payload")
            .and_then(|payload| payload.get("type"))
            .and_then(Value::as_str)
            != Some("task_complete")
        || task_record
            .value
            .get("payload")
            .and_then(|payload| payload.get("turn_id"))
            .and_then(Value::as_str)
            != Some(preimage.context.turn_id.as_str())
    {
        return Err(error(
            "source_identity_mismatch",
            "certificate native joins differ",
        ));
    }
    let session_count = records
        .iter()
        .filter(|record| record.value.get("type").and_then(Value::as_str) == Some("session_meta"))
        .count();
    let task_count = records
        .iter()
        .filter(|record| {
            record.value.get("type").and_then(Value::as_str) == Some("event_msg")
                && record
                    .value
                    .get("payload")
                    .and_then(|payload| payload.get("type"))
                    .and_then(Value::as_str)
                    == Some("task_complete")
                && record
                    .value
                    .get("payload")
                    .and_then(|payload| payload.get("turn_id"))
                    .and_then(Value::as_str)
                    == Some(preimage.context.turn_id.as_str())
        })
        .count();
    for record in &records {
        if record.value.get("type").and_then(Value::as_str) == Some("event_msg")
            && record
                .value
                .get("payload")
                .and_then(|payload| payload.get("type"))
                .and_then(Value::as_str)
                == Some("task_complete")
        {
            let turn_id = record
                .value
                .get("payload")
                .and_then(|payload| payload.get("turn_id"))
                .and_then(Value::as_str)
                .unwrap_or_default();
            if !uuid_pattern().is_match(turn_id) {
                return Err(error(
                    "context_schema_invalid",
                    "task_complete turn id is invalid",
                ));
            }
        }
    }
    if session_count != 1 {
        return Err(error(
            "context_source_ambiguous",
            "session_meta record is no longer unique",
        ));
    }
    if task_count != 1 {
        return Err(error(
            "context_source_ambiguous",
            "selected task_complete record is no longer unique",
        ));
    }
    let record_sha = preimage.rollout.task_complete.record_sha256.clone();
    Ok(RuntimeEventSource {
        agent_id: preimage.context.agent_id,
        agent_context_id: preimage.context.agent_context_id,
        codex_thread_id: preimage.context.codex_thread_id,
        parent_id: preimage.context.parent_id,
        turn_id: preimage.context.turn_id,
        role: preimage.context.role,
        decision: "NONE".to_owned(),
        applicable_gate_result: String::new(),
        rollout_path: preimage.rollout.path,
        rollout_path_bytes_b64: STANDARD.encode(&path_bytes),
        rollout_path_sha256: preimage.rollout.path_sha256,
        rollout_file_sha256: preimage.rollout.file_sha256,
        record_line: preimage.rollout.task_complete.line,
        record_byte_offset: preimage.rollout.task_complete.byte_offset,
        record_byte_length: preimage.rollout.task_complete.byte_length,
        record_bytes_b64: STANDARD.encode(&task_record.bytes),
        record_sha256: record_sha.clone(),
        stable_record_id: record_sha,
    })
}

#[cfg(test)]
mod tests {
    use super::rollout_identity;
    use std::path::Path;

    #[test]
    fn rollout_names_are_date_scoped_and_context_bound() {
        assert_eq!(
            rollout_identity(Path::new(
                "rollout-2026-11-13T09-27-36Z-11111111-1111-4111-8111-111111111111.jsonl",
            )),
            Some((
                "2026-11-13".to_owned(),
                "11111111-1111-4111-8111-111111111111".to_owned(),
            ))
        );
        assert!(rollout_identity(Path::new(
            "rollout-2026-13-45T99-99-99Z-11111111-1111-4111-8111-111111111111.jsonl"
        ))
        .is_none());
        assert!(rollout_identity(Path::new(
            "rollout-2026-11-13T09-27-36Z-11111111-1111-4111-8111-111111111111.jsonl.bak"
        ))
        .is_none());
    }
}
